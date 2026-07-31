"""OPTIMIZADOR_COLUMNAS.py — Construcción global del boleto de La Quiniela.

El objetivo no es "poner el doble en el partido más difícil", sino seleccionar,
para toda la jornada, el conjunto de signos (desarrollo) que maximiza cobertura y
valor dentro de un presupuesto, y luego ordenar/seleccionar columnas con criterio
de valor y diversidad.

Idea (auditoría de Claude):
    score(columna) = P(columna) / P_público(columna)^alpha
    utilidad ≈ cobertura de categorías + valor frente a lo que juega el público

El partido de Pleno al 15 (num == pleno_num, por defecto 15) se excluye del
desarrollo y se juega como simple del favorito (1X2), separado del marcador.

Entradas (CLI):
    --jornada N            JSON con los partidos (DATOS/QUINIELA15_J{N}.json)
    --probabilidades FILE  JSON con probabilidades del modelo (opcional)
    --fuente-prob q15|lae|apu|modelo   de dónde salen las probabilidades 1/X/2
    --publico lae|apu|q15  fuente de popularidad del público (por defecto: lae)
    --presupuesto COL      presupuesto en columnas (por defecto: 128)
    --alpha VAL            exponente de valor anti-popularidad (0 = solo cobertura)
    --max-dobles N         límite de dobles (opcional)
    --max-triples N        límite de triples (opcional)
    --pleno-num N          nº del partido de Pleno al 15 (0 = no excluir ninguno)

Uso como módulo (T2):
    from OPTIMIZADOR_COLUMNAS import optimize_jornada
    payload = optimize_jornada(74, fuente_prob="q15", publico="lae", presupuesto=128)
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

# Los 7 desarrollos posibles por partido: 3 simples, 3 dobles, 1 triple
OPTIONS = [
    ("1", ("1",)),
    ("X", ("X",)),
    ("2", ("2",)),
    ("1X", ("1", "X")),
    ("12", ("1", "2")),
    ("X2", ("X", "2")),
    ("1X2", ("1", "X", "2")),
]


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


def log_value(p: np.ndarray, q: np.ndarray, alpha: float) -> np.ndarray:
    """Valor por signo: log p - alpha*log q (probable y poco popular)."""
    return np.log(np.clip(p, EPS, 1.0)) - alpha * np.log(np.clip(q, EPS, 1.0))


def develop_ticket(
    probs: list[np.ndarray],
    public: list[np.ndarray],
    budget: int,
    alpha: float,
    eta: float = 0.5,
    max_dobles: int | None = None,
    max_triples: int | None = None,
) -> tuple[list[tuple], float]:
    """Selecciona el desarrollo (signos por partido) con programación dinámica.

    Maximiza, por partido:
        c(S) = cobertura(S) + eta * (mejor_valor_en_S - mejor_valor_global)
    sujeto a product(|S_i|) <= budget. Devuelve (opciones por partido, score).
    """
    n = len(probs)
    best_val = [float(np.max(log_value(p, q, alpha))) for p, q in zip(probs, public)]

    per_match = []
    for i in range(n):
        p, q, bv = probs[i], public[i], best_val[i]
        w = log_value(p, q, alpha)
        opts = []
        for label, signs in OPTIONS:
            mask = [SIGN_INDEX[s] for s in signs]
            cov = float(sum(p[j] for j in mask))
            val_term = max(w[j] for j in mask) - bv  # <= 0: coste de oportunidad
            opts.append((label, signs, len(signs), cov + eta * val_term))
        per_match.append(opts)

    NEG = -1e12
    dp = {1: 0.0}
    choice: list[dict[int, tuple]] = [dict() for _ in range(n)]
    for i, opts in enumerate(per_match):
        ndp: dict[int, float] = {}
        for cols, score in dp.items():
            for label, signs, cost, sc in opts:
                new_cols = cols * cost
                if new_cols > budget:
                    continue
                new_score = score + sc
                if new_score > ndp.get(new_cols, NEG):
                    ndp[new_cols] = new_score
                    choice[i][new_cols] = (label, signs, cost, sc)
        dp = ndp
        if not dp:
            raise ValueError(f"Presupuesto demasiado pequeño (no cabe el partido {i + 1}).")

    best_cols = max(dp, key=dp.get)
    final_score = dp[best_cols]
    selected: list[tuple] = []
    cols = best_cols
    for i in range(n - 1, -1, -1):
        label, signs, cost, sc = choice[i][cols]
        selected.append((label, signs))
        cols //= cost
    selected.reverse()

    if max_dobles is not None or max_triples is not None:
        selected = enforce_limits(selected, probs, public, alpha, eta, max_dobles, max_triples)
    return selected, final_score


def enforce_limits(
    selected: list[tuple],
    probs: list[np.ndarray],
    public: list[np.ndarray],
    alpha: float,
    eta: float,
    max_dobles: int | None,
    max_triples: int | None,
) -> list[tuple]:
    """Si hay más dobles/triples de los permitidos, degrada los menos valiosos."""
    result = list(selected)

    def score_at(i: int) -> float:
        _, signs = result[i]
        p, q = probs[i], public[i]
        w = log_value(p, q, alpha)
        bv = float(np.max(w))
        cov = float(sum(p[SIGN_INDEX[s]] for s in signs))
        return cov + eta * (max(w[SIGN_INDEX[s]] for s in signs) - bv)

    while max_dobles is not None and sum(1 for _, s in result if len(s) == 2) > max_dobles:
        cand = [i for i, (_, s) in enumerate(result) if len(s) == 2]
        i = min(cand, key=score_at)
        result[i] = ("1", ("1",))
    while max_triples is not None and sum(1 for _, s in result if len(s) == 3) > max_triples:
        cand = [i for i, (_, s) in enumerate(result) if len(s) == 3]
        i = min(cand, key=score_at)
        result[i] = ("1", ("1",))
    return result


def enumerate_columns(selected: list[tuple]) -> list[tuple[str, ...]]:
    """Todas las columnas del desarrollo (producto cartesiano de signos)."""
    per_match = [list(signs) for _, signs in selected]
    return list(itertools.product(*per_match))


def column_value(col: tuple[str, ...], probs: list[np.ndarray], public: list[np.ndarray], alpha: float) -> float:
    lp = sum(math.log(np.clip(probs[i][SIGN_INDEX[s]], EPS, 1.0)) for i, s in enumerate(col))
    lq = sum(math.log(np.clip(public[i][SIGN_INDEX[s]], EPS, 1.0)) for i, s in enumerate(col))
    return lp - alpha * lq


def select_diverse_columns(
    columns: list[tuple[str, ...]],
    probs: list[np.ndarray],
    public: list[np.ndarray],
    alpha: float,
    n_max: int,
    min_dist: int = 3,
) -> list[tuple[str, ...]]:
    """Top-N columnas por valor con diversidad (distancia de Hamming mínima)."""
    scored = sorted(
        ((column_value(c, probs, public, alpha), c) for c in columns),
        key=lambda t: t[0],
        reverse=True,
    )
    chosen: list[tuple[str, ...]] = []
    for _, col in scored:
        if len(chosen) >= n_max:
            break
        if all(sum(a != b for a, b in zip(col, other)) >= min_dist for other in chosen):
            chosen.append(col)
    return chosen


def coverage_distribution(probs: list[np.ndarray], selected: list[tuple]) -> np.ndarray:
    """P(k aciertos del mejor signo del desarrollo) para k=0..n (convolución)."""
    dist = np.array([1.0])
    for i, (_, signs) in enumerate(selected):
        hit = float(sum(probs[i][SIGN_INDEX[s]] for s in signs))
        new = np.zeros(len(dist) + 1)
        new[:-1] += dist * (1.0 - hit)
        new[1:] += dist * hit
        dist = new
    return dist


# --- Representaciones ---------------------------------------------------------
# Estrategia "desarrollo": lista de N conjuntos de signos permitidos por partido.
# Estrategia "columnas": lista de columnas completas de N signos.

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


def hamming_diversity(columns: list[tuple[str, ...]]) -> float:
    if len(columns) < 2:
        return 0.0
    sample = columns[:60]
    total, count = 0.0, 0
    for i in range(len(sample)):
        for j in range(i + 1, len(sample)):
            total += sum(a != b for a, b in zip(sample[i], sample[j]))
            count += 1
    return total / count if count else 0.0


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
    presupuesto: int = 128,
    alpha: float = 0.6,
    eta: float = 0.5,
    max_dobles: int | None = None,
    max_triples: int | None = None,
    pleno_num: int = 15,
    probs_override: dict | None = None,
    n_sims: int = 20000,
) -> dict:
    """Optimiza el boleto de una lista de partidos (14 + pleno aparte)."""
    main_matches = [m for m in partidos if m.get("num") != pleno_num] or partidos
    pleno_match = next((m for m in partidos if m.get("num") == pleno_num), None)

    probs = fill_missing([_prob_for(m, fuente_prob, probs_override) for m in main_matches])
    public = fill_missing(publico_per_match(main_matches, publico))

    selected, dp_score = develop_ticket(
        probs, public, budget=presupuesto, alpha=alpha, eta=eta,
        max_dobles=max_dobles, max_triples=max_triples,
    )
    n_columns = math.prod(len(signs) for _, signs in selected)
    price = float(settings.CONFIG.get("columns", {}).get("price_per_column", 0.75))
    cost = n_columns * price
    dist = coverage_distribution(probs, selected)

    all_cols = enumerate_columns(selected)
    diverse = (
        select_diverse_columns(all_cols, probs, public, alpha, n_max=min(200, len(all_cols)))
        if len(all_cols) <= 2000
        else []
    )

    dev_sistema = dev_from_field(main_matches, "sistema")
    dev_comunidad = dev_from_field(main_matches, "comunidad")
    developments: dict[str, list[tuple]] = {
        "Boleto modelo (favoritos)": dev_singles(probs),
        "Boleto popular (público)": dev_singles(public),
        "Boleto optimizado (desarrollo)": [s for _, s in selected],
    }
    if dev_sistema:
        developments["Boleto sistema quiniela15"] = dev_sistema
    if dev_comunidad:
        developments["Boleto comunidad"] = dev_comunidad
    column_sets: dict[str, list[tuple[str, ...]]] = {
        f"Top-{min(len(diverse), 50)} col. por valor": diverse[:50],
    } if diverse else {}
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
        "alpha": alpha,
        "eta": eta,
        "presupuesto": presupuesto,
        "n_columnas": n_columns,
        "coste_euros": round(cost, 2),
        "desarrollo": [
            {"num": m.get("num"), "signos": list(s), "label": l}
            for m, (l, s) in zip(main_matches, selected)
        ],
        "pleno15": pleno_info,
        "n_columnas_top": len(diverse),
        "distribucion_aciertos": {str(k): float(dist[k]) for k in range(len(dist))},
        "monte_carlo": sims,
        "columnas_top": diverse[:15],
    }


def optimize_jornada(
    jornada: int,
    *,
    fuente_prob: str = "q15",
    publico: str = "lae",
    presupuesto: int = 128,
    alpha: float = 0.6,
    eta: float = 0.5,
    max_dobles: int | None = None,
    max_triples: int | None = None,
    pleno_num: int = 15,
    probs_override: dict | None = None,
    n_sims: int = 20000,
) -> dict:
    """Optimiza el boleto de una jornada completa (14 partidos + pleno aparte).

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
        presupuesto=presupuesto, alpha=alpha, eta=eta,
        max_dobles=max_dobles, max_triples=max_triples,
        pleno_num=pleno_num, probs_override=probs_override, n_sims=n_sims,
    )


