#!/usr/bin/env python3
"""Genera el contrato JSON/API estable para "Liga de Maestros".

Lee el paquete consolidado de una jornada (`SALIDAS/paquete_jornada_J{jornada}.json`)
y emite un contrato estable (`SALIDAS/api_maestros_J{jornada}.json`) que la
plataforma Liga de Maestros puede consumir sin depender de la estructura
interna del paquete.

ROADMAP #5: "Contrato JSON o API estable para entregar el pronóstico a Liga de
Maestros".

Propiedades del contrato estable:
- ``contrato_version``: versión del esquema (semver). Solo se cambia con
  cambios no retrocompatibles; los campos se añaden de forma aditiva.
- ``build_api_contract``: función pura (sin I/O) y por tanto testeable.
- ``validar_contrato``: comprobación del esquema antes de escribir la salida.
"""

from __future__ import annotations

import argparse
import json
from typing import Optional

import settings

# Versión del esquema del contrato (semver). Incrementar el major solo ante
# cambios no retrocompatibles; añadir campos nuevos es compatible.
CONTRATO_VERSION = "1.0"

# Campos obligatorios por objeto, usados por la validación.
_REQUERIDOS_PRINCIPAL = ("jornada", "fecha_generacion", "modelo_version", "partidos", "pleno15")
_REQUERIDOS_PARTIDO = ("numero", "local", "visitante", "probabilidades")
_REQUERIDOS_PLENO = ("local", "visitante", "marcador", "pronostico_local", "pronostico_visitante")
_SIGNOS = ("1", "X", "2")


def _flotante_por_defecto(valor, por_defecto: float) -> float:
    """Devuelve ``valor`` si es un número finito; si no, ``por_defecto``."""
    if isinstance(valor, (int, float)) and valor == valor and abs(valor) != float("inf"):
        return float(valor)
    return por_defecto


def _procesar_partido(p: dict, num: int) -> dict:
    """Construye el objeto de partido (1-14) del contrato."""
    rm = p.get("recomendacion_modelo", {}) if isinstance(p.get("recomendacion_modelo"), dict) else {}
    pm = (p.get("probabilidades") or {}).get("modelo") if isinstance(p.get("probabilidades"), dict) else {}
    if not isinstance(pm, dict):
        pm = {}

    probs = {
        "1": _flotante_por_defecto(pm.get("1"), 1 / 3),
        "X": _flotante_por_defecto(pm.get("X"), 1 / 3),
        "2": _flotante_por_defecto(pm.get("2"), 1 / 3),
    }
    # Normaliza para que sumen 1 (robusto ante valores ausentes).
    total = sum(probs.values())
    if total and total != 1.0:
        probs = {k: v / total for k, v in probs.items()}

    return {
        "numero": num,
        "local": p.get("local"),
        "visitante": p.get("visitante"),
        "probabilidades": probs,
        "signo_maestro": rm.get("signo_principal"),
        "apuesta": rm.get("apuesta_recomendada"),
        "tipo": rm.get("tipo_apuesta"),
        "confianza": _flotante_por_defecto(rm.get("confianza_modelo"), 0.0),
    }


def _procesar_pleno(p: dict, paquete: dict) -> dict:
    """Construye el objeto Pleno 15 del contrato."""
    mm = p.get("modelo_maestro", {}) if isinstance(p.get("modelo_maestro"), dict) else {}
    if mm.get("disponible"):
        sel = mm.get("seleccion") or {}
        return {
            "local": p.get("local"),
            "visitante": p.get("visitante"),
            "marcador": mm.get("marcador_predicho"),
            "pronostico_local": sel.get("local"),
            "pronostico_visitante": sel.get("visitante"),
        }
    # Fallback al diagnóstico Q15 (marcadores) cuando el modelo no está.
    diag = (paquete.get("pleno15") or {}).get("diagnostico_q15") if isinstance(paquete.get("pleno15"), dict) else {}
    if not isinstance(diag, dict):
        diag = {}
    top = (diag.get("top_marcadores") or [{}])[0].get("score") if diag.get("top_marcadores") else None
    return {
        "local": p.get("local"),
        "visitante": p.get("visitante"),
        "marcador": top,
        "pronostico_local": "1",  # Fallback por defecto
        "pronostico_visitante": "1",
    }


