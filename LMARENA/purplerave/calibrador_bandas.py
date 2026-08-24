#!/usr/bin/env python3
"""CALIBRADOR DE BANDAS + AJUSTES CONTEXTUALES para PROGRAMAQUINIELA.
Módulo drop-in (solo stdlib) derivado de la auditoría REVISION_15.

Uso directo (auditoría + validación walk-forward):
    python calibrador_bandas.py /ruta/a/historico_raw

Uso como librería en el motor:
    from calibrador_bandas import estimar_factores, calibrar_probabilidades

Hallazgos base (13.448 partidos, 2010-26):
  - Descalibración por bandas dependiente de régimen: visitante con cuota
    2.5-4.0 sobrevalorado (factor reciente ~0.91, histórico ~0.97).
  - Local con cuota 1.4-1.8 ligeramente infravalorado (reciente ~1.07).
  - Favoritos en jornadas entre semana rinden +4pp ROI vs cierre en ambas eras.
"""
import csv, glob, math, os, sys
from datetime import date

# ---------------- carga ----------------

def ff(v):
    try: return float(v)
    except (TypeError, ValueError): return None

def cargar_historico(base):
    """Lee PRIMERA/SP1_*.csv y SEGUNDA/SP2_*.csv con cuotas de cierre."""
    partidos = []
    for carpeta, pref in (('PRIMERA', 'SP1'), ('SEGUNDA', 'SP2')):
        for ruta in sorted(glob.glob(os.path.join(base, carpeta, f'{pref}_*.csv'))):
            season = os.path.basename(ruta)[4:8]
            filas = []
            with open(ruta) as f:
                for row in csv.DictReader(f):
                    if row.get('FTR') not in ('H', 'D', 'A'): continue
                    o = (ff(row.get('PSCH')), ff(row.get('PSCD')), ff(row.get('PSCA')))
                    if not all(o):
                        o = (ff(row.get('B365CH')), ff(row.get('B365CD')), ff(row.get('B365CA')))
                    if not all(o):
                        o = (ff(row.get('B365H')), ff(row.get('B365D')), ff(row.get('B365A')))
                    if not all(o): continue
                    d, m, a = map(int, row['Date'].split('/'))
                    filas.append(dict(season=season, anio=a, fecha=date(a, m, d),
                                      res=row['FTR'], odds=tuple(o)))
            filas.sort(key=lambda p: p['fecha'])
            partidos += filas
    return partidos

def devig(odds):
    inv = [1 / o for o in odds]
    s = sum(inv)
    return [x / s for x in inv]

# ---------------- estimación de factores ----------------

CAP = 0.10  # corrección máxima por banda (±10% multiplicativo)

def _ratio(sub, idx, lo, hi):
    sel = [p for p in sub if lo <= p['odds'][idx] < hi]
    if len(sel) < 200: return 1.0
    real = sum(1 for p in sel if p['res'] == ('H', 'D', 'A')[idx]) / len(sel)
    impl = sum(devig(p['odds'])[idx] for p in sel) / len(sel)
    r = real / impl if impl > 0 else 1.0
    return max(1 - CAP, min(1 + CAP, r))

def estimar_factores(partidos, hasta_temporada=None, ventana=None):
    """Factores multiplicativos por banda con ventana rodante opcional.
    ventana=None -> todo el histórico disponible antes de hasta_temporada.
    ventana=N    -> últimas N temporadas disponibles."""
    sub = partidos
    if hasta_temporada:
        sub = [p for p in sub if p['season'] < hasta_temporada]
    if ventana:
        seasons = sorted({p['season'] for p in sub})[-ventana:]
        sub = [p for p in sub if p['season'] in set(seasons)]
    return {
        'visita_2.5_4.0': _ratio(sub, 2, 2.5, 4.0),
        'local_1.4_1.8': _ratio(sub, 0, 1.4, 1.8),
        'entre_semana_favorito_boost': 0.02,  # ~+4pp ROI en ambas eras -> boost conservador
        'n_muestras': len(sub),
    }

# ---------------- aplicación ----------------

def calibrar_probabilidades(probs, odds, factores, entre_semana=False):
    """probs: [pH, pD, pA] del mercado (de-vig o del ensemble); devuelve ajustadas."""
    q = list(probs)
    if 2.5 <= odds[2] < 4.0:
        q[2] *= factores['visita_2.5_4.0']
    if 1.4 <= odds[0] < 1.8:
        q[0] *= factores['local_1.4_1.8']
    if entre_semana:
        i = q.index(max(q))
        if i != 1:  # solo si el favorito no es el empate
            q[i] *= 1 + factores['entre_semana_favorito_boost']
    s = sum(q)
    return [x / s for x in q]

# ---------------- evaluación walk-forward ----------------

def evaluar(sub, clave):
    brier = sum(sum((qq - (1 if k == ('H', 'D', 'A').index(p['res']) else 0)) ** 2
                    for k, qq in enumerate(p[clave])) for p in sub) / len(sub)
    acc = sum(1 for p in sub if ('H', 'D', 'A')[p[clave].index(max(p[clave]))] == p['res']) / len(sub) * 100
    return brier, acc

def walk_forward(partidos):
    seasons = sorted({p['season'] for p in partidos})
    print(f"{'temp':>6} {'Brier mkt':>10} {'Brier cal':>10} {'acc mkt':>8} {'acc cal':>8} {'factores':>30}")
    for s in seasons:
        if s <= '1213': continue  # necesita >=2 temporadas previas
        train = [p for p in partidos if p['season'] < s]
        test = [p for p in partidos if p['season'] == s]
        f = estimar_factores(train, ventana=6)
        for p in test:
            probs = devig(p['odds'])
            p['cal'] = calibrar_probabilidades(probs, p['odds'], f, p['fecha'].weekday() in (1, 2, 3))
            p['mkt'] = probs
        bm, am = evaluar(test, 'mkt')
        bc, ac = evaluar(test, 'cal')
        print(f"{s:>6} {bm:>10.4f} {bc:>10.4f} {am:>7.2f}% {ac:>7.2f}%  "
              f"v2540={f['visita_2.5_4.0']:.3f} h1418={f['local_1.4_1.8']:.3f}")

if __name__ == '__main__':
    base = sys.argv[1] if len(sys.argv) > 1 else '.'
    walk_forward(cargar_historico(base))
