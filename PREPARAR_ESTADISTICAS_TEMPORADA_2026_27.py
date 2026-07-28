import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

import settings


ROOT = Path(__file__).resolve().parent
DATOS_DIR = settings.DATOS_DIR
TEAMS_PATH = DATOS_DIR / "temporada_2026_27_equipos.json"
HIGHLIGHTLY_CSV = DATOS_DIR / "highlightly_dataset" / "highlightly_partidos_2023_2026.csv"
OUT_PATH = DATOS_DIR / "temporada_2026_27_estadisticas_base.json"

SOURCE_SEASON = "2025"
SOURCE_LEAGUES = {"La Liga", "Segunda Division", "Segunda División"}

# Factores prudentes para no comparar a pelo ligas distintas.
# No sustituyen a un modelo calibrado; evitan que un ascendido parezca mejor
# que equipos de Primera solo por haber dominado una categoria inferior.
TRANSITION_FACTORS = {
    "misma_categoria": 1.00,
    "segunda_a_primera": 0.78,
    "primera_a_segunda": 1.12,
    "primera_rfef_a_segunda": 0.70,
    "filial_primera_rfef_a_segunda": 0.66,
    "sin_muestra": None,
}
TRANSITION_FACTORS.update(settings.transition_factors())


ALIASES = {
    "Athletic Club": ["Athletic Club"],
    "Atletico de Madrid": ["Atlético Madrid", "Atletico Madrid"],
    "CA Osasuna": ["Osasuna"],
    "Deportivo Alaves": ["Alavés", "Alaves"],
    "Elche CF": ["Elche"],
    "FC Barcelona": ["Barcelona"],
    "Getafe CF": ["Getafe"],
    "Levante UD": ["Levante"],
    "Malaga CF": ["Malaga", "Málaga"],
    "R. Racing Club": ["Racing Santander"],
    "Rayo Vallecano": ["Rayo Vallecano"],
    "RC Celta": ["Celta de Vigo"],
    "RC Deportivo": ["Deportivo La Coruña", "Deportivo La Coruna"],
    "RCD Espanyol de Barcelona": ["Espanyol"],
    "Real Betis": ["Real Betis"],
    "Real Madrid": ["Real Madrid"],
    "Real Sociedad": ["Real Sociedad"],
    "Sevilla FC": ["Sevilla FC"],
    "Valencia CF": ["Valencia"],
    "Villarreal CF": ["Villarreal"],
    "AD Ceuta FC": ["AD Ceuta FC"],
    "Albacete BP": ["Albacete"],
    "Burgos CF": ["Burgos"],
    "Cadiz CF": ["Cadiz", "Cádiz"],
    "CD Castellon": ["Castellón", "Castellon"],
    "CD Eldense": ["Eldense"],
    "CD Leganes": ["Leganes", "Leganés"],
    "CD Tenerife": ["Tenerife"],
    "CE Sabadell": ["Sabadell"],
    "Cordoba CF": ["Cordoba", "Córdoba"],
    "FC Andorra": ["FC Andorra"],
    "Girona FC": ["Girona"],
    "Granada CF": ["Granada CF"],
    "R. Sociedad B": ["Real Sociedad B"],
    "RC Celta Fortuna": ["Celta Fortuna"],
    "RCD Mallorca": ["Mallorca"],
    "Real Oviedo": ["Oviedo"],
    "Real Sporting": ["Sporting Gijón", "Sporting Gijon"],
    "Real Valladolid CF": ["Valladolid"],
    "SD Eibar": ["Eibar"],
    "UD Almeria": ["Almería", "Almeria"],
    "UD Las Palmas": ["Las Palmas"],
}


def empty_stats():
    return {
        "pj": 0,
        "g": 0,
        "e": 0,
        "p": 0,
        "gf": 0,
        "gc": 0,
        "dg": 0,
        "pts": 0,
        "home": {"pj": 0, "g": 0, "e": 0, "p": 0, "gf": 0, "gc": 0, "pts": 0},
        "away": {"pj": 0, "g": 0, "e": 0, "p": 0, "gf": 0, "gc": 0, "pts": 0},
        "source_leagues": defaultdict(int),
    }


def normalize_league(name):
    return name.replace("División", "Division")


def add_result(stats, side, gf, gc):
    bucket = stats[side]
    bucket["pj"] += 1
    bucket["gf"] += gf
    bucket["gc"] += gc
    stats["pj"] += 1
    stats["gf"] += gf
    stats["gc"] += gc
    if gf > gc:
        result = "g"
        pts = 3
    elif gf == gc:
        result = "e"
        pts = 1
    else:
        result = "p"
        pts = 0
    bucket[result] += 1
    bucket["pts"] += pts
    stats[result] += 1
    stats["pts"] += pts
    stats["dg"] = stats["gf"] - stats["gc"]


def clean_stats(stats):
    cleaned = dict(stats)
    cleaned["source_leagues"] = dict(stats["source_leagues"])
    cleaned["ppg"] = round(stats["pts"] / stats["pj"], 3) if stats["pj"] else None
    cleaned["gf_per_match"] = round(stats["gf"] / stats["pj"], 3) if stats["pj"] else None
    cleaned["gc_per_match"] = round(stats["gc"] / stats["pj"], 3) if stats["pj"] else None
    for side in ("home", "away"):
        bucket = cleaned[side]
        bucket["ppg"] = round(bucket["pts"] / bucket["pj"], 3) if bucket["pj"] else None
    return cleaned


def infer_target_competitions(teams):
    target = {}
    statuses = {}
    for item in teams["laliga_ea_sports"]:
        target[item["team"]] = "La Liga"
        statuses[item["team"]] = item["status"]
    for item in teams["laliga_hypermotion"]:
        target[item["team"]] = "Segunda Division"
        statuses[item["team"]] = item["status"]
    return target, statuses


