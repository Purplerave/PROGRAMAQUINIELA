from pathlib import Path

import pandas as pd
import pytest

import settings
import MOTOR_QUINIELA_MAESTRO as motor


def test_required_project_files_exist():
    assert settings.CONFIG_PATH.is_file()
    assert settings.RAW_BASE.joinpath("PRIMERA").is_dir()
    assert settings.RAW_BASE.joinpath("SEGUNDA").is_dir()


def test_historical_csvs_are_packaged():
    csv_files = list(Path(settings.RAW_BASE).rglob("*.csv"))
    assert len(csv_files) == 32


def test_loader_uses_original_by_default():
    assert len(motor.load_raw_history()) > 0


def test_loader_uses_sanitized_source(monkeypatch, tmp_path):
    source = tmp_path / "historico_saneado.csv"
    original = next(settings.RAW_BASE.joinpath("PRIMERA").glob("*.csv"))
    frame = pd.read_csv(original, nrows=1)
    frame["division"] = "Primera"
    frame["season"] = "2025-2026"
    frame["source_file"] = original.name
    frame.to_csv(source, index=False)
    monkeypatch.setattr(motor, "SANITIZED_HISTORY", source)
    loaded = motor.load_raw_history("saneado")
    assert len(loaded) == 1
    assert loaded.iloc[0]["division"] == "Primera"
    assert loaded.iloc[0]["season"] == "2025-2026"
    assert loaded.iloc[0]["source_file"] == original.name


@pytest.mark.parametrize(("division", "expected_code"), [("Primera", 0), ("Segunda", 1)])
def test_sanitized_division_codes(monkeypatch, tmp_path, division, expected_code):
    original = next(settings.RAW_BASE.joinpath("PRIMERA").glob("*.csv"))
    frame = pd.read_csv(original, nrows=1)
    frame["division"] = division
    frame["season"] = "2025-2026"
    frame["source_file"] = original.name
    source = tmp_path / f"{division}.csv"
    frame.to_csv(source, index=False)
    monkeypatch.setattr(motor, "SANITIZED_HISTORY", source)
    loaded = motor.load_raw_history("saneado")
    assert loaded.iloc[0]["division_code"] == expected_code


def test_sanitized_unknown_division_fails(monkeypatch, tmp_path):
    original = next(settings.RAW_BASE.joinpath("PRIMERA").glob("*.csv"))
    frame = pd.read_csv(original, nrows=1)
    frame["division"] = "Desconocida"
    frame["season"] = "2025-2026"
    frame["source_file"] = original.name
    source = tmp_path / "desconocida.csv"
    frame.to_csv(source, index=False)
    monkeypatch.setattr(motor, "SANITIZED_HISTORY", source)
    with pytest.raises(ValueError, match="División desconocida"):
        motor.load_raw_history("saneado")


def test_loader_reports_missing_sanitized_source(monkeypatch, tmp_path):
    missing = tmp_path / "no-existe.csv"
    monkeypatch.setattr(motor, "SANITIZED_HISTORY", missing)
    with pytest.raises(FileNotFoundError, match="histórico saneado"):
        motor.load_raw_history("saneado")
