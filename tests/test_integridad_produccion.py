"""Regresiones para los puntos críticos de la auditoría de producción."""
from __future__ import annotations

import json
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

import MOTOR_PREDICCION_JORNADA as jornada
import MOTOR_QUINIELA_MAESTRO as maestro
import OPTIMIZADOR_COLUMNAS as columnas
import PREDECIR_JORNADA as paquete
import settings
from scripts.backtests import BACKTEST_HISTORICO_TEMPORADAS as backtest
from scripts.json_output import write_json
from scripts.motor import GENERAR_CONTRATO_API as api
from scripts.motor import dixon_coles, ligaf_model
from scripts.motor.odds_at_cutoff import odds_at_cutoff
from scripts.reports import GENERAR_PRODUCTION_REFERENCE as reference


def test_training_uses_only_prior_days_each_time(monkeypatch):
    history = pd.DataFrame({"date": pd.date_range("2025-01-01", periods=130), "result": ["1", "X", "2"] * 43 + ["1"]})
    monkeypatch.setattr(jornada, "rolling_team_features", lambda frame: frame)
    calls = []

    def fit(frame, selection_mode):
        assert selection_mode == "production"
        calls.append(frame.copy())
        return None, object(), maestro.active_hybrid_config()

    monkeypatch.setattr(jornada, "fit_hybrid_models", fit)
    _, recent, config, _ = jornada._train_models(history, history.loc[125, "date"] + pd.Timedelta(hours=15))
    _, older, _, _ = jornada._train_models(history, history.loc[103, "date"] + pd.Timedelta(hours=15))
    assert recent is not older
    assert [len(c) for c in calls] == [125, 103]
    assert calls[1]["date"].max() == history.loc[102, "date"]
    assert calls[1]["target"].tolist() == (history.iloc[:103]["result"].map(maestro.LABEL_MAP)).tolist()
    assert config["weights"] == {"logit": 0.0, "hgb": 0.049, "market": 0.951, "poisson": 0.0}


def test_walk_forward_excludes_postponed_match_after_start_of_test(monkeypatch):
    rows = pd.DataFrame({
        "season": ["2024-2025", "2024-2025", "2024-2025", "2025-2026"],
        "date": pd.to_datetime(["2025-05-25", "2025-08-20", "2025-08-15", "2025-08-15"]),
        "division": "Primera", "home": "A", "away": "B", "result": "1",
    })

    def fit(train, _mode):
        assert train["date"].tolist() == [pd.Timestamp("2025-05-25")]
        raise ValueError("comprobación del corte completada")

    monkeypatch.setattr(maestro, "fit_hybrid_models", fit)
    with pytest.raises(ValueError, match="completada"):
        maestro.run_season_backtest(rows, "2025-2026")


def test_market_triplet_selection_never_mixes_sources():
    raw = pd.DataFrame([{
        "AvgCH": 1.7, "AvgCD": np.inf, "AvgCA": 5.0,
        "B365CH": 1.9, "B365CD": 3.10, "B365CA": 4.0,
        "AvgH": 2.1, "AvgD": 3.0, "AvgA": 3.3,
    }, {"AvgCH": 1.8, "AvgD": 3.3, "B365CA": 5.0}])
    odds, source = maestro._select_market_triplet(raw, maestro.CLOSE_ODDS + maestro.OPEN_ODDS)
    assert source.tolist() == ["close_b365", "incomplete"]
    np.testing.assert_allclose(odds[0], [1.9, 3.10, 4.0])
    assert np.isnan(odds[1]).all()


@pytest.mark.parametrize("observed,usable", [(None, False), ("2026-09-11T17:01Z", False), ("2026-09-11T17:00Z", True)])
def test_odds_filter_and_trace_agree_madrid_vs_utc(observed, usable):
    # Las 19h en Madrid son las 17h UTC en septiembre.
    match = {"num": 1, "fecha": "2026-09-11", "hora": "21:00", "odds_observed_at": observed,
             "odd_1": 2.0, "odd_x": 3.1, "odd_2": 4.2}
    cutoff = "2026-09-11T19:00"
    eligible, _ = odds_at_cutoff(match, cutoff)
    trace = jornada.attach_odds_traceability({"partidos": [match]}, cutoff)
    assert trace["detalle"][0]["usadas_en_motor_1x2"] is usable
    assert bool(eligible) is usable


def test_incomplete_triplet_never_biases_hybrid():
    frame = pd.DataFrame({"odd_1": [2.0], "odd_x": [3.0], "odd_2": [np.nan]})
    out = maestro.implied_probabilities(frame, "market", ["odd_1", "odd_x", "odd_2"])
    assert out[["market_1", "market_x", "market_2"]].isna().all(axis=None)


