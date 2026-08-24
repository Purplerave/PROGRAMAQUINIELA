#!/usr/bin/env python3
"""Validación dividida de las señales encontradas en el estudio de patrones."""
import csv, glob
from collections import defaultdict

def ff(v):
    try: return float(v)
    except (TypeError, ValueError): return None

partidos = []
for ruta in sorted(glob.glob('sp[12]_*.csv')):
    with open(ruta) as f:
        for row in csv.DictReader(f):
            if row.get('FTR') not in ('H','D','A'): continue
            oh, od, oa = ff(row.get('PSCH')), ff(row.get('PSCD')), ff(row.get('PSCA'))
            if not (oh and od and oa):
                oh, od, oa = ff(row.get('B365CH')), ff(row.get('B365CD')), ff(row.get('B365CA'))
            if not (oh and od and oa):
                oh, od, oa = ff(row.get('B365H')), ff(row.get('B365D')), ff(row.get('B365A'))
            if not (oh and od and oa): continue
            partidos.append((ruta, row['FTR'], (oh, od, oa)))

DESC = {'sp1_2021.csv','sp1_2122.csv','sp1_2223.csv','sp2_2021.csv','sp2_2122.csv','sp2_2223.csv'}

def bloque(nombre, filtro, idx):
    print(f'--- {nombre} ---')
    for split in ('desc', 'val'):
        sel = [(r, res, odds) for r, res, odds in partidos
               if (r in DESC) == (split == 'desc') and filtro(odds[idx])]
        if not sel:
            print(f'  {split}: sin apuestas'); continue
        n = len(sel)
        ac = sum(1 for r, res, odds in sel if res == ('H','D','A')[idx])
        roi = sum((odds[idx]-1 if res == ('H','D','A')[idx] else -1) for r, res, odds in sel) / n * 100
        print(f'  {split}: n={n:>4}, acierto {ac/n*100:.1f}%, ROI {roi:+.1f}%')
    por_temp = defaultdict(lambda: [0, 0.0])
    for r, res, odds in partidos:
        if filtro(odds[idx]):
            t = por_temp[r]
            t[0] += 1
            t[1] += odds[idx]-1 if res == ('H','D','A')[idx] else -1
    detalle = ' '.join(f'{r[4:8]}:{v[1]/v[0]*100:+.0f}%(n={v[0]})' for r, v in sorted(por_temp.items()))
    print(f'  por temporada: {detalle}\n')

bloque('VISITANTE cuota 1.8-2.5 (la señal)', lambda c: 1.8 <= c < 2.5, 2)
bloque('LOCAL cuota 1.4-1.8', lambda c: 1.4 <= c < 1.8, 0)
