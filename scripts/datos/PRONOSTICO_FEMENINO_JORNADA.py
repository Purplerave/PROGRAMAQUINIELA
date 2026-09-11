#!/usr/bin/env python3
"""Pronóstico de los partidos femeninos de una jornada (Liga F).

El motor maestro solo cubre Primera/Segunda masculina: los partidos femeninos
(11-14 en los boletos) están fuera de su dominio. Este script genera un
pronóstico documentado y reproducible para esos partidos combinando las
fuentes públicas disponibles el día del boleto:

- **Cuotas de mercado 1X2** (mejor agregado disponible): BetExplorer,
  casasdeapuestas.com y Forebet. Solo hay mercado abierto en parte de los
  partidos; la ausencia se documenta explícitamente (nunca se inventa).
- **Modelo estadístico Forebet** (probabilidades 1X2 publicadas en su página
  de Liga F Women, con predicción de marcador).
- **Comunidad quinielera** (Q15/LAE del boleto de quiniela15.com): se usa con
  peso bajo, como referencia del flujo de apuestas, no como probabilidad.

Combinación (pesos):
- Con mercado:  0,50 mercado + 0,30 modelo Forebet + 0,20 LAE.
- Sin mercado:  0,50 modelo Forebet + 0,30 LAE + 0,20 Q15.

Reglas del repo: no sustituye ni modifica nada del motor; los datos crudos de
cada fuente quedan registrados con URL y fecha de consulta en el JSON de
salida (`SALIDAS/pronostico_femenino_J{jornada}.json`).

Uso:
    python scripts/datos/PRONOSTICO_FEMENINO_JORNADA.py --jornada 6
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import settings


# ---------------------------------------------------------------------------
# Datos de fuentes externas, recopilados manualmente el 2026-09-11 (~16:00
# hora Madrid) porque no hay API sin clave para estas ligas. Cada valor lleva
# su procedencia para trazabilidad.
# ---------------------------------------------------------------------------
CONSULTADO_AT = "2026-09-11T16:00:00+02:00"

FUENTES = {
    "mercado": {
        "descripcion": "Cuotas 1X2 de casas de apuestas (agregados públicos).",
        "urls": [
            "https://www.betexplorer.com/football/spain/liga-f-women/fixtures/",
            "https://www.casasdeapuestas.com/quiniela/",
            "https://www.forebet.com/en/football-tips-and-predictions-for-spain/primera-division-women",
        ],
        "nota": "Forebet publica cuotas americanas (+X); convertidas a decimal. "
               "Sin mercado para Logroño-Valencia ni Eibar-Badalona en ninguno "
               "de los tres agregadores a la hora de consulta.",
    },
    "forebet_modelo": {
        "descripcion": "Probabilidades 1X2 del modelo estadístico de Forebet "
                       "(Primera Division Women 2026/27, Round 3).",
        "url": "https://www.forebet.com/en/football-tips-and-predictions-for-spain/primera-division-women",
    },
    "comunidad": {
        "descripcion": "Porcentajes Q15/LAE del boleto de quiniela15.com "
                       "(comunidad quinielera, día de cierre).",
        "url": "https://www.quiniela15.com/pronostico-quiniela",
    },
}

# num -> {mercado: (odd_1, odd_x, odd_2) | None,
#         forebet: (p1, px, p2) [%],
#         marcador_forebet: str}
PARTIDOS_FUENTES = {
    11: {  # Alavés Femenino - Granada (F) — dom 13/09 12:00
        "mercado": (2.55, 3.00, 2.55),
        "mercado_origen": "Forebet (+155/+200/+155; BetExplorer y "
                          "casasdeapuestas.com aún sin mercado)",
        "forebet": (31, 22, 46),
        "marcador_forebet": "0-1",
    },
    12: {  # Edf Logroño - Valencia (F) — dom 13/09 17:00
        "mercado": None,
        "mercado_origen": "Sin mercado abierto en BetExplorer, Forebet ni "
                          "casasdeapuestas.com a la hora de consulta",
        "forebet": (46, 25, 30),
        "marcador_forebet": "2-1",
    },
    13: {  # Eibar (F) - Las Planas (F) [FC Badalona Women] — dom 13/09 19:30
        "mercado": None,
        "mercado_origen": "Sin mercado abierto en BetExplorer, Forebet ni "
                          "casasdeapuestas.com a la hora de consulta",
        "forebet": (36, 30, 34),
        "marcador_forebet": "1-0",
    },
    14: {  # Madrid CFF - Sevilla (F) — sáb 12/09 16:30
        "mercado": (2.06, 3.34, 3.12),
        "mercado_origen": "Promedio de BetExplorer (2,07/3,35/3,15), "
                          "casasdeapuestas.com (2,06/3,40/3,10, 1xbet_es) y "
                          "Forebet (+105/+225/+210)",
        "forebet": (46, 19, 35),
        "marcador_forebet": "2-1",
    },
}

PESOS = {"con_mercado": (0.50, 0.30, 0.20), "sin_mercado": (0.50, 0.30, 0.20)}


def implied_probs(odds: tuple[float, float, float]) -> dict[str, float]:
    """Convierte cuotas decimales en probabilidades normalizadas 1/X/2."""
    raw = {signo: 1.0 / odd for signo, odd in zip(("1", "X", "2"), odds)}
    total = sum(raw.values())
    return {signo: raw[signo] / total for signo in raw}


def pct_to_probs(pct: tuple[float, float, float]) -> dict[str, float]:
    """Convierte porcentajes en probabilidades 1/X/2 normalizadas."""
    raw = {signo: float(p) for signo, p in zip(("1", "X", "2"), pct)}
    total = sum(raw.values())
    return {signo: raw[signo] / total for signo in raw}


def blend_probs(market: dict[str, float] | None, model: dict[str, float],
                lae: dict[str, float] | None, q15: dict[str, float] | None,
                pesos: dict[str, tuple[float, float, float]]) -> dict[str, float]:
    """Mezcla las fuentes disponibles con los pesos configurados.

    Si una fuente comunitaria (LAE/Q15) no está disponible, su peso se
    reparte proporcionalmente entre las fuentes restantes (renormalización).
    """
    if market is not None:
        w_mkt, w_mod, w_com = pesos["con_mercado"]
        com = lae if lae is not None else q15 if q15 is not None else model
        out = {s: w_mkt * market[s] + w_mod * model[s] + w_com * com[s] for s in ("1", "X", "2")}
    else:
        w_mod, w_lae, w_q15 = pesos["sin_mercado"]
        w = w_mod + w_lae + w_q15
        lae_w = w_lae if lae is not None else 0.0
        q15_w = w_q15 if q15 is not None else 0.0
        lae_p = lae if lae is not None else model
        q15_p = q15 if q15 is not None else model
        if (lae_w + q15_w) > 0:
            scale = w / (w_mod + lae_w + q15_w)
            out = {s: scale * (w_mod * model[s] + lae_w * lae_p[s] + q15_w * q15_p[s])
                   for s in ("1", "X", "2")}
        else:
            out = {s: model[s] for s in ("1", "X", "2")}
    total = sum(out.values())
    return {s: out[s] / total for s in ("1", "X", "2")}


def recommendation(probs: dict[str, float]) -> dict:
    """Signo principal, doble y nivel de confianza según probabilidad.

    Reglas:
    - favorito >= 50 % y gap >= 15 pp            -> signo simple, confianza alta
    - favorito >= 45 %                           -> doble (1º+2º), confianza media
    - gap >= 4 pp                                -> doble (1º+2º), confianza baja
    - en caso contrario                          -> triple, confianza baja
    """
    ordered = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)
    fav, fav_p = ordered[0]
    second, second_p = ordered[1]
    gap = fav_p - second_p
    if fav_p >= 0.50 and gap >= 0.15:
        confianza = "alta"
        doble = None
    elif fav_p >= 0.45:
        confianza = "media"
        doble = "".join(sorted([fav, second], key=["1", "X", "2"].index))
    elif gap >= 0.04:
        confianza = "baja"
        doble = "".join(sorted([fav, second], key=["1", "X", "2"].index))
    else:
        confianza = "baja"
        doble = "1X2"
    return {"signo": fav, "doble": doble, "confianza": confianza, "gap": round(gap, 4)}


def build_femenino_package(jornada: int) -> dict:
    """Construye el paquete de pronóstico femenino documentado."""
    boleto_path = settings.DATOS_DIR / f"QUINIELA15_J{jornada}.json"
    if not boleto_path.exists():
        raise FileNotFoundError(f"No existe: {boleto_path}")
    boleto = json.loads(boleto_path.read_text(encoding="utf-8"))
    boleto_by_num = {p.get("num"): p for p in boleto.get("partidos", [])}

    partidos = []
    for num in sorted(PARTIDOS_FUENTES):
        fuente = PARTIDOS_FUENTES[num]
        match = boleto_by_num.get(num, {})
        local, visitante = match.get("local"), match.get("visitante")

        q15_raw = match.get("q15") or {}
        lae_raw = match.get("lae") or {}
        q15 = pct_to_probs((q15_raw.get("1", 0), q15_raw.get("X", 0), q15_raw.get("2", 0)))
        lae = pct_to_probs((lae_raw.get("1", 0), lae_raw.get("X", 0), lae_raw.get("2", 0)))
        model = pct_to_probs(fuente["forebet"])
        market = implied_probs(fuente["mercado"]) if fuente["mercado"] else None

        probs = blend_probs(market, model, lae, q15, PESOS)
        rec = recommendation(probs)

        partidos.append({
            "num": num,
            "local": local,
            "visitante": visitante,
            "fecha": match.get("fecha"),
            "hora": match.get("hora"),
            "probabilidades": {s: round(probs[s], 4) for s in ("1", "X", "2")},
            "recomendacion": rec,
            "fuentes": {
                "mercado": {
                    "odds_1x2": fuente["mercado"],
                    "prob_implied": (
                        {s: round(market[s], 4) for s in ("1", "X", "2")} if market else None
                    ),
                    "origen": fuente["mercado_origen"],
                    "nota": FUENTES["mercado"]["nota"],
                },
                "modelo_forebet": {
                    "prob": {s: model[s] for s in ("1", "X", "2")},
                    "marcador_predicho": fuente["marcador_forebet"],
                },
                "comunidad": {"q15": q15_raw, "lae": lae_raw},
            },
        })

    return {
        "jornada": jornada,
        "generado_por": "scripts/datos/PRONOSTICO_FEMENINO_JORNADA.py",
        "generado_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fuentes_consultadas_at": CONSULTADO_AT,
        "dominio": "Liga F (partidos 11-14 del boleto; fuera del motor maestro)",
        "metodo": {
            "pesos_con_mercado": {"mercado": PESOS["con_mercado"][0],
                                  "modelo_forebet": PESOS["con_mercado"][1],
                                  "lae": PESOS["con_mercado"][2]},
            "pesos_sin_mercado": {"modelo_forebet": PESOS["sin_mercado"][0],
                                  "lae": PESOS["sin_mercado"][1],
                                  "q15": PESOS["sin_mercado"][2]},
            "nota": "LAE/Q15 son popularidad de la comunidad, no probabilidad "
                    "de mercado; entran con peso bajo. Si aparecen cuotas de "
                    "mercado antes del cierre, regenerar para priorizarlas.",
        },
        "fuentes_documentadas": FUENTES,
        "partidos": partidos,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Pronóstico femenino de una jornada.")
    parser.add_argument("--jornada", "-j", type=int, required=True)
    args = parser.parse_args()

    package = build_femenino_package(args.jornada)
    settings.SALIDAS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = settings.SALIDAS_DIR / f"pronostico_femenino_J{args.jornada}.json"
    out_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK -> {out_path}")
    for p in package["partidos"]:
        rec = p["recomendacion"]
        probs = p["probabilidades"]
        print(
            f"  [{p['num']}] {p['local']} - {p['visitante']}: "
            f"1 {probs['1']*100:.1f}% | X {probs['X']*100:.1f}% | 2 {probs['2']*100:.1f}% "
            f"-> {rec['signo']} (doble {rec['doble'] or '-'}, {rec['confianza']})"
        )


if __name__ == "__main__":
    main()
