#!/usr/bin/env python3
"""Audita una colección local de XML de quinielista.es sin alterar el histórico.

Verifica hashes, identidad temporada/jornada, posiciones 1..15 y coherencia entre
las variantes ``lae`` y ``publico``. Produce un informe JSON reproducible; no
convierte los XML en boletos históricos porque aún faltan fechas, resultados y
escrutinios.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

try:  # Funciona como módulo de tests y como script ejecutado directamente.
    from .DESCARGAR_QUINIELISTA_XML import OUTPUT_DIR, parse_and_validate
except ImportError:  # pragma: no cover - ruta de ejecución CLI
    from DESCARGAR_QUINIELISTA_XML import OUTPUT_DIR, parse_and_validate


DEFAULT_REPORT = OUTPUT_DIR / "auditoria_quinielista_2026.json"
NAME_RE = re.compile(r"^quinielista_(lae|publico)_(\d{4})_J(\d{2})\.manifest\.json$")


def audit_directory(directory: Path, season: int, expected_jornadas: range) -> dict[str, Any]:
    directory = directory.resolve()
    found: dict[tuple[int, str], dict[str, Any]] = {}
    issues: list[dict[str, str]] = []
    hash_counts: Counter[str] = Counter()

    for manifest_path in sorted(directory.glob("*.manifest.json")):
        match = NAME_RE.match(manifest_path.name)
        if not match:
            continue
        source, manifest_season, jornada_text = match.groups()
        if int(manifest_season) != season:
            continue
        jornada = int(jornada_text)
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            xml_path = manifest_path.with_name(manifest_path.name.replace(".manifest.json", ".xml"))
            if not xml_path.is_file():
                raise ValueError("XML ausente")
            xml_bytes = xml_path.read_bytes()
            sha256 = hashlib.sha256(xml_bytes).hexdigest()
            if manifest.get("sha256") != sha256:
                raise ValueError("SHA-256 del XML no coincide con el manifiesto")
            matches = parse_and_validate(xml_bytes, jornada, season)
            if manifest.get("season") != season or manifest.get("jornada") != jornada:
                raise ValueError("temporada/jornada del manifiesto no coincide con el nombre")
            key = (jornada, source)
            if key in found:
                raise ValueError("manifiesto duplicado")
            found[key] = {"matches": matches, "sha256": sha256, "manifest": manifest_path.name}
            hash_counts[sha256] += 1
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            issues.append({"file": manifest_path.name, "error": str(exc)})

    expected = {(jornada, source) for jornada in expected_jornadas for source in ("lae", "publico")}
    missing = [
        {"jornada": jornada, "source": source}
        for jornada, source in sorted(expected - set(found))
    ]
    discrepancies: list[dict[str, Any]] = []
    for jornada in expected_jornadas:
        lae = found.get((jornada, "lae"))
        publico = found.get((jornada, "publico"))
        if not lae or not publico:
            continue
        lae_pairs = [(item["num"], item["local"], item["visitante"]) for item in lae["matches"]]
        public_pairs = [(item["num"], item["local"], item["visitante"]) for item in publico["matches"]]
        if lae_pairs != public_pairs:
            discrepancies.append({"jornada": jornada, "reason": "fixtures_differ_between_sources"})

    duplicate_payloads = [
        {"sha256": digest, "copies": count}
        for digest, count in hash_counts.items() if count > 1
    ]
    return {
        "season": season,
        "expected_jornadas": [min(expected_jornadas), max(expected_jornadas)],
        "expected_xml": len(expected),
        "valid_xml": len(found),
        "missing": missing,
        "invalid": issues,
        "fixture_discrepancies": discrepancies,
        "duplicate_xml_payloads": duplicate_payloads,
        "status": "ready_for_enrichment" if not missing and not issues and not discrepancies else "incomplete_or_inconsistent",
        "limitations": [
            "Las fuentes XML no incluyen fecha de partido, resultado final ni escrutinio",
            "El informe no autoriza un backtest de boleto real ni cálculo de ROI",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--first-jornada", type=int, default=1)
    parser.add_argument("--last-jornada", type=int, default=75)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    jornadas = range(args.first_jornada, args.last_jornada + 1)
    report = audit_directory(args.directory, args.season, jornadas)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"XML válidos: {report['valid_xml']}/{report['expected_xml']}")
    print(f"Faltantes: {len(report['missing'])} | Inválidos: {len(report['invalid'])} | Fixtures distintos: {len(report['fixture_discrepancies'])}")
    print(f"Estado: {report['status']}")
    print(f"Informe: {args.report}")
    return 0 if report["status"] == "ready_for_enrichment" else 1


if __name__ == "__main__":
    raise SystemExit(main())
