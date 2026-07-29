"""Escritura de datos saneados bajo ``salida/datos_limpios/``.

Nunca sobrescribe archivos existentes; exige ``--confirm`` explícito.
No genera salidas por defecto.

Reglas:
- El esquema de columnas se construye como la unión ordenada de TODAS
  las filas, no solo de la primera, para no perder columnas que solo
  existen en temporadas posteriores.
- Se publica ``source_file``, ``season`` y ``division`` como nombres
  estables; no se publica ``_columns`` ni otros metadatos internos.
- Antes de escribir cualquier archivo se realiza un preflight: se
  comprueba que los cuatro destinos no existen. Si alguno ya existe,
  se aborta sin crear/escribir ninguno.
- El directorio de salida debe estar dentro de ``DEFAULT_OUTPUT_DIR``.
"""

from __future__ import annotations

import csv
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from .constants import (
    COL_AWAY_TEAM_ORIGINAL,
    COL_CUOTA_SOSPECHOSA,
    COL_HOME_TEAM_ORIGINAL,
    COL_MOTIVO_EXCLUSION,
    COL_OVERROUND,
    COL_TIENE_CIERRE_REAL,
    COL_TIENE_TIROS,
    COL_TRANSFORMACIONES,
    DEFAULT_OUTPUT_DIR,
)

# ---------------------------------------------------------------------------
# Columnas de metadatos publicados (nombres estables, no prefijo _)
# ---------------------------------------------------------------------------
META_COLUMNS = [
    COL_TIENE_CIERRE_REAL,
    COL_TIENE_TIROS,
    COL_CUOTA_SOSPECHOSA,
    COL_OVERROUND,
    COL_MOTIVO_EXCLUSION,
    COL_TRANSFORMACIONES,
    COL_HOME_TEAM_ORIGINAL,
    COL_AWAY_TEAM_ORIGINAL,
    "source_file",
    "season",
    "division",
]

# Campos internos que NO se publican
INTERNAL_FIELDS = {"_columns"}


# ---------------------------------------------------------------------------
# Validación del directorio de salida
# ---------------------------------------------------------------------------

def validate_output_dir(output_dir: Path) -> Path:
    """Valida que ``output_dir`` esté dentro de ``DEFAULT_OUTPUT_DIR``.

    Devuelve ``output_dir`` resuelto si es válido; lanza ValueError
    en caso contrario.
    """
    resolved = output_dir.resolve()
    allowed = DEFAULT_OUTPUT_DIR.resolve()
    try:
        resolved.relative_to(allowed)
    except ValueError:
        raise ValueError(
            f"El directorio de salida debe estar dentro de "
            f"{allowed}; se recibió {resolved}."
        )
    return resolved


# ---------------------------------------------------------------------------
# Serialización JSON
# ---------------------------------------------------------------------------

def _sanitize_for_json(obj: Any) -> Any:
    """Convierte valores no serializables a representaciones seguras."""
    if isinstance(obj, list):
        return [_sanitize_for_json(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, float):
        if not math.isfinite(obj):
            return None
        return obj
    return obj


# ---------------------------------------------------------------------------
# Esquema de columnas: unión ordenada de TODAS las filas
# ---------------------------------------------------------------------------

def _build_output_columns(rows: list[dict[str, Any]]) -> list[str]:
    """Construye la unión ordenada de columnas de todas las filas.

    Metadatos primero, luego las columnas del CSV en orden de primera
    aparición. Esto evita perder columnas que solo existen en filas
    posteriores (p.ej. cuotas modernas en temporadas 2019+).
    """
    seen: dict[str, None] = {}
    for row in rows:
        for key in row:
            if key not in seen and key not in INTERNAL_FIELDS:
                seen[key] = None

    csv_cols = [k for k in seen if k not in META_COLUMNS]
    return META_COLUMNS + csv_cols


# ---------------------------------------------------------------------------
# Preflight: verificar que los cuatro destinos no existen
# ---------------------------------------------------------------------------

def _preflight_check(output_dir: Path, filenames: list[str]) -> None:
    """Comprueba que ninguno de los destinos existe antes de escribir.

    Si alguno ya existe, aborta con FileExistsError sin haber creado
    ningún archivo adicional.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename in filenames:
        path = output_dir / filename
        if path.exists():
            raise FileExistsError(
                f"El archivo ya existe; no se sobrescribe: {path}"
            )


# ---------------------------------------------------------------------------
# Escritura CSV
# ---------------------------------------------------------------------------

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
    validated = validate_output_dir(output_dir)
    validated.mkdir(parents=True, exist_ok=True)
    path = validated / filename
    if path.exists():
        raise FileExistsError(
            f"El archivo ya existe; no se sobrescribe: {path}"
        )
    if not rows:
        path.touch()
        return path
    columns = _build_output_columns(rows)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=columns, extrasaction="ignore"
        )
        writer.writeheader()
        for row in rows:
            clean: dict[str, Any] = {}
            for col in columns:
                val = row.get(col)
                if isinstance(val, list):
                    clean[col] = "|".join(str(v) for v in val)
                else:
                    clean[col] = val
            writer.writerow(clean)
    return path


# ---------------------------------------------------------------------------
# Escritura JSON (manifiesto y estadísticas)
# ---------------------------------------------------------------------------

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
    validated = validate_output_dir(output_dir)
    validated.mkdir(parents=True, exist_ok=True)
    path = validated / filename
    if path.exists():
        raise FileExistsError(
            f"El archivo ya existe; no se sobrescribe: {path}"
        )
    sanitized = _sanitize_for_json(manifest)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(sanitized, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    return path


# ---------------------------------------------------------------------------
# Escritura atómica: preflight + escritura de los cuatro archivos
# ---------------------------------------------------------------------------

OUTPUT_FILENAMES = [
    "historico_saneado.csv",
    "historico_excluido.csv",
    "manifest.json",
    "estadisticas.json",
]


def write_all_outputs(
    sanitized_rows: list[dict[str, Any]],
    excluded_rows: list[dict[str, Any]],
    manifest: dict[str, Any],
    stats: dict[str, Any],
    output_dir: Path,
    *,
    confirm: bool = False,
) -> dict[str, Path]:
    """Preflight de los cuatro destinos y luego escritura atómica.

    Si cualquiera de los cuatro destinos ya existe, aborta sin crear
    ningún archivo adicional. Solo se escriben los cuatro archivos
    cuando ninguno existe previamente.
    """
    if not confirm:
        raise RuntimeError(
            "No se generan salidas por defecto. Use --confirm para escribir."
        )
    validated = validate_output_dir(output_dir)
    # Preflight: comprobar que los cuatro destinos no existen
    _preflight_check(validated, OUTPUT_FILENAMES)

    # Escritura: todos los destinos están libres
    csv_path = write_clean_csv(sanitized_rows, validated, OUTPUT_FILENAMES[0], confirm=True)
    excl_path = write_clean_csv(excluded_rows, validated, OUTPUT_FILENAMES[1], confirm=True)
    manifest_path = write_manifest(manifest, validated, OUTPUT_FILENAMES[2], confirm=True)
    stats_path = write_manifest(stats, validated, OUTPUT_FILENAMES[3], confirm=True)
    return {
        "clean": csv_path,
        "excluded": excl_path,
        "manifest": manifest_path,
        "stats": stats_path,
    }


# ---------------------------------------------------------------------------
# Manifiesto
# ---------------------------------------------------------------------------

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
