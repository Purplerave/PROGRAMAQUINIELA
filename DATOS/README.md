# Datos incluidos

- `historico_raw/PRIMERA`: temporadas 2010-11 a 2025-26.
- `historico_raw/SEGUNDA`: temporadas 2010-11 a 2025-26.
- `highlightly_dataset/highlightly_partidos_2023_2026.csv`: consolidado usado
  para preparar los priors de la temporada 2026-27.
- `temporada_2026_27_equipos.json`: equipos y transiciones de categoria.
- `temporada_2026_27_estadisticas_base.json`: priors ya preparados.
- `QUINIELA15_J*.json`: jornadas conservadas como ejemplos ejecutables.
- `mercado_jornada/MERCADO_J*.json`: cuotas reales 1X2 y porcentajes LAE por
  jornada, con proveedor y fecha de snapshot. Es el overlay que consume
  `scripts/datos/IMPORTAR_JORNADA_WEB.py`; el scrape de la web no los trae.

No se incluyen respuestas crudas de APIs, copias de seguridad ni datasets
experimentales que no sean necesarios para ejecutar este proyecto.
