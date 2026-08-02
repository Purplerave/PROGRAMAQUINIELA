"""Validación de boletos reales LAE contra el histórico.

Usa un único caso especial oficial: jornada con abreviaturas LAE (R. Oviedo,
R. Zaragoza, At. Madrid) y Pleno al 15 con marcador exacto.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from MOTOR_QUINIELA_MAESTRO import load_raw_history
from scripts.backtests.BACKTEST_BOLETOS_LAE import (
    load_ticket,
    score_real_ticket,
    validate_ticket_against_history,
)
from scripts.motor.team_names import resolve_history_name

FIXTURE = Path("DATOS/boletos_lae_reales/LAE_2026-01-25.json")


def test_aliases_lae_abreviados_del_caso_especial():
    assert resolve_history_name("At. Madrid") == "Ath Madrid"
    assert resolve_history_name("R. Oviedo") == "Oviedo"
    assert resolve_history_name("R. Zaragoza") == "Zaragoza"


def test_boleto_lae_real_valida_14_signos_y_pleno15_exact_score():
    history = load_raw_history("original")
    ticket = load_ticket(FIXTURE)

    matches = validate_ticket_against_history(ticket, history)

    assert len(matches) == 15
    assert sum(match.is_pleno15 for match in matches) == 1
    assert matches[5].away_history == "Oviedo"
    assert matches[12].home_history == "Zaragoza"
    pleno = matches[-1]
    assert pleno.num == 15
    assert pleno.home_history == "Girona"
    assert pleno.away_history == "Getafe"
    assert pleno.score == "1-1"
    assert pleno.sign == "1-1"


def test_score_real_ticket_usa_orden_lae_y_excluye_pleno_de_los_3_dobles():
    ticket = load_ticket(FIXTURE)
    history = load_raw_history("original")
    matches = validate_ticket_against_history(ticket, history)

    rows = []
    for match in matches:
        result = "X" if match.is_pleno15 else match.sign
        rows.append(
            {
                "season": match.season,
                "home": match.home_history,
                "away": match.away_history,
                "division": match.division,
                "result": result,
                "latest_pred": result,
                "favorite_market": result,
                "market_1": 0.70 if result == "1" else 0.15,
                "market_x": 0.70 if result == "X" else 0.15,
                "market_2": 0.70 if result == "2" else 0.15,
                "latest_prob_1": 0.70 if result == "1" else 0.15,
                "latest_prob_x": 0.70 if result == "X" else 0.15,
                "latest_prob_2": 0.70 if result == "2" else 0.15,
                "model_disagreement": 0.0,
                "pleno15_marcador": "1-1" if match.is_pleno15 else None,
                "pleno15_top_scores": '[{"score":"1-1","prob":0.2}]' if match.is_pleno15 else "[]",
            }
        )
    predictions = pd.DataFrame(rows)
    config = {
        "double_draw_threshold": 0.25,
        "double_draw_weight": 0.0,
        "double_disagreement_weight": 0.0,
        "double_segunda_bonus": 0.0,
    }

    scored = score_real_ticket(matches, predictions, config)

    assert scored["partidos_1_14"] == 14
    assert scored["modelo_aciertos_simples"] == 14
    assert scored["modelo_aciertos_3_dobles"] == 14
    assert all(num <= 14 for num in scored["dobles_modelo"])
    assert all(num <= 14 for num in scored["dobles_mercado"])
    assert scored["pleno15_real"] == "1-1"
    assert scored["pleno15_exacto"] is True
    assert scored["pleno15_top3"] is True
