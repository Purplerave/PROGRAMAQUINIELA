import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import poisson
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

import settings


ROOT = settings.QUINIELAS_ROOT
RAW_BASE = settings.RAW_BASE
OUT_DIR = settings.SALIDA_DIR

LABEL_MAP = {"1": 0, "X": 1, "2": 2}
DIVISION_LABELS = {"PRIMERA": "Primera", "SEGUNDA": "Segunda"}
DOUBLE_ORDER = {"1": 0, "X": 1, "2": 2}


def normalize_result(value: object) -> str | None:
    text = str(value).strip().upper()
    if text in {"H", "1", "0", "0.0"}:
        return "1"
    if text in {"D", "X", "1.0"}:
        return "X"
    if text in {"A", "2", "2.0"}:
        return "2"
    return None


def choose_odds(row: pd.Series, candidates: list[str]) -> float | None:
    for column in candidates:
        value = row.get(column)
        if pd.notna(value) and float(value) > 1.01:
            return float(value)
    return None


def season_from_filename(path: Path) -> str:
    stem = path.stem.split("_")[-1]
    if len(stem) == 4 and stem.isdigit():
        return f"20{stem[:2]}-20{stem[2:]}"
    return stem


SANITIZED_HISTORY = settings.DATOS_DIR / ".." / "salida" / "datos_limpios" / "historico_saneado.csv"


def load_raw_history(source: str = "original") -> pd.DataFrame:
    """Carga el histórico seleccionado con el mismo esquema del motor."""
    if source not in {"original", "saneado"}:
        raise ValueError(f"Fuente histórica no válida: {source}")
    if source == "saneado":
        if not SANITIZED_HISTORY.is_file():
            raise FileNotFoundError(
                f"No existe el histórico saneado: {SANITIZED_HISTORY}. "
                "Genérelo antes con scripts/datos/SANEAR_DATOS.py --confirm."
            )
        files = [(SANITIZED_HISTORY, None)]
    else:
        files = [
            (csv_path, division_name)
            for division_key, division_name in DIVISION_LABELS.items()
            for csv_path in sorted((RAW_BASE / division_key).glob("*.csv"))
        ]

    frames = []
    for csv_path, known_division in files:
        raw = pd.read_csv(csv_path)
        division_name = known_division or raw.get("division", pd.Series("Desconocida", index=raw.index))
        if isinstance(division_name, pd.Series):
            division_name = division_name.astype(str).str.strip()
        else:
            division_name = pd.Series(division_name, index=raw.index)
        unknown_divisions = sorted(set(division_name) - set(DIVISION_LABELS.values()))
        if unknown_divisions:
            raise ValueError(
                f"División desconocida en el histórico: {', '.join(unknown_divisions)}"
            )
        if raw.empty:
            continue
        frame = pd.DataFrame(
                {
                    "date": pd.to_datetime(raw["Date"], dayfirst=True, format="mixed", errors="coerce"),
                    "home": raw["HomeTeam"].astype(str).str.strip(),
                    "away": raw["AwayTeam"].astype(str).str.strip(),
                    "FTHG": pd.to_numeric(raw["FTHG"], errors="coerce"),
                    "FTAG": pd.to_numeric(raw["FTAG"], errors="coerce"),
                    "result": raw["FTR"].map(normalize_result),
                    "odd_1": raw.apply(lambda row: choose_odds(row, ["AvgCH", "AvgH", "B365CH", "B365H"]), axis=1),
                    "odd_x": raw.apply(lambda row: choose_odds(row, ["AvgCD", "AvgD", "B365CD", "B365D"]), axis=1),
                    "odd_2": raw.apply(lambda row: choose_odds(row, ["AvgCA", "AvgA", "B365CA", "B365A"]), axis=1),
                    "open_odd_1": raw.apply(lambda row: choose_odds(row, ["AvgH", "B365H"]), axis=1),
                    "open_odd_x": raw.apply(lambda row: choose_odds(row, ["AvgD", "B365D"]), axis=1),
                    "open_odd_2": raw.apply(lambda row: choose_odds(row, ["AvgA", "B365A"]), axis=1),
                    "HS": pd.to_numeric(raw.get("HS"), errors="coerce"),
                    "AS": pd.to_numeric(raw.get("AS"), errors="coerce"),
                    "HST": pd.to_numeric(raw.get("HST"), errors="coerce"),
                    "AST": pd.to_numeric(raw.get("AST"), errors="coerce"),
                    "division": division_name,
                    "division_code": division_name.map({"Primera": 0, "Segunda": 1}).fillna(-1),
                    "season": raw.get("_season", pd.Series(season_from_filename(csv_path), index=raw.index)),
                    "source_file": raw.get("_source_file", pd.Series(csv_path.name, index=raw.index)),
                }
            )
        frames.append(frame)

    if not frames:
        raise FileNotFoundError(f"No he encontrado CSVs en {RAW_BASE}")

    df = pd.concat(frames, ignore_index=True)
    df = df.dropna(
        subset=[
            "date",
            "home",
            "away",
            "FTHG",
            "FTAG",
            "odd_1",
            "odd_x",
            "odd_2",
            "open_odd_1",
            "open_odd_x",
            "open_odd_2",
            "result",
        ]
    )
    df["FTHG"] = df["FTHG"].astype(int)
    df["FTAG"] = df["FTAG"].astype(int)
    df = df[df["result"].isin(LABEL_MAP)].copy()
    return df.sort_values(["date", "division", "home", "away"]).reset_index(drop=True)


