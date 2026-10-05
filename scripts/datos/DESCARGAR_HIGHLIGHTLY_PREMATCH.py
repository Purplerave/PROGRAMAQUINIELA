"""
DESCARGAR_HIGHLIGHTLY_PREMATCH.py — Señal externa Highlightly para la jornada.

Descarga las probabilidades prematch three-way del modelo de Highlightly
(host PRO: soccer.highlightly.net, plan con 7500 llamadas/dia) para los
15 partidos de DATOS/QUINIELA15_J{N}.json y las guarda como comparativa:

    partido["hl"] = {"1": p1, "X": px, "2": p2}
    partido["hl_generated_at"] = <ultimo generatedAt del proveedor>
    partido["hl_match_id"] = <id Highlightly>

REGLA DE ORO (AGENTS.md #2, #5): esto NO son cuotas de mercado y NUNCA
entran en odd_*/open_* ni en el ensemble. Solo comparativa, como
APU/LAE/Q15. El peso market=0.951 del motor exige dinero real.

Uso:
    python scripts/datos/DESCARGAR_HIGHLIGHTLY_PREMATCH.py --jornada 12

Requiere HIGHLIGHTLY_API_KEY en entorno o .env (nunca en el repo).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import unicodedata
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
DATOS = ROOT / "DATOS"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "datos"))

HOST = "https://soccer.highlightly.net"
TIMEOUT = 25

try:
    from highlightly_client import obtener_api_key
except ImportError:  # pragma: no cover
    obtener_api_key = None


def norm(nombre: str) -> str:
    txt = unicodedata.normalize("NFKD", nombre or "")
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return " ".join(txt.lower().replace(".", "").split())


def canon(nombre: str) -> str:
    """Canon simple jornada<->Highlightly (tolerante a formas legales)."""
    try:
        from scripts.motor.team_names import resolve_history_name
        return norm(resolve_history_name(nombre))
    except Exception:
        return norm(nombre)


def solapan(corto: str, largo: str) -> bool:
    """True si todo token significativo de `corto` aparece en `largo`."""
    stop = {"de", "la", "el", "del", "cf", "cd", "ud", "sd", "rc", "ad",
            "fc", "r", "ii", "b", "at"}
    tc = [t for t in norm(corto).split() if t not in stop]
    tl = set(norm(largo).split())
    return bool(tc) and all(t in tl for t in tc)


def emparejar(partido: dict, candidatos: list[dict]) -> dict:
    """Empareja un partido del boleto con su match Highlightly (univoco)."""
    loc, vis = partido.get("local", ""), partido.get("visitante", "")
    buenos = []
    for m in candidatos:
        h = ((m.get("homeTeam") or {}).get("name")) or ""
        a = ((m.get("awayTeam") or {}).get("name")) or ""
        if canon(loc) == canon(h) and canon(vis) == canon(a):
            buenos.append((m, "canon"))
        elif solapan(loc, h) and solapan(vis, a):
            buenos.append((m, "fuzzy"))
    if len(buenos) == 1:
        return buenos[0][0]
    detalle = [(b[0].get("id"), ((b[0].get("homeTeam") or {}).get("name")),
                ((b[0].get("awayTeam") or {}).get("name")), b[1]) for b in buenos]
    raise ValueError(f"casilla {partido.get('num')}: match ambiguo o ausente "
                     f"({loc}-{vis}): {detalle}")


def ultimo_prematch(detalle: list | dict) -> tuple[dict, str]:
    if isinstance(detalle, dict):
        detalle = [detalle]
    cands = []
    for d in detalle:
        preds = (d.get("predictions") or {}).get("prematch") or []
        for p in preds:
            if p.get("modelType") != "three-way":
                continue
            probs = p.get("probabilities") or {}
            try:
                cands.append((p.get("generatedAt", ""), {
                    "1": float(str(probs["home"]).rstrip("%")) / 100.0,
                    "X": float(str(probs["draw"]).rstrip("%")) / 100.0,
                    "2": float(str(probs["away"]).rstrip("%")) / 100.0}))
            except (KeyError, ValueError, TypeError):
                continue
    if not cands:
        raise ValueError("sin prematch three-way en el detalle")
    cands.sort(key=lambda c: c[0])
    return cands[-1][1], cands[-1][0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jornada", type=int, required=True)
    args = ap.parse_args()

    if obtener_api_key is None:
        print("[ERROR] no se pudo importar highlightly_client")
        return 1
    try:
        key = obtener_api_key()
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        return 1
    headers = {"x-rapidapi-key": key}

    ruta = DATOS / f"QUINIELA15_J{args.jornada}.json"
    doc = json.loads(ruta.read_text(encoding="utf-8"))
    partidos = doc.get("partidos", [])

    fechas = sorted({p.get("fecha", "") for p in partidos if p.get("fecha")})
    bolsa: list[dict] = []
    llamadas = 0
    for fecha in fechas:
        for params in ({"date": fecha, "leagueName": "La Liga"},
                       {"date": fecha, "leagueId": 120775}):
            params = {**params, "timezone": "Europe/Madrid", "limit": 100}
            r = requests.get(f"{HOST}/matches", params=params,
                             headers=headers, timeout=TIMEOUT)
            r.raise_for_status()
            llamadas += 1
            bolsa.extend(r.json().get("data", []))
            time.sleep(1)
    print(f"[hl] {len(bolsa)} partidos API en {len(fechas)} fechas ({llamadas} llamadas)")

    backup = ruta.with_suffix(".json.bak")
    shutil.copy2(ruta, backup)
    ok = 0
    for p in partidos:
        m = emparejar(p, [c for c in bolsa if (c.get("date") or "")[:10] == p.get("fecha")])
        det = requests.get(f"{HOST}/matches/{m['id']}", headers=headers,
                           timeout=TIMEOUT).json()
        llamadas += 1
        probs, gen = ultimo_prematch(det)
        p["hl"] = probs
        p["hl_generated_at"] = gen
        p["hl_match_id"] = m["id"]
        ok += 1
        time.sleep(1)
    doc["hl_source"] = ("Highlightly PRO prematch three-way "
                        f"({ok} partidos, {llamadas} llamadas API). COMPARATIVA "
                        "unicamente: no son cuotas de mercado, no entran al modelo.")
    ruta.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[hl] J{args.jornada}: prematch en {ok} partidos (backup {backup.name}, "
          f"total llamadas API: {llamadas})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
