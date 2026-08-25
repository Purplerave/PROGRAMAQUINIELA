"""
PUBLICAR_WEB.py — Publicacion SEGURA e IDEMPOTENTE de la semana en Liga Maestros.

Cadena que ejecuta:
    1. Carga el ultimo boleto_completo_J*.json + optimizacion
    2. SEGURIDAD: si esa jornada ya fue publicada CON LOS MISMOS SIGNOS,
       aborta sin tocar nada ("YA PUBLICADA").
    3. Si no: publica (inbox + BD local + commit/push a GitHub -> deploy).

El registro queda en DATOS/PUBLICACIONES.json (auditable).

Uso:
    python PUBLICAR_WEB.py            # publica o detecta duplicado
    python PUBLICAR_WEB.py --forzar   # republica aunque sea identico
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import PANEL_QUINIELA as P  # noqa: E402

MARCADOR = ROOT / "DATOS" / "PUBLICACIONES.json"


def signos_del_boleto(boleto: dict) -> list[str]:
    ligam = {int(p["numero"]): p for p in
             (boleto.get("ligam") or {}).get("predicciones", []) if p.get("numero")}
    for pr in (boleto.get("ligaf") or {}).get("pronosticos", []):
        if pr.get("numero") is not None:
            ligam[int(pr["numero"])] = pr
    out = []
    for n in sorted(ligam):
        p = ligam[n]
        pleno = p.get("pleno") or {}
        out.append(pleno.get("signo") or p.get("signo") or p.get("signo_modelo") or "-")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--forzar", action="store_true")
    args = ap.parse_args()

    boleto_p, opt_p = P.ultimo("boleto_completo_J"), P.ultimo("optimizacion_boleto_J")
    if not boleto_p:
        sys.exit("No hay boleto_completo_J*.json. Ejecuta antes RUN_SEMANA_COMPLETA.")
    boleto = json.loads(boleto_p.read_text(encoding="utf-8"))
    opt = json.loads(opt_p.read_text(encoding="utf-8")) if opt_p else None

    jornada = boleto.get("jornada")
    signos = signos_del_boleto(boleto)
    huella = hashlib.sha256(("J%s|%s" % (jornada, "|".join(signos)))
                            .encode()).hexdigest()[:12]

    pub = {}
    if MARCADOR.exists():
        pub = json.loads(MARCADOR.read_text(encoding="utf-8"))
    previo = pub.get(str(jornada))
    if previo and previo.get("huella") == huella and not args.forzar:
        print(f"[SEGURIDAD] La J{jornada} ya fue publicada el "
              f"{previo.get('fecha')} con EXACTAMENTE los mismos signos.")
        print(f"  Signos: {' '.join(signos)}")
        print("  Nada que hacer. (Usa --forzar si de verdad quieres republicar)")
        return

    P.ESTADO["payload"] = {"boleto": boleto, "optimizacion": opt}
    res = P.publicar_liga_maestros()

    pub[str(jornada)] = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "huella": huella,
        "signos": " ".join(signos),
        "importador_rc": (res.get("importacion_web") or {}).get("returncode"),
    }
    MARCADOR.write_text(json.dumps(pub, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

    imp = res.get("importacion_web") or {}
    git = res.get("git") or {}
    print(f"[OK] J{jornada} publicada. Huella={huella}")
    print(f"     Importador local rc={imp.get('returncode')}")
    if git.get("error"):
        print(f"     PUSH ERROR: {git['error']}")
    elif git.get("pasos"):
        ultimo_paso = git["pasos"][-1] if isinstance(git["pasos"], list) else git["detalle"]
        print(f"     GIT: ...{str(ultimo_paso)[-160:]}")


if __name__ == "__main__":
    main()
