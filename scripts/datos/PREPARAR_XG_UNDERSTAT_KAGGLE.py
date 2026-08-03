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

DEFAULT_SALIDA = ROOT / "DATOS" / "xg_understat" / "understat_la_liga_xg.csv"
TEMP_HDR = ["match_id", "season", "datetime", "home", "away",
            "home_goals", "away_goals", "home_xg", "away_xg"]

# Sinónimos de columnas aceptados (normalizados a minusculas/sin espacios).
_NOMBRES_XG_LOCAL = {"xg_h", "xg_for", "xgh", "xg_home", "home_xg", "xghome", "hgx"}
_NOMBRES_XG_VISIT = {"xg_a", "xg_against", "xga", "xg_away", "away_xg", "xgaway", "agx"}
_NOMBRES_EQ_LOCAL = {"home_team", "hteam", "h_team", "hometeam", "team_h", "home"}
_NOMBRES_EQ_VISIT = {"away_team", "ateam", "a_team", "awayteam", "team_a", "away"}
_NOMBRES_FECHA = {"datetime", "date", "match_date", "kickoff"}
_NOMBRES_TEMP = {"season", "season_id", "year"}
_NOMBRES_GOALS_LOCAL = {"h_goals", "goals_h", "home_goals", "hg", "fthg"}
_NOMBRES_GOALS_VISIT = {"a_goals", "goals_a", "away_goals", "ag", "ftag"}
_NOMBRES_MATCH_ID = {"id", "match_id", "matchid"}


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
    """Devuelve [(nombre, dataframe)] de todos los CSV en el ZIP o carpeta."""
    tablas: list[tuple[str, pd.DataFrame]] = []
    if isinstance(origen, zipfile.ZipFile):
        for nombre in origen.namelist():
            if nombre.lower().endswith(".csv"):
                try:
                    tablas.append((nombre, _cargar_tabla(origen, nombre)))
                except Exception:
                    pass
    else:
        for archivo in sorted(origen.glob("*.csv")):
            try:
                tablas.append((archivo.name, pd.read_csv(archivo)))
            except Exception:
                pass
    return tablas


def localizar_partidos_la_liga(origen) -> pd.DataFrame:
    """Localiza la tabla de partidos de La Liga con xG dentro de los CSVs."""
    mejor = None
    mejor_puntuacion = 0
    for nombre, df in _leer_csvs(origen):
        cols = {_norm(c) for c in df.columns}
        tiene_xg = bool(cols & _NOMBRES_XG_LOCAL | cols & _NOMBRES_XG_VISIT)
        tiene_eq = bool(cols & _NOMBRES_EQ_LOCAL | cols & _NOMBRES_EQ_VISIT)
        if not (tiene_xg and tiene_eq):
            continue
        # Buscar marca de La Liga en la fila/columna de liga, si existe.
        es_la_liga = False
        col_liga = _encontrar_col(df, {"league", "league_name", "leagueid", "competition", "liga"})
        if col_liga:
            vals = df[col_liga].astype(str).str.lower()
            es_la_liga = vals.str.contains("laliga", regex=False).any() or vals.str.contains("la liga", regex=False).any()
        elif "la_liga" in nombre.lower() or "laliga" in nombre.lower():
            es_la_liga = True
        puntuacion = (2 if es_la_liga else 0) + (2 if tiene_xg else 0) + (1 if tiene_eq else 0)
        if es_la_liga and puntuacion > mejor_puntuacion:
            mejor = df
            mejor_puntuacion = puntuacion
    if mejor is None:
        # Fallback: si no hay columna de liga, devolver la tabla con mas xG.
        candidatas = [
            df for _, df in _leer_csvs(origen)
            if (set(_norm(c) for c in df.columns) & _NOMBRES_XG_LOCAL | set(_norm(c) for c in df.columns) & _NOMBRES_XG_VISIT)
        ]
        if candidatas:
            mejor = max(candidatas, key=len)
    if mejor is None:
        raise ValueError("No se encontró una tabla de partidos de La Liga con xG en el dataset.")
    return mejor


def _celda_valor(fila, col: str | None):
    if col is None:
        return None
    return fila.get(col)


def convertir(partidos: pd.DataFrame) -> list[dict]:
    """Transforma la tabla de partidos al esquema estandar de salida.

    Si la tabla tiene columna de liga, se conservan solo las filas de La Liga
    (para el caso de un fichero unico con varias ligas).
    """
    col_liga = _encontrar_col(partidos, {"league", "league_name", "leagueid", "competition", "liga"})
    if col_liga is not None:
        vals = partidos[col_liga].astype(str).str.lower()
        es_la_liga = vals.str.contains("laliga", regex=False) | vals.str.contains("la liga", regex=False)
        partidos = partidos[es_la_liga]

    col_xg_h = _encontrar_col(partidos, _NOMBRES_XG_LOCAL)
    col_xg_a = _encontrar_col(partidos, _NOMBRES_XG_VISIT)
    col_eq_h = _encontrar_col(partidos, _NOMBRES_EQ_LOCAL)
    col_eq_a = _encontrar_col(partidos, _NOMBRES_EQ_VISIT)
    col_fecha = _encontrar_col(partidos, _NOMBRES_FECHA)
    col_temp = _encontrar_col(partidos, _NOMBRES_TEMP)
    col_gl_h = _encontrar_col(partidos, _NOMBRES_GOALS_LOCAL)
    col_gl_a = _encontrar_col(partidos, _NOMBRES_GOALS_VISIT)
    col_id = _encontrar_col(partidos, _NOMBRES_MATCH_ID)

    filas: list[dict] = []
    for _, fila in partidos.iterrows():
        home = _celda_valor(fila, col_eq_h)
        away = _celda_valor(fila, col_eq_a)
        if home is None or away is None:
            continue
        filas.append(
            {
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
        )
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
