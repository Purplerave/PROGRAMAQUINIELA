# Datos de Liga F

## Histórico empleado por el modelo

`scripts.motor.ligaf_model.cargar_dated()` combina:

1. `ligaf_resultados_2324_dated.csv`, backbone de StatsBomb Open Data 2023/24, con procedencia/licencia en `MANIFIESTO_FUENTES.json`.
2. `liga_f_partidos_2023-27.csv`, fichero recibido como adjunto del usuario el 19/11/2026. El proveedor, URL de origen y licencia **no fueron indicados ni verificados**. Su huella SHA-256 y recuentos están en `liga_f_partidos_2023-27_manifest.json`.

La temporada 2023/24 aparece en ambas fuentes. El cargador une los nombres de equipo canónicos y exige que fecha, local, visitante y marcador coincidan; ante cualquier conflicto detiene la carga. No duplica esos 240 partidos. Las otras temporadas amplían el histórico. El orden temporal se conserva y `walkforward` pronostica todos los encuentros del día antes de incorporar los resultados de ese día.

Recuento validado al integrar el archivo:

- 2023/24: 240 partidos (completo; reconciliado 240/240 con StatsBomb).
- 2024/25: 240 partidos (30 por equipo).
- 2025/26: 240 partidos (30 por equipo).
- 2026/27: 87 partidos al 15/11/2026; temporada en curso, con Alavés y Tenerife a 10 partidos y los otros equipos a 11. No tratar como temporada completa.

El modelo usa exclusivamente fecha, equipos y goles finales. La columna de goleadoras no entra en el ajuste y tiene al menos una ausencia en un partido con goles. Este archivo no contiene cuotas, tiros, xG ni alineaciones.

## Reproducción

```bash
make ligaf-backtest
# o indicar una ruta distinta para el informe
python scripts/backtests/BACKTEST_LIGAF_MULTITEMPORADA.py --out /tmp/ligaf-backtest.json
```

El JSON contiene métricas walk-forward globales y por temporada, rango temporal, hashes de ambas fuentes y su estado de procedencia. Es una evaluación retrospectiva del histórico; no demuestra ventaja futura ni ventaja sobre el mercado. Antes de redistribuir los datos adjuntos, confirmar permiso y licencia con quien los proporcionó.
