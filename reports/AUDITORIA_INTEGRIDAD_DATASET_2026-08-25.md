# Auditoría de integridad del dataset histórico

Fecha: 25/08/2026

## Dictamen

El histórico local es internamente coherente y apto para continuar los
backtests con cautelas. No queda certificado al 100 % contra la fuente
externa original porque el repositorio no conserva una manifestación de
procedencia por archivo ni una comparación binaria reproducible contra cada
CSV descargado de la fuente.

La estructura y las columnas son compatibles con el formato público de
Football-Data, que publica archivos históricos separados para SP1 y SP2:
[Spain Football Results and Betting Odds](https://www.football-data.co.uk/spainm.php).

## Comprobaciones realizadas

| Comprobación | Resultado |
|---|---:|
| Archivos históricos | 32 CSV |
| Filas físicas | 13.475 |
| Fechas válidas | 13.472 |
| Filas completamente vacías | 3 |
| Resultados H/D/A válidos | 13.472 |
| Resultado incompatible con FTHG/FTAG | 0 |
| Duplicados por fecha/local/visitante | 0 |
| Primera por temporada | 380 filas cada temporada |
| Segunda esperada | 462 filas en la mayoría de temporadas |
| Cierres reales disponibles | 5.894 filas utilizables aproximadamente |

Las tres fechas inválidas corresponden a filas completamente vacías. Las
temporadas Segunda 2012-13 y 2013-14 tienen filas físicas adicionales que son
filas vacías, no partidos extra.

## Limitaciones detectadas

- Faltan columnas de tiros en 3.234 filas, principalmente por antigüedad del
  proveedor; no debe interpretarse como cero tiros.
- Hay 26 filas sin tripleta utilizable de apertura.
- Hay 7.578 filas sin cierre real. En ellas el motor no debe interpretar la
  cuota efectiva como un cierre observado.
- Hay 5 temporadas con estructura administrativa o huecos que requieren
  tratamiento separado.
- Existen 4 avisos sobre priors parciales de otra fuente; no afectan al
  histórico principal, pero no deben mezclarse automáticamente.
- LMArena no añade nuevas temporadas españolas: sus 32 históricos españoles
  comparados son binariamente idénticos a `DATOS/historico_raw`.

## Qué significa para Vivencia

La capa Vivencia puede usar este histórico para reconstruir estados internos,
pero sus resultados deben evaluarse solo sobre filas utilizables y con corte
temporal estricto. Las filas sin cuotas de apertura no deben entrar en una
validación que pretenda simular un boleto real.

## Veredicto operativo

1. El dataset no presenta señales internas de corrupción grave.
2. Los backtests de resultados son razonables desde el punto de vista de
   integridad estructural.
3. Los backtests económicos y de cuotas necesitan declarar exactamente qué
   filas tienen apertura y qué filas tienen cierre real.
4. Antes de congelar una versión definitiva conviene guardar un manifest SHA-256
   de los 32 CSV y comparar, al menos, una muestra completa de temporadas con
   la fuente original.
