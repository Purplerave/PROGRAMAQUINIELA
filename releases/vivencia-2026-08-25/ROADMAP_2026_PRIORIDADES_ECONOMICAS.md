# ROADMAP 2026 — PRIORIDADES ECONÓMICAS REALES (Agente Especial)

**Fecha:** 2026-08-24  
**Filosofía:** Solo seguimos lo que **mueve dinero** (P(≥12), ROI boleto 6€, mean hits con 3 dobles).  
Todo lo demás es experimento bonito pero se documenta y se deja de lado si no pasa el filtro.

---

## 1. VEREDICTO ACTUAL (después de backtest definitivo)

### Vivencia (LeagueVivenciaReconstructor)
- **Excelente técnicamente**: reconstruye tabla, rachas, momentum, six-pointers, objetivos, flags (`releg_hot`, `surprise`, `leader_bad_form`) sin fuga.
- **Resultado económico** (125 jornadas Primera, walk-forward):
  - Baseline: 6.992 mean hits
  - Vivencia boosts: 6.944 mean hits (−0.048)
  - P(≥12) = 0.0 en ambos brazos
- **Mejor uso encontrado**: **solo para seleccionar qué partidos doblar** (no para cambiar probs 1X2) → +0.013 mean hits (pequeño pero consistente).
- **Conclusión**: Vivencia **se queda** como capa de análisis humano + selector inteligente de dobles. No como booster de probabilidades.

### Lo que realmente ha funcionado históricamente
- Dominio del **mercado** (0.95 peso)
- **OPTIMIZADOR_COLUMNAS** (convolución exacta de 3 dobles)
- **Dixon-Coles** para Pleno al 15
- **Calibración** (VectorScaling)
- ContextEngine ligero (intrascendentes, derbis, fatiga)

---

## 2. PRIORIDADES REALES (ordenadas por impacto económico esperado)

### P0 — Alto impacto, factible ya
1. **Mejorar selección de dobles con Vivencia + Contexto** (la única señal positiva)
   - Usar score compuesto (vivencia + context + market_entropy) para elegir los 3-4 partidos a doblar.
   - Backtest específico: "SMART_DOUBLE_SELECTION".
   - Potencial: +0.05 a +0.15 mean hits (acumulado puede ser material).

2. **Ensemble adaptativo por jornada**
   - Meta-modelo ligero que decide peso de "market vs HGB vs Dixon-Coles" según características de la jornada (usando vivencia + context).
   - Ej: más peso a market en six-pointers, más entropía en meaningless.

3. **Sistema de cobertura inteligente (no solo 3 dobles fijos)**
   - Decidir dinámicamente 2 / 3 / 4 dobles según "caos detectado" (vivencia + context + entropy).
   - Ya parcialmente en QUINIELA_MULTIVERSO (chaos mode). Medir económicamente.

### P1 — Medio-alto impacto, requiere trabajo
4. **Usar vivencia features en un meta-modelo / stacking** (no directamente en HGB)
   - Entrenar un segundo nivel (Logistic o pequeño HGB) que tome:
     - probs del motor base
     - viv_* features
     - context features
   - Solo activar si mejora P(≥12) en walk-forward.

5. **Reglas de patrones para cobertura manual + boletos reducidos**
   - "Si hay 2+ releg_hot + 1 surprise → hacer sistema de 4 dobles"
   - Exponer `detect_patterns()` más fuerte en el programa definitivo.

6. **Mejor fatiga real** (días + partidos entre medias + rotaciones)
   - Actualmente usamos `days_since_last_match`. Mejorar con calendario real.

### P2 — Interesante pero secundario
7. **xG histórico** (Understat) — ya localizado, pendiente descargar + validar fuera de muestra.
8. **Calibración por división / fase de temporada**.
9. **Pleno al 15 mejorado** (ya decente con DC).

