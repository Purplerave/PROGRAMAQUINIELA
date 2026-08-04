"""Tests rápidos de P1.0 (consolidación de calibración).

No ejecutan el walk-forward completo (eso vive en el script). Validan las
funciones puras de evaluación económica por brazo y la regla de decisión, que
son la lógica delicada. El ajuste leak-free del calibrador se valida en el
script (integración) y por los tests de calibración existentes.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "CONSOLIDAR_CALIBRACION",
    ROOT / "scripts" / "backtests" / "CONSOLIDAR_CALIBRACION.py",
)
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)


def _frame(n=15, seed=0, result="1"):
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        m = rng.dirichlet([5, 3, 3])
        rows.append(
            {
                "latest_prob_1": m[0], "latest_prob_x": m[1], "latest_prob_2": m[2],
                "result": result,
                "division": "Primera",
            }
        )
    return pd.DataFrame(rows)


def test_renorm_sums_to_one():
    m = np.array([[2.0, 1.0, 1.0], [0.0, 0.0, 0.0]])
    out = cc._renorm(m)
    np.testing.assert_allclose(out.sum(axis=1), 1.0, atol=1e-9)


def test_evaluate_arm_shapes_and_cost():
    df = pd.concat([_frame(15, 1), _frame(15, 2)], ignore_index=True)
    probs = cc._renorm(df[["latest_prob_1", "latest_prob_x", "latest_prob_2"]].to_numpy(float))
    prizes = {14: 80000.0, 13: 2000.0, 12: 200.0, 11: 25.0, 10: 6.0}
    res = cc._evaluate_arm(probs, df, prizes)
    assert res["jornadas"] == 2
    assert res["cost_eur"] == pytest.approx(12.0)
    assert 0.0 <= res["p_ge_12"] <= 1.0


def test_decision_no_substitution_when_calibrated_worse():
    # calibrado peor que activo en todas las temporadas -> no sustituye
    per_season = []
    for i in range(5):
        activo = {"p_ge_12": 0.05, "roi": 0.2, "cost_eur": 6, "prize_eur": 7.2,
                  "accuracy_simple": 0.5, "mean_hits": 8, "p_ge_13": 0.0}
        calibrado = dict(activo, p_ge_12=0.02, prize_eur=6.1)
        per_season.append({"season": f"20{i}", "activo": activo, "calibrado": calibrado})
    agg = cc._aggregate(per_season)
    dec = cc._decision(per_season, agg)
    assert dec["sustituye"] is False
    assert dec["wins_p_ge_12_ultimas_5"] == 0


def test_decision_substitutes_when_calibrated_consistently_better():
    per_season = []
    for i in range(5):
        activo = {"p_ge_12": 0.03, "roi": 0.1, "cost_eur": 6, "prize_eur": 6.6,
                  "accuracy_simple": 0.5, "mean_hits": 8, "p_ge_13": 0.0}
        calibrado = dict(activo, p_ge_12=0.05, prize_eur=7.2)
        per_season.append({"season": f"20{i}", "activo": activo, "calibrado": calibrado})
    agg = cc._aggregate(per_season)
    dec = cc._decision(per_season, agg)
    assert dec["wins_p_ge_12_ultimas_5"] == 5
    assert dec["sustituye"] is True
