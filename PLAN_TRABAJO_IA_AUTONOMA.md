# Plan de trabajo para IA autónoma

## Misión

Mejorar y auditar `PROGRAMAQUINIELA` hasta dejar una versión local reproducible,
explicable y lista para congelar. Trabaja dentro de:

`C:\Users\Mortadelo\Desktop\QUINIELAs\PROGRAMAQUINIELA`

La ejecución de LM Arena está fuera de alcance. No modificarla, detenerla,
reiniciarla ni sustituir sus datos.

## Estado actual conocido

- Backtest walk-forward por temporadas: 7 temporadas, 842 partidos de test por temporada.
- Resultado anterior: motor `50,1018 %`, mercado `49,8303 %`, tres dobles `8,4770/15`.
- Resultado después de migrar bandas y cobertura a cuotas de apertura:
  motor `50,2715 %`, mercado `49,8303 %`, tres dobles aproximadamente `8,4770/15`.
- Contraste anterior motor/mercado: diferencial `+0,271 pp`, McNemar `p=0,230`.
- Hay trazabilidad `market_source` y `market_close_available`.
- Hay desglose por régimen y contraste pareado en
  `scripts/backtests/BACKTEST_HISTORICO_TEMPORADAS.py`.
- Suite de referencia: `280 pruebas pasadas`.
- El modelo actual es mercado-dominante: aproximadamente 95,1 % mercado y 4,9 % HGB.
- Los datos de LMArena no aportaron nuevas temporadas españolas válidas.

## Lectura obligatoria antes de actuar

Lee completamente:

1. `README.md`
2. `reports/AUDITORIA_COMPLETA_DATOS.md`
3. `reports/ESTUDIO_DATASETS_LMARENA.md`
4. `reports/ESTUDIO_MERCADO_REGIMENES.md`
5. `reports/production_reference.json`
6. `MOTOR_QUINIELA_MAESTRO.py`
7. `scripts/motor/features.py`
8. `scripts/motor/calibrador_bandas.py`
9. `scripts/motor/cobertura_bandas.py`
10. `AGENTS.md`, si existe.

## Reglas de seguridad y método

- No borres datos ni uses comandos destructivos.
- No hagas `git reset --hard`, `git checkout --` ni sobrescribas cambios ajenos.
- No descargues datasets nuevos sin documentar su procedencia.
- No uses información posterior al corte de predicción.
- No cambies pesos o reglas de producción sin backtest fuera de muestra.
- Cada cambio de motor debe tener una comparación antes/después.
- Compara siempre contra el favorito de mercado.
- Reporta como mínimo acierto simple, Brier, log-loss y media de aciertos con tres dobles.
- Conserva los cambios útiles y deja intactos los cambios no relacionados.
- No hagas commit ni push automáticamente. Deja el árbol preparado y solicita revisión.

## Fase 1 — Estado reproducible

1. Ejecuta `git status --short` y registra qué cambios ya existían.
2. Ejecuta la suite completa:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q
   ```

3. Ejecuta el backtest actual:

   ```powershell
   .\.venv\Scripts\python.exe scripts\backtests\BACKTEST_HISTORICO_TEMPORADAS.py
   ```

4. Guarda las cifras baseline en un informe temporal o en el informe final.
5. No continúes si el baseline no reproduce aproximadamente las cifras conocidas;
   investiga primero la discrepancia.

## Fase 2 — Validar las cuotas de apertura

Comprueba que calibrador y cobertura usan cuotas disponibles antes del corte:

- `open_odd_1`
- `open_odd_x`
- `open_odd_2`

Ejecuta A/B walk-forward:

1. reglas actuales;
2. reglas con apertura;
3. reglas desactivadas.

Evalúa por temporada, división y régimen. Incluye:

- acierto simple;
- favorito de mercado;
- Brier;
- log-loss;
- tres dobles;
- número de partidos afectados;
- McNemar o bootstrap pareado.

No llames “mejora” a una diferencia que no esté respaldada por el protocolo.

## Fase 3 — Auditar los movimientos de mercado

Investiga `market_move_1`, `market_move_x`, `market_move_2` y
`close_open_fav_gap`.

Compara tres brazos:

1. baseline actual;
2. movimientos anulados cuando no existe cierre real;
3. movimientos anulados siempre o redefinidos como última cuota disponible menos apertura.

La decisión debe considerar especialmente los dobles. Si el acierto no cambia pero
los dobles empeoran, no aplicar el cambio sin documentar el coste.

## Fase 4 — Timestamps de producción

Audita `MOTOR_PREDICCION_JORNADA.py` y el flujo que guarda predicciones.

Cada predicción real debe poder conservar:

- `odds_observed_at`;
- `prediction_cutoff_at`;
- `kickoff_at`.

Usa `validate_odds_timestamps` y añade pruebas que garanticen:

`odds_observed_at <= prediction_cutoff_at < kickoff_at`

No inventes timestamps cuando la fuente no los proporcione. En ese caso marca el
registro como no auditado y documenta la limitación.

## Fase 5 — Experimento Elo

Diseña un A/B walk-forward, sin tocar primero producción:

1. Elo actual.
2. Reversión parcial hacia 1500 entre temporadas.
3. Tratamiento de retornos largos y ascensos/descensos.

Mide por temporada y división. Prueba solo la variante que mejore fuera de muestra
sin empeorar estabilidad, mercado ni dobles. Si no mejora, deja el Elo actual.

## Fase 6 — Revisiones defensivas de baja prioridad

Audita y corrige solo si hay prueba y tests:

- split 80/20 que divide una misma fecha;
- desempate del favorito de mercado;
- resultado inválido `"0"` en `process_history`;
- datos externos con apertura/cierre incompletos;
- normalización de nombres y divisiones;
- avisos de pytest que puedan ocultar errores reales.

No conviertas correcciones cosméticas en cambios de modelo.

## Fase 7 — Reproducibilidad final

Cuando terminen los experimentos:

1. Actualiza `reports/AUDITORIA_COMPLETA_DATOS.md`.
2. Actualiza `README.md` con las cifras vigentes.
3. Regenera `reports/production_reference.json` usando el script oficial.
4. Comprueba que el protocolo descrito coincide exactamente con el código.
5. Unifica los hashes de datasets usando SHA-256.
6. Revisa mojibake y codificación UTF-8.
7. Ejecuta de nuevo suite completa y backtest.
8. Comprueba `git diff --check`.
9. No hagas commit ni push: entrega el árbol para revisión humana.

## Criterios para considerar terminado el trabajo

El trabajo solo está terminado si:

- la suite completa pasa;
- el backtest reproduce las cifras finales;
- cada cambio de modelo tiene A/B walk-forward;
- las reglas usan información disponible en el momento correcto;
- la documentación coincide con el código;
- los resultados contra mercado incluyen incertidumbre estadística;
- no quedan archivos temporales o credenciales en el repositorio;
- se entrega una lista de archivos modificados y una lista de pendientes.

## Informe final obligatorio

Devuelve un informe en español con estas secciones:

1. Resumen ejecutivo.
2. Baseline antes de los cambios.
3. Cambios aplicados.
4. Resultados antes/después por temporada.
5. Comparación contra mercado.
6. Intervalos de confianza y p-values.
7. Tests ejecutados.
8. Archivos modificados.
9. Riesgos y limitaciones.
10. Pendientes recomendados.

Si una hipótesis no se puede demostrar, escríbelo claramente y no la presentes
como mejora.