def implied_probabilities(df: pd.DataFrame, prefix: str, cols: list[str]) -> pd.DataFrame:
    odds = df[cols].replace(0, np.nan)
    inv = 1 / odds
    margin = inv.sum(axis=1)
    df[f"{prefix}_1"] = inv[cols[0]] / margin
    df[f"{prefix}_x"] = inv[cols[1]] / margin
    df[f"{prefix}_2"] = inv[cols[2]] / margin
    return df


def poisson_1x2(lambda_home: float, lambda_away: float, max_goals: int = 7) -> tuple[float, float, float]:
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


def top_scorelines(lambda_home: float, lambda_away: float, max_goals: int = 5, top_n: int = 3) -> list[dict]:
    if np.isnan(lambda_home) or np.isnan(lambda_away):
        return []
    scores = []
    for hg in range(max_goals + 1):
        for ag in range(max_goals + 1):
            prob = poisson.pmf(hg, lambda_home) * poisson.pmf(ag, lambda_away)
            scores.append({"score": f"{hg}-{ag}", "prob": float(prob)})
    scores.sort(key=lambda item: item["prob"], reverse=True)
    return scores[:top_n]


def safe_pair_mean(a: float, b: float) -> float:
    values = [v for v in (a, b) if not np.isnan(v)]
    if not values:
        return np.nan
    return float(np.mean(values))


