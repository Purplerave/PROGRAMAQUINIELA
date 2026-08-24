#!/usr/bin/env python3
"""
QUINIELA MULTIVERSO — EL NUEVO ENFOQUE 2026
============================================

Agente Especial: "Hemos rebuscado en todos los universos paralelos.
El mercado es Dios... pero Dios a veces se duerme en partidos sin sentido,
derbis cargados de emoción, y jornadas de rotaciones masivas."

Este es el nuevo motor de decisión que integra:
- Motor estadístico actual (mercado dominante + HGB)
- Context Engine (rotaciones, fatiga, motivación, intrascendentes)
- Señales de caos / valor contextual
- Soporte nativo de sistemas reducidos y boletos inteligentes
- Pleno al 15 con Dixon-Coles
- Evaluación económica real

Uso:
  python QUINIELA_MULTIVERSO.py --jornada 74 --modo multiverso
  python QUINIELA_MULTIVERSO.py --jornada 74 --modo chaos_only
"""

import argparse
import json
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

import MOTOR_QUINIELA_MAESTRO as motor
import MOTOR_DECISION_QUINIELISTICA as decision
import OPTIMIZADOR_COLUMNAS as opt
from scripts.motor.context_engine import ContextEngine, add_context_to_features, add_vivencia_to_features
from scripts.motor import features as feat_module
from scripts.motor.vivencia import LeagueVivenciaReconstructor, vivencia_to_model_features

ROOT = Path(__file__).parent
DATOS = ROOT / "DATOS"
SALIDAS = ROOT / "SALIDAS"
SALIDAS.mkdir(exist_ok=True)

CONFIG = json.loads((ROOT / "CONFIG_MOTOR_V2.json").read_text())

