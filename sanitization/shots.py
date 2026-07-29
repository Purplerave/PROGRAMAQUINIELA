"""Disponibilidad de tiros: marca si las columnas de tiros existen y están
pobladas.

No imputa valores; solo marca la disponibilidad real.
"""

from __future__ import annotations

from typing import Any

from .constants import COL_TIENE_TIROS, COL_TRANSFORMACIONES, SHOT_COLUMNS


def _text(value: Any) -> str:
    if value is None or isinstance(value, list):
        return ""
    return str(value).strip()


def _is_blank(value: Any) -> bool:
    return _text(value) == ""


def shot_columns_exist(columns: list[str]) -> bool:
    """True si las cuatro columnas de tiros están en el esquema."""
    return all(col in columns for col in SHOT_COLUMNS)


def has_shot_values(row: dict[str, Any]) -> bool:
    """True si las cuatro celdas de tiros tienen valor."""
    return all(not _is_blank(row.get(col)) for col in SHOT_COLUMNS)


def annotate_shots(row: dict[str, Any], columns: list[str]) -> dict[str, Any]:
    """Añade ``tiene_tiros`` a la fila y actualiza la trazabilidad.

    ``tiene_tiros`` es True solo si:
    - las columnas de tiros existen en el esquema del CSV, y
    - las cuatro celdas tienen valor.

    Si el esquema no tiene las columnas, ``tiene_tiros`` es False y
    se registra la transformación ``SHOTS_SCHEMA_MISSING``.
    Si las columnas existen pero falta algún valor, ``tiene_tiros``
    es False y se registra ``SHOTS_VALUES_INCOMPLETE``.
    """
    schema_ok = shot_columns_exist(columns)
    values_ok = has_shot_values(row) if schema_ok else False

    row[COL_TIENE_TIROS] = schema_ok and values_ok

    transforms: list[str] = row.get(COL_TRANSFORMACIONES, [])
    if not isinstance(transforms, list):
        transforms = []
    if not schema_ok:
        transforms.append("SHOTS_SCHEMA_MISSING")
    elif not values_ok:
        transforms.append("SHOTS_VALUES_INCOMPLETE")
    row[COL_TRANSFORMACIONES] = transforms
    return row
