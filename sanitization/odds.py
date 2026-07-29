"""Procesamiento de cuotas: cierre real, movimiento de mercado y overround.

Objetivos:
- Marcar si existen cuotas de cierre reales (``tiene_cierre_real``).
- Representar como ausente (NaN), no como cero, el movimiento de cuotas
  cuando no existe cierre real.
- Marcar cuotas sospechosas por overround fuera del rango configurado,
  sin eliminarlas automáticamente.
"""

from __future__ import annotations

import math
from typing import Any

from .constants import (
    COL_CUOTA_SOSPECHOSA,
    COL_MOTIVO_EXCLUSION,
    COL_OVERROUND,
    COL_TIENE_CIERRE_REAL,
    COL_TRANSFORMACIONES,
    DEFAULT_OVERROUND_MAX,
    DEFAULT_OVERROUND_MIN,
    EFFECTIVE_CLOSE_ODDS,
    OPEN_ODDS,
    REAL_CLOSE_ODDS,
)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _text(value: Any) -> str:
    if value is None or isinstance(value, list):
        return ""
    return str(value).strip()


def _to_float(value: Any) -> float | None:
    raw = _text(value).replace(",", ".")
    if not raw:
        return None
    try:
        number = float(raw)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _choose_odd(row: dict[str, Any], candidates: tuple[str, ...]) -> float | None:
    for col in candidates:
        value = _to_float(row.get(col))
        if value is not None and value > 1.01:
            return value
    return None


# ---------------------------------------------------------------------------
# Tripleta de cuotas
# ---------------------------------------------------------------------------

def odds_triplet(
    row: dict[str, Any], candidates: dict[str, tuple[str, ...]],
) -> dict[str, float] | None:
    """Devuelve la tripleta de cuotas ``{1, X, 2}`` o None si falta alguna."""
    values: dict[str, float] = {}
    for sign in ("1", "X", "2"):
        value = _choose_odd(row, candidates[sign])
        if value is None:
            return None
        values[sign] = value
    return values


# ---------------------------------------------------------------------------
# Cierre real
# ---------------------------------------------------------------------------

def has_real_close(row: dict[str, Any]) -> bool:
    """True si existe al menos una tripleta de cierre real (AvgC* / B365C*)."""
    return odds_triplet(row, REAL_CLOSE_ODDS) is not None


# ---------------------------------------------------------------------------
# Overround
# ---------------------------------------------------------------------------

def compute_overround(triplet: dict[str, float]) -> float:
    """Calcula el overround de una tripleta de cuotas."""
    return sum(1.0 / triplet[sign] for sign in ("1", "X", "2"))


def is_suspicious_overround(
    overround: float,
    min_overround: float = DEFAULT_OVERROUND_MIN,
    max_overround: float = DEFAULT_OVERROUND_MAX,
) -> bool:
    """True si el overround está fuera del rango configurado."""
    return overround < min_overround or overround > max_overround


# ---------------------------------------------------------------------------
# Movimiento de mercado
# ---------------------------------------------------------------------------

def market_move(
    opening: dict[str, float] | None,
    closing: dict[str, float] | None,
    has_close: bool,
) -> dict[str, float | None]:
    """Calcula el movimiento de cuotas entre apertura y cierre.

    Si ``has_close`` es False (no hay cierre real), el movimiento se
    representa como ``None`` (ausente), no como cero.
    """
    if opening is None or closing is None:
        return {"market_move_1": None, "market_move_x": None, "market_move_2": None}
    if not has_close:
        return {"market_move_1": None, "market_move_x": None, "market_move_2": None}
    implied_open = _implied_probs(opening)
    implied_close = _implied_probs(closing)
    return {
        "market_move_1": implied_close["1"] - implied_open["1"],
        "market_move_x": implied_close["X"] - implied_open["X"],
        "market_move_2": implied_close["2"] - implied_open["2"],
    }


def _implied_probs(triplet: dict[str, float]) -> dict[str, float]:
    inv = {sign: 1.0 / triplet[sign] for sign in ("1", "X", "2")}
    margin = sum(inv.values())
    return {sign: inv[sign] / margin for sign in ("1", "X", "2")}


# ---------------------------------------------------------------------------
# Anotación de cuotas sobre una fila
# ---------------------------------------------------------------------------

def annotate_odds(
    row: dict[str, Any],
    *,
    overround_min: float = DEFAULT_OVERROUND_MIN,
    overround_max: float = DEFAULT_OVERROUND_MAX,
) -> dict[str, Any]:
    """Añade columnas de cuotas saneadas a una fila.

    Modifica y devuelve la fila con:
    - ``tiene_cierre_real``: bool
    - ``overround``: float o None
    - ``cuota_sospechosa``: bool
    - ``market_move_1/x/2``: float o None
    - ``transformaciones``: lista actualizada
    """
    has_close = has_real_close(row)
    row[COL_TIENE_CIERRE_REAL] = has_close

    effective_close = odds_triplet(row, EFFECTIVE_CLOSE_ODDS)
    opening = odds_triplet(row, OPEN_ODDS)

    overround_val: float | None = None
    suspicious = False
    if effective_close is not None:
        overround_val = compute_overround(effective_close)
        suspicious = is_suspicious_overround(overround_val, overround_min, overround_max)

    row[COL_OVERROUND] = overround_val
    row[COL_CUOTA_SOSPECHOSA] = suspicious

    moves = market_move(opening, effective_close, has_close)
    row.update(moves)

    # Trazabilidad
    transforms: list[str] = row.get(COL_TRANSFORMACIONES, [])
    if not isinstance(transforms, list):
        transforms = []
    if not has_close:
        transforms.append("MARKET_MOVE_AS_NAN_NO_REAL_CLOSE")
    if suspicious:
        transforms.append("ODDS_OVERROUND_OUT_OF_RANGE")
    row[COL_TRANSFORMACIONES] = transforms

    return row
