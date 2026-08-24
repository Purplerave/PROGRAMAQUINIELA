#!/usr/bin/env python3
"""Segunda pasada de la auditoría:
1) Fix ascendidos (cálculo de temporada anterior).
2) Validación por eras de F2/F4/F6.
3) Calibración POR BANDAS en walk-forward (la descalibración real del mercado).
"""
import csv, glob, math
from collections import defaultdict
from datetime import date

def ff(v):
    try: return float(v)
    except (TypeError, ValueError): return None

partidos = []
por_temporada_equipos = defaultdict(set)
for ruta in sorted(glob.glob('SP[12]_*.csv')):
    liga = 'P' if ruta.startswith('SP1') else 'S'
    season = ruta[4:8]
    filas = []
    with open(ruta) as f:
        for row in csv.DictReader(f):
            if row.get('FTR') not in ('H','D','A'): continue
            oh, od, oa = ff(row.get('PSCH')), ff(row.get('PSCD')), ff(row.get('PSCA'))
            if not (oh and od and oa):
                oh, od, oa = ff(row.get('B365CH')), ff(row.get('B365CD')), ff(row.get('B365CA'))
            if not (oh and od and oa):
                oh, od, oa = ff(row.get('B365H')), ff(row.get('B365D')), ff(row.get('B365A'))
            if not (oh and od and oa): continue
            b365 = (ff(row.get('B365H')), ff(row.get('B365D')), ff(row.get('B365A')))
            b365c = (ff(row.get('B365CH')), ff(row.get('B365CD')), ff(row.get('B365CA')))
            d, m, a = map(int, row['Date'].split('/'))
            filas.append(dict(liga=liga, season=season, anio=a, fecha=date(a,m,d),
                local=row['HomeTeam'], visita=row['AwayTeam'], res=row['FTR'],
                odds=(oh,od,oa), b365=b365, b365c=b365c, gl=int(row['FTHG']), gv=int(row['FTAG'])))
            por_temporada_equipos[(liga, season)].add(row['HomeTeam'])
            por_temporada_equipos[(liga, season)].add(row['AwayTeam'])
    filas.sort(key=lambda p: p['fecha'])
    partidos += filas

def devig(o):
    inv = [1/x for x in o]; s = sum(inv)
    return [x/s for x in inv]
for p in partidos: p['prob'] = devig(p['odds'])

def temporada_prev(s):
    return f"{int(s[:2])-1:02d}{int(s[2:])-1:02d}"

ascensos = {}
for (liga, season), equipos in por_temporada_equipos.items():
    prev = por_temporada_equipos.get((liga, temporada_prev(season)))
    ascensos[(liga, season)] = equipos - prev if prev else set()

pts, jugados, hist_fecha = {}, {}, defaultdict(list)
for p in partidos:
    kl = (p['liga'], p['season'], p['local']); kv = (p['liga'], p['season'], p['visita'])
    p['ascenso_l'] = p['local'] in ascensos[(p['liga'], p['season'])]
    p['jugados_l'] = jugados.get(kl, 0); p['puntos_l'] = pts.get(kl, 0)
    hist_fecha[kl].append(p['fecha']); hist_fecha[kv].append(p['fecha'])
    hl = 3 if p['res']=='H' else 0 if p['res']=='A' else 1
    pts[kl] = pts.get(kl,0)+hl; pts[kv] = pts.get(kv,0)+(3-hl if p['res']!='D' else 1)
    jugados[kl] = jugados.get(kl,0)+1; jugados[kv] = jugados.get(kv,0)+1

def roi_linea(nombre, apuestas):
    apuestas = [a for a in apuestas if a]
    if len(apuestas) < 40: print(f"{nombre}: n={len(apuestas)} insuficiente"); return
    n = len(apuestas)
    roi = sum((c-1 if ok else -1) for c, ok, _ in apuestas)/n*100
    ac = sum(ok for _, ok, _ in apuestas)/n*100
    im = sum(i for _, _, i in apuestas)/n*100
    print(f"{nombre:<52} n={n:>5} acierto {ac:5.1f}% implíc {im:5.1f}% ROI {roi:+6.1f}%")

