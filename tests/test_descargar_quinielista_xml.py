from __future__ import annotations

import json

import pytest

from scripts.datos.DESCARGAR_QUINIELISTA_XML import parse_and_validate, write_evidence


def xml_fixture() -> bytes:
    matches = "\n".join(
        f'<partido num="{number}" local="Local {number}" visitante="Visitante {number}" porc_1="40" porc_X="30" porc_2="30"/>'
        for number in range(1, 16)
    )
    return f'<quinielista><porcentajes jornada="44" temporada="2026">{matches}</porcentajes></quinielista>'.encode()


def test_xml_validation_requires_all_fifteen_positions():
    matches = parse_and_validate(xml_fixture(), 44, 2026)
    assert len(matches) == 15
    assert matches[0]["local"] == "Local 1"

    broken = xml_fixture().replace(b'num="15"', b'num="16"')
    with pytest.raises(ValueError, match="1..15"):
        parse_and_validate(broken, 44, 2026)


def test_download_evidence_stores_hash_and_never_claims_ticket_validity(tmp_path, monkeypatch):
    # El escritor restringe las salidas al directorio de evidencia de producción.
    from scripts.datos import DESCARGAR_QUINIELISTA_XML as downloader

    output = tmp_path / "quinielista_raw"
    monkeypatch.setattr(downloader, "OUTPUT_DIR", output)
    xml_path, manifest_path = write_evidence(
        xml_fixture(), jornada=44, temporada=2026, source="lae", url="https://example.test/xml", output_dir=output
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert xml_path.is_file()
    assert manifest["status"] == "pending_enrichment"
    assert len(manifest["matches"]) == 15
    assert "resultado final" in manifest["limitations"][1]

    with pytest.raises(FileExistsError):
        write_evidence(xml_fixture(), jornada=44, temporada=2026, source="lae", url="https://example.test/xml", output_dir=output)
