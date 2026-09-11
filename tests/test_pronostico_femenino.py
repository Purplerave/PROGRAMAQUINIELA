"""Pruebas del pronóstico femenino de jornada (Liga F, fuera del motor)."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from scripts.datos.PRONOSTICO_FEMENINO_JORNADA import (
    PARTIDOS_FUENTES,
    blend_probs,
    build_femenino_package,
    implied_probs,
    pct_to_probs,
    recommendation,
)


class TestImpliedProbs:
    def test_normaliza_cuotas(self):
        probs = implied_probs((2.00, 3.00, 6.00))
        assert abs(sum(probs.values()) - 1.0) < 1e-9
        assert probs["1"] > probs["X"] > probs["2"]

    def test_pct_a_prob_normalizado(self):
        probs = pct_to_probs((60, 30, 10))
        assert abs(sum(probs.values()) - 1.0) < 1e-9
        assert abs(probs["1"] - 0.6) < 1e-9


class TestBlend:
    def test_con_mercado_usa_pesos_mercado(self):
        mercado = {"1": 0.4, "X": 0.3, "2": 0.3}
        modelo = {"1": 0.5, "X": 0.2, "2": 0.3}
        lae = {"1": 0.6, "X": 0.2, "2": 0.2}
        probs = blend_probs(mercado, modelo, lae, None,
                            {"con_mercado": (0.5, 0.3, 0.2),
                             "sin_mercado": (0.5, 0.3, 0.2)})
        assert abs(probs["1"] - (0.5 * 0.4 + 0.3 * 0.5 + 0.2 * 0.6)) < 1e-9
        assert abs(sum(probs.values()) - 1.0) < 1e-9

    def test_sin_mercado_no_exige_lae_vacia(self):
        modelo = {"1": 0.5, "X": 0.2, "2": 0.3}
        probs = blend_probs(None, modelo, None, None,
                            {"con_mercado": (0.5, 0.3, 0.2),
                             "sin_mercado": (0.5, 0.3, 0.2)})
        assert abs(sum(probs.values()) - 1.0) < 1e-9
        assert probs["1"] > probs["X"]


class TestRecommendation:
    def test_favorito_claro_simple(self):
        rec = recommendation({"1": 0.70, "X": 0.20, "2": 0.10})
        assert rec["signo"] == "1"
        assert rec["confianza"] == "alta"
        assert rec["doble"] is None

    def test_abierto_sugiere_doble(self):
        rec = recommendation({"1": 0.48, "X": 0.32, "2": 0.20})
        assert rec["signo"] == "1"
        assert rec["doble"] == "1X"
        assert rec["confianza"] in {"media", "media_baja", "baja"}


class TestPaqueteJ6:
    def test_paquete_j6_con_fuentes_documentadas(self):
        package = build_femenino_package(6)
        assert package["jornada"] == 6
        assert len(package["partidos"]) == len(PARTIDOS_FUENTES) == 4
        for p in package["partidos"]:
            assert p["num"] in {11, 12, 13, 14}
            probs = p["probabilidades"]
            assert abs(sum(probs.values()) - 1.0) < 1e-6
            assert p["recomendacion"]["signo"] in {"1", "X", "2"}
            # Toda probabilidad debe venir de fuentes documentadas
            assert "mercado" in p["fuentes"]
            assert "modelo_forebet" in p["fuentes"]
            assert "comunidad" in p["fuentes"]

    def test_partido_14_tiene_mercado(self):
        package = build_femenino_package(6)
        m14 = next(p for p in package["partidos"] if p["num"] == 14)
        assert m14["fuentes"]["mercado"]["odds_1x2"] is not None
        assert m14["fuentes"]["mercado"]["prob_implied"] is not None

    def test_sin_mercado_documentado_como_tal(self):
        package = build_femenino_package(6)
        for num in (12, 13):
            m = next(p for p in package["partidos"] if p["num"] == num)
            assert m["fuentes"]["mercado"]["odds_1x2"] is None
            assert "Sin mercado" in m["fuentes"]["mercado"]["origen"]
