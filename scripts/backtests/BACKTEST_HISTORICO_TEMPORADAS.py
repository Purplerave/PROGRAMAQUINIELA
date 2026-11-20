import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import MOTOR_QUINIELA_MAESTRO as motor
from scripts.json_output import write_json
from scripts.motor.xg_understat import XG_CSV


ROOT = PROJECT_ROOT
OUT_DIR = ROOT / "salida"


def evaluation_protocol(source: str, from_season: str, to_season: str) -> dict:
    """Identifica el dataset exacto y la ventana del resultado escrito."""
    if source == "saneado":
        files = [motor.SANITIZED_HISTORY]
    elif source == "original":
        files = sorted(path for division in motor.DIVISION_LABELS for path in (motor.RAW_BASE / division).glob("*.csv"))
    else:
        raise ValueError(f"Fuente histórica no válida: {source}")
    hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in files]
    dataset_hash = hashes[0] if source == "saneado" else hashlib.sha256("".join(hashes).encode("ascii")).hexdigest()
    code_files = [Path(__file__), Path(motor.__file__), Path(motor.settings.__file__), ROOT / "scripts/json_output.py"]
    code_files += [ROOT / "scripts" / "motor" / f"{name}.py" for name in (
        "features", "team_names", "temporal", "calibration", "calibrador_bandas", "cobertura_bandas", "dixon_coles", "xg_understat"
    )]
    code_hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in code_files]
    return {
        "tipo": "walk_forward_temporadas_v2",
        "codigo_sha256": hashlib.sha256("".join(code_hashes).encode("ascii")).hexdigest(),
        "entorno_numerico": {"python": platform.python_version(), **{
            name: importlib.metadata.version(name) for name in ("numpy", "pandas", "scipy", "scikit-learn")
        }},
        "modo": "production",
        "historico": source,
        "historico_sha256": dataset_hash,
        "xg_opcional_sha256": hashlib.sha256(XG_CSV.read_bytes()).hexdigest() if XG_CSV.is_file() else None,
        "config_sha256": hashlib.sha256(motor.settings.CONFIG_PATH.read_bytes()).hexdigest(),
        "desde_temporada": from_season,
        "hasta_temporada": to_season,
    }


