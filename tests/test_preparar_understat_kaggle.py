"""Tests del conversor del dataset Understat (Kaggle) a CSV de xG.

Se usa un CSV sintético que imita el esquema real de los datos de partidos de
Understat (extraídos con understatapi): columnas home_team/away_team, xG por
equipo, datetime y season, más una columna league para filtrar La Liga.
"""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "datos"))
import PREPARAR_XG_UNDERSTAT_KAGGLE as prep  # noqa: E402

# Imita el esquema de matches de Understat (una fila por partido).
_FILAS = [
    ["match_id", "season", "datetime", "league", "home_team", "away_team", "h_goals", "a_goals", "xG_h", "xG_a"],
    [1001, "2014", "2014-08-25", "laliga", "Real Madrid", "Getafe", 7, 3, 3.13, 0.98],
    [1002, "2014", "2014-08-25", "laliga", "Barcelona", "Elche", 3, 0, 2.44, 0.30],
    [1003, "2014", "2014-08-25", "premier", "Arsenal", "Chelsea", 2, 1, 1.9, 1.4],  # otra liga
]


def _csv_filas(filas) -> io.StringIO:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerows(filas)
    buf.seek(0)
    return buf


def test_convierte_partidos_de_la_liga_con_xg(tmp_path):
    archivo = tmp_path / "matches.csv"
    archivo.write_text(_csv_filas(_FILAS).getvalue(), encoding="utf-8")
    df = pd.read_csv(archivo)

    partidos = prep.localizar_partidos_la_liga(tmp_path)
    assert partidos is not None

    filas = prep.convertir(partidos)
    # Solo los partidos de La Liga (2), no el de Premier.
    assert len(filas) == 2
    real = filas[0]
    assert real["home"] == "Real Madrid"
    assert real["away"] == "Getafe"
    assert real["home_xg"] == 3.13
    assert real["away_xg"] == 0.98
    assert str(real["season"]) == "2014"


def test_escribe_csv_en_esquema_estandar(tmp_path):
    archivo = tmp_path / "matches.csv"
    archivo.write_text(_csv_filas(_FILAS).getvalue(), encoding="utf-8")
    partidos = prep.localizar_partidos_la_liga(tmp_path)
    filas = prep.convertir(partidos)
    assert set(filas[0].keys()) == set(prep.TEMP_HDR)


def test_normaliza_nombres_de_columna():
    assert prep._norm("xG_h") == "xgh"
    assert prep._norm("Home_Team") == "hometeam"
    assert prep._encontrar_col(pd.DataFrame({"xG_h": [1]}), prep._NOMBRES_XG_LOCAL) == "xG_h"


def test_sin_tabla_de_la_liga_lanza_error(tmp_path):
    # Solo columnas sin xG ni equipos -> debe fallar.
    (tmp_path / "otro.csv").write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    with pytest.raises(Exception):
        prep.localizar_partidos_la_liga(tmp_path)
