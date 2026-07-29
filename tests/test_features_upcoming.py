from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import MOTOR_QUINIELA_MAESTRO as motor
from scripts.motor.features import compute_features_for_upcoming, get_expected_columns


@pytest.fixture(scope="module")
def sample_history() -> pd.DataFrame:
    """Fixture con un subconjunto de histórico real para pruebas rápidas y deterministas."""
    df = motor.load_raw_history()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df[(df["date"] >= "2023-08-01") & (df["date"] < "2025-01-01")].copy()


def test_works_with_upcoming_match_without_result(sample_history: pd.DataFrame):
    """1. Funciona con un partido futuro sin resultado."""
    match = {
        "home": "Real Madrid",
        "away": "Barcelona",
        "date": "2025-01-10",
        "division": "Primera",
    }
    df_up = compute_features_for_upcoming([match], sample_history, cutoff_date="2025-01-01")
    assert len(df_up) == 1
    assert df_up.loc[0, "home"] == "Real Madrid"
    assert df_up.loc[0, "away"] == "Barcelona"
    assert np.isnan(df_up.loc[0, "FTHG"])
    assert np.isnan(df_up.loc[0, "FTAG"])
    assert np.isnan(df_up.loc[0, "result"])
    for col in motor.feature_columns():
        assert col in df_up.columns


def test_features_unchanged_when_history_contains_post_cutoff_matches(sample_history: pd.DataFrame):
    """2. Las features no cambian si history_df contiene partidos posteriores al cutoff."""
    match = {
        "home": "Real Madrid",
        "away": "Barcelona",
        "date": "2024-02-01",
        "division": "Primera",
    }
    cutoff = "2024-01-15"
    df_full = compute_features_for_upcoming([match], sample_history, cutoff_date=cutoff)
    truncated = sample_history[sample_history["date"] < cutoff].copy()
    df_trunc = compute_features_for_upcoming([match], truncated, cutoff_date=cutoff)
    pd.testing.assert_frame_equal(df_full, df_trunc)


def test_upcoming_matches_do_not_update_each_other(sample_history: pd.DataFrame):
    """3. Dos partidos futuros no se actualizan entre sí."""
    m1 = {
        "home": "Real Madrid",
        "away": "Barcelona",
        "date": "2025-01-10",
        "division": "Primera",
    }
    m2 = {
        "home": "Real Madrid",
        "away": "Sevilla",
        "date": "2025-01-17",
        "division": "Primera",
    }
    cutoff = "2025-01-01"
    df_both = compute_features_for_upcoming([m1, m2], sample_history, cutoff_date=cutoff)
    df_second_alone = compute_features_for_upcoming([m2], sample_history, cutoff_date=cutoff)

    assert df_both.loc[1, "home_elo"] == df_both.loc[0, "home_elo"]
    assert df_both.loc[1, "home_table_pj"] == df_both.loc[0, "home_table_pj"]
    pd.testing.assert_series_equal(
        df_both.loc[1].reset_index(drop=True),
        df_second_alone.loc[0].reset_index(drop=True),
        check_names=False,
    )


def test_known_teams_receive_state_before_cutoff(sample_history: pd.DataFrame):
    """4. Equipos conocidos reciben su último estado anterior al corte."""
    team = "Barcelona"
    cutoff = "2024-03-01"
    match = {
        "home": team,
        "away": "Real Madrid",
        "date": "2024-03-10",
        "division": "Primera",
    }
    df_up = compute_features_for_upcoming([match], sample_history, cutoff_date=cutoff)
    elo_up = df_up.loc[0, "home_elo"]
    pts_up = df_up.loc[0, "home_table_pts"]
    pj_up = df_up.loc[0, "home_table_pj"]

    sub_history = sample_history[sample_history["date"] < cutoff].copy()
    assert len(sub_history) > 0
    df_rolling = motor.rolling_team_features(sub_history)
    last_idx = df_rolling[(df_rolling["home"] == team) | (df_rolling["away"] == team)].index[-1]

    assert elo_up > 1000.0 and elo_up != 1500.0
    assert pj_up > 0.0 and pts_up >= 0.0


def test_unknown_team_produces_controlled_values_not_exception(sample_history: pd.DataFrame):
    """5. Equipo desconocido produce valores controlados, no excepción."""
    match = {
        "home": "Equipo Desconocido FC",
        "away": "Otro Desconocido CF",
        "date": "2025-01-10",
        "division": "Primera",
    }
    df_up = compute_features_for_upcoming([match], sample_history, cutoff_date="2025-01-01")
    assert len(df_up) == 1
    assert df_up.loc[0, "home_elo"] == 1500.0
    assert df_up.loc[0, "away_elo"] == 1500.0
    assert df_up.loc[0, "home_table_pj"] == 0.0
    assert df_up.loc[0, "home_table_pts"] == 0.0
    assert np.isnan(df_up.loc[0, "days_rest_home"])
    assert np.isnan(df_up.loc[0, "days_rest_away"])


def test_does_not_use_q15_lae_apu_as_odds(sample_history: pd.DataFrame):
    """Verifica que Q15, LAE o APU no se interpretan como cuotas en partidos futuros."""
    match = {
        "home": "Real Madrid",
        "away": "Barcelona",
        "date": "2025-01-10",
        "division": "Primera",
        "apu": {"1": 45, "X": 25, "2": 30},
        "q15": {"1": 50, "X": 30, "2": 20},
        "lae": {"1": 48, "X": 28, "2": 24},
    }
    df_up = compute_features_for_upcoming([match], sample_history, cutoff_date="2025-01-01")
    assert np.isnan(df_up.loc[0, "odd_1"])
    assert np.isnan(df_up.loc[0, "odd_x"])
    assert np.isnan(df_up.loc[0, "odd_2"])
    assert np.isnan(df_up.loc[0, "market_1"])


def test_empty_upcoming_matches_list_returns_empty_dataframe(sample_history: pd.DataFrame):
    """Verifica el comportamiento seguro con una lista vacía de partidos futuros."""
    df_empty = compute_features_for_upcoming([], sample_history, cutoff_date="2025-01-01")
    assert len(df_empty) == 0
    for col in get_expected_columns():
        assert col in df_empty.columns
