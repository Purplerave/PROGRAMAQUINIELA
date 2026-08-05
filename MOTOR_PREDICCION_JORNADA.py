"""Motor de predicción para partidos de jornada.

Conecta PREDECIR_JORNADA con MOTOR_QUINIELA_MAESTRO para obtener
probabilidades reales del modelo entrenado, evitando la dependencia
de APU/LAE/Q15 como fuente principal.

Este módulo:
- Carga el histórico para calcular features rodantes (sin fuga temporal)
- Entrena o carga modelos entrenados
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

# Core de predicción (aislado en P0.3): NO importa de MOTOR_QUINIELA_MAESTRO
# ni de este módulo; dirección unidireccional.
from prediction_engine import (
    add_market_baseline,
    apply_hybrid_config,
    build_hgb_model,
    build_logit_model,
    feature_columns,
    predict_full_probs,
)
from prediction_engine import PredictionEngine
from MOTOR_QUINIELA_MAESTRO import (
    add_pleno_al_15,  # re-export de prediction_engine.pleno (compat)
    load_raw_history,
)
from scripts.motor.features import (
    compute_features_for_upcoming,
    infer_season,
    rolling_team_features,
)
from scripts.motor.calibration import VectorScalingCalibrator

# Configuración de salida
MODELS_DIR = settings.SALIDA_DIR / "modelos"

# Pleno al 15: buckets de goles del boleto oficial y umbral para sugerir doble
PLENO_BUCKET_LABELS = ("0", "1", "2", "M")
_PLENO_ALT_GAP = 0.10
# Lambdas de emergencia si ni features ni histórico ofrecen medias (no debería ocurrir)
_FALLBACK_LAMBDA_HOME = 1.45
_FALLBACK_LAMBDA_AWAY = 1.10

# Modelo entrenado persistente
_LOGIT_MODEL: Any = None
_HGB_MODEL: Any = None
_MASTER_CONFIG: dict | None = None
_CALIBRATOR: VectorScalingCalibrator | None = None


def load_master_config() -> dict:
    """Carga la configuración del modelo maestro."""
    global _MASTER_CONFIG
    if _MASTER_CONFIG is None:
        _MASTER_CONFIG = settings.master_model_config()
    return _MASTER_CONFIG


def load_or_train_models(
    history_df: pd.DataFrame | None = None,
) -> tuple[Any, Any, dict, VectorScalingCalibrator | None]:
    """Carga modelos entrenados desde disco o los entrena desde cero.

    Si existen modelos guardados en MODELS_DIR, los carga.
    Si no, entrena con el histórico proporcionado.

    Returns:
        (logit, hgb, config, calibrator) — calibrator puede ser None si falla.
    """
    global _LOGIT_MODEL, _HGB_MODEL, _MASTER_CONFIG, _CALIBRATOR

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    if (
        _LOGIT_MODEL is not None
        and _HGB_MODEL is not None
        and _MASTER_CONFIG is not None
    ):
        # Si ya existe calibrador en memoria, devolverlo; si no, entrenar solo calibrador no es trivial,
        # así que devolvemos lo que haya (puede ser None en primera carga).
        return _LOGIT_MODEL, _HGB_MODEL, _MASTER_CONFIG, _CALIBRATOR

    logit_path = MODELS_DIR / "logit_model.json"
    hgb_path = MODELS_DIR / "hgb_model.json"

    if logit_path.exists() and hgb_path.exists():
        # TODO: Implementar carga de modelos scikit-learn
        # Por ahora, entrenamos siempre (los Pipeline no se serializan fácilmente)
        pass

    if history_df is None:
        history_df = load_raw_history()

    # Entrenar modelos + calibrador
    logit, hgb, config, calibrator = _train_models(history_df)
    _LOGIT_MODEL = logit
    _HGB_MODEL = hgb
    _MASTER_CONFIG = config
    _CALIBRATOR = calibrator
    return logit, hgb, config, calibrator


def _train_models(
    df: pd.DataFrame,
) -> tuple[Any, Any, dict, VectorScalingCalibrator | None]:
    """Entrena los modelos Logit y HGB con el histórico y ajusta el calibrador vector scaling.

    Flujo (evita fuga temporal):
      1. Extrae features rodantes (ya ordenadas por fecha).
      2. Optimiza la configuración híbrida con split temporal 84/16 interno (optimize_hybrid_config).
      3. Re-entrena modelos finales con TODO el histórico (ya lo hace optimize_hybrid_config).
      4. Para el calibrador: vuelve a dividir el histórico en subtrain 84% / valid 16% (temporal),
         entrena modelos temporales en subtrain, genera ensemble en valid y ajusta vector scaling
         solo con valid. Nunca usa la jornada futura a predecir.

    Returns:
        (logit_full, hgb_full, config_best, calibrator_or_None)
    """
    from prediction_engine.training import optimize_hybrid_config

    features_df = rolling_team_features(df)

    # Filtrar solo partidos con resultado conocido
    features_df = features_df[features_df["result"].isin({"1", "X", "2"})].copy()

    # Añadir columna target para entrenamiento
    features_df["target"] = features_df["result"].map({"1": 0, "X": 1, "2": 2})

    # Eliminar filas sin resultado
    features_df = features_df.dropna(subset=["target"])

    if len(features_df) < 100:
        raise ValueError(f"Datos insuficientes para entrenar: {len(features_df)} partidos")

    # Ordenar por fecha para split temporal consistente
    features_df = features_df.sort_values(
        ["date", "division", "home", "away"]
    ).reset_index(drop=True)

    # Obtener mejor configuración usando subtrain/valid y re-entrenar con todo
    logit_full, hgb_full, config_best = optimize_hybrid_config(features_df)

    # --- Entrenar calibrador vector scaling en validación temporal ---
    calibrator: VectorScalingCalibrator | None = None
    try:
        # Mismo split 84/16 que usa optimize_hybrid_config
        split_idx = int(len(features_df) * 0.84)
        if split_idx < 50 or (len(features_df) - split_idx) < 50:
            raise ValueError("Split de calibración demasiado pequeño")

        subtrain = features_df.iloc[:split_idx].copy()
        valid = features_df.iloc[split_idx:].copy()

        # Entrenar modelos temporales solo con subtrain
        cols = feature_columns()
        # Logit necesita columna division
        logit_sub = build_logit_model()
        hgb_sub = build_hgb_model()

        logit_sub.fit(subtrain[cols + ["division"]], subtrain["target"])
        hgb_sub.fit(subtrain[cols], subtrain["target"])

        # Probabilidades en validación
        logit_valid_probs = predict_full_probs(logit_sub, valid, cols + ["division"])
        hgb_valid_probs = predict_full_probs(hgb_sub, valid, cols)

        valid_for_cal = valid.copy()
        valid_for_cal["logit_prob_1"] = logit_valid_probs[:, 0]
        valid_for_cal["logit_prob_x"] = logit_valid_probs[:, 1]
        valid_for_cal["logit_prob_2"] = logit_valid_probs[:, 2]
        valid_for_cal["hgb_prob_1"] = hgb_valid_probs[:, 0]
        valid_for_cal["hgb_prob_x"] = hgb_valid_probs[:, 1]
        valid_for_cal["hgb_prob_2"] = hgb_valid_probs[:, 2]

        valid_for_cal = add_market_baseline(valid_for_cal)
        valid_for_cal = apply_hybrid_config(valid_for_cal, config_best, "modelo")

        cal_probs = valid_for_cal[
            ["modelo_prob_1", "modelo_prob_x", "modelo_prob_2"]
        ].to_numpy(dtype=float)
        cal_y = valid["target"].to_numpy(dtype=int)

        # Ajustar vector scaling
        cal = VectorScalingCalibrator()
        cal.fit(cal_probs, cal_y)
        calibrator = cal

    except Exception as exc:
        # No bloquear entrenamiento de modelos si la calibración falla; dejamos aviso
        # El llamante podrá ver calibrator=None y operar sin calibrar.
        print(f"[calibracion] Aviso: no se pudo entrenar calibrador vector scaling: {exc}")
        calibrator = None

    return logit_full, hgb_full, config_best, calibrator


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
    p1 = probs.get("1") or probs.get("prob_1") or 0.333
    px = probs.get("X") or probs.get("prob_x") or 0.333
    p2 = probs.get("2") or probs.get("prob_2") or 0.333

    # Entropía máxima = log(3) ≈ 1.0986 (distribución uniforme)
    # Entropía mínima = 0 (certidumbre absoluta)
    max_entropy = math.log(3)
    probs_list = [p1, px, p2]
    entropy = -sum(p * math.log(p) if p > 0 else 0 for p in probs_list)
    confidence = 1 - (entropy / max_entropy)
    return round(confidence, 4)


def _check_data_quality(feat_row: pd.Series) -> dict[str, Any]:
    """Verifica la calidad de datos disponibles para un partido."""
    warnings = []
    quality_score = 1.0

    # Verificar cuotas de mercado
    if pd.isna(feat_row.get("odd_1")) or pd.isna(feat_row.get("market_1")):
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


def _apply_transition_priors(features_df: pd.DataFrame) -> pd.DataFrame:
    """Aplica priors de transición a equipos con poca muestra en la temporada actual.

    Punto 5 Codex: Respetar la temporada y aplicar explícitamente los priors de transición.
    Punto 5 Codex (Rev 2): No añadir heurísticas de Elo nuevas no validadas.

    La búsqueda de priors acepta nombres comunes de jornada ("Malaga CF",
    "Castellón") traduciéndolos al nombre canónico del fichero de priors
    ("Malaga CF", "CD Castellon") mediante scripts/motor/team_names.
    """
    from scripts.motor.team_names import resolve_prior_name

    priors_path = settings.DATOS_DIR / "temporada_2026_27_estadisticas_base.json"
    if not priors_path.exists():
        return features_df

    try:
        priors_data = json.loads(priors_path.read_text(encoding="utf-8"))
        teams_priors = priors_data.get("teams", {})
    except Exception:
        return features_df

    normalized_priors = {normalize_name(k): v for k, v in teams_priors.items()}

    for idx, row in features_df.iterrows():
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


def _pleno_bucket_probs(score_probs: np.ndarray) -> tuple[dict[str, float], dict[str, float]]:
    """Pasa la matriz de marcadores (G x G) a probabilidades de buckets por lado.

    La matriz ya viene normalizada (DC recorta la cola en max_goals; la masa
    residual por encima de 7 goles de cada lado es < 0,1 % y se renormaliza).
    """
    home = {bucket: 0.0 for bucket in PLENO_BUCKET_LABELS}
    away = {bucket: 0.0 for bucket in PLENO_BUCKET_LABELS}
    goals_n = score_probs.shape[0]
    for hg in range(goals_n):
        for ag in range(goals_n):
            prob = float(score_probs[hg, ag])
            home[_pleno_bucket_label(hg)] += prob
            away[_pleno_bucket_label(ag)] += prob
    total_home = sum(home.values()) or 1.0
    total_away = sum(away.values()) or 1.0
    home = {b: round(v / total_home, 4) for b, v in home.items()}
    away = {b: round(v / total_away, 4) for b, v in away.items()}
    return home, away


def _pleno_select(bucket_probs: dict[str, float], gap: float = _PLENO_ALT_GAP) -> tuple[str, str | None]:
    """Selecciona el bucket principal y una alternativa si el 2º está muy cerca."""
    ordered = sorted(bucket_probs.items(), key=lambda item: item[1], reverse=True)
    principal = ordered[0][0]
    alternativa = ordered[1][0] if (ordered[0][1] - ordered[1][1]) < gap else None
    return principal, alternativa


def _league_mean_lambdas(history_df: pd.DataFrame, cutoff_date: pd.Timestamp) -> tuple[float, float]:
    """Media histórica de goles por lado SOLO con partidos anteriores al corte.

    Se usa como sustituto controlado cuando un equipo no tiene historial
    (selecciones, ligas no cubiertas), de modo que el Pleno al 15 siempre
    produce una salida estable y documentada (lambdas_fuente).
    """
    hist = history_df.copy()
    hist["date"] = pd.to_datetime(hist["date"], errors="coerce")
    hist = hist[hist["date"] < pd.to_datetime(cutoff_date)]
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

    dc_cfg = settings.master_model_config().get("dixon_coles", {})
    if not isinstance(dc_cfg, dict):
        dc_cfg = {}
    use_dc = bool(dc_cfg.get("enabled", False)) and bool(dc_cfg.get("use_for_pleno", False))
    rho = float(dc_cfg.get("rho", 0.0)) if use_dc else 0.0
    max_goals = int(dc_cfg.get("max_goals", 7))

    local = partido15.get("local")
    visitante = partido15.get("visitante")
    fecha = partido15.get("fecha")

    match = {
        "home": local,
        "away": visitante,
        "date": fecha if fecha else cutoff_date,
        "division": partido15.get("division"),  # None -> se infiere del histórico
        "season": infer_season(fecha) if fecha else None,
        "odd_1": partido15.get("odd_1"),
        "odd_x": partido15.get("odd_x"),
        "odd_2": partido15.get("odd_2"),
    }

    try:
        features_df = compute_features_for_upcoming(
            [match], history_df, cutoff_date=cutoff_date
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
        mean_home, mean_away = _league_mean_lambdas(history_df, pd.to_datetime(cutoff_date))
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

    goles_local, goles_visitante = _pleno_bucket_probs(score_probs)
    sel_local, alt_local = _pleno_select(goles_local)
    sel_visitante, alt_visitante = _pleno_select(goles_visitante)

    quality = _check_data_quality(feat_row)
    avisos = list(quality["warnings"])
    calidad = quality["quality_score"]
    if lambdas_fuente != "features_equipo":
        avisos.append("lambdas_media_liga")
        calidad = round(max(0.0, calidad - 0.25), 2)

    seleccion_confianza = round(
        float(goles_local[sel_local]) * float(goles_visitante[sel_visitante]), 4
    )

    return {
        "jornada": jornada,
        "numero": 15,
        "local": local,
        "visitante": visitante,
        "fecha": str(fecha)[:10] if fecha else None,
        "disponible": calidad >= 0.2,
        "modelo": "dixon_coles" if rho != 0.0 else "poisson_independiente",
        "rho": rho,
        "lambdas": {"local": round(lambda_home, 3), "visitante": round(lambda_away, 3)},
        "lambdas_fuente": lambdas_fuente,
        "marcador_predicho": top_marcadores[0]["score"],
        "marcador_confianza": top_marcadores[0]["prob"],
        "top_marcadores": top_marcadores,
        "goles_local": goles_local,
        "goles_visitante": goles_visitante,
        "seleccion": {
            "local": sel_local,
            "visitante": sel_visitante,
            "alternativa_local": alt_local,
            "alternativa_visitante": alt_visitante,
            "confianza": seleccion_confianza,
            "nota": "Alternativa sugerida si el segundo bucket está a menos de "
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
    if isinstance(cutoff_date, str):
        cutoff_date = pd.to_datetime(cutoff_date)

    # Normalizar partidos para la extracción de features
    normalized_matches = []
    partido15 = None
    for p in partidos:
        if p.get("num") == 15:
            # El Pleno al 15 se maneja aparte con Dixon-Coles (buckets de goles)
            partido15 = p
            continue
        
        # Respetar la temporada inferida de la fecha del partido
        fecha_partido = p.get("fecha")
        season = infer_season(fecha_partido) if fecha_partido else None

        normalized_matches.append({
            "home": p.get("local"),
            "away": p.get("visitante"),
            "date": fecha_partido,
            "division": p.get("division", "Primera"),
            "season": season,
            # Cuotas reales si vienen en el JSON de jornada (entrada estable);
            # APU/LAE/Q15 NO se pasan: nunca se interpretan como cuotas.
            "odd_1": p.get("odd_1"),
            "odd_x": p.get("odd_x"),
            "odd_2": p.get("odd_2"),
            "open_odd_1": p.get("open_odd_1"),
            "open_odd_x": p.get("open_odd_x"),
            "open_odd_2": p.get("open_odd_2"),
        })

    # Pleno al 15 con Dixon-Coles (independiente del ensemble 1X2: solo lambdas)
    pleno15_pred = None
    if partido15 is not None:
        try:
            pleno15_pred = predict_pleno15_from_model(
                partido15, history_df, jornada, cutoff_date
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
            history_df,
            cutoff_date=cutoff_date,
        )
        # Aplicar priors de transición para equipos nuevos o inicio de temporada
        features_df = _apply_transition_priors(features_df)
    except Exception as e:
        return {
            "jornada": jornada,
            "error": f"Error calculando features: {str(e)}",
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

    # Cargar o entrenar modelos (incluye calibrador vector scaling si está disponible)
    calibrator = None
    try:
        loaded = load_or_train_models(history_df)
        if len(loaded) == 4:
            logit, hgb, master_config, calibrator = loaded
        else:
            logit, hgb, master_config = loaded
            calibrator = None
    except Exception as e:
        return {
            "jornada": jornada,
            "error": f"Error cargando modelos: {str(e)}",
            "pleno15": pleno15_pred,
            "fecha_generacion": datetime.now().isoformat(timespec="seconds"),
        }

    # Obtener probabilidades de cada modelo
    cols = feature_columns()
    logit_probs = predict_full_probs(logit, features_df, cols + ["division"])
    hgb_probs = predict_full_probs(hgb, features_df, cols)

    # Preparar DataFrame para apply_hybrid_config
    features_df["logit_prob_1"] = logit_probs[:, 0]
    features_df["logit_prob_x"] = logit_probs[:, 1]
    features_df["logit_prob_2"] = logit_probs[:, 2]
    features_df["hgb_prob_1"] = hgb_probs[:, 0]
    features_df["hgb_prob_x"] = hgb_probs[:, 1]
    features_df["hgb_prob_2"] = hgb_probs[:, 2]

    # Necesario para x_disagreement_strategy
    features_df = add_market_baseline(features_df)

    # Aplicar inferencia unificada del motor maestro
    features_df = apply_hybrid_config(features_df, master_config, "modelo")

    # --- T3: Aplicar calibración vector scaling si está disponible ---
    calibrado = False
    calibration_meta: dict = {}
    if calibrator is not None and getattr(calibrator, "is_fitted", False):
        try:
            raw_probs = features_df[
                ["modelo_prob_1", "modelo_prob_x", "modelo_prob_2"]
            ].to_numpy(dtype=float)
            calibrated_probs = calibrator.predict(raw_probs)
            features_df["modelo_prob_1"] = calibrated_probs[:, 0]
            features_df["modelo_prob_x"] = calibrated_probs[:, 1]
            features_df["modelo_prob_2"] = calibrated_probs[:, 2]
            # Recalcular predicción argmax tras calibrar
            features_df["modelo_pred"] = features_df[
                ["modelo_prob_1", "modelo_prob_x", "modelo_prob_2"]
            ].idxmax(axis=1).map(
                {
                    "modelo_prob_1": "1",
                    "modelo_prob_x": "X",
                    "modelo_prob_2": "2",
                }
            )
            calibrado = True
            calibration_meta = {
                "metodo": "vector_scaling",
                "pre": calibrator.calibration_info.get("pre", {}),
                "post": calibrator.calibration_info.get("post", {}),
                "n_calibration": calibrator.calibration_info.get("n_calibration"),
            }
        except Exception as exc:
            print(f"[calibracion] Aviso: fallo al aplicar calibrador en jornada {jornada}: {exc}")
            calibrado = False

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

        # Obtener partido original
        original = normalized_matches[idx]
        partido_num = idx + 1
        
        # Buscar información adicional del partido original
        for orig_p in partidos:
            if (normalize_name(orig_p.get("local", "")) == normalize_name(original["home"])
                    and normalize_name(orig_p.get("visitante", "")) == normalize_name(original["away"])):
                partido_num = orig_p.get("num", idx + 1)
                break

        result = {
            "jornada": jornada,
            "numero": partido_num,
            "local": original["home"],
            "visitante": original["away"],
            "fecha": str(original["date"])[:10] if pd.notna(original["date"]) else None,
            "division": original.get("division", feat_row.get("division")),
            **probs,
            "signo_modelo": feat_row["modelo_pred"],
            "confianza": _calculate_confidence(probs),
            "fuente_probabilidades": {
                "modelo_primario": "motor_maestro_hibrido",
                "componentes": {
                    "logit": round(master_config["weights"].get("logit", 0), 2),
                    "hgb": round(master_config["weights"].get("hgb", 0), 2),
                    "market": round(master_config["weights"].get("market", 0), 2),
                    "poisson": round(master_config["weights"].get("poisson", 0), 2),
                },
                "draw_boost_aplicado": master_config.get("draw_boost", 0),
                "segunda_draw_boost_aplicado": master_config.get("segunda_draw_boost", 0),
                "x_disagreement_strategy": master_config.get("x_disagreement_strategy", "none"),
                "calibracion": {
                    "aplicada": calibrado,
                    "metodo": calibration_meta.get("metodo") if calibrado else None,
                    "n_calibration": calibration_meta.get("n_calibration"),
                    "pre_ece": calibration_meta.get("pre", {}).get("ece"),
                    "post_ece": calibration_meta.get("post", {}).get("ece"),
                },
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
            "version": "motor_maestro_hibrido_v2_calibrado_vector_pleno_dc",
            "fecha_entrenamiento": datetime.now().isoformat(timespec="seconds"),
            "partidos_entrenamiento": len(history_df) if history_df is not None else 0,
            "calibracion": {
                "aplicada": calibrado,
                **calibration_meta,
            },
        },
    }


def load_jornada_json(jornada: int) -> dict[str, Any]:
    """Carga los datos de una jornada desde DATOS/QUINIELA15_J{jornada}.json."""
    path = settings.DATOS_DIR / f"QUINIELA15_J{jornada}.json"
    if not path.exists():
        raise FileNotFoundError(f"No existe: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def get_cutoff_date(jornada_data: dict[str, Any]) -> datetime:
    """Determina la fecha de corte para calcular features.

    Usa la fecha del primer partido de la jornada.
    """
    partidos = jornada_data.get("partidos", [])
    fechas = []
    for p in partidos:
        fecha_str = p.get("fecha")
        if fecha_str:
            try:
                fechas.append(pd.to_datetime(fecha_str))
            except Exception:
                pass
    if fechas:
        # Un día antes del primer partido
        return min(fechas) - pd.Timedelta(days=1)
    # Por defecto, ayer
    return pd.Timestamp.now() - pd.Timedelta(days=1)


def generate_jornada_prediction(jornada: int) -> dict[str, Any]:
    """Genera predicciones completas para una jornada.

    Este es el punto de entrada principal desde PREDECIR_JORNADA.py.
    """
    # Cargar datos de la jornada
    jornada_data = load_jornada_json(jornada)
    partidos = jornada_data.get("partidos", [])

    # Cargar histórico para features
    history_df = load_raw_history()

    # Determinar fecha de corte
    cutoff_date = get_cutoff_date(jornada_data)

    # Generar predicciones del modelo
    predictions = predict_jornada_from_model(
        partidos=partidos,
        history_df=history_df,
        jornada=jornada,
        cutoff_date=cutoff_date,
    )

    # Añadir metadata
    predictions["jornada_data"] = {
        "source": f"DATOS/QUINIELA15_J{jornada}.json",
        "partidos_totales": len(partidos),
        "tiene_pleno15": any(p.get("num") == 15 for p in partidos),
    }

    return predictions


def save_predictions(predictions: dict[str, Any], jornada: int) -> Path:
    """Guarda las predicciones en SALIDAS/."""
    settings.SALIDAS_DIR.mkdir(parents=True, exist_ok=True)
    path = settings.SALIDAS_DIR / f"predicciones_modelo_J{jornada}.json"
    path.write_text(
        json.dumps(predictions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Genera predicciones del modelo para una jornada.")
    parser.add_argument("--jornada", "-j", type=int, required=True)
    parser.add_argument("--save", action="store_true", help="Guardar predicciones en SALIDAS/")
    args = parser.parse_args()

    predictions = generate_jornada_prediction(args.jornada)
    print(json.dumps(predictions, ensure_ascii=False, indent=2))

    if args.save:
        path = save_predictions(predictions, args.jornada)
        print(f"\nGuardado en: {path}")
