"""Invariantes del boleto y selección explícita de fuentes de probabilidad."""
from __future__ import annotations

import json
import math

import settings


SIGNOS = ("1", "X", "2")
BUCKETS = ("0", "1", "2", "M")


def require_positions(records: object, key: str = "num", count: int = 15) -> list[dict]:
    """Valida posiciones oficiales; no reordena ni inventa posiciones faltantes."""
    if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
        raise ValueError("El boleto debe contener una lista de partidos")
    numbers = [row.get(key) for row in records]
    expected = list(range(1, count + 1))
    if any(type(n) is not int for n in numbers) or sorted(numbers) != expected:
        raise ValueError(f"El boleto debe contener las posiciones únicas 1..{count}")
    return records


def validate_jornada(data: object, jornada: int) -> list[dict]:
    """Verifica la identidad y estructura del boleto antes de usar posiciones."""
    if (type(jornada) is not int or jornada < 1 or not isinstance(data, dict)
            or type(data.get("jornada")) is not int or data["jornada"] != jornada):
        raise ValueError(f"El boleto no declara la jornada J{jornada}")
    matches = require_positions(data.get("partidos"))
    for match in matches:
        if not all(isinstance(match.get(k), str) and match[k].strip() for k in ("local", "visitante")):
            raise ValueError(f"Faltan los nombres de los equipos en la casilla {match['num']}")
    return matches


def load_jornada_json(jornada: int) -> dict:
    """Carga la captura local, con la misma validación para cada consumidor."""
    path = settings.DATOS_DIR / f"QUINIELA15_J{jornada}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_jornada(data, jornada)
    return data


def normalize_weights(values: list) -> list[float] | None:
    """Normaliza pesos completos no negativos; no rellena vías inexistentes."""
    if any(isinstance(x, bool) for x in values):
        return None
    try:
        weights = [float(x) for x in values]
    except (TypeError, ValueError, OverflowError):
        return None
    total = sum(weights)
    if not math.isfinite(total) or total <= 0 or any(not math.isfinite(x) or x < 0 for x in weights):
        return None
    return [x / total for x in weights]


def normalized_triplet(values: object) -> dict[str, float] | None:
    if not isinstance(values, dict) or set(values) != set(SIGNOS):
        return None
    weights = normalize_weights([values[s] for s in SIGNOS])
    return dict(zip(SIGNOS, weights)) if weights is not None else None


def select_probabilities(match: dict) -> tuple[dict[str, float] | None, str]:
    """Usa el motor solo si está disponible; identifica cualquier proxy."""
    probabilities = match.get("probabilidades")
    probabilities = probabilities if isinstance(probabilities, dict) else {}
    model = match.get("modelo_maestro")
    model = model if isinstance(model, dict) else {}
    comparison = probabilities.get("comparativa")
    comparison = comparison if isinstance(comparison, dict) else {}
    motor = normalized_triplet(probabilities.get("modelo"))
    # Compatibilidad con paquetes anteriores sin modelo_maestro. El diagnóstico
    # sí lleva fuente_modelo y jamás se confunde con un pronóstico entrenado.
    if motor and (model.get("disponible") is True or ("disponible" not in model and not match.get("fuente_modelo"))):
        return motor, "motor_maestro"
    for source in ("apu", "lae", "q15"):
        proxy = normalized_triplet(comparison.get(source) or match.get(source))
        if proxy:
            return proxy, f"{source}_fallback"
    return None, "sin_fuente"
