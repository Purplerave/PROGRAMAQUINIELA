# Integración del histórico multitemporada de Liga F

**Fecha:** 19 de noviembre de 2026
**Estado:** integrado en el loader del modelo Liga F; resultados del adjunto trazados como fuente aportada por el usuario, todavía no verificada independientemente.

## Cambios

- Se añadió `DATOS/ligaf/liga_f_partidos_2023-27.csv` y un manifiesto con su SHA-256, recuentos y procedencia conocida. No se atribuye proveedor ni licencia: no venían en el archivo.
- `cargar_dated()` combina ese histórico con StatsBomb 2023/24. Compara partido por fecha y equipos canónicos, conserva una sola fila cuando coinciden los goles y se detiene si hay discrepancias. Resultado de conciliación: **240/240 fixtures de 2023/24 coinciden, 0 diferencias de marcador**.
- Se corrigió la canonización de `Levante UD Femenino` para que coincida con `Levante`, sin confundirlo con `Levante Las Planas` ni `FC Badalona`.
- Se detectó y corrigió que el hash del CSV StatsBomb 2023/24 no coincidía con su manifiesto; se añadió una prueba que verifica los hashes de ambas fuentes.
- El CSV adjunto se normalizó de BOM/CRLF a UTF-8/LF sin cambiar valores; el manifiesto conserva tanto el hash recibido como el hash del archivo normalizado.
- El cargador valida columnas, temporada derivada de la fecha, estado final, IDs, partidos repetidos, nombres y goles no negativos. Los partidos no finalizados se excluyen.
- `walkforward()` ahora desglosa las métricas por temporada, manteniendo la regla de predecir el día completo antes de incorporar resultados del mismo día.
- El backtest histórico antiguo de StatsBomb queda reproducible mediante `cargar_statsbomb_2324()` y `BACKTEST_LIGAF_2324.py`. Se añadió `BACKTEST_LIGAF_MULTITEMPORADA.py` y el comando `make ligaf-backtest`; `make audit` ejecuta ambos backtests de fútbol.

## Cobertura y calidad observada

| Temporada | Partidos | Estado |
|---|---:|---|
| 2023-24 | 240 | Completa; conciliada con StatsBomb. |
| 2024-25 | 240 | 16 equipos con 30 partidos cada uno. |
| 2025-26 | 240 | 16 equipos con 30 partidos cada uno. |
| 2026-27 | 87 | Parcial al 15/11/2026; 14 equipos con 11 partidos y Alavés/Tenerife con 10. |

El archivo tiene 807 filas, estado `Full Time` en todas, fechas y marcadores presentes, cero IDs repetidos, cero fixtures duplicados dentro de la fuente y cero marcadores negativos. Hay 48 campos de goleadoras vacíos; 47 son partidos 0-0 y uno corresponde a Granadilla Tenerife 0-1 Levante. El modelo actual usa resultado y goles de equipo, no goleadoras. No hay cuotas, tiros, xG, alineaciones ni información para validar ventaja de mercado.

**Procedencia/uso:** `provider`, URL y licencia son desconocidos. El manifiesto conserva expresamente ese estado. No redistribuir los datos fuera del proyecto hasta confirmar autorización.

## Evaluación walk-forward

Protocolo: ajuste antes de cada bloque diario y predicción de todos los partidos de esa fecha sin resultados de ese día. 60 partidos de warm-up; reajuste según la regla existente. Evaluados **747 partidos** en total; no se usan cuotas y no existe benchmark de mercado para esta fuente.

| Temporada | n evaluados | Acierto Dixon–Coles | Siempre local | Log-loss DC | Log-loss frecuencias previas |
|---|---:|---:|---:|---:|---:|
| 2023-24 | 180 | 58,89 % | 42,78 % | 0,8571 | 1,0703 |
| 2024-25 | 240 | 56,25 % | 41,67 % | 0,9407 | 1,0690 |
| 2025-26 | 240 | 60,42 % | 39,58 % | 0,8556 | 1,0637 |
| 2026-27 parcial | 87 | 56,32 % | 42,53 % | 0,9660 | 1,0731 |
| **Global** | **747** | **58,23 %** | **41,37 %** | **0,8961** | **1,0681** |

Estos resultados son diagnóstico retrospectivo de una fuente parcialmente no verificada, con un baseline simple; **no prueban ventaja prospectiva ni frente a cuotas**. No se ajustaron pesos para maximizar estas métricas. La salida de reproducción guarda los hashes de entrada y cada métrica por temporada en `SALIDAS/backtest_ligaf_multitemporada.json`.

## Verificación

- Pruebas focalizadas para dataset Liga F, integridad temporal y flujo semanal: aprobadas.
- Suite completa posterior a la integración: **366 pruebas aprobadas**.
- `make audit`: lint selectivo, QA de datasets, suite/cobertura, backtest masculino y backtest Liga F.
- La cobertura combinada del proyecto pasó de 67 % a **68 %**; `scripts/motor/ligaf_model.py` quedó en 82 %.
- Backtest legado 2023/24: se mantuvo exactamente en 180 predicciones, 58,89 % de acierto y log-loss 0,8571.

Reproducir desde la raíz:

```bash
make ligaf-backtest
make audit
```
