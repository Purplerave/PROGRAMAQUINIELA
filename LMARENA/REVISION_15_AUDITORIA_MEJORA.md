# REVISION_15 · Auditoría de Mejora — Calibración y Señales Contextuales

> **Informe técnico.** Auditoría exhaustiva de oportunidades de mejora para
> PROGRAMAQUINIELA usando su propio histórico (2010-11 → 2025-26, 13.448
> partidos con cuotas) + todo el análisis previo (REVISION_14).
>
> - **Fecha:** 2026-08-24 · **Datos:** histórico del repo + football-data.co.uk
> - **Código asociado:** `purplerave/calibrador_bandas.py` (drop-in, solo stdlib),
>   `purplerave/auditoria_mejoras.py`, `purplerave/auditoria_mejoras_2.py`
> - **Protocolo:** walk-forward por temporada; sin datos futuros en entrenamiento.

---

## 0. RESUMEN EJECUTIVO Y RECOMENDACIONES PRIORIZADAS

| # | Acción | Ganancia esperada | Riesgo |
|---|---|---|---|
| 1 | **Calibrador de bandas rodante** (visitante 2.5-4.0 ↓, local 1.4-1.8 ↑) | Brier −0.0006 en era reciente (mejora 6/7 temporadas 2020+); alimenta el optimizador de dobles | Bajo (CAP ±10%, ventana 6 temp.) |
| 2 | **Boost de favorito en jornadas entre semana** (+2pp prob.) | Señal +4pp ROI consistente en ambas eras (n=1.059) | Bajo-medio |
| 3 | **Flag manual "equipo hundido en casa, últimas 8 jornadas"** | +12/+24% ROI por era, pero n≈50/temporada | Medio (muestra pequeña) |
| 4 | NO hacer: boost de empate global, ajustes por descanso, steam-betting B365 | Todas testadas → sin edge | — |

**Honesto:** ninguna de estas acciones es una revolución. El motor ya es 95%
mercado y el mercado está bien calibrado globalmente. Las ganancias son de
décimas (Brier) y su mayor valor está en la **selección de dobles** (segunda
probabilidad) y en la futura integración del reparto público (pari-mutual).

---

## 1. DIAGNÓSTICO DEL MOTOR ACTUAL (CONFIG_MOTOR_V2.json)

- Ensemble v4: `market 0.951 / hgb 0.049 / logit 0 / poisson 0`.
- `draw_boost = 0.0` y `segunda_draw_boost = 0.0` (candidatos solo [0.0]) →
  consistente con nuestro hallazgo: el empate en Segunda está SOBREpagado en
  apuestas (ROI −11,6% / −1,0%); no hay motivo para boostearlo.
- `nordic_football_data.enabled = false`: ya probaron mezclas calibradas sin
  mejora ("calibrated blends did not improve it"). Nuestra auditoría confirma
  POR QUÉ a nivel global (sección 2) y matiza: la descalibración existe, pero
  es **por bandas y dependiente de régimen** (sección 3).
- `thresholds` ya incluye conceptos afines (`visitor_value_market: 0.23`,
  `hidden_draw_market: 0.28`) → la integración natural es vía probabilidades
  calibradas antes del módulo de decisión, no vía umbrales nuevos.
- Referencia de producción (walk-forward 2019-26): acc simple 50,07% vs
  mercado 49,83%; media 3 dobles 8,48/15.

---

## 2. CALIBRACIÓN GLOBAL: EL MERCADO YA ESTÁ BIEN CALIBRADO

Fiabilidad por clase (probabilidad implícita de cierre vs frecuencia real):

| Era | Δ LOCAL | Δ EMPATE | Δ VISITA |
|---|---|---|---|
| 2010-16 (n=6.733) | +1,5pp | −0,6pp | −0,8pp |
| 2016-20 (n=1.231) | −1,0pp | +2,7pp | −1,7pp |
| 2020-26 (n=5.484) | +1,3pp | −0,3pp | −1,0pp |

