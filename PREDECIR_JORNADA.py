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
import unicodedata
from datetime import datetime

import settings
from MOTOR_DECISION_QUINIELISTICA import diagnose_jornada
from MOTOR_PREDICCION_JORNADA import (
    generate_jornada_prediction,
    load_jornada_json,
    save_predictions,
)


def load_priors():
    """Carga los priors de equipos desde el archivo de estadísticas base."""
    path = settings.DATOS_DIR / "temporada_2026_27_estadisticas_base.json"
    if not path.exists():
        return {}, ["No existe DATOS/temporada_2026_27_estadisticas_base.json"]
    data = json.loads(path.read_text(encoding="utf-8"))
    teams = data.get("teams", {})
    missing = data.get("missing_or_partial", [])
    warnings = []
    if missing:
        warnings.append(f"Equipos con muestra baja en priors 2026/27: {', '.join(missing)}")
    return teams, warnings


def normalize_name(value):
    """Normaliza el nombre de un equipo para comparación."""
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().replace(".", "").split())


def enrich_with_priors(partidos, priors):
    """Añade priors de equipos a los partidos."""
    by_name = {normalize_name(name): stats for name, stats in priors.items()}
    for match in partidos:
        for side in ("local", "visitante"):
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

        # Si es el pleno al 15, no le asignamos predicción 1X2 del modelo
        if num == 15:
            match["modelo_maestro"] = {
                "disponible": False,
                "razon": "pleno_15_solo_marcador",
            }
            continue

        if pred:
            # Punto 2 Codex: No presentar como fiable si la calidad es muy baja
            calidad = pred.get("calidad_datos", 0)
            es_fiable = calidad >= 0.2  # Umbral de fiabilidad

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
                        # Mantener APU/LAE/Q15 solo como información comparativa
                        "apu": match.pop("apu", None),
                        "lae": match.pop("lae", None),
                        "q15": match.pop("q15", None),
                    },
                    "fuente_principal": "motor_maestro_hibrido",
                    "nota": "probabilidades.modelo contiene las predicciones del modelo. probabilidades.comparativa contiene APU/LAE/Q15 solo como referencia.",
                }
            else:
                # Baja calidad: tratar como no disponible para recomendaciones
                match["modelo_maestro"]["razon"] = "baja_calidad_datos"
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
    # Intentar obtener probabilidades del modelo del nuevo contrato
    probs_modelo = match.get("probabilidades", {}).get("modelo")
    fuente = "motor_maestro"

    if not probs_modelo:
        # Fallback: usar probabilidades comparativas (APU)
        comparativa = match.get("probabilidades", {}).get("comparativa", {})
        apu = comparativa.get("apu") or {}
        if apu:
            total = sum(apu.values())
            probs = {
                "1": apu.get("1", 0) / total if total > 0 else 0.333,
                "X": apu.get("X", 0) / total if total > 0 else 0.333,
                "2": apu.get("2", 0) / total if total > 0 else 0.333,
            }
            fuente = "apu_fallback"
        else:
            # Punto 2 Codex (Rev 3): Si no hay fuente fiable, marcar recomendación no disponible
            return {
                "disponible": False,
                "razon": "sin_fuente_de_probabilidades_fiable",
                "nota": "No se pudo generar recomendación (sin modelo ni APU)",
            }
    else:
        probs = probs_modelo

    p1 = probs.get("1", 0.333)
    px = probs.get("X", 0.333)
    p2 = probs.get("2", 0.333)

    # Ordenar probabilidades
    sorted_probs = sorted(
        [("1", p1), ("X", px), ("2", p2)],
        key=lambda x: x[1],
        reverse=True,
    )

    signo_principal = sorted_probs[0][0]
    modelo_maestro = match.get("modelo_maestro", {})
    confianza = modelo_maestro.get("confianza", 0.5) if isinstance(modelo_maestro, dict) else 0.5

    # Determinar tipo de apuesta
    gap_primero_segundo = sorted_probs[0][1] - sorted_probs[1][1]

    if confianza >= 0.7 and gap_primero_segundo >= 0.25:
        tipo_apuesta = "simple"
        signos = signo_principal
    elif confianza >= 0.5 and sorted_probs[1][1] >= 0.25:
        tipo_apuesta = "doble"
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


