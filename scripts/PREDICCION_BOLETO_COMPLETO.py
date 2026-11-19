"""Alias de compatibilidad del orquestador semanal con boleto explícito.

Ya no mezcla archivos "últimos" de jornadas diferentes. Las casillas oficiales
se declaran juntas en DATOS/BOLETO_SEMANAL.json o mediante --boleto.
"""
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.RUN_SEMANA_COMPLETA import main


if __name__ == "__main__":
    raise SystemExit(main())
