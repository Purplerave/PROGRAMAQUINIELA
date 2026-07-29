"""Inspección de un único CSV histórico."""

from __future__ import annotations

import csv
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .common import (
    EFFECTIVE_CLOSE_ODDS,
    EXPECTED_MATCHES,
    MATCH_STAT_COLUMNS,
    OPEN_ODDS,
    REAL_CLOSE_ODDS,
    SHOT_COLUMNS,
    all_blank,
    display_path,
    duplicate_metrics,
    is_blank,
    normalise_result,
    observed_distribution,
    odds_triplet,
    parse_date,
    result_from_goals,
    text,
    to_float,
)


def _season(path: Path) -> str:
    match = re.search(r"_(\d{2})(\d{2})$", path.stem)
    return f"20{match.group(1)}-20{match.group(2)}" if match else path.stem


def _division(path: Path) -> str:
    parent = path.parent.name.upper()
    if parent == "PRIMERA" or path.stem.upper().startswith("SP1_"):
        return "Primera"
    if parent == "SEGUNDA" or path.stem.upper().startswith("SP2_"):
        return "Segunda"
    return parent.title() or "Desconocida"


def _read(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _new_state() -> dict[str, Any]:
    return {
        "empty_lines": [], "exact_values": [], "non_empty": 0, "usable": 0,
        "primary_reasons": Counter(), "all_reasons": Counter(), "discarded_examples": [],
        "admin": 0, "admin_examples": [], "observed_matches": 0,
        "invalid_dates": 0, "date_examples": [], "comparable": 0, "mismatches": 0,
        "mismatch_examples": [], "match_keys": [], "team_rows": [],
        "shots_any": 0, "shots_complete": 0, "shot_missing_cells": 0,
        "open": 0, "effective_close": 0, "real_close": 0, "equal": 0,
        "equal_no_real": 0, "equal_real": 0, "overround_values": [],
        "overround_low": 0, "overround_high": 0, "overround_examples": [],
    }


def _facts(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": parse_date(row.get("Date")),
        "home": text(row.get("HomeTeam")),
        "away": text(row.get("AwayTeam")),
        "home_goals": to_float(row.get("FTHG")),
        "away_goals": to_float(row.get("FTAG")),
        "result": normalise_result(row.get("FTR")),
        "opening": odds_triplet(row, OPEN_ODDS)[0],
        "effective_close": odds_triplet(row, EFFECTIVE_CLOSE_ODDS)[0],
        "real_close": odds_triplet(row, REAL_CLOSE_ODDS)[0],
    }


def _discard_reasons(facts: dict[str, Any]) -> list[str]:
    reasons = []
    if facts["date"] is None:
        reasons.append("INVALID_DATE")
    if not facts["home"] or not facts["away"]:
        reasons.append("MISSING_MATCH_IDENTITY")
    if facts["home_goals"] is None or facts["away_goals"] is None:
        reasons.append("MISSING_GOALS")
    if facts["result"] is None:
        reasons.append("MISSING_OR_INVALID_RESULT")
    if facts["opening"] is None or facts["effective_close"] is None:
        reasons.append("MISSING_REQUIRED_ODDS")
    return reasons


def _complete_match(facts: dict[str, Any]) -> bool:
    return bool(
        facts["date"] is not None and facts["home"] and facts["away"]
        and facts["home_goals"] is not None and facts["away_goals"] is not None
        and facts["result"] is not None
    )


def _is_administrative(
    row: dict[str, Any], facts: dict[str, Any], match_stats: list[str], odds_columns: list[str]
) -> bool:
    return bool(
        _complete_match(facts) and match_stats and all_blank(row, match_stats)
        and all_blank(row, odds_columns)
    )


def _record_integrity(state: dict[str, Any], row: dict[str, Any], facts: dict[str, Any], line: int, season: str) -> None:
    date, home, away = facts["date"], facts["home"], facts["away"]
    if date is None:
        state["invalid_dates"] += 1
        if len(state["date_examples"]) < 10:
            state["date_examples"].append({"line": line, "value": text(row.get("Date"))})
    elif home and away:
        state["match_keys"].append((date.date().isoformat(), home, away))
        state["team_rows"].extend(((home, season), (away, season)))

    if None not in (facts["home_goals"], facts["away_goals"], facts["result"]):
        state["comparable"] += 1
        expected = result_from_goals(facts["home_goals"], facts["away_goals"])
        if expected != facts["result"]:
            state["mismatches"] += 1
            if len(state["mismatch_examples"]) < 10:
                state["mismatch_examples"].append({
                    "line": line, "date": text(row.get("Date")), "home": home, "away": away,
                    "goals": [facts["home_goals"], facts["away_goals"]], "result": facts["result"],
                })


def _record_shots(state: dict[str, Any], row: dict[str, Any], shot_schema: bool) -> None:
    if not shot_schema:
        return
    populated = sum(not is_blank(row.get(column)) for column in SHOT_COLUMNS)
    state["shots_any"] += int(populated > 0)
    state["shots_complete"] += int(populated == len(SHOT_COLUMNS))
    state["shot_missing_cells"] += len(SHOT_COLUMNS) - populated


def _record_odds(
    state: dict[str, Any], row: dict[str, Any], facts: dict[str, Any], line: int,
    overround_min: float, overround_max: float,
) -> None:
    opening, close, real = facts["opening"], facts["effective_close"], facts["real_close"]
    state["open"] += int(opening is not None)
    state["effective_close"] += int(close is not None)
    state["real_close"] += int(real is not None)
    if opening is not None and close is not None:
        equal = all(math.isclose(opening[s], close[s], rel_tol=1e-12, abs_tol=1e-12) for s in ("1", "X", "2"))
        if equal:
            state["equal"] += 1
            state["equal_no_real" if real is None else "equal_real"] += 1
    if close is None:
        return
    overround = sum(1.0 / close[sign] for sign in ("1", "X", "2"))
    state["overround_values"].append(overround)
    state["overround_low"] += int(overround < overround_min)
    state["overround_high"] += int(overround > overround_max)
    if (overround < overround_min or overround > overround_max) and len(state["overround_examples"]) < 20:
        state["overround_examples"].append({
            "line": line, "date": text(row.get("Date")), "home": facts["home"],
            "away": facts["away"], "overround": round(overround, 6),
        })


def _record_discard(
    state: dict[str, Any], row: dict[str, Any], facts: dict[str, Any], line: int, administrative: bool
) -> None:
    reasons = _discard_reasons(facts)
    if not reasons:
        state["usable"] += 1
        return
    state["primary_reasons"][reasons[0]] += 1
    state["all_reasons"].update(reasons)
    if len(state["discarded_examples"]) < 20:
        state["discarded_examples"].append({
            "line": line, "date": text(row.get("Date")), "home": facts["home"],
            "away": facts["away"], "reasons": reasons,
            "administrative_candidate": administrative,
        })


def _scan(
    rows: list[dict[str, Any]], columns: list[str], season: str,
    overround_min: float, overround_max: float,
) -> dict[str, Any]:
    state = _new_state()
    shot_schema = all(column in columns for column in SHOT_COLUMNS)
    match_stats = [column for column in MATCH_STAT_COLUMNS if column in columns]
    odds_columns = sorted({column for mapping in (OPEN_ODDS, REAL_CLOSE_ODDS, EFFECTIVE_CLOSE_ODDS)
                           for choices in mapping.values() for column in choices if column in columns})
    for line, row in enumerate(rows, start=2):
        state["exact_values"].append(tuple(text(row.get(column)) for column in columns))
        if all_blank(row, columns):
            state["empty_lines"].append(line)
            continue
        state["non_empty"] += 1
        facts = _facts(row)
        _record_integrity(state, row, facts, line, season)
        _record_shots(state, row, shot_schema)
        _record_odds(state, row, facts, line, overround_min, overround_max)
        administrative = _is_administrative(row, facts, match_stats, odds_columns)
        if _complete_match(facts):
            state["observed_matches"] += 1
        if administrative:
            state["admin"] += 1
            if len(state["admin_examples"]) < 20:
                state["admin_examples"].append({
                    "line": line, "date": facts["date"].date().isoformat(),
                    "home": facts["home"], "away": facts["away"],
                })
        _record_discard(state, row, facts, line, administrative)
    return state


def _overround(state: dict[str, Any], minimum: float, maximum: float) -> dict[str, Any]:
    result = {
        "range": {"min_allowed": minimum, "max_allowed": maximum},
        "rows_evaluated": len(state["overround_values"]), "below_range": state["overround_low"],
        "above_range": state["overround_high"],
        "outside_range": state["overround_low"] + state["overround_high"],
        "examples": state["overround_examples"],
    }
    if state["overround_values"]:
        result["observed"] = observed_distribution(state["overround_values"])
    return result


def _coverage(division: str, state: dict[str, Any]) -> dict[str, Any]:
    expected = EXPECTED_MATCHES.get(division)
    result = {
        "expected_regular_matches": expected, "observed_match_rows": state["observed_matches"],
        "usable_rows": state["usable"], "administrative_candidates": state["admin"],
        "other_discarded_rows": state["non_empty"] - state["usable"] - state["admin"],
    }
    if expected is not None:
        result.update({
            "usable_gap": expected - state["usable"],
            "observed_gap": expected - state["observed_matches"],
            "gap_explained_by_administrative": min(state["admin"], max(0, expected - state["usable"])),
        })
    return result


def inspect_history_csv(
    path: Path, *, overround_min: float, overround_max: float, display_root: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if overround_min >= overround_max:
        raise ValueError("overround_min debe ser menor que overround_max")
    columns, rows = _read(path)
    season, division = _season(path), _division(path)
    state = _scan(rows, columns, season, overround_min, overround_max)
    primary, all_reasons = Counter(state["primary_reasons"]), Counter(state["all_reasons"])
    primary["EMPTY_ROW"] += len(state["empty_lines"])
    all_reasons["EMPTY_ROW"] += len(state["empty_lines"])
    exact = duplicate_metrics(state["exact_values"])
    keys = duplicate_metrics(state["match_keys"])
    shot_schema = all(column in columns for column in SHOT_COLUMNS)
    report = {
        "path": display_path(path, display_root), "division": division, "season": season,
        "columns": len(columns),
        "rows": {
            "raw": len(rows), "empty": len(state["empty_lines"]), "non_empty": state["non_empty"],
            "usable": state["usable"], "discardable": len(rows) - state["usable"],
            "discarded": len(rows) - state["usable"],
            "discarded_non_empty": state["non_empty"] - state["usable"],
            "discard_primary_reasons": dict(sorted(primary.items())),
            "discard_all_reasons": dict(sorted(all_reasons.items())),
            "empty_csv_lines": state["empty_lines"][:20],
            "discarded_examples": state["discarded_examples"],
        },
        "duplicates": {"exact": exact, "match_key": keys},
        "dates": {"invalid_non_empty": state["invalid_dates"], "examples": state["date_examples"]},
        "results": {"comparable": state["comparable"], "goal_result_mismatches": state["mismatches"],
                    "examples": state["mismatch_examples"]},
        "shots": {
            "required_columns": list(SHOT_COLUMNS),
            "columns_present": [c for c in SHOT_COLUMNS if c in columns],
            "columns_missing": [c for c in SHOT_COLUMNS if c not in columns],
            "schema_complete": shot_schema, "rows_with_any_value": state["shots_any"] if shot_schema else 0,
            "rows_with_all_values": state["shots_complete"] if shot_schema else 0,
            "missing_value_cells": state["shot_missing_cells"] if shot_schema else 0,
            "rows_without_schema": 0 if shot_schema else state["non_empty"],
        },
        "odds": {
            "opening_schema_columns": [c for choices in OPEN_ODDS.values() for c in choices if c in columns],
            "real_close_schema_columns": [c for choices in REAL_CLOSE_ODDS.values() for c in choices if c in columns],
            "rows_opening_available": state["open"], "rows_effective_close_available": state["effective_close"],
            "rows_real_close_available": state["real_close"],
            "rows_without_real_close": state["non_empty"] - state["real_close"],
            "rows_open_equals_effective_close": state["equal"],
            "equal_without_real_close": state["equal_no_real"], "equal_with_real_close": state["equal_real"],
            "overround": _overround(state, overround_min, overround_max),
        },
        "administrative_matches": {
            "candidate_rows": state["admin"],
            "criterion": "Resultado completo, estadísticas de partido presentes en el esquema pero vacías y cuotas vacías.",
            "examples": state["admin_examples"],
        },
        "season_coverage": _coverage(division, state),
    }
    internal = {"match_keys": state["match_keys"], "team_rows": state["team_rows"],
                "overround_values": state["overround_values"], "overround_examples": state["overround_examples"]}
    return report, internal
