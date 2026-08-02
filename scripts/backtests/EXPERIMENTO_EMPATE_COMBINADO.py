
import pandas as pd
import numpy as np
import sys
from pathlib import Path
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import log_loss
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
    build_logit_model,
    build_hgb_model,
    predict_full_probs,
    add_market_baseline,
    apply_hybrid_config
)

TARGET_SEASONS = ["2023-2024", "2024-2025", "2025-2026"]
ACTIVE_CONFIG = settings.master_model_config()

def build_draw_model():
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", HistGradientBoostingClassifier(
            loss="log_loss", learning_rate=0.05, max_depth=4, max_iter=150, random_state=42
        ))
    ])

def run_experiment():
    raw = load_raw_history()
    features = rolling_team_features(raw)
    usable = features[features["result"].isin(LABEL_MAP)].copy()
    usable["target"] = usable["result"].map(LABEL_MAP)
    usable["is_draw"] = (usable["target"] == 1).astype(int)
    usable = usable.sort_values("date").reset_index(drop=True)
    cols = feature_columns()
    
    results = []
    
    for target in TARGET_SEASONS:
        train = usable[usable["season"].apply(lambda s: str(s) < target)].copy()
        test = usable[usable["season"] == target].copy()
        if len(train) < 1000 or len(test) == 0: continue
            
        print(f"Temporada {target}...")
        
        # 1. Modelos Base Ensemble
        logit = build_logit_model()
        hgb = build_hgb_model()
        logit.fit(train[cols + ["division"]], train["target"])
        hgb.fit(train[cols], train["target"])
        
        test = add_market_baseline(test)
        logit_p = predict_full_probs(logit, test, cols + ["division"])
        hgb_p = predict_full_probs(hgb, test, cols)
        test["logit_prob_1"], test["logit_prob_x"], test["logit_prob_2"] = logit_p[:, 0], logit_p[:, 1], logit_p[:, 2]
        test["hgb_prob_1"], test["hgb_prob_x"], test["hgb_prob_2"] = hgb_p[:, 0], hgb_p[:, 1], hgb_p[:, 2]
        
        # 2. Ensemble Activo
        test = apply_hybrid_config(test, ACTIVE_CONFIG, "active")
        ll_active = log_loss(test["target"], test[["active_prob_1", "active_prob_x", "active_prob_2"]])
        acc_active = (test["active_pred"] == test["result"]).mean()
        
        # 3. Clasificador de Empates Binario
        clf_draw = build_draw_model()
        clf_draw.fit(train[cols], train["is_draw"])
        p_draw_bin = clf_draw.predict_proba(test[cols])[:, 1]
        
        # 4. Combinación: usar p_draw_bin para reemplazar X en el ensemble activo
        # P(1_new) = P(1_act | not X_act) * (1 - p_draw_bin)
        # P(2_new) = P(2_act | not X_act) * (1 - p_draw_bin)
        # P(X_new) = p_draw_bin
        
        p_not_x_act = test["active_prob_1"] + test["active_prob_2"]
        # Evitar división por cero
        p_not_x_act = np.where(p_not_x_act == 0, 1e-6, p_not_x_act)
        
        p1_cond = test["active_prob_1"] / p_not_x_act
        p2_cond = test["active_prob_2"] / p_not_x_act
        
        test["draw_clf_prob_1"] = p1_cond * (1 - p_draw_bin)
        test["draw_clf_prob_x"] = p_draw_bin
        test["draw_clf_prob_2"] = p2_cond * (1 - p_draw_bin)
        
        ll_new = log_loss(test["target"], test[["draw_clf_prob_1", "draw_clf_prob_x", "draw_clf_prob_2"]])
        test["draw_clf_pred"] = test[["draw_clf_prob_1", "draw_clf_prob_x", "draw_clf_prob_2"]].idxmax(axis=1).map(
            {"draw_clf_prob_1": "1", "draw_clf_prob_x": "X", "draw_clf_prob_2": "2"}
        )
        acc_new = (test["draw_clf_pred"] == test["result"]).mean()
        
        results.append({
            "season": target,
            "ll_active": ll_active,
            "ll_new": ll_new,
            "acc_active": acc_active,
            "acc_new": acc_new
        })
        print(f"  LogLoss: {ll_active:.4f} -> {ll_new:.4f} ({(ll_new-ll_active):+.4f})")
        print(f"  Acierto: {acc_active:.2%} -> {acc_new:.2%} ({(acc_new-acc_active):+.2%})")

    print("\n--- RESULTADOS AGREGADOS ---")
    df = pd.DataFrame(results)
    print(df.drop(columns="season").mean())

if __name__ == "__main__":
    run_experiment()
