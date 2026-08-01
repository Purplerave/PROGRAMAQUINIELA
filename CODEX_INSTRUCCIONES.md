# INSTRUCCIONES PARA CODEX — Programa Quiniela (implementación P0–P4)

> **Fecha:** 31/07/2026 · **Estado:** análisis verificado + implementación parcial
> **Este documento es autónomo:** no necesitas la conversación original. Todo lo que
> necesitas saber para continuar está aquí o en los archivos que se citan.

---

## 0. Contexto en 10 líneas

Un agente externo auditó el proyecto y luego **verificó la auditoría ejecutando el
código** (clone de GitHub, 88 tests OK, backtest real). Los hallazgos verificados:

1. El ensemble activo (logit 0,25 / hgb 0,25 / mercado 0,35 / poisson 0,15)
   **pierde contra el favorito de mercado en todas las métricas**: acierto simple
   50,52 % vs 51,56 %, media 3 dobles 8,57 vs 8,62, y peor en log loss y Brier.
2. El README declara 51,23 % pero **no se reproduce** (da 50,52 % incluso con las
   versiones exactas de `requirements.txt`). La temporada 2024-25 sí reproduce
   exacta (52,38 % / 8,91). Los datos o el código cambiaron tras generar el README.
3. La única fuente con señal propia es el **HGB** (mejor calibrado que el mercado,
   ECE 0,013 vs 0,030). Logit y Poisson son fuentes *dañinas* en el ensemble actual.
4. El valor real del programa no está en batir al mercado partido a partido (casi
   imposible), sino en **construir boletos** con las probabilidades calibradas.

Con estos hallazgos se implementaron 4 mejoras (P0–P4). **Ya están hechas y
verificadas** (sección 2). Lo que falta es **integrarlas en el flujo de producción**
(sección 3), que es tu trabajo, en el orden indicado.

---

## 1. Cómo empezar

```bash
git clone https://github.com/Purplerave/PROGRAMAQUINIELA.git
cd PROGRAMAQUINIELA
python -m venv .venv && source .venv/bin/activate   # o PowerShell si Windows
pip install -r requirements-dev.txt                  # incluye pytest
pytest -q -m "not slow"                              # referencia: 88 passed
```

- **Reglas obligatorias (AGENTS.md):** nunca usar información futura en features;
  toda mejora se valida **walk-forward** y **contra el favorito de mercado**; no
  cambiar la config activa por una sola temporada; no declarar mejora sin validación
  fuera de muestra; los resultados se regeneran con scripts (no se suben a git).
- `salida/` está en `.gitignore`: los JSON de resultados se generan al ejecutar los
  scripts. Las tablas clave de este documento ya contienen los valores esperados.

---

## 2. Lo que YA está hecho (no rehacer, solo integrar)

Los 7 archivos de este patch están implementados y ejecutados con datos reales.
Reproducción de cada uno (resultados esperados entre paréntesis):

### 2.1 `scripts/backtests/ABLACION_MODELOS.py`
Ablación estricta: mercado vs modelos, mismo corte temporal 80/20.
```bash
python scripts/backtests/ABLACION_MODELOS.py --historico original
```
Resultado clave (2.690 partidos de test):

| Candidato | Acierto | LogLoss | Brier | ECE | 3 dobles | Δ mercado |
|---|---|---|---|---|---|---|
| **Mercado** | **51,56 %** | **0,9950** | **0,5943** | 0,0301 | **8,62** | — |
| Logit con cuotas | 46,65 % | 1,0364 | 0,6210 | 0,0245 | 8,03 | −4,91 pp |
| HGB con cuotas | 49,96 % | 1,0024 | 0,5995 | **0,0130** | 8,47 | −1,60 pp |
| Poisson solo | 42,75 % | 1,0691 | 0,6461 | 0,0179 | 7,36 | −8,81 pp |
| Ensemble activo | 50,52 % | 1,0042 | 0,6003 | 0,0446 | 8,57 | −1,04 pp |

