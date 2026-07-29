"""Lectura de los CSV originales sin modificarlos.

Cada fila se devuelve como un diccionario con todos los campos del CSV.
La función no filtra, no imputa ni transforma nada; es responsabilidad de
los módulos posteriores.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

from .constants import DEFAULT_RAW_BASE


def _season(path: Path) -> str:
    match = re.search(r"_(\d{2})(\d{2})$", path.stem)
    return f"20{match.group(1)}-20{match.group(2)}" if match else path.stem


def _division(path: Path) -> str:
    parent = path.parent.name.upper()
    if parent == "PRIMERA" or path.stem.upper().startswith("SP1_"):
        return "Primera"
    if parent == "SEGUNDA" or path.stem.upper().startswith("SP2_"):
        return "Segunda"
    return parent.title() or "Desconocida"


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Lee un CSV con codificación utf-8-sig y devuelve encabezados y filas."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def discover_csv_files(raw_base: Path | None = None) -> list[Path]:
    """Descubre los CSV históricos bajo ``raw_base``."""
    base = Path(raw_base) if raw_base is not None else DEFAULT_RAW_BASE
    return sorted(base.rglob("*.csv"))


def load_raw_rows(
    raw_base: Path | None = None,
) -> list[dict[str, Any]]:
    """Carga todas las filas brutas de todos los CSV históricos.

    Cada fila incluye metadatos: ``_source_file``, ``_season``,
    ``_division`` y ``_columns`` (lista de columnas del CSV origen).
    No se aplica ningún filtro ni transformación.
    """
    files = discover_csv_files(raw_base)
    all_rows: list[dict[str, Any]] = []
    for path in files:
        columns, rows = _read_csv(path)
        season, division = _season(path), _division(path)
        for row in rows:
            enriched = dict(row)
            enriched["_source_file"] = path.name
            enriched["_season"] = season
            enriched["_division"] = division
            enriched["_columns"] = columns
            all_rows.append(enriched)
    return all_rows
