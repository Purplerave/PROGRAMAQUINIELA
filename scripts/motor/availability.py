"""Capa de disponibilidad (QuiniLAB V1.3): features desde Highlightly.

Point-in-time: solo usa datos del partido (alineaciones publicadas, xG), nunca resultados posteriores.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
try:
    from team_names import resolve_history_name, normalize_team_name
except Exception:  # pragma: no cover
    def resolve_history_name(x):  # type: ignore
        return str(x).strip() if x is not None else ""
    def normalize_team_name(x):  # type: ignore
        return str(x).strip().lower() if x is not None else ""

def _norm_date(value: Any) -> str:
    text = str(value).strip()
    # Highlightly: ISO 8601; histórico: dd/mm/yyyy o yyyy-mm-dd
    if "T" in text:
        return text[:10]
    if "/" in text:
        d, m, y = text.split("/")
        return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    return text[:10]


def unir_al_historico(history_df, availability_df):
    """Une features de disponibilidad al histórico por fecha+local+visitante (normalizado)."""
    h = history_df.copy()
    h["_fecha"] = h.get("date", h.get("fecha")).apply(_norm_date) if "date" in h.columns or "fecha" in h.columns else ""
    home_col = "home" if "home" in h.columns else ("local" if "local" in h.columns else None)
    away_col = "away" if "away" in h.columns else ("visitante" if "visitante" in h.columns else None)
    h["_home"] = h[home_col].map(resolve_history_name) if home_col else ""
    h["_away"] = h[away_col].map(resolve_history_name) if away_col else ""

    a = availability_df.copy()
    a["_fecha"] = a["hl_date"].apply(_norm_date)
    a["_home"] = a["hl_home"].map(resolve_history_name)
    a["_away"] = a["hl_away"].map(resolve_history_name)

    merged = h.merge(a, on=["_fecha", "_home", "_away"], how="left", suffixes=("", "_hl"))
    return merged.drop(columns=["_fecha", "_home", "_away"], errors="ignore")


def _float_o_none(value: Any):
    try:
        v = float(value)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def _starter_count(block: Any) -> int:
    if not isinstance(block, dict):
        return 0
    initial = block.get("initialLineup")
    if isinstance(initial, list):
        return sum(len(row) if isinstance(row, list) else 1 for row in initial)
    return 0


def extraer_disponibilidad(registro: dict) -> dict:
    match = registro.get("match", {}) or {}
    lineups = registro.get("lineups") or {}
    stats = registro.get("stats") or []

    home_team = (match.get("homeTeam") or {}).get("name")
    away_team = (match.get("awayTeam") or {}).get("name")

    home_xg = None
    away_xg = None
    cuerpo = stats if isinstance(stats, list) else []
    for equipo in cuerpo:
        if not isinstance(equipo, dict):
            continue
        to = equipo.get("team")
        tname = to.get("name") if isinstance(to, dict) else None
        for st in equipo.get("statistics", []) or []:
            if isinstance(st, dict) and "expected goal" in str(st.get("displayName", "")).lower():
                v = _float_o_none(st.get("value"))
                if tname == home_team:
                    home_xg = v
                elif tname == away_team:
                    away_xg = v

    home_starters = _starter_count(lineups.get("homeTeam") if isinstance(lineups, dict) else None)
    away_starters = _starter_count(lineups.get("awayTeam") if isinstance(lineups, dict) else None)

    return {
        "hl_home_starters": home_starters,
        "hl_away_starters": away_starters,
        "hl_starter_diff": home_starters - away_starters,
        "hl_home_xg": home_xg,
        "hl_away_xg": away_xg,
        "hl_xg_diff": (home_xg - away_xg) if (home_xg is not None and away_xg is not None) else None,
    }


def construir_disponibilidad(path: Path) -> pd.DataFrame:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    registros = data if isinstance(data, list) else data.get("partidos", [])
    filas = []
    for r in registros:
        feat = extraer_disponibilidad(r)
        m = r.get("match", {}) or {}
        feat["hl_match_id"] = m.get("id")
        feat["hl_date"] = m.get("date")
        feat["hl_home"] = (m.get("homeTeam") or {}).get("name")
        feat["hl_away"] = (m.get("awayTeam") or {}).get("name")
        filas.append(feat)
    return pd.DataFrame(filas)
