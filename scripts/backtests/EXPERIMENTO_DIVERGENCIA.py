
import pandas as pd
import numpy as np
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import settings
from MOTOR_QUINIELA_MAESTRO import (
    load_raw_history,
    rolling_team_features,
    LABEL_MAP,
    feature_columns,
    build_hgb_model,
    predict_full_probs,
    add_market_baseline
)

TARGET_SEASONS = ["2023-2024", "2024-2025", "2025-2026"]

def run_experiment():
    raw = load_raw_history()
    features = rolling_team_features(raw)
    usable = features[features["result"].isin(LABEL_MAP)].copy()
    usable["target"] = usable["result"].map(LABEL_MAP)
    usable = usable.sort_values("date").reset_index(drop=True)
    cols = feature_columns()
    
    all_divergences = []
    
    for target in TARGET_SEASONS:
        train = usable[usable["season"].apply(lambda s: str(s) < target)].copy()
        test = usable[usable["season"] == target].copy()
        if len(train) < 1000 or len(test) == 0: continue
            
        print(f"Temporada {target}...")
        
        hgb = build_hgb_model()
        hgb.fit(train[cols], train["target"])
        
        test = add_market_baseline(test)
        hgb_p = predict_full_probs(hgb, test, cols)
        
        # Divergencia: HGB vs Market
        # Nos interesan casos donde HGB da mucha más probabilidad a un signo que el mercado
        for i, sign in enumerate(["1", "X", "2"]):
            hgb_prob = hgb_p[:, i]
            market_prob = test[f"market_{sign.lower()}"].to_numpy()
            
            diff = hgb_prob - market_prob
            
            # Guardamos para análisis
            df_div = pd.DataFrame({
                "season": target,
                "sign": sign,
                "hgb_prob": hgb_prob,
                "market_prob": market_prob,
                "diff": diff,
                "hit": (test["target"] == i).astype(int)
            })
            all_divergences.append(df_div)

    df = pd.concat(all_divergences)
    
    print("\n--- Análisis de Divergencia HGB vs Mercado ---")
    
    # Ver rendimiento por tramos de divergencia
    df["diff_bin"] = pd.cut(df["diff"], bins=[-1, -0.1, -0.05, 0.05, 0.1, 1])
    
    summary = df.groupby("diff_bin", observed=True).agg({
        "hit": ["count", "mean"],
        "market_prob": "mean",
        "hgb_prob": "mean"
    })
    summary.columns = ["count", "actual_rate", "avg_market", "avg_hgb"]
    print(summary)
    
    # El valor real es cuando actual_rate > avg_market
    summary["value"] = summary["actual_rate"] - summary["avg_market"]
    print("\nValor extra detectado por tramos:")
    print(summary["value"])

if __name__ == "__main__":
    run_experiment()
