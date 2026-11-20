#!/usr/bin/env python3
"""Verifica el manifiesto de procedencia y licencias de los datos.

Contexto (auditoría del 20/11/2026, P0): el repositorio público redistribuye
datasets cuyo permiso no está confirmado. Este verificador no resuelve la
licencia —eso exige hablar con quien aportó cada fuente—, pero impide que la
situación se degrade en silencio:

* toda ruta de `DATOS/` debe estar declarada en el manifiesto;
* el estado de licencia debe pertenecer al vocabulario acordado;
* los hashes declarados deben coincidir con los archivos;
* toda fuente no redistribuible debe estar excluida de `git archive`
  mediante `.gitattributes`.

Uso:
    python scripts/datos/VERIFICAR_PROCEDENCIA.py            # comprueba
    python scripts/datos/VERIFICAR_PROCEDENCIA.py --json ruta.json
    python scripts/datos/VERIFICAR_PROCEDENCIA.py --actualizar  # refresca hashes

Nunca modifica los datos: como mucho reescribe los hashes del manifiesto con
`--actualizar`.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = PROJECT_ROOT / "DATOS" / "PROCEDENCIA_DATOS.json"
GITATTRIBUTES = PROJECT_ROOT / ".gitattributes"

ESTADOS_VALIDOS = {"verificada", "no_verificada", "prohibida_redistribucion"}
CAMPOS_OBLIGATORIOS = (
    "id",
    "rutas",
    "descripcion",
    "origen",
    "licencia",
    "estado_licencia",
    "redistribuible",
    "capturado",
)
# Rutas locales que no se versionan y por tanto no exigen declaración.
RUTAS_EXENTAS = {
    "DATOS/BOLETO_SEMANAL.json",
    "DATOS/xg_understat",
    "DATOS/paper_trading_2627.csv",
}
IGNORAR_SUFIJOS = (".tmp", ".temp", ".download", ".log")
# Documentación y el propio manifiesto no son datos y no exigen declaración.
IGNORAR_NOMBRES = {"README.md", "PROCEDENCIA_DATOS.json"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for bloque in iter(lambda: fh.read(1 << 20), b""):
            digest.update(bloque)
    return digest.hexdigest()


def cargar(manifest: Path) -> dict:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("fuentes"), list):
        raise ValueError("El manifiesto debe ser un objeto con la clave 'fuentes'.")
    return data


def _rutas_declaradas(data: dict) -> list[str]:
    rutas: list[str] = []
    for fuente in data["fuentes"]:
        for ruta in fuente.get("rutas", []):
            rutas.append(str(ruta).rstrip("/"))
    return rutas


def _cubierta(rel: str, declaradas: list[str]) -> bool:
    """True si `rel` está declarada, contiene una ruta declarada o encaja con un patrón."""
    for d in declaradas:
        if "*" in d or "?" in d:
            if fnmatch.fnmatch(rel, d):
                return True
            continue
        if rel == d or rel.startswith(d + "/") or d.startswith(rel + "/"):
            return True
    return False


def rutas_sin_declarar(data: dict) -> list[str]:
    """Rutas de DATOS/ (nivel superior) que el manifiesto no menciona."""
    datos = PROJECT_ROOT / "DATOS"
    declaradas = _rutas_declaradas(data)
    faltan = []
    for path in sorted(datos.iterdir()):
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        if rel in RUTAS_EXENTAS or path.name.endswith(IGNORAR_SUFIJOS):
            continue
        if path.name in IGNORAR_NOMBRES:
            continue
        if not _cubierta(rel, declaradas):
            faltan.append(rel)
    return faltan


def _export_ignore_ok(ruta: str, texto_gitattributes: str) -> bool:
    """True si la ruta (o su carpeta) está marcada como export-ignore."""
    candidatos = [ruta, ruta + "/**"]
    partes = ruta.split("/")
    while len(partes) > 1:
        partes.pop()
        candidatos.append("/".join(partes) + "/**")
        candidatos.append("/".join(partes))
    for linea in texto_gitattributes.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        patron, _, atributos = linea.partition(" ")
        if "export-ignore" not in atributos:
            continue
        limpio = patron.rstrip("/")
        for candidato in candidatos:
            if limpio == candidato.rstrip("/") or fnmatch.fnmatch(candidato, limpio):
                return True
    return False


def verificar(data: dict, *, verificar_hashes: bool = True) -> tuple[list[str], list[str]]:
    """Devuelve (errores, avisos)."""
    errores: list[str] = []
    avisos: list[str] = []
    vistos: set[str] = set()

    for i, fuente in enumerate(data["fuentes"]):
        etiqueta = fuente.get("id") or f"fuente[{i}]"
        faltantes = [campo for campo in CAMPOS_OBLIGATORIOS if campo not in fuente]
        if faltantes:
            errores.append(f"{etiqueta}: faltan campos obligatorios {faltantes}")
            continue
        if etiqueta in vistos:
            errores.append(f"{etiqueta}: id duplicado")
        vistos.add(etiqueta)

        estado = fuente["estado_licencia"]
        if estado not in ESTADOS_VALIDOS:
            errores.append(f"{etiqueta}: estado_licencia inválido {estado!r} (use {sorted(ESTADOS_VALIDOS)})")
        if fuente["redistribuible"] not in (True, False, None):
            errores.append(f"{etiqueta}: 'redistribuible' debe ser true, false o null")
        if estado == "prohibida_redistribucion" and fuente["redistribuible"] is not False:
            errores.append(f"{etiqueta}: licencia prohibitiva pero 'redistribuible' no es false")
        if estado == "verificada" and not fuente.get("atribucion"):
            avisos.append(f"{etiqueta}: licencia verificada sin línea de atribución")

        for ruta in fuente["rutas"]:
            path = PROJECT_ROOT / ruta
            if not path.exists():
                errores.append(f"{etiqueta}: la ruta declarada no existe ({ruta})")
                continue
            if fuente["redistribuible"] is not True:
                if not GITATTRIBUTES.is_file():
                    errores.append("Falta .gitattributes: no se puede excluir la fuente no redistribuible")
                elif not _export_ignore_ok(ruta, GITATTRIBUTES.read_text(encoding="utf-8")):
                    errores.append(
                        f"{etiqueta}: '{ruta}' no es redistribuible y no está en .gitattributes como export-ignore"
                    )

            hashes = fuente.get("hashes") or {}
            if hashes:
                for rel, esperado in hashes.items():
                    archivo = PROJECT_ROOT / rel
                    if not archivo.is_file():
                        errores.append(f"{etiqueta}: hash de un archivo inexistente ({rel})")
                        continue
                    if verificar_hashes and sha256(archivo) != esperado:
                        errores.append(f"{etiqueta}: hash distinto al declarado en {rel}")
            elif fuente.get("hash_estricto"):
                avisos.append(f"{etiqueta}: fuente marcada hash_estricto sin hashes; ejecute --actualizar")

        if estado == "no_verificada":
            avisos.append(f"{etiqueta}: licencia sin verificar; no usar como base de una afirmación de producción")

    faltan = rutas_sin_declarar(data)
    for ruta in faltan:
        errores.append(f"Ruta de DATOS/ sin declarar en el manifiesto: {ruta}")
    return errores, avisos


def actualizar_hashes(data: dict) -> int:
    """Recalcula los hashes de las fuentes con 'hash_estricto'."""
    actualizadas = 0
    for fuente in data["fuentes"]:
        if not fuente.get("hash_estricto"):
            continue
        hashes: dict[str, str] = {}
        for ruta in fuente["rutas"]:
            path = PROJECT_ROOT / ruta
            if path.is_file():
                hashes[ruta] = sha256(path)
            elif path.is_dir():
                for archivo in sorted(path.rglob("*")):
                    if archivo.is_file() and not archivo.name.endswith(IGNORAR_SUFIJOS):
                        hashes[archivo.relative_to(PROJECT_ROOT).as_posix()] = sha256(archivo)
        fuente["hashes"] = hashes
        actualizadas += 1
    return actualizadas


def resumen(data: dict) -> dict:
    estados: dict[str, int] = {}
    for fuente in data["fuentes"]:
        estados[fuente.get("estado_licencia", "?")] = estados.get(fuente.get("estado_licencia", "?"), 0) + 1
    return {
        "fuentes": len(data["fuentes"]),
        "por_estado_licencia": estados,
        "pendientes_licencia": sorted(
            f["id"] for f in data["fuentes"] if f.get("estado_licencia") != "verificada"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--actualizar", action="store_true", help="Recalcula hashes y reescribe el manifiesto")
    parser.add_argument("--sin-hashes", action="store_true", help="No recomprueba los hashes de archivos grandes")
    parser.add_argument("--json", type=Path, help="Escribe el informe JSON en esta ruta")
    parser.add_argument("--fail-on-warning", action="store_true", help="Devuelve 1 también con avisos")
    args = parser.parse_args(argv)

    if not args.manifest.is_file():
        print(f"[procedencia] no existe el manifiesto: {args.manifest}")
        return 2

    data = cargar(args.manifest)
    if args.actualizar:
        n = actualizar_hashes(data)
        args.manifest.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"[procedencia] hashes recalculados en {n} fuentes")

    errores, avisos = verificar(data, verificar_hashes=not args.sin_hashes)
    informe = {
        "manifest": str(args.manifest.relative_to(PROJECT_ROOT)) if args.manifest.is_relative_to(PROJECT_ROOT) else str(args.manifest),
        "resumen": resumen(data),
        "errores": errores,
        "avisos": avisos,
        "ok": not errores,
    }

    print(f"[procedencia] fuentes declaradas: {informe['resumen']['fuentes']}")
    for estado, n in sorted(informe["resumen"]["por_estado_licencia"].items()):
        print(f"[procedencia]   licencia {estado}: {n}")
    if informe["resumen"]["pendientes_licencia"]:
        print("[procedencia] pendientes de licencia: " + ", ".join(informe["resumen"]["pendientes_licencia"]))
    for aviso in avisos:
        print(f"[procedencia][aviso] {aviso}")
    for error in errores:
        print(f"[procedencia][error] {error}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if errores:
        print(f"[procedencia] FALLO: {len(errores)} errores, {len(avisos)} avisos")
        return 1
    if args.fail_on_warning and avisos:
        print(f"[procedencia] FALLO por avisos: {len(avisos)}")
        return 1
    print(f"[procedencia] OK: sin errores ({len(avisos)} avisos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
