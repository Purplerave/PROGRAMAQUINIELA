from scripts.datos.IMPORTAR_BOLETOS_WEB import build_payload, parse_result_table
from scripts.motor.team_names import resolve_history_name


SAMPLE_HTML = """
<html><body>
<table>
  <tr><th>#</th><th>Partido</th><th>Goles</th><th>SIGNO</th><th>Pronósticos</th></tr>
  <tr>
    <td>1</td>
    <td>Girona<br>(1633.8)<br><br>-<br>Rayo<br>(1660.9)</td>
    <td>1<br>-<br>3</td>
    <td>2</td>
    <td>1<br>42%|35%|24%</td>
  </tr>
  <tr>
    <td>2</td>
    <td>Villarreal<br>(1744.4)<br><br>-<br>Real Oviedo<br>(1646.9)</td>
    <td>2<br>-<br>0</td>
    <td>1</td>
    <td>1</td>
  </tr>
  <tr><td>3</td><td>Alavés<br>(1)<br>-<br>Levante<br>(2)</td><td>2<br>-<br>1</td><td>1</td><td>X</td></tr>
  <tr><td>4</td><td>Mallorca<br>(1)<br>-<br>Barcelona<br>(2)</td><td>0<br>-<br>3</td><td>2</td><td>2</td></tr>
  <tr><td>5</td><td>Valencia<br>(1)<br>-<br>R. Sociedad<br>(2)</td><td>1<br>-<br>1</td><td>X</td><td>1</td></tr>
  <tr><td>6</td><td>Celta<br>(1)<br>-<br>Getafe<br>(2)</td><td>0<br>-<br>2</td><td>2</td><td>1</td></tr>
  <tr><td>7</td><td>Athletic<br>(1)<br>-<br>Sevilla<br>(2)</td><td>3<br>-<br>2</td><td>1</td><td>1</td></tr>
  <tr><td>8</td><td>Espanyol<br>(1)<br>-<br>At. Madrid<br>(2)</td><td>2<br>-<br>1</td><td>1</td><td>2</td></tr>
  <tr><td>9</td><td>R. Santander<br>(1)<br>-<br>Castellón<br>(2)</td><td>3<br>-<br>1</td><td>1</td><td>1</td></tr>
  <tr><td>10</td><td>Málaga<br>(1)<br>-<br>Eibar<br>(2)</td><td>1<br>-<br>1</td><td>X</td><td>1</td></tr>
  <tr><td>11</td><td>Granada<br>(1)<br>-<br>Deportivo<br>(2)</td><td>1<br>-<br>3</td><td>2</td><td>X</td></tr>
  <tr><td>12</td><td>Cádiz<br>(1)<br>-<br>Mirandés<br>(2)</td><td>1<br>-<br>0</td><td>1</td><td>X</td></tr>
  <tr><td>13</td><td>Huesca<br>(1)<br>-<br>Leganés<br>(2)</td><td>1<br>-<br>1</td><td>X</td><td>1</td></tr>
  <tr><td>14</td><td>Las Palmas<br>(1)<br>-<br>Andorra<br>(2)</td><td>1<br>-<br>1</td><td>X</td><td>1</td></tr>
  <tr><td>15</td><td>Elche<br>(1)<br>-<br>Betis<br>(2)</td><td>1<br>-<br>1</td><td>1-1</td><td>2-M</td></tr>
</table>
</body></html>
"""


def test_parse_result_table_extracts_15_matches_and_pleno():
    matches = parse_result_table(SAMPLE_HTML)

    assert len(matches) == 15
    assert matches[0].num == 1
    assert matches[0].local == "Girona"
    assert matches[0].visitante == "Rayo"
    assert matches[0].resultado == "1-3"
    assert matches[0].signo == "2"
    assert matches[14].tipo == "pleno15"
    assert matches[14].signo == "1-1"


def test_parse_result_table_accepts_sorteo_without_score():
    html = SAMPLE_HTML.replace(
        "<tr><td>8</td><td>Espanyol<br>(1)<br>-<br>At. Madrid<br>(2)</td><td>2<br>-<br>1</td><td>1</td><td>2</td></tr>",
        "<tr><td>8</td><td>Valencia<br>(1)<br>-<br>Real Oviedo<br>(2)</td><td>-<br>*<br>** sorteado</td><td>1** sorteado</td><td>1</td></tr>",
    )

    matches = parse_result_table(html)

    assert len(matches) == 15
    assert matches[7].num == 8
    assert matches[7].local == "Valencia"
    assert matches[7].resultado is None
    assert matches[7].signo == "1"
    assert matches[7].tipo == "sorteo"


def test_build_payload_is_compatible_with_lae_backtest_schema():
    matches = parse_result_table(SAMPLE_HTML)
    payload = build_payload(1, matches, "2025-2026", "https://example.com/resultados/1")

    assert payload["id"] == "Q15_2025_2026_J001"
    assert payload["temporada"] == "2025-2026"
    assert len(payload["partidos"]) == 15
    assert payload["partidos"][14]["tipo"] == "pleno15"


def test_aliases_observados_en_fuente_web_jornada_1():
    assert resolve_history_name("Athletic") == "Ath Bilbao"
    assert resolve_history_name("R. Sociedad") == "Sociedad"
    assert resolve_history_name("R. Santander") == "Santander"
    assert resolve_history_name("R. Valladolid") == "Valladolid"
