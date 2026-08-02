# Datos incluidos

- `historico_raw/PRIMERA`: temporadas 2010-11 a 2025-26.
- `historico_raw/SEGUNDA`: temporadas 2010-11 a 2025-26.
- `highlightly_dataset/highlightly_partidos_2023_2026.csv`: consolidado usado
  para preparar los priors de la temporada 2026-27.
- `temporada_2026_27_equipos.json`: equipos y transiciones de categoria.
- `temporada_2026_27_estadisticas_base.json`: priors ya preparados.
- `QUINIELA15_J*.json`: jornadas conservadas como ejemplos ejecutables.
- `jornadas_historicas_2023_2026.json`: 129 jornadas reales de fin de semana
  (2023-2026) reconstruidas desde Highlightly con `CONSTRUIR_JORNADAS_HISTORICAS.py`
  (agrupación por sábado ancla; evaluadas con `BACKTEST_JORNADAS_REALES.py`).
- `jornadas_lae_muestra/`: 3 boletos oficiales de La Quiniela (15 partidos,
  premios y recaudación) validados a mano; formato idéntico al que genera
  `COSECHAR_JORNADAS_LAE.py` en `jornadas_lae/`.

No se incluyen respuestas crudas de APIs, copias de seguridad ni datasets
experimentales que no sean necesarios para ejecutar este proyecto.
La cosecha completa de boletos (`DATOS/jornadas_lae/`) se genera con
`python scripts/datos/COSECHAR_JORNADAS_LAE.py` (requiere internet).
