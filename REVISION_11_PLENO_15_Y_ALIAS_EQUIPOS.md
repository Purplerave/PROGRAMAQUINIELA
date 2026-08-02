# REVISION_11_PLENO_15_Y_ALIAS_EQUIPOS

Fecha: 02/08/2026. Cierra la prioridad inmediata 1 del roadmap
("Conectar la predicción real").

## Resumen

1. **Pleno al 15 conectado al motor maestro (Dixon-Coles, T4 en producción)**:
   el partido 15 recibe predicción de marcador del modelo en lugar de depender
   únicamente de `marcadores_q15` (scrape).
2. **Resolución controlada de nombres de equipo**: los nombres comunes de las
   jornadas ("Athletic Club", "Málaga CF", "Castellón") se traducen a los
   nombres del histórico ("Ath Bilbao", "Malaga", "Castellon") y a los
   canónicos de los priors 2026/27, mediante mapa explícito con detección de
   colisiones.
3. **Entrada estable de cuotas reales**: si el JSON de jornada trae
   `odd_1/odd_x/odd_2` (+ aperturas), pasan a las features (peso mercado 0,951
   de la config v4). APU/LAE/Q15 nunca se pasan como cuotas.

## Cambios

### `MOTOR_PREDICCION_JORNADA.py`
- Nuevo `predict_pleno15_from_model`: features point-in-time ->
  `dc_score_probs` (rho −0,036 de config, `use_for_pleno`) -> buckets oficiales
  0/1/2/M por lado, top-3 marcadores, selección + alternativa (gap < 0,10),
  confianza y calidad/avisos.
- Lambdas ausentes (equipos sin historial) -> media de liga **solo con partidos
  anteriores al corte**, marcado con `lambdas_fuente: media_liga` y penalización
  de calidad. Un solo equipo conocido no dispara el fallback: su lambda rival
  sale de `safe_pair_mean` (media de sus goles con los encajados por el otro).
- `predict_jornada_from_model` devuelve `pleno15` en todos los caminos
  (éxito y errores), excluye el 15 del flujo 1X2 y pasa las cuotas reales del
  JSON a las features.
- `_apply_transition_priors` busca priors por nombre canónico vía
  `resolve_prior_name` (arregla que "Castellón" no encontraba "CD Castellon").

### `PREDECIR_JORNADA.py`
- Partido 15: `modelo_maestro.tipo = "pleno_15_marcador"` con buckets,
  top marcadores, selección, lambdas y calidad. Si la calidad < 0,2 se conserva
  el detalle bajo `detalle_baja_fiabilidad` (nunca como fuente principal).
- `pleno15` del paquete: `{modelo_maestro, diagnostico_q15, fuente_principal}`.
- `resumen_modelo.pleno15_modelo_disponible`; `enrich_with_priors` con alias.

### `scripts/motor/team_names.py` (nuevo)
- `HISTORY_NAME_ALIASES`: mapa explícito alias -> nombre exacto del histórico
  (76 equipos SP1/SP2 2010-2026). Solo pares conocidos; lo no mapeado pasa
  intacto. Colisión de alias normalizado = error en construcción.
- Filiales separados: "Real Sociedad B" -> "Sociedad B", nunca al primer equipo.
- Alineado con `sanitization/constants.ALIAS_MAP` (Leonesa -> Cultural Leonesa).
- `prior_alias_index` combina claves de `temporada_2026_27_estadisticas_base.json`
  con los `ALIASES` de PREPARAR_ESTADISTICAS_TEMPORADA_2026_27.
- Integrado en `TeamStateTracker.normalize_upcoming_match` (único punto por el
  que entran partidos futuros; las features históricas no cambian).

### Contrato Pleno al 15 (salida)

```json
{
  "numero": 15, "modelo": "dixon_coles", "rho": -0.036,
  "lambdas": {"local": 1.58, "visitante": 1.405},
  "lambdas_fuente": "features_equipo",
  "marcador_predicho": "1-1", "marcador_confianza": 0.1163,
  "top_marcadores": [{"score": "1-1", "prob": 0.1163}],
  "goles_local": {"0": 0.2065, "1": 0.325, "2": 0.2572, "M": 0.2113},
  "goles_visitante": {"0": 0.2449, "1": 0.3452, "2": 0.2422, "M": 0.1676},
  "seleccion": {"local": "1", "visitante": "1",
                "alternativa_local": "2", "alternativa_visitante": null,
                "confianza": 0.1122},
  "calidad_datos": 0.6, "avisos": ["sin_cuotas_mercado"],
  "comparativa_marcadores_q15": []
}
```

## Garantías

- **Sin fuga temporal**: mismo cutoff para 1X2 y pleno; test que compara la
  predicción con histórico truncado vs completo da salida idéntica.
- **APU/LAE/Q15/marcadores_q15 no son entrada**: test que altera
  `marcadores_q15` con valores extremos produce la misma predicción.
- **Sin cuotas**: la predicción sigue normalizada (suma 1), con aviso
  `sin_cuotas_mercado` y `tiene_cuotas: false` (mercado NaN -> 0 en peso y se
  renormaliza; el motor queda dominado por HGB + Poisson en ese caso).
- **Ascendidos**: priors por alias + mezcla lineal 0-3 partidos
  (`Malaga CF`, `Castellón` probados end-to-end).

## Validación ejecutada (02/08/2026)

- Suite completa: **147 tests en verde** (88 + 11 previos; +48 nuevos/ajustados).
- Backtest del motor maestro tras los cambios: **idéntico** al punto de partida
  (51,64 % acierto simple, 8,63/15 con 3 dobles; 2025-26: 51,54 %/8,50;
  2024-25: 52,49 %/8,64). El motor competitivo no se tocó: solo la capa de
  conexión de jornada, alias y pleno.
- End-to-end `PREDECIR_JORNADA.py --jornada 74 --save-predictions`: paquete con
  pleno DC marcado como baja fiabilidad (equipos nórdicos sin historial) y
  fallback a marcadores Q15 explícito.
- Caso feliz sintético (inicio 2026/27): Madrid-Sevilla con cuotas reales
  63,0/22,7/14,3 signo 1; Malaga CF (ascendido) reconocido con Elo 1568,8;
  Ath Bilbao-Real Sociedad vía alias con lambdas 1,58/1,405 y buckets suma 1,0.

## Limitaciones conocidas

- Equipos sin historial (selecciones, ligas nórdicas): lambdas de media de
  liga con calidad <= 0,45 y `disponible: false`; verdadera solución pasa por
  la fuente nórdica (config `nordic_football_data`, hoy desactivada por
  decisión walk-forward) o por cuotas reales de mercado.
- La confianza por entropía del bloque `recomendacion_modelo` es estricta
  (0,63/0,23/0,14 -> triple). Ajustarla requiere validación walk-forward
  (experimentos posteriores, p. ej. dobles por gap calibrado).
