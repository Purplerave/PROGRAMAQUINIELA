# Vivencia Complete Bundle — 2026-08-25

**LeagueVivenciaReconstructor + Parallel Branches**

Todo lo generado para la reconstrucción de la "vivencia" de la liga + ramas paralelas.

## Contenido

- `vivencia.py` — Core (LeagueVivenciaReconstructor + 31 features + todas las ramas)
- `PROGRAMA_DEFINITIVO_QUINIELA.py` — Programa principal actualizado con selección de dobles por vivencia
- `QUINIELA_MULTIVERSO.py` — Multiverso pipeline
- `generar_vivencia_jornada.py` — Generador de reportes
- `context_engine.py` — Integración con contexto
- Backtests clave:
  - `BACKTEST_VIVENCIA_DEFINITIVO.py`
  - `EXPERIMENTO_DYNAMIC_DOUBLES.py`
  - `EXPERIMENTO_SMART_DOUBLES_VIVENCIA.py`
- Documentación:
  - `MANIFIESTO_VIVENCIA.md`
  - `ROADMAP_2026_PRIORIDADES_ECONOMICAS.md`
  - `PIVOT_VIVENCIAS_2026-08-24.md`
  - `EXHAUSTIVE_VIVENCIA_SEARCH.md`

## Cómo usar

```bash
# Instalar dependencias
pip install numpy pandas scikit-learn

# Generar vivencia de una jornada
python generar_vivencia_jornada.py --jornada 74 --output both

# Ejecutar programa definitivo
python PROGRAMA_DEFINITIVO_QUINIELA.py --jornada 1 --modo vivencia
```

## Estado actual (2026-08-25)

- 31 features en `vivencia_to_model_features`
- 10+ ramas paralelas activas (pattern_strength, context_value, trust_regime, etc.)
- Selección dinámica de dobles usando vivencia → +1.7 mean hits en test

Creado por Arena Agent.
