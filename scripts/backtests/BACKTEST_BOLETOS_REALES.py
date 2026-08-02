"""BACKTEST_BOLETOS_REALES.py — Evalúa el motor sobre boletos REALES de La Quiniela.

Usa los boletos de 15 partidos (14 + pleno) cosechados del archivo oficial
(``DATOS/jornadas_lae/`` cuando exista; si no, la muestra validada en
``DATOS/jornadas_lae_muestra/``) y las predicciones del backtest maestro
(``salida/predicciones_backtest_optimizadas.csv``).

Qué calcula por boleto:
- Aciertos con 3 dobles sobre el boleto real (regla idéntica a
  ``simulate_doubles``: 3 dobles por máximo valor de doble).
- Acierto simple del motor y del favorito de mercado.
- Validación cruzada: si el boleto tiene ``combinacion_ganadora``, comprueba
  que los resultados del histórico coinciden con la combinación oficial.

Esto es lo que pedía la auditoría: evaluar sobre los boletos reales y no
sobre bloques arbitrarios de 15 partidos.

Uso:
    python scripts/backtests/BACKTEST_BOLETOS_REALES.py
    python scripts/backtests/BACKTEST_BOLETOS_REALES.py --tickets DATOS/jornadas_lae --predicciones salida/predicciones_backtest_optimizadas.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import settings  # noqa: E402
import MOTOR_QUINIELA_MAESTRO as motor  # noqa: E402
from scripts.motor.team_names import resolve_history_name  # noqa: E402

DEFAULT_TICKETS = settings.DATOS_DIR / "jornadas_lae_muestra"
DEFAULT_PREDICCIONES = PROJECT_ROOT / "salida" / "predicciones_backtest_optimizadas.csv"

VALID_SIGNS = {"1", "X", "2"}


def _pleno_sign_to_1x2(code: str) -> str | None:
    """Deriva el signo 1X2 de un pleno tipo '10', 'M2', 'MM' (0-2 goles, M = 3+)."""
    if len(code) != 2:
        return None

    def val(ch: str) -> int | None:
        if ch.isdigit():
            return int(ch)
        if ch.upper() == "M":
            return 3
        return None

    a, b = val(code[0]), val(code[1])
    if a is None or b is None:
        return None
    if a == b and (code[0].upper() == "M" or code[1].upper() == "M"):
        return None  # M-M es ambiguo (3-3 o 4-3...)
    return "1" if a > b else "2" if a < b else "X"


def load_tickets(tickets_dir: Path) -> list[dict]:
    """Carga boletos desde JSON sueltos o consolidados por temporada."""
    if not tickets_dir.is_dir():
        raise FileNotFoundError(f"No existe el directorio de boletos: {tickets_dir}")
    tickets: list[dict] = []
    for path in sorted(tickets_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("boletos") if "boletos" in data else data.get("jornadas", [])
        for item in items:
            partidos = item.get("partidos", [])
            pleno = item.get("pleno15")
            matches = [{"num": p["num"], "local": p["local"], "visitante": p["visitante"]} for p in partidos]
            if pleno:
                matches.append({"num": 15, "local": pleno["local"], "visitante": pleno["visitante"]})
            ticket = {
                "temporada": item.get("temporada"),
                "jornada": item.get("jornada"),
                "fecha_sorteo": item.get("fecha_sorteo") or item.get("fecha"),
                "matches": matches,
                "combinacion_ganadora": item.get("combinacion_ganadora"),
                "recaudacion_euros": item.get("recaudacion_euros"),
                "premios": item.get("premios"),
            }
            tickets.append(ticket)
    return tickets


def join_ticket(ticket: dict, preds: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Une los 15 partidos del boleto con las predicciones del backtest.

    Ventana de búsqueda: [fecha_sorteo - 4 días, fecha_sorteo + 2 días].
    Devuelve (filas unidas, faltantes).
    """
    lo = pd.Timestamp(ticket["fecha_sorteo"]) - pd.Timedelta(days=4)
    hi = pd.Timestamp(ticket["fecha_sorteo"]) + pd.Timedelta(days=2)
    rows, missing = [], []
    for m in ticket["matches"]:
        local = resolve_history_name(m["local"])
        visitante = resolve_history_name(m["visitante"])
        hit = preds[
            (preds["date"] >= lo) & (preds["date"] <= hi)
            & (preds["home"] == local) & (preds["away"] == visitante)
        ]
        if hit.empty:
            missing.append(m)
            continue
        row = hit.iloc[0].copy()
        row["num"] = m["num"]  # para validar por posición oficial del boleto
        rows.append(row)
    return pd.DataFrame(rows), missing


