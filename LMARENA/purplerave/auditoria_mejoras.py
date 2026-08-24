#!/usr/bin/env python3
"""AUDITORÍA MASIVA de mejora para PROGRAMAQUINIELA.
Dataset: histórico propio 2010-11 → 2025-26 (Primera + Segunda, ~13.4k partidos).

Parte A: calibración del mercado (diagramas de fiabilidad H/D/A por eras).
Parte B: calibración entrenada en 2010-19, validada 2019-22, testeada 2022-26.
Parte C: candidatos de features contextuales pre-registrados.
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
            kohn, kod, koa = ff(row.get('B365H')), ff(row.get('B365D')), ff(row.get('B365A'))
            d, m, a = map(int, row['Date'].split('/'))
            filas.append(dict(liga=liga, season=season, anio=a, fecha=date(a,m,d),
                local=row['HomeTeam'], visita=row['AwayTeam'], res=row['FTR'],
                odds=(oh,od,oa), ap=(kohn,kod,koa),
                gl=int(row['FTHG']), gv=int(row['FTAG'])))
            por_temporada_equipos[(liga, season)].add(row['HomeTeam'])
            por_temporada_equipos[(liga, season)].add(row['AwayTeam'])
    filas.sort(key=lambda p: p['fecha'])
    partidos += filas

def devig(odds):
    inv = [1/o for o in odds]
    s = sum(inv)
    return [x/s for x in inv]
for p in partidos:
    p['prob'] = devig(p['odds'])

def temporada_num(p):  # año de inicio de temporada
    return int(p['season'][:2]) * 100 + int(p['season'][2:]) if False else (2000 + int(p['season'][:2]) if p['season'][2:] != '10' else 2010) if False else int('20' + p['season'][:2])

# ---------- Parte A: fiabilidad del mercado por eras ----------
print("="*70)
print("PARTE A · FIABILIDAD DEL MERCADO (prob implícita vs frecuencia real)")
print("="*70)
ERAS = [('2010-16', lambda t: t < 2016), ('2016-20', lambda t: 2016 <= t < 2020),
        ('2020-26', lambda t: t >= 2020)]
for etiqueta, cond in ERAS:
    print(f"\n[{etiqueta}]")
    print(f"{'clase':<6}{'n':>7}{'implícita':>10}{'real':>8}{'Δ(pp)':>8}")
    for i, nombre in enumerate(('LOCAL','EMPATE','VISITA')):
        sub = [p for p in partidos if cond(p['anio'])]
        n = len(sub)
        im = sum(p['prob'][i] for p in sub)/n*100
        re = sum(1 for p in sub if p['res'] == ('H','D','A')[i])/n*100
        print(f"{nombre:<6}{n:>7}{im:>9.1f}%{re:>7.1f}%{re-im:>+7.1f}")

# ---------- Parte B: calibración walk-forward ----------
print("\n" + "="*70)
print("PARTE B · CALIBRACIÓN (entrena 2010-19, valida 2019-22, test 2022-26)")
print("="*70)

def brier(probs, res):
    i = ('H','D','A').index(res)
    return sum((q - (1 if k == i else 0))**2 for k, q in enumerate(probs))

def logloss(probs, res):
    i = ('H','D','A').index(res)
    return -math.log(max(probs[i], 1e-9))

def evaluar(sub, clave_probs):
    b = sum(brier(p[clave_probs], p['res']) for p in sub)/len(sub)
    ll = sum(logloss(p[clave_probs], p['res']) for p in sub)/len(sub)
    acc = sum(1 for p in sub if ('H','D','A')[p[clave_probs].index(max(p[clave_probs]))] == p['res'])/len(sub)*100
    return b, ll, acc

def aplicar_deltas(probs, deltas):
    adj = [max(probs[i] * deltas[i], 1e-4) for i in range(3)]
    s = sum(adj)
    return [x/s for x in adj]

def ajustar_deltas(sub):
    """Deltas multiplicativos por clase que igualan prob media a frecuencia real."""
    d = []
    for i in range(3):
        im = sum(p['prob'][i] for p in sub)/len(sub)
        re = sum(1 for p in sub if p['res'] == ('H','D','A')[i])/len(sub)
        d.append(re/im if im > 0 else 1.0)
    return d

train = [p for p in partidos if p['anio'] < 2019]
valid = [p for p in partidos if 2019 <= p['anio'] < 2022]
test  = [p for p in partidos if p['anio'] >= 2022]
deltas = ajustar_deltas(train)
print(f"Deltas ajustados en train (H,D,A): {[f'{d:.3f}' for d in deltas]}")
for nombre, sub in (('valid 19-22', valid), ('test 22-26', test)):
    for p in sub: p['cal'] = aplicar_deltas(p['prob'], deltas)
    bm, lm, am = evaluar(sub, 'prob')
    bc, lc, ac = evaluar(sub, 'cal')
    print(f"{nombre}: mercado Brier {bm:.4f} LL {lm:.4f} acc {am:.2f}% | "
          f"calibrado Brier {bc:.4f} LL {lc:.4f} acc {ac:.2f}%")

# ---------- Parte C: features contextuales ----------
print("\n" + "="*70)
print("PARTE C · CANDIDATOS CONTEXTUALES (pre-registrados)")
print("="*70)

def prob_imp(p, i): return p['prob'][i]

def resumen_roi(nombre, apuestas):
    """apuestas: lista de (cuota, acierto)."""
    if len(apuestas) < 40:
        print(f"{nombre}: n={len(apuestas)} (insuficiente)"); return
    n = len(apuestas)
    roi = sum((c-1 if ok else -1) for c, ok in apuestas)/n*100
    ac = sum(ok for _, ok in apuestas)/n*100
    print(f"{nombre:<58} n={n:>5} acierto {ac:5.1f}% ROI {roi:+6.1f}%")

# Preparar estado por temporada: fechas previas (descanso), puntos, ascensos
estado_previo = {}
ascensos = {}
for (liga, season), equipos in por_temporada_equipos.items():
    prev_key = (liga, f"{int(season)-1:04d}")
    prev = por_temporada_equipos.get(prev_key)
    ascensos[(liga, season)] = equipos - prev if prev else set()

hist_fecha = defaultdict(list)
pts = {}; jugados = {}; racha = {}
for p in partidos:  # partidos ya ordenados por temporada/fecha globalmente aprox
    key_l = (p['liga'], p['season'], p['local'])
    key_v = (p['liga'], p['season'], p['visita'])
    p['descanso_l'] = (p['fecha'] - hist_fecha[key_l][-1]).days if hist_fecha[key_l] else None
    p['descanso_v'] = (p['fecha'] - hist_fecha[key_v][-1]).days if hist_fecha[key_v] else None
    p['puntos_l'] = pts.get(key_l,0); p['puntos_v'] = pts.get(key_v,0)
    p['jugados_l'] = jugados.get(key_l,0); p['jugados_v'] = jugados.get(key_v,0)
    p['ascenso_l'] = p['local'] in ascensos[(p['liga'], p['season'])]
    p['ascenso_v'] = p['visita'] in ascensos[(p['liga'], p['season'])]
    hist_fecha[key_l].append(p['fecha']); hist_fecha[key_v].append(p['fecha'])
    hl, al = (3,0) if p['res']=='H' else (0,3) if p['res']=='A' else (1,1)
    pts[key_l] = pts.get(key_l,0)+hl; pts[key_v] = pts.get(key_v,0)+al
    jugados[key_l] = jugados.get(key_l,0)+1; jugados[key_v] = jugados.get(key_v,0)+1

C1, C2, C3, C4, C5, C6 = [], [], [], [], [], []
for p in partidos:
    oh, od, oa = p['odds']
    fav = ('H','D','A')[(oh,od,oa).index(min(oh,od,oa))]
    dia_sem = p['fecha'].weekday()
    # F1 descanso: local con >=2 días menos de descanso que el visita
    if p['descanso_l'] and p['descanso_v'] and p['descanso_v'] - p['descanso_l'] >= 2:
        C1.append((oh, p['res']=='H'))
    # F2 entre semana (mar-jue): favorito
    if dia_sem in (1,2,3) and fav in ('H','A'):
        C2.append(((oh,od,oa)[('H','D','A').index(fav)], fav == p['res']))
    # F3 recién ascendido en casa, primeras 12 jornadas, cuota 1.8-3.5
    if p['ascenso_l'] and p['jugados_l'] < 12 and 1.8 <= oh <= 3.5:
        C3.append((oh, p['res']=='H'))
    # F4 final de temporada: local en descenso luchando vs visitante tranquilo
    tot = 38 if p['liga']=='P' else 42
    if p['jugados_l'] >= tot-8 and p['jugados_v'] >= tot-8:
        coc_l = p['puntos_l']/max(p['jugados_l'],1); coc_v = p['puntos_v']/max(p['jugados_v'],1)
        if coc_l < 1.05 and 1.25 < coc_v < 1.65 and oh <= 3.0:
            C4.append((oh, p['res']=='H'))
    # F5 visitante con ventaja de descanso >=2 días siendo favorito
    if p['descanso_l'] and p['descanso_v'] and p['descanso_v'] - p['descanso_l'] >= 2 and fav=='A':
        C5.append((oa, p['res']=='A'))
    # F6 movimiento de mercado: apertura->cierre baja cuota local >=0.15
    if p['ap'][0] and p['ap'][0] - oh >= 0.15:
        C6.append((oh, p['res']=='H'))

resumen_roi("F1 Local con -2 días descanso vs rival", C1)
resumen_roi("F2 Favorito en jornada entre semana", C2)
resumen_roi("F3 Ascendido en casa, <12 jornadas, cuota 1.8-3.5", C3)
resumen_roi("F4 Descenso: local hundido en casa últimas 8j", C4)
resumen_roi("F5 Visitante favorito con +2 días descanso", C5)
resumen_roi("F6 Steam move: cierre baja cuota local >=0.15", C6)

# F7 ventaja de campo por era
print("\nVentaja de campo (victorias locales %) por era:")
for etiqueta, cond in ERAS:
    sub = [p for p in partidos if cond(p['anio'])]
    print(f"  {etiqueta}: {sum(1 for p in sub if p['res']=='H')/len(sub)*100:.1f}% locales "
          f"| {sum(1 for p in sub if p['res']=='D')/len(sub)*100:.1f}% empates")
