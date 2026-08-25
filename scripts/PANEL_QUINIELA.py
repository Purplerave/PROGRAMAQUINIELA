"""
PANEL_QUINIELA.py v2 — Panel de control del programa (todo-en-uno).

    python PANEL_QUINIELA.py            -> dashboard http://localhost:8787
    python PANEL_QUINIELA.py --cli      -> ejecuta y pinta por pantalla

v2: la ejecucion corre en HILO DE FONDO y el front hace polling ->
    el boton responde al instante, hay barra de estado, y cualquier
    error se muestra EN PANTALLA (nunca silencio).
"""
from __future__ import annotations

import argparse
import json
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

LOCK = threading.Lock()
ESTADO: dict = {"corriendo": False, "ultima_ejecucion": None,
                "payload": None, "log_tail": "", "error": None}


def ultimo(prefijo: str) -> Path | None:
    cand = sorted(SALIDAS.glob(f"{prefijo}*.json"))
    return cand[-1] if cand else None


def _pipeline(presupuesto: int):
    try:
        cmd = [sys.executable, str(ROOT / "scripts" / "RUN_SEMANA_COMPLETA.py"),
               "--presupuesto", str(presupuesto)]
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=1800)
        log = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        boleto_p, opt_p = ultimo("boleto_completo_J"), ultimo("optimizacion_boleto_J")
        with LOCK:
            ESTADO["log_tail"] = log[-2000:]
            ESTADO["ultima_ejecucion"] = datetime.now().isoformat(timespec="seconds")
            if proc.returncode != 0:
                ESTADO["error"] = f"RUN_SEMANA salio con codigo {proc.returncode}"
                return
            if not boleto_p:
                ESTADO["error"] = "No se genero boleto_completo_J*.json"
                return
            ESTADO["payload"] = {
                "generado": ESTADO["ultima_ejecucion"],
                "returncode": proc.returncode,
                "boleto": json.loads(boleto_p.read_text(encoding="utf-8")),
                "optimizacion": json.loads(opt_p.read_text(encoding="utf-8"))
                if opt_p else None,
            }
    except Exception as exc:  # noqa: BLE001
        with LOCK:
            ESTADO["error"] = repr(exc)
    finally:
        with LOCK:
            ESTADO["corriendo"] = False


def iniciar_semana(presupuesto: int = 8) -> dict:
    with LOCK:
        if ESTADO["corriendo"]:
            return {"ya_en_curso": True}
        ESTADO.update({"corriendo": True, "error": None})
    threading.Thread(target=_pipeline, args=(presupuesto,), daemon=True).start()
    return {"iniciado": True}


def estado_actual() -> dict:
    with LOCK:
        return dict(ESTADO)


