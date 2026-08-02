"""Backtest sobre boletos oficiales reales de LAE.

Este script cierra la brecha señalada en REVISION_01: deja de agrupar los
partidos cronológicamente de 15 en 15 y evalúa el motor sobre boletos reales
(orden oficial 1-14 + Pleno al 15). Los JSON de entrada son mínimos y
append-only, en ``DATOS/boletos_lae_reales``.

Uso rápido:
    python scripts/backtests/BACKTEST_BOLETOS_LAE.py --historico original
    python scripts/backtests/BACKTEST_BOLETOS_LAE.py --solo-validar

La validación comprueba que cada partido del boleto existe en el histórico, que
el marcador histórico coincide con el signo oficial LAE, y que el partido 15 se
trata como caso especial de marcador exacto (Pleno al 15), no como 1/X/2.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import settings
from MOTOR_QUINIELA_MAESTRO import (
    build_double,
    load_raw_history,
    rolling_team_features,
    run_season_backtest,
)
from scripts.motor.team_names import resolve_history_name

DEFAULT_FIXTURES_DIR = settings.DATOS_DIR / "boletos_lae_reales"


@dataclass(frozen=True)
class TicketMatch:
    ticket_id: str
    season: str
    num: int
    home: str
    away: str
    home_history: str
    away_history: str
    score: str | None
    sign: str
    is_pleno15: bool
    is_sorteo: bool
    history_index: int
    history_date: str
    division: str


def _score_to_sign(score: str) -> str:
    try:
        left, right = str(score).replace(" ", "").split("-")
        home_goals, away_goals = int(left), int(right)
    except Exception as exc:  # noqa: BLE001 - queremos error de datos claro
        raise ValueError(f"Marcador inválido: {score!r}") from exc
    if home_goals > away_goals:
        return "1"
    if home_goals == away_goals:
        return "X"
    return "2"


def _parse_score(score: str) -> tuple[int, int]:
    left, right = str(score).replace(" ", "").split("-")
    return int(left), int(right)


def _history_key(home: object, away: object) -> tuple[str, str]:
    return (resolve_history_name(home), resolve_history_name(away))


def load_ticket(path: Path) -> dict:
    ticket = json.loads(path.read_text(encoding="utf-8"))
    required = {"id", "temporada", "partidos"}
    missing = required - set(ticket)
    if missing:
        raise ValueError(f"{path}: faltan campos {sorted(missing)}")
    if len(ticket["partidos"]) != 15:
        raise ValueError(f"{path}: se esperaban 15 partidos, hay {len(ticket['partidos'])}")
    return ticket


def iter_ticket_paths(path_or_dir: Path | None = None) -> list[Path]:
    base = path_or_dir or DEFAULT_FIXTURES_DIR
    if base.is_file():
        return [base]
    return sorted(base.glob("*.json"))


def validate_ticket_against_history(ticket: dict, history: pd.DataFrame) -> list[TicketMatch]:
    """Valida un boleto LAE contra el histórico y devuelve sus partidos resueltos.

    El emparejamiento es por temporada + local/visitante resueltos con alias
    controlados. Si hay cero o múltiples coincidencias se falla de forma explícita
    para evitar evaluaciones silenciosas con un partido equivocado.
    """
    season = str(ticket["temporada"])
    hist = history[history["season"].astype(str).eq(season)].copy()
    if hist.empty:
        raise ValueError(f"{ticket['id']}: no hay histórico para la temporada {season}")

    matches: list[TicketMatch] = []
    seen_nums: set[int] = set()
    for raw_match in sorted(ticket["partidos"], key=lambda m: int(m["num"])):
        num = int(raw_match["num"])
        if num in seen_nums:
            raise ValueError(f"{ticket['id']}: partido duplicado num={num}")
        seen_nums.add(num)

        home_hist, away_hist = _history_key(raw_match["local"], raw_match["visitante"])
        candidates = hist[hist["home"].eq(home_hist) & hist["away"].eq(away_hist)]
        if len(candidates) != 1:
            raise ValueError(
                f"{ticket['id']} #{num}: esperado 1 match histórico para "
                f"{raw_match['local']} - {raw_match['visitante']} "
                f"({home_hist} - {away_hist}), encontrados {len(candidates)}"
            )
        row = candidates.iloc[0]

        raw_score = raw_match.get("resultado")
        score = str(raw_score).replace(" ", "") if raw_score not in {None, ""} else None
        declared_sign = str(raw_match.get("signo", "")).strip().upper().replace(" ", "")
        tipo = str(raw_match.get("tipo", "")).strip().lower()
        is_pleno15 = num == 15 or tipo == "pleno15"
        is_sorteo = tipo == "sorteo" or (not is_pleno15 and score is None)

        if is_sorteo:
            if declared_sign not in {"1", "X", "2"}:
                raise ValueError(
                    f"{ticket['id']} #{num}: partido resuelto por sorteo sin signo 1/X/2 válido: "
                    f"{declared_sign!r}"
                )
            sign_for_ticket = declared_sign
        else:
            if score is None:
                raise ValueError(f"{ticket['id']} #{num}: falta resultado para partido no marcado como sorteo")
            hg, ag = _parse_score(score)
            sign_from_score = _score_to_sign(score)
            if int(row["FTHG"]) != hg or int(row["FTAG"]) != ag:
                raise ValueError(
                    f"{ticket['id']} #{num}: marcador LAE {score} no coincide con "
                    f"histórico {int(row['FTHG'])}-{int(row['FTAG'])}"
                )
            if is_pleno15:
                if declared_sign != score:
                    raise ValueError(
                        f"{ticket['id']} #15: Pleno al 15 debe declarar marcador exacto; "
                        f"signo={declared_sign!r}, resultado={score!r}"
                    )
                sign_for_ticket = score
            elif declared_sign != sign_from_score:
                raise ValueError(
                    f"{ticket['id']} #{num}: signo LAE {declared_sign!r} no coincide "
                    f"con marcador {score} -> {sign_from_score}"
                )
            else:
                sign_for_ticket = sign_from_score

        matches.append(
            TicketMatch(
                ticket_id=str(ticket["id"]),
                season=season,
                num=num,
                home=str(raw_match["local"]),
                away=str(raw_match["visitante"]),
                home_history=home_hist,
                away_history=away_hist,
                score=score,
                sign=sign_for_ticket,
                is_pleno15=is_pleno15,
                is_sorteo=is_sorteo,
                history_index=int(row.name),
                history_date=str(pd.to_datetime(row["date"]).date()),
                division=str(row["division"]),
            )
        )
    return matches


def validate_tickets(paths: Iterable[Path], history: pd.DataFrame) -> dict:
    all_matches: list[TicketMatch] = []
    tickets = []
    for path in paths:
        ticket = load_ticket(path)
        resolved = validate_ticket_against_history(ticket, history)
        tickets.append(ticket)
        all_matches.extend(resolved)
    return {
        "tickets": tickets,
        "matches": all_matches,
        "summary": {
            "tickets": len(tickets),
            "partidos": len(all_matches),
            "plenos15": sum(m.is_pleno15 for m in all_matches),
            "sorteos": sum(m.is_sorteo for m in all_matches),
            "temporadas": sorted({m.season for m in all_matches}),
        },
    }


def _index_predictions(predictions: pd.DataFrame) -> dict[tuple[str, str, str], pd.Series]:
    indexed: dict[tuple[str, str, str], pd.Series] = {}
    for _, row in predictions.iterrows():
        key = (str(row["season"]), str(row["home"]), str(row["away"]))
        indexed[key] = row
    return indexed


def _ticket_pick_rows(matches: list[TicketMatch], predictions: pd.DataFrame) -> pd.DataFrame:
    pred_index = _index_predictions(predictions)
    rows = []
    for match in matches:
        key = (match.season, match.home_history, match.away_history)
        if key not in pred_index:
            raise ValueError(f"{match.ticket_id} #{match.num}: sin predicción para {key}")
        pred = pred_index[key]
        item = pred.to_dict()
        item.update(
            {
                "ticket_id": match.ticket_id,
                "ticket_num": match.num,
                "ticket_score": match.score,
                "ticket_sign": match.sign,
                "ticket_is_pleno15": match.is_pleno15,
                "ticket_is_sorteo": match.is_sorteo,
            }
        )
        rows.append(item)
    return pd.DataFrame(rows).sort_values(["ticket_id", "ticket_num"]).reset_index(drop=True)


def score_real_ticket(matches: list[TicketMatch], predictions: pd.DataFrame, config: dict) -> dict:
    """Evalúa simples, 3 dobles y Pleno al 15 en un boleto oficial."""
    frame = _ticket_pick_rows(matches, predictions)
    main = frame[~frame["ticket_is_pleno15"]].copy()
    pleno = frame[frame["ticket_is_pleno15"]].copy()
    if len(main) != 14 or len(pleno) != 1:
        raise ValueError(f"{matches[0].ticket_id}: esperado 14 partidos + 1 pleno; recibido {len(main)} + {len(pleno)}")

    prefix = "latest" if "latest_pred" in frame.columns else "best"
    main["modelo_simple_hit"] = main[f"{prefix}_pred"].eq(main["ticket_sign"]).astype(int)
    main["mercado_simple_hit"] = main["favorite_market"].eq(main["ticket_sign"]).astype(int)
    main["double"] = [
        build_double(p1, px, p2, config["double_draw_threshold"])
        for p1, px, p2 in zip(main[f"{prefix}_prob_1"], main[f"{prefix}_prob_x"], main[f"{prefix}_prob_2"])
    ]
    confidence = main[[f"{prefix}_prob_1", f"{prefix}_prob_x", f"{prefix}_prob_2"]].max(axis=1)
    main["double_value_score"] = (
        (1 - confidence)
        + config["double_draw_weight"] * main[f"{prefix}_prob_x"]
        + config["double_disagreement_weight"] * main["model_disagreement"]
        + np.where(main["division"].eq("Segunda"), config["double_segunda_bonus"], 0.0)
    )
    double_idx = set(main.nlargest(3, "double_value_score").index.tolist())

    main["market_double"] = [
        build_double(p1, px, p2, config["double_draw_threshold"])
        for p1, px, p2 in zip(main["market_1"], main["market_x"], main["market_2"])
    ]
    market_confidence = main[["market_1", "market_x", "market_2"]].max(axis=1)
    main["market_double_value_score"] = (
        (1 - market_confidence)
        + config["double_draw_weight"] * main["market_x"]
        + np.where(main["division"].eq("Segunda"), config["double_segunda_bonus"], 0.0)
    )
    market_double_idx = set(main.nlargest(3, "market_double_value_score").index.tolist())

    model_hits_3_dobles = 0
    market_hits_3_dobles = 0
    for idx, row in main.iterrows():
        official_sign = row["ticket_sign"]
        if idx in double_idx:
            model_hits_3_dobles += int(official_sign in row["double"])
        else:
            model_hits_3_dobles += int(row[f"{prefix}_pred"] == official_sign)

        if idx in market_double_idx:
            market_hits_3_dobles += int(official_sign in row["market_double"])
        else:
            market_hits_3_dobles += int(row["favorite_market"] == official_sign)

    pleno_row = pleno.iloc[0]
    pleno_scores_raw = pleno_row.get("pleno15_top_scores")
    try:
        pleno_top = json.loads(pleno_scores_raw) if isinstance(pleno_scores_raw, str) else []
    except json.JSONDecodeError:
        pleno_top = []
    pleno_pred = pleno_row.get("pleno15_marcador")
    pleno_real = pleno_row["ticket_score"]

    return {
        "ticket_id": matches[0].ticket_id,
        "season": matches[0].season,
        "partidos_1_14": 14,
        "sorteos_1_14": int(main["ticket_is_sorteo"].sum()),
        "modelo_aciertos_simples": int(main["modelo_simple_hit"].sum()),
        "mercado_aciertos_simples": int(main["mercado_simple_hit"].sum()),
        "modelo_aciertos_3_dobles": int(model_hits_3_dobles),
        "mercado_aciertos_3_dobles": int(market_hits_3_dobles),
        "dobles_modelo": [int(v) for v in sorted(main.loc[list(double_idx), "ticket_num"].tolist())],
        "dobles_mercado": [int(v) for v in sorted(main.loc[list(market_double_idx), "ticket_num"].tolist())],
        "pleno15_real": pleno_real,
        "pleno15_pred": pleno_pred,
        "pleno15_exacto": bool(pleno_pred == pleno_real),
        "pleno15_top3": bool(any(item.get("score") == pleno_real for item in pleno_top)),
    }


def run_lae_backtest(path_or_dir: Path | None = None, historico: str = "original") -> dict:
    raw = load_raw_history(historico)
    paths = iter_ticket_paths(path_or_dir)
    validation = validate_tickets(paths, raw)
    features = rolling_team_features(raw)
    by_ticket = []
    cache: dict[str, tuple[pd.DataFrame, dict]] = {}
    for ticket in validation["tickets"]:
        season = str(ticket["temporada"])
        if season not in cache:
            cache[season] = run_season_backtest(features, season)
        predictions, metrics = cache[season]
        matches = [m for m in validation["matches"] if m.ticket_id == ticket["id"]]
        by_ticket.append(score_real_ticket(matches, predictions, metrics["best_config"]))

    return {
        "historico": historico,
        "validacion": validation["summary"],
        "tickets": by_ticket,
        "resumen": {
            "tickets": len(by_ticket),
            "media_modelo_simples": float(np.mean([t["modelo_aciertos_simples"] for t in by_ticket])) if by_ticket else None,
            "media_mercado_simples": float(np.mean([t["mercado_aciertos_simples"] for t in by_ticket])) if by_ticket else None,
            "media_modelo_3_dobles": float(np.mean([t["modelo_aciertos_3_dobles"] for t in by_ticket])) if by_ticket else None,
            "media_mercado_3_dobles": float(np.mean([t["mercado_aciertos_3_dobles"] for t in by_ticket])) if by_ticket else None,
            "pleno15_exactos": int(sum(t["pleno15_exacto"] for t in by_ticket)),
            "pleno15_top3": int(sum(t["pleno15_top3"] for t in by_ticket)),
        },
    }


def _json_default(value):
    if isinstance(value, TicketMatch):
        return value.__dict__
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    raise TypeError(f"No serializable: {type(value)!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest de boletos reales oficiales LAE")
    parser.add_argument("--path", type=Path, default=None, help="JSON o directorio de boletos LAE")
    parser.add_argument("--historico", choices=("original", "saneado"), default="original")
    parser.add_argument("--solo-validar", action="store_true", help="solo valida los boletos contra el histórico; no entrena modelos")
    args = parser.parse_args()

    raw = load_raw_history(args.historico)
    paths = iter_ticket_paths(args.path)
    if not paths:
        raise FileNotFoundError(f"No hay boletos JSON en {args.path or DEFAULT_FIXTURES_DIR}")

    if args.solo_validar:
        payload = validate_tickets(paths, raw)
        result = {"historico": args.historico, "validacion": payload["summary"]}
    else:
        result = run_lae_backtest(args.path, args.historico)

    settings.SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    out = settings.SALIDA_DIR / "backtest_boletos_lae.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))
    print(f"\nGuardado en {out}")


if __name__ == "__main__":
    main()
