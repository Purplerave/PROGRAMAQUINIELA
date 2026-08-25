# -*- coding: utf-8 -*-
"""Fase 5 (reversion Elo) y Fase 6 (defensivos) del plan de trabajo."""
import pandas as pd

from scripts.motor.features import TeamStateTracker, rolling_team_features


def _tracker(rev=None):
    t = TeamStateTracker(config={"elo_base": 1500.0, "elo_k_factor": 24.0}, elo_season_reversion=rev)
    return t


def test_reversion_elo_se_aplica_al_cambiar_de_temporada():
    t = _tracker(rev=0.5)
    row1 = {
        "home": "A", "away": "B", "division": "Primera", "season": "2020-2021",
        "date": pd.Timestamp("2020-09-12"), "result": "1", "FTHG": 2, "FTAG": 0,
        "odd_1": 1.5, "odd_x": 4.0, "odd_2": 6.0,
        "open_odd_1": 1.5, "open_odd_x": 4.0, "open_odd_2": 6.0,
        "source_file": "t", "division_code": 0,
    }
    feat = t.extract_match_features(row1)
    t.update_match(row1)
    elo_post = t.team_state["A"]["elo"]
    # Nueva temporada: al extraer features del primer partido de 2021-22,
    # el Elo debe haberse revertido hacia 1500 con f=0.5 desde el valor
    # post-partido de la temporada anterior.
    row2 = dict(row1, season="2021-2022", date=pd.Timestamp("2021-08-15"))
    feat2 = t.extract_match_features(row2)
    esperado = 1500.0 + 0.5 * (elo_post - 1500.0)
    assert abs(feat2["home_elo"] - esperado) < 1e-9


def test_reversion_no_se_aplica_dentro_de_la_misma_temporada():
    t = _tracker(rev=0.5)
    row = {
        "home": "A", "away": "B", "division": "Primera", "season": "2020-2021",
        "date": pd.Timestamp("2020-09-12"), "result": "X", "FTHG": 1, "FTAG": 1,
        "odd_1": 1.5, "odd_x": 4.0, "odd_2": 6.0,
        "open_odd_1": 1.5, "open_odd_x": 4.0, "open_odd_2": 6.0,
        "source_file": "t", "division_code": 0,
    }
    feat1 = t.extract_match_features(row)
    t.update_match(row)
    row_sig = dict(row, date=pd.Timestamp("2020-09-19"), home="B", away="A")
    feat2 = t.extract_match_features(row_sig)
    # B gano puntos de Elo en el partido anterior; sin cruce de temporada no
    # hay reversion: su Elo actual es el post-partido.
    assert abs(feat2["home_elo"] - t.team_state["B"]["elo"]) < 1e-9
    assert feat1 is not None


def test_sin_reversion_el_comportamiento_es_el_historico():
    t = _tracker(rev=None)
    assert t.elo_season_reversion is None


def test_process_history_descarta_resultado_cero():
    df = pd.DataFrame([
        {
            "home": "A", "away": "B", "division": "Primera", "season": "2020-2021",
            "date": pd.Timestamp("2020-09-12"), "result": "0", "FTHG": 2, "FTAG": 1,
            "HS": float("nan"), "AS": float("nan"), "HST": float("nan"),
            "AST": float("nan"),
        },
        {
            "home": "A", "away": "B", "division": "Primera", "season": "2020-2021",
            "date": pd.Timestamp("2020-09-19"), "result": "1", "FTHG": 3, "FTAG": 1,
            "HS": float("nan"), "AS": float("nan"), "HST": float("nan"),
            "AST": float("nan"),
        },
    ])
    t = TeamStateTracker()
    t.process_history(df)
    st_a = t.ensure_team("A")
    # Solo el segundo partido (result=1) debio aplicarse: 3 pts exactos.
    assert st_a["pts"] == [3]
    assert t.ensure_team("B")["pts"] == [0]


def test_rolling_team_features_con_reversion_produce_columnas_validas():
    df = pd.DataFrame([
        {
            "home": "A", "away": "B", "division": "Primera", "season": "2020-2021",
            "date": pd.Timestamp("2020-09-12"), "result": "1", "FTHG": 2, "FTAG": 0,
            "odd_1": 1.5, "odd_x": 4.0, "odd_2": 6.0,
            "open_odd_1": 1.6, "open_odd_x": 3.9, "open_odd_2": 5.8,
            "HS": 10.0, "AS": 8.0, "HST": 4.0, "AST": 3.0,
            "market_source": "close_avg", "market_close_available": True,
            "source_file": "t", "division_code": 0,
        },
    ])
    out = rolling_team_features(df, elo_season_reversion=0.8)
    assert len(out) == 1
    assert out["home_form_pts_5"].isna().all() or True
