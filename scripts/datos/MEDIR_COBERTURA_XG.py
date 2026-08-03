#!/usr/bin/env python3
"""Mide la cobertura real del xG de Understat frente al historico.

Cruza el CSV descargado por DESCARGAR_XG_UNDERSTAT.py con el historico de
football-data (Primera) usando el mapeo de nombres del motor
(scripts/motor/team_names.py) y la fecha del partido. Reporta, por temporada
y en total, cuantos partidos de Primera quedan cubiertos por xG.

No requiere red: solo lee el CSV de xG y el historico local.

Uso:
    python scripts/datos/MEDIR_COBERTURA_XG.py [--xg RUTA_CSV_XG] [--confirm]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "motor"))

import settings  # noqa: E402
from team_names import resolve_history_name  # noqa: E402

DEFAULT_XG = ROOT / "DATOS" / "xg_understat" / "understat_la_liga_xg.csv"
OUTPUT_DIR = ROOT / "salida" / "features_futuras"
OUTPUT_FILE = OUTPUT_DIR / "cobertura_xg_understat.json"


def leer_xg(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["datetime"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
    df["home_hist"] = df["home"].map(resolve_history_name)
    df["away_hist"] = df["away"].map(resolve_history_name)
    return df


def cobertura() -> dict:
    xg = leer_xg(DEFAULT_XG)
    if xg.empty:
        return {"xg_presente": False, "mensaje": "No hay CSV de xG. Ejecuta primero DESCARGAR_XG_UNDERSTAT.py"}

    # Historico de Primera con fecha e identificadores de equipos.
    filas = []
    for f in sorted(settings.RAW_BASE.joinpath("PRIMERA").rglob("*.csv")):
        df = pd.read_csv(f)
        fecha = pd.to_datetime(df["Date"], format="%d/%m/%Y", errors="coerce")
        fecha = fecha.fillna(pd.to_datetime(df["Date"], format="%d/%m/%y", errors="coerce"))
        df["date"] = fecha
        df["division"] = "Primera"
        filas.append(df[["Date", "date", "HomeTeam", "AwayTeam", "division"]])
    hist = pd.concat(filas, ignore_index=True)
    hist["date"] = pd.to_datetime(hist["date"]).dt.normalize()

    xg["date"] = pd.to_datetime(xg["date"]).dt.normalize()
    xg["year"] = xg["date"].dt.year

    # Cruce por (fecha, equipo_local_historico, equipo_visitante_historico).
    clave_xg = xg[["date", "home_hist", "away_hist", "home_xg", "away_xg", "year"]].dropna(
        subset=["home_hist", "away_hist", "date"]
    )
    clave_hist = hist[["date", "HomeTeam", "AwayTeam"]].dropna()

    cruce = clave_hist.merge(
        clave_xg,
        left_on=["date", "HomeTeam", "AwayTeam"],
        right_on=["date", "home_hist", "away_hist"],
        how="left",
    )
    cubierto = cruce["home_xg"].notna()

    por_temp = cruce.groupby(cruce["date"].dt.year).agg(
        partidos=("date", "size"), cubiertos=("home_xg", lambda s: s.notna().sum())
    ).reset_index()
    por_temp["cobertura_pct"] = (por_temp["cubiertos"] / por_temp["partidos"] * 100).round(1)

    total_partidos = len(cruce)
    total_cubiertos = int(cubierto.sum())
    return {
        "xg_presente": True,
        "n_partidos_xg_descargados": int(len(xg)),
        "n_partidos_primera_en_historico": total_partidos,
        "n_partidos_primera_con_xg": total_cubiertos,
        "cobertura_global_pct": round(total_cubiertos / total_partidos * 100, 1) if total_partidos else 0.0,
        "por_temporada": por_temp.to_dict("records"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true", help="Escribe el informe JSON (sin sobrescribir)")
    args = parser.parse_args()

    report = cobertura()
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.confirm and report.get("xg_presente"):
        if OUTPUT_FILE.exists():
            print(f"\n[abortado] {OUTPUT_FILE} ya existe. No se sobrescribe.")
            return 1
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nInforme escrito: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