def evaluate_ticket(ticket: dict, preds: pd.DataFrame, config: dict) -> dict | None:
    joined, missing = join_ticket(ticket, preds)
    if len(joined) < 15:
        # Se evalúa igualmente con los partidos disponibles, indicándolo.
        if len(joined) < 14:
            return None
    if joined.empty:
        return None

    group = joined.reset_index(drop=True)
    group["double"] = [
        motor.build_double(p1, px, p2, config["double_draw_threshold"])
        for p1, px, p2 in zip(
            group["best_prob_1"], group["best_prob_x"], group["best_prob_2"]
        )
    ]
    conf = group[["best_prob_1", "best_prob_x", "best_prob_2"]].max(axis=1)
    score = (
        (1 - conf)
        + config["double_draw_weight"] * group["best_prob_x"]
        + config["double_disagreement_weight"] * group["model_disagreement"]
        + np.where(group["division"].eq("Segunda"), config["double_segunda_bonus"], 0.0)
    )
    group["double_value_score"] = score
    dobles = set(group.nlargest(3, "double_value_score").index.tolist())

    hits = 0
    for i, row in group.iterrows():
        if i in dobles:
            hits += int(row["result"] in row["double"])
        else:
            hits += int(row["best_pred"] == row["result"])

    market_valid = group["favorite_market"].notna()
    res = {
        "temporada": ticket["temporada"],
        "jornada": ticket["jornada"],
        "fecha_sorteo": ticket.get("fecha_sorteo"),
        "n_partidos_evaluados": len(group),
        "faltantes": [f"{m['local']} - {m['visitante']}" for m in missing],
        "hits_3_dobles": hits,
        "accuracy_simple": float(group["best_pred"].eq(group["result"]).mean()),
        "accuracy_market": float(group.loc[market_valid, "favorite_market"].eq(group.loc[market_valid, "result"]).mean())
        if market_valid.any()
        else None,
        "recaudacion_euros": ticket.get("recaudacion_euros"),
        "premios": ticket.get("premios"),
    }

    # Validación cruzada con la combinación ganadora oficial (por num del boleto,
    # no por posición, para no desfasarse con partidos aplazados/faltantes).
    comb = ticket.get("combinacion_ganadora")
    if comb:
        desajustes = 0
        por_num = {int(r["num"]): r["result"] for _, r in group.iterrows()}
        for i, signo in enumerate(comb):
            num = i + 1
            if num not in por_num:
                continue
            real = por_num[num]
            if signo in VALID_SIGNS:
                if real != signo:
                    desajustes += 1
            else:
                derivado = _pleno_sign_to_1x2(signo)
                if derivado is not None and real != derivado:
                    desajustes += 1
        res["combinacion_ganadora"] = comb
        res["desajustes_vs_combinacion_oficial"] = desajustes
    return res


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest del motor sobre boletos reales de La Quiniela")
    parser.add_argument("--tickets", default=str(DEFAULT_TICKETS))
    parser.add_argument("--predicciones", default=str(DEFAULT_PREDICCIONES))
    args = parser.parse_args()

    preds = pd.read_csv(args.predicciones)
    preds["date"] = pd.to_datetime(preds["date"], errors="coerce")
    config = settings.master_model_config()

    tickets = load_tickets(Path(args.tickets))
    if not tickets:
        print(f"No hay boletos en {args.tickets}", file=sys.stderr)
        return 1

    results = []
    for t in tickets:
        r = evaluate_ticket(t, preds, config)
        if r is None:
            print(f"  aviso: boleto {t.get('temporada')} J{t.get('jornada')} sin partidos unidos")
            continue
        results.append(r)

    if not results:
        print("No se pudo evaluar ningún boleto.", file=sys.stderr)
        return 1

    df = pd.DataFrame(results)
    print("=" * 78)
    print("BACKTEST SOBRE BOLETOS REALES DE LA QUINIELA (15 partidos oficiales)")
    print("=" * 78)
    for _, r in df.iterrows():
        faltantes = f" (faltan: {', '.join(r['faltantes'])})" if r["faltantes"] else ""
        mercado = f"{r['accuracy_market']:.1%}" if r["accuracy_market"] is not None else "n/d"
        print(
            f"  {r['temporada']} J{r['jornada']:>2}  {r['fecha_sorteo']}: "
            f"{r['hits_3_dobles']}/{r['n_partidos_evaluados']} con 3 dobles "
            f"(simple {r['accuracy_simple']:.1%} | mercado {mercado}){faltantes}"
        )
    print("-" * 78)
    media = df["hits_3_dobles"].mean()
    print(f"  MEDIA: {media:.2f} aciertos con 3 dobles por boleto "
          f"({media / 15.0:.1%} sobre 15)")
    print(f"  Acierto simple medio: {df['accuracy_simple'].mean():.2%} | "
          f"mercado: {df['accuracy_market'].mean():.2%}")
    desaj = df.get("desajustes_vs_combinacion_oficial")
    if desaj is not None and desaj.notna().any():
        print(f"  Validación vs combinación oficial: {int(desaj.sum())} desajustes "
              f"en {int(desaj.notna().sum())} boletos")

    out_path = settings.SALIDA_DIR / "backtest_boletos_reales.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "n_boletos": len(df),
                "media_aciertos_3_dobles": float(media),
                "acierto_simple_medio": float(df["accuracy_simple"].mean()),
                "acierto_mercado_medio": float(df["accuracy_market"].mean()),
                "boletos": df.to_dict(orient="records"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nGuardado en {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
