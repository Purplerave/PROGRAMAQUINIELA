"""Escenarios económicos 1X2, sin Pleno, con premios supuestos.

La convolución del desarrollo da los aciertos de su mejor columna. Sirve para
P(al menos una columna alcanza k), no para calcular el pago total. El valor
esperado suma las categorías exactas de **cada** columna; la linealidad de la
esperanza permite sumarlas aunque las columnas compartan selecciones.

Se presupone independencia entre partidos y un importe fijo por categoría.
Los importes por defecto son escenarios orientativos, no escrutinios oficiales
ni medias contrastadas. Se informa del coste de las columnas efectivas.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import settings
import OPTIMIZADOR_COLUMNAS as opt

# Categorías de premio de La Quiniela (juego principal, sin Pleno al 15, que se
# juega y evalúa aparte según el contrato P0).
PRIZE_CATEGORIES = (14, 13, 12, 11, 10)

# Premios ORIENTATIVOS por categoría, en euros. Puntos medios del escenario
# "normal" del escenario orientativo de La Quiniela española.
# Son variables por jornada; se pueden sobreescribir vía
# CONFIG_MOTOR_V2.json → "economia".prizes_eur o un fichero externo.
DEFAULT_PRIZES_EUR = {
    14: 40000.0,   # 1ª categoría (14 aciertos)
    13: 500.0,     # 2ª categoría
    12: 35.0,      # 3ª categoría
    11: 5.5,       # 4ª categoría
    10: 2.25,      # 5ª categoría
}

# Escenarios de premio (puntos medios de los rangos manus.ai): fácil = muchos
# acertantes (premios bajos), normal = media histórica, difícil = sorpresas/botes
# (premios altos). Permiten análisis de sensibilidad del EV/ROI en vez de un único
# número frágil. Se pueden sobreescribir vía economia.escenarios_premios_eur.
DEFAULT_SCENARIOS_EUR = {
    "facil":   {14: 3250.0,   13: 45.0,   12: 6.0,   11: 1.5,  10: 0.0},
    "normal":  {14: 40000.0,  13: 500.0,  12: 35.0,  11: 5.5,  10: 2.25},
    "dificil": {14: 150000.0, 13: 6000.0, 12: 500.0, 11: 45.0, 10: 10.0},
}


def load_prizes(config: dict | None = None) -> dict[int, float]:
    """Premios por categoría desde config/fichero, con defaults documentados.

    Prioridad: CONFIG_MOTOR_V2.json → economia.prizes_eur; si no, defaults.
    Acepta claves int o str ("14", "13", ...).
    """
    cfg = config if config is not None else settings.CONFIG
    econ = cfg.get("economia", {}) if isinstance(cfg, dict) else {}
    raw = econ.get("prizes_eur") if isinstance(econ, dict) else None
    prizes = dict(DEFAULT_PRIZES_EUR)
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                prizes[int(k)] = float(v)
            except (TypeError, ValueError):
                continue
    return prizes


def load_scenarios(config: dict | None = None) -> dict[str, dict[int, float]]:
    """Escenarios de premio (fácil/normal/difícil) desde config, con defaults.

    Prioridad: CONFIG_MOTOR_V2.json → economia.escenarios_premios_eur; si no,
    DEFAULT_SCENARIOS_EUR. Cada escenario es {categoria: premio_eur}.
    """
    cfg = config if config is not None else settings.CONFIG
    econ = cfg.get("economia", {}) if isinstance(cfg, dict) else {}
    raw = econ.get("escenarios_premios_eur") if isinstance(econ, dict) else None
    scenarios = {k: dict(v) for k, v in DEFAULT_SCENARIOS_EUR.items()}
    if isinstance(raw, dict):
        for name, table in raw.items():
            if not isinstance(table, dict):
                continue
            parsed = {}
            for k, v in table.items():
                try:
                    parsed[int(k)] = float(v)
                except (TypeError, ValueError):
                    continue
            if parsed:
                scenarios[name] = parsed
    return scenarios


def default_scenario_name(config: dict | None = None) -> str:
    cfg = config if config is not None else settings.CONFIG
    econ = cfg.get("economia", {}) if isinstance(cfg, dict) else {}
    return str(econ.get("escenario_por_defecto", "normal")) if isinstance(econ, dict) else "normal"


def _as_prob_vectors(probs) -> list[np.ndarray]:
    """Normaliza la entrada a una lista de vectores (p1, pX, p2) que suman 1."""
    out: list[np.ndarray] = []
    for p in probs:
        arr = np.asarray(p, dtype=float)
        if arr.shape != (3,):
            raise ValueError(f"Cada partido necesita 3 probabilidades (1,X,2); recibido {arr}")
        total = arr.sum()
        if not np.isfinite(arr).all() or (arr < 0).any() or not math.isfinite(total) or total <= 0:
            raise ValueError("Cada vector 1X2 debe tener masa finita, no negativa y suma positiva")
        out.append(arr / total)
    return out


def ticket_hit_distribution(probs, selected: list[tuple]) -> np.ndarray:
    """Distribución exacta P(k aciertos) de la mejor columna del desarrollo.

    Delega en ``OPTIMIZADOR_COLUMNAS.coverage_distribution`` (convolución exacta)
    para garantizar una única fuente de verdad con el optimizador.
    """
    probs = _as_prob_vectors(probs)
    return opt.coverage_distribution(probs, selected)


def _favorite_development(probs) -> list[tuple]:
    """Desarrollo de referencia "solo favoritos": 14 simples al favorito.

    Sin dobles: una única columna con el signo más probable de cada partido.
    """
    probs = _as_prob_vectors(probs)
    selected: list[tuple] = []
    for p in probs:
        best = opt.SIGNS[int(np.argmax(p))]
        selected.append((best, (best,)))
    return selected


def prize_probabilities(dist: np.ndarray) -> dict:
    """Categoría exacta de la mejor columna y probabilidad de que alcance al menos k."""
    total = len(dist) - 1
    exact = {}
    at_least = {}
    for k in PRIZE_CATEGORIES:
        if k > total:
            continue
        exact[k] = float(dist[k])
        at_least[k] = float(dist[k:].sum())
    return {"exacto": exact, "acumulado_ge": at_least}


def expected_prize(dist: np.ndarray, prizes: dict[int, float] | None = None) -> float:
    """Multiplica los recuentos esperados de cada categoría exacta por su premio.

    Una distribución normalizada representa una columna. Para un boleto,
    ``dist`` es la suma de las distribuciones de todas las columnas.
    """
    prizes = DEFAULT_PRIZES_EUR if prizes is None else prizes
    total = len(dist) - 1
    ev = 0.0
    for k in PRIZE_CATEGORIES:
        if k > total:
            continue
        amount = float(prizes.get(k, 0.0))
        if not math.isfinite(amount) or amount < 0:
            raise ValueError(f"Premio supuesto inválido para {k} aciertos")
        ev += float(dist[k]) * amount
    return ev


def ev_by_scenario(
    dist: np.ndarray,
    *,
    config: dict | None = None,
    cost: float | None = None,
    scenarios: dict[str, dict[int, float]] | None = None,
) -> dict:
    """EV y ROI del boleto bajo cada escenario de premio (fácil/normal/difícil).

    Devuelve un análisis de sensibilidad: en vez de un único EV frágil, un
    intervalo según la liquidez de la jornada. `cost` por defecto = contrato P0.
    """
    scenarios = scenarios if scenarios is not None else load_scenarios(config)
    if cost is None:
        cost = float(opt.columns_contract(config)["max_cost"])
    out = {}
    for name, prizes in scenarios.items():
        ev = expected_prize(dist, prizes)
        out[name] = {
            "premios_eur": {str(k): float(v) for k, v in prizes.items()},
            "ev_premios_eur": float(ev),
            "ev_neto_eur": float(ev - cost),
            "roi": float((ev - cost) / cost) if cost > 0 else float("nan"),
        }
    return out


def evaluate_ticket_economics(
    probs,
    selected: list[tuple] | None = None,
    *,
    config: dict | None = None,
    prizes: dict[int, float] | None = None,
    label: str = "modelo",
) -> dict:
    """Simulación económica de un desarrollo de boleto.

    Parameters
    ----------
    probs : lista de 14 vectores (p1, pX, p2).
    selected : desarrollo (lista de (label, signos)). Si es None, se construye
        el desarrollo óptimo de 3 dobles del contrato P0 (o solo-favoritos si
        el contrato no permite dobles).
    prizes : hipótesis de premios por categoría, no importes observados.
    """
    probs = _as_prob_vectors(probs)
    contract = opt.columns_contract(config)
    prizes = prizes if prizes is not None else load_prizes(config)

    if selected is None:
        n_doubles = int(contract["doubles"])
        if n_doubles > 0 and len(probs) >= n_doubles:
            best = opt.evaluate_all_three_doubles(probs, n_doubles=n_doubles)
            combo = tuple(best["mejor_combinacion"]["dobles"])
            selected = opt.build_double_development(probs, combo)
        else:
            selected = _favorite_development(probs)

    if not 1 <= len(probs) <= 14 or len(selected) != len(probs):
        raise ValueError("El desarrollo debe tener entre 1 y 14 posiciones, una por vector 1X2")
    if any(not signs or len(set(signs)) != len(signs) or not set(signs) <= set(opt.SIGNS)
           for _, signs in selected):
        raise ValueError("El desarrollo necesita signos 1X2 únicos en cada posición")
    n_columns = math.prod(len(signs) for _, signs in selected)
    if not 1 <= n_columns <= contract["columns_per_ticket"]:
        raise ValueError("El desarrollo supera el contrato de columnas")
    dist = opt.coverage_distribution(probs, selected)
    expected_counts = sum(
        (opt.coverage_distribution(probs, [(s, (s,)) for s in col]) for col in opt.enumerate_columns(selected)),
        start=np.zeros(len(probs) + 1),
    )
    ev_gross = expected_prize(expected_counts, prizes)
    cost = contract["price_per_column"] * n_columns
    ev_net = ev_gross - cost
    roi = ev_net / cost if cost > 0 else float("nan")

    return {
        "label": label,
        "contrato": contract,
        "coste_eur": cost,
        "n_columnas": n_columns,
        "retorno_realizado": False,
        "premios_usados_eur": {str(k): float(v) for k, v in prizes.items()},
        "premios_estimados": True,
        "nota_premios": (
            "EV ESTIMADO de todas las columnas con premios supuestos. "
            "No es un ROI realizado ni una garantía."
        ),
        "distribucion_aciertos": {str(k): float(dist[k]) for k in range(len(dist))},
        "esperanza_aciertos": float(sum(k * dist[k] for k in range(len(dist)))),
        "probabilidades_premio": prize_probabilities(dist),
        "ev_premios_eur": float(ev_gross),
        "ev_neto_eur": float(ev_net),
        "columnas_esperadas_por_aciertos": {str(k): float(expected_counts[k]) for k in range(len(expected_counts))},
        "roi": float(roi),
        "escenario_por_defecto": default_scenario_name(config),
        "ev_por_escenario": ev_by_scenario(expected_counts, config=config, cost=cost),
    }


def compare_model_vs_market(
    model_probs,
    market_probs,
    *,
    config: dict | None = None,
    prizes: dict[int, float] | None = None,
) -> dict:
    """Contrasta dos desarrollos bajo los mismos supuestos probabilísticos.

    Los favoritos se seleccionan con mercado y se evalúan, como el resto, bajo
    ``model_probs``. Se comparan sus costes efectivos (8 vs 1 por defecto),
    no dos estrategias al mismo presupuesto ni rendimientos observados.
    """
    prizes = prizes if prizes is not None else load_prizes(config)

    model_probs = _as_prob_vectors(model_probs)
    if len(model_probs) != len(market_probs := _as_prob_vectors(market_probs)):
        raise ValueError("Modelo y mercado deben cubrir la misma cantidad de partidos")
    modelo = evaluate_ticket_economics(
        model_probs, config=config, prizes=prizes, label="modelo_3_dobles"
    )

    fav_selected = _favorite_development(market_probs)
    solo_fav = evaluate_ticket_economics(
        model_probs,
        selected=fav_selected,
        config=config,
        prizes=prizes,
        label="solo_favoritos_mercado",
    )

    return {
        "modelo": modelo,
        "solo_favoritos_mercado": solo_fav,
        "evaluado_bajo": "probabilidades_modelo_no_validadas_como_verdad",
        "presupuestos_equivalentes": modelo["n_columnas"] == solo_fav["n_columnas"],
        "delta_ev_neto_eur": modelo["ev_neto_eur"] - solo_fav["ev_neto_eur"],
        "delta_roi": modelo["roi"] - solo_fav["roi"],
        "delta_p_ge_12": (
            modelo["probabilidades_premio"]["acumulado_ge"].get(12, 0.0)
            - solo_fav["probabilidades_premio"]["acumulado_ge"].get(12, 0.0)
        ),
    }


def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Demostración de la métrica económica del boleto (P0.1)."
    )
    parser.add_argument(
        "--demo", action="store_true", help="Ejecuta un ejemplo con 14 partidos ficticios"
    )
    args = parser.parse_args()

    if args.demo:
        rng = np.random.default_rng(42)
        probs = []
        for _ in range(14):
            v = rng.dirichlet([4, 3, 3])
            probs.append(v)
        result = evaluate_ticket_economics(probs)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()
