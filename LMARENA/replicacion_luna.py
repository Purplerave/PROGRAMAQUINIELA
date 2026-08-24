#!/usr/bin/env python3
"""Replicación pre-registrada del 'efecto luna llena' fuera de España.

Regla idéntica a la usada en LaLiga (definida antes de mirar estos datos):
  - Luna llena: |fase - 0.5| < 0.05 (ventana de ~±1.5 días).
  - Métrica principal: % de partidos donde gana el favorito (menor cuota B365).
  - Métricas secundarias: distribución H/D/A y goles por partido.
"""
import csv, glob
from datetime import date
from collections import Counter

SINODICO = 29.53058867
REF = date(2000, 1, 6)  # luna nueva de referencia
fase = lambda d: ((d - REF).days % SINODICO) / SINODICO
llena = lambda d: abs(fase(d) - 0.5) < 0.05

LIGAS = {'E0': 'Premier League', 'I1': 'Serie A', 'D1': 'Bundesliga', 'sp1': 'LaLiga (original)'}

def cargar(ruta):
    out = []
    with open(ruta) as f:
        for row in csv.DictReader(f):
            if row.get('FTR') not in ('H', 'D', 'A'): continue
            try:
                odds = tuple(float(row[c]) for c in ('B365H', 'B365D', 'B365A'))
            except (ValueError, KeyError):
                continue
            d, m, a = map(int, row['Date'].split('/'))
            out.append(dict(fecha=date(a, m, d), res=row['FTR'],
                            goles=int(row['FTHG']) + int(row['FTAG']), odds=odds))
    return out

def stats(sub):
    if not sub: return None
    d = Counter(x['res'] for x in sub)
    fav = sum(('H', 'D', 'A')[x['odds'].index(min(x['odds']))] == x['res'] for x in sub)
    return dict(n=len(sub), fav=fav/len(sub)*100, h=d['H']/len(sub)*100,
                e=d['D']/len(sub)*100, a=d['A']/len(sub)*100,
                goles=sum(x['goles'] for x in sub)/len(sub))

print(f"{'Liga':<20} {'Condición':<12} {'n':>5} {'favorito':>9} {'local':>7} {'empate':>7} {'visita':>7} {'goles':>6}")
print('-' * 80)

pool = {'llena': [], 'normal': []}
for prefijo, nombre in LIGAS.items():
    todos = []
    for ruta in sorted(glob.glob(f'{prefijo}_*.csv')):
        todos += cargar(ruta)
    ll = [p for p in todos if llena(p['fecha'])]
    no = [p for p in todos if not llena(p['fecha'])]
    pool['llena'] += ll; pool['normal'] += no
    for etiqueta, sub in (('luna llena', ll), ('sin llena', no)):
        s = stats(sub)
        print(f"{nombre:<20} {etiqueta:<12} {s['n']:>5} {s['fav']:>8.1f}% {s['h']:>6.1f}% "
              f"{s['e']:>6.1f}% {s['a']:>6.1f}% {s['goles']:>6.2f}")
    print()

print('=== TOTAL 4 LIGAS (replicación combinada) ===')
for etiqueta in ('llena', 'normal'):
    s = stats(pool[etiqueta])
    print(f"  {'Luna llena' if etiqueta=='llena' else 'Sin llena ':<12} n={s['n']:>5}  "
          f"favorito gana {s['fav']:.1f}%  | local {s['h']:.0f}% empate {s['e']:.0f}% visita {s['a']:.0f}%  | goles {s['goles']:.2f}")

import math
n = len(pool['llena']); p = stats(pool['llena'])['fav']/100
p0 = stats(pool['normal'])['fav']/100
se = math.sqrt(p0*(1-p0)/n)*100
print(f"\nDiferencia favorito: {p*100 - p0:.1f} puntos; margen de error con n={n}: ±{se:.1f} (1 sigma)")
