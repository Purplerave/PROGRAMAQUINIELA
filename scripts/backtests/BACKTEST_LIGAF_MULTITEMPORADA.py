#!/usr/bin/env python3
"""Backtest walk-forward diario del histórico multitemporada de Liga F."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, UTC
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.motor import ligaf_model


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "salida" / "backtest_ligaf_multitemporada.json",
        help="ruta de salida JSON",
    )
    args = parser.parse_args(argv)

    matches = ligaf_model.cargar_dated()
    if not matches:
        parser.error("el histórico Liga F está vacío")
    results = ligaf_model.walkforward(matches)
    baseline = ligaf_model.BASE / "ligaf_resultados_2324_dated.csv"
    supplemental = ligaf_model.BASE / "liga_f_partidos_2023-27.csv"
    payload = {
        "protocolo": results["protocolo"],
        "interpretacion": (
            "Walk-forward retrospectivo por día; no demuestra ventaja futura ni compara con cuotas."
        ),
        "generado_utc": datetime.now(UTC).isoformat(),
        "rango_fechas": [matches[0]["fecha"].date().isoformat(), matches[-1]["fecha"].date().isoformat()],
        "n_partidos": len(matches),
        "fuentes": [
            {
                "archivo": baseline.name,
                "sha256": sha256(baseline),
                "procedencia": "StatsBomb Open Data, Liga F 2023/24; ver MANIFIESTO_FUENTES.json",
            },
            {
                "archivo": supplemental.name,
                "sha256": sha256(supplemental),
                "procedencia": "Archivo proporcionado por el usuario; origen/licencia no verificados",
            },
        ],
        "metricas": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
    print(f"\nGuardado: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
