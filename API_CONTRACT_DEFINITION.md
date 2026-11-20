# Contrato JSON v1.1 — Liga de Maestros

**Salida local:** `salida/api_maestros_J{jornada}.json`. Se crea a partir de
`salida/paquete_jornada_J{jornada}.json` con `PREDECIR_JORNADA.py` o:

```bash
python scripts/motor/GENERAR_CONTRATO_API.py --jornada 74
```

El contrato no hace una petición de red. El consumidor debe aceptar v1.1
antes de usarla; no se ha validado un importador remoto. Si faltan casillas, probabilidades
válidas o un Pleno utilizable, el exportador falla y no reemplaza un archivo
anterior. Un archivo anterior no acredita el éxito de una ejecución nueva:
comprueba el código de salida y `fecha_generacion`.

## Objeto principal

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `contrato_version` | string | `1.1`, esquema `major.minor`. |
| `jornada` | entero | Identificador positivo que debe coincidir con el paquete fuente. |
| `fecha_generacion` | ISO 8601 | Marca de tiempo del paquete usado. |
| `modelo_version` | string | Versión declarada del modelo; `unknown` si el paquete no la contiene. Cada partido tiene su propia fuente. |
| `partidos` | array | Objetos con las posiciones únicas 1–14. |
| `pleno15` | objeto | Datos de la casilla 15, separada del bloque 1X2. |

## Partido 1–14

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `numero`, `local`, `visitante` | entero, string, string | Posición oficial y nombres no vacíos. |
| `probabilidades` | objeto | Exactamente `1`, `X` y `2`; números finitos de 0 a 1 que suman 1. |
| `signo_maestro`, `apuesta`, `tipo` | string o null | Signo recomendado, signos cubiertos y `simple`, `doble` o `triple`. Los tres pueden quedar `null` si el paquete no aporta recomendación. |
| `confianza` | número | Índice entre 0 y 1, no promesa de acierto. |
| `fuente_probabilidades` | string | `motor_maestro` o proxy declarado: `apu_fallback`, `lae_fallback`, `q15_fallback`. |
| `origen_prediccion` | string | `motor_v4`, `manual_pendiente` o `manual_revisado`. Un proxy sin origen explícito queda `manual_pendiente`. |

Las recomendaciones de este bloque son diagnósticos por partido. El boleto
optimizado de tres dobles está por separado en el paquete local; usa los
mismos vectores 1X2, pero respeta el presupuesto global.

Los porcentajes de una fuente externa son comparativos: no son cuotas de
mercado, ni probabilidades validadas del motor. No se genera un 33/33/33 como
sustituto de una distribución ausente.

Un elemento de `partidos` en una jornada mixta (fragmento):

```json
{
  "numero": 1,
  "local": "Equipo A",
  "visitante": "Equipo B",
  "probabilidades": {"1": 0.45, "X": 0.28, "2": 0.27},
  "signo_maestro": "1",
  "apuesta": "1X",
  "tipo": "doble",
  "confianza": 0.65,
  "fuente_probabilidades": "apu_fallback",
  "origen_prediccion": "manual_pendiente"
}
```

## Pleno al 15

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `local`, `visitante` | string | Equipos del Pleno. |
| `marcador` | string | Marcador exacto del modelo o marcador declarado por Q15. |
| `pronostico_local`, `pronostico_visitante` | string | Buckets oficiales `0`, `1`, `2`, `M` (3 o más). |
| `fuente_probabilidades`, `origen_prediccion` | string | Procedencia del modelo o del proxy Q15. No se rellena con `1-1` si falta la fuente. |
| `goles_conjuntos` | objeto opcional | Distribución de los 16 signos del Pleno cuando existe modelo; se selecciona la combinación más probable, no el producto de modas marginales. Esta combinación puede diferir del marcador exacto mostrado. |
| `goles_local`, `goles_visitante`, `top_marcadores`, `lambdas` | opcionales | Diagnóstico adicional del motor. |

La validez del JSON acredita estructura y procedencia declarada, no que el
pronóstico esté autorizado para envío o sea rentable. El panel semanal tiene
un flujo de exportación local independiente; no despliega estos archivos.
