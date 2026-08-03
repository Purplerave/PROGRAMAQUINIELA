#!/usr/bin/env python3
"""Descarga el xG por partido de La Liga desde Understat y lo guarda en CSV.

ROADMAP #3 (parte xG): estudio de viabilidad de una feature de xG. Este script
descarga los datos REALES de Understat (sin API key, scraping del JSON
embebido) para las temporadas indicadas y los consolida en un CSV tidy listo
para cruzar con el histórico y medir cobertura.

Uso (en la máquina con acceso a internet):
    python scripts/datos/DESCARGAR_XG_UNDERSTAT.py --desde 2014 --hasta 2025 --confirm

Cobertura conocida:
- La Liga (Primera): temporadas 2014/15 en adelante (~380 partidos/temporada).
- Segunda División: NO cubierta por Understat.

No escribe nada sin ``--confirm``. Nunca sobrescribe un CSV existente.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "datos"))

from understat_xg import parse_dates_data  # noqa: E402

LEAGUE = "La_liga"
BASE_URL = "https://understat.com/league/{league}/{year}"
DEFAULT_SALIDA = ROOT / "DATOS" / "xg_understat" / "understat_la_liga_xg.csv"
TEMP_HDR = ["match_id", "season", "datetime", "home", "away",
            "home_goals", "away_goals", "home_xg", "away_xg"]


def descargar_temporada(year: int) -> list[dict]:
    """Descarga y parsea los partidos con xG de una temporada de La Liga."""
    if requests is None:
        raise RuntimeError("Falta la dependencia 'requests'. Instala con: pip install -r requirements.txt")
    url = BASE_URL.format(league=LEAGUE, year=year)
    resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (xG study)"})
    resp.raise_for_status()
    partidos = parse_dates_data(resp.text)
    if not partidos:
        raise RuntimeError(f"No se parseo ningun partido de la temporada {year}: {url}")
    return partidos


def descargar(desde: int, hasta: int) -> list[dict]:
    """Descarga un rango de temporadas y las consolida."""
    todos: list[dict] = []
    for year in range(desde, hasta + 1):
        partidos = descargar_temporada(year)
        print(f"  temporada {year}/{year+1}: {len(partidos)} partidos con xG")
        todos.extend(partidos)
    return todos


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desde", type=int, default=2014, help="Primera temporada (año de inicio)")
    parser.add_argument("--hasta", type=int, default=date.today().year - 1, help="Última temporada (año de inicio)")
    parser.add_argument("--salida", type=Path, default=DEFAULT_SALIDA, help="Ruta del CSV de salida")
    parser.add_argument("--confirm", action="store_true", help="Escribe el CSV (sin sobrescribir)")
    args = parser.parse_args()

    if args.desde > args.hasta:
        parser.error("--desde debe ser <= --hasta")

    if not args.confirm:
        print("Modo prueba: se descargan y muestran los datos sin escribir el CSV.")
        print(f"Usa --confirm para guardarlos en {args.salida}")

    todos = descargar(args.desde, args.hasta)
    print(f"\nTotal: {len(todos)} partidos con xG (La Liga {args.desde}/{args.desde+1} a {args.hasta}/{args.hasta+1})")
    if todos:
        print("Ejemplo:")
        print(f"  {todos[0]}")

    if args.confirm:
        if args.salida.exists():
            print(f"\n[abortado] {args.salida} ya existe. No se sobrescribe.")
            return 1
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        with open(args.salida, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=TEMP_HDR)
            w.writeheader()
            w.writerows(todos)
        print(f"\nCSV escrito: {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
