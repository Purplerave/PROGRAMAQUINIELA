"""Agregación y hallazgos para los CSV históricos."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .common import duplicate_metrics, finding, observed_distribution


def new_aggregate() -> dict[str, Any]:
    return {
        "totals": Counter(), "discard_reasons": Counter(), "keys": [], "overround": [],
        "overround_examples": [], "team_rows": [],
    }


def accumulate(aggregate: dict[str, Any], item: dict[str, Any], internal: dict[str, Any]) -> None:
    totals = aggregate["totals"]
    rows = item["rows"]
    for key in ("raw", "empty", "non_empty", "usable", "discarded"):
        totals[key] += rows[key]
    aggregate["discard_reasons"].update(rows["discard_primary_reasons"])
    aggregate["keys"].extend(internal["match_keys"])
    aggregate["team_rows"].extend(internal["team_rows"])
    aggregate["overround"].extend(internal["overround_values"])
    for example in internal["overround_examples"]:
        if len(aggregate["overround_examples"]) < 30:
            aggregate["overround_examples"].append({"path": item["path"], **example})

    totals["invalid_dates"] += item["dates"]["invalid_non_empty"]
    totals["comparable_results"] += item["results"]["comparable"]
    totals["result_mismatches"] += item["results"]["goal_result_mismatches"]
    for suffix, metric in (("groups", "groups"), ("rows", "rows_involved"), ("excess", "excess_rows")):
        totals[f"exact_duplicate_{suffix}"] += item["duplicates"]["exact"][metric]
    totals["shot_files_complete_schema"] += int(item["shots"]["schema_complete"])
    totals["shot_rows_without_schema"] += item["shots"]["rows_without_schema"]
    totals["shot_rows_with_any_value"] += item["shots"]["rows_with_any_value"]
    totals["shot_rows_with_all_values"] += item["shots"]["rows_with_all_values"]
    totals["shot_missing_value_cells"] += item["shots"]["missing_value_cells"]
    for target, source in (
        ("opening_available", "rows_opening_available"),
        ("effective_close_available", "rows_effective_close_available"),
        ("real_close_available", "rows_real_close_available"),
        ("without_real_close", "rows_without_real_close"),
        ("equal_open_close", "rows_open_equals_effective_close"),
        ("equal_without_real_close", "equal_without_real_close"),
        ("equal_with_real_close", "equal_with_real_close"),
    ):
        totals[target] += item["odds"][source]
    totals["overround_low"] += item["odds"]["overround"]["below_range"]
    totals["overround_high"] += item["odds"]["overround"]["above_range"]
    totals["administrative"] += item["administrative_matches"]["candidate_rows"]


def match_key_summary(keys: list[tuple[str, str, str]]) -> dict[str, Any]:
    metrics = duplicate_metrics(keys)
    counts = Counter(keys)
    examples = [
        {"date": key[0], "home": key[1], "away": key[2], "rows": count}
        for key, count in sorted(counts.items()) if count > 1
    ][:20]
    return {**metrics, "examples": examples}


def season_coverage(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{
        "path": item["path"], "division": item["division"], "season": item["season"],
        **item["season_coverage"],
    } for item in files]


def _row_findings(totals: Counter, reasons: Counter, key_summary: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    if totals["empty"]:
        result.append(finding("EMPTY_ROWS", "info", "Filas completamente vacías en CSV históricos.", totals["empty"]))
    if totals["discarded"]:
        result.append(finding(
            "ROWS_DISCARDED", "warning",
            "Filas no utilizables por los requisitos actuales de identidad, marcador, fecha, resultado y cuotas.",
            totals["discarded"], primary_reasons=dict(sorted(reasons.items())),
        ))
    if totals["exact_duplicate_rows"]:
        result.append(finding(
            "EXACT_DUPLICATE", "info",
            "Filas pertenecientes a grupos de duplicados exactos dentro de un archivo.",
            totals["exact_duplicate_rows"], groups=totals["exact_duplicate_groups"],
            excess_rows=totals["exact_duplicate_excess"],
        ))
    if key_summary["rows_involved"]:
        result.append(finding(
            "MATCH_KEY_DUPLICATE", "warning", "Partidos repetidos por (fecha, local, visitante).",
            key_summary["rows_involved"], **key_summary,
        ))
    if totals["result_mismatches"]:
        result.append(finding(
            "RESULT_GOALS_MISMATCH", "warning", "El signo de resultado contradice los goles.",
            totals["result_mismatches"],
        ))
    if totals["invalid_dates"]:
        result.append(finding(
            "DATE_INVALID", "warning", "Fechas no interpretables entre filas no vacías.",
            totals["invalid_dates"],
        ))
    return result


def _shot_findings(totals: Counter, files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    missing_files = [item["path"] for item in files if not item["shots"]["schema_complete"]]
    if missing_files:
        result.append(finding(
            "SHOTS_COLUMNS_MISSING", "critical",
            "Ausencia de columnas de tiros; no se confunde con celdas vacías.",
            totals["shot_rows_without_schema"], affected_files=missing_files, file_count=len(missing_files),
        ))
    rows_with_schema = totals["non_empty"] - totals["shot_rows_without_schema"]
    missing_rows = rows_with_schema - totals["shot_rows_with_all_values"]
    if missing_rows:
        result.append(finding(
            "SHOTS_VALUES_MISSING", "warning",
            "Hay columnas de tiros, pero faltan valores en algunas filas.",
            missing_rows, missing_cells=totals["shot_missing_value_cells"],
        ))
    return result


def _odds_findings(
    totals: Counter, files: list[dict[str, Any]], aggregate: dict[str, Any], minimum: float, maximum: float,
) -> list[dict[str, Any]]:
    result = []
    missing_open = totals["non_empty"] - totals["opening_available"]
    if missing_open:
        result.append(finding(
            "ODDS_OPEN_MISSING", "warning", "Filas sin tripleta utilizable de cuotas de apertura.", missing_open,
        ))
    if totals["without_real_close"]:
        affected = [item["path"] for item in files if item["odds"]["rows_without_real_close"] > 0]
        result.append(finding(
            "ODDS_NO_REAL_CLOSE", "critical",
            "Filas sin tripleta de cierre real; el cierre efectivo puede ser un fallback a apertura.",
            totals["without_real_close"], affected_files=affected,
            equal_to_opening_via_fallback=totals["equal_without_real_close"],
        ))
    # Es evidencia del hallazgo anterior, no un segundo critical independiente.
    if totals["equal_without_real_close"]:
        result.append(finding(
            "ODDS_OPEN_EQUALS_CLOSE_NO_REAL_CLOSE", "info",
            "Igualdades de apertura y cierre efectivo explicadas por ausencia de cierre real.",
            totals["equal_without_real_close"], parent_code="ODDS_NO_REAL_CLOSE",
        ))
    if totals["equal_with_real_close"]:
        result.append(finding(
            "ODDS_OPEN_EQUALS_CLOSE_REAL", "info",
            "Igualdades de apertura y cierre con una tripleta de cierre realmente disponible.",
            totals["equal_with_real_close"],
        ))
    outside = totals["overround_low"] + totals["overround_high"]
    if outside:
        result.append(finding(
            "ODDS_OVERROUND_OUT_OF_RANGE", "warning",
            "Overround fuera del rango configurado; se marca para revisión, no como error demostrado de la fuente.",
            outside, below=totals["overround_low"], above=totals["overround_high"],
            range={"minimum": minimum, "maximum": maximum}, examples=aggregate["overround_examples"],
        ))
    return result


def _coverage_findings(
    totals: Counter, coverage: list[dict[str, Any]], aliases: dict[str, Any],
) -> list[dict[str, Any]]:
    result = []
    issues = [item for item in coverage if item["expected_regular_matches"] is not None
              and item["usable_rows"] != item["expected_regular_matches"]]
    if issues:
        result.append(finding(
            "SEASON_INCOMPLETE", "warning",
            "Temporadas con filas utilizables distintas de 380/462; se separan administrativos y huecos observados.",
            len(issues), seasons=issues,
        ))
    if totals["administrative"]:
        result.append(finding(
            "ADMINISTRATIVE_MATCH_CANDIDATE", "warning",
            "Resultados completos sin estadísticas ni cuotas, separados de partidos ordinarios descartados.",
            totals["administrative"],
        ))
    if aliases["candidates"]:
        result.append(finding(
            "ALIAS_CANDIDATE", "info",
            "Nombres temporalmente disjuntos que requieren decisión humana; no se unifican automáticamente.",
            len(aliases["candidates"]), candidates=aliases["candidates"],
        ))
    return result


def build_findings(
    aggregate: dict[str, Any], files: list[dict[str, Any]], key_summary: dict[str, Any],
    coverage: list[dict[str, Any]], aliases: dict[str, Any], minimum: float, maximum: float,
) -> list[dict[str, Any]]:
    totals = aggregate["totals"]
    return (
        _row_findings(totals, aggregate["discard_reasons"], key_summary)
        + _shot_findings(totals, files)
        + _odds_findings(totals, files, aggregate, minimum, maximum)
        + _coverage_findings(totals, coverage, aliases)
    )


def totals_payload(
    aggregate: dict[str, Any], file_count: int, key_summary: dict[str, Any], minimum: float, maximum: float,
) -> dict[str, Any]:
    totals = aggregate["totals"]
    overround = {
        "range": {"minimum": minimum, "maximum": maximum},
        "rows_evaluated": len(aggregate["overround"]), "below": totals["overround_low"],
        "above": totals["overround_high"], "outside": totals["overround_low"] + totals["overround_high"],
    }
    if aggregate["overround"]:
        overround["observed"] = observed_distribution(aggregate["overround"])
    return {
        "rows": {key: totals[key] for key in ("raw", "empty", "non_empty", "usable", "discarded")}
        | {"discard_primary_reasons": dict(sorted(aggregate["discard_reasons"].items()))},
        "dates": {"invalid_non_empty": totals["invalid_dates"]},
        "results": {"comparable": totals["comparable_results"],
                    "goal_result_mismatches": totals["result_mismatches"]},
        "duplicates": {
            "exact": {"groups": totals["exact_duplicate_groups"], "rows_involved": totals["exact_duplicate_rows"],
                      "excess_rows": totals["exact_duplicate_excess"]},
            "match_key": key_summary,
        },
        "shots": {
            "files_with_complete_schema": totals["shot_files_complete_schema"],
            "files_without_complete_schema": file_count - totals["shot_files_complete_schema"],
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
            "equal_with_real_close": totals["equal_with_real_close"], "overround": overround,
        },
        "administrative_candidates": totals["administrative"],
    }
