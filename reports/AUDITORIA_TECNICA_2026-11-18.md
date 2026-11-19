# Auditoría técnica de Programa Quiniela

**18 de noviembre de 2026 · Base auditada `92447561cccbe78f940a9aeaf54a9716d692f02d`**

## Dictamen

Se corrigieron fallos de integridad que podían producir un pronóstico retrospectivo con información posterior al corte, asociar una salida al boleto equivocado o presentar un sustituto como si fuera una predicción del motor. **No se retocaron los pesos para subir el acierto.** Al comparar antes y después sobre el mismo histórico saneado, las métricas históricas preexistentes coinciden exactamente. Eso es lo esperado: el fallo más grave estaba en la predicción de jornada, no en el ajuste por temporada del backtest de referencia.

El sistema queda en condiciones de **evaluación reproducible y revisión local**. Todavía no hay base para afirmar una ventaja estable sobre el mercado, autorizar publicaciones automáticas o reportar un retorno realizado. Se revisaron las rutas activas de datos, entrenamiento, evaluación, decisión, boleto, API y panel; no se certifica cada experimento archivado de `LMARENA/` ni un importador externo.

## 1. Estructura y límites

```text
DATOS/historico_raw → dataset_quality (solo lectura) / sanitization
                   → histórico saneado → features y estado por día
                                        ├─ backtest de Primera/Segunda → referencia
DATOS/QUINIELA15_J<N>.json + corte ──────┴─ motor maestro de jornada
                                            → recomendación + 3 dobles + Pleno
                                            → paquete local → contrato API v1.1

Boleto semanal explícito + corte → DC/Poisson Liga M / Liga F
                                 → 14×1X2 + 1×16 signos
                                 → optimización → panel → exportación local explícita
```

- **Referencia masculina:** `MOTOR_QUINIELA_MAESTRO.py` y `scripts/backtests/BACKTEST_HISTORICO_TEMPORADAS.py`. Pesos publicados: 95,1 % mercado y 4,9 % HGB, antes de ajustes y normalización. `--historico original` es un diagnóstico deliberado, no la entrada por defecto de producción.
- **Jornada del maestro:** `PREDECIR_JORNADA.py` usa una misma captura validada para diagnóstico, pronóstico y optimización. Toma el motor cuando hay datos de su dominio; si no, mantiene APU, LAE o Q15 con su procedencia. Las cotizaciones verificadas y la popularidad del público son datos distintos. La API no ejecuta apuestas ni publica.
- **Flujo semanal mixto:** `scripts/RUN_SEMANA_COMPLETA.py` y `scripts/OPTIMIZADOR_BOLETO.py`. Este Poisson log-lineal no es el ensemble HGB–mercado. `PREDICCION_BOLETO_COMPLETO.py` encamina al mismo flujo: no es otro constructor que intente conciliar archivos por proximidad. `--demo` trabaja con la captura antigua J3 en rutas propias.
- **Separación pendiente:** el maestro todavía concentra lectura, features, entrenamiento, calibración y evaluación. Coexisten reglas de cobertura de referencia y de operación, y dos directorios `salida`/`SALIDAS` (problemáticos en sistemas sin distinción de mayúsculas). Los scripts de laboratorio y de adquisición deben permanecer fuera de las rutas de producción.

## 2. Hallazgos y correcciones

