from __future__ import annotations

import json

import pandas as pd

from scripts.backtests.QUINIELA_REAL import validate_ticket
from scripts.datos.IMPORTAR_BOLETOS_QUINIELA15 import canonical_team, import_tickets, pleno_bucket_from_score, pleno_bucket_from_source


def source_ticket(prefix: str = "Local", pleno_score: str = "2-1") -> dict:
    pleno_signo = pleno_bucket_from_source(pleno_score) or "2-1"
    matches = []
    for number in range(1, 16):
        matches.append({
            "num": number,
            "local": f"{prefix} {number}",
            "visitante": f"Visitante {number}",
            "resultado": "2-1" if number < 15 else pleno_score,
            "signo": "1" if number < 15 else pleno_signo,
        })
    return {
        "id": "Q15_2025_2026_J001", "jornada_q15": 1, "temporada": "2025-2026",
        "fuente": "Quiniela15/resultados-quiniela", "source_url": "https://example.test/1", "partidos": matches,
    }


def history(pleno_home: int = 2, pleno_away: int = 1) -> pd.DataFrame:
    rows = []
    for number in range(1, 16):
        home_goals, away_goals = (pleno_home, pleno_away) if number == 15 else (2, 1)
        rows.append({
            "date": pd.Timestamp("2025-08-15") + pd.Timedelta(days=number),
            "home": f"local {number}", "away": f"visitante {number}",
            "home_goals": home_goals, "away_goals": away_goals, "division": "Primera",
        })
    return pd.DataFrame(rows)


def write_ticket(tmp_path, ticket: dict, name: str = "Q15_2025_2026_J001.json") -> None:
    (tmp_path / name).write_text(json.dumps(ticket), encoding="utf-8")


def test_importer_creates_valid_proposal_with_derived_dates(tmp_path):
    write_ticket(tmp_path, source_ticket())
    result = import_tickets(tmp_path, "2025-2026", history())
    assert result["failures"] == []
    assert result["out_of_coverage"] == []
    assert len(result["tickets"]) == 1
    assert len(result["tickets"][0]["matches"]) == 14
    assert result["tickets"][0]["matches"][0]["date"] == "2025-08-16"
    assert result["tickets"][0]["pleno15"]["score"] == "2-1"


def test_importer_reports_out_of_coverage_ticket_with_unmatched_detail(tmp_path):
    ticket = source_ticket()
    ticket["partidos"][6] = {
        "num": 7, "local": "Athletic", "visitante": "Arsenal", "resultado": "2-1", "signo": "1",
    }
    write_ticket(tmp_path, ticket)
    result = import_tickets(tmp_path, "2025-2026", history())
    assert result["tickets"] == []
    assert result["failures"] == []
    assert len(result["out_of_coverage"]) == 1
    record = result["out_of_coverage"][0]
    assert record["reason"] == "out_of_coverage"
    assert record["ticket_id"] == "Q15_2025_2026_J001"
    assert record["matches_covered"] == 14
    assert record["matches_total"] == 15
    assert record["unmatched"] == [
        {"num": 7, "local": "Athletic", "visitante": "Arsenal", "motivo": "no_en_football_data"}
    ]


def test_importer_rejects_inconsistent_score_with_exact_reason(tmp_path):
    ticket = source_ticket()
    ticket["partidos"][2] = {
        "num": 3, "local": "Local 3", "visitante": "Visitante 3", "resultado": "0-0", "signo": "X",
    }
    write_ticket(tmp_path, ticket)
    result = import_tickets(tmp_path, "2025-2026", history())
    assert result["tickets"] == []
    assert result["out_of_coverage"] == []
    assert len(result["failures"]) == 1
    failure = result["failures"][0]
    assert failure["reason"] == "inconsistent"
    assert failure["match_errors"][0]["motivo"] == "marcador_inconsistente"
    assert "marcador fuente=0-0 != Football-Data=2-1" in failure["error"]


def test_importer_rejects_ambiguous_match_with_reason(tmp_path):
    ticket = source_ticket()
    # Dos filas candidatas para el mismo par local/visitante -> ambigüedad.
    history = pd.DataFrame([
        {"date": pd.Timestamp("2025-08-15") + pd.Timedelta(days=number), "home": f"local {number}", "away": f"visitante {number}", "home_goals": 2, "away_goals": 1, "division": "Primera"}
        for number in range(1, 16)
    ])
    duplicate = history.iloc[0].copy()
    duplicate["date"] = pd.Timestamp("2026-01-01")
    history = pd.concat([history, pd.DataFrame([duplicate])], ignore_index=True)
    write_ticket(tmp_path, ticket)
    result = import_tickets(tmp_path, "2025-2026", history)
    assert len(result["failures"]) == 1
    failure = result["failures"][0]
    assert failure["reason"] == "inconsistent"
    assert failure["match_errors"][0]["motivo"] == "coincidencia_ambigua"