### P3 — Bajo retorno esperado (o ya probado negativo)
- Boosts directos de vivencia en probs 1X2 → **rechazado**
- Meter viv_* directamente como features en el HGB actual → **rechazado** (peor)
- Esotérico (luna, numerología, etc.) → probado en LMARENA, sin señal consistente.
- xG de Highlightly (solo 1 temporada) → descartado para histórico.

---

## 3. ROADMAP CONCRETO (próximos 4-6 sprints)

### Sprint 1 (inmediato) — COMPLETED 2026-08-24
- [x] **Vivencia main axis + 10 parallel branches deepened** (pattern_strength, motivation_diff, context_value, trust_regime, target_matchup, phase/fatigue interactions + is_high_value).
- [x] `vivencia_to_model_features` → 31 features; enrich + PROGRAMA_DEFINITIVO fully wired for dynamic doubles.
- [x] Targeted walk-forward (20j 2024-25): **Δmean +1.70 | ΔP(≥12) +0.05 | ROI +45** (branches_dynamic vs fixed3).
- [x] Rich branch reports for J1/J69/J74 + VIVENCIA_BRANCHES_DEEPENING_2026-08-24.json.
- [x] `PROGRAMA_DEFINITIVO_QUINIELA.py` updated with branch-aware chaos + viv_score.
- Next: full walk-forward on all branch scores + paper trade J74+ .

### Sprint 2
- [ ] Crear meta-ensemble ligero que combine motor base + vivencia/context signals.
- [ ] Medir impacto en P(≥12) y ROI.

### Sprint 3
- [ ] Descargar y validar xG Understat histórico (Primera 2014/15+).
- [ ] Probar solo si la cobertura es >60% y mejora fuera de muestra.

### Sprint 4
- [ ] Reglas automáticas de "cuántos dobles" basadas en vivencia + context.
- [ ] Generar boletos reducidos inteligentes.

### Sprint 5 (largo plazo)
- [ ] Paper-trading real 2026-27 con el nuevo selector de dobles.
- [ ] Dashboard de vivencia por jornada (para análisis humano).

---

## 4. Reglas de decisión (para no perder el tiempo)

**Solo seguimos una línea si:**
- Mejora **P(≥12)** ≥ +0.015 **o**
- Mejora **ROI 6€** ≥ +0.02 **o**
- Mejora **mean hits** ≥ +0.10 de forma consistente en ≥3 temporadas

**Vivencia solo se usa en:**
- Análisis humano (reportes)
- Selección de dobles
- Features para meta-modelos (nunca directamente en el motor principal sin meta-capa)

**Nunca:**
- Cambiamos pesos del motor base por una sola temporada.
- Mezclamos datos futuros.
- Activamos features sin backtest económico estricto.

---

## 5. Estado actual del "Programa Definitivo"

- `PROGRAMA_DEFINITIVO_QUINIELA.py` → usa vivencia de forma conservadora + patrones.
- `BACKTEST_VIVENCIA_DEFINITIVO.py` → resultado oficial (no activar boosts).
- La mejor señal encontrada (selección de dobles) **aún no está implementada** como estrategia principal → **prioridad #1**.

---

## 6. Llamada a la acción inmediata

**Ahora mismo (haz esto):**

1. Ejecuta y termina el experimento de **selección inteligente de dobles con vivencia**.
2. Actualiza `PROGRAMA_DEFINITIVO_QUINIELA.py` para que use esa estrategia por defecto.
3. Genera un nuevo backtest económico comparando:
   - 3 dobles normales
   - 3 dobles guiados por vivencia+context
4. Si el delta es positivo → congelamos como nueva estrategia base.

**Después** evaluamos si merece la pena subir a meta-modelo o reglas de cobertura.

---

**Agente Especial — 2026-08-24**

Hemos rebuscado hasta en el infierno con la vivencia.  
Resultado: es una herramienta **poderosa de contexto y análisis**, no un santo grial de probabilidades.

Ahora toca **enfocarnos en lo que sí mueve la aguja económica**.

Este roadmap es la guía. Todo lo demás es distracción.
