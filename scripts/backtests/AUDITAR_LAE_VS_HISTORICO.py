"""Audita combinación oficial LAE contra resultados del histórico local.

No recalcula predicciones ni cambia el motor. Cruza los boletos LAE de
``DATOS/jornadas_lae`` con los CSV de ``DATOS/historico_raw`` y exporta el
detalle partido a partido de las jornadas con desajustes.

Uso:
    python scripts/backtests/AUDITAR_LAE_VS_HISTORICO.py
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.motor.team_names import resolve_history_name  # noqa: E402

DEFAULT_SEASON = "2025-2026"
DEFAULT_JORNADAS = [9, 37, 46, 48, 59]


def parse_date(value: Any):
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            pass
    return None


def sign_1x2(row: dict[str, Any]) -> str:
    ftr = str(row.get("FTR", "")).strip().upper()
    if ftr == "H":
        return "1"
    if ftr == "D":
        return "X"
    if ftr == "A":
        return "2"
    home_goals = int(row.get("FTHG") or 0)
    away_goals = int(row.get("FTAG") or 0)
    if home_goals > away_goals:
        return "1"
    if away_goals > home_goals:
        return "2"
    return "X"


def pleno_bucket(goals: int) -> str:
    return "M" if goals >= 3 else str(goals)


def sign_pleno(row: dict[str, Any]) -> str:
    return pleno_bucket(int(row["FTHG"])) + pleno_bucket(int(row["FTAG"]))


def load_history() -> dict[tuple[str, str], list[dict[str, Any]]]:
    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for path in (PROJECT_ROOT / "DATOS" / "historico_raw").rglob("*.csv"):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("FTHG") in (None, "") or row.get("FTAG") in (None, ""):
                    continue
                row = dict(row)
                row["_date"] = parse_date(row.get("Date"))
                row["_home"] = resolve_history_name(row.get("HomeTeam", ""))
                row["_away"] = resolve_history_name(row.get("AwayTeam", ""))
                row["_source_file"] = str(path.relative_to(PROJECT_ROOT))
                by_pair.setdefault((row["_home"], row["_away"]), []).append(row)
    return by_pair


def closest_match(
    by_pair: dict[tuple[str, str], list[dict[str, Any]]],
    local: str,
    visitante: str,
    target_date,
) -> dict[str, Any] | None:
    home = resolve_history_name(local)
    away = resolve_history_name(visitante)
    candidates = by_pair.get((home, away), [])
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda row: abs((row["_date"] - target_date).days) if row.get("_date") and target_date else 9999,
    )[0]


def audit_jornada(jornada: dict[str, Any], by_pair: dict[tuple[str, str], list[dict[str, Any]]]) -> list[dict[str, Any]]:
    official = jornada.get("combinacion_ganadora")
    season = jornada.get("temporada")
    jornada_num = jornada.get("jornada")
    fecha = jornada.get("fecha")
    target_date = parse_date(fecha)
    rows: list[dict[str, Any]] = []

    if not isinstance(official, list):
        rows.append(
            {
                "temporada": season,
                "jornada": jornada_num,
                "fecha": fecha,
                "num": "",
                "tipo": "jornada",
                "local": "",
                "visitante": "",
                "signo_historico": "",
                "signo_oficial": "",
                "estado": "SIN_COMBINACION_OFICIAL",
                "causa_probable": "La fuente LAE/libertaddigital no trae combinación ganadora parseada",
            }
        )
        return rows

    for partido in jornada.get("partidos", []):
        num = int(partido["num"])
        match = closest_match(by_pair, partido["local"], partido["visitante"], target_date)
        official_sign = str(official[num - 1]) if num - 1 < len(official) else ""
        historical_sign = sign_1x2(match) if match else ""
        estado = "OK" if match and historical_sign == official_sign else "DESAJUSTE"
        rows.append(
            {
                "temporada": season,
                "jornada": jornada_num,
                "fecha": fecha,
                "num": num,
                "tipo": "1X2",
                "local": partido["local"],
                "visitante": partido["visitante"],
                "local_historico": resolve_history_name(partido["local"]),
                "visitante_historico": resolve_history_name(partido["visitante"]),
                "fecha_historico": match.get("_date").isoformat() if match and match.get("_date") else "",
                "marcador_historico": f"{match.get('FTHG')}-{match.get('FTAG')}" if match else "",
                "signo_historico": historical_sign,
                "signo_oficial": official_sign,
                "estado": estado,
                "causa_probable": "" if estado == "OK" else "Resultado histórico no coincide con combinación oficial; revisar aplazado/sorteo/orden/fuente",
                "source_file": match.get("_source_file") if match else "",
            }
        )

    pleno = jornada.get("pleno15") or {}
    if pleno:
        match = closest_match(by_pair, pleno.get("local", ""), pleno.get("visitante", ""), target_date)
        official_sign = str(official[14]) if len(official) >= 15 else ""
        historical_sign = sign_pleno(match) if match else ""
        estado = "OK" if match and historical_sign == official_sign else "DESAJUSTE"
        rows.append(
            {
                "temporada": season,
                "jornada": jornada_num,
                "fecha": fecha,
                "num": 15,
                "tipo": "PLENO15",
                "local": pleno.get("local", ""),
                "visitante": pleno.get("visitante", ""),
                "local_historico": resolve_history_name(pleno.get("local", "")),
                "visitante_historico": resolve_history_name(pleno.get("visitante", "")),
                "fecha_historico": match.get("_date").isoformat() if match and match.get("_date") else "",
                "marcador_historico": f"{match.get('FTHG')}-{match.get('FTAG')}" if match else "",
                "signo_historico": historical_sign,
                "signo_oficial": official_sign,
                "estado": estado,
                "causa_probable": "" if estado == "OK" else "Pleno al 15 no coincide; puede ser combinación oficial incompleta o criterio distinto",
                "source_file": match.get("_source_file") if match else "",
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audita LAE vs histórico para jornadas concretas.")
    parser.add_argument("--season", default=DEFAULT_SEASON)
    parser.add_argument("--jornadas", nargs="*", type=int, default=DEFAULT_JORNADAS)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "salida" / "auditoria_lae_vs_historico.csv",
    )
    args = parser.parse_args()

    lae_path = PROJECT_ROOT / "DATOS" / "jornadas_lae" / f"jornadas_lae_{args.season}.json"
    if not lae_path.exists():
        print(f"ERROR: no existe {lae_path}")
        return 2

    data = json.loads(lae_path.read_text(encoding="utf-8"))
    jornadas = {int(j["jornada"]): j for j in data.get("jornadas", []) if "jornada" in j}
    by_pair = load_history()

    rows: list[dict[str, Any]] = []
    for jornada_num in args.jornadas:
        jornada = jornadas.get(jornada_num)
        if not jornada:
            rows.append(
                {
                    "temporada": args.season,
                    "jornada": jornada_num,
                    "estado": "JORNADA_NO_ENCONTRADA",
                }
            )
            continue
        rows.extend(audit_jornada(jornada, by_pair))

    write_csv(args.output, rows)
    problemas = [row for row in rows if row.get("estado") != "OK"]
    print(f"Guardado: {args.output}")
    print(f"Filas auditadas: {len(rows)}")
    print(f"Problemas: {len(problemas)}")
    for row in problemas:
        print(
            f"{row.get('temporada')} J{row.get('jornada')} #{row.get('num')} "
            f"{row.get('local')} - {row.get('visitante')} | "
            f"hist={row.get('signo_historico')} oficial={row.get('signo_oficial')} | "
            f"{row.get('marcador_historico', '')} | {row.get('estado')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
