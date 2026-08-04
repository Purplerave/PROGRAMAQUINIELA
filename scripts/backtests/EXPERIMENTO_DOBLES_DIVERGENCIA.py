#!/usr/bin/env python3
"""Validación walk-forward de la selección de los 3 dobles con divergencia.

El experimento de divergencia modelo-mercado (`EXPERIMENTO_DIVERGENCIA.py`)
mostró valor solo en el rango moderado ``diff ∈ [0.05, 0.10]`` (la divergencia
excesiva, > 0.10, es sobreconfianza). Este script valida usar ese rango como
señal para elegir los tres dobles, en walk-forward multi-split (temporadas
2023-24, 2024-25 y 2025-26, entrenando solo con temporadas anteriores y la
config activa de producción, sin reoptimizar pesos).

Métricas (proxy de bloques de 15, igual que la referencia del README):

- ``V0 baseline``: selección activa (score = 1-confianza + 0.7*p_x +
  0.2*desacuerdo + 0.05*Segunda; top-3 por bloque).
- ``V1 bonus``: suma un bonus a los partidos con divergencia en rango
  (se prueban 0.05/0.10/0.15/0.20).
- ``V2 restringido``: solo los partidos en rango pueden ser dobles; si hay
  menos de 3 en el bloque, se completan con el resto por score base.
- ``V3 anti-sobreconfianza``: penaliza (excluye) los partidos con diff > 0.10.

Divergencia por partido: ``diff = p_hgb[signo_top_hgb] - p_mercado[signo_top_hgb]``.

Uso:

    python scripts/backtests/EXPERIMENTO_DOBLES_DIVERGENCIA.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from MOTOR_QUINIELA_MAESTRO import (  # noqa: E402
    build_double,
    load_raw_history,
    rolling_team_features,
    run_season_backtest,
)

TARGET_SEASONS = ["2023-2024", "2024-2025", "2025-2026"]
DIVERGENCE_RANGE = (0.05, 0.10)
PRED_PREFIX = "latest"
SIGNS = ["1", "X", "2"]
# Sufijos de columna del motor: la X es minúscula (hgb_prob_x, market_x).
COLUMN_SUFFIX = {"1": "1", "X": "x", "2": "2"}


def add_divergence(frame: pd.DataFrame) -> pd.DataFrame:
    """Añade la divergencia modelo-mercado por partido (signo top del HGB)."""
    out = frame.copy()
    hgb_cols = {sign: f"hgb_prob_{COLUMN_SUFFIX[sign]}" for sign in SIGNS}
    market_cols = {sign: f"market_{COLUMN_SUFFIX[sign]}" for sign in SIGNS}
    top_signs, diffs = [], []
    for _, row in out.iterrows():
        probs = {sign: float(row[hgb_cols[sign]]) for sign in SIGNS}
        top_sign = max(SIGNS, key=lambda sign: probs[sign])
        top_signs.append(top_sign)
        diffs.append(probs[top_sign] - float(row[market_cols[top_sign]]))
    out["hgb_top_sign"] = top_signs
    out["diff_top"] = diffs
    out["div_in_range"] = out["diff_top"].between(DIVERGENCE_RANGE[0], DIVERGENCE_RANGE[1])
    out["div_over"] = out["diff_top"] > DIVERGENCE_RANGE[1]
    return out


def evaluate_doubles(
    frame: pd.DataFrame,
    config: dict,
    mode: str,
    bonus: float = 0.0,
) -> pd.DataFrame:
    """Evalúa los 3 dobles por bloque de 15 con una regla de selección.

    ``mode``: "baseline", "bonus" (suma ``bonus`` a los partidos en rango),
    "restricted" (solo en rango, completando con el resto) o
    "anti_over" (excluye diff > 0.10).
    """
    ordered = frame.sort_values(["date", "division", "home", "away"]).reset_index(drop=True).copy()
    if "div_in_range" not in ordered.columns:
        ordered["div_in_range"] = False
        ordered["div_over"] = False
    ordered["double"] = [
        build_double(p1, px, p2, config["double_draw_threshold"])
        for p1, px, p2 in zip(
            ordered[f"{PRED_PREFIX}_prob_1"],
            ordered[f"{PRED_PREFIX}_prob_x"],
            ordered[f"{PRED_PREFIX}_prob_2"],
        )
    ]
    confidence = ordered[[f"{PRED_PREFIX}_prob_1", f"{PRED_PREFIX}_prob_x", f"{PRED_PREFIX}_prob_2"]].max(axis=1)
    base_score = (
        (1 - confidence)
        + config["double_draw_weight"] * ordered[f"{PRED_PREFIX}_prob_x"]
        + config["double_disagreement_weight"] * ordered["model_disagreement"]
        + np.where(ordered["division"].eq("Segunda"), config["double_segunda_bonus"], 0.0)
    )
    if mode == "bonus":
        score = base_score + bonus * ordered["div_in_range"].astype(float)
    elif mode == "anti_over":
        score = base_score - np.where(ordered["div_over"], 1.0, 0.0)
    else:
        score = base_score
    ordered["double_value_score"] = score
    ordered["in_range"] = ordered["div_in_range"].astype(bool)

    rows = []
    for start in range(0, len(ordered), 15):
        group = ordered.iloc[start:start + 15].copy()
        if len(group) < 15:
            continue
        if mode == "restricted":
            in_range = group.index[group["in_range"]]
            chosen = list(in_range)
            if len(chosen) < 3:
                needed = 3 - len(chosen)
                rest = group.loc[~group.index.isin(in_range), "double_value_score"].nlargest(needed).index
                chosen += list(rest)
            double_idx = set(chosen[:3])
        else:
            double_idx = set(group.nlargest(3, "double_value_score").index.tolist())
        hits = 0
        for idx, row in group.iterrows():
            if idx in double_idx:
                if row["result"] in row["double"]:
                    hits += 1
            elif row[f"{PRED_PREFIX}_pred"] == row["result"]:
                hits += 1
        rows.append({"ticket_idx": start // 15 + 1, "hits_3_dobles": hits})
    return pd.DataFrame(rows)


def summarize(blocks: pd.DataFrame, label: str, all_blocks: dict[str, pd.DataFrame]) -> dict:
    mean = float(blocks["hits_3_dobles"].mean()) if not blocks.empty else 0.0
    per_season = {}
    for season, season_blocks in all_blocks.items():
        per_season[season] = float(season_blocks["hits_3_dobles"].mean()) if not season_blocks.empty else 0.0
    std = float(blocks["hits_3_dobles"].std()) if len(blocks) > 1 else 0.0
    return {"variant": label, "mean_hits": mean, "std": std, "n_blocks": int(len(blocks)), "per_season": per_season}


def run_experiment() -> None:
    raw = load_raw_history("original")
    features = rolling_team_features(raw)
    results: dict[str, dict] = {}
    all_blocks: dict[str, pd.DataFrame] = {}

    for target in TARGET_SEASONS:
        print(f"\n=== Temporada {target} ===")
        predictions, metrics = run_season_backtest(features, target, "production")
        config = metrics["best_config"]
        frame = add_divergence(predictions)
        in_range_share = float(frame["div_in_range"].mean())
        over_share = float(frame["div_over"].mean())
        print(f"  Partidos: {len(frame)} | divergencia en rango: {in_range_share:.2%} | sobreconfianza (>0.10): {over_share:.2%}")

        all_blocks[target] = {
            "baseline": evaluate_doubles(frame, config, "baseline"),
            "bonus_005": evaluate_doubles(frame, config, "bonus", bonus=0.05),
            "bonus_010": evaluate_doubles(frame, config, "bonus", bonus=0.10),
            "bonus_015": evaluate_doubles(frame, config, "bonus", bonus=0.15),
            "bonus_020": evaluate_doubles(frame, config, "bonus", bonus=0.20),
            "restricted": evaluate_doubles(frame, config, "restricted"),
            "anti_over": evaluate_doubles(frame, config, "anti_over"),
        }

    labels = {
        "baseline": "V0 baseline (activa)",
        "bonus_005": "V1 bonus 0.05",
        "bonus_010": "V1 bonus 0.10",
        "bonus_015": "V1 bonus 0.15",
        "bonus_020": "V1 bonus 0.20",
        "restricted": "V2 restringido rango",
        "anti_over": "V3 anti-sobreconfianza",
    }
    print("\n" + "=" * 88)
    print("RESULTADOS WALK-FORWARD 3 DOBLES (bloques de 15, proxy)")
    print("=" * 88)
    print(f"{'Variante':<26} {'media':>6} {'std':>6} {'bloques':>8}   por temporada")
    for key, label in labels.items():
        blocks = pd.concat([all_blocks[season][key] for season in TARGET_SEASONS], ignore_index=True)
        summary = summarize(blocks, label, {s: all_blocks[s][key] for s in TARGET_SEASONS})
        results[key] = summary
        per = " | ".join(f"{s[-2:]}: {v:.3f}" for s, v in summary["per_season"].items())
        print(f"{label:<26} {summary['mean_hits']:>6.3f} {summary['std']:>6.3f} {summary['n_blocks']:>8}   {per}")
    print("-" * 88)
    print("Referencias: proxy activo README 8,65/15 | mercado 8,55/15")
    print("\nNota: la mejora debe ser consistente (media > baseline y, idealmente,")
    print("std baja entre temporadas) para considerarla; no vale una sola temporada.")


if __name__ == "__main__":
    run_experiment()
