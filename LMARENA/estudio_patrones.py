#!/usr/bin/env python3
"""Estudio de patrones para batir a las apuestas: LaLiga + Segunda 2020-25 (4.210 partidos).

Filosofía: no buscamos quién gana, buscamos VALUE: situaciones donde la
probabilidad real supera a la que pagan las cuotas de cierre (Pinnacle closing,
la referencia más afilada del mercado). División estricta:
  descubrimiento = temporadas 2020-21 a 2022-23
  validación     = temporadas 2023-24 y 2024-25
"""
import csv, glob
from collections import defaultdict

DESC = {'sp1_2021.csv','sp1_2122.csv','sp1_2223.csv','sp2_2021.csv','sp2_2122.csv','sp2_2223.csv'}

def ffloat(v):
    try: return float(v)
    except (TypeError, ValueError): return None

partidos = []
por_temporada_equipos = {}
for ruta in sorted(glob.glob('sp[12]_*.csv')):
    liga = 'LALIGA' if ruta.startswith('sp1') else 'SEGUNDA'
    fila_eq = set()
    with open(ruta) as f:
        for row in csv.DictReader(f):
            if row.get('FTR') not in ('H','D','A'): continue
            oh, od, oa = ffloat(row.get('PSCH')), ffloat(row.get('PSCD')), ffloat(row.get('PSCA'))
            fuente = 'pinnacle_cierre'
            if not (oh and od and oa):
                oh, od, oa = ffloat(row.get('B365CH')), ffloat(row.get('B365CD')), ffloat(row.get('B365CA'))
                fuente = 'b365_cierre'
            if not (oh and od and oa):
                oh, od, oa = ffloat(row.get('B365H')), ffloat(row.get('B365D')), ffloat(row.get('B365A'))
                fuente = 'b365_apertura'
            if not (oh and od and oa): continue
            over = ffloat(row.get('B365C>2.5')) or ffloat(row.get('B365>2.5'))
            under = ffloat(row.get('B365C<2.5')) or ffloat(row.get('B365<2.5'))
            d, m, a = map(int, row['Date'].split('/'))
            partidos.append(dict(archivo=ruta, liga=liga, desc=ruta in DESC, fecha=(a,m,d),
                local=row['HomeTeam'], visita=row['AwayTeam'], res=row['FTR'],
                gl=int(row['FTHG']), gv=int(row['FTAG']),
                odds=(oh, od, oa), over=over, under=under))
            fila_eq.add(row['HomeTeam']); fila_eq.add(row['AwayTeam'])
    por_temporada_equipos[ruta] = fila_eq

# ---- estado por temporada (forma, rachas, clasificación) en orden cronológico ----
ascendidos = {}
for ruta, equipos in por_temporada_equipos.items():
    liga, season = ruta[:3], ruta[4:8]
    clave_prev = f"{liga}_{int(season)-1:04d}.csv"
    prev = por_temporada_equipos.get(clave_prev)
    ascendidos[ruta] = equipos - prev if prev else set()

estado = {}  # (archivo, equipo) -> datos antes de cada partido
for ruta in sorted(por_temporada_equipos):
    hist = defaultdict(list)   # equipo -> puntos por partido
    pts = defaultdict(int); jugados = defaultdict(int)
    for p in [x for x in partidos if x['archivo'] == ruta]:
        for eq, es_local in ((p['local'], True), (p['visita'], False)):
            racha = 0
            for r in reversed(hist[eq]):
                if r == 3 and racha >= 0: racha += 1
                elif r == 0 and racha <= 0: racha -= 1
                else: break
            estado[(ruta, eq, p['fecha'])] = dict(
                forma=sum(hist[eq][-5:]) if hist[eq] else None,
                racha=racha, puntos=pts[eq], jugados=jugados[eq],
                ascenso=eq in ascendidos[ruta])
        # actualizar tras el partido
        hl, al = (3,0) if p['res']=='H' else (0,3) if p['res']=='A' else (1,1)
        hist[p['local']].append(hl); hist[p['visita']].append(al)
        pts[p['local']] += hl; pts[p['visita']] += al
        jugados[p['local']] += 1; jugados[p['visita']] += 1

