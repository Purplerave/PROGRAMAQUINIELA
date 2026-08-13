"""GENERAR_BOLETO_J1.py — Mejor boleto (3 dobles) de la Jornada 1 de LaLiga 2026/27.

Flujo:
  1. Carga las probabilidades 1/X/2 que ya calculó el motor maestro para la J1
     (SALIDAS/paquete_jornada_J1.json, "probabilidades.modelo").
  2. Aplica ajustes documentados por PRETEMPORADA 2026 (lesiones, mercado de
     fichajes, dinámica de amistosos) sobre esas probabilidades. Son un
     override controlado y trazable: cada ajuste cita la fuente de noticias.
  3. Deja que OPTIMIZADOR_COLUMNAS elija los 3 dobles y el Pleno al 15 de forma
     óptima (E[aciertos] = máxima suma de 2ª probabilidad) bajo el contrato
     P0: 3 dobles = 8 columnas = 6,00 EUR, Pleno al 15 aparte.
  4. Emite:
       SALIDAS/quiniela_programa_J1.json     -> array "signos" de 15 (web)
       DATOS/PROBABILIDADES_J1.json          -> consenso 1/X/2 por partido (web)
       SALIDAS/opt_boleto_J1_pretemporada.json -> detalle completo del optimizador

  El array "signos" usa el ORDEN del propio QUINIELA15_J1.json del programa
  (partidos 1..14 y pleno 15). Cada signo es "1", "X", "2", "1X", "X2", "12".
  El Pleno al 15 se devuelve como signo 1/X/2 y, aparte, el marcador por
  buckets (0/1/2/M) y el marcador exacto predicho por Dixon-Coles.

  Ejecución:
      python GENERAR_BOLETO_J1.py
"""

from __future__ import annotations

import json
from pathlib import Path

import settings
from OPTIMIZADOR_COLUMNAS import optimize_jornada


ROOT = Path(__file__).resolve().parent
PAQUETE_PATH = settings.SALIDAS_DIR / "paquete_jornada_J1.json"
OUT_PROGRAMA = settings.SALIDAS_DIR / "quiniela_programa_J1.json"
OUT_PROBS = settings.DATOS_DIR / "PROBABILIDADES_J1.json"
OUT_OPT = settings.SALIDAS_DIR / "opt_boleto_J1_pretemporada.json"

# Ajustes de pretemporada sobre las probabilidades del modelo maestro (1/X/2).
# Cada entrada: {num_partido: {"1":..., "X":..., "2":..., "razon": "fuentes"}}.
# Los valores deben sumar 1; si no, se renormalizan.
PRETEMPORADA_OVERRIDE = {
    1: {  # Alavés - Getafe
        "1": 0.42, "X": 0.33, "2": 0.25,
        "razon": "Getafe pierde a Uche (rotura de rodilla, toda la temporada); "
                 "Alavés duda con Boyé (no entrena). Partido muy abierto, la X gana peso.",
    },
    2: {  # Sevilla - Rayo
        "1": 0.48, "X": 0.28, "2": 0.24,
        "razon": "Pretemporada mala del Rayo (4 amistosos, 3 derrotas, 9 goles "
                 "encajados) y sin laterales izquierdos (Pep Chavarría al Chelsea, "
                 "Nobel Mendy baja). Sevilla estable y sin sobresaltos.",
    },
    3: {  # R. Santander - Villarreal
        "1": 0.28, "X": 0.28, "2": 0.44,
        "razon": "Villarreal con plantilla completa y sin bajas (Mikautadze, "
                 "Ayoze, Pépé). Racing ascendido aún en construcción pese a Canales.",
    },
    4: {  # Espanyol - Levante
        "1": 0.45, "X": 0.32, "2": 0.23,
        "razon": "Espanyol sin sus dos delanteros: Javi Puado (lig. cruzado, "
                 "hasta nov-dic) y Kike García (bíceps). El gol local cae; sube la X.",
    },
    5: {  # Celta - Osasuna
        "1": 0.51, "X": 0.27, "2": 0.22,
        "razon": "Osasuna vendió a su estrella Víctor Muñoz al Liverpool (40 M€) "
                 "y apenas ha fichado; Ramis estrena proyecto debilitado. Celta más sólido.",
    },
    6: {  # Andorra - Ceuta
        "1": 0.46, "X": 0.30, "2": 0.24,
        "razon": "Ambos con mucha renovación. Andorra favorito en casa pero con "
                 "incertidumbre; la X no es descartable.",
    },
    7: {  # Cádiz - Celta Fortuna
        "1": 0.53, "X": 0.26, "2": 0.21,
        "razon": "Cádiz claramente superior ante el filial del Celta (plantilla corta).",
    },
    8: {  # Real Oviedo - Granada
        "1": 0.37, "X": 0.33, "2": 0.30,
        "razon": "Partido más abierto de la jornada: Oviedo con 12 fichajes y "
                 "varias bajas en la previa; Granada perdió a Boyé, Rebbach, Neva "
                 "y Ruiz. La X tiene casi tanto peso como el favorito.",
    },
    9: {  # Mallorca - Valladolid
        "1": 0.49, "X": 0.29, "2": 0.22,
        "razon": "Mallorca descendido con buen bloque de Primera, favorito claro en casa.",
    },
    10: {  # Eibar - Tenerife
        "1": 0.46, "X": 0.30, "2": 0.24,
        "razon": "Eibar moderado favorito en casa; Tenerife rearmado. Partido sin "
                 "señal fuerte de pretemporada.",
    },
    11: {  # Burgos - Córdoba
        "1": 0.43, "X": 0.30, "2": 0.27,
        "razon": "Muy igualado (Burgos 1 .43 / X .28 / 2 .28). Sin señales fuertes; "
                 "la X se mantiene relevante.",
    },
    12: {  # Girona - Leganés
        "1": 0.54, "X": 0.28, "2": 0.18,
        "razon": "Girona favorito por cuota (1.65) pero con renovación masiva "
                 "(salen Krejčí, Lemar, Blind, Witsel) y posibles salidas de Arnau "
                 "y Álex Moreno. Baja ligeramente el 1 frente al modelo.",
    },
    13: {  # Las Palmas - Albacete
        "1": 0.55, "X": 0.26, "2": 0.19,
        "razon": "Las Palmas fuerte en casa (cuota 1.62) ante Albacete rearmado. "
                 "Single 1 de los más seguros.",
    },
    14: {  # Sporting Gijon - Sabadell
        "1": 0.52, "X": 0.27, "2": 0.21,
        "razon": "Sporting claramente favorito (cuota 1.84) ante el recién "
                 "ascendido Sabadell, pese a la reconstrucción sportinguista.",
    },
}