| Prioridad | Hallazgo | Cambio y alcance |
|---|---|---|
| P0 | **Fuga temporal de jornada.** Las features respetaban un corte, pero el ajuste podía usar el histórico entero; el caché global no distinguía histórico, configuración ni fecha. | Ajuste y features solo con resultados de días anteriores al corte civil de Madrid. Sin caché global ni búsqueda/vector scaling en vivo. Una regresión vuelve a entrenar para un corte anterior en el mismo proceso y comprueba la muestra. |
| P0 | **Cuotas temporalmente inválidas o mezcladas.** Se podía usar una parte de una tripleta, combinar proveedores o validar después de consumirla. Un día de captura no demuestra una hora. | Selección de tripletas completas, finitas y de una fuente. En jornada: `observación <= corte < inicio`, UTC para comparar, hora de Madrid si no se declara zona, rechazo de horas ambiguas o inexistentes sin offset. La misma regla se aplica antes de calcular features y coberturas. |
| P0 | **Cortes y priors ambiguos.** El fallback «ayer» hacía que una repetición no fuese el mismo experimento. El prior 2026-27 podía aparecer en otro año o antes de generarse. | Corte ISO explícito o inferencia reproducible con calendario completo (medianoche de Madrid del día anterior al primer partido). Priors restringidos a su temporada y a un día posterior a su generación declarada; conservador mientras no exista timestamp de publicación firmado. |
| P0 | **Fuentes y posiciones incoherentes.** El JSON podía rellenar una distribución uniforme, atribuir un proxy a `motor_v4`, o desalinear casillas. El optimizador y el API no partían de la misma probabilidad para los fallbacks. | Validación común de identidad y 14+1. API v1.1 valida origen, dominios, normalización y signos; probabilidad por casilla compartida por recomendación, optimizador y API. Escritura JSON estricta y atómica por archivo, sin sustituir un contrato previo en caso de error. |
| P0 | **Pleno confundido con 1X2 o con un marcador fijo.** Unir los máximos marginales no maximiza la probabilidad del signo completo. | Bloque independiente del 1X2. Se elige la moda conjunta de los 16 signos `0/1/2/M`; el marcador exacto mostrado puede diferir. Si el motor no cubre ese partido, solo se usa un marcador Q15 disponible y declarado o se rechaza la exportación API. |
| P0 | **Operación semanal sin identidad fuerte.** El valor por defecto podía presentar la captura J3 como jornada corriente; ejecutar y enviar no estaban separados. | Entrada semanal con fuente, fecha y posiciones; la demo no se renumera ni escribe las rutas reales. Panel vincula jornada, demo y SHA-256 del paquete optimizado. Exportación local explícita y rechazada para demo o boleto cerrado; sin Git, apuesta o despliegue remoto. |
| P1 | **Orden de dobles distinto de la cobertura final.** Se elegían las posiciones sin reglas de banda y se puntuaba otro desarrollo. Incluso un empate de probabilidades podía excluir al favorito. | Las 364 combinaciones del maestro se comparan con los signos efectivos y desempate determinista; el doble no descarta el favorito. Exactas bajo independencia y Monte Carlo usan `p_ge_10`…`p_ge_14`; `p_15` no representa 14/14. |
| P1 | **Economía de la mejor columna confundida con el total.** Asignar el coste máximo a una sola columna tampoco era una comparación de presupuesto. | `evaluation/economics.py` suma el valor esperado categoría por categoría de **cada columna**, informa el coste efectivo y mantiene separada la distribución de la mejor. `EVALUACION_ECONOMICA.py` conserva el diagnóstico legado, identificado como bloques sintéticos y premios supuestos. El ROI 1X2 oficial no se calcula si falta un premio alcanzado en el escrutinio. |
| P1 | **Referencia reutilizable sin identidad suficiente.** Un JSON anterior o incompleto podía confundirse con una evaluación vigente. | Ventana cerrada, 380/462 partidos por temporada, verificación de hashes del histórico, código y configuración, xG opcional y entorno numérico. La referencia rechaza incoherencias y no escribe si fallan las pruebas, salvo que se omitan explícitamente. El informe de agosto queda archivado. |

## 3. Datos y calidad

| Evidencia | Resultado y decisión |
|---|---|
| Saneamiento de 34 CSV | 13.560 filas brutas → **13.531**. Excluidas 21 candidatas a resultados administrativos, 3 vacías y 5 sin cuota requerida. Se aplicaron alias a 42 filas. No se editó el original. |
| Coberturas dispares | Saneado: **5.894** con cierre real, **10.301** con tiros y **4** cuotas marcadas sospechosas. En el tramo de siete temporadas evaluado, todas las filas usaron `close_avg`. |
| Hallazgos del auditor raw | 10 informativos, 7 avisos y 3 críticos de cobertura/consistencia: **3.234** partidos sin columnas de tiros, **7.663** filas sin cierre real y **4** equipos con parcialidad no reconocida en `missing_or_partial`. No se rellenan tiros ni se contabiliza una apertura copiada como cierre. |
| Highlightly | 7.429 filas en el CSV inspeccionado (UTF-8 con BOM); 91 no finalizadas, 68 de play-offs y 4 duplicados lógicos excedentes. Debe filtrarse y conciliarse antes de ampliar su consumo. |
| 2026-27 | Captura parcial: **85 partidos**, 41 de Primera y 44 de Segunda, del 14/08 al 07/09 de 2026. Cuotas prematch de Highlightly (no cierres certificados). Se informa por separado y no actualiza la referencia cerrada. |
| Boletos oficiales | `DATOS/quiniela_historica/` no contiene un corpus auditado. `QUINIELA_REAL.py` valida el corpus y ofrece funciones de unión por fecha/equipos y de escrutinio 1X2; no reconstruye boletos desde bloques de partidos. Sin corpus no hay ROI realizado ni validación de Pleno sobre boletos oficiales. |

