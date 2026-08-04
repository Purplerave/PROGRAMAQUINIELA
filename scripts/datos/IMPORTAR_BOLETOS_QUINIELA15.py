#!/usr/bin/env python3
"""Convierte boletos de resultados de Quiniela15 en propuestas auditables.

Los JSON de entrada contienen composición, marcador y signo, pero no fecha por
partido ni escrutinio. Este importador deriva la fecha *solo* cuando el par
local/visitante tiene una coincidencia única en Football-Data de la temporada,
y valida tanto marcador como signo. Clasifica cada boleto en tres grupos,
preservando el motivo exacto de cada partido:

- ``tickets``: los 15 partidos contrastados (propuesta evaluable);
- ``out_of_coverage``: boleto completo salvo por partidos fuera de
  Football-Data (p. ej. competiciones europeas, Copa o no incluidas en la
  temporada), con el detalle de cuáles no se pudieron contrastar;
- ``failures``: boleto con datos inconsistentes (marcador/signo distinto a
  Football-Data, coincidencia ambigua) o esquema inválido.

Escribe una propuesta en ``salida``; nunca altera ni versiona los JSON fuente
ni los CSV históricos.
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

# Alias mínimos observados en boletos Quiniela15 y en la composición XML de
# quinielista.es (nombres estilo LAE) frente a Football-Data. Las claves están
# en el espacio canónico de canonical_team (minúsculas, sin signos).
ALIASES = {
    # Nombres Quiniela15 -> nombres efectivos del CSV Football-Data 2025-26.
    "at madrid": "ath madrid",
    "athletic": "ath bilbao",
    "rayo": "vallecano",
    "real oviedo": "oviedo",
    "r sociedad": "sociedad",
    "r santander": "santander",
    "r zaragoza": "zaragoza",
    "c leonesa": "cultural leonesa",
    "r sociedad b": "sociedad b",
    "espanyol": "espanol",
    "sporting gijon": "sp gijon",
    "deportivo": "la coruna",
    "andorra": "andorra",
    # Nombres estilo LAE / quinielista.es (composición oficial) -> CSV.
    # Nota: los puntos de las siglas ("F.C.") se convierten en espacios en el
    # espacio canónico ("f c barcelona"), por lo que se incluyen ambas formas.
    "athletic club": "ath bilbao",
    "athletic bilbao": "ath bilbao",
    "atletico de madrid": "ath madrid",
    "club atletico de madrid": "ath madrid",
    "fc barcelona": "barcelona",
    "f c barcelona": "barcelona",
    "real betis": "betis",
    "real betis balompie": "betis",
    "rcd espanyol": "espanol",
    "rcd espanyol de barcelona": "espanol",
    "r c d espanyol": "espanol",
    "r c d espanyol de barcelona": "espanol",
    "real sociedad": "sociedad",
    "real sociedad b": "sociedad b",
    "real sporting de gijon": "sp gijon",
    "sporting de gijon": "sp gijon",
    "rc deportivo": "la coruna",
    "r c deportivo": "la coruna",
    "deportivo de la coruna": "la coruna",
    "racing de santander": "santander",
    "real valladolid": "valladolid",
    "real valladolid cf": "valladolid",
    "real valladolid c f": "valladolid",
    "cultural y deportiva leonesa": "cultural leonesa",
    "real zaragoza": "zaragoza",
    "rayo vallecano": "vallecano",
    "ud almeria": "almeria",
    "u d almeria": "almeria",
    "fc andorra": "andorra",
    "f c andorra": "andorra",
    "cd castellon": "castellon",
    "c d castellon": "castellon",
    "ad ceuta fc": "ceuta",
    "a d ceuta fc": "ceuta",
    "cd leganes": "leganes",
    "c d leganes": "leganes",
    "cd mirandes": "mirandes",
    "c d mirandes": "mirandes",
    "sd eibar": "eibar",
    "s d eibar": "eibar",
    "sd huesca": "huesca",
    "s d huesca": "huesca",
    "ud las palmas": "las palmas",
    "u d las palmas": "las palmas",
    "cadiz cf": "cadiz",
    "cadiz c f": "cadiz",
    "elche cf": "elche",
    "elche c f": "elche",
    "granada cf": "granada",
    "granada c f": "granada",
    "malaga cf": "malaga",
    "malaga c f": "malaga",
    "cordoba cf": "cordoba",
    "cordoba c f": "cordoba",
    "burgos cf": "burgos",
    "burgos c f": "burgos",
    "albacete balompie": "albacete",
    "ca osasuna": "osasuna",
    "c a osasuna": "osasuna",
    "rc celta": "celta",
    "r c celta": "celta",
    "rcd mallorca": "mallorca",
    "r c d mallorca": "mallorca",
    "deportivo alaves": "alaves",
    "real madrid cf": "real madrid",
    "real madrid c f": "real madrid",
    "getafe cf": "getafe",
    "getafe c f": "getafe",
    "girona fc": "girona",
    "girona f c": "girona",
    "sevilla fc": "sevilla",
    "sevilla f c": "sevilla",
    "valencia cf": "valencia",
    "valencia c f": "valencia",
    "villarreal cf": "villarreal",
    "villarreal c f": "villarreal",
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


def pleno_bucket_from_score(home_goals: int, away_goals: int) -> str:
    """Representación Quiniela15 del Pleno: marcador normal o bucket M (3+)."""
    home = "M" if home_goals >= 3 else str(home_goals)
    away = "M" if away_goals >= 3 else str(away_goals)
    # Quiniela15 usa siempre guion; M representa tres o más goles (p. ej. M-2).
    return f"{home}-{away}"


PLENO_BUCKET_RE = re.compile(r"^(?:[0-9M])+-(?:[0-9M])+$")


def pleno_bucket_from_source(score_text: object) -> str | None:
    """Bucket del marcador del Pleno tal como lo publica la fuente.

    Acepta tanto el marcador exacto (``3-2``) como el bucket ya agregado
    (``M-2``); devuelve ``None`` si la cadena no es ninguna de las dos formas.
    """
    text = str(score_text).strip()
    if not PLENO_BUCKET_RE.fullmatch(text):
        return None
    home, away = text.split("-")
    bucket = lambda side: "M" if side.isdigit() and int(side) >= 3 else side
    return f"{bucket(home)}-{bucket(away)}"


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
        if item["num"] < 15:
            if not re.fullmatch(r"\d+-\d+", str(item["resultado"])):
                raise ValueError(f"{payload['id']} partido {item['num']}: marcador inválido")
            if item["signo"] not in SIGNS:
                raise ValueError(f"{payload['id']} partido {item['num']}: signo 1X2 inválido")
        else:
            # Pleno al 15: marcador exacto ("3-2") o bucket ("M-2"); el signo es
            # el bucket de Pleno. La coherencia se valida al contrastar.
            if pleno_bucket_from_source(item["resultado"]) is None:
                raise ValueError(f"{payload['id']} partido 15: marcador de Pleno inválido")
            if pleno_bucket_from_source(item["signo"]) is None:
                raise ValueError(f"{payload['id']} partido 15: signo de Pleno inválido")
    return sorted(matches, key=lambda item: item["num"])


def enrich_match(source_match: dict[str, Any], history: pd.DataFrame, ticket_id: str) -> dict[str, Any]:
    """Contrasta un partido contra Football-Data sin abortar el boleto completo.

    Devuelve ``status: "matched"`` con los datos enriquecidos o
    ``status: "error"`` con ``motivo`` y ``detalle`` conservando el número de
    partido, los equipos y la causa exacta para la revisión.
    """
    num = source_match["num"]
    local, away_team = canonical_team(source_match["local"]), canonical_team(source_match["visitante"])
    context = f"{ticket_id} #{num} {source_match['local']} - {source_match['visitante']}"
    candidates = history[(history["home"] == local) & (history["away"] == away_team)]
    if len(candidates) != 1:
        motivo = "coincidencia_ambigua" if len(candidates) > 1 else "no_en_football_data"
        return {
            "status": "error", "num": num,
            "local": repair_mojibake(source_match["local"]),
            "visitante": repair_mojibake(source_match["visitante"]),
            "motivo": motivo,
            "detalle": f"{context}: coincidencias Football-Data={len(candidates)}",
        }
    row = candidates.iloc[0]
    expected_score = f"{row.home_goals}-{row.away_goals}"
    if num < 15:
        if str(source_match["resultado"]) != expected_score:
            return error_match(source_match, num, "marcador_inconsistente", f"{context}: marcador fuente={source_match['resultado']} != Football-Data={expected_score}")
        expected_sign = sign_from_goals(int(row.home_goals), int(row.away_goals))
        if source_match["signo"] != expected_sign:
            return error_match(source_match, num, "signo_inconsistente", f"{context}: signo fuente={source_match['signo']} != Football-Data={expected_sign}")
    else:
        expected_bucket = pleno_bucket_from_score(int(row.home_goals), int(row.away_goals))
        if pleno_bucket_from_source(source_match["signo"]) != expected_bucket:
            return error_match(source_match, num, "signo_inconsistente", f"{context}: signo Pleno fuente={source_match['signo']} != bucket={expected_bucket}")
        if pleno_bucket_from_source(source_match["resultado"]) != expected_bucket:
            return error_match(source_match, num, "marcador_inconsistente", f"{context}: marcador Pleno fuente={source_match['resultado']} != bucket={expected_bucket} (marcador Football-Data={expected_score})")
    return {
        "status": "matched",
        "date": row.date.strftime("%Y-%m-%d"),
        "home": repair_mojibake(source_match["local"]),
        "away": repair_mojibake(source_match["visitante"]),
        "score": expected_score,
        "sign": sign_from_goals(int(row.home_goals), int(row.away_goals)),
        "division": row.division,
    }


def error_match(source_match: dict[str, Any], num: int, motivo: str, detalle: str) -> dict[str, Any]:
    return {
        "status": "error", "num": num,
        "local": repair_mojibake(source_match["local"]),
        "visitante": repair_mojibake(source_match["visitante"]),
        "motivo": motivo,
        "detalle": detalle,
    }


def build_proposal(payload: dict[str, Any], enriched: list[dict[str, Any]], file_name: str) -> dict[str, Any]:
    return {
        "ticket_id": str(payload["id"]),
        "jornada": int(payload["jornada_q15"]),
        "draw_date": max(item["date"] for item in enriched),
        "source_url": payload["source_url"],
        "source": {"name": payload["fuente"], "file": file_name, "validation": "matched_football_data"},
        "matches": [
            {"number": number, "date": item["date"], "home": item["home"], "away": item["away"], "result": item["sign"]}
            for number, item in enumerate(enriched[:14], start=1)
        ],
        "pleno15": {"date": enriched[14]["date"], "home": enriched[14]["home"], "away": enriched[14]["away"], "score": enriched[14]["score"]},
    }


def classify_enriched(
    payload: dict[str, Any],
    matches: list[dict[str, Any]],
    enriched: list[dict[str, Any]],
    file_name: str,
) -> tuple[str, dict[str, Any]]:
    """Clasifica un boleto ya enriquecido partido a partido.

    Devuelve ``(kind, record)`` donde ``kind`` es ``"ticket"``,
    ``"out_of_coverage"`` o ``"failure"`` y ``record`` es la entrada de la
    propuesta correspondiente. Un boleto con cualquier partido inconsistente
    (marcador/signo distinto a Football-Data o coincidencia ambigua) va a
    ``failure``; solo los que fallan exclusivamente por partidos ausentes en
    Football-Data van a ``out_of_coverage``; el resto, ya contrastados, a
    ``ticket``. Reutilizable por otros compositores (p. ej. XML de
    quinielista.es + resultados Football-Data).
    """
    errors = [item for item in enriched if item["status"] == "error"]
    base = {
        "file": file_name,
        "ticket_id": str(payload["id"]),
        "jornada": int(payload["jornada_q15"]),
        "source_url": payload["source_url"],
    }
    if not errors:
        return "ticket", build_proposal(payload, enriched, file_name)
    unmatched = [item for item in errors if item["motivo"] == "no_en_football_data"]
    inconsistent = [item for item in errors if item["motivo"] != "no_en_football_data"]
    if unmatched and not inconsistent:
        return "out_of_coverage", {
            **base,
            "reason": "out_of_coverage",
            "matches_covered": sum(item["status"] == "matched" for item in enriched),
            "matches_total": len(matches),
            "unmatched": [
                {"num": item["num"], "local": item["local"], "visitante": item["visitante"], "motivo": item["motivo"]}
                for item in unmatched
            ],
        }
    return "failure", {
        **base,
        "reason": "inconsistent",
        "error": errors[0]["detalle"],
        "match_errors": [
            {"num": item["num"], "local": item["local"], "visitante": item["visitante"], "motivo": item["motivo"], "detalle": item["detalle"]}
            for item in errors
        ],
    }


def import_tickets(source_dir: Path, season: str, history: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    """Importa y clasifica los boletos de una carpeta fuente.

    Devuelve ``{"tickets": [...], "out_of_coverage": [...], "failures": [...]}``.
    """
    result: dict[str, list[dict[str, Any]]] = {"tickets": [], "out_of_coverage": [], "failures": []}
    if not source_dir.is_dir():
        return result
    for path in sorted(source_dir.glob("Q15_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            matches = validate_source_ticket(payload)
            if payload["temporada"] != season:
                continue
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            result["failures"].append({"file": path.name, "reason": "invalid_schema", "error": str(exc)})
            continue
        enriched = [enrich_match(match, history, str(payload["id"])) for match in matches]
        kind, record = classify_enriched(payload, matches, enriched, path.name)
        result[{"ticket": "tickets", "out_of_coverage": "out_of_coverage", "failure": "failures"}[kind]].append(record)
    result["tickets"].sort(key=lambda ticket: ticket["jornada"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--season", default="2025-2026")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not args.source_dir.is_dir():
        print(f"Aviso: no existe la carpeta fuente {args.source_dir}; no se importó nada.")
        return 1
    history = load_season_history(args.season)
    result = import_tickets(args.source_dir, args.season, history)
    tickets, out_of_coverage, failures = result["tickets"], result["out_of_coverage"], result["failures"]
    output = {
        "schema_version": "1.0",
        "source": {"name": "Quiniela15, contrastada contra Football-Data", "status": "proposal_not_official_lae"},
        "summary": {
            "total": len(tickets) + len(out_of_coverage) + len(failures),
            "accepted": len(tickets),
            "out_of_coverage": len(out_of_coverage),
            "rejected": len(failures),
        },
        "tickets": tickets,
        "out_of_coverage": out_of_coverage,
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Boletos convertidos y contrastados: {len(tickets)}")
    print(f"Fuera de cobertura Football-Data (p. ej. competiciones europeas): {len(out_of_coverage)}")
    print(f"Fallidos/inconsistentes: {len(failures)}")
    print(f"Propuesta: {args.output}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
