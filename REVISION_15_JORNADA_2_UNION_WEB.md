# Revisión 15 — Jornada 2 (2026/27) y unión con `liga-maestros-web`

Fecha: 2026-08-18. Motivo: primera ejecución del motor sobre una jornada nueva
(J2) después de la J1, y petición de que los dos repos dejen de estar
desconectados.

---

## 1. Qué estaba roto entre los dos repos

`Purplerave/liga-maestros-web` ya scrapea cada jornada a
`data/quiniela15_J{N}_scrape.json`, pero ese fichero **no encaja** con lo que
espera el motor en `DATOS/QUINIELA15_J{N}.json`. Tres huecos concretos:

| Hueco | Detalle | Consecuencia si se ignora |
|---|---|---|
| Cuotas | El scrape trae `lae: null`, `apu: null` y no trae `odd_*` | El ensemble activo pesa **0.951 en mercado**; sin cuotas ese término se anula (`market_*.fillna(0)`) y la predicción se queda solo con HGB, que nunca se validó en solitario |
| División | El scrape no la trae y `MOTOR_PREDICCION_JORNADA` hace `p.get("division", "Primera")` | Los 7 partidos de Segunda de la J2 se etiquetarían como Primera; además el histórico todavía coloca a Málaga/Deportivo en Segunda y a Oviedo en Primera |
| Nombres | quiniela15 usa `Athletic`, `At. Madrid`, `R. Santander` | Esos tres alias no existían en `HISTORY_NAME_ALIASES`, así que los equipos entraban como desconocidos (Elo 1500, sin forma, sin prior) |

El tercer punto ya afectaba a la **J1**: `R. Santander` (partido 3) entró sin
histórico, y `Sevilla`, `Celta`, `Deportivo` y `Ceuta` se quedaron sin prior
2026/27.

## 2. Qué se ha hecho

### 2.1 Importador `scripts/datos/IMPORTAR_JORNADA_WEB.py`

Convierte el scrape de la web al esquema del motor de forma reproducible y
**sin inventar nada**:

- copia local/visitante/fecha/hora/`q15` y los marcadores del Pleno;
- deduce `division` desde `DATOS/temporada_2026_27_equipos.json` (composición
  oficial verificada), no desde la última categoría del histórico;
- valida que los 30 nombres resuelven contra histórico **y** priors, y lista
  los que no;
- cuotas y LAE llegan por un overlay `--mercado` con su propia procedencia; si
  falta, los campos quedan a `null` y el importador **avisa** de que el
  ensemble perderá el componente de mercado.

```powershell
gh api repos/Purplerave/liga-maestros-web/contents/data/quiniela15_J2_scrape.json `
  --jq .content | base64 -d > salida/quiniela15_J2_scrape.json
python scripts/datos/IMPORTAR_JORNADA_WEB.py --jornada 2 `
  --scrape salida/quiniela15_J2_scrape.json `
  --mercado DATOS/mercado_jornada/MERCADO_J2.json