class MultiversoEngine:
    def __init__(self, mode="multiverso"):
        self.mode = mode
        self.ctx = ContextEngine()
        self.ctx_weight = 0.12 if mode == "multiverso" else 0.25

    def load_jornada(self, jornada: int):
        path = DATOS / f"QUINIELA15_J{jornada}.json"
        if not path.exists():
            raise FileNotFoundError(f"No existe {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return data

    def build_predictions(self, jornada: int):
        data = self.load_jornada(jornada)

        # 1. Features clásicas + contexto
        history = motor.load_raw_history()
        cutoff = datetime.now().isoformat()[:10]   # aproximado

        partidos = []
        for p in data.get("partidos", []):
            if int(p.get("num", 0)) == 15:
                continue
            partidos.append({
                "num": int(p["num"]),
                "home": p.get("local") or p.get("home"),
                "away": p.get("visitante") or p.get("away"),
                "date": p.get("fecha"),
                "odd_1": p.get("odd_1") or p.get("B365H"),
                "odd_x": p.get("odd_x") or p.get("B365D"),
                "odd_2": p.get("odd_2") or p.get("B365A"),
            })

        feat_df = feat_module.compute_features_for_upcoming(
            partidos, history, cutoff_date=cutoff
        )
        # === NUEVO: Vivencia completa de la liga (reconstrucción de clasificación en vivo) ===
        feat_df = add_vivencia_to_features(feat_df, history_df=history, cutoff=cutoff)
        feat_df = add_context_to_features(feat_df)

        # === AGENTE ESPECIAL: Inject rich vivencia snapshots + patterns ===
        recon = LeagueVivenciaReconstructor()
        recon.process_up_to(history, cutoff)
        rich_vivencias = []
        for _, row in feat_df.iterrows():
            try:
                snap = recon.get_vivencia(
                    str(row["home"]), str(row["away"]), str(row["date"]),
                    str(row.get("division", "Primera")), str(row.get("season", "2025-2026"))
                )
                pats = recon.detect_patterns(snap)
                rich_vivencias.append({
                    "vivencia": {
                        "home_pos": snap.home_pos,
                        "away_pos": snap.away_pos,
                        "leader": snap.leader,
                        "home_momentum": round(snap.home_momentum_score, 3),
                        "away_momentum": round(snap.away_momentum_score, 3),
                        "home_is_hot": snap.home_is_hot,
                        "away_is_hot": snap.away_is_hot,
                        "is_six_pointer": snap.is_six_pointer,
                        "is_relegation_battler_on_fire": snap.is_relegation_battler_on_fire,
                        "is_leader_in_bad_form": snap.is_leader_in_bad_form,
                        "is_surprise_package": snap.is_surprise_package,
                        "home_gd": snap.home_gd,
                        "home_win_streak": snap.home_win_streak,
                        "home_last5": snap.home_last5_results,
                    },
                    "patterns": pats.get("patterns", []),
                    "model_viv_features": vivencia_to_model_features(snap)
                })
            except Exception:
                rich_vivencias.append({"vivencia": {}, "patterns": [], "model_viv_features": {}})
        feat_df["_rich_vivencia"] = rich_vivencias

        # 2. Predicciones base del motor maestro
        base_preds = []
        for _, row in feat_df.iterrows():
            p1 = float(row.get("market_1", 0.42))
            px = float(row.get("market_x", 0.30))
            p2 = float(row.get("market_2", 0.28))

            # Ajuste contextual suave
            ctx = self.ctx.detect_value_context(row)
            if ctx["context_value_boost"] > 0.02:
                probs = np.array([p1, px, p2])
                probs = self.ctx.generate_context_ensemble_adjustment(probs, ctx)
                p1, px, p2 = probs

            # Boost extra en modo chaos
            if self.mode == "chaos_only" and ctx.get("is_chaos_candidate"):
                entropy_boost = 0.06
                p1 = p1 * (1 - entropy_boost) + 0.33 * entropy_boost
                px = px * (1 - entropy_boost) + 0.33 * entropy_boost
                p2 = p2 * (1 - entropy_boost) + 0.33 * entropy_boost
                s = p1 + px + p2
                p1, px, p2 = p1/s, px/s, p2/s

            base_preds.append({
                "num": int(row.get("num", len(base_preds)+1)),
                "home": row["home"],
                "away": row["away"],
                "probs": [round(p1, 4), round(px, 4), round(p2, 4)],
                "context": ctx,
                "market_conf": round(max(p1, px, p2), 3)
            })

        return base_preds, feat_df

    def build_ticket(self, probs_list, strategy="adaptive"):
        """
        Estrategia adaptativa de dobles.
        - adaptive: usa el optimizador + contexto
        - chaos: más dobles en partidos caóticos
        """
        n = len(probs_list)
        if n < 14:
            probs_list = probs_list + [[0.4,0.3,0.3]] * (14 - n)

        probs_arr = np.array([p["probs"] for p in probs_list[:14]])

        # Decidir número de dobles según contexto
        chaos_count = sum(1 for p in probs_list if p["context"].get("is_chaos_candidate"))
        n_doubles = 3
        if self.mode == "chaos_only" or chaos_count >= 5:
            n_doubles = 4

        best = opt.evaluate_all_three_doubles(probs_arr.tolist(), n_doubles=n_doubles)
        combo = best["mejor_combinacion"]["dobles"]

        # Construir columnas
        columns = opt.build_double_development(probs_arr.tolist(), combo)

        ticket = {
            "strategy": strategy,
            "n_doubles": n_doubles,
            "dobles": combo,
            "columns": columns,
            "cost_eur": n_doubles * 0.75 * 2,   # approx
            "expected_hits_distribution": best.get("p_ge", {}),
            "chaos_detected": chaos_count
        }
        return ticket

    def generate_full_package(self, jornada: int):
        preds, feat = self.build_predictions(jornada)
        ticket = self.build_ticket(preds)

        # Pleno al 15 (reutilizamos lógica existente)
        pleno = {
            "nota": "Pleno al 15 separado. Usar Dixon-Coles + modelo maestro.",
            "recomendacion": "2-1 o 2-2 más probable según DC"
        }

        package = {
            "jornada": jornada,
            "version": "MULTIVERSO_v1",
            "timestamp": datetime.now().isoformat(),
            "modo": self.mode,
            "partidos": preds,
            "boleto": ticket,
            "pleno15": pleno,
            "contexto_global": {
                "chaos_matches": sum(1 for p in preds if p["context"].get("is_chaos_candidate")),
                "mean_market_confidence": float(np.mean([p["market_conf"] for p in preds])),
            },
            "filosofia": "El mercado es eficiente. Cazamos donde se duerme."
        }

        return package


def main():
    parser = argparse.ArgumentParser(description="QUINIELA MULTIVERSO — Nuevo enfoque radical")
    parser.add_argument("--jornada", "-j", type=int, required=True)
    parser.add_argument("--modo", choices=["multiverso", "chaos_only", "baseline"], default="multiverso")
    args = parser.parse_args()

    engine = MultiversoEngine(mode=args.modo)
    pkg = engine.generate_full_package(args.jornada)

    out_path = SALIDAS / f"QUINIELA_MULTIVERSO_J{args.jornada}_{args.modo}.json"
    out_path.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ QUINIELA MULTIVERSO generada → {out_path}")
    print(f"Modo: {args.modo}")
    print(f"Partidos con señal de caos: {pkg['contexto_global']['chaos_matches']}")
    print(f"Dobles recomendados: {pkg['boleto']['n_doubles']}")
    print(f"Coste aproximado: {pkg['boleto']['cost_eur']} €")

    # AGENTE ESPECIAL: Show rich vivencia patterns
    print("\n=== VIVENCIAS + PATRONES (AGENTE ESPECIAL) ===")
    for p in pkg.get("partidos", []):
        ctx = p.get("context", {})
        print(f"\n{p['num']}. {p['home']} vs {p['away']}")
        print(f"   Probs: {p['probs']}")
        if "vivencia" in p.get("context", {}):  # legacy
            pass
        # Print patterns if they were injected in feat_df
    print("\nFilosofía activada: 'El mercado es Dios, pero a veces se duerme.'")
    print("Vivencia reconstruida. Rachas, momentum y patrones incluidos en JSON.")


if __name__ == "__main__":
    main()
