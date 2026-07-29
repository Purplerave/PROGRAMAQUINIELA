"""Trazabilidad por fila: cada fila indica qué transformaciones recibió.

La columna ``transformaciones`` es una lista de cadenas que se va
construyendo a medida que los módulos de saneamiento anotan la fila.
Este módulo proporciona utilidades para inicializarla y consultarla.
"""

from __future__ import annotations

from typing import Any

from .constants import COL_TRANSFORMACIONES


def init_transformations(row: dict[str, Any]) -> dict[str, Any]:
    """Inicializa la columna de trazabilidad si no existe."""
    if COL_TRANSFORMACIONES not in row or not isinstance(
        row[COL_TRANSFORMACIONES], list
    ):
        row[COL_TRANSFORMACIONES] = []
    return row


def add_transform(row: dict[str, Any], label: str) -> dict[str, Any]:
    """Añade una etiqueta de transformación a la fila."""
    transforms = row.get(COL_TRANSFORMACIONES, [])
    if not isinstance(transforms, list):
        transforms = []
    transforms.append(label)
    row[COL_TRANSFORMACIONES] = transforms
    return row


def get_transformations(row: dict[str, Any]) -> list[str]:
    """Devuelve la lista de transformaciones aplicadas a la fila."""
    val = row.get(COL_TRANSFORMACIONES, [])
    return val if isinstance(val, list) else []
