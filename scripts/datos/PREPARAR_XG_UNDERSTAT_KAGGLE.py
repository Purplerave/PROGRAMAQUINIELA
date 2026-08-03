#!/usr/bin/env python3
"""Convierte el dataset de Understat de Kaggle a CSV de xG por partido.

Fuente: https://www.kaggle.com/datasets/mexwell/understat-database
(datos de Understat 2014-2023, incluye La Liga, ya descargados sin Cloudflare).

Este script lee el ZIP descargado (o la carpeta extraida), localiza la tabla
de partidos de La Liga con xG y la convierte al esquema estandar que consume
MEDIR_COBERTURA_XG.py:

    DATOS/xg_understat/understat_la_liga_xg.csv
    columnas: match_id, season, datetime, home, away, home_goals,
              away_goals, home_xg, away_xg

Uso:
    python scripts/datos/PREPARAR_XG_UNDERSTAT_KAGGLE.py \
        --zip C:\\ruta\\understat-database.zip --confirm

    # o bien contra una carpeta ya extraida:
    python scripts/datos/PREPARAR_XG_UNDERSTAT_KAGGLE.py \
        --dir C:\\ruta\\understats --confirm
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "motor"))

from team_names import resolve_history_name  # noqa: E402

# Columnas extras que se conservan en la salida (ademas de xG).
EXTRA_COLS = ["home_shots", "away_shots", "home_sot", "away_sot",
              "home_deep", "away_deep", "home_ppda", "away_ppda"]

DEFAULT_SALIDA = ROOT / "DATOS" / "xg_understat" / "understat_la_liga_xg.csv"
TEMP_HDR = ["match_id", "season", "datetime", "home", "away",
            "home_goals", "away_goals", "home_xg", "away_xg"] + EXTRA_COLS

# Sinónimos de columnas aceptados (NORMALIZADOS: minusculas y sin no-alfanum).
# Equipos local/visitante (incluye la nomenclatura de understatapi).
_NOMBRES_EQ_LOCAL = {"htitle", "hteam", "hteamid", "h_team", "hometeam", "teamh", "team_h", "home", "home_team"}
_NOMBRES_EQ_VISIT = {"atitle", "ateam", "ateamid", "a_team", "awayteam", "teama", "team_a", "away", "away_team"}
# xG local/visitante.
_NOMBRES_XG_LOCAL = {"hxg", "xgh", "xgfor", "xg_home", "home_xg", "homexg", "hgx"}
_NOMBRES_XG_VISIT = {"axg", "xga", "xgagainst", "xg_away", "away_xg", "awayxg", "agx"}
# Goles local/visitante.
_NOMBRES_GOALS_LOCAL = {"hgoals", "goalsh", "homegoals", "hg", "fthg", "h_goals"}
_NOMBRES_GOALS_VISIT = {"agoals", "goalsa", "awaygoals", "ag", "ftag", "a_goals"}
_NOMBRES_FECHA = {"datetime", "date", "matchdate", "kickoff"}
_NOMBRES_TEMP = {"season", "seasonid", "year"}
_NOMBRES_MATCH_ID = {"id", "matchid"}

# Features extra que match_info.csv expone (local/visitante).
_NOMBRES_SHOT_LOCAL = {"hshot", "h_shot", "hshots"}
_NOMBRES_SHOT_VISIT = {"ashot", "a_shot", "ashots"}
_NOMBRES_SOT_LOCAL = {"hshotontarget", "h_sot", "hshotsontarget"}
_NOMBRES_SOT_VISIT = {"ashotontarget", "a_sot", "ashotsontarget"}
_NOMBRES_DEEP_LOCAL = {"hdeep", "h_deep"}
_NOMBRES_DEEP_VISIT = {"adeep", "a_deep"}
_NOMBRES_PPDA_LOCAL = {"hppda", "h_ppda"}
_NOMBRES_PPDA_VISIT = {"appda", "a_ppda"}

# Columnas extras que se conservan en la salida (ademas de xG).


def _norm(col: str) -> str:
    return "".join(ch for ch in str(col).lower() if ch.isalnum())


def _encontrar_col(df: pd.DataFrame, sinónimos: set[str]) -> str | None:
    for col in df.columns:
        if _norm(col) in sinónimos:
            return col
    return None


def _cargar_tabla(path_or_zip: Path | zipfile.ZipFile, nombre: str) -> pd.DataFrame:
    """Carga un CSV (de carpeta o de un ZIP) en un DataFrame."""
    if isinstance(path_or_zip, zipfile.ZipFile):
        with path_or_zip.open(nombre) as f:
            return pd.read_csv(f)
    return pd.read_csv(path_or_zip / nombre)


def _leer_csvs(origen) -> list[tuple[str, pd.DataFrame]]:
    """Devuelve [(nombre_ruta, dataframe)] de todos los CSV en el ZIP o carpeta.

    En carpeta busca recursivamente (los CSV viven en subcarpetas de liga,
    p.ej. `understats/La_Liga/match_data.csv`).
    """
    tablas: list[tuple[str, pd.DataFrame]] = []
    if isinstance(origen, zipfile.ZipFile):
        for nombre in origen.namelist():
            if nombre.lower().endswith(".csv"):
                try:
                    tablas.append((nombre, _cargar_tabla(origen, nombre)))
                except Exception:
                    pass
    else:
        for archivo in sorted(origen.rglob("*.csv")):
            try:
                tablas.append((archivo.as_posix(), pd.read_csv(archivo)))
            except Exception:
                pass
    return tablas


def _es_ruta_la_liga(nombre: str) -> bool:
    n = nombre.replace("\\", "/").lower()
    return "laliga" in n.replace("_", "") or "la_liga" in n


def _es_match_data(nombre: str) -> bool:
    n = nombre.replace("\\", "/").lower()
    return n.endswith("match_data.csv") or n.endswith("matches.csv")


def localizar_partidos_la_liga(origen) -> pd.DataFrame:
    """Localiza la tabla de partidos con xG por equipo dentro de los CSVs.

    Escanea TODOS los CSVs de La Liga y elige el que tenga la estructura más
    completa de "partido": equipo local + equipo visitante + xG local + xG
    visitante (por fila). Eso descarta la tabla de temporada por equipo
    (match_data.csv, que tiene xG pero no por partido local/visitante).
    """
    candidatos = _leer_csvs(origen)
    la_liga = [(nombre, df) for nombre, df in candidatos if _es_ruta_la_liga(nombre)]

    # Prioridad 1: el archivo de partidos por excelencia, match_info.csv,
    # que en understatapi contiene: id, fid, h, a, date, season, h_goals,
    # a_goals, team_h, team_a, h_xg, a_xg, h_w/h_d/h_l, league, h_shot,
    # a_shot, h_shotOnTarget, a_shotOnTarget, h_deep, a_deep, h_ppda, a_ppda.
    for nombre, df in la_liga:
        if nombre.replace("\\", "/").lower().endswith("match_info.csv"):
            if _puntuar_tabla_partidos(df) > 0:
                return df

    mejor = None
    mejor_punt = -1
    for nombre, df in la_liga:
        punt = _puntuar_tabla_partidos(df)
        if punt > mejor_punt:
            mejor = (nombre, df)
            mejor_punt = punt

    if mejor is None:
        # Fallback: cualquier CSV (de cualquier liga) con estructura de partido.
        for nombre, df in candidatos:
            punt = _puntuar_tabla_partidos(df)
            if punt > mejor_punt:
                mejor = (nombre, df)
                mejor_punt = punt

    if mejor is None:
        raise ValueError("No se encontró una tabla de partidos con xG en el dataset.")
    return mejor[1]


def _puntuar_tabla_partidos(df: pd.DataFrame) -> int:
    """Puntua una tabla segun si tiene estructura de partido con xG por equipo."""
    cols = {_norm(c) for c in df.columns}
    puntos = 0
    puntos += 1 if (cols & _NOMBRES_EQ_LOCAL) else 0
    puntos += 1 if (cols & _NOMBRES_EQ_VISIT) else 0
    puntos += 2 if (cols & _NOMBRES_XG_LOCAL) else 0
    puntos += 2 if (cols & _NOMBRES_XG_VISIT) else 0
    puntos += 1 if (cols & _NOMBRES_GOALS_LOCAL) else 0
    puntos += 1 if (cols & _NOMBRES_GOALS_VISIT) else 0
    # Debe tener como minimo equipos + xG por cada lado para ser "de partido".
    tiene_equipos = bool(cols & _NOMBRES_EQ_LOCAL) and bool(cols & _NOMBRES_EQ_VISIT)
    tiene_xg = bool(cols & _NOMBRES_XG_LOCAL) and bool(cols & _NOMBRES_XG_VISIT)
    if not (tiene_equipos and tiene_xg):
        return -1  # no es tabla de partidos con xG por equipo
    return puntos


def _celda_valor(fila, col: str | None):
    if col is None:
        return None
    return fila.get(col)


def convertir(partidos: pd.DataFrame) -> list[dict]:
    """Transforma la tabla de partidos al esquema estandar de salida.

    Cada CSV del dataset corresponde a una sola liga (ya seleccionada por ruta
    en ``localizar_partidos_la_liga``), por lo que no se filtra por liga aquí.
    """
    col_xg_h = _encontrar_col(partidos, _NOMBRES_XG_LOCAL)
    col_xg_a = _encontrar_col(partidos, _NOMBRES_XG_VISIT)
    col_eq_h = _encontrar_col(partidos, _NOMBRES_EQ_LOCAL)
    col_eq_a = _encontrar_col(partidos, _NOMBRES_EQ_VISIT)
    col_fecha = _encontrar_col(partidos, _NOMBRES_FECHA)
    col_temp = _encontrar_col(partidos, _NOMBRES_TEMP)
    col_gl_h = _encontrar_col(partidos, _NOMBRES_GOALS_LOCAL)
    col_gl_a = _encontrar_col(partidos, _NOMBRES_GOALS_VISIT)
    col_id = _encontrar_col(partidos, _NOMBRES_MATCH_ID)

    # Columnas extras (tiros, tiros a puerta, deep, ppda) por equipo.
    mapa_extra = [
        ("home_shots", _encontrar_col(partidos, _NOMBRES_SHOT_LOCAL)),
        ("away_shots", _encontrar_col(partidos, _NOMBRES_SHOT_VISIT)),
        ("home_sot", _encontrar_col(partidos, _NOMBRES_SOT_LOCAL)),
        ("away_sot", _encontrar_col(partidos, _NOMBRES_SOT_VISIT)),
        ("home_deep", _encontrar_col(partidos, _NOMBRES_DEEP_LOCAL)),
        ("away_deep", _encontrar_col(partidos, _NOMBRES_DEEP_VISIT)),
        ("home_ppda", _encontrar_col(partidos, _NOMBRES_PPDA_LOCAL)),
        ("away_ppda", _encontrar_col(partidos, _NOMBRES_PPDA_VISIT)),
    ]

    filas: list[dict] = []
    for _, fila in partidos.iterrows():
        home = _celda_valor(fila, col_eq_h)
        away = _celda_valor(fila, col_eq_a)
        if home is None or away is None:
            continue
        fila_out = {
            "match_id": _celda_valor(fila, col_id),
            "season": _celda_valor(fila, col_temp),
            "datetime": _celda_valor(fila, col_fecha),
            "home": home,
            "away": away,
            "home_goals": _celda_valor(fila, col_gl_h),
            "away_goals": _celda_valor(fila, col_gl_a),
            "home_xg": _celda_valor(fila, col_xg_h),
            "away_xg": _celda_valor(fila, col_xg_a),
        }
        for nombre, col in mapa_extra:
            fila_out[nombre] = _celda_valor(fila, col)
        filas.append(fila_out)
    return filas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, default=None, help="Ruta al ZIP descargado de Kaggle")
    parser.add_argument("--dir", type=Path, default=None, help="Ruta a la carpeta extraida (understats/)")
    parser.add_argument("--salida", type=Path, default=DEFAULT_SALIDA, help="Ruta del CSV de salida")
    parser.add_argument("--confirm", action="store_true", help="Escribe el CSV (sin sobrescribir)")
    args = parser.parse_args()

    if (args.zip is None) == (args.dir is None):
        parser.error("Debes indicar --zip O --dir (no ambos, ni ninguno).")

    if args.zip and not args.zip.exists():
        parser.error(f"No existe el ZIP: {args.zip}")
    if args.dir and not args.dir.exists():
        parser.error(f"No existe la carpeta: {args.dir}")

    origen = None
    try:
        origen = zipfile.ZipFile(args.zip) if args.zip else None
        partidos = localizar_partidos_la_liga(origen if args.zip else args.dir)
        print(f"Tabla de partidos localizada: {len(partidos)} filas, {len(partidos.columns)} columnas")
        print(f"Columnas: {list(partidos.columns)}")
        filas = convertir(partidos)
        print(f"Partidos convertidos con xG: {len(filas)}")
        if filas:
            print("Ejemplo:", filas[0])
    finally:
        if origen:
            origen.close()

    if args.confirm and filas:
        if args.salida.exists():
            print(f"\n[abortado] {args.salida} ya existe. No se sobrescribe.")
            return 1
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        with open(args.salida, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=TEMP_HDR, extrasaction="ignore")
            w.writeheader()
            for fila in filas:
                w.writerow(fila)
        print(f"\nCSV escrito: {args.salida}")
        print("Ahora mide cobertura con: python scripts/datos/MEDIR_COBERTURA_XG.py --confirm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