def _season(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{4}", value) or int(value[5:]) != int(value[:4]) + 1:
        raise argparse.ArgumentTypeError(f"Temporada inválida: {value!r}; usa AAAA-AAAA en años consecutivos")
    return value


def paired_market_statistics(predictions: pd.DataFrame) -> dict:
    """Contrasta aciertos del motor y del favorito en los mismos partidos."""
    required = {"latest_hit", "favorite_market_hit"}
    if not required.issubset(predictions.columns):
        return {"n": 0, "discordant_model_only": 0, "discordant_market_only": 0, "mcnemar_pvalue": None}

    frame = predictions.dropna(subset=["latest_hit", "favorite_market_hit"]).copy()
    if frame.empty:
        return {"n": 0, "discordant_model_only": 0, "discordant_market_only": 0, "mcnemar_pvalue": None}

    model_hit = frame["latest_hit"].astype(bool).to_numpy()
    market_hit = frame["favorite_market_hit"].astype(bool).to_numpy()
    model_only = int((model_hit & ~market_hit).sum())
    market_only = int((~model_hit & market_hit).sum())
    discordant = model_only + market_only
    pvalue = float(binomtest(model_only, discordant, 0.5, alternative="two-sided").pvalue) if discordant else 1.0

    # IC bootstrap pareado por partido; no corrige dependencia por fútbol/jornada.
    differences = model_hit.astype(float) - market_hit.astype(float)
    rng = np.random.default_rng(20260824)
    samples = np.concatenate([
        rng.choice(differences, size=(100, len(differences)), replace=True).mean(axis=1)
        for _ in range(50)
    ])
    low, high = np.quantile(samples, [0.025, 0.975])
    return {
        "n": int(len(frame)),
        "model_accuracy": float(model_hit.mean()),
        "market_accuracy": float(market_hit.mean()),
        "gap": float(differences.mean()),
        "discordant_model_only": model_only,
        "discordant_market_only": market_only,
        "mcnemar_pvalue": pvalue,
        "bootstrap_gap_ci95": [float(low), float(high)],
    }


def probabilistic_market_scores(predictions: pd.DataFrame) -> dict:
    """Brier multiclase y log-loss en el mismo subconjunto para ambos modelos."""
    model_keys = [f"latest_prob_{s}" for s in ("1", "x", "2")]
    market_keys = [f"market_{s}" for s in ("1", "x", "2")]
    keys = model_keys + market_keys
    if not set(keys + ["result"]).issubset(predictions.columns):
        return {"n": 0}
    numbers = predictions[keys].to_numpy(dtype=float)
    valid = np.isfinite(numbers).all(axis=1) & predictions["result"].isin(motor.LABEL_MAP).to_numpy()
    if not valid.any():
        return {"n": 0}
    labels = predictions.loc[valid, "result"].map(motor.LABEL_MAP).to_numpy(dtype=int)
    encoded = np.eye(3)[labels]

    def score(probs: np.ndarray) -> dict:
        observed = probs[np.arange(len(labels)), labels]
        return {
            "brier": float(np.square(probs - encoded).sum(axis=1).mean()),
            "log_loss": float(-np.log(np.maximum(observed, np.finfo(float).eps)).mean()),
        }

    return {"n": len(labels), "modelo": score(numbers[valid, :3]), "mercado": score(numbers[valid, 3:])}


def regime_statistics(predictions: pd.DataFrame) -> dict:
    """Desglosa el backtest según exista cierre de mercado real."""
    if "market_close_available" not in predictions.columns:
        return {}
    output = {}
    labels = {True: "cierre_real", False: "apertura_fallback"}
    for available, group in predictions.groupby("market_close_available", dropna=False):
        key = labels.get(bool(available), "desconocido")
        stats = paired_market_statistics(group)
        stats["market_sources"] = {
            str(source): int(count)
            for source, count in group.get("market_source", pd.Series(dtype=object)).value_counts().items()
        }
        output[key] = stats
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest walk-forward por temporadas del motor de quinielas.")
    parser.add_argument("--from-season", default="2019-2020", type=_season, help="Primera temporada a evaluar")
    parser.add_argument("--to-season", type=_season, help="Última temporada; por defecto, la última disponible")
    parser.add_argument("--historico", choices=("saneado", "original"), default=motor.settings.official_history_source())
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--save-predictions", action="store_true", help="Guarda CSV de predicciones por temporada")
    args = parser.parse_args()
    if args.to_season and args.to_season < args.from_season:
        parser.error("--to-season no puede ser anterior a --from-season")
    try:
        raw = motor.load_raw_history(args.historico)
    except FileNotFoundError as exc:
        parser.error(str(exc))
    seasons = sorted(raw.loc[raw["result"].isin(motor.LABEL_MAP), "season"].dropna().unique(), key=motor.season_sort_key)
    selected = [s for s in seasons if args.from_season <= s and (not args.to_season or s <= args.to_season)]
    if not selected:
        parser.error("No hay temporadas evaluables en el rango solicitado")
    end = args.to_season or selected[-1]
    expected = [f"{year}-{year + 1}" for year in range(int(args.from_season[:4]), int(end[:4]) + 1)]
    if selected != expected:
        parser.error(f"Faltan temporadas del rango solicitado: {', '.join(sorted(set(expected) - set(selected)))}")
    protocol = evaluation_protocol(args.historico, selected[0], selected[-1])
    features = motor.rolling_team_features(raw)
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    details = {}
    all_predictions = []
    for season in selected:
        try:
            predictions, metrics = motor.run_season_backtest(features, season)
        except ValueError as exc:
            print(f"{season}: ERROR: {exc}", file=sys.stderr)
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
        row["regime_breakdown"] = regime_statistics(predictions)
        row["paired_statistics"] = paired_market_statistics(predictions)
        row["probabilistic_scores"] = probabilistic_market_scores(predictions)
        all_predictions.append(predictions)
        rows.append(row)
        details[season] = metrics
        if args.save_predictions:
            predictions.to_csv(out_dir / f"predicciones_backtest_temporada_{season.replace('-', '_')}.csv", index=False, encoding="utf-8-sig")
        print(
            f"{season}: simple {row['accuracy_simple']:.2%} | mercado {row['accuracy_market_favorite']:.2%} | "
            f"3 dobles {row['mean_hits_3_dobles']:.2f}/15"
        )

    frame = pd.DataFrame(rows)
    csv_path = out_dir / "backtest_historico_temporadas.csv"
    json_path = out_dir / "backtest_historico_temporadas.json"
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")

    ok = frame[frame.get("error").isna()] if "error" in frame.columns else frame
    successful = [r for r in rows if "error" not in r]
    summary = {
        "protocolo": protocol,
        "temporadas_con_error": len(rows) - len(ok),
        "temporadas": int(len(ok)),
        "media_accuracy_simple": float(ok["accuracy_simple"].mean()) if not ok.empty else None,
        "media_accuracy_market": float(ok["accuracy_market_favorite"].mean()) if not ok.empty else None,
        "media_3_dobles": float(ok["mean_hits_3_dobles"].mean()) if not ok.empty else None,
        "mejor_temporada_simple": [max(successful, key=lambda r: r["accuracy_simple"])] if successful else [],
        "peor_temporada_simple": [min(successful, key=lambda r: r["accuracy_simple"])] if successful else [],
        "csv": str(csv_path),
        "json": str(json_path),
    }
    if not ok.empty:
        accuracies = ok["accuracy_simple"].dropna().astype(float).to_list()
        market = ok["accuracy_market_favorite"].dropna().astype(float).to_list()
        gaps = [a - m for a, m in zip(accuracies, market, strict=False)]
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

    if all_predictions:
        combined_predictions = pd.concat(all_predictions, ignore_index=True)
        summary["paired_statistics"] = paired_market_statistics(combined_predictions)
        summary["regime_breakdown"] = regime_statistics(combined_predictions)
        summary["probabilistic_scores"] = probabilistic_market_scores(combined_predictions)
    write_json(json_path, {"protocolo": protocol, "rows": rows, "details": details, "resumen": summary})
    write_json(out_dir / "backtest_historico_temporadas_resumen.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return int(bool(summary["temporadas_con_error"]))


if __name__ == "__main__":
    raise SystemExit(main())
