#!/usr/bin/env python3
"""Genera la vista HTML de la bitácora de la entrevista.

Lee   : entrevista/relacion.md
Escribe: entrevista/relacion.html

Uso   : python3 entrevista/build.py
"""
import html
import re
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MD = HERE / "relacion.md"
OUT = HERE / "relacion.html"

MARKER = re.compile(r'^(#{1,4}\s|> |\d+\.\s|\*\*P:\*\*|\*\*R:\*\*|---\s*$|[-•]\s)')


def inline(text: str) -> str:
    t = html.escape(text, quote=False)
    t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
    t = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', t)
    t = re.sub(r'`([^`]+)`', r'<code>\1</code>', t)
    return t


def convert(md: str) -> str:
    lines = md.splitlines()
    out = []
    i = 0
    n = len(lines)
    while i < n:
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        if s == '---':
            out.append('<hr>')
            i += 1
            continue
        m = re.match(r'^(#{1,4})\s+(.*)$', s)
        if m:
            lvl = len(m.group(1))
            out.append(f'<h{lvl}>{inline(m.group(2))}</h{lvl}>')
            i += 1
            continue
        if s.startswith('> '):
            parts = []
            while i < n and lines[i].strip().startswith('> '):
                parts.append(lines[i].strip()[2:])
                i += 1
            out.append('<blockquote>' + inline(' '.join(parts)) + '</blockquote>')
            continue
        if s.startswith('- ') or s.startswith('• '):
            items = []
            while i < n and (lines[i].strip().startswith('- ') or lines[i].strip().startswith('• ')):
                items.append(lines[i].strip()[2:])
                i += 1
            out.append('<ul>' + ''.join(f'<li>{inline(x)}</li>' for x in items) + '</ul>')
            continue
        if re.match(r'^\d+\.\s', s):
            items = []
            while i < n and re.match(r'^\d+\.\s', lines[i].strip()):
                items.append(re.sub(r'^\d+\.\s', '', lines[i].strip()))
                i += 1
            out.append('<ol>' + ''.join(f'<li>{inline(x)}</li>' for x in items) + '</ol>')
            continue
        if s.startswith('**P:**') or s.startswith('**R:**'):
            who = s[2]
            text = s[6:].strip()
            i += 1
            while i < n and lines[i].strip() and not MARKER.match(lines[i].strip()):
                text += ' ' + lines[i].strip()
                i += 1
            out.append(
                f'<div class="qa {who.lower()}"><span class="who">{who}</span>'
                f'<p>{inline(text)}</p></div>'
            )
            continue
        parts = [s]
        i += 1
        while i < n and lines[i].strip() and not MARKER.match(lines[i].strip()):
            parts.append(lines[i].strip())
            i += 1
        out.append('<p>' + inline(' '.join(parts)) + '</p>')
    return '\n'.join(out)


def meta(md: str) -> dict:
    d = {}
    for line in md.splitlines():
        m = re.match(r'^- \*\*(.+?):\*\*\s*(.*)$', line.strip())
        if m:
            d[m.group(1).strip()] = m.group(2).strip()
    return d


CSS = """
:root{
  --bg:#faf6f0; --ink:#2b2622; --muted:#8a7f74;
  --card:#ffffff; --line:#e8e0d4;
  --accent:#b4552d; --accent-soft:#f6e7dc; --r-bg:#f3eee5;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:Georgia,"Times New Roman",serif;line-height:1.65}
main{max-width:780px;margin:0 auto;padding:48px 20px 80px}
.kicker{font-family:ui-sans-serif,system-ui,sans-serif;font-size:.72rem;font-weight:700;
  letter-spacing:.18em;text-transform:uppercase;color:var(--accent);margin:0 0 6px}
h1{font-size:2.5rem;line-height:1.15;margin:0 0 20px;letter-spacing:-.01em}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin:0 0 8px;padding:0}
.stats div{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:10px 14px;min-width:130px}
.stats span{display:block;font-family:ui-sans-serif,system-ui,sans-serif;font-size:.66rem;
  letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:2px}
.stats strong{font-size:.95rem}
h2{font-size:1.3rem;margin:44px 0 10px;padding-top:20px;border-top:1px solid var(--line)}
h3{font-size:1.12rem;margin:30px 0 8px}
h4{font-size:1rem;margin:24px 0 8px}
blockquote{margin:16px 0;padding:12px 16px;background:var(--accent-soft);
  border-left:3px solid var(--accent);border-radius:0 12px 12px 0;color:#5c4a3d}
p{margin:12px 0}
ul,ol{margin:12px 0;padding-left:24px}
li{margin:4px 0}
hr{border:0;border-top:1px dashed var(--line);margin:30px 0}
.empty{margin:20px 0;padding:18px 20px;border:1px dashed var(--line);border-radius:12px;
  color:var(--muted);font-style:italic;background:var(--card)}
.qa{display:flex;gap:12px;margin:14px 0}
.qa .who{flex:0 0 34px;height:34px;border-radius:50%;display:flex;align-items:center;
  justify-content:center;font-family:ui-sans-serif,system-ui,sans-serif;font-weight:700;font-size:.85rem}
.qa.p .who{background:var(--accent);color:#fff}
.qa.r .who{background:var(--r-bg);color:var(--muted);border:1px solid var(--line)}
.qa p{flex:1;margin:0;background:var(--card);border:1px solid var(--line);
  border-radius:12px;padding:12px 16px}
.qa.r p{background:var(--r-bg);border-color:#e3dac9}
footer{margin-top:52px;padding-top:16px;border-top:1px solid var(--line);
  font-family:ui-sans-serif,system-ui,sans-serif;font-size:.75rem;color:var(--muted)}
code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.85em;
  background:var(--r-bg);padding:1px 5px;border-radius:6px}
"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Entrevista personal — Mi relación</title>
<style>{css}</style>
</head>
<body>
<main>
<header>
  <p class="kicker">Bitácora de entrevista</p>
  <h1>Mi relación</h1>
  <div class="stats">
    <div><span>Inicio</span><strong>{inicio}</strong></div>
    <div><span>Última actualización</span><strong>{actualizado}</strong></div>
    <div><span>Preguntas</span><strong>{n}</strong></div>
    <div><span>Estado</span><strong>{estado}</strong></div>
  </div>
</header>
{body}
<footer>Generado el {fecha} a partir de <code>relacion.md</code> · se actualiza con cada ronda de la entrevista</footer>
</main>
</body>
</html>
"""


def main() -> None:
    md = MD.read_text(encoding="utf-8")
    m = meta(md)
    n = len(re.findall(r'^\*\*P:\*\*', md, flags=re.M))
    body = convert(md)
    if n == 0:
        body += ('\n<div class="empty">Aún no hay respuestas. '
                 'La primera pregunta está esperando en el chat…</div>')
    out = HTML_TEMPLATE.format(
        css=CSS,
        inicio=html.escape(m.get("Inicio", "—")),
        actualizado=html.escape(m.get("Última actualización", "—")),
        n=n,
        estado=html.escape(m.get("Estado", "—")),
        body=body,
        fecha=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )
    OUT.write_text(out, encoding="utf-8")
    print(f"OK: {OUT} ({n} preguntas respondidas)")


if __name__ == "__main__":
    main()
