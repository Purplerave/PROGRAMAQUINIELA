"""
LEAGUE VIVENCIA RECONSTRUCTOR (CLEAN VERSION)
=============================================

Reconstruye la "vivencia" completa de la liga en cualquier momento:
- Posiciones y puntos exactos
- Goles totales y de los últimos 5 partidos
- Rachas (victorias, invicto, derrotas, empates)
- Momentum y forma
- Patrones interesantes (hot/cold, surprise packages, etc.)

Esto da **muchos más datos** para detectar patrones que el mercado no ve.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from scripts.motor.features import TeamStateTracker


@dataclass
class VivenciaSnapshot:
    """Snapshot rico del estado de la liga ANTES de un partido."""
    date: str
    home: str
    away: str
    division: str
    season: str

    # Clasificación
    home_pos: int
    away_pos: int
    home_pts: float
    away_pts: float
    leader: str
    leader_pts: float
    home_gap_to_leader: float
    away_gap_to_leader: float

    # Objetivos
    home_target: str
    away_target: str
    home_gap_to_europe: float
    home_gap_to_relegation: float
    away_gap_to_europe: float
    away_gap_to_relegation: float

    # Contexto
    is_six_pointer: bool
    is_title_six_pointer: bool
    is_relegation_six_pointer: bool
    is_nothing_to_play_for: bool
    home_must_win: bool
    away_nothing_to_play_for: bool

    # Fatiga
    home_matches_played: int
    away_matches_played: int
    home_days_since_last_match: float
    away_days_since_last_match: float

    # Fase y flags
    season_phase: str
    jornada_approx: int
    is_derby: bool
    is_big_match: bool
    high_stakes: bool

    # === GOLES ===
    home_gf_total: float
    home_ga_total: float
    away_gf_total: float
    away_ga_total: float
    home_gd: float
    away_gd: float
    home_gf_last5: float
    home_ga_last5: float
    away_gf_last5: float
    away_ga_last5: float

    # === RACHAS ===
    home_win_streak: int
    home_unbeaten_streak: int
    home_losing_streak: int
    home_drawing_streak: int
    away_win_streak: int
    away_unbeaten_streak: int
    away_losing_streak: int
    away_drawing_streak: int

    # Forma reciente
    home_last5_results: str
    away_last5_results: str
    home_last5_pts: int
    away_last5_pts: int
    home_form_trend: float
    away_form_trend: float

    # Patrones
    home_clean_sheets_last5: int
    away_clean_sheets_last5: int
    home_failed_to_score_last5: int
    away_failed_to_score_last5: int

    # Derivados avanzados
    home_momentum_score: float
    away_momentum_score: float
    home_is_hot: bool
    away_is_hot: bool
    home_is_cold: bool
    away_is_cold: bool
    home_bouncing_back: bool
    away_bouncing_back: bool

    home_goals_per_game_last5: float
    away_goals_per_game_last5: float
    home_conceded_per_game_last5: float
    away_conceded_per_game_last5: float

    is_relegation_battler_on_fire: bool
    is_leader_in_bad_form: bool
    is_surprise_package: bool

    # === PARALLEL BRANCH: Advanced fatigue (calendar-aware) ===
    home_fatigue: Dict[str, Any]
    away_fatigue: Dict[str, Any]
    home_congestion: float
    away_congestion: float
    home_back_to_back: int
    away_back_to_back: int

    home_table_snapshot: Dict[str, float]
    away_table_snapshot: Dict[str, float]

    # === NEW PARALLEL BRANCHES (deeper exploration) ===
    pattern_strength: float
    motivation_diff: float
    vivencia_value_score: float
    vivencia_context_score: float
    trust_regime: str
    trust_suggested_boost: float
    is_high_value_context: bool
    target_matchup_score: float
    season_phase_interaction: float
    fatigue_momentum_interaction: float


class LeagueVivenciaReconstructor:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.tracker = TeamStateTracker(config)
        self.season_matchweeks: Dict[Tuple[str, str], int] = {}

    def process_up_to(self, history_df: pd.DataFrame, cutoff: str) -> None:
        self.tracker = TeamStateTracker(self.config)
        self.tracker.process_history(history_df, cutoff_date=cutoff)
        self._compute_matchweeks(history_df, cutoff)

    def _compute_matchweeks(self, history_df: pd.DataFrame, cutoff: str):
        df = history_df.copy()
        df["date"] = pd.to_datetime(df["date"])
        cutoff_ts = pd.to_datetime(cutoff)
        df = df[df["date"] < cutoff_ts]
        for (div, season), group in df.groupby(["division", "season"]):
            self.season_matchweeks[(div, season)] = len(group["date"].unique())

    def get_vivencia(self, home: str, away: str, date: str, division: str, season: str) -> VivenciaSnapshot:
        home = str(home).strip()
        away = str(away).strip()

        home_table = self.tracker.ensure_standing(division, season, home)
        away_table = self.tracker.ensure_standing(division, season, away)

        positions = self.tracker.standing_positions(division, season)
        home_pos = positions.get(home, 99)
        away_pos = positions.get(away, 99)

        leader = max(self.tracker.standings_state.get((division, season), {}),
                     key=lambda t: self.tracker.standings_state[(division, season)][t]["pts"], default="Unknown")
        leader_pts = self.tracker.standings_state.get((division, season), {}).get(leader, {}).get("pts", 0)

        home_gap = max(0, leader_pts - home_table["pts"])
        away_gap = max(0, leader_pts - away_table["pts"])

        home_target = self._infer_target(home_pos, home_table["pts"], division)
        away_target = self._infer_target(away_pos, away_table["pts"], division)

        europe_th = 4 if division == "Primera" else 7
        releg_th = 17 if division == "Primera" else 18

        is_six = self._is_six_pointer(home_target, away_target, home_pos, away_pos)
        is_title_six = "champions" in (home_target, away_target) and is_six
        is_releg_six = "relegation" in (home_target, away_target) and is_six

        home_must = home_target in ("champions", "relegation_battle", "playoff")
        away_nothing = away_target in ("mid_table", "nothing")
        is_nothing = home_target == "nothing" and away_target == "nothing"

        home_hist = self.tracker.ensure_team(home)
        away_hist = self.tracker.ensure_team(away)

        home_last = home_hist.get("last_date")
        away_last = away_hist.get("last_date")
        home_rest = (pd.to_datetime(date) - pd.to_datetime(home_last)).days if home_last else -1
        away_rest = (pd.to_datetime(date) - pd.to_datetime(away_last)).days if away_last else -1

        jornada = self.season_matchweeks.get((division, season), 19)
        phase = self._infer_season_phase(jornada, home_target, away_target, division)

        is_derby = self._is_derby(home, away)
        is_big = (min(home_pos, away_pos) <= 6 and max(home_pos, away_pos) >= 15) or is_derby
        high = any(t in ("champions", "relegation_battle", "playoff") for t in (home_target, away_target))

        # GOLES
        gf_h = home_hist.get("gf", []) or []
        ga_h = home_hist.get("ga", []) or []
        pts_h = home_hist.get("pts", []) or []
        gf_a = away_hist.get("gf", []) or []
        ga_a = away_hist.get("ga", []) or []
        pts_a = away_hist.get("pts", []) or []

        home_gf = float(sum(gf_h))
        home_ga = float(sum(ga_h))
        away_gf = float(sum(gf_a))
        away_ga = float(sum(ga_a))
        home_gd = home_gf - home_ga
        away_gd = away_gf - away_ga

        h_gf5 = float(sum(gf_h[-5:])) if gf_h else 0.0
        h_ga5 = float(sum(ga_h[-5:])) if ga_h else 0.0
        a_gf5 = float(sum(gf_a[-5:])) if gf_a else 0.0
        a_ga5 = float(sum(ga_a[-5:])) if ga_a else 0.0

        # RACHAS
        h_win, h_unb, h_los, h_drw = self._compute_streaks(pts_h)
        a_win, a_unb, a_los, a_drw = self._compute_streaks(pts_a)

        h_last5 = "".join({3:"W",1:"D",0:"L"}.get(p,"?") for p in pts_h[-5:])
        a_last5 = "".join({3:"W",1:"D",0:"L"}.get(p,"?") for p in pts_a[-5:])

        h_pts5 = sum(pts_h[-5:]) if pts_h else 0
        a_pts5 = sum(pts_a[-5:]) if pts_a else 0

        h_trend = self._form_trend(pts_h)
        a_trend = self._form_trend(pts_a)

        h_clean5 = sum(1 for g in ga_h[-5:] if g == 0)
        a_clean5 = sum(1 for g in ga_a[-5:] if g == 0)
        h_fail5 = sum(1 for g in gf_h[-5:] if g == 0)
        a_fail5 = sum(1 for g in gf_a[-5:] if g == 0)

        # MOMENTUM + FLAGS
        h_mom = self._momentum(h_win, h_unb, h_pts5, h_gf5, h_trend)
        a_mom = self._momentum(a_win, a_unb, a_pts5, a_gf5, a_trend)

        h_hot = (h_win >= 2 or h_unb >= 3) and h_gf5 >= 4
        a_hot = (a_win >= 2 or a_unb >= 3) and a_gf5 >= 4
        h_cold = h_los >= 3 or (h_los >= 2 and h_gf5 <= 2)
        a_cold = a_los >= 3 or (a_los >= 2 and a_gf5 <= 2)
        h_bounce = h_trend > 0.3 and (h_los + h_drw >= 3)
        a_bounce = a_trend > 0.3 and (a_los + a_drw >= 3)

        h_gpg = round(h_gf5 / max(len(gf_h[-5:]), 1), 2) if gf_h else 0.0
        a_gpg = round(a_gf5 / max(len(gf_a[-5:]), 1), 2) if gf_a else 0.0
        h_cpg = round(h_ga5 / max(len(ga_h[-5:]), 1), 2) if ga_h else 0.0
        a_cpg = round(a_ga5 / max(len(ga_a[-5:]), 1), 2) if ga_a else 0.0

        releg_hot = (home_pos >= 15 or away_pos >= 15) and (h_hot or a_hot)
        leader_bad = (home_pos <= 4 or away_pos <= 4) and (h_cold or a_cold)
        surprise = (h_mom > 0.65 and home_pos > 10) or (a_mom > 0.65 and away_pos > 10)

        # === ADVANCED FATIGUE (parallel branch we keep exploring) ===
        home_fat = self._compute_advanced_fatigue(home_hist, date)
        away_fat = self._compute_advanced_fatigue(away_hist, date)

        # === PARALLEL BRANCHES COMPUTATIONS (main axis + exploration) ===
        # Inline calculations (avoid dummy objects / recursion)
        pat_str = 0.0
        if h_win >= 3: pat_str += 0.30
        if a_win >= 3: pat_str += 0.22
        if h_mom > 0.72 and home_pos > 10: pat_str += 0.28
        if releg_hot: pat_str += 0.38
        if surprise: pat_str += 0.32
        if leader_bad: pat_str += 0.27
        if is_six: pat_str += 0.18
        if h_hot: pat_str += 0.12
        pat_str = min(1.0, round(pat_str, 3))

        tscore = {"champions": 1.0, "europa": 0.82, "playoff": 0.75, "relegation_battle": 0.92, "mid_table": 0.32, "safe": 0.18, "nothing": 0.08}
        mot_diff = round(tscore.get(home_target, 0.4) - tscore.get(away_target, 0.4), 2)

        val_score = min(1.0, round(0.40 + 0.25 * pat_str + 0.15 * abs(mot_diff) + (0.15 if (is_six or high) else 0) + (0.10 if (home_fat.get("congestion_score",0)>0.55 or away_fat.get("congestion_score",0)>0.55) else 0), 3))

        ctx_score = 0.35
        ctx_score += 0.25 * pat_str
        if is_six or high: ctx_score += 0.20
        if releg_hot or surprise: ctx_score += 0.22
        if (home_fat.get("congestion_score", 0) > 0.6 or away_fat.get("congestion_score", 0) > 0.6): ctx_score += 0.15
        ctx_score += 0.10 * abs(mot_diff)
        ctx_score = min(1.0, round(ctx_score, 3))

        # trust regime inline
        regime = "balanced"
        sug_boost = 0.0
        if is_six or high:
            regime = "vivencia_high"
            sug_boost = 0.06
        if releg_hot or surprise:
            regime = "vivencia_high"
            sug_boost = max(sug_boost, 0.08)
        if h_mom > 0.76 and home_pos > 11:
            regime = "vivencia_high"
            sug_boost = max(sug_boost, 0.07)
        if is_nothing and h_mom < 0.55:
            regime = "market_high"
            sug_boost = -0.04
        sug_boost = round(sug_boost, 3)

        is_high_val = (is_six or high) or releg_hot or surprise or (h_mom > 0.75 and home_pos > 12) or (home_fat.get("congestion_score",0) > 0.65 or away_fat.get("congestion_score",0) > 0.65)

        # target matchup
        tgt_score = 0.0
        if home_target in ("champions","relegation_battle") and away_target in ("champions","relegation_battle"): tgt_score = 0.95
        elif "relegation" in (home_target, away_target): tgt_score = 0.82
        else: tgt_score = round(0.3 + 0.4*abs(mot_diff), 2)
        tgt_score = min(1.0, tgt_score)

        # season + fatigue interactions
        phase_int = 0.0
        if phase in ("relegation", "title_race"): phase_int = 0.35
        if jornada > 30: phase_int += 0.15
        phase_int = round(phase_int, 3)

        fat_mom_int = round( (home_fat.get("congestion_score",0) * max(0, h_mom-0.4)) + (away_fat.get("congestion_score",0) * max(0, a_mom-0.4)) , 3)

        return VivenciaSnapshot(
            date=str(date), home=home, away=away, division=division, season=season,
            home_pos=home_pos, away_pos=away_pos,
            home_pts=home_table["pts"], away_pts=away_table["pts"],
            leader=leader, leader_pts=leader_pts,
            home_gap_to_leader=round(home_gap, 1), away_gap_to_leader=round(away_gap, 1),
            home_target=home_target, away_target=away_target,
            home_gap_to_europe=round(max(0, (home_pos - europe_th) * 3), 1),
            home_gap_to_relegation=round(max(0, (releg_th - home_pos) * 3), 1),
            away_gap_to_europe=round(max(0, (away_pos - europe_th) * 3), 1),
            away_gap_to_relegation=round(max(0, (releg_th - away_pos) * 3), 1),
            is_six_pointer=is_six, is_title_six_pointer=is_title_six,
            is_relegation_six_pointer=is_releg_six, is_nothing_to_play_for=is_nothing,
            home_must_win=home_must, away_nothing_to_play_for=away_nothing,
            home_matches_played=int(home_table["pj"]), away_matches_played=int(away_table["pj"]),
            home_days_since_last_match=round(home_rest, 1) if home_rest > 0 else -1,
            away_days_since_last_match=round(away_rest, 1) if away_rest > 0 else -1,
            season_phase=phase, jornada_approx=jornada,
            is_derby=is_derby, is_big_match=is_big, high_stakes=high,

            # GOLES + RACHAS
            home_gf_total=round(home_gf, 1), home_ga_total=round(home_ga, 1),
            away_gf_total=round(away_gf, 1), away_ga_total=round(away_ga, 1),
            home_gd=round(home_gd, 1), away_gd=round(away_gd, 1),
            home_gf_last5=round(h_gf5, 1), home_ga_last5=round(h_ga5, 1),
            away_gf_last5=round(a_gf5, 1), away_ga_last5=round(a_ga5, 1),

            home_win_streak=h_win, home_unbeaten_streak=h_unb,
            home_losing_streak=h_los, home_drawing_streak=h_drw,
            away_win_streak=a_win, away_unbeaten_streak=a_unb,
            away_losing_streak=a_los, away_drawing_streak=a_drw,

            home_last5_results=h_last5, away_last5_results=a_last5,
            home_last5_pts=h_pts5, away_last5_pts=a_pts5,
            home_form_trend=round(h_trend, 2), away_form_trend=round(a_trend, 2),

            home_clean_sheets_last5=h_clean5, away_clean_sheets_last5=a_clean5,
            home_failed_to_score_last5=h_fail5, away_failed_to_score_last5=a_fail5,

            home_momentum_score=round(h_mom, 3), away_momentum_score=round(a_mom, 3),
            home_is_hot=h_hot, away_is_hot=a_hot,
            home_is_cold=h_cold, away_is_cold=a_cold,
            home_bouncing_back=h_bounce, away_bouncing_back=a_bounce,
            home_goals_per_game_last5=h_gpg, away_goals_per_game_last5=a_gpg,
            home_conceded_per_game_last5=h_cpg, away_conceded_per_game_last5=a_cpg,

            is_relegation_battler_on_fire=releg_hot,
            is_leader_in_bad_form=leader_bad,
            is_surprise_package=surprise,

            # === NEW: advanced fatigue from parallel branch ===
            home_fatigue=home_fat,
            away_fatigue=away_fat,
            home_congestion=home_fat.get("congestion_score", 0.0),
            away_congestion=away_fat.get("congestion_score", 0.0),
            home_back_to_back=home_fat.get("back_to_back", 0),
            away_back_to_back=away_fat.get("back_to_back", 0),

            home_table_snapshot=home_table.copy(),
            away_table_snapshot=away_table.copy(),

            # NEW PARALLEL BRANCHES (filled inline above)
            pattern_strength=pat_str,
            motivation_diff=mot_diff,
            vivencia_value_score=val_score,
            vivencia_context_score=ctx_score,
            trust_regime=regime,
            trust_suggested_boost=sug_boost,
            is_high_value_context=is_high_val,
            target_matchup_score=tgt_score,
            season_phase_interaction=phase_int,
            fatigue_momentum_interaction=fat_mom_int,
        )

    # Helpers
    def _infer_target(self, pos: int, pts: float, div: str) -> str:
        if div == "Primera":
            if pos <= 4: return "champions"
            if pos <= 7: return "europa"
            if pos >= 18 or (pos >= 15 and pts < 35): return "relegation_battle"
            return "mid_table" if pos <= 12 else "safe"
        else:
            if pos <= 2: return "champions"
            if pos <= 7: return "playoff"
            if pos >= 19: return "relegation_battle"
            return "mid_table"

    def _is_six_pointer(self, t1, t2, p1, p2):
        fighting = {"champions", "europa", "relegation_battle", "playoff"}
        return (t1 in fighting and t2 in fighting) or (abs(p1-p2) <= 3 and min(p1,p2) <= 8)

    def _infer_season_phase(self, j, ht, at, d):
        if j < 10: return "early"
        if j > 32:
            if "relegation" in (ht, at): return "relegation"
            if any(x in (ht, at) for x in ["champions", "europa"]): return "title_race"
            return "dead_rubber"
        if "relegation" in (ht, at): return "relegation"
        if any(x in (ht, at) for x in ["champions", "europa"]): return "title_race"
        return "mid"

    def _compute_streaks(self, pts):
        w = u = l = d = 0
        for p in reversed(pts or []):
            if p == 3: w += 1; u += 1; l = 0; d = 0
            elif p == 1: d += 1; u += 1; w = 0; l = 0
            else: l += 1; u = 0; w = 0; d = 0
        return w, u, l, d

    def _compute_advanced_fatigue(self, team_hist, current_date, lookback_matches=4):
        """Parallel branch: real calendar fatigue (matches in window + inter-match rest).
        This now tries to use real match dates if present in history; falls back gracefully.
        """
        # Try to use real dates if the history was enriched
        dates = []
        if "match_dates" in team_hist and team_hist["match_dates"]:
            dates = [pd.to_datetime(d) for d in team_hist["match_dates"] if pd.notna(d)]
        elif "last_dates" in team_hist:  # alternative storage
            dates = [pd.to_datetime(d) for d in team_hist["last_dates"] if pd.notna(d)]

        if not dates:
            # Fallback to simple last_date if nothing better
            last = team_hist.get("last_date")
            if last:
                return {
                    "matches_last_14d": 1,
                    "avg_rest_days": -1,
                    "congestion_score": 0.2,
                    "back_to_back": 0
                }
            return {"matches_last_14d": 0, "avg_rest_days": -1, "congestion_score": 0.0, "back_to_back": 0}

        current = pd.to_datetime(current_date)
        recent = sorted([d for d in dates if (current - d).days <= 14 and (current - d).days > 0], reverse=True)
        matches_last_14d = len(recent)

        if len(dates) >= 2:
            deltas = [(dates[i] - dates[i-1]).days for i in range(1, min(len(dates), lookback_matches+1))]
            avg_rest = float(np.mean(deltas)) if deltas else -1.0
        else:
            avg_rest = -1.0

        congestion = min(1.0, matches_last_14d / 3.5)
        if avg_rest > 0 and avg_rest < 4:
            congestion = min(1.0, congestion + 0.35)
        if avg_rest > 0 and avg_rest < 3:
            congestion = min(1.0, congestion + 0.25)

        back_to_back = 1 if any((recent[i] - recent[i+1]).days <= 3 for i in range(len(recent)-1)) else 0

        return {
            "matches_last_14d": matches_last_14d,
            "avg_rest_days": round(avg_rest, 1) if avg_rest > 0 else -1,
            "congestion_score": round(congestion, 3),
            "back_to_back": back_to_back
        }

    def _form_trend(self, pts):
        if len(pts or []) < 6: return 0.0
        return (sum(pts[-3:]) - sum(pts[-6:-3])) / 9.0

    def _momentum(self, ws, ub, pts5, gf5, trend):
        s = min(ws, 4)*0.12 + min(ub, 5)*0.08 + (pts5/15)*0.35 + min(gf5/8, 1)*0.25 + max(min(trend,1),-1)*0.2
        return max(0.0, min(1.0, s))

    def _is_derby(self, h, a):
        ds = {("Real Madrid","Barcelona"), ("Barcelona","Real Madrid"),
              ("Real Madrid","Atletico Madrid"), ("Atletico Madrid","Real Madrid"),
              ("Barcelona","Espanyol"), ("Espanyol","Barcelona"),
              ("Ath Bilbao","Real Sociedad"), ("Real Sociedad","Ath Bilbao"),
              ("Sevilla","Betis"), ("Betis","Sevilla")}
        return tuple(sorted([h,a])) in ds

    def detect_patterns(self, snap: VivenciaSnapshot) -> Dict[str, Any]:
        pats = []
        if snap.home_win_streak >= 3: pats.append(f"LOCAL {snap.home_win_streak} victorias seguidas")
        if snap.away_win_streak >= 3: pats.append(f"VISITANTE {snap.away_win_streak} victorias seguidas")
        if snap.home_losing_streak >= 3: pats.append("LOCAL en mala racha")
        if snap.home_momentum_score > 0.7 and snap.home_pos > 10:
            pats.append("LOCAL buena forma pero bajo en tabla (sorpresa)")
        if snap.home_pos >= 15 and snap.home_momentum_score > 0.65:
            pats.append("LOCAL salvación + buena racha")
        if snap.is_derby and (snap.home_is_hot or snap.away_is_hot):
            pats.append("DERBI con equipo enchufado")
        if snap.is_nothing_to_play_for and (snap.home_momentum_score > 0.6 or snap.away_momentum_score > 0.6):
            pats.append("Partido 'sin nada' pero con momentum")
        return {"patterns": pats, "num": len(pats), "home_mom": snap.home_momentum_score, "away_mom": snap.away_momentum_score}

    # ============================================================
    # PARALLEL BRANCHES (explored while keeping Vivencia as MAIN axis)
    # ============================================================

    def compute_pattern_strength(self, snap: VivenciaSnapshot) -> float:
        """Parallel branch: How 'loud' / valuable is the current vivencia signal?"""
        s = 0.0
        if snap.home_win_streak >= 3: s += 0.30
        if snap.away_win_streak >= 3: s += 0.22
        if snap.home_momentum_score > 0.72 and snap.home_pos > 10: s += 0.28
        if snap.is_relegation_battler_on_fire: s += 0.38
        if snap.is_surprise_package: s += 0.32
        if snap.is_leader_in_bad_form: s += 0.27
        if snap.is_six_pointer: s += 0.18
        if snap.home_is_hot: s += 0.12
        return min(1.0, round(s, 3))

    def compute_motivation_diff(self, snap: VivenciaSnapshot) -> float:
        """Parallel branch: Motivation gap between the two sides."""
        tscore = {
            "champions": 1.0, "europa": 0.82, "playoff": 0.75,
            "relegation_battle": 0.92, "mid_table": 0.32, "safe": 0.18, "nothing": 0.08
        }
        hm = tscore.get(snap.home_target, 0.4)
        am = tscore.get(snap.away_target, 0.4)
        return round(hm - am, 2)

    def compute_vivencia_value_score(self, snap: VivenciaSnapshot) -> float:
        """Parallel branch: Overall 'how much should we care' about this snapshot."""
        score = 0.40
        score += 0.25 * self.compute_pattern_strength(snap)
        score += 0.15 * abs(self.compute_motivation_diff(snap))
        if snap.is_six_pointer or snap.high_stakes:
            score += 0.15
        hf = snap.home_fatigue or {}
        af = snap.away_fatigue or {}
        if hf.get("congestion_score", 0) > 0.55 or af.get("congestion_score", 0) > 0.55:
            score += 0.10
        return min(1.0, round(score, 3))

    def compute_vivencia_trust_regime(self, snap: VivenciaSnapshot, market_max_prob: float = 0.70) -> dict:
        """Parallel branch: When to lean on vivencia vs market for this match."""
        regime = "balanced"
        suggested_boost = 0.0

        if snap.is_six_pointer or snap.high_stakes:
            regime = "vivencia_high"
            suggested_boost = 0.06
        if snap.is_relegation_battler_on_fire or snap.is_surprise_package:
            regime = "vivencia_high"
            suggested_boost = max(suggested_boost, 0.08)
        if snap.home_momentum_score > 0.76 and snap.home_pos > 11:
            regime = "vivencia_high"
            suggested_boost = max(suggested_boost, 0.07)

        if snap.is_nothing_to_play_for and snap.home_momentum_score < 0.55:
            regime = "market_high"
            suggested_boost = -0.04

        if market_max_prob > 0.82 and regime != "vivencia_high":
            regime = "market_cautious"

        return {
            "regime": regime,
            "suggested_boost": round(suggested_boost, 3),
            "pattern_strength": self.compute_pattern_strength(snap),
            "motivation_diff": self.compute_motivation_diff(snap),
        }

    def is_high_value_context_match(self, snap: VivenciaSnapshot) -> bool:
        """Simple helper: is this a match where vivencia/context is likely more important than raw stats?"""
        if snap.is_six_pointer or snap.high_stakes:
            return True
        if snap.is_relegation_battler_on_fire or snap.is_surprise_package:
            return True
        if snap.home_momentum_score > 0.75 and snap.home_pos > 12:
            return True
        if snap.home_fatigue.get("congestion_score", 0) > 0.65 or snap.away_fatigue.get("congestion_score", 0) > 0.65:
            return True
        return False

    def compute_vivencia_context_score(self, snap: VivenciaSnapshot) -> float:
        """New parallel branch: Combined score for how much 'extra signal' this vivencia gives vs pure market/stats.
        This is the kind of thing we can feed into double selection or risk decisions.
        """
        score = 0.35

        # Strong pattern or hot streak in bad position
        score += 0.25 * self.compute_pattern_strength(snap)

        # High stakes or six pointer
        if snap.is_six_pointer or snap.high_stakes:
            score += 0.20

        # Relegation battler or surprise on fire
        if snap.is_relegation_battler_on_fire or snap.is_surprise_package:
            score += 0.22

        # Congestion / fatigue making the match unpredictable
        hf = snap.home_fatigue or {}
        af = snap.away_fatigue or {}
        if hf.get("congestion_score", 0) > 0.6 or af.get("congestion_score", 0) > 0.6:
            score += 0.15

        # Motivation gap
        score += 0.10 * abs(self.compute_motivation_diff(snap))

        return min(1.0, round(score, 3))

    def enrich_dataframe_with_vivencia(self, df: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for _, r in df.iterrows():
            snap = self.get_vivencia(r["home"], r["away"], r["date"], r["division"], r["season"])
            d = asdict(snap)
            d["viv_home_momentum"] = d.pop("home_momentum_score")
            d["viv_away_momentum"] = d.pop("away_momentum_score")
            d["viv_home_is_hot"] = int(d.pop("home_is_hot"))
            d["viv_home_win_streak"] = d.pop("home_win_streak")
            d["viv_home_gd"] = d.pop("home_gd")
            # expose new parallel branches for double selection & models
            d["viv_pattern_strength"] = snap.pattern_strength
            d["viv_motivation_diff"] = snap.motivation_diff
            d["viv_context_value"] = snap.vivencia_context_score
            d["viv_value_score"] = snap.vivencia_value_score
            d["viv_trust_regime"] = snap.trust_regime
            d["viv_trust_boost"] = snap.trust_suggested_boost
            d["viv_is_high_value"] = int(snap.is_high_value_context)
            d["viv_target_matchup"] = snap.target_matchup_score
            d["viv_phase_interaction"] = snap.season_phase_interaction
            d["viv_fatigue_mom_int"] = snap.fatigue_momentum_interaction
            rows.append(d)
        vdf = pd.DataFrame(rows)
        base = ["home","away","date","division","season"]
        vdf = vdf.drop(columns=[c for c in base if c in vdf], errors="ignore")
        return pd.concat([df.reset_index(drop=True), vdf.reset_index(drop=True)], axis=1)


def vivencia_to_model_features(snap: VivenciaSnapshot) -> Dict[str, float]:
    """~22 numeric features + expanded parallel branches (~31 total).
    Core league state + advanced fatigue + all new context/value/trust branches.
    """
    hf = getattr(snap, "home_fatigue", {}) or {}
    af = getattr(snap, "away_fatigue", {}) or {}

    core = {
        "viv_home_pos": float(snap.home_pos),
        "viv_away_pos": float(snap.away_pos),
        "viv_home_pts": float(snap.home_pts),
        "viv_home_gd": float(snap.home_gd),
        "viv_home_win_streak": float(snap.home_win_streak),
        "viv_home_momentum": float(snap.home_momentum_score),
        "viv_home_is_hot": 1.0 if snap.home_is_hot else 0.0,
        "viv_home_is_cold": 1.0 if snap.home_is_cold else 0.0,
        "viv_home_last5_pts": float(snap.home_last5_pts),
        "viv_home_form_trend": float(snap.home_form_trend),
        "viv_away_momentum": float(snap.away_momentum_score),
        "viv_is_six_pointer": 1.0 if snap.is_six_pointer else 0.0,
        "viv_high_stakes": 1.0 if snap.high_stakes else 0.0,
        "viv_releg_hot": 1.0 if snap.is_relegation_battler_on_fire else 0.0,
        "viv_leader_bad": 1.0 if snap.is_leader_in_bad_form else 0.0,
        "viv_surprise": 1.0 if snap.is_surprise_package else 0.0,
    }

    # Parallel branch: advanced calendar fatigue
    fatigue = {
        "viv_home_matches_14d": float(hf.get("matches_last_14d", 0)),
        "viv_home_congestion": float(hf.get("congestion_score", 0.0)),
        "viv_home_back_to_back": float(hf.get("back_to_back", 0)),
        "viv_away_matches_14d": float(af.get("matches_last_14d", 0)),
        "viv_away_congestion": float(af.get("congestion_score", 0.0)),
        "viv_away_back_to_back": float(af.get("back_to_back", 0)),
    }

    # Expanded parallel branches (main axis + all explored)
    branches = {
        "viv_pattern_strength": float(getattr(snap, "pattern_strength", 0.5)),
        "viv_motivation_diff": float(getattr(snap, "motivation_diff", 0.0)),
        "viv_value_score": float(getattr(snap, "vivencia_value_score", 0.5)),
        "viv_context_value": float(getattr(snap, "vivencia_context_score", 0.5)),
        "viv_trust_boost": float(getattr(snap, "trust_suggested_boost", 0.0)),
        "viv_is_high_value": 1.0 if getattr(snap, "is_high_value_context", False) else 0.0,
        "viv_target_matchup": float(getattr(snap, "target_matchup_score", 0.5)),
        "viv_phase_interaction": float(getattr(snap, "season_phase_interaction", 0.0)),
        "viv_fatigue_mom_int": float(getattr(snap, "fatigue_momentum_interaction", 0.0)),
    }

    return {**core, **fatigue, **branches}


if __name__ == "__main__":
    print("Vivencia Reconstructor listo (con goles + rachas + patrones)")
    print("Usa: recon.get_vivencia(...) o recon.detect_patterns(snap)")
