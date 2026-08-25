# Investigación: Cómo hacer un programa de Quinielas MEJOR que las apuestas existentes

> Fecha: 2026-08-25 (Europe/Madrid) · Autor: Agent Arena · Branch: arena/01a038d2-programaquiniela
> Objetivo: Analizar el programa actual, compararlo con lo que hacen casas y “quinielas inteligentes”, y proponer mejoras concretas con criterio de ROI real, no solo acierto.

---

## 0. Resumen ejecutivo en 30 segundos

**Tu programa ya es MUY superior a las “quinielas inteligentes” del mercado** (El Pollito de Oro, Maxiloto, etc.). Ellas son heurísticos con marketing de IA: “coeficiente de incertidumbre”, aleatoriedad, estadísticas básicas [1](https://www.elpollitodeoro.com/quiniela-inteligente)[2](https://www.maxiloto.es/jugadas-inteligentes-quiniela-ia). Tu motor tiene:

- Histórico 2010-2026 (13.446 partidos) con backtest walk-forward por temporada
- Features point-in-time sin fuga intra-fecha (Elo, forma, tiros, tabla, descanso)
- Ensemble validado: **mercado 0.951 + HGB 0.049** (logit/poisson a 0)
- Dixon-Coles rho=-0.036 para Pleno al 15, calibración vector scaling, contrato P0 (3 dobles = 8 columnas = 6€)
- Evaluación económica real (EV/ROI por escenario fácil/normal/difícil)

**El diagnóstico honesto del repo es:**
- Acierto simple medio 7 temporadas: **50.27%** vs mercado **49.83%** → +0.44 pp, p=0.0436 McNemar, IC95 [+0.02,+0.85] (production_reference.json). Es estadísticamente significativo pero económicamente ruido.
- Media 3 dobles: **8.48/15**. P(≥12) modelo 3.57% vs solo-mercado 0.77% → 4.7× más. Ahí está tu edge real.
- ROI boleto 6€ con premios ESTIMADOS manus.ai: **fácil -93%, normal -50%, difícil +492%** vs solo-mercado -99%/-92%/-13%. Solo rentable en jornadas difíciles/botes. Esto confirma la literatura: el mercado 1X2 es casi eficiente, el edge de la Quiniela no está en predecir mejor, sino en **colocar dobles donde el público se equivoca y donde el premio no se reparte** [3](https://www.researchgate.net/publication/362022551_Dissecting_Poisson_based_prediction_models_in_association_football_A_comprehensive_look_at_methodology_assumptions_and_accuracy_using_data_from_the_main_European_Leagues_2011_-_2022).

**Para superarlo no necesitas más acierto simple. Necesitas:**
1. Medir y optimizar **EV parimutuel** (premio / nº de acertantes), no acierto.
2. Atacar **ineficiencias de contexto** que las cuotas de apertura descuentan mal (final de temporada, rotaciones, ascenso/descenso, fatiga).
3. Modelo de goles ataque/defensa jerárquico con decaimiento temporal + xG Understat.
4. Construcción de boleto por valor anti-popularidad, no por segunda probabilidad sola.

El resto de este documento detalla 12 palancas con coste/impacto y un roadmap v5.

---

## 1. Estado actual — auditoría rápida del código

### 1.1 Arquitectura
```
load_raw_history() → rolling_team_features() [TeamStateTracker sin fuga intra-fecha]
  → feature_columns() ~65 features
  → build_hgb_model() + build_logit_model() (logit condicional, peso 0)
  → optimize_hybrid_config() walk-forward 3 últimas temporadas, métrica mean-0.5*std
  → apply_hybrid_config() + _apply_calibracion_bandas() + cobertura_bandas
  → simulate_doubles() 3 dobles, evaluación exhaustiva C(14,3)=364 en OPTIMIZADOR_COLUMNAS
  → evaluation/economics.py EV por convolución exacta
```

- `MOTOR_QUINIELA_MAESTRO.py` 1200 líneas, `features.py` 907, `MOTOR_PREDICCION_JORNADA.py` 944. Monolíticos pero disciplinados.
- Config activa v4: `weights {market 0.951, hgb 0.049, logit 0, poisson 0}`, `dixon_coles {rho -0.036, use_for_pleno true}`, `calibracion_bandas {enabled true, ventana 6, cap 0.10, factores congelados 2026-27}`, `cobertura_dobles_banda {visita 2.5-4.0=1X, local 1.4-1.8=1X}`.
- `settings.py` lee `CONFIG_MOTOR_V2.json` como fuente única de verdad.

### 1.2 Features actuales (reales, no APU/LAE)
Elo con ventaja local 55 y K=24, forma 5 últimos (pts, gf, ga, local/visita), tiros/SOT 5, xG 5 (pero cobertura 0% histórico, solo estructura), tabla point-in-time (pos, pj, pts, ppg, gd), días descanso, market implied (close AvgCH/CD/CA → fallback open), market_move, market_entropy, close_open_fav_gap, lambda_home/away via `safe_pair_mean(home_gf, away_ga)` y `shot * goal_per_sot 0.30`, poisson_1X2 y opcional dc_poisson_1x2.

**Gap:** lambdas son medias simples, no modelo ataque/defensa. Es la base más débil y limita a Dixon-Coles y Pleno.

### 1.3 Validación
- Corte por fecha (no por fila) — corrige fuga 2023-04-16.
- `validate_odds_timestamps()` invariante `odds_observed_at <= prediction_cutoff_at < kickoff_at` pero sin timestamps reales en JSON actuales → `no_auditado`.
- Backtest walk-forward 2019-2026, 842 partidos/season, 5894 total para significancia.
- Tests: 290 passed (production_reference).

### 1.4 Economía
`evaluation/economics.py` usa convolución exacta (misma que optimizador) para P(k), EV = Σ P(exacto k)*premio(k). Escenarios: fácil/normal/difícil con rangos manus.ai. Compara modelo vs solo-favoritos-mercado.

**Hallazgo clave P0.1/P0.2/P1.0 (EXPERIMENTOS_REGISTRO.md):**
- Calibración VectorScaling mejora ECE 0.0326→0.0245 y LogLoss, pero con evaluación **leak-free** (calibrador solo con temporadas previas) **empeora** P(≥12) 3.57%→2.04% (0/5). Rechazada para boleto, mantenida solo como diagnóstico.
- Divergencia HGB-mercado: solo tramo +0.05/+0.10 tiene +2% acierto (849 casos), >+0.10 es sobreconfianza -2.1% (245 casos). Rechazada como regla universal.
- Ensemble simplificado P1.2: logit/poisson con peso 0 eliminados del path crítico → iso-resultado, más rápido.

---

## 2. Qué hacen las “apuestas que ya hay” — benchmark real

| Sistema | Qué hace realmente | Validación | Edge vs mercado |
|---|---|---|---|
| **El Pollito de Oro / Maxiloto Quiniela Inteligente** | Heurístico: estadísticas básicas + coeficiente incertidumbre (aleatoriedad) + IA marketing. Usuario elige dobles/triples e incertidumbre 20% [1](https://www.elpollitodeoro.com/quiniela-inteligente) | Sin backtest público, sin ROI | 0 — es wrapper de favorito + ruido |
| **Casas (Bet365, etc.)** | Cuotas con overround 4-5%, ajustadas por flujo dinero y sharp money [4](https://topscorerdaily.com/premier-forecasts/premier-league-predictions-england-data-driven-match-analysis). 50-58% acierto 1X2 con Dixon-Coles, log loss 0.85-0.95 [5](https://www.golsinyali.com/en/blog/best-football-prediction-algorithms-2026) | Eficiente en 1X2, sesgo favorite-longshot | Rey |
| **Tu motor v4** | Walk-forward, HGB residual, DC, bandas, evaluación exhaustiva dobles, EV | 7 temporadas, McNemar p=0.043, 290 tests | +0.44pp acierto, +4.7× P≥12 |

**Conclusión:** Ya estás por encima. Para superarlo de verdad hay que dejar de competir en acierto simple (donde nadie gana) y competir en **EV parimutuel**.

### 2.1 Teoría por qué el mercado 1X2 es casi imbatible
Literatura: Dixon-Coles corrige Poisson solo en 4 marcadores (0-0,1-0,0-1,1-1) con tau, pero mejora es pequeña [6](https://statsultra.com/dixon-coles-model/). xG mejora RPS 65.6% vs EPV 59.6% [7](https://www.golsinyali.com/en/blog/best-football-prediction-algorithms-2026), pero necesitas ventana 4 temporadas + time decay xi 0.001-0.003 [8](https://pena.lt/y/2025/03/10/which-model-should-you-use-to-predict-football-matches/). Incluso modelo xG simple con Skellam + isotonic no bate consistentemente a bookmakers [9](https://journals.sagepub.com/doi/10.1177/22150218261416681). En college football, favoritos sobrevalorados sistemáticamente, pero casas ajustan líneas para contrarrestar hot-hand [10](https://www.aeaweb.org/conference/2010/retrieve.php?pdfid=406). En NFL, longshot bias existe pero ROI sigue negativo -3% a -4% [11](https://myweb.ecu.edu/robbinst/PDFs/Weak%20Form%20Efficiency%20in%20Sports%20Betting%20Markets.pdf).

**Traducción a Quiniela:** el boleto no es apuesta a cuota fija, es **parimutuel**. Tu EV depende de cuántos otros aciertan lo mismo. Aunque tu prob sea igual que mercado, si eliges combinaciones impopulares (visitante valor, empate oculto) tu premio esperado sube porque se reparte menos.

---

## 3. Las 12 palancas para hacerlo mejor — con coste/impacto

### Palanca 1: Modelo ataque/defensa jerárquico con time decay (P1.1 original T5)
**Problema actual:** lambda = mean(gf últimos 5, ga rival) + tiros*0.30. No distingue ataque vs defensa, no pondera antigüedad, no maneja ascensos.

**Solución:**
```python
log λ_home = μ + home_adv + att_home - def_away
log λ_away = μ + att_away - def_home
```
- Estimación MLE por temporada con pesos Dixon-Coles `w(t)=exp(-xi*Δt)` xi~0.0015, lookback 4 temporadas [8].
- Regresión a la media para equipos nuevos: `att_new = factor * att_prev`, usando `transition_factors` ya en config (segunda_a_primera 0.78, etc.).
- Regularización L2 (prior gaussiano) para equipos con <10 partidos.
- Validar por **log loss de marcador**, no solo 1X2. Comparar vs lambda actual en walk-forward.

**Coste M, Impacto Alto.** Es la base para todo lo demás (DC, Pleno).

### Palanca 2: xG Understat real (no Highlightly)
Highlightly solo tiene xG 2025/26, no histórico [EXPERIMENTOS_REGISTRO]. Understat tiene Primera 2014+ (~75% Primera). Ya tienes `DESCARGAR_XG_UNDERSTAT.py` + `MEDIR_COBERTURA_XG.py`.

**Integración:**
- `scripts/motor/xg_understat.py merge_xg()` ya añade columnas, pero `feature_columns()` no incluye xG activamente (experimento A/B mostró -0.29pp, rechazado).
- Nuevo intento: no usar xG como feature directa del HGB (mercado ya lo descuenta), sino como **feature para lambdas ataque/defensa**: `xg_for_diff` y `xg_against_diff` ya existen, usarlas para ajustar att/def.
- Validar solo en Primera, con imputación flag `sin_xg`.

**Coste M, Impacto Medio.** No esperes +2pp, pero mejora lambdas y Pleno.

### Palanca 3: Features de contexto automatizables (donde el mercado falla)
Tu config ya tiene `manual_context_flags` [final_temporada, rotaciones, ascenso_descenso...] pero son manuales. Automatízalas point-in-time:

- **Motivación:** distancia a ascenso/descenso vía tabla ppg, jornada relativa (jornada 35+/42), `home_table_pos` y `away_table_pos` ya existen → deriva `motivacion_diff = f(pos, pts_restantes, objetivo)`. Literatura: partidos intrascendentes sesgan favorito mercado.
- **Fatiga:** `days_rest_diff` existe, pero añade interacción `days_rest * elo_diff` + `partidos_ultimos_14_dias`.
- **Derbi/rivalidad:** lista estática de derbis (Sevilla-Betis, etc.) + misma comunidad autónoma.
- **Entrenador:** cambio entrenador últimos 3 partidos (si consigues fuente, si no, proxy: forma muy mala + nuevo entrenador = bounce).
- **Rotaciones:** entre semana (ya tienes `boost_favorito_entre_semana` 0.02) → generalizar a `es_entre_semana` y `competicion_europea_previa`.

**Validación:** cada feature solo entra si mejora P(≥12) o ROI en walk-forward multi-split con regla `mean-0.5*std` y gana en ≥4/5 últimas.

**Coste S/M, Impacto Potencial Alto.** Es donde está el edge según auditoría Grok.

### Palanca 4: Modelar al público (LAE/Q15/APU) y optimizar EV, no acierto
Actualmente `OPTIMIZADOR_COLUMNAS` maximiza E[aciertos] = suma prob favorito + segunda prob. Ranking por segunda prob = ranking por E[aciertos]. Correcto para aciertos, **incorrecto para dinero**.

**Nuevo objetivo:**
```
EV(boleto) = Σ_k P_modelo(k aciertos) * Premio(k) / E[N_acertantes(k)]
E[N_acertantes(k)] ≈ N_total_apuestas * P_publico(k)
P_publico(k) = convolución con probs LAE/Q15
```
- Ya tienes `lae`, `q15`, `apu` por partido en JSON jornada. Usa `lae` como proxy público (es el % real de columnas jugadas LAE).
- `column_value()` actual hace `log(p_model) - alpha*log(p_public)` con alpha 0.6 solo para ranking columnas. **Extiéndelo a selección de dobles**: evalúa las 364 combinaciones no por E[aciertos] sino por EV estimado con premios escenario normal.
- Implementa `evaluation/economics.py` → `ev_by_public()` que calcula EV ajustado por popularidad.

**Ejemplo:** partido con favorito 70% mercado, pero público 85% (sobreapostado). Doblar 1X vs X2: E[aciertos] puede ser similar, pero EV de X2 es mucho mayor si sale porque pocos lo llevan.

**Coste M, Impacto 🔥 Alto.** Es el corazón para batir Quiniela.

### Palanca 5: Construcción de boleto con diversidad y múltiples presupuestos
Contrato P0 es 3 dobles = 6€, pero la ley permite hasta 8 triples, etc. Tu optimizador ya evalúa 364 combos exactos. Siguiente:

- **Presupuesto variable:** genera boleto óptimo para 6€, 12€ (4 dobles), 24€, 48€ con algoritmo genético: empieza con 3 dobles óptimos, añade doble donde más sube EV/€.
- **Diversidad:** en vez de 8 columnas idénticas salvo dobles, selecciona top-N columnas por valor con penalización de correlación (no todas con mismo signo). Ya tienes `select_diverse_columns` en roadmap.
- **Cobertura inteligente:** evita dobles sobreconfiados (`double_avoid_overconfidence` ya existe, diff HGB-mercado >0.10) y fuerza 1X en bandas robustas (ya hecho).

**Coste S, Impacto Medio.**

### Palanca 6: Pleno al 15 con Negative Binomial y Bivariate Poisson
DC corrige solo 4 marcadores. Para Pleno necesitas buckets 0/1/2/M. Mejora:

- **Negative Binomial** maneja overdispersion: Var = μ + αμ², mejor para goleadas 5-0 que Poisson subestima [4]. α estimado por liga.
- **Bivariate Poisson** modela correlación de goles más allá de DC (útil en partidos abiertos).
- **Weibull Count + Copula** es más flexible pero costoso [8]. Prueba NB primero.
- Usa xG para lambdas del Pleno, no solo gf/ga.

**Coste M, Impacto Bajo-Medio** (Pleno es separado, pero paga mucho).

### Palanca 7: Calibración y cuantificación de incertidumbre
VectorScaling rechazado para boleto, pero útil para diagnóstico. Añade:

- **Conformal prediction:** intervalos de confianza por partido, no solo prob puntual. Útil para decidir dónde poner doble.
- **Desacuerdo modelos:** `model_disagreement` ya existe, úsalo como feature de riesgo (si logit y HGB discrepan mucho, partido abierto → candidato triple).
- **ECE por división:** Primera vs Segunda calibran distinto.

**Coste S, Impacto Medio.**

### Palanca 8: Ingesta de cuotas reales en tiempo real
Actualmente usas `AvgCH/CD/CA` histórico. Para producción:

- **Odds API:** Football-Data, The Odds API, Betfair Exchange (mejor proxy de prob real sin overround).
- **Timestamps:** implementa `odds_observed_at` real en JSON jornada, valida invariante. Ya tienes `validate_odds_timestamps`.
- **Closing Line Value:** compara tu prob vs cierre, mide CLV como métrica de calidad.
- **Mercado como feature, no como target:** en vez de ensemble peso mercado, usa `market_1, market_x, market_2, market_move, market_entropy` como features del HGB (ya están), y deja que HGB aprenda cuándo fiarse del mercado.

**Coste M, Impacto Medio.**

### Palanca 9: CatBoost + Ensemble económico
Tu HGB es bueno (ECE 0.013 vs mercado 0.030), pero CatBoost suele ganar en tabular con categorical [7]. Prueba:

- **CatBoost con class_weights [1.0,1.3,1.0]** para empates (más difíciles) — usado por ExPrysm con 69 features, P=0.70*CatBoost+0.30*Poisson [12](https://exprysm.com/insights/methodology/dixon-coles-model.html).
- **Ensemble económico:** no optimices pesos por log loss, sino por P(≥12) o ROI en validación. `EXPERIMENTO_ENSEMBLES_ECONOMICO.py` ya lo hace, pero con fuga parcial. Rehacer leak-free.

**Coste M, Impacto Medio.**

### Palanca 10: Paper trading 2026/27 y gestión bankroll
Ya tienes `PAPER_TRADING_2627.py` y `temporada_2026_27_estadisticas_base.json` con priors ajustados por transición.

- Corre paper trading cada jornada con boletos reales LAE (`DATOS/boletos_lae_reales/`) y compara vs Q15.
- **Bankroll:** no juegues todas las jornadas. Juega solo cuando EV estimado > umbral (jornadas difíciles, botes, alta incertidumbre). Usa Kelly fraccional para Quiniela: f = EV / Var, con tope 2% bankroll.
- Registra en `DATOS/registro_experimentos.json` append-only.

**Coste S, Impacto Alto** (evita quemar dinero en jornadas fáciles donde ROI -93%).

### Palanca 11: Feature store y prediction_engine aislado
Roadmap P0.3: extraer `prediction_engine/` con interfaz pura `predict(features) -> {p1,pX,p2,lambda_home,lambda_away}` sin I/O. Beneficio: tests rápidos, iso-resultado, permite experimentar sin romper optimizador.

**Coste L, Impacto Alto** a largo plazo.

### Palanca 12: Datos de jugadores (Transfermarkt, lesiones, alineaciones)
Más caro, pero última frontera:

- Valor de mercado plantilla, bajas clave (lesionados, sancionados), alineación probable.
- Fuente: Transfermarkt + API-Football. Necesitas histórico consistente (difícil, por eso REVISION_12 lo bloqueó).
- Empieza con proxy simple: nº de titulares habituales con >80% minutos ausentes.

**Coste L, Impacto Incierto.**

---

## 4. Roadmap v5 propuesto — qué hacer en orden

### Fase P0 (ya hecho, consolidar)
- [x] Métrica económica EV/ROI (P0.1)
- [x] Experimento ensembles económico (P0.2)
- [x] Contrato columnas fijo + optimizador exhaustivo 364 combos + convolución exacta
- [x] Referencia producción reproducible + CI

### Fase P1 (próximas 2-4 semanas) — donde está el dinero
**P1.1 — Contexto automatizado (Palanca 3)**
- Implementar `motivacion_diff`, `fatiga_interaccion`, `es_derbi` como features point-in-time en `TeamStateTracker`.
- Walk-forward: si mejora P(≥12) en ≥4/5 temporadas y score robusto, entra. Si no, RECHAZADO documentado.

**P1.2 — EV parimutuel (Palanca 4) — EMPEZAR AQUÍ**
- Extender `OPTIMIZADOR_COLUMNAS` para evaluar 364 combos por EV con `lae` como público, no solo E[aciertos].
- Nuevo script `EXPERIMENTO_EV_PUBLICO.py`: compara boleto max-E[aciertos] vs max-EV.
- Criterio: gana EV neto en ≥4/5 temporadas.

**P1.3 — Modelo ataque/defensa con decay (Palanca 1)**
- Reescribir `extract_match_features` lambdas con modelo log-lineal + `weights_dc`.
- Validar por log loss marcador y P(≥12).

### Fase P2 (1-2 meses)
- P2.1 CatBoost + ensemble económico leak-free (Palanca 9)
- P2.2 Ingesta cuotas reales + CLV (Palanca 8)
- P2.3 Paper trading + filtro jornadas difíciles (Palanca 10)
- P2.4 Negative Binomial para Pleno (Palanca 6)

### Fase P3 (estructural)
- P3.1 prediction_engine aislado (Palanca 11)
- P3.2 Feature store + Makefile `make backtest`, `make predict J=...`
- P3.3 Datos jugadores si hay fuente histórica (Palanca 12)

---

## 5. Qué NO hacer (para no perder tiempo, según registro)

- Re-implementar clasificador binario empate global → **rechazado** AUC 0.55, empeora LogLoss.
- Divergencia universal → **rechazada**, solo rango +0.05/+0.10 vale, y ni eso es consistente.
- Añadir más features estadísticas clásicas (tiros, posesión) esperando batir mercado → mercado ya las descuenta (experimentos previos).
- Activar xG como feature directa HGB → evaluado -0.29pp, no entra. Usar solo para lambdas.
- VectorScaling en camino crítico boleto → P1.0 lo rechazó leak-free (P≥12 2.04% vs 3.57%).
- Overfit a una temporada buena → regla: ≥4/5 temporadas + mean-0.5*std.

---

## 6. Cómo sería el motor v5 ideal (contrato)

```python
# prediction_engine/predict.py
def predict_match(home, away, date, division, market_odds, context) -> dict:
    # features point-in-time con TeamStateTracker + contexto automatizado
    # lambdas = attack_defense_model(home, away, date, decay=0.0015, lookback=4y)
    # p_1x2_market = implied(market_odds)  # close Avg
    # p_1x2_model = catboost(features + market_features)
    # p_1x2 = 0.95*market + 0.05*model  # pesos walk-forward
    # p_1x2_calibrated = vector_scaling(p_1x2) # solo diagnóstico
    # score_probs = negative_binomial(lambdas, alpha_league) * dixon_coles_tau(rho)
    # return {p1, pX, p2, lambdas, score_probs, confidence, disagreement}
```

```python
# optimizer/ev_optimizer.py
def optimize_ticket_ev(probs_model, probs_public_lae, premios_escenario, presupuesto=6):
    # evalua 364 combos por EV = sum_k P_model(k)*premio(k)/E[N_public(k)]
    # E[N_public(k)] = N_total * conv(public_probs)
    # selecciona combo max EV, luego columnas por valor anti-popularidad con diversidad
```

---

## 7. Conclusión honesta

Tu programa **ya bate a las quinielas inteligentes comerciales** por goleada en rigor, reproducibilidad y evaluación económica. Pero **no bate al mercado 1X2 de forma rentable en jornadas normales** porque nadie lo hace de forma consistente: es eficiente por diseño [10][11].

**El camino para ser mejor que las apuestas no es predecir mejor el 1X2.** Es:

1. **Aceptar que el mercado es el rey** (peso 0.951 lo demuestra) y usarlo como base.
2. **Medir en dinero parimutuel**, no en acierto. Tu P(≥12) 3.57% vs 0.77% es el verdadero edge.
3. **Cazar ineficiencias de contexto** que las cuotas de apertura no descuentan (motivación, fatiga, rotaciones) y **explotar sesgos del público** (LAE sobreapuesta favoritos, infravalora visitante y empate).
4. **Jugar solo jornadas difíciles/botes** donde ROI pasa de -50% a +492%.

Si implementas Palanca 4 (EV público) + Palanca 3 (contexto) + Palanca 1 (ataque/defensa), tienes una mejora esperada de **+1-2pp en P(≥12) y +50-100% EV relativo** según experimentos similares [8][12]. No es magia, es ingeniería disciplinada walk-forward.

**Próximo paso inmediato recomendado:** Implementa `EXPERIMENTO_EV_PUBLICO.py` (Palanca 4). Es 1-2 días, impacto alto, y te dice si el boleto óptimo por EV es distinto al óptimo por aciertos. Si lo es, reescribe `OPTIMIZADOR_COLUMNAS` para optimizar EV. Ese es el salto de “programa que acierta” a “programa que gana dinero”.

---

## Referencias y fuentes

- Datos internos: `CONFIG_MOTOR_V2.json`, `reports/production_reference.json`, `EXPERIMENTOS_REGISTRO.md`, `ROADMAP_MEJORA_AUDITORIA_GROK.md`, `scripts/motor/features.py`, `OPTIMIZADOR_COLUMNAS.py`, `evaluation/economics.py`
- Quiniela inteligente heurística: El Pollito de Oro [1], Maxiloto [2]
- Modelos Poisson/Dixon-Coles: Dissecting Poisson models 2011-2022 [3], StatsUltra DC [6], Pena.lt comparativa modelos [8], Goalmodel R package [13]
- Estado del arte 2026: Best AI Football Prediction Algorithms [5][7]
- xG y calibración: Skellam + isotonic Bundesliga 2014-25 [9]
- Eficiencia mercados: College football favorite overpricing [10], NFL weak form [11], NYU Stern inefficiency [14]
- Producción ensemble CatBoost+Poisson: ExPrysm methodology [12]

[1] https://www.elpollitodeoro.com/quiniela-inteligente
[2] https://www.maxiloto.es/jugadas-inteligentes-quiniela-ia
[3] https://www.researchgate.net/publication/362022551_Dissecting_Poisson_based_prediction_models_in_association_football_A_comprehensive_look_at_methodology_assumptions_and_accuracy_using_data_from_the_main_European_Leagues_2011_-_2022
[4] https://topscorerdaily.com/premier-forecasts/premier-league-predictions-england-data-driven-match-analysis
[5] https://www.golsinyali.com/en/blog/best-football-prediction-algorithms-2026
[6] https://statsultra.com/dixon-coles-model/
[7] https://www.golsinyali.com/en/blog/best-football-prediction-algorithms-2026
[8] https://pena.lt/y/2025/03/10/which-model-should-you-use-to-predict-football-matches/
[9] https://journals.sagepub.com/doi/10.1177/22150218261416681
[10] https://www.aeaweb.org/conference/2010/retrieve.php?pdfid=406
[11] https://myweb.ecu.edu/robbinst/PDFs/Weak%20Form%20Efficiency%20in%20Sports%20Betting%20Markets.pdf
[12] https://exprysm.com/insights/methodology/dixon-coles-model.html
[13] https://github.com/opisthokonta/goalmodel
[14] https://www.stern.nyu.edu/sites/default/files/assets/documents/con_042958.pdf
