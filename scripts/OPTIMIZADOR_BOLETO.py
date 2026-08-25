"""
OPTIMIZADOR_BOLETO.py — D5: de probabilidades a apuesta optima (dinero).

Entrada : SALIDAS/boleto_completo_J{N}.json  (casillas Liga M + Liga F)
Salida  : SALIDAS/optimizacion_boleto_J{N}.json + resumen en consola

POLITICAS
---------
cobertura (exacta):
    Elige las K columnas de MAYOR producto de probabilidades
    (busqueda best-first exacta tipo k-mejores-hojas).
    Maximiza P(15 aciertos) dado un presupuesto K de columnas. Sin supuestos.

ev_parimutuel:
    Modela al publico: p_publico(i,s) = normalizado( p_modelo^(1/T) ), T>=1
    (publico menos afilado que el modelo -> esa diferencia ES el edge).
    Si el desenlace es la columna l, los co-ganadores esperados son kappa*r_l
    y el premio por boleto = BOTE/(1+kappa*r_l).
        EV(S) = sum_{l en S} q_l * BOTE/(1+kappa*r_l)  -  K*PRECIO
    Optimiza greedy por ratio marginal EV/coste sobre candidatos top-N.
    SUPUESTOS EXPLICITOS (v1, sin cuotas de cierre aun):
        - BOTE, PRECIO, KAPPA, T son parametros CLI, no verdades.
        - Al llegar D3 (cuotas reales) se sustituye el modelo de publico.

Notas: trata las 15 casillas como 1X2. El pleno al descanso moderno de la
casilla 15 queda como deuda (D7) — se documenta, no se simula.
"""
from __future__ import annotations

import argparse
import heapq
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SALIDAS = ROOT / "SALIDAS"


MAX_CASILLAS = 15


