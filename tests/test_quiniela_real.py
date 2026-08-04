from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.backtests.QUINIELA_REAL import (
    attach_ticket_positions,
    evaluate_official_doubles,
    evaluate_realized_roi,
    load_official_tickets,
)


def official_ticket() -> dict:
    matches = [
        {
            "number": number,
            "date": "2026-02-21",
            "home": f"Local {number}",
            "away": f"Visitante {number}",
            "result": "1",
        }
        for number in range(1, 15)
    ]
    return {
        "ticket_id": "2025-2026-J44",
        "jornada": 44,
        "draw_date": "2026-02-22",
        "source_url": "https://example.test/lae/j44",
        "matches": matches,
        "pleno15": {"date": "2026-02-22", "home": "Local P15", "away": "Visitante P15", "score": "2-1"},
    }


def predictions_for_ticket(ticket: dict) -> pd.DataFrame:
    rows = []
    for match in ticket["matches"]:
        rows.append({
            "date": match["date"], "home": match["home"], "away": match["away"], "division": "Primera",
            "pred_prob_1": 0.60, "pred_prob_x": 0.25, "pred_prob_2": 0.15,
            "pred_pred": "1", "model_disagreement": 0.05,
        })
    return pd.DataFrame(rows)


def config() -> dict:
    return {"double_draw_threshold": 0.30, "double_draw_weight": 0.7, "double_disagreement_weight": 0.2, "double_segunda_bonus": 0.05}


def test_loader_accepts_versioned_official_ticket_file(tmp_path):
    payload = {"schema_version": "1.0", "source": {"name": "LAE"}, "tickets": [official_ticket()]}
    (tmp_path / "2025_26.json").write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_official_tickets(tmp_path)
    assert [ticket["ticket_id"] for ticket in loaded] == ["2025-2026-J44"]


def test_loader_rejects_ticket_without_all_official_positions(tmp_path):
    ticket = official_ticket()
    ticket["matches"] = ticket["matches"][:-1]
    payload = {"schema_version": "1.0", "source": {"name": "LAE"}, "tickets": [ticket]}
    (tmp_path / "bad.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="exactamente 14"):
        load_official_tickets(tmp_path)


def test_attach_requires_exact_date_and_teams():
    ticket = official_ticket()
    predictions = predictions_for_ticket(ticket)
    joined, coverage = attach_ticket_positions(predictions, [ticket])
    assert coverage == {"requested_matches": 14, "matched_matches": 14, "unmatched_or_ambiguous": 0, "ambiguous_matches": 0}
    assert joined["official_ticket_number"].tolist() == list(range(1, 15))

    predictions.loc[0, "date"] = "2026-02-22"
    joined, coverage = attach_ticket_positions(predictions, [ticket])
    assert len(joined) == 13
    assert coverage["unmatched_or_ambiguous"] == 1


def test_doubles_uses_only_complete_real_ticket():
    ticket = official_ticket()
    joined, _ = attach_ticket_positions(predictions_for_ticket(ticket), [ticket])
    score = evaluate_official_doubles(joined, "pred", config())
    assert score.loc[0, "ticket_id"] == "2025-2026-J44"
    assert score.loc[0, "hits_3_dobles_14"] == 14
    assert len(score.loc[0, "doubles"]) == 3

    incomplete = joined.iloc[:-1]
    assert evaluate_official_doubles(incomplete, "pred", config()).empty


def test_realized_roi_requires_official_payouts_and_calculates_when_present():
    winners = ["1"] * 14
    columns = [tuple(winners), tuple(["X"] * 14)]
    unavailable = evaluate_realized_roi(columns, winners, None, price_per_column=0.75)
    assert unavailable["status"] == "missing_official_payouts"
    assert unavailable["return"] is None

    result = evaluate_realized_roi(columns, winners, {"14": 1000.0}, price_per_column=0.75)
    assert result["status"] == "realized"
    assert result["cost"] == 1.5
    assert result["return"] == 1000.0
    assert result["profit"] == 998.5


def test_double_avoid_overconfidence_mask_excludes_overconfident_match():
    from scripts.backtests.QUINIELA_REAL import double_avoid_overconfidence_mask

    frame = pd.DataFrame({
        "hgb_prob_1": [0.30, 0.55], "hgb_prob_x": [0.35, 0.25], "hgb_prob_2": [0.35, 0.20],
        "market_1": [0.50, 0.50], "market_x": [0.20, 0.30], "market_2": [0.30, 0.20],
    })
    # Fila 0: top HGB = X (0.35), diff vs market_x = 0.15 > 0.10 -> excluida.
    # Fila 1: top HGB = 1 (0.55), diff vs market_1 = 0.05 -> no excluida.
    mask = double_avoid_overconfidence_mask(frame, {"double_avoid_overconfidence": True, "double_avoid_overconfidence_threshold": 0.1}, "pred")
    assert list(mask) == [True, False]
    # Desactivada -> nada excluido.
    mask_off = double_avoid_overconfidence_mask(frame, {"double_avoid_overconfidence": False}, "pred")
    assert not mask_off.any()
    # Sin columnas de mercado -> defensiva, nada excluido.
    mask_no_market = double_avoid_overconfidence_mask(frame.drop(columns=["market_1", "market_x", "market_2"]), {"double_avoid_overconfidence": True}, "pred")
    assert not mask_no_market.any()
