"""Constantes y configuración del saneamiento de datos."""

from __future__ import annotations

from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_BASE = PROJECT_ROOT / "DATOS" / "historico_raw"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "salida" / "datos_limpios"

# ---------------------------------------------------------------------------
# Esquema de cuotas — reproduce el orden de fallback del motor
# ---------------------------------------------------------------------------
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
EFFECTIVE_CLOSE_ODDS = {
    "1": ("AvgCH", "AvgH", "B365CH", "B365H"),
    "X": ("AvgCD", "AvgD", "B365CD", "B365D"),
    "2": ("AvgCA", "AvgA", "B365CA", "B365A"),
}

# ---------------------------------------------------------------------------
# Columnas de tiros y estadísticas
# ---------------------------------------------------------------------------
SHOT_COLUMNS = ("HS", "AS", "HST", "AST")
MATCH_STAT_COLUMNS = (
    "HS", "AS", "HST", "AST", "HF", "AF", "HC", "AC", "HY", "AY", "HR", "AR",
)

# ---------------------------------------------------------------------------
# Columnas mínimas requeridas para que una fila sea utilizable
# ---------------------------------------------------------------------------
REQUIRED_FIELDS = ("Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR")

# ---------------------------------------------------------------------------
# Alias controlados — solo se aplican los que estén explícitamente aquí
# ---------------------------------------------------------------------------
ALIAS_MAP: dict[str, str] = {
    "Leonesa": "Cultural Leonesa",
}

# Equipos que NO deben unificarse aunque parezcan similares
ALIAS_EXCLUSIONS: set[str] = {
    "Barcelona B", "Real Madrid B", "Sevilla B", "Sociedad B",
    "Villarreal B", "Ath Bilbao B", "Celta", "Ceuta",
    "Murcia", "UCAM Murcia", "Lorca", "Mallorca",
}

# ---------------------------------------------------------------------------
# Rango de overround para marcar cuotas sospechosas
# ---------------------------------------------------------------------------
DEFAULT_OVERROUND_MIN = 1.0
DEFAULT_OVERROUND_MAX = 1.4

# ---------------------------------------------------------------------------
# Partidos esperados por división
# ---------------------------------------------------------------------------
EXPECTED_MATCHES: dict[str, int] = {"Primera": 380, "Segunda": 462}

# ---------------------------------------------------------------------------
# Nombres de columnas de salida propios del saneamiento
# ---------------------------------------------------------------------------
COL_TIENE_CIERRE_REAL = "tiene_cierre_real"
COL_TIENE_TIROS = "tiene_tiros"
COL_CUOTA_SOSPECHOSA = "cuota_sospechosa"
COL_OVERROUND = "overround"
COL_MOTIVO_EXCLUSION = "motivo_exclusion"
COL_TRANSFORMACIONES = "transformaciones"
COL_HOME_TEAM_ORIGINAL = "home_team_original"
COL_AWAY_TEAM_ORIGINAL = "away_team_original"