La auditoría de datos **reporta** los críticos conocidos, no los convierte en un aprobado ni los bloquea mecánicamente: faltan columnas en períodos donde nunca se observaron. Para incorporar datos nuevos deben conservarse el identificador del partido, temporada/división, fecha e instante de disponibilidad, fuente/licencia y reglas de exclusión.

## 4. Resultados comparables

**2019-20 a 2025-26 · mismo histórico saneado antes y después · 842 partidos por temporada.** Entrenamiento con temporadas previas y estados prepartido actualizados solo con días anteriores. El comparador elige el favorito del mismo mercado 1X2 de cierre. Los porcentajes de la tabla son **motor / mercado**, y no cambiaron con el parche.

| Temporada | n | Total | Primera (n=380) | Segunda (n=462) | Media 3 dobles* |
|---|---:|---:|---:|---:|---:|
| 2019-20 | 842 | 46,91 / 45,96 % | 51,84 / 51,84 % | 42,86 / 41,13 % | 7,86 |
| 2020-21 | 842 | 50,83 / 50,24 % | 54,47 / 54,47 % | 47,84 / 46,75 % | 8,45 |
| 2021-22 | 842 | 48,69 / 47,98 % | 52,37 / 51,84 % | 45,67 / 44,81 % | 8,27 |
| 2022-23 | 842 | 50,12 / 50,12 % | 53,42 / 54,21 % | 47,40 / 46,75 % | 8,61 |
| 2023-24 | 842 | 50,59 / 50,59 % | 55,26 / 55,53 % | 46,75 / 46,54 % | 8,57 |
| 2024-25 | 842 | 52,38 / 52,38 % | 55,79 / 55,53 % | 49,57 / 49,78 % | 8,73 |
| 2025-26 | 842 | 51,54 / 51,54 % | 54,74 / 54,47 % | 48,92 / 49,13 % | 8,46 |
| **Agregado** | **5.894** | **50,15 / 49,83 %** | **53,98 / 53,98 %** | **47,00 / 46,41 %** | **8,42** |

\* Aciertos sobre bloques mecánicos de **15** partidos con selección heurística de tres dobles. No equivalen al desarrollo exhaustivo **14+1** ni a boletos o premios reales. También cambian las unidades: `p_ge_14` del optimizador corresponde a las 14 casillas 1X2; el Pleno no se cuenta ahí.

- Diferencial de acierto **+0,322 pp**; 86 partidos que acertó solo el motor frente a 67 que acertó solo el mercado. McNemar exacto bilateral **p = 0,1454**; IC95 % bootstrap pareado por partido **[−0,085; +0,730] pp**. El intervalo no ajusta la dependencia por equipo o jornada. No demuestra superioridad ni equivalencia matemática.
- En el mismo conjunto pareado, Brier multiclase **0,602313 vs 0,602976** y log-loss **1,006267 vs 1,007301** (menor es mejor). Son diferencias pequeñas, no una validación independiente de calibración. Los pesos y las reglas publicados se eligieron con experimentos históricos anteriores: el walk-forward no sustituye a una ventana prospectiva nunca usada para decidir cambios.
- La referencia de agosto (50,27 % / 49,83 %, otro commit) y el diagnóstico original que incluía 2026-27 parcial no son el «antes» comparable. La evaluación histórica con cierre no equivale a disponer de ese cierre en el instante de jugar una Quiniela.

**2026-27, parcial y sin cierres.** 42/85 aciertos del motor (49,41 %) frente a 43/85 del favorito de la cuota prematch (50,59 %); Primera 53,66 % / 56,10 % y Segunda 45,45 % / 45,45 %. Es un seguimiento acotado de una muestra y fuente distintas, no la octava temporada de la referencia.

