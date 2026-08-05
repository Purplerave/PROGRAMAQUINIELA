"""prediction_engine.pleno — Helpers del Pleno al 15 (core, sin I/O).

El Pleno al 15 predice marcadores por buckets (0/1/2/M). Este módulo
contiene las piezas puras (cálculo sobre matrices de probabilidad de
marcador, selección de bucket, top scorelines).  La carga de históricos
y el acceso al JSON de jornada viven en
``MOTOR_PREDICCION_JORNADA.predict_pleno15_from_model`` y
``MOTOR_QUINIELA_MAESTRO.add_pleno_al_15``.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from .core import top_scorelines  # re-export para que add_pleno_al_15 lo use

PLENO_BUCKET_LABELS: tuple[str, ...] = ("0", "1", "2", "M")
PLENO_ALT_GAP: float = 0.10


def _pleno_bucket_label(goals: int) -> str:
    return str(goals) if goals < 3 else "M"


def pleno_bucket_probs(score_probs: np.ndarray) -> tuple[dict[str, float], dict[str, float]]:
    """Convierte matriz (G x G) de probabilidades de marcador a buckets por lado."""
    home: dict[str, float] = {b: 0.0 for b in PLENO_BUCKET_LABELS}
    away: dict[str, float] = {b: 0.0 for b in PLENO_BUCKET_LABELS}
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


def pleno_select(
    bucket_probs: dict[str, float], gap: float = PLENO_ALT_GAP
) -> tuple[str, str | None]:
    """Selecciona bucket principal + alternativa si el 2º está a menos de ``gap``."""
    ordered = sorted(bucket_probs.items(), key=lambda item: item[1], reverse=True)
    principal = ordered[0][0]
    alternativa = ordered[1][0] if (ordered[0][1] - ordered[1][1]) < gap else None
    return principal, alternativa


def add_pleno_al_15(frame: pd.DataFrame, rho: float | None = None) -> pd.DataFrame:
    """Añade columnas de Pleno al 15 (top marcadores / marcador / confianza).

    Versión pura: requiere que ya existan ``lambda_home`` y ``lambda_away``
    en el frame. La elección de ``rho`` (por defecto desde config) se hace
    aquí; no hay I/O.
    """
    import settings  # lectura de config; no I/O de datos.

    out = frame.copy()
    if rho is None:
        try:
            cfg = settings.master_model_config().get("dixon_coles", {})
            if isinstance(cfg, dict) and cfg.get("enabled") and cfg.get("use_for_pleno"):
                rho = float(cfg.get("rho", -0.036))
            else:
                rho = 0.0
        except Exception:
            rho = 0.0

    top_scores = [
        top_scorelines(lh, la, max_goals=5, top_n=3, rho=rho)
        for lh, la in zip(out["lambda_home"], out["lambda_away"])
    ]
    out["pleno15_top_scores"] = [
        json.dumps(scores, ensure_ascii=False) for scores in top_scores
    ]
    out["pleno15_marcador"] = [
        scores[0]["score"] if scores else None for scores in top_scores
    ]
    out["pleno15_confianza"] = [
        scores[0]["prob"] if scores else None for scores in top_scores
    ]
    out["pleno15_local_goles_esperados"] = out["lambda_home"]
    out["pleno15_visitante_goles_esperados"] = out["lambda_away"]
    return out


__all__ = [
    "PLENO_BUCKET_LABELS",
    "PLENO_ALT_GAP",
    "pleno_bucket_probs",
    "pleno_select",
    "add_pleno_al_15",
]