def build_package(jornada: int, use_model: bool = True) -> dict:
    """Construye el paquete completo para una jornada.

    Args:
        jornada: Número de jornada
        use_model: Si True, intenta usar el modelo maestro para predicciones

    Returns:
        Paquete JSON con toda la información de la jornada
    """
    # 1. Obtener diagnóstico quinielístico (con APU/LAE/Q15)
    diagnostic = diagnose_jornada(jornada)

    # 2. Cargar priors de equipos
    priors, global_warnings = load_priors()

    # 3. Obtener predicciones del modelo maestro
    model_predictions = {}
    model_errors = []

    if use_model:
        try:
            model_predictions = generate_jornada_prediction(jornada)
            if "error" in model_predictions:
                model_errors.append(model_predictions["error"])
                model_predictions = {}
        except Exception as e:
            model_errors.append(f"Error generando predicciones del modelo: {str(e)}")
            model_predictions = {}

    # 4. Combinar datos
    partidos = diagnostic.get("partidos", [])

    # Enriquecer con priors
    partidos = enrich_with_priors(partidos, priors)

    # Integrar predicciones del modelo
    if model_predictions.get("predicciones"):
        partidos = _integrate_model_predictions(partidos, model_predictions)
    elif model_errors:
        # Marcar error global pero intentar con datos disponibles
        for match in partidos:
            if match.get("num") != 15:
                match["modelo_maestro"] = {
                    "disponible": False,
                    "razon": "error_modelo",
                    "error": model_errors[0] if model_errors else "Desconocido",
                }

    # 5. Añadir recomendaciones basadas en modelo
    for match in partidos:
        if match.get("num") != 15:
            match["recomendacion_modelo"] = build_recommendation_for_match(match)

    # 6. Generar avisos de priors
    match_warnings = prior_warnings_for_matches(partidos)

    # 7. Extraer Pleno al 15
    pleno = next((p for p in partidos if p.get("num") == 15), None)
    pleno_data = pleno.get("pleno15") if pleno else None

    # 7.5 Boleto optimizado (T2): desarrollo global con presupuesto y valor.
    #     Usa las probabilidades del modelo cuando existen; si no, Q15 como
    #     fuente de probabilidades y LAE como popularidad del público.
    boleto_optimizado = None
    try:
        from OPTIMIZADOR_COLUMNAS import optimize_jornada

        probs_override = {}
        for match in partidos:
            pm = match.get("probabilidades", {}).get("modelo")
            if isinstance(pm, dict) and all(s in pm for s in ("1", "X", "2")):
                probs_override[match.get("num")] = pm
        budget = int(settings.CONFIG.get("columns", {}).get("default_budget", 128))
        boleto_optimizado = optimize_jornada(
            jornada,
            fuente_prob="q15",
            publico="lae",
            presupuesto=budget,
            probs_override=probs_override or None,
        )
    except Exception as exc:
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
    }

    package = {
        "jornada": jornada,
        "fecha_generacion": datetime.now().isoformat(timespec="seconds"),
        "version_config": settings.CONFIG.get("version", "desconocida"),
        "estado": "paquete_jornada_v3_modelo",
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
            "nota": "La v3 integra el motor maestro para probabilidades principales. APU/LAE/Q15 se mantienen como referencia comparativa. El boleto optimizado se construye con OPTIMIZADOR_COLUMNAS (T2).",
            "cambios": [
                "probabilidades.modelo ahora contiene predicciones del motor maestro",
                "probabilidades.comparativa contiene APU/LAE/Q15 para referencia",
                "recomendacion_modelo genera signos/dobles basados en el modelo",
                "modelo_maestro contiene metadata de calidad y features",
                "boleto_optimizado contiene desarrollo global, coste, distribución de aciertos y Monte Carlo",
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

    return package


def main():
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
    args = parser.parse_args()

    settings.SALIDAS_DIR.mkdir(parents=True, exist_ok=True)

    # Generar paquete
    package = build_package(args.jornada, use_model=not args.no_model)

    # Guardar paquete principal
    out_path = settings.SALIDAS_DIR / f"paquete_jornada_J{args.jornada}.json"
    out_path.write_text(
        json.dumps(package, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Guardar predicciones del modelo si se solicita
    if args.save_predictions:
        try:
            from MOTOR_PREDICCION_JORNADA import generate_jornada_prediction, save_predictions
            preds = generate_jornada_prediction(args.jornada)
            save_predictions(preds, args.jornada)
            print(f"Predicciones del modelo guardadas.")
        except Exception as e:
            print(f"Nota: No se pudieron guardar predicciones: {e}")

    print(f"OK -> {out_path}")
    print(json.dumps({
        "jornada": args.jornada,
        "partidos": len(package["partidos"]),
        "modelo_disponible": package["modelo_info"].get("disponible", False),
        "partidos_con_modelo": package["resumen_modelo"]["partidos_con_prediccion"],
        "avisos_partido": len(package["avisos"]["partidos"]),
        "estado": package["estado"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