**Liga F, separada.** `BACKTEST_LIGAF_2324.py` corrigió el reajuste a cortes por día, incluso si el warmup o un nuevo ajuste caen entre dos partidos de la misma fecha. Del backbone de 240 partidos se evaluaron 180: **58,89 %** de acierto frente a **42,78 %** de jugar siempre `1`; log-loss **0,8571** frente a **1,0703** de frecuencias históricas. El código previo dio 58,89 % y log-loss 0,8568. Comparar con estas referencias simples no demuestra ventaja frente a cuotas, ni valida las plantillas actuales: hay equipos que solo reciben rating neutro.

## 5. Verificación operativa

- **J74 (histórica, nórdica):** en el original se entrenaban 13.531 partidos pese a que la jornada es de julio y no había cobertura propia. Con corte del **23/07 a las 00:00 de Madrid**, el entrenamiento previo fue de **13.446**, hasta el 31/05. Sin predicciones maestras disponibles para sus 14 casillas; se validan los proxies APU (primera casilla, `X=0,26`) y Pleno Q15 **2-1**. El proxy sale `manual_pendiente`, no `motor_v4`.
- **J6 (histórica, mixta):** **15** posiciones, **10/14** con fuente maestra y **4/14** con proxy Q15. Corte **10/09 a las 00:00 de Madrid**; última fecha de ajuste 07/09. Ajuste con 13.531 partidos. La captura tiene 9 tripletas fechadas (una en el Pleno), 8 habilitadas para 1X2 y ninguna violación temporal. Pleno del modelo **1-1**. 364 desarrollos, 8 columnas, **6 €**; sin LAE completa el listado se ordena por probabilidad, no por popularidad inventada.
- **J3 demo semanal:** 4 casillas Liga F y Pleno **M-0**, presupuesto de 8 columnas/6 €. Cobertura libre **0,005823 %** de 14+Pleno bajo el modelo de independencia, no probabilidad empírica validada. EV parimutuel restringido a 512 candidatos, bote y modelo de co-ganadores supuestos. Comprobados consola, HTTP local y renderizado JS con DOM simulado; demo bloqueada y ruta anterior de publicación ausente. El modo CLI sin boleto devuelve un error. No se exportó ni publicó una jornada real.
- **Pruebas:** **311** iniciales y **361** en el árbol final (4 min 13 s, Python 3.11.2). Regresiones de futuro/mismo día, DST, tripletas, alias y priors, Pleno conjunto, invalidación de referencia, coherencia del optimizador, pagos por columna, JSON y aislamiento de demo/exportación. Las dos integraciones pesadas de jornada sumaron 197 s: son la primera diana de perfilado. `pip check`, lint selectivo y `git diff --check` pasaron. CI configurada para 3.11/3.12; no se ejecutó en remoto.
- **Cobertura:** la pasada instrumentada de `make audit` (359 pruebas; las dos regresiones finales se verificaron en la suite de 361) registró **67 %** combinado de sentencias y ramas según `coverage`, excluidos tests y `LMARENA/`. En los archivos medidos: 86 % predicción de jornada, 68 % paquete, 80 % contrato API, 85 % orquestador semanal; quedan brechas en el maestro (35 %) y el panel (51 %). El lint amplio aún tiene deuda —no se hizo un formateo masivo ni se confunde lint selectivo con ausencia de defectos.

## 6. Reproducción

Desde la raíz, con un entorno virtual y dependencias de desarrollo instaladas:

```bash
python -m pip install -r requirements-dev.txt
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
make sanitize  # solo en una copia nueva: no sobreescribe un saneado existente
make audit     # lint selectivo, JSON QA nuevo, pytest/cobertura y siete temporadas
```

Para guardar predicciones y certificar los hashes de un backtest concreto sin tocar el archivo de agosto:

```bash
out=salida/auditoria_2026-11-18
python scripts/backtests/BACKTEST_HISTORICO_TEMPORADAS.py \
  --historico saneado --from-season 2019-2020 --to-season 2025-2026 \
  --out-dir "$out" --save-predictions
python scripts/reports/GENERAR_PRODUCTION_REFERENCE.py \
  --reuse-backtest --backtest-json "$out/backtest_historico_temporadas.json" \
  --out "$out/referencia.json"
```

