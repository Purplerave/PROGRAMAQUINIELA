"""Tests de jornadas/boletos reales: parser de COSECHAR_JORNADAS_LAE y
evaluación de BACKTEST_BOLETOS_REALES, más reglas de anclaje de
CONSTRUIR_JORNADAS_HISTORICAS."""

from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

import scripts.backtests.BACKTEST_BOLETOS_REALES as bbr
import scripts.datos.CONSTRUIR_JORNADAS_HISTORICAS as cjh
import scripts.datos.COSECHAR_JORNADAS_LAE as cjl
from scripts.motor.team_names import resolve_history_name


# ---------------------------------------------------------------------------
# weekend_anchor (CONSTRUIR_JORNADAS_HISTORICAS)
# ---------------------------------------------------------------------------

def test_weekend_anchor_viernes_al_sabado_siguiente():
    assert cjh.weekend_anchor(date(2025, 11, 28)) == date(2025, 11, 29)  # viernes


def test_weekend_anchor_lunes_al_sabado_anterior():
    assert cjh.weekend_anchor(date(2025, 11, 24)) == date(2025, 11, 22)  # lunes


def test_weekend_anchor_miercoles_fuera():
    assert cjh.weekend_anchor(date(2025, 11, 26)) is None  # miércoles (Copa)


def test_weekend_anchor_domingo_al_sabado_de_su_semana():
    assert cjh.weekend_anchor(date(2025, 11, 23)) == date(2025, 11, 22)  # domingo


# ---------------------------------------------------------------------------
# Parser de COSECHAR_JORNADAS_LAE (HTML sintético con la estructura de LD)
# ---------------------------------------------------------------------------

LD_HTML = """<html><body><h1>Quiniela - Jornada 29 - 2024-2025</h1>
<p>Recaudación 301.845.225 €</p>
<table>
<tr><th>P.</th><th>Equipos</th><th></th><th>1</th><th>X</th><th>2</th></tr>
{rows}
<tr><td>Pleno al 15</td><td></td><td></td><td></td><td></td><td></td></tr>
</table>
<table>
<tr><td><img src="a.png">Atlético de Madrid</td><td>0</td><td>1</td><td>2</td><td>M</td></tr>
<tr><td><img src="b.png">Getafe</td><td>0</td><td>1</td><td>2</td><td>M</td></tr>
</table>
<table>
<tr><th>Aciertos</th><th>Pleno al 15</th><th>14</th><th>13</th><th>12</th><th>11</th><th>10</th></tr>
<tr><td>Acertantes</td><td>0</td><td>0</td><td>2</td><td>23</td><td>176</td><td>1.209</td></tr>
<tr><td>Premios</td><td>-</td><td>-</td><td>113.191€</td><td>9.842€</td><td>1.286€</td><td>224€</td></tr>
</table>
</body></html>"""

_ld_rows = "\n".join(
    f"<tr><td>{i}</td><td>EquipoLocal{i}</td><td>EquipoVisitante{i}</td><td>1</td><td>X</td><td>2</td></tr>"
    for i in range(1, 15)
)
LD_HTML = LD_HTML.format(rows=_ld_rows)


def test_parse_jornada_extrae_partidos_pleno_premios():
    data = cjl.parse_jornada(LD_HTML)
    assert len(data["partidos"]) == 14
    assert data["partidos"][0]["local"] == "EquipoLocal1"
    assert data["partidos"][0]["visitante"] == "EquipoVisitante1"
    assert data["partidos"][-1]["num"] == 14
    assert data["pleno15"] == {"local": "Atlético de Madrid", "visitante": "Getafe"}
    assert data["recaudacion_euros"] == 301845225
    assert data["premios"]["13"] == {"acertantes": 2, "premio_euros": 113191}
    assert data["premios"]["pleno15"] == {"acertantes": 0, "premio_euros": None}


def test_parse_jornada_rechaza_estructura_desconocida():
    with pytest.raises(ValueError):
        cjl.parse_jornada("<html><body>sin tablas</body></html>")


