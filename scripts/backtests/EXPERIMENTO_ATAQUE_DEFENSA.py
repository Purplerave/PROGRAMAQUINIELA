
import pandas as pd
import numpy as np
import sys
from pathlib import Path
from scipy.optimize import minimize
from sklearn.metrics import log_loss

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import settings
from MOTOR_QUINIELA_MAESTRO import (
    load_raw_history,
    LABEL_MAP
)

def estimate_attack_defense(df: pd.DataFrame):
    """
    Estima parámetros de ataque y defensa para cada equipo usando Poisson.
    """
    teams = sorted(list(set(df["home"]) | set(df["away"])))
    team_map = {t: i for i, t in enumerate(teams)}
    n_teams = len(teams)
    
    # Parámetros: mu, home_adv, attack[n_teams], defense[n_teams]
    # Total params = 2 + 2 * n_teams
    # Restricción: sum(attack) = 0 para identificabilidad
    
    initial_params = np.zeros(2 + 2 * n_teams)
    
    home_idx = df["home"].map(team_map).values
    away_idx = df["away"].map(team_map).values
    hg = df["FTHG"].values
    ag = df["FTAG"].values
    
    def objective(params):
        mu = params[0]
        home_adv = params[1]
        att = params[2 : 2 + n_teams]
        dfn = params[2 + n_teams : ]
        
        log_lam_h = mu + home_adv + att[home_idx] - dfn[away_idx]
        log_lam_a = mu + att[away_idx] - dfn[home_idx]
        
        lam_h = np.exp(log_lam_h)
        lam_a = np.exp(log_lam_a)
        
        # Log-likelihood Poisson
        ll_h = hg * log_lam_h - lam_h
        ll_a = ag * log_lam_a - lam_a
        
        return - (np.sum(ll_h) + np.sum(ll_a))
    
    # Restricción: sum(att) = 0
    cons = [{"type": "eq", "fun": lambda x: np.sum(x[2 : 2 + n_teams])}]
    
    res = minimize(objective, initial_params, method="SLSQP", constraints=cons, options={"maxiter": 100})
    
    if not res.success:
        print("Warning: Optimization did not converge fully")
        
    return res.x, teams

def get_lambdas(params, teams, home, away):
    team_map = {t: i for i, t in enumerate(teams)}
    n_teams = len(teams)
    mu = params[0]
    home_adv = params[1]
    att = params[2 : 2 + n_teams]
    dfn = params[2 + n_teams : ]
    
    h_idx = team_map.get(home)
    a_idx = team_map.get(away)
    
    if h_idx is None or a_idx is None:
        return 1.3, 1.1 # Fallback
        
    lam_h = np.exp(mu + home_adv + att[h_idx] - dfn[a_idx])
    lam_a = np.exp(mu + att[a_idx] - dfn[h_idx])
    
    return lam_h, lam_a

def run_experiment():
    raw = load_raw_history()
    # Usar solo datos recientes para estimar (ej. últimas 2 temporadas completas)
    usable = raw[raw["season"].isin(["2024-2025", "2023-2024"])].copy()
    test = raw[raw["season"] == "2025-2026"].copy()
    
    print(f"Entrenando con {len(usable)} partidos...")
    params, teams = estimate_attack_defense(usable)
    
    print("Evaluando en 2025-2026...")
    results = []
    for _, row in test.iterrows():
        lh, la = get_lambdas(params, teams, row["home"], row["away"])
        results.append({"lh_new": lh, "la_new": la})
        
    test_res = pd.concat([test.reset_index(drop=True), pd.DataFrame(results)], axis=1)
    
    # Comparar con lambdas actuales (necesitamos calcularlas)
    from scripts.motor.features import rolling_team_features
    feat = rolling_team_features(raw)
    test_feat = feat[feat["season"] == "2025-2026"].copy()
    
    # Merge para comparar
    merged = test_res.merge(test_feat[["date", "home", "away", "lambda_home", "lambda_away"]], on=["date", "home", "away"])
    
    # Métrica: LogLoss del marcador real bajo Poisson con esas lambdas
    from scipy.stats import poisson
    
    def score_ll(row, lh_col, la_col):
        p_h = poisson.pmf(row["FTHG"], row[lh_col])
        p_a = poisson.pmf(row["FTAG"], row[la_col])
        return -np.log(np.clip(p_h * p_a, 1e-10, 1.0))
        
    merged["ll_old"] = merged.apply(lambda r: score_ll(row, "lambda_home", "lambda_away"), axis=1)
    merged["ll_new"] = merged.apply(lambda r: score_ll(row, "lh_new", "la_new"), axis=1)
    
    print(f"LogLoss Marcador (Old): {merged['ll_old'].mean():.4f}")
    print(f"LogLoss Marcador (New): {merged['ll_new'].mean():.4f}")
    
if __name__ == "__main__":
    # Este experimento requiere mucho tiempo de CPU para optimizar, así que lo limitamos.
    # Pero el usuario pidió analizar la viabilidad.
    run_experiment()
