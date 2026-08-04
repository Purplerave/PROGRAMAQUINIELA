"""Tests del OPTIMIZADOR_COLUMNAS (P0, auditoría externa 04/08/2026).

Cubren:
- Las 364 combinaciones de tres dobles sobre 14 partidos.
- La selección por segunda probabilidad (maximizar aciertos esperados).
- El cálculo EXACTO de P(≥10), P(≥11), P(≥12), P(≥13) y P(≥14).
- El contrato fijo 3 dobles / 8 columnas / 6,00 EUR.
- El Pleno al 15 separado del desarrollo.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import pytest

from OPTIMIZADOR_COLUMNAS import (
    SIGN_INDEX,
    build_double_development,
    columns_contract,
    coverage_distribution,
    enumerate_columns,
    evaluate_all_three_doubles,
    expected_hits,
    optimize_jornada,
    second_probabilities,
    three_double_combinations,
)

SIGNS = ("1", "X", "2")


def synthetic_probs(n: int = 14, seed: int = 7) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    probs = []
    for _ in range(n):
        p = rng.random(3) + 0.1
        probs.append(p / p.sum())
    return probs


# --- 364 combinaciones --------------------------------------------------------

def test_tres_dobles_364_combinaciones():
    combos = three_double_combinations(14, 3)
    assert len(combos) == math.comb(14, 3) == 364
    assert len(set(combos)) == 364
    for combo in combos:
        assert len(combo) == 3
        assert len(set(combo)) == 3
        assert all(0 <= i < 14 for i in combo)
    assert combos[0] == (0, 1, 2)
    assert combos[-1] == (11, 12, 13)


def test_combinaciones_orden_lexicografico_determinista():
    combos_a = three_double_combinations(14, 3)
    combos_b = three_double_combinations(14, 3)
    assert combos_a == combos_b == list(itertools.combinations(range(14), 3))


# --- Selección por segunda probabilidad ---------------------------------------

def test_seleccion_equivale_a_top3_segunda_probabilidad():
    probs = synthetic_probs()
    segunda = second_probabilities(probs)
    top3 = sorted(range(14), key=lambda i: segunda[i], reverse=True)[:3]
    best_combo = tuple(sorted(top3))
    resultado = evaluate_all_three_doubles(probs, 3)
    assert tuple(resultado["mejor_combinacion"]["dobles"]) == best_combo


def test_seleccion_maximiza_aciertos_esperados_exhaustivamente():
    probs = synthetic_probs()
    resultado = evaluate_all_three_doubles(probs, 3)
    assert resultado["n_combinaciones"] == 364
    mejor = resultado["mejor_combinacion"]
    # Verificación exhaustiva independiente: ninguna combinación supera al ganador.
    max_esperado = -1.0
    for combo in three_double_combinations(14, 3):
        selected = build_double_development(probs, combo)
        esperado = expected_hits(probs, selected)
        max_esperado = max(max_esperado, esperado)
    assert mejor["aciertos_esperados"] == pytest.approx(max_esperado)
    # El ranking por E[aciertos] y por suma de segunda probabilidad es idéntico.
    ranking = resultado["ranking_completo"]
    by_segunda = sorted(
        ranking, key=lambda r: r["suma_segunda_probabilidad"], reverse=True
    )
    assert [r["dobles"] for r in ranking] == [r["dobles"] for r in by_segunda]


def test_seleccion_determinista():
    probs = synthetic_probs()
    r1 = evaluate_all_three_doubles(probs, 3)
    r2 = evaluate_all_three_doubles(probs, 3)
    assert r1["mejor_combinacion"] == r2["mejor_combinacion"]
    assert r1["ranking_completo"] == r2["ranking_completo"]


def test_dobles_llevan_los_dos_signos_mas_probables():
    probs = synthetic_probs()
    selected = build_double_development(probs, (0, 1, 2))
    for i in (0, 1, 2):
        _, signs = selected[i]
        assert len(signs) == 2
        top2 = set(int(j) for j in np.argsort(probs[i])[-2:])
        assert set(SIGN_INDEX[s] for s in signs) == top2
    for i in (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13):
        _, signs = selected[i]
        assert len(signs) == 1
        assert SIGNS[int(np.argmax(probs[i]))] == signs[0]


# --- Probabilidades exactas ---------------------------------------------------

def test_distribucion_exacta_coincide_con_brute_force():
    """P(k aciertos) por convolución == enumeración exhaustiva de 2^14 casos."""
    rng = np.random.default_rng(0)
    probs = []
    for _ in range(14):
        p = rng.random(3) + 0.1
        probs.append(p / p.sum())
    selected = build_double_development(probs, (1, 5, 9))
    dist = coverage_distribution(probs, selected)
    assert len(dist) == 15

    # Brute force sobre los 2^14 subconjuntos de partidos acertados.
    coberturas = [
        sum(probs[idx][SIGN_INDEX[s]] for s in signs)
        for idx, (_, signs) in enumerate(selected)
    ]
    exact = np.zeros(15)
    for mask in range(2 ** 14):
        prob = 1.0
        hits = 0
        for i in range(14):
            if mask & (1 << i):
                prob *= coberturas[i]
                hits += 1
            else:
                prob *= 1.0 - coberturas[i]
        exact[hits] += prob
    np.testing.assert_allclose(dist, exact, atol=1e-12)


def test_probabilidades_tail_exactas():
    probs = synthetic_probs()
    resultado = evaluate_all_three_doubles(probs, 3)
    exactas = resultado["mejor_combinacion"]["probabilidades_exactas"]
    assert set(exactas) == {"p_ge_10", "p_ge_11", "p_ge_12", "p_ge_13", "p_ge_14"}
    # Monótonas decrecientes y en [0, 1].
    valores = [exactas[f"p_ge_{k}"] for k in (10, 11, 12, 13, 14)]
    assert all(0.0 <= v <= 1.0 for v in valores)
    assert valores == sorted(valores, reverse=True)
    # P(>=14) == producto de coberturas (único caso con 14 aciertos).
    mejor = resultado["mejor_combinacion"]
    selected = build_double_development(probs, tuple(mejor["dobles"]))
    dist = coverage_distribution(probs, selected)
    assert exactas["p_ge_14"] == pytest.approx(float(dist[14]))
    assert dist.sum() == pytest.approx(1.0)


def test_todas_las_combinaciones_tienen_probabilidades_exactas_validas():
    probs = synthetic_probs()
    resultado = evaluate_all_three_doubles(probs, 3)
    for entry in resultado["ranking_completo"]:
        p = entry["probabilidades_exactas"]
        assert set(p) == {"p_ge_10", "p_ge_11", "p_ge_12", "p_ge_13", "p_ge_14"}
        assert 0.0 <= p["p_ge_10"] <= 1.0
        assert p["p_ge_10"] >= p["p_ge_14"]


def test_ticket_uniforme_matches_binomial():
    """Con todas las probabilidades uniformes (1/3), la distribución de
    aciertos de 14 simples es Binomial(14, 1/3)."""
    uniforme = [np.full(3, 1 / 3) for _ in range(14)]
    selected = build_double_development(uniforme, ())
    dist = coverage_distribution(uniforme, selected)
    esperado = np.array(
        [math.comb(14, k) * (1 / 3) ** k * (2 / 3) ** (14 - k) for k in range(15)]
    )
    np.testing.assert_allclose(dist, esperado, atol=1e-12)


# --- Contrato de columnas en la jornada real ----------------------------------

def test_jornada_real_contrato_3_dobles_8_columnas():
    payload = optimize_jornada(74, fuente_prob="q15", publico="lae", n_sims=2000)
    assert payload["n_dobles"] == 3
    assert payload["n_columnas"] == 8
    assert payload["coste_euros"] == 6.0
    desarrollo = payload["desarrollo"]
    assert len(desarrollo) == 14
    n_dobles = sum(1 for d in desarrollo if len(d["signos"]) == 2)
    n_simples = sum(1 for d in desarrollo if len(d["signos"]) == 1)
    assert n_dobles == 3
    assert n_simples == 11
    # 8 columnas reales = producto cartesiano.
    selected = [(d["label"], tuple(d["signos"])) for d in desarrollo]
    assert len(enumerate_columns(selected)) == 8
    assert payload["contrato"] == columns_contract()


def test_jornada_real_probabilidades_exactas_y_evaluacion_exhaustiva():
    payload = optimize_jornada(74, fuente_prob="q15", publico="lae", n_sims=2000)
    exactas = payload["probabilidades_exactas"]
    assert set(exactas) == {"p_ge_10", "p_ge_11", "p_ge_12", "p_ge_13", "p_ge_14"}
    ev = payload["evaluacion_exhaustiva"]
    assert ev["n_combinaciones"] == 364
    assert len(ev["ranking_completo"]) == 364
    assert ev["mejor_combinacion"]["probabilidades_exactas"] == exactas
    # Distribución normalizada.
    dist = payload["distribucion_aciertos"]
    assert sum(dist.values()) == pytest.approx(1.0)


def test_jornada_real_pleno15_separado():
    payload = optimize_jornada(74, fuente_prob="q15", publico="lae", n_sims=2000)
    assert payload["pleno15"] is not None
    assert payload["pleno15"]["num"] == 15
    assert payload["pleno15"]["signo"] in SIGNS
    # El partido 15 no participa en el desarrollo ni en las columnas.
    assert all(d["num"] != 15 for d in payload["desarrollo"])
    assert len(payload["columnas_top"]) == 8
    assert all(len(col) == 14 for col in payload["columnas_top"])


def test_contrato_inconsistente_rechazado():
    with pytest.raises(ValueError):
        columns_contract({"columns": {"doubles": 3, "columns_per_ticket": 16}})
    with pytest.raises(ValueError):
        columns_contract(
            {"columns": {"doubles": 3, "columns_per_ticket": 8, "price_per_column": 1.0, "max_cost": 6.0}}
        )
