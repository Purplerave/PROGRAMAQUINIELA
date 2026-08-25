"""Estudia apertura, cierre, movimiento de cuotas y bandas de favorito.

No modifica la configuración del motor. Usa solo filas válidas del histórico
español y separa apertura de cierre real para evitar mezclar regímenes.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "DATOS" / "historico_raw"
DEFAULT_OUT = ROOT / "reports" / "ESTUDIO_MERCADO_REGIMENES.md"
LABELS = ("H", "D", "A")


def odds_triplet(row: pd.Series, avg: tuple[str, str, str], b365: tuple[str, str, str]) -> tuple[float, float, float] | None:
    for columns in (avg, b365):
        if not all(c in row.index for c in columns):
            continue
        values = pd.to_numeric(row[list(columns)], errors="coerce")
        if values.notna().all() and (values > 1.01).all():
            return tuple(float(v) for v in values)
    return None


def probabilities(odds: tuple[float, float, float]) -> tuple[float, float, float]:
    inverse = [1.0 / value for value in odds]
    total = sum(inverse)
    return tuple(value / total for value in inverse)


def regime_rows() -> pd.DataFrame:
    rows: list[dict] = []
    for division_key, division in (("PRIMERA", "Primera"), ("SEGUNDA", "Segunda")):
        for path in sorted((RAW / division_key).glob("SP*.csv")):
            frame = pd.read_csv(path)
            season = path.stem.split("_")[-1]
            season = f"20{season[:2]}-20{season[2:]}"
            for _, row in frame.iterrows():
                result = str(row.get("FTR", "")).strip()
                if result not in LABELS or pd.isna(row.get("Date")):
                    continue
                opening_odds = odds_triplet(row, ("AvgH", "AvgD", "AvgA"), ("B365H", "B365D", "B365A"))
                closing_odds = odds_triplet(row, ("AvgCH", "AvgCD", "AvgCA"), ("B365CH", "B365CD", "B365CA"))
                if opening_odds is None:
                    continue
                opening_probs = probabilities(opening_odds)
                favorite_idx = int(max(range(3), key=lambda i: opening_probs[i]))
                opening_favorite_odds = opening_odds[favorite_idx]
                item = {
                    "season": season,
                    "division": division,
                    "result": result,
                    "open_odds": opening_odds,
                    "open_probs": opening_probs,
                    "open_favorite": LABELS[favorite_idx],
                    "open_favorite_odds": opening_favorite_odds,
                    "open_hit": LABELS[favorite_idx] == result,
                    "has_close": closing_odds is not None,
                }
                if closing_odds is not None:
                    closing_probs = probabilities(closing_odds)
                    close_idx = int(max(range(3), key=lambda i: closing_probs[i]))
                    item.update(
                        close_odds=closing_odds,
                        close_probs=closing_probs,
                        close_favorite=LABELS[close_idx],
                        close_favorite_odds=closing_odds[close_idx],
                        close_hit=LABELS[close_idx] == result,
                        favorite_switched=LABELS[close_idx] != LABELS[favorite_idx],
                        favorite_prob_move=closing_probs[close_idx] - opening_probs[close_idx],
                    )
                rows.append(item)
    return pd.DataFrame(rows)


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def summary(frame: pd.DataFrame, favorite: str, odds: str) -> dict:
    if frame.empty:
        return {"n": 0}
    return {
        "n": int(len(frame)),
        "accuracy": float(frame[f"{favorite}_hit"].mean()),
        "mean_favorite_odds": float(frame[f"{odds}_favorite_odds"].mean()),
    }


def band_table(frame: pd.DataFrame, favorite: str, odds: str) -> list[dict]:
    bins = [(1.01, 1.5, "1.01-1.50"), (1.5, 2.0, "1.50-2.00"), (2.0, 2.5, "2.00-2.50"), (2.5, 3.5, "2.50-3.50"), (3.5, math.inf, "3.50+")]
    output = []
    for lo, hi, label in bins:
        part = frame[(frame[f"{odds}_favorite_odds"] >= lo) & (frame[f"{odds}_favorite_odds"] < hi)]
        output.append({"band": label, **summary(part, favorite, odds)})
    return output


def render(frame: pd.DataFrame) -> str:
    close = frame[frame["has_close"]].copy()
    lines = [
        "# Estudio de regímenes de mercado",
        "",
        "> Análisis walk-forward descriptivo de cuotas de apertura y cierre. No modifica el motor.",
        "",
        "## Resumen",
        "",
        f"- Filas válidas con apertura: **{len(frame):,}**.",
        f"- Filas con cierre real: **{len(close):,}** ({len(close)/len(frame):.2%}).",
        f"- Filas sin cierre real: **{len(frame)-len(close):,}** ({(1-len(close)/len(frame)):.2%}); el motor usa apertura como fallback.",
        "- El análisis no usa estadísticas posteriores al partido ni incorpora variables nuevas.",
        "",
        "## Favorito de mercado por régimen",
        "",
        "| Régimen | División | N | Acierto favorito | Cuota media favorito |",
        "|---|---|---:|---:|---:|",
    ]
    regimes = [("Apertura 2010-2026", frame, "open", "open"), ("Cierre real 2019-2026", close, "close", "close")]
    for name, data, favorite, odds in regimes:
        for division in ("Primera", "Segunda"):
            item = summary(data[data.division == division], favorite, odds)
            lines.append(f"| {name} | {division} | {item.get('n', 0):,} | {pct(item['accuracy']) if item.get('n') else '-'} | {item.get('mean_favorite_odds', 0):.3f} |")
        item = summary(data, favorite, odds)
        lines.append(f"| {name} | **Total** | {item.get('n', 0):,} | **{pct(item['accuracy']) if item.get('n') else '-'}** | {item.get('mean_favorite_odds', 0):.3f} |")

    lines += ["", "## Apertura por bandas de cuota del favorito", "", "| División | Banda | N | Acierto |", "|---|---|---:|---:|"]
    for division in ("Primera", "Segunda", "Total"):
        data = frame if division == "Total" else frame[frame.division == division]
        for item in band_table(data, "open", "open"):
            lines.append(f"| {division} | {item['band']} | {item['n']:,} | {pct(item['accuracy']) if item['n'] else '-'} |")

    lines += ["", "## Cierre frente a apertura", "", "| Métrica | Resultado |", "|---|---:|"]
    if not close.empty:
        lines += [
            f"| Favorito cambia entre apertura y cierre | {int(close.favorite_switched.sum()):,} ({close.favorite_switched.mean():.2%}) |",
            f"| Cierre mejora la elección del favorito | {pct(close.close_hit.mean() - close.open_hit.mean())} puntos relativos |",
            f"| Apertura acierto en muestra con cierre | {pct(close.open_hit.mean())} |",
            f"| Cierre acierto en la misma muestra | {pct(close.close_hit.mean())} |",
            f"| Movimiento medio de probabilidad del favorito de cierre | {close.favorite_prob_move.mean():+.4f} |",
        ]
    lines += [
        "",
        "## Interpretación para dobles",
        "",
        "- Los rangos deben evaluarse con la cuota disponible al corte del boleto; no es válido seleccionar una regla con cierre y aplicarla a una jornada donde solo se conocía apertura.",
        "- La cuota del favorito por sí sola no decide el segundo signo: hay que medir cobertura 1X/X2/12 y P(≥12) con el contrato de tres dobles.",
        "- El siguiente experimento recomendable es un A/B de dobles usando únicamente apertura en 2010-19 y una rama separada con cierre real desde 2019-20.",
        "",
        "## Conclusión provisional",
        "",
        "El dataset sí permite estudiar de forma sólida el comportamiento del mercado y la colocación de dobles. La principal limitación no es el volumen, sino que la disponibilidad de cierre cambia completamente a partir de 2019-20. Antes de integrar cualquier regla nueva hay que controlar ese cambio de régimen.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    frame = regime_rows()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(frame), encoding="utf-8")
    print(f"Filas analizadas: {len(frame)} | cierres reales: {int(frame.has_close.sum())}")
    print(f"Informe: {args.out}")


if __name__ == "__main__":
    main()
