#!/usr/bin/env python3
"""CLI del registro prospectivo append-only.

El registro vive en ``DATOS/registro_prospectivo.jsonl`` y lo implementa
``scripts/motor/registro_prospectivo.py``. Este envoltorio existe para que la
ruta de uso sea corta y estable:

    python scripts/registro_prospectivo.py --verificar
    python scripts/registro_prospectivo.py --resumen
    python scripts/registro_prospectivo.py --anadir partidos_J75.json
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.motor.registro_prospectivo import main

if __name__ == "__main__":
    sys.exit(main())
