"""scripts/motor/dixon_coles.py — Modelo de Poisson bivariante de Dixon-Coles.

Corrige la correlación de los marcadores bajos (0-0, 1-0, 0-1 y 1-1) que el
Poisson independiente no captura, mediante el factor tau con un parámetro rho:

    tau(0,0) = 1 - lambda*mu*rho
    tau(1,0) = 1 + lambda*rho
    tau(0,1) = 1 + mu*rho
    tau(1,1) = 1 - rho

P(x,y) = tau(x,y) * Pois(x;lambda_local) * Pois(y;lambda_visitante)
"""

from __future__ import annotations

import numpy as np
from scipy.stats import poisson

DEFAULT_MAX_GOALS = 7
DEFAULT_RHO_GRID = np.linspace(-0.30, 0.10, 41)


def dc_tau_matrix(lam_h: np.ndarray, lam_a: np.ndarray, rho: float, goals: int) -> np.ndarray:
    """Factor tau para todos los marcadores, vectorizado sobre (n, goals, goals)."""
    n = len(lam_h)
    xg, yg = np.meshgrid(np.arange(goals), np.arange(goals), indexing="ij")
    xx = np.broadcast_to(xg, (n, goals, goals))
    yy = np.broadcast_to(yg, (n, goals, goals))
    lam_h3 = lam_h[:, None, None]
    lam_a3 = lam_a[:, None, None]
    tau = np.ones((n, goals, goals), dtype=float)
    tau = np.where((xx == 0) & (yy == 0), 1.0 - lam_h3 * lam_a3 * rho, tau)
    tau = np.where((xx == 1) & (yy == 0), 1.0 + lam_h3 * rho, tau)
    tau = np.where((xx == 0) & (yy == 1), 1.0 + lam_a3 * rho, tau)
    tau = np.where((xx == 1) & (yy == 1), 1.0 - rho, tau)
    return tau


def dc_score_probs(
    lam_h: np.ndarray | list, lam_a: np.ndarray | list, rho: float,
    max_goals: int = DEFAULT_MAX_GOALS,
) -> np.ndarray:
    """Probabilidades de cada marcador (x, y) con Dixon-Coles. Forma (n, G, G)."""
    lam_h = np.asarray(lam_h, dtype=float)
    lam_a = np.asarray(lam_a, dtype=float)
    goals = max_goals + 1
    p_h = poisson.pmf(np.arange(goals)[None, :], lam_h[:, None])   # (n, G)
    p_a = poisson.pmf(np.arange(goals)[None, :], lam_a[:, None])   # (n, G)
    prod = p_h[:, :, None] * p_a[:, None, :]                       # (n, G, G)
    tau = dc_tau_matrix(lam_h, lam_a, rho, goals)
    prob = np.clip(prod * tau, 1e-15, None)
    prob = prob / prob.sum(axis=(1, 2), keepdims=True)
    return prob


def dc_1x2(
    lam_h: np.ndarray | list, lam_a: np.ndarray | list, rho: float,
    max_goals: int = DEFAULT_MAX_GOALS,
) -> np.ndarray:
    """Probabilidades 1/X/2 con Dixon-Coles. Forma (n, 3)."""
    prob = dc_score_probs(lam_h, lam_a, rho, max_goals)
    goals = max_goals + 1
    xg, yg = np.meshgrid(np.arange(goals), np.arange(goals), indexing="ij")
    p1 = prob[:, xg > yg].sum(axis=1)
    px = prob[:, xg == yg].sum(axis=1)
    p2 = prob[:, xg < yg].sum(axis=1)
    return np.stack([p1, px, p2], axis=1)


def top_scorelines(
    lam_h: np.ndarray | list, lam_a: np.ndarray | list, rho: float,
    max_goals: int = DEFAULT_MAX_GOALS, top_n: int = 3,
) -> list[list[dict]]:
    """Top-N marcadores más probables por partido (para el Pleno al 15)."""
    prob = dc_score_probs(lam_h, lam_a, rho, max_goals)
    n = prob.shape[0]
    out = []
    for i in range(n):
        flat = prob[i]
        idx = np.argsort(flat, axis=None)[::-1][:top_n]
        rows = []
        for flat_idx in idx:
            x, y = np.unravel_index(flat_idx, flat.shape)
            rows.append(
                {
                    "score": f"{x}-{y}",
                    "prob": float(flat[x, y]),
                    "local": int(x),
                    "visitante": int(y),
                }
            )
        out.append(rows)
    return out


def estimate_rho(
    lam_h: np.ndarray, lam_a: np.ndarray, hg: np.ndarray, ag: np.ndarray,
    grid: np.ndarray | None = None, max_goals: int = DEFAULT_MAX_GOALS,
) -> float:
    """Estima rho por máxima verosimilitud sobre marcadores observados."""
    if grid is None:
        grid = DEFAULT_RHO_GRID
    n = len(lam_h)
    goals = max_goals + 1
    best_rho, best_ll = 0.0, -np.inf
    hg_c = np.clip(hg.astype(int), 0, max_goals)
    ag_c = np.clip(ag.astype(int), 0, max_goals)
    for rho in grid:
        prob = dc_score_probs(lam_h, lam_a, float(rho), max_goals)
        ll = float(np.log(prob[np.arange(n), hg_c, ag_c]).sum())
        if ll > best_ll:
            best_ll, best_rho = ll, float(rho)
    return best_rho
