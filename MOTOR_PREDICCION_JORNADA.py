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

from MOTOR_QUINIELA_MAESTRO import (
    add_market_baseline,
    apply_hybrid_config,
    build_hgb_model,
    build_logit_model,
    feature_columns,
    predict_full_probs,
)
from scripts.motor.features import (
    compute_features_for_upcoming,
    infer_season,
    rolling_team_features,
)

# Configuración de salida
MODELS_DIR = settings.SALIDA_DIR / "modelos"

# Modelo entrenado persistente
_LOGIT_MODEL: Any = None
_HGB_MODEL: Any = None
_MASTER_CONFIG: dict | None = None


def load_master_config() -> dict:
    """Carga la configuración del modelo maestro."""
    global _MASTER_CONFIG
    if _MASTER_CONFIG is None:
        _MASTER_CONFIG = settings.master_model_config()
    return _MASTER_CONFIG


def load_or_train_models(history_df: pd.DataFrame | None = None) -> tuple[Any, Any, dict]:
    """Carga modelos entrenados desde disco o los entrena desde cero.

    Si existen modelos guardados en MODELS_DIR, los carga.
    Si no, entrena con el histórico proporcionado.
    """
    global _LOGIT_MODEL, _HGB_MODEL, _MASTER_CONFIG

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    if _LOGIT_MODEL is not None and _HGB_MODEL is not None and _MASTER_CONFIG is not None:
        return _LOGIT_MODEL, _HGB_MODEL, _MASTER_CONFIG

    logit_path = MODELS_DIR / "logit_model.json"
    hgb_path = MODELS_DIR / "hgb_model.json"

    if logit_path.exists() and hgb_path.exists():
        # TODO: Implementar carga de modelos scikit-learn
        # Por ahora, entrenamos siempre (los Pipeline no se serializan fácilmente)
        pass

    if history_df is None:
        from MOTOR_QUINIELA_MAESTRO import load_raw_history
        history_df = load_raw_history()

    # Entrenar modelos
    logit, hgb, config = _train_models(history_df)
    _LOGIT_MODEL = logit
    _HGB_MODEL = hgb
    _MASTER_CONFIG = config
    return logit, hgb, config


def _train_models(df: pd.DataFrame) -> tuple[Any, Any, dict]:
    """Entrena los modelos Logit y HGB con el histórico."""
    from MOTOR_QUINIELA_MAESTRO import optimize_hybrid_config

    features_df = rolling_team_features(df)

    # Filtrar solo partidos con resultado conocido
    features_df = features_df[features_df["result"].isin({"1", "X", "2"})].copy()

    # Añadir columna target para entrenamiento
    features_df["target"] = features_df["result"].map({"1": 0, "X": 1, "2": 2})

    # Eliminar filas sin resultado
    features_df = features_df.dropna(subset=["target"])

    if len(features_df) < 100:
        raise ValueError(f"Datos insuficientes para entrenar: {len(features_df)} partidos")

    # Obtener mejor configuración usando subtrain/valid
    logit, hgb, config = optimize_hybrid_config(features_df)
    
    # optimize_hybrid_config ya re-entrena los modelos finales con TODO el histórico
    # usando la mejor configuración encontrada antes de devolverlos.
    
    return logit, hgb, config


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
    """
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
    for p in partidos:
        if p.get("num") == 15 and p.get("pleno15"):
            # El Pleno al 15 se maneja separadamente
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
        })

    if not normalized_matches:
        return {
            "jornada": jornada,
            "predicciones": [],
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
            "fecha_generacion": datetime.now().isoformat(timespec="seconds"),
        }

    if features_df.empty:
        return {
            "jornada": jornada,
            "error": "No se pudieron calcular features para los partidos",
            "fecha_generacion": datetime.now().isoformat(timespec="seconds"),
        }

    # Cargar o entrenar modelos
    try:
        logit, hgb, master_config = load_or_train_models(history_df)
    except Exception as e:
        return {
            "jornada": jornada,
            "error": f"Error cargando modelos: {str(e)}",
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
        "estado": "completado" if results else "sin_datos",
        "fecha_generacion": datetime.now().isoformat(timespec="seconds"),
        "modelo_info": {
            "version": "motor_maestro_hibrido_v1",
            "fecha_entrenamiento": datetime.now().isoformat(timespec="seconds"),
            "partidos_entrenamiento": len(history_df) if history_df is not None else 0,
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
    from MOTOR_QUINIELA_MAESTRO import load_raw_history

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
        "tiene_pleno15": any(p.get("num") == 15 and p.get("pleno15") for p in partidos),
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
