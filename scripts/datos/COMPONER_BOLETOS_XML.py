#!/usr/bin/env python3
"""Compone boletos evaluables desde los XML auditados de quinielista.es.

Los XML (variantes ``lae``/``publico``, ya descargados y auditados con SHA-256)
aportan la composición oficial LAE ordenada 1..15 (local/visitante) pero no
resultados. Este script une cada partido con Football-Data de la misma
temporada (coincidencia única local+visitante) y genera una propuesta con el
mismo esquema y clasificación que ``IMPORTAR_BOLETOS_QUINIELA15.py``:

- ``tickets``: los 15 partidos localizados en Football-Data (fecha y resultado
  derivados; composición según LAE vía quinielista.es);
- ``out_of_coverage``: jornadas con partidos fuera de Football-Data
  (competiciones europeas, internacionales, Copa…), detallados;
- ``failures``: coincidencias ambiguas u otros errores.

Procedencia: composición LAE (quinielista.es, XML con manifiesto SHA-256) +
resultados Football-Data. La salida sigue siendo
``proposal_not_official_lae``: sin escrutinio oficial por categoría no hay
boleto oficial completo ni ROI.

Uso:

    python scripts/datos/COMPONER_BOLETOS_XML.py
        [--xml-dir salida/quinielista_raw] [--temporada 2026]
        [--output salida/quiniela_historica_propuesta_xml_2025_2026.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

try:  # Funciona como módulo de tests y como script ejecutado directamente.
    from .DESCARGAR_QUINIELISTA_XML import OUTPUT_DIR, URLS, parse_and_validate
    from .IMPORTAR_BOLETOS_QUINIELA15 import (
        ROOT,
        canonical_team,
        classify_enriched,
        load_season_history,
        repair_mojibake,
        sign_from_goals,
    )
except ImportError:  # pragma: no cover - ruta de ejecución CLI
    from DESCARGAR_QUINIELISTA_XML import OUTPUT_DIR, URLS, parse_and_validate
    from IMPORTAR_BOLETOS_QUINIELA15 import (
        ROOT,
        canonical_team,
        classify_enriched,
        load_season_history,
        repair_mojibake,
        sign_from_goals,
    )


DEFAULT_XML_DIR = OUTPUT_DIR
DEFAULT_OUTPUT = ROOT / "salida" / "quiniela_historica_propuesta_xml_2025_2026.json"
MANIFEST_RE = re.compile(r"^quinielista_(lae|publico)_(\d{4})_J(\d{2})\.manifest\.json$")


def load_xml_jornadas(directory: Path, temporada: int) -> dict[int, dict[str, dict[str, Any]]]:
    """Carga las jornadas desde manifiestos válidos (XML + SHA-256).

    Devuelve ``{jornada: {"lae": {...}, "publico": {...}}}`` solo para las
    evidencias cuyo SHA-256 coincide con el manifiesto y cuya estructura 1..15
    es válida. Las evidencias rotas se ignoran (la auditoría las reporta).
    """
    directory = directory.resolve()
    found: dict[int, dict[str, dict[str, Any]]] = {}
    for manifest_path in sorted(directory.glob("*.manifest.json")):
        match = MANIFEST_RE.match(manifest_path.name)
        if not match:
            continue
        source, manifest_season, jornada_text = match.groups()
        if int(manifest_season) != temporada:
            continue
        jornada = int(jornada_text)
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            xml_path = manifest_path.with_name(manifest_path.name.replace(".manifest.json", ".xml"))
            xml_bytes = xml_path.read_bytes()
            if hashlib.sha256(xml_bytes).hexdigest() != manifest.get("sha256"):
                raise ValueError("SHA-256 del XML no coincide con el manifiesto")
            matches = parse_and_validate(xml_bytes, jornada, temporada)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        found.setdefault(jornada, {})[source] = {
            "matches": matches,
            "file": manifest_path.name,
            "url": manifest.get("url", ""),
        }
    return found


def build_source_tickets(jornadas: dict[int, dict[str, dict[str, Any]]], temporada: int, season: str) -> list[dict[str, Any]]:
    """Convierte las jornadas en boletos fuente (esquema del importador)."""
    tickets: list[dict[str, Any]] = []
    for jornada in sorted(jornadas):
        entry = jornadas[jornada]
        source = "lae" if "lae" in entry else "publico"
        data = entry[source]
        url = data.get("url") or URLS[source].format(jornada=jornada, temporada=temporada)
        tickets.append({
            "id": f"Q15XML_2025_2026_J{jornada:03d}",
            "jornada_q15": jornada,
            "temporada": season,
            "fuente": f"quinielista.es ({source}) composicion + Football-Data resultados",
            "source_url": url,
            "partidos": [
                {"num": int(match["num"]), "local": match["local"], "visitante": match["visitante"]}
                for match in data["matches"]
            ],
        })
    return tickets


def enrich_from_football_data(source_match: dict[str, Any], history: pd.DataFrame, ticket_id: str) -> dict[str, Any]:
    """Localiza un partido de la composición en Football-Data (sin resultados en el XML).

    Devuelve ``status: "matched"`` con fecha/resultado derivados, o
    ``status: "error"`` con el motivo exacto (``no_en_football_data`` para
    competiciones fuera del histórico o ``coincidencia_ambigua``).
    """
    num = source_match["num"]
    home, away = canonical_team(source_match["local"]), canonical_team(source_match["visitante"])
    context = f"{ticket_id} #{num} {source_match['local']} - {source_match['visitante']}"
    candidates = history[(history["home"] == home) & (history["away"] == away)]
    if len(candidates) != 1:
        motivo = "coincidencia_ambigua" if len(candidates) > 1 else "no_en_football_data"
        return {
            "status": "error", "num": num,
            "local": repair_mojibake(source_match["local"]),
            "visitante": repair_mojibake(source_match["visitante"]),
            "motivo": motivo,
            "detalle": f"{context}: coincidencias Football-Data={len(candidates)}",
        }
    row = candidates.iloc[0]
    return {
        "status": "matched",
        "date": row.date.strftime("%Y-%m-%d"),
        "home": repair_mojibake(source_match["local"]),
        "away": repair_mojibake(source_match["visitante"]),
        "score": f"{int(row.home_goals)}-{int(row.away_goals)}",
        "sign": sign_from_goals(int(row.home_goals), int(row.away_goals)),
        "division": row.division,
    }


def compose_tickets(
    source_tickets: list[dict[str, Any]],
    history: pd.DataFrame,
) -> dict[str, list[dict[str, Any]]]:
    """Clasifica los boletos compuestos con la misma semántica del importador."""
    result: dict[str, list[dict[str, Any]]] = {"tickets": [], "out_of_coverage": [], "failures": []}
    for payload in source_tickets:
        enriched = [enrich_from_football_data(match, history, str(payload["id"])) for match in payload["partidos"]]
        kind, record = classify_enriched(payload, payload["partidos"], enriched, str(payload["id"]) + ".xml")
        result[{"ticket": "tickets", "out_of_coverage": "out_of_coverage", "failure": "failures"}[kind]].append(record)
    result["tickets"].sort(key=lambda ticket: ticket["jornada"])
    return result


def diagnose_unmatched(out_of_coverage: list[dict[str, Any]], history: pd.DataFrame, sample: int = 12) -> None:
    """Imprime una muestra de partidos sin contrastar con su diagnóstico.

    Ayuda a localizar nombres de equipo del XML que no casan con Football-Data:
    muestra el nombre crudo, su clave canónica y cuántas veces esa clave aparece
    como local/visitante en el histórico cargado (0 = el nombre no se resuelve).
    """
    seen = 0
    for record in out_of_coverage:
        for match in record.get("unmatched", []):
            if seen >= sample:
                return
            home = canonical_team(match["local"])
            away = canonical_team(match["visitante"])
            print(
                f"  [{match['num']:>2}] {match['local']!r} ({home!r} -> local en CSV: "
                f"{(history['home'] == home).sum()}) | {match['visitante']!r} ({away!r} -> "
                f"visitante en CSV: {(history['away'] == away).sum()})"
            )
            seen += 1
    if not seen:
        print("  (sin partidos sin contrastar)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xml-dir", type=Path, default=DEFAULT_XML_DIR)
    parser.add_argument("--temporada", type=int, default=2026, help="año final: 2026 representa 2025-26")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not args.xml_dir.is_dir():
        print(f"No existe la carpeta de XML: {args.xml_dir}")
        return 1
    season = f"{args.temporada - 1}-{args.temporada}"
    jornadas = load_xml_jornadas(args.xml_dir, args.temporada)
    if not jornadas:
        print(f"No se encontraron manifiestos XML válidos en {args.xml_dir}")
        return 1
    source_tickets = build_source_tickets(jornadas, args.temporada, season)
    history = load_season_history(season)
    result = compose_tickets(source_tickets, history)
    tickets, out_of_coverage, failures = result["tickets"], result["out_of_coverage"], result["failures"]
    output = {
        "schema_version": "1.0",
        "source": {
            "name": "quinielista.es (lae/publico) composicion LAE + Football-Data resultados",
            "status": "proposal_not_official_lae",
            "xml_evidence": f"{args.xml_dir} (SHA-256 por manifiesto)",
        },
        "summary": {
            "total": len(tickets) + len(out_of_coverage) + len(failures),
            "accepted": len(tickets),
            "out_of_coverage": len(out_of_coverage),
            "rejected": len(failures),
        },
        "tickets": tickets,
        "out_of_coverage": out_of_coverage,
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Jornadas con XML válido: {len(source_tickets)}")
    print(f"Boletos compuestos y contrastados: {len(tickets)}")
    print(f"Fuera de cobertura Football-Data (p. ej. competiciones europeas): {len(out_of_coverage)}")
    print(f"Fallidos/inconsistentes: {len(failures)}")
    if out_of_coverage:
        print("Diagnóstico de nombres sin contrastar (muestra):")
        diagnose_unmatched(out_of_coverage, history)
    print(f"Propuesta: {args.output}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
