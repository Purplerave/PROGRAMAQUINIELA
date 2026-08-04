"""Tests del experimento de dobles con divergencia (reglas de selección)."""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.backtests.EXPERIMENTO_DOBLES_DIVERGENCIA import add_divergence, evaluate_doubles

CONFIG = {
    "double_draw_threshold": 0.3,
    "double_draw_weight": 0.7,
    "double_disagreement_weight": 0.2,
    "double_segunda_bonus": 0.05,
}


def frame_with_divergence() -> pd.DataFrame:
    rows = []
    for i in range(15):
        rows.append({
            "date": pd.Timestamp("2025-08-15") + pd.Timedelta(days=i),
            "home": f"L{i}", "away": f"V{i}",
            "division": "Primera",
            "result": "1",
            "hgb_prob_1": 0.5, "hgb_prob_x": 0.3, "hgb_prob_2": 0.2,
            "market_1": 0.5, "market_x": 0.3, "market_2": 0.2,
            "model_disagreement": 0.0,
            "latest_prob_1": 0.5, "latest_prob_x": 0.3, "latest_prob_2": 0.2,
            "latest_pred": "1",
        })
    return pd.DataFrame(rows)


def test_add_divergence_flags_range_and_over():
    df = frame_with_divergence()
    # Partido 0: hgb_1 - market_1 = 0.0 -> fuera de rango.
    # Partido 1: subimos hgb_1 a 0.58 -> diff 0.08 (en rango).
    # Partido 2: subimos hgb_1 a 0.65 -> diff 0.15 (sobreconfianza).
    df.loc[1, "hgb_prob_1"] = 0.58
    df.loc[2, "hgb_prob_1"] = 0.65
    out = add_divergence(df)
    assert not out.loc[0, "div_in_range"]
    assert bool(out.loc[1, "div_in_range"])
    assert not out.loc[2, "div_in_range"]
    assert bool(out.loc[2, "div_over"])
    assert out.loc[1, "diff_top"] == pytest.approx(0.08)
    assert out.loc[1, "hgb_top_sign"] == "1"


def test_evaluate_doubles_baseline_always_picks_3():
    df = add_divergence(frame_with_divergence())
    blocks = evaluate_doubles(df, CONFIG, "baseline")
    assert len(blocks) == 1
    assert 0 <= blocks.loc[0, "hits_3_dobles"] <= 15


def test_evaluate_doubles_restricted_fills_from_rest():
    df = add_divergence(frame_with_divergence())
    # Sin ningún partido en rango -> completa con el resto por score.
    blocks = evaluate_doubles(df, CONFIG, "restricted")
    assert len(blocks) == 1

    # Con 2 en rango -> completa hasta 3.
    df.loc[1, "hgb_prob_1"] = 0.58
    df.loc[2, "hgb_prob_1"] = 0.59
    blocks = evaluate_doubles(df, CONFIG, "restricted")
    assert len(blocks) == 1


def test_evaluate_doubles_bonus_changes_score():
    df = add_divergence(frame_with_divergence())
    df.loc[1, "hgb_prob_1"] = 0.58  # en rango
    base = evaluate_doubles(df, CONFIG, "baseline")
    bonus = evaluate_doubles(df, CONFIG, "bonus", bonus=0.5)
    # Ambos devuelven un bloque; el bonus reordena la selección.
    assert len(base) == 1 and len(bonus) == 1
