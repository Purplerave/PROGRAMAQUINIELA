"""Repara combinaciones ganadoras LAE desde HTML cacheado.

Lee ``DATOS/jornadas_lae/jornadas_lae_*.json`` y vuelve a extraer la
combinación ganadora desde los HTML de ``DATOS/jornadas_lae/cache``.

Motivo: el parser original podía desplazar signos alrededor del Pleno al 15 o
quedarse con ``null`` aunque el HTML cacheado tuviera la combinación.

Uso:
    python scripts/datos/REPARAR_COMBINACIONES_LAE_DESDE_CACHE.py --dry-run
    python scripts/datos/REPARAR_COMBINACIONES_LAE_DESDE_CACHE.py
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LAE_DIR = PROJECT_ROOT / "DATOS" / "jornadas_lae"
CACHE_DIR = LAE_DIR / "cache"


def extract_between(html: str, start: str, end_pattern: str) -> str | None:
    start_idx = html.find(start)
    if start_idx < 0:
        return None
    match = re.search(end_pattern, html[start_idx + len(start) :], flags=re.S)
    if not match:
        return html[start_idx + len(start) :]
    return html[start_idx + len(start) : start_idx + len(start) + match.start()]


def extract_regular_sign(html: str, num: int) -> str | None:
    start = f'<td class="posicion">{num}</td>'
    if num < 14:
        end_pattern = rf'<td class="posicion">\s*{num + 1}\s*</td>'
    else:
        end_pattern = r'<tr class="pleno15">'
    section = extract_between(html, start, end_pattern)
    if section is None:
        return None
    marked = re.search(r'class="signo marcado">\s*([^<]+?)\s*</td>', section, flags=re.S)
    return marked.group(1).strip() if marked else None


def extract_pleno15_sign(html: str) -> str | None:
    start = '<tr class="pleno15">'
    section = extract_between(html, start, r'<h2>Recaudación</h2>|<table class="acertantes">')
    if section is None:
        return None
    values = [v.strip() for v in re.findall(r'class="signo marcado">\s*([^<]+?)\s*</td>', section, flags=re.S)]
    if len(values) >= 2:
        return values[0] + values[1]
    if len(values) == 1:
        return values[0]
    return None


def extract_combo_from_html(html: str) -> list[str] | None:
    combo: list[str] = []
    for num in range(1, 15):
        sign = extract_regular_sign(html, num)
        if sign not in {"1", "X", "2"}:
            return None
        combo.append(sign)
    pleno = extract_pleno15_sign(html)
    if not pleno:
        return None
    combo.append(pleno)
    return combo


def repair_file(path: Path, dry_run: bool) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    season = data.get("temporada") or path.stem.replace("jornadas_lae_", "")
    changes: list[dict[str, Any]] = []

    for jornada in data.get("jornadas", []):
        num = int(jornada.get("jornada"))
        html_path = CACHE_DIR / f"ld_{season}_{num:02d}.html"
        if not html_path.exists():
            continue
        combo = extract_combo_from_html(html_path.read_text(encoding="utf-8", errors="replace"))
        old = jornada.get("combinacion_ganadora")
        if combo is None or combo == old:
            continue
        changes.append(
            {
                "temporada": season,
                "jornada": num,
                "antes": old,
                "despues": combo,
                "html": str(html_path.relative_to(PROJECT_ROOT)),
            }
        )
        if not dry_run:
            jornada["combinacion_ganadora"] = combo

    if changes and not dry_run:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description="Repara combinaciones LAE desde HTML cacheado.")
    parser.add_argument("--dry-run", action="store_true", help="Solo informa; no modifica JSON.")
    parser.add_argument("--season", help="Temporada concreta, por ejemplo 2025-2026.")
    args = parser.parse_args()

    if args.season:
        files = [LAE_DIR / f"jornadas_lae_{args.season}.json"]
    else:
        files = sorted(LAE_DIR.glob("jornadas_lae_*.json"))

    all_changes: list[dict[str, Any]] = []
    for path in files:
        if not path.exists():
            print(f"No existe: {path}")
            continue
        all_changes.extend(repair_file(path, dry_run=args.dry_run))

    report_path = PROJECT_ROOT / "salida" / "reparacion_combinaciones_lae.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(all_changes, ensure_ascii=False, indent=2), encoding="utf-8")

    modo = "DRY-RUN" if args.dry_run else "APLICADO"
    print(f"Modo: {modo}")
    print(f"Cambios detectados: {len(all_changes)}")
    print(f"Informe: {report_path}")
    for change in all_changes:
        print(
            f"{change['temporada']} J{change['jornada']}: "
            f"{change['antes']} -> {change['despues']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