def cargar_casillas(ruta_boleto: Path) -> tuple[list[dict], list[str]]:
    avisos = []
    d = json.loads(ruta_boleto.read_text(encoding="utf-8"))
    casillas = {}
    usadas = set()
    lm = d.get("ligam") or {}
    predicciones_lm = list(lm.get("predicciones") or [])
    # Si el paquete LigaM no encaja con el boleto de 15 (p.ej. temporada sin
    # Liga F), se recorta conservando las casillas mas bajas y SE AVISA.
    huecos_para_ligaf = max(0, 15 - len(predicciones_lm))
    exceso = len(predicciones_lm) + huecos_para_ligaf - MAX_CASILLAS
    if exceso > 0:
        recortadas = [f"{p['local']} - {p['visitante']}" for p in predicciones_lm[-exceso:]]
        avisos.append(f"RECORTE por estructura 14+1: {exceso} partidos LigaM fuera "
                      f"(paquete antiguo sin Liga F): {recortadas}")
        predicciones_lm = predicciones_lm[:len(predicciones_lm) - exceso]
    for p in predicciones_lm:
        num = int(p.get("numero") or len(casillas) + 1)
        if p.get("pleno"):
            probs_c = [float(x) for x in p["pleno"]["probs"]]
            etiq = list(p["pleno"]["etiquetas"])
            origen = "ligam_pleno"
        else:
            probs_c = [float(p["prob_1"]), float(p["prob_x"]), float(p["prob_2"])]
            etiq = ["1", "X", "2"]
            origen = "ligam"
        casillas[num] = {"numero": num,
                         "partido": f"{p['local']} - {p['visitante']}",
                         "probs": probs_c, "etiquetas": etiq,
                         "origen": origen}
        usadas.add(num)
    lf = (d.get("ligaf") or {}).get("pronosticos") or []
    nxt = 1
    for p in lf:
        while nxt in usadas:
            nxt += 1
        if nxt > MAX_CASILLAS:
            avisos.append(f"LigaF fuera de boleto por falta de casillas: {p['local']} - {p['visitante']}")
            continue
        casillas[nxt] = {"numero": nxt,
                         "partido": f"{p['local']} - {p['visitante']}",
                         "probs": [float(p["p1"]), float(p["px"]), float(p["p2"])],
                         "etiquetas": ["1", "X", "2"],
                         "origen": "ligaf"}
        usadas.add(nxt)
    if len(casillas) < MAX_CASILLAS:
        faltan = [i for i in range(1, MAX_CASILLAS + 1) if i not in casillas]
        avisos.append(f"Boleto INCOMPLETO: faltan las casillas {faltan}")
    return [casillas[k] for k in sorted(casillas)], avisos


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boleto", type=str, required=True, help="ruta boleto_completo_J*.json")
    ap.add_argument("--presupuesto", type=int, default=8, help="columnas a jugar")
    ap.add_argument("--bote", type=float, default=1_500_000.0)
    ap.add_argument("--precio", type=float, default=0.75, help="EUR por columna")
    ap.add_argument("--kappa", type=float, default=3000.0,
                    help="escala de co-ganadores esperados (parimutuel)")
    ap.add_argument("--temperatura", type=float, default=2.0,
                    help="T del publico: >1 significa publico mas plano que el modelo")
    args = ap.parse_args()

    ruta = Path(args.boleto)
    casillas, avisos = cargar_casillas(ruta)
    for a in avisos:
        print(f"[AVISO] {a}")
    n = len(casillas)
    probs = [c["probs"] for c in casillas]
    etiqueta = ruta.stem.replace("boleto_completo_", "")
    print(f"Boleto {etiqueta}: {n} casillas cargadas "
          f"({sum(1 for c in casillas if c['origen']=='ligaf')} de Liga F)")

    # ---- politica cobertura (exacta) ----
    topk = top_k_hojas(probs, min(args.presupuesto, 3 ** n))
    p_hit = sum(w for w, _ in topk)
    coste = len(topk) * args.precio
    print(f"\n[COBERTURA] columnas={len(topk)} coste={coste:.2f} EUR  "
          f"P(acertar todo)={p_hit:.5f} ({p_hit*100:.3f}%)")

    # ---- politica EV parimutuel ----
    pub = publico(probs, args.temperatura)

    def ev_de(seleccion):
        ev = 0.0
        for _, t in seleccion:
            q = 1.0
            r = 1.0
            for i, s in enumerate(t):
                q *= probs[i][s]
                r *= pub[i][s]
            ev += q * args.bote / (1.0 + args.kappa * r)
        return ev - len(seleccion) * args.precio

    candidatos = top_k_hojas(probs, min(max(args.presupuesto * 50, 512), 3 ** n))
    elegidos, mejor_ev = [], None
    restantes = list(candidatos)
    while restantes and len(elegidos) < args.presupuesto:
        mejor_delta, mejor_item = None, None
        base = ev_de(elegidos)
        for item in restantes:
            ev_n = ev_de(elegidos + [item])
            delta = ev_n - base
            if mejor_delta is None or delta > mejor_delta:
                mejor_delta, mejor_item = delta, item
        if mejor_delta is None or mejor_delta <= 0:
            break
        elegidos.append(mejor_item)
        restantes.remove(mejor_item)
        mejor_ev = base + mejor_delta
    if elegidos:
        p_hit_ev = sum(w for w, _ in elegidos)
        print(f"[EV PARIMUTUEL] columnas={len(elegidos)} coste={len(elegidos)*args.precio:.2f} EUR  "
              f"P(acertar todo)={p_hit_ev:.5f}  EV={mejor_ev:+.2f} EUR")

    def firmas(t):
        return " ".join(casillas[i]["etiquetas"][s] for i, s in enumerate(t))

    # ---- QUINIELA CLASICA: fijos + dobles derivados de la cobertura ----
    usados = [set() for _ in range(n)]
    for _, t in topk:
        for i, s in enumerate(t):
            usados[i].add(s)
    dobles, fijos = [], []
    for i, c in enumerate(casillas):
        signos = [c["etiquetas"][s] for s in sorted(usados[i])]
        item = {"casilla": c["numero"], "partido": c["partido"], "signos": signos}
        if len(signos) == 2:
            dobles.append(item)
        else:
            fijos.append({**item, "signo": signos[0],
                          "prob_pct": round(100 * max(c["probs"]), 1)})
    bloque_clasica = {
        "n_columnas": len(topk),
        "coste_eur": round(len(topk) * args.precio, 2),
        "dobles": dobles,
        "fijos": fijos,
        "columnas": [{"signos": firmas(t), "peso": round(w, 6)} for w, t in topk],
    }

    # ---- TRES DOBLES EXACTOS (formato clasico del quinielista) ----
    # Elegimos las 3 casillas con mejor ratio p_segunda/p_favorito; el resto
    # va fijo al favorito -> 2^3 = 8 columnas. Es la solucion OPTIMA dentro
    # de la familia "exactamente 3 dobles".
    import itertools
    ratios = []
    for i, c in enumerate(casillas):
        ps = sorted(c["probs"], reverse=True)
        if len(ps) >= 2 and ps[0] > 0:
            ratios.append((ps[1] / ps[0], i))
    ratios.sort(reverse=True)
    idx_dobles = [i for _, i in ratios[:3]]
    cols_3d, p_total_3d = [], 0.0
    fijos_3d = []
    for combo in itertools.product([0, 1], repeat=len(idx_dobles)):
        peso, signs = 1.0, []
        for i, c in enumerate(casillas):
            et = c["etiquetas"]
            orden_local = sorted(range(len(et)), key=lambda k: -c["probs"][k])
            s = orden_local[combo[idx_dobles.index(i)]] if i in idx_dobles else orden_local[0]
            signs.append(et[s])
            peso *= c["probs"][s]
        cols_3d.append({"signos": " ".join(signs), "peso": round(peso, 6)})
        p_total_3d += peso
    for i, c in enumerate(casillas):
        if i in idx_dobles:
            continue
        orden_local = sorted(range(len(c["etiquetas"])), key=lambda k: -c["probs"][k])
        fijos_3d.append({
            "casilla": c["numero"], "partido": c["partido"],
            "signo": c["etiquetas"][orden_local[0]],
            "prob_pct": round(100 * c["probs"][orden_local[0]], 1),
        })
    tres_dobles = {
        "n_columnas": len(cols_3d),
        "coste_eur": round(len(cols_3d) * args.precio, 2),
        "p_acierto": round(p_total_3d, 6),
        "dobles": [{
            "casilla": casillas[i]["numero"], "partido": casillas[i]["partido"],
            "signos": [casillas[i]["etiquetas"][k] for k in
                       sorted(range(len(casillas[i]["etiquetas"])),
                              key=lambda k: -casillas[i]["probs"][k])[:2]],
        } for i in idx_dobles],
        "fijos": fijos_3d,
        "columnas": cols_3d,
    }

    salida = {
        "entrada": ruta.name,
        "avisos": avisos,
        "tres_dobles": tres_dobles,
        "quiniela_clasica": bloque_clasica,
        "parametros": {"presupuesto": args.presupuesto, "bote": args.bote,
                        "precio": args.precio, "kappa": args.kappa,
                        "temperatura_publico": args.temperatura},
        "casillas": [{"numero": c["numero"], "partido": c["partido"],
                       "probs": c["probs"], "origen": c["origen"]} for c in casillas],
        "politica_cobertura": {
            "columnas": [{"signos": firmas(t), "peso": round(w, 6)} for w, t in topk],
            "coste_eur": round(coste, 2),
            "p_acierto_total": round(p_hit, 6),
        },
        "politica_ev_parimutuel": {
            "columnas": [{"signos": firmas(t), "peso": round(w, 6)} for w, t in elegidos],
            "coste_eur": round(len(elegidos) * args.precio, 2),
            "p_acierto_total": round(sum(w for w, _ in elegidos), 6),
            "ev_eur": round(mejor_ev, 2) if mejor_ev is not None else None,
            "supuestos": ["modelo de publico = p^(1/T) normalizado",
                            "co-ganadores = kappa * masa_publica_columna",
                            "sin cuotas de cierre (D3 pendiente)"],
        },
    }
    out = SALIDAS / f"optimizacion_boleto_{etiqueta}.json"
    out.write_text(json.dumps(salida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Guardado:", out)


if __name__ == "__main__":
    main()
