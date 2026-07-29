import csv
import json
import subprocess
import sys
from pathlib import Path

import dataset_quality as dq


ROOT = Path(__file__).resolve().parents[1]


def _write_csv(path, fieldnames, rows, *, bom=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    encoding = "utf-8-sig" if bom else "utf-8"
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _history_row(**changes):
    row = {
        "Date": "01/09/2020",
        "HomeTeam": "Local",
        "AwayTeam": "Visitante",
        "FTHG": "2",
        "FTAG": "1",
        "FTR": "H",
        "HS": "10",
        "AS": "8",
        "HST": "4",
        "AST": "3",
        "HF": "9",
        "AF": "11",
        "HC": "5",
        "AC": "2",
        "HY": "1",
        "AY": "2",
        "HR": "0",
        "AR": "0",
        "B365H": "2.0",
        "B365D": "3.0",
        "B365A": "4.0",
        "B365CH": "2.1",
        "B365CD": "3.1",
        "B365CA": "4.1",
    }
    row.update(changes)
    return row


def test_history_rules_distinguish_empty_admin_and_real_close(tmp_path):
    fields = list(_history_row())
    csv_path = tmp_path / "SEGUNDA" / "SP2_2021.csv"
    no_real_close = _history_row(B365CH="", B365CD="", B365CA="")
    genuine_equality = _history_row(
        Date="02/09/2020", HomeTeam="Otro", B365CH="2.0", B365CD="3.0", B365CA="4.0"
    )
    mismatch_and_low_overround = _history_row(
        Date="03/09/2020",
        HomeTeam="Tercero",
        FTR="A",
        B365CH="5.0",
        B365CD="5.0",
        B365CA="5.0",
    )
    invalid_date = _history_row(Date="no-es-fecha", HomeTeam="Cuarto")
    administrative = _history_row(
        Date="05/09/2020",
        HomeTeam="Administrativo",
        FTHG="0",
        FTAG="1",
        FTR="A",
        **{column: "" for column in dq.MATCH_STAT_COLUMNS},
        B365H="",
        B365D="",
        B365A="",
        B365CH="",
        B365CD="",
        B365CA="",
    )
    empty = {field: "" for field in fields}
    _write_csv(
        csv_path,
        fields,
        [no_real_close, genuine_equality, mismatch_and_low_overround, invalid_date, administrative, empty],
    )

    result = dq.audit_history_csv(csv_path, overround_min=0.8, overround_max=1.3)

    assert result["rows"]["raw"] == 6
    assert result["rows"]["empty"] == 1
    assert result["rows"]["usable"] == 3
    assert result["rows"]["discardable"] == 3
    assert result["rows"]["discard_primary_reasons"] == {
        "EMPTY_ROW": 1,
        "INVALID_DATE": 1,
        "MISSING_REQUIRED_ODDS": 1,
    }
    assert result["administrative_matches"]["candidate_rows"] == 1
    assert result["dates"]["invalid_non_empty"] == 1
    assert result["results"]["goal_result_mismatches"] == 1
    assert result["odds"]["equal_without_real_close"] == 1
    assert result["odds"]["equal_with_real_close"] == 1
    assert result["odds"]["overround"]["below_range"] == 1
    assert result["shots"]["schema_complete"] is True
    assert result["shots"]["rows_with_all_values"] == 4


def test_history_alias_candidates_do_not_unify_reserve_teams(tmp_path):
    fields = list(_history_row())
    first = tmp_path / "SEGUNDA" / "SP2_1718.csv"
    second = tmp_path / "SEGUNDA" / "SP2_2526.csv"
    _write_csv(
        first,
        fields,
        [
            _history_row(HomeTeam="Leonesa", AwayTeam="Rival 1"),
            _history_row(Date="02/09/2020", HomeTeam="Barcelona B", AwayTeam="Rival 2"),
        ],
    )
    _write_csv(
        second,
        fields,
        [
            _history_row(HomeTeam="Cultural Leonesa", AwayTeam="Rival 3"),
            _history_row(Date="02/09/2020", HomeTeam="Barcelona", AwayTeam="Rival 4"),
        ],
    )

    result = dq.audit_historical(tmp_path)
    pairs = {tuple(item["names"]) for item in result["aliases"]["candidates"]}

    assert ("Cultural Leonesa", "Leonesa") in pairs
    assert ("Barcelona", "Barcelona B") not in pairs
    assert all(item["action"] == "human_review_only" for item in result["aliases"]["candidates"])


def test_highlightly_detects_bom_states_playoffs_and_logical_duplicates(tmp_path):
    path = tmp_path / "highlightly.csv"
    fields = [
        "match_id",
        "date",
        "league_name",
        "league_season",
        "round",
        "status",
        "home_name",
        "away_name",
        "home_goals",
        "away_goals",
        "sign",
    ]
    rows = [
        {
            "match_id": "1",
            "date": "2025-08-01",
            "league_name": "La Liga",
            "league_season": "2025",
            "round": "Regular Season - 1",
            "status": "Finished",
            "home_name": "A",
            "away_name": "B",
            "home_goals": "1",
            "away_goals": "0",
            "sign": "1",
        },
        {
            "match_id": "2",
            "date": "2025-08-01",
            "league_name": "La Liga",
            "league_season": "2025",
            "round": "Regular Season - 1",
            "status": "Finished",
            "home_name": "A",
            "away_name": "B",
            "home_goals": "1",
            "away_goals": "0",
            "sign": "1",
        },
        {
            "match_id": "3",
            "date": "2025-08-02",
            "league_name": "Segunda División",
            "league_season": "2025",
            "round": "Promotion Play-offs",
            "status": "Cancelled",
            "home_name": "C",
            "away_name": "D",
            "home_goals": "",
            "away_goals": "",
            "sign": "",
        },
    ]
    _write_csv(path, fields, rows, bom=True)

    result = dq.audit_highlightly(path)

    assert result["encoding"]["valid_utf8"] is True
    assert result["encoding"]["has_utf8_bom"] is True
    assert result["encoding"]["replacement_characters"] == 0
    assert result["statuses"]["non_finished"] == 1
    assert result["playoffs"]["rows"] == 1
    assert result["duplicates"]["logical_match_key"] == {
        "groups": 1,
        "rows_involved": 2,
        "excess_rows": 1,
        "examples": [{"date": "2025-08-01", "home": "A", "away": "B", "rows": 2}],
    }
    codes = {item["code"] for item in result["findings"]}
    assert "HIGHLIGHTLY_UTF8_BOM_PRESENT" in codes
    assert "HIGHLIGHTLY_LOGICAL_DUPLICATE" in codes


def test_priors_detect_partial_splits_omitted_from_declared_list(tmp_path):
    teams_path = tmp_path / "teams.json"
    priors_path = tmp_path / "priors.json"
    teams_path.write_text(
        json.dumps(
            {
                "season": "2026/27",
                "laliga_ea_sports": [{"team": "Equipo", "status": "permanencia"}],
                "laliga_hypermotion": [],
            }
        ),
        encoding="utf-8",
    )
    priors_path.write_text(
        json.dumps(
            {
                "season_target": "2026/27",
                "teams": {
                    "Equipo": {
                        "pj": 1,
                        "g": 1,
                        "e": 0,
                        "p": 0,
                        "gf": 2,
                        "gc": 0,
                        "dg": 2,
                        "pts": 3,
                        "home": {"pj": None},
                        "away": {"pj": None},
                        "context": {
                            "status_2026_27": "permanencia",
                            "confidence": "media_baja",
                            "raw_ppg": 3.0,
                            "transition_factor": 0.7,
                            "adjusted_ppg": 2.1,
                        },
                    }
                },
                "missing_or_partial": [],
                "missing_data_strategy": {"teams": ["Equipo"]},
            }
        ),
        encoding="utf-8",
    )

    result = dq.audit_priors(teams_path, priors_path)

    assert result["partiality"]["actual_partial_splits"] == ["Equipo"]
    assert result["partiality"]["partial_not_listed"] == ["Equipo"]
    codes = {item["code"] for item in result["findings"]}
    assert "PRIOR_PARTIAL_NOT_LISTED" in codes
    assert "PRIOR_STRATEGY_TEAM_MISMATCH" not in codes


def test_repository_integration_uses_discovery_and_stable_invariants():
    report = dq.audit_datasets(ROOT)
    historical = report["historical"]
    rows = historical["totals"]["rows"]

    assert historical["file_count"] == len(list((ROOT / "DATOS" / "historico_raw").rglob("*.csv")))
    assert historical["file_count"] > 0
    assert rows["raw"] == rows["empty"] + rows["non_empty"]
    assert rows["raw"] == rows["usable"] + rows["discarded"]
    assert report["highlightly"]["rows"] > 0
    assert report["highlightly"]["encoding"]["valid_utf8"] is True
    assert report["priors"]["teams"]["only_roster"] == []
    assert report["priors"]["teams"]["only_priors"] == []
    assert report["read_only"] is True
    json.dumps(report, ensure_ascii=False, allow_nan=False)


def test_cli_writes_json_only_when_requested(tmp_path):
    output = tmp_path / "evidence" / "audit.json"
    completed = subprocess.run(
        [sys.executable, "scripts/datos/VALIDAR_DATASETS.py", "--json", str(output)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "CONTROL DE CALIDAD" in completed.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["read_only"] is True
