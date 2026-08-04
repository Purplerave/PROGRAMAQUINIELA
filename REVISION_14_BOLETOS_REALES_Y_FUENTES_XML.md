# REVISION 14 — Boletos reales, fuentes XML y estado de la sesión

**Fecha:** 2026-08-04  
**Estado:** infraestructura implementada; captura XML validada en el equipo del usuario; enriquecimiento pendiente.

Este documento es el relevo operativo de la sesión. Debe leerse antes de tocar
las fuentes, los datos descargados o la métrica de tres dobles.

---

## 1. Objetivo

Corregir la limitación metodológica de `simulate_doubles`: hasta ahora agrupa
partidos consecutivos en bloques mecánicos de 15 filas. Es una métrica proxy y
**no** una simulación de boletos oficiales de La Quiniela.

La meta es evaluar predicciones y desarrollos sobre jornadas reales:

- los 14 partidos oficiales y su orden;
- el Pleno al 15 separado;
- fechas reales por partido para enlazar predicciones históricas;
- resultados oficiales;
- escrutinio/premio por categoría para medir ROI realizado.

No se puede inferir un boleto oficial ordenando CSV de fútbol por fecha o por
nombre de equipo.

---

## 2. Cambios implementados en este repositorio

### 2.1 Referencia de producción congelada

Commit `10447f4` separa los modos del motor:

```powershell
python MOTOR_QUINIELA_MAESTRO.py --historico original --modo produccion
```

- `produccion` entrena con el corte temporal establecido y evalúa únicamente
  los pesos persistidos en `CONFIG_MOTOR_V2.json`.
- `busqueda` conserva la optimización experimental y no es cifra de referencia.
- La referencia reproducida es 51,64 % frente a 51,56 % del favorito de mercado
  y 8,63/15 para el proxy de tres dobles.

### 2.2 Contrato API v1.1

El contrato incorpora `origen_prediccion` por partido y Pleno al 15:

- `motor_v4`;
- `manual_pendiente`;
- `manual_revisado`.

El generador mantiene `motor_v4` como fallback cuando el paquete fuente no
aporta origen. Esto transporta trazabilidad, pero no crea un flujo manual por
sí solo.

### 2.3 Backtest de boletos reales y ROI

Commit `b6c1730` añade:

- `scripts/backtests/QUINIELA_REAL.py`;
- `DATOS/quiniela_historica/README.md`;
- tests de validación y ROI.

El módulo acepta solo JSON con `schema_version: "1.0"` que declare:

- `ticket_id`, jornada, fecha y URL fuente;
- exactamente partidos 1..14, cada uno con fecha, local, visitante y signo;
- Pleno al 15;
- opcionalmente `payouts` por categoría.

El enlace a las predicciones exige **fecha + local + visitante** y descarta el
boleto entero si no puede cubrir los 14 partidos. `evaluate_realized_roi` no
calcula retorno si faltan pagos oficiales: devuelve
`status: missing_official_payouts`.

### 2.4 Captura XML de quinielista.es

Commit `de84764` añade:

```powershell
python scripts/datos/DESCARGAR_QUINIELISTA_XML.py --jornada 44 --temporada 2026 --fuente lae
```

Guarda evidencia externa en `salida/quinielista_raw/` (ignorado por Git): XML
original y manifiesto con URL, fecha UTC y SHA-256. Valida temporada, jornada y
la composición 1..15.

**Limitación deliberada:** este XML trae composición y porcentajes, pero no
fecha real por partido, resultado final ni escrutinio. Se marca como
`pending_enrichment` y no se convierte automáticamente en boleto histórico.

### 2.5 Auditor local de XML

Commit `fd3ec74` añade:

```powershell
python scripts/datos/AUDITAR_QUINIELISTA_XML.py
```

El auditor verifica SHA-256, estructura 1..15, cobertura esperada y que los
fixtures de `lae` y `publico` sean idénticos. Genera:

```text
salida/quinielista_raw/auditoria_quinielista_2026.json
```

---

## 3. Investigación de fuentes

### 3.1 `jualoppaz/pronostigol`

Repositorio: <https://github.com/jualoppaz/pronostigol>

