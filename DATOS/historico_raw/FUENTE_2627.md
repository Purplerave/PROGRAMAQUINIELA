# Fuente de SP1_2627.csv y SP2_2627.csv

- **Origen**: Highlightly Football API (plan PRO del fundador), descargado el 08/09/2026.
- **Contenido**: 41 partidos de Primera (15/08/2026–07/09/2026, jornadas 1–4 + adelanto R.Sociedad–Celta del 03/09) y 44 de Segunda (14/08/2026–07/09/2026, jornadas 1–4). Todos con marcador final.
- **Cuotas**: columnas `AvgH/AvgD/AvgA` = media aritmética del mercado prematch "Full Time Result" entre todas las casas disponibles (35–49 por partido). **No hay cuotas de cierre**: `odd_*` y `open_*` beben de la misma media (`market_close_available=false` en estas 85 filas; los features de movimiento de línea leen cero aquí).
- **Tiros**: `HS/HST/AS/AST` desde el endpoint `/statistics` (HS = a puerta + fuera + bloqueados). Verificado por conciliación contra tiros por jugador del endpoint `/matches/{id}` en 3 partidos (12/12, 3/3+25/25, 11/11+15/15).
- **Nombres**: mapeados a convención football-data (`Athletic Club→Ath Bilbao`, `Racing Santander→Santander`, `Rayo Vallecano→Vallecano`, `Real Sociedad→Sociedad`, `Atlético Madrid→Ath Madrid`, etc.). Equipos nuevos sin histórico previo: `Celta B` (Celta Fortuna), `Eldense`, `Sabadell`.
- **Validación**: `load_raw_history` carga las 85 filas sin NaN en cuotas; `SANEAR_DATOS` las acepta al 100% (cero exclusiones, cero sospechosas); pytest 292/292 con conteos actualizados.
- **Script**: pull + conversión puntuales en `/tmp` (no commiteados); la key de Highlightly NO está en ningún repo.
