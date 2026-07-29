"""Constantes y utilidades compartidas por los auditores."""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHOT_COLUMNS = ("HS", "AS", "HST", "AST")
MATCH_STAT_COLUMNS = (
    "HS", "AS", "HST", "AST", "HF", "AF", "HC", "AC", "HY", "AY", "HR", "AR"
)
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
# Reproduce el orden actual del motor, incluido el fallback a apertura.
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


def finding(code: str, severity: str, message: str, count: int, **details: Any) -> dict[str, Any]:
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


def text(value: Any) -> str:
    if value is None or isinstance(value, list):
        return ""
    return str(value).strip()


def is_blank(value: Any) -> bool:
    return text(value) == ""


def to_float(value: Any) -> float | None:
    raw = text(value).replace(",", ".")
    if not raw:
        return None
    try:
        number = float(raw)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def choose_odd(row: dict[str, Any], candidates: Iterable[str]) -> tuple[float | None, str | None]:
    for column in candidates:
        value = to_float(row.get(column))
        if value is not None and value > 1.01:
            return value, column
    return None, None


def odds_triplet(
    row: dict[str, Any], candidates: dict[str, tuple[str, ...]]
) -> tuple[dict[str, float] | None, dict[str, str] | None]:
    values: dict[str, float] = {}
    sources: dict[str, str] = {}
    for sign in ("1", "X", "2"):
        value, source = choose_odd(row, candidates[sign])
        if value is None or source is None:
            return None, None
        values[sign] = value
        sources[sign] = source
    return values, sources


def parse_date(value: Any) -> datetime | None:
    raw = text(value)
    if not raw:
        return None
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d-%m-%y"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def normalise_result(value: Any) -> str | None:
    raw = text(value).upper()
    if raw in {"H", "1", "0", "0.0"}:
        return "1"
    if raw in {"D", "X", "1.0"}:
        return "X"
    if raw in {"A", "2", "2.0"}:
        return "2"
    return None


def result_from_goals(home: float, away: float) -> str:
    if home > away:
        return "1"
    if home < away:
        return "2"
    return "X"


def all_blank(row: dict[str, Any], columns: Iterable[str]) -> bool:
    return all(is_blank(row.get(column)) for column in columns)


def duplicate_metrics(values: list[tuple[Any, ...]]) -> dict[str, int]:
    groups = [count for count in Counter(values).values() if count > 1]
    return {
        "groups": len(groups),
        "rows_involved": sum(groups),
        "excess_rows": sum(count - 1 for count in groups),
    }


def display_path(path: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            pass
    return path.as_posix()


def observed_distribution(values: list[float]) -> dict[str, float]:
    return {
        "minimum": round(min(values), 6),
        "median": round(statistics.median(values), 6),
        "maximum": round(max(values), 6),
    }
