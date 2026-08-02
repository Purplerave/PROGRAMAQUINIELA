"""Pruebas de scripts/motor/team_names.py y de su conexión con features/priors.

Garantiza que los nombres comunes de las jornadas se traducen a
los nombres del histórico y a los nombres canónicos de los priors 2026/27,
de forma explícita y sin fundir filiales ni inventar equipos.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

import settings
from scripts.motor.features import compute_features_for_upcoming
from scripts.motor.team_names import (
    history_alias_index,
    normalize_team_name,
    prior_alias_index,
    resolve_history_name,
    resolve_prior_name,
)


class TestNormalizeTeamName:
    def test_accents_dots_case(self):
        assert normalize_team_name("Málaga C.F.") == "malaga cf"

    def test_non_string(self):
        assert normalize_team_name(None) == ""


class TestHistoryAliasIndex:
    def test_builds_without_collisions(self):
        index = history_alias_index()
        assert len(index) > 0

    def test_all_history_names_resolve_to_themselves(self):
        """Los nombres exactos del histórico se resuelven a sí mismos, salvo el
        alias controlado del repo (sanitization/constants.ALIAS_MAP):
        Leonesa -> Cultural Leonesa (mismo club, nombre histórico distinto)."""
        from MOTOR_QUINIELA_MAESTRO import load_raw_history

        controlled_exceptions = {"Leonesa": "Cultural Leonesa"}

        history = load_raw_history()
        names = set(history["home"].unique()) | set(history["away"].unique())
        for name in names:
            expected = controlled_exceptions.get(name, name)
            assert resolve_history_name(name) == expected, (
                f"No resuelve: {name} -> {resolve_history_name(name)}"
            )

    def test_leonesa_alias_controlado(self):
        """Alineado con sanitization/constants.ALIAS_MAP."""
        assert resolve_history_name("Leonesa") == "Cultural Leonesa"
        assert resolve_history_name("Cultural Leonesa") == "Cultural Leonesa"

    @pytest.mark.parametrize(
        "jornada_name,expected",
        [
            ("Athletic Club", "Ath Bilbao"),
            ("Atlético de Madrid", "Ath Madrid"),
            ("Real Sociedad", "Sociedad"),
            ("Rayo Vallecano", "Vallecano"),
            ("Málaga CF", "Malaga"),
            ("RC Deportivo", "La Coruna"),
            ("R. Racing Club", "Santander"),
            ("Castellón", "Castellon"),
            ("UD Las Palmas", "Las Palmas"),
            ("CD Castellón", "Castellon"),
            ("FC Barcelona", "Barcelona"),
            ("Sevilla FC", "Sevilla"),
            ("Real Sporting", "Sp Gijon"),
            ("RCD Espanyol de Barcelona", "Espanol"),
            ("RC Celta", "Celta"),
            ("Deportivo Alavés", "Alaves"),
            ("CA Osasuna", "Osasuna"),
            ("Real Betis", "Betis"),
        ],
    )
    def test_common_names_map_to_history(self, jornada_name, expected):
        assert resolve_history_name(jornada_name) == expected

    def test_filiales_no_se_funden_con_primer_equipo(self):
        assert resolve_history_name("Real Sociedad B") == "Sociedad B"
        assert resolve_history_name("Real Sociedad") == "Sociedad"
        assert resolve_history_name("Villarreal B") == "Villarreal B"
        assert resolve_history_name("Villarreal") == "Villarreal"
        assert resolve_history_name("Real Madrid Castilla") == "Real Madrid B"
        assert resolve_history_name("Real Madrid") == "Real Madrid"

    def test_unknown_passes_through(self):
        assert resolve_history_name("Kristiansund") == "Kristiansund"
        assert resolve_history_name("Ganador Semifinal 1") == "Ganador Semifinal 1"


class TestPriorAliasIndex:
    def test_builds_and_maps_jornada_names(self):
        index = prior_alias_index()
        assert len(index) > 0
        assert resolve_prior_name("Castellón") == "CD Castellon"
        assert resolve_prior_name("Malaga CF") == "Malaga CF"
        assert resolve_prior_name("Málaga") == "Malaga CF"
        assert resolve_prior_name("Racing Santander") == "R. Racing Club"
        assert resolve_prior_name("Deportivo La Coruña") == "RC Deportivo"

    def test_unknown_prior_returns_none(self):
        assert resolve_prior_name("Kristiansund") is None


class TestFeaturesConAlias:
    """El equipo con nombre común produce EXACTAMENTE las mismas features
    que con su nombre histórico."""

    @pytest.fixture(scope="class")
    def history_subset(self):
        from MOTOR_QUINIELA_MAESTRO import load_raw_history

        df = load_raw_history()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df[(df["date"] >= "2023-08-01") & (df["date"] < "2025-07-01")].copy()

    @pytest.mark.parametrize(
        "jornada_name,history_name",
        [
            ("Athletic Club", "Ath Bilbao"),
            ("Real Sociedad", "Sociedad"),
            ("Rayo Vallecano", "Vallecano"),
        ],
    )
    def test_alias_features_identical(self, history_subset, jornada_name, history_name):
        cols = [
            "home_elo", "home_table_pj", "home_table_pts", "home_form_pts_5",
            "home_gf_5", "home_ga_5", "lambda_home", "poisson_1",
        ]
        base = {"away": "Barcelona", "date": "2025-01-10", "division": "Primera"}
        df_alias = compute_features_for_upcoming(
            [{**base, "home": jornada_name}], history_subset, cutoff_date="2025-01-01"
        )
        df_hist = compute_features_for_upcoming(
            [{**base, "home": history_name}], history_subset, cutoff_date="2025-01-01"
        )
        for col in cols:
            val_a, val_h = df_alias.loc[0, col], df_hist.loc[0, col]
            assert (pd.isna(val_a) and pd.isna(val_h)) or val_a == val_h, (
                f"{col}: alias {val_a} != histórico {val_h}"
            )

    def test_alias_division_inference(self, history_subset):
        """Sin división explícita, el alias permite inferirla del histórico."""
        df = compute_features_for_upcoming(
            [{"home": "Real Sociedad", "away": "Real Madrid", "date": "2025-01-10"}],
            history_subset,
            cutoff_date="2025-01-01",
        )
        assert df.loc[0, "division"] == "Primera"

    def test_mixed_alias_and_history_names(self, history_subset):
        df = compute_features_for_upcoming(
            [{"home": "Málaga CF", "away": "Malaga", "date": "2025-01-10", "division": "Segunda"}],
            history_subset,
            cutoff_date="2025-01-01",
        )
        # Ambos lados son el mismo equipo tras resolver alias
        assert df.loc[0, "home"] == "Malaga"
        assert df.loc[0, "away"] == "Malaga"
        assert df.loc[0, "home_elo"] == df.loc[0, "away_elo"]


class TestPriorsConAlias:
    def test_transition_prior_via_jornada_name(self):
        """_apply_transition_priors encuentra priors con nombres de jornada."""
        from MOTOR_PREDICCION_JORNADA import _apply_transition_priors

        priors = json.loads(
            (settings.DATOS_DIR / "temporada_2026_27_estadisticas_base.json")
            .read_text(encoding="utf-8")
        )["teams"]
        adj_castellon = priors["CD Castellon"]["context"]["adjusted_ppg"]

        df = pd.DataFrame([
            {"home": "Castellón", "away": "Las Palmas",
             "home_table_pj": 0.0, "home_table_ppg": np.nan,
             "away_table_pj": 1.0, "away_table_ppg": 1.0},
        ])
        out = _apply_transition_priors(df)
        assert out.loc[0, "home_table_ppg"] == pytest.approx(adj_castellon, abs=1e-9)

    def test_enrich_with_priors_via_jornada_name(self):
        from PREDECIR_JORNADA import enrich_with_priors, load_priors

        priors, _ = load_priors()
        partidos = [{"num": 1, "local": "Castellón", "visitante": "Malaga CF"}]
        out = enrich_with_priors(partidos, priors)
        assert "prior_local" in out[0]
        assert "prior_visitante" in out[0]
        assert out[0]["prior_visitante"]["transition"] == "segunda_a_primera"
