import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import MOTOR_QUINIELA_MAESTRO as motor


ROOT = PROJECT_ROOT
OUT_DIR = ROOT / "salida"


def season_key(season):
    text = str(season)
    try:
        return int(text.split("-")[0])
    except Exception:
        return 0


def main():
    parser = argparse.ArgumentParser(description="Backtest walk-forward por temporadas del motor de quinielas.")
    parser.add_argument("--from-season", default="2019-2020", help="Primera temporada a evaluar")
    parser.add_argument("--to-season", default="", help="Última temporada a evaluar. Vacío = última disponible")
    parser.add_argument("--save-predictions", action="store_true", help="Guarda CSV de predicciones por temporada")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = motor.load_raw_history()
    features = motor.rolling_team_features(raw)
    usable = features[features["result"].isin(motor.LABEL_MAP)].copy()
    seasons = sorted(usable["season"].dropna().unique().tolist(), key=motor.season_sort_key)
    selected = [s for s in seasons if season_key(s) >= season_key(args.from_season)]
    if args.to_season:
        selected = [s for s in selected if season_key(s) <= season_key(args.to_season)]

    rows = []
    details = {}
    for season in selected:
        try:
            predictions, metrics = motor.run_season_backtest(features, season)
        except Exception as exc:
            rows.append({
                "season": season,
                "error": str(exc),
            })
            continue
        model = metrics["latest_season_model"]
        row = {
            "season": season,
            "train_matches": metrics["train_matches"],
            "test_matches": metrics["test_matches"],
            "date_from": metrics["test_date_from"],
            "date_to": metrics["test_date_to"],
            "accuracy_simple": model["accuracy_simple"],
            "accuracy_market_favorite": model["accuracy_market_favorite"],
            "mean_hits_3_dobles": model["mean_hits_3_dobles"],
            "best_jornada_3_dobles": model["best_jornada_3_dobles"],
            "primera_matches": model["division_breakdown"].get("Primera", {}).get("matches", 0),
            "primera_accuracy": model["division_breakdown"].get("Primera", {}).get("accuracy_simple", None),
            "segunda_matches": model["division_breakdown"].get("Segunda", {}).get("matches", 0),
            "segunda_accuracy": model["division_breakdown"].get("Segunda", {}).get("accuracy_simple", None),
        }
        rows.append(row)
        details[season] = metrics
        if args.save_predictions:
            predictions.to_csv(OUT_DIR / f"predicciones_backtest_temporada_{season.replace('-', '_')}.csv", index=False, encoding="utf-8-sig")
        print(
            f"{season}: simple {row['accuracy_simple']:.2%} | mercado {row['accuracy_market_favorite']:.2%} | "
            f"3 dobles {row['mean_hits_3_dobles']:.2f}/15"
        )

    frame = pd.DataFrame(rows)
    csv_path = OUT_DIR / "backtest_historico_temporadas.csv"
    json_path = OUT_DIR / "backtest_historico_temporadas.json"
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    json_path.write_text(json.dumps({"rows": rows, "details": details}, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = frame[frame.get("error").isna()] if "error" in frame.columns else frame
    summary = {
        "temporadas": int(len(ok)),
        "media_accuracy_simple": float(ok["accuracy_simple"].mean()) if not ok.empty else None,
        "media_accuracy_market": float(ok["accuracy_market_favorite"].mean()) if not ok.empty else None,
        "media_3_dobles": float(ok["mean_hits_3_dobles"].mean()) if not ok.empty else None,
        "mejor_temporada_simple": ok.sort_values("accuracy_simple", ascending=False).head(1).to_dict("records") if not ok.empty else [],
        "peor_temporada_simple": ok.sort_values("accuracy_simple", ascending=True).head(1).to_dict("records") if not ok.empty else [],
        "csv": str(csv_path),
        "json": str(json_path),
    }
    if not ok.empty:
        accuracies = ok["accuracy_simple"].dropna().astype(float).to_list()
        market = ok["accuracy_market_favorite"].dropna().astype(float).to_list()
        gaps = [a - m for a, m in zip(accuracies, market)]
        summary["stability"] = {
            "mean_accuracy": float(np.mean(accuracies)) if accuracies else None,
            "std_accuracy": float(np.std(accuracies)) if accuracies else None,
            "cv_accuracy": float(np.std(accuracies) / np.mean(accuracies)) if accuracies and np.mean(accuracies) else None,
            "min_accuracy": float(np.min(accuracies)) if accuracies else None,
            "max_accuracy": float(np.max(accuracies)) if accuracies else None,
            "trend": float(np.polyfit(range(len(accuracies)), accuracies, 1)[0]) if len(accuracies) > 1 else None,
            "mean_market": float(np.mean(market)) if market else None,
            "std_market": float(np.std(market)) if market else None,
            "mean_gap_vs_market": float(np.mean(gaps)) if gaps else None,
        }
    (OUT_DIR / "backtest_historico_temporadas_resumen.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
