
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
    build_logit_model,
    build_hgb_model,
    predict_full_probs,
    add_market_baseline,
    apply_hybrid_config,
    evaluate_config,
    simulate_doubles
)

def multi_split_optimization(df: pd.DataFrame, n_seasons: int = 3):
    """
    Versión mejorada de la optimización que usa múltiples temporadas como bloques de validación.
    """
    usable = df[df["result"].isin(LABEL_MAP)].copy()
    usable["target"] = usable["result"].map(LABEL_MAP)
    usable = usable.sort_values(["date", "division", "home", "away"]).reset_index(drop=True)
    
    seasons = sorted(usable["season"].dropna().unique().tolist(), 
                    key=lambda s: (int(str(s).split("-")[0]), str(s)))
    
    # Tomamos las últimas N temporadas completas para validación
    # Si estamos en medio de una, la última puede estar incompleta pero sirve igual.
    val_seasons = seasons[-n_seasons:]
    print(f"Temporadas de validación: {val_seasons}")
    
    # Candidatos (sacados de settings o defaults)
    master_config = settings.master_model_config()
    weight_candidates = master_config.get("weight_candidates", [])
    draw_boosts = master_config.get("draw_boost_candidates", [0.0])
    segunda_draw_boosts = master_config.get("segunda_draw_boost_candidates", [0.0])
    x_strategies = master_config.get("x_disagreement_strategy_candidates", ["none"])
    
    # Para cada temporada de validación, obtenemos las predicciones de los modelos base
    val_frames = []
    
    for v_season in val_seasons:
        train_mask = usable["season"].apply(lambda s: seasons.index(s) < seasons.index(v_season))
        val_mask = usable["season"] == v_season
        
        train_sub = usable[train_mask].copy()
        val_sub = usable[val_mask].copy()
        
        if len(train_sub) < 1000 or len(val_sub) < 100:
            print(f"Saltando {v_season} por falta de datos (Train: {len(train_sub)}, Val: {len(val_sub)})")
            continue
            
        print(f"Entrenando modelos base para validación en {v_season}...")
        logit = build_logit_model()
        hgb = build_hgb_model()
        
        logit.fit(train_sub[feature_columns() + ["division"]], train_sub["target"])
        hgb.fit(train_sub[feature_columns()], train_sub["target"])
        
        val_sub = add_market_baseline(val_sub)
        logit_probs = predict_full_probs(logit, val_sub, feature_columns() + ["division"])
        hgb_probs = predict_full_probs(hgb, val_sub, feature_columns())
        
        val_sub["logit_prob_1"] = logit_probs[:, 0]
        val_sub["logit_prob_x"] = logit_probs[:, 1]
        val_sub["logit_prob_2"] = logit_probs[:, 2]
        val_sub["hgb_prob_1"] = hgb_probs[:, 0]
        val_sub["hgb_prob_x"] = hgb_probs[:, 1]
        val_sub["hgb_prob_2"] = hgb_probs[:, 2]
        
        val_frames.append(val_sub)
    
    if not val_frames:
        raise ValueError("No se pudieron generar bloques de validación suficientes.")
        
    # Grid search sobre los candidatos evaluando en TODOS los val_frames
    import itertools
    
    best = None
    results = []
    
    # Simplificamos los candidatos para el experimento (solo los más importantes)
    # En la integración final usaremos todos los de la config.
    
    combinations = list(itertools.product(
        weight_candidates,
        draw_boosts,
        segunda_draw_boosts,
        x_strategies
    ))
    
    print(f"Evaluando {len(combinations)} combinaciones en {len(val_frames)} splits...")
    
    for weights, db, sdb, x_strat in combinations:
        config = {
            "weights": weights,
            "draw_boost": db,
            "segunda_draw_boost": sdb,
            "x_disagreement_strategy": x_strat,
            # Defaults para el resto
            "double_draw_weight": 0.70,
            "double_disagreement_weight": 0.20,
            "double_segunda_bonus": 0.05,
            "double_draw_threshold": 0.30
        }
        
        split_scores = []
        for val_df in val_frames:
            # Usamos evaluate_config pero nos interesa solo el acierto simple o logloss
            # para decidir. El roadmap dice "acierto simple" y "3 dobles".
            ev = evaluate_config(val_df, "tmp", config)
            split_scores.append(ev["score"])
            
        mean_score = np.mean(split_scores)
        std_score = np.std(split_scores)
        
        # Métrica de estabilidad: penalizamos la varianza
        final_metric = mean_score - (0.5 * std_score)
        
        results.append({
            "config": config,
            "mean_score": mean_score,
            "std_score": std_score,
            "final_metric": final_metric
        })
        
        if best is None or final_metric > best["final_metric"]:
            best = results[-1]
            
    print("\n--- Resultados de Optimización Multi-Split ---")
    print(f"Mejor configuración (métrica final: {best['final_metric']:.4f}):")
    print(f"Pesos: {best['config']['weights']}")
    print(f"Mean Score: {best['mean_score']:.4f}, Std: {best['std_score']:.4f}")
    
    return best["config"]

if __name__ == "__main__":
    raw = load_raw_history()
    features = rolling_team_features(raw)
    best_cfg = multi_split_optimization(features)
    print("\nConfiguración optimizada completada.")
