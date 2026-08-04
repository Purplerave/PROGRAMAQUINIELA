from __future__ import annotations

import json

from scripts.datos.AUDITAR_QUINIELISTA_XML import audit_directory
from scripts.datos.DESCARGAR_QUINIELISTA_XML import write_evidence


def xml_fixture(jornada: int, temporada: int, local_prefix: str = "Local") -> bytes:
    matches = "".join(
        f'<partido num="{number}" local="{local_prefix} {number}" visitante="Visitante {number}"/>'
        for number in range(1, 16)
    )
    return f'<quinielista><porcentajes jornada="{jornada}" temporada="{temporada}">{matches}</porcentajes></quinielista>'.encode()


def write_source(tmp_path, monkeypatch, jornada: int, source: str, prefix: str = "Local"):
    from scripts.datos import DESCARGAR_QUINIELISTA_XML as downloader

    monkeypatch.setattr(downloader, "OUTPUT_DIR", tmp_path)
    return write_evidence(
        xml_fixture(jornada, 2026, prefix), jornada=jornada, temporada=2026,
        source=source, url="https://example.test/xml", output_dir=tmp_path,
    )


def test_audit_reports_missing_source_and_only_marks_ready_when_complete(tmp_path, monkeypatch):
    write_source(tmp_path, monkeypatch, 1, "lae")
    write_source(tmp_path, monkeypatch, 1, "publico")
    report = audit_directory(tmp_path, 2026, range(1, 3))
    assert report["valid_xml"] == 2
    assert report["missing"] == [{"jornada": 2, "source": "lae"}, {"jornada": 2, "source": "publico"}]
    assert report["status"] == "incomplete_or_inconsistent"


def test_audit_detects_fixture_disagreement_and_sha_tampering(tmp_path, monkeypatch):
    xml_path, _ = write_source(tmp_path, monkeypatch, 1, "lae")
    write_source(tmp_path, monkeypatch, 1, "publico", prefix="Otro local")
    report = audit_directory(tmp_path, 2026, range(1, 2))
    assert report["fixture_discrepancies"] == [{"jornada": 1, "reason": "fixtures_differ_between_sources"}]

    xml_path.write_bytes(b"not xml")
    report = audit_directory(tmp_path, 2026, range(1, 2))
    assert len(report["invalid"]) == 1
    assert "SHA-256" in report["invalid"][0]["error"]
