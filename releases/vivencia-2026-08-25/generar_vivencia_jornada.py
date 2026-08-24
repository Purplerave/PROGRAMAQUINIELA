#!/usr/bin/env python3
"""
GENERADOR DE VIVENCIAS DE JORNADA (MEJORADO)
===========================================

Reconstruye cómo se vivía cada partido de una jornada en el momento exacto.

Ejemplo:
  python scripts/motor/generar_vivencia_jornada.py --jornada 74 --output json

Incluye:
- Posición exacta en tabla
- Diferencia con el líder
- Objetivo de cada equipo (champions / descenso / nada)
- Six-pointers
- Fatiga real (días de descanso + partidos recientes)
- Fase de la temporada
- Derbis y big matches
- Rachas, momentum y patrones especiales (Agente Especial)
"""

import argparse
import json
from pathlib import Path
from datetime import datetime
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import MOTOR_QUINIELA_MAESTRO as motor
from scripts.motor.vivencia import LeagueVivenciaReconstructor
from scripts.motor.context_engine import add_vivencia_to_features

DATOS = PROJECT_ROOT / "DATOS"
SALIDAS = PROJECT_ROOT / "SALIDAS"
SALIDAS.mkdir(exist_ok=True)

def infer_division_season(partidos):
    """Infer division and season intelligently from teams in jornada JSON."""
    sample_teams = [p.get("local") or p.get("home", "") for p in partidos[:3]]
    teams_str = " ".join(sample_teams).lower()
    
    if any(x in teams_str for x in ["real madrid", "barcelona", "atletico", "athletic", "villarreal"]):
        return "Primera", "2025-2026"
    if any(x in teams_str for x in ["kristiansund", "brann", "molde", "bodo", "viking"]):
        return "Eliteserien", "2026"
    if "segunda" in str(partidos[0].get("division", "")).lower() or any("castellon" in t.lower() for t in sample_teams):
        return "Segunda", "2025-2026"
    return "Primera", "2025-2026"