Conclusión: **el ensemble activo no aporta frente al mercado; HGB es la única fuente
con señal propia y la mejor calibrada.**

### 2.2 `scripts/backtests/EXPERIMENTO_PESOS_OPTIMIZADOS.py`
Optimización de los 4 pesos con `scipy.optimize.minimize` (log loss en validación).
```bash
python scripts/backtests/EXPERIMENTO_PESOS_OPTIMIZADOS.py --historico original
```
Resultado: pesos óptimos **mercado 0,84 · HGB 0,11 · logit 0,05 · poisson 0,00**.
En test: 51,82 % (+0,26 pp vs mercado), log loss y Brier iguales al mercado. La
ventaja está dentro del ruido, pero el mensaje es claro: **el mercado debe dominar**.

### 2.3 `scripts/backtests/WALK_FORWARD_PESOS.py` (la base de la decisión de config)
Optimización multi-split: para cada temporada 2021-22…2025-26, entrena solo con el
pasado, optimiza pesos en validación interna, evalúa fuera de muestra.
```bash
python scripts/backtests/WALK_FORWARD_PESOS.py --historico original
```
Acierto simple (Δ vs mercado):

| Temporada | Mercado | Activo | Óptimo | Consenso |
|---|---|---|---|---|
| 2021-22 | 47,98 % | 49,64 % (+1,66) | 48,46 % (+0,48) | 48,22 % (+0,24) |
| 2022-23 | 50,12 % | 47,86 % (−2,26) | 50,00 % (−0,12) | 49,88 % (−0,24) |
| 2023-24 | 50,59 % | 49,76 % (−0,83) | 50,83 % (+0,24) | 51,07 % (+0,48) |
| 2024-25 | 52,38 % | 51,66 % (−0,71) | 52,49 % (+0,12) | 52,49 % (+0,12) |
| 2025-26 | 51,54 % | 49,88 % (−1,66) | 51,31 % (−0,24) | 51,54 % (+0,00) |
| **Media** | 50,52 % | 49,76 % | 50,62 % | **50,64 %** |

- Pesos óptimos en todas las temporadas: **mercado ≈ 0,95 · HGB ≈ 0,05 · logit = 0 ·
  poisson = 0**.
- El **consenso** (media de los óptimos) gana o empata al mercado en 4/5 temporadas y
  mejora ECE (0,031 vs 0,034) sin perder log loss ni Brier.

### 2.4 `OPTIMIZADOR_COLUMNAS.py` (el corazón del proyecto, según la auditoría)
Construye el boleto globalmente: dado un presupuesto en columnas, elige qué partidos
llevan doble/triple y qué signos (programación dinámica + valor anti-popularidad +
selección de columnas por valor con diversidad + Monte Carlo).
```bash
python OPTIMIZADOR_COLUMNAS.py --jornada 74 --fuente-prob q15 --publico lae --presupuesto 128
```
Ejemplo de salida (jornada 74, prob. q15, público LAE, presupuesto 128):

| Estrategia | Coste | E[aciertos] | P(15) | P(≥14) | P(≥13) |
|---|---|---|---|---|---|
| Boleto modelo (favoritos) | 0,75 € | 9,75 | 0,11 % | 1,08 % | 5,68 % |
| Boleto popular | 0,75 € | 9,57 | 0,08 % | 0,90 % | 3,92 % |
| **Boleto optimizado** | 81 € | **11,88** | **2,58 %** | **13,55 %** | **35,69 %** |
| Top-N por valor | 37,50 € | 10,95 | 0,27 % | 3,69 % | 15,61 % |

Argumentos: `--jornada N`, `--fuente-prob q15|lae|apu|modelo`, `--publico lae|apu|q15`,
`--presupuesto COL`, `--alpha` (valor anti-popularidad), `--max-dobles/--max-triples`,
`--probabilidades FILE` (para usar el motor). Salida JSON en `salida/opt_boleto_j{N}.json`.

