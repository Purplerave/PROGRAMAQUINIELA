# Datos incluidos

- `historico_raw/PRIMERA`: temporadas 2010-11 a 2025-26.
- `historico_raw/SEGUNDA`: temporadas 2010-11 a 2025-26.
- `historico_raw/PRIMERA/SP1_2627.csv` / `historico_raw/SEGUNDA/SP2_2627.csv`: muestra parcial 2026-27, no temporada cerrada.
- `BOLETO_SEMANAL.json`: entrada local no versionada del flujo mixto; ver README.
- `highlightly_dataset/highlightly_partidos_2023_2026.csv`: consolidado usado
  para preparar los priors de la temporada 2026-27.
- `temporada_2026_27_equipos.json`: equipos y transiciones de categoria.
- `temporada_2026_27_estadisticas_base.json`: priors ya preparados.
- `QUINIELA15_J*.json`: jornadas conservadas como ejemplos ejecutables.
- `jornadas_lae/jornadas_lae_*.json`: combinaciones oficiales LAE 2023-2026
  (224 jornadas), reparadas desde HTML cacheado (no versionado).
  Procedencia y estado: ROADMAP 02/08/2026. Base de
  `scripts/backtests/AUDITAR_LAE_VS_HISTORICO.py`.
- `paper_trading_2627.json`: tracker de paper-trading 2026-27 (visitante
  cuota [1.8, 2.5)). Actualizar con `python scripts/datos/PAPER_TRADING_2627.py`.

No se incluyen respuestas crudas de APIs, copias de seguridad ni datasets
experimentales que no sean necesarios para ejecutar este proyecto.
