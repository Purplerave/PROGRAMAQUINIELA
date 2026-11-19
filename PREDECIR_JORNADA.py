"""Genera paquete consolidado para una jornada.

Este script conecta PREDECIR_JORNADA con MOTOR_QUINIELA_MAESTRO para obtener
probabilidades reales del modelo entrenado, manteniendo APU/LAE/Q15 como
información comparativa.

Flujo:
1. Carga datos de la jornada desde DATOS/QUINIELA15_J{jornada}.json
2. Obtiene predicciones del modelo maestro
3. Añade priors de equipos
4. Genera recomendaciones finales
5. Guarda en SALIDAS/paquete_jornada_J{jornada}.json
"""

import argparse
import json
import logging
import unicodedata
from datetime import datetime

import settings
from MOTOR_DECISION_QUINIELISTICA import diagnose_jornada
from MOTOR_PREDICCION_JORNADA import (
    _calculate_confidence,
    generate_jornada_prediction,
    get_cutoff_date,
    save_predictions,
)


from scripts.json_output import write_json
from scripts.motor.boletos import load_jornada_json, select_probabilities
from scripts.motor.features import infer_season
from scripts.motor.odds_at_cutoff import kickoff_at, odds_at_cutoff
from scripts.motor.temporal import local_timestamp, utc_timestamp
from scripts.motor.transition_priors import load_transition_priors


def normalize_name(value):
    """Normaliza el nombre de un equipo para comparación."""
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().replace(".", "").split())


def enrich_with_priors(partidos, priors):
    """Añade priors de equipos a los partidos.

    Acepta nombres comunes de jornada ("Castellón", "Malaga CF") traduciéndolos
    al nombre canónico del fichero de priors ("CD Castellon", "Malaga CF")
    mediante scripts/motor/team_names.
    """
    from scripts.motor.team_names import resolve_prior_name

    by_name = {normalize_name(name): stats for name, stats in priors.items()}
    for match in partidos:
        for side in ("local", "visitante"):
            canonical = resolve_prior_name(match.get(side))
            prior = priors.get(canonical) if canonical else None
            if prior is None:
                prior = by_name.get(normalize_name(match.get(side)))
            if not prior:
                continue
            context = prior.get("context", {})
            match[f"prior_{side}"] = {
                "adjusted_ppg": context.get("adjusted_ppg"),
                "confidence": context.get("confidence"),
                "transition": context.get("transition"),
                "note": context.get("note"),
            }
    return partidos


def prior_warnings_for_matches(partidos):
    """Genera avisos de calidad de priors por partido."""
    warnings = []
    for match in partidos:
        for side in ("local", "visitante"):
            prior = match.get(f"prior_{side}")
            if not prior:
                continue
            confidence = prior.get("confidence")
            transition = prior.get("transition")
            if confidence in {"baja", "muy_baja"} or transition != "misma_categoria":
                warnings.append(
                    {
                        "equipo": match.get(side),
                        "partido": match.get("num"),
                        "confidence": confidence,
                        "transition": transition,
                        "adjusted_ppg": prior.get("adjusted_ppg"),
                    }
                )
    return warnings


