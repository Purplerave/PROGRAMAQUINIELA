# Mejoras aplicadas tras la auditoría externa del 20/11/2026

Rama `arena/0683e24a-programaquiniela`, sobre `e422abe`. Este informe documenta
**solo lo que se cambió y cómo se verificó**. No cambia resultados deportivos ni
inventa datos, cuotas o licencias.

## Resumen

| Hallazgo de la auditoría | Estado tras esta pasada | Evidencia |
| --- | --- | --- |
| **P0** datos con licencia dudosa en repo público | Manifiesto legible por máquina, verificación en CI, exclusión de exportaciones y guía de purga del historial | `DATOS/PROCEDENCIA_DATOS.json`, `scripts/datos/VERIFICAR_PROCEDENCIA.py`, `.gitattributes`, 12 pruebas |
| **P1** cifra de referencia no totalmente fuera de muestra | Walk-forward **anidado** implementado y ejecutado sobre la misma ventana | `scripts/backtests/WALK_FORWARD_ANIDADO.py`, `salida/walk_forward_anidado.json` |
| **P1** «ensemble» es 95 % mercado | Documentación viva corregida; descripción explícita de «favorito de mercado + ajuste pequeño» | `README.md` (§ «Qué es y qué no es este motor») |
| **P1** sin evidencia prospectiva | Registro append-only con cadena de hashes, invariantes temporales y CLI; vacío y validado | `scripts/motor/registro_prospectivo.py`, 19 pruebas |
| **P1** `salida/` y `SALIDAS/` colisionan en Windows | Una sola carpeta física y alias; 11 scripts, `settings`, CI y documentación migrados; prueba de regresión de rutas | `settings.py`, `tests/test_rutas_salida.py` |
| **P2** `LMARENA/` (14 MB) con copias divergentes | 67 archivos retirados (64 CSV duplicados y 3 copias obsoletas); laboratorio aislado y documentado | `LMARENA/README.md` |
| **P2** reproducibilidad | Locks con SHA-256, versiones exactas, matriz Linux/Windows/macOS, `pip check` | `requirements*.lock.txt`, `.github/workflows/ci.yml` |
| **P2** lint testimonial (`E9,F82x`) | Ruff completo (E4/E7/E9/F/W/B/UP/SIM/RUF/C4) limpio: de 408 avisos a 0 | `pyproject.toml`, `make lint` |
| **P2** `read_pickle` sobre caché local | Caché JSON gzip versionada, sin ejecución de código | `scripts/backtests/EVALUAR_ACIERTOS_BOLETOS.py` |

## 1. P0 — Procedencia y licencias

No se puede resolver una licencia sin hablar con quien aportó cada fuente, así
que se ha hecho lo que sí se puede verificar automáticamente:

1. `DATOS/PROCEDENCIA_DATOS.json` declara 9 fuentes con origen, URL, licencia,
   estado (`verificada` / `no_verificada` / `prohibida_redistribucion`),
   atribución, fecha de captura y SHA-256 de 65 archivos inmutables.
   Resultado: **2 fuentes verificadas** (StatsBomb Open Data con atribución y
   los artefactos propios) y **7 sin verificar** (histórico de football-data,
   Highlightly y su derivado, adjunto de Liga F, muestra de BetExplorer,
   jornadas/boletos de LAE).
2. `scripts/datos/VERIFICAR_PROCEDENCIA.py` falla (código 1) si:
   - alguna ruta de `DATOS/` no está declarada;
   - un hash declarado no coincide con el archivo;
   - el estado de licencia no pertenece al vocabulario;
   - una fuente no redistribuible no está excluida de las exportaciones.
3. `.gitattributes`: las rutas sin licencia verificada llevan `export-ignore`,
   de modo que `git archive`, los ZIP de release y los paquetes publicables no
   las incluyen. El repositorio sigue siendo clonable con su historial, pero un
   artefacto de distribución ya no redistribuye datos sin permiso.
4. Job `procedencia` en CI ejecuta el verificador en cada push y PR.
5. `DATOS/README.md` y `README.md` explican las consecuencias operativas.

**Lo que queda en manos humanas** (no automatizable):

```bash
# Reescribir el historial para eliminar los datos no verificables. Cambia TODOS
# los SHA; requiere decisión explícita y coordinación con quien tenga clones.
git filter-repo --invert-paths \
  --path DATOS/historico_raw --path DATOS/highlightly_dataset \
  --path DATOS/highlightly_enriquecido --path DATOS/jornadas_lae \
  --path DATOS/boletos_lae_reales --path DATOS/boletos_lae_fuente \
  --path DATOS/ligaf/liga_f_partidos_2023-27.csv
```

