# Roadmap de mejora — respuesta a la auditoría externa (Grok, 04/08/2026)

> Documento de trabajo. Ordena **todo lo mejorable** del proyecto de **más urgente a
> menos urgente**. Cada punto incluye: qué dijo la auditoría, si es **cierto /
> matizable / falso** contra el código real del repo, qué hacer, y **criterios de
> aceptación numéricos** para saber cuándo está terminado.
>
> Regla de oro heredada del proyecto: **nada entra al motor activo sin un experimento
> walk-forward que lo justifique**. Este roadmap no cambia esa cultura, la refuerza.

---

## 0. Veredicto validado con datos del repo

La auditoría es, en lo esencial, **correcta**. Verificado el 04/08/2026 contra
`reports/production_reference.json`, `CONFIG_MOTOR_V2.json` y el árbol de código:

| Afirmación de Grok | Evidencia en el repo | Veredicto |
|---|---|---|
| Peso mercado 0.951, HGB 0.049, logit/poisson 0.0 | `CONFIG_MOTOR_V2.json → master_model.weights` | **CIERTO** |
| El edge sobre el mercado es marginal | `metricas_agregadas`: media acierto **0.5007** vs mercado **0.4983** → **+0,24 pp** (7 temporadas). `mean_gap_vs_market = 0.00238` | **CIERTO** (dentro del ruido: `std_accuracy ≈ 0.017`) |
| No hay evaluación económica (ROI/EV/premios) | `grep` de "roi/ev/premio/bankroll" → **0 coincidencias en código**, solo texto en ROADMAP | **CIERTO** |
| Ficheros monolíticos | `MOTOR_QUINIELA_MAESTRO.py` 906 líneas, `MOTOR_PREDICCION_JORNADA.py` 875, `features.py` 875 | **CIERTO** (grande, pero no "37k líneas": son ~906; Grok confundió bytes con líneas) |
| Mezcla `salida/` y `SALIDAS/` | ambas existen, ambas casi vacías (`.gitkeep`) | **CIERTO** (deuda cosmética real) |
| 12 `REVISION_*.md` saturan el root | 12 ficheros en raíz | **CIERTO** |
| README Windows-céntrico, CI Linux | 7 menciones a PowerShell/`python .\` en README; CI en `ubuntu` | **CIERTO** |
| No hay Makefile / entrada única | no existe `Makefile` | **CIERTO** |
| Divergencia y clasificador de empates no aportan | ya **rechazados/condicionales** en `EXPERIMENTOS_REGISTRO.md` | **CIERTO** — Grok propone re-atacarlos; ya se hizo, hay que ser honestos con eso |

**Conclusión honesta:** el sistema es disciplinado y reproducible, pero **hoy es un
wrapper del mercado + HGB residual**. La siguiente victoria NO es más features ni más
calibración: es **(a) medir en dinero** y **(b) buscar ineficiencias sistemáticas
concretas**. Todo lo demás es pulir el chasis.

---

## FASE P0 — Ahora (1–2 semanas). Bloquea todo lo demás.

### P0.1 — Métrica económica obligatoria (EV del boleto de 6 €)  ⬅️ EMPEZAR AQUÍ
**Por qué primero:** sin esto, `8,48/15` es un número bonito sin significado. Es la
única forma de saber si algún experimento futuro "vale la pena" de verdad. Es el
punto de mayor ROI del roadmap y hoy no existe en el código.

**Qué construir:** módulo `evaluation/economics.py` que, dado un boleto (14 signos +
dobles/triples) y el resultado real, calcule:
- Coste fijo (contrato P0: 3 dobles = 8 columnas × 0,75 € = **6,00 €**).
- Nº de aciertos por columna y **distribución** de aciertos de las 8 columnas.
- Categorías de premio de La Quiniela (10, 11, 12, 13, 14, especial 14+pleno).
- **EV estimado** del boleto usando premios medios históricos por categoría.
- Comparación directa vs boleto **"solo favoritos de mercado"** (mismo presupuesto).

**Criterios de aceptación:**  ✅ **COMPLETADO (04/08/2026)**
- [x] `scripts/backtests/EVALUACION_ECONOMICA.py` corre sobre el backtest
      walk-forward y emite por temporada: coste, ROI (%), P(≥10..≥14) y **delta ROI
      vs solo-mercado**. `evaluation/economics.py` aporta el EV ex-ante por partido.
- [x] Tests unitarios: distribución de aciertos y P(≥k) coinciden con la convolución
      exacta de `OPTIMIZADOR_COLUMNAS.py` (misma fuente de verdad) — `tests/test_economics.py`.
- [x] `reports/production_reference.json` incluye el bloque `economia`.

**Resultado medido (ex-post, 392 jornadas, premios ESTIMADOS manus.ai, 3 escenarios):**
modelo **P(≥12)=3,57%** vs solo-mercado 0,77% (~4,7× más). ROI del boleto de 6 € por
escenario — modelo vs solo-mercado: **fácil −93%/−99%**, **normal −50%/−92%**,
**difícil +492%/−13%**. El modelo bate a solo-mercado en los tres, pero el juego solo
es rentable en jornadas "difíciles" (botes). ⚠️ La cifra "+130%" de la primera versión
estaba inflada (premio de 14 sobreestimado + varianza); corregida el 04/08/2026. El
edge NO está en el acierto simple (ruido), está en la colocación de dobles. Ver `EXPERIMENTOS_REGISTRO.md`.

> ⚠️ Nota de honestidad: los importes de premio de La Quiniela son variables (pozo,
> nº de acertantes). El EV será **estimado con premios medios históricos** y debe
> etiquetarse como tal, con intervalo, no como garantía.

### P0.2 — Experimento limpio de ensembles con métrica económica
**Por qué:** cierra la pregunta "¿el modelo aporta algo sobre el mercado?" midiendo
lo que importa (P(≥12/13/14) y EV), no solo acierto simple.

**Brazos a comparar (walk-forward multi-temporada):**
1. Solo mercado.
2. Mercado + HGB (pesos actuales 0.951/0.049).
3. Mercado + calibración (VectorScaling ya existente).
4. Mercado + regla de divergencia **restringida al rango +0.05/+0.10** (el único
   tramo con señal según `EXPERIMENTOS_REGISTRO.md`).

**Criterios de aceptación:**  ✅ **COMPLETADO (04/08/2026)**
- [x] Tabla comparativa con acierto simple, media aciertos, P(≥12/13/14) y ROI por
      brazo (`scripts/backtests/EXPERIMENTO_ENSEMBLES_ECONOMICO.py`).
- [x] **Regla de decisión escrita y aplicada** (≥4 de últimas 5 temporadas mejor
      P(≥12) + `mean-0.5*std` superior). Resultado: **ningún brazo sustituye al
      activo**; se congela el peso de mercado y se documenta.

**Resultado (walk-forward 2019-2026, premios ESTIMADOS):** la **calibración**
(`mercado_hgb_calib`) es el brazo más robusto — misma P(≥12) media que el mercado
(3,36%) pero **menor varianza** (std 0,024 vs 0,040 del activo) y mejor score
robusto (0,0214 vs 0,0053). Gana P(≥12) en 3/5 (umbral 4), así que aún NO sustituye,
pero es la candidata prioritaria de P1. La divergencia da buen ROI pero es
inconsistente (1/5). Detalle en `EXPERIMENTOS_REGISTRO.md`.

### P0.3 — Separar el core de predicción (`prediction_engine`)
**Por qué:** hoy `MOTOR_QUINIELA_MAESTRO.py` (906 líneas) mezcla carga de datos,
features, entrenamiento, tuning, evaluación, Pleno 15 y reporting. Cualquier cambio
serio es peligroso y ralentiza P1.

**Qué hacer (mínimo viable, sin big-bang):**
- Extraer `prediction_engine/` con una interfaz pura:
  `predict(features_point_in_time) -> {p1, pX, p2, lambda_home, lambda_away}`
  ya calibradas. Sin I/O, sin optimizador, sin reporting.
- El optimizador de columnas, la decisión quinielística y el reporting **consumen**
  ese motor; no lo reimplementan.

**Criterios de aceptación:**  ✅ **COMPLETADO (05/08/2026)**
- [x] `prediction_engine` no importa nada de optimización/reporting (dependencia
      unidireccional, verificable con un test de imports —
      `tests/test_prediction_engine_boundaries.py`).
- [x] Los 215 tests siguen en verde (ahora 222 con los nuevos del engine);
      backtest walk-forward 2019-2026 reproduce las mismas métricas
      (accuracy_simple, mean_hits_3_dobles, P(≥12), ROI) al bit
      (**iso-resultado**), tanto el backtest histórico como la evaluación
      económica y el experimento de ensembles y la consolidación de calibración.
- [x] `prediction_engine/core.py` (construcción de modelos + ensemble +
      mercado + dobles + top scorelines), `prediction_engine/training.py`
      (optimización walk-forward multi-temporada + evaluación),
      `prediction_engine/pleno.py` (Pleno al 15 puro) y la fachada
      `PredictionEngine` en `core.py`.
- [x] `MOTOR_QUINIELA_MAESTRO.py` pasa a ser una fachada fina que mantiene
      la API pública (imports desde backtests, OPTIMIZADOR_COLUMNAS y
      MOTOR_PREDICCION_JORNADA funcionan sin cambios); la carga de datos y
      el CLI permanecen aquí.
- [x] `MOTOR_PREDICCION_JORNADA.py` consume `prediction_engine` directamente
      (no sólo a través de la fachada), reforzando la dirección de dependencia.

---

## FASE P1 — Siguiente ciclo (2–4 semanas). Aquí está el edge, si existe.

> 🔎 **Actualización tras P1.0 (04/08/2026):** la ventaja de la calibración que
> sugería P0.2 era un **artefacto de fuga temporal**. Reevaluada sin fuga, la
> calibración es PEOR que el activo (P(≥12) 2,04% vs 3,57%, 0/5 temporadas). Se
> mantiene solo como diagnóstico (ECE/LogLoss), NO en el camino crítico del boleto.
> Esto refuerza el veredicto de la auditoría: el mercado es muy eficiente.

### P1.0 — Consolidar la calibración como brazo activo  ❌ **RECHAZADA (04/08/2026)**
**Resultado:** `scripts/backtests/CONSOLIDAR_CALIBRACION.py` ajusta el calibrador
con la receta de producción (84/16 del train, sin fuga; nunca ve la temporada de
test) y aplica la regla de decisión de P0.2.

**Criterios de aceptación:**  ✅ evaluado, hipótesis descartada
- [x] Calibración integrada en el path de backtest (leak-free).
- [x] Regla aplicada: calibrado gana P(≥12) en **0/5** → **NO se activa**. Score
      robusto 0,0116 vs 0,0240 del activo; ROI +84% vs +130%. Documentado en
      `EXPERIMENTOS_REGISTRO.md`. El resultado positivo de P0.2 queda anulado.

### P1.1 — Ataque real al edge en contextos que el mercado descuenta mal
**Por qué:** las features estadísticas clásicas (Elo, forma, tiros) ya están
absorbidas por el mercado (confirmado por experimentos previos). Lo prometedor es
**contexto** que las cuotas de apertura descuentan mal.

**Vías (ordenadas por prometedoras y baratas):**
1. **Rotaciones / fin de temporada / ascenso-descenso**: partidos "intrascendentes"
   o de máxima presión donde el favor de mercado se sesga. Ya hay `manual_context_flags`
   en config → convertirlos en features derivables automáticamente (jornada relativa,
   distancia a zona de ascenso/descenso vía tabla point-in-time).
2. **Fatiga por selecciones / calendario congestionado** (días de descanso ya existe
   como feature → medir su interacción con el sesgo de mercado).
3. **Empates solo donde el mercado está sesgado** (no clasificador global — ese ya
   fracasó): buscar sub-poblaciones (p. ej. derbis, Segunda con equipos parejos).

**Criterio de aceptación (idéntico para cada vía):** entra al motor solo si mejora
**EV o P(≥12)** en walk-forward multi-temporada con la regla de P0.2. Si no, se
registra como RECHAZADO en `EXPERIMENTOS_REGISTRO.md` con números.

### P1.2 — Simplificar el ensemble (menos es más)
**Por qué:** logit y Poisson pesan **0.0** en el ensemble. Están en el camino
crítico sin aportar.

**Qué hacer:** o se eliminan del path de ensemble (siguen disponibles para Pleno /
Dixon-Coles donde sí se usan), o se justifica su presencia con un experimento.

**Criterios de aceptación:**
- [ ] El ensemble activo solo combina fuentes con peso > 0, o hay un experimento que
      justifique numéricamente mantenerlos.
- [ ] Sin cambio de métricas (iso-resultado) tras la limpieza.

### P1.3 — Gobernanza de datos: decidir original vs saneado
**Por qué:** existen dataset original y saneado; el original sigue siendo default
"por inercia". `REVISION_05` ya los compara — falta **decisión documentada**.

**Criterios de aceptación:**
- [ ] Una línea en config y en README diciendo cuál es la fuente oficial y **por qué**
      (con el número de la comparación).
- [ ] El otro dataset queda como diagnóstico, no como camino paralelo.

---

## FASE P2 — Estructural / higiene (cuando P0/P1 estén estables)

### P2.1 — Entrada única reproducible (Makefile / scripts)
- [ ] `make backtest`, `make predict JORNADA=74`, `make test`, `make reference`.
- [ ] Cualquiera reproduce el backtest en **< 5 minutos** siguiendo solo el README.

### P2.2 — Ordenar el árbol del proyecto
- [ ] Unificar `salida/` y `SALIDAS/` en **una** carpeta (ambas están vacías: coste ~0).
- [ ] Mover los 12 `REVISION_*.md` y docs históricas a `docs/` (dejar en root solo
      README, ROADMAP y este documento).
- [ ] `scripts/` como único hogar de scripts ejecutables; nada de scripts sueltos
      en root salvo los `PREDECIR_/MOTOR_` de entrada (o moverlos también tras P0.3).

### P2.3 — Refactor progresivo a paquetes claros
- [ ] `data/ features/ models/ decision/ evaluation/ production/` — migración
      incremental, un paquete por PR, tests en verde en cada paso.

### P2.4 — Documentación multiplataforma
- [ ] README con comandos Linux/macOS **y** Windows (CI es Linux; hoy el README es
      PowerShell-céntrico → 7 menciones).
- [ ] Un `QUICKSTART` de 10 líneas al principio.

---

## Tablero resumen (de más a menos urgente)

| Prio | Tarea | Coste | Impacto | Estado |
|------|-------|-------|---------|--------|
| P0.1 | Métrica económica EV/ROI del boleto 6 € | M | 🔥 Alto | ✅ Hecho (04/08) |
| P0.2 | Experimento limpio de ensembles (EV, P≥12/13/14) | M | 🔥 Alto | ✅ Hecho (04/08) |
| P0.3 | Extraer `prediction_engine` (core aislado) | L | Alto | ✅ Hecho (05/08) |
| P1.0 | Consolidar calibración (leak-free) | M | — | ❌ Rechazada (04/08) |
| P1.1 | Edge por contexto (rotaciones/descenso/fatiga) | L | ⭐ Potencial | Pendiente |
| P1.2 | Simplificar ensemble (quitar pesos 0) | S | Medio | Pendiente |
| P1.3 | Decidir dataset oficial (original vs saneado) | S | Medio | Pendiente |
| P2.1 | Makefile / entrada única < 5 min | S | Medio | Pendiente |
| P2.2 | Ordenar árbol (salida/SALIDAS, docs/) | S | Bajo | Pendiente |
| P2.3 | Refactor a paquetes | L | Bajo/Medio | Pendiente |
| P2.4 | README multiplataforma | S | Bajo | Pendiente |

Coste: S = horas, M = 1–3 días, L = semana+.

---

## Lo que NO hay que hacer (para no perder tiempo)

- Re-implementar el clasificador binario de empates global → **ya rechazado** con números.
- Aplicar divergencia como regla universal → **ya rechazada**; solo vale el rango moderado.
- Añadir más features estadísticas clásicas esperando que batan al mercado → el
  histórico dice que no. El mercado ya las descuenta.
- Activar xG → evaluado, **−0,29 pp**, no entra.
- Añadir la calibración VectorScaling al camino crítico del boleto → **P1.0 la
  rechazó** con evaluación sin fuga (P(≥12) 2,04% vs 3,57% del activo, 0/5). Se
  mantiene solo como diagnóstico de ECE/LogLoss.

**Principio rector:** aceptar que el mercado es el rey, **medir en dinero**, y cazar
solo ineficiencias sistemáticas específicas. Todo lo demás es ingeniería de lujo
alrededor del core.
