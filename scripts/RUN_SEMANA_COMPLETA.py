"""Ejecuta el flujo semanal mixto sobre un boleto 14+1 explícito.

Por defecto exige DATOS/BOLETO_SEMANAL.json. La captura J3 antigua solo se
usa con --demo, y sus salidas no reemplazan un boleto real.
"""
from __future__ import annotations

import argparse
import math
import json
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import settings
from OPTIMIZADOR_COLUMNAS import columns_contract
from scripts.json_output import write_json
from scripts.motor import ligaf_model, ligam_model
from scripts.motor.boletos import require_positions
from scripts.motor.pleno_model import predecir_pleno
from scripts.motor.temporal import local_timestamp, utc_timestamp

ROOT = settings.PROJECT_DIR
BOLETO_FUENTE = settings.DATOS_DIR / "BOLETO_SEMANAL.json"

# Captura histórica J3 (2026-08-25); prueba local, nunca jornada vigente.
BOLETO_J3_DEFAULT = {
    "fuente": "quiniela15.com", "capturado": "2026-08-25",
    "jornada": 3, "temporada": "2627", "bote_eur": 1300000.0,
    "cierre": "2026-08-29T17:00:00",
    "casillas": [
        {"numero": 1,  "local": "Levante",     "visitante": "Betis"},
        {"numero": 2,  "local": "R. Sociedad", "visitante": "Espanyol"},
        {"numero": 3,  "local": "Sevilla",     "visitante": "At. Madrid"},
        {"numero": 4,  "local": "Real Madrid", "visitante": "Malaga"},
        {"numero": 5,  "local": "Deportivo",   "visitante": "Valencia"},
        {"numero": 6,  "local": "Celta",       "visitante": "Athletic"},
        {"numero": 7,  "local": "Osasuna",     "visitante": "Getafe"},
        {"numero": 8,  "local": "Albacete",    "visitante": "Real Oviedo"},
        {"numero": 9,  "local": "Cadiz",       "visitante": "Valladolid"},
        {"numero": 10, "local": "Cordoba",     "visitante": "Granada"},
        {"numero": 11, "local": "Athletic Club",   "visitante": "Las Planas", "liga_f": True},
        {"numero": 12, "local": "Eibar",           "visitante": "Espanyol",   "liga_f": True},
        {"numero": 13, "local": "Alaves Gloriosas","visitante": "Valencia Fem","liga_f": True},
        {"numero": 14, "local": "Real Madrid W",   "visitante": "Atletico Madrid W", "liga_f": True},
        {"numero": 15, "local": "Barcelona",   "visitante": "Rayo Vallecano"},
    ],
}


def cargar_boleto(path: Path = BOLETO_FUENTE, *, demo: bool = False) -> dict:
    if not demo and not path.is_file():
        raise FileNotFoundError(f"No existe {path}. Proporciona un boleto vigente con --boleto o usa --demo para la J3 de ejemplo.")
    ticket = deepcopy(BOLETO_J3_DEFAULT) if demo else json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(ticket, dict):
        raise ValueError("El boleto semanal debe ser un objeto JSON")
    journey = ticket.get("jornada")
    if type(journey) is not int or journey < 1:
        raise ValueError("El boleto semanal debe declarar una jornada entera positiva")
    if not isinstance(ticket.get("fuente"), str) or not ticket["fuente"].strip():
        raise ValueError("El boleto semanal debe declarar su fuente")
    closure = utc_timestamp(ticket.get("cierre"))
    date_cutoff = utc_timestamp(ticket.get("prediction_cutoff_at", ticket["cierre"]))
    if date_cutoff > closure:
        raise ValueError("prediction_cutoff_at no puede ser posterior al cierre")
    for match in require_positions(ticket.get("casillas"), key="numero"):
        for side in ("local", "visitante"):
            if not isinstance(match.get(side), str) or not match[side].strip():
                raise ValueError(f"Falta {side} en la casilla {match['numero']}")
        if type(match.get("liga_f", False)) is not bool:
            raise ValueError(f"liga_f debe ser booleano (casilla {match['numero']})")
        if match.get("kickoff_at") and closure > utc_timestamp(match["kickoff_at"]):
            raise ValueError(f"Cierre posterior al inicio de la casilla {match['numero']}")
    return ticket


def _fit_at_cutoff(history: list[dict], fit, cutoff: object, competition: str) -> tuple[tuple, int]:
    day = local_timestamp(cutoff).date()
    prior = [p for p in history if p["fecha"].date() < day]
    if not prior:
        raise ValueError(f"Sin histórico anterior al corte para {competition}")
    return fit(prior), len(prior)


