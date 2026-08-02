"""BACKTEST_JORNADAS_REALES.py — Evaluación del motor sobre jornadas reales.

Reemplaza la métrica antigua de "aciertos con tres dobles" (bloques
consecutivos de 15 partidos ordenados por fecha) por la evaluación sobre
jornadas reconstruidas con coherencia temporal real
(``DATOS/jornadas_historicas_2023_2026.json``, construidas a partir del
dataset Highlightly incluido en el repo).

Qué mide por jornada (misma regla que ``simulate_doubles``):
- 3 dobles: los 3 partidos con mayor ``double_value_score``
  (baja confianza + peso del empate + desacuerdo modelo/mercado + bonus
  Segunda). El resto, el favorito del motor (``best_pred``).
- Aciertos = signos cubiertos por el desarrollo (favorito o doble).
- También reporta el acierto simple del motor y del favorito de mercado
  por jornada, para comparar en las mismas unidades.

Nota de comparabilidad: un boleto real de La Quiniela tiene 15 partidos;
la jornada reconstruida contiene TODOS los partidos españoles del fin de
semana (normalmente 19-22). La cifra "aciertos por jornada" no es por tanto
directamente comparable con el antiguo "X.XX/15", sino una medida más
exigente (más partidos que cubrir con los mismos 3 dobles).

Uso:
    python scripts/backtests/BACKTEST_JORNADAS_REALES.py [--predicciones salida/predicciones_backtest_optimizadas.csv]
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

import settings  # noqa: E402
import MOTOR_QUINIELA_MAESTRO as motor  # noqa: E402

JORNADAS_PATH = settings.DATOS_DIR / "jornadas_historicas_2023_2026.json"
DEFAULT_PREDICCIONES = PROJECT_ROOT / "salida" / "predicciones_backtest_optimizadas.csv"

MIN_PARTIDOS_JORNADA = 15  # solo fines de semana completos


def load_predicciones(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    needed = {
        "date", "home", "away", "division", "result",
        "best_pred", "best_prob_1", "best_prob_x", "best_prob_2",
        "favorite_market", "model_disagreement",
    }
    missing = needed - set(df.columns)
    if missing:
        raise ValueError(f"Faltan columnas en predicciones: {sorted(missing)}")
    return df


def evaluate_jornada(
    preds: pd.DataFrame,
    partidos: list[dict],
    config: dict,
) -> tuple[dict | None, list[pd.Series]]:
    """Devuelve (métricas, filas unidas) o (None, []) si no hay suficientes partidos."""
    rows = []
    for p in partidos:
        hit = preds[
            (preds["date"].dt.date.astype(str) == p["fecha"])
            & (preds["home"] == p["local"])
            & (preds["away"] == p["visitante"])
        ]
        if hit.empty:
            continue
        rows.append(hit.iloc[0])
    if len(rows) < MIN_PARTIDOS_JORNADA:
        return None, []

    group = pd.DataFrame(rows).reset_index(drop=True)
    group["double"] = [
        motor.build_double(p1, px, p2, config["double_draw_threshold"])
        for p1, px, p2 in zip(
            group["best_prob_1"], group["best_prob_x"], group["best_prob_2"]
        )
    ]
    confidence = group[["best_prob_1", "best_prob_x", "best_prob_2"]].max(axis=1)
    score = (
        (1 - confidence)
        + config["double_draw_weight"] * group["best_prob_x"]
        + config["double_disagreement_weight"] * group["model_disagreement"]
        + np.where(group["division"].eq("Segunda"), config["double_segunda_bonus"], 0.0)
    )
    group["double_value_score"] = score
    double_idx = set(group.nlargest(3, "double_value_score").index.tolist())

    hits = 0
    for idx, row in group.iterrows():
        if idx in double_idx:
            if row["result"] in row["double"]:
                hits += 1
        elif row["best_pred"] == row["result"]:
            hits += 1

    market_valid = group["favorite_market"].notna()
    return (
        {
            "n_partidos": len(group),
            "hits_3_dobles": hits,
            "accuracy_simple": float(group["best_pred"].eq(group["result"]).mean()),
            "accuracy_market": float(group.loc[market_valid, "favorite_market"].eq(group.loc[market_valid, "result"]).mean())
            if market_valid.any()
            else None,
            "market_available": int(market_valid.sum()),
        },
        rows,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest sobre jornadas reales 2023-2026")
    parser.add_argument("--predicciones", default=str(DEFAULT_PREDICCIONES), help="CSV de predicciones del backtest maestro")
    args = parser.parse_args()

    if not JORNADAS_PATH.is_file():
        print(f"ERROR: ejecuta antes scripts/datos/CONSTRUIR_JORNADAS_HISTORICAS.py ({JORNADAS_PATH})", file=sys.stderr)
        return 1

    jornadas_data = json.loads(JORNADAS_PATH.read_text(encoding="utf-8"))
    preds = load_predicciones(Path(args.predicciones))
    config = settings.master_model_config()

    joined_rows = []
    results = []
    for j in jornadas_data["jornadas"]:
        r, rows = evaluate_jornada(preds, j["partidos"], config)
        if r is None:
            continue
        r["jornada_id"] = j["jornada_id"]
        r["temporada"] = j["temporada"]
        r["sabado_ancla"] = j["sabado_ancla"]
        results.append(r)
        joined_rows.extend(rows)

    if not results:
        print("No se pudo unir ninguna jornada con las predicciones.", file=sys.stderr)
        return 1

    df = pd.DataFrame(results)

    # Métrica antigua (bloques de 15) sobre EXACTAMENTE los mismos partidos
    joined = pd.DataFrame(joined_rows).reset_index(drop=True)
    old = motor.simulate_doubles(joined, "best", config)
    old_mean = float(old["hits_3_dobles"].mean()) if not old.empty else float("nan")
    old_rate = old_mean / 15.0 if not old.empty else float("nan")
    new_mean = float(df["hits_3_dobles"].mean())
    new_rate = new_mean / float(df["n_partidos"].mean())

    print("=" * 74)
    print("BACKTEST SOBRE JORNADAS REALES (Highlightly 2023-2026)")
    print("=" * 74)
    print(f"Jornadas evaluadas (>= {MIN_PARTIDOS_JORNADA} partidos unidos): {len(df)}")
    print(f"Partidos cubiertos: {int(df['n_partidos'].sum())}")
    print(f"Tamaño medio de jornada: {df['n_partidos'].mean():.1f} partidos")
    print(f"  (un boleto real de LAE tiene 15; la jornada incluye todo el fin de semana)")
    print("-" * 74)
    print(f"{'Temporada':<12}{'Jornadas':>9}{'Aciertos 3D (media)':>20}{'Acierto simple':>16}{'Mercado':>10}")
    print("-" * 74)
    for season, g in df.groupby("temporada"):
        print(
            f"{season:<12}{len(g):>9}{g['hits_3_dobles'].mean():>17.2f}"
            f"{g['accuracy_simple'].mean():>16.2%}{g['accuracy_market'].mean():>10.2%}"
        )
    print("-" * 74)
    print(
        f"{'TOTAL':<12}{len(df):>9}{df['hits_3_dobles'].mean():>17.2f}"
        f"{df['accuracy_simple'].mean():>16.2%}{df['accuracy_market'].mean():>10.2%}"
    )
    print()
    print("Comparación con la métrica antigua sobre EXACTAMENTE los mismos partidos:")
    print(f"  Bloques de 15 (métrica antigua):  {old_mean:.2f}/15  ({old_rate:.1%} de acierto)")
    print(
        f"  Jornadas reales:                 {new_mean:.2f}/"
        f"{df['n_partidos'].mean():.0f}  ({new_rate:.1%} de acierto)"
    )
    print()
    print("  La métrica antigua agrupa 15 partidos consecutivos del CSV, que pueden")
    print("  pertenecer a dos fines de semana distintos: los 3 dobles 'cubren'")
    print("  partidos que nunca coexistieron en un mismo boleto, lo que infla la")
    print("  cifra. En jornadas reales los partidos sí comparten boleto semanal.")
    if not old.empty:
        print(f"  (bloques antiguos: {len(old)} tickets simulados de 15)")

    out_path = settings.SALIDA_DIR / "backtest_jornadas_reales.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "n_jornadas": len(df),
                "media_aciertos_3_dobles_por_jornada": float(df["hits_3_dobles"].mean()),
                "media_partidos_por_jornada": float(df["n_partidos"].mean()),
                "acierto_simple_medio_por_jornada": float(df["accuracy_simple"].mean()),
                "acierto_mercado_medio_por_jornada": float(df["accuracy_market"].mean()),
                "antigua_metrica_bloques_15_mismos_partidos": old_mean,
                "acierto_antigua_metrica_bloques": old_rate,
                "acierto_jornadas_reales": new_rate,
                "por_temporada": [
                    {
                        "temporada": s,
                        "n_jornadas": int(len(g)),
                        "media_aciertos_3_dobles": float(g["hits_3_dobles"].mean()),
                        "acierto_simple": float(g["accuracy_simple"].mean()),
                        "acierto_mercado": float(g["accuracy_market"].mean()),
                    }
                    for s, g in df.groupby("temporada")
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nGuardado en {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
