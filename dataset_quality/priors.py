"""Coherencia del inventario 2026/27 y sus priors."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from .common import PROJECT_ROOT, display_path, finding, text, to_float


DEFAULT_TEAMS = PROJECT_ROOT / "DATOS" / "temporada_2026_27_equipos.json"
DEFAULT_PRIORS = PROJECT_ROOT / "DATOS" / "temporada_2026_27_estadisticas_base.json"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _roster(roster: dict[str, Any]) -> dict[str, Any]:
    sections = ("laliga_ea_sports", "laliga_hypermotion")
    items = [item for section in sections for item in roster.get(section, [])]
    names = [text(item.get("team")) for item in items]
    return {
        "names": names,
        "statuses": {text(item.get("team")): text(item.get("status")) for item in items},
        "primera": len(roster.get("laliga_ea_sports", [])),
        "segunda": len(roster.get("laliga_hypermotion", [])),
        "duplicates": sorted(name for name, count in Counter(names).items() if count > 1),
    }


def _side_is_partial(stats: dict[str, Any]) -> bool:
    values = []
    for side in ("home", "away"):
        bucket = stats.get(side, {}) if isinstance(stats, dict) else {}
        values.extend(bucket.values() if isinstance(bucket, dict) else [None])
    return any(value is None for value in values)


def _internal_rules(stats: dict[str, Any]) -> list[str]:
    pj, wins, draws, losses = (to_float(stats.get(key)) for key in ("pj", "g", "e", "p"))
    gf, gc, points, dg = (to_float(stats.get(key)) for key in ("gf", "gc", "pts", "dg"))
    failed = []
    if None not in (pj, wins, draws, losses) and not math.isclose(pj, wins + draws + losses):
        failed.append("pj != g + e + p")
    if None not in (points, wins, draws) and not math.isclose(points, 3 * wins + draws):
        failed.append("pts != 3*g + e")
    if None not in (dg, gf, gc) and not math.isclose(dg, gf - gc):
        failed.append("dg != gf - gc")
    return failed


def _adjusted_ppg_mismatch(team: str, context: dict[str, Any]) -> dict[str, Any] | None:
    raw = to_float(context.get("raw_ppg"))
    factor = to_float(context.get("transition_factor"))
    adjusted = to_float(context.get("adjusted_ppg"))
    if raw is None or factor is None:
        return None
    expected = round(raw * factor, 3)
    if adjusted is not None and math.isclose(adjusted, expected, abs_tol=1e-9):
        return None
    return {"team": team, "raw_ppg": raw, "factor": factor, "expected": expected, "actual": adjusted}


def _inspect_teams(prior_teams: dict[str, Any], roster_statuses: dict[str, str]) -> dict[str, Any]:
    status_mismatches, partial, internal, adjusted = [], [], [], []
    confidences: Counter[str] = Counter()
    for team, stats in prior_teams.items():
        context = stats.get("context", {}) if isinstance(stats, dict) else {}
        confidences[text(context.get("confidence")) or "<missing>"] += 1
        expected_status = roster_statuses.get(team)
        actual_status = text(context.get("status_2026_27"))
        if expected_status is not None and actual_status != expected_status:
            status_mismatches.append({
                "team": team, "roster_status": expected_status, "prior_status": actual_status,
            })
        if _side_is_partial(stats):
            partial.append(team)
        failed = _internal_rules(stats)
        if failed:
            internal.append({"team": team, "rules": failed})
        ppg_mismatch = _adjusted_ppg_mismatch(team, context)
        if ppg_mismatch:
            adjusted.append(ppg_mismatch)
    return {
        "status_mismatches": status_mismatches, "partial": sorted(set(partial)),
        "internal": internal, "adjusted": adjusted, "confidences": dict(sorted(confidences.items())),
    }


def _partiality(priors: dict[str, Any], actual: list[str]) -> dict[str, Any]:
    listed = sorted(set(priors.get("missing_or_partial", [])))
    strategy = priors.get("missing_data_strategy", {})
    strategy_teams = sorted(set(strategy.get("teams", []))) if isinstance(strategy, dict) else []
    return {
        "actual_partial_splits": actual, "missing_or_partial": listed, "strategy_teams": strategy_teams,
        "partial_not_listed": sorted(set(actual) - set(listed)),
        "listed_but_complete": sorted(set(listed) - set(actual)),
        "strategy_missing_actual": sorted(set(actual) - set(strategy_teams)),
        "strategy_extra": sorted(set(strategy_teams) - set(actual)),
    }


def _inventory_findings(
    roster: dict[str, Any], priors: dict[str, Any], inventory: dict[str, Any],
    only_roster: list[str], only_priors: list[str],
) -> list[dict[str, Any]]:
    result = []
    if roster.get("season") != priors.get("season_target"):
        result.append(finding(
            "PRIOR_SEASON_MISMATCH", "critical",
            "La temporada objetivo no coincide entre inventario y priors.", 1,
            roster=roster.get("season"), priors=priors.get("season_target"),
        ))
    names = inventory["names"]
    if (len(names) != 42 or len(set(names)) != 42
            or inventory["primera"] != 20 or inventory["segunda"] != 22):
        deviation = (
            abs(42 - len(set(names))) + abs(20 - inventory["primera"])
            + abs(22 - inventory["segunda"]) + len(inventory["duplicates"])
        )
        result.append(finding(
            "TEAMS_COUNT_INVALID", "critical",
            "El inventario no contiene 42 equipos únicos (20 de Primera y 22 de Segunda).",
            max(1, deviation), total=len(names), unique=len(set(names)),
            primera=inventory["primera"], segunda=inventory["segunda"],
            duplicate_names=inventory["duplicates"],
        ))
    if only_roster or only_priors:
        result.append(finding(
            "PRIOR_TEAM_SET_MISMATCH", "critical",
            "Los equipos del inventario y de los priors no coinciden.",
            len(only_roster) + len(only_priors), only_roster=only_roster, only_priors=only_priors,
        ))
    return result


def _quality_findings(
    inspected: dict[str, Any], partiality: dict[str, Any], prior_count: int,
) -> list[dict[str, Any]]:
    result = []
    if inspected["status_mismatches"]:
        result.append(finding(
            "PRIOR_STATUS_MISMATCH", "warning",
            "El estado 2026-27 no coincide entre inventario y prior.",
            len(inspected["status_mismatches"]), teams=inspected["status_mismatches"],
        ))
    result.append(finding(
        "PRIOR_CONFIDENCE_LEVELS", "info", "Distribución declarada de niveles de confianza.",
        prior_count, levels=inspected["confidences"],
    ))
    partial_conflict = partiality["partial_not_listed"] or partiality["listed_but_complete"]
    if partial_conflict:
        result.append(finding(
            "PRIOR_PARTIAL_NOT_LISTED", "critical",
            "missing_or_partial contradice la parcialidad real de los splits local/visitante.",
            len(partiality["partial_not_listed"]) + len(partiality["listed_but_complete"]),
            actual_partial=partiality["actual_partial_splits"], listed=partiality["missing_or_partial"],
            partial_not_listed=partiality["partial_not_listed"],
            listed_but_complete=partiality["listed_but_complete"],
        ))
    strategy_conflict = partiality["strategy_missing_actual"] or partiality["strategy_extra"]
    if strategy_conflict:
        result.append(finding(
            "PRIOR_STRATEGY_TEAM_MISMATCH", "warning",
            "La lista de missing_data_strategy no coincide con los equipos realmente parciales.",
            len(partiality["strategy_missing_actual"]) + len(partiality["strategy_extra"]),
            missing_from_strategy=partiality["strategy_missing_actual"],
            extra_in_strategy=partiality["strategy_extra"],
        ))
    if inspected["internal"]:
        result.append(finding(
            "PRIOR_INTERNAL_INCONSISTENCY", "warning",
            "Totales PJ/G/E/P, puntos o diferencia de goles incoherentes.",
            len(inspected["internal"]), teams=inspected["internal"],
        ))
    if inspected["adjusted"]:
        result.append(finding(
            "PRIOR_ADJUSTED_PPG_MISMATCH", "warning",
            "adjusted_ppg no coincide con raw_ppg por el factor declarado.",
            len(inspected["adjusted"]), teams=inspected["adjusted"],
        ))
    return result


def audit_priors(
    teams_path: str | Path = DEFAULT_TEAMS, priors_path: str | Path = DEFAULT_PRIORS,
    *, display_root: str | Path | None = None,
) -> dict[str, Any]:
    """Comprueba inventario, estados, confianza y parcialidad de los priors."""

    roster_path, stats_path = Path(teams_path), Path(priors_path)
    root = Path(display_root) if display_root is not None else None
    roster, priors = _load(roster_path), _load(stats_path)
    inventory = _roster(roster)
    prior_teams = priors.get("teams", {})
    prior_names = list(prior_teams)
    only_roster = sorted(set(inventory["names"]) - set(prior_names))
    only_priors = sorted(set(prior_names) - set(inventory["names"]))
    inspected = _inspect_teams(prior_teams, inventory["statuses"])
    partiality = _partiality(priors, inspected["partial"])
    findings = _inventory_findings(
        roster, priors, inventory, only_roster, only_priors
    ) + _quality_findings(inspected, partiality, len(prior_names))
    return {
        "sources": {"teams": display_path(roster_path, root), "priors": display_path(stats_path, root)},
        "seasons": {"roster": roster.get("season"), "priors": priors.get("season_target"),
                    "match": roster.get("season") == priors.get("season_target")},
        "teams": {
            "expected": 42, "roster_total": len(inventory["names"]),
            "roster_unique": len(set(inventory["names"])), "primera": inventory["primera"],
            "segunda": inventory["segunda"], "priors": len(prior_names),
            "duplicate_roster_names": inventory["duplicates"], "only_roster": only_roster,
            "only_priors": only_priors, "status_mismatches": inspected["status_mismatches"],
        },
        "confidence_counts": inspected["confidences"], "partiality": partiality,
        "coherence": {"internal_mismatches": inspected["internal"],
                      "adjusted_ppg_mismatches": inspected["adjusted"]},
        "findings": findings,
    }
