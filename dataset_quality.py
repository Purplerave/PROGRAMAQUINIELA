"""Auditoría reproducible y de solo lectura de los datasets del proyecto.

Las funciones públicas devuelven únicamente estructuras serializables. No corrigen,
normalizan ni sobrescriben los datos inspeccionados.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_RAW_BASE = PROJECT_ROOT / "DATOS" / "historico_raw"
DEFAULT_HIGHLIGHTLY = (
    PROJECT_ROOT / "DATOS" / "highlightly_dataset" / "highlightly_partidos_2023_2026.csv"
)
DEFAULT_TEAMS = PROJECT_ROOT / "DATOS" / "temporada_2026_27_equipos.json"
DEFAULT_PRIORS = PROJECT_ROOT / "DATOS" / "temporada_2026_27_estadisticas_base.json"

SHOT_COLUMNS = ("HS", "AS", "HST", "AST")
MATCH_STAT_COLUMNS = ("HS", "AS", "HST", "AST", "HF", "AF", "HC", "AC", "HY", "AY", "HR", "AR")
OPEN_ODDS = {
    "1": ("AvgH", "B365H"),
    "X": ("AvgD", "B365D"),
    "2": ("AvgA", "B365A"),
}
REAL_CLOSE_ODDS = {
    "1": ("AvgCH", "B365CH"),
    "X": ("AvgCD", "B365CD"),
    "2": ("AvgCA", "B365CA"),
}
# Reproduce el orden de preferencia del cargador actual, incluido su fallback.
EFFECTIVE_CLOSE_ODDS = {
    "1": ("AvgCH", "AvgH", "B365CH", "B365H"),
    "X": ("AvgCD", "AvgD", "B365CD", "B365D"),
    "2": ("AvgCA", "AvgA", "B365CA", "B365A"),
}
EXPECTED_MATCHES = {"Primera": 380, "Segunda": 462}
SEVERITY_RATIONALE = {
    "info": "Evidencia descriptiva que no invalida por sí sola el consumo del dato.",
    "warning": "Anomalía que requiere revisión humana o tratamiento explícito antes de reutilizar el dato.",
    "critical": "Cobertura o semántica ausente que puede introducir señal ficticia o engañar a consumidores automáticos.",
}


def _finding(code: str, severity: str, message: str, count: int, **details: Any) -> dict[str, Any]:
    if severity not in SEVERITY_RATIONALE:
        raise ValueError(f"Severidad desconocida: {severity}")
    item: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "severity_rationale": SEVERITY_RATIONALE[severity],
        "message": message,
        "count": int(count),
    }
    if details:
        item["details"] = details
    return item


def _text(value: Any) -> str:
    if value is None or isinstance(value, list):
        return ""
    return str(value).strip()


def _is_blank(value: Any) -> bool:
    return _text(value) == ""


def _to_float(value: Any) -> float | None:
    text = _text(value).replace(",", ".")
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _choose_odd(row: dict[str, Any], candidates: Iterable[str]) -> tuple[float | None, str | None]:
    for column in candidates:
        value = _to_float(row.get(column))
        if value is not None and value > 1.01:
            return value, column
    return None, None


def _odds_triplet(
    row: dict[str, Any], candidates: dict[str, tuple[str, ...]]
) -> tuple[dict[str, float] | None, dict[str, str] | None]:
    values: dict[str, float] = {}
    sources: dict[str, str] = {}
    for sign in ("1", "X", "2"):
        value, source = _choose_odd(row, candidates[sign])
        if value is None or source is None:
            return None, None
        values[sign] = value
        sources[sign] = source
    return values, sources


def _parse_date(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d-%m-%y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _normalise_result(value: Any) -> str | None:
    text = _text(value).upper()
    if text in {"H", "1", "0", "0.0"}:
        return "1"
    if text in {"D", "X", "1.0"}:
        return "X"
    if text in {"A", "2", "2.0"}:
        return "2"
    return None


def _result_from_goals(home: float, away: float) -> str:
    if home > away:
        return "1"
    if home < away:
        return "2"
    return "X"


def _season_from_filename(path: Path) -> str:
    match = re.search(r"_(\d{2})(\d{2})$", path.stem)
    if not match:
        return path.stem
    return f"20{match.group(1)}-20{match.group(2)}"


def _division_from_path(path: Path) -> str:
    parent = path.parent.name.upper()
    if parent == "PRIMERA" or path.stem.upper().startswith("SP1_"):
        return "Primera"
    if parent == "SEGUNDA" or path.stem.upper().startswith("SP2_"):
        return "Segunda"
    return parent.title() or "Desconocida"


def _all_blank(row: dict[str, Any], columns: Iterable[str]) -> bool:
    return all(_is_blank(row.get(column)) for column in columns)


def _is_empty_row(row: dict[str, Any], columns: Iterable[str]) -> bool:
    return _all_blank(row, columns)


def _duplicate_metrics(values: list[tuple[Any, ...]]) -> dict[str, int]:
    counts = Counter(values)
    groups = [count for count in counts.values() if count > 1]
    return {
        "groups": len(groups),
        "rows_involved": sum(groups),
        "excess_rows": sum(count - 1 for count in groups),
    }


def _display_path(path: Path, display_root: Path | None) -> str:
    if display_root is not None:
        try:
            return path.resolve().relative_to(display_root.resolve()).as_posix()
        except ValueError:
            pass
    return path.as_posix()


def _inspect_history_csv(
    path: Path,
    *,
    overround_min: float,
    overround_max: float,
    display_root: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if overround_min >= overround_max:
        raise ValueError("overround_min debe ser menor que overround_max")

    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        rows = list(reader)

    division = _division_from_path(path)
    season = _season_from_filename(path)
    non_empty: list[tuple[int, dict[str, Any]]] = []
    empty_indexes: list[int] = []
    exact_values: list[tuple[Any, ...]] = []
    usable_count = 0
    primary_discard_reasons: Counter[str] = Counter()
    all_discard_reasons: Counter[str] = Counter()
    discarded_examples: list[dict[str, Any]] = []
    administrative_examples: list[dict[str, Any]] = []
    invalid_date_examples: list[dict[str, Any]] = []
    mismatch_examples: list[dict[str, Any]] = []
    match_keys: list[tuple[str, str, str]] = []
    team_rows: list[tuple[str, str]] = []
    comparable_results = 0
    result_mismatches = 0
    invalid_dates = 0
    administrative_rows = 0
    observed_match_rows = 0

    shot_schema = all(column in columns for column in SHOT_COLUMNS)
    shots_any = 0
    shots_complete = 0
    shots_missing_values = 0

    open_available = 0
    effective_close_available = 0
    real_close_available = 0
    equal_open_close = 0
    equal_without_real_close = 0
    equal_with_real_close = 0
    overround_values: list[float] = []
    overround_low = 0
    overround_high = 0
    overround_examples: list[dict[str, Any]] = []

    present_match_stats = [column for column in MATCH_STAT_COLUMNS if column in columns]
    all_known_odds_columns = sorted(
        {
            column
            for mapping in (OPEN_ODDS, REAL_CLOSE_ODDS, EFFECTIVE_CLOSE_ODDS)
            for choices in mapping.values()
            for column in choices
            if column in columns
        }
    )

    for csv_line, row in enumerate(rows, start=2):
        exact_values.append(tuple(_text(row.get(column)) for column in columns))
        if _is_empty_row(row, columns):
            empty_indexes.append(csv_line)
            continue
        non_empty.append((csv_line, row))

        date = _parse_date(row.get("Date"))
        home = _text(row.get("HomeTeam"))
        away = _text(row.get("AwayTeam"))
        home_goals = _to_float(row.get("FTHG"))
        away_goals = _to_float(row.get("FTAG"))
        result = _normalise_result(row.get("FTR"))
        opening, _ = _odds_triplet(row, OPEN_ODDS)
        effective_close, _ = _odds_triplet(row, EFFECTIVE_CLOSE_ODDS)
        real_close, _ = _odds_triplet(row, REAL_CLOSE_ODDS)

        if date is None:
            invalid_dates += 1
            if len(invalid_date_examples) < 10:
                invalid_date_examples.append({"line": csv_line, "value": _text(row.get("Date"))})
        if date is not None and home and away:
            key = (date.date().isoformat(), home, away)
            match_keys.append(key)
            team_rows.extend(((home, season), (away, season)))

        if home_goals is not None and away_goals is not None and result is not None:
            comparable_results += 1
            if _result_from_goals(home_goals, away_goals) != result:
                result_mismatches += 1
                if len(mismatch_examples) < 10:
                    mismatch_examples.append(
                        {
                            "line": csv_line,
                            "date": _text(row.get("Date")),
                            "home": home,
                            "away": away,
                            "goals": [home_goals, away_goals],
                            "result": result,
                        }
                    )

        if shot_schema:
            populated = sum(not _is_blank(row.get(column)) for column in SHOT_COLUMNS)
            shots_any += int(populated > 0)
            shots_complete += int(populated == len(SHOT_COLUMNS))
            shots_missing_values += len(SHOT_COLUMNS) - populated

        open_available += int(opening is not None)
        effective_close_available += int(effective_close is not None)
        real_close_available += int(real_close is not None)
        if opening is not None and effective_close is not None:
            equal = all(
                math.isclose(opening[sign], effective_close[sign], rel_tol=1e-12, abs_tol=1e-12)
                for sign in ("1", "X", "2")
            )
            if equal:
                equal_open_close += 1
                if real_close is None:
                    equal_without_real_close += 1
                else:
                    equal_with_real_close += 1
        if effective_close is not None:
            overround = sum(1.0 / effective_close[sign] for sign in ("1", "X", "2"))
            overround_values.append(overround)
            outside = overround < overround_min or overround > overround_max
            overround_low += int(overround < overround_min)
            overround_high += int(overround > overround_max)
            if outside and len(overround_examples) < 20:
                overround_examples.append(
                    {
                        "line": csv_line,
                        "date": _text(row.get("Date")),
                        "home": home,
                        "away": away,
                        "overround": round(overround, 6),
                    }
                )

        reasons: list[str] = []
        if date is None:
            reasons.append("INVALID_DATE")
        if not home or not away:
            reasons.append("MISSING_MATCH_IDENTITY")
        if home_goals is None or away_goals is None:
            reasons.append("MISSING_GOALS")
        if result is None:
            reasons.append("MISSING_OR_INVALID_RESULT")
        if opening is None or effective_close is None:
            reasons.append("MISSING_REQUIRED_ODDS")

        complete_match = date is not None and bool(home) and bool(away) and home_goals is not None and away_goals is not None and result is not None
        is_administrative = bool(
            complete_match
            and present_match_stats
            and _all_blank(row, present_match_stats)
            and _all_blank(row, all_known_odds_columns)
        )
        if complete_match:
            observed_match_rows += 1
        if is_administrative:
            administrative_rows += 1
            if len(administrative_examples) < 20:
                administrative_examples.append(
                    {"line": csv_line, "date": date.date().isoformat(), "home": home, "away": away}
                )

        if reasons:
            primary_discard_reasons[reasons[0]] += 1
            all_discard_reasons.update(reasons)
            if len(discarded_examples) < 20:
                discarded_examples.append(
                    {
                        "line": csv_line,
                        "date": _text(row.get("Date")),
                        "home": home,
                        "away": away,
                        "reasons": reasons,
                        "administrative_candidate": is_administrative,
                    }
                )
        else:
            usable_count += 1

    exact_duplicates = _duplicate_metrics(exact_values)
    key_duplicates = _duplicate_metrics(match_keys)
    non_empty_count = len(non_empty)
    expected = EXPECTED_MATCHES.get(division)
    season_coverage: dict[str, Any] = {
        "expected_regular_matches": expected,
        "observed_match_rows": observed_match_rows,
        "usable_rows": usable_count,
        "administrative_candidates": administrative_rows,
        "other_discarded_rows": non_empty_count - usable_count - administrative_rows,
    }
    if expected is not None:
        season_coverage.update(
            {
                "usable_gap": expected - usable_count,
                "observed_gap": expected - observed_match_rows,
                "gap_explained_by_administrative": min(
                    administrative_rows, max(0, expected - usable_count)
                ),
            }
        )

    overround_summary: dict[str, Any] = {
        "range": {"min_allowed": overround_min, "max_allowed": overround_max},
        "rows_evaluated": len(overround_values),
        "below_range": overround_low,
        "above_range": overround_high,
        "outside_range": overround_low + overround_high,
        "examples": overround_examples,
    }
    if overround_values:
        overround_summary["observed"] = {
            "minimum": round(min(overround_values), 6),
            "median": round(statistics.median(overround_values), 6),
            "maximum": round(max(overround_values), 6),
        }

    combined_primary_reasons = Counter(primary_discard_reasons)
    combined_primary_reasons["EMPTY_ROW"] += len(empty_indexes)
    combined_all_reasons = Counter(all_discard_reasons)
    combined_all_reasons["EMPTY_ROW"] += len(empty_indexes)
    public = {
        "path": _display_path(path, display_root),
        "division": division,
        "season": season,
        "columns": len(columns),
        "rows": {
            "raw": len(rows),
            "empty": len(empty_indexes),
            "non_empty": non_empty_count,
            "usable": usable_count,
            "discardable": len(rows) - usable_count,
            "discarded": len(rows) - usable_count,
            "discarded_non_empty": non_empty_count - usable_count,
            "discard_primary_reasons": dict(sorted(combined_primary_reasons.items())),
            "discard_all_reasons": dict(sorted(combined_all_reasons.items())),
            "empty_csv_lines": empty_indexes[:20],
            "discarded_examples": discarded_examples,
        },
        "duplicates": {"exact": exact_duplicates, "match_key": key_duplicates},
        "dates": {"invalid_non_empty": invalid_dates, "examples": invalid_date_examples},
        "results": {
            "comparable": comparable_results,
            "goal_result_mismatches": result_mismatches,
            "examples": mismatch_examples,
        },
        "shots": {
            "required_columns": list(SHOT_COLUMNS),
            "columns_present": [column for column in SHOT_COLUMNS if column in columns],
            "columns_missing": [column for column in SHOT_COLUMNS if column not in columns],
            "schema_complete": shot_schema,
            "rows_with_any_value": shots_any if shot_schema else 0,
            "rows_with_all_values": shots_complete if shot_schema else 0,
            "missing_value_cells": shots_missing_values if shot_schema else 0,
            "rows_without_schema": 0 if shot_schema else non_empty_count,
        },
        "odds": {
            "opening_schema_columns": [
                column for choices in OPEN_ODDS.values() for column in choices if column in columns
            ],
            "real_close_schema_columns": [
                column for choices in REAL_CLOSE_ODDS.values() for column in choices if column in columns
            ],
            "rows_opening_available": open_available,
            "rows_effective_close_available": effective_close_available,
            "rows_real_close_available": real_close_available,
            "rows_without_real_close": non_empty_count - real_close_available,
            "rows_open_equals_effective_close": equal_open_close,
            "equal_without_real_close": equal_without_real_close,
            "equal_with_real_close": equal_with_real_close,
            "overround": overround_summary,
        },
        "administrative_matches": {
            "candidate_rows": administrative_rows,
            "criterion": "Resultado completo, estadísticas de partido presentes en el esquema pero vacías y cuotas vacías.",
            "examples": administrative_examples,
        },
        "season_coverage": season_coverage,
    }
    internal = {
        "match_keys": match_keys,
        "team_rows": team_rows,
        "overround_values": overround_values,
        "overround_examples": overround_examples,
    }
    return public, internal


def audit_history_csv(
    path: str | Path,
    *,
    overround_min: float = 1.0,
    overround_max: float = 1.4,
) -> dict[str, Any]:
    """Inspecciona un CSV histórico sin modificarlo."""

    public, _ = _inspect_history_csv(
        Path(path), overround_min=overround_min, overround_max=overround_max
    )
    return public


def _normalise_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_name = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_name).strip()


def _is_obvious_reserve(name: str) -> bool:
    normalised = _normalise_name(name)
    return bool(re.search(r"(?:^| )(?:b|ii|u23|reserves?)$", normalised)) or "fortuna" in normalised


def _alias_similarity(left: str, right: str) -> tuple[bool, float, str]:
    left_norm = _normalise_name(left)
    right_norm = _normalise_name(right)
    ratio = SequenceMatcher(None, left_norm, right_norm).ratio()
    left_tokens = set(left_norm.split())
    right_tokens = set(right_norm.split())
    qualifiers = {
        "athletic",
        "atletico",
        "club",
        "cultural",
        "deportivo",
        "fc",
        "cf",
        "cd",
        "rc",
        "rcd",
        "real",
        "ud",
    }
    if left_tokens < right_tokens and right_tokens - left_tokens <= qualifiers:
        return True, ratio, "tokens_with_club_qualifier"
    if right_tokens < left_tokens and left_tokens - right_tokens <= qualifiers:
        return True, ratio, "tokens_with_club_qualifier"
    if ratio >= 0.88:
        return True, ratio, "high_string_similarity"
    return False, ratio, "below_candidate_threshold"


def _alias_candidates(team_seasons: dict[str, set[str]]) -> dict[str, Any]:
    teams = sorted(team_seasons)
    candidates: list[dict[str, Any]] = []
    reserve_pairs_excluded = 0
    overlapping_season_pairs_excluded = 0
    for index, left in enumerate(teams):
        for right in teams[index + 1 :]:
            if _is_obvious_reserve(left) or _is_obvious_reserve(right):
                reserve_pairs_excluded += 1
                continue
            candidate, ratio, method = _alias_similarity(left, right)
            if not candidate:
                continue
            common_seasons = team_seasons[left] & team_seasons[right]
            if common_seasons:
                overlapping_season_pairs_excluded += 1
                continue
            candidates.append(
                {
                    "names": [left, right],
                    "similarity": round(ratio, 4),
                    "method": method,
                    "seasons": {
                        left: sorted(team_seasons[left]),
                        right: sorted(team_seasons[right]),
                    },
                    "common_seasons": [],
                    "action": "human_review_only",
                }
            )
    return {
        "candidates": candidates,
        "obvious_reserve_pairs_excluded": reserve_pairs_excluded,
        "overlapping_season_pairs_excluded": overlapping_season_pairs_excluded,
        "policy": "No se unifica ningún nombre; se excluyen filiales obvios y pares que coexisten en una temporada.",
    }


def audit_historical(
    raw_base: str | Path = DEFAULT_RAW_BASE,
    *,
    overround_min: float = 1.0,
    overround_max: float = 1.4,
    display_root: str | Path | None = None,
) -> dict[str, Any]:
    """Audita todos los CSV encontrados bajo ``raw_base``."""

    base = Path(raw_base)
    root = Path(display_root) if display_root is not None else None
    paths = sorted(base.rglob("*.csv"))
    files: list[dict[str, Any]] = []
    all_keys: list[tuple[str, str, str]] = []
    team_seasons: dict[str, set[str]] = defaultdict(set)
    totals: Counter[str] = Counter()
    discard_reasons: Counter[str] = Counter()
    all_overround: list[float] = []
    overround_examples: list[dict[str, Any]] = []

    for path in paths:
        item, internal = _inspect_history_csv(
            path,
            overround_min=overround_min,
            overround_max=overround_max,
            display_root=root,
        )
        files.append(item)
        all_keys.extend(internal["match_keys"])
        for team, season in internal["team_rows"]:
            team_seasons[team].add(season)
        all_overround.extend(internal["overround_values"])
        for example in internal["overround_examples"]:
            if len(overround_examples) < 30:
                overround_examples.append({"path": item["path"], **example})

        rows = item["rows"]
        for key in ("raw", "empty", "non_empty", "usable", "discarded"):
            totals[key] += rows[key]
        discard_reasons.update(rows["discard_primary_reasons"])
        totals["invalid_dates"] += item["dates"]["invalid_non_empty"]
        totals["comparable_results"] += item["results"]["comparable"]
        totals["result_mismatches"] += item["results"]["goal_result_mismatches"]
        totals["exact_duplicate_groups"] += item["duplicates"]["exact"]["groups"]
        totals["exact_duplicate_rows"] += item["duplicates"]["exact"]["rows_involved"]
        totals["exact_duplicate_excess"] += item["duplicates"]["exact"]["excess_rows"]
        totals["shot_files_complete_schema"] += int(item["shots"]["schema_complete"])
        totals["shot_rows_without_schema"] += item["shots"]["rows_without_schema"]
        totals["shot_rows_with_any_value"] += item["shots"]["rows_with_any_value"]
        totals["shot_rows_with_all_values"] += item["shots"]["rows_with_all_values"]
        totals["shot_missing_value_cells"] += item["shots"]["missing_value_cells"]
        totals["opening_available"] += item["odds"]["rows_opening_available"]
        totals["effective_close_available"] += item["odds"]["rows_effective_close_available"]
        totals["real_close_available"] += item["odds"]["rows_real_close_available"]
        totals["without_real_close"] += item["odds"]["rows_without_real_close"]
        totals["equal_open_close"] += item["odds"]["rows_open_equals_effective_close"]
        totals["equal_without_real_close"] += item["odds"]["equal_without_real_close"]
        totals["equal_with_real_close"] += item["odds"]["equal_with_real_close"]
        totals["overround_low"] += item["odds"]["overround"]["below_range"]
        totals["overround_high"] += item["odds"]["overround"]["above_range"]
        totals["administrative"] += item["administrative_matches"]["candidate_rows"]

    global_key_duplicates = _duplicate_metrics(all_keys)
    key_counts = Counter(all_keys)
    key_examples = [
        {"date": key[0], "home": key[1], "away": key[2], "rows": count}
        for key, count in sorted(key_counts.items())
        if count > 1
    ][:20]
    aliases = _alias_candidates(team_seasons)

    season_issues = [
        {
            "path": item["path"],
            "division": item["division"],
            "season": item["season"],
            **item["season_coverage"],
        }
        for item in files
        if item["season_coverage"]["expected_regular_matches"] is not None
        and item["season_coverage"]["usable_rows"]
        != item["season_coverage"]["expected_regular_matches"]
    ]
    missing_shot_files = [item["path"] for item in files if not item["shots"]["schema_complete"]]
    real_close_missing_files = [
        item["path"] for item in files if item["odds"]["rows_without_real_close"] > 0
    ]

    findings: list[dict[str, Any]] = []
    if totals["empty"]:
        findings.append(
            _finding("EMPTY_ROWS", "info", "Filas completamente vacías en CSV históricos.", totals["empty"])
        )
    if totals["discarded"]:
        findings.append(
            _finding(
                "ROWS_DISCARDED",
                "warning",
                "Filas no utilizables por los requisitos actuales de identidad, marcador, fecha, resultado y cuotas.",
                totals["discarded"],
                primary_reasons=dict(sorted(discard_reasons.items())),
            )
        )
    if totals["exact_duplicate_rows"]:
        findings.append(
            _finding(
                "EXACT_DUPLICATE",
                "info",
                "Filas pertenecientes a grupos de duplicados exactos dentro de un archivo.",
                totals["exact_duplicate_rows"],
                groups=totals["exact_duplicate_groups"],
                excess_rows=totals["exact_duplicate_excess"],
            )
        )
    if global_key_duplicates["rows_involved"]:
        findings.append(
            _finding(
                "MATCH_KEY_DUPLICATE",
                "warning",
                "Partidos repetidos por (fecha, local, visitante).",
                global_key_duplicates["rows_involved"],
                **global_key_duplicates,
                examples=key_examples,
            )
        )
    if totals["result_mismatches"]:
        findings.append(
            _finding(
                "RESULT_GOALS_MISMATCH",
                "warning",
                "El signo de resultado contradice los goles.",
                totals["result_mismatches"],
            )
        )
    if totals["invalid_dates"]:
        findings.append(
            _finding(
                "DATE_INVALID",
                "warning",
                "Fechas no interpretables entre filas no vacías.",
                totals["invalid_dates"],
            )
        )
    if missing_shot_files:
        findings.append(
            _finding(
                "SHOTS_COLUMNS_MISSING",
                "critical",
                "Ausencia de columnas de tiros; no se confunde con celdas vacías.",
                totals["shot_rows_without_schema"],
                affected_files=missing_shot_files,
                file_count=len(missing_shot_files),
            )
        )
    rows_with_shot_schema = totals["non_empty"] - totals["shot_rows_without_schema"]
    missing_shot_rows = rows_with_shot_schema - totals["shot_rows_with_all_values"]
    if missing_shot_rows:
        findings.append(
            _finding(
                "SHOTS_VALUES_MISSING",
                "warning",
                "Hay columnas de tiros, pero faltan valores en algunas filas.",
                missing_shot_rows,
                missing_cells=totals["shot_missing_value_cells"],
            )
        )
    missing_open = totals["non_empty"] - totals["opening_available"]
    if missing_open:
        findings.append(
            _finding(
                "ODDS_OPEN_MISSING",
                "warning",
                "Filas sin tripleta utilizable de cuotas de apertura.",
                missing_open,
            )
        )
    if totals["without_real_close"]:
        findings.append(
            _finding(
                "ODDS_NO_REAL_CLOSE",
                "critical",
                "Filas sin tripleta de cierre real; el cierre efectivo puede ser un fallback a apertura.",
                totals["without_real_close"],
                affected_files=real_close_missing_files,
            )
        )
    if totals["equal_without_real_close"]:
        findings.append(
            _finding(
                "ODDS_OPEN_EQUALS_CLOSE_NO_REAL_CLOSE",
                "critical",
                "Apertura y cierre efectivo coinciden porque no existe una tripleta de cierre real.",
                totals["equal_without_real_close"],
            )
        )
    if totals["equal_with_real_close"]:
        findings.append(
            _finding(
                "ODDS_OPEN_EQUALS_CLOSE_REAL",
                "info",
                "Igualdades de apertura y cierre con una tripleta de cierre realmente disponible.",
                totals["equal_with_real_close"],
            )
        )
    overround_outside = totals["overround_low"] + totals["overround_high"]
    if overround_outside:
        findings.append(
            _finding(
                "ODDS_OVERROUND_OUT_OF_RANGE",
                "warning",
                "Overround fuera del rango configurado; se marca para revisión, no como error demostrado de la fuente.",
                overround_outside,
                below=totals["overround_low"],
                above=totals["overround_high"],
                range={"minimum": overround_min, "maximum": overround_max},
                examples=overround_examples,
            )
        )
    if season_issues:
        findings.append(
            _finding(
                "SEASON_INCOMPLETE",
                "warning",
                "Temporadas con filas utilizables distintas de 380/462; se separan administrativos y huecos observados.",
                len(season_issues),
                seasons=season_issues,
            )
        )
    if totals["administrative"]:
        findings.append(
            _finding(
                "ADMINISTRATIVE_MATCH_CANDIDATE",
                "warning",
                "Resultados completos sin estadísticas ni cuotas, separados de partidos ordinarios descartados.",
                totals["administrative"],
            )
        )
    if aliases["candidates"]:
        findings.append(
            _finding(
                "ALIAS_CANDIDATE",
                "info",
                "Nombres temporalmente disjuntos que requieren decisión humana; no se unifican automáticamente.",
                len(aliases["candidates"]),
                candidates=aliases["candidates"],
            )
        )

    overround_summary: dict[str, Any] = {
        "range": {"minimum": overround_min, "maximum": overround_max},
        "rows_evaluated": len(all_overround),
        "below": totals["overround_low"],
        "above": totals["overround_high"],
        "outside": overround_outside,
    }
    if all_overround:
        overround_summary["observed"] = {
            "minimum": round(min(all_overround), 6),
            "median": round(statistics.median(all_overround), 6),
            "maximum": round(max(all_overround), 6),
        }

    return {
        "source": _display_path(base, root),
        "file_count": len(files),
        "totals": {
            "rows": {
                "raw": totals["raw"],
                "empty": totals["empty"],
                "non_empty": totals["non_empty"],
                "usable": totals["usable"],
                "discarded": totals["discarded"],
                "discard_primary_reasons": dict(sorted(discard_reasons.items())),
            },
            "dates": {"invalid_non_empty": totals["invalid_dates"]},
            "results": {
                "comparable": totals["comparable_results"],
                "goal_result_mismatches": totals["result_mismatches"],
            },
            "duplicates": {
                "exact": {
                    "groups": totals["exact_duplicate_groups"],
                    "rows_involved": totals["exact_duplicate_rows"],
                    "excess_rows": totals["exact_duplicate_excess"],
                },
                "match_key": {**global_key_duplicates, "examples": key_examples},
            },
            "shots": {
                "files_with_complete_schema": totals["shot_files_complete_schema"],
                "files_without_complete_schema": len(files) - totals["shot_files_complete_schema"],
                "rows_without_schema": totals["shot_rows_without_schema"],
                "rows_with_any_value": totals["shot_rows_with_any_value"],
                "rows_with_all_values": totals["shot_rows_with_all_values"],
                "missing_value_cells_where_schema_exists": totals["shot_missing_value_cells"],
            },
            "odds": {
                "rows_opening_available": totals["opening_available"],
                "rows_effective_close_available": totals["effective_close_available"],
                "rows_real_close_available": totals["real_close_available"],
                "rows_without_real_close": totals["without_real_close"],
                "rows_open_equals_effective_close": totals["equal_open_close"],
                "equal_without_real_close": totals["equal_without_real_close"],
                "equal_with_real_close": totals["equal_with_real_close"],
                "overround": overround_summary,
            },
            "administrative_candidates": totals["administrative"],
        },
        "season_coverage": [
            {
                "path": item["path"],
                "division": item["division"],
                "season": item["season"],
                **item["season_coverage"],
            }
            for item in files
        ],
        "aliases": aliases,
        "files": files,
        "findings": findings,
    }


def _read_csv_bytes(path: Path) -> tuple[list[str], list[dict[str, str]], dict[str, Any]]:
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw.decode("utf-8-sig")
        valid_utf8 = True
        decode_error = None
    except UnicodeDecodeError as exc:
        text = raw.decode("utf-8-sig", errors="replace")
        valid_utf8 = False
        decode_error = {"start": exc.start, "end": exc.end, "reason": exc.reason}
    replacement_characters = text.count("\ufffd")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    rows = [dict(row) for row in reader]
    return list(reader.fieldnames or []), rows, {
        "valid_utf8": valid_utf8,
        "has_utf8_bom": has_bom,
        "replacement_characters": replacement_characters,
        "decode_error": decode_error,
    }


def _is_playoff(round_name: str) -> bool:
    text = _normalise_name(round_name).replace(" ", "-")
    return "play-off" in text or "playoff" in text or "promotion" in text


def _is_finished_status(status: str) -> bool:
    """Incluye finales en 90 minutos, prórroga y penaltis."""

    return status.casefold().startswith("finished")


def audit_highlightly(
    path: str | Path = DEFAULT_HIGHLIGHTLY,
    *,
    display_root: str | Path | None = None,
) -> dict[str, Any]:
    """Audita cobertura, estados, duplicados y codificación de Highlightly."""

    csv_path = Path(path)
    root = Path(display_root) if display_root is not None else None
    columns, rows, encoding = _read_csv_bytes(csv_path)
    exact_values = [tuple(_text(row.get(column)) for column in columns) for row in rows]
    match_ids = [(_text(row.get("match_id")),) for row in rows if _text(row.get("match_id"))]
    logical_keys = [
        (_text(row.get("date")), _text(row.get("home_name")), _text(row.get("away_name")))
        for row in rows
        if _text(row.get("date")) and _text(row.get("home_name")) and _text(row.get("away_name"))
    ]
    exact_duplicates = _duplicate_metrics(exact_values)
    id_duplicates = _duplicate_metrics(match_ids)
    logical_duplicates = _duplicate_metrics(logical_keys)
    logical_counts = Counter(logical_keys)
    logical_examples = [
        {"date": key[0], "home": key[1], "away": key[2], "rows": count}
        for key, count in sorted(logical_counts.items())
        if count > 1
    ][:20]

    statuses = Counter(_text(row.get("status")) or "<empty>" for row in rows)
    non_finished = sum(
        count for status, count in statuses.items() if not _is_finished_status(status)
    )
    rows_without_goals = [
        row
        for row in rows
        if _to_float(row.get("home_goals")) is None or _to_float(row.get("away_goals")) is None
    ]
    missing_goals_by_status = Counter(
        _text(row.get("status")) or "<empty>" for row in rows_without_goals
    )
    playoff_rows = [row for row in rows if _is_playoff(_text(row.get("round")))]
    playoff_by_group = Counter(
        (_text(row.get("league_name")), _text(row.get("league_season"))) for row in playoff_rows
    )
    valid_dates = [_parse_date(row.get("date")) for row in rows]
    valid_dates = [date for date in valid_dates if date is not None]

    coverage_groups: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for row in rows:
        key = (_text(row.get("league_name")), _text(row.get("league_season")))
        coverage_groups[key]["rows"] += 1
        finished = _is_finished_status(_text(row.get("status")))
        coverage_groups[key]["finished"] += int(finished)
        coverage_groups[key]["non_finished"] += int(not finished)
        coverage_groups[key]["playoffs"] += int(_is_playoff(_text(row.get("round"))))

    coverage: list[dict[str, Any]] = []
    incomplete_spanish: list[dict[str, Any]] = []
    for (league, season), counts in sorted(coverage_groups.items()):
        normalised_league = league.replace("División", "Division")
        expected = {"La Liga": 380, "Segunda Division": 462}.get(normalised_league)
        regular_finished = counts["finished"] - sum(
            1
            for row in rows
            if _text(row.get("league_name")) == league
            and _text(row.get("league_season")) == season
            and _is_finished_status(_text(row.get("status")))
            and _is_playoff(_text(row.get("round")))
        )
        item: dict[str, Any] = {
            "league": league,
            "season": season,
            "rows": counts["rows"],
            "finished": counts["finished"],
            "non_finished": counts["non_finished"],
            "playoffs": counts["playoffs"],
            "regular_finished": regular_finished,
            "expected_regular_matches": expected,
        }
        if expected is not None:
            item["regular_finished_gap"] = expected - regular_finished
            if regular_finished != expected:
                incomplete_spanish.append(dict(item))
        coverage.append(item)

    sign_comparable = 0
    sign_mismatches = 0
    sign_examples: list[dict[str, Any]] = []
    for row in rows:
        home_goals = _to_float(row.get("home_goals"))
        away_goals = _to_float(row.get("away_goals"))
        sign = _normalise_result(row.get("sign"))
        if home_goals is None or away_goals is None or sign is None:
            continue
        sign_comparable += 1
        if _result_from_goals(home_goals, away_goals) != sign:
            sign_mismatches += 1
            if len(sign_examples) < 10:
                sign_examples.append(
                    {
                        "match_id": _text(row.get("match_id")),
                        "home": _text(row.get("home_name")),
                        "away": _text(row.get("away_name")),
                    }
                )

    odds_columns = [
        column for column in columns if "odd" in column.casefold() or column.startswith(("B365", "Avg"))
    ]
    shot_columns = [column for column in SHOT_COLUMNS if column in columns]
    findings: list[dict[str, Any]] = []
    if not encoding["valid_utf8"]:
        findings.append(
            _finding(
                "HIGHLIGHTLY_UTF8_INVALID",
                "critical",
                "El CSV no decodifica como UTF-8 estricto.",
                1,
                decode_error=encoding["decode_error"],
            )
        )
    elif encoding["has_utf8_bom"]:
        findings.append(
            _finding(
                "HIGHLIGHTLY_UTF8_BOM_PRESENT",
                "info",
                "CSV UTF-8 válido con BOM; debe leerse como utf-8-sig para no contaminar la primera columna.",
                1,
            )
        )
    else:
        findings.append(
            _finding(
                "HIGHLIGHTLY_UTF8_BOM_MISSING",
                "info",
                "CSV UTF-8 válido sin BOM.",
                1,
            )
        )
    if encoding["replacement_characters"]:
        findings.append(
            _finding(
                "HIGHLIGHTLY_REPLACEMENT_CHARACTER",
                "warning",
                "Caracteres de reemplazo U+FFFD presentes en el contenido decodificado.",
                encoding["replacement_characters"],
            )
        )
    if non_finished:
        findings.append(
            _finding(
                "HIGHLIGHTLY_NON_FINISHED",
                "info",
                "Partidos no finalizados (Finished, Finished after extra time y Finished after penalties sí cuentan como finales).",
                non_finished,
                statuses=dict(sorted(statuses.items())),
            )
        )
    if rows_without_goals:
        findings.append(
            _finding(
                "HIGHLIGHTLY_GOALS_MISSING",
                "info",
                "Filas sin ambos goles disponibles, contabilizadas por estado.",
                len(rows_without_goals),
                statuses=dict(sorted(missing_goals_by_status.items())),
            )
        )
    if playoff_rows:
        findings.append(
            _finding(
                "HIGHLIGHTLY_PLAYOFF",
                "info",
                "Filas de play-off/promoción separadas de la liga regular.",
                len(playoff_rows),
                groups=[
                    {"league": key[0], "season": key[1], "rows": count}
                    for key, count in sorted(playoff_by_group.items())
                ],
            )
        )
    if exact_duplicates["rows_involved"]:
        findings.append(
            _finding(
                "HIGHLIGHTLY_EXACT_DUPLICATE",
                "warning",
                "Filas exactas duplicadas en Highlightly.",
                exact_duplicates["rows_involved"],
                **exact_duplicates,
            )
        )
    if id_duplicates["rows_involved"]:
        findings.append(
            _finding(
                "HIGHLIGHTLY_MATCH_ID_DUPLICATE",
                "warning",
                "Identificadores match_id repetidos.",
                id_duplicates["rows_involved"],
                **id_duplicates,
            )
        )
    if logical_duplicates["rows_involved"]:
        findings.append(
            _finding(
                "HIGHLIGHTLY_LOGICAL_DUPLICATE",
                "warning",
                "Duplicados excedentes por (fecha, local, visitante), aunque puedan tener match_id distinto.",
                logical_duplicates["excess_rows"],
                **logical_duplicates,
                examples=logical_examples,
            )
        )
    if incomplete_spanish:
        findings.append(
            _finding(
                "HIGHLIGHTLY_SEASON_INCOMPLETE",
                "warning",
                "Cobertura regular española distinta de 380/462 partidos finalizados.",
                len(incomplete_spanish),
                groups=incomplete_spanish,
            )
        )
    if sign_mismatches:
        findings.append(
            _finding(
                "HIGHLIGHTLY_SIGN_MISMATCH",
                "warning",
                "El signo derivado contradice los goles.",
                sign_mismatches,
                examples=sign_examples,
            )
        )

    return {
        "source": _display_path(csv_path, root),
        "rows": len(rows),
        "columns": columns,
        "encoding": encoding,
        "date_range": {
            "minimum": min(valid_dates).date().isoformat() if valid_dates else None,
            "maximum": max(valid_dates).date().isoformat() if valid_dates else None,
            "invalid": len(rows) - len(valid_dates),
        },
        "schema_capabilities": {
            "odds_columns": odds_columns,
            "shot_columns": shot_columns,
            "can_supply_motor_odds": bool(odds_columns),
            "can_supply_motor_shots": len(shot_columns) == len(SHOT_COLUMNS),
        },
        "statuses": {"counts": dict(sorted(statuses.items())), "non_finished": non_finished},
        "goals": {
            "rows_without_both_goals": len(rows_without_goals),
            "missing_by_status": dict(sorted(missing_goals_by_status.items())),
        },
        "playoffs": {
            "rows": len(playoff_rows),
            "groups": [
                {"league": key[0], "season": key[1], "rows": count}
                for key, count in sorted(playoff_by_group.items())
            ],
        },
        "duplicates": {
            "exact": exact_duplicates,
            "match_id": id_duplicates,
            "logical_match_key": {**logical_duplicates, "examples": logical_examples},
        },
        "sign_consistency": {
            "comparable": sign_comparable,
            "mismatches": sign_mismatches,
            "examples": sign_examples,
        },
        "coverage": coverage,
        "findings": findings,
    }


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def audit_priors(
    teams_path: str | Path = DEFAULT_TEAMS,
    priors_path: str | Path = DEFAULT_PRIORS,
    *,
    display_root: str | Path | None = None,
) -> dict[str, Any]:
    """Comprueba inventario, estados, confianza y parcialidad de los priors."""

    roster_path = Path(teams_path)
    stats_path = Path(priors_path)
    root = Path(display_root) if display_root is not None else None
    roster = _load_json(roster_path)
    priors = _load_json(stats_path)

    sections = ("laliga_ea_sports", "laliga_hypermotion")
    roster_items = [item for section in sections for item in roster.get(section, [])]
    roster_names = [_text(item.get("team")) for item in roster_items]
    roster_status = {_text(item.get("team")): _text(item.get("status")) for item in roster_items}
    prior_teams = priors.get("teams", {})
    prior_names = list(prior_teams)
    duplicate_roster_names = sorted(name for name, count in Counter(roster_names).items() if count > 1)
    only_roster = sorted(set(roster_names) - set(prior_names))
    only_priors = sorted(set(prior_names) - set(roster_names))

    status_mismatches: list[dict[str, str]] = []
    confidence_counts: Counter[str] = Counter()
    partial_teams: list[str] = []
    internal_mismatches: list[dict[str, Any]] = []
    adjusted_ppg_mismatches: list[dict[str, Any]] = []
    for team, stats in prior_teams.items():
        context = stats.get("context", {}) if isinstance(stats, dict) else {}
        confidence_counts[_text(context.get("confidence")) or "<missing>"] += 1
        expected_status = roster_status.get(team)
        actual_status = _text(context.get("status_2026_27"))
        if expected_status is not None and actual_status != expected_status:
            status_mismatches.append(
                {"team": team, "roster_status": expected_status, "prior_status": actual_status}
            )

        side_values: list[Any] = []
        for side in ("home", "away"):
            bucket = stats.get(side, {}) if isinstance(stats, dict) else {}
            if isinstance(bucket, dict):
                side_values.extend(bucket.values())
            else:
                side_values.append(None)
        if any(value is None for value in side_values):
            partial_teams.append(team)

        pj = _to_float(stats.get("pj"))
        wins = _to_float(stats.get("g"))
        draws = _to_float(stats.get("e"))
        losses = _to_float(stats.get("p"))
        gf = _to_float(stats.get("gf"))
        gc = _to_float(stats.get("gc"))
        points = _to_float(stats.get("pts"))
        dg = _to_float(stats.get("dg"))
        failed: list[str] = []
        if None not in (pj, wins, draws, losses) and not math.isclose(pj, wins + draws + losses):
            failed.append("pj != g + e + p")
        if None not in (points, wins, draws) and not math.isclose(points, 3 * wins + draws):
            failed.append("pts != 3*g + e")
        if None not in (dg, gf, gc) and not math.isclose(dg, gf - gc):
            failed.append("dg != gf - gc")
        if failed:
            internal_mismatches.append({"team": team, "rules": failed})

        raw_ppg = _to_float(context.get("raw_ppg"))
        factor = _to_float(context.get("transition_factor"))
        adjusted = _to_float(context.get("adjusted_ppg"))
        if raw_ppg is not None and factor is not None:
            expected_adjusted = round(raw_ppg * factor, 3)
            if adjusted is None or not math.isclose(adjusted, expected_adjusted, abs_tol=1e-9):
                adjusted_ppg_mismatches.append(
                    {
                        "team": team,
                        "raw_ppg": raw_ppg,
                        "factor": factor,
                        "expected": expected_adjusted,
                        "actual": adjusted,
                    }
                )

    listed_partial = sorted(set(priors.get("missing_or_partial", [])))
    strategy = priors.get("missing_data_strategy", {})
    strategy_teams = sorted(set(strategy.get("teams", []))) if isinstance(strategy, dict) else []
    actual_partial = sorted(set(partial_teams))
    partial_not_listed = sorted(set(actual_partial) - set(listed_partial))
    listed_but_complete = sorted(set(listed_partial) - set(actual_partial))
    strategy_missing_actual = sorted(set(actual_partial) - set(strategy_teams))
    strategy_extra = sorted(set(strategy_teams) - set(actual_partial))

    findings: list[dict[str, Any]] = []
    if roster.get("season") != priors.get("season_target"):
        findings.append(
            _finding(
                "PRIOR_SEASON_MISMATCH",
                "critical",
                "La temporada objetivo no coincide entre inventario y priors.",
                1,
                roster=roster.get("season"),
                priors=priors.get("season_target"),
            )
        )
    primera_count = len(roster.get("laliga_ea_sports", []))
    segunda_count = len(roster.get("laliga_hypermotion", []))
    if (
        len(roster_names) != 42
        or len(set(roster_names)) != 42
        or primera_count != 20
        or segunda_count != 22
    ):
        count_deviation = (
            abs(42 - len(set(roster_names)))
            + abs(20 - primera_count)
            + abs(22 - segunda_count)
            + len(duplicate_roster_names)
        )
        findings.append(
            _finding(
                "TEAMS_COUNT_INVALID",
                "critical",
                "El inventario no contiene 42 equipos únicos (20 de Primera y 22 de Segunda).",
                max(1, count_deviation),
                total=len(roster_names),
                unique=len(set(roster_names)),
                primera=len(roster.get("laliga_ea_sports", [])),
                segunda=len(roster.get("laliga_hypermotion", [])),
                duplicate_names=duplicate_roster_names,
            )
        )
    if only_roster or only_priors:
        findings.append(
            _finding(
                "PRIOR_TEAM_SET_MISMATCH",
                "critical",
                "Los equipos del inventario y de los priors no coinciden.",
                len(only_roster) + len(only_priors),
                only_roster=only_roster,
                only_priors=only_priors,
            )
        )
    if status_mismatches:
        findings.append(
            _finding(
                "PRIOR_STATUS_MISMATCH",
                "warning",
                "El estado 2026-27 no coincide entre inventario y prior.",
                len(status_mismatches),
                teams=status_mismatches,
            )
        )
    findings.append(
        _finding(
            "PRIOR_CONFIDENCE_LEVELS",
            "info",
            "Distribución declarada de niveles de confianza.",
            len(prior_names),
            levels=dict(sorted(confidence_counts.items())),
        )
    )
    if partial_not_listed or listed_but_complete:
        findings.append(
            _finding(
                "PRIOR_PARTIAL_NOT_LISTED",
                "critical",
                "missing_or_partial contradice la parcialidad real de los splits local/visitante.",
                len(partial_not_listed) + len(listed_but_complete),
                actual_partial=actual_partial,
                listed=listed_partial,
                partial_not_listed=partial_not_listed,
                listed_but_complete=listed_but_complete,
            )
        )
    if strategy_missing_actual or strategy_extra:
        findings.append(
            _finding(
                "PRIOR_STRATEGY_TEAM_MISMATCH",
                "warning",
                "La lista de missing_data_strategy no coincide con los equipos realmente parciales.",
                len(strategy_missing_actual) + len(strategy_extra),
                missing_from_strategy=strategy_missing_actual,
                extra_in_strategy=strategy_extra,
            )
        )
    if internal_mismatches:
        findings.append(
            _finding(
                "PRIOR_INTERNAL_INCONSISTENCY",
                "warning",
                "Totales PJ/G/E/P, puntos o diferencia de goles incoherentes.",
                len(internal_mismatches),
                teams=internal_mismatches,
            )
        )
    if adjusted_ppg_mismatches:
        findings.append(
            _finding(
                "PRIOR_ADJUSTED_PPG_MISMATCH",
                "warning",
                "adjusted_ppg no coincide con raw_ppg por el factor declarado.",
                len(adjusted_ppg_mismatches),
                teams=adjusted_ppg_mismatches,
            )
        )

    return {
        "sources": {
            "teams": _display_path(roster_path, root),
            "priors": _display_path(stats_path, root),
        },
        "seasons": {
            "roster": roster.get("season"),
            "priors": priors.get("season_target"),
            "match": roster.get("season") == priors.get("season_target"),
        },
        "teams": {
            "expected": 42,
            "roster_total": len(roster_names),
            "roster_unique": len(set(roster_names)),
            "primera": len(roster.get("laliga_ea_sports", [])),
            "segunda": len(roster.get("laliga_hypermotion", [])),
            "priors": len(prior_names),
            "duplicate_roster_names": duplicate_roster_names,
            "only_roster": only_roster,
            "only_priors": only_priors,
            "status_mismatches": status_mismatches,
        },
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "partiality": {
            "actual_partial_splits": actual_partial,
            "missing_or_partial": listed_partial,
            "strategy_teams": strategy_teams,
            "partial_not_listed": partial_not_listed,
            "listed_but_complete": listed_but_complete,
            "strategy_missing_actual": strategy_missing_actual,
            "strategy_extra": strategy_extra,
        },
        "coherence": {
            "internal_mismatches": internal_mismatches,
            "adjusted_ppg_mismatches": adjusted_ppg_mismatches,
        },
        "findings": findings,
    }


def audit_datasets(
    project_root: str | Path = PROJECT_ROOT,
    *,
    overround_min: float = 1.0,
    overround_max: float = 1.4,
) -> dict[str, Any]:
    """Ejecuta la auditoría completa de las tres familias de datos requeridas."""

    root = Path(project_root)
    historical = audit_historical(
        root / "DATOS" / "historico_raw",
        overround_min=overround_min,
        overround_max=overround_max,
        display_root=root,
    )
    highlightly = audit_highlightly(
        root / "DATOS" / "highlightly_dataset" / "highlightly_partidos_2023_2026.csv",
        display_root=root,
    )
    priors = audit_priors(
        root / "DATOS" / "temporada_2026_27_equipos.json",
        root / "DATOS" / "temporada_2026_27_estadisticas_base.json",
        display_root=root,
    )
    findings = historical["findings"] + highlightly["findings"] + priors["findings"]
    severity_counts = Counter(item["severity"] for item in findings)
    return {
        "schema_version": 1,
        "read_only": True,
        "configuration": {
            "overround_min": overround_min,
            "overround_max": overround_max,
            "expected_regular_matches": EXPECTED_MATCHES,
        },
        "severity_policy": SEVERITY_RATIONALE,
        "summary": {
            "finding_count": len(findings),
            "findings_by_severity": {
                severity: severity_counts.get(severity, 0)
                for severity in ("info", "warning", "critical")
            },
        },
        "historical": historical,
        "highlightly": highlightly,
        "priors": priors,
        "findings": findings,
    }


def format_summary(report: dict[str, Any]) -> str:
    """Genera un resumen humano; la evidencia completa permanece en el diccionario."""

    historical = report["historical"]
    h_rows = historical["totals"]["rows"]
    highlightly = report["highlightly"]
    priors = report["priors"]
    severities = report["summary"]["findings_by_severity"]
    lines = [
        "CONTROL DE CALIDAD DE DATASETS (solo lectura)",
        (
            f"Histórico: {historical['file_count']} CSV · {h_rows['raw']} brutas · "
            f"{h_rows['empty']} vacías · {h_rows['usable']} utilizables · "
            f"{h_rows['discarded']} descartables"
        ),
        (
            f"Highlightly: {highlightly['rows']} filas · UTF-8="
            f"{'sí' if highlightly['encoding']['valid_utf8'] else 'no'} · "
            f"BOM={'sí' if highlightly['encoding']['has_utf8_bom'] else 'no'} · "
            f"no finalizados={highlightly['statuses']['non_finished']} · "
            f"play-offs={highlightly['playoffs']['rows']}"
        ),
        (
            f"Priors: inventario={priors['teams']['roster_unique']}/42 · "
            f"priors={priors['teams']['priors']} · "
            f"parciales reales={len(priors['partiality']['actual_partial_splits'])}"
        ),
        (
            "Hallazgos: "
            f"info={severities['info']} · warning={severities['warning']} · "
            f"critical={severities['critical']}"
        ),
        "",
    ]
    for item in report["findings"]:
        lines.append(
            f"[{item['severity'].upper():8}] {item['code']}: {item['count']} · {item['message']}"
        )
    return "\n".join(lines)


__all__ = [
    "audit_datasets",
    "audit_highlightly",
    "audit_historical",
    "audit_history_csv",
    "audit_priors",
    "format_summary",
]
