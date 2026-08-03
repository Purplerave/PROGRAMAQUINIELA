# Configuración de credenciales (API de Highlightly)

El proyecto nunca guarda credenciales en el repositorio. La clave de la API de
Highlightly se configura en el fichero `.env` de la raíz del proyecto (ya está
en `.gitignore`, por lo que **no se sube a git**).

## 1. Crear el fichero `.env`

En la raíz del proyecto (`PROGRAMAQUINIELA/`), crea un archivo llamado `.env`
con este contenido:

```
HIGHLIGHTLY_API_KEY=TU_CLAVE_AQUI
```

Sustituye `TU_CLAVE_AQUI` por tu clave real (sin comillas). Se lee desde la
variable de entorno `HIGHLIGHTLY_API_KEY` o desde este `.env`.

## 2. Dónde está la clave

- **Host directo:** `https://sports.highlightly.net`, header `x-rapidapi-key`.
- **Si te registraste vía RapidAPI:** tu plan PRO está asociado a un host de
  RapidAPI (p.ej. `sport-highlights-api.p.rapidapi.com`). En ese caso, además
  de la clave hay que indicar el host. Si al usar el script recibes un error de
  host, dime y ajusto el cliente para añadir `x-rapidapi-host`.

## 3. Validar sin gastar el presupuesto

```bash
python scripts/datos/DESCARGAR_HIGHLIGHTLY_XG.py --prueba 5
```

Descarga solo 5 partidos y muestra el xG extraído (no escribe CSV). Si sale
`None`, ejecuta:

```bash
python scripts/datos/DESCARGAR_HIGHLIGHTLY_XG.py --raw <match_id>
```

para volcar el JSON crudo y afinar el parser.

## 4. Descarga completa

```bash
python scripts/datos/DESCARGAR_HIGHLIGHTLY_XG.py --desde 2014 --hasta 2025 --confirm
```

Escribe `DATOS/highlightly_dataset/highlightly_la_liga_xg.csv`.

## Seguridad

- No subas `.env` ni tu clave a git.
- `.env` y `.env.*` están ignorados por `.gitignore`.
- Este proyecto solo usa la clave para llamar a la API; no la envía a ningún
  otro sitio.
