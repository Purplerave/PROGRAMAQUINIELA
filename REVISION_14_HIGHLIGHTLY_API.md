# REVISION 14: integración con la API PRO de Highlightly (xG)

Fecha: 2026-08-03
Relacionado con: ROADMAP #3 (parte xG) y REVISION_13.

## Objetivo

Dar al usuario una forma segura y reproducible de aprovechar su plan **PRO de
Highlightly (7500 llamadas)** para descargar el **xG por partido de La Liga**,
sin comprometer la clave ni gastar el presupuesto a ciegas.

## Por qué no se puede llamar a la API desde el sandbox

- El entorno de ejecución del agente **no tiene salida a internet** (todas las
  peticiones TLS directas fallan).
- La herramienta de proxy web disponible **no puede inyectar cabeceras
  HTTP**; y la API de Highlightly exige la cabecera `x-rapidapi-key` (devuelve
  403 "Missing mandatory HTTP Headers" sin ella).

Por tanto, la descarga real la ejecuta **el usuario en su máquina** con su
clave. El agente prepara el cliente correcto, los tests y el pipeline de
validación posterior.

## Autenticación confirmada

- Host directo: `https://sports.highlightly.net`
- Header obligatorio: `x-rapidapi-key: <clave>`
- Vía RapidAPI: además `x-rapidapi-host` **`football-highlights-api.p.rapidapi.com`**
  (confirmado por el usuario). El cliente usa este host por defecto.

## Entregables

| Archivo | Propósito |
|---|---|
| `scripts/datos/highlightly_client.py` | Cliente (leagues, matches, statistics, lineups) + parsing de xG. Lee la clave de `HIGHLIGHTLY_API_KEY` (env) o `.env`. |
| `scripts/datos/DESCARGAR_HIGHLIGHTLY_XG.py` | Descarga xG por temporada de La Liga → CSV (mismo esquema que Understat). Modos `--prueba` y `--raw`. |
| `ENV_EJEMPLO.md` | Cómo configurar `.env` (ignorado por git) y validar. |
| `tests/test_highlightly_client.py` | Parsing y carga de clave validados sin red (8 tests). |
| `requirements.txt` | Añade `requests`. |

## Cómo lo usará el usuario

```bash
# 1. Crear .env con HIGHLIGHTLY_API_KEY=...

# 2. Validar con pocas llamadas
python scripts/datos/DESCARGAR_HIGHLIGHTLY_XG.py --prueba 5

# 3. (opcional) inspeccionar respuesta cruda si el xG sale None
python scripts/datos/DESCARGAR_HIGHLIGHTLY_XG.py --raw <match_id>

# 4. Descarga completa
python scripts/datos/DESCARGAR_HIGHLIGHTLY_XG.py --desde 2014 --hasta 2025 --confirm

# 5. Medir cobertura (igual que con Understat)
python scripts/datos/MEDIR_COBERTURA_XG.py --xg DATOS/highlightly_dataset/highlightly_la_liga_xg.csv --confirm
```

## Presupuesto

- Cada partido = 1 llamada a `/football/statistics/{match_id}`.
- La Liga ≈ 380 partidos/temporada.
- Rango 2014-2025 ≈ 4560 llamadas (dentro del PRO de 7500).

## Nota sobre el parser

El parser de xG busca el atributo `displayName` que contenga
`"Expected Goal"` en cada equipo de `/statistics`. Como el agente no puede ver
la respuesta autenticada real, se incluye `--raw` para que el usuario capture
una respuesta y, si el esquema difiere, se ajusta el parser con datos reales.

## Estado

- Cliente, descargador, tests y guía **listos y testeables** (177 tests en
  verde).
- **Pendiente del usuario:** configurar `.env` y ejecutar el paso 2/4 para
  obtener el CSV de xG real.
- El motor sigue sin tocarse. Tras obtener el xG real, el siguiente paso es
  construir features rodantes de xG y validarlas fuera de muestra.

## Veredicto final (validado con la cuenta real del usuario, 03/08/2026)

Probes realizados en el host directo de Highlightly:

| Temporada | Partido | xG en statistics/match_detail |
|---|---|---|
| 2025/26 | Real Madrid vs Atletico (2026) | ✅ Sí (2.41) |
| 2022/23 | Cadiz vs Real Madrid (2023) | ❌ No |
| 2019/20 | Levante vs Getafe (2020) | ❌ No |

**Conclusión:** Highlightly solo ofrece xG en temporadas **muy recientes**
(2025/26), no en el histórico. Para un histórico profundo (2010-11 a 2025-26),
Highlightly **no sirve**.

**Decisión:** la fuente de xG para este proyecto es **Understat** (gratis, xG
por partido de La Liga 2014/15+, sin API key). Highlightly queda disponible
solo para temporada actual si se quisiera, pero no es la fuente de histórico.
