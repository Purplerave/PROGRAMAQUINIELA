"""Pruebas del importador scripts/datos/IMPORTAR_JORNADA_WEB.py.

Cubren el contrato del puente entre `Purplerave/liga-maestros-web` y el motor:
- el esquema de salida es el que consumen MOTOR_PREDICCION_JORNADA y
  MOTOR_DECISION_QUINIELISTICA;
- la division sale de la composicion oficial 2026/27, no del historico;
- sin overlay de mercado no se inventan cuotas: quedan a None y se avisa;
- los nombres cortos de quiniela15 resuelven contra historico y priors.
"""

from __future__ import annotations

import pytest

from scripts.datos.IMPORTAR_JORNADA_WEB import convert
from scripts.motor.team_names import resolve_history_name, resolve_prior_name


def scrape_fixture() -> dict:
    partidos = [
        {"num": 1, "local": "Athletic", "visitante": "Sevilla",
         "q15": {"1": 70, "X": 19, "2": 10}, "fecha": "2026-08-22", "hora": "17:00"},
        {"num": 2, "local": "Ceuta", "visitante": "Las Palmas",
         "q15": {"1": 20, "X": 25, "2": 55}, "fecha": "2026-08-22", "hora": "19:00"},
        {"num": 15, "local": "At. Madrid", "visitante": "Villarreal",
         "q15": None, "marcadores_q15": [{"score": "2-1", "pct": 29}],
         "fecha": "2026-08-23", "hora": "17:00"},
    ]
    return {
        "jornada": 2,
        "source_url": "https://www.quiniela15.com/pronostico-quiniela",
        "scraped_at": "2026-08-18T15:31:44",
        "cierre": "sábado 22 de agosto a las 17:00",
        "partidos": partidos,
    }


def mercado_fixture() -> dict[int, dict]:
    return {
        1: {"num": 1, "odd_1": 1.70, "odd_x": 3.58, "odd_2": 5.25,
            "lae": {"1": 63, "X": 22, "2": 15}},
        2: {"num": 2, "odd_1": 3.15, "odd_x": 3.17, "odd_2": 2.22,
            "lae": {"1": 28, "X": 25, "2": 47}},
        15: {"num": 15, "odd_1": 1.87, "odd_x": 3.65, "odd_2": 3.95,
             "goles_local_lae": {"0": 7, "1": 31, "2": 45, "M": 17},
             "goles_visitante_lae": {"0": 20, "1": 49, "2": 22, "M": 9}},
    }


def test_convert_produce_esquema_del_motor():
    payload, warnings = convert(
        scrape_fixture(), 2, mercado_fixture(), {"fuente": "test"}, "fixture"
    )
    # El scrape de prueba trae 3 partidos, no 15: el importador debe decirlo.
    assert any("se esperaban 15" in w for w in warnings)

    por_num = {p["num"]: p for p in payload["partidos"]}

    p1 = por_num[1]
    assert p1["odd_1"] == 1.70 and p1["odd_x"] == 3.58 and p1["odd_2"] == 5.25
    assert p1["q15"] == {"1": 70, "X": 19, "2": 10}
    assert p1["lae"] == {"1": 63, "X": 22, "2": 15}
    assert p1["fecha"] == "2026-08-22" and p1["hora"] == "17:00"

    # El Pleno al 15 no lleva 1X2: lleva marcadores y buckets de goles.
    p15 = por_num[15]
    assert "q15" not in p15 and "lae" not in p15
    assert p15["pleno15"]["marcador_q15"] == {"2-1": 29}
    assert p15["pleno15"]["goles_local_lae"]["2"] == 45

    assert payload["fuentes"]["mercado"] == {"fuente": "test"}


def test_division_sale_de_la_composicion_oficial_2026_27():
    payload, _ = convert(
        scrape_fixture(), 2, mercado_fixture(), {}, "fixture"
    )
    por_num = {p["num"]: p for p in payload["partidos"]}
    # Athletic y At. Madrid en Primera; Ceuta/Las Palmas en Segunda, aunque el
    # historico de football-data todavia refleje la temporada anterior.
    assert por_num[1]["division"] == "Primera"
    assert por_num[2]["division"] == "Segunda"
    assert por_num[15]["division"] == "Primera"


def test_sin_mercado_no_se_inventan_cuotas():
    payload, warnings = convert(scrape_fixture(), 2, {}, {}, "fixture")
    for partido in payload["partidos"]:
        assert partido["odd_1"] is None
        assert partido["odd_x"] is None
        assert partido["odd_2"] is None
    assert any("sin cuotas reales" in w for w in warnings)
    assert all(p.get("lae") is None for p in payload["partidos"] if p["num"] != 15)


@pytest.mark.parametrize(
    ("comun", "historico", "prior"),
    [
        ("Athletic", "Ath Bilbao", "Athletic Club"),
        ("At. Madrid", "Ath Madrid", "Atletico de Madrid"),
        ("R. Santander", "Santander", "R. Racing Club"),
        ("Sevilla", "Sevilla", "Sevilla FC"),
        ("Celta", "Celta", "RC Celta"),
        ("Deportivo", "La Coruna", "RC Deportivo"),
        ("Ceuta", "Ceuta", "AD Ceuta FC"),
    ],
)
def test_nombres_cortos_de_quiniela15_resuelven(comun, historico, prior):
    assert resolve_history_name(comun) == historico
    assert resolve_prior_name(comun) == prior
