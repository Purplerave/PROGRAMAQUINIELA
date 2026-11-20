#!/usr/bin/env python3
"""Valida y exporta el contrato JSON v1.1 para Liga de Maestros."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import settings
from scripts.json_output import write_json
from scripts.motor.boletos import BUCKETS, SIGNOS, require_positions, select_probabilities


CONTRATO_VERSION = "1.1"
ORIGENES_PREDICCION_VALIDOS = ("motor_v4", "manual_pendiente", "manual_revisado")
SOURCES_1X2 = ("motor_maestro", "apu_fallback", "lae_fallback", "q15_fallback")
SOURCES_PLENO = ("motor_maestro", "q15_fallback")
JOINT_SIGNS = {f"{h}-{a}" for h in BUCKETS for a in BUCKETS}
_SCORE = re.compile(r"(?:[0-9]+|M)-(?:[0-9]+|M)")


def prediction_origin(match: dict, default: str = "motor_v4") -> str:
    origin = match.get("origen_prediccion", match.get("origen", default))
    if origin not in ORIGENES_PREDICCION_VALIDOS or (origin == "motor_v4" and default == "manual_pendiente"):
        return default
    return origin


def _procesar_partido(match: dict) -> dict:
    probs, source = select_probabilities(match)
    rec = match.get("recomendacion_modelo")
    rec = rec if isinstance(rec, dict) else {}
    return {
        "numero": match["num"],
        "local": match.get("local"),
        "visitante": match.get("visitante"),
        "probabilidades": probs,
        "signo_maestro": rec.get("signo_principal"),
        "apuesta": rec.get("apuesta_recomendada"),
        "tipo": rec.get("tipo_apuesta"),
        "confianza": rec.get("confianza_modelo", 0.0),
        "fuente_probabilidades": source,
        "origen_prediccion": prediction_origin(match, "motor_v4" if source == "motor_maestro" else "manual_pendiente"),
    }


def _bucket(value: object) -> str | None:
    text = str(value).upper()
    if text in BUCKETS:
        return text
    if re.fullmatch(r"[0-9]+", text):
        return "M" if int(text) >= 3 else str(int(text))
    return None


def _procesar_pleno(match: dict, package: dict) -> dict:
    model = match.get("modelo_maestro") or {}
    available = model.get("disponible") is True
    if available:
        selection = model.get("seleccion") or {}
        score = model.get("marcador_predicho")
        home, away = _bucket(selection.get("local")), _bucket(selection.get("visitante"))
    else:
        # El proxy es un marcador publicado, nunca un 1-1 inventado.
        diagnostic = (package.get("pleno15") or {}).get("diagnostico_q15") or match.get("pleno15") or {}
        score = next((str(m.get("score", "")).upper() for m in diagnostic.get("top_marcadores", [])
                      if isinstance(m, dict) and _SCORE.fullmatch(str(m.get("score", "")).upper())), None)
        home, away = map(_bucket, score.split("-")) if score else (None, None)

    return {
        "local": match.get("local"),
        "visitante": match.get("visitante"),
        "marcador": score,
        "pronostico_local": home,
        "pronostico_visitante": away,
        "fuente_probabilidades": "motor_maestro" if available else "q15_fallback" if score else "sin_fuente",
        "origen_prediccion": prediction_origin(match, "motor_v4" if available else "manual_pendiente"),
        **{key: model[key] for key in ("goles_local", "goles_visitante", "goles_conjuntos", "top_marcadores", "lambdas")
           if available and model.get(key)},
    }


def build_api_contract(paquete: dict) -> dict:
    """Transforma el paquete explícito 14+1 sin inventar resultados ni posiciones."""
    partidos = sorted(require_positions(paquete.get("partidos")), key=lambda p: p["num"])
    return {
        "contrato_version": CONTRATO_VERSION,
        "jornada": paquete.get("jornada"),
        "fecha_generacion": paquete.get("fecha_generacion"),
        "modelo_version": (paquete.get("modelo_info") or {}).get("version", "unknown"),
        "partidos": [_procesar_partido(p) for p in partidos[:-1]],
        "pleno15": _procesar_pleno(partidos[-1], paquete),
    }


def _probability(value: object) -> bool:
    # El rango rechaza también NaN e infinitos, sin conversiones implícitas.
    return type(value) in (int, float) and 0 <= value <= 1


def _name(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validar_contrato(contrato: dict) -> list[str]:
    """Devuelve errores de tipos, identidad, dominios y normalización."""
    if not isinstance(contrato, dict):
        return ["El contrato debe ser un objeto"]
    errors = []
    if contrato.get("contrato_version") != CONTRATO_VERSION:
        errors.append("contrato_version no soportada")
    jornada = contrato.get("jornada")
    if type(jornada) is not int or jornada < 1:
        errors.append("jornada debe ser un entero positivo")
    try:
        datetime.fromisoformat(contrato.get("fecha_generacion"))
    except (TypeError, ValueError):
        errors.append("fecha_generacion debe ser ISO 8601")
    if not _name(contrato.get("modelo_version")):
        errors.append("modelo_version debe ser texto no vacío")

    partidos = contrato.get("partidos")
    try:
        require_positions(partidos, key="numero", count=14)
    except ValueError as exc:
        errors.append(f"Se requieren 14 partidos: {exc}")
    for p in partidos if isinstance(partidos, list) else []:
        if not isinstance(p, dict):
            continue  # Ya informado por require_positions.
        num = p.get("numero")
        if not all(_name(p.get(key)) for key in ("local", "visitante")):
            errors.append(f"Equipos ausentes en partido {num}")
        probs = p.get("probabilidades")
        if not isinstance(probs, dict) or set(probs) != set(SIGNOS) or not all(_probability(v) for v in probs.values()):
            errors.append(f"Probabilidades 1X2 inválidas en partido {num}")
        elif abs(sum(probs.values()) - 1.0) > 1e-6:
            errors.append(f"Probabilidades no suman 1 en partido {num}")
        source, origin = p.get("fuente_probabilidades"), p.get("origen_prediccion")
        if source not in SOURCES_1X2:
            errors.append(f"fuente_probabilidades inválida en partido {num}")
        if origin not in ORIGENES_PREDICCION_VALIDOS or (origin == "motor_v4" and source != "motor_maestro"):
            errors.append(f"origen_prediccion incompatible en partido {num}")
        if not _probability(p.get("confianza")):
            errors.append(f"Confianza inválida en partido {num}")
        sign, bet, kind = p.get("signo_maestro"), p.get("apuesta"), p.get("tipo")
        if any(v is not None for v in (sign, bet, kind)):
            sizes = {"simple": 1, "doble": 2, "triple": 3}
            if (sign not in SIGNOS or not isinstance(bet, str) or not isinstance(kind, str)
                    or kind not in sizes or len(bet) != sizes[kind] or len(set(bet)) != len(bet)
                    or not set(bet) <= set(SIGNOS) or sign not in bet):
                errors.append(f"Recomendación incoherente en partido {num}")

    pleno = contrato.get("pleno15")
    if not isinstance(pleno, dict):
        errors.append("pleno15 ausente o inválido")
    else:
        if not all(_name(pleno.get(key)) for key in ("local", "visitante")):
            errors.append("Equipos ausentes en pleno15")
        score = pleno.get("marcador")
        if not isinstance(score, str) or not _SCORE.fullmatch(score):
            errors.append("Marcador ausente o inválido en pleno15")
        if not all(pleno.get(k) in BUCKETS for k in ("pronostico_local", "pronostico_visitante")):
            errors.append("Buckets inválidos en pleno15")
        source, origin = pleno.get("fuente_probabilidades"), pleno.get("origen_prediccion")
        if source not in SOURCES_PLENO:
            errors.append("fuente_probabilidades inválida en pleno15")
        if origin not in ORIGENES_PREDICCION_VALIDOS or (origin == "motor_v4" and source != "motor_maestro"):
            errors.append("origen_prediccion incompatible en pleno15")
        selection = f"{pleno.get('pronostico_local')}-{pleno.get('pronostico_visitante')}"
        if (
            source == "q15_fallback"
            and isinstance(score, str)
            and _SCORE.fullmatch(score)
            and "-".join(_bucket(part) for part in score.split("-")) != selection
        ):
            errors.append("El Pleno basado en Q15 no coincide con su marcador")
        if "goles_conjuntos" in pleno:
            joint = pleno["goles_conjuntos"]
            if (source != "motor_maestro" or not isinstance(joint, dict) or set(joint) != JOINT_SIGNS
                    or not all(_probability(p) for p in joint.values()) or abs(sum(joint.values()) - 1.0) > 1e-6):
                errors.append("Distribución conjunta inválida en pleno15")
            elif selection not in joint or max(joint.values()) - joint[selection] > 1e-8:
                errors.append("La selección del Pleno no representa la moda conjunta")
    return errors


def generate_api_contract(jornada: int) -> dict | None:
    path = settings.SALIDA_DIR / f"paquete_jornada_J{jornada}.json"
    if not path.is_file():
        print(f"Error: No se encuentra el paquete de la jornada {jornada} en {path}")
        return None
    try:
        package = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(package, dict) or type(package.get("jornada")) is not int or package["jornada"] != jornada:
            raise ValueError(f"{path.name} no declara la jornada {jornada}")
        contrato = build_api_contract(package)
        errors = validar_contrato(contrato)
        if errors:
            raise ValueError("; ".join(errors))
        out = settings.SALIDA_DIR / f"api_maestros_J{jornada}.json"
        write_json(out, contrato)
    except (AttributeError, TypeError, ValueError, OSError) as exc:
        print(f"Contrato no válido o no escribible; no se actualiza la salida: {exc}")
        return None
    print(f"Contrato API generado: {out} (esquema v{CONTRATO_VERSION})")
    return contrato


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jornada", "-j", type=int, required=True)
    return int(generate_api_contract(parser.parse_args().jornada) is None)


if __name__ == "__main__":
    raise SystemExit(main())