def renormalize(probs: dict) -> dict:
    """Renormaliza a suma 1 (por si los ajustes no suman exactamente 1)."""
    total = sum(probs[s] for s in ("1", "X", "2"))
    if total <= 0:
        raise ValueError(f"Probabilidades no válidas: {probs}")
    return {s: probs[s] / total for s in ("1", "X", "2")}


def load_model_probs(paquete: dict) -> dict:
    """Extrae probabilidades.modelo por nº de partido del paquete del motor."""
    out = {}
    for p in paquete.get("partidos", []):
        if p.get("num") == 15:
            continue
        m = (p.get("probabilidades") or {}).get("modelo")
        if isinstance(m, dict) and all(s in m for s in ("1", "X", "2")):
            out[p["num"]] = {"1": m["1"], "X": m["X"], "2": m["2"]}
    return out


def build_probs_override(model_probs: dict) -> dict:
    """Mezcla: si hay ajuste de pretemporada para un partido lo usa; si no, el modelo."""
    override = {}
    for num, probs in model_probs.items():
        adj = PRETEMPORADA_OVERRIDE.get(num)
        if adj:
            probs = renormalize(adj)
        else:
            probs = renormalize(probs)
        override[num] = {s: round(float(probs[s]), 4) for s in ("1", "X", "2")}
    return override


def build_signos(desarrollo: list[dict], pleno: dict | None) -> list[str]:
    """Array de 15 signos en el orden del QUINIELA15_J1.json del programa.

    Los 14 primeros salen del desarrollo (3 dobles + 11 simples). El nº 15
    (Pleno) lleva el signo 1/X/2 del favorito; el marcador se documenta aparte.
    """
    signos: list[str] = []
    # desarrollo viene alineado con main_matches (números 1..14 en orden)
    for item in desarrollo:
        signos.append(item["label"])
    if pleno:
        signos.append(pleno.get("signo", "1"))
    else:
        signos.append("1")
    return signos


def build_probabilidades_j1(model_probs: dict, probs_override: dict) -> dict:
    """Estructura de consenso que lee el importador de la web:
    {str(num): {"num": num, "probabilidades": {"1": pct, "X": pct, "2": pct}}}."""
    out = {}
    for num, probs in probs_override.items():
        out[str(num)] = {
            "num": num,
            "probabilidades": {s: round(float(probs[s]) * 100, 1) for s in ("1", "X", "2")},
        }
    return out


