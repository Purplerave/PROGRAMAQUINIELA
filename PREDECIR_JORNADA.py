import argparse
import json
import unicodedata
from datetime import datetime

import settings
from MOTOR_DECISION_QUINIELISTICA import diagnose_jornada


def load_priors():
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
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().replace(".", "").split())


def enrich_with_priors(partidos, priors):
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


def build_package(jornada):
    diagnostic = diagnose_jornada(jornada)
    priors, global_warnings = load_priors()
    partidos = enrich_with_priors(diagnostic.get("partidos", []), priors)
    match_warnings = prior_warnings_for_matches(partidos)
    pleno = next((p.get("pleno15") for p in partidos if p.get("num") == 15), None)
    return {
        "jornada": jornada,
        "fecha_generacion": datetime.now().isoformat(timespec="seconds"),
        "version_config": settings.CONFIG.get("version", diagnostic.get("version")),
        "estado": "paquete_jornada_v2",
        "partidos": partidos,
        "pleno15": pleno,
        "columnas": {
            "estado": "pendiente_v3",
            "nota": "La v2 consolida diagnostico, avisos y priors. Las columnas se conectaran despues.",
        },
        "avisos": {
            "globales": global_warnings,
            "partidos": match_warnings,
        },
        "fuentes": {
            "diagnostico": f"SALIDAS/diagnostico_quinielistico_J{jornada}.json",
            "jornada": f"DATOS/QUINIELA15_J{jornada}.json",
            "priors": "DATOS/temporada_2026_27_estadisticas_base.json",
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Genera paquete consolidado para una jornada.")
    parser.add_argument("--jornada", "-j", type=int, required=True)
    args = parser.parse_args()
    settings.SALIDAS_DIR.mkdir(parents=True, exist_ok=True)
    package = build_package(args.jornada)
    out_path = settings.SALIDAS_DIR / f"paquete_jornada_J{args.jornada}.json"
    out_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK -> {out_path}")
    print(json.dumps({
        "jornada": args.jornada,
        "partidos": len(package["partidos"]),
        "avisos_partido": len(package["avisos"]["partidos"]),
        "estado": package["estado"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
