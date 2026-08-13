# Revisión del motor y datos de pretemporada — Jornada 1 de LaLiga 2026/27

> Fecha: 13/08/2026 · Fuente de la jornada: `DATOS/QUINIELA15_J1.json`
> Alcance: cómo funciona el programa, qué emite para la J1, y por qué una IA local
> puede dar resultados distintos. Se añaden datos de pretemporada y temporada
> 2025/26 de los 28 equipos que aparecen en el boleto.

---

## 1. Cómo funciona el programa (revisión de código)

### 1.1. El flujo que produce el boleto de una jornada

```
PREDECIR_JORNADA.py  --jornada 1
   ├─ MOTOR_DECISION_QUINIELISTICA.py   → diagnóstico por partido (usa APU/LAE/Q15)
   ├─ MOTOR_PREDICCION_JORNADA.py       → predicción real del modelo maestro
   │     ├─ MOTOR_QUINIELA_MAESTRO.py   → entrena Logit + HistGradientBoosting
   │     ├─ scripts/motor/features.py   → features point-in-time (Elo, forma, tabla, tiros)
   │     └─ scripts/motor/dixon_coles.py→ Pleno al 15 (buckets 0/1/2/M)
   ├─ PRIORS de equipos  → temporada_2026_27_estadisticas_base.json
   └─ OPTIMIZADOR_COLUMNAS.py           → 3 dobles, 8 columnas, coste máx. 6,00 €
```

### 1.2. De dónde salen las probabilidades finales

El ensemble maestro está definido en `CONFIG_MOTOR_V2.json` (`master_model.weights`):

```
prob_final = 0.951 × mercado + 0.049 × HGB + 0.0 × logit + 0.0 × poisson
```

Conclusión clave: **la predicción de la jornada es ~95 % cuotas de mercado** y solo
~5 % del modelo estadístico. Para la J1, el “mercado” son las cuotas decimales
`odd_1/odd_x/odd_2` que vienen ya dentro de `QUINIELA15_J1.json` (fuente
`manus_ai_cuotas`, bookies Bet365/Codere/William Hill/1xBet/PokerStars/Pinnacle/Luckia).

- El diagnóstico (`MOTOR_DECISION_QUINIELISTICA`) usa APU/LAE/Q15 **como proxy de
  mercado**, no como el modelo. En `QUINIELA15_J1.json` no hay APU, así que el
  diagnóstico usa `lae` como “modelo” y `q15` como “público”.
- El **modelo estadístico** (HGB) se entrena sobre el histórico de Primera y
  Segunda (2010-11 → 2025/26). Sus features son rodantes point-in-time: Elo,
  forma (5 últimos), goles, tabla, tiros, descanso, cuotas.

### 1.3. Qué pasa específicamente en la J1 (inicio de temporada)

Como es la primera jornada, **ningún equipo tiene partidos de la temporada actual**
(`home_table_pj` = 0). El código entonces:

