"""Tests del evaluador de aciertos reales sobre boletos oficiales.

Usan un DataFrame de predicciones sintético y boletos con nombres estilo
Quiniela15 para ejercitar el cruce por alias sin ejecutar el motor.
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.backtests.EVALUAR_ACIERTOS_BOLETOS import evaluate_ticket_results, key_name

CONFIG = {
    "double_draw_threshold": 0.3,
    "double_draw_weight": 0.2,
    "double_disagreement_weight": 0.2,
    "double_segunda_bonus": 0.1,
}

PRIMERA_PROBS = (0.45, 0.35, 0.20)  # doble 1X
SEGURA_PROBS = (0.60, 0.25, 0.15)   # doble 1X


def base_ticket() -> dict:
    matches = []
    for number in range(1, 15):
        local = "Rayo" if number == 1 else "Athletic" if number == 2 else f"Local {number}"
        visitante = f"Visitante {number}"
        matches.append({
            "number": number,
            "date": f"2025-08-{14 + number:02d}",
            "home": local,
            "away": visitante,
            "result": "1",
        })
    # El resultado real se ajusta en cada test según el escenario.
    matches[0]["result"] = "2"
    matches[1]["result"] = "X"
    return {
        "ticket_id": "Q15_2025_2026_J001",
        "jornada": 1,
        "draw_date": "2025-08-30",
        "source_url": "https://example.test/1",
        "matches": matches,
        "pleno15": {"date": "2025-08-31", "home": "Girona", "away": "Rayo", "score": "2-1"},
    }


def predictions_frame() -> pd.DataFrame:
    rows = []
    for number in range(1, 15):
        date = pd.Timestamp(f"2025-08-{14 + number:02d}")
        home = "Vallecano" if number == 1 else "Ath Bilbao" if number == 2 else f"Local {number}"
        probs = PRIMERA_PROBS if number <= 3 else SEGURA_PROBS
        result = "2" if number == 1 else "X" if number == 2 else "1"
        rows.append({
            "date": date, "home": home, "away": f"Visitante {number}",
            "division": "Primera", "result": result,
            "favorite_market": "1", "favorite_market_hit": int("1" == result),
            "model_disagreement": 0.0,
            "best_prob_1": probs[0], "best_prob_x": probs[1], "best_prob_2": probs[2],
            "best_pred": "1",
            "pleno15_marcador": "2-1",
        })
    rows.append({
        "date": pd.Timestamp("2025-08-31"), "home": "Girona", "away": "Vallecano",
        "division": "Primera", "result": "2",
        "favorite_market": "2", "favorite_market_hit": 1,
        "model_disagreement": 0.0,
        "best_prob_1": 0.2, "best_prob_x": 0.2, "best_prob_2": 0.6,
        "best_pred": "2",
        "pleno15_marcador": "2-1",
    })
    return pd.DataFrame(rows)


def test_key_name_resolves_aliases_and_accents():
    assert key_name("Rayo") == "vallecano"
    assert key_name("Athletic") == "athbilbao"
    assert key_name("At. Madrid") == "athmadrid"
    assert key_name("Sporting GijÃ³n") == "spgijon"
    assert key_name("Girona") == "girona"


def test_evaluator_counts_hits_doubles_and_pleno():
    tickets = [base_ticket()]
    result = evaluate_ticket_results(predictions_frame(), tickets, CONFIG)
    row = result["tickets"][0]
    assert row["evaluated"] is True
    # Simples: solo el partido 3 y los 4..14 aciertan (pred "1").
    assert row["hits_simple_14"] == 12
    # Mercado: falla en 1 y X; acierta en 3..14 -> 12.
    assert row["hits_market_14"] == 12
    # Tres dobles sobre los partidos 1,2,3 (1X): 2 y 3 aciertan + 4..14 -> 13.
    assert row["hits_3dobles_14"] == 13
    assert row["doubles_positions"] == [1, 2, 3]
    # Pleno exacto y bucket coinciden.
    assert row["pleno_exacto"] == 1
    assert row["pleno_bucket"] == 1
    assert row["pleno_oficial"] == "2-1"
    assert row["pleno_modelo"] == "2-1"
    agg = result["aggregate"]
    assert agg["n_tickets"] == 1
    assert agg["mean_hits_simple_14"] == 12.0
    assert agg["mean_hits_3dobles_14"] == 13.0
    assert agg["mean_hits_15_con_pleno_bucket"] == 14.0


def test_evaluator_marks_incomplete_ticket_when_a_match_is_missing():
    ticket = base_ticket()
    # Eliminamos el partido 14 de las predicciones: el boleto no puede evaluarse.
    frame = predictions_frame()
    frame = frame[frame["date"] != pd.Timestamp("2025-08-28")].reset_index(drop=True)
    result = evaluate_ticket_results(frame, [ticket], CONFIG)
    row = result["tickets"][0]
    assert row["evaluated"] is False
    assert row["reason"] == "cobertura_incompleta"
    assert row["matches_attached"] == 13
    assert row["matches_expected"] == 14
    assert result["aggregate"] is None


def test_evaluator_reports_pleno_miss_when_model_score_differs():
    ticket = base_ticket()
    frame = predictions_frame()
    frame.loc[frame["date"] == pd.Timestamp("2025-08-31"), "pleno15_marcador"] = "1-0"
    result = evaluate_ticket_results(frame, [ticket], CONFIG)
    row = result["tickets"][0]
    assert row["pleno_exacto"] == 0
    assert row["pleno_bucket"] == 0


def test_aggregate_rows_across_proposals():
    from scripts.backtests.EVALUAR_ACIERTOS_BOLETOS import aggregate_rows

    row_a = {
        "evaluated": True, "hits_simple_14": 7, "hits_market_14": 7, "hits_3dobles_14": 8,
        "hits_15_con_pleno_bucket": 9, "pleno_exacto": 0, "pleno_bucket": 1,
        "matches": [{"hit_motor": True, "hit_market": True}] * 14,
    }
    row_b = {
        "evaluated": True, "hits_simple_14": 9, "hits_market_14": 9, "hits_3dobles_14": 9,
        "hits_15_con_pleno_bucket": 10, "pleno_exacto": 1, "pleno_bucket": 1,
        "matches": [{"hit_motor": True, "hit_market": False}] * 14,
    }
    agg = aggregate_rows([row_a, row_b])
    assert agg["n_tickets"] == 2
    assert agg["mean_hits_simple_14"] == 8.0
    assert agg["mean_hits_3dobles_14"] == 8.5
    assert agg["pleno_exacto_total"] == 1
    assert agg["pleno_bucket_total"] == 2
    assert agg["matches_union"] == 28
    assert abs(agg["accuracy_motor_union"] - 1.0) < 1e-9
    assert abs(agg["accuracy_market_union"] - 0.5) < 1e-9
    assert aggregate_rows([{"evaluated": False, "reason": "cobertura_incompleta"}]) is None
