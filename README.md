# Motor Quiniela

Proyecto autonomo para entrenar, evaluar y ejecutar el motor de pronosticos de
La Quiniela. Incluye los historicos de Primera y Segunda desde 2010-11, el
backtest temporal y los datos base preparados para la temporada 2026-27.

## Entrada rápida / Quickstart (Makefile)

Si dispone de `make` (Linux / macOS / WSL / Git Bash):

```bash
make help               # Muestra los comandos principales
make sanitize           # Genera el histórico oficial en salida/ (necesario en una copia nueva)
make test               # Ejecuta la suite de pruebas
make backtest           # Walk-forward sobre histórico saneado; puede incluir la última temporada parcial
make predict JORNADA=74 # Genera el paquete de predicción para la jornada
make audit              # Calidad de datos, pruebas, cobertura y backtest cerrado
make reference          # Regenera salida/referencia_produccion.json (2019-20 a 2025-26)
```

`make audit` reutiliza el saneado existente y crea nueva evidencia de datos en
`salida/auditoria.*/datasets.json`. Si han cambiado los CSV de origen, genera
el saneado en una copia nueva o archiva primero `salida/datos_limpios/`: el
saneador no sobreescribe archivos. La aparición de avisos de cobertura en QA
no equivale a un aprobado del dataset.

La auditoría de arquitectura, los hallazgos y el plan de mejora están en
[Auditoría técnica — fase 1](reports/AUDITORIA_TECNICA_2026-11-18.md).

## Instalacion

### Linux / macOS (bash)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

## Uso

Evaluación de producción (fuente oficial: histórico saneado —ver «Dataset oficial»— y pesos
congelados en `CONFIG_MOTOR_V2.json`):

Bash (Linux / macOS):
```bash
python3 MOTOR_QUINIELA_MAESTRO.py --historico saneado --modo produccion
```

PowerShell (Windows):
```powershell
python MOTOR_QUINIELA_MAESTRO.py --historico saneado --modo produccion
```

Para explorar de nuevo los candidatos de hiperparámetros, use explícitamente
`--modo busqueda`. Ese modo es experimental: no actualiza la configuración ni
es la fuente de la cifra de referencia.

Para seleccionar el histórico saneado (debe existir previamente):

Bash:
```bash
python3 MOTOR_QUINIELA_MAESTRO.py --historico saneado
```

PowerShell:
```powershell
python MOTOR_QUINIELA_MAESTRO.py --historico saneado
```

El archivo saneado se genera explícitamente con:

Bash:
```bash
python3 scripts/datos/SANEAR_DATOS.py --confirm
# O mediante make:
make sanitize
```

PowerShell:
```powershell
python scripts/datos/SANEAR_DATOS.py --confirm
```

Backtest walk-forward por temporadas (requiere el saneamiento previo). Para
reproducir los resultados de siete temporadas cerradas, añade `--to-season
2025-2026`; para un diagnóstico contra el histórico raw, indica `--historico original`:

Bash:
```bash
python3 scripts/backtests/BACKTEST_HISTORICO_TEMPORADAS.py
# O mediante make:
make backtest
```

PowerShell:
```powershell
python scripts\backtests\BACKTEST_HISTORICO_TEMPORADAS.py
```

Preparar las estadisticas base de 2026-27:

Bash:
```bash
python3 PREPARAR_ESTADISTICAS_TEMPORADA_2026_27.py
```

PowerShell:
```powershell
python PREPARAR_ESTADISTICAS_TEMPORADA_2026_27.py
```

Generar el diagnostico y el paquete de una jornada disponible en `DATOS`:

Bash:
```bash
python3 MOTOR_DECISION_QUINIELISTICA.py --jornada 74
python3 PREDECIR_JORNADA.py --jornada 74
# O mediante make:
make predict JORNADA=74
```

PowerShell:
```powershell
python MOTOR_DECISION_QUINIELISTICA.py --jornada 74
python PREDECIR_JORNADA.py --jornada 74
```

`PREDECIR_JORNADA.py` usa la fuente oficial y los pesos publicados. Excluye del
entrenamiento el día del corte y todos los partidos posteriores. Si el boleto
no contiene todas sus fechas, indica el corte conocido con `--corte AAAA-MM-DDTHH:MM:SS`,
o decláralo en `prediction_cutoff_at`; no se usa «ayer» como sustituto. Las
cuotas sin fecha **y hora** de observación verificables quedan fuera del motor; sin mercado
se marca la limitación. Cuando el motor no cubre una competición o equipo, se
etiqueta el proxy disponible, sin inventar probabilidades. Para solo diagnóstico
usa `--no-model`. Con `--save-predictions` se guarda el mismo cálculo que se
incluyó en el paquete, sin reentrenar.