def test_explicit_cutoff_cannot_be_after_actual_kickoff():
    ticket = {"partidos": [{"fecha": "2026-10-01", "hora": "18:00"}]}
    with pytest.raises(ValueError, match="anterior al primer partido"):
        jornada.get_cutoff_date(ticket, "2026-10-01T16:00Z")


def test_future_or_wrong_season_priors_never_change_features():
    frame = pd.DataFrame([{"season": "2026-2027", "home": "Malaga CF", "away": "CD Castellon",
                           "home_table_pj": 0, "away_table_pj": 0, "home_table_ppg": 0.0, "away_table_ppg": 0.0}])
    pd.testing.assert_frame_equal(jornada._apply_transition_priors(frame, "2026-06-20"), frame)
    older = frame.assign(season="2025-2026", table_ppg_diff=0.0)
    pd.testing.assert_frame_equal(jornada._apply_transition_priors(older, "2026-08-20"), older)


def test_pleno_chooses_joint_mode_not_product_of_marginals(monkeypatch):
    matrix = np.zeros((1, 8, 8))
    matrix[0, 0, :2] = [0.28, 0.35]
    matrix[0, 1, :2] = [0.33, 0.04]
    monkeypatch.setattr(dixon_coles, "dc_score_probs", lambda *args, **kw: matrix)
    monkeypatch.setattr(jornada, "compute_features_for_upcoming", lambda *args, **kw: pd.DataFrame([{
        "lambda_home": 1.0, "lambda_away": 1.0, "division": "Primera", "home_form_pts_5": 1, "away_form_pts_5": 1,
    }]))
    out = jornada.predict_pleno15_from_model({"local": "A", "visitante": "B"}, pd.DataFrame({"date": []}), 77, "2026-08-15")
    # Ambas modas marginales son 0; el signo más probable es 0-1.
    assert out["goles_local"]["0"] > out["goles_local"]["1"]
    assert out["goles_visitante"]["0"] > out["goles_visitante"]["1"]
    assert (out["seleccion"]["local"], out["seleccion"]["visitante"]) == ("0", "1")
    assert out["seleccion"]["confianza"] == out["goles_conjuntos"]["0-1"] == 0.35


def test_certainty_accepts_true_zero_probability():
    assert jornada._calculate_confidence({"1": 1.0, "X": 0.0, "2": 0.0}) == 1.0


def test_without_model_package_uses_same_proxy_in_optimizer_and_api(monkeypatch):
    captured = []
    real_optimizer = columnas.optimize_jornada

    def optimize(*args, **kwargs):
        captured.append(kwargs["probs_override"])
        return real_optimizer(*args, **kwargs, n_sims=10)

    monkeypatch.setattr(columnas, "optimize_jornada", optimize)
    data = paquete.build_package(74, use_model=False)
    assert len(captured) == 1
    assert captured[0][1]["X"] == pytest.approx(0.26)
    assert data["boleto_optimizado"]["fuentes_probabilidades_por_casilla"]["1"] == "apu_fallback"
    assert data["resumen_modelo"]["partidos_con_prediccion"] == 0
    assert data["partidos"][0]["recomendacion_modelo"]["fuente_utilizada"] == "apu_fallback"
    contract = api.build_api_contract(data)
    assert api.validar_contrato(contract) == []
    assert contract["partidos"][0]["origen_prediccion"] == "manual_pendiente"
    assert contract["partidos"][0]["probabilidades"]["X"] == pytest.approx(0.26)
    assert contract["pleno15"]["pronostico_local"] == "2"
    assert contract["pleno15"]["pronostico_visitante"] == "1"


def test_missing_probability_and_positions_are_rejected():
    input_rows = [{"num": i, "q15": {"1": 55, "X": 25, "2": 20}} for i in range(1, 16)]
    input_rows[0]["q15"].pop("X")
    with pytest.raises(ValueError, match=r"casillas \[1\]"):
        columnas._optimize_partidos(input_rows, jornada=1, n_sims=10)
    input_rows[-1]["num"] = 14
    with pytest.raises(ValueError, match=r"1\.\.15"):
        columnas._optimize_partidos(input_rows, jornada=1, n_sims=10)


def test_monte_carlo_uses_actual_14_match_thresholds():
    summary = columnas.summarize_hits(np.array([10, 13, 14, 14]))
    assert summary["p_ge_14"] == 0.5
    assert summary["p_ge_13"] == 0.75
    assert summary["p_ge_10"] == 1.0
    assert "p_15" not in summary


