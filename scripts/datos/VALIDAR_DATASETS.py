#!/usr/bin/env python3
"""CLI de solo lectura para la auditoría reproducible de datasets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dataset_quality import audit_datasets, format_summary  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspecciona los datasets sin modificarlos ni generar salidas por defecto."
    )
    parser.add_argument(
        "--json",
        type=Path,
        metavar="RUTA",
        help="guarda la evidencia completa en JSON únicamente cuando se solicita",
    )
    parser.add_argument(
        "--overround-min",
        type=float,
        default=1.0,
        help="límite inferior abierto para marcar overround (por defecto: 1.0)",
    )
    parser.add_argument(
        "--overround-max",
        type=float,
        default=1.4,
        help="límite superior abierto para marcar overround (por defecto: 1.4)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.overround_min >= args.overround_max:
        parser.error("--overround-min debe ser menor que --overround-max")

    report = audit_datasets(
        PROJECT_ROOT,
        overround_min=args.overround_min,
        overround_max=args.overround_max,
    )
    print(format_summary(report))

    if args.json is not None:
        output_path = args.json.expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with output_path.open("x", encoding="utf-8") as handle:
                json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.write("\n")
        except FileExistsError:
            print(
                f"ERROR: la ruta de evidencia ya existe; no se sobrescribe: {output_path}",
                file=sys.stderr,
            )
            return 2
        print(f"\nEvidencia JSON guardada en: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