def main_source_league(stats):
    if not stats["source_leagues"]:
        return None
    return max(stats["source_leagues"].items(), key=lambda item: item[1])[0]


def transition_key(target_competition, status, source_league, pj):
    if pj == 0:
        if status == "ascendido_primera_rfef_filial":
            return "filial_primera_rfef_a_segunda"
        if status == "ascendido_primera_rfef":
            return "primera_rfef_a_segunda"
        return "sin_muestra"
    if target_competition == "La Liga" and source_league == "Segunda Division":
        return "segunda_a_primera"
    if target_competition == "Segunda Division" and source_league == "La Liga":
        return "primera_a_segunda"
    return "misma_categoria"


def confidence_for_transition(key, pj):
    if key == "sin_muestra":
        return "muy_baja"
    if key in {"primera_rfef_a_segunda", "filial_primera_rfef_a_segunda"}:
        return "baja"
    if pj < 30:
        return "media"
    if key == "misma_categoria":
        return "alta"
    return "media"


def comparability_note(key):
    notes = {
        "misma_categoria": "Comparable de forma directa con equipos de la misma categoria.",
        "segunda_a_primera": "Ascendido: los datos brutos vienen de Segunda y se rebajan para Primera.",
        "primera_a_segunda": "Descendido: los datos brutos vienen de Primera y se recontextualizan para Segunda.",
        "primera_rfef_a_segunda": "Ascendido desde Primera RFEF: falta muestra local equivalente, usar con cautela.",
        "filial_primera_rfef_a_segunda": "Filial ascendido desde Primera RFEF: muestra no comparable y riesgo competitivo especial.",
        "sin_muestra": "Sin muestra suficiente en el dataset local.",
    }
    return notes[key]


def add_contextual_layer(team, stats, target_competitions, statuses):
    source_league = main_source_league(stats)
    target_competition = target_competitions[team]
    status = statuses[team]
    key = transition_key(target_competition, status, source_league, stats["pj"])
    factor = TRANSITION_FACTORS[key]
    raw_ppg = round(stats["pts"] / stats["pj"], 3) if stats["pj"] else None
    if raw_ppg is None or factor is None:
        adjusted_ppg = None
    else:
        adjusted_ppg = round(raw_ppg * factor, 3)
    return {
        "target_competition": target_competition,
        "status_2026_27": status,
        "source_main_league": source_league,
        "transition": key,
        "transition_factor": factor,
        "raw_ppg": raw_ppg,
        "adjusted_ppg": adjusted_ppg,
        "confidence": confidence_for_transition(key, stats["pj"]),
        "note": comparability_note(key),
    }


def main():
    teams = json.loads(TEAMS_PATH.read_text(encoding="utf-8"))
    target_competitions, statuses = infer_target_competitions(teams)
    canonical_names = [
        item["team"]
        for section in ("laliga_ea_sports", "laliga_hypermotion")
        for item in teams[section]
    ]
    alias_to_canonical = {}
    for canonical in canonical_names:
        for alias in ALIASES.get(canonical, [canonical]):
            alias_to_canonical[alias] = canonical

    stats_by_team = {team: empty_stats() for team in canonical_names}

    with HIGHLIGHTLY_CSV.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            league = normalize_league(row["league_name"])
            if row["league_season"] != SOURCE_SEASON or league not in SOURCE_LEAGUES:
                continue
            if row["status"] != "Finished" or not row["home_goals"] or not row["away_goals"]:
                continue
            home = alias_to_canonical.get(row["home_name"])
            away = alias_to_canonical.get(row["away_name"])
            home_goals = int(row["home_goals"])
            away_goals = int(row["away_goals"])
            if home:
                add_result(stats_by_team[home], "home", home_goals, away_goals)
                stats_by_team[home]["source_leagues"][league] += 1
            if away:
                add_result(stats_by_team[away], "away", away_goals, home_goals)
                stats_by_team[away]["source_leagues"][league] += 1

    cleaned_teams = {}
    for team, stats in stats_by_team.items():
        cleaned = clean_stats(stats)
        cleaned["context"] = add_contextual_layer(team, stats, target_competitions, statuses)
        cleaned_teams[team] = cleaned

    payload = {
        "season_target": "2026/27",
        "generated_at": date.today().isoformat(),
        "source": {
            "type": "local_highlightly_dataset",
            "path": str(HIGHLIGHTLY_CSV),
            "season": SOURCE_SEASON,
            "leagues": sorted(SOURCE_LEAGUES),
            "note": "Base estadistica inicial antes de empezar 2026/27. No sustituye cuotas, lesiones ni mercado.",
        },
        "comparability_model": {
            "purpose": "Evitar comparar directamente equipos de categorias distintas.",
            "transition_factors": TRANSITION_FACTORS,
            "warning": "Factores heurísticos iniciales. Deben calibrarse con backtest de ascendidos/descendidos.",
        },
        "teams": cleaned_teams,
        "missing_or_partial": [
            team for team, stats in stats_by_team.items() if stats["pj"] < 20
        ],
        "missing_data_strategy": {
            "status": "pendiente_fuente_externa",
            "teams": [
                team for team, stats in stats_by_team.items() if stats["pj"] < 20
            ],
            "rules": [
                "No inventar adjusted_ppg si no hay muestra fiable.",
                "Buscar primero fuente estable de Primera RFEF.",
                "Si no hay fuente, usar cuotas/mercado como proxy inicial con confianza baja.",
                "Datos historicos antiguos solo con penalizacion y nota explicita."
            ]
        },
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {OUT_PATH}")
    print(f"Equipos sin muestra fuerte: {', '.join(payload['missing_or_partial']) or '-'}")


if __name__ == "__main__":
    main()