def rolling_team_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.sort_values(["date", "division", "home", "away"]).reset_index(drop=True)

    team_state: dict[str, dict[str, list[float] | float]] = {}
    standings_state: dict[tuple[str, str], dict[str, dict[str, float]]] = {}
    rows = []
    master_config = settings.master_model_config()
    base_elo = float(master_config.get("elo_base", 1500.0))
    k_factor = float(master_config.get("elo_k_factor", 24.0))
    home_advantage = float(master_config.get("elo_home_advantage", 55.0))
    goal_per_sot = float(master_config.get("goal_per_sot", 0.30))

    def ensure_team(team: str) -> dict:
        if team not in team_state:
            team_state[team] = {
                "gf": [],
                "ga": [],
                "pts": [],
                "home_pts": [],
                "away_pts": [],
                "shots": [],
                "shots_against": [],
                "sot": [],
                "sot_against": [],
                "elo": base_elo,
                "last_date": None,
            }
        return team_state[team]

    def ensure_standing(division: str, season: str, team: str) -> dict[str, float]:
        key = (division, season)
        if key not in standings_state:
            standings_state[key] = {}
        table = standings_state[key]
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

    def standing_positions(division: str, season: str) -> dict[str, int]:
        table = standings_state.get((division, season), {})
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

    def ppg(stats: dict[str, float]) -> float:
        return float(stats["pts"] / stats["pj"]) if stats["pj"] else np.nan

    def update_standing(stats: dict[str, float], gf: int, ga: int, pts: int) -> None:
        stats["pj"] += 1
        stats["pts"] += pts
        stats["gf"] += gf
        stats["ga"] += ga
        if pts == 3:
            stats["pg"] += 1
        elif pts == 1:
            stats["pe"] += 1
        else:
            stats["pp"] += 1

    def avg_last(values: list[float], n: int = 5) -> float:
        if not values:
            return np.nan
        return float(np.mean(values[-n:]))

    for _, row in df.iterrows():
        home = row["home"]
        away = row["away"]
        home_hist = ensure_team(home)
        away_hist = ensure_team(away)
        home_elo = float(home_hist["elo"])
        away_elo = float(away_hist["elo"])
        home_table = ensure_standing(row["division"], row["season"], home)
        away_table = ensure_standing(row["division"], row["season"], away)
        positions = standing_positions(row["division"], row["season"])
        home_pos = positions.get(home, np.nan)
        away_pos = positions.get(away, np.nan)
        home_gd = home_table["gf"] - home_table["ga"]
        away_gd = away_table["gf"] - away_table["ga"]
        home_ppg = ppg(home_table)
        away_ppg = ppg(away_table)

        home_gf = avg_last(home_hist["gf"])
        away_ga = avg_last(away_hist["ga"])
        away_gf = avg_last(away_hist["gf"])
        home_ga = avg_last(home_hist["ga"])
        home_sot = avg_last(home_hist["sot"])
        away_sot_against = avg_last(away_hist["sot_against"])
        away_sot = avg_last(away_hist["sot"])
        home_sot_against = avg_last(home_hist["sot_against"])

        lambda_home = safe_pair_mean(home_gf, away_ga)
        lambda_away = safe_pair_mean(away_gf, home_ga)
        shot_lambda_home = safe_pair_mean(home_sot, away_sot_against)
        shot_lambda_away = safe_pair_mean(away_sot, home_sot_against)

        if not np.isnan(shot_lambda_home):
            lambda_home = safe_pair_mean(lambda_home, shot_lambda_home * goal_per_sot)
        if not np.isnan(shot_lambda_away):
            lambda_away = safe_pair_mean(lambda_away, shot_lambda_away * goal_per_sot)

        poi_1, poi_x, poi_2 = poisson_1x2(lambda_home, lambda_away)

        home_shots = avg_last(home_hist["shots"])
        away_shots = avg_last(away_hist["shots"])
        home_shots_against = avg_last(home_hist["shots_against"])
        away_shots_against = avg_last(away_hist["shots_against"])

        days_rest_home = float((row["date"] - home_hist["last_date"]).days) if home_hist["last_date"] is not None else np.nan
        days_rest_away = float((row["date"] - away_hist["last_date"]).days) if away_hist["last_date"] is not None else np.nan
        days_rest_diff = days_rest_home - days_rest_away if pd.notna(days_rest_home) and pd.notna(days_rest_away) else np.nan

        rows.append(
            {
                "date": row["date"],
                "home": home,
                "away": away,
                "division": row["division"],
                "division_code": row["division_code"],
                "season": row["season"],
                "source_file": row["source_file"],
                "odd_1": row["odd_1"],
                "odd_x": row["odd_x"],
                "odd_2": row["odd_2"],
                "open_odd_1": row["open_odd_1"],
                "open_odd_x": row["open_odd_x"],
                "open_odd_2": row["open_odd_2"],
                "FTHG": row["FTHG"],
                "FTAG": row["FTAG"],
                "result": row["result"],
                "home_form_pts_5": avg_last(home_hist["pts"]),
                "away_form_pts_5": avg_last(away_hist["pts"]),
                "home_gf_5": home_gf,
                "home_ga_5": home_ga,
                "away_gf_5": away_gf,
                "away_ga_5": away_ga,
                "home_home_pts_5": avg_last(home_hist["home_pts"]),
                "away_away_pts_5": avg_last(away_hist["away_pts"]),
                "home_elo": home_elo,
                "away_elo": away_elo,
                "elo_diff": (home_elo + home_advantage) - away_elo,
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
                "home_table_pos": home_pos,
                "away_table_pos": away_pos,
                "table_pos_diff": away_pos - home_pos if pd.notna(home_pos) and pd.notna(away_pos) else np.nan,
                "home_table_pj": home_table["pj"],
                "away_table_pj": away_table["pj"],
                "home_table_pts": home_table["pts"],
                "away_table_pts": away_table["pts"],
                "table_pts_diff": home_table["pts"] - away_table["pts"],
                "home_table_ppg": home_ppg,
                "away_table_ppg": away_ppg,
                "table_ppg_diff": home_ppg - away_ppg if pd.notna(home_ppg) and pd.notna(away_ppg) else np.nan,
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
        )

        hg = int(row["FTHG"])
        ag = int(row["FTAG"])
        hs = float(row["HS"]) if pd.notna(row["HS"]) else np.nan
        ass = float(row["AS"]) if pd.notna(row["AS"]) else np.nan
        hst = float(row["HST"]) if pd.notna(row["HST"]) else np.nan
        ast = float(row["AST"]) if pd.notna(row["AST"]) else np.nan

        if row["result"] == "1":
            home_pts, away_pts = 3, 0
        elif row["result"] == "2":
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

        away_hist["gf"].append(ag)
        away_hist["ga"].append(hg)
        away_hist["pts"].append(away_pts)
        away_hist["away_pts"].append(away_pts)
        away_hist["shots"].append(ass)
        away_hist["shots_against"].append(hs)
        away_hist["sot"].append(ast)
        away_hist["sot_against"].append(hst)

        expected_home = 1 / (1 + 10 ** ((away_elo - (home_elo + home_advantage)) / 400))
        expected_away = 1 - expected_home
        if row["result"] == "1":
            score_home, score_away = 1.0, 0.0
        elif row["result"] == "2":
            score_home, score_away = 0.0, 1.0
        else:
            score_home = score_away = 0.5
        home_hist["elo"] = home_elo + k_factor * (score_home - expected_home)
        away_hist["elo"] = away_elo + k_factor * (score_away - expected_away)
        update_standing(home_table, hg, ag, home_pts)
        update_standing(away_table, ag, hg, away_pts)
        home_hist["last_date"] = row["date"]
        away_hist["last_date"] = row["date"]

    feat_df = pd.DataFrame(rows)
    feat_df = implied_probabilities(feat_df, "market", ["odd_1", "odd_x", "odd_2"])
    feat_df = implied_probabilities(feat_df, "open_market", ["open_odd_1", "open_odd_x", "open_odd_2"])
    feat_df["form_pts_diff"] = feat_df["home_form_pts_5"] - feat_df["away_form_pts_5"]
    feat_df["goal_for_diff"] = feat_df["home_gf_5"] - feat_df["away_gf_5"]
    feat_df["goal_against_diff"] = feat_df["away_ga_5"] - feat_df["home_ga_5"]
    feat_df["venue_form_diff"] = feat_df["home_home_pts_5"] - feat_df["away_away_pts_5"]
    feat_df["shots_diff"] = feat_df["home_shots_5"] - feat_df["away_shots_5"]
    feat_df["shots_against_diff"] = feat_df["away_shots_against_5"] - feat_df["home_shots_against_5"]
    feat_df["sot_diff"] = feat_df["home_sot_5"] - feat_df["away_sot_5"]
    feat_df["sot_against_diff"] = feat_df["away_sot_against_5"] - feat_df["home_sot_against_5"]
    feat_df["market_move_1"] = feat_df["market_1"] - feat_df["open_market_1"]
    feat_df["market_move_x"] = feat_df["market_x"] - feat_df["open_market_x"]
    feat_df["market_move_2"] = feat_df["market_2"] - feat_df["open_market_2"]
    feat_df["market_entropy"] = -(
        feat_df["market_1"] * np.log(feat_df["market_1"])
        + feat_df["market_x"] * np.log(feat_df["market_x"])
        + feat_df["market_2"] * np.log(feat_df["market_2"])
    )
    feat_df["close_open_fav_gap"] = feat_df[["market_1", "market_x", "market_2"]].max(axis=1) - feat_df[
        ["open_market_1", "open_market_x", "open_market_2"]
    ].max(axis=1)
    return feat_df


def feature_columns() -> list[str]:
    return [
        "division_code",
        "odd_1",
        "odd_x",
        "odd_2",
        "open_odd_1",
        "open_odd_x",
        "open_odd_2",
        "market_1",
        "market_x",
        "market_2",
        "open_market_1",
        "open_market_x",
        "open_market_2",
        "market_move_1",
        "market_move_x",
        "market_move_2",
        "market_entropy",
        "close_open_fav_gap",
        "home_form_pts_5",
        "away_form_pts_5",
        "home_gf_5",
        "home_ga_5",
        "away_gf_5",
        "away_ga_5",
        "home_home_pts_5",
        "away_away_pts_5",
        "form_pts_diff",
        "goal_for_diff",
        "goal_against_diff",
        "venue_form_diff",
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
        "shots_diff",
        "shots_against_diff",
        "sot_diff",
        "sot_against_diff",
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
    ]


def build_logit_model() -> Pipeline:
    numeric_features = [column for column in feature_columns() if column != "division_code"]
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="median")),
                        ("scaler", StandardScaler()),
                    ]
                ),
                numeric_features,
            ),
            (
                "cat",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                ["division"],
            ),
        ]
    )
    model = LogisticRegression(max_iter=3500, class_weight="balanced", random_state=42)
    return Pipeline([("prep", preprocessor), ("model", model)])