Test de deltas por clase (entrena 2010-19, valida/testea después):

| Split | Brier mercado | Brier calibrado | Acc mercado | Acc calibrado |
|---|---|---|---|---|
| valid 2019-22 | 0,6115 | 0,6115 | 48,54% | 48,43% |
| test 2022-26 | 0,5965 | 0,5963 | 50,96% | 50,94% |

**Conclusión:** los shifts globales de clase no aportan nada. La vía de mejora
NO es recalibrar el mercado en bloque. (Esto explica el resultado nórdico.)

---

## 3. CALIBRACIÓN POR BANDAS: LA DESCALIBRACIÓN REAL

El mercado sobrevalora al visitante de gama media-alta y subvalora al local
favorito moderado, pero **la intensidad depende del régimen**:

| Banda | Factor real/implícito TRAIN (<2019) | Factor TEST (≥2019) |
|---|---|---|
| Visitante cuota 2.5–4.0 | 0,965 (n=3.000) | **0,908** (n=2.534) |
| Local cuota 1.4–1.8 | 1,015 (n=1.285) | **1,068** (n=1.124) |

Validación walk-forward del `calibrador_bandas.py` (ventana 6 temporadas,
CAP ±10%, boost entre-semana +2%), 13 temporadas test:

- **Brier mejorado en 9/13 temporadas**; en 2020-26 mejora en **6 de 7**
  (media era reciente: 0,6026 → 0,6020).
- **Acc simple neutra** (±0,2pp por temporada): esperado — la corrección de
  banda rara vez cambia el argmax. Su valor está en las probabilidades que
  consume el `OPTIMIZADOR_COLUMNAS` (selección por segunda probabilidad).
- Los factores recientes (0,90 / 1,07) son más fuertes que los históricos:
  coincide con la caída post-2020 de la ventaja de campo (locales: 47,3% en
  2010-16 → 44,8% en 2020-26). → **Imprescindible estimación rodante**; jamás
  factores fijos.

---

## 4. SEÑALES CONTEXTUALES AUDITADAS (pre-registradas)

| Feature | n | ROI 2010-19 | ROI 2019-26 | Veredicto |
|---|---|---|---|---|
| F2 Favorito en jornada entre semana | 1.059 | **+4,5%** | **+4,0%** | ✅ **Consistente** → boost +2pp |
| F4 Local hundido (cociente<1,05) en casa, últimas 8j | 93 | +12,0% | +24,1% | 🟡 Flag manual; muestra pequeña |
| F1 Local con −2 días de descanso | 995 | — | −0,2% | ❌ El mercado ya lo precia |
| F3 Recién ascendido en casa <12j (cuota 1.8-3.5) | 678 | −9,3% | +0,3% | ❌ Sin edge (sus transition_factors ya cubren) |
| F5 Visitante favorito con +2 días descanso | 214 | — | +2,4% | ❌ Débil |
| F6 Steam move (B365 apertura→cierre, Δ≥0,15) | 1.044 | n/d | **−8,2%** | ❌ Contrario: apostar el steam pierde |
| Empate Segunda cuota ≥3,2 | 989 | −11,6% | −1,0% | ❌ Evitar (coherente con draw_boost=0) |

Nota F4: la definición exacta (validada en ambos splits) es: local con
puntos/partido < 1,05, visitante entre 1,25 y 1,65, ambos con ≥ tot−8 jornadas
jugadas, cuota local ≤ 3,0. Candidata a `manual_context_flags` con aviso de
muestra pequeña.

---

## 5. ESPECIFICACIÓN DE INTEGRACIÓN

### 5.1 Punto de inserción
Después de la probabilidad de mercado (o del ensemble) y ANTES de
`MOTOR_DECISION_QUINIELISTICA` / `OPTIMIZADOR_COLUMNAS`:

