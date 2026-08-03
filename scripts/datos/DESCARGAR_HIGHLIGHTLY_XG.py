#!/usr/bin/env python3
"""Descarga el xG por partido de La Liga desde la API de Highlightly (PRO).

Lee la API key de la variable de entorno ``HIGHLIGHTLY_API_KEY`` o del fichero
``.env`` (ver highlightly_client.py). Descarga las estadísticas de cada partido
de La Liga para las temporadas indicadas, extrae el xG y lo consolida en un CSV
en el mismo esquema que el de Understat, de modo que pueda medirse la cobertura
con MEDIR_COBERTURA_XG.py.

Uso:
    # 1) Valida sin gastar todo el presupuesto (descarga solo 5 partidos y enseña xG)
    python scripts/datos/DESCARGAR_HIGHLIGHTLY_XG.py --prueba 5

    # 2) Inspecciona el JSON crudo de un partido (para afinar el parser si cambia)
    python scripts/datos/DESCARGAR_HIGHLIGHTLY_XG.py --raw <match_id>

    # 3) Descarga el rango de temporadas y escribe el CSV
    python scripts/datos/DESCARGAR_HIGHLIGHTLY_XG.py --desde 2014 --hasta 2025 --confirm

NOTA sobre presupuesto: cada partido cuesta 1 llamada a /statistics. La Liga
tiene ~380 partidos/temporada. Un rango 2014-2025 son ~4560 llamadas (dentro de
un plan PRO de 7500). Usa --prueba y --raw antes de lanzar el rango completo.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

from highlightly_client import BASE_URL, HighlightlyClient, parse_estadisticas, localizar_campo_xg  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SALIDA = ROOT / "DATOS" / "highlightly_dataset" / "highlightly_la_liga_xg.csv"
TEMP_HDR = ["match_id", "season", "datetime", "home", "away",
            "home_goals", "away_goals", "home_xg", "away_xg"]

NOMBRE_LIGA = "La Liga"


def _equipo_nombre(objeto) -> str:
    if not isinstance(objeto, dict):
        return ""
    return str(objeto.get("name") or objeto.get("title") or "")


def localizar_la_liga(cliente: HighlightlyClient) -> dict:
    """Busca la liga de La Liga (Primera División española) y devuelve su id."""
    ligas = cliente.buscar_ligas(NOMBRE_LIGA)
    # Preferir la de España que NO sea "La Liga 2"/Segunda.
    for liga in ligas:
        nombre = str(liga.get("name") or liga.get("league_name") or "")
        pais = str(liga.get("country_name") or liga.get("country") or "")
        nombre_l = nombre.lower()
        if ("la liga" in nombre_l or "primera" in nombre_l or nombre_l.startswith("liga")) and \
           "segunda" not in nombre_l and "2" not in nombre_l:
            return liga
    # Fallback: primera coincidencia
    if ligas:
        return ligas[0]
    raise RuntimeError("No se encontró la liga de La Liga. Revisa el resultado de /football/leagues")


def extraer_partido_resumido(match: dict) -> dict:
    """Convierte un match de Highlightly al resumen que necesitamos."""
    return {
        "match_id": match.get("id"),
        "datetime": match.get("datetime") or match.get("date"),
        "home": _equipo_nombre(match.get("home") or match.get("homeTeam")),
        "away": _equipo_nombre(match.get("away") or match.get("awayTeam")),
    }


def descargar_temporada(cliente, league_id, season, limite=None) -> list[dict]:
    partidos_api = cliente.obtener_partidos(league_id, season)
    filas: list[dict] = []
    for match in partidos_api:
        status = str(match.get("status") or "").lower()
        if status and not status.startswith("finished"):
            continue
        resumen = extraer_partido_resumido(match)
        match_id = resumen["match_id"]
        if match_id is None:
            continue
        stats = parse_estadisticas(cliente.obtener_estadisticas(match_id))
        if len(stats) >= 2 and stats[0]["xg"] is not None and stats[1]["xg"] is not None:
            resumen["home_xg"] = stats[0]["xg"]
            resumen["away_xg"] = stats[1]["xg"]
        else:
            resumen["home_xg"] = None
            resumen["away_xg"] = None
        filas.append(resumen)
        if limite and len(filas) >= limite:
            break
    return filas




def probar_endpoints(cliente: HighlightlyClient, match_id: int) -> dict:
    """Prueba varios endpoints y reporta en cual aparece xG."""
    resultado = {}
    pruebas = {
        "statistics": lambda: cliente.obtener_estadisticas(match_id),
        "match_detail": lambda: cliente.obtener_partido(match_id),
        "box_score": lambda: cliente.obtener_boxscore(match_id),
    }
    for nombre, fn in pruebas.items():
        try:
            data = fn()
            time.sleep(2)  # respetar el rate limit entre endpoints
        except Exception as e:
            resultado[nombre] = {"error": str(e)[:120]}
            continue
        hit = localizar_campo_xg(data)
        if hit:
            ruta, valor = hit
            resultado[nombre] = {"tiene_xg": True, "ruta": ruta, "valor": valor}
        else:
            resultado[nombre] = {"tiene_xg": False}
    return resultado


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desde", type=int, default=2014, help="Primera temporada (año de inicio)")
    parser.add_argument("--hasta", type=int, default=date.today().year - 1, help="Última temporada (año de inicio)")
    parser.add_argument("--league-id", type=int, default=None, help="Id de La Liga (si se conoce)")
    parser.add_argument("--season", type=str, default=None, help="Temporada única (ej. 2025). Evita el rango.")
    parser.add_argument("--prueba", type=int, default=0, help="Descarga solo N partidos (prueba) y no escribe CSV")
    parser.add_argument("--raw", type=int, default=None, help="Vuelca el JSON crudo de /statistics de un match_id")
    parser.add_argument("--probe", type=int, default=None, help="Sondea statistics/match/boxscore y reporta donde esta el xG")
    parser.add_argument("--host", choices=["rapidapi", "directo"], default="rapidapi", help="Host a usar (rapidapi por defecto)")
    parser.add_argument("--confirm", action="store_true", help="Escribe el CSV (sin sobrescribir)")
    args = parser.parse_args()

    base_url = BASE_URL if args.host == "directo" else None
    rapidapi_host = None if args.host == "directo" else None
    try:
        cliente = HighlightlyClient(base_url=base_url, rapidapi_host=rapidapi_host)
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        print("Configura la clave antes de continuar. Ver ENV_EJEMPLO.md.")
        return 2

    if args.raw is not None:
        print(json.dumps(cliente.obtener_estadisticas(args.raw), ensure_ascii=False, indent=2))
        print("\nParsed xG:", parse_estadisticas(cliente.obtener_estadisticas(args.raw)))
        return 0

    if args.probe is not None:
        resumen = probar_endpoints(cliente, args.probe)
        print(f"Probe del match {args.probe} (donde esta el xG?):")
        for nombre, info in resumen.items():
            print(f"  {nombre:15} -> {info}")
        return 0

    if args.season:
        temporadas = [args.season]
    else:
        if args.desde > args.hasta:
            parser.error("--desde debe ser <= --hasta")
        temporadas = [str(a) for a in range(args.desde, args.hasta + 1)]

    league_id = args.league_id or localizar_la_liga(cliente).get("id")
    print(f"Usando league_id={league_id} ({NOMBRE_LIGA})")

    filas: list[dict] = []
    llamadas = 0
    for season in temporadas:
        filas_temporada = descargar_temporada(cliente, league_id, season, limite=args.prueba or None)
        llamadas += len(filas_temporada)
        filas.extend(filas_temporada)
        print(f"  temporada {season}: {len(filas_temporada)} partidos con estadísticas")
        if args.prueba and len(filas) >= args.prueba:
            break

    if args.prueba:
        print(f"\nPRUEBA: {len(filas)} partidos descargados (llamadas ~{llamadas}). No se escribió CSV.")
        for f in filas[:10]:
            print(f"  {f}")
        print("Si el xG sale como None, ejecuta --raw <match_id> para inspeccionar la respuesta.")
        return 0

    print(f"\nTotal: {len(filas)} partidos con estadísticas ({llamadas} llamadas a /statistics)")
    if args.confirm:
        if DEFAULT_SALIDA.exists():
            print(f"[abortado] {DEFAULT_SALIDA} ya existe. No se sobrescribe.")
            return 1
        DEFAULT_SALIDA.parent.mkdir(parents=True, exist_ok=True)
        with open(DEFAULT_SALIDA, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=TEMP_HDR, extrasaction="ignore")
            w.writeheader()
            for fila in filas:
                w.writerow(fila)
        print(f"CSV escrito: {DEFAULT_SALIDA}")
    else:
        print("Modo prueba de rango: usa --confirm para escribir el CSV.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
