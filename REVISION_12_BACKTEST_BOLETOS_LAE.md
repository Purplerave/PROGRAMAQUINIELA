# REVISION_12 — Backtest de boletos reales LAE

Fecha: 02/08/2026

## Objetivo

Sustituir el proxy de boletos sintéticos (bloques cronológicos de 15 partidos)
por una ruta reproducible que pueda evaluar boletos oficiales reales de LAE:
orden 1-14, Pleno al 15 separado y validación contra resultados históricos.

## Cambios

- Nuevo dataset mínimo append-only:
  - `DATOS/boletos_lae_reales/LAE_2026-01-25.json`
  - Fuente declarada en el propio JSON: página oficial LAE del 25/01/2026.
  - Caso especial incluido: abreviaturas oficiales (`At. Madrid`, `R. Oviedo`,
    `R. Zaragoza`) y Pleno al 15 como marcador exacto (`Girona - Getafe 1-1`).
- Nuevo script:
  - `scripts/backtests/BACKTEST_BOLETOS_LAE.py`
  - Modo validación: `--solo-validar`.
  - Modo backtest: entrena walk-forward por temporada, empareja el boleto real
    contra predicciones del motor y mide simples, 3 dobles y Pleno al 15.
- Alias ampliados en `scripts/motor/team_names.py`:
  - `At. Madrid` → `Ath Madrid`
  - `R. Oviedo` → `Oviedo`
  - `R. Zaragoza` → `Zaragoza`
- Tests nuevos:
  - `tests/test_backtest_boletos_lae.py`

## Validación de datos

Comando:

```bash
PYTHONPATH=. python scripts/backtests/BACKTEST_BOLETOS_LAE.py --solo-validar
```

Resultado:

```json
{
  "historico": "original",
  "validacion": {
    "tickets": 1,
    "partidos": 15,
    "plenos15": 1,
    "temporadas": ["2025-2026"]
  }
}
```

La validación comprueba:

1. Cada partido existe una única vez en el histórico de la temporada.
2. Los marcadores del JSON coinciden con `FTHG-FTAG` histórico.
3. Los signos 1/X/2 de los partidos 1-14 coinciden con el marcador.
4. El partido 15 se evalúa como Pleno al 15 por marcador exacto, no como 1/X/2.

## Backtest con el caso real disponible

Comando:

```bash
PYTHONPATH=. python scripts/backtests/BACKTEST_BOLETOS_LAE.py --historico original
```

Resultado sobre `LAE_2026-01-25`:

| Métrica | Modelo | Mercado |
|---|---:|---:|
| Aciertos simples 1-14 | 8 | 8 |
| Aciertos con 3 dobles | 8 | 8 |

Pleno al 15:

- Real: `1-1`
- Predicción top-1 DC: `1-0`
- Exacto: no
- Top-3: sí

Dobles seleccionados por el motor en el boleto real: partidos 3, 8 y 12.

## Conclusión

El backtest de boletos reales LAE queda implementado y validado con 1 caso
especial. Por ahora no se extrae conclusión estadística: un único boleto solo
prueba la tubería y el tratamiento correcto del Pleno/alias. La comparación
operativa deberá ampliarse añadiendo más JSON oficiales al directorio
`DATOS/boletos_lae_reales`.
