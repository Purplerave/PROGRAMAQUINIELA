# Auditoría total del programa Quiniela

**Fecha:** 19 de noviembre de 2026
**Árbol base inspeccionado:** `120e5f4221a060a577bcd9d31d49156246df67dc` (rama `arena/e8b69a4d-programaquiniela`)
**Alcance:** rutas de producción y evaluación, flujos de boleto/panel, importadores y validadores, datasets versionados, configuración, pruebas, CI, documentación, dependencias y experimentos archivados. No se ejecutaron adquisiciones externas ni se certificaron manualmente los 27.000+ renglones de código ni las fuentes/licencias de cada dato.

## Dictamen ejecutivo

El repositorio tiene controles temporales, trazabilidad de fuentes, validaciones de contrato y una suite de regresión considerable. La referencia oficial reproducible queda **ligeramente por encima del favorito de mercado en acierto**, pero la evidencia estadística no demuestra una ventaja: el diferencial pareado es **+0,322 puntos porcentuales**, IC95 % **[−0,085; +0,730] pp**, McNemar **p=0,1454**. El modelo no debe anunciarse como superior ni utilizar estas cifras para prometer rentabilidad.

La ejecución completa de `make audit` sobre el árbol de trabajo, incluida la mejora descrita abajo, terminó con código cero: lint selectivo aprobado, **361 pruebas aprobadas**, cobertura combinada de sentencias/ramas **67 %** y backtest de siete temporadas cerrado reproducido. A la vez, la inspección de datos encontró **3 hallazgos críticos**, entre ellos 7.663 filas sin cierre real de cuotas. Esos hallazgos están descritos y no se deben “arreglar” fabricando datos. El código de salida verde de la auditoría de datasets no diferenciaba un dataset con hallazgos críticos de uno sin ellos.

**Mejora implementada en esta auditoría:** `scripts/datos/VALIDAR_DATASETS.py` incorpora `--fail-on-severity {info,warning,critical}`. Si se solicita, devuelve código 1 cuando existe esa severidad o una más alta, conservando la evidencia JSON solicitada incluso al fallar. El comportamiento por defecto no cambia para no romper la inspección informativa de datasets históricos con limitaciones conocidas. Se añadió una prueba de regresión de ese contrato. Ver `README.md` para el uso.

## Evidencia ejecutada

En este entorno se creó un `.venv` local ignorado por Git e instalaron las versiones declaradas en `requirements-dev.txt` (Python 3.11.2).

| Comprobación | Resultado observado |
|---|---|
| `make lint` | Correcto: Ruff limitado a `E9,F821,F822,F823`; `git diff --check` sin errores. No equivale a lint integral. |
| `scripts/datos/VALIDAR_DATASETS.py` | 34 CSV históricos; 13.560 filas brutas, 13.531 utilizables, 29 descartadas; Highlightly 7.429 filas; 42 equipos/priors. **10 info, 7 warning, 3 critical.** |
| Pruebas | **361/361 aprobadas**, Python 3.11.2, 319,07 s en la verificación posterior al cambio del umbral. |
| Cobertura | **67 %** combinada. Maestro 35 %, panel 51 %, preparación de estadísticas 25 %, reporte de referencia 30 %. Los porcentajes más bajos necesitan casos unitarios dirigidos; no significan que las salidas evaluadas estén necesariamente incorrectas. |
| Backtest oficial | 5.894 partidos de 2019-20 a 2025-26; resultado resumido abajo. Sin errores de temporada. |
| Compilación manual / Python 3.12 / Windows / revisión legal y de licencias de datos | No certificadas en esta pasada. CI sí define matrix 3.11/3.12, pero no se ejecutó en remoto. |

## Hallazgos principales

| Prioridad | Hallazgo | Riesgo / recomendación |
|---|---|---|
| **P1** | El auditor de datasets informaba 3 críticos pero terminaba con código 0, por lo que no servía como puerta automática de calidad. | Añadido `--fail-on-severity`; el umbral queda optativo porque los críticos conocidos incluyen indisponibilidad histórica y el auditor no debe inventar datos ni bloquear una inspección descriptiva. La nueva regresión confirma el código 1 y la persistencia de evidencia. |
| **P1 datos** | **7.663** partidos no tienen tripleta de cierre real; **7.637** quedan con cuota de apertura reutilizada como cierre efectivo. | No interpretar el backtest como información observada al cierre en todos los partidos. Separar apertura, cierre real y fallback en comparaciones; adquirir snapshots fechados antes de proclamar rendimiento prospectivo. |
| **P1 datos** | **3.234** filas carecen de columnas de tiros. | No imputar como si fueran observaciones. Asegurar que cada experimento excluya explícitamente variables sin cobertura o evalúe submuestras comparables. |
| **P1 datos** | Los cuatro equipos CD Eldense, CD Tenerife, CE Sabadell y RC Celta Fortuna tienen splits reales parciales no listados en `missing_or_partial`. | Revisar procedencia y actualizar la declaración de parcialidad antes de usar esos priors. No se editaron datos de origen en esta auditoría. |
| **P1 estadística** | Diferencial de acierto del modelo vs. favorito de mercado de **+0,322 pp**, con intervalo que cruza cero y `p=0,1454`. | Evidencia inconclusa. Priorizar el registro prospectivo inmutable de predicciones al corte, métricas probabilísticas y evaluación pareada por temporada/división; no retocar pesos usando la ventana evaluada. |
| **P1 validación** | Los tests tardan alrededor de cinco minutos; hay cobertura baja en partes centrales. `make lint` solo selecciona errores graves y nombres no definidos; una pasada diagnóstica con Ruff completo encontró **403** infracciones en el repositorio (incluidos laboratorios y tests), por lo que no se aplicó autocorrección masiva. | Mantener suite completa, reducir lentitud solo después de perfilar, incrementar cobertura por comportamiento/riesgo; ampliar Ruff en lotes, sin formateo masivo que oculte cambios funcionales. |
| **P2 arquitectura** | El motor maestro concentra funciones de lectura, features, ajuste y evaluación; hay dos árboles de salida diferenciados solo por mayúsculas (`salida`/`SALIDAS`). | Extraer módulos gradualmente con pruebas de paridad. Consolidar rutas solo con compatibilidad documentada para Windows/macOS y herramientas de entrega. |
| **P2 reproducibilidad** | Dependencias de runtime parcialmente fijadas, `requests` sin versión exacta y sin lock integral de hashes. | Añadir lock reproducible de entorno de aplicación/CI; planificar actualización y auditoría de dependencias por separado. |
| **P2 alcance** | El árbol incluye una carpeta de laboratorio `LMARENA/` con scripts experimentales y material de numerología/herramientas exploratorias. | Mantenerla claramente aislada de las rutas de producción; no mezclar resultados ni fuentes de estos experimentos con la referencia oficial sin protocolo preinscrito y validación fuera de muestra. |

