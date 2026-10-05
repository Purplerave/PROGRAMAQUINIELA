"""
DESCARGAR_BOLETO_QUINIELA15.py — Paso 1 del ciclo semanal automatico.

Descarga la proxima quiniela desde quiniela15.com (HTML server-rendered),
extrae las 15 casillas (numero, local, visitante, dia+hora), detecta las
de Liga F por el sufijo "(F)" y guarda:

    DATOS/BOLETO_SEMANAL.json     <- fuente de verdad de RUN_SEMANA_COMPLETA
    SALIDAS/raw_quiniela15.html   <- evidencia cruda para auditoria/debug

Validacion estricta: si no encuentra exactamente 15 casillas, NO escribe
nada nuevo y sale con error (mejor fallar que inventar).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATOS = ROOT / "DATOS"
URL = "https://www.quiniela15.com/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def get(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "es-ES,es;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def quitar_tags(fragmento: str) -> str:
    txt = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", fragmento)
    txt = re.sub(r"<[^>]+>", "\n", txt)
    lineas = [l.strip() for l in txt.splitlines() if l.strip()]
    return "\n".join(lineas)


HORA_RE = re.compile(r"^[DLVMSJX]\s+\d{1,2}:\d{2}$")


def parsear_filas(html: str) -> list[dict]:
    """Parseo por filas de la tabla (Local, Visitante, Sis., Usu., Hora).

    El parseo anterior por marcas `>N<` fallaba porque Sis./Usu. tambien
    contienen celdas numericas 1..15: cada casilla heredaba la hora de la
    fila anterior (y la 1 quedaba vacia). Aqui se consume la tabla en
    orden: numero esperado 1..15, local, visitante y la primera celda
    con patron dia+hora posterior.
    """
    m_hora = re.search(r"Hora", html)
    if not m_hora:
        return []
    fin_opcs = [html.find("Resultados en directo", m_hora.end()),
                html.find("Haz tu pronóstico", m_hora.end())]
    fin = min([x for x in fin_opcs if x > 0], default=len(html))
    frag = html[m_hora.end():fin]
    toks = [l for l in quitar_tags(frag).splitlines()
            if l and not l.startswith("Escudo") and "src=" not in l
            and not l.startswith("<img")]
    filas: list[dict] = []
    esperado, k = 1, 0
    while k < len(toks) and esperado <= 15:
        if toks[k] != str(esperado):
            k += 1
            continue
        if k + 2 >= len(toks):
            break
        local, visitante = toks[k + 1], toks[k + 2]
        if (not re.fullmatch(r"[A-Za-zÁÉÍÓÚáéíóúÑñ.'()\-/ ]{3,34}", local)
                or not re.fullmatch(r"[A-Za-zÁÉÍÓÚáéíóúÑñ.'()\-/ ]{3,34}", visitante)):
            k += 1
            continue
        j = k + 3
        while j < len(toks) and not HORA_RE.match(toks[j]):
            j += 1
        if j >= len(toks) or j - (k + 3) > 6:
            k += 1
            continue
        inter = toks[k + 3:j]
        filas.append({"numero": esperado, "local": local,
                      "visitante": visitante,
                      "sistema": inter[0] if len(inter) > 0 else "",
                      "comunidad": inter[-1] if len(inter) > 1 else "",
                      "dia_hora": toks[j]})
        esperado += 1
        k = j + 1
    return filas


def parsear(html: str) -> dict:
    # Bloque entre el titulo del pronostico y el texto del cierre/bote
    m_jor = re.search(r"jornada\s+(\d{1,2})", html, re.I)
    m_bote = re.search(r"bote[^0-9]{0,40}([\d][\d.]{2,12})\s*(?:€|eur)", html, re.I)
    inicio = html.find("Local")
    fin_opcs = [html.find("Resultados en directo"), html.find("Haz tu pronóstico")]
    fin = min([x for x in fin_opcs if x > 0], default=len(html))
    bloque = html[inicio:fin] if 0 < inicio < fin else html

    # posiciones de numeros de casilla (celda suelta 1..15)
    filas = parsear_filas(html)
    casillas = []
    if len(filas) == 15 and all(f["local"] and f["visitante"] for f in filas):
        casillas = filas
    else:
        marcas = [(mm.start(), int(mm.group(1)))
                  for mm in re.finditer(r">(\d{1,2})<", bloque)
                  if 1 <= int(mm.group(1)) <= 15]
        # dedup consecutivos manteniendo orden ascendente estricto
        limpios, esperado = [], 1
        for pos, num in marcas:
            if num == esperado:
                limpios.append((pos, num))
                esperado += 1
            elif limpios and num == limpios[-1][1]:
                continue
        casillas = []
        for i, (pos, num) in enumerate(limpios):
            hasta = limpios[i + 1][0] if i + 1 < len(limpios) else len(bloque)
            frag = quitar_tags(bloque[pos:hasta])
            lineas = frag.splitlines()
            equipos = [l for l in lineas
                       if re.fullmatch(r"[A-Za-zÁÉÍÓÚáéíóúÑñ.'()\-/ ]{3,34}", l)
                       and not re.match(r"^[DLVMS]\s\d", l)]
            m_hora = re.search(r"\b([DLVMS])\s+(\d{1,2}:\d{2})\b", frag)
            local = visitante = ""
            for j, l in enumerate(equipos):
                if re.match(r"^\d+$", l):
                    continue
                if not local:
                    local = l
                elif not visitante:
                    visitante = l
                    break
            casillas.append({"numero": num, "local": local,
                             "visitante": visitante,
                             "dia_hora": (m_hora.group(0) if m_hora else "")})
    doc = {
        "fuente": "quiniela15.com",
        "capturado": datetime.now().isoformat(timespec="seconds"),
        "jornada": int(m_jor.group(1)) if m_jor else None,
        "bote_eur": float(m_bote.group(1).replace(".", "")) if m_bote else None,
        "casillas": casillas,
    }
    return doc


def marcar_ligaf(doc: dict) -> None:
    for c in doc["casillas"]:
        lf = "(f)" in c["local"].lower() or "(f)" in c["visitante"].lower()
        c["liga_f"] = lf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default=str(DATOS / "BOLETO_SEMANAL.json"))
    args = ap.parse_args()

    html = get(URL)
    (ROOT / "SALIDAS" / "raw_quiniela15.html").write_text(html[:400000],
                                                          encoding="utf-8")
    doc = parsear(html)
    n = len(doc["casillas"])
    incompletas = [c for c in doc["casillas"] if not c["local"] or not c["visitante"]]
    print(f"[quiniela15] jornada={doc['jornada']} casillas={n} "
          f"incompletas={len(incompletas)} bote={doc['bote_eur']}")
    for c in doc["casillas"]:
        print(f"  {c['numero']:>2}. {c['local']} - {c['visitante']} ({c['dia_hora']})")
    if n != 15 or incompletas:
        print("[ERROR] Parseo incompleto: revisar SALIDAS/raw_quiniela15.html")
        sys.exit(1)
    marcar_ligaf(doc)
    Path(args.salida).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
    print("Guardado:", args.salida)


if __name__ == "__main__":
    main()
