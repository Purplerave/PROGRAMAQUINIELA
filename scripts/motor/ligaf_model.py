"""
ligaf_model.py — Modulo OFICIAL del motor para las casillas de Liga F.

Modelo: Dixon-Coles simplificado (log-lineal ataque/defensa + ventaja local),
MLE ponderado con decay temporal w=exp(-0.002*dias), regularizacion L2.
Evaluación retrospectiva walk-forward diaria; los resultados reproducibles,
por temporada y con hashes de datos se generan con
`scripts/backtests/BACKTEST_LIGAF_MULTITEMPORADA.py`. Las métricas históricas
no garantizan rendimiento futuro ni ventaja frente al mercado.

Contrato del modulo:
    - cargar_dated()            -> histórico StatsBomb + resultados multitemporada
    - cargar_statsbomb_2324()   -> backbone StatsBomb 2023/24 aislado
    - ajustar(partidos)         -> (ratings, mu, gamma)
    - predecir(local, vis, ...) -> {"p1","px","p2","signo","fuente"}
    - walkforward(...)          -> metricas honestas OOS

Nombres SIEMPRE normalizados con canon() (mapa de renombres historicos).
Equipos sin historial -> prior NEUTRO documentado (caso ascendidos).
"""
from __future__ import annotations

import csv
import math
import unicodedata
from datetime import datetime
from itertools import groupby
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

BASE = Path(__file__).resolve().parents[2] / "DATOS" / "ligaf"
XI = 0.002          # decay por dia
GOLES_MAX = 8       # rejilla Poisson
WARMUP = 60
REFIT_CADA = 15

REGLAS_CANON = [
    ("badalona", "badalona"), ("levante las planas", "las_planas"),
    ("levante ud femenino", "levante"), ("levante ud", "levante"),
    ("granadilla", "tenerife"), ("costa adeje", "tenerife"),
    ("barcelona", "barcelona"), ("atletico de madrid", "atletico"),
    ("at. madrid", "atletico"), ("atletico madrid w", "atletico"),
    ("atletico", "atletico"),
    ("athletic", "athletic"), ("real madrid", "rmadrid"),
    ("betis", "betis"), ("real sociedad", "rso"),
    ("sporting de huelva", "sporting_huelva"), ("espanyol", "espanyol"),
    ("eibar", "eibar"), ("sevilla", "sevilla"), ("valencia", "valencia"),
    ("villarreal", "villarreal"), ("granada", "granada"),
    ("madrid cff", "madridcff"), ("deportivo de la coruna", "dep_coruna"),
    ("alaves gloriosas", "alaves"), ("alaves", "alaves"),
    ("alhama", "alhama"), ("logrono", "logrono"), ("levante badalona", "badalona"),
]


