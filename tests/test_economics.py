"""Tests de la métrica económica del boleto (P0.1).

Criterios de aceptación del roadmap:
  - La distribución de aciertos coincide EXACTAMENTE con la convolución de
    OPTIMIZADOR_COLUMNAS (única fuente de verdad).
  - P(≥k) coincide con exact_tail_probabilities del optimizador.
  - EV, coste y ROI son coherentes con el contrato P0 (6,00 €).
  - La comparación modelo vs solo-favoritos-de-mercado es consistente.
"""

from __future__ import annotations

import numpy as np
import pytest

import OPTIMIZADOR_COLUMNAS as opt
from evaluation import economics as econ


def _sample_probs(seed: int = 0, n: int = 14):
    rng = np.random.default_rng(seed)
    return [rng.dirichlet([4, 3, 3]) for _ in range(n)]


def test_distribution_matches_optimizer_convolution():
    probs = _sample_probs(1)
    best = opt.evaluate_all_three_doubles(probs, n_doubles=3)
    combo = tuple(best["mejor_combinacion"]["dobles"])
    selected = opt.build_double_development(probs, combo)

    dist_econ = econ.ticket_hit_distribution(probs, selected)
    dist_opt = opt.coverage_distribution(
        [np.asarray(p, dtype=float) / np.sum(p) for p in probs], selected
    )
    np.testing.assert_allclose(dist_econ, dist_opt, rtol=0, atol=1e-12)


def test_distribution_sums_to_one():
    probs = _sample_probs(2)
    result = econ.evaluate_ticket_economics(probs)
    dist = np.array([result["distribucion_aciertos"][str(k)] for k in range(15)])
    assert dist.sum() == pytest.approx(1.0, abs=1e-9)


def test_tail_probabilities_match_optimizer():
    probs = _sample_probs(3)
    result = econ.evaluate_ticket_economics(probs)
    # reconstruye el mismo desarrollo óptimo
    best = opt.evaluate_all_three_doubles(
        [np.asarray(p, float) / np.sum(p) for p in probs], n_doubles=3
    )
    combo = tuple(best["mejor_combinacion"]["dobles"])
    selected = opt.build_double_development(
        [np.asarray(p, float) / np.sum(p) for p in probs], combo
    )
    dist = opt.coverage_distribution(
        [np.asarray(p, float) / np.sum(p) for p in probs], selected
    )
    tails = opt.exact_tail_probabilities(dist)
    for k in (10, 11, 12, 13, 14):
        assert result["probabilidades_premio"]["acumulado_ge"][k] == pytest.approx(
            tails[f"p_ge_{k}"], abs=1e-12
        )


def test_contract_and_cost():
    probs = _sample_probs(4)
    result = econ.evaluate_ticket_economics(probs)
    assert result["coste_eur"] == pytest.approx(6.0)
    assert result["contrato"]["columns_per_ticket"] == 8
    assert result["contrato"]["doubles"] == 3


def test_ev_and_roi_relationship():
    probs = _sample_probs(5)
    result = econ.evaluate_ticket_economics(probs)
    ev = result["ev_premios_eur"]
    cost = result["coste_eur"]
    assert result["ev_neto_eur"] == pytest.approx(ev - cost)
    assert result["roi"] == pytest.approx((ev - cost) / cost)


def test_expected_prize_uses_exact_categories():
    # Distribución degenerada: siempre 12 aciertos -> EV = premio(12).
    dist = np.zeros(15)
    dist[12] = 1.0
    prizes = {14: 80000.0, 13: 2000.0, 12: 200.0, 11: 25.0, 10: 6.0}
    assert econ.expected_prize(dist, prizes) == pytest.approx(200.0)


def test_expected_prize_below_10_pays_zero():
    dist = np.zeros(15)
    dist[9] = 1.0  # 9 aciertos no cobran
    assert econ.expected_prize(dist) == pytest.approx(0.0)


def test_prizes_estimated_flag_present():
    result = econ.evaluate_ticket_economics(_sample_probs(6))
    assert result["premios_estimados"] is True
    assert "ESTIMADO" in result["nota_premios"].upper()


def test_favorite_development_single_column():
    probs = _sample_probs(7)
    selected = econ._favorite_development(probs)
    # 14 simples: cada partido con un único signo.
    assert len(selected) == 14
    assert all(len(signs) == 1 for _, signs in selected)


def test_compare_model_vs_market_keys():
    model = _sample_probs(8)
    market = _sample_probs(9)
    cmp = econ.compare_model_vs_market(model, market)
    assert set(cmp) >= {
        "modelo",
        "solo_favoritos_mercado",
        "delta_ev_neto_eur",
        "delta_roi",
        "delta_p_ge_12",
    }
    # deltas coherentes con los componentes
    assert cmp["delta_ev_neto_eur"] == pytest.approx(
        cmp["modelo"]["ev_neto_eur"] - cmp["solo_favoritos_mercado"]["ev_neto_eur"]
    )


def test_load_prizes_defaults_and_override():
    base = econ.load_prizes({})
    assert base[14] == econ.DEFAULT_PRIZES_EUR[14]
    overridden = econ.load_prizes({"economia": {"prizes_eur": {"14": 123456.0}}})
    assert overridden[14] == pytest.approx(123456.0)
    # el resto de categorías se mantienen por defecto
    assert overridden[10] == econ.DEFAULT_PRIZES_EUR[10]