# ---- hipótesis ----
def prob_imp(odds, i):
    inv = [1/o for o in odds]
    return inv[i]/sum(inv)

tests = defaultdict(lambda: {'desc': [], 'val': []})

for p in partidos:
    oh, od, oa = p['odds']
    fav_i = (oh, od, oa).index(min(oh, od, oa))
    clave_split = 'desc' if p['desc'] else 'val'

    def apostar(nombre, i):
        tests[nombre][clave_split].append((p['odds'][i], prob_imp(p['odds'], i), p['res'] == ('H','D','A')[i]))

    if min(oh, od, oa) <= 1.50: apostar('H1 Gran favorito (<=1.50)', fav_i)
    if max(oh, oa) >= 5.00: apostar('H2 Perdedor enorme (>=5.0)', 0 if oa >= 5 else 2)
    if 2.6 <= oh <= 4.5 and oa < 1.90: apostar('H3 Local infravalorado (2.6-4.5 vs fav)', 0)
    if p['liga'] == 'SEGUNDA' and od >= 3.2: apostar('H4 Empate en Segunda (cuota>=3.2)', 1)
    if p['liga'] == 'SEGUNDA' and p['under'] and p['over'] and p['over'] >= 1.95:
        tests['H5 Under 2.5 en Segunda (mercado mira al over)'][clave_split].append(
            (p['under'], 1/p['under']/ (1/p['over']+1/p['under']), p['gl']+p['gv'] < 2.5))
    for eq, es_local in ((p['local'], True), (p['visita'], False)):
        st = estado[(p['archivo'], eq, p['fecha'])]
        tot_jorn = 42 if p['liga']=='SEGUNDA' else 38
        if es_local and st['puntos'] <= 0.9*st['jugados'] and st['jugados'] >= tot_jorn-9 and oh <= 2.6:
            apostar('H6 Descenso: colgable en casa últimas 8j', 0)
        if not es_local and st['racha'] >= 4 and oa <= 2.2:
            apostar('H7 Pinchar la racha (visitante 4+ victorias, fav)', 0)

print(f"{'HIPÓTESIS':<48} | {'DESCUBRIMIENTO (20-23)':^38} | {'VALIDACIÓN (23-25)':^38}")
print(f"{'':48} | {'n':>5} {'aciert':>6} {'implíc':>6} {'ROI':>6} | {'n':>5} {'aciert':>6} {'implíc':>6} {'ROI':>6}")
print('-'*135)
for nombre in sorted(tests):
    linea = f"{nombre:<48} |"
    for split in ('desc','val'):
        apuestas = tests[nombre][split]
        n = len(apuestas)
        if n == 0: linea += f" {'—':>5} {'—':>6} {'—':>6} {'—':>6} |"; continue
        aciertos = sum(a[2] for a in apuestas)
        impl = sum(a[1] for a in apuestas)/n*100
        roi = sum(a[0]-1 if a[2] else -1 for a in apuestas)/n*100
        linea += f" {n:>5} {aciertos/n*100:>5.1f}% {impl:>5.1f}% {roi:>+5.1f}% |"
    print(linea)

# ---- tabla descriptiva favorite-longshot (todo el periodo) ----
print("\nSesgo favorito-perdedor (cuotas de cierre, todo el periodo):")
print(f"{'Banda de cuota':<16} {'n':>6} {'real':>7} {'implícita':>9} {'ROI':>7}")
bandas = [(1,1.4),(1.4,1.8),(1.8,2.5),(2.5,4),(4,100)]
for lo, hi in bandas:
    for i in (0,2):
        sel = [(p, i) for p in partidos if lo <= p['odds'][i] < hi]
        if len(sel) < 50: continue
        n = len(sel); real = sum(1 for p,i in sel if p['res']==('H','D','A')[i])/n*100
        impl = sum(prob_imp(p['odds'], i) for p,i in sel)/n*100
        roi = sum((p['odds'][i]-1 if p['res']==('H','D','A')[i] else -1) for p,i in sel)/n*100
        lado = 'local' if i==0 else 'visita'
        print(f"{lo}-{hi} {lado:<6} {n:>6} {real:>6.1f}% {impl:>8.1f}% {roi:>+6.1f}%")