### 2.5 `scripts/backtests/CALIBRACION_PROBABILIDADES.py`
Isotonic por clase y **vector scaling** (logit multinomial sobre log-probs),
ajustados en validación temporal y aplicados fuera de muestra.
```bash
python scripts/backtests/CALIBRACION_PROBABILIDADES.py --historico original
```
Media 5 temporadas:

| Métrica | Ens. bruto | Ens. isotonic | **Ens. vector** |
|---|---|---|---|
| LogLoss | 1,0010 | 1,0129 | **1,0001** |
| Brier | 0,5987 | 0,5985 | **0,5979** |
| ECE | 0,0326 | 0,0299 | **0,0245** |

**Vector scaling: mejora consistente (ECE −25 %), barata, sin tocar el acierto.
Es el método recomendado.** Isotonic por clase es inestable con bloques pequeños: no usar.

### 2.6 `scripts/motor/dixon_coles.py` + `scripts/backtests/DIXON_COLES.py`
Poisson bivariante de Dixon-Coles (factor tau para 0-0, 1-0, 0-1, 1-1).
```bash
python scripts/backtests/DIXON_COLES.py --historico original
```
Rho estimado por máxima verosimilitud fuera de muestra: **−0,036** (signo correcto).
Media 5 temporadas: log loss 1,0764 → 1,0761; Brier 0,6511 → 0,6509; pleno exacto
13,06 % → 13,14 %; pleno top-3 35,30 % → 34,75 %. Mejora pequeña y real en calidad
de probabilidades, neutra en acierto.

---

## 3. Lo que NO está hecho — tus tareas pendientes (por prioridad)

Cada tarea indica **dónde mirar** (rutas y funciones exactas) y **criterios de
aceptación**. Hazlas en orden. No saltes a la siguiente sin cerrar la anterior.

> **Estado de tareas:** T1 ✅ (31/07/2026) · T2 ✅ (31/07/2026) · T3 ✅ (01/08/2026) · T6 ✅ (31/07/2026) ·
> T4 ⏳ · T5 ⏳ · T7 ⏳ · T8 ⏳
> Cada tarea hecha se marca aquí y se documenta en la sección 6 (Registro de ejecución).

### T1 — Activar la nueva configuración de pesos (P0) — ✅ HECHO 31/07/2026
- **Problema:** `CONFIG_MOTOR_V2.json` → `master_model.weights` usa
  `{logit: 0.25, hgb: 0.25, market: 0.35, poisson: 0.15}`, que pierde contra el
  mercado en 4/5 temporadas.
- **Evidencia:** sección 2.3 (walk-forward). Pesos de consenso:
  `{logit: 0.0, hgb: 0.049, market: 0.951, poisson: 0.0}`.
- **Dónde mirar:**
  - `CONFIG_MOTOR_V2.json` → `master_model.weights` y `master_model.weight_candidates`
    (actualmente 3 combinaciones a mano; el grid eligió la config perdedora).
  - `MOTOR_QUINIELA_MAESTRO.py` → `optimize_hybrid_config()` (usa `weight_candidates`),
    `apply_hybrid_config()` (aplica los pesos).
- **Qué hacer:**
  1. Vuelve a ejecutar `WALK_FORWARD_PESOS.py` (sección 2.3) y confirma el consenso.
  2. Si el consenso sigue ganando/empatando en ≥4/5 temporadas y mejora ECE, actualiza
     `weights` y `weight_candidates` en el JSON.
  3. Re-ejecuta `MOTOR_QUINIELA_MAESTRO.py --historico original` y documenta el antes
     (50,52 % / 8,57) y el después en este mismo documento (añade una sección 4).
- **Aceptación:** la config activa ya no pierde contra el favorito de mercado en el
  backtest principal; el cambio está documentado y reproducido.
