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

Comportamiento:
- Reanudable: si el HTML ya está en caché, no se vuelve a pedir.
- Detecta el nº real de jornadas de cada temporada desde la propia página
  (enlaces "Jornada N" de la cabecera) y se detiene ahí; si no puede
  detectarlo, se detiene tras 3 errores 404 consecutivos.
- Parser tolerante: tablas anidadas, filas sueltas y compresión gzip.
- Si una jornada no se reconoce, guarda el HTML en cache/debug_*.html para
  diagnóstico y continúa.

Requisitos: solo stdlib (urllib, html.parser, gzip). Sin dependencias nuevas.
El sandbox de desarrollo no tiene salida a internet; este script está pensado
para ejecutarse en una máquina con acceso. La muestra ya cosechada y validada
está en DATOS/jornadas_lae_muestra/ (3 boletos completos con premios).

Uso:
    python scripts/datos/COSECHAR_JORNADAS_LAE.py
    python scripts/datos/COSECHAR_JORNADAS_LAE.py --temporadas 2023-2024
    python scripts/datos/COSECHAR_JORNADAS_LAE.py --jornadas 1-10 --sin-combinaciones
    python scripts/datos/COSECHAR_JORNADAS_LAE.py --refrescar   # ignora la caché
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
import urllib.request
import zlib
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
MAX_JORNADAS_GUESS = 80   # tope si no se puede detectar el nº real de jornadas
MAX_CONSECUTIVE_404 = 3   # parada por defecto cuando no se detecta el nº real

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


# ---------------------------------------------------------------------------
# Parser HTML tolerante
# ---------------------------------------------------------------------------