Hash SHA-256 del saneado evaluado: `3499578ec8b2f30d6b6d1c03e533d0790bc6b13c368f2a7c91b09a742989e989`. Configuración: `f6fd09f3b12c3887d35e9427f23b0dd959072a21989037e87248b71c0e11cb2a`. Entorno: Python 3.11.2, NumPy 2.2.6, pandas 2.3.3, SciPy 1.16.3, scikit-learn 1.7.2; sin CSV Understat opcional. Los JSON y CSV grandes se regeneran localmente, no se añaden a Git.

**Reproducir el «antes» con la misma fuente.** Extraer el commit base en un directorio temporal, sin cambiar de rama. El backtest antiguo no tenía `--historico`: hay que inyectar el saneado expresamente en ese proceso.

```bash
base=$(mktemp -d)
py=$(command -v python)
git archive 92447561cccbe78f940a9aeaf54a9716d692f02d | tar -x -C "$base"
(
  cd "$base" || exit 1
  "$py" scripts/datos/SANEAR_DATOS.py --confirm || exit 1
  "$py" - <<'PY'
import sys
from pathlib import Path
from scripts.backtests import BACKTEST_HISTORICO_TEMPORADAS as bt

bt.OUT_DIR = Path.cwd() / 'salida' / 'comparacion_base'
load_history = bt.motor.load_raw_history
bt.motor.load_raw_history = lambda: load_history('saneado')
sys.argv = ['backtest', '--from-season', '2019-2020', '--to-season', '2025-2026']
bt.main()
PY
)
printf 'Referencia anterior en %s/salida/comparacion_base\n' "$base"
```

El saneado regenerado en una copia limpia del commit base produjo el mismo SHA-256. El cotejo de `rows` (sin la clave nueva `probabilistic_scores`), `details` y `paired_statistics` dio igualdad exacta. El nuevo fingerprint (`6acd14d7eb0323bc07411cfe8a366f8e4388a53e9c8ac81654a1952d1741b846`) identifica el código evaluado, no significa que el commit base ya contenga el parche.

## 7. Qué falta para el «nivel dios»

| Orden | Trabajo | Criterio verificable antes de darlo por hecho |
|---|---|---|
| 1 | **Histórico oficial de boletos y escrutinios.** Ingesta legal, versionada y auditada; fixtures, cierre y premios por columna. | Cada boleto validado conserva UUID/temporada/jornada, 14+1 posiciones, fechas y fuente; las exclusiones se cuentan. Comparación de modelos con el mismo presupuesto, mismas reglas, sin ceros imputados ni Pleno inventado. |
| 2 | **Snapshots disponibles al corte.** Cuotas completas, porcentajes jugados y plantillas/competición con fecha de disponibilidad. | Reejecutar una jornada solo con su captura produce la misma salida, o falla identificando el dato ausente. Informar cobertura y resultados por división, régimen, proveedor y estado de datos. Nunca equiparar popularidad LAE al mercado de cuotas. |
| 3 | **Prueba prospectiva congelada.** Comparar mercado, HGB, Poisson/DC y ensemble con calendario y métricas registrados de antemano. | Historial de predicciones emitidas antes del cierre; evaluación pareada de log-loss/Brier, aciertos, Pleno y P(≥10…14); IC por bloques, controles de calibración y muestra suficiente. No cambiar parámetros mirando esa misma ventana. |
| 4 | **Una arquitectura mantenible sin fusionar protocolos distintos.** Esquemas comunes de fuente/partido/boleto; dependencias explícitas; adaptadores para motores y salida. | Pruebas de paridad de resultados al extraer módulos, regeneración limpia con datos versionados, contrato legible por el importador real antes de habilitar entregas externas. Detectar artefactos obsoletos y transacciones a medias. |
| 5 | **Rendimiento y calidad continuos.** Perfilar reconstrucción de estado y ajuste; reducir deuda de Ruff en lotes pequeños; lock de dependencias y pruebas de sistema operativo. | Caché solo con clave de histórico/configuración/corte/modelo, con pruebas contra fuga temporal. Medir tiempo y memoria antes/después, sin cambiar probabilidades ni perder identidad. |

**Prioridad recomendada:** empezar por la evidencia oficial y los snapshots al corte. Añadir modelos o afinar umbrales antes de tener esos datos multiplicaría la complejidad sin aclarar si el boleto seleccionado mejora al mercado en el momento real de decidir.
