"""Métrica económica del boleto de La Quiniela (P0.1).

Objetivo (auditoría externa 04/08/2026): dejar de medir solo "aciertos" y medir
DINERO. Este módulo calcula, para un desarrollo de boleto (dobles/triples +
simples) y un vector de probabilidades por partido:

  - Coste fijo del boleto (contrato P0: 3 dobles = 8 columnas × 0,75 € = 6,00 €).
  - Distribución EXACTA del nº de aciertos de la mejor columna (convolución de
    Bernoulli independientes), reutilizando la misma maquinaria que
    ``OPTIMIZADOR_COLUMNAS`` para que exista una única fuente de verdad.
  - Probabilidad de premio por categoría P(exactamente k) y P(≥k).
  - Valor esperado (EV) del boleto usando premios medios históricos por categoría.
  - ROI esperado = (EV − coste) / coste.
  - Comparación directa contra el boleto de referencia "solo favoritos de
    mercado" con el MISMO presupuesto.

⚠️  ADVERTENCIA DE HONESTIDAD (imprescindible, la audita el ROADMAP):
    Los importes de premio de La Quiniela son VARIABLES (dependen del bote y del
    número de acertantes de la jornada). El EV que produce este módulo es una
    ESTIMACIÓN con premios medios históricos, NO una garantía. Se etiqueta
    siempre como estimado y los premios usados quedan registrados en la salida.

La probabilidad de acertar una categoría con un boleto de N columnas se calcula
sobre la MEJOR columna (la de mayor cobertura), que es la política real de cobro:
en La Quiniela se cobra por la columna que más aciertos consigue. Con dobles al
favorito + segundo signo, la cobertura por partido es la suma de probabilidades
de los signos jugados, exactamente como en ``coverage_distribution``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import settings  # noqa: E402
import OPTIMIZADOR_COLUMNAS as opt  # noqa: E402  (reutiliza convolución exacta)

# Categorías de premio de La Quiniela (juego principal, sin Pleno al 15, que se
# juega y evalúa aparte según el contrato P0).
PRIZE_CATEGORIES = (14, 13, 12, 11, 10)

# Premios medios históricos ORIENTATIVOS por categoría, en euros. Medianas
# aproximadas a partir de sorteos públicos 2024-2026 (El País, 20minutos, La Bruja
# de Oro, Lottoster). Son variables por jornada; se pueden sobreescribir vía
# CONFIG_MOTOR_V2.json → "economia".prizes_eur o un fichero externo.
DEFAULT_PRIZES_EUR = {
    14: 80000.0,   # 1ª categoría (14 aciertos), sin bote acumulado
    13: 2000.0,    # 2ª categoría
    12: 200.0,     # 3ª categoría
    11: 25.0,      # 4ª categoría
    10: 6.0,       # 5ª categoría
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


def _as_prob_vectors(probs) -> list[np.ndarray]:
    """Normaliza la entrada a una lista de vectores (p1, pX, p2) que suman 1."""
    out: list[np.ndarray] = []
    for p in probs:
        arr = np.asarray(p, dtype=float)
        if arr.shape != (3,):
            raise ValueError(f"Cada partido necesita 3 probabilidades (1,X,2); recibido {arr}")
        s = arr.sum()
        if s <= 0:
            arr = np.full(3, 1 / 3)
        else:
            arr = arr / s
        out.append(arr)
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
    """P(exactamente k) y P(≥k) por categoría de premio a partir de la dist."""
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
    """EV bruto de premios = Σ_k P(exactamente k aciertos) × premio(k).

    La Quiniela paga por la categoría exacta alcanzada (10, 11, 12, 13 o 14),
    no acumulativamente. Por eso se usa P(exactamente k), no P(≥k).
    """
    prizes = prizes or DEFAULT_PRIZES_EUR
    total = len(dist) - 1
    ev = 0.0
    for k in PRIZE_CATEGORIES:
        if k > total:
            continue
        ev += float(dist[k]) * float(prizes.get(k, 0.0))
    return ev


def evaluate_ticket_economics(
    probs,
    selected: list[tuple] | None = None,
    *,
    config: dict | None = None,
    prizes: dict[int, float] | None = None,
    label: str = "modelo",
) -> dict:
    """Evaluación económica completa de un desarrollo de boleto.

    Parameters
    ----------
    probs : lista de 14 vectores (p1, pX, p2).
    selected : desarrollo (lista de (label, signos)). Si es None, se construye
        el desarrollo óptimo de 3 dobles del contrato P0 (o solo-favoritos si
        el contrato no permite dobles).
    prizes : premios por categoría; por defecto los históricos medios.
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

    dist = ticket_hit_distribution(probs, selected)
    ev_gross = expected_prize(dist, prizes)
    cost = float(contract["max_cost"])
    ev_net = ev_gross - cost
    roi = ev_net / cost if cost > 0 else float("nan")

    return {
        "label": label,
        "contrato": contract,
        "coste_eur": cost,
        "premios_usados_eur": {str(k): float(v) for k, v in prizes.items()},
        "premios_estimados": True,
        "nota_premios": (
            "EV ESTIMADO con premios medios históricos (variables por jornada). "
            "No es una garantía."
        ),
        "distribucion_aciertos": {str(k): float(dist[k]) for k in range(len(dist))},
        "esperanza_aciertos": float(sum(k * dist[k] for k in range(len(dist)))),
        "probabilidades_premio": prize_probabilities(dist),
        "ev_premios_eur": float(ev_gross),
        "ev_neto_eur": float(ev_net),
        "roi": float(roi),
    }


def compare_model_vs_market(
    model_probs,
    market_probs,
    *,
    config: dict | None = None,
    prizes: dict[int, float] | None = None,
) -> dict:
    """Compara el boleto del modelo (3 dobles óptimos) contra dos referencias:

      - "mercado_dobles": mismo desarrollo de 3 dobles pero con probabilidades
        de mercado (¿el modelo elige mejores dobles que el mercado?).
      - "solo_favoritos_mercado": 14 simples al favorito de mercado (una única
        columna). Es el boleto trivial de mínimo coste conceptual; se escala su
        coste al del contrato para comparar EV por euro de forma justa.

    Todas las evaluaciones usan como VERDAD la distribución de aciertos inducida
    por las probabilidades reales de cada partido; para una evaluación honesta,
    ``model_probs`` y ``market_probs`` deben ser probabilidades bien calibradas.
    """
    prizes = prizes if prizes is not None else load_prizes(config)

    modelo = evaluate_ticket_economics(
        model_probs, config=config, prizes=prizes, label="modelo_3_dobles"
    )

    market_probs_v = _as_prob_vectors(market_probs)
    fav_selected = _favorite_development(market_probs_v)
    solo_fav = evaluate_ticket_economics(
        market_probs_v,
        selected=fav_selected,
        config=config,
        prizes=prizes,
        label="solo_favoritos_mercado",
    )

    return {
        "modelo": modelo,
        "solo_favoritos_mercado": solo_fav,
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
