# Revisión de mejoras pendientes — 20 de noviembre de 2026

## Alcance y dictamen

Revisión estática de los pendientes de `reports/AUDITORIA_TOTAL_2026-11-19.md`,
los metadatos de los priors de 2026/27, el tracker prospectivo y los comandos de
verificación. También se contrastaron las afirmaciones de la auditoría CTO
compartida por el usuario con el código de esta rama. No se modificaron
resultados deportivos, cuotas, pesos del modelo ni fuentes sin procedencia
verificable.

## Contraste de hallazgos de la auditoría CTO

La referencia inspeccionada en este checkout es `3e995d9ee35e5fa6277ce18986c9ea4881457236`
(rama de trabajo `arena/50c4ca06-programaquiniela`), no una rama `main` móvil.
La certificación documentada el 19/11 cita otro árbol; sus cifras sirven de
contexto, no son la certificación de esta rama. Hoy sí se ejecutó la suite
completa de este checkout.

| Hallazgo compartido | Contraste con el código de esta rama | Acción / decisión |
|---|---|---|
| C1 · congelar y certificar release en Linux, macOS y Windows | El workflow versionado ya incluye Python 3.11/3.12 sobre Ubuntu, pero no Windows/macOS. No se puede crear una etiqueta de lanzamiento o afirmar CI remota aprobada desde esta revisión. | No etiqueté ni publiqué una release; se necesita autorización de lanzamiento y una ejecución remota/Windows. |
| C2 · hacer inequívoco el origen de cuotas y parciales | El hallazgo de priors estaba presente y queda corregido abajo. El selector `scripts/motor/odds_at_cutoff.py` ya distingue `no_auditado`, `violacion` y `auditable`, y expone `fuente_tripleta` como `principal` o `apertura_fallback`; no declaré observada una apertura. La propagación y formato final deben conservarse al ampliar informes. | Se mantiene la política temporal existente; sigue pendiente registrar cierres reales para los datos que no los tienen. |
| C3 · RapidAPI/directo envía header incorrecto | **Confirmado.** Antes, cualquier `base_url` conservaba `x-rapidapi-host` aunque apuntase a `sports.highlightly.net`. Además, no había cobertura de transporte para los errores citados. | Corregido: se deriva el host del endpoint, se omite el header para el host directo y se permite override explícito. Añadidas pruebas para hosts, 429, 401/403, timeout y JSON inválido. |
| C4 · POST del panel sin protección CSRF | **Confirmado.** `/api/run` y `/api/exportar` aceptaban POST sin token ni comprobar `Origin`. | Corregido: token aleatorio por proceso, comprobación conjunta de host/origen loopback, comparación de token y rechazo de cuerpos POST. Se conserva el bind a `127.0.0.1`; no se vuelve servidor público. |
| C5 · procedencia del dataset Liga F adjunto | El README y manifiesto ya declaran proveedor/URL/licencia desconocidos, guardan hash y dicen no redistribuir antes de verificar permiso. | No hay fuente para resolverlo automáticamente. Uso interno no equivale a licencia de redistribución; confirmar con quien aportó el fichero. |
| Q1–Q6 · arranque, interfaz, lock, cobertura, informe y organización | Son mejoras válidas, pero varias requieren pruebas Windows, decisiones de formato/instalación o cambios transversales. | No se mezclaron con estas dos correcciones de seguridad/cliente. Permanecen en la hoja de ruta; evitar refactorizar o fijar dependencias arbitrariamente. |

**Cambio aplicado hoy:** los cuatro equipos sin splits local/visitante
(CD Eldense, CD Tenerife, CE Sabadell y RC Celta Fortuna) ya figuran en
`missing_or_partial`. Coincide ahora con sus estadísticas nulas y con
`missing_data_strategy.teams`; consumidores que leen esta lista reciben la alerta
de muestra baja. Se añadió una regresión que comprueba esta coherencia en los
datos del repositorio. No se fabricaron splits.

## Pendientes confirmados a esta fecha

