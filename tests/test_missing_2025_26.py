from pathlib import Path

import pytest

from scripts.datos import PREPARAR_AUSENTES_2025_26 as missing


def test_builds_exact_missing_counts():
    rows = missing.build_missing_rows()
    assert len(rows) == 168
    assert sum(row["division"] == "Primera" for row in rows) == 80
    assert sum(row["division"] == "Segunda" for row in rows) == 88


def test_rows_are_traceable_and_do_not_invent_features():
    row = missing.build_missing_rows()[0]
    assert row["source"] == "Highlightly"
    assert row["missing_odds"] is True
    assert row["missing_shots"] is True
    assert row["result"] in {"H", "D", "A"}


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
