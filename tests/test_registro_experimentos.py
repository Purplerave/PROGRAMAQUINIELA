"""Tests del registro append-only de experimentos (ROADMAP #4)."""

from __future__ import annotations

import json

import pytest

from scripts.registro_experimentos import (
    CAMPOS_OBLIGATORIOS,
    cargar,
    listar,
    registrar,
)


@pytest.fixture
def ruta(tmp_path):
    return tmp_path / "registro_test.json"


def test_empieza_vacio_y_appenda_ids_incrementales(ruta):
    a = registrar("exp a", "IMPLEMENTADO", path=ruta)
    b = registrar("exp b", "RECHAZADO", path=ruta)
    assert a["id"] == 1
    assert b["id"] == 2
    entradas = listar(ruta)
    assert [e["id"] for e in entradas] == [1, 2]
    assert [e["nombre"] for e in entradas] == ["exp a", "exp b"]


def test_es_append_only_no_borra_existentes(ruta):
    registrar("exp a", "RECHAZADO", path=ruta)
    # Re-añadimos varias veces: nunca se pierden entradas previas.
    for i in range(3):
        registrar(f"exp {i}", "IMPLEMENTADO", path=ruta)
    entradas = listar(ruta)
    assert len(entradas) == 4
    # Las entradas previas conservan su id y contenido.
    assert entradas[0]["nombre"] == "exp a"
    assert [e["id"] for e in entradas] == [1, 2, 3, 4]


def test_guarda_fecha_y_metricas(ruta):
    e = registrar(
        "exp",
        "RECHAZADO",
        fecha="2026-08-03",
        configuracion="config x",
        metricas={"acu": 0.51},
        razon="razon",
        referencia="REVISION_12",
        path=ruta,
    )
    assert e["fecha"] == "2026-08-03"
    assert e["metricas"] == {"acu": 0.51}
    persistido = json.loads(ruta.read_text(encoding="utf-8"))
    assert persistido["registro"][-1]["referencia"] == "REVISION_12"


def test_falta_campo_obligatorio_levanta_error(ruta):
    with pytest.raises(ValueError):
        registrar("sin resultado", None, path=ruta)


def test_escribir_false_no_toca_archivo(ruta):
    antes = listar(ruta)
    registrar("exp", "RECHAZADO", path=ruta, escribir=False)
    assert listar(ruta) == antes


def test_registro_seed_incluye_historico():
    # El registro sembrado con los experimentos previos debe existir y tener entradas.
    from scripts.registro_experimentos import REGISTRO_PATH

    assert REGISTRO_PATH.is_file()
    entradas = listar(REGISTRO_PATH)
    assert len(entradas) >= 5
    nombres = " | ".join(e["nombre"] for e in entradas)
    assert "Features futuras" in nombres
