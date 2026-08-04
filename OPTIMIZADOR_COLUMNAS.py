"""OPTIMIZADOR_COLUMNAS.py — Construcción global del boleto de La Quiniela.

Contrato de columnas (P0, auditoría externa 04/08/2026, `CONFIG_MOTOR_V2.json`):

    - 3 dobles sobre los 14 partidos del bloque principal.
    - 8 columnas (2^3).
    - 0,75 EUR por columna.
    - Coste máximo del boleto: 6,00 EUR.
    - El Pleno al 15 se mantiene separado (signo 1X2 + marcador por buckets).

Método de selección:

    1. Se evalúan EXHAUSTIVAMENTE las C(14, 3) = 364 combinaciones posibles
       de tres dobles sobre los 14 partidos principales.
    2. Para cada combinación se construye el desarrollo (3 dobles con los dos
       signos más probables + 11 simples con el favorito) y se calcula su
       acierto esperado:  E[aciertos] = sum_i P(acierto del partido i).
       Como sumar un doble al favorito del partido i añade exactamente la
       probabilidad del segundo signo más probable, maximizar E[aciertos] es
       equivalente a seleccionar por SEGUNDA PROBABILIDAD. El ranking de las
       364 combinaciones por E[aciertos] y por suma de segunda probabilidad
       es idéntico.
    3. Se selecciona la combinación con mayor acierto esperado (desempate:
       primera combinación en orden lexicográfico, resultado determinista).
    4. Para la combinación ganadora (y para cada una de las 364) se calculan
       EXACTAMENTE P(≥10), P(≥11), P(≥12), P(≥13) y P(≥14) mediante la
       convolución exacta de las distribuciones Bernoulli independientes por
       partido (sin Monte Carlo).
    5. El Pleno al 15 se excluye del desarrollo y se juega como simple del
       favorito (1X2), separado del marcador.

Entradas (CLI):

    --jornada N            JSON con los partidos (DATOS/QUINIELA15_J{N}.json)
    --probabilidades FILE  JSON con probabilidades del modelo (opcional)
    --fuente-prob q15|lae|apu|modelo   de dónde salen las probabilidades 1/X/2
    --publico lae|apu|q15  fuente de popularidad del público (por defecto: lae)
    --alpha VAL            exponente de valor anti-popularidad (solo ranking
                           de las 8 columnas por valor; no afecta al desarrollo)
    --pleno-num N          nº del partido de Pleno al 15 (0 = no excluir ninguno)
    --n-sims N             simulaciones del Monte Carlo comparativo

Uso como módulo (T2):

    from OPTIMIZADOR_COLUMNAS import optimize_jornada
    payload = optimize_jornada(74, fuente_prob="q15", publico="lae")
    # payload["desarrollo"]: 3 dobles + 11 simples (8 columnas, 6,00 EUR)
    # payload["probabilidades_exactas"]: P(>=10) ... P(>=14)
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import settings

SIGNS = ("1", "X", "2")
SIGN_INDEX = {s: i for i, s in enumerate(SIGNS)}
EPS = 1e-12

# Categorías exigidas por la auditoría: P(≥10) ... P(≥14) sobre 14 partidos.
TAIL_THRESHOLDS = (10, 11, 12, 13, 14)


def columns_contract(config: dict | None = None) -> dict:
    """Contrato de columnas validado a partir de `CONFIG_MOTOR_V2.json`.

    Elimina la ambigüedad previa entre `default_budget` y `beam_size`: el
    boleto queda fijado por {doubles, columns_per_ticket, price_per_column,
    max_cost}. Valida las identidades 2^doubles == columns_per_ticket y
    columns_per_ticket * price_per_column == max_cost.
    """
    section = (config if config is not None else settings.CONFIG).get("columns", {})
    doubles = int(section.get("doubles", 3))
    columns = int(section.get("columns_per_ticket", 2 ** doubles))
    price = float(section.get("price_per_column", 0.75))
    max_cost = float(section.get("max_cost", columns * price))
    if 2 ** doubles != columns:
        raise ValueError(
            f"Contrato de columnas inconsistente: 2^{doubles} = {2 ** doubles} "
            f"!= columns_per_ticket = {columns}"
        )
    if abs(columns * price - max_cost) > 1e-9:
        raise ValueError(
            f"Contrato de columnas inconsistente: {columns} * {price} = "
            f"{columns * price} != max_cost = {max_cost}"
        )
    return {
        "contract_version": str(section.get("contract_version", "2026-08-04")),
        "doubles": doubles,
        "columns_per_ticket": columns,
        "price_per_column": price,
        "max_cost": max_cost,
    }


def pct_to_prob(values: dict | None) -> np.ndarray | None:
    """Convierte {signo: porcentaje} en probabilidades normalizadas (1,X,2)."""
    if not values:
        return None
    out = []
    for s in SIGNS:
        raw = values.get(s)
        if raw is None:
            return None
        try:
            out.append(float(raw))
        except (TypeError, ValueError):
            return None
    total = sum(out)
    if total <= 0:
        return None
    return np.array(out) / total


def publico_per_match(partidos: list[dict], fuente: str) -> list[np.ndarray]:
    return [pct_to_prob(m.get(fuente)) for m in partidos]


def fill_missing(probs: list[np.ndarray | None]) -> list[np.ndarray]:
    """Rellena probabilidades ausentes con la distribución uniforme."""
    return [p if p is not None else np.full(3, 1 / 3) for p in probs]


def second_probability(p: np.ndarray) -> float:
    """Probabilidad del segundo signo más probable de un partido."""
    return float(np.sort(np.asarray(p, dtype=float))[-2])


def second_probabilities(probs: list[np.ndarray]) -> np.ndarray:
    """Segunda probabilidad de cada partido (criterio de selección de dobles)."""
    return np.array([second_probability(p) for p in probs], dtype=float)


def three_double_combinations(n_matches: int, n_doubles: int = 3) -> list[tuple[int, ...]]:
    """Todas las combinaciones posibles de n_doubles dobles sobre n_matches.

    Para 14 partidos y 3 dobles devuelve exactamente C(14, 3) = 364
    combinaciones, en orden lexicográfico determinista.
    """
    if n_matches < n_doubles:
        raise ValueError(
            f"Se necesitan al menos {n_doubles} partidos para {n_doubles} dobles "
            f"(hay {n_matches})."
        )
    return list(itertools.combinations(range(n_matches), n_doubles))


def build_double_development(
    probs: list[np.ndarray], double_indices: tuple[int, ...]
) -> list[tuple[str, tuple[str, ...]]]:
    """Desarrollo para una combinación dada: dobles con los 2 signos más
    probables y simples con el favorito en el resto de partidos.

    Devuelve una lista de (label, signos) alineada con `probs`.
    """
    selected: list[tuple[str, tuple[str, ...]]] = []
    for i, p in enumerate(probs):
        if i in double_indices:
            top2 = [int(j) for j in np.argsort(p)[-2:]]
            signs = tuple(sorted((SIGNS[j] for j in top2), key=lambda s: SIGN_INDEX[s]))
            label = "".join(signs)
        else:
            best = SIGNS[int(np.argmax(p))]
            signs = (best,)
            label = best
        selected.append((label, signs))
    return selected


def coverage_distribution(probs: list[np.ndarray], selected: list[tuple]) -> np.ndarray:
    """Distribución EXACTA de P(k aciertos del desarrollo) para k=0..n.

    Cada partido contribuye una Bernoulli independiente con probabilidad de
    acierto igual a la cobertura del desarrollo (suma de probabilidades de los
    signos jugados). La convolución exacta de las 14 Bernoulli produce la
    distribución de aciertos sin aproximación.
    """
    dist = np.array([1.0])
    for i, (_, signs) in enumerate(selected):
        hit = float(sum(probs[i][SIGN_INDEX[s]] for s in signs))
        new = np.zeros(len(dist) + 1)
        new[:-1] += dist * (1.0 - hit)
        new[1:] += dist * hit
        dist = new
    return dist


def exact_tail_probabilities(dist: np.ndarray) -> dict[str, float]:
    """P(≥k) exactas a partir de la distribución de aciertos (convolución)."""
    total = len(dist) - 1
    out: dict[str, float] = {}
    for k in TAIL_THRESHOLDS:
        if k > total:
            continue
        out[f"p_ge_{k}"] = float(dist[k:].sum())
    return out


def expected_hits(probs: list[np.ndarray], selected: list[tuple]) -> float:
    """E[aciertos] = suma de las coberturas por partido del desarrollo."""
    return float(
        sum(
            probs[i][SIGN_INDEX[s]]
            for i, (_, signs) in enumerate(selected)
            for s in signs
        )
    )


def evaluate_development(
    probs: list[np.ndarray], selected: list[tuple], double_indices: tuple[int, ...]
) -> dict:
    """Métricas exactas de un desarrollo: E[aciertos], suma de segunda
    probabilidad de los dobles y P(≥10) ... P(≥14)."""
    dist = coverage_distribution(probs, selected)
    segunda = float(sum(second_probabilities(probs)[i] for i in double_indices))
    return {
        "dobles": list(double_indices),
        "n_columnas": int(2 ** len(double_indices)),
        "aciertos_esperados": expected_hits(probs, selected),
        "suma_segunda_probabilidad": segunda,
        "probabilidades_exactas": exact_tail_probabilities(dist),
        "distribucion_aciertos": {str(k): float(dist[k]) for k in range(len(dist))},
    }


def evaluate_all_three_doubles(
    probs: list[np.ndarray], n_doubles: int = 3
) -> dict:
    """Evalúa exhaustivamente las C(14, n_doubles) combinaciones de dobles.

    Para cada combinación calcula E[aciertos] (equivalente a la suma de
    segunda probabilidad de los dobles) y las P(≥k) exactas. Selecciona la
    combinación con mayor acierto esperado; los empates se resuelven a favor
    de la primera combinación en orden lexicográfico (determinista).
    """
    combos = three_double_combinations(len(probs), n_doubles)
    results = []
    for combo in combos:
        selected = build_double_development(probs, combo)
        metrics = evaluate_development(probs, selected, combo)
        metrics["desarrollo"] = selected
        results.append(metrics)

    # `max` devuelve el primer máximo: con combos en orden lexicográfico el
    # desempate es determinista.
    best = max(results, key=lambda r: r["aciertos_esperados"])
    return {
        "n_combinaciones": len(results),
        "criterio": (
            "maximizar aciertos esperados = suma(P(favorito)) + suma(segunda "
            "probabilidad de los dobles); ranking identico al de la suma de "
            "segunda probabilidad"
        ),
        "mejor_combinacion": {
            "dobles": best["dobles"],
            "aciertos_esperados": best["aciertos_esperados"],
            "suma_segunda_probabilidad": best["suma_segunda_probabilidad"],
            "probabilidades_exactas": best["probabilidades_exactas"],
        },
        "top_10": [
            {
                "dobles": r["dobles"],
                "aciertos_esperados": r["aciertos_esperados"],
                "suma_segunda_probabilidad": r["suma_segunda_probabilidad"],
            }
            for r in sorted(results, key=lambda r: r["aciertos_esperados"], reverse=True)[:10]
        ],
        "ranking_completo": [
            {
                "dobles": r["dobles"],
                "aciertos_esperados": r["aciertos_esperados"],
                "suma_segunda_probabilidad": r["suma_segunda_probabilidad"],
                "probabilidades_exactas": r["probabilidades_exactas"],
            }
            for r in sorted(results, key=lambda r: r["aciertos_esperados"], reverse=True)
        ],
    }


def enumerate_columns(selected: list[tuple]) -> list[tuple[str, ...]]:
    """Todas las columnas del desarrollo (producto cartesiano de signos)."""
    per_match = [list(signs) for _, signs in selected]
    return list(itertools.product(*per_match))


def column_value(col: tuple[str, ...], probs: list[np.ndarray], public: list[np.ndarray], alpha: float) -> float:
    lp = sum(math.log(np.clip(probs[i][SIGN_INDEX[s]], EPS, 1.0)) for i, s in enumerate(col))
    lq = sum(math.log(np.clip(public[i][SIGN_INDEX[s]], EPS, 1.0)) for i, s in enumerate(col))
    return lp - alpha * lq


# --- Estrategias de referencia (solo comparativa) -----------------------------

def dev_singles(probs: list[np.ndarray]) -> list[tuple]:
    """Desarrollo de simples con el favorito de cada fuente."""
    return [tuple([SIGNS[int(np.argmax(p))]]) for p in probs]


def dev_from_field(partidos: list[dict], field: str) -> list[tuple] | None:
    """Desarrollo de simples a partir de un campo de la jornada ('sistema', 'comunidad')."""
    out = []
    for m in partidos:
        v = m.get(field)
        if v not in SIGNS:
            return None
        out.append((v,))
    return out


def monte_carlo(
    probs: list[np.ndarray],
    developments: dict[str, list[tuple]],
    column_sets: dict[str, list[tuple[str, ...]]],
    n_sims: int = 20000,
    seed: int = 42,
) -> dict[str, dict[str, float]]:
    """Simula jornadas y mide la distribución del mejor acierto de cada estrategia."""
    rng = np.random.default_rng(seed)
    n_matches = len(probs)
    results = np.zeros((n_sims, n_matches), dtype=int)
    for j, p in enumerate(probs):
        results[:, j] = rng.choice(3, size=n_sims, p=p)

    out: dict[str, dict[str, float]] = {}
    for name, sets in developments.items():
        hits = np.zeros(n_sims, dtype=int)
        for j, allowed in enumerate(sets):
            hits += np.isin(results[:, j], [SIGN_INDEX[s] for s in allowed])
        out[name] = summarize_hits(hits, n_matches)
    for name, cols in column_sets.items():
        if not cols:
            continue
        mat = np.array([[SIGN_INDEX[s] for s in col] for col in cols])
        best = np.zeros(n_sims, dtype=int)
        for c in range(mat.shape[0]):
            best = np.maximum(best, (results == mat[c]).sum(axis=1))
        out[name] = summarize_hits(best, n_matches)
    return out


def summarize_hits(hits: np.ndarray, total: int) -> dict[str, float]:
    return {
        "esperanza": float(hits.mean()),
        "p_15": float((hits == total).mean()),
        "p_14": float((hits >= total - 1).mean()),
        "p_13": float((hits >= total - 2).mean()),
        "p_12": float((hits >= total - 3).mean()),
        "p_11": float((hits >= total - 4).mean()),
        "p_10": float((hits >= total - 5).mean()),
    }


def render_ticket(partidos: list[dict], selected: list[tuple]) -> str:
    lines = []
    for m, (label, signs) in zip(partidos, selected):
        local = str(m.get("local", "?"))
        visit = str(m.get("visitante", "?"))
        row = "".join("X" if s in signs else "." for s in ("1", "X", "2"))
        lines.append(f"  {m.get('num', '?'):>2}  {local:<22} vs {visit:<22}  [{row}]  ({label})")
    return "\n".join(lines)


# --- Núcleo reutilizable (T2) -------------------------------------------------

def _prob_for(match: dict, fuente_prob: str, override: dict | None) -> np.ndarray | None:
    """Probabilidades de un partido: override (modelo) > fuente_prob > None."""
    num = match.get("num")
    if override and num in override:
        p = override[num]
        if isinstance(p, dict) and all(s in p for s in SIGNS):
            return pct_to_prob(p)
    return pct_to_prob(match.get(fuente_prob))


def _optimize_partidos(
    partidos: list[dict],
    *,
    jornada: int,
    fuente_prob: str = "q15",
    publico: str = "lae",
    alpha: float = 0.6,
    pleno_num: int = 15,
    probs_override: dict | None = None,
    n_sims: int = 20000,
) -> dict:
    """Optimiza el boleto de una lista de partidos bajo el contrato de columnas.

    - Los 14 partidos del bloque principal se cubren con 3 dobles (evaluación
      exhaustiva de las 364 combinaciones) y 11 simples: 8 columnas en total.
    - El Pleno al 15 (pleno_num) se excluye del desarrollo y se juega aparte.
    """
    contract = columns_contract()
    main_matches = [m for m in partidos if m.get("num") != pleno_num] or partidos
    pleno_match = next((m for m in partidos if m.get("num") == pleno_num), None)

    probs = fill_missing([_prob_for(m, fuente_prob, probs_override) for m in main_matches])
    public = fill_missing(publico_per_match(main_matches, publico))

    exhaustive = evaluate_all_three_doubles(probs, n_doubles=contract["doubles"])
    best_combo = tuple(exhaustive["mejor_combinacion"]["dobles"])
    selected = build_double_development(probs, best_combo)
    best_metrics = evaluate_development(probs, selected, best_combo)
    dist = coverage_distribution(probs, selected)

    n_columns = contract["columns_per_ticket"]
    cost = n_columns * contract["price_per_column"]

    all_cols = enumerate_columns(selected)
    # Las 8 columnas del boleto, ordenadas por valor (anti-popularidad).
    ranked_cols = sorted(
        all_cols, key=lambda c: column_value(c, probs, public, alpha), reverse=True
    )

    dev_sistema = dev_from_field(main_matches, "sistema")
    dev_comunidad = dev_from_field(main_matches, "comunidad")
    developments: dict[str, list[tuple]] = {
        "Boleto modelo (favoritos)": dev_singles(probs),
        "Boleto popular (público)": dev_singles(public),
        "Boleto optimizado (3 dobles)": [s for _, s in selected],
    }
    if dev_sistema:
        developments["Boleto sistema quiniela15"] = dev_sistema
    if dev_comunidad:
        developments["Boleto comunidad"] = dev_comunidad
    column_sets: dict[str, list[tuple[str, ...]]] = {
        "8 columnas del boleto": all_cols,
    }
    sims = monte_carlo(probs, developments, column_sets, n_sims=n_sims)

    pleno_info = None
    if pleno_match is not None:
        pp = fill_missing([_prob_for(pleno_match, fuente_prob, probs_override)])[0]
        pleno_sign = SIGNS[int(np.argmax(pp))]
        pleno_info = {
            "num": pleno_match.get("num"),
            "signo": pleno_sign,
            "prob_favorito": round(float(np.max(pp)), 4),
        }

    return {
        "jornada": jornada,
        "fuente_prob": fuente_prob,
        "publico": publico,
        "contrato": contract,
        "n_dobles": contract["doubles"],
        "n_columnas": n_columns,
        "coste_euros": round(cost, 2),
        "aciertos_esperados": best_metrics["aciertos_esperados"],
        "desarrollo": [
            {
                "num": m.get("num"),
                "signos": list(s),
                "label": l,
                "segunda_probabilidad": round(second_probability(p), 4),
            }
            for m, (l, s), p in zip(main_matches, selected, probs)
        ],
        "pleno15": pleno_info,
        "probabilidades_exactas": best_metrics["probabilidades_exactas"],
        "distribucion_aciertos": best_metrics["distribucion_aciertos"],
        "evaluacion_exhaustiva": exhaustive,
        "monte_carlo": sims,
        "columnas_top": [list(c) for c in ranked_cols],
    }


def optimize_jornada(
    jornada: int,
    *,
    fuente_prob: str = "q15",
    publico: str = "lae",
    alpha: float = 0.6,
    pleno_num: int = 15,
    probs_override: dict | None = None,
    n_sims: int = 20000,
) -> dict:
    """Optimiza el boleto de una jornada completa (14 partidos + pleno aparte).

    El contrato de columnas es FIJO (3 dobles = 8 columnas = 6,00 EUR) y se
    lee de `CONFIG_MOTOR_V2.json`; no hay presupuesto configurable.

    probs_override: dict {num_partido: {"1": p1, "X": px, "2": p2}} con las
    probabilidades del modelo (si se proporcionan, tienen prioridad sobre
    fuente_prob).
    """
    path = settings.DATOS_DIR / f"QUINIELA15_J{jornada}.json"
    if not path.exists():
        raise FileNotFoundError(f"No existe {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return _optimize_partidos(
        data["partidos"], jornada=jornada, fuente_prob=fuente_prob, publico=publico,
        alpha=alpha, pleno_num=pleno_num, probs_override=probs_override,
        n_sims=n_sims,
    )


# --- CLI ----------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Optimizador de boletos de La Quiniela (contrato: 3 dobles = 8 columnas = 6,00 EUR)"
    )
    parser.add_argument("--jornada", type=int, required=True, help="número de jornada (DATOS/QUINIELA15_J{N}.json)")
    parser.add_argument("--probabilidades", type=str, default=None, help="JSON con probabilidades del modelo (opcional)")
    parser.add_argument("--fuente-prob", choices=("q15", "lae", "apu", "modelo"), default="q15")
    parser.add_argument("--publico", choices=("lae", "apu", "q15"), default="lae")
    parser.add_argument("--alpha", type=float, default=0.6, help="exponente de valor anti-popularidad (solo ranking de columnas)")
    parser.add_argument("--pleno-num", type=int, default=15, help="nº del partido de Pleno al 15 (0 = no excluir ninguno)")
    parser.add_argument("--n-sims", type=int, default=20000)
    args = parser.parse_args()

    override = None
    if args.probabilidades:
        probs_file = Path(args.probabilidades)
        if not probs_file.exists():
            raise FileNotFoundError(f"No existe {probs_file}")
        with open(probs_file, encoding="utf-8") as fh:
            prob_data = json.load(fh)
        items = prob_data if isinstance(prob_data, list) else prob_data.get("partidos", [])
        override = {}
        for i, item in enumerate(items, start=1):
            if isinstance(item, dict):
                inner = item.get("probabilidades", item)
                if isinstance(inner, dict):
                    override[i] = inner

    payload = optimize_jornada(
        args.jornada, fuente_prob=args.fuente_prob, publico=args.publico,
        alpha=args.alpha, pleno_num=args.pleno_num,
        probs_override=override or None, n_sims=args.n_sims,
    )

    contract = payload["contrato"]
    partidos = json.loads(
        (settings.DATOS_DIR / f"QUINIELA15_J{args.jornada}.json").read_text(encoding="utf-8")
    )["partidos"]
    main_matches = [m for m in partidos if m.get("num") != args.pleno_num] or partidos
    selected = [(d["label"], tuple(d["signos"])) for d in payload["desarrollo"]]

    print("=" * 82)
    print(f"OPTIMIZADOR DE BOLETOS — jornada {args.jornada}  (prob: {payload['fuente_prob']} | público: {payload['publico']})")
    print("=" * 82)
    print(
        f"Contrato: {contract['doubles']} dobles = {contract['columns_per_ticket']} columnas "
        f"a {contract['price_per_column']:.2f} EUR = {contract['max_cost']:.2f} EUR max. "
        f"(v{contract['contract_version']})"
    )
    print(f"\nDesarrollo recomendado ({payload['n_columnas']} columnas, {payload['coste_euros']:.2f} EUR, "
          f"E[aciertos]={payload['aciertos_esperados']:.4f}):")
    print(render_ticket(main_matches, selected))
    if payload.get("pleno15"):
        p15 = payload["pleno15"]
        print(f"  Pleno al 15 (partido {p15['num']}): signo {p15['signo']} (prob. favorito {p15['prob_favorito']:.1%}) — separado del desarrollo")

    top = payload.get("columnas_top", [])
    if top:
        print(f"\nLas {len(top)} columnas del boleto por valor (anti-popularidad):")
        p = fill_missing([_prob_for(m, payload["fuente_prob"], None) for m in main_matches])
        q = fill_missing(publico_per_match(main_matches, payload["publico"]))
        for i, col in enumerate(top, 1):
            print(f"  {i:>2}. {''.join(col)}   valor={column_value(tuple(col), p, q, args.alpha):.3f}")

    exact = payload["probabilidades_exactas"]
    print("\nProbabilidades EXACTAS del desarrollo ganador (convolución, sin Monte Carlo):")
    for k in TAIL_THRESHOLDS:
        if f"p_ge_{k}" in exact:
            print(f"  ≥{k:>2}: {exact[f'p_ge_{k}']:>6.2%}")

    ev = payload["evaluacion_exhaustiva"]
    print(f"\nEvaluación exhaustiva: {ev['n_combinaciones']} combinaciones de {contract['doubles']} dobles evaluadas")
    print(f"  Mejor combinación (dobles en partidos {[i + 1 for i in ev['mejor_combinacion']['dobles']]}): "
          f"E[aciertos]={ev['mejor_combinacion']['aciertos_esperados']:.4f} | "
          f"suma 2ª probabilidad={ev['mejor_combinacion']['suma_segunda_probabilidad']:.4f}")
    print("  Top 5 por acierto esperado:")
    for i, r in enumerate(ev["top_10"][:5], 1):
        print(
            f"    {i}. dobles {[j + 1 for j in r['dobles']]} | "
            f"E[aciertos]={r['aciertos_esperados']:.4f} | "
            f"suma 2ª prob={r['suma_segunda_probabilidad']:.4f}"
        )

    print(f"\nComparación de estrategias — Monte Carlo ({args.n_sims:,} simulaciones):")
    sims = payload["monte_carlo"]
    price = contract["price_per_column"]

    def coste_estrategia(name: str) -> float:
        if name == "Boleto optimizado (3 dobles)":
            return float(payload["coste_euros"])
        if name == "8 columnas del boleto":
            return payload["n_columnas"] * price
        return price  # estrategias de simples = 1 columna

    hdr = f"{'Estrategia':<30}{'Coste':>8}{'E[aciertos]':>12}{'P(15)':>9}{'P(≥14)':>9}{'P(≥13)':>9}{'P(≥12)':>9}{'P(≥11)':>9}"
    print(hdr)
    print("-" * len(hdr))
    for name, m in sims.items():
        print(
            f"{name:<30}{coste_estrategia(name):>7.2f}€{m['esperanza']:>12.3f}{m['p_15']:>9.2%}{m['p_14']:>9.2%}"
            f"{m['p_13']:>9.2%}{m['p_12']:>9.2%}{m['p_11']:>9.2%}"
        )
    print("  (nota: el desarrollo se elige por evaluación exhaustiva de las 364 combinaciones;")
    print("   las de simples de referencia son 1 columna (14 simples + pleno))")

    out_dir = settings.SALIDA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"opt_boleto_j{args.jornada}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGuardado en {out_path}")


if __name__ == "__main__":
    main()
