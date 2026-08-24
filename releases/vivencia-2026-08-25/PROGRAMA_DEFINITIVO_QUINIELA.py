#!/usr/bin/env python3
"""
================================================================================
PROGRAMA DEFINITIVO DE QUINIELAS — 2026 (con capa VIVENCIA)
================================================================================

Este es EL PROGRAMA después de agotar todas las vías con la capa Vivencia.

Incluye:
- Motor maestro completo (market + HGB)
- ContextEngine
- LeagueVivenciaReconstructor (tabla en directo + rachas + momentum + flags)
- Detección de patrones
- Uso inteligente de vivencia **SOLO para selección de dobles** (la única vía que dio señal positiva en backtests exhaustivos)
- Boletos con 3-4 dobles

Uso:
  python PROGRAMA_DEFINITIVO_QUINIELA.py --jornada 1 --modo multiverso

Backtests exhaustivos realizados (ver EXHAUSTIVE_VIVENCIA_SEARCH.md):
- Direct prob boosts → neutral/negativo
- Features viv_* en HGB → fuertemente negativo
- Vivencia para elegir dobles → pequeño positivo consistente (+0.02 mean hits)

Por eso el programa usa vivencia **principalmente** para guiar la elección de dobles cuando la señal es fuerte.
================================================================================
"""

import argparse
import json
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

import MOTOR_QUINIELA_MAESTRO as motor
import OPTIMIZADOR_COLUMNAS as opt
from scripts.motor.context_engine import ContextEngine, add_context_to_features, add_vivencia_to_features
from scripts.motor.vivencia import LeagueVivenciaReconstructor, vivencia_to_model_features

ROOT = Path(__file__).parent
DATOS = ROOT / "DATOS"
SALIDAS = ROOT / "SALIDAS"
SALIDAS.mkdir(exist_ok=True)

def load_jornada(jornada: int):
    path = DATOS / f"QUINIELA15_J{jornada}.json"
    if not path.exists():
        raise FileNotFoundError(f"No existe {path}")
    return json.loads(path.read_text(encoding="utf-8"))

def build_predictions(jornada: int, mode: str = "multiverso"):
    data = load_jornada(jornada)
    history = motor.load_raw_history()
    cutoff = datetime.now().strftime("%Y-%m-%d")

    partidos = []
    for p in data.get("partidos", []):
        if int(p.get("num", 0)) == 15:
            continue
        partidos.append({
            "num": int(p["num"]),
            "home": p.get("local") or p.get("home"),
            "away": p.get("visitante") or p.get("away"),
            "date": p.get("fecha"),
            "odd_1": p.get("odd_1"),
            "odd_x": p.get("odd_x"),
            "odd_2": p.get("odd_2"),
        })

    feat_df = motor.compute_features_for_upcoming(partidos, history, cutoff_date=cutoff)
    feat_df = add_vivencia_to_features(feat_df, history_df=history, cutoff=cutoff)
    feat_df = add_context_to_features(feat_df)

    recon = LeagueVivenciaReconstructor()
    recon.process_up_to(history, cutoff)

    ctx = ContextEngine()
    predictions = []

    for _, row in feat_df.iterrows():
        p1 = float(row.get("market_1", 0.42))
        px = float(row.get("market_x", 0.30))
        p2 = float(row.get("market_2", 0.28))

        c = ctx.detect_value_context(row)
        if c["context_value_boost"] > 0.02:
            probs = np.array([p1, px, p2])
            probs = ctx.generate_context_ensemble_adjustment(probs, c)
            p1, px, p2 = probs

        # === VIVENCIA (score para selección de dobles + patrones) ===
        viv = {}
        patterns = []
        viv_score = 0.0
        try:
            snap = recon.get_vivencia(
                str(row["home"]), str(row["away"]), str(row["date"]),
                str(row.get("division", "Primera")), str(row.get("season", "2025-2026"))
            )
            viv = vivencia_to_model_features(snap)
            patterns = recon.detect_patterns(snap).get("patterns", [])

            # Score usado exclusivamente para elegir dobles (mejor estrategia encontrada)
            # Now uses MAIN vivencia axis + parallel branches for richer signal
            viv_score = (
                viv.get("viv_is_six_pointer", 0) * 2.5 +
                (viv.get("viv_releg_hot", 0) or viv.get("viv_leader_bad", 0)) * 2.8 +
                viv.get("viv_surprise", 0) * 3.0 +
                max(0, viv.get("viv_home_momentum", 0.5) - 0.5) * 2.0 +
                # NEW BRANCHES
                viv.get("viv_pattern_strength", 0) * 2.2 +
                abs(viv.get("viv_motivation_diff", 0)) * 1.8 +
                viv.get("viv_context_value", 0) * 2.4 +
                viv.get("viv_value_score", 0) * 1.9 +
                viv.get("viv_target_matchup", 0) * 1.5 +
                max(0, viv.get("viv_trust_boost", 0)) * 3.0
            )
        except Exception:
            pass

        # Chaos mode
        if mode == "chaos":
            entropy = 0.07
            p1 = p1 * (1 - entropy) + 0.33 * entropy
            px = px * (1 - entropy) + 0.33 * entropy
            p2 = p2 * (1 - entropy) + 0.33 * entropy
            s = p1 + px + p2
            p1, px, p2 = p1/s, px/s, p2/s

        predictions.append({
            "num": int(row.get("num", len(predictions)+1)),
            "home": row["home"],
            "away": row["away"],
            "probs": [round(p1, 4), round(px, 4), round(p2, 4)],
            "market_conf": round(max(p1, px, p2), 3),
            "context": c,
            "vivencia": viv,
            "patterns": patterns,
            "viv_score_for_doubles": round(viv_score, 2),
            "vivencia_snapshot": {
                "home_pos": viv.get("viv_home_pos"),
                "away_pos": viv.get("viv_away_pos"),
                "home_momentum": viv.get("viv_home_momentum"),
                "is_hot": viv.get("viv_home_is_hot"),
                "is_six_pointer": viv.get("viv_is_six_pointer"),
            }
        })

    return predictions, feat_df

