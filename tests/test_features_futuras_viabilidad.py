"""Tests del estudio de viabilidad de features futuras (ROADMAP #3).

Comprueba que la verificación de cobertura es reproducible y que ninguna de
las cuatro familias candidatas (xG, bajas, alineaciones, entrenador) tiene
una fuente histórica consistente, mientras que los tiros/SOT sí existen.
"""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATOS_DIR = PROJECT_ROOT / "DATOS"
FAMILIAS = ["xg", "bajas", "alineaciones", "entrenador"]


@pytest.fixture(scope="module")
def verificar():
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "datos"))
    import VERIFICAR_FEATURES_FUTURAS as vf

    return vf


def test_historico_y_fuentes_existen():
    assert DATOS_DIR.joinpath("historico_raw", "PRIMERA").is_dir()
    assert DATOS_DIR.joinpath("highlightly_dataset").is_dir()
    assert DATOS_DIR.joinpath("temporada_2026_27_estadisticas_base.json").is_file()


def test_ninguna_familia_tiene_cobertura_historica(verificar):
    report = verificar.run()
    for fam in FAMILIAS:
        verdict = report["veredicto_por_familia"][fam]
        assert verdict["cobertura_historica_consistente"] is False, fam
        assert verdict["columnas_historicas_encontradas"] == [], fam


def test_tiros_sot_disponibles_como_contraste(verificar):
    report = verificar.run()
    tiros = report["historico"]["columnas_tiros_disponibles_(contraste)"]
    assert {"HS", "AS", "HST", "AST"} <= set(tiros)


def test_veredicto_por_familia_cubre_las_cuatro(verificar):
    report = verificar.run()
    assert set(report["veredicto_por_familia"].keys()) == set(FAMILIAS)