## Hallazgos de datasets (recuento del auditor)

- **Críticos:** falta de columnas de tiros en 3.234 partidos; ausencia de cierre real en 7.663 filas; cuatro priors parciales mal declarados.
- **Avisos:** 29 filas descartables, 21 candidatas administrativas, 7 temporadas incompletas, 4 overrounds fuera del rango configurado, 26 sin tripleta de apertura, 21 filas con valores de tiros faltantes y 4 duplicados lógicos Highlightly excedentes, entre otros.
- **Contexto:** las filas descartadas incluyen problemas de identidad/fecha/cuotas y candidatos administrativos; no deben reconstruirse automáticamente como resultados oficiales. El dato de apertura no es un cierre verificable, aunque coincida numéricamente con él.
- El auditor informa lo que encuentra; la clasificación crítica significa que una ausencia puede inducir señal engañosa si un consumidor la trata como observación. No afirma que el histórico saneado sea inservible para todos los experimentos.

## Backtest comparable

Walk-forward oficial, histórico saneado, siete temporadas cerradas. Porcentajes de acierto simple del motor / favorito de mercado:

| Temporada | Total | Primera | Segunda | Media con 3 dobles |
|---|---:|---:|---:|---:|
| 2019-20 | 46,91 / 45,96 % | 51,84 / 51,84 % | 42,86 / 41,13 % | 7,86 |
| 2020-21 | 50,83 / 50,24 % | 54,47 / 54,47 % | 47,84 / 46,75 % | 8,45 |
| 2021-22 | 48,69 / 47,98 % | 52,37 / 51,84 % | 45,67 / 44,81 % | 8,27 |
| 2022-23 | 50,12 / 50,12 % | 53,42 / 54,21 % | 47,40 / 46,75 % | 8,61 |
| 2023-24 | 50,59 / 50,59 % | 55,26 / 55,53 % | 46,75 / 46,54 % | 8,57 |
| 2024-25 | 52,38 / 52,38 % | 55,79 / 55,53 % | 49,57 / 49,78 % | 8,73 |
| 2025-26 | 51,54 / 51,54 % | 54,74 / 54,47 % | 48,92 / 49,13 % | 8,46 |
| **Global** | **50,15 / 49,83 %** | — | — | **8,42** |

La media de tres dobles es una métrica de bloques mecánicos, no boletos históricos, cobertura oficial ni retorno. El ROI realizado no está demostrado. La ventana histórica tampoco reemplaza capturas inmutables de lo que se conocía realmente antes de cada partido.

## Prioridades recomendadas

1. Resolver metadatos y procedencia de los cuatro priors parciales; conservar versiones/hash y revisión humana.
2. Poner snapshots temporales de cuotas, popularidad y predicciones emitidas en un almacén append-only; comparar cada uno con su benchmark disponible al mismo corte.
3. Definir una evaluación prospectiva congelada con log-loss/Brier, calibración, aciertos, resultados de Quiniela y coste real; no cambiar parámetros durante su ventana.
4. Decidir políticas de calidad por consumidor. Usar `--fail-on-severity critical` para flujos que no toleran críticos; dejar sin umbral los informes exploratorios, declarando su estado.
5. Perfilar los tests lentos y elevar cobertura donde el comportamiento es complejo: maestro, escritura/exportación y transformación de priors.
6. Añadir un lock de dependencias y una matriz de plataforma; mantener los motores separados hasta que las pruebas de paridad prueben equivalencia.

## Reproducir

```bash
python -m pip install -r requirements-dev.txt
make audit
python scripts/datos/VALIDAR_DATASETS.py \
  --json salida/auditoria_estricta.json \
  --fail-on-severity critical
```

El segundo comando devuelve código 1 con los datos actuales, como indicador de que la fuente tiene críticos abiertos; guarda primero el JSON solicitado. La primera línea `make audit` sigue siendo descriptiva y ejecuta el backtest/cobertura sin bloquear por limitaciones históricas declaradas.