def build_api_contract(paquete: dict) -> dict:
    """Transforma un paquete de jornada en el contrato estable (función pura).

    No lee ni escribe archivos: solo transforma ``paquete``. Emite el dict del
    contrato, que luego puede escribirse o validarse.
    """
    partidos_in = paquete.get("partidos", []) or []
    partidos_out = []
    pleno15 = None

    for p in partidos_in:
        num = p.get("num")
        if num == 15:
            pleno15 = _procesar_pleno(p, paquete)
            continue
        if num is not None:
            partidos_out.append(_procesar_partido(p, num))

    partidos_out.sort(key=lambda x: x["numero"])

    return {
        "contrato_version": CONTRATO_VERSION,
        "jornada": paquete.get("jornada"),
        "fecha_generacion": paquete.get("fecha_generacion"),
        "modelo_version": (paquete.get("modelo_info") or {}).get("version", "unknown")
        if isinstance(paquete.get("modelo_info"), dict)
        else "unknown",
        "partidos": partidos_out,
        "pleno15": pleno15,
    }


def validar_contrato(contrato: dict) -> list[str]:
    """Valida el esquema del contrato. Devuelve una lista de errores (vacía si ok)."""
    errores: list[str] = []
    for campo in _REQUERIDOS_PRINCIPAL:
        if campo not in contrato:
            errores.append(f"falta campo principal: {campo}")

    partidos = contrato.get("partidos") or []
    if not isinstance(partidos, list):
        errores.append("partidos debe ser una lista")
    else:
        if len(partidos) != 14:
            errores.append(f"se esperaban 14 partidos, hay {len(partidos)}")
        for m in partidos:
            for campo in _REQUERIDOS_PARTIDO:
                if campo not in m:
                    errores.append(f"falta campo en partido {m.get('numero')}: {campo}")
            probs = m.get("probabilidades")
            if isinstance(probs, dict):
                for s in _SIGNOS:
                    if s not in probs:
                        errores.append(f"probabilidades sin signo {s} en partido {m.get('numero')}")
                total = sum(probs.get(s, 0) for s in _SIGNOS)
                if total and abs(total - 1.0) > 1e-6:
                    errores.append(f"probabilidades no suman 1 en partido {m.get('numero')}")
            else:
                errores.append(f"probabilidades ausentes en partido {m.get('numero')}")

    pleno = contrato.get("pleno15")
    if pleno is None:
        errores.append("falta pleno15")
    elif not isinstance(pleno, dict):
        errores.append("pleno15 debe ser un objeto")
    else:
        for campo in _REQUERIDOS_PLENO:
            if campo not in pleno:
                errores.append(f"falta campo en pleno15: {campo}")
    return errores


def generate_api_contract(jornada: int) -> Optional[dict]:
    """Lee el paquete de disco, lo transforma, valida y escribe el contrato.

    Devuelve el contrato si se generó correctamente; ``None`` si el paquete no
    existe o el contrato no supera la validación.
    """
    paquete_path = settings.SALIDAS_DIR / f"paquete_jornada_J{jornada}.json"
    if not paquete_path.exists():
        print(f"Error: No se encuentra el paquete de la jornada {jornada} en {paquete_path}")
        return None

    with open(paquete_path, "r", encoding="utf-8") as f:
        paquete = json.load(f)

    contrato = build_api_contract(paquete)
    errores = validar_contrato(contrato)
    if errores:
        print("Contrato no válido; no se escribe la salida:")
        for err in errores:
            print(f"  - {err}")
        return None

    out_path = settings.SALIDAS_DIR / f"api_maestros_J{jornada}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(contrato, f, ensure_ascii=False, indent=2)
    print(f"Contrato API generado: {out_path} (esquema v{CONTRATO_VERSION})")
    return contrato


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jornada", "-j", type=int, required=True, help="Número de jornada")
    args = parser.parse_args()
    generate_api_contract(args.jornada)


if __name__ == "__main__":
    main()