Los resultados generados se escriben en `salida/` y `SALIDAS/` y no se suben
al repositorio.

### Boleto semanal mixto y panel local

Este flujo Poisson de Liga M/Liga F es distinto del motor maestro basado en
mercado. No sirve para reproducir las métricas del backtest del motor maestro.

```bash
python scripts/RUN_SEMANA_COMPLETA.py --boleto ruta/mi_boleto.json --presupuesto 8
python scripts/PANEL_QUINIELA.py --boleto ruta/mi_boleto.json
python scripts/RUN_SEMANA_COMPLETA.py --demo  # J3 histórica, salidas *_demo_J3.json
```

Sin `--boleto`, debe existir `DATOS/BOLETO_SEMANAL.json` (fichero local). El JSON
incluye `jornada` entera, `fuente`, `cierre` ISO 8601, `bote_eur` opcional y
`casillas` con las 15 posiciones únicas. Cada casilla lleva `numero`, `local`,
`visitante` y `liga_f: true` si es de Liga F. Se puede indicar `kickoff_at` por
partido y `prediction_cutoff_at` si el corte es anterior al cierre. La casilla
15 siempre se pronostica como marcador por buckets, no como 1X2.

El panel no escribe en aplicaciones externas. `python scripts/PUBLICAR_WEB.py
--jornada N` (nombre histórico) prepara archivos en
`SALIDAS/entrega_liga_maestros/J<N>/` para revisión y entrega manual. No ejecuta
Git ni un importador ni publica en remoto. La demo y las jornadas cerradas
no se exportan.

## Estructura

- `MOTOR_QUINIELA_MAESTRO.py`: modelos, ensemble y evaluacion principal.
- `MOTOR_DECISION_QUINIELISTICA.py`: seleccion de signos y dobles.
- `MOTOR_PREDICCION_JORNADA.py`: entrenamiento al corte y predicción 1X2/Pleno.
- `PREDECIR_JORNADA.py`: paquete final y exportación local JSON/API v1.1.
- `scripts/RUN_SEMANA_COMPLETA.py`: flujo semanal mixto con boleto explícito.
- `scripts/motor/`: estado punto-en-el-tiempo, alias, calibración y validadores del boleto.
- `PREPARAR_ESTADISTICAS_TEMPORADA_2026_27.py`: actualiza los priors de equipos.
- `CONFIG_MOTOR_V2.json`: parametros activos del motor.
- `DATOS/historico_raw/`: CSV historicos necesarios para reproducir el backtest.
- `scripts/backtests/`: evaluacion walk-forward por temporada.
- `scripts/motor/calibrador_bandas.py`: calibración por bandas (REVISION_15/16).
- `scripts/motor/cobertura_bandas.py`: segundo signo del doble 1X en bandas robustas (REVISION_17). 3 dobles fijos.
- `scripts/datos/PAPER_TRADING_2627.py`: paper-trading Primera 2026-27.
- `scripts/motor/xg_understat.py`: carga y fusion del xG de Understat (Primera
  2014-2024). Añade columnas de xG al historico; aditivo y no afecta al modelo.
- `scripts/backtests/EXPERIMENTO_XG.py`: A/B walk-forward Sin-xG vs Con-xG.
- `REVISION_*.md`: informes tecnicos (validaciones, experimentos y decisiones).

## Reglas de evaluacion

Los datos futuros nunca deben entrar en el entrenamiento de una temporada
anterior. Toda mejora debe compararse con el favorito de mercado y reportar,
como minimo, acierto simple y media de aciertos con tres dobles. No se considera
mejora una subida obtenida solo sobre los mismos datos usados para ajustar.

## Resultado de referencia

Configuración activa: `motor_quinielistico_v4` (logit 0, HGB 0,049, mercado
0,951 y Poisson 0). Auditoría del 18/11/2026 sobre histórico saneado: **5.894
partidos de siete temporadas cerradas (2019-20 a 2025-26)**.

- **50,15 %** de acierto simple frente a **49,83 %** del favorito de mercado.
- **8,42/15** con tres dobles en bloques mecánicos; no son boletos oficiales.
- Diferencial **+0,32 pp**; McNemar pareado **p = 0,1454**; IC95 bootstrap por
  partido **[−0,08; +0,73] pp**. No demuestra una ventaja estable.
- 2024-25: 52,38 % frente a 52,38 %; 8,73/15. 2025-26: 51,54 % frente a
  51,54 %; 8,46/15. El [informe de auditoría](reports/AUDITORIA_TECNICA_2026-11-18.md)
  contiene el desglose completo por Primera, Segunda y temporada.

