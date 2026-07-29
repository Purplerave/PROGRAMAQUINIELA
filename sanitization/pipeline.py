"""Orquestación del pipeline de saneamiento.

Lee las filas brutas, aplica cada transformación en orden, separa las
filas excluidas de las saneadas y genera las salidas bajo
``salida/datos_limpios/``.

El pipeline no modifica los CSV originales ni entrena modelos.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from .aliases import apply_alias
from .constants import (
    ALIAS_MAP,
    COL_MOTIVO_EXCLUSION,
    COL_TRANSFORMACIONES,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_OVERROUND_MAX,
    DEFAULT_OVERROUND_MIN,
    DEFAULT_RAW_BASE,
)
from .filters import exclusion_reason
from .loaders import load_raw_rows
from .odds import annotate_odds
from .shots import annotate_shots
from .traceability import add_transform, init_transformations
from .writer import (
    build_manifest,
    validate_output_dir,
    write_all_outputs,
)


def sanitize_row(
    row: dict[str, Any],
    *,
    overround_min: float = DEFAULT_OVERROUND_MIN,
    overround_max: float = DEFAULT_OVERROUND_MAX,
    alias_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Aplica todas las transformaciones de saneamiento a una fila.

    Devuelve la fila enriquecida con las columnas de saneamiento.
    Si la fila debe ser excluida, se marca con ``motivo_exclusion``.

    Los metadatos internos ``_source_file``, ``_season`` y ``_division``
    se publican con nombres estables ``source_file``, ``season`` y
    ``division``. ``_columns`` no se publica.
    """
    columns: list[str] = row.get("_columns", [])

    # 1. Inicializar trazabilidad
    init_transformations(row)

    # 2. Publicar metadatos internos con nombres estables
    row["source_file"] = row.get("_source_file", "")
    row["season"] = row.get("_season", "")
    row["division"] = row.get("_division", "")

    # 3. Alias controlados (antes de filtrar, para que los alias
    #    se apliquen a las filas que pasen el filtro)
    effective_alias = alias_map if alias_map is not None else ALIAS_MAP
    if effective_alias:
        apply_alias(row, alias_map=effective_alias)

    # 4. Exclusión
    reason = exclusion_reason(row, columns)
    if reason is not None:
        row[COL_MOTIVO_EXCLUSION] = reason
        add_transform(row, f"EXCLUDED:{reason}")
        return row

    # 5. Cuotas: cierre real, movimiento, overround
    annotate_odds(
        row,
        overround_min=overround_min,
        overround_max=overround_max,
    )

    # 6. Tiros
    annotate_shots(row, columns)

    return row


def run_pipeline(
    raw_base: Path | None = None,
    output_dir: Path | None = None,
    *,
    confirm: bool = False,
    overround_min: float = DEFAULT_OVERROUND_MIN,
    overround_max: float = DEFAULT_OVERROUND_MAX,
    alias_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Ejecuta el pipeline completo de saneamiento.

    Devuelve un diccionario con el manifiesto y las estadísticas.
    Si ``confirm`` es False, no se escriben archivos.

    ``output_dir`` debe estar dentro de ``DEFAULT_OUTPUT_DIR``
    (``salida/datos_limpios/``). Si no, se aborta con ValueError.
    """
    effective_raw = Path(raw_base) if raw_base is not None else DEFAULT_RAW_BASE
    effective_out = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_DIR
    # Validar que el directorio de salida está dentro del permitido
    if confirm:
        validate_output_dir(effective_out)
    effective_alias = alias_map if alias_map is not None else ALIAS_MAP

    # Cargar filas brutas
    raw_rows = load_raw_rows(effective_raw)
    input_count = len(raw_rows)

    # Sanear cada fila
    sanitized: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()

    for row in raw_rows:
        result = sanitize_row(
            row,
            overround_min=overround_min,
            overround_max=overround_max,
            alias_map=effective_alias,
        )
        if result.get(COL_MOTIVO_EXCLUSION):
            excluded.append(result)
            reason_counts[result[COL_MOTIVO_EXCLUSION]] += 1
        else:
            sanitized.append(result)

    # Estadísticas
    output_count = len(sanitized)
    excluded_count = len(excluded)

    # Manifiesto
    timestamp = datetime.now()
    manifest = build_manifest(
        input_rows=input_count,
        output_rows=output_count,
        excluded_rows=excluded_count,
        exclusion_reasons=dict(sorted(reason_counts.items())),
        alias_map=effective_alias,
        overround_min=overround_min,
        overround_max=overround_max,
        timestamp=timestamp,
    )

    # Estadísticas por división y temporada
    division_stats: dict[str, Any] = {}
    for row in sanitized:
        div = row.get("division", "Desconocida")
        season = row.get("season", "Desconocida")
        key = f"{div}/{season}"
        if key not in division_stats:
            division_stats[key] = 0
        division_stats[key] += 1

    # Banderas
    has_real_close_count = sum(
        1 for row in sanitized if row.get("tiene_cierre_real") is True
    )
    has_shots_count = sum(
        1 for row in sanitized if row.get("tiene_tiros") is True
    )
    suspicious_count = sum(
        1 for row in sanitized if row.get("cuota_sospechosa") is True
    )
    alias_applied_count = sum(
        1 for row in sanitized
        if any("ALIAS_APPLIED" in t for t in row.get(COL_TRANSFORMACIONES, []))
    )

    stats = {
        "input_rows": input_count,
        "output_rows": output_count,
        "excluded_rows": excluded_count,
        "exclusion_reasons": dict(sorted(reason_counts.items())),
        "has_real_close": has_real_close_count,
        "has_real_close_pct": round(has_real_close_count / output_count * 100, 2) if output_count else 0,
        "has_shots": has_shots_count,
        "has_shots_pct": round(has_shots_count / output_count * 100, 2) if output_count else 0,
        "suspicious_odds": suspicious_count,
        "alias_applied": alias_applied_count,
        "by_division_season": division_stats,
    }

    result_payload: dict[str, Any] = {
        "manifest": manifest,
        "stats": stats,
    }

    # Escribir salidas solo si se confirma explícitamente
    if confirm:
        output_paths = write_all_outputs(
            sanitized, excluded, manifest, stats,
            effective_out, confirm=True,
        )
        result_payload["output_files"] = {
            key: str(path) for key, path in output_paths.items()
        }

    return result_payload


def format_summary(result: dict[str, Any]) -> str:
    """Genera un resumen humano del saneamiento."""
    stats = result["stats"]
    lines = [
        "SANEAMIENTO DE DATOS (solo lectura sobre originales)",
        "",
        f"Filas de entrada:    {stats['input_rows']}",
        f"Filas saneadas:      {stats['output_rows']}",
        f"Filas excluidas:     {stats['excluded_rows']}",
        "",
        "Motivos de exclusión:",
    ]
    for reason, count in stats["exclusion_reasons"].items():
        lines.append(f"  {reason}: {count}")
    lines.extend([
        "",
        f"Cierre real de cuotas: {stats['has_real_close']} ({stats['has_real_close_pct']}%)",
        f"Tiros disponibles:     {stats['has_shots']} ({stats['has_shots_pct']}%)",
        f"Cuotas sospechosas:    {stats['suspicious_odds']}",
        f"Alias aplicados:       {stats['alias_applied']}",
    ])
    if "output_files" in result:
        lines.append("")
        lines.append("Archivos generados:")
        for key, path in result["output_files"].items():
            lines.append(f"  {key}: {path}")
    else:
        lines.append("")
        lines.append("No se generaron archivos (use --confirm para escribir).")
    return "\n".join(lines)
