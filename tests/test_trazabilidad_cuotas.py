# -*- coding: utf-8 -*-
"""Trazabilidad temporal de cuotas en produccion (plan Fase 4).

Politica: no se inventan timestamps. Si la fuente no declara
`odds_observed_at`, el partido queda `no_auditado`. La invariante
    odds_observed_at <= prediction_cutoff_at < kickoff_at
se valida solo en partidos con los tres campos.
"""
from MOTOR_PREDICCION_JORNADA import attach_odds_traceability


def _jornada(partidos):
    return {"partidos": partidos}


def test_partido_completo_es_auditado_y_cumple_invariante():
    jornada = _jornada([
        {
            "num": 1,
            "odds_observed_at": "2026-08-20T10:00:00",
            "kickoff_at": "2026-08-22T18:00:00",
        }
    ])
    bloque = attach_odds_traceability(jornada, "2026-08-21T12:00:00")
    assert bloque["auditados"] == 1
    assert bloque["no_auditados"] == 0
    assert bloque["violaciones_invariante"] == 0


def test_sin_odds_observed_at_se_marca_no_auditado_y_no_se_inventa():
    jornada = _jornada([{"num": 1, "fecha": "2026-08-22"}])
    bloque = attach_odds_traceability(jornada, "2026-08-21")
    assert bloque["no_auditados"] == 1
    det = bloque["detalle"][0]
    assert det["estado"] == "no_auditado"
    assert det["motivo"] == "odds_observed_at_ausente"
    assert det["odds_observed_at"] is None


def test_cutoff_posterior_al_kickoff_es_violacion():
    jornada = _jornada([
        {
            "num": 2,
            "odds_observed_at": "2026-08-20T10:00:00",
            "kickoff_at": "2026-08-22T18:00:00",
        }
    ])
    bloque = attach_odds_traceability(jornada, "2026-08-23T12:00:00")
    assert bloque["violaciones_invariante"] >= 1
    assert any(
        "corte_no_anterior_al_kickoff" in v.get("issues", [])
        for v in bloque["violaciones"]
    )


def test_mixto_auditable_y_no_auditable():
    jornada = _jornada([
        {
            "num": 1,
            "odds_observed_at": "2026-08-20T10:00:00",
            "kickoff_at": "2026-08-22T18:00:00",
        },
        {"num": 2},
    ])
    bloque = attach_odds_traceability(jornada, "2026-08-21T09:00:00")
    assert bloque["auditados"] == 1
    assert bloque["no_auditados"] == 1
    estados = {d["num"]: d["estado"] for d in bloque["detalle"]}
    assert estados[1] == "auditable"
    assert estados[2] == "no_auditado"


def test_jornada_vacia_devuelve_bloque_coherente():
    bloque = attach_odds_traceability(_jornada([]), "2026-08-21")
    assert bloque["total_partidos"] == 0
    assert bloque["auditados"] == 0
    assert bloque["no_auditados"] == 0