class _HtmlTablesParser(HTMLParser):
    """Extrae tablas y filas de un HTML tolerando tablas anidadas y HTML suelto.

    - ``tables``: listas de filas por cada <table> (soporta anidamiento con
      una pila, de modo que una tabla dentro de una celda no rompe la exterior).
    - ``flat_rows``: TODAS las filas <tr> encontradas, estén o no dentro de
      una tabla reconocida (respaldo para estructuras raras).
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self.flat_rows: list[list[str]] = []
        self._stack: list[list[list[str]]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def _flush_cell(self) -> None:
        if self._cell is None:
            return
        text = " ".join("".join(self._cell).split())
        self._cell = None
        if self._row is not None:
            self._row.append(text)

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._stack.append([])
            self._row = None
            self._cell = None
        elif tag == "tr":
            self._row = []
            if self._stack:
                self._stack[-1].append(self._row)
        elif tag in ("td", "th"):
            self._flush_cell()
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self._flush_cell()
        elif tag == "tr":
            if self._row is not None:
                self.flat_rows.append(self._row)
            self._row = None
        elif tag == "table":
            if self._stack:
                table = self._stack.pop()
                self.tables.append([r for r in table if r])
            self._row = None


def extract_tables(html: str) -> list[list[list[str]]]:
    parser = _HtmlTablesParser()
    parser.feed(html)
    return parser.tables


def extract_rows(html: str) -> list[list[str]]:
    """Todas las filas (de tablas y sueltas), sin duplicados."""
    parser = _HtmlTablesParser()
    parser.feed(html)
    rows: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for table in parser.tables:
        for row in table:
            key = tuple(row)
            if key not in seen:
                seen.add(key)
                rows.append(row)
    for row in parser.flat_rows:
        key = tuple(row)
        if key not in seen:
            seen.add(key)
            rows.append(row)
    return rows


def _match_partido_row(row: list[str]) -> tuple[int, str, str] | None:
    """Intenta leer una fila de partido: (num, local, visitante) o None.

    Tolera partidos con local o visitante vacíos (boletos con equipos "por
    confirmar" o aplazados: LD los publica en blanco). Solo exige que la
    fila tenga el número y las columnas de signos.
    """
    if len(row) < 4:
        return None
    m = re.fullmatch(r"(\d{1,2})", row[0].strip())
    if m:
        num = int(m.group(1))
        if 1 <= num <= 14:
            return num, row[1].strip(), row[2].strip()
    # Variante: primera celda vacía y el número en la segunda (columna extra)
    if not row[0].strip() and len(row) >= 5:
        m = re.fullmatch(r"(\d{1,2})", row[1].strip())
        if m:
            num = int(m.group(1))
            if 1 <= num <= 14:
                return num, row[2].strip(), row[3].strip()
    return None


def _match_pleno(rows: list[list[str]]) -> dict | None:
    """Filas del Pleno al 15: celdas [equipo, 0, 1, 2, M] (con o sin columnas extra)."""
    pleno = None
    for row in rows:
        cells = [c.strip() for c in row]
        if all(s in cells for s in ("0", "1", "2", "M")):
            team = " ".join(c for c in cells if c not in ("0", "1", "2", "M")).strip()
            if not team:
                continue
            if pleno is None:
                pleno = {"local": team}
            elif "visitante" not in pleno:
                pleno["visitante"] = team
    return pleno


def _match_premios(tables: list[list[list[str]]]) -> dict | None:
    """Tabla de premios: cabecera [Aciertos, Pleno al 15, 14, 13, 12, 11, 10]."""
    premios = None
    for table in tables:
        if len(table) < 3:
            continue
        headers = [c.strip() for c in table[0]]
        if not any("Pleno al 15" in c for c in headers):
            continue
        keys: list[str | None] = []
        for c in headers:
            if "Pleno" in c:
                keys.append("pleno15")
            elif c.isdigit():
                keys.append(c)
            else:
                keys.append(None)
        if not any(keys):
            continue
        data_rows = {r[0].strip().lower(): r for r in table[1:]}
        acert_row = data_rows.get("acertantes")
        premio_row = data_rows.get("premios")
        premios = {}
        for idx, key in enumerate(keys):
            if key is None:
                continue
            acert = _cell_int(acert_row, None, idx)
            premio = _cell_int(premio_row, None, idx)
            if acert is None and premio is None:
                continue
            premios[key] = {"acertantes": acert, "premio_euros": premio}
        if premios:
            break
    return premios


def _match_recaudacion(html: str) -> int | None:
    m = re.search(r"Recaudaci[oó]n\s*(?:total|bruta)?[^€]{0,40}?([\d.,]{6,})\s*€", html)
    return _parse_euros(m.group(1)) if m else None


def _match_fecha(html: str) -> str | None:
    m = re.search(r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+(\d{4})", html)
    if not m:
        return None
    dia, mes, ano = m.groups()
    mes_num = MESES.get(mes.lower())
    if not mes_num:
        return None
    return f"{ano}-{mes_num:02d}-{int(dia):02d}"


def parse_jornada(html: str) -> dict:
    """Parsea el HTML de una jornada de Libertad Digital.

    Devuelve un dict con 'partidos' (14), 'pleno15', 'fecha', 'recaudacion_euros'
    y 'premios'. Si la estructura no se reconoce, lanza ValueError con un
    diagnóstico (nº de tablas y filas encontradas).
    """
    tables = extract_tables(html)
    rows = extract_rows(html)

    partidos: list[dict] = []
    seen_nums: set[int] = set()
    for row in rows:
        m = _match_partido_row(row)
        if m is None:
            continue
        num, local, visitante = m
        if num in seen_nums:
            continue
        seen_nums.add(num)
        partido: dict = {"num": num, "local": local, "visitante": visitante}
        if not (local and visitante):
            partido["sin_equipos"] = True  # "por confirmar"/aplazado en LD
        partidos.append(partido)

    if len(partidos) < 14:
        raise ValueError(
            f"Estructura no reconocida: {len(partidos)} partidos "
            f"(tablas={len(tables)}, filas={len(rows)})"
        )

    partidos.sort(key=lambda p: p["num"])
    return {
        "partidos": partidos,
        "pleno15": _match_pleno(rows),
        "fecha": _match_fecha(html),
        "recaudacion_euros": _match_recaudacion(html),
        "premios": _match_premios(tables),
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


def max_jornada_from_nav(html: str) -> int | None:
    """Nº máximo de jornada visible en la página (enlaces 'Jornada N')."""
    nums = [int(x) for x in re.findall(r"Jornada\s+(\d{1,2})", html)]
    return max(nums) if nums else None


# ---------------------------------------------------------------------------
# Descarga
# ---------------------------------------------------------------------------

def _decode_response(raw: bytes, content_encoding: str | None) -> str:
    enc = (content_encoding or "").lower()
    if enc == "gzip":
        raw = gzip.decompress(raw)
    elif enc == "deflate":
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
    # 'br' (brotli) no está en stdlib; si el servidor lo manda, la página
    # quedará ilegible y el parser lo reportará como estructura desconocida.
    return raw.decode("utf-8", errors="replace")


def fetch_html(
    url: str,
    cache_path: Path,
    delay: float = DELAY_SECONDS,
    refresh: bool = False,
) -> str:
    """Descarga (o lee de caché) una página. Si ``refresh`` es True, ignora la caché."""
    if cache_path.is_file() and not refresh:
        return cache_path.read_text(encoding="utf-8", errors="replace")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = _decode_response(resp.read(), resp.headers.get("Content-Encoding"))
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(html, encoding="utf-8")
    time.sleep(delay)
    return html


# ---------------------------------------------------------------------------
# Cosecha
# ---------------------------------------------------------------------------

def cosechar(
    temporadas: list[str],
    rango_jornadas: tuple[int, int] | None,
    con_combinaciones: bool,
    refrescar: bool,
) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    errores = 0

    for temporada in temporadas:
        print(f"\n=== TEMPORADA {temporada} ===")
        comb_by_j: dict[int, list[str]] = {}
        if con_combinaciones:
            try:
                q15_html = fetch_html(
                    BASE_URL_Q15.format(temporada=temporada),
                    CACHE_DIR / f"q15_{temporada}.html",
                    refresh=refrescar,
                )
                comb_by_j = parse_combinaciones_quinielafutbol(q15_html)
                print(f"  combinaciones ganadoras descargadas: {len(comb_by_j)}")
            except Exception as exc:  # noqa: BLE001
                print(f"  aviso combinaciones: {exc}")

        n = rango_jornadas[0] if rango_jornadas else 1
        n_max = rango_jornadas[1] if rango_jornadas else None
        consec_404 = 0
        jornadas: list[dict] = []
        fallidas: list[int] = []
        no_encontradas: list[int] = []
        debug_saved = 0

        while True:
            if n_max is not None and n > n_max:
                break
            if n_max is None and n > MAX_JORNADAS_GUESS:
                break

            url = BASE_URL.format(temporada=temporada, n=n)
            cache_path = CACHE_DIR / f"ld_{temporada}_{n:02d}.html"
            try:
                html = fetch_html(url, cache_path, refresh=refrescar)
            except Exception as exc:  # noqa: BLE001
                consec_404 += 1
                no_encontradas.append(n)
                if consec_404 >= MAX_CONSECUTIVE_404 and n_max is None:
                    break
                n += 1
                continue

            if len(html) < 5000 or "Quiniela - Jornada" not in html:
                consec_404 += 1
                no_encontradas.append(n)
                if consec_404 >= MAX_CONSECUTIVE_404 and n_max is None:
                    break
                n += 1
                continue

            consec_404 = 0
            if n_max is None:
                detected = max_jornada_from_nav(html)
                if detected is not None and detected >= n:
                    n_max = detected

            try:
                data = parse_jornada(html)
            except ValueError as exc:
                fallidas.append(n)
                saved = ""
                if debug_saved < 3:
                    (CACHE_DIR / f"debug_{temporada}_{n:02d}.html").write_text(html, encoding="utf-8")
                    debug_saved += 1
                    saved = " [HTML guardado en cache/ para diagnóstico]"
                print(f"  jornada {n}: parseo fallido ({exc}){saved}")
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
                print(f"  {n} jornadas cosechadas...")
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
            print(f"  -> {len(jornadas)} jornadas en {out_path.name}")
        print(
            f"  resumen {temporada}: {len(jornadas)} cosechadas | "
            f"{len(fallidas)} fallidas {fallidas[:10]} | "
            f"{len(no_encontradas)} no encontradas {no_encontradas[:10]}"
        )

    print(f"\nTOTAL: {total} jornadas | errores de parseo: {errores}")
    print(f"HTML crudo en: {CACHE_DIR}")
    return 0 if errores == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Cosecha los boletos reales de La Quiniela")
    parser.add_argument("--temporadas", nargs="+", default=["2023-2024", "2024-2025", "2025-2026"])
    parser.add_argument("--jornadas", default=None, help="rango '1-10' (por defecto: todas hasta el final de temporada)")
    parser.add_argument("--sin-combinaciones", action="store_true", help="no descargar quinielafutbol.info")
    parser.add_argument("--refrescar", action="store_true", help="ignorar la caché y volver a descargar")
    args = parser.parse_args()

    rango = None
    if args.jornadas:
        a, _, b = args.jornadas.partition("-")
        rango = (int(a), int(b))

    return cosechar(args.temporadas, rango, not args.sin_combinaciones, args.refrescar)


if __name__ == "__main__":
    sys.exit(main())
