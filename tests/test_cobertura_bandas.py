from scripts.motor.cobertura_bandas import signo_doble_banda
from OPTIMIZADOR_COLUMNAS import build_double_development
import numpy as np


def test_visita_media_fuerza_1x():
    assert signo_doble_banda(2.1, 3.1) == "1X"


def test_local_moderado_fuerza_1x():
    assert signo_doble_banda(1.55, 6.0) == "1X"


def test_fuera_de_banda_no_fuerza():
    assert signo_doble_banda(2.2, 4.5) is None
    assert signo_doble_banda(1.2, 8.0) is None


def test_no_fuerza_visita_18_25():
    assert signo_doble_banda(2.4, 2.1) is None


def test_optimizador_aplica_solo_con_matches():
    p = np.array([0.40, 0.25, 0.35])  # top2 = 1 y 2 → 12
    # sin matches: no se fuerza
    sel = build_double_development([p], (0,))
    assert sel[0][0] == "12"
    # con cuota visita 3.0: 1X
    sel2 = build_double_development([p], (0,), matches=[{"odd_1": 2.2, "odd_2": 3.0}])
    assert sel2[0][0] == "1X"


def test_sigue_siendo_un_doble():
    p = np.array([0.50, 0.30, 0.20])
    sel = build_double_development([p], (0,), matches=[{"odd_1": 1.5, "odd_2": 6.0}])
    assert len(sel[0][1]) == 2