- **Ojo:** no "optimices" contra el test. La decisión sale del walk-forward, no de
  mirar el resultado final.
- **Resultado (31/07/2026):** `CONFIG_MOTOR_V2.json` → `version: motor_quinielistico_v4`;
  `weights` = `{logit 0.0, hgb 0.049, market 0.951, poisson 0.0}` y `weight_candidates`
  con 4 combinaciones mercado-dominantes. Backtest principal: **51,64 %** (antes
  50,52 %) vs mercado 51,56 %; 3 dobles **8,63** (antes 8,57). 2024-25: 52,49 % /
  8,64; 2025-26: 51,54 % / 8,50 (empata con el mercado). El grid eligió candidatos
  de la misma familia (market 0,8–0,95 + HGB). Detalles en la sección 6.

### T2 — Integrar el optimizador de boletos en el flujo de predicción (P2) — ✅ HECHO 31/07/2026
- **Problema:** `OPTIMIZADOR_COLUMNAS.py` existía y funcionaba por separado, pero
  `PREDECIR_JORNADA.py` aún no generaba el boleto optimizado de cada jornada.
- **Dónde mirar:**
  - `PREDECIR_JORNADA.py` → `build_package()` (empaqueta el pronóstico final).
  - `MOTOR_PREDICCION_JORNADA.py` → `predict_jornada_from_model()`,
    `generate_jornada_prediction()` (genera las probabilidades del modelo por partido).
  - `CONFIG_MOTOR_V2.json` → `columns.price_per_column` (0,75 €), `beam_size` (6000)
    y `default_budget` (128, nueva).
  - Los JSON de jornada (`DATOS/QUINIELA15_J*.json`) ya contienen `lae`, `apu` y `q15`
    (porcentajes de público) por partido.
- **Qué hacer:**
  1. Haz que el paquete de jornada (`build_package`) incluya, además de la predicción
     1X2, el resultado de `OPTIMIZADOR_COLUMNAS` con:
     - probabilidades del motor (cuando existan; si no, `q15`/`lae` como fallback);
     - público = `lae` (o `apu`);
     - presupuesto y precio leídos de la config.
  2. Propón un contrato de salida estable (p. ej. `salida/paquete_j{N}.json` con
     `desarrollo`, `columnas_top`, `coste`, `monte_carlo`).
- **Aceptación:** `python PREDECIR_JORNADA.py --jornada 74` (o la jornada vigente)
  emite un JSON con el desarrollo optimizado y su coste; la lógica de
  `OPTIMIZADOR_COLUMNAS.py` se importa como módulo (no como script suelto).
- **Nota:** `OPTIMIZADOR_COLUMNAS.py` está en la raíz; si prefieres moverlo a
  `scripts/motor/`, hazlo con cuidado de no romper `PREDECIR_JORNADA.py`.
- **Resultado (31/07/2026):**
  - `OPTIMIZADOR_COLUMNAS.py` expone `optimize_jornada()` / `_optimize_partidos()`
    (importable como módulo) y trata el **Pleno al 15 aparte** (partido `pleno_num`,
    por defecto 15): se excluye del desarrollo y se juega como simple del favorito.
  - `PREDECIR_JORNADA.build_package()` añade `boleto_optimizado` al paquete:
    desarrollo (14 partidos + pleno), coste, distribución de aciertos y Monte Carlo.
    Usa las probabilidades del modelo cuando superan el control de calidad
    (`probs_override`); si no, Q15 + LAE (fallback probado con la jornada 74).
  - `CONFIG_MOTOR_V2.json` → `columns.default_budget = 128`.
  - Verificado: `python PREDECIR_JORNADA.py --jornada 74` genera el paquete con
    `boleto_optimizado` (108 columnas, 81,00 €, E[aciertos] 11,21 vs 9,75 del
    favorito). Detalles en la sección 6.

