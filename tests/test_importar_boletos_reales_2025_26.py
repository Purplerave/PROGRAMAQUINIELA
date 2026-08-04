"""Integración del importador contra el histórico Football-Data real 2025-26.

Reconstruye un boleto sintético con la nomenclatura de Quiniela15 (alias
documentados, mojibake de consola y Pleno en bucket) a partir de partidos
reales de la temporada, y comprueba que el importador lo acepta completo y
con fechas derivadas. Es la verificación más cercana a los 9 JSON reales
(J001-J008, J010) disponible sin depender de la red ni de datos del usuario.
"""
from __future__ import annotations

import json

import pytest

from scripts.datos.IMPORTAR_BOLETOS_QUINIELA15 import (
    load_season_history,
    import_tickets,
    pleno_bucket_from_score,
    sign_from_goals,
)

# Nombre canónico Football-Data -> nombre usado por la fuente Quiniela15.
Q15_NAMES = {
    "vallecano": "Rayo",
    "sociedad": "R. Sociedad",
    "espanol": "Espanyol",
    "la coruna": "Deportivo",
    "sp gijon": "Sporting Gijón",
    "oviedo": "Real Oviedo",
    "zaragoza": "R. Zaragoza",
    "cultural leonesa": "C. Leonesa",
    "santander": "R. Santander",
    "ath bilbao": "Athletic",
    "ath madrid": "At Madrid",
    "sociedad b": "R. Sociedad B",
    "andorra": "Andorra",
    "alaves": "AlavÃ©s",
}


def q15_name(csv_name: str) -> str:
    return Q15_NAMES.get(csv_name, csv_name.title())


def real_history():
    try:
        return load_season_history("2025-2026")
    except (FileNotFoundError, ValueError) as exc:
        pytest.skip(f"Histórico real 2025-26 no disponible: {exc}")


def test_real_fixtures_2025_26_import_as_complete_ticket(tmp_path):
    history = real_history()
    rows = history.iloc[:15].reset_index(drop=True)
    matches = []
    for index, row in rows.iterrows():
        number = index + 1
        resultado = f"{row.home_goals}-{row.away_goals}"
        signo = sign_from_goals(int(row.home_goals), int(row.away_goals)) if number < 15 else pleno_bucket_from_score(int(row.home_goals), int(row.away_goals))
        matches.append({
            "num": number,
            "local": q15_name(row["home"]),
            "visitante": q15_name(row["away"]),
            "resultado": resultado,
            "signo": signo,
        })
    ticket = {
        "id": "Q15_2025_2026_J999", "jornada_q15": 999, "temporada": "2025-2026",
        "fuente": "Quiniela15/resultados-quiniela", "source_url": "https://www.quiniela15.com/resultados-quiniela/999",
        "partidos": matches,
    }
    (tmp_path / "Q15_2025_2026_J999.json").write_text(json.dumps(ticket), encoding="utf-8")
    result = import_tickets(tmp_path, "2025-2026", history)
    assert result["failures"] == []
    assert result["out_of_coverage"] == []
    assert len(result["tickets"]) == 1
    proposal = result["tickets"][0]
    assert proposal["draw_date"] == rows["date"].max().strftime("%Y-%m-%d")
    assert len(proposal["matches"]) == 14
    # El Pleno conserva el marcador exacto contrastado, no el bucket.
    assert proposal["pleno15"]["score"] == f"{int(rows.iloc[14].home_goals)}-{int(rows.iloc[14].away_goals)}"
    # El orden oficial 1..14 se mantiene.
    assert [match["number"] for match in proposal["matches"]] == list(range(1, 15))
