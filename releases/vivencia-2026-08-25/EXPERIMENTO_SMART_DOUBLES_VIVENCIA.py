#!/usr/bin/env python3
"""
EXPERIMENTO_SMART_DOUBLES_VIVENCIA.py
=====================================

La única señal positiva encontrada hasta ahora con Vivencia:
Usar la vivencia + contexto NO para cambiar las probabilidades 1X2,
sino para **elegir inteligentemente qué 3 partidos doblar**.

Estrategia:
- Se mantienen las probs del motor base (market + HGB).
- Se calcula un "vivencia_value_score" por partido:
    score = 0.35 * is_six_pointer +
            0.25 * (releg_hot or surprise or leader_bad) +
            0.20 * |home_momentum - 0.5| +   # momentum extremo = más caos
            0.15 * context_value_boost +
            0.05 * market_entropy
- Se eligen los 3 partidos con mayor score para doblar.
- Se compara contra la selección "normal" del optimizador (second probability).

Mide: mean hits, P(≥12), ROI con 3 dobles.

Este es el siguiente paso lógico según el ROADMAP.
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import json
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import MOTOR_QUINIELA_MAESTRO as motor
import OPTIMIZADOR_COLUMNAS as opt
from scripts.motor.context_engine import add_context_to_features
from scripts.motor.vivencia import LeagueVivenciaReconstructor, vivencia_to_model_features

OUT_DIR = PROJECT_ROOT / "salida"
OUT_DIR.mkdir(exist_ok=True)

PRIZES = {15: 150000, 14: 45000, 13: 12000, 12: 3500, 11: 900, 10: 250}

def compute_vivencia_value_score(row, snap_vf, ctx):
    """Score 0-1 para decidir si un partido merece ser doblado."""
    score = 0.0

    # Vivencia signals (las que más han funcionado)
    if snap_vf.get("viv_is_six_pointer", 0) > 0.5:
        score += 0.35
    if snap_vf.get("viv_releg_hot", 0) > 0.5:
        score += 0.18
    if snap_vf.get("viv_surprise", 0) > 0.5:
        score += 0.15
    if snap_vf.get("viv_leader_bad", 0) > 0.5:
        score += 0.12

    mom = snap_vf.get("viv_home_momentum", 0.5)
    score += 0.20 * abs(mom - 0.5)   # momentum extremo = más valor para doblar

    # Context
    score += 0.15 * ctx.get("context_value_boost", 0.0)

    # Market uncertainty (más entropía = más interesante doblar)
    entropy = row.get("market_entropy", 0.9)
    score += 0.05 * min(entropy, 1.1)

    return min(1.0, score)

def evaluate_with_fixed_doubles(probs_list, results, doubles_indices):
    """Evalúa una jornada forzando dobles en posiciones concretas."""
    if len(probs_list) < 14:
        return 0, 0

    # Construimos la selección con los dobles indicados
    selected = []
    for i, p in enumerate(probs_list[:14]):
        if i in doubles_indices:
            # Doble: las dos opciones más probables
            sorted_idx = np.argsort(p)[::-1][:2]
            selected.append([list("1X2")[j] for j in sorted_idx])
        else:
            # Simple: el favorito
            selected.append([list("1X2")[np.argmax(p)]])

    hits = sum(1 for s, res in zip(selected, results[:14]) if res in s)
    prize = PRIZES.get(hits, 0)
    return hits, prize

def run_smart_doubles_experiment(seasons=None):
    print("="*72)
    print("EXPERIMENTO: SMART DOUBLES GUIDED BY VIVENCIA + CONTEXT")
    print("Objetivo: Elegir los 3 dobles usando vivencia en vez de second-probability")
    print("="*72)

    raw = motor.load_raw_history()
    raw = raw[raw.division == "Primera"].copy()

    feat = motor.rolling_team_features(raw)
    feat = feat[feat.result.isin(motor.LABEL_MAP)].copy()

    if seasons is None:
        seasons = [s for s in sorted(feat.season.dropna().unique()) if str(s) >= "2021-2022"][-4:]

    baseline_hits = []
    smart_hits = []

    for season in seasons:
        print(f"\n--- {season} ---")
        try:
            preds, _ = motor.run_season_backtest(feat, season)
            preds = preds.sort_values(["date", "division", "home", "away"]).reset_index(drop=True)

            # Enriquecer con vivencia y contexto
            cutoff = f"{season.split('-')[0]}-08-20"
            try:
                preds = add_context_to_features(preds)
            except:
                pass

            recon = LeagueVivenciaReconstructor()
            recon.process_up_to(raw, cutoff)

            # Calcular score de vivencia para cada partido
            viv_scores = []
            for _, row in preds.iterrows():
                try:
                    snap = recon.get_vivencia(
                        str(row["home"]), str(row["away"]), str(row["date"]),
                        str(row.get("division", "Primera")), season
                    )
                    vf = vivencia_to_model_features(snap)
                    ctx = {"context_value_boost": row.get("context_value_boost", 0.0)}
                    sc = compute_vivencia_value_score(row, vf, ctx)
                except:
                    sc = 0.1
                viv_scores.append(sc)

            preds["vivencia_double_score"] = viv_scores

            # Evaluación por jornada
            for start in range(0, len(preds), 15):
                g = preds.iloc[start:start+15]
                if len(g) < 14: continue

                bprobs = g[["market_1", "market_x", "market_2"]].fillna(0.33).values.tolist()
                results = g["result"].astype(str).tolist()

                # === BASELINE: mejores 3 dobles según optimizador (second prob) ===
                best = opt.evaluate_all_three_doubles(bprobs, n_doubles=3)
                base_combo = set(best["mejor_combinacion"]["dobles"])
                hb, _ = evaluate_with_fixed_doubles(bprobs, results, base_combo)
                baseline_hits.append(hb)

                # === SMART: los 3 partidos con mayor vivencia_double_score ===
                top3_idx = g["vivencia_double_score"].nlargest(3).index
                local_pos = [list(g.index).index(i) for i in top3_idx]
                hs, _ = evaluate_with_fixed_doubles(bprobs, results, set(local_pos))
                smart_hits.append(hs)

            print(f"  Jornadas: {len([h for h in baseline_hits if True])} (acum)")
            print(f"  Baseline mean so far: {np.mean(baseline_hits[-25:]):.3f}")
            print(f"  Smart     mean so far: {np.mean(smart_hits[-25:]):.3f}")

        except Exception as e:
            print(f"  ERROR {season}: {str(e)[:80]}")
            continue

    # Resultado final
    def stats(hits, name):
        arr = np.array(hits)
        n = len(arr)
        cost = n * 6.0
        prize = sum(PRIZES.get(h, 0) for h in arr)
        roi = (prize - cost) / cost if cost > 0 else -1
        return {
            "name": name,
            "jornadas": n,
            "mean_hits": round(float(arr.mean()), 3),
            "p_ge_12": round(float((arr >= 12).mean()), 4),
            "roi": round(roi, 4)
        }

    b = stats(baseline_hits, "baseline")
    s = stats(smart_hits, "smart_vivencia_doubles")

    result = {
        "experiment": "SMART_DOUBLES_VIVENCIA_v1",
        "timestamp": datetime.now().isoformat(),
        "seasons": seasons,
        "baseline": b,
        "smart_vivencia": s,
        "delta_mean_hits": round(s["mean_hits"] - b["mean_hits"], 3),
        "delta_roi": round(s["roi"] - b["roi"], 4),
        "verdict": "PROMETEDOR - seguir desarrollando" if s["mean_hits"] > b["mean_hits"] else "NEUTRAL"
    }

    out = OUT_DIR / "EXPERIMENTO_SMART_DOUBLES_VIVENCIA.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "="*72)
    print("RESULTADO FINAL")
    print("="*72)
    print(json.dumps(result, indent=2))
    print(f"\nGuardado en: {out}")
    print(f"\n>>> {result['verdict']} <<<")

    return result

if __name__ == "__main__":
    run_smart_doubles_experiment()
