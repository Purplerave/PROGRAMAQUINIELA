"""Tests del contrato de columnas P0 (auditoría externa 04/08/2026).

Contrato: 3 dobles = 8 columnas a 0,75 EUR = coste máximo 6,00 EUR.
Verifica además que la ambigüedad previa (`default_budget`, `beam_size`) ha
desaparecido de la configuración.
"""

from __future__ import annotations

import json
import math

import settings
from OPTIMIZADOR_COLUMNAS import columns_contract


def test_contract_fixed_values():
    contract = columns_contract()
    assert contract["doubles"] == 3
    assert contract["columns_per_ticket"] == 8
    assert contract["price_per_column"] == 0.75
    assert contract["max_cost"] == 6.0


def test_contract_identities():
    contract = columns_contract()
    assert 2 ** contract["doubles"] == contract["columns_per_ticket"]
    assert math.isclose(
        contract["columns_per_ticket"] * contract["price_per_column"],
        contract["max_cost"],
        abs_tol=1e-9,
    )


def test_contract_version_present():
    contract = columns_contract()
    assert contract["contract_version"] == "2026-08-04"


def test_no_ambiguous_budget_keys_in_config():
    section = settings.CONFIG.get("columns", {})
    assert isinstance(section, dict)
    assert "default_budget" not in section, "default_budget debe eliminarse (contrato fijo)"
    assert "beam_size" not in section, "beam_size debe eliminarse (contrato fijo)"


def test_no_code_reads_removed_keys():
    """Ningún .py del proyecto LEE las claves ambiguas eliminadas (las menciones
    en prosa de docstrings/tests son documentación, no uso)."""
    import pathlib

    project = pathlib.Path(settings.PROJECT_DIR)
    usage_patterns = (
        'get("default_budget"', 'get("beam_size"',
        "get('default_budget'", "get('beam_size'",
        '["default_budget"]', '["beam_size"]',
        "['default_budget']", "['beam_size']",
    )
    offenders = []
    for path in project.rglob("*.py"):
        if ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        if path.name == "test_config_contract.py":  # este test define los patrones
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in usage_patterns:
            if pattern in text:
                offenders.append(f"{path.relative_to(project)} -> {pattern}")
    assert not offenders, f"El código aún lee claves ambiguas: {offenders}"


def test_contract_is_serializable_and_coherent():
    raw = settings.CONFIG_PATH.read_text(encoding="utf-8")
    parsed = json.loads(raw)  # debe seguir siendo JSON válido
    section = parsed["columns"]
    assert section["doubles"] == 3
    assert section["columns_per_ticket"] == 8
    assert abs(section["columns_per_ticket"] * section["price_per_column"] - section["max_cost"]) < 1e-9


# --------------------------------------------------------------------------- #
# Contrato del ensemble (auditoría 20/11/2026, P1)
# --------------------------------------------------------------------------- #
def test_los_pesos_del_maestro_suman_uno():
    weights = settings.master_model_config()["weights"]
    assert math.isclose(sum(weights.values()), 1.0, abs_tol=1e-9)
    assert set(weights) == {"logit", "hgb", "market", "poisson"}


def test_el_mercado_domina_y_la_documentacion_lo_dice():
    """El motor es «mercado + ajuste pequeño»; que no se vuelva a vender como ensemble."""
    weights = settings.master_model_config()["weights"]
    assert weights["market"] >= 0.9
    assert weights["hgb"] <= 0.1
    readme = (settings.PROJECT_DIR / "README.md").read_text(encoding="utf-8")
    assert "ajuste pequeño" in readme
    assert "no bate al mercado" in readme


def test_la_referencia_no_se_reoptimiza_en_produccion(monkeypatch):
    """`--modo produccion` debe devolver exactamente los pesos publicados."""
    import MOTOR_QUINIELA_MAESTRO as motor

    config = motor.active_hybrid_config()
    assert config["weights"] == settings.master_model_config()["weights"]
