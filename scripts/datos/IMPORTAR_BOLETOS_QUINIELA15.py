#!/usr/bin/env python3
"""Convierte boletos de resultados de Quiniela15 en propuestas auditables.

Los JSON de entrada contienen composición, marcador y signo, pero no fecha por
partido ni escrutinio. Este importador deriva la fecha *solo* cuando el par
local/visitante tiene una coincidencia única en Football-Data de la temporada,
y valida tanto marcador como signo. Escribe una propuesta en ``salida``; nunca
altera ni versiona los JSON fuente ni los CSV históricos.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RAW_BASE = ROOT / "DATOS" / "historico_raw"
DEFAULT_SOURCE = ROOT / "DATOS" / "boletos_lae_reales"
DEFAULT_OUTPUT = ROOT / "salida" / "quiniela_historica_propuesta_2025_2026.json"
SIGNS = {"1", "X", "2"}

# Alias mínimos observados en boletos Quiniela15 frente a Football-Data.
ALIASES = {
    # Nombres Quiniela15 -> nombres efectivos del CSV Football-Data 2025-26.
    "at madrid": "ath madrid",
    "athletic": "ath bilbao",
    "rayo": "vallecano",
    "real oviedo": "oviedo",
    "r sociedad": "sociedad",
    "r santander": "santander",
    "espanyol": "espanol",
    "sporting gijon": "sp gijon",
    "deportivo": "la coruna",
    "andorra": "andorra",
}


def repair_mojibake(value: object) -> str:
    """Repara UTF-8 leído como latin-1 sin modificar textos correctamente codificados."""
    text = str(value).strip()
    if "Ã" in text or "Â" in text:
        try:
            return text.encode("latin1").decode("utf-8")
        except UnicodeError:
            pass
    return text


def canonical_team(value: object) -> str:
    text = repair_mojibake(value)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return ALIASES.get(text, text)


def sign_from_goals(home_goals: int, away_goals: int) -> str:
    return "1" if home_goals > away_goals else "2" if home_goals < away_goals else "X"


def load_season_history(season: str) -> pd.DataFrame:
    """Carga solo los CSV Football-Data de una temporada para enlazar fechas."""
    short = f"{season[2:4]}{season[-2:]}"
    paths = [
        RAW_BASE / "PRIMERA" / f"SP1_{short}.csv",
        RAW_BASE / "SEGUNDA" / f"SP2_{short}.csv",
    ]
    frames = []
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"No existe histórico para {season}: {path}")
        division = "Primera" if "SP1" in path.name else "Segunda"
        frame = pd.read_csv(path).dropna(how="all")
        required = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"{path} sin columnas requeridas: {sorted(missing)}")
        frame = frame.assign(
            date=pd.to_datetime(frame["Date"], dayfirst=True, format="mixed", errors="raise"),
            home=frame["HomeTeam"].map(canonical_team),
            away=frame["AwayTeam"].map(canonical_team),
            home_goals=pd.to_numeric(frame["FTHG"], errors="raise").astype(int),
            away_goals=pd.to_numeric(frame["FTAG"], errors="raise").astype(int),
            division=division,
        )
        frames.append(frame[["date", "home", "away", "home_goals", "away_goals", "division"]])
    history = pd.concat(frames, ignore_index=True)
    if history.duplicated(["date", "home", "away"]).any():
        raise ValueError(f"Duplicados en Football-Data para {season}")
    return history


def validate_source_ticket(payload: dict[str, Any]) -> list[dict[str, Any]]:
    required = {"id", "jornada_q15", "temporada", "fuente", "source_url", "partidos"}
    missing = required - set(payload)
    if missing:
        raise ValueError(f"Boleto sin campos: {sorted(missing)}")
    matches = payload["partidos"]
    if not isinstance(matches, list) or len(matches) != 15:
        raise ValueError(f"{payload['id']}: se requieren exactamente 15 partidos")
    numbers = [item.get("num") for item in matches]
    if sorted(numbers) != list(range(1, 16)):
        raise ValueError(f"{payload['id']}: num debe ser 1..15")
    for item in matches:
        if not all(item.get(field) is not None for field in ("local", "visitante", "resultado", "signo")):
            raise ValueError(f"{payload['id']} partido {item.get('num')}: datos incompletos")
        if not re.fullmatch(r"\d+-\d+", str(item["resultado"])):
            raise ValueError(f"{payload['id']} partido {item['num']}: marcador inválido")
        if item["num"] < 15 and item["signo"] not in SIGNS:
            raise ValueError(f"{payload['id']} partido {item['num']}: signo 1X2 inválido")
    return sorted(matches, key=lambda item: item["num"])


def match_history(source_match: dict[str, Any], history: pd.DataFrame, ticket_id: str) -> dict[str, Any]:
    home, away = canonical_team(source_match["local"]), canonical_team(source_match["visitante"])
    candidates = history[(history["home"] == home) & (history["away"] == away)]
    if len(candidates) != 1:
        raise ValueError(f"{ticket_id} #{source_match['num']}: coincidencias Football-Data={len(candidates)} para {source_match['local']} - {source_match['visitante']}")
    row = candidates.iloc[0]
    expected_score = f"{row.home_goals}-{row.away_goals}"
    if str(source_match["resultado"]) != expected_score:
        raise ValueError(f"{ticket_id} #{source_match['num']}: marcador fuente={source_match['resultado']} != Football-Data={expected_score}")
    expected_sign = sign_from_goals(int(row.home_goals), int(row.away_goals))
    if source_match["num"] < 15 and source_match["signo"] != expected_sign:
        raise ValueError(f"{ticket_id} #{source_match['num']}: signo fuente={source_match['signo']} != Football-Data={expected_sign}")
    if source_match["num"] == 15 and source_match["signo"] != expected_score:
        raise ValueError(f"{ticket_id} #15: signo debe ser el marcador exacto {expected_score}")
    return {
        "date": row.date.strftime("%Y-%m-%d"),
        "home": repair_mojibake(source_match["local"]),
        "away": repair_mojibake(source_match["visitante"]),
        "score": expected_score,
        "sign": expected_sign,
        "division": row.division,
    }


def import_tickets(source_dir: Path, season: str, history: pd.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    proposals, failures = [], []
    for path in sorted(source_dir.glob("Q15_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            matches = validate_source_ticket(payload)
            if payload["temporada"] != season:
                continue
            enriched = [match_history(match, history, str(payload["id"])) for match in matches]
            proposals.append({
                "ticket_id": str(payload["id"]),
                "jornada": int(payload["jornada_q15"]),
                "draw_date": max(item["date"] for item in enriched),
                "source_url": payload["source_url"],
                "source": {"name": payload["fuente"], "file": path.name, "validation": "matched_football_data"},
                "matches": [
                    {"number": number, "date": item["date"], "home": item["home"], "away": item["away"], "result": item["sign"]}
                    for number, item in enumerate(enriched[:14], start=1)
                ],
                "pleno15": {"date": enriched[14]["date"], "home": enriched[14]["home"], "away": enriched[14]["away"], "score": enriched[14]["score"]},
            })
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append({"file": path.name, "error": str(exc)})
    proposals.sort(key=lambda ticket: ticket["jornada"])
    return proposals, failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--season", default="2025-2026")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    history = load_season_history(args.season)
    tickets, failures = import_tickets(args.source_dir, args.season, history)
    output = {"schema_version": "1.0", "source": {"name": "Quiniela15, contrastada contra Football-Data", "status": "proposal_not_official_lae"}, "tickets": tickets, "failures": failures}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Boletos convertidos y contrastados: {len(tickets)}")
    print(f"Fallidos/ambiguos: {len(failures)}")
    print(f"Propuesta: {args.output}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