@pytest.mark.parametrize("invalid", [0, "0.25", float("nan"), float("inf"), -0.3, True])
def test_api_checks_probability_domain_instead_of_only_sum(invalid):
    data = api.build_api_contract(paquete.build_package(74, use_model=False))
    data["partidos"][0]["probabilidades"] = {"1": invalid, "X": 0, "2": 0}
    assert any("Probabilidades" in error for error in api.validar_contrato(data))


def test_no_api_without_source_and_existing_file_is_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SALIDA_DIR", tmp_path)
    result = paquete.build_package(74, use_model=False)
    result["partidos"][0]["probabilidades"]["comparativa"] = {}
    write_json(tmp_path / "paquete_jornada_J74.json", result)
    path = tmp_path / "api_maestros_J74.json"
    path.write_text("anterior", encoding="utf-8")
    assert api.generate_api_contract(74) is None
    assert path.read_text(encoding="utf-8") == "anterior"
    with pytest.raises(ValueError):
        write_json(path, {"error": float("nan")})
    assert path.read_text(encoding="utf-8") == "anterior"


def test_standalone_api_command_resolves_project_imports(tmp_path):
    script = settings.PROJECT_DIR / "scripts" / "motor" / "GENERAR_CONTRATO_API.py"
    proc = subprocess.run([sys.executable, str(script), "--help"], cwd=tmp_path, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "--jornada" in proc.stdout


def test_reference_rejects_stale_hash_and_incomplete_season():
    protocol = {"historico": "saneado", "historico_sha256": "test-hash", "desde_temporada": "2025-2026", "hasta_temporada": "2025-2026"}
    artifact = {"protocolo": protocol, "rows": [{"season": "2025-2026", "test_matches": 842}], "details": {"2025-2026": {"divisions_test": {"Primera": 380, "Segunda": 462}}},
                "resumen": {"protocolo": protocol, "temporadas": 1, "temporadas_con_error": 0}}
    reference.validate_backtest_reference(artifact, protocol)
    with pytest.raises(ValueError, match="hashes"):
        reference.validate_backtest_reference(artifact, {**protocol, "historico_sha256": "otro"})
    artifact["rows"][0]["test_matches"] = 841
    with pytest.raises(ValueError, match="incompleta"):
        reference.validate_backtest_reference(artifact, protocol)
    artifact["rows"][0]["error"] = "faltan datos"
    with pytest.raises(ValueError, match="sin errores"):
        reference.validate_backtest_reference(artifact, protocol)


def test_backtest_nonzero_when_a_requested_season_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["backtest", "--out-dir", str(tmp_path), "--from-season", "2025-2026"])
    monkeypatch.setattr(maestro, "load_raw_history", lambda s: pd.DataFrame({"season": ["2025-2026"], "result": ["1"]}))
    monkeypatch.setattr(backtest, "evaluation_protocol", lambda source, *_: {"historico": source})
    monkeypatch.setattr(maestro, "rolling_team_features", lambda d: d)

    def fail(*_):
        raise ValueError("fallo controlado")

    monkeypatch.setattr(maestro, "run_season_backtest", fail)
    assert backtest.main() == 1
    payload = json.loads((tmp_path / "backtest_historico_temporadas.json").read_text(encoding="utf-8"))
    assert payload["resumen"]["temporadas_con_error"] == 1
    assert payload["protocolo"]["historico"] == "saneado"



def test_ligaf_walkforward_never_trains_on_other_games_from_same_day(monkeypatch):
    monkeypatch.setattr(ligaf_model, "WARMUP", 1)
    monkeypatch.setattr(ligaf_model, "REFIT_CADA", 1)
    fitted = []
    observed = []

    def fit(previous):
        last = max(p["fecha"].date() for p in previous)
        fitted.append(len(previous))
        return ({"ultimo": last}, 0.0, 0.0)

    def predict(home, _away, params, _mu, _gamma):
        assert params["ultimo"].isoformat() < home
        observed.append(home)
        return {"signo": "1", "p1": 0.6, "px": 0.25, "p2": 0.15}

    monkeypatch.setattr(ligaf_model, "ajustar", fit)
    monkeypatch.setattr(ligaf_model, "predecir", predict)
    matches = [{"fecha": day, "local": day.date().isoformat(), "visitante": "B", "gh": 1, "ga": 0}
               for day in pd.date_range("2025-01-01", periods=6, freq="12h")]
    out = ligaf_model.walkforward(matches)
    assert fitted == [2, 4]
    assert len(observed) == out["n_evaluados"] == 4
    assert observed == ["2025-01-02"] * 2 + ["2025-01-03"] * 2
    assert out["por_temporada"]["2024-25"]["n_evaluados"] == 4



