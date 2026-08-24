# REVISION_17 · Segundo signo del doble por cobertura de banda

> 2026-08-24. Contrato intacto: **3 dobles = 8 columnas = 6,00 EUR**.

## Regla pre-registrada

Solo cambia el **segundo signo** cuando el partido es uno de los 3 dobles:

| Banda de cuota | Doble | Por qué |
|---|---|---|
| Visitante [2.5, 4.0) | **1X** | Cubre 70.8 % / 72.7 % (2010-19 / 2019-26). Visita sobrepagada. |
| Local [1.4, 1.8) | **1X** | Cubre 84.4 % / 85.5 %. |
| Visitante [1.8, 2.5) | no forzar | Régimen post-2020; paper-trading. |

Racha visitante ≥3: **cerrada** (ROI −15.3 % en 2010-19).

## Aceptación (walk-forward 2019-26, mercado + calibrador)

`python scripts/backtests/BACKTEST_COBERTURA_DOBLES.py`

Media 3 dobles: **8.469 → 8.485** (Δ +0.015). Acepta (≥ −0.1).
2020-21 baja −0.14 (ruido de temporada); 2021-22 sube +0.20. Acc simple no cambia
(solo el segundo signo).

## Dónde

- `scripts/motor/cobertura_bandas.py`
- `MOTOR_QUINIELA_MAESTRO.build_double` (backtest)
- `OPTIMIZADOR_COLUMNAS.build_double_development` (boleto de jornada)
- `CONFIG_MOTOR_V2.json` → `cobertura_dobles_banda.enabled`

No hay 4º doble. No hay triple. No hay boost de empate.
