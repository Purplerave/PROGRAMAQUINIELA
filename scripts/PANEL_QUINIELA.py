"""
PANEL_QUINIELA.py — Panel de control del programa (todo-en-uno).

    python PANEL_QUINIELA.py            -> abre dashboard en http://localhost:8787
    python PANEL_QUINIELA.py --cli      -> ejecuta la semana y pinta la quiniela
                                           por pantalla (sin navegador)

Acciones del panel:
    [EJECUTAR SEMANA]  lanza RUN_SEMANA_COMPLETA.py (doble motor + optimizador)
    [PUBLICAR EN LIGA MAESTROS]  vuelca el paquete completo a
        liga-maestros-web/data/inbox/QUINIELA_J{N}_PROGRAMA.json
        (la web ya trata al 'programa' como participante del ranking)

Sin dependencias externas: http.server + subprocess + json.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SALIDAS = ROOT / "SALIDAS"
WEB_ROOT = Path(r"C:\Users\Mortadelo\Desktop\QUINIELAs\liga-maestros-web")
INBOX = WEB_ROOT / "data" / "inbox"
PUERTO = 8787

_ESTADO = {"ultima_ejecucion": None, "payload": None, "log": ""}


def ultimo(prefijo: str) -> Path | None:
    cand = sorted(SALIDAS.glob(f"{prefijo}*.json"))
    return cand[-1] if cand else None


def ejecutar_semana(presupuesto: int = 8) -> dict:
    cmd = [sys.executable, str(ROOT / "scripts" / "RUN_SEMANA_COMPLETA.py"),
           "--presupuesto", str(presupuesto)]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=1200)
    _ESTADO["log"] = (proc.stdout or "") + (proc.stderr or "")
    _ESTADO["ultima_ejecucion"] = datetime.now().isoformat(timespec="seconds")
    boleto_p = ultimo("boleto_completo_J")
    opt_p = ultimo("optimizacion_boleto_J")
    payload = {
        "generado": _ESTADO["ultima_ejecucion"],
        "returncode": proc.returncode,
        "boleto": json.loads(boleto_p.read_text(encoding="utf-8")) if boleto_p else None,
        "optimizacion": json.loads(opt_p.read_text(encoding="utf-8")) if opt_p else None,
        "cola_log": _ESTADO["log"][-1500:],
    }
    _ESTADO["payload"] = payload
    return payload


def publicar_liga_maestros() -> dict:
    payload = _ESTADO.get("payload") or {}
    boleto = payload.get("boleto")
    if not boleto:
        raise RuntimeError("No hay boleto ejecutado todavia. Pulsa EJECUTAR primero.")
    jornada = boleto.get("jornada") or "SIN_NUMERO"
    INBOX.mkdir(parents=True, exist_ok=True)
    destino = INBOX / f"QUINIELA_J{jornada}_PROGRAMA.json"
    paquete = {
        "tipo": "quiniela_programa",
        "jornada": jornada,
        "publicado": datetime.now().isoformat(timespec="seconds"),
        "fuente": "PROGRAMAQUINIELA::RUN_SEMANA_COMPLETA",
        "bote_eur": boleto.get("bote_eur"),
        "cierre": boleto.get("cierre"),
        "casillas": [], 
    }
    ligam = {p["numero"]: p for p in (boleto.get("ligam") or {}).get("predicciones", [])}
    for pr in (boleto.get("ligaf") or {}).get("pronosticos", []):
        num = pr.get("numero")
        if num is not None:
            ligam[num] = pr
    for num in sorted(ligam):
        p = ligam[num]
        es_pleno = bool(p.get("pleno") or p.get("pleno_descanso"))
        signo = p.get("pleno", {}).get("signo") if p.get("pleno") else p.get(
            "signo", p.get("signo_modelo"))
        casilla = {
            "numero": num,
            "partido": f"{p['local']} - {p['visitante']}",
            "signo_programa": signo,
            "pleno": es_pleno,
        }
        if p.get("pleno"):
            casilla["top3_pleno"] = p["pleno"].get("signo") and [
                {"signo": t["signo"], "p": t["p"]} for t in
                (json.loads(json.dumps(p["pleno"])) .get("top3") or [])
            ] if isinstance(p["pleno"], dict) and "top3" in p["pleno"] else None
        paquete["casillas"].append(casilla)
    opt = payload.get("optimizacion") or {}
    if opt:
        paquete["apuesta_recomendada"] = {
            "politica_cobertura": opt.get("politica_cobertura"),
            "politica_ev_parimutuel": opt.get("politica_ev_parimutuel"),
        }
    destino.write_text(json.dumps(paquete, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    return {"publicado_en": str(destino), "jornada": jornada,
            "n_casillas": len(paquete["casillas"])}


# ---------------------------------------------------------------- CLI ----

def pintar_cli(payload: dict) -> None:
    boleto = payload.get("boleto")
    if not boleto:
        print("Sin resultados."); return
    print(f"\n== QUINIELA J{boleto.get('jornada')} | bote "
          f"{boleto.get('bote_eur'):,.0f} EUR | cierre {boleto.get('cierre')} ==")
    ligam = {p["numero"]: p for p in (boleto.get("ligam") or {}).get("predicciones", [])}
    for pr in (boleto.get("ligaf") or {}).get("pronosticos", []):
        if pr.get("numero") is not None:
            ligam[pr["numero"]] = pr
    print(f"{'CAS':>3} {'PARTIDO':<42} {'P1':>5} {'PX':>5} {'P2':>5}  SIGNO   ORIGEN")
    for num in sorted(ligam):
        p = ligam[num]
        if p.get("pleno"):
            print(f"{num:>3} {p['local']} - {p['visitante']}"[:46],
                  f"  PLENO -> {p['pleno']['signo']} ({max(p['pleno']['probs']):.2f})",
                  "[16 signos]")
            continue
        print(f"{num:>3} {p['local']} - {p['visitante']}"[:46],
              f"{p.get('prob_1', p.get('p1', 0)):>6.3f}",
              f"{p.get('prob_x', p.get('px', 0)):>6.3f}",
              f"{p.get('prob_2', p.get('p2', 0)):>6.3f}",
              f"  {p.get('signo', p.get('signo_modelo','-')):^4}  "
              f"{str(p.get('fuente') or p.get('fuente_ratings',''))[:28]}")
    opt = payload.get("optimizacion") or {}
    for pol in ("politica_cobertura", "politica_ev_parimutuel"):
        datos = opt.get(pol) or {}
        cols = datos.get("columnas") or []
        if cols:
            extra = (f" P={datos['p_acierto_total']:.5f}"
                     f" EV={datos.get('ev_eur','')}EUR" if "ev_eur" in datos else
                     f" P={datos['p_acierto_total']:.5f}")
            print(f"\n[{pol.upper()}] {len(cols)} columnas, "
                  f"coste {datos.get('coste_eur', 0)} EUR{extra}")
            for c in cols[:10]:
                print("   ", c["signos"], c["peso"])
    pub = publicar_liga_maestros()
    print("\n[PUBLICADO]", pub)


# ---------------------------------------------------------------- HTTP ----

HTML = """<!doctype html><html lang=es><head><meta charset=utf-8>
<title>PANEL QUINIELA</title><style>
body{background:#0b1020;color:#e7ecff;font-family:system-ui;margin:0;padding:24px}
h1{margin:0 0 4px}.sub{color:#8ea0c9;margin-bottom:18px}
button{background:#1c6ef2;border:0;color:#fff;padding:12px 20px;border-radius:10px;
font-size:15px;font-weight:600;cursor:pointer;margin-right:10px}
button.sec{background:#24304f}button:disabled{opacity:.5}
table{border-collapse:collapse;width:100%;margin-top:14px}
td,th{padding:8px 10px;border-bottom:1px solid #223055;text-align:left;font-size:14px}
tr.ligaf td{background:#12203c}.pleno td{background:#3a2a12}
.bar{height:8px;background:#223055;border-radius:4px;display:inline-block;width:70px;
vertical-align:middle}.bar>i{display:block;height:100%;background:#39d98a;border-radius:4px}
.signo{font-weight:800;color:#ffd166}.cols{white-space:pre-wrap;background:#101a33;
padding:12px;border-radius:10px;margin-top:10px;line-height:1.5}
.log{background:#0d1428;color:#93a5cf;font-family:ui-monospace,monospace;font-size:11px;
padding:10px;border-radius:10px;max-height:160px;overflow:auto;margin-top:10px}
</style></head><body>
<h1>&#127922; PANEL QUINIELA <span id=jor></span></h1>
<div class=sub>Programa oficial · doble motor DC · pleno 16 signos · optimizador cobertura/EV</div>
<button onclick=run(this)>&#9654; EJECUTAR SEMANA</button>
<button class=sec onclick=pub(this)>&#128228; PUBLICAR EN LIGA MAESTROS</button>
<span id=msg></span>
<div id=salida></div><div class=log id=log></div>
<script>
async function run(b){b.disabled=true;msg('Ejecutando doble motor + optimizador...');
const r=await fetch('/api/run',{method:'POST'});const d=await r.json();
b.disabled=false;msg(d.returncode==0?'OK':'ERROR rc='+d.returncode);render(d);}
async function pub(b){b.disabled=true;const r=await fetch('/api/publicar',{method:'POST'});
const d=await r.json();b.disabled=false;msg(JSON.stringify(d));}
function msg(t){document.getElementById('msg').textContent=t;}
function bar(v,max){return `<span class=bar><i style="width:${Math.round(100*v/max)}%"></i></span>`;}
function render(d){if(!d.boleto)return;const B=d.boleto;jor.textContent='· J'+B.jornada;
let lm={};(B.ligam?.predicciones||[]).forEach(p=>lm[p.numero]=p);
(B.ligaf?.pronosticos||[]).forEach(p=>{if(p.numero!=null)lm[p.numero]=p;});
let rows='';Object.keys(lm).map(Number).sort((a,b)=>a-b).forEach(n=>{const p=lm[n];
const lf=p.pleno||String(p.fuente||p.fuente_ratings||'').includes('2324');
const cls=(lf?'ligaf ':'')+(p.pleno?'pleno':'');
if(p.pleno){rows+=`<tr class="${cls}"><td>${n}</td><td>${p.local} - ${p.visitante}</td>
<td colspan=3>PLENO 15: <b>${p.pleno.signo}</b></td></tr>`;return;}
const s=p.signo||p.signo_modelo;const mx=Math.max(p.prob_1??p.p1,p.prob_x??p.px,p.prob_2??p.p2);
rows+=`<tr class="${cls}"><td>${n}</td><td>${p.local} - ${p.visitante}</td>
<td>${bar(p.prob_1??p.p1,mx)} ${(p.prob_1??p.p1).toFixed(2)}</td>
<td>${bar(p.prob_x??p.px,mx)} ${(p.prob_x??p.px).toFixed(2)}</td>
<td>${bar(p.prob_2??p.p2,mx)} ${(p.prob_2??p.p2).toFixed(2)}</td>
<td class=signo>${s}</td></tr>`;});
let opt='';const O=d.optimizacion||{};
for(const k of ['politica_cobertura','politica_ev_parimutuel']){const o=O[k];if(!o)continue;
opt+=`<div class=cols><b>${k}</b> · ${o.columnas.length} col · ${o.coste_eur} EUR · P=${o.p_acierto_total}`
+(o.ev_eur!=null?` · EV=${o.ev_eur} EUR`:'')+`\n`;
o.columnas.forEach(c=>opt+=c.signos+'\n');opt+='</div>';}
salida.innerHTML=`<table><tr><th>CAS</th><th>PARTIDO</th><th>1</th><th>X</th><th>2</th><th>SIGNO</th></tr>${rows}</table>`+opt;
log.textContent=d.cola_log||'';}
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/":
            self._send(200, HTML.encode(), "text/html; charset=utf-8")
        elif self.path == "/api/estado":
            self._send(200, _ESTADO.get("payload") or {})
        else:
            self._send(404, {"error": "ruta desconocida"})

    def do_POST(self):
        try:
            if self.path == "/api/run":
                self._send(200, ejecutar_semana())
            elif self.path == "/api/publicar":
                self._send(200, publicar_liga_maestros())
            else:
                self._send(404, {"error": "ruta desconocida"})
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"error": str(exc)})

    def log_message(self, *a):  # silencio
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli", action="store_true", help="ejecuta y pinta por pantalla")
    ap.add_argument("--presupuesto", type=int, default=8)
    args = ap.parse_args()

    if args.cli:
        payload = ejecutar_semana(args.presupuesto)
        pintar_cli(payload)
        sys.exit(0)

    threading.Thread(target=lambda: (time.sleep(0.8),
                                     webbrowser.open(f"http://localhost:{PUERTO}")),
                     daemon=True).start()
    print(f"Panel abierto en http://localhost:{PUERTO}")
    ThreadingHTTPServer(("127.0.0.1", PUERTO), Handler).serve_forever()
