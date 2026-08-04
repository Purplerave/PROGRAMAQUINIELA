"""Tests de la corrección P0: sin fuga temporal entre partidos de la misma fecha.

La corrección (scripts/motor/features.py) procesa el histórico por lotes de
fecha: primero extrae las features de TODOS los partidos de una fecha con el
estado anterior a esa fecha y solo después aplica los resultados de la fecha.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import MOTOR_QUINIELA_MAESTRO as motor
from scripts.motor.features import get_expected_columns, rolling_team_features


def _history_frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


def test_mismo_dia_no_ve_resultado_previo_del_mismo_dia():
    """Dos partidos del mismo equipo el mismo día: el 2º no puede ver el 1º."""
    rows = [
        {
            "date": "2024-01-01", "home": "A", "away": "B",
            "division": "Primera", "division_code": 0, "season": "2023-2024",
            "source_file": "t.csv", "FTHG": 3, "FTAG": 0, "result": "1",
            "odd_1": 1.5, "odd_x": 4.0, "odd_2": 6.0,
            "open_odd_1": 1.6, "open_odd_x": 3.8, "open_odd_2": 5.5,
            "HS": 12, "AS": 3, "HST": 6, "AST": 1,
        },
        {
            "date": "2024-01-01", "home": "A", "away": "C",
            "division": "Primera", "division_code": 0, "season": "2023-2024",
            "source_file": "t.csv", "FTHG": 0, "FTAG": 1, "result": "2",
            "odd_1": 2.0, "odd_x": 3.2, "odd_2": 3.8,
            "open_odd_1": 2.1, "open_odd_x": 3.1, "open_odd_2": 3.6,
            "HS": 5, "AS": 9, "HST": 2, "AST": 5,
        },
    ]
    feat = rolling_team_features(_history_frame(rows))
    assert len(feat) == 2
    # Ambos partidos parten del estado inicial (previo a la fecha): mismo Elo,
    # misma forma y misma tabla. El 2º no incorpora el 3-0 del 1º.
    assert feat.loc[0, "home_elo"] == feat.loc[1, "home_elo"] == 1500.0
    assert feat.loc[0, "home_table_pj"] == feat.loc[1, "home_table_pj"] == 0.0
    assert feat.loc[0, "home_table_pts"] == feat.loc[1, "home_table_pts"] == 0.0
    assert np.isnan(feat.loc[0, "home_form_pts_5"])
    assert np.isnan(feat.loc[1, "home_form_pts_5"])
    assert np.isnan(feat.loc[0, "days_rest_home"])
    assert np.isnan(feat.loc[1, "days_rest_home"])


def test_tabla_clasificacion_sin_fuga_intra_fecha():
    """La victoria de D el día 1 no puede alterar la tabla que ve E ese mismo día."""
    rows = [
        {
            "date": "2024-01-01", "home": "D", "away": "F",
            "division": "Primera", "division_code": 0, "season": "2023-2024",
            "source_file": "t.csv", "FTHG": 2, "FTAG": 0, "result": "1",
            "odd_1": 1.3, "odd_x": 5.0, "odd_2": 8.0,
            "open_odd_1": 1.3, "open_odd_x": 5.0, "open_odd_2": 8.0,
            "HS": 10, "AS": 2, "HST": 5, "AST": 0,
        },
        {
            "date": "2024-01-01", "home": "E", "away": "G",
            "division": "Primera", "division_code": 0, "season": "2023-2024",
            "source_file": "t.csv", "FTHG": 1, "FTAG": 1, "result": "X",
            "odd_1": 2.4, "odd_x": 3.1, "odd_2": 3.0,
            "open_odd_1": 2.4, "open_odd_x": 3.1, "open_odd_2": 3.0,
            "HS": 6, "AS": 6, "HST": 3, "AST": 3,
        },
    ]
    feat = rolling_team_features(_history_frame(rows))
    assert feat.loc[1, "home_table_pj"] == 0.0
    assert feat.loc[1, "home_table_pts"] == 0.0
    # Y el propio D tampoco ve su victoria del mismo día.
    assert feat.loc[0, "home_table_pj"] == 0.0


def test_dia_siguiente_si_ve_resultados_del_dia_anterior():
    """El día 2 sí debe incorporar los resultados del día 1 (orden correcto)."""
    rows = [
        {
            "date": "2024-01-01", "home": "A", "away": "B",
            "division": "Primera", "division_code": 0, "season": "2023-2024",
            "source_file": "t.csv", "FTHG": 3, "FTAG": 0, "result": "1",
            "odd_1": 1.5, "odd_x": 4.0, "odd_2": 6.0,
            "open_odd_1": 1.6, "open_odd_x": 3.8, "open_odd_2": 5.5,
            "HS": 12, "AS": 3, "HST": 6, "AST": 1,
        },
        {
            "date": "2024-01-02", "home": "A", "away": "C",
            "division": "Primera", "division_code": 0, "season": "2023-2024",
            "source_file": "t.csv", "FTHG": 1, "FTAG": 1, "result": "X",
            "odd_1": 2.0, "odd_x": 3.2, "odd_2": 3.8,
            "open_odd_1": 2.1, "open_odd_x": 3.1, "open_odd_2": 3.6,
            "HS": 6, "AS": 6, "HST": 3, "AST": 3,
        },
    ]
    feat = rolling_team_features(_history_frame(rows))
    # El día 2, A tiene 1 partido jugado, 3 puntos, forma 3 y Elo actualizado.
    assert feat.loc[1, "home_table_pj"] == 1.0
    assert feat.loc[1, "home_table_pts"] == 3.0
    assert feat.loc[1, "home_form_pts_5"] == 3.0
    assert feat.loc[1, "home_elo"] != 1500.0
    assert feat.loc[1, "days_rest_home"] == 1.0


def test_historico_real_consistente_y_sin_regresiones():
    """El batching por fecha no rompe el cálculo sobre histórico real."""
    raw = motor.load_raw_history()
    sub = raw[(raw["date"] >= "2023-08-01") & (raw["date"] < "2024-01-01")].copy()
    feat = rolling_team_features(sub)
    assert len(feat) == len(sub)
    assert feat.shape[1] == len(get_expected_columns())
    assert feat["result"].notna().all()
