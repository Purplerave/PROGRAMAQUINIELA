#!/usr/bin/env python3
"""Descarga historico 2025-26 desde football-data.co.uk (gratis, apertura+cierre).

Si no hay internet, genera placeholder trazable y no rompe validacion.
Fuentes: https://www.football-data.co.uk/mmz4281/2425/SP1.csv etc.
"""
from __future__ import annotations
from pathlib import Path
import urllib.request, hashlib, csv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_PRIMERA = PROJECT_ROOT / "DATOS" / "historico_raw" / "PRIMERA" / "SP1_2526.csv"
OUT_SEGUNDA = PROJECT_ROOT / "DATOS" / "historico_raw" / "SEGUNDA" / "SP2_2526.csv"

URLS = {
    OUT_PRIMERA: "https://www.football-data.co.uk/mmz4281/2526/SP1.csv",
    OUT_SEGUNDA: "https://www.football-data.co.uk/mmz4281/2426/SP2.csv",  # nota: 24/25 si 25/26 no existe aun cae a placeholder
    # fallback 25/26 real cuando exista:
}

# URLs reales 25/26 (cuando esten publicadas seran 2526/ ; si fallan se deja placeholder)
URLS_REAL = {
    OUT_PRIMERA: "https://www.football-data.co.uk/mmz4281/2526/SP1.csv",
    OUT_SEGUNDA: "https://www.football-data.co.uk/mmz4281/2526/SP2.csv",
}

def try_download(url: str, dest: Path) -> bool:
    try:
        print(f"Bajando {url} -> {dest.name} ...")
        data = urllib.request.urlopen(url, timeout=15).read()
        # validacion minima: debe tener header Div,Date
        if b"Div,Date" not in data[:500]:
            print(f"  -> contenido no valido (primeros 200b): {data[:200]!r}")
            return False
        dest.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()[:16]
        # contar filas
        lines = data.decode("utf-8", errors="ignore").strip().splitlines()
        print(f"  -> OK {len(lines)-1} partidos sha256:{sha}...")
        return True
    except Exception as e:
        print(f"  -> fallo: {e}")
        return False

def verify_existing(dest: Path) -> None:
    data = dest.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    text = data.decode("utf-8", errors="ignore")
    lines = text.strip().splitlines()
    header = lines[0] if lines else ""
    has_open = "B365H" in header and "B365D" in header
    has_close = "B365CH" in header or "B365C" in header or "B365CH" in header
    n = max(0, len(lines)-1)
    print(f"Verificando {dest.name}: {n} partidos sha256:{sha[:16]}... open:{has_open} close:{has_close}")
    if not has_open or not has_close:
        print(f"  -> AVISO: faltan tripletas apertura/cierre completas")

def main() -> int:
    ok_any = False
    for dest, url in URLS_REAL.items():
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            verify_existing(dest)
            ok_any = True
            continue
        if try_download(url, dest):
            ok_any = True
        else:
            # placeholder trazable: no inventa cuotas, solo documenta intento
            placeholder = dest.with_suffix(".pendiente.txt")
            placeholder.write_text(f"Pendiente descarga 2025-26 desde {url}\nIntentado y no disponible el {__import__('datetime').datetime.utcnow().isoformat()}Z\n\nUsar highlightly como puente hasta que football-data publique 25/26.\n", encoding="utf-8")
            print(f"  -> placeholder {placeholder.name}")
    if not ok_any:
        print("\nSin internet o 25/26 aun no publicado -> usa HIGHLIGHTLY_ENRIQUECIDO como puente (paper_trading con timestamp real).")
    else:
        print("\nValidar con: python scripts/datos/VALIDAR_DATASETS.py")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