def _integrate_model_predictions(partidos: list[dict], model_predictions: dict) -> list[dict]:
    """Integra las predicciones del modelo con los partidos.

    Reemplaza las probabilidades del modelo con las del motor maestro
    mientras mantiene APU/LAE/Q15 como información comparativa.
    """
    # Indexar predicciones por número de partido
    pred_by_num = {}
    for pred in model_predictions.get("predicciones", []):
        pred_by_num[pred.get("numero")] = pred

    for match in partidos:
        num = match.get("num")
        pred = pred_by_num.get(num)

        # El partido 15 es el Pleno al 15: no recibe predicción 1X2; recibe
        # la predicción de marcador (buckets 0/1/2/M) del modelo Dixon-Coles.
        if num == 15:
            pleno_pred = model_predictions.get("pleno15")
            if pleno_pred and pleno_pred.get("disponible"):
                match["modelo_maestro"] = {
                    "disponible": True,
                    "tipo": "pleno_15_marcador",
                    "modelo": pleno_pred.get("modelo"),
                    "rho": pleno_pred.get("rho"),
                    "lambdas": pleno_pred.get("lambdas"),
                    "lambdas_fuente": pleno_pred.get("lambdas_fuente"),
                    "marcador_predicho": pleno_pred.get("marcador_predicho"),
                    "marcador_confianza": pleno_pred.get("marcador_confianza"),
                    "top_marcadores": pleno_pred.get("top_marcadores"),
                    "goles_local": pleno_pred.get("goles_local"),
                    "goles_visitante": pleno_pred.get("goles_visitante"),
                    "goles_conjuntos": pleno_pred.get("goles_conjuntos"),
                    "seleccion": pleno_pred.get("seleccion"),
                    "avisos": pleno_pred.get("avisos", []),
                    "calidad_datos": pleno_pred.get("calidad_datos"),
                    "fuente": pleno_pred.get("fuente_probabilidades"),
                    "comparativa_marcadores_q15": pleno_pred.get("comparativa_marcadores_q15", []),
                }
            elif pleno_pred:
                # Predicción generada pero de baja fiabilidad: se conserva el
                # detalle claramente marcado, nunca como fuente principal.
                match["modelo_maestro"] = {
                    "disponible": False,
                    "tipo": "pleno_15_marcador",
                    "razon": pleno_pred.get("razon") or "baja_calidad_datos",
                    "modelo": pleno_pred.get("modelo"),
                    "lambdas_fuente": pleno_pred.get("lambdas_fuente"),
                    "calidad_datos": pleno_pred.get("calidad_datos"),
                    "avisos": pleno_pred.get("avisos", []),
                    "detalle_baja_fiabilidad": {
                        "marcador_predicho": pleno_pred.get("marcador_predicho"),
                        "top_marcadores": pleno_pred.get("top_marcadores"),
                        "goles_local": pleno_pred.get("goles_local"),
                        "goles_visitante": pleno_pred.get("goles_visitante"),
                        "seleccion": pleno_pred.get("seleccion"),
                        "lambdas": pleno_pred.get("lambdas"),
                    },
                }
            else:
                match["modelo_maestro"] = {
                    "disponible": False,
                    "tipo": "pleno_15_marcador",
                    "razon": "pleno15_sin_prediccion_modelo",
                }
            continue

        if pred:
            # Punto 2 Codex: No presentar como fiable si la calidad es muy baja
            calidad = pred.get("calidad_datos", 0)
            umbral_calidad = settings.config_section("decision_thresholds").get("calidad_min", 0.2)
            es_fiable = pred.get("dominio_validado", True) and calidad >= umbral_calidad

            # Reemplazar probabilities.modelo con las del motor maestro
            match["modelo_maestro"] = {
                "disponible": es_fiable,
                "prob_1": pred.get("prob_1"),
                "prob_x": pred.get("prob_x"),
                "prob_2": pred.get("prob_2"),
                "signo_predicho": pred.get("signo_modelo"),
                "confianza": pred.get("confianza"),
                "fuente": pred.get("fuente_probabilidades"),
                "avisos": pred.get("avisos", []),
                "calidad_datos": calidad,
                "features": pred.get("features_disponibles"),
            }

            if es_fiable:
                # Indicar claramente que las probabilidades usadas son del modelo
                match["probabilidades"] = {
                    "modelo": {
                        "1": pred.get("prob_1"),
                        "X": pred.get("prob_x"),
                        "2": pred.get("prob_2"),
                    },
                    "comparativa": {
                        # Mantener APU/LAE/Q15/HL solo como información comparativa
                        "apu": match.pop("apu", None),
                        "lae": match.pop("lae", None),
                        "q15": match.pop("q15", None),
                        "hl": match.pop("hl", None),
                        "hl_generated_at": match.pop("hl_generated_at", None),
                        "pizarra": match.pop("pizarra", None),
                    },
                    "fuente_principal": "motor_maestro_hibrido",
                    "nota": "probabilidades.modelo contiene las predicciones del modelo. probabilidades.comparativa contiene APU/LAE/Q15 solo como referencia.",
                }
            else:
                # Baja calidad: tratar como no disponible para recomendaciones
                match["modelo_maestro"]["razon"] = (
                    "baja_calidad_datos" if pred.get("dominio_validado", True) else "fuera_del_dominio_validado"
                )
                match["probabilidades"] = {
                    "modelo": None,
                    "comparativa": {
                        "apu": match.pop("apu", None),
                        "lae": match.pop("lae", None),
                        "q15": match.pop("q15", None),
                    },
                    "fuente_principal": "fallback_apu_lae_q15",
                    "nota": "ATENCIÓN: Predicción del modelo con baja fiabilidad. Se usan APU/LAE como fallback.",
                    "aviso": f"Calidad de datos insuficiente ({calidad}). Revisar avisos.",
                }
        else:
            # No hay predicción del modelo para este partido
            match["modelo_maestro"] = {
                "disponible": False,
                "razon": "datos_insuficientes_o_error",
            }
            match["probabilidades"] = {
                "modelo": None,
                "comparativa": {
                    "apu": match.pop("apu", None),
                    "lae": match.pop("lae", None),
                    "q15": match.pop("q15", None),
                },
                "fuente_principal": "fallback_apu_lae_q15",
                "nota": "ATENCIÓN: No se pudieron obtener probabilidades del modelo. Se usan APU/LAE como fallback.",
                "aviso": "Las probabilidades pueden no ser óptimas. Revisar calidad de datos.",
            }

    return partidos