def _na(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def canon(nombre: str) -> str:
    n = _na(nombre)
    for clave, destino in REGLAS_CANON:
        if clave in n:
            return destino
    return n


def _fixture_key(match: dict) -> tuple:
    return (match["fecha"].date(), match["local"], match["visitante"])


def _season_from_date(match_date: datetime) -> str:
    start = match_date.year if match_date.month >= 7 else match_date.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def _load_uploaded_results(path: Path) -> list[dict]:
    """Lee y valida el CSV adicional; solo admite partidos finalizados."""
    required = {"season", "date", "match_id", "home", "home_goals", "away_goals", "away", "status"}
    allowed_non_final = {
        "scheduled", "not started", "not_started", "postponed", "cancelled",
        "canceled", "abandoned", "live", "in progress", "in_progress", "tbd",
    }
    completed = {"full time", "finished", "finished after extra time", "finished after penalties", "ft"}
    matches = []
    ids: set[str] = set()
    fixtures: set[tuple] = set()

    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV Liga F sin columnas requeridas: {sorted(missing)}")
        for line, row in enumerate(reader, start=2):
            status = (row.get("status") or "").strip().casefold()
            if status in allowed_non_final:
                continue
            if status not in completed:
                raise ValueError(f"Estado de partido desconocido en {path}:{line}: {status!r}")

            try:
                match_date = datetime.strptime((row.get("date") or "").strip(), "%Y-%m-%d")
                home_goals = int(row.get("home_goals"))
                away_goals = int(row.get("away_goals"))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Fecha o marcador inválido en {path}:{line}") from exc
            if home_goals < 0 or away_goals < 0:
                raise ValueError(f"Marcador negativo en {path}:{line}")
            if (row.get("season") or "").strip() != _season_from_date(match_date):
                raise ValueError(f"Temporada no coincide con la fecha en {path}:{line}")

            match_id = (row.get("match_id") or "").strip()
            if not match_id or match_id in ids:
                raise ValueError(f"ID vacío o duplicado en {path}:{line}: {match_id!r}")
            ids.add(match_id)
            home, away = canon(row.get("home") or ""), canon(row.get("away") or "")
            if not home or not away or home == away:
                raise ValueError(f"Identidad de equipos inválida en {path}:{line}")
            match = {
                "fecha": match_date,
                "local": home,
                "visitante": away,
                "gh": home_goals,
                "ga": away_goals,
            }
            key = _fixture_key(match)
            if key in fixtures:
                raise ValueError(f"Partido duplicado en {path}:{line}: {key}")
            fixtures.add(key)
            matches.append(match)
    return matches


def cargar_statsbomb_2324() -> list[dict]:
    """Carga únicamente el backbone fijado de StatsBomb 2023-24."""
    baseline_path = BASE / "ligaf_resultados_2324_dated.csv"
    baseline = []
    with baseline_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            baseline.append({
                "fecha": datetime.fromisoformat(row["date"]),
                "local": canon(row["local"]),
                "visitante": canon(row["visitante"]),
                "gh": int(row["gh"]),
                "ga": int(row["ga"]),
            })
    baseline.sort(key=lambda item: (item["fecha"], item["local"], item["visitante"]))
    return baseline


def cargar_dated() -> list[dict]:
    """Combina el backbone StatsBomb con resultados multitemporada validados.

    La temporada 2023-24 está presente en ambas fuentes. Se conserva una única
    fila cuando coinciden fecha/equipos/marcador y se falla cerrado ante
    cualquier discrepancia; las temporadas posteriores amplían el histórico.
    """
    supplemental_path = BASE / "liga_f_partidos_2023-27.csv"
    baseline = cargar_statsbomb_2324()

    by_fixture = {}
    for match in baseline:
        key = _fixture_key(match)
        if key in by_fixture:
            raise ValueError(f"Partido duplicado en el backbone StatsBomb: {key}")
        by_fixture[key] = match

    for match in _load_uploaded_results(supplemental_path):
        key = _fixture_key(match)
        if key in by_fixture:
            old = by_fixture[key]
            if (old["gh"], old["ga"]) != (match["gh"], match["ga"]):
                raise ValueError(
                    f"Discrepancia de marcador entre fuentes para {key}: "
                    f"StatsBomb={old['gh']}-{old['ga']}, importado={match['gh']}-{match['ga']}"
                )
            continue
        by_fixture[key] = match

    matches = sorted(by_fixture.values(), key=lambda item: (item["fecha"], item["local"], item["visitante"]))
    return matches


def ajustar(partidos: list[dict]):
    equipos = sorted({p["local"] for p in partidos} | {p["visitante"] for p in partidos})
    idx = {e: i for i, e in enumerate(equipos)}
    nt = len(idx)
    hoy = max(p["fecha"] for p in partidos)
    datos = [(idx[p["local"]], idx[p["visitante"]], p["gh"], p["ga"],
              math.exp(-XI * max((hoy - p["fecha"]).days, 0))) for p in partidos]

    def nll(params):
        mu, gamma = params[0], params[1]
        att, dfn = params[2:2 + nt], params[2 + nt:]
        total = 0.0
        for i, j, gh, ga, w in datos:
            lh = math.exp(mu + gamma + att[i] - dfn[j])
            lv = math.exp(mu + att[j] - dfn[i])
            total += w * ((lh - gh * math.log(lh)) + (lv - ga * math.log(lv)))
        return total + 0.01 * float(np.sum(params[2:] ** 2))

    x0 = np.zeros(2 + 2 * nt)
    x0[0] = math.log(max(0.5, sum(p["gh"] + p["ga"] for p in partidos) / max(1, len(partidos)) / 2))
    x0[1] = 0.25
    result = minimize(nll, x0, method="L-BFGS-B")
    if not result.success or not np.isfinite(result.x).all():
        raise RuntimeError(f"No convergió el ajuste {__name__}: {result.message}")
    params = result.x
    inv = {v: k for k, v in idx.items()}
    ratings = {inv[i]: {"att": float(params[2 + i]), "def": float(params[2 + nt + i])}
               for i in range(nt)}
    return ratings, float(params[0]), float(params[1])


def probs_1x2(lh: float, lv: float) -> tuple[float, float, float]:
    ph = [math.exp(-lh) * lh ** k / math.factorial(k) for k in range(GOLES_MAX + 1)]
    pa = [math.exp(-lv) * lv ** k / math.factorial(k) for k in range(GOLES_MAX + 1)]
    p1 = px = p2 = 0.0
    for h in range(GOLES_MAX + 1):
        for a in range(GOLES_MAX + 1):
            pp = ph[h] * pa[a]
            if h > a:
                p1 += pp
            elif h == a:
                px += pp
            else:
                p2 += pp
    s = p1 + px + p2
    return p1 / s, px / s, p2 / s


def predecir(local: str, visitante: str, ratings: dict, mu: float, gamma: float) -> dict:
    loc, vis = canon(local), canon(visitante)
    fl = loc in ratings
    fv = vis in ratings
    rl = ratings.get(loc, {"att": 0.0, "def": 0.0})
    rv = ratings.get(vis, {"att": 0.0, "def": 0.0})
    lh = math.exp(mu + gamma + rl["att"] - rv["def"])
    lv = math.exp(mu + rv["att"] - rl["def"])
    p1, px, p2 = probs_1x2(lh, lv)
    fuente_l = "fitted_ligaf_history" if fl else "NEUTRO_sin_historial"
    fuente_v = "fitted_ligaf_history" if fv else "NEUTRO_sin_historial"
    signo = ["1", "X", "2"][int(np.argmax([p1, px, p2]))]
    return {"local": local, "visitante": visitante,
            "p1": round(p1, 3), "px": round(px, 3), "p2": round(p2, 3),
            "signo": signo,
            "fuente_ratings": f"{fuente_l} vs {fuente_v}"}


def walkforward(partidos: list[dict]) -> dict:
    """Predice el día completo antes de incorporar cualquiera de sus resultados."""
    aciertos, homes, losses, baseline_losses = [], [], [], []
    season_metrics: dict[str, dict] = {}
    previous: list[dict] = []
    params = None
    last_fit = 0
    ordered = sorted(partidos, key=lambda p: p["fecha"])
    classes = ("1", "X", "2")
    frequencies = [0, 0, 0]

    def observed_index(p: dict) -> int:
        return 0 if p["gh"] > p["ga"] else 1 if p["gh"] == p["ga"] else 2

    for _, group in groupby(ordered, key=lambda p: p["fecha"].date()):
        matches = list(group)
        if len(previous) >= WARMUP:
            if params is None or len(previous) - last_fit >= REFIT_CADA:
                params = ajustar(previous)
                last_fit = len(previous)
            base = [n / len(previous) for n in frequencies]
            for match in matches:
                pred = predecir(match["local"], match["visitante"], *params)
                outcome = observed_index(match)
                probs = [pred["p1"], pred["px"], pred["p2"]]
                aciertos.append(pred["signo"] == classes[outcome])
                homes.append(outcome == 0)
                logloss = -math.log(max(probs[outcome], 1e-12))
                baseline_logloss = -math.log(max(base[outcome], 1e-12))
                losses.append(logloss)
                baseline_losses.append(baseline_logloss)
                season = _season_from_date(match["fecha"])
                metrics = season_metrics.setdefault(
                    season,
                    {"n": 0, "correct": 0, "home_wins": 0, "logloss": 0.0, "baseline_logloss": 0.0},
                )
                metrics["n"] += 1
                metrics["correct"] += int(pred["signo"] == classes[outcome])
                metrics["home_wins"] += int(outcome == 0)
                metrics["logloss"] += logloss
                metrics["baseline_logloss"] += baseline_logloss
        for match in matches:
            frequencies[observed_index(match)] += 1
        previous.extend(matches)

    n = len(aciertos)
    if not n:
        raise ValueError("Histórico insuficiente para el walk-forward diario de Liga F")
    by_season = {
        season: {
            "n_evaluados": metrics["n"],
            "DC_acierto": round(metrics["correct"] / metrics["n"], 4),
            "siempre_1_acierto": round(metrics["home_wins"] / metrics["n"], 4),
            "DC_logloss": round(metrics["logloss"] / metrics["n"], 4),
            "baseline_frecuencias_logloss": round(
                metrics["baseline_logloss"] / metrics["n"], 4
            ),
        }
        for season, metrics in sorted(season_metrics.items())
    }
    return {
        "protocolo": "walk_forward_dias_sin_resultados_del_mismo_dia",
        "n_evaluados": n,
        "DC_acierto": round(sum(aciertos) / n, 4),
        "siempre_1_acierto": round(sum(homes) / n, 4),
        "DC_logloss": round(sum(losses) / n, 4),
        "baseline_frecuencias_logloss": round(sum(baseline_losses) / n, 4),
        "por_temporada": by_season,
    }
