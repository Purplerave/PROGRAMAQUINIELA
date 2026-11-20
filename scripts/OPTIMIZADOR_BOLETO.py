"""Optimiza el boleto semanal 14+1, con alfabetos 1X2 y Pleno de 16 signos.

La cobertura maximiza P(14+Pleno) entre columnas libres suponiendo partidos
independientes. Tres dobles es otra política (Pleno fijo, ocho columnas).
El EV parimutuel es hipotético y solo se busca entre los candidatos de mayor
cobertura; no es el retorno real ni una garantía de beneficio.
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import itertools
import json
import math
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import settings
from OPTIMIZADOR_COLUMNAS import columns_contract
from scripts.json_output import write_json
from scripts.motor.boletos import SIGNOS, normalize_weights, require_positions
from scripts.motor.pleno_model import ETIQUETAS_PLENO


def parse_casillas(data: dict) -> list[dict]:
    """Conserva la numeración explícita, sin rellenar huecos ni aceptar un Pleno 1X2."""
    if not isinstance(data, dict):
        raise ValueError("El boleto debe ser un objeto JSON")
    def section(name: str, key: str) -> list[dict]:
        league = data.get(name, {})
        if not isinstance(league, dict) or not isinstance(league.get(key, []), list):
            raise ValueError(f"Bloque {name}.{key} inválido")
        return league.get(key, [])

    lm = section("ligam", "predicciones")
    lf = section("ligaf", "pronosticos")
    require_positions(lm + lf, key="numero")
    casillas = []
    for source, matches in (("ligam", lm), ("ligaf", lf)):
        for match in matches:
            numero = match["numero"]
            if not all(isinstance(match.get(k), str) and match[k].strip() for k in ("local", "visitante")):
                raise ValueError(f"Identidad incompleta en casilla {numero}")
            pleno = match.get("pleno")
            if numero == 15:
                labels = pleno.get("etiquetas") if isinstance(pleno, dict) else None
                if (not isinstance(labels, list) or len(labels) != len(ETIQUETAS_PLENO)
                        or not all(isinstance(label, str) for label in labels)
                        or set(labels) != set(ETIQUETAS_PLENO)):
                    raise ValueError("La casilla 15 debe declarar los 16 signos del Pleno al 15")
                weights = pleno.get("probs")
            else:
                if pleno is not None:
                    raise ValueError(f"Pleno al 15 inesperado en casilla {numero}")
                labels = list(SIGNOS)
                keys = ("prob_1", "prob_x", "prob_2") if source == "ligam" else ("p1", "px", "p2")
                weights = [match.get(k) for k in keys]
            probs = (normalize_weights(weights) if isinstance(weights, list) and len(labels) == len(weights)
                     and all(type(w) in (float, int) for w in weights) else None)
            if probs is None or any(float(w) > 1 for w in weights) or abs(sum(map(float, weights)) - 1) > 0.002:
                raise ValueError(f"Probabilidades inválidas en casilla {numero}")
            casillas.append({
                "numero": numero, "partido": f"{match['local']} - {match['visitante']}",
                "probs": probs, "etiquetas": labels, "origen": source,
            })
    return sorted(casillas, key=lambda c: c["numero"])


def cargar_casillas(ruta_boleto: Path) -> tuple[list[dict], list[str]]:
    return parse_casillas(json.loads(ruta_boleto.read_text(encoding="utf-8"))), []


def top_k_hojas(probs: list[list[float]], k: int) -> list[tuple[float, tuple[int, ...]]]:
    """k-mejores hojas del arbol de productos (best-first, sin duplicados).
    Admite alfabetos distintos por casilla (1X2 y pleno de 16 signos)."""
    n = len(probs)
    orden = [sorted(range(len(p)), key=lambda s: -p[s]) for p in probs]
    mejor = tuple(orden[i][0] for i in range(n))
    w0 = 1.0
    for i, s in enumerate(mejor):
        w0 *= probs[i][s]

    def peso(t):
        w = 1.0
        for i, s in enumerate(t):
            w *= probs[i][s]
        return w

    heap = [(-w0, mejor)]
    heapq.heapify(heap)
    resultados = []
    vistos = {mejor}
    while heap and len(resultados) < k:
        negw, t = heapq.heappop(heap)
        resultados.append((-negw, t))
        for i in range(n - 1, -1, -1):
            pos_actual = orden[i].index(t[i])
            if pos_actual + 1 >= len(orden[i]):
                continue
            hijo = list(t)
            hijo[i] = orden[i][pos_actual + 1]
            hijo = tuple(hijo[:i + 1]) + tuple(orden[j][0] for j in range(i + 1, n))
            if hijo in vistos:
                continue
            vistos.add(hijo)
            heapq.heappush(heap, (-peso(hijo), hijo))
    return resultados


def publico(probs: list[list[float]], T: float) -> list[list[float]]:
    pub = [[p ** (1.0 / T) for p in fila] for fila in probs]
    return [[x / sum(fila) for x in fila] for fila in pub]


def _orden(casilla: dict) -> list[int]:
    return sorted(range(len(casilla["etiquetas"])), key=lambda i: -casilla["probs"][i])


def _column(casillas: list[dict], indices: tuple[int, ...], weight: float) -> dict:
    return {
        "signos": " ".join(c["etiquetas"][i] for c, i in zip(casillas, indices, strict=False)),
        "peso": round(weight, 12),
    }


def _three_doubles(casillas: list[dict], price: float) -> dict:
    ordering = [_orden(c) for c in casillas]
    # Para maximizar P(14+Pleno), duplicar i multiplica la masa por
    # (p1+p2)/p1. La casilla 15 está excluida aunque su ratio sea mayor.
    selected = sorted(range(14), key=lambda i: -casillas[i]["probs"][ordering[i][1]] / casillas[i]["probs"][ordering[i][0]])[:3]
    options = [order[:2] if i in selected else order[:1] for i, order in enumerate(ordering)]
    columns = []
    mass = 0.0
    for indices in itertools.product(*options):
        p = math.prod(c["probs"][j] for c, j in zip(casillas, indices, strict=False))
        mass += p
        columns.append(_column(casillas, indices, p))
    doubles, singles = [], []
    for i, (c, opt) in enumerate(zip(casillas, options, strict=False)):
        item = {"casilla": c["numero"], "partido": c["partido"]}
        if i in selected:
            doubles.append({**item, "signos": [c["etiquetas"][j] for j in sorted(opt)]})
        else:
            singles.append({**item, "signo": c["etiquetas"][opt[0]], "prob_pct": round(100 * c["probs"][opt[0]], 1)})
    return {
        "n_columnas": len(columns), "coste_eur": round(len(columns) * price, 2),
        "p_acierto": round(mass, 12), "dobles": doubles, "fijos": singles, "columnas": columns,
    }


def optimize_weekly(casillas: list[dict], *, budget: int, jackpot: float, price: float, kappa: float, temperature: float) -> dict:
    """Evalúa dos carteras libres y un desarrollo clásico con límite común."""
    contract = columns_contract()
    if type(budget) is not int or not 1 <= budget <= contract["columns_per_ticket"]:
        raise ValueError(f"El presupuesto debe ser de 1 a {contract['columns_per_ticket']} columnas")
    if price != contract["price_per_column"]:
        raise ValueError(f"El precio por columna es fijo: {contract['price_per_column']} EUR")
    if not all(math.isfinite(x) for x in (jackpot, kappa, temperature)) or min(jackpot, kappa) < 0 or temperature < 1:
        raise ValueError("Bote y kappa deben ser finitos y no negativos; temperatura debe ser finita y >= 1")
    probs = [c["probs"] for c in casillas]
    public = publico(probs, temperature)
    candidates = top_k_hojas(probs, max(budget * 50, 512))
    coverage = candidates[:budget]

    def edge(item: tuple[float, tuple[int, ...]]) -> float:
        weight, indices = item
        crowd = math.prod(public[i][s] for i, s in enumerate(indices))
        return weight * jackpot / (1 + kappa * crowd) - price

    ranked = sorted(((edge(item), item) for item in candidates), key=lambda pair: -pair[0])
    portfolio = [(net, item) for net, item in ranked[:budget] if net > 0]

    def describe(selection: list[tuple[float, tuple[int, ...]]]) -> dict:
        return {
            "columnas": [_column(casillas, indices, p) for p, indices in selection],
            "coste_eur": round(len(selection) * price, 2),
            "p_acierto_total": round(sum(p for p, _ in selection), 12),
        }

    return {
        "tres_dobles": _three_doubles(casillas, price) if budget >= contract["columns_per_ticket"] else None,
        "parametros": {"presupuesto": budget, "bote": jackpot, "precio": price, "kappa": kappa,
                       "temperatura_publico": temperature, "independencia_entre_partidos": True},
        "casillas": casillas,
        "politica_cobertura": describe(coverage),
        "politica_ev_parimutuel": {
            **describe([item for _, item in portfolio]),
            "ev_eur": round(sum(net for net, _ in portfolio), 2),
            "ev_estimado": True,
            "n_candidatos": len(candidates),
            "supuestos": ["modelo de público = p^(1/T) normalizado", "co-ganadores = kappa * masa pública",
                          "EV optimizado entre candidatos de mayor probabilidad; no es el ROI real"],
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--boleto", type=Path, required=True, help="ruta boleto_completo_J*.json")
    ap.add_argument("--presupuesto", type=int, default=8, help="columnas a jugar: 1..8")
    ap.add_argument("--bote", type=float, help="importe supuesto para EV (por defecto, el del boleto)")
    ap.add_argument("--precio", type=float, default=columns_contract()["price_per_column"])
    ap.add_argument("--kappa", type=float, default=3000.0)
    ap.add_argument("--temperatura", type=float, default=2.0)
    args = ap.parse_args()
    try:
        raw = args.boleto.read_bytes()
        data = json.loads(raw)
        casillas = parse_casillas(data)
        jornada = data.get("jornada")
        demo = data.get("demo", False)
        if type(jornada) is not int or jornada < 1 or type(demo) is not bool:
            raise ValueError("jornada o indicador demo inválidos")
        jackpot = args.bote if args.bote is not None else float(data.get("bote_eur", 0))
        output = optimize_weekly(casillas, budget=args.presupuesto, jackpot=jackpot, price=args.precio,
                                 kappa=args.kappa, temperature=args.temperatura)
        output.update(jornada=jornada, demo=demo, entrada=args.boleto.name,
                      entrada_sha256=hashlib.sha256(raw).hexdigest(), avisos=[])
        tag = f"{'demo_' if demo else ''}J{jornada}"
        out = settings.SALIDA_DIR / f"optimizacion_boleto_{tag}.json"
        write_json(out, output)
    except (OSError, ValueError, TypeError) as exc:
        ap.error(str(exc))
    cover = output["politica_cobertura"]
    print(f"Cobertura {tag}: {len(cover['columnas'])} columnas · {cover['coste_eur']:.2f} EUR · P(14+Pleno)={cover['p_acierto_total']:.6%}")
    print(f"Guardado: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
