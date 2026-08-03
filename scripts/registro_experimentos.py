#!/usr/bin/env python3
"""Registro append-only de experimentos del Programa Quiniela.

ROADMAP #4: "Registro append-only de experimento, configuración, fecha y
métricas".

Garantías del registro:
- **Append-only**: cada experimento se añade con un ``id`` incremental y único.
  Nunca se modifican ni eliminan entradas existentes; solo se leen y se
  añaden.
- **Traza completa**: cada entrada registra fecha, nombre, configuración,
  resultado, métricas, razón y referencia documental.
- **Regla del proyecto**: "No sobrescribir resultados históricos de
  experimentos" y "No declarar una mejora sin validación fuera de muestra".

Almacenamiento: `DATOS/registro_experimentos.json`. La ruta se puede sustituir
para tests (``REGISTRO_PATH``) o mediante ``--path``.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

REGISTRO_PATH = Path(__file__).resolve().parents[1] / "DATOS" / "registro_experimentos.json"

# Campos mínimos exigidos a cada entrada (clave interna -> etiqueta humana).
CAMPOS_OBLIGATORIOS = ("nombre", "fecha", "resultado")
CAMPOS_OPCIONALES = ("configuracion", "metricas", "razon", "referencia")

_REGISTRO_VERSION = 1


def cargar(path: Path) -> dict:
    """Carga el registro. Si no existe, devuelve uno vacío (no lo crea)."""
    if not path.exists():
        return {"version": _REGISTRO_VERSION, "registro": []}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("registro"), list):
        raise ValueError(f"Registro corrupto en {path}: no es un objeto con lista 'registro'")
    return data


def _ultimo_id(entradas: list[dict]) -> int:
    ids = [e.get("id", 0) for e in entradas]
    return max(ids, default=0)


def _normalizar_entrada(id_: int, entrada: dict) -> dict:
    """Rellena claves opcionales y fija el id. Valida obligatorias."""
    faltantes = [c for c in CAMPOS_OBLIGATORIOS if not entrada.get(c)]
    if faltantes:
        raise ValueError(f"Faltan campos obligatorios: {', '.join(faltantes)}")
    normalizada = {"id": id_, "fecha": entrada.get("fecha"), "nombre": entrada["nombre"], "resultado": entrada["resultado"]}
    for campo in CAMPOS_OPCIONALES:
        valor = entrada.get(campo)
        if valor not in (None, ""):
            normalizada[campo] = valor
    return normalizada


def registrar(nombre: str, resultado: str, *, fecha: str | None = None,
              configuracion: str | None = None, metricas=None, razon: str | None = None,
              referencia: str | None = None, path: Path | None = None,
              escribir: bool = True) -> dict:
    """Añade un experimento al registro (append-only).

    Devuelve la entrada añadida (con su ``id``). Con ``escribir=False`` solo
    devuelve la entrada normalizada sin tocar el archivo (útil en tests).
    """
    ruta = path or REGISTRO_PATH
    data = cargar(ruta)
    entradas = data["registro"]
    nueva = _normalizar_entrada(
        _ultimo_id(entradas) + 1,
        {
            "nombre": nombre,
            "fecha": fecha or date.today().isoformat(),
            "resultado": resultado,
            "configuracion": configuracion,
            "metricas": metricas,
            "razon": razon,
            "referencia": referencia,
        },
    )
    if escribir:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump({"version": _REGISTRO_VERSION, "registro": entradas + [nueva]}, f, ensure_ascii=False, indent=2)
            f.write("\n")
    return nueva


def listar(path: Path | None = None) -> list[dict]:
    """Devuelve la lista de entradas del registro (sin modificar nada)."""
    data = cargar(path or REGISTRO_PATH)
    return data["registro"]


def _main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nombre", required=True, help="Nombre del experimento")
    parser.add_argument("--resultado", required=True, help="Resultado (IMPLEMENTADO/RECHAZADO/...)")
    parser.add_argument("--fecha", help="Fecha ISO (por defecto: hoy)")
    parser.add_argument("--configuracion", help="Configuración del experimento")
    parser.add_argument("--metricas", help="Métricas (texto libre o JSON)")
    parser.add_argument("--razon", help="Razón del resultado")
    parser.add_argument("--referencia", help="Referencia documental (REVISION_xx, etc.)")
    parser.add_argument("--path", help="Ruta alternativa del registro (tests)")
    args = parser.parse_args()

    metricas = args.metricas
    if metricas:
        try:
            metricas = json.loads(metricas)
        except json.JSONDecodeError:
            pass  # se conserva como texto libre

    entrada = registrar(
        args.nombre,
        args.resultado,
        fecha=args.fecha,
        configuracion=args.configuracion,
        metricas=metricas,
        razon=args.razon,
        referencia=args.referencia,
        path=Path(args.path) if args.path else None,
    )
    print(f"Experiment registrado con id={entrada['id']}: {entrada['nombre']} -> {entrada['resultado']}")


if __name__ == "__main__":
    _main()
