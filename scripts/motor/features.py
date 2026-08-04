"""Módulo con la lógica central de cálculo de estado de equipos y features del motor.

Proporciona tanto el cálculo rodante para histórico (`rolling_team_features`)
como la extracción point-in-time para partidos futuros (`compute_features_for_upcoming`),
compartiendo una única arquitectura de cálculo de estado sin fuga temporal.

Sin fuga temporal entre partidos de la misma fecha: las features de todos los
partidos de una fecha se extraen antes de aplicar los resultados de esa fecha
al estado (por lotes por fecha), de modo que ningún partido ve resultados,
Elo, forma, tabla o descanso de otros partidos disputados el mismo día.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import poisson

import settings
from scripts.motor.dixon_coles import dc_1x2 as dixon_coles_1x2
from scripts.motor.team_names import resolve_history_name

LABEL_MAP = {"1": 0, "X": 1, "2": 2}


def safe_pair_mean(a: float, b: float) -> float:
    """Calcula la media de un par de valores omitiendo NaNs."""
    values = [v for v in (a, b) if not np.isnan(v)]
    if not values:
        return np.nan
    return float(np.mean(values))


def poisson_1x2(
    lambda_home: float, lambda_away: float, max_goals: int = 7
) -> tuple[float, float, float]:
    """Calcula probabilidades 1, X, 2 mediante el modelo de Poisson independiente."""
    if np.isnan(lambda_home) or np.isnan(lambda_away):
        return (np.nan, np.nan, np.nan)
    p1 = px = p2 = 0.0
    for hg in range(max_goals + 1):
        for ag in range(max_goals + 1):
            prob = poisson.pmf(hg, lambda_home) * poisson.pmf(ag, lambda_away)
            if hg > ag:
                p1 += prob
            elif hg == ag:
                px += prob
            else:
                p2 += prob
    total = p1 + px + p2
    if total <= 0:
        return (np.nan, np.nan, np.nan)
    return (p1 / total, px / total, p2 / total)


def dc_poisson_1x2(
    lambda_home: float, lambda_away: float, rho: float = -0.036, max_goals: int = 7
) -> tuple[float, float, float]:
    """Probabilidades 1/X/2 con Dixon-Coles (rho corrige marcadores bajos).

    Si lambda es NaN, devuelve NaN. Si rho == 0, equivale al Poisson independiente.
    """
    if np.isnan(lambda_home) or np.isnan(lambda_away):
        return (np.nan, np.nan, np.nan)
    try:
        probs = dixon_coles_1x2([lambda_home], [lambda_away], rho, max_goals)
        if probs.shape[0] == 0:
            return poisson_1x2(lambda_home, lambda_away, max_goals)
        p1, px, p2 = probs[0]
        return (float(p1), float(px), float(p2))
    except Exception:
        # Fallback a Poisson independiente si falla DC
        return poisson_1x2(lambda_home, lambda_away, max_goals)


def implied_probabilities(
    df: pd.DataFrame, prefix: str, cols: list[str]
) -> pd.DataFrame:
    """Convierte columnas de cuotas decimales en probabilidades implícitas normalizadas."""
    if df.empty:
        out = df.copy()
        out[f"{prefix}_1"] = pd.Series(dtype=float)
        out[f"{prefix}_x"] = pd.Series(dtype=float)
        out[f"{prefix}_2"] = pd.Series(dtype=float)
        return out
    odds = df[cols].replace(0, np.nan)
    inv = 1 / odds
    margin = inv.sum(axis=1)
    df[f"{prefix}_1"] = inv[cols[0]] / margin
    df[f"{prefix}_x"] = inv[cols[1]] / margin
    df[f"{prefix}_2"] = inv[cols[2]] / margin
    return df


def infer_season(dt: object) -> str:
    """Infiere la temporada futbolística española (ej. '2025-2026') a partir de una fecha."""
    ts = pd.to_datetime(dt, errors="coerce")
    if pd.isna(ts):
        return "2025-2026"
    year = int(ts.year)
    if ts.month >= 7:
        return f"{year}-{year + 1}"
    return f"{year - 1}-{year}"


def get_expected_columns() -> list[str]:
    """Devuelve la lista ordenada completa de columnas generadas en el DataFrame de features."""
    return [
        "date",
        "home",
        "away",
        "division",
        "division_code",
        "season",
        "source_file",
        "odd_1",
        "odd_x",
        "odd_2",
        "open_odd_1",
        "open_odd_x",
        "open_odd_2",
        "FTHG",
        "FTAG",
        "result",
        "home_form_pts_5",
        "away_form_pts_5",
        "home_gf_5",
        "home_ga_5",
        "away_gf_5",
        "away_ga_5",
        "home_home_pts_5",
        "away_away_pts_5",
        "home_elo",
        "away_elo",
        "elo_diff",
        "poisson_1",
        "poisson_x",
        "poisson_2",
        "lambda_home",
        "lambda_away",
        "home_shots_5",
        "away_shots_5",
        "home_shots_against_5",
        "away_shots_against_5",
        "home_sot_5",
        "away_sot_5",
        "home_sot_against_5",
        "away_sot_against_5",
        "home_table_pos",
        "away_table_pos",
        "table_pos_diff",
        "home_table_pj",
        "away_table_pj",
        "home_table_pts",
        "away_table_pts",
        "table_pts_diff",
        "home_table_ppg",
        "away_table_ppg",
        "table_ppg_diff",
        "home_table_gf",
        "away_table_gf",
        "home_table_ga",
        "away_table_ga",
        "home_table_gd",
        "away_table_gd",
        "table_gf_diff",
        "table_ga_diff",
        "table_gd_diff",
        "days_rest_home",
        "days_rest_away",
        "days_rest_diff",
        "market_1",
        "market_x",
        "market_2",
        "open_market_1",
        "open_market_x",
        "open_market_2",
        "form_pts_diff",
        "goal_for_diff",
        "goal_against_diff",
        "venue_form_diff",
        "shots_diff",
        "shots_against_diff",
        "sot_diff",
        "sot_against_diff",
        "home_xg_5",
        "away_xg_5",
        "home_xg_against_5",
        "away_xg_against_5",
        "xg_for_diff",
        "xg_against_diff",
        "market_move_1",
        "market_move_x",
        "market_move_2",
        "market_entropy",
        "close_open_fav_gap",
    ]


def finalize_feature_dataframe(feat_df: pd.DataFrame) -> pd.DataFrame:
    """Completa un DataFrame de features con probabilidades implícitas y diferencias."""
    if feat_df.empty:
        out = feat_df.copy()
        for col in get_expected_columns():
            if col not in out.columns:
                out[col] = pd.Series(dtype=float)
        return out[get_expected_columns()]

    out = feat_df.copy()
    out = implied_probabilities(out, "market", ["odd_1", "odd_x", "odd_2"])
    out = implied_probabilities(
        out, "open_market", ["open_odd_1", "open_odd_x", "open_odd_2"]
    )
    out["form_pts_diff"] = out["home_form_pts_5"] - out["away_form_pts_5"]
    out["goal_for_diff"] = out["home_gf_5"] - out["away_gf_5"]
    out["goal_against_diff"] = out["away_ga_5"] - out["home_ga_5"]
    out["venue_form_diff"] = out["home_home_pts_5"] - out["away_away_pts_5"]
    out["shots_diff"] = out["home_shots_5"] - out["away_shots_5"]
    out["shots_against_diff"] = (
        out["away_shots_against_5"] - out["home_shots_against_5"]
    )
    out["sot_diff"] = out["home_sot_5"] - out["away_sot_5"]
    out["sot_against_diff"] = (
        out["away_sot_against_5"] - out["home_sot_against_5"]
    )
    out["xg_for_diff"] = out["home_xg_5"] - out["away_xg_5"]
    out["xg_against_diff"] = (
        out["away_xg_against_5"] - out["home_xg_against_5"]
    )
    out["market_move_1"] = out["market_1"] - out["open_market_1"]
    out["market_move_x"] = out["market_x"] - out["open_market_x"]
    out["market_move_2"] = out["market_2"] - out["open_market_2"]
    out["market_entropy"] = -(
        out["market_1"] * np.log(out["market_1"])
        + out["market_x"] * np.log(out["market_x"])
        + out["market_2"] * np.log(out["market_2"])
    )
    out["close_open_fav_gap"] = out[
        ["market_1", "market_x", "market_2"]
    ].max(axis=1) - out[
        ["open_market_1", "open_market_x", "open_market_2"]
    ].max(
        axis=1
    )
    return out[get_expected_columns()]


class TeamStateTracker:
    """Motor de cálculo de estado de equipos (Elo, forma, goles, tiros, clasificación y descanso)."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.team_state: dict[str, dict[str, Any]] = {}
        self.standings_state: dict[
            tuple[str, str], dict[str, dict[str, float]]
        ] = {}
        self.team_divisions: dict[str, str] = {}
        master_config = (
            config if config is not None else settings.master_model_config()
        )
        self.base_elo = float(master_config.get("elo_base", 1500.0))
        self.k_factor = float(master_config.get("elo_k_factor", 24.0))
        self.home_advantage = float(master_config.get("elo_home_advantage", 55.0))
        self.goal_per_sot = float(master_config.get("goal_per_sot", 0.30))
        # T4: Dixon-Coles config
        dc_cfg = master_config.get("dixon_coles", {}) if isinstance(master_config.get("dixon_coles"), dict) else {}
        self.dc_enabled = bool(dc_cfg.get("enabled", True))
        self.dc_rho = float(dc_cfg.get("rho", -0.036))
        self.dc_max_goals = int(dc_cfg.get("max_goals", 7))
        self.dc_use_for_ensemble = bool(dc_cfg.get("use_for_ensemble", False))
        self.dc_use_for_pleno = bool(dc_cfg.get("use_for_pleno", True))

    def ensure_team(self, team: str) -> dict[str, Any]:
        """Asegura la inicialización de la estructura de historial y Elo de un equipo."""
        if team not in self.team_state:
            self.team_state[team] = {
                "gf": [],
                "ga": [],
                "pts": [],
                "home_pts": [],
                "away_pts": [],
                "shots": [],
                "shots_against": [],
                "sot": [],
                "sot_against": [],
                "xg": [],
                "xg_against": [],
                "elo": self.base_elo,
                "last_date": None,
            }
        return self.team_state[team]

    def ensure_standing(
        self, division: str, season: str, team: str
    ) -> dict[str, float]:
        """Asegura la inicialización de la tabla de clasificación para temporada y división."""
        key = (division, season)
        if key not in self.standings_state:
            self.standings_state[key] = {}
        table = self.standings_state[key]
        if team not in table:
            table[team] = {
                "pj": 0.0,
                "pts": 0.0,
                "pg": 0.0,
                "pe": 0.0,
                "pp": 0.0,
                "gf": 0.0,
                "ga": 0.0,
            }
        return table[team]

    def standing_positions(
        self, division: str, season: str
    ) -> dict[str, int]:
        """Calcula el puesto numérico en la tabla para la temporada y división dadas."""
        table = self.standings_state.get((division, season), {})
        ordered = sorted(
            table.items(),
            key=lambda item: (
                -item[1]["pts"],
                -(item[1]["gf"] - item[1]["ga"]),
                -item[1]["gf"],
                item[0],
            ),
        )
        return {team: idx + 1 for idx, (team, _) in enumerate(ordered)}

    def ppg(self, stats: dict[str, float]) -> float:
        """Puntos por partido jugados en temporada actual."""
        return float(stats["pts"] / stats["pj"]) if stats["pj"] else np.nan

    def avg_last(self, values: list[float], n: int = 5) -> float:
        """Calcula la media móvil de las últimas n apariciones."""
        if not values:
            return np.nan
        return float(np.mean(values[-n:]))

    def update_standing(
        self, stats: dict[str, float], gf: int, ga: int, pts: int
    ) -> None:
        """Actualiza la tabla de clasificación de un equipo en la temporada en curso."""
        stats["pj"] += 1.0
        stats["pts"] += float(pts)
        stats["gf"] += float(gf)
        stats["ga"] += float(ga)
        if pts == 3:
            stats["pg"] += 1.0
        elif pts == 1:
            stats["pe"] += 1.0
        else:
            stats["pp"] += 1.0

    def extract_match_features(
        self, row: dict[str, Any] | pd.Series, is_upcoming: bool = False
    ) -> dict[str, Any]:
        """Extrae el diccionario completo de features previas al partido (solo lectura del estado)."""
        home = str(row["home"]).strip()
        away = str(row["away"]).strip()
        division = str(row["division"]).strip()
        season = str(row["season"]).strip()

        home_hist = self.ensure_team(home)
        away_hist = self.ensure_team(away)
        home_elo = float(home_hist["elo"])
        away_elo = float(away_hist["elo"])
        home_table = self.ensure_standing(division, season, home)
        away_table = self.ensure_standing(division, season, away)
        positions = self.standing_positions(division, season)
        home_pos = positions.get(home, np.nan)
        away_pos = positions.get(away, np.nan)
        home_gd = home_table["gf"] - home_table["ga"]
        away_gd = away_table["gf"] - away_table["ga"]
        home_ppg = self.ppg(home_table)
        away_ppg = self.ppg(away_table)

        home_gf = self.avg_last(home_hist["gf"])
        away_ga = self.avg_last(away_hist["ga"])
        away_gf = self.avg_last(away_hist["gf"])
        home_ga = self.avg_last(home_hist["ga"])
        home_sot = self.avg_last(home_hist["sot"])
        away_sot_against = self.avg_last(away_hist["sot_against"])
        away_sot = self.avg_last(away_hist["sot"])
        home_sot_against = self.avg_last(home_hist["sot_against"])

        lambda_home = safe_pair_mean(home_gf, away_ga)
        lambda_away = safe_pair_mean(away_gf, home_ga)
        shot_lambda_home = safe_pair_mean(home_sot, away_sot_against)
        shot_lambda_away = safe_pair_mean(away_sot, home_sot_against)

        if not np.isnan(shot_lambda_home):
            lambda_home = safe_pair_mean(
                lambda_home, shot_lambda_home * self.goal_per_sot
            )
        if not np.isnan(shot_lambda_away):
            lambda_away = safe_pair_mean(
                lambda_away, shot_lambda_away * self.goal_per_sot
            )

        # Poisson independiente por defecto
        poi_1, poi_x, poi_2 = poisson_1x2(lambda_home, lambda_away, max_goals=self.dc_max_goals)

        # T4: si está habilitado el uso de DC para el ensemble, sobrescribir poisson con DC
        if self.dc_enabled and self.dc_use_for_ensemble:
            dc_p1, dc_px, dc_p2 = dc_poisson_1x2(
                lambda_home, lambda_away, rho=self.dc_rho, max_goals=self.dc_max_goals
            )
            # Solo sobrescribir si DC produce valores válidos
            if not (np.isnan(dc_p1) or np.isnan(dc_px) or np.isnan(dc_p2)):
                poi_1, poi_x, poi_2 = dc_p1, dc_px, dc_p2

        home_shots = self.avg_last(home_hist["shots"])
        away_shots = self.avg_last(away_hist["shots"])
        home_shots_against = self.avg_last(home_hist["shots_against"])
        away_shots_against = self.avg_last(away_hist["shots_against"])

        home_xg = self.avg_last(home_hist["xg"])
        away_xg = self.avg_last(away_hist["xg"])
        home_xg_against = self.avg_last(home_hist["xg_against"])
        away_xg_against = self.avg_last(away_hist["xg_against"])

        last_date_home = home_hist["last_date"]
        last_date_away = away_hist["last_date"]
        days_rest_home = (
            float((pd.to_datetime(row["date"]) - pd.to_datetime(last_date_home)).days)
            if last_date_home is not None
            else np.nan
        )
        days_rest_away = (
            float((pd.to_datetime(row["date"]) - pd.to_datetime(last_date_away)).days)
            if last_date_away is not None
            else np.nan
        )
        days_rest_diff = (
            days_rest_home - days_rest_away
            if pd.notna(days_rest_home) and pd.notna(days_rest_away)
            else np.nan
        )

        return {
            "date": row["date"],
            "home": home,
            "away": away,
            "division": division,
            "division_code": row["division_code"],
            "season": season,
            "source_file": row["source_file"],
            "odd_1": row["odd_1"],
            "odd_x": row["odd_x"],
            "odd_2": row["odd_2"],
            "open_odd_1": row["open_odd_1"],
            "open_odd_x": row["open_odd_x"],
            "open_odd_2": row["open_odd_2"],
            "FTHG": row.get("FTHG", np.nan),
            "FTAG": row.get("FTAG", np.nan),
            "result": row.get("result", np.nan),
            "home_form_pts_5": self.avg_last(home_hist["pts"]),
            "away_form_pts_5": self.avg_last(away_hist["pts"]),
            "home_gf_5": home_gf,
            "home_ga_5": home_ga,
            "away_gf_5": away_gf,
            "away_ga_5": away_ga,
            "home_home_pts_5": self.avg_last(home_hist["home_pts"]),
            "away_away_pts_5": self.avg_last(away_hist["away_pts"]),
            "home_elo": home_elo,
            "away_elo": away_elo,
            "elo_diff": (home_elo + self.home_advantage) - away_elo,
            "poisson_1": poi_1,
            "poisson_x": poi_x,
            "poisson_2": poi_2,
            "lambda_home": lambda_home,
            "lambda_away": lambda_away,
            "home_shots_5": home_shots,
            "away_shots_5": away_shots,
            "home_shots_against_5": home_shots_against,
            "away_shots_against_5": away_shots_against,
            "home_sot_5": home_sot,
            "away_sot_5": away_sot,
            "home_sot_against_5": home_sot_against,
            "away_sot_against_5": away_sot_against,
            "home_xg_5": home_xg,
            "away_xg_5": away_xg,
            "home_xg_against_5": home_xg_against,
            "away_xg_against_5": away_xg_against,
            "home_table_pos": home_pos,
            "away_table_pos": away_pos,
            "table_pos_diff": (
                away_pos - home_pos
                if pd.notna(home_pos) and pd.notna(away_pos)
                else np.nan
            ),
            "home_table_pj": home_table["pj"],
            "away_table_pj": away_table["pj"],
            "home_table_pts": home_table["pts"],
            "away_table_pts": away_table["pts"],
            "table_pts_diff": home_table["pts"] - away_table["pts"],
            "home_table_ppg": home_ppg,
            "away_table_ppg": away_ppg,
            "table_ppg_diff": (
                home_ppg - away_ppg
                if pd.notna(home_ppg) and pd.notna(away_ppg)
                else np.nan
            ),
            "home_table_gf": home_table["gf"],
            "away_table_gf": away_table["gf"],
            "home_table_ga": home_table["ga"],
            "away_table_ga": away_table["ga"],
            "home_table_gd": home_gd,
            "away_table_gd": away_gd,
            "table_gf_diff": home_table["gf"] - away_table["gf"],
            "table_ga_diff": away_table["ga"] - home_table["ga"],
            "table_gd_diff": home_gd - away_gd,
            "days_rest_home": days_rest_home,
            "days_rest_away": days_rest_away,
            "days_rest_diff": days_rest_diff,
        }

    def update_match(self, row: dict[str, Any] | pd.Series) -> None:
        """Actualiza el estado interno posterior a la disputa de un partido con resultado."""
        result = row.get("result")
        fthg = row.get("FTHG")
        ftag = row.get("FTAG")
        if pd.isna(result) or pd.isna(fthg) or pd.isna(ftag):
            return

        home = str(row["home"]).strip()
        away = str(row["away"]).strip()
        division = str(row["division"]).strip()
        season = str(row["season"]).strip()
        self.team_divisions[home] = division
        self.team_divisions[away] = division

        home_hist = self.ensure_team(home)
        away_hist = self.ensure_team(away)
        home_elo = float(home_hist["elo"])
        away_elo = float(away_hist["elo"])
        home_table = self.ensure_standing(division, season, home)
        away_table = self.ensure_standing(division, season, away)

        hg = int(fthg)
        ag = int(ftag)
        hs = (
            float(row["HS"])
            if "HS" in row and pd.notna(row.get("HS"))
            else np.nan
        )
        ass = (
            float(row["AS"])
            if "AS" in row and pd.notna(row.get("AS"))
            else np.nan
        )
        hst = (
            float(row["HST"])
            if "HST" in row and pd.notna(row.get("HST"))
            else np.nan
        )
        ast = (
            float(row["AST"])
            if "AST" in row and pd.notna(row.get("AST"))
            else np.nan
        )
        h_xg = (
            float(row["home_xg"])
            if "home_xg" in row and pd.notna(row.get("home_xg"))
            else np.nan
        )
        a_xg = (
            float(row["away_xg"])
            if "away_xg" in row and pd.notna(row.get("away_xg"))
            else np.nan
        )

        if result == "1":
            home_pts, away_pts = 3, 0
        elif result == "2":
            home_pts, away_pts = 0, 3
        else:
            home_pts = away_pts = 1

        home_hist["gf"].append(hg)
        home_hist["ga"].append(ag)
        home_hist["pts"].append(home_pts)
        home_hist["home_pts"].append(home_pts)
        home_hist["shots"].append(hs)
        home_hist["shots_against"].append(ass)
        home_hist["sot"].append(hst)
        home_hist["sot_against"].append(ast)
        home_hist["xg"].append(h_xg)
        home_hist["xg_against"].append(a_xg)

        away_hist["gf"].append(ag)
        away_hist["ga"].append(hg)
        away_hist["pts"].append(away_pts)
        away_hist["away_pts"].append(away_pts)
        away_hist["shots"].append(ass)
        away_hist["shots_against"].append(hs)
        away_hist["sot"].append(ast)
        away_hist["sot_against"].append(hst)
        away_hist["xg"].append(a_xg)
        away_hist["xg_against"].append(h_xg)

        expected_home = 1 / (
            1
            + 10
            ** ((away_elo - (home_elo + self.home_advantage)) / 400.0)
        )
        expected_away = 1.0 - expected_home
        if result == "1":
            score_home, score_away = 1.0, 0.0
        elif result == "2":
            score_home, score_away = 0.0, 1.0
        else:
            score_home = score_away = 0.5

        home_hist["elo"] = (
            home_elo + self.k_factor * (score_home - expected_home)
        )
        away_hist["elo"] = (
            away_elo + self.k_factor * (score_away - expected_away)
        )
        self.update_standing(home_table, hg, ag, home_pts)
        self.update_standing(away_table, ag, hg, away_pts)
        home_hist["last_date"] = row["date"]
        away_hist["last_date"] = row["date"]

    def process_history(
        self, history_df: pd.DataFrame, cutoff_date: object = None
    ) -> None:
        """Procesa cronológicamente un histórico de partidos hasta la fecha de corte.

        Sin fuga temporal entre partidos de la misma fecha: primero se
        actualizan todos los partidos de una fecha con el estado previo a esa
        fecha, y solo después se aplican sus resultados al estado. Ningún
        partido ve resultados de otros partidos disputados el mismo día.
        """
        df = history_df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        if cutoff_date is not None:
            cutoff_ts = pd.to_datetime(cutoff_date, errors="coerce")
            df = df[df["date"] < cutoff_ts]
        df = df[df["result"].astype(str).isin({"1", "X", "2", "0", "1", "2"})].copy()
        df = df.sort_values(["date", "division", "home", "away"]).reset_index(
            drop=True
        )
        for _, group in df.groupby("date", sort=False):
            for _, row in group.iterrows():
                self.update_match(row)

    def normalize_upcoming_match(
        self, match: dict[str, Any], cutoff_date: object
    ) -> dict[str, Any]:
        """Normaliza un diccionario de partido futuro para su extracción sin resultado.

        Traduce los nombres comunes de la jornada ("Athletic Club", "Málaga CF")
        a los nombres exactos del histórico ("Ath Bilbao", "Malaga") mediante el
        mapa controlado de scripts/motor/team_names.py. Lo no mapeado pasa intacto.
        """
        home = resolve_history_name(str(match.get("home") or match.get("local") or "").strip())
        away = resolve_history_name(str(match.get("away") or match.get("visitante") or "").strip())
        dt_val = match.get("date") or match.get("fecha") or cutoff_date
        dt = pd.to_datetime(dt_val, errors="coerce")
        if pd.isna(dt):
            dt = pd.to_datetime(cutoff_date, errors="coerce")
        division = match.get("division")
        if not division:
            division = (
                self.team_divisions.get(home)
                or self.team_divisions.get(away)
                or "Primera"
            )
        division = str(division).strip()
        season = match.get("season")
        if not season:
            season = infer_season(dt)
        season = str(season).strip()

        division_code_map = {"Primera": 0, "Segunda": 1}
        odd_1 = (
            float(match["odd_1"])
            if "odd_1" in match and pd.notna(match["odd_1"])
            else np.nan
        )
        odd_x = (
            float(match["odd_x"])
            if "odd_x" in match and pd.notna(match["odd_x"])
            else np.nan
        )
        odd_2 = (
            float(match["odd_2"])
            if "odd_2" in match and pd.notna(match["odd_2"])
            else np.nan
        )
        open_odd_1 = (
            float(match["open_odd_1"])
            if "open_odd_1" in match and pd.notna(match["open_odd_1"])
            else np.nan
        )
        open_odd_x = (
            float(match["open_odd_x"])
            if "open_odd_x" in match and pd.notna(match["open_odd_x"])
            else np.nan
        )
        open_odd_2 = (
            float(match["open_odd_2"])
            if "open_odd_2" in match and pd.notna(match["open_odd_2"])
            else np.nan
        )

        return {
            "date": dt,
            "home": home,
            "away": away,
            "division": division,
            "division_code": division_code_map.get(division, -1),
            "season": season,
            "source_file": str(match.get("source_file", "upcoming")),
            "odd_1": odd_1,
            "odd_x": odd_x,
            "odd_2": odd_2,
            "open_odd_1": open_odd_1,
            "open_odd_x": open_odd_x,
            "open_odd_2": open_odd_2,
            "FTHG": np.nan,
            "FTAG": np.nan,
            "result": np.nan,
        }


