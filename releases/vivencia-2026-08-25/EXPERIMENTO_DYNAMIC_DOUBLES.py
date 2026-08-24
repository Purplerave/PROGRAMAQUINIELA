#!/usr/bin/env python3
"""
EXPERIMENTO_DYNAMIC_DOUBLES.py
==============================

P0 experimento según el nuevo roadmap post-Vivencia.

Idea central:
En vez de fijar siempre 3 dobles, decidimos dinámicamente el número de dobles (2, 3 o 4)
y cuáles, combinando:
- Market entropy (incertidumbre)
- Context signals (intrascendente, derby, high_pressure)
- Vivencia flags (releg_hot, surprise, six_pointer, momentum extremo)

Métricas objetivo: P(≥12), ROI 6€, mean hits.

Este es el siguiente golpe económico real después de que la rama Vivencia no aportara boosts directos.
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

def chaos_score(row, snap_vf):
    """Score 0-1 de 'caos / valor para poner más dobles'."""
    score = 0.0

    # Context
    if row.get("is_meaningless", 0): score += 0.22
    if row.get("is_derby", 0): score += 0.18
    if row.get("both_fatigued", 0): score += 0.12
    if row.get("high_pressure_match", 0): score += 0.10

    # Vivencia
    if snap_vf.get("viv_is_six_pointer", 0) > 0.5: score += 0.20
    if snap_vf.get("viv_releg_hot", 0) > 0.5: score += 0.15
    if snap_vf.get("viv_surprise", 0) > 0.5: score += 0.13
    if snap_vf.get("viv_leader_bad", 0) > 0.5: score += 0.10

    mom = snap_vf.get("viv_home_momentum", 0.5)
    if abs(mom - 0.5) > 0.25: score += 0.12

    # Market uncertainty
    ent = row.get("market_entropy", 0.85)
    score += 0.25 * min(ent / 1.1, 1.0)

    return min(1.0, score)

def decide_n_doubles(chaos_scores, base=3):
    """Decide cuántos dobles según nivel de caos de la jornada."""
    mean_chaos = np.mean(chaos_scores) if len(chaos_scores) > 0 else 0.3
    if mean_chaos > 0.48:
        return 4
    elif mean_chaos > 0.32:
        return 3
    else:
        return 2

def run_dynamic_doubles_experiment(seasons=None):
    print("="*72)
    print("EXPERIMENTO DYNAMIC DOUBLES (P0 post-Vivencia)")
    print("Decidir número de dobles + cuáles usando context + vivencia + entropy")
    print("="*72)

    raw = motor.load_raw_history()
    raw = raw[raw.division == "Primera"].copy()

    feat = motor.rolling_team_features(raw)
    feat = feat[feat.result.isin(motor.LABEL_MAP)].copy()

    if seasons is None:
        seasons = [s for s in sorted(feat.season.dropna().unique()) if str(s) >= "2021-2022"][-4:]

    baseline_hits = []
    dynamic_hits = []

    for season in seasons:
        print(f"\n--- {season} ---")
        try:
            preds, _ = motor.run_season_backtest(feat, season)
            preds = preds.sort_values(["date", "division", "home", "away"]).reset_index(drop=True)

            preds = add_context_to_features(preds)

            recon = LeagueVivenciaReconstructor()
            cutoff = f"{season.split('-')[0]}-08-20"
            recon.process_up_to(raw, cutoff)

            chaos_scores = []
            for _, row in preds.iterrows():
                try:
                    snap = recon.get_vivencia(str(row["home"]), str(row["away"]), str(row["date"]),
                                              str(row.get("division", "Primera")), season)
                    vf = vivencia_to_model_features(snap)
                    sc = chaos_score(row, vf)
                except:
                    sc = 0.25
                chaos_scores.append(sc)

            preds["chaos_score"] = chaos_scores

            # Por jornada
            for start in range(0, len(preds), 15):
                g = preds.iloc[start:start+15]
                if len(g) < 14: continue

                bprobs = g[["market_1", "market_x", "market_2"]].fillna(0.33).values.tolist()
                res = g["result"].astype(str).tolist()

                # BASELINE: siempre 3 dobles (mejor selección del optimizador)
                best3 = opt.evaluate_all_three_doubles(bprobs, n_doubles=3)
                combo3 = tuple(best3["mejor_combinacion"]["dobles"])
                sel3 = opt.build_double_development(bprobs, combo3)
                hb = sum(1 for s, r in zip(sel3, res) if r in s)
                baseline_hits.append(hb)

                # DYNAMIC
                n_d = decide_n_doubles(g["chaos_score"].values)
                # Elegimos los n_d partidos con mayor chaos_score
                top_idx = g["chaos_score"].nlargest(n_d).index
                local_pos = [list(g.index).index(i) for i in top_idx]
                sel_dyn = []
                for i in range(14):
                    if i in local_pos:
                        top2 = np.argsort(bprobs[i])[::-1][:2]
                        sel_dyn.append([list("1X2")[j] for j in top2])
                    else:
                        sel_dyn.append([list("1X2")[np.argmax(bprobs[i])]])

                hd = sum(1 for s, r in zip(sel_dyn, res) if r in s)
                dynamic_hits.append(hd)

            print(f"  Jornadas acumuladas: {len(baseline_hits)}")
            print(f"  Baseline mean: {np.mean(baseline_hits[-30:]):.2f}")
            print(f"  Dynamic  mean: {np.mean(dynamic_hits[-30:]):.2f}")

        except Exception as e:
            print(f"  ERROR: {str(e)[:70]}")
            continue

    def stats(hits, name):
        arr = np.array(hits)
        n = len(arr)
        cost = n * 6.0
        prize = sum(PRIZES.get(h, 0) for h in arr)
        roi = (prize - cost) / cost if cost > 0 else -1.0
        return {
            "name": name,
            "jornadas": n,
            "mean_hits": round(float(arr.mean()), 3),
            "p_ge_12": round(float((arr >= 12).mean()), 4),
            "roi": round(roi, 4)
        }

    b = stats(baseline_hits, "fixed_3_doubles")
    d = stats(dynamic_hits, "dynamic_doubles")

    result = {
        "experiment": "DYNAMIC_DOUBLES_v1",
        "timestamp": datetime.now().isoformat(),
        "seasons": seasons,
        "fixed_3": b,
        "dynamic": d,
        "delta_mean": round(d["mean_hits"] - b["mean_hits"], 3),
        "delta_p12": round(d["p_ge_12"] - b["p_ge_12"], 4),
        "delta_roi": round(d["roi"] - b["roi"], 4),
        "verdict": "AVANZAR" if d["mean_hits"] > b["mean_hits"] + 0.05 or d["p_ge_12"] > b["p_ge_12"] else "NEUTRAL / REFINAR"
    }

    out = OUT_DIR / "EXPERIMENTO_DYNAMIC_DOUBLES.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "="*72)
    print(json.dumps(result, indent=2))
    print(f"\nGuardado: {out}")
    print(f"\n>>> {result['verdict']} <<<")
    return result

if __name__ == "__main__":
    run_dynamic_doubles_experiment()