| Prioridad | Pendiente | Estado comprobable / siguiente paso |
|---|---|---|
| **P1 · evidencia prospectiva** | No hay evidencia suficiente de ventaja frente al mercado y faltan cuotas al corte verificadas para una evaluación de Quiniela real. | La última auditoría pareada (5.894 partidos) reportó +0,322 pp en acierto, con IC95 % [−0,085; +0,730] y McNemar p=0,1454. No demuestra superioridad. El tracker `DATOS/paper_trading_2627.json` solo contiene la J2 de agosto: 14 resultados, 0 observaciones de cuotas verificadas y 0 apuestas core cerradas. Mantener pesos congelados; registrar predicciones, cuotas, corte, kickoff y fuente antes de cada partido. No presentar J2 como comparación prospectiva válida. |
| **P1 · calidad de histórico** | Siguen faltando cierres reales de cuota en miles de filas y datos de tiros en parte del histórico. | La auditoría total del 19/11 cuantificó 7.663 filas sin tripleta de cierre real y 3.234 sin columnas de tiros. La lista de priors incoherente queda corregida, pero las limitaciones de fuentes no. No reemplazar apertura por cierre ni imputar tiros como observados; conseguir snapshots trazables o excluir la característica del análisis correspondiente. |
| **P1 · actualidad de los priors** | El artefacto de estadísticas base es del 04/07/2026 y procede de la temporada 2025 (antes del inicio 2026/27). | La advertencia de confianza baja continúa siendo necesaria. No incorporar resultados 2026/27 sin fuente, fecha de disponibilidad y reglas de corte; actualizar la muestra cuando haya datos reproducibles. |
| **P1 · paper trading** | La señal visitante [1,8; 2,5) no ha llegado a la muestra para la evaluación intermedia; la actualización de agosto no acredita cuotas observadas. | El propio tracker fija evaluación intermedia en enero 2027 (n≈70) y final en junio (n≈120–140). Conservar regla preregistrada; no activarla en producción ni estimar ROI a partir de cuota ausente. |
| **P2 · reproducibilidad de dependencias** | `requests` sigue definido con rango abierto (`>=2.31`) y no existe lock completo con hashes. | Añadir lock de runtime/dev y probar instalación limpia en CI en un cambio separado. Antes, decidir el flujo y plataforma objetivo; no fijar versiones de forma arbitraria ni mezclar actualización de dependencias con cambios del modelo. |
| **P2 · cobertura y latencia** | La auditoría anterior reportó 67 % de cobertura combinada y alrededor de cinco minutos para la suite; maestro (35 %) y panel (51 %) son zonas débiles. | Perfilar primero las pruebas lentas. Añadir tests unitarios a funciones puras de entrenamiento/exportación con salidas congeladas y, al extraer módulos, demostrar paridad. Mantener la suite completa en CI. |
| **P2 · arquitectura y portabilidad** | El maestro concentra responsabilidades y conviven `salida/` y `SALIDAS/`. | Separar funciones en incrementos pequeños con pruebas de paridad. No consolidar rutas de salida hasta documentar compatibilidad con sistemas de archivos case-insensitive y scripts consumidores. |
| **P2 · gobernanza de datos** | Procedencia/licencia de algunas fuentes aportadas no está confirmada y los snapshots no son todavía un registro append-only homogéneo. | Mantener atribución, URL, fecha de captura, hash y estado de licencia por fuente; no ampliar la ingesta ni usar datasets no verificados para una afirmación de producción. |

## Límites de esta pasada

- Esta revisión no vuelve a ejecutar el backtest de siete temporadas: los
  cambios fueron de seguridad local, selección de endpoint API y metadatos; no
  se modificó el motor predictivo ni sus parámetros.
- No se actualizó el histórico 2026/27: no se reemplazan datos fechados por
  supuestos ni se accede a fuentes que no están versionadas localmente.
- Los porcentajes y hallazgos estadísticos anteriores son los documentados en
  la auditoría del 19/11; no deben interpretarse como mediciones de hoy.

## Verificación ejecutada hoy

- `python -m pytest tests/ -q`: **377 pruebas aprobadas** (4 min 15 s,
  Python 3.11.2; incluye los cambios de seguridad y cliente API).
- `python -m pytest tests/test_highlightly_client.py tests/test_flujo_semanal.py -q`:
  **29 aprobadas**.
- `python -m pytest tests/test_dataset_quality.py -q`: **6 aprobadas**.
- `make lint`: Ruff selectivo y `git diff --check` aprobados.
- `python scripts/datos/VALIDAR_DATASETS.py`: 34 CSV, 13.560 filas brutas,
  13.531 utilizables; parciales reales=4. Hallazgos: 10 informativos,
  7 avisos y **2 críticos**: tiros ausentes en 3.234 partidos y cierre real
  ausente en 7.663 filas. Ya no aparece el hallazgo de parcialidad incoherente.
- `pip check`: sin dependencias rotas.

El backtest no se repitió porque no se tocó el motor ni sus parámetros. La suite
completa pasó; esto no resuelve las limitaciones de fuentes y evaluación
prospectiva descritas arriba.

Ningún resultado histórico garantiza aciertos o rentabilidad futura.