1. Usa las features de **la temporada anterior** (Elo y forma de 2025/26).
2. Aplica **priors de transición** (`_apply_transition_priors`): para equipos con
   `< 3 partidos mezcla linealmente el PPG ajustado del fichero
   `temporada_2026_27_estadisticas_base.json` (PPG de 2025/26 × factor de transición).
3. Como el peso del modelo es 0.049, todo ese “conocimiento” histórico queda
   diluido por el peso del mercado.

**Esto confirma tu intuición:** para la J1, el programa descansa casi por completo
en las cuotas de las casas y casi nada en lo que ha pasado en la pretemporada
(amistosos, fichajes, bajas, cambio de entrenador). Esa información **no existe en
ningún canal del programa**. Por eso, si tu IA local razona con noticias de
pretemporada, sus resultados **tienen que** diferir de los del motor.

### 1.4. Pleno al 15

El partido 15 (Deportivo–Elche) se resuelve con Dixon-Coles a partir de las lambdas
de goles esperados de cada equipo (no usa `marcadores_q15` como entrada; solo como
referencia). Buckets oficiales: `0`, `1`, `2`, `M` (3+ goles).

---

## 2. Lo que emite el programa para la J1 (ejecución real, 13/08/2026)

Ejecutado con `python PREDECIR_JORNADA.py --jornada 1 --save-predictions`
(`MOTOR_QUINIELA_MAESTRO`, config `motor_quinielistico_v4`).

| Nº | Partido | 1 | X | 2 | Signo | Boleto (3 dobles) |
|----|---------|---|---|---|-------|-------------------|
| 1 | Alavés – Getafe | .43 | .31 | .26 | 1 | **1X** |
| 2 | Sevilla – Rayo | .42 | .30 | .28 | 1 | **1X** |
| 3 | Racing – Villarreal | .29 | .28 | .43 | 2 | 2 |
| 4 | Espanyol – Levante | .50 | .28 | .22 | 1 | 1 |
| 5 | Celta – Osasuna | .47 | .29 | .24 | 1 | 1 |
| 6 | Andorra – Ceuta | .50 | .28 | .22 | 1 | 1 |
| 7 | Cádiz – Celta Fortuna | .51 | .27 | .21 | 1 | 1 |
| 8 | Oviedo – Granada | .38 | .31 | .31 | 1 | **12** |
| 9 | Mallorca – Valladolid | .48 | .30 | .22 | 1 | 1 |
| 10 | Eibar – Tenerife | .46 | .29 | .25 | 1 | 1 |
| 11 | Burgos – Córdoba | .43 | .28 | .28 | 1 | 1 |
| 12 | Girona – Leganés | .58 | .26 | .16 | 1 | 1 |
| 13 | Las Palmas – Albacete | .55 | .26 | .19 | 1 | 1 |
| 14 | Sporting – Sabadell | .52 | .27 | .21 | 1 | 1 |
| 15 | Deportivo – Elche (Pleno) | — | — | — | — | 1-0 (buckets 1/0) |

- **3 dobles:** 1X (partido 1), 1X (partido 2), 12 (partido 8) → **8 columnas, 6,00 €**.
- El resto, a signo simple con el favorito de mercado (todos menos el 3 van al "1").
- Confianzas del modelo muy bajas (0.004–0.124), típicas de arranque de temporada.
  El umbral `confianza_min=0.7` nunca se alcanza, por eso `recomendacion_modelo`
  devuelve "triple" (1X2) en todos — el boleto final lo decide el optimizador.

---

## 3. Temporada 2025/26 (contexto del prior)

Clasificación final de LaLiga 2025/26 (la que alimenta los priors del programa):

| # | Equipo | Pts | | # | Equipo | Pts |
|---|--------|-----|-|---|--------|-----|
| 1 | Barcelona (campeón) | 94 | | 11 | Espanyol | 46 |
| 2 | Real Madrid | 86 | | 12 | Athletic | 45 |
| 3 | Villarreal | 72 | | 13 | Sevilla | 43 |
| 4 | Atlético | 69 | | 14 | Alavés | 43 |
| 5 | Betis | 60 | | 15 | Elche | 43 |
| 6 | Celta | 54 | | 16 | Levante | 42 |
| 7 | Getafe | 51 | | 17 | Osasuna | 42 |
| 8 | Rayo | 50 | | 18 | **Mallorca (desc.)** | 42 |
| 9 | Valencia | 49 | | 19 | **Girona (desc.)** | 41 |
| 10 | Real Sociedad | 46 | | 20 | **Oviedo (desc.)** | 29 |

**Ascendidos a Primera 2026/27:** Racing de Santander, Deportivo, Málaga.
Los priors del programa son coherentes con esta tabla (p. ej. Barça 2.47 ppg,
Villarreal 1.89 ppg), pero como dijiste, para la J1 **el PPG de la temporada
anterior dice poco** de lo que va a pasar en el debut.

---

## 4. Datos de pretemporada por partido (contraste con el boleto)

> Resumen de la información recopilada en agosto de 2026. Cada equipo se ha
> contrastado con su mercado de fichajes, pretemporada y bajas de cara a la J1.

### Primera

**1. Alavés – Getafe — boleto: 1X**
- **Alavés** (refuerzos: Lucas Boyé Granada, Carles Aleñá *desde el Getafe*, Denis
  Suárez, Ángel Pérez, Jon Pacheco cesión, Mariano Díaz). Riesgo: **Boyé sigue sin
  entrenar con el grupo y apunta a baja** para la J1. Nuevo técnico (Quique).
- **Getafe** (refuerzos: Orel Mangala, Andrés García; cerca Enes Ünal y Johan
  Mojica). **Baja grave: Uche (rotura de rodilla, toda la temporada)**. Satriano
  pasa a ser el referente ofensivo. Bordalás mantiene la base (David Soria).
- Lectura: partido abierto, público Q15 lo ve muy igualado (X 40 %). El doble 1X
  es prudente y encaja con las dudas en ambos equipos.

**2. Sevilla – Rayo — boleto: 1X**
- **Sevilla** (refuerzos: Guridi, Sangante, Juan Iglesias, Julio Díaz, Robbie Ure —
  éste último aún sin poder ser inscrito por trámites). Bajas por lesión: Alfon,
  Marcao. García Plaza, técnico estable. Prep. tranquila, sin sobresaltos.
- **Rayo** (nuevo técnico Beñat San José, **solo 1 fichaje**: Kumbulla cesión).
  **Pretemporada mala: 4 partidos, 3 derrotas y 9 goles encajados.** Sin laterales
  izquierdos (salida de Espino y Pep Chavarría al Chelsea; Nobel Mendy fuera).
  Nota positiva: Isi Palazón podrá jugar (suspensión cautelarmente anulada).
- Lectura: **los datos de pretemporada refuerzan claramente la victoria local del
  Sevilla**. El doble 1X "gasta" un doble donde el mercado y la forma apuntan a
  single 1. Es el candidato más claro a quitar el doble.

**3. Racing – Villarreal — boleto: 2**
- **Racing** (ascendido, técnico José Alberto López). Refuerzos: Agirrezabala
  (p. Athletic), Sergio Canales (libre desde Monterrey), Facu González (Juventus),
  Villalibre. Equipo aún "en construcción" y falto de efectivos en pretemporada.
- **Villarreal** (nuevo técnico Íñigo Pérez). Plantilla potente y prácticamente
  completa: Mikautadze, Ayoze, Pépé, Renato Veiga, Foyth, Luiz Júnior. Sin bajas.
- Lectura: el "2" es razonable por calidad y plantilla. Único matiz: estreno como
  local del ascendido en El Sardinero con Canales, puede apretar el resultado.

**4. Espanyol – Levante — boleto: 1**
- **Espanyol** (Manolo González). **Dos bajas ofensivas graves: Javi Puado
  (ligamento cruzado, hasta nov-dic) y Kike García (bíceps, hasta diciembre).**
  Refuerzos: Hartman, Moscardo, Calatrava.
- **Levante** (Luis Castro). Bajas: Brugué (sanción), Tunde, Elegazabal. Fichajes:
  Thiago Fernández (cesión), Yanis Musuayi (9).
- Lectura: el "1" es coherente con las cuotas, **pero ojo**: con Puado y Kike
  García fuera, el Espanyol pierde gran parte de su gol; el empate tiene más peso
  del que sugiere el single 1.

**5. Celta – Osasuna — boleto: 1**
- **Celta** (Claudio Giráldez). Refuerzos: Carles Pérez, Javi Galán (desde Osasuna),
  Damián Rodríguez, Febas, Faye, Altay Bayindir. Bajas: Mingueza (Crystal Palace),
  Fer López (Wolves). Dudas: Javi Galán (recto femoral), Vecino; Pablo Durán fuera.
- **Osasuna** (nuevo técnico Luis Miguel Ramis). **Vendió a su estrella Víctor
  Muñoz al Liverpool (40 M€)** y perdió a Becker (Mainz), Javi Galán (Celta) y Juan
  Cruz (Oviedo). Balance neto +36,5 M€ y casi sin gasto. Solo fichaje: Dubasin.
  Baja: Rosier (duda).
- Lectura: **Osasuna llega visiblemente debilitado y en transición.** El "1" del
  Celta es de los más sólidos del boleto pese a las dudas locales.

**15. Deportivo – Elche (Pleno) — boleto: 1-0**
- **Deportivo** (ascendido, Hidalgo). **Fichaje bomba: Aubameyang.** También
  Angeliño (vuelve a casa), Nsongo, Luismi Cruz, Mella, Mario Soriano. Bajas en la
  previa: Noé Carrillo se lesionó; Yeremay/Altimira en duda (Altimira ya entrena).
- **Elche** (Martín Anselmi). Arrancó sin incorporaciones (solo ejecutó compras de
  Villar, Sangaré y Chust). **Puede vender a Affengruber y a Álvaro Rodríguez.**
  Bajas: Lucas Cepeda (no disponible), Yago Santiago (lesión), Diangana (duda).
- Lectura: Deportivo más reforzado y en casa; Elche con salidas y bajas. El pleno
  a favor de Deportivo (buckets local 1) es razonable; con Aubameyang quizá más
  gol local que 1-0.

### Segunda (LaLiga Hypermotion)

**6. Andorra – Ceuta — boleto: 1**
- **Andorra** (varios refuerzos: Pau López, Jordi Cano, Nacho Quintana, Arón
  Rodrigo, Andoni López, Moro Sidibe, Randy Schneider).
- **Ceuta** (Ale Meléndez, Cedric Teguía, Jordi Escobar, Omar Sadik, Kenneth Mamah).
- Lectura: ambos con mucho movimiento; Andorra parte favorito en casa (cuota 2.00).
  Single 1 coherente, no es de los más seguros.

**7. Cádiz – Celta Fortuna — boleto: 1**
- **Cádiz** (varias incorporaciones: Ezkieta, Javi Castro, Urko Izeta, Beñat de
  Jesús, José Andújar, Ibón Sánchez, Yussi Diarra).
- **Celta Fortuna** (filial del Celta; fichaje: Bernard Somuah). Históricamente un
  rival flojo y de plantilla corta.
- Lectura: Cádiz claramente superior en categoría/plantilla. Single 1 razonable.

**8. Oviedo – Granada — boleto: 12 (el doble más discutible)**
- **Oviedo** (técnico Julián Calero, **12 fichajes**: Jacobo González, Youness,
  Pablo Sáenz, Chris Ramos, Juan Cruz, Carlos Fernández, Aldasoro, Aisar Ahmed…).
  Bajas/dudas en la previa: Nacho Vidal, Aisar, Dani Calvo y Carlos Fernández;
  Hassan traspasado al Celtic. Mucho cambio y equipo sin afinar en pretemporada.
- **Granada** (apenas 1 alta; **perdió a Lucas Boyé y Abde Rebbach (Alavés), Carlos
  Neva y Sergio Ruiz**). Merma importante de talento.
- Lectura: partido muy igualado según el propio modelo (1 .38 / X .31 / 2 .31).
  **El doble 12 (excluyendo la X) es agresivo** en un choque tan abierto y con tanta
  rotación en ambos bandos; la X tiene casi tanta probabilidad como el 2.

**9. Mallorca – Valladolid — boleto: 1**
- **Mallorca** (descendido, con buen bloque de Primera). Favorito claro en casa.
- **Valladolid** (refuerzos: Michelin, Trilli). Ascendido/rearmado.
- Lectura: single 1 coherente; Mallorca con más calidad.

**10. Eibar – Tenerife — boleto: 1**
- **Eibar** (Jokin Aranbarri; refuerzos de Las Palmas: Iván Gil y Pejiño; Lucas
  Núñez). Bajas: Corpas y Puertas (Albacete).
- **Tenerife** (Álvaro Cervera; varias altas, sale Yaakobishvili al Girona).
- Lectura: Eibar favorito moderado en casa; single 1 aceptable.

**11. Burgos – Córdoba — boleto: 1**
- **Burgos** (Sergio Francisco; refuerzos: Oier Luengo, Javi Llabrés, Alberto
  Dadie, José Gragera cesión). Bajas: Atienza (Leganés), Morante (Girona).
- **Córdoba** (Carlos Isaac; sale Jacobo a Oviedo).
- Lectura: partido muy abierto (1 .43 / X .28 / 2 .28); single 1 algo aventurado.

**12. Girona – Leganés — boleto: 1**
- **Girona** (descendido, técnico Quique Álvarez). **Grandísima renovación**: salen
  Krejčí (Wolves), Lemar, Echeverri, Blind, Witsel…; entran Yaakobishvili, Min-su
  Kim, Morante, Asprilla. Posibles salidas de Arnau y Álex Moreno antes del debut.
  Stuani sigue.
- **Leganés** (Rubén Albés; varias altas: Atienza, Javi Hernández, Buurmeester,
  Kechta, Tejero, Gharbi, Soko). Baja: Franquesa.
- Lectura: Girona favorito por cuotas (cuota 1.65), pero **con tantísimo cambio es
  de los partidos con más incertidumbre real** de la jornada; el "1" no es tan
  firme como parece a simple vista.

**13. Las Palmas – Albacete — boleto: 1**
- **Las Palmas** (Rubén de la Barrera; altas: Cedeño, Bassinga, Miyashiro, Sergio
  Ruiz, Betancor; bajas: Iker Bravo, Barcia, Pedrola, Mármol, Pejiño, Viera).
- **Albacete** (Alberto González; altas: Corpas, Soberón, Ortuño, Carlos Marín,
  Jesús Vallejo, Antonio Puertas).
- Lectura: Las Palmas fuerte en casa (cuota 1.62); single 1 de los más seguros.

**14. Sporting – Sabadell — boleto: 1**
- **Sporting** (nuevo técnico Nicolás Larcamón; **reconstrucción**: salen Vázquez,
  Oliván, Curbelo, Dubasin, Smith…; entran Sáenz, Arana, Sarco, Guillamón…).
- **Sabadell** (ascendido desde Primera RFEF; refuerzos: Pere Pons, Miki Codina,
  Óscar Sanz, Català…).
- Lectura: Sporting claramente favorito (cuota 1.84) ante un recién ascendido;
  single 1 razonable pese a la reconstrucción.

---

## 5. Conclusiones y recomendaciones

### 5.1. Por qué la IA local da "resultados distintos"
El motor para la J1 es, en la práctica, **un espejo de las cuotas de las casas
(95 %) con un 5 % de modelo basado en la temporada anterior**. No tiene ningún
canal para pretemporada (amistosos, fichajes netos, bajas por lesión, cambios de
entrenador, dinámica de mercado). Cualquier IA que use esa información producirá
probabilidades diferentes — y, en una jornada inaugural, posiblemente más
informadas en partidos donde la pretemporada se desvía del mercado.

### 5.2. Dónde la pretemporada sugiere matizar el boleto del programa
- **Sevilla–Rayo (nº2):** la mala pretemporada y la crisis defensiva del Rayo
  hacen que el single **1** sea más sólido que el doble 1X. Candidato a recuperar
  un doble.
- **Osasuna (nº5):** venta de la estrella y pocos fichajes → refuerza el **1** del
  Celta.
- **Espanyol (nº4):** sin Puado y Kike García, el gol local mengua → la **X** gana
  peso; el single 1 es asumible pero menos firme.
- **Oviedo–Granada (nº8):** doble **12** agresivo en un partido muy abierto; la X
  tiene probabilidad similar al 2. Es el doble más discutible del boleto.
- **Girona–Leganés (nº12):** máxima rotación de plantilla → el "1" tiene más
  incertidumbre de la que refleja la cuota.

### 5.3. Recomendaciones para que el programa use pretemporada
1. **Feature de "gol neto de mercado/amistosos"** (altas−bajas ponderadas por valor,
   o resultado agregado de amistosos de verano) por equipo, point-in-time.
2. **Feature de "continuidad de plantilla / entrenador"** (nº de refuerzos, cambio
   de técnico sí/no, minutos de los que se van vs. llegan) — clave en J1.
3. **Bajas por lesión ponderadas** (minutos del 2025/26 de los lesionados).
4. Introducir todo esto **solo tras validarlo con walk-forward** (regla del
   `AGENTS.md`: nunca declarar mejora sin validación fuera de muestra), y **no
   mezclarlo con la temporada anterior** como se hace hoy.
5. Para la J1 concreta, revisar a mano las cuotas del fichero frente a las señales
   de pretemporada, porque el motor no lo hará por sí solo.

---

## 6. Fuentes principales
- LaLiga — calendario y confirmación de la J1 2026/27 (laliga.com; elmundo.es; marca.com; libertaddigital.com).
- Clasificación final LaLiga 2025/26 (Wikipedia; resultadosfutbol24.es; livefutbol.com).
- Mercado de fichajes LaLiga y LaLiga Hypermotion 2026/27 (AS.com; Transfermarkt; fichajes.com).
- Previas y onces de la J1 (Marca, jornadaperfecta.com, futbolfantasy.com, AS.com).
- Pretemporada por equipo: Mundo Deportivo, COPE, AS, Marca, El Desmarque, racinguismo.com, la voz de Asturias, jornadaperfecta.com.
- Ejecución del programa: `PREDECIR_JORNADA.py --jornada 1` → `SALIDAS/paquete_jornada_J1.json`.