- Aplicación Node/AngularJS/MongoDB antigua; licencia ISC.
- El modelo Mongo `quiniela_tickets` contempla temporada, jornada, fecha,
  precio, premio y lista de partidos. Es una referencia útil de esquema.
- El repositorio no incluye el dump de MongoDB con el histórico.
- La API pública prevista no pudo consultarse desde el sandbox por error TLS.
- No integrar la aplicación: está desactualizada. Solo considerar un adaptador
  si se obtiene una exportación legal/auditable de sus tickets.

### 3.2 `RicardoMoya/KinielaGPT`

Repositorio: <https://github.com/RicardoMoya/KinielaGPT>

- Identifica endpoints XML de `quinielista.es` por jornada y temporada.
- Su licencia AGPL-3.0 impide copiar/integrar su código en este proyecto sin
  asumir las obligaciones de AGPL para la obra derivada.
- Se puede estudiar independientemente el endpoint público; no se debe copiar
  su heurística de ajuste de mercado sin backtest propio.
- Desde el sandbox los endpoints devolvieron errores TLS; desde el equipo del
  usuario sí responden.

---

## 4. Captura realizada en el equipo del usuario

Ruta local del usuario:

```text
C:\Users\Mortadelo\Desktop\QUINIELAs\PROGRAMAQUINIELA
```

Temporada consultada: `2026`, que el endpoint representa como 2025-26.

Se descargaron dos variantes por jornada:

- `lae`;
- `publico`.

Resultado de auditoría local tras reintentos:

```text
XML válidos: 148/150
Faltantes: 2 | Inválidos: 0 | Fixtures distintos: 0
Estado: incomplete_or_inconsistent
```

Faltan solamente:

| Jornada | Fuente |
|---:|---|
| 24 | lae |
| 65 | lae |

Las variantes `publico` de esas jornadas existen. Para las 73 jornadas con
ambas variantes, los 15 fixtures tienen el mismo orden y los mismos equipos.
Los dos XML LAE ausentes no bloquean el trabajo de composición; solo impiden
comparar sus porcentajes LAE específicos.

**No borrar ni versionar automáticamente** `salida/quinielista_raw/`. Es
material externo descargado y reproducible, correctamente ignorado por Git.

---

## 5. Datos locales adicionales descubiertos

En el equipo del usuario existen archivos no versionados:

```text
DATOS/boletos_lae_reales/
DATOS/boletos_lae_fuente/
202526.json
tmp_debug/
python
```

No ejecutar `git clean`, `git reset --hard` ni añadirlos a Git sin auditoría.

Hasta ahora se han identificado **9** ficheros en `DATOS/boletos_lae_reales/`:

```text
Q15_2025_2026_J001.json … J008.json, J010.json
```

Ejemplo conocido de `Q15_2025_2026_J001.json`:

```json
{
  "id": "Q15_2025_2026_J001",
  "jornada_q15": 1,
  "temporada": "2025-2026",
  "fuente": "Quiniela15/resultados-quiniela",
  "source_url": "https://www.quiniela15.com/resultados-quiniela/1",
  "partidos": [
    {"num": 1, "local": "Girona", "visitante": "Rayo", "resultado": "1-3", "signo": "2"}
  ]
}
```

Estos JSON son una fuente piloto prometedora porque contienen equipos,
resultado y signo. Sin embargo, no se deben etiquetar como oficiales LAE sin
contraste: su fuente declarada es `Quiniela15/resultados-quiniela`.

### Validación posterior del piloto J001

El usuario ejecutó la inspección de J001. Quedó confirmado que contiene 15
partidos ordenados:

- posiciones 1..14: marcador `goles_local-goles_visitante` y signo `1`, `X` o
  `2` coherente;
- posición 15: marcador exacto y signo de **bucket de Pleno**. Quiniela15
  conserva `1-1` cuando ambos goles son 0..2, pero usa `M2` para un marcador
  como `3-2` (`M` = tres o más goles).

Se observaron cadenas como `AlavÃ©s`, `MÃ¡laga` y `CastellÃ³n` en la consola
PowerShell. Esto es mojibake de visualización/lectura ANSI de PowerShell, no se
debe corregir manualmente en los JSON fuente. El importador lee UTF-8 con BOM y
aplica una reparación conservadora solo para el emparejamiento.

