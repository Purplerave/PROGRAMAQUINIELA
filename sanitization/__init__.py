"""Capa reproducible de saneamiento de datos.

API pública:
- ``run_pipeline()``: ejecuta el saneamiento completo.
- ``sanitize_row()``: sanea una fila individual.
- ``format_summary()``: genera un resumen humano.
"""

from .aliases import apply_alias
from .constants import (
    ALIAS_MAP,
    COL_CUOTA_SOSPECHOSA,
    COL_MOTIVO_EXCLUSION,
    COL_OVERROUND,
    COL_TIENE_CIERRE_REAL,
    COL_TIENE_TIROS,
    COL_TRANSFORMACIONES,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_OVERROUND_MAX,
    DEFAULT_OVERROUND_MIN,
    DEFAULT_RAW_BASE,
    MATCH_STAT_COLUMNS,
    SHOT_COLUMNS,
)
from .filters import exclusion_reason, is_administrative_candidate, is_empty_row
from .loaders import discover_csv_files, load_raw_rows
from .odds import annotate_odds, compute_overround, has_real_close, is_suspicious_overround
from .pipeline import format_summary, run_pipeline, sanitize_row
from .shots import annotate_shots
from .traceability import add_transform, get_transformations, init_transformations
from .writer import build_manifest, write_clean_csv, write_manifest

__all__ = [
    "ALIAS_MAP",
    "COL_CUOTA_SOSPECHOSA",
    "COL_MOTIVO_EXCLUSION",
    "COL_OVERROUND",
    "COL_TIENE_CIERRE_REAL",
    "COL_TIENE_TIROS",
    "COL_TRANSFORMACIONES",
    "DEFAULT_OUTPUT_DIR",
    "DEFAULT_OVERROUND_MAX",
    "DEFAULT_OVERROUND_MIN",
    "DEFAULT_RAW_BASE",
    "MATCH_STAT_COLUMNS",
    "SHOT_COLUMNS",
    "add_transform",
    "annotate_odds",
    "annotate_shots",
    "apply_alias",
    "build_manifest",
    "compute_overround",
    "discover_csv_files",
    "exclusion_reason",
    "format_summary",
    "get_transformations",
    "has_real_close",
    "init_transformations",
    "is_administrative_candidate",
    "is_empty_row",
    "is_suspicious_overround",
    "load_raw_rows",
    "run_pipeline",
    "sanitize_row",
    "write_clean_csv",
    "write_manifest",
]
