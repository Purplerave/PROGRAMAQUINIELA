"""Motor de predicción para partidos de jornada.

Conecta PREDECIR_JORNADA con MOTOR_QUINIELA_MAESTRO para obtener
probabilidades reales del modelo entrenado, evitando la dependencia
de APU/LAE/Q15 como fuente principal.

Este módulo:
- Carga el histórico para calcular features rodantes (sin fuga temporal)
- Entrena sobre un histórico anterior al corte
- Genera probabilidades 1/X/2 por partido
- Devuelve un contrato JSON estable por jornada
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import settings

from MOTOR_QUINIELA_MAESTRO import (
    LABEL_MAP,
    _attach_calibracion_bandas,
    apply_hybrid_config,
    fit_hybrid_models,
    hybrid_inputs,
    load_raw_history,
)
from scripts.json_output import write_json
from scripts.motor.boletos import load_jornada_json as load_jornada_json, validate_jornada
from scripts.motor.features import (
    compute_features_for_upcoming,
    infer_season,
    rolling_team_features,
)
from scripts.motor.odds_at_cutoff import kickoff_at, odds_at_cutoff
from scripts.motor.temporal import history_before, local_timestamp, utc_timestamp
from scripts.motor.transition_priors import load_transition_priors

# Pleno al 15: buckets de goles del boleto oficial y umbral para sugerir doble
PLENO_BUCKET_LABELS = ("0", "1", "2", "M")
_PLENO_ALT_GAP = 0.10
# Lambdas de emergencia si ni features ni histórico ofrecen medias (no debería ocurrir)
_FALLBACK_LAMBDA_HOME = 1.45
_FALLBACK_LAMBDA_AWAY = 1.10

def _train_models(history_df: pd.DataFrame, cutoff_date: object) -> tuple:
    """Entrena solo con resultados anteriores al día del corte y pesos congelados.

    No reutiliza modelos globales: una segunda jornada puede tener otro corte
    o histórico. Vector scaling y búsqueda de pesos quedan en experimentos.
    """
    eligible = history_before(history_df, cutoff_date)
    features = rolling_team_features(eligible)
    train = features.loc[features["result"].isin(LABEL_MAP)].copy()
    train["target"] = train["result"].map(LABEL_MAP)
    if len(train) < 100 or train["target"].nunique() < len(LABEL_MAP):
        raise ValueError(f"Histórico anterior al corte insuficiente: {len(train)} partidos; se requieren al menos 100 y los tres resultados")
    logit, hgb, config = fit_hybrid_models(train, selection_mode="production")
    return logit, hgb, config, train


def normalize_name(value: str) -> str:
    """Normaliza el nombre de un equipo para comparación."""
    import unicodedata
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().replace(".", "").split())


def _calculate_confidence(probs: dict[str, float]) -> float:
    """Calcula un índice de confianza (0-1) basado en la entropía de las probabilidades."""
    # Manejar ambos formatos: {"1": x} o {"prob_1": x}
    ps = [probs.get(sign, probs.get(alias, 0.0)) for sign, alias in (("1", "prob_1"), ("X", "prob_x"), ("2", "prob_2"))]
    total = sum(ps)
    if total <= 0:
        return 0.0
    entropy = -sum((p / total) * math.log(p / total) for p in ps if p > 0)
    return round(max(0.0, 1 - entropy / math.log(3)), 4)


def _check_data_quality(feat_row: pd.Series) -> dict[str, Any]:
    """Verifica la calidad de datos disponibles para un partido."""
    warnings = []
    quality_score = 1.0

    # Verificar cuotas de mercado
    if not bool(pd.notna(feat_row.get("market_1"))):
        warnings.append("sin_cuotas_mercado")
        quality_score -= 0.3

    # Verificar histórico de equipo local
    if feat_row.get("home_table_pj", 0) == 0:
        warnings.append("sin_partidos_local")
        quality_score -= 0.2

    # Verificar histórico de equipo visitante
    if feat_row.get("away_table_pj", 0) == 0:
        warnings.append("sin_partidos_visitante")
        quality_score -= 0.2

    # Verificar Elo
    if feat_row.get("home_elo", 1500) == 1500 and feat_row.get("away_elo", 1500) == 1500:
        warnings.append("equipos_sin_elo")
        quality_score -= 0.15

    # Verificar forma reciente
    if pd.isna(feat_row.get("home_form_pts_5")):
        warnings.append("sin_forma_local")
        quality_score -= 0.1

    return {
        "warnings": warnings,
        "quality_score": round(max(0.0, quality_score), 2),
        "is_complete": len(warnings) == 0,
    }


def _in_model_domain(row: pd.Series, match: dict) -> bool:
    return not match.get("liga_f", False) and row["division"] in ("Primera", "Segunda") and all(
        pd.notna(row.get(f"{side}_form_pts_5")) for side in ("home", "away")
    )


def _apply_transition_priors(features_df: pd.DataFrame, cutoff_date: object) -> pd.DataFrame:
    """Aplica priors de transición a equipos con poca muestra en la temporada actual.

    Punto 5 Codex: Respetar la temporada y aplicar explícitamente los priors de transición.
    Punto 5 Codex (Rev 2): No añadir heurísticas de Elo nuevas no validadas.

    La búsqueda de priors acepta nombres comunes de jornada ("Malaga CF",
    "Castellón") traduciéndolos al nombre canónico del fichero de priors
    ("Malaga CF", "CD Castellon") mediante scripts/motor/team_names.
    """
    from scripts.motor.team_names import resolve_prior_name

    target_season, teams_priors, _ = load_transition_priors(cutoff_date)
    if not teams_priors:
        return features_df

    features_df = features_df.copy()
    normalized_priors = {normalize_name(k): v for k, v in teams_priors.items()}
    for idx, row in features_df.loc[features_df["season"].eq(target_season)].iterrows():
        for side in ["home", "away"]:
            pj_col = f"{side}_table_pj"
            ppg_col = f"{side}_table_ppg"
            pj = row.get(pj_col, 0)

            # Si hay menos de 3 partidos en la temporada actual, usamos el prior
            if pj < 3:
                team_name = row.get(side)
                # 1) Traducción por alias al nombre canónico del fichero de priors
                canonical = resolve_prior_name(team_name)
                prior = teams_priors.get(canonical) if canonical else None
                # 2) Fallback: coincidencia normalizada directa (comportamiento anterior)
                if prior is None:
                    prior = normalized_priors.get(normalize_name(team_name))
                if prior:
                    adj_ppg = prior.get("context", {}).get("adjusted_ppg")
                    if adj_ppg is not None:
                        # Mezcla lineal: 0 partidos = 100% prior, 3 partidos = 0% prior
                        weight = max(0.0, pj) / 3.0
                        current_ppg = row.get(ppg_col, 0) if pd.notna(row.get(ppg_col)) else 0.0
                        new_ppg = (weight * current_ppg) + ((1.0 - weight) * adj_ppg)
                        features_df.at[idx, ppg_col] = new_ppg

    # Recalcular diferencias basadas en los nuevos valores
    if "home_table_ppg" in features_df.columns and "away_table_ppg" in features_df.columns:
        features_df["table_ppg_diff"] = features_df["home_table_ppg"] - features_df["away_table_ppg"]

    return features_df


# ---------------------------------------------------------------------------
# Pleno al 15 (Dixon-Coles, T4)
# ---------------------------------------------------------------------------

def _pleno_bucket_label(goals: int) -> str:
    """Bucket oficial del Pleno al 15: 0, 1, 2 o M (3 o más goles)."""
    return str(goals) if goals < 3 else "M"


def _pleno_bucket_probs(score_probs: np.ndarray) -> dict[str, float]:
    """Agrupa la matriz de Dixon-Coles en los 16 signos conjuntos oficiales."""
    joint = {f"{h}-{a}": 0.0 for h in PLENO_BUCKET_LABELS for a in PLENO_BUCKET_LABELS}
    for (hg, ag), prob in np.ndenumerate(score_probs):
        joint[f"{_pleno_bucket_label(hg)}-{_pleno_bucket_label(ag)}"] += float(prob)
    return joint


def _pleno_alternative(bucket_probs: dict[str, float], selected: str) -> str | None:
    alternatives = {bucket: p for bucket, p in bucket_probs.items() if bucket != selected}
    second = max(alternatives, key=alternatives.get)
    return second if abs(bucket_probs[selected] - alternatives[second]) < _PLENO_ALT_GAP else None


def _league_mean_lambdas(history_df: pd.DataFrame, cutoff_date: pd.Timestamp) -> tuple[float, float]:
    """Media histórica de goles por lado SOLO con partidos anteriores al corte.

    Se usa como sustituto controlado cuando un equipo no tiene historial
    (selecciones, ligas no cubiertas), de modo que el Pleno al 15 siempre
    produce una salida estable y documentada (lambdas_fuente).
    """
    hist = history_before(history_df, cutoff_date)
    mean_home = float(hist["FTHG"].mean()) if len(hist) else np.nan
    mean_away = float(hist["FTAG"].mean()) if len(hist) else np.nan
    if np.isnan(mean_home):
        mean_home = _FALLBACK_LAMBDA_HOME
    if np.isnan(mean_away):
        mean_away = _FALLBACK_LAMBDA_AWAY
    return mean_home, mean_away


def predict_pleno15_from_model(
    partido15: dict[str, Any],
    history_df: pd.DataFrame,
    jornada: int,
    cutoff_date: str | datetime,
) -> dict[str, Any]:
    """Predice el Pleno al 15 (marcador por buckets 0/1/2/M) con Dixon-Coles.

    Usa las mismas features point-in-time que el resto de la jornada
    (`compute_features_for_upcoming`, sin fuga temporal) y aplica el rho de
    `master_model.dixon_coles` de la config activa (validado walk-forward, T4).

    APU/LAE/Q15 y `marcadores_q15` NO se usan como entrada; se devuelven solo
    como referencia comparativa.

    Returns:
        Contrato JSON del Pleno al 15 con buckets, top marcadores, selección,
        confianza, calidad de datos y avisos.
    """
    from scripts.motor.dixon_coles import dc_score_probs

    cutoff_date = get_cutoff_date({"partidos": [partido15]}, cutoff_date)
    dc_cfg = settings.master_model_config().get("dixon_coles", {})
    if not isinstance(dc_cfg, dict):
        dc_cfg = {}
    use_dc = bool(dc_cfg.get("enabled", False)) and bool(dc_cfg.get("use_for_pleno", False))
    rho = float(dc_cfg.get("rho", 0.0)) if use_dc else 0.0
    max_goals = int(dc_cfg.get("max_goals", 7))

    local = partido15.get("local")
    visitante = partido15.get("visitante")
    kickoff = kickoff_at(partido15)
    fecha = local_timestamp(kickoff).normalize() if kickoff else None

    match = {
        "home": local,
        "away": visitante,
        "date": fecha if fecha is not None else local_timestamp(cutoff_date).normalize(),
        "division": partido15.get("division"),  # None -> se infiere del histórico
        "season": infer_season(fecha) if fecha else None,
        **odds_at_cutoff(partido15, cutoff_date)[0],
    }

    try:
        features_df = compute_features_for_upcoming(
            [match], history_before(history_df, cutoff_date), cutoff_date=local_timestamp(cutoff_date).normalize()
        )
    except Exception as exc:
        return {
            "jornada": jornada,
            "numero": 15,
            "local": local,
            "visitante": visitante,
            "disponible": False,
            "razon": f"error_features: {exc}",
        }

    if features_df.empty:
        return {
            "jornada": jornada,
            "numero": 15,
            "local": local,
            "visitante": visitante,
            "disponible": False,
            "razon": "sin_features",
        }

    feat_row = features_df.iloc[0]
    lambda_home = feat_row.get("lambda_home")
    lambda_away = feat_row.get("lambda_away")
    home_missing = pd.isna(lambda_home)
    away_missing = pd.isna(lambda_away)

    lambdas_fuente = "features_equipo"
    if home_missing or away_missing:
        mean_home, mean_away = _league_mean_lambdas(history_df, cutoff_date)
        if home_missing and away_missing:
            lambdas_fuente = "media_liga"
        else:
            lambdas_fuente = "parcial_media_liga"
        if home_missing:
            lambda_home = mean_home
        if away_missing:
            lambda_away = mean_away
    lambda_home = float(lambda_home)
    lambda_away = float(lambda_away)

    # Matriz de marcadores con Dixon-Coles (rho validado en T4) o Poisson
    score_probs = dc_score_probs(
        np.array([lambda_home]), np.array([lambda_away]), rho, max_goals=max_goals
    )[0]

    flat_idx = np.argsort(score_probs, axis=None)[::-1][:3]
    top_marcadores = []
    for idx in flat_idx:
        hg, ag = np.unravel_index(idx, score_probs.shape)
        top_marcadores.append({"score": f"{hg}-{ag}", "prob": round(float(score_probs[hg, ag]), 4)})

    joint = _pleno_bucket_probs(score_probs)
    signo_pleno = max(joint, key=joint.get)
    sel_local, sel_visitante = signo_pleno.split("-")
    goles_local = {h: sum(joint[f"{h}-{a}"] for a in PLENO_BUCKET_LABELS) for h in PLENO_BUCKET_LABELS}
    goles_visitante = {a: sum(joint[f"{h}-{a}"] for h in PLENO_BUCKET_LABELS) for a in PLENO_BUCKET_LABELS}
    alt_local = _pleno_alternative(goles_local, sel_local)
    alt_visitante = _pleno_alternative(goles_visitante, sel_visitante)

    quality = _check_data_quality(feat_row)
    avisos = list(quality["warnings"])
    calidad = quality["quality_score"]
    if lambdas_fuente != "features_equipo":
        avisos.append("lambdas_media_liga")
        calidad = round(max(0.0, calidad - 0.25), 2)

    model_domain = _in_model_domain(feat_row, partido15)
    if not model_domain:
        avisos.append("fuera_del_dominio_validado")

    return {
        "jornada": jornada,
        "numero": 15,
        "local": local,
        "visitante": visitante,
        "fecha": str(fecha)[:10] if fecha else None,
        "disponible": model_domain and calidad >= settings.config_section("decision_thresholds").get("calidad_min", 0.2),
        "modelo": "dixon_coles" if rho != 0.0 else "poisson_independiente",
        "rho": rho,
        "lambdas": {"local": round(lambda_home, 3), "visitante": round(lambda_away, 3)},
        "lambdas_fuente": lambdas_fuente,
        "marcador_predicho": top_marcadores[0]["score"],
        "marcador_confianza": top_marcadores[0]["prob"],
        "top_marcadores": top_marcadores,
        "goles_local": {k: round(p, 6) for k, p in goles_local.items()},
        "goles_visitante": {k: round(p, 6) for k, p in goles_visitante.items()},
        "goles_conjuntos": {k: round(p, 8) for k, p in joint.items()},
        "seleccion": {
            "local": sel_local,
            "visitante": sel_visitante,
            "alternativa_local": alt_local,
            "alternativa_visitante": alt_visitante,
            "confianza": round(joint[signo_pleno], 8),
            "nota": "Selección por probabilidad conjunta. Alternativa marginal a menos de "
                    f"{_PLENO_ALT_GAP:.2f} del primero.",
        },
        "avisos": avisos,
        "calidad_datos": calidad,
        "fuente_probabilidades": {
            "modelo_primario": "motor_maestro_pleno15",
            "detalle": "Lambdas point-in-time (forma gf/ga + tiros) con Dixon-Coles. "
                       "marcadores_q15 solo se adjunta como referencia, no se usa.",
        },
        "comparativa_marcadores_q15": partido15.get("marcadores_q15") or [],
    }


def predict_jornada_from_model(
    partidos: list[dict[str, Any]],
    history_df: pd.DataFrame,
    jornada: int,
    cutoff_date: str | datetime,
) -> dict[str, Any]:
    """Genera predicciones del modelo para una jornada completa.

    Args:
        partidos: Lista de partidos de la jornada (del JSON de jornada)
        history_df: DataFrame con el histórico para calcular features
        jornada: Número de jornada
        cutoff_date: Fecha de corte (partidos posteriores se ignoran)

    Returns:
        Diccionario con predicciones por partido y metadatos
    """
    cutoff_instant = get_cutoff_date({"partidos": partidos}, cutoff_date)
    cutoff_day = local_timestamp(cutoff_instant).normalize()

    # Normalizar partidos para la extracción de features
    normalized_matches = []
    partido15 = None
    for p in partidos:
        if p.get("num") == 15:
            # El Pleno al 15 se maneja aparte con Dixon-Coles (buckets de goles)
            partido15 = p
            continue

        # Respetar la temporada inferida de la fecha del partido
        kickoff = kickoff_at(p)
        fecha_partido = local_timestamp(kickoff).normalize() if kickoff else cutoff_day
        season = infer_season(fecha_partido)

        normalized_matches.append({
            "num": p.get("num"),
            "liga_f": p.get("liga_f", False),
            "home": p.get("local"),
            "away": p.get("visitante"),
            "date": fecha_partido,
            # Issue #35: no forzar "Primera" aquí. Si el boleto no trae
            # división, se propaga None y `normalize_upcoming_match` la
            # infiere por equipo desde el histórico (team_divisions).
            # Forzar Primera dejaba a Segunda con pj=0 silencioso.
            "division": (p.get("division") or None),
            "season": season,
            # Solo se entregan al motor cuotas completas y verificadas al corte.
            **odds_at_cutoff(p, cutoff_instant)[0],
        })

    # Pleno al 15 con Dixon-Coles (independiente del ensemble 1X2: solo lambdas)
    pleno15_pred = None
    if partido15 is not None:
        try:
            pleno15_pred = predict_pleno15_from_model(
                partido15, history_df, jornada, cutoff_instant
            )
        except Exception as e:
            pleno15_pred = {
                "jornada": jornada,
                "numero": 15,
                "local": partido15.get("local"),
                "visitante": partido15.get("visitante"),
                "disponible": False,
                "razon": f"error_pleno15: {e}",
            }

    if not normalized_matches:
        return {
            "jornada": jornada,
            "predicciones": [],
            "pleno15": pleno15_pred,
            "estado": "sin_partidos",
            "fecha_generacion": datetime.now().isoformat(timespec="seconds"),
        }

    # Extraer features rodantes para partidos futuros (sin fuga temporal)
    try:
        features_df = compute_features_for_upcoming(
            normalized_matches,
            history_before(history_df, cutoff_instant),
            cutoff_date=cutoff_day,
        )
        features_df = _apply_transition_priors(features_df, cutoff_instant)
    except Exception as e:
        return {
            "jornada": jornada,
            "error": f"Error calculando features: {e!s}",
            "pleno15": pleno15_pred,
            "fecha_generacion": datetime.now().isoformat(timespec="seconds"),
        }

    if features_df.empty:
        return {
            "jornada": jornada,
            "error": "No se pudieron calcular features para los partidos",
            "pleno15": pleno15_pred,
            "fecha_generacion": datetime.now().isoformat(timespec="seconds"),
        }

    try:
        logit, hgb, master_config, train = _train_models(history_df, cutoff_instant)
    except ValueError as exc:
        return {
            "jornada": jornada,
            "error": f"Error cargando modelos: {exc}",
            "pleno15": pleno15_pred,
            "fecha_generacion": datetime.now().isoformat(timespec="seconds"),
        }

    # Mismo cálculo 1X2 que en el backtest. El ajuste de bandas se estima una
    # vez por temporada, solo con datos previos; no usa factores de otra época.
    inputs = hybrid_inputs(features_df, logit, hgb)
    predictions = []
    for season, group in inputs.groupby("season", sort=False):
        config = _attach_calibracion_bandas(master_config, train, season)
        predictions.append(apply_hybrid_config(group, config, "modelo"))
    features_df = pd.concat(predictions).sort_index()
    calibration_meta = {"vector_scaling": False, "bandas": "estimadas_con_temporadas_previas"}

    # Combinar resultados
    results = []
    for idx, (_, feat_row) in enumerate(features_df.iterrows()):
        prob_1 = feat_row["modelo_prob_1"]
        prob_x = feat_row["modelo_prob_x"]
        prob_2 = feat_row["modelo_prob_2"]

        probs = {
            "prob_1": round(prob_1, 4),
            "prob_x": round(prob_x, 4),
            "prob_2": round(prob_2, 4),
        }

        # Verificar calidad de datos
        quality = _check_data_quality(feat_row)

        original = normalized_matches[idx]
        model_domain = _in_model_domain(feat_row, original)
        if not model_domain:
            quality["warnings"].append("fuera_del_dominio_validado")

        result = {
            "jornada": jornada,
            "numero": original["num"],
            "local": original["home"],
            "visitante": original["away"],
            "fecha": str(original["date"])[:10] if pd.notna(original["date"]) else None,
            "division": feat_row["division"],
            "dominio_validado": model_domain,
            **probs,
            "signo_modelo": feat_row["modelo_pred"],
            "confianza": _calculate_confidence(probs),
            "fuente_probabilidades": {
                "modelo_primario": "motor_maestro_hibrido",
                "componentes": {
                    "logit": master_config["weights"].get("logit", 0),
                    "hgb": master_config["weights"].get("hgb", 0),
                    "market": master_config["weights"].get("market", 0),
                    "poisson": master_config["weights"].get("poisson", 0),
                },
                "tiene_mercado_verificado": bool(pd.notna(feat_row.get("market_1"))),
                "draw_boost_aplicado": master_config.get("draw_boost", 0),
                "segunda_draw_boost_aplicado": master_config.get("segunda_draw_boost", 0),
                "x_disagreement_strategy": master_config.get("x_disagreement_strategy", "none"),
                "calibracion": {"aplicada": False, **calibration_meta},
            },
            "avisos": quality["warnings"],
            "calidad_datos": quality["quality_score"],
            "features_disponibles": {
                "home_elo": round(feat_row.get("home_elo", 1500), 1),
                "away_elo": round(feat_row.get("away_elo", 1500), 1),
                "home_table_pj": int(feat_row.get("home_table_pj", 0)),
                "away_table_pj": int(feat_row.get("away_table_pj", 0)),
                "home_form_pts_5": round(feat_row.get("home_form_pts_5", 0), 2) if pd.notna(feat_row.get("home_form_pts_5")) else None,
                "away_form_pts_5": round(feat_row.get("away_form_pts_5", 0), 2) if pd.notna(feat_row.get("away_form_pts_5")) else None,
                "tiene_cuotas": not (pd.isna(feat_row.get("odd_1"))),
            },
        }
        results.append(result)

    return {
        "jornada": jornada,
        "predicciones": results,
        "pleno15": pleno15_pred,
        "estado": "completado" if results else "sin_datos",
        "fecha_generacion": datetime.now().isoformat(timespec="seconds"),
        "modelo_info": {
            "version": settings.CONFIG.get("version", "desconocida"),
            "modo": "produccion",
            "fecha_entrenamiento": datetime.now().isoformat(timespec="seconds"),
            "partidos_entrenamiento": len(train),
            "ultimo_dia_entrenamiento": train["date"].max().date().isoformat(),
            "prediction_cutoff_at": cutoff_instant.isoformat(),
            "calibracion": {
                "aplicada": False,
                **calibration_meta,
            },
        },
    }


def get_cutoff_date(jornada_data: dict[str, Any], cutoff: object = None) -> pd.Timestamp:
    """Obtiene un corte reproducible; nunca usa la fecha actual como fallback."""
    kickoffs = [kickoff_at(p) for p in jornada_data.get("partidos", [])]
    known = [utc_timestamp(dt) for dt in kickoffs if dt]
    supplied = cutoff if cutoff is not None else jornada_data.get("prediction_cutoff_at")
    if supplied is not None:
        instant = utc_timestamp(supplied)
        if known and instant >= min(known):
            raise ValueError("El corte debe ser anterior al primer partido de la jornada")
        # Conservar el offset para que no se confundan dos horas del cambio DST.
        return instant
    if not known or len(known) != len(kickoffs):
        raise ValueError("Faltan fechas de partido: indica un corte ISO documentado con --corte")
    return utc_timestamp(local_timestamp(min(known)).normalize() - pd.Timedelta(days=1))


def attach_odds_traceability(
    jornada_data: dict[str, Any], cutoff_date: object
) -> dict[str, Any]:
    """Informa qué cuotas pasaron el mismo filtro temporal que usa el motor."""
    detalle = []
    for idx, match in enumerate(jornada_data.get("partidos", []), 1):
        _, entry = odds_at_cutoff({"num": idx, **match}, cutoff_date)
        detalle.append(entry)
    violaciones = [{"num": e["num"], "issues": e["issues"]} for e in detalle if e["estado"] == "violacion"]
    return {
        "politica": "Solo se usan tripletas completas con timestamps verificables; las demás no entran al motor.",
        "invariante": "odds_observed_at <= prediction_cutoff_at < kickoff_at",
        "prediction_cutoff_at": utc_timestamp(cutoff_date).isoformat(),
        "total_partidos": len(detalle),
        "auditados": sum(e["estado"] == "auditable" for e in detalle),
        "no_auditados": sum(e["estado"] == "no_auditado" for e in detalle),
        "violaciones_invariante": len(violaciones),
        "violaciones": violaciones,
        "detalle": detalle,
    }


def generate_jornada_prediction(
    jornada: int, cutoff: object = None, *, jornada_data: dict | None = None
) -> dict[str, Any]:
    """Genera predicciones completas para una jornada.

    Este es el punto de entrada principal desde PREDECIR_JORNADA.py.
    """
    # Cargar datos de la jornada
    data = load_jornada_json(jornada) if jornada_data is None else jornada_data
    partidos = validate_jornada(data, jornada)

    cutoff_date = get_cutoff_date(data, cutoff)
    source = settings.official_history_source()
    history_df = load_raw_history(source)

    # Generar predicciones del modelo
    predictions = predict_jornada_from_model(
        partidos=partidos,
        history_df=history_df,
        jornada=jornada,
        cutoff_date=cutoff_date,
    )

    predictions.setdefault("modelo_info", {})["historico"] = source
    predictions["jornada_data"] = {
        "source": f"DATOS/QUINIELA15_J{jornada}.json",
        "partidos_totales": len(partidos),
        "tiene_pleno15": any(p.get("num") == 15 for p in partidos),
    }

    # Trazabilidad temporal de cuotas (plan Fase 4)
    predictions["trazabilidad_cuotas"] = attach_odds_traceability(
        data, cutoff_date
    )

    return predictions


def save_predictions(predictions: dict[str, Any], jornada: int) -> Path:
    """Guarda las predicciones en salida/."""
    settings.SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    path = settings.SALIDA_DIR / f"predicciones_modelo_J{jornada}.json"
    write_json(path, predictions)
    return path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Genera predicciones del modelo para una jornada.")
    parser.add_argument("--jornada", "-j", type=int, required=True)
    parser.add_argument("--save", action="store_true", help="Guardar predicciones en salida/")
    parser.add_argument("--corte", help="fecha/hora ISO documentada del corte")
    args = parser.parse_args()

    try:
        predictions = generate_jornada_prediction(args.jornada, args.corte)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
    if "error" in predictions:
        parser.exit(1, predictions["error"] + "\n")
    print(json.dumps(predictions, ensure_ascii=False, indent=2))

    if args.save:
        path = save_predictions(predictions, args.jornada)
        print(f"\nGuardado en: {path}")
