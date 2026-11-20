# Configuración de credenciales (API de Highlightly)

El proyecto nunca guarda credenciales en Git. La clave se configura mediante
`HIGHLIGHTLY_API_KEY` en el entorno o en `.env` en la raíz del proyecto; ambos
métodos son compatibles y `.env` está ignorado por `.gitignore`.

```dotenv
HIGHLIGHTLY_API_KEY=TU_CLAVE_AQUI
```

## Selección del endpoint

El endpoint por defecto es RapidAPI:

- URL: `https://football-highlights-api.p.rapidapi.com`
- Headers: `x-rapidapi-key` y `x-rapidapi-host: football-highlights-api.p.rapidapi.com`

Para usar el host directo de Highlightly, sin header `x-rapidapi-host`:

```dotenv
HIGHLIGHTLY_HOST=sports.highlightly.net
```

También puede configurarse como URL completa, por ejemplo
`HIGHLIGHTLY_HOST=https://sports.highlightly.net`.

Para otro host de RapidAPI, define su hostname `*.rapidapi.com` en
`HIGHLIGHTLY_HOST`; el cliente utiliza ese mismo hostname en el header
`x-rapidapi-host`. El endpoint y el header se derivan de una sola selección
para evitar enviar el host de RapidAPI a la API directa.

## Validar

```bash
python scripts/datos/DESCARGAR_HIGHLIGHTLY_XG.py --prueba 5
```

La prueba descarga solo cinco partidos y no escribe CSV. Para inspeccionar una
respuesta JSON sin procesar:

```bash
python scripts/datos/DESCARGAR_HIGHLIGHTLY_XG.py --raw <match_id>
```

## Seguridad

- No subas `.env` ni la clave a Git.
- El cliente envía la clave solo al endpoint configurado.
- Un error HTTP 401/403 se informa como error; el cliente no reintenta esos
  estados. Solo reintenta HTTP 429 según su política de espera.
