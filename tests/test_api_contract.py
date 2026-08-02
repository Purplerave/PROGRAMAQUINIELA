from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.motor.GENERAR_CONTRATO_API import (
    ContractValidationError,
    build_api_contract,
    generate_api_contract,
)


def _match(num: int, *, probs=None, apuesta="1X", tipo="doble", confianza=0.7):
    probs = probs or {"1": 0.5, "X": 0.3, "2": 0.2}
    return {
        "num": num,
        "local": f"Local {num}",
        "visitante": f"Visitante {num}",
        "probabilidades": {
            "modelo": probs,
            "fuente_principal": "ensemble_calibrado",
        },
        "fuente_probabilidades": {"modelo_primario": "motor_maestro"},
        "modelo_maestro": {
            "disponible": True,
            "confianza": confianza,
            "calidad": "alta",
            "features_usadas": {"cuotas_disponibles": True},
        },
        "recomendacion_modelo": {
            "disponible": True,
            "signo_principal": "1",
            "apuesta_recomendada": apuesta,
            "tipo_apuesta": tipo,
            "confianza_modelo": confianza,
        },
        "avisos": [],
    }


def _pleno(*, disponible=True):
    mm = {"disponible": disponible, "tipo": "pleno_15_marcador", "calidad": "media"}
    if disponible:
        mm.update({
            "marcador_predicho": "2-1",
            "seleccion": {"local": "2", "visitante": "1"},
        })
    else:
        mm.update({"razon": "modelo_pleno15_no_disponible"})
    return {
        "num": 15,
        "local": "Local 15",
        "visitante": "Visitante 15",
        "modelo_maestro": mm,
    }


def _package(*, pleno_disponible=True):
    return {
        "fecha_generacion": "2026-08-02T20:00:00",
        "modelo_info": {"version": "test_v1"},
        "partidos": [_match(i) for i in range(1, 15)] + [_pleno(disponible=pleno_disponible)],
    }


def test_build_api_contract_valid_package():
    contract = build_api_contract(_package(), jornada=1)

    assert contract["jornada"] == 1
    assert len(contract["partidos"]) == 14
    assert contract["partidos"][0]["probabilidades"] == {"1": 0.5, "X": 0.3, "2": 0.2}
    assert contract["partidos"][0]["fuente"] == "ensemble_calibrado"
    assert contract["partidos"][0]["cuotas_disponibles"] is True
    assert contract["pleno15"]["disponible"] is True
    assert contract["pleno15"]["pronostico_local"] == "2"
    assert contract["pleno15"]["pronostico_visitante"] == "1"


def test_pleno15_no_disponible_no_inventa_1_1():
    contract = build_api_contract(_package(pleno_disponible=False), jornada=1)

    pleno = contract["pleno15"]
    assert pleno["disponible"] is False
    assert pleno["marcador"] is None
    assert pleno["pronostico_local"] is None
    assert pleno["pronostico_visitante"] is None
    assert pleno["motivo"] == "modelo_pleno15_no_disponible"


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda pkg: pkg["partidos"].pop(14), "partido 15"),
        (lambda pkg: pkg["partidos"].append(dict(pkg["partidos"][0])), "duplicados"),
        (lambda pkg: pkg["partidos"][0]["probabilidades"].update({"modelo": {"1": 0.9, "X": 0.2, "2": 0.2}}), "suman"),
        (lambda pkg: pkg["partidos"][0]["probabilidades"].update({"modelo": {"1": 0.5, "X": 0.5}}), "exactamente"),
        (lambda pkg: pkg["partidos"][0]["recomendacion_modelo"].update({"apuesta_recomendada": "1X", "tipo_apuesta": "simple"}), "no coincide"),
        (lambda pkg: pkg["partidos"][0]["recomendacion_modelo"].update({"confianza_modelo": 1.2}), "confianza"),
    ],
)

def test_build_api_contract_rejects_invalid_content(mutate, match):
    pkg = _package()
    mutate(pkg)
    with pytest.raises(ContractValidationError, match=match):
        build_api_contract(pkg, jornada=1)


def test_generate_api_contract_creates_output_parent(tmp_path: Path):
    paquete = tmp_path / "entrada" / "paquete.json"
    paquete.parent.mkdir()
    paquete.write_text(json.dumps(_package(), ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "missing" / "nested" / "api.json"

    contract = generate_api_contract(1, paquete_path=paquete, out_path=out)

    assert out.exists()
    assert json.loads(out.read_text(encoding="utf-8")) == contract


def test_generate_api_contract_rejects_corrupt_json(tmp_path: Path):
    paquete = tmp_path / "bad.json"
    paquete.write_text("{bad", encoding="utf-8")

    with pytest.raises(ContractValidationError, match="corrupto"):
        generate_api_contract(1, paquete_path=paquete, out_path=tmp_path / "out.json")
