"""prediction_engine.training — Entrenamiento / optimización del ensemble.

Responsabilidades:
    * Optimización walk-forward multi-temporada de pesos y boosts
      (``optimize_hybrid_config``) con la métrica ``mean - 0.5*std``.
    * Evaluación de una configuración sobre un bloque de datos
      (``evaluate_config``) incluyendo el simulacro de 3 dobles por jornada.
    * Resumen de métricas (``summarize_results``).
    * Helper de alto nivel ``train_engine`` que devuelve un
      :class:`PredictionEngine` entrenado sobre un histórico dado.

No hace I/O: recibe y devuelve DataFrames/dicts.
"""

from __future__ import annotations

import itertools
from typing import Any

import numpy as np
import pandas as pd

import settings

from .core import (
    LABEL_MAP,
    PredictionEngine,
    add_market_baseline,
    apply_hybrid_config,
    build_double,
    build_hgb_model,
    build_logit_model,
    feature_columns,
    predict_full_probs,
    season_sort_key,
)


# ---------------------------------------------------------------------------
# Simulación de dobles y evaluación
# ---------------------------------------------------------------------------


def simulate_doubles(
    frame: pd.DataFrame, pred_prefix: str, config: dict
) -> pd.DataFrame:
    """Simula la elección de 3 dobles por jornada (15 partidos).

    Replica el comportamiento histórico: por bloque de 15 partidos ordenados,
    elige los 3 con mayor ``double_value_score`` y anota cuántos aciertos se
    obtienen (con el doble o con el signo simple). Se usa como parte de la
    métrica de optimización y como metrica agregada en los reportes.
    """
    ordered = (
        frame.sort_values(["date", "division", "home", "away"]).reset_index(drop=True).copy()
    )
    ordered["double"] = [
        build_double(p1, px, p2, config["double_draw_threshold"])
        for p1, px, p2 in zip(
            ordered[f"{pred_prefix}_prob_1"],
            ordered[f"{pred_prefix}_prob_x"],
            ordered[f"{pred_prefix}_prob_2"],
        )
    ]
    confidence = ordered[
        [f"{pred_prefix}_prob_1", f"{pred_prefix}_prob_x", f"{pred_prefix}_prob_2"]
    ].max(axis=1)
    score = (
        (1 - confidence)
        + config["double_draw_weight"] * ordered[f"{pred_prefix}_prob_x"]
        + config["double_disagreement_weight"] * ordered["model_disagreement"]
        + np.where(ordered["division"].eq("Segunda"), config["double_segunda_bonus"], 0.0)
    )
    ordered["double_value_score"] = score

    jornada_scores = []
    for start in range(0, len(ordered), 15):
        group = ordered.iloc[start : start + 15].copy()
        if len(group) < 15:
            continue
        double_idx = set(group.nlargest(3, "double_value_score").index.tolist())
        hits = 0
        for idx, row in group.iterrows():
            if idx in double_idx:
                if row["result"] in row["double"]:
                    hits += 1
            elif row[f"{pred_prefix}_pred"] == row["result"]:
                hits += 1
        jornada_scores.append({"ticket_idx": start // 15 + 1, "hits_3_dobles": hits})
    return pd.DataFrame(jornada_scores)


def evaluate_config(
    frame: pd.DataFrame, pred_prefix: str, config: dict
) -> dict[str, Any]:
    """Evalúa una configuración de ensemble sobre un bloque de datos.

    Devuelve el DataFrame enriquecido y un dict de métricas (score robusto,
    acierto simple, media de dobles, breakdown por división, etc.).
    """
    working = apply_hybrid_config(frame, config, pred_prefix)
    doubles_df = simulate_doubles(working, pred_prefix, config)
    division_breakdown: dict[str, dict[str, Any]] = {}
    for division, group in working.groupby("division"):
        division_breakdown[division] = {
            "matches": int(len(group)),
            "accuracy_simple": float(group[f"{pred_prefix}_hit"].mean()),
            "accuracy_market_favorite": float(group["favorite_market_hit"].mean()),
        }
    double_mean = float(doubles_df["hits_3_dobles"].mean()) if not doubles_df.empty else 0.0
    return {
        "predictions": working,
        "score": float(working[f"{pred_prefix}_hit"].mean()) + 0.017 * double_mean,
        "accuracy_simple": float(working[f"{pred_prefix}_hit"].mean()),
        "accuracy_market_favorite": float(working["favorite_market_hit"].mean()),
        "mean_hits_3_dobles": double_mean if not doubles_df.empty else None,
        "best_jornada_3_dobles": (
            int(doubles_df["hits_3_dobles"].max()) if not doubles_df.empty else None
        ),
        "avg_confidence": float(
            working[
                [f"{pred_prefix}_prob_1", f"{pred_prefix}_prob_x", f"{pred_prefix}_prob_2"]
            ].max(axis=1).mean()
        ),
        "accuracy_by_pick": {
            sign: (
                float(working.loc[working[f"{pred_prefix}_pred"] == sign, f"{pred_prefix}_hit"].mean())
                if not working.loc[working[f"{pred_prefix}_pred"] == sign].empty
                else None
            )
            for sign in ["1", "X", "2"]
        },
        "division_breakdown": division_breakdown,
    }


def summarize_results(
    frame: pd.DataFrame, pred_prefix: str, config: dict
) -> dict[str, Any]:
    """Versión ligera de ``evaluate_config`` sin devolver el DataFrame."""
    eval_result = evaluate_config(frame, pred_prefix, config)
    return {
        "accuracy_simple": eval_result["accuracy_simple"],
        "accuracy_market_favorite": eval_result["accuracy_market_favorite"],
        "avg_confidence": eval_result["avg_confidence"],
        "accuracy_by_pick": eval_result["accuracy_by_pick"],
        "mean_hits_3_dobles": eval_result["mean_hits_3_dobles"],
        "best_jornada_3_dobles": eval_result["best_jornada_3_dobles"],
        "division_breakdown": eval_result["division_breakdown"],
    }


# ---------------------------------------------------------------------------
# Optimización walk-forward
# ---------------------------------------------------------------------------


def _score_val_blocks(
    train: pd.DataFrame,
    val_seasons: list[str],
) -> list[pd.DataFrame]:
    """Genera los bloques de validación con sus probabilidades base.

    Para cada temporada de validación, entrena logit/hgb SÓLO con las
    temporadas *anteriores* (sin fuga), devuelve los bloques con las
    columnas ``logit_prob_*`` / ``hgb_prob_*`` / ``favorite_market*`` ya
    calculadas.
    """
    cols = feature_columns()
    blocks: list[pd.DataFrame] = []
    for v_season in val_seasons:
        train_mask = train["season"].apply(
            lambda s, vs=v_season: season_sort_key(s) < season_sort_key(vs)
        )
        val_mask = train["season"] == v_season

        t_sub = train[train_mask].copy()
        v_sub = train[val_mask].copy()

        if len(t_sub) < 500 or len(v_sub) < 50:
            continue

        l_sub = build_logit_model()
        h_sub = build_hgb_model()
        l_sub.fit(t_sub[cols + ["division"]], t_sub["target"])
        h_sub.fit(t_sub[cols], t_sub["target"])

        v_sub = add_market_baseline(v_sub)
        l_probs = predict_full_probs(l_sub, v_sub, cols + ["division"])
        h_probs = predict_full_probs(h_sub, v_sub, cols)

        v_sub["logit_prob_1"] = l_probs[:, 0]
        v_sub["logit_prob_x"] = l_probs[:, 1]
        v_sub["logit_prob_2"] = l_probs[:, 2]
        v_sub["hgb_prob_1"] = h_probs[:, 0]
        v_sub["hgb_prob_x"] = h_probs[:, 1]
        v_sub["hgb_prob_2"] = h_probs[:, 2]
        blocks.append(v_sub)
    return blocks


def optimize_hybrid_config(
    train: pd.DataFrame,
) -> tuple[Any, Any, dict[str, Any]]:
    """Optimiza pesos/boosts/dobles con walk-forward multi-temporada.

    Devuelve ``(logit_final, hgb_final, best_config)`` donde los dos
    primeros son pipelines re-entrenados sobre TODO ``train`` y
    ``best_config`` es la configuración ganadora según la métrica
    ``mean_score - 0.5 * std_score`` sobre los bloques de validación.
    """
    usable = train.copy()
    cols = feature_columns()

    # Decidir bloques de validación ---------------------------------------
    if "season" not in usable.columns or usable["season"].nunique() < 2:
        split_idx = int(len(usable) * 0.84)
        subtrain = usable.iloc[:split_idx].copy()
        valid = usable.iloc[split_idx:].copy()

        logit_sub = build_logit_model()
        hgb_sub = build_hgb_model()
        logit_sub.fit(subtrain[cols + ["division"]], subtrain["target"])
        hgb_sub.fit(subtrain[cols], subtrain["target"])

        valid_eval = add_market_baseline(valid)
        logit_probs = predict_full_probs(logit_sub, valid, cols + ["division"])
        hgb_probs = predict_full_probs(hgb_sub, valid, cols)
        valid_eval["logit_prob_1"] = logit_probs[:, 0]
        valid_eval["logit_prob_x"] = logit_probs[:, 1]
        valid_eval["logit_prob_2"] = logit_probs[:, 2]
        valid_eval["hgb_prob_1"] = hgb_probs[:, 0]
        valid_eval["hgb_prob_x"] = hgb_probs[:, 1]
        valid_eval["hgb_prob_2"] = hgb_probs[:, 2]

        val_blocks = [valid_eval]
    else:
        seasons = sorted(
            usable["season"].dropna().unique().tolist(), key=season_sort_key
        )
        val_seasons = seasons[-3:]
        val_blocks = _score_val_blocks(usable, val_seasons)
        if not val_blocks:
            return optimize_hybrid_config(usable.assign(season=np.nan))

    # Grids de candidatos (desde config + defaults) -----------------------
    master_config = settings.master_model_config()
    default_weight_candidates = [
        {"logit": 0.35, "hgb": 0.00, "market": 0.45, "poisson": 0.20},
        {"logit": 0.25, "hgb": 0.25, "market": 0.35, "poisson": 0.15},
        {"logit": 0.30, "hgb": 0.20, "market": 0.30, "poisson": 0.20},
    ]
    config_weights = master_config.get("weights")
    weight_candidates = master_config.get("weight_candidates") or default_weight_candidates
    if isinstance(config_weights, dict) and config_weights not in weight_candidates:
        weight_candidates = [config_weights, *weight_candidates]

    draw_boosts = master_config.get(
        "draw_boost_candidates", [master_config.get("draw_boost", 0.0)]
    )
    segunda_draw_boosts = master_config.get(
        "segunda_draw_boost_candidates", [master_config.get("segunda_draw_boost", 0.0)]
    )
    double_draw_weights = master_config.get(
        "double_draw_weight_candidates",
        [master_config.get("double_draw_weight", 0.70), 0.85],
    )
    double_disagreement_weights = master_config.get(
        "double_disagreement_weight_candidates",
        [master_config.get("double_disagreement_weight", 0.20)],
    )
    double_segunda_bonus = master_config.get(
        "double_segunda_bonus_candidates",
        [0.0, master_config.get("double_segunda_bonus", 0.05)],
    )
    double_draw_thresholds = master_config.get(
        "double_draw_threshold_candidates",
        [master_config.get("double_draw_threshold", 0.31)],
    )
    x_disagreement_strategies = master_config.get(
        "x_disagreement_strategy_candidates",
        [master_config.get("x_disagreement_strategy", "none")],
    )

    best: dict[str, Any] | None = None
    for (
        weights,
        draw_boost,
        segunda_boost,
        double_weight,
        disagree_weight,
        segunda_bonus,
        draw_threshold,
        x_strategy,
    ) in itertools.product(
        weight_candidates,
        draw_boosts,
        segunda_draw_boosts,
        double_draw_weights,
        double_disagreement_weights,
        double_segunda_bonus,
        double_draw_thresholds,
        x_disagreement_strategies,
    ):
        candidate_config = {
            "weights": weights,
            "draw_boost": draw_boost,
            "segunda_draw_boost": segunda_boost,
            "double_draw_weight": double_weight,
            "double_disagreement_weight": disagree_weight,
            "double_segunda_bonus": segunda_bonus,
            "double_draw_threshold": draw_threshold,
            "x_disagreement_strategy": x_strategy,
        }
        scores = []
        for block in val_blocks:
            evaluation = evaluate_config(block, "opt", candidate_config)
            scores.append(evaluation["score"])
        mean_score = float(np.mean(scores))
        std_score = float(np.std(scores))
        final_metric = mean_score - 0.5 * std_score
        if best is None or final_metric > best["final_metric"]:
            best = {
                "config": candidate_config,
                "final_metric": final_metric,
                "mean_score": mean_score,
                "std_score": std_score,
            }

    assert best is not None
    # Re-entrenar con TODO el train --------------------------------------
    final_logit = build_logit_model()
    final_hgb = build_hgb_model()
    final_logit.fit(train[cols + ["division"]], train["target"])
    final_hgb.fit(train[cols], train["target"])

    return final_logit, final_hgb, best["config"]


def train_engine(
    train_df: pd.DataFrame,
    *,
    calibrator: Any | None = None,
    require_target: bool = True,
) -> PredictionEngine:
    """High-level: entrena un ``PredictionEngine`` sobre ``train_df``.

    ``train_df`` debe incluir la columna ``target`` (0/1/2 mapeada desde
    ``result`` por :data:`LABEL_MAP`) además de :data:`FEATURE_COLUMNS` y
    ``division``/``season``/``result``/``market_*``/``poisson_*``.
    """
    if require_target and "target" not in train_df.columns:
        raise ValueError("train_engine requiere la columna 'target'.")
    logit, hgb, config = optimize_hybrid_config(train_df)
    return PredictionEngine(logit, hgb, config, calibrator=calibrator)


__all__ = [
    "simulate_doubles",
    "evaluate_config",
    "summarize_results",
    "optimize_hybrid_config",
    "train_engine",
]