### T3 — Aplicar la calibración vector scaling en producción (P3) — ✅ HECHO 01/08/2026
- **Problema:** la calibración está validada en backtest pero no se aplica en las
  predicciones reales.
- **Dónde mirar:**
  - `scripts/backtests/CALIBRACION_PROBABILIDADES.py` → `calibrate_vectorscaling()`
    (extraerla a un módulo reutilizable, p. ej. `scripts/motor/calibration.py`).
  - `MOTOR_PREDICCION_JORNADA.py` → `_train_models()` (donde entrena logit+HGB) y
    `predict_jornada_from_model()` (donde emite probabilidades).
- **Qué hacer:**
  1. Mueve `calibrate_vectorscaling` (y sus métricas) a un módulo compartido.
  2. En `_train_models`, además de los modelos, ajusta el calibrador con el bloque de
     validación temporal (84/16 del histórico disponible, nunca la jornada a predecir).
  3. En `predict_jornada_from_model`, aplica el calibrador antes de emitir 1/X/2.
- **Aceptación:** un backtest con calibración aplicada muestra ECE ≤ 0,025 (vs 0,033
  sin calibrar) y log loss no peor; la jornada real usa probabilidades calibradas.
- **No:** calibrar con los mismos datos de evaluación (fuga temporal).
- **Resultado (01/08/2026):**
  - Nuevo módulo `scripts/motor/calibration.py` con `VectorScalingCalibrator`,
    `brier_multiclass`, `ece_by_confidence` y `calibrate_vectorscaling()` reutilizable.
    `CALIBRACION_PROBABILIDADES.py` ahora importa del módulo compartido.
  - `MOTOR_PREDICCION_JORNADA._train_models()` entrena logit/HGB finales con todo el
    histórico (vía `optimize_hybrid_config`) y además ajusta el calibrador con split
    temporal 84/16: entrena modelos temporales en subtrain, genera ensemble en valid
    con `apply_hybrid_config`, y ajusta vector scaling solo con valid. Nunca usa la
    jornada futura (no fuga).
  - `load_or_train_models()` cachea y devuelve `(logit, hgb, config, calibrator)`.
  - `predict_jornada_from_model()` aplica el calibrador tras `apply_hybrid_config`
    (re-calcula `modelo_pred` por argmax calibrado) y añade metadatos
    `fuente_probabilidades.calibracion` y `modelo_info.calibracion`.
  - Evidencia walk-forward 5 temporadas (sección 2.5): ECE 0,0326 → **0,0245**
    (≤0,025), LogLoss 1,0010 → **1,0001** (no peor), Brier 0,5987 → **0,5979**.
  - Verificación jornada real (J74 y Real Madrid-Barcelona 2026-08-15):
    `prob_1/prob_x/prob_2` calibradas, `calibracion.aplicada=true`,
    `pre_ece 0,0308 → post_ece 0,0164`, `log_loss 0,9944 → 0,9914` con 2152 partidos
    de validación. El paquete de jornada sigue funcionando y usa probabilidades
    calibradas cuando el control de calidad lo permite.

### T4 — Aplicar Dixon-Coles en producción (P4, bajo coste)
- **Problema:** el motor aún usa Poisson independiente (`poisson_1x2`) para el 1X2 y
  el Pleno al 15; el módulo DC (`scripts/motor/dixon_coles.py`) está sin conectar.
- **Dónde mirar:**
  - `scripts/motor/features.py` → `poisson_1x2()` (Poisson independiente actual).
  - `MOTOR_QUINIELA_MAESTRO.py` → `top_scorelines()` y `add_pleno_al_15()` (Pleno al 15).