print("=== RE-VALIDACIÓN POR ERAS ===")
F2, F3, F4, F6 = [], [], [], []
for p in partidos:
    oh, od, oa = p['odds']; fav_i = (oh,od,oa).index(min(oh,od,oa)); fav = ('H','D','A')[fav_i]
    im = p['prob'][fav_i]
    if p['fecha'].weekday() in (1,2,3) and fav in ('H','A'):
        F2.append((p['anio'], (min(oh,od,oa), fav == p['res'], im)))
    if p['ascenso_l'] and p['jugados_l'] < 12 and 1.8 <= oh <= 3.5:
        F3.append((p['anio'], (oh, p['res']=='H', p['prob'][0])))
    tot = 38 if p['liga']=='P' else 42
    if p['jugados_l'] >= tot-8:
        coc_l = p['puntos_l']/max(p['jugados_l'],1)
        coc_v = pts.get((p['liga'], p['season'], p['visita']),0)/max(jugados.get((p['liga'], p['season'], p['visita']),1),1)
        if coc_l < 1.05 and 1.25 < coc_v < 1.65 and oh <= 3.0:
            F4.append((p['anio'], (oh, p['res']=='H', p['prob'][0])))
    if p['b365'][0] and p['b365c'][0] and p['b365'][0] - p['b365c'][0] >= 0.15:
        F6.append((p['anio'], (p['b365c'][0], p['res']=='H', devig(p['b365c'])[0])))

for nombre, data in (('F2 favorito entre semana', F2), ('F3 ascendido en casa', F3),
                     ('F4 hundido en casa últimas 8j', F4), ('F6 steam B365→B365', F6)):
    print(f"\n{nombre}:")
    for et, cond in (('2010-19', lambda a: a < 2019), ('2019-26', lambda a: a >= 2019)):
        roi_linea(f"  {et}", [x for a, x in data if cond(a)])

print("\n=== CALIBRACIÓN POR BANDAS (walk-forward) ===")
train = [p for p in partidos if p['anio'] < 2019]
test  = [p for p in partidos if p['anio'] >= 2019]

def stats_bandas(sub, nombre):
    """Ratio real/implícito para estimar factores de banda en train."""
    sel_a = [p for p in sub if 2.5 <= p['odds'][2] < 4.0]
    sel_h = [p for p in sub if 1.4 <= p['odds'][0] < 1.8]
    ra = (sum(1 for p in sel_a if p['res']=='A')/len(sel_a)) / (sum(p['prob'][2] for p in sel_a)/len(sel_a)) if sel_a else 1
    rh = (sum(1 for p in sel_h if p['res']=='H')/len(sel_h)) / (sum(p['prob'][0] for p in sel_h)/len(sel_h)) if sel_h else 1
    print(f"{nombre}: factor visita[2.5-4)={ra:.3f} (n={len(sel_a)}), factor local[1.4-1.8)={rh:.3f} (n={len(sel_h)})")
    return ra, rh

ra, rh = stats_bandas(train, "TRAIN (<2019)")
stats_bandas(test, "TEST (>=2019, solo informativo)")

def aplicar_bandas(probs, odds, ra, rh):
    q = list(probs)
    if 2.5 <= odds[2] < 4.0: q[2] *= ra
    if 1.4 <= odds[0] < 1.8: q[0] *= rh
    s = sum(q); return [x/s for x in q]

def evaluar(sub, clave):
    b = sum(sum((qq - (1 if k == ('H','D','A').index(p['res']) else 0))**2 for k, qq in enumerate(p[clave])) for p in sub)/len(sub)
    ll = sum(-math.log(max(p[clave][('H','D','A').index(p['res'])], 1e-9)) for p in sub)/len(sub)
    acc = sum(1 for p in sub if ('H','D','A')[p[clave].index(max(p[clave]))] == p['res'])/len(sub)*100
    return b, ll, acc

for fracc, nombre in ((1.0, 'bandas full train'), (0.5, 'bandas 50% conservador')):
    ra_c = 1 + (ra-1)*fracc; rh_c = 1 + (rh-1)*fracc
    for p in test: p['cal'] = aplicar_bandas(p['prob'], p['odds'], ra_c, rh_c)
    bm, lm, am = evaluar(test, 'prob'); bc, lc, ac = evaluar(test, 'cal')
    print(f"\nTEST 2019-26 [{nombre}] ({ra_c:.3f}/{rh_c:.3f}):")
    print(f"  mercado  : Brier {bm:.4f} LL {lm:.4f} acc {am:.2f}%")
    print(f"  calibrado: Brier {bc:.4f} LL {lc:.4f} acc {ac:.2f}%")