def build_hgb_model() -> Pipeline:
    numeric_features = feature_columns()
    preprocessor = Pipeline([("imputer", SimpleImputer(strategy="median"))])
    master_config = settings.master_model_config()
    model = HistGradientBoostingClassifier(
        loss="log_loss",
        learning_rate=float(master_config.get("hgb_learning_rate", 0.06)),
        max_depth=int(master_config.get("hgb_max_depth", 6)),
        max_iter=int(master_config.get("hgb_max_iter", 300)),
        min_samples_leaf=int(master_config.get("hgb_min_samples_leaf", 30)),
        random_state=42,
    )
    return Pipeline([("prep", preprocessor), ("model", model)])


def predict_full_probs(model: Pipeline, frame: pd.DataFrame, columns: list[str]) -> np.ndarray:
    raw_probs = model.predict_proba(frame[columns])
    classes = model.named_steps["model"].classes_
    probs = np.zeros((len(frame), 3), dtype=float)
    for src_idx, class_id in enumerate(classes):
        probs[:, int(class_id)] = raw_probs[:, src_idx]
    return probs


def add_market_baseline(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    market_cols = out[["market_1", "market_x", "market_2"]].fillna(-1)
    out["favorite_market"] = market_cols.idxmax(axis=1).map(
        {"market_1": "1", "market_x": "X", "market_2": "2"}
    )
    out["favorite_market_hit"] = (out["favorite_market"] == out["result"]).astype(int)
    return out


def apply_hybrid_config(frame: pd.DataFrame, config: dict, prefix: str) -> pd.DataFrame:
    out = frame.copy()
    weights = config["weights"]
    draw_boost = config["draw_boost"]
    segunda_draw_boost = config["segunda_draw_boost"]

    out[f"{prefix}_prob_1"] = (
        weights["logit"] * out["logit_prob_1"]
        + weights["hgb"] * out["hgb_prob_1"]
        + weights["market"] * out["market_1"].fillna(0)
        + weights["poisson"] * out["poisson_1"].fillna(0)
    )
    out[f"{prefix}_prob_x"] = (
        weights["logit"] * out["logit_prob_x"]
        + weights["hgb"] * out["hgb_prob_x"]
        + weights["market"] * out["market_x"].fillna(0)
        + weights["poisson"] * out["poisson_x"].fillna(0)
    )
    out[f"{prefix}_prob_2"] = (
        weights["logit"] * out["logit_prob_2"]
        + weights["hgb"] * out["hgb_prob_2"]
        + weights["market"] * out["market_2"].fillna(0)
        + weights["poisson"] * out["poisson_2"].fillna(0)
    )

    out[f"{prefix}_prob_x"] = out[f"{prefix}_prob_x"] + draw_boost
    segunda_mask = out["division"].eq("Segunda")
    out.loc[segunda_mask, f"{prefix}_prob_x"] = out.loc[segunda_mask, f"{prefix}_prob_x"] + segunda_draw_boost

    total = out[[f"{prefix}_prob_1", f"{prefix}_prob_x", f"{prefix}_prob_2"]].sum(axis=1)
    out[f"{prefix}_prob_1"] = out[f"{prefix}_prob_1"] / total
    out[f"{prefix}_prob_x"] = out[f"{prefix}_prob_x"] / total
    out[f"{prefix}_prob_2"] = out[f"{prefix}_prob_2"] / total
    out[f"{prefix}_pred"] = out[[f"{prefix}_prob_1", f"{prefix}_prob_x", f"{prefix}_prob_2"]].idxmax(axis=1).map(
        {f"{prefix}_prob_1": "1", f"{prefix}_prob_x": "X", f"{prefix}_prob_2": "2"}
    )
    if config.get("x_disagreement_strategy") == "market_pick_only":
        x_disagree = out[f"{prefix}_pred"].eq("X") & out["favorite_market"].ne("X")
        out.loc[x_disagree, f"{prefix}_pred"] = out.loc[x_disagree, "favorite_market"]
    out[f"{prefix}_hit"] = (out[f"{prefix}_pred"] == out["result"]).astype(int)
    out["model_disagreement"] = (
        (out["logit_prob_1"] - out["hgb_prob_1"]).abs()
        + (out["logit_prob_x"] - out["hgb_prob_x"]).abs()
        + (out["logit_prob_2"] - out["hgb_prob_2"]).abs()
    ) / 3.0
    return out


def build_double(prob1: float, probx: float, prob2: float, draw_threshold: float) -> str:
    probs = {"1": prob1, "X": probx, "2": prob2}
    sorted_probs = sorted(probs.items(), key=lambda item: item[1], reverse=True)
    top_sign = sorted_probs[0][0]
    second_sign = sorted_probs[1][0]
    if probx >= draw_threshold:
        if top_sign == "1":
            return "1X"
        if top_sign == "2":
            return "X2"
    return "".join(sorted((top_sign, second_sign), key=lambda sign: DOUBLE_ORDER[sign]))


def simulate_doubles(frame: pd.DataFrame, pred_prefix: str, config: dict) -> pd.DataFrame:
    ordered = frame.sort_values(["date", "division", "home", "away"]).reset_index(drop=True).copy()
    ordered["double"] = [
        build_double(p1, px, p2, config["double_draw_threshold"])
        for p1, px, p2 in zip(
            ordered[f"{pred_prefix}_prob_1"],
            ordered[f"{pred_prefix}_prob_x"],
            ordered[f"{pred_prefix}_prob_2"],
        )
    ]
    confidence = ordered[[f"{pred_prefix}_prob_1", f"{pred_prefix}_prob_x", f"{pred_prefix}_prob_2"]].max(axis=1)
    score = (
        (1 - confidence)
        + config["double_draw_weight"] * ordered[f"{pred_prefix}_prob_x"]
        + config["double_disagreement_weight"] * ordered["model_disagreement"]
        + np.where(ordered["division"].eq("Segunda"), config["double_segunda_bonus"], 0.0)
    )
    ordered["double_value_score"] = score

    jornada_scores = []
    for start in range(0, len(ordered), 15):
        group = ordered.iloc[start:start + 15].copy()
        if len(group) < 15:
            continue
        double_idx = set(group.nlargest(3, "double_value_score").index.tolist())
        hits = 0
        for idx, row in group.iterrows():
            if idx in double_idx:
                if row["result"] in row["double"]:
                    hits += 1
            elif row[f"{pred_prefix}_pred"] == row["result"]:
                hits += 1
        jornada_scores.append({"ticket_idx": start // 15 + 1, "hits_3_dobles": hits})
    return pd.DataFrame(jornada_scores)


def evaluate_config(frame: pd.DataFrame, pred_prefix: str, config: dict) -> dict:
    working = apply_hybrid_config(frame, config, pred_prefix)
    doubles_df = simulate_doubles(working, pred_prefix, config)
    division_breakdown = {}
    for division, group in working.groupby("division"):
        division_breakdown[division] = {
            "matches": int(len(group)),
            "accuracy_simple": float(group[f"{pred_prefix}_hit"].mean()),
            "accuracy_market_favorite": float(group["favorite_market_hit"].mean()),
        }
    double_mean = float(doubles_df["hits_3_dobles"].mean()) if not doubles_df.empty else 0.0
    return {
        "predictions": working,
        "score": float(working[f"{pred_prefix}_hit"].mean()) + 0.017 * double_mean,
        "accuracy_simple": float(working[f"{pred_prefix}_hit"].mean()),
        "accuracy_market_favorite": float(working["favorite_market_hit"].mean()),
        "mean_hits_3_dobles": double_mean if not doubles_df.empty else None,
        "best_jornada_3_dobles": int(doubles_df["hits_3_dobles"].max()) if not doubles_df.empty else None,
        "avg_confidence": float(working[[f"{pred_prefix}_prob_1", f"{pred_prefix}_prob_x", f"{pred_prefix}_prob_2"]].max(axis=1).mean()),
        "accuracy_by_pick": {
            sign: float(working.loc[working[f"{pred_prefix}_pred"] == sign, f"{pred_prefix}_hit"].mean())
            if not working.loc[working[f"{pred_prefix}_pred"] == sign].empty
            else None
            for sign in ["1", "X", "2"]
        },
        "division_breakdown": division_breakdown,
    }


def optimize_hybrid_config(train: pd.DataFrame) -> tuple[Pipeline, Pipeline, dict]:
    split_idx = int(len(train) * 0.84)
    subtrain = train.iloc[:split_idx].copy()
    valid = train.iloc[split_idx:].copy()

    logit = build_logit_model()
    hgb = build_hgb_model()
    logit.fit(subtrain[feature_columns() + ["division"]], subtrain["target"])
    hgb.fit(subtrain[feature_columns()], subtrain["target"])

    valid_eval = add_market_baseline(valid)
    logit_probs = predict_full_probs(logit, valid, feature_columns() + ["division"])
    hgb_probs = predict_full_probs(hgb, valid, feature_columns())
    valid_eval["logit_prob_1"] = logit_probs[:, 0]
    valid_eval["logit_prob_x"] = logit_probs[:, 1]
    valid_eval["logit_prob_2"] = logit_probs[:, 2]
    valid_eval["hgb_prob_1"] = hgb_probs[:, 0]
    valid_eval["hgb_prob_x"] = hgb_probs[:, 1]
    valid_eval["hgb_prob_2"] = hgb_probs[:, 2]

    master_config = settings.master_model_config()
    default_weight_candidates = [
        {"logit": 0.35, "hgb": 0.00, "market": 0.45, "poisson": 0.20},
        {"logit": 0.25, "hgb": 0.25, "market": 0.35, "poisson": 0.15},
        {"logit": 0.30, "hgb": 0.20, "market": 0.30, "poisson": 0.20},
    ]
    config_weights = master_config.get("weights")
    weight_candidates = master_config.get("weight_candidates") or default_weight_candidates
    if isinstance(config_weights, dict) and config_weights not in weight_candidates:
        weight_candidates = [config_weights, *weight_candidates]
    draw_boosts = master_config.get("draw_boost_candidates", [master_config.get("draw_boost", 0.0)])
    segunda_draw_boosts = master_config.get("segunda_draw_boost_candidates", [master_config.get("segunda_draw_boost", 0.0)])
    double_draw_weights = master_config.get("double_draw_weight_candidates", [master_config.get("double_draw_weight", 0.70), 0.85])
    double_disagreement_weights = master_config.get("double_disagreement_weight_candidates", [master_config.get("double_disagreement_weight", 0.20)])
    double_segunda_bonus = master_config.get("double_segunda_bonus_candidates", [0.0, master_config.get("double_segunda_bonus", 0.05)])
    double_draw_thresholds = master_config.get("double_draw_threshold_candidates", [master_config.get("double_draw_threshold", 0.31)])
    x_disagreement_strategies = master_config.get(
        "x_disagreement_strategy_candidates",
        [master_config.get("x_disagreement_strategy", "none")],
    )

    best = None
    for weights, draw_boost, segunda_boost, double_weight, disagree_weight, segunda_bonus, draw_threshold, x_strategy in itertools.product(
        weight_candidates,
        draw_boosts,
        segunda_draw_boosts,
        double_draw_weights,
        double_disagreement_weights,
        double_segunda_bonus,
        double_draw_thresholds,
        x_disagreement_strategies,
    ):
        config = {
            "weights": weights,
            "draw_boost": draw_boost,
            "segunda_draw_boost": segunda_boost,
            "double_draw_weight": double_weight,
            "double_disagreement_weight": disagree_weight,
            "double_segunda_bonus": segunda_bonus,
            "double_draw_threshold": draw_threshold,
            "x_disagreement_strategy": x_strategy,
        }
        evaluation = evaluate_config(valid_eval, "opt", config)
        payload = {
            "config": config,
            "score": evaluation["score"],
            "accuracy_simple": evaluation["accuracy_simple"],
            "mean_hits_3_dobles": evaluation["mean_hits_3_dobles"],
        }
        if best is None or payload["score"] > best["score"]:
            best = payload

    final_logit = build_logit_model()
    final_hgb = build_hgb_model()
    final_logit.fit(train[feature_columns() + ["division"]], train["target"])
    final_hgb.fit(train[feature_columns()], train["target"])
    return final_logit, final_hgb, best["config"]


def add_pleno_al_15(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    top_scores = [
        top_scorelines(lh, la, max_goals=5, top_n=3)
        for lh, la in zip(out["lambda_home"], out["lambda_away"])
    ]
    out["pleno15_top_scores"] = [json.dumps(scores, ensure_ascii=False) for scores in top_scores]
    out["pleno15_marcador"] = [scores[0]["score"] if scores else None for scores in top_scores]
    out["pleno15_confianza"] = [scores[0]["prob"] if scores else None for scores in top_scores]
    out["pleno15_local_goles_esperados"] = out["lambda_home"]
    out["pleno15_visitante_goles_esperados"] = out["lambda_away"]
    return out


def summarize_results(frame: pd.DataFrame, pred_prefix: str, config: dict) -> dict:
    eval_result = evaluate_config(frame, pred_prefix, config)
    return {
        "accuracy_simple": eval_result["accuracy_simple"],
        "accuracy_market_favorite": eval_result["accuracy_market_favorite"],
        "avg_confidence": eval_result["avg_confidence"],
        "accuracy_by_pick": eval_result["accuracy_by_pick"],
        "mean_hits_3_dobles": eval_result["mean_hits_3_dobles"],
        "best_jornada_3_dobles": eval_result["best_jornada_3_dobles"],
        "division_breakdown": eval_result["division_breakdown"],
    }


def season_sort_key(season: object) -> tuple[int, str]:
    text = str(season)
    try:
        return (int(text.split("-")[0]), text)
    except ValueError:
        return (0, text)


def run_season_backtest(df: pd.DataFrame, target_season: str) -> tuple[pd.DataFrame, dict]:
    usable = df[df["result"].isin(LABEL_MAP)].copy()
    usable["target"] = usable["result"].map(LABEL_MAP)
    usable = usable.sort_values(["date", "division", "home", "away"]).reset_index(drop=True)
    seasons = sorted(usable["season"].dropna().unique().tolist(), key=season_sort_key)
    if target_season not in seasons:
        raise ValueError(f"No existe la temporada {target_season}. Disponibles: {seasons}")

    train_seasons = [season for season in seasons if season_sort_key(season) < season_sort_key(target_season)]
    if not train_seasons:
        raise ValueError(f"No hay temporadas anteriores para entrenar antes de {target_season}.")

    train = usable[usable["season"].isin(train_seasons)].copy()
    test = usable[usable["season"] == target_season].copy()
    if train.empty or test.empty:
        raise ValueError(f"No se puede hacer backtest de {target_season}: train={len(train)} test={len(test)}")

    logit, hgb, best_config = optimize_hybrid_config(train)
    test_eval = add_market_baseline(test)
    logit_probs = predict_full_probs(logit, test, feature_columns() + ["division"])
    hgb_probs = predict_full_probs(hgb, test, feature_columns())
    test_eval["logit_prob_1"] = logit_probs[:, 0]
    test_eval["logit_prob_x"] = logit_probs[:, 1]
    test_eval["logit_prob_2"] = logit_probs[:, 2]
    test_eval["hgb_prob_1"] = hgb_probs[:, 0]
    test_eval["hgb_prob_x"] = hgb_probs[:, 1]
    test_eval["hgb_prob_2"] = hgb_probs[:, 2]

    predictions = apply_hybrid_config(test_eval, best_config, "latest")
    predictions = add_pleno_al_15(predictions)
    metrics = {
        "season": target_season,
        "train_seasons": train_seasons,
        "dataset_matches": int(len(usable)),
        "train_matches": int(len(train)),
        "test_matches": int(len(test)),
        "test_date_from": str(test["date"].min().date()),
        "test_date_to": str(test["date"].max().date()),
        "divisions_test": {division: int(count) for division, count in test["division"].value_counts().sort_index().items()},
        "best_config": best_config,
        "latest_season_model": summarize_results(test_eval, "latest", best_config),
    }
    return predictions, metrics


def run_latest_season_backtest(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    usable = df[df["result"].isin(LABEL_MAP)].copy()
    seasons = sorted(usable["season"].dropna().unique().tolist(), key=season_sort_key)
    if len(seasons) < 2:
        raise ValueError("No hay temporadas suficientes para separar entrenamiento y última temporada.")
    return run_season_backtest(df, seasons[-1])


def run_backtest(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    usable = df[df["result"].isin(LABEL_MAP)].copy()
    usable["target"] = usable["result"].map(LABEL_MAP)
    usable = usable.sort_values(["date", "division", "home", "away"]).reset_index(drop=True)

    split_idx = int(len(usable) * 0.8)
    train = usable.iloc[:split_idx].copy()
    test = usable.iloc[split_idx:].copy()

    logit, hgb, best_config = optimize_hybrid_config(train)
    test_eval = add_market_baseline(test)
    logit_probs = predict_full_probs(logit, test, feature_columns() + ["division"])
    hgb_probs = predict_full_probs(hgb, test, feature_columns())
    test_eval["logit_prob_1"] = logit_probs[:, 0]
    test_eval["logit_prob_x"] = logit_probs[:, 1]
    test_eval["logit_prob_2"] = logit_probs[:, 2]
    test_eval["hgb_prob_1"] = hgb_probs[:, 0]
    test_eval["hgb_prob_x"] = hgb_probs[:, 1]
    test_eval["hgb_prob_2"] = hgb_probs[:, 2]

    predictions = apply_hybrid_config(test_eval, best_config, "best")
    predictions = add_pleno_al_15(predictions)

    metrics = {
        "split_date": str(test["date"].min().date()),
        "dataset_matches": int(len(usable)),
        "train_matches": int(len(train)),
        "test_matches": int(len(test)),
        "divisions": {division: int(count) for division, count in usable["division"].value_counts().sort_index().items()},
        "best_config": best_config,
        "optimized_model": summarize_results(test_eval, "best", best_config),
    }
    return predictions, metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Ejecuta el motor con un histórico seleccionado.")
    parser.add_argument(
        "--historico",
        choices=("original", "saneado"),
        default="original",
        help="fuente histórica (por defecto: original)",
    )
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = load_raw_history(args.historico)
    features = rolling_team_features(raw)
    predictions, metrics = run_backtest(features)
    latest_predictions, latest_metrics = run_latest_season_backtest(features)
    completed_predictions, completed_metrics = run_season_backtest(features, "2024-2025")

    predictions.to_csv(OUT_DIR / "predicciones_backtest_optimizadas.csv", index=False, encoding="utf-8-sig")
    (OUT_DIR / "backtest_resumen_optimizado.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    latest_predictions.to_csv(OUT_DIR / "predicciones_backtest_ultima_temporada.csv", index=False, encoding="utf-8-sig")
    (OUT_DIR / "backtest_ultima_temporada.json").write_text(
        json.dumps(latest_metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    completed_predictions.to_csv(OUT_DIR / "predicciones_backtest_temporada_2024_2025.csv", index=False, encoding="utf-8-sig")
    (OUT_DIR / "backtest_temporada_2024_2025.json").write_text(
        json.dumps(completed_metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=" * 68)
    print("MOTOR QUINIELA MAESTRO - VERSION OPTIMIZADA")
    print("=" * 68)
    print(f"Base usada: {RAW_BASE}")
    print(f"Partidos limpios: {metrics['dataset_matches']}")
    print(f"Train: {metrics['train_matches']}  |  Test: {metrics['test_matches']}")
    print(f"Fecha de corte test: {metrics['split_date']}")
    print(f"Reparto divisiones: {metrics['divisions']}")
    print("-" * 68)
    print("CONFIG GANADORA")
    print(json.dumps(metrics["best_config"], ensure_ascii=False, indent=2))
    print("-" * 68)
    final = metrics["optimized_model"]
    print("RESULTADO FINAL")
    print(f"Acierto simple: {final['accuracy_simple']:.2%}")
    print(f"Favorito mercado: {final['accuracy_market_favorite']:.2%}")
    print(f"Media con 3 dobles: {final['mean_hits_3_dobles']:.2f}/15")
    for division, values in final["division_breakdown"].items():
        print(
            f"{division}: {values['matches']} partidos | "
            f"motor {values['accuracy_simple']:.2%} | "
            f"mercado {values['accuracy_market_favorite']:.2%}"
        )
    print("-" * 68)
    latest = latest_metrics["latest_season_model"]
    print(f"BACKTEST ULTIMA TEMPORADA DISPONIBLE: {latest_metrics['season']}")
    print(f"Test: {latest_metrics['test_matches']} partidos ({latest_metrics['test_date_from']} a {latest_metrics['test_date_to']})")
    print(f"Acierto simple: {latest['accuracy_simple']:.2%}")
    print(f"Favorito mercado: {latest['accuracy_market_favorite']:.2%}")
    print(f"Media con 3 dobles: {latest['mean_hits_3_dobles']:.2f}/15")
    print("-" * 68)
    completed = completed_metrics["latest_season_model"]
    print("BACKTEST TEMPORADA CERRADA: 2024-2025")
    print(f"Test: {completed_metrics['test_matches']} partidos ({completed_metrics['test_date_from']} a {completed_metrics['test_date_to']})")
    print(f"Acierto simple: {completed['accuracy_simple']:.2%}")
    print(f"Favorito mercado: {completed['accuracy_market_favorite']:.2%}")
    print(f"Media con 3 dobles: {completed['mean_hits_3_dobles']:.2f}/15")
    print(f"Salida: {OUT_DIR}")


if __name__ == "__main__":
    main()
