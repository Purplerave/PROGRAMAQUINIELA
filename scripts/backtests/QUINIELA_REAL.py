"""Backtest reproducible de boletos oficiales y retorno realizado.

Este módulo no reconstruye jornadas a partir de partidos consecutivos. Solo opera
sobre boletos que declaren explícitamente los partidos oficiales 1..14, sus
fechas y resultados. Los datos externos se mantienen fuera de Git hasta que se
hayan auditado su procedencia y licencia.

Esquema de cada JSON en ``DATOS/quiniela_historica``::

    {
      "schema_version": "1.0",
      "source": {"name": "LAE", "url": "...", "retrieved_at": "..."},
      "tickets": [{
        "ticket_id": "2025-2026-J44",
        "jornada": 44,
        "draw_date": "2026-02-22",
        "source_url": "...",
        "matches": [
          {"number": 1, "date": "2026-02-21", "home": "...",
           "away": "...", "result": "1"},
          ...
        ],
        "pleno15": {"date": "...", "home": "...", "away": "...",
                    "score": "2-1"},
        "payouts": {"10": 2.50, "11": 8.00, "12": 40.00,
                    "13": 500.00, "14": 10000.00}
      }]
    }

Los importes de ``payouts`` son el premio por columna ganadora de la categoría;
no se infieren ni se inventan si no llegan del escrutinio oficial.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TICKETS_DIR = ROOT / "DATOS" / "quiniela_historica"
SIGNS = {"1", "X", "2"}
DOUBLE_ORDER = {"1": 0, "X": 1, "2": 2}


def canonical_team(value: object) -> str:
    """Clave conservadora para emparejar equipos; los alias se pasan explícitos."""
    text = unicodedata.normalize("NFKD", str(value).strip())
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]", "", text)


def _iso_date(value: object, field: str) -> str:
    try:
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        raise ValueError(f"{field} debe ser una fecha ISO válida: {value!r}") from None


def validate_ticket(ticket: dict[str, Any]) -> None:
    """Valida los requisitos mínimos antes de aceptar un boleto histórico."""
    required = ("ticket_id", "jornada", "draw_date", "source_url", "matches", "pleno15")
    missing = [field for field in required if not ticket.get(field)]
    if missing:
        raise ValueError(f"Boleto sin campos obligatorios: {', '.join(missing)}")
    if not isinstance(ticket["jornada"], int) or ticket["jornada"] < 1:
        raise ValueError(f"jornada inválida en {ticket['ticket_id']!r}")
    _iso_date(ticket["draw_date"], "draw_date")
    matches = ticket["matches"]
    if not isinstance(matches, list) or len(matches) != 14:
        raise ValueError(f"{ticket['ticket_id']}: se requieren exactamente 14 partidos")
    numbers = [match.get("number") for match in matches]
    if sorted(numbers) != list(range(1, 15)):
        raise ValueError(f"{ticket['ticket_id']}: los números deben ser exactamente 1..14")
    for match in matches:
        missing_match = [field for field in ("number", "date", "home", "away", "result") if not match.get(field)]
        if missing_match:
            raise ValueError(f"{ticket['ticket_id']} partido {match.get('number')}: faltan {missing_match}")
        _iso_date(match["date"], "match.date")
        if match["result"] not in SIGNS:
            raise ValueError(f"{ticket['ticket_id']} partido {match['number']}: resultado inválido")
    pleno = ticket["pleno15"]
    if not isinstance(pleno, dict) or not all(pleno.get(field) for field in ("date", "home", "away", "score")):
        raise ValueError(f"{ticket['ticket_id']}: pleno15 incompleto")
    _iso_date(pleno["date"], "pleno15.date")
    if "payouts" in ticket:
        if not isinstance(ticket["payouts"], dict):
            raise ValueError(f"{ticket['ticket_id']}: payouts debe ser un objeto")
        for category, amount in ticket["payouts"].items():
            if not str(category).isdigit() or float(amount) < 0:
                raise ValueError(f"{ticket['ticket_id']}: payout inválido para {category!r}")


def load_official_tickets(directory: Path = DEFAULT_TICKETS_DIR) -> list[dict[str, Any]]:
    """Carga y valida todos los JSON auditados de boletos oficiales."""
    if not directory.exists():
        return []
    tickets: list[dict[str, Any]] = []
    ids: set[str] = set()
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "1.0" or not isinstance(payload.get("source"), dict):
            raise ValueError(f"{path}: schema_version 1.0 y source son obligatorios")
        for ticket in payload.get("tickets", []):
            validate_ticket(ticket)
            ticket_id = str(ticket["ticket_id"])
            if ticket_id in ids:
                raise ValueError(f"ticket_id duplicado: {ticket_id}")
            ids.add(ticket_id)
            tickets.append(ticket)
    return tickets


def attach_ticket_positions(
    predictions: pd.DataFrame,
    tickets: list[dict[str, Any]],
    aliases: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Une predicciones a partidos oficiales sin aproximaciones por jornada.

    La unión exige fecha, local y visitante. Si dos filas candidatas comparten
    clave, o no existe una coincidencia, no se adjudica el partido: así se evita
    atribuir resultados a un boleto equivocado por un alias ambiguo.
    """
    required = {"date", "home", "away"}
    absent = required - set(predictions.columns)
    if absent:
        raise ValueError(f"Faltan columnas de predicción: {sorted(absent)}")
    aliases = aliases or {}

    def name(value: object) -> str:
        raw = str(value).strip()
        return canonical_team(aliases.get(raw, raw))

    indexed: dict[tuple[str, str, str], list[int]] = {}
    for index, row in predictions.iterrows():
        key = (_iso_date(row["date"], "prediction.date"), name(row["home"]), name(row["away"]))
        indexed.setdefault(key, []).append(index)

    assigned: list[pd.DataFrame] = []
    requested = matched = ambiguous = 0
    for ticket in tickets:
        validate_ticket(ticket)
        for match in ticket["matches"]:
            requested += 1
            key = (_iso_date(match["date"], "match.date"), name(match["home"]), name(match["away"]))
            candidates = indexed.get(key, [])
            if len(candidates) != 1:
                ambiguous += int(len(candidates) > 1)
                continue
            row = predictions.loc[[candidates[0]]].copy()
            row["official_ticket_id"] = ticket["ticket_id"]
            row["official_ticket_number"] = match["number"]
            row["official_ticket_result"] = match["result"]
            assigned.append(row)
            matched += 1
    joined = pd.concat(assigned, ignore_index=True) if assigned else predictions.iloc[0:0].copy()
    return joined, {"requested_matches": requested, "matched_matches": matched, "unmatched_or_ambiguous": requested - matched, "ambiguous_matches": ambiguous}


