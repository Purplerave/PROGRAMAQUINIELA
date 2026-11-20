"""Contrato del walk-forward anidado (auditoría 20/11/2026, P1).

La comparación entre brazos es la que decide si la ventaja publicada es
sobreajuste. Estas pruebas fijan la estadística y evitan que una edición futura
la convierta en un número favorable por accidente.
"""

import argparse

import numpy as np
import pandas as pd
import pytest

from scripts.backtests import WALK_FORWARD_ANIDADO as anidado


def test_mcnemar_simetrico_y_con_ic():
    rng = np.random.default_rng(0)
    a = rng.random(500) < 0.5
    b = rng.random(500) < 0.5
    datos = anidado._mcnemar(a, b)
    assert datos["n"] == 500
    assert datos["solo_a"] + datos["solo_b"] <= 500
    assert 0.0 <= datos["mcnemar_pvalue"] <= 1.0
    assert datos["gap_ci95"][0] <= datos["gap"] <= datos["gap_ci95"][1]


def test_mcnemar_identico_no_es_significativo():
    a = np.array([True, False, True, False])
    datos = anidado._mcnemar(a, a.copy())
    assert datos["gap"] == 0.0
    assert datos["mcnemar_pvalue"] == 1.0


def test_resumen_brazo_usa_solo_partidos_con_mercado():
    frame = pd.DataFrame(
        {
            "latest_hit": [True, True, False, True],
            "favorite_market_hit": [True, False, False, np.nan],
        }
    )
    datos = anidado._resumen_brazo(frame)
    assert datos["n"] == 3
    assert datos["acierto"] == pytest.approx(2 / 3)
    assert datos["mercado"] == pytest.approx(1 / 3)
    assert datos["gap"] > 0


def test_resumen_brazo_vacio():
    frame = pd.DataFrame({"latest_hit": [], "favorite_market_hit": []})
    assert anidado._resumen_brazo(frame) == {"n": 0}


def test_valida_formato_de_temporada():
    assert anidado._season("2024-2025") == "2024-2025"
    with pytest.raises(argparse.ArgumentTypeError):
        anidado._season("2024-2026")
    with pytest.raises(argparse.ArgumentTypeError):
        anidado._season("24-25")


def test_el_informe_se_escribe_con_estructura_esperada(tmp_path):
    """Comprueba el contrato del JSON con un payload mínimo, sin entrenar."""
    from scripts.json_output import write_json

    payload = {"protocolo": "walk_forward_anidado_v1", "ventana": {"desde": "2019-2020"}}
    destino = tmp_path / "anidado.json"
    write_json(destino, payload)
    import json

    assert json.loads(destino.read_text(encoding="utf-8"))["protocolo"] == "walk_forward_anidado_v1"