def main():
    parser = argparse.ArgumentParser(description="Reconstruye la vivencia real de una jornada con datos de clasificación")
    parser.add_argument("--jornada", "-j", type=int, required=True)
    parser.add_argument("--output", choices=["json", "text", "both"], default="both")
    parser.add_argument("--cutoff", default=None, help="Fecha de corte (YYYY-MM-DD). Por defecto usa hoy.")
    args = parser.parse_args()

    source = DATOS / f"QUINIELA15_J{args.jornada}.json"
    if not source.exists():
        print(f"ERROR: No existe {source}")
        return

    data = json.loads(source.read_text(encoding="utf-8"))
    raw_partidos = data.get("partidos", [])
    
    partidos = []
    for p in raw_partidos:
        if int(p.get("num", 15)) == 15:
            continue
        partidos.append({
            "num": int(p["num"]),
            "home": p.get("local") or p.get("home"),
            "away": p.get("visitante") or p.get("away"),
            "date": p.get("fecha") or "2026-01-01",
        })

    if not partidos:
        print("No hay partidos válidos")
        return

    # Infer league/season from teams
    division, season = infer_division_season(raw_partidos)
    print(f"Detectado: {division} / {season}")

    # Cargar histórico completo
    print("Cargando histórico...")
    history = motor.load_raw_history()

    cutoff = args.cutoff or datetime.now().strftime("%Y-%m-%d")

    recon = LeagueVivenciaReconstructor()
    recon.process_up_to(history, cutoff)

    print(f"\n=== VIVENCIAS JORNADA {args.jornada} (corte: {cutoff}) ===\n")

    vivencias = []
    for p in partidos:
        try:
            snap = recon.get_vivencia(
                p["home"], p["away"], p["date"],
                division, season
            )
            patterns = recon.detect_patterns(snap)
            
            viv = {
                "num": p["num"],
                "match": f"{snap.home} vs {snap.away}",
                "pos": f"{snap.home} ({snap.home_pos}º, {snap.home_pts}pts) vs {snap.away} ({snap.away_pos}º, {snap.away_pts}pts)",
                "leader": f"Líder: {snap.leader} ({snap.leader_pts} pts)",
                "gaps": f"Local a líder: {snap.home_gap_to_leader} | Visitante: {snap.away_gap_to_leader}",
                "targets": f"{snap.home_target.upper()} vs {snap.away_target.upper()}",
                "stakes": {
                    "six_pointer": snap.is_six_pointer,
                    "title_six": snap.is_title_six_pointer,
                    "relegation_six": snap.is_relegation_six_pointer,
                    "nothing": snap.is_nothing_to_play_for,
                },
                "fatigue": {
                    "home_rest_days": snap.home_days_since_last_match,
                    "away_rest_days": snap.away_days_since_last_match,
                    "home_played": snap.home_matches_played,
                    "away_played": snap.away_matches_played,
                },
                "phase": snap.season_phase,
                "flags": [f for f, v in {
                    "derby": snap.is_derby,
                    "big_match": snap.is_big_match,
                    "high_stakes": snap.high_stakes
                }.items() if v],
                "goals": {
                    "home_gf_total": snap.home_gf_total,
                    "home_ga_total": snap.home_ga_total,
                    "home_gd": snap.home_gd,
                    "home_gf_last5": snap.home_gf_last5,
                    "away_gf_last5": snap.away_gf_last5,
                },
                "streaks": {
                    "home_win_streak": snap.home_win_streak,
                    "away_win_streak": snap.away_win_streak,
                    "home_unbeaten": snap.home_unbeaten_streak,
                },
                "momentum": {
                    "home_mom": round(snap.home_momentum_score, 3),
                    "away_mom": round(snap.away_momentum_score, 3),
                    "home_hot": snap.home_is_hot,
                    "away_hot": snap.away_is_hot,
                    "home_cold": snap.home_is_cold,
                },
                "special_patterns": patterns.get("patterns", []),
                "model_features": {}  # populated externally if needed
            }
            vivencias.append(viv)
        except Exception as e:
            print(f"  Error procesando {p['home']} vs {p['away']}: {e}")
            continue

    # Reporte humano
    if args.output in ("text", "both"):
        for v in vivencias:
            print(f"{v['num']:2}. {v['match']}")
            print(f"    {v['pos']}")
            print(f"    {v['leader']}")
            print(f"    Objetivos: {v['targets']}")
            print(f"    Fase: {v['phase']} | Fatiga: L {v['fatigue']['home_rest_days']}d / V {v['fatigue']['away_rest_days']}d")
            flags = ", ".join(v["flags"]) or "ninguno"
            print(f"    Flags: {flags}")
            if any(v["stakes"].values()):
                print(f"    STAKES: {v['stakes']}")
            if v.get("special_patterns"):
                print(f"    PATRONES: {'; '.join(v['special_patterns'])}")
            print()

    # JSON completo
    if args.output in ("json", "both"):
        out = {
            "jornada": args.jornada,
            "cutoff": cutoff,
            "division": division,
            "season": season,
            "generated_at": datetime.now().isoformat(),
            "matches": vivencias,
            "summary": {
                "six_pointers": sum(1 for v in vivencias if v["stakes"]["six_pointer"]),
                "high_stakes": sum(1 for v in vivencias if v.get("flags")),
                "nothing_matches": sum(1 for v in vivencias if v["stakes"]["nothing"]),
                "hot_teams": sum(1 for v in vivencias if v["momentum"].get("home_hot") or v["momentum"].get("away_hot")),
                "derbies": sum(1 for v in vivencias if "derby" in v.get("flags", [])),
            }
        }
        out_path = SALIDAS / f"vivencia_J{args.jornada}.json"
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n✅ JSON guardado en: {out_path}")

    print("\nVIVENCIAS LISTAS. Ahora el modelo puede 'sentir' cómo se vivía la liga en ese momento.")
    print("Agente Especial: Rebuscando hasta en el infierno las rachas, momentum y patrones que el mercado ignora.")

if __name__ == "__main__":
    main()
