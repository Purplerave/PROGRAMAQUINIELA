"""Tests de OPTIMIZADOR_COLUMNAS: desarrollo, límites de dobles/triples y degradación.

Cubre el bug corregido: al degradar un doble/triple por límite de presupuesto,
el simple resultante debe ser el mejor según la utilidad del optimizador
(probable y poco popular), nunca el signo local "1" por defecto.
"""

from __future__ import annotations

import numpy as np
import pytest

import OPTIMIZADOR_COLUMNAS as opt


def probs_where_favorite_is_x() -> list[np.ndarray]:
    """Tres partidos cuyo favorito por utilidad es X (popular el 1)."""
    return [
        np.array([0.30, 0.45, 0.25]),  # favorito X
        np.array([0.25, 0.50, 0.25]),  # favorito X
        np.array([0.30, 0.35, 0.35]),  # favorito 2 (X2 muy próximo)
    ]


def probs_where_favorite_is_2() -> list[np.ndarray]:
    return [
        np.array([0.25, 0.25, 0.50]),
        np.array([0.20, 0.30, 0.50]),
    ]


def test_enforce_limits_degrada_al_mejor_simple_no_a_1():
    probs = probs_where_favorite_is_x()
    public = [np.array([0.60, 0.25, 0.15])] * 3  # el público sobreapuesta el 1
    # Desarrollo con 3 dobles: 1X, 1X, X2
    selected = [("1X", ("1", "X")), ("1X", ("1", "X")), ("X2", ("X", "2"))]
    out = opt.enforce_limits(selected, probs, public, alpha=0.6, eta=0.5,
                             max_dobles=2, max_triples=None)
    assert sum(1 for _, s in out if len(s) == 2) == 2
    # Ningún simple degradado debe ser "1" si el mejor simple era X o 2
    for i, (label, signs) in enumerate(out):
        if len(signs) == 1:
            expected = opt.SIGNS[int(np.argmax(opt.log_value(probs[i], public[i], 0.6)))]
            assert signs[0] == expected, f"degradado a {signs[0]}, esperado {expected}"


def test_enforce_limits_degradacion_elige_mejor_utilidad():
    probs = [np.array([0.34, 0.33, 0.33]), np.array([0.40, 0.30, 0.30])]
    public = [np.array([1 / 3, 1 / 3, 1 / 3])] * 2
    selected = [("12", ("1", "2")), ("1X", ("1", "X"))]
    out = opt.enforce_limits(selected, probs, public, alpha=0.0, eta=0.5,
                             max_dobles=1, max_triples=None)
    degraded = [s for _, s in out if len(s) == 1]
    assert len(degraded) == 1
    # Con alpha=0 la utilidad es la probabilidad: el degradado es el favorito "1"
    assert degraded[0] == ("1",)
    # Y debe degradarse el doble de menor cobertura (el 12, cobertura 0.67 < 0.70)
    assert out[0][0] == "1"


def test_enforce_limits_con_triples_elige_mejor_simple():
    probs = [np.array([0.30, 0.40, 0.30]), np.array([0.20, 0.60, 0.20])]
    public = [np.array([0.5, 0.3, 0.2]), np.array([0.4, 0.4, 0.2])]
    selected = [("1X2", ("1", "X", "2")), ("X2", ("X", "2"))]
    out = opt.enforce_limits(selected, probs, public, alpha=0.0, eta=0.5,
                             max_dobles=None, max_triples=0)
    triple_degraded = [s for _, s in out if len(s) == 3]
    assert not triple_degraded
    # El triple debe degradar al mejor simple: partido 2 -> X (0.60), partido 1 -> X (0.40)
    labels = [l for l, _ in out]
    assert "X" in labels


def test_develop_ticket_respeta_limites():
    rng = np.random.default_rng(7)
    probs = [p / p.sum() for p in rng.random((10, 3))]
    public = [np.array([0.45, 0.30, 0.25])] * 10
    selected, _ = opt.develop_ticket(probs, public, budget=128, alpha=0.3,
                                     eta=0.5, max_dobles=2, max_triples=0)
    n_dobles = sum(1 for _, s in selected if len(s) == 2)
    n_triples = sum(1 for _, s in selected if len(s) == 3)
    assert n_dobles <= 2
    assert n_triples == 0
    # Todos los simples son el favorito por utilidad de su partido
    for i, (_, signs) in enumerate(selected):
        if len(signs) == 1:
            w = opt.log_value(probs[i], public[i], 0.3)
            assert signs[0] == opt.SIGNS[int(np.argmax(w))]
