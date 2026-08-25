# Auditoría de `liga-maestros-web`

Fecha: 25/08/2026

Repositorio auditado:
[Purplerave/liga-maestros-web](https://github.com/Purplerave/liga-maestros-web)

## Dictamen ejecutivo

El repositorio es una fuente operativa útil para jornadas, predicciones y
seguimiento de la web, pero no es por sí solo un histórico completo y
certificado para entrenar `PROGRAMAQUINIELA`.

Contiene JSON públicos de jornadas y predicciones, pero la base SQLite activa
`DATOS/LIGA_MAESTROS_PRO.db` está excluida del repositorio por `.gitignore`.
Por ello, el contenido de GitHub no representa necesariamente todo el estado
real de la aplicación desplegada.

## Inventario relevante del snapshot

### Jornadas y resultados

- `quiniela15_J1_scrape.json`: 15 partidos, temporada `2026-2027`, sin campos
  obligatorios ausentes.
- `quiniela15_J1_resultados.json`: 14 resultados; falta el partido 5 porque
  aparece como aplazado. El partido 15 contiene el marcador del Pleno al 15.
- `quiniela15_J2_scrape.json`: 15 partidos, sin duplicados de número ni de
  pareja local/visitante, pero sin temporada y sin división en los partidos.
- No se encontró `quiniela15_J2_resultados.json` en el snapshot público.

### Predicciones

- `predicciones_J1.json`: 20 entradas de programas/maestros, todas con 15
  signos y `generado_en` global.
- `predicciones_J2.json`: 19 entradas, todas con 15 signos y
  `generado_en=2026-08-19T12:00:00+02:00`.
- J2 incluye el boleto del Programa, pero su nota indica que fue volcado desde
  `tools/PROGRAMA_QUINIELA/SALIDAS/quiniela_programa_J2.json`.
- Los JSON no declaran de forma homogénea `odds_observed_at`,
  `prediction_cutoff_at` y `kickoff_at` por partido. El timestamp global de
  generación no sustituye a esa trazabilidad.

### Datos históricos y runtime

- `HISTORIAL_JORNADAS_DETALLADO.json` contiene solo las claves J46, J48, J50,
  J51 y J75 en el snapshot.
- `RESULTADOS_MAESTROS.json` contiene solo J75.
- El repositorio incluye datos de J75 y J76, además de J1/J2. J75/J76 deben
  tratarse como datos de otro contexto o futuro hasta verificar temporada,
  fuente y estado.
- `data/` contiene estados, horarios, standings, predicciones y resultados
  auxiliares, pero no constituye un esquema histórico único.

## Problemas de calidad o gobernanza

1. **Base viva ausente de GitHub**: la SQLite está ignorada. No se puede
   certificar desde el repositorio público que los JSON coinciden con la base
   desplegada.
2. **J2 incompleta para evaluación**: hay fixture y predicciones, pero no un
   resultado oficial público en el nombre esperado.
3. **Temporada/división incompletas en J2**: deben completarse desde una fuente
   oficial o marcarse como no auditadas; no inferirse silenciosamente.
4. **Timestamps insuficientes**: `generado_en` indica cuándo se escribió el
   fichero, no necesariamente cuándo se observaron las cuotas ni cuándo se
   cerró cada boleto.
5. **Fuentes heterogéneas**: conviven scrapeos de Quiniela15, datos de
   Highlightly, JSON manuales y datos de participantes IA. No deben mezclarse
   sin conservar `source_url`, `scraped_at` y estado de verificación.
6. **Resultados aplazados**: J1 no debe evaluarse como una jornada completa de
   15 hasta resolver el partido aplazado con fuente oficial.

## Qué sí puede usarse

- Fixture oficial de una jornada, después de validar 15 números y fechas.
- Predicciones congeladas antes del cierre, si tienen hora verificable.
- Resultados finalizados con fuente y estado `FT`.
- Comparación entre Programa, Maestros y Peña como experimento de la web.

## Qué no debe hacerse

- No sustituir `DATOS/historico_raw` por el contenido de este repositorio.
- No usar J2 para reentrenar el modelo.
- No calcular rendimiento de J2 sin resultados oficiales completos.
- No tratar `generado_en` como timestamp de cuotas.
- No mezclar J75/J76 con 2026-27 sin verificar su temporada.
- No reconstruir una jornada agrupando partidos por fecha: usar el número
  oficial de jornada.

## Siguiente integración recomendada

Crear un adaptador de solo lectura que produzca un registro canónico:

```text
temporada
jornada_oficial
num_partido
local
visitante
division
fecha
hora
source_url
scraped_at
odds_observed_at
prediction_cutoff_at
kickoff_at
prediccion_programa
resultado
estado_resultado
```

El adaptador debe rechazar jornadas incompletas, duplicados, temporadas
ausentes y timestamps no auditables. La base SQLite viva solo debe usarse si
se obtiene un backup explícitamente autorizado y se comprueba su integridad.

## Conclusión

`liga-maestros-web` es una buena fuente de operación y de paper-trading, no un
reemplazo del histórico de entrenamiento. Para las jornadas 2026-27 se debe
usar como fuente de fixture/predicción/resultados, con un adaptador y una
auditoría separada. J1 está parcialmente validada; J2 todavía necesita su
resultado oficial completo y metadatos de temporada/división.

## Revisión de los commits posteriores de enriquecimiento

Se revisaron `e0238c5` y `45bac91` después de la auditoría inicial.

### Hallazgos bloqueantes

1. `DATOS/paper_trading_2627.json` sigue teniendo `n_filas_totales=0` y no
   contiene `odds_observed_at`, `prediction_cutoff_at` ni `kickoff_at` en sus
   columnas. Por tanto, todavía no es un registro real de paper-trading con
   timestamps.
2. `scripts/datos/ADAPTAR_HIGHLIGHTLY.py` declara que genera un CSV histórico
   en `DATOS/historico_raw/HIGHLIGHTLY_ENRIQUECIDO/` con 119 columnas, pero el
   archivo commiteado está en `DATOS/highlightly_enriquecido/` y conserva el
   esquema original de 9 columnas (`date`, `datetime_utc`, `league`, `home`,
   `away`, `score`, `sign`, `home_id`, `away_id`). El artefacto commiteado no
   es reproducible con el script tal como está.
3. El archivo Highlightly commiteado no contiene una columna `market_source`.
   La etiqueta aparece solo en el texto de consola del script; no queda
   almacenada en las filas.
4. No se encontró una integración del archivo enriquecido en
   `load_raw_history`, `rolling_team_features` o el entrenamiento del motor.
   En consecuencia, la frase “enriquece Elo/forma” describe una posibilidad,
   no un efecto actualmente activo en producción.
5. `DESCARGAR_FOOTBALL_DATA_2526.py` no verifica hash, número de partidos,
   temporada ni existencia de las tripletas de apertura/cierre cuando los CSV
   ya existen; solo evita sobrescribirlos. Eso no basta para certificar el
   pipeline 25/26.

### Estado corregido

Los commits `e0238c5` y `45bac91` no han demostrado una mejora del motor ni
han activado el enriquecimiento en producción. La suite y el backtest siguen
siendo válidos, pero el árbol no debe declararse completamente auditado hasta
resolver las discrepancias anteriores. Tras este informe queda además un
archivo de auditoría local pendiente de incluir o descartar antes de publicar.
