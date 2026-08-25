"""
BACKTEST_LIGAF_2324.py — Verificacion del modulo oficial ligaf_model
sobre el backbone REAL de StatsBomb (240 partidos, temporada 2023/2024).

Protocolo walk-forward honesto: warmup 60, refit cada 15, metricas solo
sobre partidos nunca vistos. Salida: SALIDAS/backtest_ligaf_2324.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.ligaf_model import cargar_dated, walkforward  # noqa: E402

SALIDAS = Path(__file__).resolve().parents[2] / "SALIDAS"


def main():
    partidos = cargar_dated()
    print(f"backbone real: {len(partidos)} partidos "
          f"({partidos[0]['fecha'].date()} .. {partidos[-1]['fecha'].date()})", flush=True)
    res = walkforward(partidos)
    res["fuente"] = "StatsBomb Open Data, comp 182 / season 281 (Liga F 23-24)"
    res["generado"] = datetime.now().isoformat()
    print(json.dumps(res, indent=2))
    SALIDAS.mkdir(exist_ok=True)
    out = SALIDAS / "backtest_ligaf_2324.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Guardado:", out)


if __name__ == "__main__":
    main()
