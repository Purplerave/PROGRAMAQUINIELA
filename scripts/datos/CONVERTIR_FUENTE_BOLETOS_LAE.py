"""Convierte una fuente agregada de jornadas a JSON por boleto.

Entrada esperada: lista JSON con jornadas y campo ``partidos`` (15 partidos).
Salida: un fichero por jornada en DATOS/boletos_lae_reales, compatible con
scripts/backtests/BACKTEST_BOLETOS_LAE.py.

Por defecto solo materializa jornadas con ``validable_historico=true`` para no
mezclar Champions/extranjeras con el backtest basado en histórico español.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import settings

DEFAULT_SOURCE = settings.DATOS_DIR / "boletos_lae_fuente" / "202526.json"
DEFAULT_OUT_DIR = settings.DATOS_DIR / "boletos_lae_reales"


def normalize_sign(num: int, value: object) -> str:
    text = str(value or "").strip().upper().replace(" ", "")
    if num < 15:
        if text in {"1", "X", "2"}:
            return text
        match = re.match(r"^([1X2])", text)
        if match:
            return match.group(1)
        raise ValueError(f"signo inválido para partido {num}: {value!r}")
    match = re.search(r"([012M]-[012M]|\d+-\d+)", text)
    if not match:
        raise ValueError(f"signo inválido para pleno: {value!r}")
    return match.group(1)


def normalize_resultado(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().replace(" ", "")
    if not text:
        return None
    if "sorteado" in text.lower():
        return None
    match = re.search(r"(\d+)-(\d+)", text)
    if not match:
        return None
    return f"{int(match.group(1))}-{int(match.group(2))}"


def normalize_match(raw: dict[str, Any]) -> dict[str, Any]:
    num = int(raw["num"])
    raw_resultado = raw.get("resultado")
    resultado = normalize_resultado(raw_resultado)
    tipo = raw.get("tipo")
    if num == 15:
        tipo = "pleno15"
    elif resultado is None:
        tipo = "sorteo"

    out = {
        "num": num,
        "local": str(raw["local"]).strip(),
        "visitante": str(raw["visitante"]).strip(),
        "resultado": resultado,
        "signo": normalize_sign(num, raw.get("signo")),
    }
    if tipo:
        out["tipo"] = tipo
    return out


def normalize_jornada(raw: dict[str, Any]) -> dict[str, Any]:
    jornada = int(raw["jornada_q15"])
    partidos = sorted((normalize_match(m) for m in raw["partidos"]), key=lambda m: int(m["num"]))
    nums = [m["num"] for m in partidos]
    if nums != list(range(1, 16)):
        raise ValueError(f"J{jornada:03d}: nums inválidos {nums}")
    return {
        "id": raw.get("id") or f"Q15_2025_2026_J{jornada:03d}",
        "jornada_q15": jornada,
        "temporada": raw.get("temporada", "2025-2026"),
        "fuente": raw.get("fuente", "fuente_externa"),
        "source_url": raw.get("source_url"),
        "competicion_tipo": raw.get("competicion_tipo"),
        "validable_historico": bool(raw.get("validable_historico")),
        "partidos": partidos,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Convierte fuente agregada a boletos individuales")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--incluir-no-validables", action="store_true")
    parser.add_argument(
        "--validar-historico",
        action="store_true",
        help="solo escribe jornadas que pasan la validación contra el histórico local",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    history = None
    if args.validar_historico:
        from MOTOR_QUINIELA_MAESTRO import load_raw_history
        from scripts.backtests.BACKTEST_BOLETOS_LAE import validate_ticket_against_history

        history = load_raw_history("original")

    data = json.loads(args.source.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("La fuente debe ser una lista de jornadas")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    skipped = []
    errors = {}
    for raw in data:
        jornada = int(raw.get("jornada_q15", -1))
        try:
            if not args.incluir_no_validables and not raw.get("validable_historico"):
                skipped.append(jornada)
                continue
            payload = normalize_jornada(raw)
            if history is not None:
                validate_ticket_against_history(payload, history)  # type: ignore[name-defined]
            out_path = args.out_dir / f"Q15_2025_2026_J{jornada:03d}.json"
            if out_path.exists() and not args.overwrite:
                raise FileExistsError(f"Ya existe {out_path}; usa --overwrite")
            out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            written.append(str(out_path))
        except Exception as exc:  # noqa: BLE001
            if args.validar_historico:
                skipped.append(jornada)
            else:
                errors[jornada] = str(exc)

    summary = {"source": str(args.source), "escritos": len(written), "omitidos": len(skipped), "errores": errors}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