- **Qué hacer:**
  1. Estima rho sobre el histórico disponible antes del corte (aprox. −0,04; usa
     `estimate_rho` con el grid por defecto).
  2. Usa `dc_1x2` / `dc_score_probs` en el Pleno al 15 y en las probabilidades que
     alimentan al optimizador. Para el 1X2 del ensemble, mide antes/después: si DC no
     mejora log loss fuera de muestra, mantén el Poisson independiente en el ensemble
     y usa DC solo para marcadores/pleno.
- **Aceptación:** comparativa documentada (1X2 y pleno) con y sin DC en walk-forward.

### T5 — Modelo de goles ataque/defensa (mejora de fondo para lambdas y DC)
- **Problema:** las lambdas actuales se construyen con goles recientes + tiros ×
  `goal_per_sot` (0,30). Es la base más débil del sistema y limita a DC y al Pleno.
- **Dónde mirar:**
  - `scripts/motor/features.py` → `TeamStateTracker.extract_match_features()` (donde
    se calculan `lambda_home`/`lambda_away`), `TeamStateTracker.update_match()`.
- **Qué hacer:**
  1. Implementa el modelo log-lineal:
     `log λ_local = μ + localía + ataque_local − defensa_visitante`,
     `log λ_visitante = μ + ataque_visitante − defensa_local`,
     con regresión a la media, ponderación temporal, ajuste por ascensos/descensos
     (`settings.transition_factors()`) y regularización para equipos con poca muestra.
  2. Valida por **log loss de marcadores** (no solo 1X2): compara contra las lambdas
     actuales en walk-forward. Conserva solo si mejora.
- **Aceptación:** tabla de comparación lambdas actuales vs nuevas (log loss de
  marcador, pleno top-3) por temporada; si no mejora, no se integra.

### T6 — Reproducibilidad y README (urgente, afecta a la confianza) — ✅ HECHO 31/07/2026
- **Problema:** el README declaraba 51,23 % pero se reproducía 50,52 %. La temporada
  2024-25 sí era exacta (52,38 % / 8,91), la 2025-26 no (README 50,36 % / 8,30 vs
  50,71 % / 8,41 reproducido).
- **Dónde mirar:** `README.md` (sección "Resultado de referencia").
- **Qué hacer:**
  1. Ejecuta `MOTOR_QUINIELA_MAESTRO.py --historico original` con las versiones de
     `requirements.txt` y actualiza las cifras del README a lo que salga.
  2. Añade al README: versiones exactas, fecha de ejecución y (si es fácil) un hash
     del dataset (`DATOS/historico_raw/**`) para saber cuándo cambian los datos.
- **Aceptación:** un colega con las mismas versiones reproduce el README exacto.
- **No:** ajustar umbrales hasta "recuperar" el 51,23 %: eso sería sobreajuste.
- **Resultado (31/07/2026):** README actualizado con las cifras reales de la
  configuración v4 (51,64 % / 8,63; 2024-25 52,49 % / 8,64; 2025-26 51,54 % / 8,50),
  versiones de librerías, fecha de ejecución y hash del dataset
  (`51a9688ac065015da9335512af5a34a8`). Detalles en la sección 6.

### T7 — Tests de los módulos nuevos
- Añade `tests/test_dixon_coles.py` (calibración numérica del factor tau, sumas a 1),
  `tests/test_optimizador_columnas.py` (presupuesto respetado, desarrollo válido,
  distribución de aciertos suma 1), `tests/test_ablation_smoke.py` (los scripts de
  backtest se importan sin errores).
- Ejecuta `pytest -q -m "not slow"` al final; la suite completa debe quedar en verde.

### T8 — Pendientes de la auditoría (posteriores, menor prioridad)
Si queda tiempo: flujo único de probabilidades (una sola función propietaria),
dataclasses/Pydantic para partido/probabilidad/recomendación, sistema de identidades
de equipos (módulo propio con alias y colisiones), incertidumbre por partido
(intervalos, desacuerdo entre modelos), registro de experimentos (hash de dataset,
versión de config, métricas). No bloquean las tareas T1–T7.

