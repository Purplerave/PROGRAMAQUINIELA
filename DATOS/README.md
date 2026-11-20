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
- `ligaf/liga_f_partidos_2023-27.csv`: resultados multitemporada de Liga F
  aportados por usuario, con procedencia/licencia pendiente de confirmar;
  se reconcilian con el backbone StatsBomb 2023/24 al cargar el motor.

No se incluyen respuestas crudas de APIs, copias de seguridad ni datasets
experimentales que no sean necesarios para ejecutar este proyecto.

## Procedencia y licencias

`DATOS/PROCEDENCIA_DATOS.json` es el manifiesto legible por máquina de cada
fuente: origen, URL, licencia, estado (`verificada`, `no_verificada`,
`prohibida_redistribucion`), atribución, fecha de captura y SHA-256 de los
archivos inmutables. Se comprueba en CI con:

```bash
python scripts/datos/VERIFICAR_PROCEDENCIA.py            # falla si algo no cuadra
python scripts/datos/VERIFICAR_PROCEDENCIA.py --json salida/procedencia.json
python scripts/datos/VERIFICAR_PROCEDENCIA.py --actualizar  # refresca hashes
```

Siete de las nueve fuentes están **sin licencia verificada**. Esto significa:

- no se amplían con más descargas ni se presentan como base de una afirmación
  de producción;
- sus rutas figuran en `.gitattributes` con `export-ignore`, de modo que
  `git archive`, los ZIP de release y los paquetes publicables no las incluyen;
- si se necesita cerrar el tema por completo, hay que reescribir el historial
  con `git filter-repo` (ver `reports/MEJORA_AUDITORIA_2026-11-20.md`).

Ningún resultado histórico del proyecto se apoya en una licencia supuesta: la
cifra de referencia solo es reproducible mientras los datos estén presentes en
la copia de trabajo, que es un uso interno.
