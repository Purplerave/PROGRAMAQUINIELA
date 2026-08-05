"""Evaluación económica walk-forward del boleto de 6 € (P0.1).

Traduce el backtest de acierto a métricas de DINERO por jornada y temporada:

  - Coste fijo del boleto (contrato P0: 3 dobles = 8 columnas = 6,00 €).
  - Distribución empírica de aciertos de la mejor columna por jornada.
  - Frecuencia de premio por categoría (10..14) sobre las jornadas jugadas.
  - Ganancia bruta REALIZADA (premio medio histórico por categoría alcanzada).
  - ROI realizado del boleto del modelo vs el boleto "solo favoritos de mercado".

A diferencia de ``evaluation.economics`` (que calcula el EV EX-ANTE por
convolución de probabilidades), este script mide el resultado EX-POST: coge las
predicciones reales del walk-forward, arma el boleto y lo comprueba contra los
resultados reales. Las dos vistas son complementarias:

  * EX-ANTE  → ¿qué EV promete el boleto según las probabilidades? (calibración)
  * EX-POST  → ¿cuánto habría rendido de verdad en el histórico? (realidad)

⚠️  Los premios son ESTIMADOS con medias históricas (ver evaluation/economics.py).
    El ROI resultante es orientativo, no una garantía.

Uso:
    python scripts/backtests/EVALUACION_ECONOMICA.py [--from-season 2019-2020]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import MOTOR_QUINIELA_MAESTRO as motor  # noqa: E402
import OPTIMIZADOR_COLUMNAS as opt  # noqa: E402
from evaluation import economics as econ  # noqa: E402

OUT_DIR = PROJECT_ROOT / "salida"
PREFIX = "latest"
SIGN_COLS_MODEL = [f"{PREFIX}_prob_1", f"{PREFIX}_prob_x", f"{PREFIX}_prob_2"]
SIGN_COLS_MARKET = ["market_1", "market_x", "market_2"]


def season_key(season) -> int:
    try:
        return int(str(season).split("-")[0])
    except Exception:
        return 0


def _probs_from_row(row, cols) -> np.ndarray | None:
    vals = [row.get(c) for c in cols]
    if any(v is None or pd.isna(v) for v in vals):
        return None
    arr = np.array([float(v) for v in vals], dtype=float)
    s = arr.sum()
    if s <= 0:
        return None
    return arr / s


def _hits_for_selected(probs_group, selected, results) -> int:
    """Aciertos de la mejor columna: por partido suma 1 si el resultado real
    está entre los signos jugados del desarrollo."""
    hits = 0
    for (_, signs), res in zip(selected, results):
        if res in signs:
            hits += 1
    return hits


def evaluate_jornada(group: pd.DataFrame, prizes: dict[int, float]) -> dict | None:
    """Evalúa una jornada de 14 partidos (bloque principal del boleto)."""
    # El bloque de 15 incluye el Pleno; el boleto principal son 14 partidos.
    block = group.head(14)
    if len(block) < 14:
        return None

    model_probs, market_probs, results = [], [], []
    for _, row in block.iterrows():
        mp = _probs_from_row(row, SIGN_COLS_MODEL)
        kp = _probs_from_row(row, SIGN_COLS_MARKET)
        res = row.get("result")
        if mp is None or kp is None or res not in ("1", "X", "2"):
            return None
        model_probs.append(mp)
        market_probs.append(kp)
        results.append(res)

    # Boleto del modelo: 3 dobles óptimos (contrato P0).
    best = opt.evaluate_all_three_doubles(model_probs, n_doubles=3)
    combo = tuple(best["mejor_combinacion"]["dobles"])
    model_selected = opt.build_double_development(model_probs, combo)
    model_hits = _hits_for_selected(model_probs, model_selected, results)

    # Boleto de referencia: solo favoritos de mercado (14 simples, 1 columna).
    market_selected = econ._favorite_development(market_probs)
    market_hits = _hits_for_selected(market_probs, market_selected, results)

    def prize(hits: int) -> float:
        return float(prizes.get(hits, 0.0)) if hits >= 10 else 0.0

    return {
        "model_hits": model_hits,
        "market_hits": market_hits,
        "model_prize_eur": prize(model_hits),
        "market_prize_eur": prize(market_hits),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluación económica walk-forward (P0.1).")
    parser.add_argument("--from-season", default="2019-2020")
    parser.add_argument("--to-season", default="")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    prizes = econ.load_prizes()
    contract = opt.columns_contract()
    cost = float(contract["max_cost"])

    raw = motor.load_raw_history()
    features = motor.rolling_team_features(raw)
    usable = features[features["result"].isin(motor.LABEL_MAP)].copy()
    seasons = sorted(usable["season"].dropna().unique().tolist(), key=motor.season_sort_key)
    selected_seasons = [s for s in seasons if season_key(s) >= season_key(args.from_season)]
    if args.to_season:
        selected_seasons = [s for s in selected_seasons if season_key(s) <= season_key(args.to_season)]

    season_rows = []
    all_model_hits, all_market_hits = [], []
    total_model_prize = total_market_prize = 0.0
    total_jornadas = 0

    for season in selected_seasons:
        try:
            predictions, _ = motor.run_season_backtest(features, season)
        except Exception as exc:  # temporadas sin train, etc.
            print(f"{season}: SKIP ({exc})")
            continue

        predictions = predictions.sort_values(["date", "division", "home", "away"]).reset_index(drop=True)
        jornadas = []
        for start in range(0, len(predictions), 15):
            group = predictions.iloc[start:start + 15]
            if len(group) < 15:
                continue
            res = evaluate_jornada(group, prizes)
            if res is not None:
                jornadas.append(res)

        if not jornadas:
            print(f"{season}: sin jornadas evaluables")
            continue

        n = len(jornadas)
        model_prize = sum(j["model_prize_eur"] for j in jornadas)
        market_prize = sum(j["market_prize_eur"] for j in jornadas)
        model_cost = cost * n
        # El boleto de referencia es 1 columna; para comparar EV por euro de forma
        # justa lo evaluamos también a coste de 1 columna (0,75 €) y a coste del
        # contrato completo (6 €). Reportamos ambos ROIs.
        price_col = float(contract["price_per_column"])
        market_cost_1col = price_col * n
        market_cost_full = cost * n

        row = {
            "season": season,
            "jornadas": n,
            "model_mean_hits": float(np.mean([j["model_hits"] for j in jornadas])),
            "market_mean_hits": float(np.mean([j["market_hits"] for j in jornadas])),
            "model_cost_eur": model_cost,
            "model_prize_eur": model_prize,
            "model_roi": (model_prize - model_cost) / model_cost if model_cost else None,
            "market_prize_eur": market_prize,
            "market_roi_1col": (market_prize - market_cost_1col) / market_cost_1col if market_cost_1col else None,
            "market_roi_full": (market_prize - market_cost_full) / market_cost_full if market_cost_full else None,
            "model_p_ge_10": float(np.mean([j["model_hits"] >= 10 for j in jornadas])),
            "model_p_ge_11": float(np.mean([j["model_hits"] >= 11 for j in jornadas])),
            "model_p_ge_12": float(np.mean([j["model_hits"] >= 12 for j in jornadas])),
            "model_p_ge_13": float(np.mean([j["model_hits"] >= 13 for j in jornadas])),
            "model_p_ge_14": float(np.mean([j["model_hits"] >= 14 for j in jornadas])),
        }
        season_rows.append(row)
        all_model_hits += [j["model_hits"] for j in jornadas]
        all_market_hits += [j["market_hits"] for j in jornadas]
        total_model_prize += model_prize
        total_market_prize += market_prize
        total_jornadas += n

        print(
            f"{season}: {n} jornadas | modelo {row['model_mean_hits']:.2f} ac "
            f"ROI {row['model_roi']:+.1%} | mercado {row['market_mean_hits']:.2f} ac "
            f"ROI(6€) {row['market_roi_full']:+.1%}"
        )

    if total_jornadas == 0:
        print("No hay jornadas evaluables.")
        return

    total_model_cost = cost * total_jornadas
    total_market_cost_full = cost * total_jornadas

    # Análisis de sensibilidad: ROI del modelo y del mercado bajo cada escenario
    # de premio (fácil / normal / difícil) de la estimación manus.ai.
    scenarios = econ.load_scenarios()

    def roi_under(hits_list, scenario_prizes, ticket_cost):
        prize = sum(
            float(scenario_prizes.get(h, 0.0)) if h >= 10 else 0.0 for h in hits_list
        )
        total_cost = ticket_cost * len(hits_list)
        return {
            "premio_total_eur": prize,
            "coste_total_eur": total_cost,
            "roi": (prize - total_cost) / total_cost if total_cost else None,
        }

    sensibilidad = {}
    for name, sp in scenarios.items():
        sensibilidad[name] = {
            "modelo": roi_under(all_model_hits, sp, cost),
            "solo_favoritos_mercado_6eur": roi_under(all_market_hits, sp, cost),
        }

    summary = {
        "contrato": contract,
        "premios_usados_eur": {str(k): float(v) for k, v in prizes.items()},
        "premios_estimados": True,
        "escenario_por_defecto": econ.default_scenario_name(),
        "nota": (
            "ROI EX-POST con premios estimados (manus.ai; variables por jornada). "
            "Orientativo, no garantía. Pleno al 15 excluido (se juega aparte). "
            "Ver 'sensibilidad_escenarios' para el rango fácil/normal/difícil."
        ),
        "sensibilidad_escenarios": sensibilidad,
        "jornadas_totales": total_jornadas,
        "modelo": {
            "coste_total_eur": total_model_cost,
            "premio_total_eur": total_model_prize,
            "roi": (total_model_prize - total_model_cost) / total_model_cost,
            "mean_hits": float(np.mean(all_model_hits)),
            "p_ge_12": float(np.mean([h >= 12 for h in all_model_hits])),
            "p_ge_13": float(np.mean([h >= 13 for h in all_model_hits])),
            "p_ge_14": float(np.mean([h >= 14 for h in all_model_hits])),
        },
        "solo_favoritos_mercado": {
            "premio_total_eur": total_market_prize,
            "roi_1col": (total_market_prize - float(contract["price_per_column"]) * total_jornadas)
            / (float(contract["price_per_column"]) * total_jornadas),
            "roi_6eur": (total_market_prize - total_market_cost_full) / total_market_cost_full,
            "mean_hits": float(np.mean(all_market_hits)),
            "p_ge_12": float(np.mean([h >= 12 for h in all_market_hits])),
            "p_ge_13": float(np.mean([h >= 13 for h in all_market_hits])),
            "p_ge_14": float(np.mean([h >= 14 for h in all_market_hits])),
        },
        "delta_roi_vs_market_6eur": (
            (total_model_prize - total_model_cost) / total_model_cost
            - (total_market_prize - total_market_cost_full) / total_market_cost_full
        ),
        "por_temporada": season_rows,
    }

    csv_path = OUT_DIR / "evaluacion_economica.csv"
    json_path = OUT_DIR / "evaluacion_economica.json"
    pd.DataFrame(season_rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== RESUMEN ECONÓMICO (ex-post, premios estimados) ===")
    print(json.dumps(
        {k: v for k, v in summary.items() if k not in ("por_temporada", "premios_usados_eur")},
        ensure_ascii=False, indent=2,
    ))
    print(f"\nCSV : {csv_path}\nJSON: {json_path}")


if __name__ == "__main__":
    main()
