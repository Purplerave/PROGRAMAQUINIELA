"""Tests rápidos del experimento de ensembles P0.2.

No ejecutan el backtest completo (eso vive en el script); validan las funciones
puras de construcción de brazos y de evaluación económica por temporada, que
son la parte con lógica delicada (blend con pesos activos, regla de divergencia,
agregación y regla de decisión).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "EXPERIMENTO_ENSEMBLES_ECONOMICO",
    ROOT / "scripts" / "backtests" / "EXPERIMENTO_ENSEMBLES_ECONOMICO.py",
)
exp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp)


def _frame(n=14):
    rng = np.random.default_rng(0)
    rows = []
    for _ in range(n):
        m = rng.dirichlet([5, 3, 3])
        h = rng.dirichlet([4, 4, 3])
        rows.append(
            {
                "market_1": m[0], "market_x": m[1], "market_2": m[2],
                "hgb_prob_1": h[0], "hgb_prob_x": h[1], "hgb_prob_2": h[2],
                "logit_prob_1": h[0], "logit_prob_x": h[1], "logit_prob_2": h[2],
                "poisson_1": h[0], "poisson_x": h[1], "poisson_2": h[2],
                "result": "1",
                "division": "Primera",
            }
        )
    return pd.DataFrame(rows)


def test_market_probs_normalized():
    df = _frame()
    p = exp._market_probs(df)
    assert p.shape == (14, 3)
    np.testing.assert_allclose(p.sum(axis=1), 1.0, atol=1e-9)


def test_blend_active_uses_config_weights():
    df = _frame()
    p = exp._blend_active(df)
    np.testing.assert_allclose(p.sum(axis=1), 1.0, atol=1e-9)
    # Con market=0.951 el blend debe estar dominado por el mercado.
    market = exp._market_probs(df)
    # correlación alta entre blend y mercado
    assert np.corrcoef(p.ravel(), market.ravel())[0, 1] > 0.9


def test_divergence_only_moderate_range():
    # Construye un caso con divergencia fuerte (>0.10): NO debe empujar.
    df = _frame(14)
    df.loc[0, ["market_1", "market_x", "market_2"]] = [0.2, 0.3, 0.5]
    df.loc[0, ["hgb_prob_1", "hgb_prob_x", "hgb_prob_2"]] = [0.6, 0.2, 0.2]  # diff_1 = +0.4
    market = exp._market_probs(df)
    diverg = exp._divergence_probs(df)
    # fuera del rango [0.05,0.10] no cambia respecto al mercado (renormalizado)
    np.testing.assert_allclose(diverg[0], market[0], atol=1e-9)


def test_divergence_pushes_in_moderate_range():
    df = _frame(14)
    df.loc[0, ["market_1", "market_x", "market_2"]] = [0.30, 0.35, 0.35]
    df.loc[0, ["hgb_prob_1", "hgb_prob_x", "hgb_prob_2"]] = [0.37, 0.33, 0.30]  # diff_1=+0.07
    market = exp._market_probs(df)
    diverg = exp._divergence_probs(df)
    # el signo 1 debe subir respecto al mercado
    assert diverg[0, 0] > market[0, 0]


def test_evaluate_arm_season_shapes():
    # 30 partidos = 2 bloques de 15 -> 2 jornadas de 14
    df = pd.concat([_frame(15), _frame(15)], ignore_index=True)
    probs = exp._market_probs(df)
    prizes = {14: 80000.0, 13: 2000.0, 12: 200.0, 11: 25.0, 10: 6.0}
    res = exp._evaluate_arm_season(probs, df, prizes)
    assert res["jornadas"] == 2
    assert 0.0 <= res["p_ge_12"] <= 1.0
    assert res["cost_eur"] == pytest.approx(12.0)  # 2 jornadas × 6 €


def test_decision_rule_flags_no_substitution_when_inconsistent():
    # brazo candidato mejor en 1 sola temporada -> no sustituye
    per_season = []
    for i in range(5):
        base = {"p_ge_12": 0.05, "roi": 0.1, "cost_eur": 6, "prize_eur": 6.6, "accuracy_simple": 0.5, "mean_hits": 8}
        cand_better = i == 0
        cand = dict(base, p_ge_12=0.06 if cand_better else 0.04)
        per_season.append({"season": f"20{i}", "mercado_hgb": base, "solo_mercado": cand})
    agg = exp._aggregate(per_season)
    dec = exp._decision(per_season, agg)
    assert dec["solo_mercado"]["sustituye_al_activo"] is False
