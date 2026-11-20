"""Panel local del boleto semanal. Ejecutar y exportar son acciones separadas.

La exportación prepara archivos bajo SALIDAS; no importa datos, lanza Git ni
publica en ningún repositorio externo.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import settings
from scripts.OPTIMIZADOR_BOLETO import parse_casillas
from scripts.RUN_SEMANA_COMPLETA import BOLETO_FUENTE, cargar_boleto, output_label
from scripts.json_output import write_json
from scripts.motor.boletos import SIGNOS
from scripts.motor.pleno_model import ETIQUETAS_PLENO
from scripts.motor.temporal import utc_timestamp


PUERTO = 8787
PANEL_TOKEN = secrets.token_urlsafe(32)
MAX_POST_BODY_BYTES = 0  # Las dos operaciones POST no aceptan payload.
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
LOCK = threading.Lock()
ESTADO: dict = {"corriendo": False, "ultima_ejecucion": None,
                "payload": None, "log_tail": "", "error": None}


def load_weekly_output(jornada: int, demo: bool = False) -> dict:
    if type(jornada) is not int or jornada < 1:
        raise ValueError("La jornada debe ser un entero positivo")
    tag = output_label(jornada, demo)
    path = settings.SALIDAS_DIR / f"boleto_completo_{tag}.json"
    raw = path.read_bytes()
    ticket = json.loads(raw)
    opt = json.loads((settings.SALIDAS_DIR / f"optimizacion_boleto_{tag}.json").read_text(encoding="utf-8"))
    if (not isinstance(ticket, dict) or not isinstance(opt, dict)
            or ticket.get("jornada") != jornada or opt.get("jornada") != jornada
            or ticket.get("demo") is not demo or opt.get("demo") is not demo
            or opt.get("entrada_sha256") != hashlib.sha256(raw).hexdigest()):
        raise ValueError("La optimización no corresponde al boleto actual; vuelve a ejecutar la semana")
    parse_casillas(ticket)
    return {"boleto": ticket, "optimizacion": opt}


def _pipeline(presupuesto: int, source: Path, demo: bool):
    try:
        ticket = cargar_boleto(source, demo=demo)
        cmd = [sys.executable, str(settings.PROJECT_DIR / "scripts" / "RUN_SEMANA_COMPLETA.py"),
               "--presupuesto", str(presupuesto), "--jornada", str(ticket["jornada"])]
        cmd += ["--demo"] if demo else ["--boleto", str(source.resolve())]
        proc = subprocess.run(cmd, cwd=settings.PROJECT_DIR, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=1800)
        log = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        with LOCK:
            ESTADO["log_tail"] = log[-2000:]
        if proc.returncode:
            raise RuntimeError(f"La ejecución semanal falló (código {proc.returncode})")
        payload = load_weekly_output(ticket["jornada"], demo)
        with LOCK:
            ESTADO["payload"] = payload
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        with LOCK:
            ESTADO["error"] = str(exc)
    finally:
        with LOCK:
            ESTADO["ultima_ejecucion"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            ESTADO["corriendo"] = False


def iniciar_semana(presupuesto: int = 8, source: Path = BOLETO_FUENTE, demo: bool = False) -> dict:
    with LOCK:
        if ESTADO["corriendo"]:
            return {"ya_en_curso": True}
        ESTADO.update(corriendo=True, error=None, payload=None, log_tail="")
    threading.Thread(target=_pipeline, args=(presupuesto, source, demo), daemon=True).start()
    return {"iniciado": True}


def estado_actual() -> dict:
    with LOCK:
        return dict(ESTADO)


def exportar_liga_maestros(payload: dict) -> dict:
    ticket = payload["boleto"]
    jornada = ticket.get("jornada")
    if type(jornada) is not int or jornada < 1:
        raise ValueError("Jornada inválida para exportación")
    if ticket.get("demo") is not False:
        raise ValueError("Un boleto de demostración no se puede exportar")
    if utc_timestamp(ticket.get("cierre")) <= datetime.now(timezone.utc):
        raise ValueError(f"La jornada J{jornada} ya está cerrada")
    casillas = parse_casillas(ticket)
    matches = sorted(ticket["ligam"]["predicciones"] + ticket["ligaf"]["pronosticos"], key=lambda p: p["numero"])
    signs = []
    inbox_rows = []
    for p in matches:
        pleno = p.get("pleno") or {}
        sign = pleno.get("signo") or p.get("signo") or p.get("signo_modelo")
        if sign not in (ETIQUETAS_PLENO if p["numero"] == 15 else SIGNOS):
            raise ValueError(f"Signo inválido en casilla {p['numero']}")
        signs.append(sign)
        inbox_rows.append({"numero": p["numero"], "partido": f"{p['local']} - {p['visitante']}",
                           "signo_programa": sign, "pleno": p["numero"] == 15})
    target = settings.SALIDAS_DIR / "entrega_liga_maestros" / f"J{jornada}"
    opt = payload["optimizacion"]
    write_json(target / "inbox" / f"QUINIELA_J{jornada}_PROGRAMA.json", {
        "tipo": "quiniela_programa", "jornada": jornada, "exportado": datetime.now(timezone.utc).isoformat(),
        "fuente": "PROGRAMAQUINIELA", "cierre": ticket["cierre"], "bote_eur": ticket.get("bote_eur"),
        "casillas": inbox_rows, "apuesta_recomendada": {
            k: opt[k] for k in ("politica_cobertura", "politica_ev_parimutuel") if k in opt
        },
    })
    write_json(target / "DATOS" / f"QUINIELA15_J{jornada}.json", {
        "jornada": jornada, "partidos": [{"num": p["numero"], "local": p["local"], "visitante": p["visitante"]} for p in matches],
    })
    write_json(target / "SALIDAS" / f"quiniela_programa_J{jornada}.json", {"signos": signs})
    write_json(target / "DATOS" / f"PROBABILIDADES_J{jornada}.json", {
        str(c["numero"]): {"num": c["numero"], "probabilidades": dict(zip(c["etiquetas"], c["probs"]))}
        for c in casillas[:-1]
    })
    return {"estado": "exportado_localmente", "ruta": str(target), "jornada": jornada, "n_casillas": len(casillas)}


def exportar_actual() -> dict:
    state = estado_actual()
    payload = state["payload"]
    if state["corriendo"] or not payload:
        raise ValueError("No hay boleto vigente de una ejecución completada")
    ticket = payload["boleto"]
    return exportar_liga_maestros(load_weekly_output(ticket["jornada"], ticket["demo"]))


def _host_local_valido(host: str | None) -> bool:
    if not host:
        return False
    try:
        parsed = urlsplit(f"//{host}")
        return (
            parsed.hostname in LOCAL_HOSTS
            and parsed.port == PUERTO
            and parsed.username is None
            and parsed.password is None
            and parsed.path == ""
        )
    except ValueError:
        return False


def _origen_local_valido(origin: str | None) -> bool:
    if not origin:
        return False
    try:
        parsed = urlsplit(origin)
        return (
            parsed.scheme == "http"
            and parsed.hostname in LOCAL_HOSTS
            and parsed.port == PUERTO
            and parsed.username is None
            and parsed.password is None
            and parsed.path == ""
            and parsed.query == ""
            and parsed.fragment == ""
        )
    except ValueError:
        return False


def validar_post(headers, token: str = PANEL_TOKEN) -> tuple[int, str] | None:
    """Autoriza solo POST del panel local, con origen, token y cuerpo vacío."""
    if not _host_local_valido(headers.get("Host")):
        return 403, "host no permitido"
    origin = headers.get("Origin")
    if not _origen_local_valido(origin):
        return 403, "origen no permitido"
    request_host = urlsplit(f"//{headers['Host']}")
    origin_host = urlsplit(origin)
    if (request_host.hostname != origin_host.hostname
            or request_host.port != origin_host.port):
        return 403, "host y origen no coinciden"
    supplied = headers.get("X-Panel-Token", "")
    if not supplied or not hmac.compare_digest(supplied, token):
        return 403, "token de sesión inválido"
    if headers.get("Transfer-Encoding"):
        return 400, "transfer-encoding no permitido"
    try:
        length = int(headers.get("Content-Length", "0"))
    except (TypeError, ValueError):
        return 400, "content-length inválido"
    if length < 0:
        return 400, "content-length inválido"
    if length > MAX_POST_BODY_BYTES:
        return 413, "el panel no acepta cuerpos POST"
    return None


# ------------------------------------------------------------------ CLI --

def pintar_cli(payload: dict) -> None:
    boleto = payload.get("boleto")
    if not boleto:
        print(payload.get("error", "Sin resultados")); return
    label = "DEMO " if boleto.get("demo") else ""
    print(f"\n== QUINIELA {label}J{boleto.get('jornada')} | bote "
          f"{float(boleto.get('bote_eur') or 0):,.0f} EUR | cierre {boleto.get('cierre')} ==")
    ligam = {int(p["numero"]): p for p in
             (boleto.get("ligam") or {}).get("predicciones", []) if p.get("numero")}
    for pr in (boleto.get("ligaf") or {}).get("pronosticos", []):
        if pr.get("numero") is not None:
            ligam[int(pr["numero"])] = pr
    print(f"{'CAS':>3}  {'PARTIDO':<44}{'SIGNO':^7}ORIGEN")
    for num in sorted(ligam):
        p = ligam[num]
        partido = f"{p['local']} - {p['visitante']}"[:44]
        pleno = p.get("pleno") or {}
        if pleno.get("signo"):
            print(f"{num:>3}  {partido:<44}{pleno['signo']:^7}[pleno 16 signos] "
                  f"p={max(pleno.get('probs', [0])):.2f}")
            continue
        signo = p.get("signo") or p.get("signo_modelo") or "-"
        fuente = str(p.get("fuente") or p.get("fuente_ratings") or "")[:26]
        a = p.get("prob_1", p.get("p1", 0))
        x = p.get("prob_x", p.get("px", 0))
        b = p.get("prob_2", p.get("p2", 0))
        print(f"{num:>3}  {partido:<44}{signo:^7}"
              f"{100*a:4.0f}/{100*x:3.0f}/{100*b:3.0f}%  {fuente}")
    opt = payload.get("optimizacion") or {}
    for pol in ("politica_cobertura", "politica_ev_parimutuel"):
        datos = opt.get(pol) or {}
        cols = datos.get("columnas") or []
        if cols:
            extra = f" EV estimado={datos['ev_eur']} EUR" if datos.get("ev_eur") is not None else ""
            print(f"\n[{pol}] {len(cols)} columnas · {datos.get('coste_eur')} EUR · "
                  f"P={datos.get('p_acierto_total')}{extra}")
            for c in cols:
                print("   ", c["signos"])
    qc = opt.get("tres_dobles")
    if qc:
        print(f"\n== TU QUINIELA · {qc['n_columnas']} columnas · "
              f"{qc['coste_eur']} EUR ==")
        for d in qc["dobles"]:
            print(f"  DOBLE casilla {d['casilla']}: {'/'.join(d['signos'])}"
                  f"   [{d['partido']}]")
        print("  FIJOS:", " ".join(f"{f['casilla']}={f['signo']}" for f in qc["fijos"]))


# ------------------------------------------------------------------ HTTP --

HTML = r"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PANEL QUINIELA</title><style>
body{background:#0b1020;color:#e7ecff;font-family:system-ui;margin:0;padding:24px}
h1{margin:0 0 4px}.sub{color:#8ea0c9;margin-bottom:16px}
button{background:#1c6ef2;border:0;color:#fff;padding:12px 20px;border-radius:10px;
font-size:15px;font-weight:700;cursor:pointer;margin-right:10px}
button.sec{background:#24304f}button:disabled{opacity:.45;cursor:wait}
#status{display:inline-block;margin-left:6px;font-weight:600}
table{border-collapse:collapse;width:100%;margin-top:14px}
td,th{padding:8px 10px;border-bottom:1px solid #223055;text-align:left;font-size:14px}
tr.ligaf td{background:#12203c}tr.pleno td{background:#3a2a12}
.bar{height:8px;background:#223055;border-radius:4px;display:inline-block;width:70px}
.bar>i{display:block;height:100%;background:#39d98a;border-radius:4px}
.signo{font-weight:800;color:#ffd166;font-size:15px}
.cols{white-space:pre-wrap;background:#101a33;padding:12px;border-radius:10px;
margin-top:10px;line-height:1.55;font-family:ui-monospace,monospace;font-size:13px}
.log{background:#0d1428;color:#93a5cf;font-family:ui-monospace,monospace;font-size:11px;
padding:10px;border-radius:10px;max-height:150px;overflow:auto;margin-top:10px;
white-space:pre-wrap}
.err{background:#4a1220;color:#ffb3c0;padding:10px;border-radius:10px;margin-top:10px}
.spin{display:inline-block;width:14px;height:14px;border:3px solid #33456f;
border-top-color:#ffd166;border-radius:50%;animation:g .8s linear infinite;
vertical-align:-2px;margin-right:8px}@keyframes g{to{transform:rotate(360deg)}}
</style></head><body>
<h1>&#127922; PANEL QUINIELA <span id="jor"></span></h1>
<div class="sub">doble motor DC · pleno 16 signos · optimizador cobertura/EV</div>
<button id="btnRun">&#9654; EJECUTAR SEMANA</button>
<button id="btnPub" class="sec" disabled>&#128228; EXPORTAR ARCHIVOS</button>
<span id="status">listo</span>
<div id="errbox"></div>
<div id="salida"></div>
<div class="log" id="log"></div>
<script>
"use strict";
const $=id=>document.getElementById(id);
const st=t=>{$('status').textContent=t;};
const PANEL_TOKEN=__PANEL_TOKEN_JSON__;
async function post(url){const r=await fetch(url,{method:'POST',headers:{'X-Panel-Token':PANEL_TOKEN}});const d=await r.json();if(!r.ok)throw Error(d.error||r.status);return d;}
$('btnRun').addEventListener('click',async()=>{
  $('btnRun').disabled=true;$('btnPub').disabled=true;$('errbox').textContent='';$('salida').innerHTML='';
  st('Ejecutando doble motor + optimizador...');
  try{
    await post('/api/run');
    while(true){
      await new Promise(resolve=>setTimeout(resolve,1500));
      const response=await fetch('/api/estado');
      if(!response.ok)throw Error(response.status);
      const e=await response.json();
      if(e.corriendo)continue;
      $('btnRun').disabled=false;
      $('log').textContent=e.log_tail||'';
      if(e.error){st('ERROR');$('errbox').textContent=e.error;return;}
      st('OK · '+(e.ultima_ejecucion||''));
      if(e.payload)render(e.payload);
      return;
    }
  }catch(ex){$('btnRun').disabled=false;st('FALLO RED');
    $('errbox').textContent=ex.message;}
});
$('btnPub').addEventListener('click',async()=>{
  $('btnPub').disabled=true;st('Exportando...');
  try{const d=await post('/api/exportar');
    st('EXPORTADO LOCALMENTE');$('errbox').textContent='';
    alert('Archivos listos para revisar en:\n'+d.ruta);
  }catch(ex){st('ERROR');$('errbox').textContent=ex.message;}
  $('btnPub').disabled=false;
});
function bar(v,max){return '<span class="bar"><i style="width:'+
  Math.round(100*v/max)+'%"></i></span>';}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function render(d){const B=d.boleto;if(!B){st('sin datos');return;}
  $('jor').textContent=(B.demo?'· DEMO ':'· ')+'J'+B.jornada+' · bote '+(B.bote_eur/1e6)+'M€';
  $('btnPub').disabled=B.demo===true;
  let lm={};(B.ligam&&B.ligam.predicciones||[]).forEach(p=>lm[p.numero]=p);
  const isF=new Set();
  ((B.ligaf||{}).pronosticos||[]).forEach(p=>{if(p.numero!=null){lm[p.numero]=p;isF.add(p.numero);}});
  let rows='';
  Object.keys(lm).map(Number).sort((a,b)=>a-b).forEach(n=>{const p=lm[n];
    const esLigaF=isF.has(n);
    const cls=(esLigaF?'ligaf ':'')+(p.pleno?'pleno':'');
    const pl=p.pleno||{};
    if(pl.signo){
      rows+='<tr class="'+cls.trim()+'"><td>'+n+'</td><td>'+esc(p.local+' - '+p.visitante)+
        '</td><td colspan="3"><b>PLENO 15:</b> '+esc(pl.signo)+
        ' ('+Math.max.apply(null,pl.probs).toFixed(3)+')</td></tr>';return;}
    const s=p.signo||p.signo_modelo||'-';
    const pc=v=>Math.round(v*100)+'%';
    const a=p.prob_1!=null?p.prob_1:p.p1,x=p.prob_x!=null?p.prob_x:p.px,
          b=p.prob_2!=null?p.prob_2:p.p2,mx=Math.max(a,x,b);
    rows+='<tr class="'+cls.trim()+'"><td>'+n+'</td><td>'+esc(p.local+' - '+p.visitante)+
      '</td><td>'+bar(a,mx)+' '+pc(a)+'</td><td>'+bar(x,mx)+' '+pc(x)+
      '</td><td>'+bar(b,mx)+' '+pc(b)+'</td><td class="signo">'+esc(s)+'</td></tr>';
  });
  let opt='';const O=d.optimizacion||{};
  const T=O.tres_dobles||((O.politica_cobertura||{}).tres_dobles)||null;
  if(T){const mapa={};(T.fijos||[]).forEach(f=>mapa[f.casilla]=f.signo);
    (T.dobles||[]).forEach(dd=>{mapa[dd.casilla]=dd.signos.join('/');});
    const linea=Object.keys(mapa).map(Number).sort((a,b)=>a-b)
      .map(n=>{const v=mapa[n];return '['+n+']'+
        (v.indexOf('/')>=0?'<span class="signo">'+esc(v)+'</span>':esc(v));}).join(' ');
    opt+='<div class="cols" style="background:#13291d;border:1px solid #2f7d4f;font-size:16px">'+
      '<b>&#127942; TU COLUMNA \u2014 3 DOBLES</b>  ('+esc(T.n_columnas)+
      ' combinaciones \u00b7 '+esc(T.coste_eur)+' EUR al jugarla \u00b7 P='+
      (T.p_acierto*100).toFixed(3)+'%)\n\n'+linea+
      '\n\n<b>LOS 3 DOBLES:</b>\n'+T.dobles.map(dd=>
        'casilla '+esc(dd.casilla)+'\u00aa: <span class="signo">'+esc(dd.signos.join('/'))+
        '</span> \u2014 '+esc(dd.partido)).join('\n')+'</div>';}
  ['politica_cobertura','politica_ev_parimutuel'].forEach(k=>{const o=O[k];if(!o)return;
    opt+='<details style="margin-top:10px"><summary style="cursor:pointer;color:#8ea0c9">'+
      k+' \u2014 ver detalle</summary><div class="cols"><b>'+k+'</b> · '+
      o.columnas.length+' columnas · '+
      esc(o.coste_eur)+' EUR · P='+esc(o.p_acierto_total)+
      (o.ev_eur!=null?(' · EV estimado='+esc(o.ev_eur)+' EUR'):'')+'\n'+
      o.columnas.map(c=>esc(c.signos)).join('\n')+'</div></details>';});
  $('salida').innerHTML='<table><tr><th>CAS</th><th>PARTIDO</th><th>1</th><th>X</th>'+
    '<th>2</th><th>SIGNO</th></tr>'+rows+'</table>'+opt;
  $('log').textContent=d.cola_log||'';}
(async()=>{try{const e=await (await fetch('/api/estado')).json();if(e.payload)render(e.payload);}catch(_){}})();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    presupuesto = 8
    source = BOLETO_FUENTE
    demo = False

    def _send(self, code, obj, ctype="application/json; charset=utf-8"):
        raw = obj if isinstance(obj, bytes) else json.dumps(
            obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if not _host_local_valido(self.headers.get("Host")):
            self._send(403, {"error": "host no permitido"})
        elif self.path == "/":
            page = HTML.replace("__PANEL_TOKEN_JSON__", json.dumps(PANEL_TOKEN))
            self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/estado":
            self._send(200, estado_actual())
        else:
            self._send(404, {"error": "ruta desconocida"})

    def do_POST(self):
        if self.path not in ("/api/run", "/api/exportar"):
            self._send(404, {"error": "ruta desconocida"})
            return
        denial = validar_post(self.headers)
        if denial is not None:
            status, message = denial
            self._send(status, {"error": message})
            return
        try:
            if self.path == "/api/run":
                self._send(200, iniciar_semana(self.presupuesto, self.source, self.demo))
            else:
                self._send(200, exportar_actual())
        except (ValueError, OSError) as exc:
            self._send(400, {"error": str(exc)})

    def log_message(self, *a):  # silencio
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cli", action="store_true")
    ap.add_argument("--presupuesto", type=int, default=8)
    inputs = ap.add_mutually_exclusive_group()
    inputs.add_argument("--boleto", type=Path, default=BOLETO_FUENTE)
    inputs.add_argument("--demo", action="store_true")
    args = ap.parse_args()
    if args.cli:
        iniciar_semana(args.presupuesto, args.boleto, args.demo)
        while estado_actual()["corriendo"]:
            time.sleep(0.1)
        state = estado_actual()
        pintar_cli(state["payload"] or state)
        if not state["payload"] and state["log_tail"]:
            print(state["log_tail"], file=sys.stderr)
        return int(state["payload"] is None)

    Handler.presupuesto, Handler.source, Handler.demo = args.presupuesto, args.boleto, args.demo
    webbrowser.open(f"http://localhost:{PUERTO}")
    print(f"Panel local: http://localhost:{PUERTO}  (Ctrl+C para apagar)")
    ThreadingHTTPServer(("127.0.0.1", PUERTO), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
