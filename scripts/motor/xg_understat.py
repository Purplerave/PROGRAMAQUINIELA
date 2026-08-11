"""scripts/motor/xg_understat.py — Carga y fusión del dataset de xG (Understat).

Integra el xG de disparo (shot-based xG) de Understat en el histórico del motor.

Procedencia de los datos (regla 5 de AGENTS.md):
- Fuente: Understat, vía el dataset de Kaggle `understat-database.zip`, extraído
  por `PREPARAR_XG_UNDERSTAT_[KAGGLE].py` y guardado como
  `DATOS/xg_understat/understat_la_liga_xg.csv`.
- Cobertura: 3.800 partidos de Primera, temporadas 2014-15 a 2023-24 (380 cada
  una). No cubre Segunda ni temporadas anteriores/posteriores.
- El xG es de disparo (por tiro), no posicional.
- Validez verificada (REVISION_12): 100 % de cobertura por par de equipos, 98,2 %
  por fecha exacta y goles 100 % coherentes con el histórico.

La fusión es tolerante a desplazamientos de fecha de 1 día (partidos aplazados):
primero intenta unir por (fecha, local, visitante) exacto y, si no hay match,
por par de equipos con ventana de ±3 días (fallback seguro en este dataset).

Comportamiento ante ausencia de datos: si el CSV no existe, está vacío o no
tiene el esquema esperado, añade las columnas de xG rellenas con NaN (con un
aviso claro por stderr) para no romper el flujo del motor. La carga es
tolerante al separador (``;``, ``,`` o tabulador) y acepta sinónimos comunes
de nombres de columna (p. ej. ``match_date``/``fecha``, ``home_team``/``local``,
``home_xg``/``xg_h``), porque distintos preparadores externos generan el CSV
con esquemas ligeramente distintos.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

import settings
from scripts.motor.team_names import resolve_history_name

XG_CSV = settings.DATOS_DIR / "xg_understat" / "understat_la_liga_xg.csv"

# Columnas de xG que se añaden al histórico tras la fusión.
XG_OUTPUT_COLUMNS = [
    "home_xg",
    "away_xg",
    "home_xg_deep",
    "away_xg_deep",
    "home_ppda",
    "away_ppda",
]

_DATE_FALLBACK_WINDOW = pd.Timedelta(days=3)

# Sinónimos aceptados para cada columna canónica del CSV de entrada.
COLUMN_ALIASES: dict[str, list[str]] = {
    "date": ["date", "match_date", "fecha", "fecha_partido", "datetime", "kickoff"],
    "team_h": ["team_h", "home_team", "h_team", "home", "local", "equipo_local", "home_team_name"],
    "team_a": ["team_a", "away_team", "a_team", "away", "visitante", "equipo_visitante", "away_team_name"],
    "h_xg": ["h_xg", "home_xg", "xg_h", "hxg", "xg_local", "home_xg_shot"],
    "a_xg": ["a_xg", "away_xg", "xg_a", "axg", "xg_visitante", "away_xg_shot"],
    "h_deep": ["h_deep", "home_xg_deep", "deep_h", "home_deep"],
    "a_deep": ["a_deep", "away_xg_deep", "deep_a", "away_deep"],
    "h_ppda": ["h_ppda", "home_ppda", "ppda_h"],
    "a_ppda": ["a_ppda", "away_ppda", "ppda_a"],
}

_XG_SEPARATORS = [";", ",", "\t"]


def _normalize_hist(value: object) -> str:
    """Normaliza un nombre a la forma canónica del histórico (sin cambios si no se resuelve)."""
    if not isinstance(value, str):
        return ""
    return resolve_history_name(value.strip())


def _norm_column(name: object) -> str:
    """Clave de columna normalizada: minúsculas, sin espacios ni símbolos."""
    return "".join(ch for ch in str(name).strip().lower() if ch.isalnum())


def _read_xg_csv(path: Path) -> pd.DataFrame | None:
    """Lee el CSV de xG detectando el separador y limpiando nombres de columna."""
    for sep in _XG_SEPARATORS:
        try:
            raw = pd.read_csv(path, sep=sep, encoding="utf-8-sig")
        except (pd.errors.ParserError, UnicodeDecodeError, OSError):
            continue
        if raw.shape[1] >= 2:
            break
    else:
        raw = None
    if raw is None or raw.empty:
        return None
    raw.columns = [str(c).strip() for c in raw.columns]
    return raw


def _map_columns(raw: pd.DataFrame) -> dict[str, str]:
    """Mapea las columnas reales del CSV a los nombres canónicos esperados."""
    present = {_norm_column(col): col for col in raw.columns}
    mapped: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if _norm_column(alias) in present:
                mapped[canonical] = present[_norm_column(alias)]
                break
    return mapped


def load_xg_frame() -> pd.DataFrame | None:
    """Carga el CSV de xG y lo deja en claves normalizadas del histórico.

    Devuelve None si el fichero no existe, está vacío o no contiene las
    columnas mínimas (fecha, local, visitante, xG local/visitante). Si el
    fichero existe pero con otro esquema, avisa por stderr: el xG es aditivo
    y no activo, por lo que el motor continúa sin él.
    """
    if not XG_CSV.exists():
        return None
    raw = _read_xg_csv(XG_CSV)
    if raw is None or raw.empty:
        return None

    mapped = _map_columns(raw)
    required = ["date", "team_h", "team_a", "h_xg", "a_xg"]
    missing = [col for col in required if col not in mapped]
    if missing:
        print(
            f"[xg_understat] Aviso: {XG_CSV.name} no tiene las columnas esperadas "
            f"(faltan: {', '.join(missing)}). Columnas encontradas: {sorted(raw.columns.tolist())}. "
            "Se omite el xG (aditivo, no activo); el motor continúa sin él.",
            file=sys.stderr,
        )
        return None

    def value(col: str) -> object:
        source = mapped.get(col)
        return raw[source] if source is not None else np.nan

    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(value("date"), errors="coerce"),
            "date_str": pd.to_datetime(value("date"), errors="coerce").dt.strftime("%Y-%m-%d"),
            "home": raw[mapped["team_h"]].map(_normalize_hist),
            "away": raw[mapped["team_a"]].map(_normalize_hist),
            "home_xg": pd.to_numeric(value("h_xg"), errors="coerce"),
            "away_xg": pd.to_numeric(value("a_xg"), errors="coerce"),
            "home_xg_deep": pd.to_numeric(value("h_deep"), errors="coerce"),
            "away_xg_deep": pd.to_numeric(value("a_deep"), errors="coerce"),
            "home_ppda": pd.to_numeric(value("h_ppda"), errors="coerce"),
            "away_ppda": pd.to_numeric(value("a_ppda"), errors="coerce"),
        }
    ).dropna(subset=["date", "home", "away", "home_xg", "away_xg"])
    return frame.reset_index(drop=True)


def _merge_exact(frame: pd.DataFrame, xg: pd.DataFrame) -> pd.DataFrame:
    """Une por (fecha exacta, local, visitante) y marca los partidos emparejados."""
    keys = ["date_str", "home", "away"]
    # ``frame`` aún no tiene las columnas de xG, así que el left-merge las añade
    # sin conflictos de sufijos.
    merged = frame.merge(xg[keys + XG_OUTPUT_COLUMNS], on=keys, how="left")
    matched = merged[XG_OUTPUT_COLUMNS].notna().all(axis=1)
    merged["_xg_matched"] = matched
    return merged


def _merge_fallback(frame: pd.DataFrame, xg: pd.DataFrame) -> pd.DataFrame:
    """Fallback por par de equipos con ventana de ±3 días para partidos aplazados."""
    unmatched_idx = frame.index[~frame["_xg_matched"]]
    if len(unmatched_idx) == 0:
        return frame

    # Índice del xG por par de equipos -> lista de (fecha, valores)
    pair_index: dict[tuple[str, str], list[pd.Series]] = {}
    for row in xg.itertuples(index=False):
        pair_index.setdefault((row.home, row.away), []).append(row)

    for idx in unmatched_idx:
        frow = frame.loc[idx]
        candidates = pair_index.get((frow["home"], frow["away"]), [])
        within = [
            row
            for row in candidates
            if abs(row.date - frow["date"]) <= _DATE_FALLBACK_WINDOW
        ]
        if len(within) == 1:
            row = within[0]
            for col in XG_OUTPUT_COLUMNS:
                frame.at[idx, col] = row.__getattribute__(col)
            frame.at[idx, "_xg_matched"] = True
    return frame


def merge_xg(frame: pd.DataFrame) -> pd.DataFrame:
    """Añade las columnas de xG al histórico del motor.

    ``frame`` debe tener ``date`` (datetime) y ``home``/``away`` en nombres del
    histórico. Las filas sin correspondencia quedan con NaN en las columnas de xG.
    """
    out = frame.copy()
    out["date_str"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out["home"] = out["home"].map(_normalize_hist)
    out["away"] = out["away"].map(_normalize_hist)

    xg = load_xg_frame()
    if xg is not None:
        out = _merge_exact(out, xg)
        out = _merge_fallback(out, xg)

    # Garantizar que todas las columnas de xG existan (NaN si no hubo datos).
    for col in XG_OUTPUT_COLUMNS:
        if col not in out.columns:
            out[col] = np.nan
    if "_xg_matched" in out.columns:
        out = out.drop(columns=["_xg_matched"])
    return out.reset_index(drop=True)


def xg_coverage_summary() -> dict[str, object]:
    """Resumen de cobertura del xG sobre el histórico para diagnóstico/validación."""
    xg = load_xg_frame()
    if xg is None:
        return {"available": False, "matches": 0}
    return {
        "available": True,
        "matches": int(len(xg)),
        "date_from": str(xg["date"].min().date()),
        "date_to": str(xg["date"].max().date()),
        "seasons": sorted(xg["date"].dt.year.value_counts().index.tolist()),
    }


if __name__ == "__main__":
    print("Cobertura xG:", xg_coverage_summary())