def build_recommendation_for_match(match: dict) -> dict:
    """Genera recomendación de signos y dobles basada en el modelo.

    Usa las probabilidades del motor maestro para determinar:
    - Signo principal
    - Doble (si aplica)
    - Triple (si aplica)
    - Nivel de confianza
    """
    probs, fuente = select_probabilities(match)
    if probs is None:
        return {
            "disponible": False,
            "razon": "sin_fuente_de_probabilidades_fiable",
            "nota": "No se pudo generar recomendación: faltan probabilidades válidas",
        }
    p1, px, p2 = (probs[s] for s in ("1", "X", "2"))

    # Ordenar probabilidades
    sorted_probs = sorted(
        [("1", p1), ("X", px), ("2", p2)],
        key=lambda x: x[1],
        reverse=True,
    )

    signo_principal = sorted_probs[0][0]
    modelo_maestro = match.get("modelo_maestro", {})
    confianza = modelo_maestro.get("confianza", _calculate_confidence(probs)) if fuente == "motor_maestro" else _calculate_confidence(probs)

    # Determinar tipo de apuesta
    gap_primero_segundo = sorted_probs[0][1] - sorted_probs[1][1]

    thresholds = settings.config_section("decision_thresholds")
    umbral_conf = thresholds.get("confianza_min", 0.7)
    umbral_gap = thresholds.get("gap_min", 0.25)
    umbral_doble = thresholds.get("double_sorted_prob_min", 0.25)
    p_top = sorted_probs[0][1]
    # Issue #36: un favorito 1@0.891 (gap 0.82, conf 0.62 por entropía)
    # caía a "triple" porque la confianza de entropía nunca llega a 0.7
    # y la 2ª prob (<0.25) bloqueaba el doble. Un triple en un 89% es
    # absurdo: si el gap es amplio y p_top >= 0.60 con confianza mínima
    # de doble (>=0.5), es fijo. Se exige confianza >=0.5 para no regalar
    # simples cuando el propio modelo duda (conf baja => triple/doble).
    es_fijo_por_cuota = (
        p_top >= 0.60
        and gap_primero_segundo >= umbral_gap
        and confianza >= 0.5
    )
    if (confianza >= umbral_conf and gap_primero_segundo >= umbral_gap) or es_fijo_por_cuota:
        tipo_apuesta = "simple"
        signos = signo_principal
    elif confianza >= 0.5 and sorted_probs[1][1] >= umbral_doble:
        tipo_apuesta = "doble"
        from scripts.motor.cobertura_bandas import signo_doble_banda

        forced = signo_doble_banda(
            match.get("open_odd_1") or match.get("odd_1"),
            match.get("open_odd_2") or match.get("odd_2"),
            probs=(p1, px, p2),
        )
        if forced and signo_principal in forced and settings.config_section("cobertura_dobles_banda").get("enabled", True):
            signos = forced
        else:
            segundo = sorted_probs[1][0]
            signos = "".join(sorted([signo_principal, segundo], key=["1", "X", "2"].index))
    else:
        tipo_apuesta = "triple"
        signos = "1X2"

    return {
        "disponible": True,
        "signo_principal": signo_principal,
        "apuesta_recomendada": signos,
        "tipo_apuesta": tipo_apuesta,
        "confianza_modelo": round(confianza, 3) if isinstance(confianza, float) else confianza,
        "gap_probabilidad": round(gap_primero_segundo, 3),
        "fuente_utilizada": fuente,
        "nota": f"Recomendación basada en {fuente}",
    }