`reports/production_reference.json` conserva la referencia archivada del
24/08/2026 (50,27 %, otro commit/configuración/entorno), no la medición vigente.
El procedimiento actual permite regenerar una referencia con el SHA-256 del
histórico **efectivamente evaluado**, el código, la configuración y el entorno.

La métrica de tres dobles es un indicador agregado: el histórico se ordena y se
parte en bloques mecánicos de 15 partidos para seleccionar tres dobles. **No
reconstruye los boletos oficiales de La Quiniela ni estima ROI, premios o el
resultado de jornadas reales.**

## Boletos oficiales y ROI

El soporte de backtest real está en `scripts/backtests/QUINIELA_REAL.py`. Solo
acepta jornadas que declaren los 14 partidos oficiales, sus fechas, el Pleno al
15 y su fuente trazable; nunca infiere un boleto desde filas consecutivas. La
CLI valida y resume el corpus; no ejecuta un backtest completo por sí sola.

Bash:
```bash
python3 scripts/backtests/QUINIELA_REAL.py
# O mediante make:
make real-quiniela
```

PowerShell:
```powershell
python scripts/backtests/QUINIELA_REAL.py
```

Los JSON auditados se incorporan en `DATOS/quiniela_historica/` según su
`README.md`. El ROI realizado exige además el escrutinio/premio oficial por
categoría; sin él el módulo devuelve aciertos y coste, pero no inventa retorno.
`evaluation/economics.py` suma los premios **supuestos** de todas las columnas
para el EV teórico y cobra el coste efectivo. `make economics` es un experimento
legado sobre bloques sintéticos y la mejor columna, nunca una estimación de
ROI realizado ni una comparación válida a presupuesto igual.

Las cifras se obtuvieron en modo producción con la configuración incluida en
el repositorio; ese modo nunca reoptimiza los pesos durante la ejecución.
Para generar un informe local sin modificar la referencia archivada:

```bash
python scripts/reports/GENERAR_PRODUCTION_REFERENCE.py --out salida/referencia_produccion.json
```

`--reuse-backtest` exige un resultado de la misma ventana, código, entorno y
hashes. Por defecto, un error de pruebas bloquea la generación del informe.

Contrato de columnas: 3 dobles sobre los 14 partidos = 8 columnas a 0,75 EUR
= 6,00 EUR máximo; Pleno al 15 separado. `OPTIMIZADOR_COLUMNAS.py` evalúa 364
combinaciones con los **signos realmente cubiertos** (incluidas las bandas
cuando aplican) y calcula P(≥10) … P(≥14) por convolución bajo independencia
entre partidos. El optimizador semanal distingue tres dobles con Pleno fijo,
columnas libres de cobertura y EV parimutuel **estimado**, no ROI realizado.

Estas cifras son una referencia reproducible, no una garantia de resultados.

## xG (Understat) — experimento evaluado, no activo

Se integro el xG de disparo de Understat (Primera, 2014-2024; validado en
`REVISION_12_XG_UNDERSTAT.md`) como feature rodante point-in-time en
`scripts/motor/features.py`. El experimento A/B walk-forward en 10 temporadas
(`REVISION_13_XG_INTEGRACION.md`, reproducido con
`python3 scripts/backtests/EXPERIMENTO_XG.py --solo-primera --max-seasons 10`)
mostró que **no mejora el modelo fuera de muestra** (−0,29 pp de acierto y
−0,071 en la media de tres dobles vs el conjunto activo). Por ello **no se
activa** en `feature_columns()` ni en la configuracion. La infraestructura queda
aditiva y disponible por si en el futuro se justifica (p. ej. xG posicional o
cobertura de Segunda).

## Dataset oficial

Fuente oficial: **histórico saneado** (`salida/datos_limpios/historico_saneado.csv`).

Justificación (REVISION_05): empate estadístico completo entre original y saneado
en los tres backtests (principal, 2025-26, 2024-25). McNemar no significativo
(p=0,0931 principal; IC95 incluye 0 en todos). El saneado añade trazabilidad,
exclusiones documentadas y corrige la entidad Cultural Leonesa. Por tanto, es la
fuente preferente sin coste predictivo.

El **histórico original** (`DATOS/historico_raw/`) queda como **dataset de
diagnóstico**, no como camino paralelo. No hay rama alternativa ni pipeline
duplicada: el saneado se genera desde el original con un solo comando
(`python scripts/datos/SANEAR_DATOS.py --confirm`) y se valida con
`pytest tests/test_sanitization.py`.