```python
from calibrador_bandas import estimar_factores, calibrar_probabilidades
factores = estimar_factores(historico, hasta_temporada=temp_actual, ventana=6)
probs_ajustadas = calibrar_probabilidades(probs_ensemble, cuotas_cierre,
                                          factores, entre_semana=es_entre_semana)
```

### 5.2 Parámetros (congelables en CONFIG)
```json
"calibracion_bandas": {
  "enabled": true,
  "ventana_temporadas": 6,
  "cap_multiplicativo": 0.10,
  "banda_visita": [2.5, 4.0],
  "banda_local": [1.4, 1.8],
  "boost_favorito_entre_semana": 0.02,
  "nota": "REVISION_15: factores re-estimados cada temporada solo con datos previos; CAP limita el riesgo de sobreajuste de régimen."
}
```

### 5.3 Protocolo de aceptación (reglas del propio repo)
1. Ejecutar `BACKTEST_HISTORICO_TEMPORADAS.py` con/sin calibrador.
2. Acepta solo si mejora Brier/logloss fuera de muestra SIN empeorar acc
   simple ni media de 3 dobles más allá de −0,1pp.
3. Regenerar `reports/production_reference.json` y congelar factores por
   temporada (modo producción nunca re-estima).

---

## 6. LÍMITES Y PRÓXIMO APALANCAMIENTO

- Ganancia realista del calibrador: **décimas de Brier**, acc simple neutra.
- El ROI de la quiniela depende del **pari-mutual**: el siguiente gran paso es
  incorporar el **reparto público** (columnas `apu/lae/q15` ya referenciadas en
  config) para colocar dobles donde la probabilidad calibrada diverja del
  público, no del mercado.
- Paper-trading 2026-27 de la banda visitante 1.8–2.5 (REVISION_14) sigue
  pendiente para confirmar/descartar el edge reciente en datos futuros.

---

## 7. REPRODUCCIÓN

| Script | Qué hace |
|---|---|
| `purplerave/auditoria_mejoras.py` | Fiabilidad global + candidatos contextuales (Parte A/C) |
| `purplerave/auditoria_mejoras_2.py` | Re-validación por eras + calibración por bandas (Parte B+) |
| `purplerave/calibrador_bandas.py` | Módulo drop-in + walk-forward de 13 temporadas |
| `purplerave/replicar_senales.py` | Réplica de señales REVISION_14 en este histórico |

---

## 8. FORMATO MÁQUINA

```json
{
  "meta": {"fecha": "2026-08-24", "partidos": 13448, "temporadas_test": 13},
  "calibracion_global": {"mejora": false, "brier_test_mkt": 0.5965, "brier_test_cal": 0.5963},
  "calibracion_bandas": {
    "factores_train_pre2019": {"visita_2.5_4.0": 0.965, "local_1.4_1.8": 1.015},
    "factores_test_post2019": {"visita_2.5_4.0": 0.908, "local_1.4_1.8": 1.068},
    "walk_forward": {"brier_mejora_en": "9/13 temporadas", "era_2020+": "6/7 mejoran", "acc_simple": "neutra"},
    "config": {"ventana": 6, "cap": 0.10, "boost_entre_semana": 0.02}
  },
  "senales_contextuales": {
    "favorito_entre_semana": {"roi_2010_19": 0.045, "roi_2019_26": 0.040, "n": 1059, "accion": "boost +2pp"},
    "hundido_en_casa_final": {"roi_2010_19": 0.120, "roi_2019_26": 0.241, "n": 93, "accion": "flag manual"},
    "descanso": {"roi": -0.002, "accion": "descartado"},
    "ascendido_casa": {"roi_2019_26": 0.003, "accion": "descartado"},
    "steam_b365": {"roi_2019_26": -0.082, "accion": "descartado (inverso)"}
  },
  "proximos_pasos": ["backtest con/sin calibrador", "integrar reparto publico en optimizador", "paper-trading 2026-27"]
}
```

---

*Auditoría generada con walk-forward estricto. Cifras reproducibles con los
scripts citados. Ninguna mejora está garantizada fuera de muestra.*
