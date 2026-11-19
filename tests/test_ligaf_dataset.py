from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import pytest

from scripts.motor import ligaf_model


FIELDS = ["season", "date", "match_id", "home", "home_goals", "away_goals", "away", "scorers", "status"]
ROOT = Path(__file__).resolve().parents[1]


def _write_supplement(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _row(**overrides):
    row = {
        "season": "2023-24",
        "date": "2023-09-15",
        "match_id": "upload-1",
        "home": "Valencia",
        "home_goals": "0",
        "away_goals": "2",
        "away": "Real Madrid",
        "scorers": "",
        "status": "Full Time",
    }
    row.update(overrides)
    return row


def test_cargar_dated_merges_seasons_and_deduplicates_statsbomb():
    baseline = ligaf_model.cargar_statsbomb_2324()
    matches = ligaf_model.cargar_dated()

    assert len(baseline) == 240
    assert len(matches) == 807  # 240 duplicate 2023-24 rows collapse; 480 + 87 are new.
    assert matches == sorted(matches, key=lambda item: (item["fecha"], item["local"], item["visitante"]))
    keys = [ligaf_model._fixture_key(match) for match in matches]
    assert len(keys) == len(set(keys))
    assert Counter(ligaf_model._season_from_date(match["fecha"]) for match in matches) == {
        "2023-24": 240,
        "2024-25": 240,
        "2025-26": 240,
        "2026-27": 87,
    }
    assert ligaf_model.canon("Levante UD Femenino") == ligaf_model.canon("Levante") == "levante"
    assert ligaf_model.canon("FC Levante Badalona") == "badalona"
    assert ligaf_model.canon("Levante Las Planas") == "las_planas"


def test_uploaded_loader_skips_nonfinal_and_checks_schema_and_result_rows(tmp_path):
    path = tmp_path / "results.csv"
    _write_supplement(
        path,
        [
            _row(),
            _row(date="2023-09-16", match_id="pending", status="Postponed", home_goals="", away_goals=""),
        ],
    )

    matches = ligaf_model._load_uploaded_results(path)
    assert len(matches) == 1
    assert matches[0]["fecha"] == datetime(2023, 9, 15)
    assert matches[0]["local"] == "valencia"


def test_uploaded_loader_rejects_duplicate_fixture_and_wrong_season(tmp_path):
    path = tmp_path / "results.csv"
    _write_supplement(path, [_row(), _row(match_id="upload-2")])
    with pytest.raises(ValueError, match="Partido duplicado"):
        ligaf_model._load_uploaded_results(path)

    _write_supplement(path, [_row(season="2024-25")])
    with pytest.raises(ValueError, match="Temporada no coincide"):
        ligaf_model._load_uploaded_results(path)

    _write_supplement(path, [_row(home="")])
    with pytest.raises(ValueError, match="Identidad de equipos inválida"):
        ligaf_model._load_uploaded_results(path)


def test_cargar_dated_fails_closed_on_conflicting_source_score(tmp_path, monkeypatch):
    baseline = tmp_path / "ligaf_resultados_2324_dated.csv"
    with baseline.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "local", "visitante", "gh", "ga"])
        writer.writeheader()
        writer.writerow({
            "date": "2023-09-15",
            "local": "Valencia CF",
            "visitante": "Real Madrid CF W",
            "gh": 1,
            "ga": 2,
        })
    supplemental = tmp_path / "liga_f_partidos_2023-27.csv"
    _write_supplement(supplemental, [_row()])
    monkeypatch.setattr(ligaf_model, "BASE", tmp_path)

    with pytest.raises(ValueError, match="Discrepancia de marcador"):
        ligaf_model.cargar_dated()


def test_ligaf_source_manifests_match_the_versioned_files():
    directory = ROOT / "DATOS" / "ligaf"
    for manifest_name, file_key in (
        ("MANIFIESTO_FUENTES.json", "csv"),
        ("liga_f_partidos_2023-27_manifest.json", "dataset"),
    ):
        manifest = json.loads((directory / manifest_name).read_text(encoding="utf-8"))
        source_path = directory / manifest["archivos"][file_key] if file_key == "csv" else directory / manifest[file_key]
        actual = hashlib.sha256(source_path.read_bytes()).hexdigest()
        expected = manifest["archivos"]["sha256_csv"] if file_key == "csv" else manifest["sha256"]
        assert actual == expected
