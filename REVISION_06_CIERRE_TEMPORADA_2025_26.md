# REVISION 06: cierre de la temporada 2025-26

Fecha de revision: 2026-07-29

## 1. Objetivo y alcance

Esta revision comprueba si los historicos de Primera y Segunda 2025-26
pueden considerarse temporadas cerradas.

Es una auditoria de solo lectura. No se han modificado CSV, modelos,
configuraciones, pesos ni salidas del motor. La temporada 2026-27 no se
incorpora porque todavia no ha comenzado.

## 2. Dictamen

La temporada 2025-26 **no esta cerrada en el dataset**.

| Division | Equipos | Partidos disponibles | Partidos esperados | Faltan |
|---|---:|---:|---:|---:|
| Primera | 20 | 300 | 380 | 80 |
| Segunda | 22 | 374 | 462 | 88 |
| **Total** | 42 | **674** | **842** | **168** |

Los 674 partidos usados por el backtest de ultima temporada coinciden con
todo el corte almacenado, pero no con las dos temporadas completas.

## 3. Archivos revisados

- `DATOS/historico_raw/PRIMERA/SP1_2526.csv`
- `DATOS/historico_raw/SEGUNDA/SP2_2526.csv`

| Division | Primera fecha | Ultima fecha almacenada |
|---|---|---|
| Primera | 2025-08-15 | 2026-04-06 |
| Segunda | 2025-08-15 | 2026-04-06 |

La fecha final confirma que el historico se obtuvo antes de terminar la
temporada.

## 4. Calidad de las filas existentes

Sobre las 674 filas disponibles se verifico:

- 0 duplicados por fecha, equipo local y visitante.
- 0 fechas invalidas.
- 0 resultados finales fuera de `H`, `D` o `A`.
- 0 filas sin las cuotas medias `AvgH`, `AvgD` y `AvgA`.
- 20 equipos distintos en Primera.
- 22 equipos distintos en Segunda.
- 0 candidatos administrativos confirmados en este corte.

Estas comprobaciones no demuestran que todas las estadisticas posibles
esten presentes; demuestran que el esquema basico utilizado por el motor
esta completo en las filas existentes.

## 5. Anomalia pendiente de contraste

Debe contrastarse externamente el movimiento de cuotas de:

- Mallorca - Barcelona
- Fecha: 2025-08-16
- Resultado almacenado: 0-3
- Apertura media: 6.75 / 4.74 / 1.43
- Cierre medio: 8.70 / 5.79 / 1.56

El partido y su resultado son coherentes. Lo pendiente es confirmar que
las cuotas de cierre y su movimiento proceden correctamente de la fuente.
No debe eliminarse ni corregirse sin esa comprobacion.

## 6. Reproduccion

Desde la raiz del proyecto:

```powershell
python -c "import pandas as pd; from pathlib import Path; files=[('Primera',Path('DATOS/historico_raw/PRIMERA/SP1_2526.csv'),380),('Segunda',Path('DATOS/historico_raw/SEGUNDA/SP2_2526.csv'),462)]; [(print(n,len(d:=pd.read_csv(p).dropna(how='all')),e,e-len(d),pd.to_datetime(d['Date'],dayfirst=True,errors='coerce').min(),pd.to_datetime(d['Date'],dayfirst=True,errors='coerce').max())) for n,p,e in files]"
```

Comprobaciones complementarias:

```powershell
python -m pytest -q
python scripts/datos/VALIDAR_DATASETS.py
```

## 7. Siguiente fase recomendada

1. Consultar la documentacion y el cliente existente de Highlightly para
   identificar los IDs exactos de Primera y Segunda 2025-26.
2. Obtener listados por competicion y temporada, con paginacion, evitando
   una llamada individual por partido.
3. Comparar primero por fecha, local, visitante y resultado.
4. Generar una propuesta de incorporacion separada, sin sobrescribir los
   CSV originales.
5. Revisar los 168 partidos candidatos y la cuota Mallorca-Barcelona.
6. Crear nuevos artefactos versionados solo despues de aprobar el informe.
7. Repetir control de calidad y backtests original/completado.

## 8. Condicion de cierre

La temporada solo podra marcarse como cerrada cuando:

- Primera contenga 380 partidos regulares validos.
- Segunda contenga 462 partidos regulares validos.
- Los 168 partidos nuevos esten contrastados y sin duplicados.
- Las incidencias aplazadas o administrativas esten documentadas.
- El control de calidad y los tests terminen correctamente.