# --- CLI ----------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Optimizador global de boletos de La Quiniela")
    parser.add_argument("--jornada", type=int, required=True, help="número de jornada (DATOS/QUINIELA15_J{N}.json)")
    parser.add_argument("--probabilidades", type=str, default=None, help="JSON con probabilidades del modelo (opcional)")
    parser.add_argument("--fuente-prob", choices=("q15", "lae", "apu", "modelo"), default="q15")
    parser.add_argument("--publico", choices=("lae", "apu", "q15"), default="lae")
    parser.add_argument("--presupuesto", type=int, default=128, help="presupuesto en columnas")
    parser.add_argument("--alpha", type=float, default=0.6, help="exponente de valor anti-popularidad")
    parser.add_argument("--eta", type=float, default=0.5, help="peso del valor frente a la cobertura")
    parser.add_argument("--max-dobles", type=int, default=None)
    parser.add_argument("--max-triples", type=int, default=None)
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
        presupuesto=args.presupuesto, alpha=args.alpha, eta=args.eta,
        max_dobles=args.max_dobles, max_triples=args.max_triples,
        pleno_num=args.pleno_num, probs_override=override or None, n_sims=args.n_sims,
    )

    price = float(settings.CONFIG.get("columns", {}).get("price_per_column", 0.75))
    partidos = json.loads(
        (settings.DATOS_DIR / f"QUINIELA15_J{args.jornada}.json").read_text(encoding="utf-8")
    )["partidos"]
    main_matches = [m for m in partidos if m.get("num") != args.pleno_num] or partidos
    selected = [(d["label"], tuple(d["signos"])) for d in payload["desarrollo"]]

    print("=" * 82)
    print(f"OPTIMIZADOR DE BOLETOS — jornada {args.jornada}  (prob: {payload['fuente_prob']} | público: {payload['publico']})")
    print("=" * 82)
    print(f"Presupuesto: {args.presupuesto} col. | alpha={args.alpha} | eta={args.eta} | precio columna {price:.2f} €")
    print(f"\nDesarrollo recomendado ({payload['n_columnas']} columnas, {payload['coste_euros']:.2f} €):")
    print(render_ticket(main_matches, selected))
    if payload.get("pleno15"):
        p15 = payload["pleno15"]
        print(f"  Pleno al 15 (partido {p15['num']}): signo {p15['signo']} (prob. favorito {p15['prob_favorito']:.1%})")

    top = payload.get("columnas_top", [])
    if top:
        print(f"\nTop {len(top)} columnas por valor (diversidad media: {hamming_diversity(top):.2f}):")
        for i, col in enumerate(top[:15], 1):
            probs_list = fill_missing(publico_per_match(main_matches, payload["fuente_prob"]))
            public_list = fill_missing(publico_per_match(main_matches, payload["publico"]))
            # para imprimir el valor usamos las mismas probs que el payload
            p = fill_missing([_prob_for(m, payload["fuente_prob"], None) for m in main_matches])
            q = fill_missing(publico_per_match(main_matches, payload["publico"]))
            print(f"  {i:>2}. {''.join(col)}   valor={column_value(col, p, q, payload['alpha']):.3f}")
        _ = probs_list, public_list

    dist = payload["distribucion_aciertos"]
    print("\nProbabilidad del desarrollo de alcanzar cada categoría (convolución exacta):")
    for k in range(10, 15):
        prob_at_least = sum(float(dist[str(j)]) for j in range(k, len(dist)))
        print(f"  ≥{k:>2}: {prob_at_least:>6.2%}")

    print(f"\nComparación de estrategias — Monte Carlo ({args.n_sims:,} simulaciones):")
    sims = payload["monte_carlo"]

    def coste_estrategia(name: str) -> float:
        if name == "Boleto optimizado (desarrollo)":
            return float(payload["coste_euros"])
        if name.startswith("Top-"):
            return payload["n_columnas_top"] * price
        return price  # estrategias de simples = 1 columna

    hdr = f"{'Estrategia':<30}{'Coste':>8}{'E[aciertos]':>12}{'P(15)':>9}{'P(≥14)':>9}{'P(≥13)':>9}{'P(≥12)':>9}{'P(≥11)':>9}"
    print(hdr)
    print("-" * len(hdr))
    for name, m in sims.items():
        print(
            f"{name:<30}{coste_estrategia(name):>7.2f}€{m['esperanza']:>12.3f}{m['p_15']:>9.2%}{m['p_14']:>9.2%}"
            f"{m['p_13']:>9.2%}{m['p_12']:>9.2%}{m['p_11']:>9.2%}"
        )
    print("  (nota: el desarrollo y el top-N se eligen dentro del presupuesto; las de simples")
    print("   de referencia son 1 columna (14 simples + pleno), por eso su coste es solo el precio base)")

    out_dir = settings.SALIDA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"opt_boleto_j{args.jornada}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGuardado en {out_path}")


if __name__ == "__main__":
    main()
