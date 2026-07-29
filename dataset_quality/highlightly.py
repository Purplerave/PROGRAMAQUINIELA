"""Auditoría del CSV de Highlightly."""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .common import (
    PROJECT_ROOT,
    SHOT_COLUMNS,
    display_path,
    duplicate_metrics,
    finding,
    normalise_result,
    parse_date,
    result_from_goals,
    text,
    to_float,
)


DEFAULT_HIGHLIGHTLY = (
    PROJECT_ROOT / "DATOS" / "highlightly_dataset" / "highlightly_partidos_2023_2026.csv"
)


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]], dict[str, Any]]:
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        decoded = raw.decode("utf-8-sig")
        valid, error = True, None
    except UnicodeDecodeError as exc:
        decoded = raw.decode("utf-8-sig", errors="replace")
        valid, error = False, {"start": exc.start, "end": exc.end, "reason": exc.reason}
    reader = csv.DictReader(io.StringIO(decoded, newline=""))
    return list(reader.fieldnames or []), [dict(row) for row in reader], {
        "valid_utf8": valid, "has_utf8_bom": has_bom,
        "replacement_characters": decoded.count("\ufffd"), "decode_error": error,
    }


def _normalise(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()


def _is_playoff(round_name: str) -> bool:
    normalised = _normalise(round_name).replace(" ", "-")
    return "play-off" in normalised or "playoff" in normalised or "promotion" in normalised


def _is_finished(status: str) -> bool:
    return status.casefold().startswith("finished")


def _duplicates(rows: list[dict[str, str]], columns: list[str]) -> dict[str, Any]:
    exact = [tuple(text(row.get(column)) for column in columns) for row in rows]
    match_ids = [(text(row.get("match_id")),) for row in rows if text(row.get("match_id"))]
    logical_keys = [
        (text(row.get("date")), text(row.get("home_name")), text(row.get("away_name")))
        for row in rows
        if text(row.get("date")) and text(row.get("home_name")) and text(row.get("away_name"))
    ]
    logical_counts = Counter(logical_keys)
    examples = [
        {"date": key[0], "home": key[1], "away": key[2], "rows": count}
        for key, count in sorted(logical_counts.items()) if count > 1
    ][:20]
    return {
        "exact": duplicate_metrics(exact), "match_id": duplicate_metrics(match_ids),
        "logical_match_key": {**duplicate_metrics(logical_keys), "examples": examples},
    }


def _status_and_goals(rows: list[dict[str, str]]) -> tuple[dict[str, Any], dict[str, Any]]:
    statuses = Counter(text(row.get("status")) or "<empty>" for row in rows)
    non_finished = sum(count for status, count in statuses.items() if not _is_finished(status))
    without_goals = [
        row for row in rows
        if to_float(row.get("home_goals")) is None or to_float(row.get("away_goals")) is None
    ]
    missing_by_status = Counter(text(row.get("status")) or "<empty>" for row in without_goals)
    return (
        {"counts": dict(sorted(statuses.items())), "non_finished": non_finished},
        {"rows_without_both_goals": len(without_goals),
         "missing_by_status": dict(sorted(missing_by_status.items()))},
    )


def _playoffs(rows: list[dict[str, str]]) -> dict[str, Any]:
    selected = [row for row in rows if _is_playoff(text(row.get("round")))]
    groups = Counter((text(row.get("league_name")), text(row.get("league_season"))) for row in selected)
    return {
        "rows": len(selected),
        "groups": [{"league": key[0], "season": key[1], "rows": count}
                   for key, count in sorted(groups.items())],
    }


def _regular_finished(rows: list[dict[str, str]], league: str, season: str) -> int:
    return sum(
        1 for row in rows
        if text(row.get("league_name")) == league
        and text(row.get("league_season")) == season
        and _is_finished(text(row.get("status")))
        and not _is_playoff(text(row.get("round")))
    )


def _coverage(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for row in rows:
        key = (text(row.get("league_name")), text(row.get("league_season")))
        finished = _is_finished(text(row.get("status")))
        groups[key]["rows"] += 1
        groups[key]["finished"] += int(finished)
        groups[key]["non_finished"] += int(not finished)
        groups[key]["playoffs"] += int(_is_playoff(text(row.get("round"))))
    result = []
    for (league, season), counts in sorted(groups.items()):
        expected = {"La Liga": 380, "Segunda Division": 462}.get(
            league.replace("División", "Division")
        )
        regular = _regular_finished(rows, league, season)
        item = {
            "league": league, "season": season, "rows": counts["rows"],
            "finished": counts["finished"], "non_finished": counts["non_finished"],
            "playoffs": counts["playoffs"], "regular_finished": regular,
            "expected_regular_matches": expected,
        }
        if expected is not None:
            item["regular_finished_gap"] = expected - regular
        result.append(item)
    return result


def _sign_consistency(rows: list[dict[str, str]]) -> dict[str, Any]:
    comparable, mismatches, examples = 0, 0, []
    for row in rows:
        home, away = to_float(row.get("home_goals")), to_float(row.get("away_goals"))
        sign = normalise_result(row.get("sign"))
        if home is None or away is None or sign is None:
            continue
        comparable += 1
        if result_from_goals(home, away) != sign:
            mismatches += 1
            if len(examples) < 10:
                examples.append({
                    "match_id": text(row.get("match_id")), "home": text(row.get("home_name")),
                    "away": text(row.get("away_name")),
                })
    return {"comparable": comparable, "mismatches": mismatches, "examples": examples}


def _encoding_findings(encoding: dict[str, Any]) -> list[dict[str, Any]]:
    if not encoding["valid_utf8"]:
        result = [finding(
            "HIGHLIGHTLY_UTF8_INVALID", "critical", "El CSV no decodifica como UTF-8 estricto.",
            1, decode_error=encoding["decode_error"],
        )]
    elif encoding["has_utf8_bom"]:
        result = [finding(
            "HIGHLIGHTLY_UTF8_BOM_PRESENT", "info",
            "CSV UTF-8 válido con BOM; debe leerse como utf-8-sig para no contaminar la primera columna.", 1,
        )]
    else:
        result = [finding(
            "HIGHLIGHTLY_UTF8_BOM_MISSING", "info", "CSV UTF-8 válido sin BOM.", 1,
        )]
    if encoding["replacement_characters"]:
        result.append(finding(
            "HIGHLIGHTLY_REPLACEMENT_CHARACTER", "warning",
            "Caracteres de reemplazo U+FFFD presentes en el contenido decodificado.",
            encoding["replacement_characters"],
        ))
    return result


def _content_findings(
    statuses: dict[str, Any], goals: dict[str, Any], playoffs: dict[str, Any],
    duplicates: dict[str, Any], coverage: list[dict[str, Any]], signs: dict[str, Any],
) -> list[dict[str, Any]]:
    result = []
    if statuses["non_finished"]:
        result.append(finding(
            "HIGHLIGHTLY_NON_FINISHED", "info",
            "Partidos no finalizados (Finished, Finished after extra time y Finished after penalties sí cuentan como finales).",
            statuses["non_finished"], statuses=statuses["counts"],
        ))
    if goals["rows_without_both_goals"]:
        result.append(finding(
            "HIGHLIGHTLY_GOALS_MISSING", "info",
            "Filas sin ambos goles disponibles, contabilizadas por estado.",
            goals["rows_without_both_goals"], statuses=goals["missing_by_status"],
        ))
    if playoffs["rows"]:
        result.append(finding(
            "HIGHLIGHTLY_PLAYOFF", "info", "Filas de play-off/promoción separadas de la liga regular.",
            playoffs["rows"], groups=playoffs["groups"],
        ))
    exact, match_id, logical = duplicates["exact"], duplicates["match_id"], duplicates["logical_match_key"]
    if exact["rows_involved"]:
        result.append(finding(
            "HIGHLIGHTLY_EXACT_DUPLICATE", "warning", "Filas exactas duplicadas en Highlightly.",
            exact["rows_involved"], **exact,
        ))
    if match_id["rows_involved"]:
        result.append(finding(
            "HIGHLIGHTLY_MATCH_ID_DUPLICATE", "warning", "Identificadores match_id repetidos.",
            match_id["rows_involved"], **match_id,
        ))
    if logical["rows_involved"]:
        result.append(finding(
            "HIGHLIGHTLY_LOGICAL_DUPLICATE", "warning",
            "Duplicados excedentes por (fecha, local, visitante), aunque puedan tener match_id distinto.",
            logical["excess_rows"], groups=logical["groups"], rows_involved=logical["rows_involved"],
            excess_rows=logical["excess_rows"], examples=logical["examples"],
        ))
    incomplete = [item for item in coverage if item["expected_regular_matches"] is not None
                  and item["regular_finished"] != item["expected_regular_matches"]]
    if incomplete:
        result.append(finding(
            "HIGHLIGHTLY_SEASON_INCOMPLETE", "warning",
            "Cobertura regular española distinta de 380/462 partidos finalizados.",
            len(incomplete), groups=incomplete,
        ))
    if signs["mismatches"]:
        result.append(finding(
            "HIGHLIGHTLY_SIGN_MISMATCH", "warning", "El signo derivado contradice los goles.",
            signs["mismatches"], examples=signs["examples"],
        ))
    return result


def audit_highlightly(
    path: str | Path = DEFAULT_HIGHLIGHTLY, *, display_root: str | Path | None = None,
) -> dict[str, Any]:
    """Audita cobertura, estados, duplicados y codificación de Highlightly."""

    csv_path = Path(path)
    root = Path(display_root) if display_root is not None else None
    columns, rows, encoding = _read_csv(csv_path)
    duplicates = _duplicates(rows, columns)
    statuses, goals = _status_and_goals(rows)
    playoffs, coverage, signs = _playoffs(rows), _coverage(rows), _sign_consistency(rows)
    dates = [parsed for row in rows if (parsed := parse_date(row.get("date"))) is not None]
    odds_columns = [c for c in columns if "odd" in c.casefold() or c.startswith(("B365", "Avg"))]
    shot_columns = [column for column in SHOT_COLUMNS if column in columns]
    findings = _encoding_findings(encoding) + _content_findings(
        statuses, goals, playoffs, duplicates, coverage, signs
    )
    return {
        "source": display_path(csv_path, root), "rows": len(rows), "columns": columns,
        "encoding": encoding,
        "date_range": {
            "minimum": min(dates).date().isoformat() if dates else None,
            "maximum": max(dates).date().isoformat() if dates else None,
            "invalid": len(rows) - len(dates),
        },
        "schema_capabilities": {
            "odds_columns": odds_columns, "shot_columns": shot_columns,
            "can_supply_motor_odds": bool(odds_columns),
            "can_supply_motor_shots": len(shot_columns) == len(SHOT_COLUMNS),
        },
        "statuses": statuses, "goals": goals, "playoffs": playoffs, "duplicates": duplicates,
        "sign_consistency": signs, "coverage": coverage, "findings": findings,
    }
