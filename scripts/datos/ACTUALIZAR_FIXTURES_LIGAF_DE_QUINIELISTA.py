"""
ACTUALIZAR_FIXTURES_LIGAF_DE_QUINIELISTA.py — D6 (v1 honesta).

Fuente: XML OFICIAL de la LAE via quinielista.es (misma fuente que ya usa
DESCARGAR_QUINIELISTA_XML.py). El boletin oficial trae las 15 casillas
numeradas, INCLUIDAS las de Liga F desde la temporada 2026-27.

Problema resuelto: Wikipedia aun no publica la temporada actual y FBref
bloquea bots (403 verificado 2026-08-25). El boletin LAE es la fuente
primaria correcta: ES literalmente la lista de partidos del boleto.

Deteccion Liga F: una casilla es candidata si AMBOS equipos canonizan al
universo de clubes Liga F (canon() del motor). Nombres ambiguos con la
liga masculina (Valencia, Espanyol, Eibar, Athletic...) se marcan
REVISAR=1 para confirmacion humana de 10 segundos. Nunca se adivina en
silencio.

Uso:
    python ACTUALIZAR_FIXTURES_LIGAF_DE_QUINIELISTA.py --jornada 3 --temporada 2627
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

from motor.ligaf_model import canon  # noqa: E402
from DESCARGAR_QUINIELISTA_XML import URLS, USER_AGENT, parse_and_validate, fetch_xml  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "DATOS" / "ligaf" / "proxima_jornada_ligaf.csv"

# Clubes cuyo canon SOLO existe en Liga F (sin ambiguedad masculina)
CLUBES_LIGAF_UNICOS = {
    "badalona", "las_planas", "tenerife", "barcelona", "madridcff",
    "dep_coruna", "alhama", "logrono", "sporting_huelva",
}


def es_candidata_ligaf(local: str, visitante: str) -> tuple[bool, int]:
    cl, cv = canon(local), canon(visitante)
    unicos = {cl, cv} & CLUBES_LIGAF_UNICOS
    ambos = cl in _UNIVERSE and cv in _UNIVERSE
    return ambos, len(unicos)


def cargar_universo() -> set[str]:
    global _UNIVERSE
    ruta = ROOT / "DATOS" / "ligaf" / "ligaf_resultados_2324_dated.csv"
    universo = set()
    if ruta.exists():
        import csv as _csv
        with open(ruta, encoding="utf-8") as f:
            for r in _csv.DictReader(f):
                universo.add(canon(r["local"]))
                universo.add(canon(r["visitante"]))
    universo |= CLUBES_LIGAF_UNICOS | {"atletico", "athletic", "rmadrid", "rso",
                                        "betis", "sevilla", "villarreal", "granada",
                                        "eibar", "espanyol", "valencia", "levante"}
    _UNIVERSE = universo
    return universo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jornada", type=int, required=True)
    ap.add_argument("--temporada", type=int, default=2627)
    args = ap.parse_args()

    url = URLS["lae"].format(jornada=args.jornada, temporada=args.temporada)
    print(f"[lae] descargando {url}", flush=True)
    xml_bytes = fetch_xml(url)
    if b'activo="no"' in xml_bytes:
        print(f"[espera] La jornada {args.jornada}/{args.temporada} AUN NO ESTA PUBLICADA "
              f"por la LAE (activo=\"no\", casillas vacias).")
        print("         Reintenta cuando se publique (habitualmente jueves-viernes).")
        return
    partidos = parse_and_validate(xml_bytes, args.jornada, args.temporada)

    cargar_universo()
    filas = []
    for p in partidos:
        cand, n_unicos = es_candidata_ligaf(p.get("local", ""), p.get("visitante", ""))
        if cand:
            revisar = 1 if n_unicos == 0 else 0
            filas.append({"numero": p["num"], "local": p["local"],
                          "visitante": p["visitante"], "revisar": revisar})

    FIXTURES.parent.mkdir(parents=True, exist_ok=True)
    with open(FIXTURES, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["numero", "local", "visitante", "revisar"])
        w.writeheader()
        w.writerows(filas)

    print(f"[ok] {len(filas)} candidatas Liga F escritas en {FIXTURES}")
    for fila in filas:
        marca = "REVISAR (nombres ambiguos)" if fila["revisar"] else "ok"
        print(f"  casilla {fila['numero']}: {fila['local']} - {fila['visitante']}  [{marca}]")
    print("[nota] Confirma las marcadas REVISAR y borra la columna 'revisar' si quieres;")
    print("       PREDICCION_BOLETO_COMPLETO ya acepta la columna 'numero'.")


if __name__ == "__main__":
    main()
