"""Exclusión explícita de filas vacías y candidatos administrativos.

Criterios reproducibles:
- EMPTY_ROW: todas las celdas del CSV están vacías.
- ADMINISTRATIVE_CANDIDATE: resultado completo pero sin cuotas ni
  estadísticas de partido (criterio del Reus 2018-19).
- MISSING_REQUIRED_ODDS: no se puede construir la tripleta de cuotas
  de apertura necesaria para el motor.

Las filas excluidas se marcan con motivo, no se eliminan del DataFrame
hasta que el usuario lo decida; el módulo ``pipeline`` se encarga de
separarlas.
"""

from __future__ import annotations

import math
from typing import Any

from .constants import (
    EFFECTIVE_CLOSE_ODDS,
    MATCH_STAT_COLUMNS,
    OPEN_ODDS,
    REQUIRED_FIELDS,
    SHOT_COLUMNS,
)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _text(value: Any) -> str:
    if value is None or isinstance(value, list):
        return ""
    return str(value).strip()


def _is_blank(value: Any) -> bool:
    return _text(value) == ""


def _to_float(value: Any) -> float | None:
    raw = _text(value).replace(",", ".")
    if not raw:
        return None
    try:
        number = float(raw)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _all_blank(row: dict[str, Any], columns: list[str]) -> bool:
    return all(_is_blank(row.get(col)) for col in columns)


# ---------------------------------------------------------------------------
# Detección de fila vacía
# ---------------------------------------------------------------------------

def is_empty_row(row: dict[str, Any], columns: list[str]) -> bool:
    """True si todas las celdas del CSV están vacías."""
    return _all_blank(row, columns)


# ---------------------------------------------------------------------------
# Detección de candidato administrativo
# ---------------------------------------------------------------------------

def _has_complete_result(row: dict[str, Any]) -> bool:
    """True si fecha, identidad, goles y resultado están presentes."""
    return all(
        not _is_blank(row.get(f)) for f in REQUIRED_FIELDS
    )


def is_administrative_candidate(
    row: dict[str, Any],
    columns: list[str],
) -> bool:
    """True si el partido tiene resultado completo pero sin cuotas ni
    estadísticas de partido (criterio de REVISION_02 A2).

    Requiere que las columnas de estadísticas de partido existan en el
    esquema del CSV y estén vacías, y que las cuotas también estén vacías.
    Si el esquema no tiene columnas de estadísticas, no aplica (criterio
    de REVISION_03: «estadísticas de partido presentes en el esquema pero
    vacías»).
    """
    if not _has_complete_result(row):
        return False
    match_stats = [c for c in MATCH_STAT_COLUMNS if c in columns]
    # Las columnas de estadísticas deben existir en el esquema
    if not match_stats:
        return False
    odds_cols = sorted({
        col
        for mapping in (OPEN_ODDS, EFFECTIVE_CLOSE_ODDS)
        for choices in mapping.values()
        for col in choices
        if col in columns
    })
    return _all_blank(row, match_stats) and _all_blank(row, odds_cols)


# ---------------------------------------------------------------------------
# Detección de cuotas de apertura ausentes
# ---------------------------------------------------------------------------

def _choose_odd(row: dict[str, Any], candidates: tuple[str, ...]) -> float | None:
    for col in candidates:
        value = _to_float(row.get(col))
        if value is not None and value > 1.01:
            return value
    return None


def has_opening_odds(row: dict[str, Any]) -> bool:
    """True si se puede construir la tripleta de cuotas de apertura."""
    for sign in ("1", "X", "2"):
        if _choose_odd(row, OPEN_ODDS[sign]) is None:
            return False
    return True


# ---------------------------------------------------------------------------
# Motivo de exclusión
# ---------------------------------------------------------------------------

def exclusion_reason(
    row: dict[str, Any],
    columns: list[str],
) -> str | None:
    """Devuelve el motivo de exclusión o None si la fila es utilizable.

    Orden de prioridad: vacía > administrativa > sin cuotas de apertura.
    """
    if is_empty_row(row, columns):
        return "EMPTY_ROW"
    if is_administrative_candidate(row, columns):
        return "ADMINISTRATIVE_CANDIDATE"
    if not has_opening_odds(row):
        return "MISSING_REQUIRED_ODDS"
    return None
