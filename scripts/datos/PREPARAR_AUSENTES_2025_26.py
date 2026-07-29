#!/usr/bin/env python3
"""Identifica los partidos 2025-26 ausentes del historico.

Lee los dos CSV historicos y el consolidado local de Highlightly. No llama a
ninguna API ni modifica las fuentes. Solo escribe con ``--confirm`` y nunca
sobrescribe el destino.
"""

from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
HIGHLIGHTLY = ROOT / "DATOS" / "highlightly_dataset" / "highlightly_partidos_2023_2026.csv"
HISTORICOS = {
    "Primera": ROOT / "DATOS" / "historico_raw" / "PRIMERA" / "SP1_2526.csv",
    "Segunda": ROOT / "DATOS" / "historico_raw" / "SEGUNDA" / "SP2_2526.csv",
}
OUTPUT_DIR = ROOT / "salida" / "datos_completado_2025_26"
OUTPUT_FILE = OUTPUT_DIR / "partidos_ausentes_highlightly.csv"

ALIASES = {
    "Alaves": "Alaves",
    "Almeria": "Almeria",
    "Andorra": "FC Andorra",
    "Ath Bilbao": "Athletic Club",
    "Ath Madrid": "Atletico Madrid",
    "Betis": "Real Betis",
    "Castellon": "Castellon",
    "Celta": "Celta de Vigo",
    "Ceuta": "AD Ceuta FC",
    "Espanol": "Espanyol",
    "Granada": "Granada CF",
    "La Coruna": "Deportivo La Coruna",
    "Santander": "Racing Santander",
    "Sevilla": "Sevilla FC",
    "Sociedad": "Real Sociedad",
    "Sociedad B": "Real Sociedad B",
    "Sp Gijon": "Sporting Gijon",
    "Vallecano": "Rayo Vallecano",
}

FIELDS = [
    "match_id", "date", "division", "season", "round", "home", "away",
    "home_goals", "away_goals", "result", "source", "missing_odds",
    "missing_shots",
]


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]", "", text)


def canonical_historical_team(value: object) -> str:
    text = str(value).strip()
    return normalize(ALIASES.get(text, text))


def match_key(date: object, home: object, away: object) -> tuple[str, str, str]:
    day = pd.to_datetime(
        str(date), format="%Y-%m-%d", errors="raise"
    ).strftime("%Y-%m-%d")
    return day, normalize(home), normalize(away)


def load_historical_keys() -> set[tuple[str, str, str]]:
    keys: set[tuple[str, str, str]] = set()
    for path in HISTORICOS.values():
        frame = pd.read_csv(path).dropna(how="all")
        for row in frame.itertuples(index=False):
            day = pd.to_datetime(row.Date, dayfirst=True).strftime("%Y-%m-%d")
            key = (
                day,
                canonical_historical_team(row.HomeTeam),
                canonical_historical_team(row.AwayTeam),
            )
            if key in keys:
                raise ValueError(f"Partido historico duplicado: {key}")
            keys.add(key)
    return keys


def result_from_goals(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "H"
    if home_goals < away_goals:
        return "A"
    return "D"


def load_highlightly_season() -> pd.DataFrame:
    frame = pd.read_csv(HIGHLIGHTLY, encoding="utf-8-sig")
    selected = frame[
        (frame["league_season"].astype(str) == "2025")
        & frame["league_name"].isin(["La Liga", "Segunda División"])
        & (frame["status"] == "Finished")
    ].copy()
    if len(selected) != 842:
        raise ValueError(f"Highlightly debe contener 842 partidos; contiene {len(selected)}")
    return selected


def build_missing_rows() -> list[dict[str, object]]:
    historical_keys = load_historical_keys()
    source = load_highlightly_season()
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()

    for row in source.itertuples(index=False):
        key = match_key(row.date, row.home_name, row.away_name)
        if key in seen:
            raise ValueError(f"Partido Highlightly duplicado: {key}")
        seen.add(key)
        if key in historical_keys:
            continue

        home_goals, away_goals = int(row.home_goals), int(row.away_goals)
        rows.append({
            "match_id": int(row.match_id),
            "date": key[0],
            "division": "Primera" if row.league_name == "La Liga" else "Segunda",
            "season": "2025-2026",
            "round": row.round,
            "home": row.home_name,
            "away": row.away_name,
            "home_goals": home_goals,
            "away_goals": away_goals,
            "result": result_from_goals(home_goals, away_goals),
            "source": "Highlightly",
            "missing_odds": True,
            "missing_shots": True,
        })

    rows.sort(key=lambda item: (str(item["date"]), str(item["division"]), str(item["home"])))
    counts = pd.Series([row["division"] for row in rows]).value_counts().to_dict()
    if counts != {"Segunda": 88, "Primera": 80}:
        raise ValueError(f"Conteo inesperado de ausentes: {counts}")
    return rows


def write_rows(rows: list[dict[str, object]], destination: Path = OUTPUT_FILE) -> Path:
    resolved = destination.resolve()
    if not resolved.is_relative_to(OUTPUT_DIR.resolve()):
        raise ValueError(f"La salida debe estar bajo {OUTPUT_DIR}")
    if resolved.exists():
        raise FileExistsError(f"No se sobrescribe el archivo existente: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true", help="escribe el CSV de salida")
    args = parser.parse_args()
    rows = build_missing_rows()
    counts = pd.Series([row["division"] for row in rows]).value_counts()
    print(f"Ausentes: {len(rows)} | Primera: {counts['Primera']} | Segunda: {counts['Segunda']}")
    if not args.confirm:
        print("No se ha escrito ningun archivo. Use --confirm para generarlo.")
        return 0
    print(f"Creado: {write_rows(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