def main() -> None:
    if not PAQUETE_PATH.exists():
        raise FileNotFoundError(
            f"No existe {PAQUETE_PATH}. Ejecuta antes: "
            "python PREDECIR_JORNADA.py --jornada 1"
        )
    paquete = json.loads(PAQUETE_PATH.read_text(encoding="utf-8"))
    model_probs = load_model_probs(paquete)
    probs_override = build_probs_override(model_probs)

    # Extraer modelo del Pleno 15 del paquete (Dixon-Coles) para el optimizador
    pleno_match = next(
        (p for p in paquete.get("partidos", []) if p.get("num") == 15), None
    )
    pleno_modelo = None
    if pleno_match:
        mm = pleno_match.get("modelo_maestro")
        if isinstance(mm, dict) and mm.get("disponible"):
            pleno_modelo = mm

    payload = optimize_jornada(
        1,
        fuente_prob="q15",
        publico="lae",
        probs_override=probs_override,
        pleno_modelo=pleno_modelo,
    )

    # Guardar detalle del optimizador con los ajustes aplicados
    payload["pretemporada_ajustes"] = {
        str(k): v for k, v in PRETEMPORADA_OVERRIDE.items()
    }
    OUT_OPT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    signos = build_signos(payload["desarrollo"], payload.get("pleno15"))
    programa_out = {
        "jornada": 1,
        "temporada": "2026-2027",
        "generado_en": paquete.get("fecha_generacion"),
        "version_config": paquete.get("version_config"),
        "nota": (
            "Mejor boleto J1 2026/27 con 3 dobles (contrato P0: 8 columnas, "
            "6,00 EUR) construido sobre las probabilidades del motor maestro y "
            "ajustado por pretemporada 2026 (lesiones, fichajes, amistosos). "
            "Ver GENERAR_BOLETO_J1.py para los ajustes y sus fuentes."
        ),
        "signos": signos,
        "pleno15": {
            "signo": (payload.get("pleno15") or {}).get("signo"),
            "marcador_predicho": (payload.get("pleno15") or {}).get("marcador_predicho"),
            "top_marcadores": (payload.get("pleno15") or {}).get("top_marcadores"),
            "goles_local": (payload.get("pleno15") or {}).get("goles_local"),
            "goles_visitante": (payload.get("pleno15") or {}).get("goles_visitante"),
            "seleccion": (payload.get("pleno15") or {}).get("seleccion"),
            "buckets": ["0", "1", "2", "M"],
        },
        "contrato": payload.get("contrato"),
        "aciertos_esperados": payload.get("aciertos_esperados"),
        "probabilidades_exactas": payload.get("probabilidades_exactas"),
    }

    settings.SALIDAS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PROGRAMA.write_text(
        json.dumps(programa_out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    OUT_PROBS.write_text(
        json.dumps(
            build_probabilidades_j1(model_probs, probs_override),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # --- Consola ---
    main_matches = [p for p in paquete.get("partidos", []) if p.get("num") != 15]
    print("=" * 80)
    print("MEJOR BOLETO J1 2026/27 — 3 dobles (contrato P0, 8 columnas = 6,00 €)")
    print("=" * 80)
    for item, match in zip(payload["desarrollo"], main_matches):
        local = match["local"]
        visit = match["visitante"]
        row = "".join("X" if s in item["signos"] else "." for s in ("1", "X", "2"))
        print(
            f"  {item['num']:>2}  {local:<20} vs {visit:<20} "
            f"[{row}]  ({item['label']})"
        )
    p15 = payload.get("pleno15") or {}
    print("-" * 80)
    print(
        f"  Pleno al 15 (Deportivo-Elche): signo {p15.get('signo')} | "
        f"marcador predicho {p15.get('marcador_predicho')}"
    )
    if p15.get("top_marcadores"):
        print("  Top marcadores:", p15["top_marcadores"][:3])
    print(f"  Selección buckets local/visitante: {p15.get('seleccion')}")
    print("-" * 80)
    print(f"E[aciertos] del desarrollo (14 partidos): {payload.get('aciertos_esperados')}")
    exact = payload.get("probabilidades_exactas") or {}
    print("Probabilidades exactas:")
    for k in ("p_ge_10", "p_ge_11", "p_ge_12", "p_ge_13", "p_ge_14"):
        if k in exact:
            print(f"  {k}: {exact[k]:.2%}")
    print("-" * 80)
    print(f"Signos (array web): {' '.join(signos)}")
    print(f"\nEscrito en:")
    print(f"  {OUT_PROGRAMA}")
    print(f"  {OUT_PROBS}")
    print(f"  {OUT_OPT}")


if __name__ == "__main__":
    main()