def build_double(prob1: float, probx: float, prob2: float, draw_threshold: float) -> str:
    probs = {"1": prob1, "X": probx, "2": prob2}
    ordered = sorted(probs.items(), key=lambda item: item[1], reverse=True)
    top, second = ordered[0][0], ordered[1][0]
    if probx >= draw_threshold:
        if top == "1":
            return "1X"
        if top == "2":
            return "X2"
    return "".join(sorted((top, second), key=lambda sign: DOUBLE_ORDER[sign]))


def double_avoid_overconfidence_mask(frame: pd.DataFrame, config: dict, pred_prefix: str) -> np.ndarray:
    """Máscara de partidos sobreconfiados que no deben ser dobles (regla activa).

    Igual que en el maestro: un partido con divergencia
    ``p_hgb[signo_top] - p_mercado[signo_top] > umbral`` (por defecto 0.10) no
    debe gastar uno de los tres dobles. Defensiva: si el config no la activa o
    faltan columnas de mercado, no excluye nada.
    """
    if not config.get("double_avoid_overconfidence", False):
        return np.zeros(len(frame), dtype=bool)
    threshold = float(config.get("double_avoid_overconfidence_threshold", 0.10))
    # La divergencia se mide con el HGB frente al mercado; fallback al prefijo.
    prob_cols = ["hgb_prob_1", "hgb_prob_x", "hgb_prob_2"]
    if not set(prob_cols).issubset(frame.columns):
        prob_cols = [f"{pred_prefix}_prob_1", f"{pred_prefix}_prob_x", f"{pred_prefix}_prob_2"]
    market_cols = ["market_1", "market_x", "market_2"]
    if not set(prob_cols).issubset(frame.columns) or not set(market_cols).issubset(frame.columns):
        return np.zeros(len(frame), dtype=bool)
    probs = frame[prob_cols].to_numpy(dtype=float)
    market = frame[market_cols].to_numpy(dtype=float)
    top = probs.argmax(axis=1)
    diff = probs[np.arange(len(probs)), top] - market[np.arange(len(probs)), top]
    return diff > threshold


