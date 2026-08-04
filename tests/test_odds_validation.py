"""Tests de la validación opcional de cuotas (P0, auditoría externa 04/08/2026).

Invariante: odds_observed_at <= prediction_cutoff_at < kickoff_at.
La validación es opt-in (`check_odds_timestamps=True` en
`compute_features_for_upcoming` o llamada directa a `validate_odds_timestamps`).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import MOTOR_QUINIELA_MAESTRO as motor
from scripts.motor.features import (
    ODDS_TIMESTAMP_FIELDS,
    compute_features_for_upcoming,
    validate_odds_timestamps,
)


def _match(num: int, odds: str, cutoff: str, kickoff: str) -> dict:
    return {
        "num": num,
        "odds_observed_at": odds,
        "prediction_cutoff_at": cutoff,
        "kickoff_at": kickoff,
    }


def test_invariante_valida_secuencia_correcta():
    m = _match(1, "2026-08-03T12:00:00", "2026-08-03T18:00:00", "2026-08-04T20:00:00")
    report = validate_odds_timestamps([m])
    assert report["ok"] is True
    assert report["partidos_validados"] == 1
    assert report["violaciones"] == []


def test_igualdad_odds_corte_es_valida():
    """odds_observed_at == prediction_cutoff_at cumple la invariante (<=)."""
    m = _match(1, "2026-08-03T18:00:00", "2026-08-03T18:00:00", "2026-08-04T20:00:00")
    assert validate_odds_timestamps([m])["ok"] is True


def test_cuotas_observadas_despues_del_corte_es_violacion():
    m = _match(2, "2026-08-04T21:00:00", "2026-08-04T18:00:00", "2026-08-04T20:00:00")
    report = validate_odds_timestamps([m])
    assert report["ok"] is False
    assert "cuotas_observadas_despues_del_corte" in report["violaciones"][0]["issues"]


def test_corte_igual_al_kickoff_es_violacion():
    """El corte debe ser ESTRICTAMENTE anterior al inicio del partido."""
    m = _match(3, "2026-08-04T18:00:00", "2026-08-04T20:00:00", "2026-08-04T20:00:00")
    report = validate_odds_timestamps([m])
    assert report["ok"] is False
    assert "corte_no_anterior_al_kickoff" in report["violaciones"][0]["issues"]


def test_corte_posterior_al_kickoff_es_violacion():
    m = _match(4, "2026-08-04T12:00:00", "2026-08-04T21:00:00", "2026-08-04T20:00:00")
    report = validate_odds_timestamps([m])
    assert report["ok"] is False
    assert "corte_no_anterior_al_kickoff" in report["violaciones"][0]["issues"]


def test_timestamps_ausentes_son_violacion():
    report = validate_odds_timestamps([{"num": 5}])
    assert report["ok"] is False
    issues = report["violaciones"][0]["issues"]
    assert "odds_observed_at_ausente" in issues
    assert "prediction_cutoff_at_ausente" in issues
    assert "kickoff_at_ausente" in issues


def test_timestamps_invalidos_son_violacion():
    m = _match(6, "no-es-una-fecha", "2026-08-03T18:00:00", "2026-08-04T20:00:00")
    report = validate_odds_timestamps([m])
    assert report["ok"] is False
    assert "odds_observed_at_invalido" in report["violaciones"][0]["issues"]


def test_validacion_mixta_cuenta_partidos_validados():
    ok = _match(1, "2026-08-03T12:00:00", "2026-08-03T18:00:00", "2026-08-04T20:00:00")
    bad = _match(2, "2026-08-04T21:00:00", "2026-08-04T18:00:00", "2026-08-04T20:00:00")
    report = validate_odds_timestamps([ok, bad, ok])
    assert report["ok"] is False
    assert report["partidos_validados"] == 2
    assert len(report["violaciones"]) == 1


def test_campos_personalizables():
    m = {"num": 1, "observada": "2026-08-03T12:00:00", "corte": "2026-08-03T18:00:00", "inicio": "2026-08-04T20:00:00"}
    report = validate_odds_timestamps([m], fields=("observada", "corte", "inicio"))
    assert report["ok"] is True


def test_constante_de_campos_por_defecto():
    assert ODDS_TIMESTAMP_FIELDS == ("odds_observed_at", "prediction_cutoff_at", "kickoff_at")


# --- Integración con compute_features_for_upcoming (opt-in) -------------------

@pytest.fixture(scope="module")
def sample_history() -> pd.DataFrame:
    raw = motor.load_raw_history()
    raw["date"] = pd.to_datetime(raw["date"])
    return raw[raw["date"] < "2025-01-01"].copy()


def test_flag_opt_in_lanza_valueerror_con_violaciones(sample_history):
    m = _match(2, "2026-08-04T21:00:00", "2026-08-04T18:00:00", "2026-08-04T20:00:00")
    m.update({"home": "Real Madrid", "away": "Barcelona", "date": "2025-01-10"})
    with pytest.raises(ValueError, match="Validación de cuotas fallida"):
        compute_features_for_upcoming(
            [m], sample_history, cutoff_date="2025-01-01", check_odds_timestamps=True
        )


def test_flag_opt_in_pasa_con_timestamps_correctos(sample_history):
    m = _match(1, "2025-01-09T12:00:00", "2025-01-09T18:00:00", "2025-01-10T20:00:00")
    m.update({"home": "Real Madrid", "away": "Barcelona", "date": "2025-01-10"})
    df = compute_features_for_upcoming(
        [m], sample_history, cutoff_date="2025-01-01", check_odds_timestamps=True
    )
    assert len(df) == 1
    assert np.isnan(df.loc[0, "FTHG"])


def test_sin_flag_la_validacion_no_interfiere(sample_history):
    """Por defecto la validación está desactivada (opcional)."""
    m = _match(2, "2026-08-04T21:00:00", "2026-08-04T18:00:00", "2026-08-04T20:00:00")
    m.update({"home": "Real Madrid", "away": "Barcelona", "date": "2025-01-10"})
    df = compute_features_for_upcoming([m], sample_history, cutoff_date="2025-01-01")
    assert len(df) == 1
