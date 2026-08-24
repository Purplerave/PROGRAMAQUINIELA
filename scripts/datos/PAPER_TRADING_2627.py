#!/usr/bin/env python3
"""Tracker de paper-trading 2026-27 (Misión B / REVISION_14).

Regla PRE-REGISTRADA e inamovible:
  - Apuesta virtual 1 u. al VISITANTE si cuota de cierre ∈ [1.8, 2.5).
  - Opcional (no cuenta para el veredicto): LOCAL cuota [1.4, 1.8).
  - Fuente: football-data.co.uk SP1 (Primera). Cierre: PSCH/PSCA, si no B365C*, si no B365*.

Evaluación:
  - Intermedia ~enero 2027 (n≈70)
  - Final ~junio 2027 (n≈120-140)
  - Si ROI visitante ≥ +5% con n suficiente → integrar como banda extra (con CAP).
  - Si ROI ≤ 0 → cerrar la señal.

No reoptimizar umbrales tras ver resultados.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import settings

FD_URL = "https://www.football-data.co.uk/mmz4281/2627/SP1.csv"
TRACK_CSV = settings.DATOS_DIR / "paper_trading_2627.csv"
TRACK_JSON = settings.DATOS_DIR / "paper_trading_2627.json"

COLS = [
    "fecha",
    "jornada",
    "local",
    "visita",
    "cuota_cierre_visitante",
    "cuota_cierre_local",
    "banda",
    "apuesta",
    "resultado",
    "acierto",
    "profit_1u",
    "notas",
]


def _ff(v):
    try:
        x = float(v)
        return x if x > 1.01 else None
    except (TypeError, ValueError):
        return None


def _odds(row):
    h = _ff(row.get("PSCH")) or _ff(row.get("B365CH")) or _ff(row.get("B365H"))
    d = _ff(row.get("PSCD")) or _ff(row.get("B365CD")) or _ff(row.get("B365D"))
    a = _ff(row.get("PSCA")) or _ff(row.get("B365CA")) or _ff(row.get("B365A"))
    return h, d, a


def fetch_sp1(url: str = FD_URL) -> list[dict]:
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            raw = resp.read().decode("latin-1")
    except Exception as exc:
        print(f"[paper] no se pudo descargar {url}: {exc}")
        return []
    lines = raw.splitlines()
    if not lines:
        return []
    return list(csv.DictReader(lines))


def select_bets(rows: list[dict]) -> list[dict]:
    out = []
    jornada = 0
    last_date = None
    for row in rows:
        ftr = (row.get("FTR") or "").strip()
        fecha = row.get("Date") or ""
        if fecha != last_date:
            if last_date is not None:
                jornada += 1
            last_date = fecha
        h, d, a = _odds(row)
        if a is None or h is None:
            continue
        banda = None
        apuesta = None
        cuota = None
        if 1.8 <= a < 2.5:
            banda = "visita_1.8_2.5"
            apuesta = "2"
            cuota = a
        # opcional, no entra en veredicto principal
        elif 1.4 <= h < 1.8:
            banda = "local_1.4_1.8_opcional"
            apuesta = "1"
            cuota = h
        else:
            continue
        acierto = ""
        profit = ""
        if ftr in {"H", "D", "A"}:
            won = (apuesta == "1" and ftr == "H") or (apuesta == "2" and ftr == "A")
            acierto = "1" if won else "0"
            profit = f"{(cuota - 1):.3f}" if won else "-1.000"
        out.append(
            {
                "fecha": fecha,
                "jornada": jornada + 1,
                "local": row.get("HomeTeam") or "",
                "visita": row.get("AwayTeam") or "",
                "cuota_cierre_visitante": f"{a:.3f}" if a else "",
                "cuota_cierre_local": f"{h:.3f}" if h else "",
                "banda": banda,
                "apuesta": apuesta,
                "resultado": ftr,
                "acierto": acierto,
                "profit_1u": profit,
                "notas": "regla_pre_registrada_REVISION_14",
            }
        )
    return out


def summarize(bets: list[dict]) -> dict:
    core = [b for b in bets if b["banda"] == "visita_1.8_2.5" and b["acierto"] in {"0", "1"}]
    n = len(core)
    wins = sum(1 for b in core if b["acierto"] == "1")
    pnl = sum(float(b["profit_1u"]) for b in core) if n else 0.0
    stake = float(n)
    roi = (pnl / stake) if stake else None
    return {
        "regla": "apostar visitante si cuota cierre [1.8, 2.5)",
        "n_cerrados_core": n,
        "aciertos": wins,
        "hit_rate": (wins / n) if n else None,
        "pnl_1u": pnl,
        "roi": roi,
        "veredicto_provisional": (
            "muestra_insuficiente"
            if n < 40
            else ("integrar_si_sostiene" if roi is not None and roi >= 0.05 else ("cerrar" if roi is not None and roi <= 0 else "seguir"))
        ),
        "evaluacion_intermedia": "enero 2027 (n≈70)",
        "evaluacion_final": "junio 2027 (n≈120-140)",
        "n_filas_totales": len(bets),
    }


def write_tracker(bets: list[dict]) -> None:
    settings.DATOS_DIR.mkdir(parents=True, exist_ok=True)
    with TRACK_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(bets)
    summary = summarize(bets)
    payload = {
        "temporada": "2026-27",
        "fuente": FD_URL,
        "columnas": COLS,
        "resumen": summary,
        "apuestas": bets,
    }
    TRACK_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"escrito {TRACK_CSV} ({len(bets)} filas)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=FD_URL)
    parser.add_argument("--offline", action="store_true", help="no descarga; reescribe resumen del CSV existente")
    args = parser.parse_args()
    if args.offline and TRACK_CSV.is_file():
        with TRACK_CSV.open(encoding="utf-8") as fh:
            bets = list(csv.DictReader(fh))
        write_tracker(bets)
        return
    rows = fetch_sp1(args.url)
    bets = select_bets(rows)
    write_tracker(bets)


if __name__ == "__main__":
    main()
