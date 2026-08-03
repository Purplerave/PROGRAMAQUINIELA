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
import time
from datetime import date
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

try:
    import curl_cffi  # noqa: F401
    _HAY_CURL_CFFI = True
except ImportError:  # pragma: no cover
    _HAY_CURL_CFFI = False

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "datos"))

from understat_xg import (  # noqa: E402
    _DATES_RE,
    _TEAMS_RE,
    _PLAYERS_RE,
    _SHOTS_RE,
    _GROUPS_RE,
    parse_dates_data,
)

LEAGUE = "La_liga"
BASE_URL = "https://understat.com/league/{league}/{year}"
DEFAULT_SALIDA = ROOT / "DATOS" / "xg_understat" / "understat_la_liga_xg.csv"
TEMP_HDR = ["match_id", "season", "datetime", "home", "away",
            "home_goals", "away_goals", "home_xg", "away_xg"]

# User-Agent de navegador moderno (Understat bloquea UAs genéricos/robots).
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

DELAY_SEGUNDOS = 1.5


def _obtener_html(url: str, usar_curl_cffi: bool, impersonate: str = "chrome") -> tuple[str, str]:
    """Obtiene el HTML de Understat. Devuelve (html, motor_usado).

    - ``usar_curl_cffi``: usa curl_cffi imitando el TLS de un navegador real.
    - ``impersonate``: perfil TLS de curl_cffi (chrome/safari/firefox/edge...).
    """
    if usar_curl_cffi and _HAY_CURL_CFFI:
        from curl_cffi import requests as cffi_requests
        resp = cffi_requests.get(url, timeout=40, impersonate=impersonate)
        resp.raise_for_status()
        return resp.text, f"curl_cffi({impersonate})"
    if requests is None:
        raise RuntimeError("Falta la dependencia 'requests'. Instala con: pip install -r requirements.txt")
    resp = requests.get(url, timeout=40, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    return resp.text, "requests"


def descargar_temporada(year: int, usar_curl_cffi: bool = False, impersonate: str = "chrome") -> list[dict]:
    """Descarga y parsea los partidos con xG de una temporada de La Liga."""
    url = BASE_URL.format(league=LEAGUE, year=year)
    texto, motor = _obtener_html(url, usar_curl_cffi, impersonate)
    print(f"  [{motor}] longitud {len(texto)} chars")
    partidos = parse_dates_data(texto)
    if not partidos:
        raise RuntimeError(
            f"No se parseo ningun partido de la temporada {year}: {url}\n"
            f"  'datesData' presente: {'datesData' in texto} | 'teamsData' presente: {'teamsData' in texto}"
        )
    return partidos


def descargar(desde: int, hasta: int, usar_curl_cffi: bool = False, impersonate: str = "chrome") -> list[dict]:
    """Descarga un rango de temporadas y las consolida."""
    todos: list[dict] = []
    for year in range(desde, hasta + 1):
        partidos = descargar_temporada(year, usar_curl_cffi, impersonate)
        print(f"  temporada {year}/{year+1}: {len(partidos)} partidos con xG")
        todos.extend(partidos)
        if year != hasta:
            time.sleep(DELAY_SEGUNDOS)
    return todos


def diagnosticar_temporada(year: int, usar_curl_cffi: bool = False, impersonate: str = "chrome"):
    """Inspecciona la respuesta real de Understat para una temporada."""
    url = BASE_URL.format(league=LEAGUE, year=year)
    texto, motor = _obtener_html(url, usar_curl_cffi, impersonate)
    print(f"URL: {url}")
    print(f"Motor: {motor}")
    print(f"Longitud HTML: {len(texto)} chars")
    bloques = {
        "datesData": _DATES_RE.search(texto),
        "teamsData": _TEAMS_RE.search(texto),
        "playersData": _PLAYERS_RE.search(texto),
        "shotsData": _SHOTS_RE.search(texto),
        "groupsData": _GROUPS_RE.search(texto),
    }
    for nombre, m in bloques.items():
        print(f"  {nombre}: {'presente' if m else 'NO'}")
    bajo = texto.lower()
    for marca in ["cloudflare", "cf-browser-verification", "challenge",
                  "attention required", "just a moment", "verify you are human", "cf-ray"]:
        if marca in bajo:
            print(f"  -> Posible reto/bots detectado: {marca}")
    print("Primeros 400 caracteres:")
    print(texto[:400])
    return texto


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desde", type=int, default=2014, help="Primera temporada (año de inicio)")
    parser.add_argument("--diagnostico", type=int, default=None, help="Inspecciona la respuesta real de Understat para un año")
    parser.add_argument("--hasta", type=int, default=date.today().year - 1, help="Última temporada (año de inicio)")
    parser.add_argument("--salida", type=Path, default=DEFAULT_SALIDA, help="Ruta del CSV de salida")
    parser.add_argument("--curl-cffi", action="store_true", help="Usa curl_cffi (imita navegador) para sortear bloqueos")
    parser.add_argument("--impersonate", type=str, default="chrome", help="Perfil TLS de curl_cffi (chrome/safari/firefox/edge)")
    parser.add_argument("--confirm", action="store_true", help="Escribe el CSV (sin sobrescribir)")
    args = parser.parse_args()

    if args.curl_cffi and not _HAY_CURL_CFFI:
        print("curl_cffi no está instalado. Se usará requests normal.")
        print("Para sortear bloqueos: pip install curl_cffi")

    if args.diagnostico is not None:
        diagnosticar_temporada(args.diagnostico, args.curl_cffi, args.impersonate)
        return 0

    if args.desde > args.hasta:
        parser.error("--desde debe ser <= --hasta")

    if not args.confirm:
        print("Modo prueba: se descargan y muestran los datos sin escribir el CSV.")
        print(f"Usa --confirm para guardarlos en {args.salida}")

    todos = descargar(args.desde, args.hasta, args.curl_cffi, args.impersonate)
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