def test_parse_combinaciones_quinielafutbol():
    html = """<table>
    <tr><th>Semana</th><th>Nº de jornada</th><th>DIA</th><th>Sorteo</th><th>Combinacion Ganadora</th></tr>
    <tr><td>50 - 2024</td><td>29</td><td>Q-DOMINGO</td><td>2024/071</td><td>X,1,1,X,X,2,X,2,1,1,1,2,X,2,10</td></tr>
    </table>"""
    comb = cjl.parse_combinaciones_quinielafutbol(html)
    assert comb == {29: ["X", "1", "1", "X", "X", "2", "X", "2", "1", "1", "1", "2", "X", "2", "10"]}


# ---------------------------------------------------------------------------
# Evaluación sobre boletos (BACKTEST_BOLETOS_REALES)
# ---------------------------------------------------------------------------

def _preds_frame() -> pd.DataFrame:
    """15 filas sintéticas: todos los resultados '1'; el motor falla solo en el 1."""
    rows = []
    for i in range(15):
        pred = "1"
        if i == 0:
            pred = "2"  # el motor y el mercado fallan en el partido 1
        rows.append({
            "date": pd.Timestamp("2024-12-14"),
            "home": f"Local{i}",
            "away": f"Visitante{i}",
            "division": "Primera" if i % 3 else "Segunda",
            "result": "1",
            "best_pred": pred,
            "best_prob_1": 0.5, "best_prob_x": 0.25, "best_prob_2": 0.25,
            "favorite_market": pred,
            "model_disagreement": 0.1,
        })
    return pd.DataFrame(rows)


def test_evaluate_ticket_cuenta_aciertos_y_dobles():
    ticket = {
        "temporada": "2024-2025", "jornada": 29, "fecha_sorteo": "2024-12-15",
        "matches": [
            {"num": i + 1, "local": f"Local{i}", "visitante": f"Visitante{i}"}
            for i in range(15)
        ],
        # combinación oficial: coincide con los resultados reales
        "combinacion_ganadora": ["1"] * 14 + ["10"],
    }
    preds = _preds_frame()
    config = {"double_draw_threshold": 0.30, "double_draw_weight": 0.70,
              "double_disagreement_weight": 0.20, "double_segunda_bonus": 0.05}
    r = bbr.evaluate_ticket(ticket, preds, config)
    assert r is not None
    assert r["n_partidos_evaluados"] == 15
    # simple: solo falla el partido 1 -> 14/15 (motor y mercado)
    assert r["accuracy_simple"] == pytest.approx(14 / 15)
    assert r["accuracy_market"] == pytest.approx(14 / 15)
    # 3 dobles (1X en los 3 partidos de mayor score: índice 0, 3, 6): el doble
    # del partido 0 acierta (resultado 1), los otros dos también -> 15/15
    assert r["hits_3_dobles"] == 15
    # los resultados del histórico coinciden con la combinación oficial
    assert r["desajustes_vs_combinacion_oficial"] == 0


def test_load_tickets_acepta_formato_muestra(tmp_path):
    tickets_file = tmp_path / "muestra.json"
    tickets_file.write_text(json.dumps({"boletos": [{
        "temporada": "2025-2026", "jornada": 22, "fecha_sorteo": "2025-11-23",
        "partidos": [{"num": 1, "local": "Alavés", "visitante": "Celta"}],
        "pleno15": {"local": "Espanyol", "visitante": "Sevilla"},
        "combinacion_ganadora": ["2"] * 14 + ["21"],
    }]}), encoding="utf-8")
    tickets = bbr.load_tickets(tmp_path)
    assert len(tickets) == 1
    t = tickets[0]
    assert t["matches"][0]["local"] == "Alavés"
    assert t["matches"][-1]["local"] == "Espanyol"  # el pleno entra como num 15


def test_muestra_real_tiene_15_partidos_y_nombres_resolubles():
    """La muestra cosechada debe tener 15 partidos por boleto y nombres mapeables."""
    tickets = bbr.load_tickets(bbr.DEFAULT_TICKETS)
    assert len(tickets) == 3
    for t in tickets:
        assert len(t["matches"]) == 15, f"boleto {t['temporada']} J{t['jornada']}"
        assert t["combinacion_ganadora"] and len(t["combinacion_ganadora"]) == 15
        for m in t["matches"]:
            assert resolve_history_name(m["local"])
            assert resolve_history_name(m["visitante"])
    # alias añadido: Villarreal II -> Villarreal B
    assert resolve_history_name("Villarreal II") == "Villarreal B"
