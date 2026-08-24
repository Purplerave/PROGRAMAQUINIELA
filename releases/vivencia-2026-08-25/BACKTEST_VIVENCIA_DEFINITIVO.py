#!/usr/bin/env python3
"""
BACKTEST_VIVENCIA_DEFINITIVO.py — DEFINITIVE FINAL VERSION
==========================================================

Backtest walk-forward limpio que responde la pregunta clave:
¿La reconstrucción de la "vivencia" de la liga (tabla en el momento exacto + rachas + momentum + flags) 
mejora las métricas económicas (P(≥12), ROI 6€) respecto al baseline?

Tres brazos:
- BASELINE: motor actual (market + HGB) + 3 dobles
- VIVENCIA: baseline + enriquecimiento con LeagueVivenciaReconstructor (tabla point-in-time, rachas, momentum, is_releg_hot, etc.) + boost contextual

Todo sin fuga. Reconstrucción por fecha/cutoff.

Ejecuta:
  source .venv/bin/activate
  python scripts/backtests/BACKTEST_VIVENCIA_DEFINITIVO.py
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
from scripts.motor.context_engine import add_context_to_features, add_vivencia_to_features
from scripts.motor.vivencia import LeagueVivenciaReconstructor, vivencia_to_model_features

OUT_DIR = PROJECT_ROOT / "salida"
OUT_DIR.mkdir(exist_ok=True)

PRIZES = {15: 150000, 14: 45000, 13: 12000, 12: 3500, 11: 900, 10: 250}

def safe_probs(row, cols=("market_1", "market_x", "market_2")):
    vals = []
    for c in cols:
        v = row.get(c, np.nan)
        if pd.isna(v) or v <= 0:
            v = row.get("latest_prob_" + c.split("_")[-1], 0.33)
        vals.append(float(v) if not pd.isna(v) else 0.33)
    s = sum(vals)
    return [v/s for v in vals] if s > 0 else [0.33]*3

def evaluate_jornada(probs_list, results, n_doubles=3):
    if len(probs_list) < 14:
        return 0, 0
    best = opt.evaluate_all_three_doubles(probs_list, n_doubles=n_doubles)
    combo = tuple(best["mejor_combinacion"]["dobles"])
    selected = opt.build_double_development(probs_list, combo)
    hits = sum(1 for s, res in zip(selected, results) if str(res) in s)
    prize = PRIZES.get(hits, 0)
    return hits, prize

def run_definitive_vivencia_backtest():
    print("="*72)
    print("BACKTEST VIVENCIA DEFINITIVO v4 — TABLA EN DIRECTO + RACHAS + MOMENTUM")
    print("¿Sirve la vivencia para superar al mercado en dinero real?")
    print("="*72)

    raw = motor.load_raw_history()
    print(f"\nHistórico: {len(raw)} partidos")

    # Enfocamos en Primera (donde la clasificación es más rica)
    raw = raw[raw.division == "Primera"].copy()
    print(f"Primera: {len(raw)} partidos")

    print("\n[1] Features base (rolling, sin fuga)...")
    feat = motor.rolling_team_features(raw)
    feat = feat[feat.result.isin(motor.LABEL_MAP)].copy()
    print(f"  Features: {len(feat)}")

    # Temporadas recientes con buena cobertura
    all_seasons = sorted([s for s in feat.season.dropna().unique() if str(s) >= "2021-2022"])
    seasons = all_seasons[-5:]   # últimas 5
    print(f"Walk-forward seasons: {seasons}")

    all_baseline_hits = []
    all_vivencia_hits = []

    for season in seasons:
        print(f"\n--- {season} ---")
        try:
            # Baseline backtest del motor (split correcto + modelo)
            preds, meta = motor.run_season_backtest(feat, season)
            preds = preds.sort_values(["date", "division", "home", "away"]).reset_index(drop=True)
            print(f"  Partidos: {len(preds)}")

            # Probabilidades baseline
            preds["b_prob1"] = preds.apply(lambda r: safe_probs(r)[0], axis=1)
            preds["b_probx"] = preds.apply(lambda r: safe_probs(r)[1], axis=1)
            preds["b_prob2"] = preds.apply(lambda r: safe_probs(r)[2], axis=1)

            # === VIVENCIA (reconstrucción "en directo") ===
            # Usamos cutoff al inicio de la temporada para simular "lo que sabíamos entonces"
            cutoff = f"{season.split('-')[0]}-08-20"
            try:
                viv_df = add_vivencia_to_features(preds.copy(), history_df=raw, cutoff=cutoff)
            except Exception:
                viv_df = add_context_to_features(preds.copy())

            recon = LeagueVivenciaReconstructor()
            recon.process_up_to(raw, cutoff)

            v1, vx, v2 = [], [], []
            for _, row in viv_df.iterrows():
                bp = np.array([row["b_prob1"], row["b_probx"], row["b_prob2"]])
                try:
                    snap = recon.get_vivencia(
                        str(row["home"]), str(row["away"]),
                        str(row["date"]),
                        str(row.get("division", "Primera")), season
                    )
                    vf = vivencia_to_model_features(snap)

                    boost = 0.0
                    if vf.get("viv_releg_hot", 0) > 0.5: boost += 0.048
                    if vf.get("viv_surprise", 0) > 0.5: boost += 0.055
                    if vf.get("viv_leader_bad", 0) > 0.5: boost += 0.032
                    if vf.get("viv_is_six_pointer", 0) > 0.5: boost += 0.025
                    if vf.get("viv_home_momentum", 0) > 0.70: boost += 0.038
                    if vf.get("viv_home_is_hot", 0) > 0.5: boost += 0.028

                    if boost > 0.01:
                        # empujamos ligeramente hacia el lado con momentum + contexto
                        adj = bp * (1 - 0.6*boost) + np.array([0.75*boost, 0.15*boost, 0.10*boost])
                        adj = adj / adj.sum()
                        bp = adj
                except Exception:
                    pass
                v1.append(bp[0]); vx.append(bp[1]); v2.append(bp[2])

            viv_df["v_prob1"] = v1
            viv_df["v_probx"] = vx
            viv_df["v_prob2"] = v2

            # === Evaluación por jornada (3 dobles) ===
            season_b_hits = []
            season_v_hits = []

            for start in range(0, len(preds), 15):
                g = viv_df.iloc[start : start+15]
                if len(g) < 14: continue

                bprobs = g[["b_prob1","b_probx","b_prob2"]].values.tolist()
                vprobs = g[["v_prob1","v_probx","v_prob2"]].values.tolist()
                res = g["result"].astype(str).tolist()

                hb, _ = evaluate_jornada(bprobs, res, 3)
                hv, _ = evaluate_jornada(vprobs, res, 3)

                season_b_hits.append(hb)
                season_v_hits.append(hv)

            print(f"  Jornadas evaluadas: {len(season_b_hits)}")
            print(f"  BASELINE  mean={np.mean(season_b_hits):.2f}  P≥12={np.mean([h>=12 for h in season_b_hits]):.3f}")
            print(f"  VIVENCIA  mean={np.mean(season_v_hits):.2f}  P≥12={np.mean([h>=12 for h in season_v_hits]):.3f}")

            all_baseline_hits.extend(season_b_hits)
            all_vivencia_hits.extend(season_v_hits)

        except Exception as e:
            print(f"  ERROR {season}: {str(e)[:110]}")
            continue

    # === RESULTADO GLOBAL ===
    def global_metrics(hits_list, label):
        if not hits_list:
            return {"label": label, "jornadas": 0}
        arr = np.array(hits_list)
        n = len(arr)
        cost = n * 6.0
        prize = sum(PRIZES.get(h, 0) for h in arr)
        roi = (prize - cost) / cost if cost > 0 else -1
        return {
            "label": label,
            "jornadas": n,
            "mean_hits": round(float(arr.mean()), 3),
            "p_ge_11": round(float((arr >= 11).mean()), 4),
            "p_ge_12": round(float((arr >= 12).mean()), 4),
            "p_ge_13": round(float((arr >= 13).mean()), 4),
            "roi_6eur": round(roi, 4),
            "total_prize": prize,
            "total_cost": cost
        }

    b = global_metrics(all_baseline_hits, "baseline")
    v = global_metrics(all_vivencia_hits, "vivencia")

    delta_p12 = round(v.get("p_ge_12", 0) - b.get("p_ge_12", 0), 5)
    delta_roi = round(v.get("roi_6eur", 0) - b.get("roi_6eur", 0), 4)
    delta_mean = round(v.get("mean_hits", 0) - b.get("mean_hits", 0), 3)

    verdict = "ACTIVAR VIVENCIA EN PRODUCCIÓN" if (delta_p12 >= 0.012 or delta_roi >= 0.015 or delta_mean >= 0.20) else "NO ACTIVAR (o solo contexto ligero)"

    final_report = {
        "experiment": "BACKTEST_VIVENCIA_DEFINITIVO_v4",
        "date": datetime.now().isoformat(),
        "description": "Walk-forward en Primera. Vivencia reconstruida con cutoff por temporada usando LeagueVivenciaReconstructor (posiciones, rachas, momentum, flags).",
        "seasons": seasons,
        "baseline": b,
        "vivencia": v,
        "deltas": {
            "p_ge_12": delta_p12,
            "roi": delta_roi,
            "mean_hits": delta_mean
        },
        "verdict": verdict,
        "recommendation": "Integrar vivencia_to_model_features + boosts en QUINIELA_MULTIVERSO y MOTOR si el veredicto es positivo."
    }

    out_file = OUT_DIR / "BACKTEST_VIVENCIA_DEFINITIVO.json"
    out_file.write_text(json.dumps(final_report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "="*72)
    print("RESULTADO FINAL DEFINITIVO")
    print("="*72)
    print(json.dumps(final_report, indent=2, ensure_ascii=False))
    print(f"\nGuardado: {out_file}")

    print("\n=== RESUMEN AGENTE ESPECIAL ===")
    print(f"Baseline: mean={b.get('mean_hits')}  P≥12={b.get('p_ge_12')}  ROI={b.get('roi_6eur')}")
    print(f"Vivencia: mean={v.get('mean_hits')}  P≥12={v.get('p_ge_12')}  ROI={v.get('roi_6eur')}")
    print(f"\nΔP(≥12) = {delta_p12:+.5f}")
    print(f"ΔROI    = {delta_roi:+.4f}")
    print(f"Δmean   = {delta_mean:+.3f}")
    print(f"\n>>> VEREDICTO: {verdict} <<<")

    return final_report

if __name__ == "__main__":
    run_definitive_vivencia_backtest()