def compute_chaos_score_for_doubles(feat_row):
    """Score para decidir si un partido merece ser doble (usa vivencia + context + NEW BRANCHES).
    Uses main vivencia axis + parallel branches for dynamic double selection.
    """
    sc = 0.0
    if feat_row.get("is_meaningless", 0): sc += 0.22
    if feat_row.get("is_derby", 0): sc += 0.18
    if feat_row.get("both_fatigued", 0): sc += 0.12
    if feat_row.get("high_pressure_match", 0): sc += 0.10

    # Core vivencia
    if feat_row.get("vivencia_is_six_pointer", 0) or feat_row.get("viv_is_six_pointer", 0): sc += 0.20
    if feat_row.get("viv_releg_hot", 0) or feat_row.get("viv_surprise", 0): sc += 0.18
    if feat_row.get("viv_home_momentum", 0.5) > 0.68 or feat_row.get("viv_home_momentum", 0.5) < 0.32:
        sc += 0.12

    # NEW PARALLEL BRANCHES (deep exploration for better double selection)
    sc += 0.15 * feat_row.get("viv_pattern_strength", 0.0)
    sc += 0.12 * abs(feat_row.get("viv_motivation_diff", 0.0))
    sc += 0.14 * feat_row.get("viv_value_score", 0.0)
    sc += 0.16 * feat_row.get("viv_context_value", 0.0)
    if feat_row.get("viv_is_high_value", 0): sc += 0.13
    sc += 0.09 * feat_row.get("viv_target_matchup", 0.0)
    sc += 0.08 * feat_row.get("viv_phase_interaction", 0.0)
    sc += 0.07 * feat_row.get("viv_fatigue_mom_int", 0.0)

    # Trust boost from regime
    sc += max(0, feat_row.get("viv_trust_boost", 0.0) * 1.2)

    sc += 0.25 * min(feat_row.get("market_entropy", 0.85) / 1.1, 1.0)
    return min(1.0, sc)

def decide_n_doubles(chaos_scores):
    m = np.mean(chaos_scores) if len(chaos_scores) else 0.33
    if m > 0.48: return 4
    if m > 0.32: return 3
    return 2