def test_pleno_accepts_exact_score_or_bucket_in_resultado(tmp_path):
    # El Pleno de la temporada sintética es 3-2 -> bucket M-2.
    season = history(pleno_home=3, pleno_away=2)
    # signo en bucket y resultado exacto -> aceptado.
    ticket = source_ticket(pleno_score="3-2")
    write_ticket(tmp_path, ticket)
    result = import_tickets(tmp_path, "2025-2026", season)
    assert result["failures"] == []
    assert len(result["tickets"]) == 1

    # signo en bucket y resultado también en bucket (M-2) -> aceptado.
    segundo = tmp_path / "bucket"
    segundo.mkdir()
    ticket = source_ticket(pleno_score="M-2")
    write_ticket(segundo, ticket, name="Q15_2025_2026_J002.json")
    result = import_tickets(segundo, "2025-2026", season)
    assert result["failures"] == []
    assert len(result["tickets"]) == 1
    assert result["tickets"][0]["pleno15"]["score"] == "3-2"


def test_pleno_bucket_rejects_incoherent_bucket(tmp_path):
    ticket = source_ticket(pleno_score="M-2")
    # El marcador en bucket es coherente con Football-Data (M-2), pero el signo
    # declara otro bucket (1-1): el boleto debe ir a failures por signo.
    ticket["partidos"][14]["signo"] = "1-1"
    write_ticket(tmp_path, ticket)
    result = import_tickets(tmp_path, "2025-2026", history())
    assert len(result["failures"]) == 1
    assert result["failures"][0]["reason"] == "inconsistent"
    assert result["failures"][0]["match_errors"][0]["motivo"] == "signo_inconsistente"


def test_pleno_bucket_from_source_forms():
    assert pleno_bucket_from_source("1-1") == "1-1"
    assert pleno_bucket_from_source("M-2") == "M-2"
    assert pleno_bucket_from_source("2-1") == "2-1"
    assert pleno_bucket_from_source("3-3") == "M-M"
    assert pleno_bucket_from_source("") is None
    assert pleno_bucket_from_source("2X1") is None
    assert pleno_bucket_from_source("M-X") is None


def test_proposal_ticket_meets_quiniela_real_schema(tmp_path):
    """La propuesta aceptada debe poder validarse con el backtest de boletos reales."""
    write_ticket(tmp_path, source_ticket(pleno_score="M-2"))
    result = import_tickets(tmp_path, "2025-2026", history(pleno_home=3, pleno_away=2))
    proposal = result["tickets"][0]
    validate_ticket(proposal)  # no debe lanzar


def test_importer_repairs_console_mojibake_and_known_ticket_aliases():
    assert canonical_team("AlavÃ©s") == "alaves"
    assert canonical_team("Rayo") == "vallecano"
    assert canonical_team("R. Sociedad") == "sociedad"
    assert canonical_team("Sporting GijÃ³n") == "sp gijon"
    assert canonical_team("C. Leonesa") == "cultural leonesa"
    assert canonical_team("R. Sociedad B") == "sociedad b"


def test_lae_style_aliases_resolve_to_football_data_teams():
    # Nombres oficiales estilo LAE / quinielista.es -> CSV Football-Data.
    assert canonical_team("Athletic Club") == "ath bilbao"
    assert canonical_team("Atlético de Madrid") == "ath madrid"
    assert canonical_team("F.C. Barcelona") == "barcelona"
    assert canonical_team("Real Betis Balompié") == "betis"
    assert canonical_team("R.C.D. Espanyol de Barcelona") == "espanol"
    assert canonical_team("Real Sociedad") == "sociedad"
    assert canonical_team("Real Sociedad B") == "sociedad b"
    assert canonical_team("Real Sporting de Gijón") == "sp gijon"
    assert canonical_team("RC Deportivo") == "la coruna"
    assert canonical_team("Deportivo de La Coruña") == "la coruna"
    assert canonical_team("Racing de Santander") == "santander"
    assert canonical_team("Real Valladolid C.F.") == "valladolid"
    assert canonical_team("Cultural y Deportiva Leonesa") == "cultural leonesa"
    assert canonical_team("Real Zaragoza") == "zaragoza"
    assert canonical_team("C.D. Leganés") == "leganes"
    assert canonical_team("U.D. Las Palmas") == "las palmas"
    assert canonical_team("Cádiz C.F.") == "cadiz"
    assert canonical_team("Málaga C.F.") == "malaga"


def test_pleno_bucket_uses_hyphen_with_m_marker():
    assert pleno_bucket_from_score(1, 1) == "1-1"
    assert pleno_bucket_from_score(3, 2) == "M-2"
    assert pleno_bucket_from_score(4, 5) == "M-M"
