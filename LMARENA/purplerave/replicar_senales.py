#!/usr/bin/env python3
"""Replicación de las señales de bandas de cuota en el histórico de Purplerave
(Primera + Segunda, 2010-11 a 2025-26, ~13.400 partidos).
"""
import csv, glob
from collections import defaultdict

def ff(v):
    try: return float(v)
    except (TypeError, ValueError): return None

partidos = []
fuentes = defaultdict(int)
for ruta in sorted(glob.glob('SP[12]_*.csv')):
    with open(ruta) as f:
        for row in csv.DictReader(f):
            if row.get('FTR') not in ('H', 'D', 'A'): continue
            src = None
            oh, od, oa = ff(row.get('PSCH')), ff(row.get('PSCD')), ff(row.get('PSCA'))
            if oh and od and oa: src = 'cierre_pinnacle'
            else:
                oh, od, oa = ff(row.get('B365CH')), ff(row.get('B365CD')), ff(row.get('B365CA'))
                if oh and od and oa: src = 'cierre_b365'
                else:
                    oh, od, oa = ff(row.get('B365H')), ff(row.get('B365D')), ff(row.get('B365A'))
                    if oh and od and oa: src = 'apertura_b365'
            if not src: continue
            fuentes[src] += 1
            anio = 2000 + int(ruta[4:6])
            partidos.append(dict(temp=anio, src=src, res=row['FTR'], odds=(oh, od, oa)))

print(f"Partidos con cuotas: {len(partidos)}")
for k, v in fuentes.items(): print(f"  fuente {k}: {v}")

def prob_imp(odds, i):
    inv = [1/o for o in odds]
    return inv[i] / sum(inv)

def informe(nombre, filtro, idx, eras):
    print(f"\n--- {nombre} ---")
    print(f"{'Periodo':<12} {'n':>5} {'acierto':>8} {'implícita':>9} {'ROI':>7}")
    for etiqueta, cond in eras:
        sel = [p for p in partidos if cond(p['temp']) and filtro(p['odds'][idx])]
        if len(sel) < 30:
            print(f"{etiqueta:<12} {len(sel):>5}   (muestra insuficiente)"); continue
        n = len(sel)
        ac = sum(1 for p in sel if p['res'] == ('H','D','A')[idx]) / n * 100
        im = sum(prob_imp(p['odds'], idx) for p in sel) / n * 100
        roi = sum((p['odds'][idx]-1 if p['res'] == ('H','D','A')[idx] else -1) for p in sel) / n * 100
        print(f"{etiqueta:<12} {n:>5} {ac:>7.1f}% {im:>8.1f}% {roi:>+6.1f}%")

ERAS = [('2010-16', lambda t: t < 2016), ('2016-20', lambda t: 2016 <= t < 2020),
        ('2020-26', lambda t: t >= 2020), ('TOTAL', lambda t: True)]
informe('SEÑAL 1: VISITANTE cuota 1.8-2.5', lambda c: 1.8 <= c < 2.5, 2, ERAS)
informe('SEÑAL 2: LOCAL cuota 1.4-1.8', lambda c: 1.4 <= c < 1.8, 0, ERAS)
informe('CONTRASTE: VISITANTE cuota 2.5-4.0 (banda a evitar)', lambda c: 2.5 <= c < 4.0, 2, ERAS)