def publicar_liga_maestros() -> dict:
    payload = estado_actual().get("payload")
    if not payload or not payload.get("boleto"):
        raise RuntimeError("No hay boleto. Pulsa primero EJECUTAR SEMANA.")
    boleto = payload["boleto"]
    jornada = boleto.get("jornada") or "SIN_NUMERO"
    INBOX.mkdir(parents=True, exist_ok=True)

    ligam = {int(p["numero"]): p for p in
             (boleto.get("ligam") or {}).get("predicciones", []) if p.get("numero")}
    for pr in (boleto.get("ligaf") or {}).get("pronosticos", []):
        if pr.get("numero") is not None:
            ligam[int(pr["numero"])] = pr

    casillas = []
    for num in sorted(ligam):
        p = ligam[num]
        pleno = p.get("pleno") or {}
        casillas.append({
            "numero": num,
            "partido": f"{p['local']} - {p['visitante']}",
            "signo_programa": pleno.get("signo") or p.get("signo") or p.get("signo_modelo"),
            "pleno": bool(pleno),
            **({"top3_pleno": pleno.get("top3")} if pleno.get("top3") else {}),
        })

    paquete = {
        "tipo": "quiniela_programa",
        "jornada": jornada,
        "publicado": datetime.now().isoformat(timespec="seconds"),
        "fuente": "PROGRAMAQUINIELA::PANEL_QUINIELA",
        "bote_eur": boleto.get("bote_eur"),
        "cierre": boleto.get("cierre"),
        "casillas": casillas,
    }
    opt = payload.get("optimizacion") or {}
    if opt:
        paquete["apuesta_recomendada"] = {
            k: opt[k] for k in ("politica_cobertura", "politica_ev_parimutuel")
            if opt.get(k)}
    destino = INBOX / f"QUINIELA_J{jornada}_PROGRAMA.json"
    destino.write_text(json.dumps(paquete, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    return {"publicado_en": str(destino), "jornada": jornada,
            "n_casillas": len(casillas)}


# ------------------------------------------------------------------ CLI --

def pintar_cli(payload: dict) -> None:
    boleto = payload.get("boleto")
    if not boleto:
        print(payload.get("error", "Sin resultados")); return
    print(f"\n== QUINIELA J{boleto.get('jornada')} | bote "
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
            print(f"{num:>3}  {partido:<44}{'M-0*':^7}[pleno 16 signos] "
                  f"{pleno.get('signo')} p={max(pleno.get('probs', [0])):.2f}")
            continue
        signo = p.get("signo") or p.get("signo_modelo") or "-"
        fuente = str(p.get("fuente") or p.get("fuente_ratings") or "")[:30]
        print(f"{num:>3}  {partido:<44}{signo:^7}{fuente}")
    opt = payload.get("optimizacion") or {}
    for pol in ("politica_cobertura", "politica_ev_parimutuel"):
        datos = opt.get(pol) or {}
        cols = datos.get("columnas") or []
        if cols:
            extra = f" EV={datos['ev_eur']}EUR" if datos.get("ev_eur") is not None else ""
            print(f"\n[{pol}] {len(cols)} columnas · {datos.get('coste_eur')} EUR · "
                  f"P={datos.get('p_acierto_total')}{extra}")
            for c in cols:
                print("   ", c["signos"])
    print("\n[PUBLICADO]", publicar_liga_maestros())


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
<button id="btnPub" class="sec">&#128228; PUBLICAR EN LIGA MAESTROS</button>
<span id="status">listo</span>
<div id="errbox"></div>
<div id="salida"></div>
<div class="log" id="log"></div>
<script>
"use strict";
const $=id=>document.getElementById(id);
const st=t=>{$('status').innerHTML=t;};
async function post(url){const r=await fetch(url,{method:'POST'});return r.json();}
$('btnRun').addEventListener('click',async()=>{
  $('btnRun').disabled=true;$('errbox').textContent='';$('salida').innerHTML='';
  st('<span class="spin"></span>Ejecutando doble motor + optimizador...');
  try{
    let d=await post('/api/run');
    const encuesta=setInterval(async()=>{
      const e=await (await fetch('/api/estado')).json();
      if(e.corriendo)return;
      clearInterval(encuesta);$('btnRun').disabled=false;
      if(e.error){st('ERROR');$('errbox').innerHTML='<div class="err">'+e.error+
        '</div><div class="log">'+(e.log_tail||'')+'</div>';return;}
      st('OK · '+ (e.ultima_ejecucion||''));
      if(e.payload)render(e.payload);
    },1500);
  }catch(ex){$('btnRun').disabled=false;st('FALLO RED');
    $('errbox').innerHTML='<div class="err">'+ex+'</div>';}
});
$('btnPub').addEventListener('click',async()=>{
  $('btnPub').disabled=true;st('Publicando...');
  try{const d=await post('/api/publicar');
    st('PUBLICADO');$('errbox').innerHTML='';
    alert('Publicado en:\n'+(d.publicado_en||JSON.stringify(d)));
  }catch(ex){st('ERROR');$('errbox').innerHTML='<div class="err">'+ex+'</div>';}
  $('btnPub').disabled=false;
});
function bar(v,max){return '<span class="bar"><i style="width:'+
  Math.round(100*v/max)+'%"></i></span>';}
function esc(s){return String(s).replace(/</g,'&lt;');}
function render(d){const B=d.boleto;if(!B){st('sin datos');return;}
  $('jor').textContent='· J'+B.jornada+' · bote '+(B.bote_eur/1e6)+'M€';
  let lm={};(B.ligam&&B.ligam.predicciones||[]).forEach(p=>lm[p.numero]=p);
  ((B.ligaf||{}).pronosticos||[]).forEach(p=>{if(p.numero!=null)lm[p.numero]=p;});
  let rows='';
  Object.keys(lm).map(Number).sort((a,b)=>a-b).forEach(n=>{const p=lm[n];
    const esLigaF=/2324/.test(String(p.fuente||p.fuente_ratings||''));
    const cls=(esLigaF?'ligaf ':'')+(p.pleno?'pleno':'');
    const pl=p.pleno||{};
    if(pl.signo){
      rows+='<tr class="'+cls.trim()+'"><td>'+n+'</td><td>'+esc(p.local+' - '+p.visitante)+
        '</td><td colspan="3"><b>PLENO 15:</b> '+esc(pl.signo)+
        ' ('+Math.max.apply(null,pl.probs).toFixed(3)+')</td></tr>';return;}
    const s=p.signo||p.signo_modelo||'-';
    const a=p.prob_1!=null?p.prob_1:p.p1,x=p.prob_x!=null?p.prob_x:p.px,
          b=p.prob_2!=null?p.prob_2:p.p2,mx=Math.max(a,x,b);
    rows+='<tr class="'+cls.trim()+'"><td>'+n+'</td><td>'+esc(p.local+' - '+p.visitante)+
      '</td><td>'+bar(a,mx)+' '+a.toFixed(2)+'</td><td>'+bar(x,mx)+' '+x.toFixed(2)+
      '</td><td>'+bar(b,mx)+' '+b.toFixed(2)+'</td><td class="signo">'+esc(s)+'</td></tr>';
  });
  let opt='';const O=d.optimizacion||{};
  ['politica_cobertura','politica_ev_parimutuel'].forEach(k=>{const o=O[k];if(!o)return;
    opt+='<div class="cols"><b>'+k+'</b> · '+o.columnas.length+' columnas · '+
      o.coste_eur+' EUR · P='+o.p_acierto_total+
      (o.ev_eur!=null?(' · EV='+o.ev_eur+' EUR'):'')+'\n'+
      o.columnas.map(c=>c.signos).join('\n')+'</div>';});
  $('salida').innerHTML='<table><tr><th>CAS</th><th>PARTIDO</th><th>1</th><th>X</th>'+
    '<th>2</th><th>SIGNO</th></tr>'+rows+'</table>'+opt;
  $('log').textContent=d.cola_log||'';}
(async()=>{try{const e=await (await fetch('/api/estado')).json();if(e.payload)render(e.payload);}catch(_){}})();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, obj, ctype="application/json; charset=utf-8"):
        raw = obj if isinstance(obj, bytes) else json.dumps(
            obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/":
            self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/estado":
            self._send(200, estado_actual())
        else:
            self._send(404, {"error": "ruta desconocida"})

    def do_POST(self):
        try:
            if self.path == "/api/run":
                self._send(200, iniciar_semana())
            elif self.path == "/api/publicar":
                self._send(200, publicar_liga_maestros())
            else:
                self._send(404, {"error": "ruta desconocida"})
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"error": repr(exc)})

    def log_message(self, *a):  # silencio
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli", action="store_true")
    ap.add_argument("--presupuesto", type=int, default=8)
    args = ap.parse_args()

    if args.cli:
        iniciar_semana(args.presupuesto)
        while ESTADO["corriendo"]:
            time.sleep(1)
        pintar_cli(ESTADO["payload"] or ESTADO)
        sys.exit(0)

    webbrowser.open(f"http://localhost:{PUERTO}")
    print(f"Panel: http://localhost:{PUERTO}  (Ctrl+C para apagar)")
    ThreadingHTTPServer(("127.0.0.1", PUERTO), Handler).serve_forever()