Confirmar por escrito la licencia de las 7 fuentes pendientes es la única vía
para pasar de `no_verificada` a `verificada`. El manifiesto tiene
`--actualizar` para refrescar hashes cuando los datos cambien con permiso.

## 2. P1 — Evaluación: walk-forward anidado

**Problema.** En modo producción los pesos (HGB 0,049 / mercado 0,951), los
parámetros de dobles y las bandas congeladas se eligieron mirando 2019-26 y
luego se aplican a esas mismas temporadas. Las bandas ya se estimaban solo con
`train` (`_attach_calibracion_bandas`), pero los pesos no.

**Solución.** `scripts/backtests/WALK_FORWARD_ANIDADO.py` (nuevo, `make anidado`)
compara dos brazos sobre la misma ventana:

- *congelado*: `selection_mode="production"`, la configuración publicada
  aplicada hacia atrás (el backtest oficial);
- *anidado*: `selection_mode="search"`, que re-elege pesos y parámetros de
  dobles en cada temporada exterior usando **solo temporadas anteriores**.

**Resultado (histórico saneado, 2019-20 a 2025-26, n=5.894):**

| Brazo | Acierto simple | Favorito de mercado | Diferencia | IC95 pareado | McNemar | 3 dobles |
| --- | --- | --- | --- | --- | --- | --- |
| Congelado (publicado) | 50,15 % | 49,83 % | +0,32 pp | [−0,08; +0,75] | p = 0,1454 | 8,42/15 |
| **Anidado (honesto)** | **50,29 %** | 49,83 % | **+0,46 pp** | [−0,12; +1,05] | p = 0,1364 | **8,51/15** |

La comparación directa congelado vs anidado da −0,14 pp (p = 0,594) y los pesos
elegidos difieren en **6 de 7 temporadas**. Lectura correcta:

- el sobreajuste de la configuración congelada es **pequeño**, como sospechaba
  la auditoría: reajustar fuera de muestra no hunde el resultado;
- aun así, la ventaja frente al mercado **sigue sin ser significativa** en
  ninguno de los dos brazos;
- por temporada el anidado oscila entre −0,24 pp y +1,90 pp, ruido propio de
  ~842 partidos por temporada. No hay regularidad que explotar.

Cifra a citar en adelante: **50,29 % vs 49,83 %, diferencia no significativa**.
El +0,32 pp publicado era la estimación optimista.

## 3. P1 — Qué es el motor

`README.md` ya no deja lugar a la interpretación anterior. Se documenta que:

- HGB pesa 0,049, mercado 0,951, logit 0 y Poisson 0;
- no es «mercado + Poisson + ML»;
- su valor está en el generador de boletos, el optimizador de columnas, el
  modelo de Pleno y la trazabilidad temporal;
- la evidencia prospectiva está a cero y así se dice.

`REVISION_05` y `REVISION_10` se conservan como informes fechados (describen el
estado de entonces); la documentación viva es la que manda.

## 4. P1 — Registro prospectivo append-only

`scripts/motor/registro_prospectivo.py` + `DATOS/registro_prospectivo.jsonl`:

- una línea JSON por partido con predicción, probabilidades, corte, kickoff,
  cuotas y hora de observación;
- invariantes duras: `registrado_at ≤ prediction_cutoff_at < kickoff_at` y
  `odds_observed_at ≤ prediction_cutoff_at` (tolerancia 1 s);
- cadena SHA-256 (`hash_prev` + `hash`): editar una línea rompe la cadena;
- sin duplicados `(jornada, num_partido)`;
- `--verificar`, `--resumen`, `--anadir`; `make registro-verificar`;
- `--resumen` no calcula ROI sin cuotas auditadas.

El registro está **vacío a propósito**: no se rellenan jornadas pasadas con
precios recordados a posteriori. Eso sería exactamente el sesgo que la
auditoría señala.

## 5. P1 — Una sola carpeta de salida

- `settings.SALIDA_DIR = <repo>/salida`; `settings.SALIDAS_DIR` es ahora un
  **alias del mismo objeto** (compatibilidad para consumidores externos).
- Migrados 11 scripts y módulos (más `settings.py`), `Makefile`, `.gitignore`,
  CI y documentación viva. `SALIDAS/.gitkeep` eliminado del árbol.
- La única subcarpeta `SALIDAS` que sobrevive es la del contrato de importación
  externo (`salida/entrega_liga_maestros/J<N>/SALIDAS/`), documentada en el
  código.
- `tests/test_rutas_salida.py` verifica: alias idéntico, ningún módulo con
  `SALIDAS_DIR`, y ninguna ruta versionada que colisione al ignorar
  mayúsculas.

## 6. P2 — Laboratorio, dependencias y lint

