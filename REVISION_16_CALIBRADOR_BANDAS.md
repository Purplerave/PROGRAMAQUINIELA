# REVISION_16 · Integración del calibrador de bandas + paper-trading 2026-27

> Fecha: 2026-08-24. Protocolo: walk-forward, factores solo con temporadas
> previas, sin reoptimizar umbrales. Misiones A y B del HANDOFF_LMARENA.

## 1. Qué se integró

El módulo `scripts/motor/calibrador_bandas.py` (stdlib + pandas) se aplica
**después** del ensemble y **antes** de la predicción argmax / dobles
(`apply_hybrid_config` en `MOTOR_QUINIELA_MAESTRO.py`).

Bloque en `CONFIG_MOTOR_V2.json`:

- `enabled: true`
- ventana 6 temporadas, CAP ±10 %
- bandas visita [2.5, 4.0) y local [1.4, 1.8)
- boost favorito entre-semana +2 pp
- `factores_produccion_2026_27` congelados (visita 0.90, local 1.063)

En cada `run_season_backtest` los factores se reestiman con el **train**
(temporadas anteriores) y se inyectan en la config de esa temporada.

## 2. Aceptación (REVISION_15 §5.3)

Script: `python scripts/backtests/BACKTEST_CALIBRADOR_BANDAS.py`

Comparación mercado 100 % ± calibrador, 7 temporadas 2019-26 (mismo pipeline
de dobles del motor). El HGB no se reentrena: el calibrador es un post-proceso
del ensemble; reentrenar HGB no cambia el A/B de esta capa.

| Métrica (media 7 temp.) | sin | con | Δ |
|---|---|---|---|
| Brier | 0.6030 | 0.6025 | **−0.00048** |
| Logloss | 1.0073 | 1.0066 | **−0.00074** |
| Acc simple | 49.83 % | 49.76 % | −0.068 pp |
| Media 3 dobles | 8.485 | 8.469 | −0.015 |

**Criterio: ACEPTA** (Brier y logloss mejoran; acc y dobles no empeoran más
de −0.1 pp / −0.1 hits).

Honestidad: la ganancia es de **décimas de Brier**, como advertía REVISION_15.
En 2025-26 los dobles caen −0.20 (ruido de temporada); la media OOS cumple.

Walk-forward del módulo puro (cuotas Pinnacle/B365, 13 temp.): Brier mejora
en 9/13 y en 6/7 de 2020+ (reproducido).

## 3. Paper-trading 2026-27 (Misión B)

Regla **pre-registrada**: 1 u. virtual al visitante si cuota de cierre ∈ [1.8, 2.5).
Opcional (no decide): local [1.4, 1.8).

- Tracker: `DATOS/paper_trading_2627.json` (+ CSV local; `DATOS/*.csv` no se versiona)
- Actualizar: `python scripts/datos/PAPER_TRADING_2627.py`
- Fuente: football-data.co.uk `2627/SP1.csv`
- Corte intermedio enero 2027 (n≈70); final junio 2027 (n≈120-140)
- ROI ≥ +5 % y n suficiente → banda extra con CAP. ROI ≤ 0 → cerrar señal.

A 2026-08-24 la temporada 26/27 aún no tiene CSV público usable desde este
entorno (SSL/EOF o fichero vacío). El tracker queda montado con n=0.

## 4. Lo que NO se tocó

- Pesos del ensemble (0.951 / 0.049)
- `draw_boost` = 0
- Señales esotéricas (cerradas)
- Banda visita 1.8–2.5 **no** entra al calibrador hasta el paper-trading
- Reparto público (Misión C) pendiente

## 5. Reproducción

```bash
python scripts/motor/calibrador_bandas.py DATOS/historico_raw
python scripts/backtests/BACKTEST_CALIBRADOR_BANDAS.py
python -m pytest tests/test_calibrador_bandas.py -q
python scripts/datos/PAPER_TRADING_2627.py
```

Ningún resultado garantiza rentabilidad futura.