def evaluate_official_doubles(frame: pd.DataFrame, pred_prefix: str, config: dict) -> pd.DataFrame:
    """Evalúa tres dobles por boleto oficial de 14 partidos.

    Un boleto se descarta entero si no hay 14 emparejamientos únicos: informar
    una media con cobertura parcial volvería a mezclar una métrica no comparable.
    """
    required = {
        "official_ticket_id", "official_ticket_number", "official_ticket_result", "model_disagreement",
        f"{pred_prefix}_prob_1", f"{pred_prefix}_prob_x", f"{pred_prefix}_prob_2", f"{pred_prefix}_pred",
    }
    absent = required - set(frame.columns)
    if absent:
        raise ValueError(f"No se puede evaluar boleto oficial; faltan {sorted(absent)}")
    rows: list[dict[str, Any]] = []
    for ticket_id, group in frame.groupby("official_ticket_id", sort=True):
        group = group.sort_values("official_ticket_number").copy()
        if len(group) != 14 or group["official_ticket_number"].tolist() != list(range(1, 15)):
            continue
        group["double"] = [
            build_double(p1, px, p2, config["double_draw_threshold"])
            for p1, px, p2 in zip(group[f"{pred_prefix}_prob_1"], group[f"{pred_prefix}_prob_x"], group[f"{pred_prefix}_prob_2"])
        ]
        confidence = group[[f"{pred_prefix}_prob_1", f"{pred_prefix}_prob_x", f"{pred_prefix}_prob_2"]].max(axis=1)
        value = (
            (1 - confidence)
            + config["double_draw_weight"] * group[f"{pred_prefix}_prob_x"]
            + config["double_disagreement_weight"] * group["model_disagreement"]
            + np.where(group["division"].eq("Segunda"), config["double_segunda_bonus"], 0.0)
        )
        value = value - np.where(double_avoid_overconfidence_mask(group, config, pred_prefix), 1.0, 0.0)
        double_numbers = set(group.loc[value.nlargest(3).index, "official_ticket_number"])
        hits = sum(
            (row["official_ticket_result"] in row["double"])
            if row["official_ticket_number"] in double_numbers
            else (row[f"{pred_prefix}_pred"] == row["official_ticket_result"])
            for _, row in group.iterrows()
        )
        rows.append({"ticket_id": ticket_id, "hits_3_dobles_14": int(hits), "doubles": sorted(double_numbers)})
    return pd.DataFrame(rows)


def evaluate_realized_roi(
    columns: list[tuple[str, ...] | list[str]],
    winning_signs: list[str],
    payouts: dict[str, float] | None,
    price_per_column: float,
) -> dict[str, Any]:
    """Calcula retorno histórico de columnas ya jugadas cuando existe escrutinio.

    No estima premios. Si no hay payouts, devuelve el coste y marca el retorno
    como no disponible para impedir que se confunda probabilidad con ROI real.
    """
    if len(winning_signs) != 14 or any(sign not in SIGNS for sign in winning_signs):
        raise ValueError("winning_signs debe contener exactamente 14 signos 1/X/2")
    if price_per_column < 0:
        raise ValueError("price_per_column no puede ser negativo")
    normalized_columns = [tuple(column) for column in columns]
    if any(len(column) != 14 or any(sign not in SIGNS for sign in column) for column in normalized_columns):
        raise ValueError("cada columna debe contener 14 signos 1/X/2")
    cost = len(normalized_columns) * price_per_column
    hit_counts = [sum(sign == winner for sign, winner in zip(column, winning_signs)) for column in normalized_columns]
    categories = {str(hits): hit_counts.count(hits) for hits in set(hit_counts)}
    if payouts is None:
        return {"cost": cost, "return": None, "profit": None, "roi": None, "categories": categories, "status": "missing_official_payouts"}
    clean_payouts = {str(category): float(amount) for category, amount in payouts.items()}
    gross_return = sum(clean_payouts.get(str(hits), 0.0) for hits in hit_counts)
    return {
        "cost": cost,
        "return": gross_return,
        "profit": gross_return - cost,
        "roi": (gross_return - cost) / cost if cost else None,
        "categories": categories,
        "status": "realized",
    }


def main() -> int:
    """Valida los boletos disponibles y muestra su cobertura de datos."""
    import argparse

    parser = argparse.ArgumentParser(description="Valida el histórico de boletos oficiales de La Quiniela.")
    parser.add_argument("--tickets-dir", type=Path, default=DEFAULT_TICKETS_DIR)
    args = parser.parse_args()
    tickets = load_official_tickets(args.tickets_dir)
    if not tickets:
        print(f"No hay boletos oficiales auditados en {args.tickets_dir}.")
        return 0
    with_payouts = sum("payouts" in ticket for ticket in tickets)
    print(f"Boletos oficiales válidos: {len(tickets)}")
    print(f"Con escrutinio/premios para ROI: {with_payouts}")
    print(f"Rango de jornadas: {min(ticket['jornada'] for ticket in tickets)}–{max(ticket['jornada'] for ticket in tickets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
