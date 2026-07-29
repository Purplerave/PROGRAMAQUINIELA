#!/usr/bin/env python3
"""CLI de generación de datos saneados.

No genera salidas por defecto; exige ``--confirm`` explícito.
No sobrescribe archivos existentes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sanitization import run_pipeline, format_summary, DEFAULT_OUTPUT_DIR, DEFAULT_RAW_BASE  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Saneamiento de datos: lee los CSV originales, aplica "
            "transformaciones reproducibles y escribe bajo salida/datos_limpios/. "
            "No genera salidas por defecto; use --confirm."
        ),
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="escribe los archivos saneados bajo salida/datos_limpios/",
    )
    parser.add_argument(
        "--raw-base",
        type=Path,
        default=DEFAULT_RAW_BASE,
        help="directorio base de los CSV originales (por defecto: DATOS/historico_raw)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="directorio de salida (por defecto: salida/datos_limpios/)",
    )
    parser.add_argument(
        "--overround-min",
        type=float,
        default=1.0,
        help="límite inferior abierto para marcar overround sospechoso (por defecto: 1.0)",
    )
    parser.add_argument(
        "--overround-max",
        type=float,
        default=1.4,
        help="límite superior abierto para marcar overround sospechoso (por defecto: 1.4)",
    )
    parser.add_argument(
        "--alias",
        nargs=2,
        action="append",
        metavar=("ORIGEN", "DESTINO"),
        dest="aliases",
        help="alias adicional (puede repetirse); p.ej. --alias Leonesa 'Cultural Leonesa'",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.overround_min >= args.overround_max:
        parser.error("--overround-min debe ser menor que --overround-max")

    alias_map: dict[str, str] | None = None
    if args.aliases:
        alias_map = dict(args.aliases)

    try:
        result = run_pipeline(
            raw_base=args.raw_base,
            output_dir=args.output_dir,
            confirm=args.confirm,
            overround_min=args.overround_min,
            overround_max=args.overround_max,
            alias_map=alias_map,
        )
    except (FileExistsError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(format_summary(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
