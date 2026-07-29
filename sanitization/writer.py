"""Escritura de datos saneados bajo ``salida/datos_limpios/``.

Nunca sobrescribe archivos existentes; exige ``--confirm`` explícito.
No genera salidas por defecto.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .constants import (
    COL_CUOTA_SOSPECHOSA,
    COL_MOTIVO_EXCLUSION,
    COL_OVERROUND,
    COL_TIENE_CIERRE_REAL,
    COL_TIENE_TIROS,
    COL_TRANSFORMACIONES,
    DEFAULT_OUTPUT_DIR,
)


def _sanitize_for_json(obj: Any) -> Any:
    """Convierte valores no serializables a representaciones seguras."""
    if isinstance(obj, list):
        return [_sanitize_for_json(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, float):
        import math
        if not math.isfinite(obj):
            return None
        return obj
    return obj


def _output_columns(row: dict[str, Any]) -> list[str]:
    """Ordena las columnas de salida: metadatos primero, luego las del CSV."""
    meta = [
        COL_TIENE_CIERRE_REAL,
        COL_TIENE_TIROS,
        COL_CUOTA_SOSPECHOSA,
        COL_OVERROUND,
        COL_MOTIVO_EXCLUSION,
        COL_TRANSFORMACIONES,
    ]
    # Preservar columnas del CSV original en su orden
    csv_cols = [k for k in row if k not in meta and not k.startswith("_")]
    return meta + csv_cols


def write_clean_csv(
    rows: list[dict[str, Any]],
    output_dir: Path,
    filename: str,
    *,
    confirm: bool = False,
) -> Path:
    """Escribe las filas saneadas en un CSV bajo ``output_dir``.

    Si ``confirm`` es False, no genera el archivo.
    Si el archivo ya existe, aborta con FileExistsError.
    """
    if not confirm:
        raise RuntimeError(
            "No se generan salidas por defecto. Use --confirm para escribir."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    if path.exists():
        raise FileExistsError(
            f"El archivo ya existe; no se sobrescribe: {path}"
        )
    if not rows:
        path.touch()
        return path
    columns = _output_columns(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=columns, extrasaction="ignore"
        )
        writer.writeheader()
        for row in rows:
            clean = {}
            for col in columns:
                val = row.get(col)
                if isinstance(val, list):
                    clean[col] = "|".join(str(v) for v in val)
                else:
                    clean[col] = val
            writer.writerow(clean)
    return path


def write_manifest(
    manifest: dict[str, Any],
    output_dir: Path,
    filename: str = "manifest.json",
    *,
    confirm: bool = False,
) -> Path:
    """Escribe el manifiesto de saneamiento en JSON."""
    if not confirm:
        raise RuntimeError(
            "No se generan salidas por defecto. Use --confirm para escribir."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    if path.exists():
        raise FileExistsError(
            f"El archivo ya existe; no se sobrescribe: {path}"
        )
    sanitized = _sanitize_for_json(manifest)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(sanitized, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    return path


def build_manifest(
    input_rows: int,
    output_rows: int,
    excluded_rows: int,
    exclusion_reasons: dict[str, int],
    alias_map: dict[str, str],
    overround_min: float,
    overround_max: float,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Construye el manifiesto de la ejecución de saneamiento."""
    return {
        "schema_version": 1,
        "read_only_originals": True,
        "timestamp": (timestamp or datetime.now()).isoformat(),
        "input_rows": input_rows,
        "output_rows": output_rows,
        "excluded_rows": excluded_rows,
        "exclusion_reasons": exclusion_reasons,
        "alias_map": alias_map,
        "overround_range": {"min": overround_min, "max": overround_max},
        "output_directory": "salida/datos_limpios/",
    }
