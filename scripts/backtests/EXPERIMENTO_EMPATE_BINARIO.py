
import pandas as pd
import numpy as np
import sys
from pathlib import Path
import itertools
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import log_loss, roc_auc_score, precision_score, recall_score
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import settings
from MOTOR_QUINIELA_MAESTRO import (
    load_raw_history,
    rolling_team_features,
    LABEL_MAP,
    feature_columns,
    add_market_baseline
)

TARGET_SEASONS = ["2023-2024", "2024-2025", "2025-2026"]

def build_draw_model():
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", HistGradientBoostingClassifier(
            loss="log_loss",
            learning_rate=0.05,
            max_depth=5,
            max_iter=200,
            random_state=42
        ))
    ])

def run_experiment():
    raw = load_raw_history()
    features = rolling_team_features(raw)
    
    usable = features[features["result"].isin(LABEL_MAP)].copy()
    usable["target"] = usable["result"].map(LABEL_MAP)
    # Target binario: 1 si es empate (X=1 en LABEL_MAP), 0 en otro caso
    usable["is_draw"] = (usable["target"] == 1).astype(int)
    usable = usable.sort_values("date").reset_index(drop=True)
    
    cols = feature_columns()
    
    per_season = []
    
    for target in TARGET_SEASONS:
        train = usable[usable["season"].apply(lambda s: str(s) < target)].copy()
        test = usable[usable["season"] == target].copy()
        
        if len(train) < 1000 or len(test) == 0:
            continue
            
        print(f"Evaluando temporada {target}...")
        
        # Entrenar clasificador binario de empates
        clf = build_draw_model()
        clf.fit(train[cols], train["is_draw"])
        
        # Probabilidades binarias en test
        draw_probs = clf.predict_proba(test[cols])[:, 1]
        
        y_true = test["is_draw"].to_numpy()
        
        # Métricas del clasificador binario
        auc = roc_auc_score(y_true, draw_probs)
        ll = log_loss(y_true, draw_probs)
        
        # Umbral simple para ver precisión/recall (ej. 0.33 ya que los empates son ~25%)
        preds = (draw_probs > 0.30).astype(int)
        prec = precision_score(y_true, preds, zero_division=0)
        rec = recall_score(y_true, preds, zero_division=0)
        
        per_season.append({
            "season": target,
            "auc": auc,
            "log_loss": ll,
            "precision_30": prec,
            "recall_30": rec,
            "mean_draw_prob": np.mean(draw_probs),
            "actual_draw_rate": np.mean(y_true)
        })
        
        print(f"  AUC: {auc:.4f}, LogLoss: {ll:.4f}, Prec@30: {prec:.4f}, Rec@30: {rec:.4f}")

    print("\n--- RESUMEN CLASIFICADOR BINARIO DE EMPATES ---")
    df_res = pd.DataFrame(per_season)
    print(df_res.drop(columns=["season"]).mean())

if __name__ == "__main__":
    run_experiment()
