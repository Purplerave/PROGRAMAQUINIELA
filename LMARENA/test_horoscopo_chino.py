#!/usr/bin/env python3
"""Test: ¿predice el horóscopo chino los partidos de LaLiga (2020-21 a 2024-25)?

Regla (predefinida antes de ver resultados):
  Cada club tiene el animal de su AÑO de fundación. Cada partido tiene el
  animal del AÑO de la fecha. Puntuación: armonía con el año = +1,
  choque con el año = -1, neutro = 0. Se predice el equipo con más puntos;
  si empatan, el método "no se moja" (sin predicción).

Armonías tradicionales: parejas (六合) + trinos (三合).
Choques tradicionales (六冲): Rata-Caballo, Buey-Cabra, Tigre-Mono,
Conejo-Gallo, Dragón-Perro, Serpiente-Cerdo.
"""
import csv, glob, random
from collections import Counter

ANIMALES = ['Rata','Buey','Tigre','Conejo','Dragón','Serpiente',
            'Caballo','Cabra','Mono','Gallo','Perro','Cerdo']

def animal(anio: int) -> int:
    return (anio - 1900) % 12

HARMONIA = {
    0:{1,4,8}, 1:{0,5,9}, 2:{11,6,10}, 3:{10,7,11}, 4:{9,0,8}, 5:{8,1,9},
    6:{7,2,10}, 7:{6,3,11}, 8:{5,0,4}, 9:{4,1,5}, 10:{3,2,6}, 11:{2,3,7},
}
CHOQUE = {0:6, 6:0, 1:7, 7:1, 2:8, 8:2, 3:9, 9:3, 4:10, 10:4, 5:11, 11:5}

ANO_FUND = {  # año oficial de fundación de cada club que pasó por Primera 2020-25
    'Alaves':1921, 'Almeria':2001, 'Ath Bilbao':1898, 'Ath Madrid':1903,
    'Barcelona':1899, 'Betis':1907, 'Cadiz':1910, 'Celta':1923, 'Eibar':1940,
    'Elche':1922, 'Espanol':1900, 'Getafe':1946, 'Girona':1930, 'Granada':1931,
    'Huesca':1960, 'Las Palmas':1949, 'Leganes':1928, 'Levante':1909,
    'Mallorca':1916, 'Osasuna':1920, 'Real Madrid':1902, 'Sevilla':1890,
    'Sociedad':1909, 'Valencia':1919, 'Vallecano':1924, 'Valladolid':1928,
    'Villarreal':1923,
}
animal_club = {eq: animal(a) for eq, a in ANO_FUND.items()}

partidos = []
for ruta in sorted(glob.glob('sp1_*.csv')):
    with open(ruta) as f:
        for row in csv.DictReader(f):
            if row.get('FTR') not in ('H','D','A') or not row.get('B365H'):
                continue
            d, m, a = map(int, row['Date'].split('/'))
            partidos.append(dict(anio=a, local=row['HomeTeam'], visita=row['AwayTeam'],
                                 res=row['FTR'], odds=(float(row['B365H']), float(row['B365D']), float(row['B365A']))))

def puntuacion(animal_eq: int, animal_anio: int) -> int:
    if animal_eq in HARMONIA.get(animal_anio, set()): return +1
    if CHOQUE[animal_eq] == animal_anio: return -1
    return 0

picks, aciertos = [], []
for p in partidos:
    aa = animal(p['anio'])
    pl = puntuacion(animal_club[p['local']], aa)
    pv = puntuacion(animal_club[p['visita']], aa)
    if pl == pv:
        continue  # el método no se moja
    picks.append(p)
    aciertos.append(('H' if pl > pv else 'A') == p['res'])

subset_dist = Counter(p['res'] for p in picks)
n = len(picks)
random.seed(42)
azar_sim = sum(random.choice(list(subset_dist.elements())) == p['res'] for p in picks) / n * 100
siempre_local = subset_dist['H'] / n * 100
favorito = sum(('H','D','A')[p['odds'].index(min(p['odds']))] == p['res'] for p in picks) / n * 100
horoscopo = sum(aciertos) / n * 100

print("Animales de cada club (año de fundación):")
grupos = {}
for eq, a in sorted(animal_club.items(), key=lambda x: animal_club[x[0]]):
    grupos.setdefault(animal_club[eq], []).append(eq)
for a, eqs in sorted(grupos.items()):
    print(f"  {ANIMALES[a]:<8} {', '.join(eqs)}")

print(f"\n=== LaLiga 2020-21 a 2024-25: {len(partidos)} partidos totales ===")
print(f"Partidos donde el horóscopo 'se moja': {n} ({n/len(partidos)*100:.0f}%)")
print(f"Distribución en ese subconjunto: local {subset_dist['H']/n*100:.0f}% | empate {subset_dist['D']/n*100:.0f}% | visita {subset_dist['A']/n*100:.0f}%\n")
print(f"  Baseline azar (simulado, solo en partidos con pick): {azar_sim:.1f}%")
print(f"  Baseline siempre-local (idem)                       : {siempre_local:.1f}%")
print(f"  Baseline favorito de Bet365 (idem)                  : {favorito:.1f}%")
print(f"  ---")
print(f"  HORÓSCOPO CHINO                                     : {horoscopo:.1f}%")

print("\nPor temporada:")
for temporada in sorted({p['anio'] for p in picks}):
    idx = [i for i, p in enumerate(picks) if p['anio'] == temporada]
    acc = sum(aciertos[i] for i in idx) / len(idx) * 100
    print(f"  {temporada}: {len(idx):>3} picks, acierto {acc:.1f}%")
