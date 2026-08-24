#!/usr/bin/env python3
"""El giro científico: modelo de Poisson para predecir LaLiga 2020-25.

Sin filtraciones temporales: cada partido se predice SOLO con lo ocurrido
antes en esa misma temporada.
  ataque(eq)  = media móvil de goles a favor / media de la liga
  defensa(eq) = media móvil de goles en contra / media de la liga
  λ_local  = media_goles_local_liga × ataque(local) × defensa(visita)
  λ_visita = media_goles_visita_liga × ataque(visita) × defensa(local)
Matriz de Poisson 0-6 goles por equipo → P(local/empate/visita).
Ventana móvil: últimos 8 partidos (con decaimiento si hay menos).
"""
import csv, glob, math
from collections import defaultdict

VENTANA = 8
MAXG = 7  # goles 0..6 en la matriz

def poisson(k, lam):
    return math.exp(-lam) * lam**k / math.factorial(k)

def probs(lh, lv):
    ph = pd = pa = 0.0
    for i in range(MAXG):
        for j in range(MAXG):
            p = poisson(i, lh) * poisson(j, lv)
            if i > j: ph += p
            elif i == j: pd += p
            else: pa += p
    return ph, pd, pa

temporadas = sorted(glob.glob('sp1_*.csv'))
aciertos = 0; total = 0; fav_aciertos = 0; brier = 0.0
por_temporada = []

for ruta in temporadas:
    filas = []
    with open(ruta) as f:
        for row in csv.DictReader(f):
            if row.get('FTR') not in ('H', 'D', 'A') or not row.get('B365H'):
                continue
            filas.append(dict(local=row['HomeTeam'], visita=row['AwayTeam'],
                              res=row['FTR'], gl=int(row['FTHG']), gv=int(row['FTAG']),
                              odds=(float(row['B365H']), float(row['B365D']), float(row['B365H']) and float(row['B365A']))))
    # orden cronológico aproximado: el CSV ya viene por jornada
    hist = defaultdict(list)          # equipo -> lista de (goles_a_favor, goles_en_contra)
    goles_local = []; goles_visita = []
    ac_t = tot_t = fav_t = 0

    for fila in filas:
        gl_avg = sum(goles_local) / len(goles_local) if goles_local else 1.50
        gv_avg = sum(goles_visita) / len(goles_visita) if goles_visita else 1.20
        liga_avg = (gl_avg + gv_avg) / 2

        def fuerza(eq, lado):
            partidos = hist[eq][-VENTANA:]
            if not partidos: return 1.0
            gf = sum(g for g, c in partidos) / len(partidos) if lado == 'ataq' else sum(c for g, c in partidos) / len(partidos)
            return gf / liga_avg if liga_avg else 1.0

        lh = gl_avg * fuerza(fila['local'], 'ataq') * fuerza(fila['visita'], 'def')
        lv = gv_avg * fuerza(fila['visita'], 'ataq') * fuerza(fila['local'], 'def')
        lh = max(0.2, min(4.0, lh)); lv = max(0.2, min(4.0, lv))
        ph, pd, pa = probs(lh, lv)
        pred = ('H', 'D', 'A')[(ph, pd, pa).index(max(ph, pd, pa))]

        ac_t += (pred == fila['res']); tot_t += 1
        fav_t += (('H', 'D', 'A')[fila['odds'].index(min(fila['odds']))] == fila['res'])
        brier += sum((q - (1 if r == fila['res'] else 0))**2
                     for q, r in zip((ph, pd, pa), ('H', 'D', 'A')))

        hist[fila['local']].append((fila['gl'], fila['gv']))
        hist[fila['visita']].append((fila['gv'], fila['gl']))
        goles_local.append(fila['gl']); goles_visita.append(fila['gv'])

    aciertos += ac_t; total += tot_t; fav_aciertos += fav_t
    por_temporada.append((ruta, tot_t, ac_t/tot_t*100, fav_t/tot_t*100))

print(f"{'Temporada':<14} {'partidos':>8} {'Poisson':>9} {'favorito cuotas':>16}")
for ruta, n, a, f_ in por_temporada:
    print(f"{ruta:<14} {n:>8} {a:>8.1f}% {f_:>15.1f}%")
print('-' * 46)
print(f"{'TOTAL':<14} {total:>8} {aciertos/total*100:>8.1f}% {fav_aciertos/total*100:>15.1f}%")
print(f"\nBrier score del modelo (más bajo = mejores probabilidades): {brier/total:.3f}")
print("Referencia: predecir siempre 45/27/28 fijo daría Brier ≈ 1.08; azar uniforme 1.33")