```

Salida: `cuotas 15/15`, `lae 14/14`, `avisos: ninguno`.

### 2.2 Alias de equipo

Añadidos, con su prueba en `tests/test_importar_jornada_web.py`:

| Nombre en quiniela15 | Histórico | Prior 2026/27 |
|---|---|---|
| `Athletic` | `Ath Bilbao` | `Athletic Club` |
| `At. Madrid` | `Ath Madrid` | `Atletico de Madrid` |
| `R. Santander` | `Santander` | `R. Racing Club` |
| `Sevilla` | (ya) | `Sevilla FC` |
| `Celta` | (ya) | `RC Celta` |
| `Deportivo` | (ya) | `RC Deportivo` |
| `Ceuta` | (ya) | `AD Ceuta FC` |

Los 30 equipos de la J2 resuelven ahora al 100 %. Suite completa: 268 → 278
tests, todos en verde.

### 2.3 Datos de mercado (`DATOS/mercado_jornada/MERCADO_J2.json`)

- `odd_1/odd_x/odd_2`: media de casas de BetExplorer (LaLiga y LaLiga2,
  fixtures de la 2ª jornada), snapshot 2026-08-18.
- `lae`: campo «% en lae» de Quinielista / Eduardo Losilla vía Mundo
  Deportivo, snapshot 2026-08-18.
- Pleno al 15: buckets 0/1/2/M de LAE para local y visitante.

**Control cruzado:** la «probabilidad real» que publica Mundo Deportivo
coincide con la normalización `1/cuota` de este snapshot (partido 1:
55/26/19; partido 12: 62/23/15; partido 9: 30/29/41). Las dos fuentes son
independientes, así que el snapshot queda validado.

Las cuotas son de **apertura de semana**, no de cierre. Si se quiere el
número definitivo, hay que refrescar el overlay el sábado antes de las 17:00 y
volver a lanzar el importador.

---

## 3. Resultado de la ejecución (J2)

`python PREDECIR_JORNADA.py --jornada 2` →
`SALIDAS/paquete_jornada_J2.json`, `SALIDAS/api_maestros_J2.json`.
`python MOTOR_DECISION_QUINIELISTICA.py --jornada 2` →
`SALIDAS/diagnostico_quinielistico_J2.json`.

### 3.1 Probabilidades por partido

| # | Partido | Modelo 1/X/2 | Mercado | q15 | LAE | Signo | Riesgo | Etiqueta |
|---|---|---|---|---|---|---|---|---|
| 1 | Athletic – Sevilla | .56/.27/.17 | .56/.26/.18 | .70/.19/.10 | .63/.22/.15 | **1** | bajo | fijo lógico |
| 2 | Valencia – Celta | .44/.29/.27 | .43/.29/.28 | .44/.31/.25 | .46/.30/.24 | **1** | medio | partido abierto |
| 3 | Espanyol – R. Madrid | .13/.20/.67 | .13/.21/.66 | .08/.12/.81 | .19/.17/.64 | **2** | bajo | favorito sobreapostado |
| 4 | Getafe – R. Santander | .44/.32/.24 | .45/.32/.23 | .51/.29/.20 | .50/.28/.22 | **1** | medio | favorito razonable |
| 5 | Elche – Barcelona | .11/.18/.71 | .11/.17/.72 | .08/.08/.84 | .18/.16/.66 | **2** | bajo | favorito sobreapostado |
| 6 | Osasuna – Levante | .54/.26/.20 | .52/.27/.22 | .71/.19/.11 | .60/.24/.16 | **1** | bajo | favorito razonable |
| 7 | Málaga – Deportivo | .345/.304/.351 | .37/.31/.33 | .33/.43/.25 | .42/.33/.25 | **2** | alto | partido abierto |
| 8 | R. Oviedo – Leganés | .52/.28/.20 | .50/.29/.22 | .55/.27/.19 | .50/.29/.21 | **1** | medio | favorito razonable |
| 9 | Ceuta – Las Palmas | .25/.29/.46 | .29/.29/.42 | .20/.25/.55 | .28/.25/.47 | **2** | medio | partido abierto |
| 10 | Eldense – Cádiz | .38/.31/.31 | .40/.30/.30 | .22/.35/.43 | .31/.31/.38 | **1** | alto | triple candidato |
| 11 | Eibar – Valladolid | .41/.32/.28 | .42/.31/.27 | .53/.28/.19 | .48/.30/.22 | **1** | medio | partido abierto |
| 12 | Castellón – Sabadell | .63/.23/.14 | .62/.23/.15 | .74/.15/.11 | .63/.22/.15 | **1** | bajo | favorito razonable |
| 13 | Sporting – Burgos | .392/.301/.307 | .39/.31/.30 | .43/.32/.25 | .51/.29/.20 | **1** | medio | favorito razonable |
| 14 | Tenerife – Almería | .31/.29/.40 | .32/.29/.40 | .31/.30/.39 | .37/.29/.34 | **2** | extremo | triple candidato |

Discrepancias con el público que conviene mirar a ojo:

- **10 Eldense – Cádiz**: el modelo y el mercado dan favorito al Eldense
  (.38/.40), mientras q15 y LAE juegan el 2 (.43/.38). Es el mayor desacuerdo
  de la jornada.
- **7 Málaga – Deportivo**: el modelo se decanta por el 2 por 6 milésimas
  (.351 vs .345) y el mercado por el 1 (.37). A efectos prácticos es un
  triple; el optimizador lo abre como doble `12`.
- **13 Sporting – Burgos**: LAE carga el 1 al 51 % y el modelo lo deja en
  .392, con el 2 casi igualado (.307). Es el partido con más valor negativo
  del boleto (−0,118 frente al público).
- **14 Tenerife – Almería**: modelo y mercado dan el 2 (.40); LAE juega el 1.

### 3.2 Boleto recomendado (contrato P0: 3 dobles = 8 columnas = 6,00 €)

```
 1  Athletic – Sevilla        1
 2  Valencia – Celta          1
 3  Espanyol – R. Madrid      2
 4  Getafe – R. Santander     1X   ← doble
 5  Elche – Barcelona         2
 6  Osasuna – Levante         1
 7  Málaga – Deportivo        12   ← doble
 8  R. Oviedo – Leganés       1
 9  Ceuta – Las Palmas        2
