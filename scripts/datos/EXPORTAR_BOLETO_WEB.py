#!/usr/bin/env python3
"""Exporta el boleto del motor al formato que consume liga-maestros-web.

Es el puente en sentido contrario a IMPORTAR_JORNADA_WEB.py:

    liga-maestros-web  --(IMPORTAR_JORNADA_WEB)-->  DATOS/QUINIELA15_JN.json
    SALIDAS/paquete_jornada_JN.json  --(este script)-->  data/predicciones_JN.json

La web lee `data/predicciones_J{N}.json` y toma `programa.signos` (15 signos,
dobles como "1X"/"12", Pleno como "1-1") para meterlos en la tabla
`predicciones` como usuario `programa`. Los textos que se ven junto a cada
signo van en `data/PREDICTION_REASONS.json` bajo la clave de la jornada.

Este script genera los dos ficheros a partir del paquete del motor, sin
retocar nada a mano:

    python PREDECIR_JORNADA.py --jornada 2
    python scripts/datos/EXPORTAR_BOLETO_WEB.py --jornada 2

Salida en `export_web/`:
    predicciones_J2.json          -> copiar a data/ de la web
    PREDICTION_REASONS_J2.json    -> fusionar en data/PREDICTION_REASONS.json

Los motivos se generan a partir de los numeros (modelo, mercado, LAE, Q15).
Con `--motivos fichero.json` se pueden sustituir por textos redactados a mano.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import settings  # noqa: E402

EXPORT_DIR = ROOT / "export_web"
SIGNS = ("1", "X", "2")


def _pct(value: float) -> int:
    return int(round(float(value) * 100))


def _market_probs(partido: dict[str, Any]) -> list[float] | None:
    odds = [partido.get("odd_1"), partido.get("odd_x"), partido.get("odd_2")]
    if not all(isinstance(o, (int, float)) and o > 1 for o in odds):
        return None
    inv = [1 / float(o) for o in odds]
    total = sum(inv)
    return [x / total for x in inv]


def _auto_motivo(num: int, jornada_match: dict[str, Any], probs: dict[str, float], signo: str) -> str:
    """Frase corta y verificable a partir de los numeros disponibles."""
    ordered = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)
    fav, fav_p = ordered[0]
    second, second_p = ordered[1]
    partes = [f"Modelo {_pct(probs['1'])}/{_pct(probs['X'])}/{_pct(probs['2'])}"]

    market = _market_probs(jornada_match)
    if market:
        partes.append(f"mercado {_pct(market[0])}/{_pct(market[1])}/{_pct(market[2])}")

    lae = jornada_match.get("lae")
    if isinstance(lae, dict):
        publico = lae.get(fav)
        if publico is not None:
            valor = fav_p - float(publico) / 100
            etiqueta = "valor" if valor > 0.02 else ("sobreapostado" if valor < -0.05 else "en linea")
            partes.append(f"LAE juega el {fav} al {int(publico)}% ({etiqueta})")

    if len(signo) == 2:
        partes.append(f"doble {signo}: {second} a {abs(fav_p - second_p) * 100:.0f} puntos del {fav}")
    else:
        partes.append(f"se juega {signo}")
    return ". ".join(partes) + "."


def _pleno_motivo(pleno: dict[str, Any], signo: str) -> str:
    lambdas = pleno.get("lambdas") or {}
    local = lambdas.get("local")
    visitante = lambdas.get("visitante")
    base = "Dixon-Coles"
    if local is not None and visitante is not None:
        base += f": {float(local):.2f} goles locales y {float(visitante):.2f} visitantes"
    return f"{base}. Buckets {signo}."


def build_export(jornada: int, motivos_override: list[str] | None) -> tuple[dict, dict, list[str]]:
    paquete_path = settings.SALIDAS_DIR / f"paquete_jornada_J{jornada}.json"
    if not paquete_path.exists():
        raise SystemExit(
            f"No existe {paquete_path}. Ejecute antes: python PREDECIR_JORNADA.py --jornada {jornada}"
        )
    jornada_path = settings.DATOS_DIR / f"QUINIELA15_J{jornada}.json"
    if not jornada_path.exists():
        raise SystemExit(f"No existe {jornada_path}")

    paquete = json.loads(paquete_path.read_text(encoding="utf-8"))
    fuente = json.loads(jornada_path.read_text(encoding="utf-8"))
    por_num = {int(p["num"]): p for p in fuente.get("partidos", [])}

    boleto = paquete.get("boleto_optimizado") or {}
    desarrollo = boleto.get("desarrollo") or []
    if len(desarrollo) != 14:
        raise SystemExit(f"El paquete no trae 14 partidos en boleto_optimizado ({len(desarrollo)})")

    pleno_modelo = (paquete.get("pleno15") or {}).get("modelo_maestro") or {}
    seleccion = pleno_modelo.get("seleccion") or {}
    pleno_signo = f"{seleccion.get('local', '-')}-{seleccion.get('visitante', '-')}"
    if "-" in (seleccion.get("local"), seleccion.get("visitante")):
        raise SystemExit("El modelo no ha producido buckets para el Pleno al 15")

    probs_por_num = {}
    for partido in paquete.get("partidos", []):
        mm = partido.get("modelo_maestro") or {}
        if int(partido["num"]) == 15 or not mm.get("disponible") or "prob_1" not in mm:
            continue
        probs_por_num[int(partido["num"])] = {
            "1": mm["prob_1"],
            "X": mm["prob_x"],
            "2": mm["prob_2"],
        }

    signos: list[str] = []
    detalle_partidos = []
    motivos: list[str] = []
    dobles: list[int] = []

    for item in desarrollo:
        num = int(item["num"])
        signo = str(item["label"])
        signos.append(signo)
        if len(signo) == 2:
            dobles.append(num)
        probs = probs_por_num.get(num)
        origen = por_num.get(num, {})
        detalle_partidos.append(
            {
                "num": num,
                "local": origen.get("local"),
                "visitante": origen.get("visitante"),
                "signo": signo,
                "prob": {k: round(v, 3) for k, v in probs.items()} if probs else None,
            }
        )
        motivos.append(_auto_motivo(num, origen, probs, signo) if probs else "")

    signos.append(pleno_signo)
    motivos.append(_pleno_motivo(pleno_modelo, pleno_signo))

    if motivos_override:
        if len(motivos_override) != 15:
            raise SystemExit(f"--motivos debe traer 15 textos, trae {len(motivos_override)}")
        motivos = list(motivos_override)

    pleno_origen = por_num.get(15, {})
    predicciones = {
        "jornada": jornada,
        "temporada": "2026-2027",
        "generado_en": paquete.get("fecha_generacion"),
        "nota": (
            f"Boleto del PROGRAMA para la J{jornada}, generado por el motor de "
            "Purplerave/PROGRAMAQUINIELA. Tres dobles: 8 columnas x 0,75 EUR = 6,00 EUR, "
            "Pleno al 15 aparte."
        ),
        "fuente": {
            "repo": "Purplerave/PROGRAMAQUINIELA",
            "comando": f"python PREDECIR_JORNADA.py --jornada {jornada}",
            "salida": f"SALIDAS/paquete_jornada_J{jornada}.json",
            "datos_jornada": f"DATOS/QUINIELA15_J{jornada}.json",
            "config": paquete.get("version_config"),
            "modelo": (paquete.get("modelo_info") or {}).get("version"),
            "mercado": (fuente.get("fuentes") or {}).get("mercado", {}).get("consultado_en"),
        },
        "programa": {"signos": signos, "nombre": "PROGRAMA", "puntos_jornada": 0},
        "detalle_programa": {
            "dobles": dobles,
            "columnas": boleto.get("n_columnas"),
            "coste_euros": boleto.get("coste_euros"),
            "aciertos_esperados": round(float(boleto.get("aciertos_esperados", 0)), 3),
            "probabilidades_acierto": {
                k: round(v, 4) for k, v in (boleto.get("probabilidades_exactas") or {}).items()
            },
            "partidos": detalle_partidos,
            "pleno15": {
                "num": 15,
                "local": pleno_origen.get("local"),
                "visitante": pleno_origen.get("visitante"),
                "signo": pleno_signo,
                "modelo": pleno_modelo.get("modelo"),
                "lambdas": pleno_modelo.get("lambdas"),
                "goles_local": pleno_modelo.get("goles_local"),
                "goles_visitante": pleno_modelo.get("goles_visitante"),
            },
        },
    }

    reasons = {str(jornada): {"programa": motivos}}
    return predicciones, reasons, signos


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Exporta el boleto del motor al formato de liga-maestros-web."
    )
    parser.add_argument("--jornada", "-j", type=int, required=True)
    parser.add_argument(
        "--motivos",
        default=None,
        help='JSON con {"motivos": [...15 textos...]} para sustituir los generados',
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    override = None
    if args.motivos:
        payload = json.loads(Path(args.motivos).read_text(encoding="utf-8"))
        override = payload.get("motivos") if isinstance(payload, dict) else payload

    predicciones, reasons, signos = build_export(args.jornada, override)

    pred_path = EXPORT_DIR / f"predicciones_J{args.jornada}.json"
    reasons_path = EXPORT_DIR / f"PREDICTION_REASONS_J{args.jornada}.json"
    if not args.dry_run:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        pred_path.write_text(
            json.dumps(predicciones, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        reasons_path.write_text(
            json.dumps(reasons, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    print(f"boleto  : {' '.join(signos)}")
    print(f"dobles  : {predicciones['detalle_programa']['dobles']}")
    print(f"coste   : {predicciones['detalle_programa']['coste_euros']} EUR")
    print(f"escribe : {pred_path}{' (dry-run)' if args.dry_run else ''}")
    print(f"          {reasons_path}{' (dry-run)' if args.dry_run else ''}")
    print()
    print("En liga-maestros-web:")
    print(f"  copiar predicciones_J{args.jornada}.json a data/")
    print(f"  fusionar PREDICTION_REASONS_J{args.jornada}.json en data/PREDICTION_REASONS.json")
    print(f"  ensure_jornada_{args.jornada}() debe llamar a _import_programa_ticket(conn, {args.jornada})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
