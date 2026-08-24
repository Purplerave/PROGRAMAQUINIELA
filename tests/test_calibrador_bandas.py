"""Tests del calibrador de bandas (REVISION_15/16)."""

from datetime import date

import pandas as pd

from scripts.motor.calibrador_bandas import (
    calibrar_probabilidades,
    estimar_factores,
    season_code,
    aplicar_calibracion_bandas,
)


def test_season_code():
    assert season_code("2019-2020") == "1920"
    assert season_code("1920") == "1920"


def test_calibrar_no_cambia_fuera_de_banda():
    fac = {"visita_2.5_4.0": 0.9, "local_1.4_1.8": 1.07, "entre_semana_favorito_boost": 0.02}
    probs = [0.5, 0.3, 0.2]
    out = calibrar_probabilidades(probs, (2.2, 3.4, 4.5), fac, entre_semana=False)
    assert abs(sum(out) - 1) < 1e-9
    assert out == [x / sum(probs) for x in probs]


def test_calibrar_baja_visita_banda():
    fac = {"visita_2.5_4.0": 0.9, "local_1.4_1.8": 1.0, "entre_semana_favorito_boost": 0.02}
    out = calibrar_probabilidades([0.4, 0.3, 0.3], (2.2, 3.4, 3.0), fac)
    assert out[2] < 0.3


def test_estimar_factores_cap_y_ventana():
    partidos = []
    for i in range(250):
        partidos.append({"season": "1819", "res": "H", "odds": (1.5, 4.0, 6.0)})
    for i in range(250):
        partidos.append({"season": "1920", "res": "A", "odds": (2.8, 3.3, 2.7)})
    f = estimar_factores(partidos, hasta_temporada="2021", ventana=6, cap=0.10)
    assert 0.9 <= f["visita_2.5_4.0"] <= 1.1
    assert 0.9 <= f["local_1.4_1.8"] <= 1.1


def test_aplicar_en_frame():
    frame = pd.DataFrame(
        {
            "date": [pd.Timestamp("2024-08-20")],
            "season": ["2024-2025"],
            "odd_1": [1.5],
            "odd_x": [4.0],
            "odd_2": [7.0],
            "hy_prob_1": [0.60],
            "hy_prob_x": [0.25],
            "hy_prob_2": [0.15],
            "result": ["1"],
        }
    )
    fac = {"visita_2.5_4.0": 1.0, "local_1.4_1.8": 1.08, "entre_semana_favorito_boost": 0.02}
    out = aplicar_calibracion_bandas(frame, "hy", factores=fac, enabled=True)
    assert out["hy_prob_1"].iloc[0] > 0.60
    assert abs(out["hy_prob_1"].iloc[0] + out["hy_prob_x"].iloc[0] + out["hy_prob_2"].iloc[0] - 1) < 1e-9


def test_config_tiene_bloque():
    import settings

    cfg = settings.CONFIG["calibracion_bandas"]
    assert cfg["enabled"] is True
    assert cfg["ventana_temporadas"] == 6
    assert cfg["cap_multiplicativo"] == 0.10
