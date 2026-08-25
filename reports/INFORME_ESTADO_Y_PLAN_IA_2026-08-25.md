# Informe de estado y plan para la otra IA

Fecha: 25/08/2026  
Proyecto: `PROGRAMAQUINIELA`  
Repositorio operativo relacionado: `Purplerave/liga-maestros-web`

## 1. Objetivo

Dejar el motor local reproducible, trazable y listo para trabajar la temporada
2026-27. La prioridad no es perseguir una mejora aparente en el histórico,
sino demostrar cualquier mejora fuera de muestra y registrar correctamente las
jornadas reales.

## 2. Estado actual

La versión local ya tiene una base estable:

- Suite: `290 passed`; los avisos de pytest son cosméticos/conocidos.
- Backtest walk-forward: 7 temporadas y 842 partidos por temporada.
- Motor: `50,2715 %`.
- Mercado: `49,8303 %`.
- Media con tres dobles: `8,4770/15`.
- Diferencial motor-mercado: aproximadamente `+0,44 puntos porcentuales`.
- McNemar: `p=0,0436`; el intervalo bootstrap es estrecho y roza el cero,
  por lo que no debe presentarse como superioridad definitiva.
- Elo experimental con reversión: rechazado; queda apagado por defecto.
- Las bandas y la cobertura usan cuotas de apertura cuando existen.
- La trazabilidad temporal no inventa horas: si faltan, marca `no_auditado`.
- El split del backtest es por fecha y no deja días compartidos entre train y
  test.
- `market_source` y metadatos de régimen no entran accidentalmente como
  features del modelo.

Commits estables conocidos, en orden descendente:

```text
7a66583  Actualiza referencia tras correccion trazabilidad
a41bd8d  Corrige trazabilidad: highlightly con market_source, verifica 25/26, paper_trading con timestamps
45bac91  Actualiza referencia reproducible tras enriquecido
e0238c5  Mejor programa quinielas: enriquecido highlightly + pipeline 25/26 apertura/cierre
fe21813  Actualiza referencia reproducible de produccion
23943bf  Estabiliza motor, trazabilidad y validacion walk-forward
```

## 3. Qué quedó corregido en los últimos commits

### Highlightly

`DATOS/highlightly_enriquecido/SP1_SP2_highlightly_2326.csv` es ahora un
artefacto auxiliar reproducible de 2.537 partidos, con 10 columnas y
`market_source=no_auditado`. Conserva `datetime_utc`, pero no contiene cuotas
auditadas.

Importante: `use_highlightly_enrichment=false` sigue desactivado. Por tanto,
Highlightly no está mejorando actualmente Elo, forma ni el backtest de
producción. No activar esta integración sin un A/B walk-forward.

### Football-Data 2025-26

Los ficheros `SP1_2526.csv` y `SP2_2526.csv` existen y se verifican en número
de partidos, hash y presencia de cabeceras de apertura/cierre. Esta comprobación
es estructural; todavía conviene añadir una comprobación fila a fila de que las
tripletas de cuotas no estén vacías o incompletas antes de llamarlo certificado.

### Paper-trading 2026-27

`DATOS/paper_trading_2627.json` ya tiene columnas para:

- `odds_observed_at`;
- `prediction_cutoff_at`;
- `kickoff_at`;
- `source_url` y `scraped_at`;
- estado del resultado y beneficio simulado.

Está vacío (`n_filas_totales=0`). Esto es correcto mientras no haya resultados
oficiales completos, pero significa que aún no existe evidencia de paper-trading.

## 4. Auditoría de `liga-maestros-web`

El repositorio web sirve como fuente operativa de fixtures, predicciones y
resultados, pero no sustituye al histórico de entrenamiento de
`PROGRAMAQUINIELA`.

Hallazgos relevantes:

- J1 tiene fixture de 15 partidos y 14 resultados porque un partido fue
  aplazado.
- J2 tiene fixture y predicciones, pero en el snapshot auditado no aparece un
  resultado oficial completo.
- J2 no declara de forma completa temporada y división.
- La SQLite viva está excluida de GitHub; los JSON públicos no garantizan que
  coincidan con la base desplegada.
- `generado_en` no equivale a hora de observación de cuotas.
- J75/J76 no deben mezclarse con 2026-27 hasta verificar temporada, fuente y
  estado.

Conclusión: usar `liga-maestros-web` para seguimiento de la temporada y
paper-trading, no para sustituir `DATOS/historico_raw` ni para reentrenar con
J2 antes de cerrar la auditoría.

## 5. Pasos exactos para la otra IA

### Paso 1 — Crear una fotografía nueva

Ejecutar desde `PROGRAMAQUINIELA` y guardar el resultado en un informe:

```powershell
git status --short
git log --oneline -10
git diff --check
.\.venv\Scripts\python.exe -m pytest -q
```

Si la suite no da 290 tests pasados, detenerse y diagnosticar antes de tocar el
motor.

### Paso 2 — Validar el estado de datos

Ejecutar los validadores existentes y guardar sus salidas:

```powershell
.\.venv\Scripts\python.exe scripts\datos\VALIDAR_DATASETS.py
.\.venv\Scripts\python.exe scripts\datos\DESCARGAR_FOOTBALL_DATA_2526.py
```

