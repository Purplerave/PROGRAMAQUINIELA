from pathlib import Path

import pytest

from scripts.datos import PREPARAR_AUSENTES_2025_26 as missing


def test_completed_history_has_no_missing_matches():
    rows = missing.build_missing_rows()
    assert rows == []


def test_result_from_goals():
    assert missing.result_from_goals(2, 1) == "H"
    assert missing.result_from_goals(1, 1) == "D"
    assert missing.result_from_goals(0, 1) == "A"


def test_aliases_match_known_historical_names():
    assert missing.canonical_historical_team("Ath Madrid") == missing.normalize("Atlético Madrid")
    assert missing.canonical_historical_team("Ceuta") == missing.normalize("AD Ceuta FC")
    assert missing.canonical_historical_team("La Coruna") == missing.normalize("Deportivo La Coruña")


def test_writer_rejects_overwrite(monkeypatch, tmp_path):
    output_dir = tmp_path / "allowed"
    destination = output_dir / "missing.csv"
    monkeypatch.setattr(missing, "OUTPUT_DIR", output_dir)
    missing.write_rows([], destination)
    with pytest.raises(FileExistsError):
        missing.write_rows([], destination)


def test_writer_rejects_external_path(monkeypatch, tmp_path):
    output_dir = tmp_path / "allowed"
    monkeypatch.setattr(missing, "OUTPUT_DIR", output_dir)
    with pytest.raises(ValueError):
        missing.write_rows([], tmp_path / "outside.csv")
