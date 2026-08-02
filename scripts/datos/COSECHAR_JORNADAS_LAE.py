"""COSECHAR_JORNADAS_LAE.py — Descarga los boletos REALES de La Quiniela (15 partidos).

La evaluación del motor necesita saber qué 15 partidos formaron cada boleto
real (14 partidos + Pleno al 15), algo que el histórico de football-data.co.uk
no tiene y que este script descarga de fuentes públicas:

- Partidos del boleto: Libertad Digital (archivo completo por temporada):
  https://www.libertaddigital.com/deportes/liga/{temporada}/quiniela/{n}.html
  (temporada: "2023-2024"; n: 1..N; N ≈ 72-76 jornadas por temporada).
- Combinación ganadora (resultados): quinielafutbol.info (opcional, para
  validación cruzada de los resultados al unir con el histórico):
  https://www.quinielafutbol.info/historico/resultados-la-quiniela-{temporada}.html

Salida (por jornada y consolidada por temporada):
    DATOS/jornadas_lae/j{ano_inicio}_{n}.json      (una jornada)
    DATOS/jornadas_lae/jornadas_lae_{temporada}.json
    DATOS/jornadas_lae/cache/*.html                (HTML crudo, para re-parsear)

Requisitos: solo stdlib (urllib, html.parser). Sin dependencias nuevas.
El sandbox de desarrollo no tiene salida a internet; este script está pensado
para ejecutarse en una máquina con acceso. La muestra ya cosechada y validada
está en DATOS/jornadas_lae_muestra/ (3 boletos completos con premios).

Uso:
    python scripts/datos/COSECHAR_JORNADAS_LAE.py
    python scripts/datos/COSECHAR_JORNADAS_LAE.py --temporadas 2023-2024 2024-2025
    python scripts/datos/COSECHAR_JORNADAS_LAE.py --jornadas 1-10 --sin-combinaciones

La descarga es reanudable: si el HTML ya está en caché, no se vuelve a pedir.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import settings  # noqa: E402

OUT_DIR = settings.DATOS_DIR / "jornadas_lae"
CACHE_DIR = OUT_DIR / "cache"
BASE_URL = "https://www.libertaddigital.com/deportes/liga/{temporada}/quiniela/{n}.html"
BASE_URL_Q15 = "https://www.quinielafutbol.info/historico/resultados-la-quiniela-{temporada}.html"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
DELAY_SECONDS = 1.5  # cortesía con el servidor entre peticiones

SIGN_CELLS = {"1", "X", "2"}


class _TablesParser(HTMLParser):
    """Extrae todas las tablas de un HTML como listas de filas de celdas."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append([r for r in self._table if r])
            self._table = None


def extract_tables(html: str) -> list[list[list[str]]]:
    parser = _TablesParser()
    parser.feed(html)
    return parser.tables


def parse_jornada(html: str) -> dict:
    """Parsea el HTML de una jornada de Libertad Digital.

    Devuelve un dict con 'partidos' (14), 'pleno15', 'fecha', 'recaudacion_euros'
    y 'premios'. Si la estructura no se reconoce, lanza ValueError.
    """
    tables = extract_tables(html)
    partidos: list[dict] = []
    pleno = None
    premios = None
    recaudacion = None

    for table in tables:
        # Tabla de partidos: 6 columnas, primera celda numérica 1..14 o "Pleno al 15"
        for row in table:
            if len(row) >= 6 and row[0].strip() == "Pleno al 15":
                continue
            if len(row) >= 6 and re.fullmatch(r"\d{1,2}", row[0].strip() or ""):
                num = int(row[0].strip())
                if 1 <= num <= 14 and len(row) >= 4:
                    partidos.append({"num": num, "local": row[1], "visitante": row[2]})
        # Tabla del pleno: filas [equipo, 0, 1, 2, M]
        for row in table:
            if len(row) == 5 and row[1:5] == ["0", "1", "2", "M"] and row[0]:
                if pleno is None:
                    pleno = {"local": row[0]}
                else:
                    pleno["visitante"] = row[0]
        # Tabla de premios: cabecera con Pleno al 15 / 14 / 13 / 12 / 11 / 10
        if len(table) >= 3 and any("Pleno al 15" in c for c in table[0]) and table[1] and table[1][0].strip().lower() in ("acertantes", "aciertos"):
            headers = table[0]
            keys = []
            for c in headers:
                c = c.strip()
                if "Pleno" in c:
                    keys.append("pleno15")
                elif c.isdigit():
                    keys.append(c)
                else:
                    keys.append(None)
            premios = {}
            data_rows = {r[0].strip().lower(): r for r in table[1:]}
            acert_row = data_rows.get("acertantes")
            premio_row = data_rows.get("premios")
            for idx, key in enumerate(keys):
                if key is None:
                    continue
                acert = _cell_int(acert_row, None, idx)
                premio = _cell_int(premio_row, None, idx)
                if acert is None and premio is None:
                    continue
                premios[key] = {"acertantes": acert, "premio_euros": premio}

    # Recaudación: "301.845.225 €" en el texto
    match = re.search(r"Recaudaci[oó]n\s*(?:total|bruta)?[^€]{0,40}?([\d.,]{6,})\s*€", html)
    if match:
        recaudacion = _parse_euros(match.group(1))

    if len(partidos) < 14:
        raise ValueError(f"Estructura no reconocida: {len(partidos)} partidos")

    partidos.sort(key=lambda p: p["num"])
    fecha_match = re.search(r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+(\d{4})", html)
    fecha = None
    if fecha_match:
        meses = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
            "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
        }
        dia, mes, ano = fecha_match.groups()
        mes_num = meses.get(mes.lower())
        if mes_num:
            fecha = f"{ano}-{mes_num:02d}-{int(dia):02d}"

    return {
        "partidos": partidos,
        "pleno15": pleno,
        "fecha": fecha,
        "recaudacion_euros": recaudacion,
        "premios": premios,
    }


