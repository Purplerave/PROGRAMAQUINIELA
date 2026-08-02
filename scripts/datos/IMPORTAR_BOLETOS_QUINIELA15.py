"""Importa boletos/resultados reales desde Quiniela15.

Quiniela15 publica páginas de resultados con el orden real del boleto (1-14) y
el Pleno al 15. Este script descarga esas páginas y genera JSON compatibles con
``scripts/backtests/BACKTEST_BOLETOS_LAE.py``.

Ejemplos:
    python scripts/datos/IMPORTAR_BOLETOS_QUINIELA15.py --desde 1 --hasta 60
    python scripts/datos/IMPORTAR_BOLETOS_QUINIELA15.py --jornadas 1,2,3 --dry-run

Notas:
- La fuente no es SELAE directa: se etiqueta como ``Quiniela15`` y se conserva la
  URL de procedencia.
- No decide si un boleto pertenece al histórico español disponible. Después de
  importar, valida con:
      PYTHONPATH=. python scripts/backtests/BACKTEST_BOLETOS_LAE.py --solo-validar
"""

from __future__ import annotations

import argparse
import html
import json
import re
import ssl
import sys
import time
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import settings

BASE_URL = "https://www.quiniela15.com/resultados-quiniela/{jornada}"
DEFAULT_OUT_DIR = settings.DATOS_DIR / "boletos_lae_reales"
SIGNS = {"1", "X", "2"}


