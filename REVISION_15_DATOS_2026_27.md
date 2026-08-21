# REVISION 15: datos al 100 % para la jornada 2 de 2026-27 (21/08/2026)

Viernes 21/08/2026. Objetivo: dejar el programa con todos los datos
disponibles y generar la mejor quiniela para la jornada 2 de la temporada
2026-27 (cierre: sábado 22/08 a las 17:00; bote: 1.100.000 EUR).

## 1. Contexto de la temporada

La jornada 1 de La Liga 2026-27 se repartió entre el 15 y el 27 de agosto
(descanso post-Mundial). A fecha 21/08/2026:

- Jugados hasta el 17/08: 5 partidos de Primera y los 11 de Segunda (feed de
  Football-Data actualizado a 17/08/2026).
- Jugados entre semana: At. Madrid 2-0 Málaga (19/08) y Rayo Vallecano 1-1
  Alavés (20/08), aún no publicados por Football-Data.
- Aplazados: Barcelona-Athletic (27/08), Celta-Osasuna (27/08, su signo en la
  quiniela J1 se sorteó y salió X), Real Madrid-R. Sociedad (26/08) y
  Valencia-Betis (25/08).

## 2. Datos añadidos (procedencia)

| Dato | Fuente | Captura |
|---|---|---|
| SP1_2627.csv (5 partidos) | https://www.football-data.co.uk/mmz4281/2627/SP1.csv | 21/08/2026 |
| SP2_2627.csv (11 partidos) | https://www.football-data.co.uk/mmz4281/2627/SP2.csv | 21/08/2026 |
| Ath Madrid 2-0 Malaga (19/08) | quiniela15 (calendario La Liga) + es.wikipedia.org | 21/08/2026 |
| Vallecano 1-1 Alaves (20/08, HT 0-0) | quiniela15 + elpais.com + marca.com + telemadrid.es | 21/08/2026 |
| QUINIELA15_J2.json (composición, Q15/LAE/APU, forma, histórico H2H) | https://www.quiniela15.com/pronostico-quiniela | 21/08/2026 |
| Cuotas 1X2 de los 15 partidos | OddsPortal (medias de mercado, laliga + laliga2) | 21/08/2026 |

El feed 2026-27 de Football-Data cambió el esquema de columnas (HxG/AxG,
nuevo set de casas). `scripts/datos/GENERAR_HISTORICO_2026_27.py` proyecta las
filas sobre el esquema canónico de 131 columnas del repositorio: columnas
comunes copiadas tal cual; columnas que el feed ya no publica (BMGM*, CL*,
LB*, PS*, P>2.5, PAHH, PCAHH...) en blanco; HxG/AxG no se incorporan (el xG
se gestiona aparte). Los dos partidos entre semana se añaden solo con
resultado (sin cuotas ni stats) y con fuentes auditadas en el docstring del
script; el saneado los marca como `ADMINISTRATIVE_CANDIDATE` (criterio A2).

## 3. Cambios de código

- `MOTOR_QUINIELA_MAESTRO.load_raw_history(..., require_odds=True)`:
  parámetro opt-in. Con `False` se conservan las filas sin cuotas (mercado
  NaN). El comportamiento por defecto no cambia: la evaluación de producción
  sigue usando solo filas con cuotas completas.
- `MOTOR_PREDICCION_JORNADA`: la generación de jornada usa el histórico
  completo para el estado point-in-time de equipos (forma/Elo/tabla, con los
  partidos entre semana incluidos) y el histórico con cuotas para entrenar
  los modelos. `predict_jornada_from_model` acepta `history_train` opcional
  (retrocompatible).
- `scripts/motor/team_names.py`: alias nuevos observados en la temporada
  2026-27: "Athletic" -> Ath Bilbao; "At. Madrid" -> Ath Madrid;
  "R. Santander" -> Santander; "Deportivo A Coruna"/"Dep A Coruna" ->
  La Coruna; clave nueva "Celta B" (Celta Fortuna, sin fundir con Celta).
- `PREPARAR_ESTADISTICAS_TEMPORADA_2026_27.py`: los mismos alias para la
  resolución de priors (Athletic, At. Madrid, R. Santander, Deportivo,
  Sevilla, Ceuta, Celta, Celta B).
- `OPTIMIZADOR_COLUMNAS.py`: nuevo `load_probs_override()` que acepta el JSON
  del motor maestro (`{"predicciones": [{numero, prob_1, prob_x, prob_2}]}`)
  además de los formatos anteriores; el ranking de columnas por valor
  respeta el override del modelo. Tests añadidos.
- `tests/test_project_smoke.py` y `tests/test_sanitization.py`: contadores
  actualizados al dataset ampliado (34 CSVs; input_rows 13.493; output_rows
  13.462; ADMINISTRATIVE_CANDIDATE 23 = 21 históricos + 2 nuevos).

## 4. Validación

- `pytest -q`: 268 passed (22/08/2026 sandbox, numpy 2.2.6 / pandas 2.3.3 /
  scipy 1.16.3 / scikit-learn 1.7.2).
- Evaluación de producción (`--modo produccion`, pesos congelados v4):

| Métrica | Valor |
|---|---|
| Partidos limpios | 13.462 |
| Acierto simple (test principal, 2.693 partidos) | 51,62 % (mercado 51,58 %) |
| Media con 3 dobles | 8,63/15 |
| Primera (1.231 test) | 54,91 % (mercado 54,91 %) |
| Segunda (1.462 test) | 48,84 % (mercado 48,77 %) |
| Última temporada (2026-27, 16 partidos) | 56,25 % (mercado 56,25 %), 10,00/15 con 3 dobles |

- Hash del dataset histórico combinado (34 CSVs, PRIMERA+SEGUNDA):
  `26ed3ceaf4899c6138ae5c56efa353bd5b5c25cb07bb769dbf0db3c36a99e3a4`
  (anterior, 32 CSVs hasta 2025-26: `51a9688ac065015da9335512af5a34a8`).

## 5. Quiniela generada (jornada 2)

`SALIDAS/paquete_jornada_J2.json`, `SALIDAS/predicciones_modelo_J2.json`,
`SALIDAS/diagnostico_quinielistico_J2.json` y `salida/opt_boleto_j2.json`.

Boleto óptimo (contrato P0: 3 dobles = 8 columnas a 0,75 EUR = 6,00 EUR;
Pleno al 15 separado):

1. Athletic–Sevilla **1** · 2. Valencia–Celta **1** · 3. Espanyol–R. Madrid **2** ·
4. Getafe–R. Santander **1X** · 5. Elche–Barcelona **2** · 6. Osasuna–Levante **1** ·
7. Málaga–Deportivo **12** · 8. R. Oviedo–Leganés **1** · 9. Ceuta–Las Palmas **2** ·
10. Eldense–Cádiz **1** · 11. Eibar–Valladolid **1** · 12. Castellón–Sabadell **1** ·
13. Sporting–Burgos **12** · 14. Tenerife–Almería **2**.

Pleno al 15 (At. Madrid–Villarreal): **1-1** (Dixon-Coles, lambdas 1,56/1,54;
signo del Pleno: 1). Alternativa del modelo: 2-2.

Aciertos esperados del boleto: 7,96/14. Probabilidades exactas por
convolución: P(≥10) 19,6 %, P(≥11) 7,5 %, P(≥12) 2,0 %, P(≥13) 0,33 %,
P(≥14) 0,03 %.

Nota: como siempre, es una estimación estadística, no una garantía.
