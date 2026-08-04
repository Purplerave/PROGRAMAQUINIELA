"""Tests del compositor de boletos desde XML de quinielista.es + Football-Data."""
from __future__ import annotations

import hashlib
import json
from xml.etree import ElementTree as ET

import pandas as pd

from scripts.datos.COMPONER_BOLETOS_XML import (
    build_source_tickets,
    compose_tickets,
    enrich_from_football_data,
    load_xml_jornadas,
)


def xml_bytes(jornada: int, temporada: int, local_visitante: list[tuple[str, str]]) -> bytes:
    root = ET.Element("quinielista")
    porcentajes = ET.SubElement(root, "porcentajes", {"jornada": str(jornada), "temporada": str(temporada)})
    for num, (local, visitante) in enumerate(local_visitante, start=1):
        ET.SubElement(porcentajes, "partido", {
            "num": str(num), "local": local, "visitante": visitante,
            "uno": "40.0", "equis": "35.0", "dos": "25.0",
        })
    return ET.tostring(root, encoding="utf-8")


def write_evidence(tmp_path, jornada: int, temporada: int, source: str, local_visitante: list[tuple[str, str]], tamper: bool = False):
    data = xml_bytes(jornada, temporada, local_visitante)
    if tamper:
        data = data.replace(b"</porcentajes>", b"<extra/> </porcentajes>")  # cambia el SHA sin romper el XML
    stem = f"quinielista_{source}_{temporada}_J{jornada:02d}"
    (tmp_path / f"{stem}.xml").write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    if tamper:
        digest = "0" * 64  # SHA del manifiesto no coincide con el XML
    manifest = {
        "status": "pending_enrichment", "source": "quinielista.es", "source_variant": source,
        "url": f"https://www.quinielista.es/xml2/porcentajes_lae.asp?jornada={jornada}&temporada={temporada}",
        "retrieved_at": "2026-08-04T12:00:00+00:00",
        "sha256": digest,
        "season": temporada, "jornada": jornada,
        "matches": [{"number": n, "home": h, "away": a} for n, (h, a) in enumerate(local_visitante, start=1)],
    }
    (tmp_path / f"{stem}.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def synthetic_history(n_jornadas: int) -> pd.DataFrame:
    rows = []
    for jornada in range(1, n_jornadas + 1):
        for number in range(1, 16):
            rows.append({
                "date": pd.Timestamp("2025-08-15") + pd.Timedelta(days=20 * (jornada - 1) + number),
                "home": f"local {number}", "away": f"visitante {number}",
                "home_goals": 2, "away_goals": 1, "division": "Primera",
            })
    return pd.DataFrame(rows)


def test_load_xml_jornadas_only_accepts_valid_evidence(tmp_path):
    write_evidence(tmp_path, 1, 2026, "lae", [(f"Local {n}", f"Visitante {n}") for n in range(1, 16)])
    write_evidence(tmp_path, 2, 2026, "lae", [(f"Local {n}", f"Visitante {n}") for n in range(1, 16)], tamper=True)
    jornadas = load_xml_jornadas(tmp_path, 2026)
    assert list(jornadas) == [1]  # la J2 tiene SHA alterado y se descarta
    assert "lae" in jornadas[1]


def test_compose_tickets_from_xml_creates_proposal(tmp_path):
    write_evidence(tmp_path, 1, 2026, "lae", [(f"Local {n}", f"Visitante {n}") for n in range(1, 16)])
    jornadas = load_xml_jornadas(tmp_path, 2026)
    source_tickets = build_source_tickets(jornadas, 2026, "2025-2026")
    assert source_tickets[0]["id"] == "Q15XML_2025_2026_J001"
    assert len(source_tickets[0]["partidos"]) == 15
    result = compose_tickets(source_tickets, synthetic_history(1))
    assert result["failures"] == []
    assert result["out_of_coverage"] == []
    assert len(result["tickets"]) == 1
    proposal = result["tickets"][0]
    assert proposal["ticket_id"] == "Q15XML_2025_2026_J001"
    assert len(proposal["matches"]) == 14
    assert [match["number"] for match in proposal["matches"]] == list(range(1, 15))
    assert proposal["pleno15"]["score"] == "2-1"


def test_compose_reports_foreign_match_as_out_of_coverage(tmp_path):
    partidos = [(f"Local {n}", f"Visitante {n}") for n in range(1, 16)]
    partidos[9] = ("Athletic", "Arsenal")
    write_evidence(tmp_path, 4, 2026, "lae", partidos)
    jornadas = load_xml_jornadas(tmp_path, 2026)
    result = compose_tickets(build_source_tickets(jornadas, 2026, "2025-2026"), synthetic_history(1))
    assert result["tickets"] == []
    assert len(result["out_of_coverage"]) == 1
    record = result["out_of_coverage"][0]
    assert record["matches_covered"] == 14
    assert record["matches_total"] == 15
    assert record["unmatched"] == [{"num": 10, "local": "Athletic", "visitante": "Arsenal", "motivo": "no_en_football_data"}]


def test_enrich_from_football_data_resolves_lae_style_names():
    history = pd.DataFrame([{
        "date": pd.Timestamp("2025-08-16"), "home": "ath bilbao", "away": "arsenal",
        "home_goals": 2, "away_goals": 1, "division": "Primera",
    }])
    match = {"num": 3, "local": "Athletic Club", "visitante": "Arsenal"}
    enriched = enrich_from_football_data(match, history, "Q15XML_J003")
    assert enriched["status"] == "matched"
    assert enriched["home"] == "Athletic Club"
    assert enriched["sign"] == "1"
    assert enriched["division"] == "Primera"


def test_prefers_lae_variant_when_both_exist(tmp_path):
    partidos = [(f"Local {n}", f"Visitante {n}") for n in range(1, 16)]
    write_evidence(tmp_path, 1, 2026, "lae", partidos)
    write_evidence(tmp_path, 1, 2026, "publico", partidos)
    jornadas = load_xml_jornadas(tmp_path, 2026)
    source_tickets = build_source_tickets(jornadas, 2026, "2025-2026")
    assert len(source_tickets) == 1
    assert "lae" in source_tickets[0]["fuente"]
