# REVISION_13 — Backtest LAE temporada 2025-2026 desde Quiniela15

Fecha: 02/08/2026

## Fuente recibida

- Fichero agregado: `DATOS/boletos_lae_fuente/202526.json`.
- Contenido: 75 jornadas Quiniela15 de la temporada 2025-2026.
- Clasificación declarada en la fuente:
  - `espana_liga`: 47 jornadas.
  - `europa`: 17 jornadas.
  - `extranjera`: 11 jornadas.
  - `validable_historico=true`: 47 jornadas.
  - `validable_historico=false`: 28 jornadas.

## Conversión y filtrado

Nuevo script:

```bash
PYTHONPATH=. python scripts/datos/CONVERTIR_FUENTE_BOLETOS_LAE.py --overwrite --validar-historico
```

Resultado:

```json
{
  "escritos": 35,
  "omitidos": 40,
  "errores": {}
}
```

Se materializan únicamente jornadas que pasan validación estricta contra el
histórico local de Primera/Segunda. Se omiten:

- jornadas europeas/extranjeras/selecciones,
- jornadas marcadas como españolas pero con partidos no cubiertos por el histórico,
- jornadas con inconsistencias de marcador frente al histórico.

Los JSON validados se escriben como:

```text
DATOS/boletos_lae_reales/Q15_2025_2026_J*.json
```

## Casos especiales soportados

- Partidos 1-14 resueltos por sorteo/aplazamiento:
  - `resultado: null`
  - `signo: 1/X/2`
  - `tipo: sorteo`
- Signos de Quiniela15 con anotación, por ejemplo:
  - `1** sorteado` → `1`
  - `X** sorteado` → `X`
- En el bloque validado final hay 4 partidos resueltos por sorteo.

## Validación del bloque Q15

Comando:

```bash
PYTHONPATH=. python scripts/backtests/BACKTEST_BOLETOS_LAE.py --solo-validar --pattern 'Q15_*.json'
```

Resultado:

```json
{
  "tickets": 35,
  "partidos": 525,
  "plenos15": 35,
  "sorteos": 4,
  "temporadas": ["2025-2026"]
}
```

## Backtest global sobre boletos reales Q15 validados

Comando:

```bash
PYTHONPATH=. python scripts/backtests/BACKTEST_BOLETOS_LAE.py --historico original --pattern 'Q15_*.json'
```

Resultado agregado:

| Métrica | Modelo | Mercado |
|---|---:|---:|
| Media aciertos simples 1-14 | 7,31 | 7,29 |
| Media aciertos con 3 dobles | 7,97 | 8,11 |

Pleno al 15:

| Métrica | Valor |
|---|---:|
| Exactos top-1 | 5/35 |
| En top-3 | 14/35 |

## Lectura

- El modelo queda ligeramente por encima del mercado en simples sobre boletos
  reales validados: 7,31 vs 7,29 aciertos medios.
- Con la estrategia actual de 3 dobles, el mercado queda por encima: 8,11 vs 7,97.
- El Pleno al 15 alcanza 5 exactos y 14 top-3 sobre 35 jornadas.
- El resultado confirma que la tubería real ya funciona; el siguiente trabajo no
  debe ser cambiar el predictor 1X2 por intuición, sino revisar la selección de
  dobles/optimización sobre boletos reales.
