"""Genera y valida el contrato JSON para Liga de Maestros.

La salida de integración no debe inventar predicciones para completar campos.
Si el Pleno al 15 o un partido no tiene modelo disponible, se marca de forma
explícita con ``disponible=false`` y valores nulos.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

SIGNS = ("1", "X", "2")
BUCKETS_PLENO = {"0", "1", "2", "M"}
BET_TYPE_BY_LEN = {1: "simple", 2: "doble", 3: "triple"}
PROB_TOLERANCE = 0.025


class ContractValidationError(ValueError):
    """Error de validación del contrato API."""


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractValidationError(message)


def _validate_probability_block(raw: Any, *, num: int) -> dict[str, float]:
    _require(isinstance(raw, dict), f"partido {num}: probabilidades.modelo ausente o no es objeto")
    _require(set(raw) == set(SIGNS), f"partido {num}: probabilidades.modelo debe tener exactamente 1/X/2")
    probs = {sign: float(raw[sign]) for sign in SIGNS}
    for sign, value in probs.items():
        _require(_is_number(value), f"partido {num}: probabilidad {sign} no numérica")
        _require(0.0 <= value <= 1.0, f"partido {num}: probabilidad {sign} fuera de [0,1]")
    total = sum(probs.values())
    _require(abs(total - 1.0) <= PROB_TOLERANCE, f"partido {num}: probabilidades suman {total:.6f}, no 1")
    # Normalización leve para evitar arrastrar redondeos en la API pública.
    return {sign: round(probs[sign] / total, 6) for sign in SIGNS}


def _validate_recommendation(raw: Any, *, num: int) -> dict[str, Any]:
    _require(isinstance(raw, dict), f"partido {num}: recomendacion_modelo ausente o no es objeto")
    sign = raw.get("signo_principal")
    apuesta = raw.get("apuesta_recomendada")
    bet_type = raw.get("tipo_apuesta")
    confianza = raw.get("confianza_modelo")

    _require(sign in SIGNS, f"partido {num}: signo_principal inválido: {sign!r}")
    _require(isinstance(apuesta, str) and apuesta, f"partido {num}: apuesta_recomendada inválida")
    apuesta_signs = list(apuesta)
    _require(all(s in SIGNS for s in apuesta_signs), f"partido {num}: apuesta contiene signos inválidos: {apuesta!r}")
    _require(len(set(apuesta_signs)) == len(apuesta_signs), f"partido {num}: apuesta contiene signos duplicados: {apuesta!r}")
    _require(sign in apuesta_signs, f"partido {num}: apuesta {apuesta!r} no contiene signo principal {sign!r}")
    expected_type = BET_TYPE_BY_LEN.get(len(apuesta_signs))
    _require(bet_type == expected_type, f"partido {num}: tipo {bet_type!r} no coincide con apuesta {apuesta!r}")
    _require(_is_number(confianza), f"partido {num}: confianza no numérica")
    confianza = float(confianza)
    _require(0.0 <= confianza <= 1.0, f"partido {num}: confianza fuera de [0,1]")

    return {
        "signo_maestro": sign,
        "apuesta": apuesta,
        "tipo": bet_type,
        "confianza": round(confianza, 6),
    }


def _source_metadata(partido: dict[str, Any]) -> tuple[str | None, bool, str | None, list[str]]:
    probs = partido.get("probabilidades") or {}
    fuente = probs.get("fuente_principal") or (partido.get("fuente_probabilidades") or {}).get("modelo_primario")
    mm = partido.get("modelo_maestro") or {}
    calidad_raw = mm.get("calidad") or mm.get("calidad_datos") or partido.get("calidad")
    calidad = str(calidad_raw) if calidad_raw is not None else None
    avisos = partido.get("avisos") or mm.get("avisos") or []
    if isinstance(avisos, str):
        avisos = [avisos]
    elif not isinstance(avisos, list):
        avisos = []
    comparativa = probs.get("comparativa") if isinstance(probs, dict) else None
    cuotas_disponibles = bool((mm.get("features_usadas") or {}).get("cuotas_disponibles"))
    if isinstance(comparativa, dict) and any(comparativa.get(k) for k in ("cuotas", "market", "mercado")):
        cuotas_disponibles = True
    return fuente, cuotas_disponibles, calidad, [str(a) for a in avisos]


def _build_match_contract(partido: dict[str, Any]) -> dict[str, Any]:
    num = int(partido.get("num"))
    probs = _validate_probability_block((partido.get("probabilidades") or {}).get("modelo"), num=num)
    recommendation = _validate_recommendation(partido.get("recomendacion_modelo"), num=num)
    fuente, cuotas_disponibles, calidad, avisos = _source_metadata(partido)
    return {
        "numero": num,
        "local": partido.get("local"),
        "visitante": partido.get("visitante"),
        "probabilidades": probs,
        "fuente": fuente,
        "cuotas_disponibles": cuotas_disponibles,
        "calidad": calidad,
        "avisos": avisos,
        **recommendation,
    }


def _build_pleno_contract(partido: dict[str, Any], paquete: dict[str, Any]) -> dict[str, Any]:
    mm = partido.get("modelo_maestro") or {}
    if mm.get("disponible") is True:
        sel = mm.get("seleccion") or {}
        local_bucket = sel.get("local")
        away_bucket = sel.get("visitante")
        _require(local_bucket in BUCKETS_PLENO, f"pleno15: bucket local inválido: {local_bucket!r}")
        _require(away_bucket in BUCKETS_PLENO, f"pleno15: bucket visitante inválido: {away_bucket!r}")
        marcador = mm.get("marcador_predicho") or sel.get("marcador")
        _require(isinstance(marcador, str) and marcador, "pleno15: marcador_predicho ausente")
        return {
            "disponible": True,
            "local": partido.get("local"),
            "visitante": partido.get("visitante"),
            "marcador": marcador,
            "pronostico_local": local_bucket,
            "pronostico_visitante": away_bucket,
            "calidad": mm.get("calidad"),
            "avisos": mm.get("avisos") or [],
            "motivo": None,
        }

    motivo = mm.get("razon") or mm.get("motivo") or "modelo_pleno15_no_disponible"
    return {
        "disponible": False,
        "local": partido.get("local"),
        "visitante": partido.get("visitante"),
        "marcador": None,
        "pronostico_local": None,
        "pronostico_visitante": None,
        "calidad": mm.get("calidad"),
        "avisos": mm.get("avisos") or [],
        "motivo": motivo,
    }


def validate_package_structure(data: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    partidos = data.get("partidos")
    _require(isinstance(partidos, list), "paquete: partidos debe ser una lista")
    nums = [p.get("num") for p in partidos if isinstance(p, dict)]
    _require(len(nums) == len(partidos), "paquete: todos los partidos deben ser objetos con num")
    _require(len(set(nums)) == len(nums), f"paquete: números de partido duplicados: {nums}")
    normal = [p for p in partidos if p.get("num") != 15]
    pleno = [p for p in partidos if p.get("num") == 15]
    _require(len(normal) == 14, f"paquete: se esperaban 14 partidos normales, hay {len(normal)}")
    _require(len(pleno) == 1, f"paquete: se esperaba exactamente 1 partido 15, hay {len(pleno)}")
    _require(sorted(p.get("num") for p in normal) == list(range(1, 15)), "paquete: deben existir partidos 1..14")
    return normal, pleno[0]


def build_api_contract(data: dict[str, Any], jornada: int) -> dict[str, Any]:
    normal, pleno = validate_package_structure(data)
    api_out = {
        "jornada": jornada,
        "fecha_generacion": data.get("fecha_generacion"),
        "modelo_version": data.get("modelo_info", {}).get("version", "unknown"),
        "partidos": [_build_match_contract(p) for p in sorted(normal, key=lambda item: item["num"])],
        "pleno15": _build_pleno_contract(pleno, data),
    }
    validate_api_contract(api_out)
    return api_out


def validate_api_contract(contract: dict[str, Any]) -> None:
    partidos = contract.get("partidos")
    _require(isinstance(partidos, list) and len(partidos) == 14, "contrato: partidos debe contener 14 objetos")
    nums = [p.get("numero") for p in partidos]
    _require(nums == list(range(1, 15)), f"contrato: números esperados 1..14, recibido {nums}")
    for p in partidos:
        _validate_probability_block(p.get("probabilidades"), num=int(p["numero"]))
        _validate_recommendation(
            {
                "signo_principal": p.get("signo_maestro"),
                "apuesta_recomendada": p.get("apuesta"),
                "tipo_apuesta": p.get("tipo"),
                "confianza_modelo": p.get("confianza"),
            },
            num=int(p["numero"]),
        )
    pleno = contract.get("pleno15")
    _require(isinstance(pleno, dict), "contrato: pleno15 debe ser objeto")
    _require(isinstance(pleno.get("disponible"), bool), "contrato: pleno15.disponible debe ser bool")
    if pleno["disponible"]:
        _require(pleno.get("pronostico_local") in BUCKETS_PLENO, "contrato: pleno15 pronostico_local inválido")
        _require(pleno.get("pronostico_visitante") in BUCKETS_PLENO, "contrato: pleno15 pronostico_visitante inválido")
        _require(isinstance(pleno.get("marcador"), str) and pleno.get("marcador"), "contrato: pleno15 marcador ausente")
    else:
        _require(pleno.get("pronostico_local") is None, "contrato: pleno15 no disponible no debe tener pronostico_local")
        _require(pleno.get("pronostico_visitante") is None, "contrato: pleno15 no disponible no debe tener pronostico_visitante")
        _require(pleno.get("marcador") is None, "contrato: pleno15 no disponible no debe tener marcador")
        _require(isinstance(pleno.get("motivo"), str) and pleno.get("motivo"), "contrato: pleno15 no disponible requiere motivo")


def generate_api_contract(
    jornada: int,
    paquete_path: Path | None = None,
    out_path: Path | None = None,
) -> dict[str, Any]:
    paquete_path = paquete_path or Path(f"SALIDAS/paquete_jornada_J{jornada}.json")
    if not paquete_path.exists():
        raise FileNotFoundError(f"No se encuentra el paquete de la jornada {jornada}: {paquete_path}")

    try:
        data = json.loads(paquete_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractValidationError(f"JSON de entrada corrupto: {paquete_path}: {exc}") from exc

    api_out = build_api_contract(data, jornada)

    out_path = out_path or Path(f"SALIDAS/api_maestros_J{jornada}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(api_out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Contrato API generado: {out_path}")
    return api_out


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera contrato API validado para Liga de Maestros")
    parser.add_argument("--jornada", "-j", type=int, required=True)
    args = parser.parse_args()
    try:
        generate_api_contract(args.jornada)
    except (ContractValidationError, FileNotFoundError) as exc:
        raise SystemExit(f"Error generando contrato API: {exc}") from exc


if __name__ == "__main__":
    main()
