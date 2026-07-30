"""Pruebas de integración para MOTOR_PREDICCION_JORNADA.

这些测试验证:
1. La conexión con MOTOR_QUINIELA_MAESTRO funciona
2. Las predicciones se generan sin fuga temporal
3. El contrato JSON es estable
4. No se usan APU/LAE/Q15 como fuente principal
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import settings
from MOTOR_PREDICCION_JORNADA import (
    _calculate_confidence,
    _check_data_quality,
    generate_jornada_prediction,
    get_cutoff_date,
    load_jornada_json,
    normalize_name,
    predict_jornada_from_model,
    save_predictions,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="module")
def small_history():
    """Histórico pequeño para pruebas rápidas (solo 2 temporadas)."""
    from scripts.motor.features import rolling_team_features
    from MOTOR_QUINIELA_MAESTRO import load_raw_history

    print("Loading full history...")
    full_df = load_raw_history()
    full_df["date"] = pd.to_datetime(full_df["date"])

    # Filtrar solo las últimas temporadas disponibles
    seasons = sorted(full_df["season"].unique())
    if len(seasons) >= 2:
        recent_seasons = seasons[-2:]
    else:
        recent_seasons = seasons

    print(f"Seasons: {recent_seasons}")
    df = full_df[full_df["season"].isin(recent_seasons)].copy()
    print(f"Rows after filter: {len(df)}")

    print("Computing features...")
    features = rolling_team_features(df)
    print(f"Features computed: {len(features)}")
    return features


@pytest.fixture(scope="module")
def sample_jornada_data():
    """Datos de jornada de muestra."""
    return {
        "jornada": 99,
        "partidos": [
            {
                "num": 1,
                "local": "Real Madrid",
                "visitante": "Barcelona",
                "fecha": "2025-01-15",
                "division": "Primera",
            },
            {
                "num": 2,
                "local": "Sevilla",
                "visitante": "Atletico Madrid",
                "fecha": "2025-01-15",
                "division": "Primera",
            },
        ],
    }


# ============================================================================
# TESTS: Funciones auxiliares
# ============================================================================

class TestNormalizeName:
    def test_lowercase(self):
        assert normalize_name("REAL MADRID") == "real madrid"

    def test_accents(self):
        assert normalize_name("Atlético") == "atletico"

    def test_dots(self):
        assert normalize_name("R.C.D.") == "rcd"

    def test_non_string(self):
        assert normalize_name(None) == ""
        assert normalize_name(123) == ""


class TestCalculateConfidence:
    def test_high_confidence(self):
        probs = {"1": 0.90, "X": 0.05, "2": 0.05}
        conf = _calculate_confidence(probs)
        # 0.90/0.05/0.05 tiene confianza ~0.64 (alta pero no extrema)
        assert conf > 0.5
        assert conf < 0.8

    def test_low_confidence(self):
        probs = {"1": 0.34, "X": 0.33, "2": 0.33}
        conf = _calculate_confidence(probs)
        assert conf < 0.1


class TestCheckDataQuality:
    def test_unknown_team(self):
        """Equipo desconocido genera avisos."""
        feat_row = pd.Series({
            "home_elo": 1500.0,
            "away_elo": 1500.0,
            "home_table_pj": 0.0,
            "away_table_pj": 0.0,
            "odd_1": np.nan,
            "home_form_pts_5": np.nan,
        })
        quality = _check_data_quality(feat_row)
        assert len(quality["warnings"]) > 0
        assert "sin_partidos_local" in quality["warnings"]
        assert "sin_partidos_visitante" in quality["warnings"]

    def test_complete_team_has_no_critical_warnings(self):
        """Equipo con historial no tiene avisos críticos."""
        feat_row = pd.Series({
            "home_elo": 1600.0,
            "away_elo": 1550.0,
            "home_table_pj": 10.0,
            "away_table_pj": 10.0,
            "odd_1": 2.0,
            "home_form_pts_5": 1.5,
        })
        quality = _check_data_quality(feat_row)
        # No debe tener avisos de partidos o Elo
        critical = [w for w in quality["warnings"] if "sin_partidos" in w or "equipos_sin_elo" in w]
        assert len(critical) == 0


# ============================================================================
# TESTS: Carga de datos de jornada
# ============================================================================

class TestLoadJornadaJson:
    def test_loads_existing_jornada(self):
        data = load_jornada_json(74)
        assert data["jornada"] == 74
        assert len(data["partidos"]) == 15

    def test_raises_on_missing_jornada(self):
        with pytest.raises(FileNotFoundError):
            load_jornada_json(9999)


class TestGetCutoffDate:
    def test_uses_first_match_date(self):
        jornada = {
            "partidos": [
                {"fecha": "2025-01-15"},
                {"fecha": "2025-01-16"},
                {"fecha": None},
            ]
        }
        cutoff = get_cutoff_date(jornada)
        expected = pd.Timestamp("2025-01-14")
        assert cutoff == expected

    def test_fallback_to_yesterday(self):
        cutoff = get_cutoff_date({"partidos": []})
        expected = pd.Timestamp.now() - pd.Timedelta(days=1)
        assert cutoff.date() == expected.date()


# ============================================================================
# TESTS: Predicciones del modelo (con subset de datos)
# ============================================================================

class TestPredictJornadaFromModel:
    @pytest.mark.slow
    def test_generates_predictions(self, small_history, sample_jornada_data):
        predictions = predict_jornada_from_model(
            partidos=sample_jornada_data["partidos"],
            history_df=small_history,
            jornada=99,
            cutoff_date="2025-01-01",
        )
        assert predictions["jornada"] == 99
        assert predictions["estado"] in ("completado", "sin_datos")
        assert "predicciones" in predictions

    @pytest.mark.slow
    def test_prediction_structure(self, small_history, sample_jornada_data):
        predictions = predict_jornada_from_model(
            partidos=sample_jornada_data["partidos"],
            history_df=small_history,
            jornada=99,
            cutoff_date="2025-01-01",
        )

        for pred in predictions.get("predicciones", []):
            required = ["jornada", "numero", "local", "visitante",
                       "prob_1", "prob_x", "prob_2", "signo_modelo",
                       "confianza", "fuente_probabilidades", "avisos"]
            for field in required:
                assert field in pred, f"Falta campo: {field}"

            assert 0 <= pred["prob_1"] <= 1
            assert 0 <= pred["prob_x"] <= 1
            assert 0 <= pred["prob_2"] <= 1

    @pytest.mark.slow
    def test_signo_is_valid(self, small_history, sample_jornada_data):
        predictions = predict_jornada_from_model(
            partidos=sample_jornada_data["partidos"],
            history_df=small_history,
            jornada=99,
            cutoff_date="2025-01-01",
        )

        for pred in predictions.get("predicciones", []):
            assert pred["signo_modelo"] in {"1", "X", "2"}

    @pytest.mark.slow
    def test_confianza_range(self, small_history, sample_jornada_data):
        predictions = predict_jornada_from_model(
            partidos=sample_jornada_data["partidos"],
            history_df=small_history,
            jornada=99,
            cutoff_date="2025-01-01",
        )

        for pred in predictions.get("predicciones", []):
            assert 0 <= pred["confianza"] <= 1


# ============================================================================
# TESTS: Sin fuga temporal
# ============================================================================

class TestNoTemporalLeakage:
    @pytest.mark.slow
    def test_upcoming_match_without_result(self, small_history):
        from scripts.motor.features import compute_features_for_upcoming

        match = {
            "home": "Real Madrid",
            "away": "Barcelona",
            "date": "2025-01-10",
            "division": "Primera",
        }
        features = compute_features_for_upcoming(
            [match],
            small_history,
            cutoff_date="2025-01-01",
        )
        if not features.empty:
            assert np.isnan(features.iloc[0]["FTHG"])
            assert np.isnan(features.iloc[0]["result"])

    @pytest.mark.slow
    def test_apu_lae_q15_not_used_as_odds(self, small_history):
        from scripts.motor.features import compute_features_for_upcoming

        match = {
            "home": "Real Madrid",
            "away": "Barcelona",
            "date": "2025-01-10",
            "division": "Primera",
            "apu": {"1": 45, "X": 25, "2": 30},
            "q15": {"1": 50, "X": 30, "2": 20},
        }
        features = compute_features_for_upcoming(
            [match],
            small_history,
            cutoff_date="2025-01-01",
        )
        if not features.empty:
            assert np.isnan(features.iloc[0]["odd_1"])


# ============================================================================
# TESTS: Integración con PREDECIR_JORNADA
# ============================================================================

class TestIntegration:
    @pytest.mark.slow
    def test_generate_jornada_prediction(self):
        """Test básico de generate_jornada_prediction.

        Este test entrena modelos y puede tardar.
        """
        predictions = generate_jornada_prediction(74)
        assert "jornada" in predictions
        # Verificar estructura básica aunque haya error
        assert "estado" in predictions or "error" in predictions

    def test_save_predictions(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "SALIDAS_DIR", tmp_path)

        predictions = {"jornada": 74, "predicciones": [], "estado": "test"}
        path = save_predictions(predictions, 74)

        assert path.exists()
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["jornada"] == 74


# ============================================================================
# TESTS: Contrato JSON estable
# ============================================================================

class TestJsonContract:
    @pytest.mark.slow
    def test_probabilities_are_normalized(self, small_history, sample_jornada_data):
        predictions = predict_jornada_from_model(
            partidos=sample_jornada_data["partidos"],
            history_df=small_history,
            jornada=99,
            cutoff_date="2025-01-01",
        )

        for pred in predictions.get("predicciones", []):
            total = pred["prob_1"] + pred["prob_x"] + pred["prob_2"]
            assert 0.99 <= total <= 1.01

    @pytest.mark.slow
    def test_fuente_probabilidades_structure(self, small_history, sample_jornada_data):
        predictions = predict_jornada_from_model(
            partidos=sample_jornada_data["partidos"],
            history_df=small_history,
            jornada=99,
            cutoff_date="2025-01-01",
        )

        for pred in predictions.get("predicciones", []):
            fuente = pred["fuente_probabilidades"]
            assert fuente["modelo_primario"] == "motor_maestro_hibrido"
            assert "componentes" in fuente


# ============================================================================
# TESTS: edge cases
# ============================================================================

class TestEdgeCases:
    @pytest.mark.slow
    def test_handles_empty_partidos_list(self, small_history):
        predictions = predict_jornada_from_model(
            partidos=[],
            history_df=small_history,
            jornada=99,
            cutoff_date="2025-01-01",
        )
        assert predictions["estado"] == "sin_partidos"

    @pytest.mark.slow
    def test_handles_unknown_team(self, small_history):
        match = {
            "home": "Equipo Fantastico FC",
            "away": "Club Inexistente SA",
            "date": "2025-01-10",
            "division": "Primera",
        }
        predictions = predict_jornada_from_model(
            partidos=[match],
            history_df=small_history,
            jornada=99,
            cutoff_date="2025-01-01",
        )
        if predictions.get("predicciones"):
            pred = predictions["predicciones"][0]
            assert "avisos" in pred
