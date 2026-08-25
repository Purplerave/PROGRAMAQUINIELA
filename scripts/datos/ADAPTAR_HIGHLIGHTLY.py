#!/usr/bin/env python3
"""Adapta highlightly 2023-2026 a esquema historico_raw sin inventar cuotas.

Lee DATOS/highlightly_dataset/highlightly_partidos_2023_2026.csv,
filtra ES (laliga/segunda), mapea a columnas SP1/SP2 historicas,
deja cuotas NaN con market_source=no_auditado, genera CSV valido
para enriquecer Elo/forma sin contaminar backtest de mercado.
"""
from __future__ import annotations
import csv
from pathlib import Path
import hashlib

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC = PROJECT_ROOT / "DATOS" / "highlightly_dataset" / "highlightly_partidos_2023_2026.csv"
OUT_DIR = PROJECT_ROOT / "DATOS" / "historico_raw" / "HIGHLIGHTLY_ENRIQUECIDO"
OUT_FILE = OUT_DIR / "SP1_SP2_highlightly_2326.csv"

# mapeo nombres highlightly -> historico (los que difieren)
NAME_MAP = {
    "Athletic Club": "Ath Bilbao",
    "Atletico Madrid": "Ath Madrid",
    "Deportivo Alaves": "Alaves",
    "Celta Vigo": "Celta",
    "Espanyol": "Espanol",
}

def map_name(n: str) -> str:
    return NAME_MAP.get(n, n)

HEADER_HIST = "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR,B365H,B365D,B365A,BWH,BWD,BWA,IWH,IWD,IWA,PSH,PSD,PSA,WHH,WHD,WHA,VCH,VCD,VCA,MaxH,MaxD,MaxA,AvgH,AvgD,AvgA,B365>2.5,B365<2.5,P>2.5,P<2.5,Max>2.5,Max<2.5,Avg>2.5,Avg<2.5,AHh,B365AHH,B365AHA,PAHH,PAHA,MaxAHH,MaxAHA,AvgAHH,AvgAHA,B365CH,B365CD,B365CA,BWCH,BWCD,BWCA,IWCH,IWCD,IWCA,PSCH,PSCD,PSCA,WHCH,WHCD,WHCA,VCCH,VCCD,VCCA,MaxCH,MaxCD,MaxCA,AvgCH,AvgCD,AvgCA,B365C>2.5,B365C<2.5,PC>2.5,PC<2.5,MaxC>2.5,MaxC<2.5,AvgC>2.5,AvgC<2.5,AHCh,B365CAHH,B365CAHA,PCAHH,PCAHA,MaxCAHH,MaxCAHA,AvgCAHH,AvgCAHA"

def main() -> int:
    if not SRC.exists():
        print(f"ERROR: no existe {SRC}")
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    with SRC.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            if row["league_key"] not in ("laliga", "segunda"):
                continue
            if row["status"] != "Finished" or row["sign"] not in ("1","X","2"):
                continue
            # fecha highlightly 2023-08-11 -> historico dd/mm/yyyy
            y,m,d = row["date"].split("-")
            date_hist = f"{d}/{m}/{y}"
            div = "SP1" if row["league_key"]=="laliga" else "SP2"
            home = map_name(row["home_name"])
            away = map_name(row["away_name"])
            rows.append({
                "Div": div, "Date": date_hist, "Time": row["time_utc"][:5] if row["time_utc"] else "17:00",
                "HomeTeam": home, "AwayTeam": away,
                "FTHG": row["home_goals"], "FTAG": row["away_goals"], "FTR": row["sign"],
            })
    # ordenar por fecha
    from datetime import datetime
    rows.sort(key=lambda x: datetime.strptime(x["Date"], "%d/%m/%Y"))
    # escribir con header completo pero cuotas vacias
    cols = HEADER_HIST.split(",")
    with OUT_FILE.open("w", encoding="utf-8", newline="") as out:
        out.write(HEADER_HIST + "\n")
        for r in rows:
            vals = []
            for c in cols:
                vals.append(r.get(c, ""))
            out.write(",".join(vals) + "\n")
    sha = hashlib.sha256(OUT_FILE.read_bytes()).hexdigest()[:16]
    print(f"Escrito {OUT_FILE} : {len(rows)} partidos (SP1/SP2)  sha256:{sha}...")
    print(f"Origen: {SRC}  market_source=no_auditado, cuotas vacias, no contamina backtest mercado.")
    print(f"Uso: enriquecer Elo/forma via rolling_team_features; ignorado por calibrador_bandas (usa open_odd).")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