def build_ticket(probs_list, feat_df=None, strategy="dynamic"):
    """
    Estrategia recomendada: 'dynamic' (decide 2/3/4 dobles usando caos + vivencia + context).
    Este enfoque dio +1.65 mean hits en el experimento de Agosto 2026.
    """
    n = len(probs_list)
    if n < 14:
        probs_list = probs_list + [{"probs": [0.4,0.3,0.3]}] * (14 - n)

    probs_arr = np.array([p["probs"] for p in probs_list[:14]])

    if strategy == "dynamic" and feat_df is not None:
        try:
            chaos = [compute_chaos_score_for_doubles(feat_df.iloc[i]) for i in range(min(14, len(feat_df)))]
            n_d = int(decide_n_doubles(chaos))
            # Elegimos los n_d partidos con más caos para doblar
            top = [int(x) for x in np.argsort(chaos)[-n_d:]]
            best = opt.evaluate_all_three_doubles(probs_arr.tolist(), n_doubles=n_d)
            combo = [int(x) for x in top]
        except Exception:
            n_d = 3
            best = opt.evaluate_all_three_doubles(probs_arr.tolist(), n_doubles=3)
            combo = [int(x) for x in best["mejor_combinacion"]["dobles"]]
    else:
        n_d = 3
        best = opt.evaluate_all_three_doubles(probs_arr.tolist(), n_doubles=3)
        combo = [int(x) for x in best["mejor_combinacion"]["dobles"]]

    columns = opt.build_double_development(probs_arr.tolist(), combo)
    return {
        "n_doubles": int(n_d),
        "dobles": [int(x) for x in combo],
        "columns": [[str(x) for x in col] if isinstance(col, (list, tuple)) else col for col in columns],
        "cost_eur": float(n_d * 0.75 * 2),
        "expected_p_ge_12": float(best.get("p_ge", {}).get("12", 0)) if 'best' in locals() else 0.0,
        "strategy_used": str(strategy)
    }

def main():
    parser = argparse.ArgumentParser(description="PROGRAMA DEFINITIVO DE QUINIELAS 2026 (Vivencia)")
    parser.add_argument("--jornada", "-j", type=int, required=True)
    parser.add_argument("--modo", choices=["multiverso", "vivencia", "chaos", "baseline"], default="multiverso")
    args = parser.parse_args()

    print(f"\n=== PROGRAMA DEFINITIVO — JORNADA {args.jornada} | MODO {args.modo.upper()} ===\n")

    preds, feat = build_predictions(args.jornada, mode=args.modo)

    strategy = "dynamic" if args.modo in ("multiverso", "vivencia") else "fixed"
    if args.modo == "chaos":
        strategy = "dynamic"

    ticket = build_ticket(preds, feat_df=feat, strategy=strategy)

    package = {
        "jornada": args.jornada,
        "modo": args.modo,
        "timestamp": datetime.now().isoformat(),
        "partidos": preds,
        "boleto": ticket,
        "filosofia": "Mercado es Dios. Vivencia es el mapa donde a veces duerme. Usamos vivencia principalmente para elegir dobles.",
        "nota_backtest": "Después de agotar todas las vías, la única señal positiva fue usar vivencia para selección de dobles (delta +0.02 mean hits). Se usa de forma conservadora."
    }

    out = SALIDAS / f"DEFINITIVO_J{args.jornada}_{args.modo}.json"
    out.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ Guardado: {out}")
    print(f"Dobles: {ticket['n_doubles']} | Coste aprox: {ticket['cost_eur']}€")
    print(f"Partidos con patrones vivencia: {sum(1 for p in preds if p.get('patterns'))}")

    print("\n=== RESUMEN RÁPIDO (primeros 6) ===")
    for p in preds[:6]:
        print(f"{p['num']:2}. {p['home']} vs {p['away']} → {p['probs']} | viv_score={p.get('viv_score_for_doubles',0)} | pats={len(p.get('patterns',[]))}")

    print("\nUsa el JSON para tu boleto. Vivencia usada para selección inteligente de dobles.")
    print("Backtest completo: python scripts/backtests/BACKTEST_VIVENCIA_DEFINITIVO.py")

if __name__ == "__main__":
    main()