**LMARENA.** Retirados 64 CSV idénticos (SHA-256) a `DATOS/historico_raw`
(9 MB de duplicados), la copia **desactualizada** de `CONFIG_MOTOR_V2.json`, la
copia divergente de `calibrador_bandas.py` y una `production_reference.json`
obsoleta. Se conservan los scripts y datasets únicos con un `README.md` que
explica su estado y cómo recuperar lo retirado del historial.

**Reproducibilidad.**

- `requirements.txt` / `requirements-dev.txt`: versiones exactas, sin rangos
  (`requests==2.34.2` en lugar de `>=2.31`).
- `requirements.lock.txt`, `requirements-dev.lock.txt`,
  `requirements-tools.lock.txt`: árbol transitivo completo con hashes
  (`pip-compile --generate-hashes`). Instalación verificada en entornos limpios
  con `pip install --require-hashes`, incluido `pip check`.
- `make lock` regenera. `pip-tools` va en un `.in` aparte porque depende de
  `pip`, que no se puede fijar con hash sin tocar el instalador.
- CI: matriz **Ubuntu 3.11/3.12 + Windows 3.12 + macOS 3.12**, instalación
  desde el lock, `pip check` y suite completa.
- Caché local de `EVALUAR_ACIERTOS_BOLETOS.py` pasa de `pickle` a JSON gzip con
  versión; un `.pkl` antiguo se ignora y se recalcula.

**Lint.** `pyproject.toml` selecciona `E4,E7,E9,F,W,B,UP,SIM,RUF,C4` con
exclusiones justificadas (longitud de línea, caracteres unicode en español,
ternarios explícitos) y `per-file-ignores` para `E402` en scripts que ajustan
`sys.path`. De los **408 avisos** de la auditoría se pasó a **0**.

Correcciones con valor real que aparecieron al limpiar:

- dos bucles anidados colapsables y un `dict`-comprehension que era una
  identidad (`WALK_FORWARD_PESOS`);
- `rapidapi_host` calculado siempre como `None` en `DESCARGAR_HIGHLIGHTLY_XG`;
- variables muertas en `build_hgb_model`, `ADAPTAR_HIGHLIGHTLY`,
  `dixon_coles` y varios tests;
- reexportaciones de `MOTOR_QUINIELA_MAESTRO` (`implied_probabilities` y
  compañía) restauradas explícitamente: son API pública aunque el módulo no las
  use.

## 7. Verificación ejecutada

| Comprobación | Resultado |
| --- | --- |
| `make lint` (`ruff check .` + `git diff --check`) | **0 avisos**, diff limpio |
| `pytest tests/ -q` | **427 pruebas aprobadas, 1 omitida** (antes: 377), 4 min 13 s |
| `make test-fast` (`-m "not slow"`) | **415 pruebas en 29 s** (las dos integraciones de ~105 s quedan marcadas `slow`) |
| `python scripts/datos/VERIFICAR_PROCEDENCIA.py` | 0 errores, 7 avisos de licencia declarados |
| Backtest oficial 2019-20…2025-26 | Reproduce **50,15 % vs 49,83 %**, n=5.894, p=0,1454 |
| Walk-forward anidado | **50,29 % vs 49,83 %**, IC95 [−0,12; +1,05], p=0,1364 |
| Instalación `--require-hashes` | Correcta en venv limpio (runtime y dev) |

El backtest se repitió después de los cambios y coincide dígito a dígito con la
cifra documentada: el motor predictivo y sus parámetros **no se tocaron**.

## 8. Pendientes que requieren decisión humana

1. **Confirmar licencias** de las 7 fuentes pendientes (o retirarlas del
   historial con `filter-repo`).
2. **Acumular evidencia prospectiva** con el registro nuevo: predicción y cuota
   antes del corte, sin tocar pesos durante la ventana.
3. **Cierres reales de cuota** en las 7.663 filas sin tripleta de cierre y
   tiros en las 3.234 sin disparos: no se imputan.
4. **Priors 2026-27**: el artefacto sigue siendo del 04/07/2026; actualizarlo
   exige fuente, fecha de disponibilidad y regla de corte.
5. **Historial de Git**: reescritura solo con autorización explícita.

## 9. Límites

- No se ha revisado el historial de Git ni se ha reescrito.
- No se ha validado el panel en un Windows real; la matriz de CI lo hará en el
  primer push.
- `make test-fast` omite las dos pruebas de integración más lentas; el CI
  ejecuta siempre la suite completa.
- La matriz anidada no corrige la dependencia entre partidos de una misma
  jornada; el bootstrap es por partido, como el informe anterior.
- Las mejoras de lint no implican que el motor sea mejor: solo que el código es
  más fácil de auditar.