No hay fecha ni pagos/escrutinio en el esquema observado. La fecha se puede
derivar únicamente tras coincidencia única de local+visitante contra
Football-Data de la misma temporada; ROI continúa bloqueado hasta disponer de
premios verificables.

### Primer intento de cruce (estado 2026-08-04)

El primer intento rechazó los 9 boletos, correctamente, en la primera
coincidencia ausente de cada uno. Reveló dos clases de causa:

1. **Alias de nomenclatura** entre Quiniela15 y Football-Data: `Rayo`/
   `Vallecano`, `R. Sociedad`/`Sociedad`, `Real Oviedo`/`Oviedo`,
   `Athletic`/`Ath Bilbao`, `Espanyol`/`Espanol`, `Sporting Gijón`/`Sp Gijon`
   y `Deportivo`/`La Coruna`. El importador incorpora ahora estos alias
   explícitos y testeados; no usa emparejamiento aproximado.
2. **Partidos fuera de Primera/Segunda**, que el histórico/modelo actual no
   cubre: al menos `Athletic - Arsenal` (J006) y `FC Kairat Almaty - Real
   Madrid` (J010). Estos no deben forzarse ni imputarse. Un boleto que los
   contenga no podrá evaluarse como boleto completo del motor español hasta
   disponer de predicciones históricas compatibles para esas competiciones.

El siguiente reintento debe distinguir boletos españoles completos de los que
quedan fuera de cobertura, preservando el motivo exacto en `failures`.

### Importador de propuesta

Commit `93552eb` añade:

```powershell
python scripts/datos/IMPORTAR_BOLETOS_QUINIELA15.py
```

El importador procesa `DATOS/boletos_lae_reales/Q15_*.json`, repara mojibake,
exige posiciones 1..15, deriva fechas por coincidencia única contra
Football-Data, y compara marcador y signo antes de escribir:

```text
salida/quiniela_historica_propuesta_2025_2026.json
```

No altera JSON fuente, no escribe en `DATOS/quiniela_historica/` y marca la
salida como `proposal_not_official_lae`. Todo boleto ambiguo o con un marcador
inconsistente queda en `failures` y no se usa.

---

## 6. Estado Git del equipo del usuario

El usuario trabaja en otra rama local:

```text
arena/019fc667-programaquiniela
```

No confundirla con la rama de esta sesión de Arena (`arena/019fcc17-programaquiniela`).
En la sesión local del usuario se resolvió un merge preservando sus versiones
locales de `ROADMAP_PROGRAMA_QUINIELA.md` y
`scripts/motor/GENERAR_CONTRATO_API.py`, porque eran más completas. Tras ello
su rama quedó adelantada respecto a su remoto por 16 commits y los datos
anteriores permanecieron sin seguimiento.

El usuario debe hacer copia/backup de las carpetas de datos antes de nuevas
operaciones Git. Un `git push` de su rama solo publicará archivos versionados;
no subirá esos datos no rastreados.

---

## 7. Siguiente paso exacto

No descargar más lotes ni modificar el motor todavía. Primero inspeccionar el
esquema completo de un boleto piloto local:

```powershell
$d = Get-Content -Raw DATOS\boletos_lae_reales\Q15_2025_2026_J001.json | ConvertFrom-Json
"Campos superiores:"
$d.PSObject.Properties.Name
"Total de partidos:"
$d.partidos.Count
"Partidos 1 a 15:"
$d.partidos | ForEach-Object {
    "{0} | {1} | {2} | resultado={3} | signo={4}" -f `
        $_.num, $_.local, $_.visitante, $_.resultado, $_.signo
}
```

Con ese esquema se implementará un importador separado que:

1. copie/transforme los nueve JSON a un artefacto de propuesta, sin modificar
   sus originales;
2. derive la fecha exclusivamente si el emparejamiento local/visitante es único
   en el histórico de la temporada;
3. marque toda ambigüedad como error de revisión manual;
4. valide los signos contra los resultados de Football-Data;
5. no calcule ROI hasta disponer de escrutinio/premios verificables.

---

## 8. Verificaciones realizadas antes del relevo

En la rama de Arena:

```text
164 passed, 29 warnings
```

Los warnings existentes son de columnas de tiros totalmente ausentes en parte
de los tests y una deprecación de fixture de pytest; no son fallos de los
módulos de boletos/XML.
