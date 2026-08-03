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

Comportamiento ante ausencia de datos: si el CSV no existe o está vacío, añade
las columnas de xG rellenas con NaN para no romper el flujo del motor.
"""

from __future__ import annotations

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


def _normalize_hist(value: object) -> str:
    """Normaliza un nombre a la forma canónica del histórico (sin cambios si no se resuelve)."""
    if not isinstance(value, str):
        return ""
    return resolve_history_name(value.strip())


def load_xg_frame() -> pd.DataFrame | None:
    """Carga el CSV de xG y lo deja en claves normalizadas del histórico.

    Devuelve None si el fichero no existe o está vacío.
    """
    if not XG_CSV.exists():
        return None
    raw = pd.read_csv(XG_CSV, sep=";")
    if raw.empty:
        return None
    raw.columns = [c.strip() for c in raw.columns]

    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(raw["date"], errors="coerce"),
            "date_str": pd.to_datetime(raw["date"], errors="coerce").dt.strftime("%Y-%m-%d"),
            "home": raw["team_h"].map(_normalize_hist),
            "away": raw["team_a"].map(_normalize_hist),
            "home_xg": pd.to_numeric(raw["h_xg"], errors="coerce"),
            "away_xg": pd.to_numeric(raw["a_xg"], errors="coerce"),
            "home_xg_deep": pd.to_numeric(raw["h_deep"], errors="coerce"),
            "away_xg_deep": pd.to_numeric(raw["a_deep"], errors="coerce"),
            "home_ppda": pd.to_numeric(raw["h_ppda"], errors="coerce"),
            "away_ppda": pd.to_numeric(raw["a_ppda"], errors="coerce"),
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
