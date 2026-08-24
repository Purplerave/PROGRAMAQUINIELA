"""
CONTEXT ENGINE — El nuevo enfoque Multiverso para La Quiniela (2026+)

El mercado es extremadamente eficiente en stats clásicas.
EL EDGE REAL está en **contextos donde el mercado no descuenta bien**:
- Rotaciones / fin de temporada (partidos "intrascendentes")
- Fatiga acumulada + calendario congestionado
- Presión máxima (descenso, título, play-off)
- Derbis y rivalidades (emoción > stats)
- Ascenso/descenso psicológico
- "Hidden value" en Segunda

Este módulo genera features de contexto + señales de valor contextual.
Solo se activa si mejora P(≥12) o EV económico en walk-forward.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Any, Dict, List, Optional
from dataclasses import asdict


class ContextEngine:
    """
    Motor de contexto para detectar ineficiencias del mercado.
    Punto de vista: "El mercado es Dios, pero a veces duerme".
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.season_end_threshold = self.config.get("season_end_jornada", 32)
        self.relegation_zone = self.config.get("relegation_zone", (17, 20))
        self.title_zone = self.config.get("title_zone", (1, 4))
        self.playoff_zone = self.config.get("playoff_zone", (5, 7))
        self.fatigue_threshold_days = self.config.get("fatigue_threshold_days", 3)

    def compute_context_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Añade features de contexto point-in-time.
        Debe llamarse DESPUÉS de las features estándar.
        """
        out = df.copy()

        # 1. Jornada relativa (fin de temporada)
        out["jornada_num"] = out.groupby("season").cumcount() + 1
        out["is_season_end"] = (out["jornada_num"] >= self.season_end_threshold).astype(int)
        out["days_to_end"] = 38 - out["jornada_num"]

        # 2. Motivación / presión (basado en tabla point-in-time)
        out["home_motivation"] = self._motivation_score(
            out["home_table_pos"], out["home_table_pts"], out["home_table_ppg"]
        )
        out["away_motivation"] = self._motivation_score(
            out["away_table_pos"], out["away_table_pts"], out["away_table_ppg"]
        )
        out["motivation_diff"] = out["home_motivation"] - out["away_motivation"]
        out["high_pressure_match"] = (
            (out["home_motivation"] > 0.7) | (out["away_motivation"] > 0.7)
        ).astype(int)

        # 3. Fatiga y descanso (ya existe days_rest, lo enriquecemos)
        out["fatigue_home"] = (out["days_rest_home"] < self.fatigue_threshold_days).astype(int)
        out["fatigue_away"] = (out["days_rest_away"] < self.fatigue_threshold_days).astype(int)
        out["fatigue_diff"] = out["days_rest_home"] - out["days_rest_away"]
        out["both_fatigued"] = ((out["fatigue_home"] == 1) & (out["fatigue_away"] == 1)).astype(int)

        # 4. Contexto de temporada (ascenso/descenso psicológico)
        out["home_in_relegation_battle"] = (
            (out["home_table_pos"] >= self.relegation_zone[0]) & 
            (out["home_table_pos"] <= self.relegation_zone[1])
        ).astype(int)
        out["away_in_relegation_battle"] = (
            (out["away_table_pos"] >= self.relegation_zone[0]) & 
            (out["away_table_pos"] <= self.relegation_zone[1])
        ).astype(int)

        out["home_title_chase"] = (
            (out["home_table_pos"] >= self.title_zone[0]) & 
            (out["home_table_pos"] <= self.title_zone[1])
        ).astype(int)

        # 5. Derbi / rivalidad (heurística simple por nombres comunes)
        out["is_derby"] = self._is_derby(out["home"], out["away"]).astype(int)

        # 6. "Intrascendente" (el gran sesgo del mercado)
        out["is_meaningless"] = (
            (out["is_season_end"] == 1) & 
            (out["home_in_relegation_battle"] == 0) & 
            (out["away_in_relegation_battle"] == 0) &
            (out["home_title_chase"] == 0)
        ).astype(int)

        # 7. Segunda división bonus (más impredecible)
        out["is_segunda"] = (out["division"] == "Segunda").astype(int)

        # 8. Market overconfidence proxy (dónde el mercado puede estar sesgado)
        out["market_confidence"] = out[["market_1", "market_x", "market_2"]].max(axis=1)
        out["market_entropy"] = out.get("market_entropy", 0)  # ya calculado antes

        return out

    def _motivation_score(self, pos: pd.Series, pts: pd.Series, ppg: pd.Series) -> pd.Series:
        """Score de motivación 0-1 basado en posición y ppg."""
        pos = pos.fillna(10)
        ppg = ppg.fillna(1.0)
        
        # Alta motivación si estás luchando por algo
        score = np.where(
            (pos <= 4) | (pos >= 17),  # título o descenso
            0.9 + (ppg - 1.2) * 0.1,
            np.where(
                (pos >= 5) & (pos <= 7),  # play-off
                0.75,
                0.4 + (ppg - 1.0) * 0.15   # medio tabla
            )
        )
        return np.clip(score, 0.1, 1.0)

    def _is_derby(self, home: pd.Series, away: pd.Series) -> pd.Series:
        """Heurística de derbis clásicos españoles."""
        derbies = {
            ("Real Madrid", "Barcelona"), ("Barcelona", "Real Madrid"),
            ("Real Madrid", "Atletico Madrid"), ("Atletico Madrid", "Real Madrid"),
            ("Barcelona", "Espanyol"), ("Espanyol", "Barcelona"),
            ("Ath Bilbao", "Real Sociedad"), ("Real Sociedad", "Ath Bilbao"),
            ("Sevilla", "Betis"), ("Betis", "Sevilla"),
            ("Valencia", "Villarreal"),  # semi
            ("Celta", "Deportivo"),  # histórico
        }
        pairs = set(zip(home.str.strip(), away.str.strip()))
        is_derby = [tuple(sorted(p)) in {(a,b) for a,b in derbies} for p in pairs]
        return pd.Series(is_derby, index=home.index)

    def detect_value_context(self, row: pd.Series) -> Dict[str, Any]:
        """
        Detecta si este partido es un candidato a 'value contextual'.
        Devuelve señales para el decision engine.
        """
        signals = []
        value_boost = 0.0

        if row.get("is_meaningless", 0) == 1:
            signals.append("partido_intrascendente")
            value_boost += 0.08   # el mercado sobreestima favoritos aquí

        if row.get("is_derby", 0) == 1:
            signals.append("derbi")
            value_boost += 0.05   # emoción rompe stats

        if row.get("both_fatigued", 0) == 1 and row.get("is_season_end", 0) == 0:
            signals.append("fatiga_doble")
            value_boost += 0.04

        if row.get("high_pressure_match", 0) == 1:
            signals.append("presion_maxima")
            value_boost += 0.06

        if row.get("is_segunda", 0) == 1 and row.get("market_confidence", 0.65) > 0.72:
            signals.append("segunda_sorpresas")
            value_boost += 0.07

        # Señal de divergencia contextual (donde el mercado puede estar equivocado)
        market_fav = max(row.get("market_1", 0), row.get("market_x", 0), row.get("market_2", 0))
        if market_fav > 0.78 and row.get("is_meaningless", 0):
            signals.append("favorito_sobrevalorado_fin_temporada")
            value_boost += 0.10

        return {
            "context_signals": signals,
            "context_value_boost": round(value_boost, 4),
            "is_chaos_candidate": len(signals) >= 2 or value_boost > 0.12
        }

    def generate_context_ensemble_adjustment(self, probs: np.ndarray, context: Dict) -> np.ndarray:
        """
        Ajusta las probabilidades 1X2 según contexto.
        Muy conservador: solo aplica boost pequeño.
        """
        if not context.get("context_signals"):
            return probs

        adj = probs.copy()
        boost = context.get("context_value_boost", 0.0)

        # En partidos intrascendentes: empujar ligeramente hacia el empate o el underdog
        if "partido_intrascendente" in context.get("context_signals", []):
            # Suavizar el favorito
            fav_idx = np.argmax(adj)
            adj[fav_idx] = adj[fav_idx] * (1 - boost * 0.6)
            adj = adj / adj.sum()

        # En derbis o presión: aumentar ligeramente la entropía
        if "derbi" in context.get("context_signals", []) or "presion_maxima" in context.get("context_signals", []):
            adj = adj * 0.96 + (np.ones(3) / 3) * 0.04
            adj = adj / adj.sum()

        return np.clip(adj, 0.05, 0.9)


# Helper para integrar fácilmente
def add_context_to_features(features_df: pd.DataFrame) -> pd.DataFrame:
    engine = ContextEngine()
    return engine.compute_context_features(features_df)


# ==================== INTEGRACIÓN CON VIVENCIA (RECONSTRUCCIÓN DE LIGA) ====================

try:
    from scripts.motor.vivencia import LeagueVivenciaReconstructor
except ImportError:
    LeagueVivenciaReconstructor = None

def add_vivencia_to_features(features_df: pd.DataFrame, 
                             history_df: Optional[pd.DataFrame] = None,
                             cutoff: Optional[str] = None) -> pd.DataFrame:
    """
    Enriquece el DataFrame con la 'vivencia' completa de la liga en ese momento.
    Esto es lo que el usuario pidió: reconstruir quién lideraba, gaps, objetivos,
    six-pointers, fatiga real, fase de temporada, etc.

    Requiere haber procesado el histórico hasta la fecha de corte.
    """
    if history_df is None or cutoff is None:
        # Modo ligero: usa solo lo que ya hay en features
        engine = ContextEngine()
        out = engine.compute_context_features(features_df)
        # Añadimos flags básicos de vivencia
        out["vivencia_is_high_stakes"] = out.get("high_pressure_match", 0)
        out["vivencia_season_phase"] = np.where(
            out.get("is_season_end", 0) == 1, "dead_rubber", "mid"
        )
        return out

    recon = LeagueVivenciaReconstructor()
    recon.process_up_to(history_df, cutoff)

    enriched = recon.enrich_dataframe_with_vivencia(features_df)

    # --- PATCH: inject table columns from vivencia snapshots (if present) ---
    if "home_table_snapshot" in enriched.columns:
        for idx, row in enriched.iterrows():
            try:
                h_snap = row.get("home_table_snapshot") or {}
                a_snap = row.get("away_table_snapshot") or {}
                enriched.loc[idx, "home_table_pos"] = row.get("viv_home_pos", h_snap.get("pos", 12))
                enriched.loc[idx, "away_table_pos"] = row.get("viv_away_pos", a_snap.get("pos", 12))
                enriched.loc[idx, "home_table_pts"] = row.get("viv_home_pts", h_snap.get("pts", 40))
                enriched.loc[idx, "away_table_pts"] = row.get("viv_away_pts", a_snap.get("pts", 40))
                enriched.loc[idx, "home_table_ppg"] = h_snap.get("pts", 40) / max(h_snap.get("pj", 20), 1)
                enriched.loc[idx, "away_table_ppg"] = a_snap.get("pts", 40) / max(a_snap.get("pj", 20), 1)
            except Exception:
                pass
    # --- end patch ---

    # Fusionamos con el contexto clásico
    engine = ContextEngine()
    enriched = engine.compute_context_features(enriched)

    # Flags muy potentes para el modelo (safe access)
    if "vivencia_high_stakes" not in enriched.columns:
        enriched["vivencia_high_stakes"] = enriched.get("high_pressure_match", 0).astype(int)
    else:
        enriched["vivencia_high_stakes"] = enriched["vivencia_high_stakes"].astype(int)

    if "vivencia_is_six_pointer" not in enriched.columns:
        enriched["vivencia_is_six_pointer"] = 0
    enriched["vivencia_is_six_pointer"] = enriched.get("vivencia_is_six_pointer", 0).astype(int)

    # Safe nothing match
    home_target = enriched.get("vivencia_home_target", pd.Series([""] * len(enriched)))
    away_target = enriched.get("vivencia_away_target", pd.Series([""] * len(enriched)))
    enriched["vivencia_nothing_match"] = ((home_target == "nothing") & (away_target == "nothing")).astype(int)

    # Also inject raw vivencia numeric fields if missing (for models)
    for col in ["viv_home_pos", "viv_home_momentum", "viv_home_is_hot", "viv_home_win_streak", "viv_home_gd"]:
        if col not in enriched.columns:
            enriched[col] = 0

    return enriched


def get_vivencia_for_match(home: str, away: str, date: str, 
                           division: str, season: str,
                           history_df: pd.DataFrame, cutoff: str) -> Dict[str, Any]:
    """Devuelve el snapshot rico de vivencia para un partido concreto (útil para reportes)."""
    recon = LeagueVivenciaReconstructor()
    recon.process_up_to(history_df, cutoff)
    snap = recon.get_vivencia(home, away, date, division, season)
    return asdict(snap)


if __name__ == "__main__":
    print("ContextEngine ready. Multiverso activado.")