def output_label(jornada: int, demo: bool = False) -> str:
    return f"{'demo_' if demo else ''}J{jornada}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--boleto", type=Path, default=BOLETO_FUENTE)
    inputs.add_argument("--demo", action="store_true", help="ejecuta la captura histórica de J3, aislada")
    parser.add_argument("--jornada", type=int, help="comprueba que la jornada coincide con el boleto")
    parser.add_argument("--bote", type=float, help="bote supuesto: solo para EV estimado")
    parser.add_argument("--presupuesto", type=int, default=8, help="número de columnas, de 1 a 8")
    args = parser.parse_args(argv)
    contract = columns_contract()
    if not 1 <= args.presupuesto <= contract["columns_per_ticket"]:
        parser.error(f"--presupuesto debe estar entre 1 y {contract['columns_per_ticket']} columnas")

    try:
        ticket = cargar_boleto(args.boleto, demo=args.demo)
        jornada = ticket["jornada"]
        if args.jornada is not None and args.jornada != jornada:
            raise ValueError(f"Se solicitó J{args.jornada} pero el boleto declara J{jornada}")
        bote = float(args.bote if args.bote is not None else ticket.get("bote_eur", 0))
        if not math.isfinite(bote) or bote < 0:
            raise ValueError("bote_eur debe ser un importe finito no negativo")
        cutoff = min(utc_timestamp(ticket.get("prediction_cutoff_at", ticket["cierre"])), datetime.now(timezone.utc))
        sources = {
            False: ("ligam", ligam_model.cargar_historico, ligam_model.ajustar, ligam_model.predecir, ligam_model.canon_ligam),
            True: ("ligaf", ligaf_model.cargar_dated, ligaf_model.ajustar, ligaf_model.predecir, ligaf_model.canon),
        }
        params, counts = {}, {}
        for league in {p.get("liga_f", False) for p in ticket["casillas"]}:
            name, load, fit, _, _ = sources[league]
            params[league], counts[name] = _fit_at_cutoff(load(), fit, cutoff, name)
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))

    pred_m, pred_f = [], []
    for match in sorted(ticket["casillas"], key=lambda p: p["numero"]):
        num, home, away = (match[k] for k in ("numero", "local", "visitante"))
        female = match.get("liga_f", False)
        name, _, _, predict, canonical = sources[female]
        pred = predict(home, away, *params[female])
        pred["numero"] = num
        if num == 15:
            pred["pleno"] = predecir_pleno(home, away, *params[female], canonical, origen=name)
        if female:
            pred_f.append(pred)
        else:
            pred_m.append({
                "numero": num, "local": home, "visitante": away,
                "prob_1": pred["p1"], "prob_x": pred["px"], "prob_2": pred["p2"],
                "signo_modelo": pred["signo"], "fuente": pred["fuente_ratings"],
                **({"pleno": pred["pleno"]} if num == 15 else {}),
            })
        sign = (pred.get("pleno") or pred)["signo"]
        print(f"  {num:>2}. {home} - {away} -> {sign} [{pred['fuente_ratings']}]", flush=True)

    package = {
        "jornada": jornada, "demo": args.demo,
        "generado": datetime.now(timezone.utc).isoformat(),
        "fuente_boleto": ticket["fuente"], "temporada": ticket.get("temporada"),
        "bote_eur": bote, "cierre": ticket["cierre"], "prediction_cutoff_at": cutoff.isoformat(),
        "partidos_entrenamiento": counts,
        "motores": {
            "ligam": "Poisson log-lineal con decaimiento (histórico reciente football-data)",
            "ligaf": "Poisson log-lineal con decaimiento (StatsBomb 182/281)",
        },
        "ligam": {"predicciones": pred_m}, "ligaf": {"pronosticos": pred_f},
    }
    label = output_label(jornada, args.demo)
    path = settings.SALIDAS_DIR / f"boleto_completo_{label}.json"
    write_json(path, package)
    print(f"Paquete {'de demostración' if args.demo else 'semanal'}: {path}", flush=True)
    cmd = [sys.executable, str(ROOT / "scripts" / "OPTIMIZADOR_BOLETO.py"),
           "--boleto", str(path), "--presupuesto", str(args.presupuesto), "--bote", str(bote)]
    result = subprocess.run(cmd, cwd=ROOT)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