class TableExtractor(HTMLParser):
    """Extrae tablas HTML como filas/celdas de texto preservando saltos <br>."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._current_table: list[list[str]] = []
        self._current_row: list[str] = []
        self._cell_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001 - API HTMLParser
        tag = tag.lower()
        if tag == "table":
            self._in_table = True
            self._current_table = []
        elif self._in_table and tag == "tr":
            self._in_row = True
            self._current_row = []
        elif self._in_row and tag in {"td", "th"}:
            self._in_cell = True
            self._cell_parts = []
        elif self._in_cell and tag == "br":
            self._cell_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._in_cell:
            text = html.unescape("".join(self._cell_parts))
            text = re.sub(r"[ \t\r\f\v]+", " ", text)
            text = re.sub(r"\n\s*\n+", "\n", text)
            self._current_row.append(text.strip())
            self._in_cell = False
            self._cell_parts = []
        elif tag == "tr" and self._in_row:
            if self._current_row:
                self._current_table.append(self._current_row)
            self._in_row = False
            self._current_row = []
        elif tag == "table" and self._in_table:
            if self._current_table:
                self.tables.append(self._current_table)
            self._in_table = False
            self._current_table = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_parts.append(data)


@dataclass(frozen=True)
class ParsedMatch:
    num: int
    local: str
    visitante: str
    resultado: str
    signo: str
    tipo: str | None = None


def _clean_team_line(line: str) -> str | None:
    line = " ".join(line.strip().split())
    if not line or line == "-":
        return None
    if re.fullmatch(r"\(?\d+(?:\.\d+)?\)?", line):
        return None
    return line


def parse_match_cell(cell: str) -> tuple[str, str]:
    """Devuelve local/visitante desde la celda 'Equipo (fuerza) - Equipo'."""
    lines = [_clean_team_line(line) for line in re.split(r"\n+", cell)]
    lines = [line for line in lines if line]
    if "-" not in lines:
        # fallback para HTML convertido sin saltos claros
        compact = re.sub(r"\(\d+(?:\.\d+)?\)", "", cell)
        parts = [p.strip() for p in compact.split("-") if p.strip()]
        if len(parts) >= 2:
            return parts[0], parts[1]
        raise ValueError(f"No puedo separar local/visitante en: {cell!r}")
    sep = lines.index("-")
    home_candidates = [line for line in lines[:sep] if line != "-"]
    away_candidates = [line for line in lines[sep + 1:] if line != "-"]
    if not home_candidates or not away_candidates:
        raise ValueError(f"Local/visitante incompletos en: {cell!r}")
    return home_candidates[0], away_candidates[0]


def parse_score_cell(cell: str) -> str:
    values = re.findall(r"\d+", cell)
    if len(values) < 2:
        raise ValueError(f"Marcador no encontrado en: {cell!r}")
    return f"{int(values[0])}-{int(values[1])}"


def parse_result_table(html_text: str) -> list[ParsedMatch]:
    parser = TableExtractor()
    parser.feed(html_text)

    matches: list[ParsedMatch] = []
    for table in parser.tables:
        for row in table:
            if len(row) < 4:
                continue
            first = row[0].strip()
            if not re.fullmatch(r"\d{1,2}", first):
                continue
            num = int(first)
            if not 1 <= num <= 15:
                continue
            try:
                local, visitante = parse_match_cell(row[1])
                resultado = parse_score_cell(row[2])
            except ValueError:
                continue
            signo = row[3].strip().upper().replace(" ", "")
            if num < 15 and signo not in SIGNS:
                # Evita capturar tablas secundarias o filas incompletas.
                continue
            if num == 15 and not re.fullmatch(r"[012M]-[012M]|\d+-\d+", signo):
                continue
            matches.append(
                ParsedMatch(
                    num=num,
                    local=local,
                    visitante=visitante,
                    resultado=resultado,
                    signo=signo,
                    tipo="pleno15" if num == 15 else None,
                )
            )

    # La página puede tener tablas secundarias: nos quedamos con el primer set 1..15 completo.
    by_num: dict[int, ParsedMatch] = {}
    for match in matches:
        by_num.setdefault(match.num, match)
    ordered = [by_num[n] for n in range(1, 16) if n in by_num]
    if len(ordered) != 15:
        raise ValueError(f"No se han podido extraer 15 partidos; encontrados {len(ordered)}")
    return ordered


def fetch_html(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; PROGRAMAQUINIELA/1.0; +https://github.com/Purplerave/PROGRAMAQUINIELA)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9",
        },
    )
    context = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=context) as response:  # noqa: S310 - URL controlada por CLI
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def build_payload(jornada: int, matches: list[ParsedMatch], temporada: str, source_url: str) -> dict:
    return {
        "id": f"Q15_{temporada.replace('-', '_')}_J{jornada:03d}",
        "jornada_q15": jornada,
        "temporada": temporada,
        "fuente": "Quiniela15/resultados-quiniela",
        "source_url": source_url,
        "nota": "Importado desde Quiniela15. Validar contra histórico antes de usar en métricas.",
        "partidos": [
            {
                "num": match.num,
                "local": match.local,
                "visitante": match.visitante,
                "resultado": match.resultado,
                "signo": match.signo,
                **({"tipo": match.tipo} if match.tipo else {}),
            }
            for match in matches
        ],
    }


def import_jornada(jornada: int, temporada: str, out_dir: Path, overwrite: bool = False) -> Path:
    url = BASE_URL.format(jornada=jornada)
    html_text = fetch_html(url)
    matches = parse_result_table(html_text)
    payload = build_payload(jornada, matches, temporada, url)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"Q15_{temporada.replace('-', '_')}_J{jornada:03d}.json"
    if out_path.exists() and not overwrite:
        raise FileExistsError(f"Ya existe {out_path}; usa --overwrite")
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def parse_jornadas(args: argparse.Namespace) -> list[int]:
    if args.jornadas:
        return sorted({int(part.strip()) for part in args.jornadas.split(",") if part.strip()})
    if args.desde is None or args.hasta is None:
        raise ValueError("Indica --jornadas o --desde/--hasta")
    if args.hasta < args.desde:
        raise ValueError("--hasta debe ser >= --desde")
    return list(range(args.desde, args.hasta + 1))


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa resultados/boletos desde Quiniela15")
    parser.add_argument("--jornadas", help="lista separada por comas, ej. 1,2,3")
    parser.add_argument("--desde", type=int, help="primera jornada Q15")
    parser.add_argument("--hasta", type=int, help="última jornada Q15")
    parser.add_argument("--temporada", default="2025-2026", help="temporada a escribir en el JSON")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.5, help="pausa entre descargas")
    parser.add_argument("--dry-run", action="store_true", help="parsea e informa, pero no escribe ficheros")
    args = parser.parse_args()

    jornadas = parse_jornadas(args)
    written: list[str] = []
    errors: dict[int, str] = {}
    for jornada in jornadas:
        url = BASE_URL.format(jornada=jornada)
        try:
            html_text = fetch_html(url)
            matches = parse_result_table(html_text)
            if args.dry_run:
                print(f"J{jornada:03d}: {len(matches)} partidos — {matches[0].local} - {matches[0].visitante} ...")
            else:
                payload = build_payload(jornada, matches, args.temporada, url)
                args.out_dir.mkdir(parents=True, exist_ok=True)
                out_path = args.out_dir / f"Q15_{args.temporada.replace('-', '_')}_J{jornada:03d}.json"
                if out_path.exists() and not args.overwrite:
                    raise FileExistsError(f"Ya existe {out_path}; usa --overwrite")
                out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                written.append(str(out_path))
                print(f"J{jornada:03d}: escrito {out_path}")
        except Exception as exc:  # noqa: BLE001 - importación batch, queremos continuar
            errors[jornada] = str(exc)
            print(f"J{jornada:03d}: ERROR {exc}", file=sys.stderr)
        time.sleep(max(0.0, args.sleep))

    summary = {"jornadas": jornadas, "escritos": written, "errores": errors}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