def _cell_int(row: list[str] | None, default, idx: int = 1):
    if not row or len(row) <= idx:
        return default
    return _parse_euros(row[idx])


def _parse_euros(text: str) -> int | None:
    try:
        return int(text.replace(".", "").replace(",", "").replace("€", "").strip())
    except (TypeError, ValueError):
        return None


def parse_combinaciones_quinielafutbol(html: str) -> dict[int, list[str]]:
    """Parsea la tabla de combinaciones ganadoras de una temporada (quinielafutbol.info)."""
    out: dict[int, list[str]] = {}
    for table in extract_tables(html):
        for row in table:
            if len(row) < 5:
                continue
            num = row[1].strip()
            if not re.fullmatch(r"\d{1,2}", num):
                continue
            comb = [c.strip() for c in row[4].split(",") if c.strip()]
            if len(comb) == 15:
                out[int(num)] = comb
    return out


def fetch_html(url: str, cache_path: Path, delay: float = DELAY_SECONDS) -> str:
    if cache_path.is_file():
        return cache_path.read_text(encoding="utf-8", errors="replace")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(raw, encoding="utf-8")
    time.sleep(delay)
    return raw


def cosechar(
    temporadas: list[str],
    rango_jornadas: tuple[int, int] | None,
    con_combinaciones: bool,
) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    errores = 0
    for temporada in temporadas:
        comb_by_j = {}
        if con_combinaciones:
            try:
                q15_html = fetch_html(
                    BASE_URL_Q15.format(temporada=temporada),
                    CACHE_DIR / f"q15_{temporada}.html",
                )
                comb_by_j = parse_combinaciones_quinielafutbol(q15_html)
                print(f"  [{temporada}] combinaciones ganadoras: {len(comb_by_j)}")
            except Exception as exc:  # noqa: BLE001
                print(f"  [{temporada}] aviso combinaciones: {exc}")

        # Descubrir el nº de jornadas de la temporada probando hasta 404
        n = rango_jornadas[0] if rango_jornadas else 1
        n_max = rango_jornadas[1] if rango_jornadas else 80
        jornadas: list[dict] = []
        while n <= n_max:
            url = BASE_URL.format(temporada=temporada, n=n)
            cache_path = CACHE_DIR / f"ld_{temporada}_{n:02d}.html"
            try:
                html = fetch_html(url, cache_path)
            except Exception as exc:  # noqa: BLE001
                print(f"  [{temporada}] jornada {n}: error de red ({exc}); se reanuda en la próxima ejecución")
                errores += 1
                n += 1
                continue
            if len(html) < 5000 or "Quiniela - Jornada" not in html:
                if rango_jornadas is None and n > 5:
                    break  # fin de temporada (404 o página inexistente)
                print(f"  [{temporada}] jornada {n}: página no encontrada")
                errores += 1
                n += 1
                continue
            try:
                data = parse_jornada(html)
            except ValueError as exc:
                print(f"  [{temporada}] jornada {n}: parseo fallido ({exc})")
                errores += 1
                n += 1
                continue
            data["temporada"] = temporada
            data["jornada"] = n
            data["combinacion_ganadora"] = comb_by_j.get(n)
            data["fuente"] = url
            jornadas.append(data)
            total += 1
            if n % 10 == 0:
                print(f"  [{temporada}] {n} jornadas cosechadas...")
            n += 1

        if jornadas:
            out_path = OUT_DIR / f"jornadas_lae_{temporada}.json"
            out_path.write_text(
                json.dumps(
                    {"temporada": temporada, "n_jornadas": len(jornadas), "jornadas": jornadas},
                    ensure_ascii=False,
                    indent=1,
                ),
                encoding="utf-8",
            )
            print(f"  [{temporada}] {len(jornadas)} jornadas -> {out_path.name}")

    print(f"\nTotal jornadas cosechadas: {total} | errores: {errores}")
    print(f"HTML crudo en: {CACHE_DIR}")
    return 0 if errores == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Cosecha los boletos reales de La Quiniela")
    parser.add_argument("--temporadas", nargs="+", default=["2023-2024", "2024-2025", "2025-2026"])
    parser.add_argument("--jornadas", default=None, help="rango '1-10' (por defecto: todas hasta 404)")
    parser.add_argument("--sin-combinaciones", action="store_true", help="no descargar quinielafutbol.info")
    args = parser.parse_args()

    rango = None
    if args.jornadas:
        a, _, b = args.jornadas.partition("-")
        rango = (int(a), int(b))

    return cosechar(args.temporadas, rango, not args.sin_combinaciones)


if __name__ == "__main__":
    sys.exit(main())
