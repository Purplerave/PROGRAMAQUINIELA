"""
INYECTAR_CUOTAS_JORNADA.py — Inyecta cuotas reales de casas al JSON de jornada.

Uso semanal (lunes sin mercado -> jueves con mercado):
    1. Rellenar DATOS/CUOTAS_J{N}.csv con las cuotas 1X2 vistas en la casa
       (bet365 u otra) + instante de observacion (odds_observed_at).
    2. python scripts/datos/INYECTAR_CUOTAS_JORNADA.py --jornada N --csv DATOS/CUOTAS_J12.csv
    3. Re-ejecutar: python PREDECIR_JORNADA.py --jornada N

Reglas (AGENTS.md):
    - Solo cuotas REALES de casas. Nunca APU/LAE/Q15 ni porcentajes de
      publico: el motor las rechaza como mercado.
    - Cada fila declara odds_observed_at (cuando se vieron). Sin timestamp
      no hay trazabilidad: el script lo exige.
    - Hace backup DATOS/QUINIELA15_J{N}.json.bak antes de tocar nada.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATOS = ROOT / "DATOS"
sys.path.insert(0, str(ROOT))

PLENO_NUM = 15


def _f(value: str, campo: str, num: int) -> float:
    try:
        v = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        raise ValueError(f"casilla {num}: {campo} no numerico ({value!r})")
    if not v > 1.01:
        raise ValueError(f"casilla {num}: {campo}={v} no parece cuota (>1.01)")
    return v


def leer_csv(ruta: Path) -> dict[int, dict]:
    if not ruta.exists():
        raise FileNotFoundError(f"No existe: {ruta}")
    filas: dict[int, dict] = {}
    with ruta.open(encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            if not (row.get("num") or "").strip():
                continue
            num = int(row["num"])
            if num == PLENO_NUM:
                print(f"  aviso: casilla 15 ignorada (el pleno usa Dixon-Coles, no 1X2)")
                continue
            o1 = _f(row.get("odd_1", ""), "odd_1", num)
            ox = _f(row.get("odd_x", ""), "odd_x", num)
            o2 = _f(row.get("odd_2", ""), "odd_2", num)
            margen = 1 / o1 + 1 / ox + 1 / o2
            if not 1.0 <= margen <= 1.35:
                print(f"  aviso: casilla {num} overround raro ({margen:.3f}), revisa cifras")
            obs = (row.get("odds_observed_at") or "").strip()
            if not obs:
                raise ValueError(f"casilla {num}: falta odds_observed_at (trazabilidad obligatoria)")
            fila: dict = {"odd_1": o1, "odd_x": ox, "odd_2": o2,
                          "odds_observed_at": obs,
                          "odds_source": (row.get("fuente") or "casa (manual)").strip()}
            for k in ("open_odd_1", "open_odd_x", "open_odd_2"):
                if (row.get(k) or "").strip():
                    fila[k] = _f(row.get(k), k, num)
            filas[num] = fila
    faltan = [n for n in range(1, 15) if n not in filas]
    if faltan:
        # Hueco documentado (p. ej. casilla 1 J12 sin cuotas publicadas aun):
        # se inyecta el resto y el motor usa HGB+Poisson con aviso en el
        # faltante. Falla solo si no hay NINGUNA cuota valida.
        if len(filas) == 0:
            raise ValueError("CSV sin cuotas validas")
        print(f"  aviso: sin cuotas en casillas {faltan} (fallback HGB+Poisson con aviso)")
    return filas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jornada", type=int, required=True)
    ap.add_argument("--csv", default=None)
    args = ap.parse_args()

    ruta_json = DATOS / f"QUINIELA15_J{args.jornada}.json"
    if not ruta_json.exists():
        print(f"[ERROR] No existe {ruta_json}")
        return 1
    ruta_csv = Path(args.csv) if args.csv else DATOS / f"CUOTAS_J{args.jornada}.csv"

    try:
        cuotas = leer_csv(ruta_csv)
    except (FileNotFoundError, ValueError) as e:
        print(f"[ERROR] {e}")
        return 1

    doc = json.loads(ruta_json.read_text(encoding="utf-8"))
    backup = ruta_json.with_suffix(".json.bak")
    shutil.copy2(ruta_json, backup)

    n = 0
    for p in doc.get("partidos", []):
        if p.get("num") in cuotas:
            p.update(cuotas[p["num"]])
            n += 1
    ruta_json.write_text(json.dumps(doc, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(f"Inyectadas cuotas en {n} partidos de J{args.jornada} (backup: {backup.name})")
    print(f"Siguiente: python PREDECIR_JORNADA.py --jornada {args.jornada}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