---

## 4. Mapa de rutas (dónde buscar cada cosa)

| Tema | Archivo(s) | Funciones/claves |
|---|---|---|
| Config de pesos | `CONFIG_MOTOR_V2.json` | `master_model.weights`, `weight_candidates`, `columns.*` |
| Ensemble y backtest | `MOTOR_QUINIELA_MAESTRO.py` | `optimize_hybrid_config`, `apply_hybrid_config`, `simulate_doubles`, `run_backtest` |
| Features point-in-time | `scripts/motor/features.py` | `TeamStateTracker`, `poisson_1x2`, `rolling_team_features` |
| Predicción de jornada | `MOTOR_PREDICCION_JORNADA.py` | `_train_models`, `predict_jornada_from_model`, `generate_jornada_prediction` |
| Paquete final | `PREDECIR_JORNADA.py` | `build_package`, `build_recommendation_for_match` |
| Datos de jornada | `DATOS/QUINIELA15_J*.json` | campos `q15`, `lae`, `apu`, `sistema`, `comunidad` |
| Optimizador de boleto | `OPTIMIZADOR_COLUMNAS.py` | `develop_ticket`, `select_diverse_columns`, `monte_carlo` |
| Calibración | `scripts/backtests/CALIBRACION_PROBABILIDADES.py` | `calibrate_vectorscaling` (mover a `scripts/motor/calibration.py`) |
| Dixon-Coles | `scripts/motor/dixon_coles.py` | `dc_1x2`, `dc_score_probs`, `estimate_rho` |
| Resultados esperados | `salida/*.json` (regenerables) | `ablacion_modelos`, `walk_forward_pesos`, `opt_boleto_j*`, `dixon_coles` |

---

## 5. Reglas de oro (resumen)

1. Nunca entrenar con datos posteriores a la evaluación (fuga temporal = resultado
   falso). Esto incluye la calibración.
2. Toda mejora se decide con walk-forward y contra el favorito de mercado, no con un
   máximo aislado ni sobre los mismos datos de ajuste.
3. No cambiar la config activa por una sola temporada buena.
4. Si una cifra no reproduce, se actualiza el README; nunca se "recupera" la cifra a
   base de umbrales.
5. No subir `salida/` ni cacharros a git (ya está en `.gitignore`).
6. Este documento se actualiza al cerrar cada tarea (marca T1–T8 con su resultado),
   siguiendo el estilo de `ROADMAP_PROGRAMA_QUINIELA.md` y `AGENTS.md`.

---

## 6. Registro de ejecución

Tareas completadas sobre el repositorio, con fecha, cambio y evidencia. Antes de
empezar una tarea nueva, comprueba aquí y en el §3 que nadie la ha hecho ya.

### 31/07/2026 — T1 (config de pesos v4) y T6 (README)

- **T1 — Activar la nueva configuración de pesos.**
  - `CONFIG_MOTOR_V2.json`: `version` → `motor_quinielistico_v4`; `weights` →
    `{logit 0.0, hgb 0.049, market 0.951, poisson 0.0}`; `weight_candidates` → 4
    combinaciones mercado-dominantes.
  - Evidencia (walk-forward, sección 2.3): el consenso gana/empata al mercado en 4/5
    temporadas y mejora ECE (0,031 vs 0,034) sin perder log loss ni Brier.
  - Backtest principal (`MOTOR_QUINIELA_MAESTRO.py --historico original`):

    | | Antes (v3) | Después (v4) | Mercado |
    |---|---|---|---|
    | Acierto simple | 50,52 % | **51,64 %** | 51,56 % |
    | 3 dobles | 8,57 | **8,63** | 8,62 |
    | 2024-25 | 52,38 % / 8,91 | 52,49 % / 8,64 | 52,38 % |
    | 2025-26 | 50,71 % / 8,41 | 51,54 % / 8,50 | 51,54 % |

  - El grid eligió candidatos de la familia nueva (market 0,80–0,95 + HGB 0,05–0,20;
    logit y poisson a 0). La config activa ya no pierde contra el mercado.
