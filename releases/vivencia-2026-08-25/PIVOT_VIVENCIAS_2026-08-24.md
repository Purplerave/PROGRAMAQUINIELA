# PIVOT — Vivencias branch (2026-08-24)

## Resumen brutalmente honesto

Después de **exhaustive search** (múltiples backtests walk-forward en Primera):

- Backtest principal (125 jornadas): **Δ mean hits = -0.048**
- Smart doubles con vivencia (100 jornadas): **Δ = -0.07**
- Veredictos: **NO ACTIVAR** / **NEUTRAL**

**La capa Vivencia es técnicamente excelente** (reconstruye la liga en el momento exacto con posiciones, rachas, momentum, flags especiales, patrones humanos).

**Pero no genera edge económico medible** cuando se usa de las formas probadas:
- Boosts en probabilidades 1X2 → neutral/negativo
- Features directas en el modelo → empeora
- Selección de dobles con scoring actual → neutral

## Decisión tomada

**Pivotamos.**

- **Vivencia se mantiene** como:
  - Herramienta de análisis humano (reportes de jornada muy ricos)
  - Capa de contexto visible en el programa definitivo
  - Fuente de ideas y patrones para humanos
  - Posible input futuro para meta-modelos (cuando tengamos stacking)

- **NO invertimos más esfuerzo** en boosters directos de vivencia por ahora.

## Qué sí ha demostrado valor histórico (y dónde seguimos)

1. Dominio del **mercado** + HGB ligero
2. **OPTIMIZADOR_COLUMNAS** con convolución exacta
3. **Dixon-Coles** para Pleno al 15
4. **Calibración** (VectorScaling)
5. **ContextEngine** ligero (intrascendentes, derbis, fatiga)
6. **Selección inteligente de dobles** (la parte que más mueve el ROI)

## Nuevo enfoque inmediato (P0)

Prioridades reales para mover **P(≥12)** y **ROI del boleto de 6€**:

- Dynamic number of doubles (2/3/4) basado en señales de caos (context + vivencia flags + entropy)
- Meta-ensemble ligero por jornada
- Mejor fatiga real (calendario + proxies de rotaciones)
- Reglas de cobertura basadas en patrones humanos

## Archivos de referencia

- `ROADMAP_2026_PRIORIDADES_ECONOMICAS.md`
- `BACKTEST_VIVENCIA_DEFINITIVO.json`
- `EXPERIMENTO_SMART_DOUBLES_VIVENCIA.json`
- `EXHAUSTIVE_VIVENCIA_SEARCH.md`
- `PROGRAMA_DEFINITIVO_QUINIELA.py` (usa vivencia de forma conservadora)

**Agente Especial**  
Hemos rebuscado hasta el final con esta rama.  
Ahora tocamos lo que históricamente sí mueve el dinero.
