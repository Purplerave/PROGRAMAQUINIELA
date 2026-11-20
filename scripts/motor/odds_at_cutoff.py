"""Selección única de las cuotas que existían al corte de una jornada."""
from __future__ import annotations

import math
from datetime import date, datetime

from scripts.motor.features import validate_odds_timestamps
from scripts.motor.temporal import utc_timestamp


def kickoff_at(match: dict) -> str | None:
    explicit = match.get("kickoff_at") or match.get("fecha_hora")
    if explicit:
        return explicit
    day = match.get("fecha")
    if isinstance(day, str) and len(day) == 10 and match.get("hora"):
        return f"{day}T{match['hora']}"
    return day


def _date_without_time(value: object) -> bool:
    if isinstance(value, str):
        try:
            date.fromisoformat(value)
        except ValueError:
            return False
        return True
    return isinstance(value, date) and not isinstance(value, datetime)


ODDS_GROUPS = (("odd_1", "odd_x", "odd_2"), ("open_odd_1", "open_odd_x", "open_odd_2"))


def odds_at_cutoff(match: dict, cutoff_date: object) -> tuple[dict[str, float], dict]:
    """Devuelve cuotas utilizables y evidencia de la misma decisión."""
    observed = match.get("odds_observed_at")
    kickoff = kickoff_at(match)
    entry = {
        "num": match.get("num"),
        "odds_observed_at": observed,
        "prediction_cutoff_at": utc_timestamp(cutoff_date).isoformat(),
        "kickoff_at": kickoff,
        "usadas_en_motor_1x2": False,
    }
    if not observed or not kickoff:
        entry.update(estado="no_auditado", motivo="odds_observed_at_ausente" if not observed else "kickoff_at_ausente")
        return {}, entry
    if _date_without_time(observed):
        entry.update(estado="no_auditado", motivo="odds_observed_at_sin_hora")
        return {}, entry
    report = validate_odds_timestamps([entry])
    if not report["ok"]:
        entry.update(estado="violacion", issues=report["violaciones"][0]["issues"])
        return {}, entry

    odds = {}
    for group in ODDS_GROUPS:
        try:
            values = [float(match[k]) for k in group]
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
        if all(math.isfinite(v) and v > 1.01 for v in values):
            odds.update(zip(group, values, strict=False))
    # Igual que el histórico: la apertura completa hace de mercado si no
    # existe una tripleta principal. La traza conserva cuál fue la fuente.
    market_source = "principal" if "odd_1" in odds else None
    if not market_source and "open_odd_1" in odds:
        odds.update((key.removeprefix("open_"), odds[key]) for key in ODDS_GROUPS[1])
        market_source = "apertura_fallback"
    entry.update(estado="auditable", fuente_tripleta=market_source,
                 usadas_en_motor_1x2=bool(odds) and match.get("num") != 15)
    return odds, entry