def rolling_team_features(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula las features evolutivas sobre un dataset histórico completo.

    Sin fuga temporal entre partidos de la misma fecha: las features de todos
    los partidos de una fecha se extraen con el estado previo a esa fecha, y
    solo después se aplican los resultados de esa fecha al estado. Así ningún
    partido utiliza información de otros partidos disputados el mismo día
    (resultados, Elo, forma, tabla o descanso).
    """
    df_sorted = df.copy()
    df_sorted = df_sorted.sort_values(
        ["date", "division", "home", "away"]
    ).reset_index(drop=True)
    tracker = TeamStateTracker()
    rows = []
    for _, group in df_sorted.groupby("date", sort=False):
        # 1) Extraer features de TODOS los partidos de la fecha con el estado
        #    anterior a la fecha (sin ver resultados del mismo día).
        for _, row in group.iterrows():
            feat = tracker.extract_match_features(row, is_upcoming=False)
            rows.append(feat)
        # 2) Aplicar después los resultados de la fecha al estado.
        for _, row in group.iterrows():
            tracker.update_match(row)
    feat_df = pd.DataFrame(rows)
    return finalize_feature_dataframe(feat_df)


ODDS_TIMESTAMP_FIELDS = ("odds_observed_at", "prediction_cutoff_at", "kickoff_at")


def validate_odds_timestamps(
    partidos: list[dict[str, Any]],
    *,
    fields: tuple[str, str, str] = ODDS_TIMESTAMP_FIELDS,
) -> dict:
    """Valida (opcional) la invariante temporal de las cuotas de cada partido:

        odds_observed_at <= prediction_cutoff_at < kickoff_at

    - `odds_observed_at`:    instante en que se observaron las cuotas usadas.
    - `prediction_cutoff_at`: instante de corte de la predicción (debe ser
      posterior o igual a la observación de cuotas y anterior al inicio).
    - `kickoff_at`:           inicio del partido.

    Cada partido debe declarar los tres timestamps en sus campos (por defecto
    `odds_observed_at`, `prediction_cutoff_at`, `kickoff_at`). Devuelve:

        {
            "ok": bool,
            "partidos_validados": int,
            "violaciones": [
                {"num": ..., "issues": [...], "timestamps": {...}}, ...
            ]
        }

    Un partido con timestamps ausentes o no parseables se considera violación.
    """
    if len(fields) != 3:
        raise ValueError(f"Se necesitan exactamente 3 campos de timestamp, recibidos: {fields}")
    odds_field, cutoff_field, kickoff_field = fields
    violations: list[dict[str, Any]] = []
    for match in partidos:
        num = match.get("num")
        timestamps = {f: match.get(f) for f in fields}
        issues: list[str] = []
        parsed: dict[str, pd.Timestamp] = {}
        for field, value in timestamps.items():
            if value is None or (isinstance(value, str) and not value.strip()):
                issues.append(f"{field}_ausente")
                continue
            ts = pd.to_datetime(value, errors="coerce")
            if pd.isna(ts):
                issues.append(f"{field}_invalido")
                continue
            parsed[field] = ts
        if issues:
            violations.append(
                {"num": num, "issues": issues, "timestamps": timestamps}
            )
            continue
        if parsed[odds_field] > parsed[cutoff_field]:
            issues.append("cuotas_observadas_despues_del_corte")
        if not (parsed[cutoff_field] < parsed[kickoff_field]):
            issues.append("corte_no_anterior_al_kickoff")
        if issues:
            violations.append(
                {"num": num, "issues": issues, "timestamps": timestamps}
            )
    validados = len(partidos) - len(violations)
    return {"ok": not violations, "partidos_validados": validados, "violaciones": violations}


def compute_features_for_upcoming(
    partidos: list[dict[str, Any]] | pd.DataFrame,
    history_df: pd.DataFrame,
    cutoff_date: object,
    *,
    check_odds_timestamps: bool = False,
) -> pd.DataFrame:
    """Construye las features previas a partidos futuros sin necesitar resultado ni fuga temporal.

    - Reutiliza exactamente la misma lógica de estado de `rolling_team_features`.
    - Solo utiliza los partidos de `history_df` con `date < cutoff_date`.
    - No modifica ni actualiza los estados rodantes entre los partidos futuros.
    - No requiere FTHG, FTAG, result ni cuotas Q15/LAE/APU.
    - Si `check_odds_timestamps=True`, valida la invariante opcional
      `odds_observed_at <= prediction_cutoff_at < kickoff_at` de cada partido
      y lanza ValueError si algún partido la incumple (o no la declara).
    """
    if check_odds_timestamps:
        if isinstance(partidos, pd.DataFrame):
            match_list_for_validation = partidos.to_dict("records")
        else:
            match_list_for_validation = list(partidos)
        report = validate_odds_timestamps(match_list_for_validation)
        if not report["ok"]:
            details = "; ".join(
                f"partido {v['num']}: {', '.join(v['issues'])}"
                for v in report["violaciones"]
            )
            raise ValueError(
                f"Validación de cuotas fallida "
                f"({len(report['violaciones'])}/{len(partidos)} partidos): {details}"
            )

    tracker = TeamStateTracker()
    tracker.process_history(history_df, cutoff_date=cutoff_date)

    if isinstance(partidos, pd.DataFrame):
        match_list = partidos.to_dict("records")
    else:
        match_list = list(partidos)

    rows = []
    for m in match_list:
        row = tracker.normalize_upcoming_match(m, cutoff_date=cutoff_date)
        feat = tracker.extract_match_features(row, is_upcoming=True)
        rows.append(feat)

    if not rows:
        return pd.DataFrame(columns=get_expected_columns())

    feat_df = pd.DataFrame(rows)
    return finalize_feature_dataframe(feat_df)