Además, implementar o ejecutar una comprobación fila a fila para SP1/SP2 25-26:

- número de partidos esperado;
- fechas válidas;
- `FTR` válido;
- apertura completa `B365H/B365D/B365A`;
- cierre completo `B365CH/B365CD/B365CA`;
- ausencia de duplicados local/visitante/fecha;
- hash SHA-256 y origen documentado.

No modificar los CSV originales durante esta comprobación.

### Paso 3 — Congelar la jornada real

Para cada jornada 2026-27, importar desde `liga-maestros-web` un registro
canónico con:

```text
temporada, jornada_oficial, num_partido, local, visitante, division,
fecha, hora, source_url, scraped_at, odds_observed_at,
prediction_cutoff_at, kickoff_at, prediccion_programa,
resultado, estado_resultado
```

Rechazar el lote si hay números duplicados, partidos duplicados, temporada
ausente, timestamps inventados o resultado incompleto. Los aplazados deben
quedar como `aplazado`, no como fallo del modelo.

### Paso 4 — Activar paper-trading solo con trazabilidad

Antes del primer pronóstico de cada jornada:

1. Guardar el fixture y su `source_url`.
2. Guardar las cuotas observadas y `odds_observed_at`.
3. Fijar `prediction_cutoff_at`.
4. Verificar `odds_observed_at <= prediction_cutoff_at < kickoff_at`.
5. Guardar el boleto congelado.
6. Tras los partidos, importar solo resultados oficiales con estado `FT`.
7. Calcular aciertos y `profit_1u` sin reescribir la predicción original.

No llamar “resultado del paper-trading” a un JSON vacío ni a una jornada sin
resultado completo.

### Paso 5 — Evaluar la temporada de forma secuencial

Después de cada jornada, generar un informe acumulado con:

- aciertos del Programa;
- aciertos del mercado/favorito;
- aciertos de Maestros y Peña, si sus predicciones están congeladas;
- número de partidos evaluables;
- aplazados y partidos pendientes;
- cobertura de timestamps;
- tres dobles y composición del boleto;
- Brier/log-loss solo cuando haya probabilidades comparables.

No reentrenar ni cambiar pesos por una sola jornada. Hacer una revisión
intermedia cuando haya al menos 70 partidos evaluables y una evaluación final
con al menos 120, manteniendo la regla congelada.

### Paso 6 — Experimentos futuros, solo en ramas o copias

Solo proponer cambios de motor si existe una hipótesis concreta. Para cada uno:

1. escribir la hipótesis antes de probarla;
2. ejecutar A/B walk-forward con el mismo corte temporal;
3. comparar contra el mercado;
4. medir acierto, Brier, log-loss, dobles y estabilidad por temporada/división;
5. registrar p-value o intervalo bootstrap;
6. mantener el cambio apagado si no mejora fuera de muestra.

Experimentos autorizados para estudiar, no para activar automáticamente:

- integración de Highlightly como enriquecimiento de forma/Elo;
- redefinición de `market_move_*` usando última cuota menos apertura;
- mejora de normalización de nombres y divisiones;
- validación de avisos de pytest.

### Paso 7 — Cierre de cada ciclo

Actualizar:

- `reports/AUDITORIA_COMPLETA_DATOS.md`;
- `reports/ESTUDIO_DATASETS_LMARENA.md`, si aparecen datos nuevos;
- `reports/production_reference.json`;
- este informe, con fecha y cifras nuevas;
- registro de experimentos.

Después ejecutar suite, backtest, `git diff --check` y comprobar que no hay
credenciales, cachés ni archivos temporales versionados.

## 6. Pendientes reales, por prioridad

1. Incluir este informe y el informe de auditoría web en el siguiente commit,
   si se quiere conservar la evidencia en Git.
2. Regenerar `production_reference.json` después del commit final para que el
   hash y el estado del árbol sean coherentes.
3. Completar la comprobación fila a fila de cuotas 25-26.
4. Obtener y archivar el resultado oficial completo de J2, incluyendo el
   aplazado si procede.
5. Empezar paper-trading real jornada a jornada.
6. No activar Highlightly en producción hasta un A/B walk-forward positivo.
7. No publicar ni hacer `git push` hasta que los checks anteriores estén verdes.

## 7. Criterio de finalización

La otra IA puede declarar el ciclo terminado únicamente cuando:

- los 290 tests pasan;
- el backtest reproduce `50,2715 % / 49,8303 % / 8,4770` o documenta una
  variación justificada;
- los datos nuevos tienen fuente, hash y timestamps;
- la jornada evaluada está completa o sus aplazados están marcados;
- el paper-trading conserva las predicciones originales;
- cualquier cambio de motor tiene A/B walk-forward;
- la referencia de producción coincide con el código y el commit final;
- `git status --short` queda limpio salvo artefactos ignorados.

## Dictamen

El motor está en estado estable para publicar localmente y comenzar el registro
de 2026-27. Lo siguiente no es seguir cambiando el modelo a ciegas: es cerrar la
trazabilidad de datos, iniciar paper-trading real y acumular jornadas suficientes
para saber si la ventaja histórica se mantiene.
