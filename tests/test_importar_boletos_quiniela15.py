from __future__ import annotations

import json

import pandas as pd

from scripts.datos.IMPORTAR_BOLETOS_QUINIELA15 import canonical_team, import_tickets


def source_ticket() -> dict:
    matches = []
    for number in range(1, 16):
        matches.append({
            "num": number,
            "local": f"Local {number}",
            "visitante": f"Visitante {number}",
            "resultado": "2-1",
            "signo": "1" if number < 15 else "2-1",
        })
    return {
        "id": "Q15_2025_2026_J001", "jornada_q15": 1, "temporada": "2025-2026",
        "fuente": "Quiniela15/resultados-quiniela", "source_url": "https://example.test/1", "partidos": matches,
    }


def history() -> pd.DataFrame:
    return pd.DataFrame([
        {"date": pd.Timestamp("2025-08-15") + pd.Timedelta(days=number), "home": f"local {number}", "away": f"visitante {number}", "home_goals": 2, "away_goals": 1, "division": "Primera"}
        for number in range(1, 16)
    ])


def test_importer_creates_valid_proposal_with_derived_dates(tmp_path):
    (tmp_path / "Q15_2025_2026_J001.json").write_text(json.dumps(source_ticket()), encoding="utf-8")
    tickets, failures = import_tickets(tmp_path, "2025-2026", history())
    assert failures == []
    assert len(tickets) == 1
    assert len(tickets[0]["matches"]) == 14
    assert tickets[0]["matches"][0]["date"] == "2025-08-16"
    assert tickets[0]["pleno15"]["score"] == "2-1"


def test_importer_repairs_console_mojibake():
    assert canonical_team("AlavÃ©s") == "alaves"
