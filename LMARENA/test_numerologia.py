#!/usr/bin/env python3
"""Test real: ¿predice el 'camino de vida' (fecha de fundación) los partidos de LaLiga 2024-25?

Reglas numerológicas testadas:
  R1 'Afinidad': si solo un equipo es afín al número del día, gana ese; si no, empate.
  R2 'Igualdad': si solo un equipo tiene camino de vida IGUAL al número del día, gana ese; si no, empate.
Baselines: siempre-local, azar (distribución real), favorito de Bet365.
"""
import csv, random
from collections import Counter

def reducir(n):
    while n > 9:
        n = sum(int(d) for d in str(n))
    return n

def num_fecha(d, m, a):
    return reducir(d + m + reducir(sum(int(x) for x in str(a))))

FUNDACION = {  # fecha oficial reconocida por cada club (día, mes, año)
    'Alaves': (23, 1, 1921), 'Ath Bilbao': (18, 7, 1898), 'Ath Madrid': (26, 4, 1903),
    'Barcelona': (29, 11, 1899), 'Betis': (12, 9, 1907), 'Celta': (28, 8, 1923),
    'Espanol': (28, 10, 1900), 'Getafe': (26, 4, 1946), 'Girona': (30, 7, 1930),
    'Las Palmas': (22, 8, 1949), 'Leganes': (26, 6, 1928), 'Mallorca': (5, 3, 1916),
    'Osasuna': (24, 10, 1920), 'Real Madrid': (6, 3, 1902), 'Sevilla': (25, 1, 1890),
    'Sociedad': (7, 9, 1909), 'Valencia': (18, 3, 1919), 'Valladolid': (20, 6, 1928),
    'Vallecano': (29, 5, 1924), 'Villarreal': (10, 3, 1923),
}
AMIGOS = {
    1: {1, 2, 3, 9}, 2: {1, 3, 5, 7}, 3: {1, 2, 3, 5, 6, 9},
    4: {4, 5, 6, 7}, 5: {1, 3, 5, 6}, 6: {3, 4, 5, 6, 9},
    7: {2, 5, 6, 7}, 8: {4, 5, 7, 8}, 9: {1, 2, 3, 9},
}

partidos = []
with open('sp1_2425.csv') as f:
    for row in csv.DictReader(f):
        if row.get('FTR') not in ('H', 'D', 'A') or not row.get('B365H'):
            continue
        d, m, a = map(int, row['Date'].split('/'))
        partidos.append(dict(
            dia=num_fecha(d, m, a), local=row['HomeTeam'], visita=row['AwayTeam'],
            res=row['FTR'], odds=(float(row['B365H']), float(row['B365D']), float(row['B365A']))))

vida = {eq: num_fecha(*f) for eq, f in FUNDACION.items()}
print("Camino de vida de cada club:")
for eq in sorted(vida, key=vida.get):
    print(f"  {vida[eq]}: {', '.join(e for e in vida if vida[e]==vida[eq])}")

def evaluar(regla):
    aciertos = Counter()
    for p in partidos:
        aciertos[regla(p) == p['res']] += 1
    return aciertos[True] / len(partidos) * 100

def r_afinidad(p):
    af_l = p['dia'] == vida[p['local']] or p['dia'] in AMIGOS[vida[p['local']]]
    af_v = p['dia'] == vida[p['visita']] or p['dia'] in AMIGOS[vida[p['visita']]]
    if af_l and not af_v: return 'H'
    if af_v and not af_l: return 'A'
    return 'D'

def r_igualdad(p):
    eq_l = p['dia'] == vida[p['local']]
    eq_v = p['dia'] == vida[p['visita']]
    if eq_l and not eq_v: return 'H'
    if eq_v and not eq_l: return 'A'
    return 'D'

dist = Counter(p['res'] for p in partidos)
azar_esperado = sum((c/len(partidos))**2 for c in dist.values()) * 100  # prob. acertar eligiendo al azar según la distribución

random.seed(42)
azar_sim = sum((random.choice(list(dist.elements())) == p['res']) for p in partidos) / len(partidos) * 100
favorito = sum((('H','D','A')[p['odds'].index(min(p['odds']))] == p['res']) for p in partidos) / len(partidos) * 100

print(f"\n=== LaLiga 2024-25: {len(partidos)} partidos ===")
print(f"Distribución real: local {dist['H']/3.8:.0f}% | empate {dist['D']/3.8:.0f}% | visita {dist['A']/3.8:.0f}%")
print(f"\n  Baseline azar (simulado)          : {azar_sim:.1f}%")
print(f"  Baseline siempre-local            : {dist['H']/len(partidos)*100:.1f}%")
print(f"  Baseline favorito de Bet365       : {favorito:.1f}%")
print(f"  ---")
print(f"  R1 Numerología 'afinidad'         : {evaluar(r_afinidad):.1f}%")
print(f"  R2 Numerología 'igualdad estricta': {evaluar(r_igualdad):.1f}%")
