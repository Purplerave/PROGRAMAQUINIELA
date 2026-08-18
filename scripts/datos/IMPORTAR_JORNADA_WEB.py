#!/usr/bin/env python3
"""Une liga-maestros-web con el motor: convierte un scrape de jornada en DATOS/QUINIELA15_J{N}.json.

Problema que resuelve
---------------------
La web (`Purplerave/liga-maestros-web`) ya scrapea cada jornada a
``data/quiniela15_J{N}_scrape.json`` (15 partidos, horarios, porcentajes de la
comunidad de quiniela15 y marcadores del Pleno). El motor
(`Purplerave/PROGRAMAQUINIELA`) espera otro esquema en
``DATOS/QUINIELA15_J{N}.json`` (``odd_1/odd_x/odd_2``, ``q15``, ``lae`` y un
bloque ``pleno15``). Hasta ahora el puente se hacia a mano.

Este importador hace la conversion de forma reproducible y **sin inventar
datos**:

- Copia tal cual lo que la web ya trae: local, visitante, fecha, hora, ``q15``
  y los marcadores del Pleno al 15.
- Deduce ``division`` (Primera/Segunda) desde
  ``DATOS/temporada_2026_27_equipos.json``, no desde la ultima categoria
  conocida del historico (que en agosto todavia es la de la temporada
  anterior).
- Comprueba que los 30 nombres de equipo resuelven contra el historico y
  contra los priors 2026/27 (``scripts/motor/team_names``). Si alguno no
  resuelve, lo reporta: no lo silencia.
- Las cuotas reales (``odd_*``) y los porcentajes LAE **no** estan en el
  scrape. Se aportan aparte con ``--mercado``, un JSON con su propia
  ``fuente``/``consultado_en``. Si no se aporta, los campos quedan a ``null``
  y el importador avisa de que el ensemble perdera el componente de mercado
  (peso 0.951 en CONFIG_MOTOR_V2.json).

Uso
---
    python scripts/datos/IMPORTAR_JORNADA_WEB.py --jornada 2 \
        --mercado DATOS/mercado_jornada/MERCADO_J2.json

    python scripts/datos/IMPORTAR_JORNADA_WEB.py --jornada 2 \
        --scrape ../liga-maestros-web/data/quiniela15_J2_scrape.json --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import settings  # noqa: E402
from scripts.motor.team_names import (  # noqa: E402
    resolve_history_name,
    resolve_prior_name,
)

WEB_RAW_URL = (
    "https://raw.githubusercontent.com/Purplerave/liga-maestros-web/"
    "main/data/quiniela15_J{jornada}_scrape.json"
)
SIGNS = ("1", "X", "2")
PLENO_NUM = 15


# --- carga de fuentes ---------------------------------------------------------


def load_scrape(jornada: int, origen: str | None) -> tuple[dict[str, Any], str]:
    """Carga el scrape de la web desde ruta local o desde GitHub raw."""
    if origen is None:
        origen = WEB_RAW_URL.format(jornada=jornada)
    if origen.startswith("http://") or origen.startswith("https://"):
        try:
            with urllib.request.urlopen(origen, timeout=30) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8")), origen
        except OSError as exc:  # sin salida a internet, proxy, etc.
            raise SystemExit(
                f"No se pudo descargar {origen}: {exc}\n"
                "Descargue el fichero a mano y pase la ruta con --scrape, por ejemplo:\n"
                "  gh api repos/Purplerave/liga-maestros-web/contents/data/"
                f"quiniela15_J{jornada}_scrape.json --jq .content | base64 -d "
                f"> salida/quiniela15_J{jornada}_scrape.json"
            ) from exc
    path = Path(origen)
    if not path.exists():
        raise FileNotFoundError(f"No existe el scrape: {path}")
    return json.loads(path.read_text(encoding="utf-8")), str(path)


def load_mercado(path_str: str | None) -> tuple[dict[int, dict[str, Any]], dict[str, Any]]:
    """Carga el overlay de mercado (cuotas reales + LAE) indexado por num."""
    if not path_str:
        return {}, {}
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"No existe el fichero de mercado: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    by_num = {int(item["num"]): item for item in data.get("partidos", [])}
    meta = {k: v for k, v in data.items() if k != "partidos"}
    return by_num, meta


def division_index() -> dict[str, str]:
    """Nombre canonico de priors -> 'Primera' / 'Segunda' para 2026/27."""
    path = settings.DATOS_DIR / "temporada_2026_27_equipos.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    index: dict[str, str] = {}
    for entry in data.get("laliga_ea_sports", []):
        index[entry["team"]] = "Primera"
    for entry in data.get("laliga_hypermotion", []):
        index[entry["team"]] = "Segunda"
    return index


# --- conversion ---------------------------------------------------------------


def _pct_block(value: Any) -> dict[str, int] | None:
    """Normaliza un bloque de porcentajes {1,X,2}; devuelve None si falta algo."""
    if not isinstance(value, dict):
        return None
    out: dict[str, int] = {}
    for sign in SIGNS:
        raw = value.get(sign)
        if raw in (None, ""):
            return None
        out[sign] = int(round(float(raw)))
    return out


def _match_division(local: str, visitante: str, div_index: dict[str, str]) -> tuple[str | None, list[str]]:
    warnings: list[str] = []
    divisions = []
    for side, name in (("local", local), ("visitante", visitante)):
        canonical = resolve_prior_name(name)
        div = div_index.get(canonical) if canonical else None
        if div is None:
            warnings.append(f"sin division 2026/27 para {side} {name!r}")
        divisions.append(div)
    if divisions[0] and divisions[1] and divisions[0] != divisions[1]:
        warnings.append(
            f"division incoherente {local!r}={divisions[0]} vs {visitante!r}={divisions[1]}"
        )
        return None, warnings
    return divisions[0] or divisions[1], warnings


def convert(
    scrape: dict[str, Any],
    jornada: int,
    mercado: dict[int, dict[str, Any]],
    mercado_meta: dict[str, Any],
    origen: str,
) -> tuple[dict[str, Any], list[str]]:
    """Convierte el scrape de la web al esquema DATOS/QUINIELA15_J{N}.json."""
    warnings: list[str] = []
    div_index = division_index()
    partidos_in = scrape.get("partidos", [])
    if len(partidos_in) != 15:
        warnings.append(f"el scrape trae {len(partidos_in)} partidos, se esperaban 15")

    partidos_out: list[dict[str, Any]] = []
    sin_cuotas: list[int] = []

    for raw in partidos_in:
        num = int(raw["num"])
        local = str(raw.get("local") or "").strip()
        visitante = str(raw.get("visitante") or "").strip()

        for side, name in (("local", local), ("visitante", visitante)):
            if resolve_prior_name(name) is None:
                warnings.append(
                    f"partido {num}: {side} {name!r} no resuelve contra los priors 2026/27"
                )

        division, div_warnings = _match_division(local, visitante, div_index)
        warnings.extend(f"partido {num}: {w}" for w in div_warnings)

        item: dict[str, Any] = {
            "num": num,
            "local": local,
            "visitante": visitante,
            "division": division,
            "fecha": raw.get("fecha"),
            "hora": raw.get("hora"),
        }

        mkt = mercado.get(num, {})
        odds = {key: mkt.get(key) for key in ("odd_1", "odd_x", "odd_2")}
        if all(isinstance(v, (int, float)) and v > 1 for v in odds.values()):
            item.update({k: float(v) for k, v in odds.items()})
        else:
            item.update({"odd_1": None, "odd_x": None, "odd_2": None})
            sin_cuotas.append(num)

        item["historico_equipo"] = {
            "local": resolve_history_name(local),
            "visitante": resolve_history_name(visitante),
        }

        if num == PLENO_NUM:
            marcadores = raw.get("marcadores_q15") or []
            item["marcadores_q15"] = marcadores
            pleno: dict[str, Any] = {
                "marcador_q15": {
                    str(m.get("score")): m.get("pct")
                    for m in marcadores
                    if m.get("score")
                },
            }
            for key in ("goles_local_lae", "goles_visitante_lae"):
                if isinstance(mkt.get(key), dict):
                    pleno[key] = mkt[key]
            item["pleno15"] = pleno
        else:
            q15 = _pct_block(raw.get("q15"))
            item["q15"] = q15
            if q15 is None:
                warnings.append(f"partido {num}: sin porcentajes q15 en el scrape")
            item["lae"] = _pct_block(mkt.get("lae"))

        partidos_out.append(item)

    if sin_cuotas:
        warnings.append(
            "sin cuotas reales en los partidos "
            + ", ".join(str(n) for n in sin_cuotas)
            + ": el ensemble se quedara solo con el componente HGB "
            "(market pesa 0.951 en CONFIG_MOTOR_V2.json)"
        )

    out = {
        "jornada": jornada,
        "source_url": scrape.get("source_url"),
        "scraped_at": scrape.get("scraped_at"),
        "cierre": scrape.get("cierre"),
        "importado_de": origen,
        "importador": "scripts/datos/IMPORTAR_JORNADA_WEB.py",
        "fuentes": {
            "partidos_horarios_q15": {
                "repo": "Purplerave/liga-maestros-web",
                "fichero": f"data/quiniela15_J{jornada}_scrape.json",
                "sitio": scrape.get("source_url"),
                "scraped_at": scrape.get("scraped_at"),
            },
            "division_2026_27": "DATOS/temporada_2026_27_equipos.json",
            "mercado": mercado_meta or None,
        },
        "notas": [
            "q15 = porcentajes de la comunidad de quiniela15.com (proxy de publico).",
            "lae y odd_* proceden del overlay de mercado; nunca se derivan de q15.",
            "division se toma de la composicion oficial 2026/27, no del historico.",
        ],
        "partidos": partidos_out,
    }
    return out, warnings


# --- CLI ----------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Importa una jornada de liga-maestros-web al formato del motor."
    )
    parser.add_argument("--jornada", "-j", type=int, required=True)
    parser.add_argument(
        "--scrape",
        default=None,
        help="ruta local o URL del quiniela15_J{N}_scrape.json (por defecto, GitHub raw)",
    )
    parser.add_argument(
        "--mercado",
        default=None,
        help="JSON con cuotas reales (odd_1/odd_x/odd_2) y porcentajes LAE por partido",
    )
    parser.add_argument("--dry-run", action="store_true", help="no escribe el fichero")
    args = parser.parse_args()

    scrape, origen = load_scrape(args.jornada, args.scrape)
    mercado, mercado_meta = load_mercado(args.mercado)
    payload, warnings = convert(scrape, args.jornada, mercado, mercado_meta, origen)

    destino = settings.DATOS_DIR / f"QUINIELA15_J{args.jornada}.json"
    if not args.dry_run:
        destino.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    con_cuotas = sum(1 for p in payload["partidos"] if p.get("odd_1"))
    con_lae = sum(1 for p in payload["partidos"] if p.get("lae"))
    print(f"origen   : {origen}")
    print(f"destino  : {destino}{' (dry-run, no escrito)' if args.dry_run else ''}")
    print(f"partidos : {len(payload['partidos'])}")
    print(f"cuotas   : {con_cuotas}/15")
    print(f"lae      : {con_lae}/14")
    if warnings:
        print("avisos:")
        for w in warnings:
            print(f"  - {w}")
    else:
        print("avisos: ninguno")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