def test_optimizer_ranks_actual_double_coverage_with_bands():
    probabilities = [np.array([0.52, 0.05, 0.43]), np.array([0.68, 0.28, 0.04])]
    match_odds = [{"odd_1": 2.1, "odd_2": 3.0}, {"odd_1": 1.6, "odd_2": 8.0}]
    free = columnas.evaluate_all_three_doubles(probabilities, n_doubles=1)
    banded = columnas.evaluate_all_three_doubles(probabilities, n_doubles=1, matches=match_odds)
    assert free["mejor_combinacion"]["dobles"] == [0]
    assert banded["mejor_combinacion"]["dobles"] == [1]
    assert banded["mejor_combinacion"]["aciertos_esperados"] == pytest.approx(0.52 + 0.68 + 0.28)


def test_double_never_excludes_favorite_even_with_ties_or_band():
    probabilities = [np.array([0.36, 0.24, 0.40]), np.array([1 / 3, 1 / 3, 1 / 3])]
    selected = columnas.build_double_development(probabilities, (0, 1), [{"odd_1": 2.5, "odd_2": 3.0}, {}])
    assert "2" in selected[0][1]
    assert "1" in selected[1][1]



def test_proper_scores_pair_only_complete_predictions():
    predictions = pd.DataFrame({
        "result": ["1", "2"], "latest_prob_1": [0.8, np.nan], "latest_prob_x": [0.1, np.nan],
        "latest_prob_2": [0.1, np.nan], "market_1": [0.6, 0.4], "market_x": [0.2, 0.2], "market_2": [0.2, 0.4],
    })
    scores = backtest.probabilistic_market_scores(predictions)
    assert scores["n"] == 1
    assert scores["modelo"]["brier"] == pytest.approx(0.06)
    assert scores["modelo"]["log_loss"] == pytest.approx(-np.log(0.8))
    assert scores["mercado"]["brier"] == pytest.approx(0.24)


@pytest.mark.parametrize("cutoff", ["2026-03-29T02:30", "2026-10-25T02:30"])
def test_rejects_naive_nonexistent_and_ambiguous_cutoffs(cutoff):
    with pytest.raises(ValueError, match="ambigua o inexistente"):
        jornada.get_cutoff_date({"partidos": []}, cutoff)


def test_fall_dst_offsets_distinguish_the_two_occurrences():
    early = jornada.get_cutoff_date({}, "2026-10-25T02:30+02:00")
    late = jornada.get_cutoff_date({}, "2026-10-25T02:30+01:00")
    assert late - early == pd.Timedelta(hours=1)


def test_cutoff_requires_a_complete_calendar_or_a_declared_instant():
    ticket = {"partidos": [{"fecha": "2026-09-12"}, {}]}
    with pytest.raises(ValueError, match="Faltan fechas"):
        jornada.get_cutoff_date(ticket)
    assert jornada.get_cutoff_date(ticket, "2026-09-10T22:00Z").isoformat() == "2026-09-10T22:00:00+00:00"


def test_verified_opening_triplet_is_also_market_if_no_primary_quote():
    match = {"num": 1, "kickoff_at": "2026-09-11T21:00+02:00", "odds_observed_at": "2026-09-10T12:00+02:00",
             "open_odd_1": 2.1, "open_odd_x": 3.8, "open_odd_2": 3.0, "odd_1": 1.1}
    odds, trace = odds_at_cutoff(match, "2026-09-11T19:00+02:00")
    assert trace["fuente_tripleta"] == "apertura_fallback"
    assert [odds[k] for k in ("odd_1", "odd_x", "odd_2")] == [2.1, 3.8, 3.0]



def test_date_only_odds_cannot_be_assumed_to_be_observed_at_midnight():
    match = {"num": 1, "fecha": "2026-09-13", "odds_observed_at": "2026-09-12", "odd_1": 2.0, "odd_x": 3.0, "odd_2": 4.0}
    odds, trace = odds_at_cutoff(match, "2026-09-12T13:00+02:00")
    assert not odds
    assert trace["motivo"] == "odds_observed_at_sin_hora"


def test_pleno_without_kickoff_uses_declared_cutoff_in_local_time():
    rows = pd.DataFrame([{"date": pd.Timestamp("2025-05-19"), "home": "Barcelona", "away": "Sevilla", "result": "1",
                          "FTHG": 2, "FTAG": 1, "division": "Primera", "season": "2024-2025", "division_code": 0}])
    match = {"num": 15, "local": "Barcelona", "visitante": "Sevilla", "division": "Primera"}
    out = jornada.predict_pleno15_from_model(match, rows, 12, "2025-05-23T13:30+02:00")
    assert out["disponible"]
    assert sum(out["goles_conjuntos"].values()) == pytest.approx(1, abs=1e-6)
    assert not jornada.predict_pleno15_from_model({**match, "liga_f": True}, rows, 12, "2025-05-23T13:30+02:00")["disponible"]