def build_package(jornada: int, use_model: bool = True, cutoff: object = None) -> dict:
    return _build_package(jornada, use_model, cutoff)[0]


def _build_package(jornada: int, use_model: bool, cutoff: object) -> tuple[dict, dict]:
    """Construye el paquete completo para una jornada.

    Args:
        jornada: Número de jornada
        use_model: Si True, intenta usar el modelo maestro para predicciones

    Returns:
        Paquete JSON con toda la información de la jornada
    """
    # 1. Obtener diagnóstico quinielístico (con APU/LAE/Q15)
    data = load_jornada_json(jornada)
    diagnostic = diagnose_jornada(jornada, jornada_data=data)

    partidos = diagnostic.get("partidos", [])
    model_predictions = {}
    model_errors = []
    global_warnings = []
    try:
        resolved_cutoff = get_cutoff_date(data, cutoff)
    except ValueError as exc:
        if cutoff is not None:
            raise
        resolved_cutoff = None
        global_warnings.append(str(exc))
        if use_model:
            model_errors.append(str(exc))

    if resolved_cutoff is not None:
        season, priors, prior_warnings = load_transition_priors(resolved_cutoff)
        raw_by_position = {p["num"]: p for p in data["partidos"]}
        enrich_with_priors([
            p for p in partidos
            if infer_season(local_timestamp(kickoff_at(raw_by_position[p["num"]]) or resolved_cutoff)) == season
        ], priors)
        global_warnings.extend(prior_warnings)
        if use_model:
            try:
                model_predictions = generate_jornada_prediction(jornada, resolved_cutoff, jornada_data=data)
                if "error" in model_predictions:
                    model_errors.append(model_predictions["error"])
            except (OSError, ValueError) as exc:
                model_errors.append(f"Error generando predicciones del modelo: {exc}")

    _integrate_model_predictions(partidos, model_predictions)
    if model_errors:
        for match in partidos:
            if match["num"] != 15 and not match["modelo_maestro"].get("disponible"):
                match["modelo_maestro"].update(razon="error_modelo", error=model_errors[0])

    # 5. Añadir recomendaciones basadas en modelo
    for match in partidos:
        if match["num"] != 15:
            odds = odds_at_cutoff(raw_by_position[match["num"]], resolved_cutoff)[0] if resolved_cutoff is not None else {}
            match["recomendacion_modelo"] = build_recommendation_for_match({**match, **odds})

    # 6. Generar avisos de priors
    match_warnings = prior_warnings_for_matches(partidos)

    # 7. Extraer Pleno al 15 (diagnóstico Q15 como comparativa + modelo DC)
    pleno = next((p for p in partidos if p.get("num") == 15), None)
    pleno_data = None
    if pleno:
        pleno_data = {
            "nota": "El Pleno al 15 separa signo 1X2 de marcador por buckets 0/1/2/M.",
            "modelo_maestro": pleno.get("modelo_maestro"),
            "diagnostico_q15": pleno.get("pleno15"),
            "fuente_principal": (
                "motor_maestro_pleno15"
                if (pleno.get("modelo_maestro") or {}).get("disponible")
                else "fallback_marcadores_q15"
            ),
        }

    # 7.5 Boleto optimizado (T2): contrato fijo de columnas (P0 2026-08-04):
    #     3 dobles = 8 columnas a 0,75 EUR = 6,00 EUR máximo, Pleno al 15 aparte.
    #     Usa la misma distribución por partido que la recomendación y la API.
    #     La popularidad LAE solo sirve para ordenar las columnas elegidas.
    boleto_optimizado = None
    try:
        from OPTIMIZADOR_COLUMNAS import optimize_jornada

        probs_override, probability_sources = {}, {}
        for match in partidos:
            if match["num"] == 15:
                continue
            num = match["num"]
            probs, source = select_probabilities(match)
            probs_override[num] = probs
            probability_sources[str(num)] = source
        # Extraer modelo_maestro del Pleno 15 para pasarlo al optimizador
        pleno_match = next((p for p in partidos if p.get("num") == 15), None)
        pleno_mm = None
        if pleno_match:
            mm = pleno_match.get("modelo_maestro")
            if isinstance(mm, dict) and mm.get("disponible"):
                pleno_mm = mm

        boleto_optimizado = optimize_jornada(
            jornada,
            fuente_prob="paquete",
            publico="lae",
            probs_override=probs_override,
            pleno_modelo=pleno_mm,
            cutoff_date=resolved_cutoff,
            jornada_data=data,
        )
        boleto_optimizado["fuentes_probabilidades_por_casilla"] = probability_sources
    except Exception as exc:
        logging.error("PREDECIR_JORNADA: %s", exc, exc_info=True)
        boleto_optimizado = {"error": f"no_disponible: {exc}"}

    # 8. Construir paquete final
    resumen = {
        "partidos_con_prediccion": len([p for p in partidos if p.get("num") != 15 and p.get("modelo_maestro", {}).get("disponible") is True]),
        "partidos_sin_prediccion": len([p for p in partidos if p.get("num") != 15 and p.get("modelo_maestro", {}).get("disponible") is not True]),
        "partidos_con_recomendacion": len([p for p in partidos if p.get("num") != 15 and p.get("recomendacion_modelo", {}).get("disponible") is True]),
        "partidos_sin_recomendacion": len([p for p in partidos if p.get("num") != 15 and p.get("recomendacion_modelo", {}).get("disponible") is False]),
        "partidos_sin_dobles": len([p for p in partidos if p.get("num") != 15 and p.get("recomendacion_modelo", {}).get("disponible") is True and p.get("recomendacion_modelo", {}).get("tipo_apuesta") == "simple"]),
        "partidos_con_dobles": len([p for p in partidos if p.get("num") != 15 and p.get("recomendacion_modelo", {}).get("disponible") is True and p.get("recomendacion_modelo", {}).get("tipo_apuesta") == "doble"]),
        "partidos_con_triple": len([p for p in partidos if p.get("num") != 15 and p.get("recomendacion_modelo", {}).get("disponible") is True and p.get("recomendacion_modelo", {}).get("tipo_apuesta") == "triple"]),
        "confianza_media": round(
            sum(
                p.get("modelo_maestro", {}).get("confianza", 0)
                for p in partidos
                if p.get("num") != 15 and p.get("modelo_maestro", {}).get("disponible") is True
            ) / max(1, len([p for p in partidos if p.get("num") != 15 and p.get("modelo_maestro", {}).get("disponible") is True])),
            3,
        ),
        "pleno15_modelo_disponible": any(
            p.get("num") == 15 and p.get("modelo_maestro", {}).get("disponible") is True
            for p in partidos
        ),
    }

    package = {
        "jornada": jornada,
        "fecha_generacion": datetime.now().isoformat(timespec="seconds"),
        "version_config": settings.CONFIG.get("version", "desconocida"),
        "prediction_cutoff_at": utc_timestamp(resolved_cutoff).isoformat() if resolved_cutoff is not None else None,
        "estado": "paquete_jornada_v3_modelo",
        "trazabilidad_cuotas": model_predictions.get("trazabilidad_cuotas"),
        "modelo_info": {
            **model_predictions.get("modelo_info", {}),
            "disponible": resumen["partidos_con_prediccion"] > 0,
            "errores": model_errors,
        },
        "partidos": partidos,
        "pleno15": pleno_data,
        "boleto_optimizado": boleto_optimizado,
        "resumen_modelo": resumen,
        "columnas": {
            "estado": "v3_modelo_integrado",
            "nota": "La v3 integra el motor maestro para probabilidades principales. APU/LAE/Q15 se mantienen como referencia comparativa. El boleto optimizado se construye con OPTIMIZADOR_COLUMNAS (T2). El Pleno al 15 lo predice el modelo Dixon-Coles (T4).",
            "cambios": [
                "probabilidades.modelo ahora contiene predicciones del motor maestro",
                "probabilidades.comparativa contiene APU/LAE/Q15 para referencia",
                "recomendacion_modelo genera signos/dobles basados en el modelo",
                "modelo_maestro contiene metadata de calidad y features",
                "boleto_optimizado contiene desarrollo global, coste, distribución de aciertos y Monte Carlo",
                "pleno15.modelo_maestro contiene buckets 0/1/2/M, top marcadores y selección Dixon-Coles",
            ],
        },
        "avisos": {
            "globales": global_warnings,
            "partidos": match_warnings,
            "modelo": model_errors,
        },
        "fuentes": {
            "diagnostico": f"SALIDAS/diagnostico_quinielistico_J{jornada}.json",
            "jornada": f"DATOS/QUINIELA15_J{jornada}.json",
            "priors": "DATOS/temporada_2026_27_estadisticas_base.json",
            "modelo": model_predictions.get("modelo_info", {}).get("version", "no_disponible"),
        },
    }

    return package, model_predictions


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Genera paquete consolidado para una jornada con predicciones del modelo."
    )
    parser.add_argument("--jornada", "-j", type=int, required=True)
    parser.add_argument(
        "--no-model",
        action="store_true",
        help="No usar el modelo maestro (solo diagnóstico básico)",
    )
    parser.add_argument(
        "--save-predictions",
        action="store_true",
        help="Guardar predicciones del modelo en SALIDAS/predicciones_modelo_J{jornada}.json",
    )
    parser.add_argument("--corte", help="fecha/hora ISO documentada del corte")
    args = parser.parse_args()
    if args.no_model and args.save_predictions:
        parser.error("--no-model y --save-predictions no se pueden combinar")
    try:
        package, predictions = _build_package(args.jornada, not args.no_model, args.corte)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    # Guardar paquete principal
    out_path = settings.SALIDAS_DIR / f"paquete_jornada_J{args.jornada}.json"
    write_json(out_path, package)
    if args.save_predictions and predictions.get("predicciones"):
        save_predictions(predictions, args.jornada)
        print("Predicciones del modelo guardadas.")

    from scripts.motor.GENERAR_CONTRATO_API import generate_api_contract

    contract_ok = generate_api_contract(args.jornada) is not None
    if not contract_ok:
        print(f"Paquete local guardado, pero sin contrato publicable: {out_path}")
    if package["boleto_optimizado"].get("error"):
        print(f"Paquete local guardado, pero sin optimización: {package['boleto_optimizado']['error']}")
    if package["modelo_info"]["errores"]:
        print("Motor no disponible; los proxies no son pronósticos del modelo.")
    print(f"Paquete -> {out_path}")
    print(json.dumps({
        "jornada": args.jornada,
        "partidos": len(package["partidos"]),
        "modelo_disponible": package["modelo_info"].get("disponible", False),
        "partidos_con_modelo": package["resumen_modelo"]["partidos_con_prediccion"],
        "avisos_partido": len(package["avisos"]["partidos"]),
        "estado": package["estado"],
    }, ensure_ascii=False, indent=2))
    return int(not contract_ok or bool(package["boleto_optimizado"].get("error")) or bool(package["modelo_info"]["errores"]))


if __name__ == "__main__":
    raise SystemExit(main())
