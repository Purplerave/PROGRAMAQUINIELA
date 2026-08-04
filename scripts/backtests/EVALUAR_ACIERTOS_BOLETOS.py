#!/usr/bin/env python3
"""Evalúa aciertos reales del motor sobre boletos oficiales contrastados.

Toma la propuesta de ``IMPORTAR_BOLETOS_QUINIELA15.py`` (la sección
``tickets``, boletos con los 15 partidos contrastados contra Football-Data),
genera las predicciones del motor en modo producción (pesos congelados de
``CONFIG_MOTOR_V2.json``, sin reoptimizar) y mide por boleto:

- aciertos simples sobre los 14 partidos oficiales (motor y favorito de
  mercado);
- aciertos con tres dobles elegidos sobre los 14 partidos reales del boleto;
- Pleno al 15: marcador exacto y bucket (p. ej. ``M-2``) del modelo frente al
  oficial.

No calcula ROI: sin escrutinio/premio oficial por categoría no hay retorno
(`missing_official_payouts`). La métrica proxy de bloques artificiales
(8,63/15) se mantiene como referencia del README; este script la sustituye
solo cuando hay boletos oficiales completos.

Uso:

    python scripts/backtests/EVALUAR_ACIERTOS_BOLETOS.py
        [--propuesta salida/quiniela_historica_propuesta_2025_2026.json]
        [--cache salida/predicciones_test_principal.pkl] [--no-cache]

La primera ejecución entrena y evalúa el motor en el corte temporal habitual
(equivale a ``MOTOR_QUINIELA_MAESTRO.py --modo produccion`` sobre el test
principal) y guarda las predicciones en ``--cache`` para reutilizarlas.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.backtests.QUINIELA_REAL import (  # noqa: E402
    attach_ticket_positions,
    canonical_team as qreal_canonical,
    evaluate_official_doubles,
)
from scripts.datos.IMPORTAR_BOLETOS_QUINIELA15 import (  # noqa: E402
    canonical_team as q15_canonical,
    pleno_bucket_from_source,
)

ROOT = PROJECT_ROOT
DEFAULT_PROPUESTA = ROOT / "salida" / "quiniela_historica_propuesta_2025_2026.json"
DEFAULT_CACHE = ROOT / "salida" / "predicciones_test_principal.pkl"
DEFAULT_OUTPUT = ROOT / "salida" / "evaluacion_aciertos_boletos_2025_2026.json"
PRED_PREFIX = "best"


def _iso(value: object) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def key_name(value: object) -> str:
    """Clave de emparejamiento: alias Quiniela15 -> CSV y luego clave simple."""
    return qreal_canonical(q15_canonical(value))


def load_propuesta(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0":
        raise ValueError(f"{path}: schema_version 1.0 es obligatorio")
    tickets = payload.get("tickets", [])
    if not isinstance(tickets, list):
        raise ValueError(f"{path}: 'tickets' debe ser una lista")
    return payload


def compute_reference_predictions() -> tuple[pd.DataFrame, dict[str, Any]]:
    """Reproduce el test principal del motor en modo producción (pesos congelados)."""
    from MOTOR_QUINIELA_MAESTRO import load_raw_history, rolling_team_features, run_backtest

    raw = load_raw_history("original")
    features = rolling_team_features(raw)
    predictions, metrics = run_backtest(features, "production")
    return predictions, metrics


def load_or_compute_predictions(cache_path: Path | None, use_cache: bool) -> tuple[pd.DataFrame, dict[str, Any]]:
    if use_cache and cache_path is not None and cache_path.is_file():
        blob = pd.read_pickle(cache_path)
        return blob["predictions"], blob["metrics"]
    predictions, metrics = compute_reference_predictions()
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        pd.to_pickle({"predictions": predictions, "metrics": metrics}, cache_path)
    return predictions, metrics


def _prediction_index(predictions: pd.DataFrame) -> dict[tuple[str, str, str], list[int]]:
    indexed: dict[tuple[str, str, str], list[int]] = {}
    for index, row in predictions.iterrows():
        key = (_iso(row["date"]), qreal_canonical(row["home"]), qreal_canonical(row["away"]))
        indexed.setdefault(key, []).append(index)
    return indexed


def evaluate_ticket_results(
    predictions: pd.DataFrame,
    tickets: list[dict[str, Any]],
    config: dict[str, Any],
    pred_prefix: str = PRED_PREFIX,
) -> dict[str, Any]:
    """Evalúa los boletos aceptados contra las predicciones del motor.

    El cruce exige fecha + local + visitante únicos (sin aproximaciones). Un
    boleto se evalúa solo si sus 14 partidos se encuentran; en otro caso se
    reporta ``cobertura_incompleta`` con el número de coincidencias.
    """
    if not tickets:
        return {"tickets": [], "aggregate": None, "attach_stats": {"requested_matches": 0, "matched_matches": 0, "unmatched_or_ambiguous": 0, "ambiguous_matches": 0}}

    def renamed(ticket: dict[str, Any]) -> dict[str, Any]:
        copy = json.loads(json.dumps(ticket, ensure_ascii=False))
        for match in copy["matches"]:
            match["home"] = q15_canonical(match["home"])
            match["away"] = q15_canonical(match["away"])
        copy["pleno15"]["home"] = q15_canonical(copy["pleno15"]["home"])
        copy["pleno15"]["away"] = q15_canonical(copy["pleno15"]["away"])
        return copy

    joined, attach_stats = attach_ticket_positions(predictions, [renamed(ticket) for ticket in tickets], aliases=None)
    index = _prediction_index(predictions)

    evaluated_rows: list[dict[str, Any]] = []
    for ticket in tickets:
        ticket_id = str(ticket["ticket_id"])
        summary = {
            "ticket_id": ticket_id,
            "jornada": int(ticket["jornada"]),
            "draw_date": _iso(ticket["draw_date"]),
        }
        sub = joined[joined["official_ticket_id"] == ticket_id] if not joined.empty else joined.iloc[0:0]
        sub = sub.sort_values("official_ticket_number").copy()
        numbers = sub["official_ticket_number"].astype(int).tolist() if not sub.empty else []
        if len(sub) != 14 or numbers != list(range(1, 15)):
            summary.update({
                "evaluated": False,
                "reason": "cobertura_incompleta",
                "matches_attached": int(len(sub)),
                "matches_expected": 14,
            })
            evaluated_rows.append(summary)
            continue

        results = sub["official_ticket_result"].tolist()
        motor_pred = sub[f"{pred_prefix}_pred"].tolist()
        market_pred = sub["favorite_market"].tolist()
        hits_simple = sum(p == r for p, r in zip(motor_pred, results))
        hits_market = sum(m == r for m, r in zip(market_pred, results))

        doubles_df = evaluate_official_doubles(sub, pred_prefix, config)
        hits_dobles = int(doubles_df.loc[doubles_df["ticket_id"] == ticket_id, "hits_3_dobles_14"].iloc[0])
        double_numbers = [int(n) for n in doubles_df.loc[doubles_df["ticket_id"] == ticket_id, "doubles"].iloc[0]]

        pleno = ticket["pleno15"]
        pleno_key = (_iso(pleno["date"]), key_name(pleno["home"]), key_name(pleno["away"]))
        candidates = index.get(pleno_key, [])
        pleno_exact = pleno_bucket = pleno_top3 = None
        pleno_modelo_bucket = None
        if len(candidates) == 1:
            row = predictions.loc[candidates[0]]
            official_score = str(pleno["score"])
            official_bucket = pleno_bucket_from_source(official_score)
            model_top = row.get("pleno15_marcador")
            if pd.notna(model_top):
                pleno_exact = int(str(model_top) == official_score)
            # Bucket del modelo: usa el bucket agregado (0/1/2/M) si existe;
            # si no (caché vieja), deriva del marcador top-1.
            model_bucket_raw = row.get("pleno15_bucket")
            model_bucket = str(model_bucket_raw) if pd.notna(model_bucket_raw) else pleno_bucket_from_source(str(model_top)) if pd.notna(model_top) else None
            pleno_modelo_bucket = model_bucket
            if official_bucket is not None and model_bucket is not None:
                pleno_bucket = int(official_bucket == model_bucket)
            # Cobertura top-3: ¿el bucket oficial está entre los buckets de los
            # 3 marcadores más probables? (triplica la cobertura del top-1).
            top3 = []
            try:
                top3 = json.loads(row.get("pleno15_top_scores") or "[]")
            except (TypeError, ValueError, json.JSONDecodeError):
                top3 = []
            top3_buckets = {pleno_bucket_from_source(str(item.get("score", ""))) for item in top3 if isinstance(item, dict)}
            pleno_top3 = int(official_bucket in top3_buckets) if official_bucket is not None else None
        pleno_hit = 1 if pleno_bucket else 0
        summary.update({
            "evaluated": True,
            "hits_simple_14": hits_simple,
            "hits_market_14": hits_market,
            "hits_3dobles_14": hits_dobles,
            "hits_15_con_pleno_bucket": hits_dobles + pleno_hit,
            "pleno_exacto": pleno_exact,
            "pleno_bucket": pleno_bucket,
            "pleno_top3_bucket": pleno_top3,
            "pleno_oficial": str(pleno["score"]),
            "pleno_modelo": str(predictions.loc[candidates[0]].get("pleno15_marcador")) if len(candidates) == 1 else None,
            "pleno_modelo_bucket": pleno_modelo_bucket,
            "doubles_positions": double_numbers,
            "matches": [
                {
                    "number": int(r["official_ticket_number"]),
                    "home": r["home"],
                    "away": r["away"],
                    "result": r["official_ticket_result"],
                    "motor": r[f"{pred_prefix}_pred"],
                    "market": r["favorite_market"],
                    "hit_motor": bool(r[f"{pred_prefix}_pred"] == r["official_ticket_result"]),
                    "hit_market": bool(r["favorite_market"] == r["official_ticket_result"]),
                }
                for _, r in sub.iterrows()
            ],
        })
        evaluated_rows.append(summary)

    evaluated = [row for row in evaluated_rows if row.get("evaluated")]
    aggregate = None
    if evaluated:
        aggregate = {
            "n_tickets": len(evaluated),
            "mean_hits_simple_14": float(sum(row["hits_simple_14"] for row in evaluated) / len(evaluated)),
            "mean_hits_market_14": float(sum(row["hits_market_14"] for row in evaluated) / len(evaluated)),
            "mean_hits_3dobles_14": float(sum(row["hits_3dobles_14"] for row in evaluated) / len(evaluated)),
            "mean_hits_15_con_pleno_bucket": float(sum(row["hits_15_con_pleno_bucket"] for row in evaluated) / len(evaluated)),
            "pleno_exacto_total": sum(1 for row in evaluated if row["pleno_exacto"]),
            "pleno_bucket_total": sum(1 for row in evaluated if row["pleno_bucket"]),
            "pleno_top3_bucket_total": sum(1 for row in evaluated if row.get("pleno_top3_bucket")),
        }
        attached_all = joined[joined["official_ticket_id"].isin([row["ticket_id"] for row in evaluated])]
        aggregate["accuracy_motor_union"] = float(attached_all[f"{pred_prefix}_pred"].eq(attached_all["official_ticket_result"]).mean())
        aggregate["accuracy_market_union"] = float(attached_all["favorite_market"].eq(attached_all["official_ticket_result"]).mean())
    return {
        "tickets": evaluated_rows,
        "aggregate": aggregate,
        "attach_stats": attach_stats,
        "nota": "Sin escrutinio oficial por categoria no se calcula ROI (status missing_official_payouts). "
                "La referencia proxy del README (8,63/15) se calcula sobre bloques artificiales de 15 filas "
                "y no es comparable directamente con los boletos oficiales.",
    }


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Agrega filas de boleto evaluadas de una o varias propuestas."""
    evaluated = [row for row in rows if row.get("evaluated")]
    if not evaluated:
        return None
    n = len(evaluated)
    union_motor = [match["hit_motor"] for row in evaluated for match in row["matches"]]
    union_market = [match["hit_market"] for row in evaluated for match in row["matches"]]
    return {
        "n_tickets": n,
        "mean_hits_simple_14": float(sum(row["hits_simple_14"] for row in evaluated) / n),
        "mean_hits_market_14": float(sum(row["hits_market_14"] for row in evaluated) / n),
        "mean_hits_3dobles_14": float(sum(row["hits_3dobles_14"] for row in evaluated) / n),
        "mean_hits_15_con_pleno_bucket": float(sum(row["hits_15_con_pleno_bucket"] for row in evaluated) / n),
        "pleno_exacto_total": sum(1 for row in evaluated if row["pleno_exacto"]),
        "pleno_bucket_total": sum(1 for row in evaluated if row["pleno_bucket"]),
        "pleno_top3_bucket_total": sum(1 for row in evaluated if row.get("pleno_top3_bucket")),
        "accuracy_motor_union": float(sum(union_motor) / len(union_motor)) if union_motor else None,
        "accuracy_market_union": float(sum(union_market) / len(union_market)) if union_market else None,
        "matches_union": len(union_motor),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--propuesta", type=Path, nargs="+", default=[DEFAULT_PROPUESTA])
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--no-cache", action="store_true", help="Recomputa las predicciones sin leer ni escribir la caché")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    missing = [str(path) for path in args.propuesta if not path.is_file()]
    if missing:
        print("No existe(n) la(s) propuesta(s):")
        for path in missing:
            print(f"  - {path}")
        print("Ejecuta primero: python scripts/datos/IMPORTAR_BOLETOS_QUINIELA15.py")
        return 1

    predictions, metrics = load_or_compute_predictions(args.cache, use_cache=not args.no_cache)
    print(f"Predicciones del test principal: {len(predictions)} filas "
          f"(train {metrics.get('train_matches')} / test {metrics.get('test_matches')}, "
          f"split {metrics.get('split_date')})")

    from MOTOR_QUINIELA_MAESTRO import active_hybrid_config

    config = active_hybrid_config()

    propuestas: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    for propuesta_path in args.propuesta:
        payload = load_propuesta(propuesta_path)
        tickets = payload["tickets"]
        print(f"\nPropuesta: {propuesta_path}")
        print(f"Boletos aceptados disponibles: {len(tickets)}")
        if not tickets:
            print("No hay boletos aceptados (sección 'tickets' vacía).")
            continue
        result = evaluate_ticket_results(predictions, tickets, config, pred_prefix=PRED_PREFIX)
        propuestas.append({
            "propuesta": str(propuesta_path),
            "tickets": result["tickets"],
            "aggregate": result["aggregate"],
            "attach_stats": result["attach_stats"],
        })
        all_rows.extend(result["tickets"])

        print("-" * 78)
        for row in result["tickets"]:
            if not row.get("evaluated"):
                print(f"J{row['jornada']:02d} {row['ticket_id']}: {row['reason']} ({row['matches_attached']}/{row['matches_expected']})")
                continue
            print(
                f"J{row['jornada']:02d} {row['ticket_id']}: simples {row['hits_simple_14']}/14 | "
                f"mercado {row['hits_market_14']}/14 | 3 dobles {row['hits_3dobles_14']}/14 | "
                f"pleno {row['pleno_oficial']} (modelo {row['pleno_modelo']}) exacto={row['pleno_exacto']}"
            )
        print("-" * 78)
        agg = result["aggregate"]
        if agg:
            print(f"Media por boleto evaluado: simples {agg['mean_hits_simple_14']:.2f}/14 | "
                  f"mercado {agg['mean_hits_market_14']:.2f}/14 | "
                  f"3 dobles {agg['mean_hits_3dobles_14']:.2f}/14 | "
                  f"15 con pleno(bucket) {agg['mean_hits_15_con_pleno_bucket']:.2f}/15")
            print(f"Acierto sobre la unión de partidos: motor {agg['accuracy_motor_union']:.2%} | "
                  f"mercado {agg['accuracy_market_union']:.2%}")
            print(f"Pleno exacto: {agg['pleno_exacto_total']}/{agg['n_tickets']} | bucket: {agg['pleno_bucket_total']}/{agg['n_tickets']} | top3: {agg.get('pleno_top3_bucket_total', 0)}/{agg['n_tickets']}")
        else:
            print("Ningún boleto pudo evaluarse por cobertura incompleta.")

    global_agg = aggregate_rows(all_rows)
    report = {
        "schema_version": "1.0",
        "modo_motor": "produccion",
        "config_weights": config["weights"],
        "reference_proxy_3_dobles": "8,63/15 bloques artificiales (no comparable directamente)",
        "propuestas": propuestas,
        "aggregate_global": global_agg,
        "nota": "Sin escrutinio oficial por categoria no se calcula ROI (status missing_official_payouts). "
                "La referencia proxy del README (8,63/15) se calcula sobre bloques artificiales de 15 filas "
                "y no es comparable directamente con los boletos oficiales.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if global_agg:
        print("\n" + "=" * 78)
        print(f"GLOBAL ({len(args.propuesta)} propuesta(s)): "
              f"{global_agg['n_tickets']} boletos evaluados, {global_agg['matches_union']} partidos en unión")
        print(f"  simples {global_agg['mean_hits_simple_14']:.2f}/14 | mercado {global_agg['mean_hits_market_14']:.2f}/14 | "
              f"3 dobles {global_agg['mean_hits_3dobles_14']:.2f}/14 | 15 con pleno {global_agg['mean_hits_15_con_pleno_bucket']:.2f}/15")
        print(f"  unión: motor {global_agg['accuracy_motor_union']:.2%} | mercado {global_agg['accuracy_market_union']:.2%} | "
              f"pleno exacto {global_agg['pleno_exacto_total']}/{global_agg['n_tickets']} | bucket {global_agg['pleno_bucket_total']}/{global_agg['n_tickets']} | top3 {global_agg.get('pleno_top3_bucket_total', 0)}/{global_agg['n_tickets']}")
    print(f"Detalle: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
