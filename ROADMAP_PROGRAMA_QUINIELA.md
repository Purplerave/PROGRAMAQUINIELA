# Hoja de ruta del Programa Quiniela

Estado consolidado el 29/07/2026. Actualizado el 01/08/2026 (config v4 + calibración vector scaling en producción).
Este documento debe mantenerse breve y actualizarse al cerrar cada tarea.

## Último avance (01/08/2026 — T3 calibración)

- Nuevo módulo `scripts/motor/calibration.py` con `VectorScalingCalibrator` (ECE 0,0326→0,0245, LogLoss 1,0010→1,0001 en walk-forward 5 temporadas).
- `MOTOR_PREDICCION_JORNADA` ahora entrena calibrador con split 84/16 temporal y aplica calibración antes de emitir 1/X/2.
- `PREDECIR_JORNADA.py` genera paquete con probabilidades calibradas (`fuente_probabilidades.calibracion.aplicada=true`).
- Validado: `CALIBRACION_PROBABILIDADES.py --historico original` muestra mejora consistente sin fuga temporal.

## Punto de partida validado

- Histórico completo: 13.446 partidos de Primera y Segunda.
- Temporada 2025-2026 cerrada: 842/842 partidos.
- Histórico original y saneado comparados; el original continúa como fuente
  predeterminada.
- Motor híbrido: regresión logística, HGB, mercado y Poisson.
- Config activa v4 (31/07/2026): mercado dominante (logit 0.0, hgb 0.049,
  market 0.951, poisson 0.0), elegida por walk-forward multi-split.
- Backtest principal: 51,64 % de acierto simple y 8,63/15 con tres dobles
  (favorito de mercado: 51,56 %).
- Backtest 2025-2026: 51,54 % y 8,50/15.
- Backtest 2024-2025: 52,49 % y 8,64/15.
- Log Loss, Brier y ECE disponibles (scripts de backtest nuevos).
- Features point-in-time para partidos futuros implementadas sin resultado y
  sin fuga temporal.
- La refactorización reproduce exactamente las 82 columnas de los 13.446
  partidos históricos.

## Prioridad inmediata

### 1. Conectar la predicción real

Hacer que `PREDECIR_JORNADA.py` use las probabilidades del motor maestro
entrenado mediante `compute_features_for_upcoming`.

Criterios de aceptación:

- Entrada estable con los partidos y cuotas reales disponibles.
- Salida JSON con probabilidades 1/X/2, signo, confianza, dobles y Pleno al 15.
- Ningún dato posterior al inicio del partido.
- Los proxies Q15, LAE y APU no se interpretan como cuotas.
- Pruebas con equipos conocidos, ascendidos, desconocidos y cuotas ausentes.

### 2. Optimización walk-forward multi-split

Sustituir la selección basada en un único bloque de validación por varias
temporadas de validación temporal. Elegir configuraciones por rendimiento
medio y estabilidad, no por un único máximo.

Criterios de aceptación:

- Train siempre anterior a validación.
- Resultados por temporada y promedio.
- Comparación contra configuración activa y favorito de mercado.
- No activar una configuración si la mejora no es consistente.

### 3. Evaluar el Pleno al 15

Medir los marcadores Poisson contra resultados reales: acierto exacto,
presencia en top 3 y calibración de goles local/visitante.

## Experimentos posteriores

Ejecutar por separado y conservar solo si mejoran el walk-forward:

1. Clasificador binario empate/no empate combinado con el ensemble.
2. Señal de divergencia modelo-mercado para decisiones quinielísticas.
3. Nuevas features: xG, bajas, alineaciones y cambio de entrenador, únicamente
   cuando exista una fuente histórica consistente.
4. Registro append-only de experimento, configuración, fecha y métricas.
5. Contrato JSON o API estable para entregar el pronóstico a Liga de Maestros.

## Reglas

- No cambiar el motor activo por una mejora de una sola temporada.
- No mezclar datos futuros ni encuestas públicas con cuotas reales.
- No añadir una feature sin medir cobertura, calidad y efecto fuera de muestra.
- No sobrescribir resultados históricos de experimentos.
- Mantener siempre una comparación reproducible contra mercado y configuración
  vigente.