- **T6 — README regenerado** con las cifras de la configuración v4, versiones de
  librerías, fecha (31/07/2026) y hash del dataset `51a9688ac065015da9335512af5a34a8`.

### 31/07/2026 — T2 (integración del optimizador de boletos)

- `OPTIMIZADOR_COLUMNAS.py` refactorizado: `optimize_jornada()` / `_optimize_partidos()`
  reutilizables; el Pleno al 15 (partido `pleno_num`, por defecto 15) se excluye del
  desarrollo y se juega como simple del favorito.
- `PREDECIR_JORNADA.build_package()` añade `boleto_optimizado` al paquete de jornada
  (desarrollo, coste, distribución de aciertos, Monte Carlo). Fuente de probabilidades:
  modelo (si supera el control de calidad) → Q15; público: LAE.
- `CONFIG_MOTOR_V2.json` → `columns.default_budget = 128`.
- Verificado con `python PREDECIR_JORNADA.py --jornada 74`: paquete con
  `boleto_optimizado` (108 columnas, 81,00 €; E[aciertos] 11,21 vs 9,75 del favorito;
  P(≥13) 35,7 %). En jornadas con equipos sin histórico español (nórdicos), el modelo
  queda marcado como no fiable por el control de calidad y el boleto usa Q15/LAE —
  comportamiento previsto.

### 01/08/2026 — T3 (calibración vector scaling en producción)

- Nuevo módulo `scripts/motor/calibration.py` extraído de `CALIBRACION_PROBABILIDADES.py`:
  `VectorScalingCalibrator` (wrapper de `LogisticRegression` sobre log-probs con
  `fit(probs, y)` y `predict(probs)`), métricas `brier_multiclass`,
  `ece_by_confidence`, helpers `calibrate_vectorscaling` y `evaluate_calibration`.
- `scripts/backtests/CALIBRACION_PROBABILIDADES.py` refactorizado para importar del
  módulo compartido (`EPS`, `VectorScalingCalibrator`, métricas) y usar
  `VectorScalingCalibrator` en lugar de re-implementar.
- `MOTOR_PREDICCION_JORNADA.py`:
  - `_train_models()` devuelve además `calibrator`: optimiza config híbrida con
    `optimize_hybrid_config`, re-entrena full histórico, luego split 84/16 temporal
    para calibrador (subtrain → modelos temporales → ensemble en valid →
    `VectorScalingCalibrator.fit`).
  - `load_or_train_models()` → 4 valores con cache de calibrador.
  - `predict_jornada_from_model()` aplica calibrador tras `apply_hybrid_config`,
    recalcula `modelo_pred`, añade `fuente_probabilidades.calibracion` por partido
    y `modelo_info.calibracion` global con `pre/post ECE/log_loss/Brier` y `n_calibration`.
- Evidencia:
  - Walk-forward 5 temporadas: ECE 0,0326→0,0245, LogLoss 1,0010→1,0001, Brier
    0,5987→0,5979 (criterio aceptación cumplido).
  - Jornada 74 (nórdica, sin cuotas): calibrado true, `pre_ece 0,0308 → post_ece 0,0164`,
    `pre_log_loss 0,9944 → 0,9914`, 2152 partidos validación.
  - `PREDECIR_JORNADA.py --jornada 74` sigue generando `SALIDAS/paquete_jornada_J74.json`
    con boleto optimizado; el modelo queda marcado como no fiable por calidad (<0.2)
    para equipos nórdicos (comportamiento esperado).
  - `pytest -q -m "not slow"` en verde (32 tests).

Pendiente para próximas sesiones: T4 (Dixon-Coles en producción), T5 (modelo de goles),
T7 (tests), T8 (higiene).
