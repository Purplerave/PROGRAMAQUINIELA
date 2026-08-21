# Datos incluidos

- `historico_raw/PRIMERA`: temporadas 2010-11 a 2026-27 (la 2026-27 en curso,
  generada con `scripts/datos/GENERAR_HISTORICO_2026_27.py` desde el feed de
  football-data.co.uk; ver `REVISION_15_DATOS_2026_27.md`).
- `historico_raw/SEGUNDA`: temporadas 2010-11 a 2026-27 (ídem).
- `highlightly_dataset/highlightly_partidos_2023_2026.csv`: consolidado usado
  para preparar los priors de la temporada 2026-27.
- `temporada_2026_27_equipos.json`: equipos y transiciones de categoria.
- `temporada_2026_27_estadisticas_base.json`: priors ya preparados.
- `QUINIELA15_J*.json`: jornadas conservadas como ejemplos ejecutables.
  `QUINIELA15_J1.json` y `QUINIELA15_J2.json` corresponden a la temporada
  2026-27 (la J2 incluye cuotas 1X2 medias de mercado vía OddsPortal).

No se incluyen respuestas crudas de APIs, copias de seguridad ni datasets
experimentales que no sean necesarios para ejecutar este proyecto.
