import argparse
import json
from collections import Counter
from pathlib import Path

import settings


ROOT = settings.QUINIELAS_ROOT
PROG_DIR = settings.PROJECT_DIR
DATOS_DIR = settings.DATOS_DIR
SALIDAS_DIR = settings.SALIDAS_DIR
CONFIG_PATH = settings.CONFIG_PATH

SIGNS = ("1", "X", "2")


def repair_text(value):
    if not isinstance(value, str):
        return value
    if "Ã" not in value and "Â" not in value:
        return value
    try:
        return value.encode("latin1").decode("utf-8")
    except Exception:
        return value


def pct_to_prob(values):
    if not values:
        return None
    out = {}
    for sign in SIGNS:
        raw = values.get(sign)
        if raw in ("", None):
            return None
        out[sign] = float(raw) / 100.0
    total = sum(out.values())
    if total <= 0:
        return None
    return {sign: out[sign] / total for sign in SIGNS}


def choose_market_proxy(match, config):
    for key in config["fallback_sources"]["market_proxy_order"]:
        probs = pct_to_prob(match.get(key))
        if probs:
            return key, probs
    return "none", None


def sorted_signs(probs):
    return sorted(probs.items(), key=lambda item: item[1], reverse=True)


def risk_label(probs, config):
    ordered = sorted_signs(probs)
    gap = ordered[0][1] - ordered[1][1]
    limits = config["risk_gap_points"]
    if gap >= limits["low"]:
        return "bajo", gap
    if gap >= limits["medium"]:
        return "medio", gap
    if gap >= limits["high"]:
        return "alto", gap
    return "extremo", gap


def classify_match(market, public, config):
    thresholds = config["thresholds"]
    ordered = sorted_signs(market)
    fav, fav_prob = ordered[0]
    value = {sign: market[sign] - public.get(sign, 0.0) for sign in SIGNS}
    labels = []

    if fav_prob >= thresholds["logical_fixed_prob"] and value[fav] > -0.10:
        labels.append("fijo logico")
    if fav_prob >= 0.50 and value[fav] <= thresholds["favorite_overbet_value"]:
        labels.append("favorito sobreapostado")
    if fav_prob < thresholds["trap_market_favorite_max"] and public.get(fav, 0.0) > thresholds["trap_public_favorite"]:
        labels.append("partido trampa")
    if market["X"] >= thresholds["hidden_draw_market"] and public.get("X", 0.0) <= thresholds["hidden_draw_public_max"]:
        labels.append("empate oculto")
    if market["2"] >= thresholds["visitor_value_market"] and public.get("2", 0.0) <= thresholds["visitor_value_public_max"]:
        labels.append("visitante de valor")
    if all(thresholds["triple_min"] <= market[sign] <= thresholds["triple_max"] for sign in SIGNS):
        labels.append("triple candidato")

    if not labels:
        labels.append("favorito razonable" if fav_prob >= 0.50 else "partido abierto")
    return labels, value


def recommendation(market, public, labels):
    ordered = sorted_signs(market)
    fav = ordered[0][0]
    second = ordered[1][0]
    value_order = sorted(SIGNS, key=lambda sign: market[sign] - public.get(sign, 0.0), reverse=True)

    if "partido trampa" in labels or "favorito sobreapostado" in labels:
        conservative = "".join(sorted({fav, second}, key=SIGNS.index))
        balanced = "".join(sorted(set(value_order[:2]), key=SIGNS.index))
        aggressive = value_order[0]
    elif "triple candidato" in labels:
        conservative = "".join(sorted({fav, "X"}, key=SIGNS.index))
        balanced = "1X2"
        aggressive = value_order[0]
    elif "empate oculto" in labels:
        conservative = "".join(sorted({fav, "X"}, key=SIGNS.index))
        balanced = conservative
        aggressive = "X"
    else:
        conservative = fav
        balanced = "".join(sorted({fav, second}, key=SIGNS.index)) if market[second] >= 0.24 else fav
        aggressive = value_order[0] if value_order[0] != fav and market[value_order[0]] >= 0.20 else fav

    return {
        "conservadora": conservative,
        "equilibrada": balanced,
        "agresiva": aggressive,
    }


def pleno_summary(match):
    scores = match.get("marcadores_q15") or []
    return {
        "nota": "El Pleno al 15 separa signo 1X2 de marcador por goles.",
        "top_marcadores": scores[:5],
        "buckets": ["0", "1", "2", "M"],
    }


def load_master_notes(jornada):
    for name in [f"PREDICCIONES_J{jornada}_DEFINITIVO.json", f"PREDICCIONES_J{jornada}_FINAL.json"]:
        path = ROOT / name
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        notes = {}
        for item in data.get("maestra") or []:
            notes[int(item.get("p"))] = {
                "signo": repair_text(item.get("s", "")),
                "razon": repair_text(item.get("r", "")),
            }
        return notes
    return {}


def diagnose_jornada(jornada):
    raw_config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config = raw_config.get("decision", raw_config)
    source_path = DATOS_DIR / f"QUINIELA15_J{jornada}.json"
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    data = json.loads(source_path.read_text(encoding="utf-8"))
    master_notes = load_master_notes(jornada)

    out = {
        "jornada": jornada,
        "version": raw_config.get("version", config.get("version", "sin_version")),
        "pesos_configurables": config["weights"],
        "advertencia": "Si no hay cuotas reales, se usa proxy: apu > lae > tendencia. Recalibrar con backtesting.",
        "partidos": [],
    }

    for match in data.get("partidos", []):
        num = int(match["num"])
        item = {
            "num": num,
            "local": repair_text(match.get("local")),
            "visitante": repair_text(match.get("visitante")),
            "fecha": match.get("fecha"),
            "hora": match.get("hora"),
            "contexto_manual": [],
            "maestra": master_notes.get(num),
        }
        if num == 15:
            item["pleno15"] = pleno_summary(match)
            out["partidos"].append(item)
            continue

        public = pct_to_prob(match.get("q15")) or pct_to_prob(match.get("lae"))
        market_source, market = choose_market_proxy(match, config)
        if not public or not market:
            item["diagnostico"] = "sin probabilidades suficientes"
            out["partidos"].append(item)
            continue

        labels, value = classify_match(market, public, config)
        risk, gap = risk_label(market, config)
        item.update({
            "fuente_modelo": market_source,
            "probabilidades": {
                "modelo": {k: round(v, 4) for k, v in market.items()},
                "publico": {k: round(v, 4) for k, v in public.items()},
            },
            "valor": {k: round(v, 4) for k, v in value.items()},
            "riesgo": risk,
            "gap_primero_segundo": round(gap, 4),
            "etiquetas": labels,
            "recomendacion": recommendation(market, public, labels),
        })
        out["partidos"].append(item)

    return out


def main():
    parser = argparse.ArgumentParser(description="Genera diagnostico quinielistico por partido.")
    parser.add_argument("--jornada", "-j", type=int, required=True)
    args = parser.parse_args()
    SALIDAS_DIR.mkdir(parents=True, exist_ok=True)
    payload = diagnose_jornada(args.jornada)
    out_path = SALIDAS_DIR / f"diagnostico_quinielistico_J{args.jornada}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    counts = Counter(label for p in payload["partidos"] for label in p.get("etiquetas", []))
    print(f"OK -> {out_path}")
    print(json.dumps({"jornada": args.jornada, "etiquetas": counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
