"""Registro prospectivo append-only de predicciones y cuotas.

Motivo (auditoría 20/11/2026, P1): todas las cifras del proyecto son
retrospectivas. El tracker de paper-trading tiene una sola jornada y cero
cuotas verificadas. Para poder afirmar algo sobre ventaja real hace falta un
registro que se escriba **antes del corte**, con la predicción, la cuota
observada, la hora de observación, el corte y el kickoff, y que no se pueda
editar después sin que se note.

Diseño
------
* Formato JSONL (`DATOS/registro_prospectivo.jsonl`): una línea, un partido.
* Cadena de hashes: cada registro incluye ``hash_prev`` y ``hash``
  (SHA-256 de la serialización canónica del registro más el hash anterior).
  Alterar una línea rompe la cadena y ``--verificar`` lo detecta.
* Invariantes temporales, comprobadas al añadir y al verificar:
  ``odds_observed_at <= prediction_cutoff_at < kickoff_at`` y
  ``registrado_at <= prediction_cutoff_at``.
* Prohibido el duplicado ``(jornada, num_partido)``.

No calcula ROI ni aciertos: eso se hace en ``--resumen`` solo con registros
cuyo resultado se haya añadido después (campo ``resultado``), y siempre
declarando cuántos quedan pendientes.

Uso::

    python scripts/registro_prospectivo.py --verificar
    python scripts/registro_prospectivo.py --resumen
    python scripts/registro_prospectivo.py --anadir partidos_J75.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import settings

REGISTRO_PATH = settings.DATOS_DIR / "registro_prospectivo.jsonl"

CAMPOS_OBLIGATORIOS = (
    "jornada",
    "num_partido",
    "local",
    "visitante",
    "kickoff_at",
    "prediction_cutoff_at",
    "registrado_at",
    "signo",
    "probabilidades",
    "source",
)
SIGNOS = ("1", "X", "2")
CAMPOS_HASH = ("hash_prev", "hash")

#: Tolerancia (segundos) al comparar timestamps: evita falsos negativos por microsegundos.
TOLERANCIA_S = 1.0


class RegistroInvalido(ValueError):
    """El registro no cumple el contrato o rompe la cadena."""


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _parse_ts(valor: Any, campo: str) -> datetime:
    if not isinstance(valor, str) or not valor:
        raise RegistroInvalido(f"{campo}: se espera timestamp ISO 8601 con zona")
    texto = valor.strip().replace("Z", "+00:00")
    try:
        momento = datetime.fromisoformat(texto)
    except ValueError as exc:  # pragma: no cover - mensaje explícito
        raise RegistroInvalido(f"{campo}: timestamp inválido ({valor!r})") from exc
    if momento.tzinfo is None:
        raise RegistroInvalido(f"{campo}: falta zona horaria ({valor!r})")
    return momento


def _canonico(registro: dict[str, Any]) -> str:
    return json.dumps(registro, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash_registro(registro: dict[str, Any], hash_prev: str) -> str:
    payload = _canonico({k: v for k, v in registro.items() if k != "hash"})
    return hashlib.sha256((hash_prev + payload).encode("utf-8")).hexdigest()


def cargar(path: Path = REGISTRO_PATH) -> list[dict[str, Any]]:
    """Lee el registro sin tolerar líneas corruptas."""
    if not path.is_file():
        return []
    registros: list[dict[str, Any]] = []
    for n, linea in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not linea.strip():
            continue
        try:
            registros.append(json.loads(linea))
        except json.JSONDecodeError as exc:
            raise RegistroInvalido(f"línea {n} no es JSON válido: {exc}") from exc
    return registros


def validar_registro(registro: dict[str, Any]) -> None:
    """Valida campos, tipos e invariantes temporales de un registro suelto."""
    faltan = [campo for campo in CAMPOS_OBLIGATORIOS if campo not in registro]
    if faltan:
        raise RegistroInvalido(f"faltan campos obligatorios: {faltan}")

    if registro["signo"] not in SIGNOS:
        raise RegistroInvalido(f"signo inválido: {registro['signo']!r}")
    if not isinstance(registro["jornada"], int) or registro["jornada"] < 1:
        raise RegistroInvalido("jornada debe ser un entero >= 1")
    if not isinstance(registro["num_partido"], int) or not 1 <= registro["num_partido"] <= 15:
        raise RegistroInvalido("num_partido debe estar entre 1 y 15")
    for campo in ("local", "visitante"):
        if not isinstance(registro[campo], str) or not registro[campo].strip():
            raise RegistroInvalido(f"{campo} no puede estar vacío")

    probs = registro["probabilidades"]
    if not isinstance(probs, dict) or set(probs) != set(SIGNOS):
        raise RegistroInvalido("probabilidades debe tener exactamente las claves 1, X y 2")
    try:
        valores = [float(probs[s]) for s in SIGNOS]
    except (TypeError, ValueError) as exc:
        raise RegistroInvalido("probabilidades no numéricas") from exc
    if any(not 0.0 <= v <= 1.0 for v in valores):
        raise RegistroInvalido("probabilidades fuera de [0, 1]")
    if abs(sum(valores) - 1.0) > 1e-3:
        raise RegistroInvalido(f"probabilidades no suman 1 (suma={sum(valores):.4f})")

    kickoff = _parse_ts(registro["kickoff_at"], "kickoff_at")
    corte = _parse_ts(registro["prediction_cutoff_at"], "prediction_cutoff_at")
    reg = _parse_ts(registro["registrado_at"], "registrado_at")
    if corte >= kickoff:
        raise RegistroInvalido("prediction_cutoff_at debe ser anterior a kickoff_at")
    if (reg - corte).total_seconds() > TOLERANCIA_S:
        raise RegistroInvalido(
            "registrado_at es posterior al corte: la predicción ya no es prospectiva"
        )

    cuotas = registro.get("cuotas")
    obs = registro.get("odds_observed_at")
    if cuotas is None:
        if obs is not None:
            raise RegistroInvalido("odds_observed_at sin cuotas")
        return
    if not isinstance(cuotas, dict) or set(cuotas) != set(SIGNOS):
        raise RegistroInvalido("cuotas debe tener exactamente las claves 1, X y 2")
    for signo in SIGNOS:
        try:
            cuota = float(cuotas[signo])
        except (TypeError, ValueError) as exc:
            raise RegistroInvalido(f"cuota {signo} no numérica") from exc
        if not cuota > 1.01:
            raise RegistroInvalido(f"cuota {signo} debe ser > 1.01 (recibido {cuota})")
    observado = _parse_ts(obs, "odds_observed_at")
    if (observado - corte).total_seconds() > TOLERANCIA_S:
        raise RegistroInvalido("odds_observed_at es posterior al corte")
    if observado >= kickoff:
        raise RegistroInvalido("odds_observed_at debe ser anterior a kickoff_at")

    source = registro["source"]
    if not isinstance(source, dict) or not source.get("name"):
        raise RegistroInvalido("source debe ser un objeto con 'name'")

    resultado = registro.get("resultado")
    if resultado is not None and resultado not in SIGNOS:
        raise RegistroInvalido(f"resultado inválido: {resultado!r}")


def verificar_cadena(registros: list[dict[str, Any]]) -> list[str]:
    """Comprueba hashes, orden y duplicados. Devuelve la lista de errores."""
    errores: list[str] = []
    hash_prev = ""
    vistos: set[tuple[int, int]] = set()
    for i, registro in enumerate(registros, start=1):
        etiqueta = f"registro {i}"
        try:
            validar_registro(registro)
        except RegistroInvalido as exc:
            errores.append(f"{etiqueta}: {exc}")
        clave = (registro.get("jornada"), registro.get("num_partido"))
        if clave in vistos:
            errores.append(f"{etiqueta}: duplicado de jornada/partido {clave}")
        vistos.add(clave)
        if registro.get("hash_prev") != hash_prev:
            errores.append(f"{etiqueta}: hash_prev no encadena con el registro anterior")
        esperado = _hash_registro(registro, hash_prev)
        if registro.get("hash") != esperado:
            errores.append(f"{etiqueta}: hash no coincide (¿registro editado?)")
        hash_prev = registro.get("hash", "")
    return errores


def anadir(registros: list[dict[str, Any]], path: Path = REGISTRO_PATH, *, ahora: datetime | None = None) -> int:
    """Añade registros validados y encadenados. Devuelve cuántos se añadieron."""
    ahora = ahora or datetime.now(UTC)
    existentes = cargar(path)
    errores_cadena = verificar_cadena(existentes)
    if errores_cadena:
        raise RegistroInvalido(
            "el registro existente está corrupto; no se añade nada: " + "; ".join(errores_cadena[:3])
        )
    claves = {(r["jornada"], r["num_partido"]) for r in existentes}
    hash_prev = existentes[-1]["hash"] if existentes else ""

    nuevos: list[dict[str, Any]] = []
    for registro in registros:
        limpio = {k: v for k, v in registro.items() if k not in CAMPOS_HASH}
        limpio.setdefault("registrado_at", ahora.isoformat(timespec="seconds"))
        validar_registro(limpio)
        clave = (limpio["jornada"], limpio["num_partido"])
        if clave in claves:
            raise RegistroInvalido(f"ya existe un registro para jornada/partido {clave}")
        claves.add(clave)
        limpio["hash_prev"] = hash_prev
        limpio["hash"] = _hash_registro(limpio, hash_prev)
        hash_prev = limpio["hash"]
        nuevos.append(limpio)

    if not nuevos:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for registro in nuevos:
            fh.write(json.dumps(registro, ensure_ascii=False, sort_keys=True) + "\n")
    return len(nuevos)


def resumen(registros: list[dict[str, Any]]) -> dict[str, Any]:
    """Resumen descriptivo: nunca inventa aciertos ni ROI sin cuotas verificadas."""
    con_cuotas = [r for r in registros if r.get("cuotas")]
    resueltos = [r for r in registros if r.get("resultado") in SIGNOS]
    aciertos = [r for r in resueltos if r["resultado"] == r["signo"]]
    con_cuotas_resueltos = [r for r in con_cuotas if r.get("resultado") in SIGNOS]
    return {
        "n_registros": len(registros),
        "n_con_cuotas": len(con_cuotas),
        "n_resueltos": len(resueltos),
        "n_pendientes": len(registros) - len(resueltos),
        "acierto": (len(aciertos) / len(resueltos)) if resueltos else None,
        "n_resueltos_con_cuotas": len(con_cuotas_resueltos),
        "nota": (
            "Sin cuotas observadas antes del corte no se puede estimar ROI ni comparar "
            "con el mercado; el acierto simple tampoco es evidencia de ventaja por sí solo."
        ),
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Registro prospectivo append-only (predicción + cuota + corte + kickoff).")
    parser.add_argument("--registro", type=Path, default=REGISTRO_PATH, help="Ruta del JSONL")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--verificar", action="store_true", help="Comprueba cadena, invariantes y duplicados")
    grupo.add_argument("--resumen", action="store_true", help="Resumen descriptivo del registro")
    grupo.add_argument("--anadir", type=Path, help="JSON con un registro o una lista de registros")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.verificar:
        try:
            registros = cargar(args.registro)
        except RegistroInvalido as exc:
            print(f"[registro][error] {exc}")
            return 1
        errores = verificar_cadena(registros)
        for error in errores:
            print(f"[registro][error] {error}")
        if errores:
            print(f"[registro] FALLO: {len(errores)} errores en {len(registros)} registros")
            return 1
        print(f"[registro] OK: cadena válida con {len(registros)} registros")
        return 0

    if args.resumen:
        try:
            datos = resumen(cargar(args.registro))
        except RegistroInvalido as exc:
            print(f"[registro][error] {exc}")
            return 1
        print(json.dumps(datos, ensure_ascii=False, indent=2))
        return 0

    contenido = json.loads(args.anadir.read_text(encoding="utf-8"))
    registros = contenido if isinstance(contenido, list) else [contenido]
    try:
        n = anadir(registros, args.registro)
    except RegistroInvalido as exc:
        print(f"[registro][error] {exc}")
        return 1
    print(f"[registro] añadidos {n} registros a {args.registro}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
