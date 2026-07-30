# REVISION_10_CONEXION_MOTOR_JORNADA

## Resumen

Este documento describe la integración entre **PREDECIR_JORNADA.py** y **MOTOR_QUINIELA_MAESTRO.py** para obtener probabilidades reales del modelo entrenado en lugar de depender exclusivamente de APU/LAE/Q15.

## Arquitectura de la Solución

```
┌─────────────────────┐     ┌──────────────────────────┐     ┌──────────────────────┐
│ DATOS/J{jornada}.json │────▶│ PREDECIR_JORNADA.py      │────▶│ SALIDAS/             │
└─────────────────────┘     │                          │     │ - paquete_jornada_...│
                            │  1. Load jornada data    │     │ - predicciones_modelo│
                            │  2. Generate predictions │     └──────────────────────┘
                            │  3. Add priors           │              │
                            │  4. Build recommendations│              │
                            └──────────┬───────────────┘              │
                                       │                              │
                                       ▼                              │
                            ┌──────────────────────────┐              │
                            │ MOTOR_PREDICCION_JORNADA │◀─────────────┘
                            │                          │   (guardar predicciones)
                            │  - Extract features      │
                            │  - Train/load models    │
                            │  - Generate probs       │
                            └──────────┬───────────────┘
                                       │
                                       ▼
                            ┌──────────────────────────┐
                            │ MOTOR_QUINIELA_MAESTRO   │
                            │                          │
                            │  - Logistic Regression   │
                            │  - HistGradientBoosting  │
                            │  - Market + Poisson     │
                            └──────────────────────────┘
```

## Archivos Modificados/Creados

### Nuevos Archivos

1. **`MOTOR_PREDICCION_JORNADA.py`** (nuevo)
   - Módulo central para predicción de jornadas
   - Conecta con MOTOR_QUINIELA_MAESTRO para obtener probabilidades
   - Genera contrato JSON estable por partido

2. **`tests/test_modelo_jornada.py`** (nuevo)
   - Suite de pruebas de integración
   - 24 tests cubriendo diferentes escenarios

3. **`pytest.ini`** (nuevo)
   - Configuración de pytest con marker `slow`

### Archivos Modificados

1. **`PREDECIR_JORNADA.py`**
   - Integración con MOTOR_PREDICCION_JORNADA
   - Añade campo `modelo_maestro` con predicciones
   - Mantiene APU/LAE/Q15 como información comparativa
   - Genera `recomendacion_modelo` basada en el modelo

## Contrato JSON por Partido

Cada predicción incluye:

```json
{
  "jornada": 74,
  "numero": 1,
  "local": "Equipo Local",
  "visitante": "Equipo Visitante",
  "prob_1": 0.631,
  "prob_x": 0.203,
  "prob_2": 0.166,
  "signo_modelo": "1",
  "confianza": 0.170,
  "fuente_probabilidades": {
    "modelo_primario": "motor_maestro_hibrido",
    "componentes": {
      "logit": 0.25,
      "hgb": 0.25,
      "market": 0.35,
      "poisson": 0.15
    },
    "draw_boost_aplicado": 0.0,
    "segunda_draw_boost_aplicado": 0.0,
    "x_disagreement_strategy": "none"
  },
  "avisos": ["sin_cuotas_mercado"],
  "calidad_datos": 0.7,
  "features_disponibles": {
    "home_elo": 1702.5,
    "away_elo": 1680.3,
    "home_table_pj": 38,
    "away_table_pj": 38,
    "home_form_pts_5": 2.4,
    "away_form_pts_5": 1.8,
    "tiene_cuotas": false
  }
}
```

## Comando para Generar una Jornada

```bash
# Generar paquete completo con predicciones del modelo
python PREDECIR_JORNADA.py --jornada 74

# Generar solo diagnóstico básico (sin modelo)
python PREDECIR_JORNADA.py --jornada 74 --no-model

# Guardar también predicciones del modelo en JSON separado
python PREDECIR_JORNADA.py --jornada 74 --save-predictions
```

## Estructura de Salida

```
SALIDAS/
├── paquete_jornada_J74.json          # Paquete completo
├── diagnostico_quinielistico_J74.json # Diagnóstico (existente)
└── predicciones_modelo_J74.json      # Solo predicciones (con --save-predictions)
```

## Verificación de No Fuga Temporal

El sistema garantiza que:

1. **Features de partidos futuros**: `compute_features_for_upcoming` solo usa datos con `date < cutoff_date`
2. **Sin resultado conocido**: `FTHG`, `FTAG`, `result` son `NaN` para partidos futuros
3. **Cuotas no usadas como odds**: APU/LAE/Q15 no se interpretan como cuotas de mercado
4. **Sin actualización entre partidos**: Los partidos futuros no se actualizan entre sí

## Limitaciones

1. **Equipos fuera del histórico**: Los equipos de ligas no españolas (ej. Noruega, Suecia en J74) no tienen datos y producen predicciones basadas en默认值
2. **Sin cuotas de mercado**: Para partidos sin cuotas, se usa solo Poisson + modelos ML
3. **Entrenamiento local**: Los modelos se entrenan en cada ejecución (no hay persistencia de modelos)

## Pruebas Ejecutadas

### Suite Rápida (13 tests, ~1s)
- Normalización de nombres
- Cálculo de confianza
- Calidad de datos
- Carga de jornadas
- Fecha de corte
- Guardado de predicciones

### Suite Completa (24 tests, marked as `@slow`)
- Predicciones con histórico
- Verificación de contrato JSON
- edge cases
- Integración completa

### Ejecución de Pruebas

```bash
# Solo tests rápidos
pytest tests/test_modelo_jornada.py -v -m "not slow"

# Todos los tests
pytest tests/test_modelo_jornada.py -v

# Solo tests de integración
pytest tests/test_modelo_jornada.py::TestIntegration -v
```

## Ejemplo de Salida

```json
{
  "jornada": 74,
  "estado": "paquete_jornada_v3_modelo",
  "resumen_modelo": {
    "partidos_con_prediccion": 15,
    "partidos_sin_prediccion": 0,
    "partidos_sin_dobles": 3,
    "partidos_con_dobles": 5,
    "partidos_con_triple": 7,
    "confianza_media": 0.08
  }
}
```

## Cambios Respecto a Versión Anterior

| Aspecto | Antes | Ahora |
|---------|-------|-------|
| Fuente principal | APU/LAE/Q15 | Motor maestro híbrido |
| Modelo ML | No usado | Logit + HGB |
| Poisson | No usado | Integrado en predicción |
| APU/LAE/Q15 | Fuente principal | Solo comparativa |
| Recomendaciones | Solo diagnóstico | Diagnóstico + Modelo |

## Notas de Implementación

1. **Reutilización de features**: Se usa `compute_features_for_upcoming` existente y se aplican **priors de transición** para equipos nuevos o al inicio de temporada.
2. **Reutilización de modelos**: Se entrenan con `optimize_hybrid_config` y se re-entrenan con el histórico completo usando la mejor configuración encontrada.
3. **Inferencia Consistente**: Se utiliza `apply_hybrid_config` del motor maestro para asegurar que se aplican todos los boosts (`draw_boost`, `segunda_draw_boost`) y estrategias (`x_disagreement_strategy`).
4. **Respeto de Temporada**: Se infiere la temporada a partir de la fecha de cada partido en lugar de forzar la última del histórico.
