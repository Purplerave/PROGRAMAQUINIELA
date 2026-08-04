#!/usr/bin/env python3
"""Descarga y audita el XML de una jornada desde quinielista.es.

El XML contiene la composición ordenada 1..15 y porcentajes publicados, pero no
incluye fecha real de cada partido, resultado final ni escrutinio. Por ello esta
herramienta lo almacena como evidencia externa *pendiente de enriquecer*; nunca
lo convierte por sí sola en un boleto histórico válido para QUINIELA_REAL.

Las descargas se guardan bajo ``salida/quinielista_raw`` (ignorado por Git) junto
con un manifiesto SHA-256, URL y hora de captura.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "salida" / "quinielista_raw"
URLS = {
    "lae": "https://www.quinielista.es/xml2/porcentajes_lae.asp?jornada={jornada}&temporada={temporada}",
    "publico": "https://www.quinielista.es/xml2/porcentajes.asp?jornada={jornada}&temporada={temporada}",
}
USER_AGENT = "PROGRAMAQUINIELA/1.0 (audited historical-ticket research)"


def parse_and_validate(xml_bytes: bytes, jornada: int, temporada: int) -> list[dict[str, str]]:
    """Comprueba identidad y estructura 1..15 sin asumir resultados futuros."""
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as exc:
        raise ValueError(f"XML inválido: {exc}") from exc
    percentages = root.find("porcentajes")
    if percentages is None:
        raise ValueError("XML sin elemento quinielista/porcentajes")
    if percentages.get("jornada") != str(jornada) or percentages.get("temporada") != str(temporada):
        raise ValueError(
            "La respuesta no corresponde a la jornada/temporada solicitada: "
            f"{percentages.get('jornada')}/{percentages.get('temporada')}"
        )
    matches = [dict(element.attrib) for element in percentages.findall("partido")]
    numbers = sorted(int(match.get("num", "0")) for match in matches)
    if numbers != list(range(1, 16)):
        raise ValueError(f"El XML debe traer exactamente partidos 1..15; recibió {numbers}")
    if any(not match.get("local") or not match.get("visitante") for match in matches):
        raise ValueError("Hay un partido sin equipo local o visitante")
    return sorted(matches, key=lambda match: int(match["num"]))


def fetch_xml(url: str, timeout: int = 20) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/xml,text/xml,*/*"})
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
            return response.read()
    except URLError as exc:
        raise RuntimeError(f"No se pudo descargar {url}: {exc.reason}") from exc


def write_evidence(
    xml_bytes: bytes,
    *,
    jornada: int,
    temporada: int,
    source: str,
    url: str,
    output_dir: Path = OUTPUT_DIR,
) -> tuple[Path, Path]:
    """Escribe XML y manifiesto de forma atómica sin sobrescribir evidencia."""
    matches = parse_and_validate(xml_bytes, jornada, temporada)
    output_dir = output_dir.resolve()
    if not output_dir.is_relative_to(OUTPUT_DIR.resolve()):
        raise ValueError(f"La salida debe estar bajo {OUTPUT_DIR}")
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"quinielista_{source}_{temporada}_J{jornada:02d}"
    xml_path = output_dir / f"{stem}.xml"
    manifest_path = output_dir / f"{stem}.manifest.json"
    if xml_path.exists() or manifest_path.exists():
        raise FileExistsError(f"Ya existe evidencia para {temporada}/J{jornada} ({source}); no se sobrescribe")
    digest = hashlib.sha256(xml_bytes).hexdigest()
    manifest = {
        "status": "pending_enrichment",
        "source": "quinielista.es",
        "source_variant": source,
        "url": url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sha256": digest,
        "season": temporada,
        "jornada": jornada,
        "matches": [{"number": int(match["num"]), "home": match["local"], "away": match["visitante"]} for match in matches],
        "limitations": [
            "XML no aporta fecha real por partido",
            "XML no aporta resultado final",
            "XML no aporta escrutinio o premios",
            "No es apto por sí solo para DATOS/quiniela_historica",
        ],
    }
    xml_path.write_bytes(xml_bytes)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return xml_path, manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jornada", type=int, required=True)
    parser.add_argument("--temporada", type=int, required=True, help="año final: 2026 representa 2025-26")
    parser.add_argument("--fuente", choices=tuple(URLS), default="lae")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()
    if args.jornada < 1 or args.temporada < 2000:
        parser.error("jornada y temporada no son válidas")
    url = URLS[args.fuente].format(jornada=args.jornada, temporada=args.temporada)
    try:
        xml_bytes = fetch_xml(url, timeout=args.timeout)
        xml_path, manifest_path = write_evidence(
            xml_bytes, jornada=args.jornada, temporada=args.temporada, source=args.fuente, url=url
        )
    except (RuntimeError, ValueError, FileExistsError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"Evidencia XML: {xml_path}")
    print(f"Manifiesto: {manifest_path}")
    print("Estado: pending_enrichment; faltan fechas, resultados y escrutinio para un backtest real.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
