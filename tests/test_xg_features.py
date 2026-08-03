"""Pruebas de las features de xG (Understat) point-in-time y su fusión."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.motor.features import (
    TeamStateTracker,
    compute_features_for_upcoming,
    get_expected_columns,
)
from scripts.motor.xg_understat import XG_OUTPUT_COLUMNS, merge_xg

XG_COLS = [
    "home_xg_5",
    "away_xg_5",
    "home_xg_against_5",
    "away_xg_against_5",
    "xg_for_diff",
    "xg_against_diff",
]


def _base_history(with_xg: bool = True) -> pd.DataFrame:
    rows = []
    # equipos A y B, 3 partidos seguidos cada uno; xG fijo por partido.
    for i in range(1, 4):
        rows.append({
            "date": pd.Timestamp(f"2020-0{i}-05"),
            "home": "AA",
            "away": "BB",
            "FTHG": 2,
            "FTAG": 1,
            "result": "1",
            "odd_1": 2.0, "odd_x": 3.0, "odd_2": 4.0,
            "open_odd_1": 2.0, "open_odd_x": 3.0, "open_odd_2": 4.0,
            "division": "Primera", "division_code": 0,
            "season": "2019-2020", "source_file": "x",
            "home_xg": 1.5, "away_xg": 0.8,
        })
        # partido de vuelta (BB local) algunos días después
        rows.append({
            "date": pd.Timestamp(f"2020-0{i}-20"),
            "home": "BB",
            "away": "AA",
            "FTHG": 0,
            "FTAG": 1,
            "result": "2",
            "odd_1": 3.0, "odd_x": 3.0, "odd_2": 2.0,
            "open_odd_1": 3.0, "open_odd_x": 3.0, "open_odd_2": 2.0,
            "division": "Primera", "division_code": 0,
            "season": "2019-2020", "source_file": "x",
            "home_xg": 0.8, "away_xg": 1.5,
        })
    df = pd.DataFrame(rows)
    if not with_xg:
        df = df.drop(columns=["home_xg", "away_xg"])
    return df


def test_expected_columns_include_xg_features():
    for col in XG_COLS:
        assert col in get_expected_columns()


def test_rolling_xg_point_in_time_no_leak():
    tracker = TeamStateTracker(config={})
    df = _base_history(with_xg=True)
    feats = []
    for _, row in df.iterrows():
        f = tracker.extract_match_features(row)
        feats.append(f)
        tracker.update_match(row)

    # 1er partido: sin historial previo -> xG_5 NaN
    assert np.isnan(feats[0]["home_xg_5"])
    # 2º partido (BB local): BB tuvo 1 partido previo como visitante (xG=0.8)
    assert feats[1]["home_xg_5"] == 0.8
    # 5º partido: AA como local ya acumula 2 partidos de xG (1.5 cada uno) -> media 1.5
    assert abs(feats[4]["home_xg_5"] - 1.5) < 1e-9
    # 5º partido: away BB -> away_xg_5 media de los 2 partidos de BB (xg=0.8)
    assert abs(feats[4]["away_xg_5"] - 0.8) < 1e-9


def test_rolling_xg_without_source_returns_nan_not_error():
    tracker = TeamStateTracker(config={})
    df = _base_history(with_xg=False)
    feats = []
    for _, row in df.iterrows():
        f = tracker.extract_match_features(row)
        feats.append(f)
        tracker.update_match(row)
    # Sin columna de xG, las features deben ser NaN y no reventar.
    assert all(np.isnan(feats[i]["home_xg_5"]) for i in range(len(feats)))


def test_merge_xg_adds_columns_and_keeps_unmatched_nan():
    frame = pd.DataFrame({
        "date": [pd.Timestamp("2020-01-05"), pd.Timestamp("2000-01-01")],
        "home": ["AA", "ZZ"],
        "away": ["BB", "YY"],
        "FTHG": [2, 1],
        "FTAG": [1, 1],
        "result": ["1", "X"],
    })
    # Sin fichero xG disponible -> columnas NaN sin romper.
    out = merge_xg(frame)
    for col in XG_OUTPUT_COLUMNS:
        assert col in out.columns
    assert out[XG_OUTPUT_COLUMNS].isna().all().all()


def test_upcoming_features_have_xg_columns():
    history = _base_history(with_xg=True)
    match = {"home": "AA", "away": "BB", "date": "2020-05-01",
             "division": "Primera"}
    out = compute_features_for_upcoming([match], history, cutoff_date="2020-05-01")
    for col in XG_COLS:
        assert col in out.columns