10  Eldense – Cádiz           1
11  Eibar – Valladolid        1X   ← doble
12  Castellón – Sabadell      1
13  Sporting – Burgos         1
14  Tenerife – Almería        2
```

- Aciertos esperados: **7,884 / 14** (J1 fue 7,591).
- P(≥10) = 18,39 % · P(≥11) = 6,88 % · P(≥12) = 1,80 % · P(≥13) = 0,29 % ·
  P(≥14) = 0,022 %.
- Coste: 8 columnas × 0,75 € = **6,00 €**. Pleno al 15 aparte.
- Evaluación exhaustiva de las 364 combinaciones de tres dobles; la segunda
  opción (dobles 4, 7 y 10) queda a 0,0024 aciertos esperados, así que la
  elección de los dobles es prácticamente un empate técnico entre 10 y 11.
- Monte Carlo (20 000 sims): boleto optimizado 7,868 esperados vs 6,887 del
  boleto de favoritos y 6,706 del boleto popular.

### 3.3 Pleno al 15 — At. Madrid – Villarreal (Dixon-Coles)

- λ local 1,42 · λ visitante 1,735 (ρ = −0,036).
- Buckets local: 0 → .241 · **1 → .344** · 2 → .244 · M → .171
- Buckets visitante: 0 → .177 · **1 → .305** · 2 → .266 · M → .252
- Selección: **1 – 1**, alternativa en el visitante: 2 (está a .039).
- Referencia: quiniela15 juega 2-1 (29 %), y LAE carga el 2 del local (45 %).
  El modelo es bastante más plano que el público en el bucket local.

---

## 4. Dos cosas que no cuadran (no tocadas, para decidir)

Ninguna se ha modificado: cambiarlas exige backtest antes/después según
`AGENTS.md`. Se dejan documentadas.

**(a) El motor de jornada reoptimiza los pesos en cada ejecución.**
`CONFIG_MOTOR_V2.json` congela `hgb 0.049 / market 0.951`, y el README dice
que producción «nunca reoptimiza los pesos durante la ejecución». Pero
`MOTOR_PREDICCION_JORNADA._train_models()` llama a `optimize_hybrid_config()`,
y tanto en J1 como en J2 salió **`hgb 0.2 / market 0.8`** más
`x_disagreement_strategy = market_pick_only`. Es decir: la predicción de
jornada no usa la configuración validada del repo. En la J2 esa diferencia es
la que hace que el partido 7 se decante por el 2 (.351) en vez de por el 1 del
mercado (.37). Habría que elegir: o `PREDECIR_JORNADA` lee los pesos
congelados, o el README deja de afirmar lo contrario.

**(b) `recomendacion_modelo.apuesta_recomendada` devuelve `1X2` en los 14
partidos.** Los umbrales de `decision_thresholds` piden `confianza_min = 0.7`,
pero la confianza es un índice de entropía normalizada que en 1X2 realista no
pasa de ~0,3 (el máximo de la J2 es 0,279 en Elche–Barcelona). El umbral es
inalcanzable, así que ese campo siempre dice «triple» y no aporta nada. **La
recomendación buena es `boleto_optimizado`**, que sí respeta el contrato de 3
dobles. Requiere recalibrar el umbral contra el histórico, no tocarlo a ojo.

---

## 5. Reproducir

```powershell
gh api repos/Purplerave/liga-maestros-web/contents/data/quiniela15_J2_scrape.json `
  --jq .content | base64 -d > salida/quiniela15_J2_scrape.json
python scripts/datos/IMPORTAR_JORNADA_WEB.py --jornada 2 `
  --scrape salida/quiniela15_J2_scrape.json `
  --mercado DATOS/mercado_jornada/MERCADO_J2.json
python PREDECIR_JORNADA.py --jornada 2
python MOTOR_DECISION_QUINIELISTICA.py --jornada 2
python -m pytest -q
```

Entorno: Python 3.11, numpy 2.2.6, pandas 2.3.3, scipy 1.16.3,
scikit-learn 1.7.2. Histórico: 13 446 partidos limpios (PRIMERA + SEGUNDA,
2010-11 → 2025-26).

Estas cifras son una referencia reproducible sobre el snapshot de cuotas del
2026-08-18, no una garantía de resultados.
