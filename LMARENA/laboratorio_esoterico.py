#!/usr/bin/env python3
"""Laboratorio esotérico: biorritmos, fases de la luna y zodiaco occidental
puestos a prueba contra LaLiga 2020-21 a 2024-25 (1.900 partidos).

Todas las reglas se definen ANTES de mirar resultados.
"""
import csv, glob, math, random
from datetime import date
from collections import Counter

# ---------- Datos ----------
FUNDACION = {  # fecha oficial de fundación de cada club
    'Alaves':(23,1,1921), 'Almeria':(26,7,2001), 'Ath Bilbao':(18,7,1898),
    'Ath Madrid':(26,4,1903), 'Barcelona':(29,11,1899), 'Betis':(12,9,1907),
    'Cadiz':(10,9,1910), 'Celta':(28,8,1923), 'Eibar':(30,11,1940),
    'Elche':(28,8,1922), 'Espanol':(28,10,1900), 'Getafe':(26,4,1946),
    'Girona':(30,7,1930), 'Granada':(14,4,1931), 'Huesca':(29,3,1960),
    'Las Palmas':(22,8,1949), 'Leganes':(26,6,1928), 'Levante':(9,9,1909),
    'Mallorca':(5,3,1916), 'Osasuna':(24,10,1920), 'Real Madrid':(6,3,1902),
    'Sevilla':(25,1,1890), 'Sociedad':(7,9,1909), 'Valencia':(18,3,1919),
    'Vallecano':(29,5,1924), 'Valladolid':(20,6,1928), 'Villarreal':(10,3,1923),
}
fund = {eq: date(*f[::-1]) for eq, f in FUNDACION.items()}

partidos = []
for ruta in sorted(glob.glob('sp1_*.csv')):
    with open(ruta) as f:
        for row in csv.DictReader(f):
            if row.get('FTR') not in ('H','D','A') or not row.get('B365H'):
                continue
            d, m, a = map(int, row['Date'].split('/'))
            partidos.append(dict(fecha=date(a,m,d), local=row['HomeTeam'],
                visita=row['AwayTeam'], res=row['FTR'], golL=int(row['FTHG']),
                golV=int(row['FTAG']), odds=(float(row['B365H']), float(row['B365D']), float(row['B365A']))))

# ---------- Método 1: BIORRITMOS ----------
# Ciclos desde la fundación: físico 23d, emocional 28d, intelectual 33d.
def onda(fecha, club, periodo):
    t = (fecha - fund[club]).days
    return math.sin(2*math.pi*t/periodo)

def bio(fecha, club, modo):
    if modo == 'fisico':
        return onda(fecha, club, 23)
    return sum(onda(fecha, club, p) for p in (23, 28, 33))  # combinado

def regla_bio(modo):
    def r(p):
        return 'H' if bio(p['fecha'], p['local'], modo) > bio(p['fecha'], p['visita'], modo) else 'A'
    return r

# ---------- Método 2: FASES DE LA LUNA ----------
SINODICO = 29.53058867
LUNA_NUEVA_REF = date(2000, 1, 6)  # nueva el 06/01/2000 18:14 UTC

def fase(fecha):  # 0 = nueva, 0.5 = llena, 1 = nueva otra vez
    return ((fecha - LUNA_NUEVA_REF).days % SINODICO) / SINODICO

def regla_luna(p):  # creciente = casa 'crece', menguante = fuera
    return 'H' if fase(p['fecha']) < 0.5 else 'A'

def es_llena(f):  # ventana de ±1.5 días alrededor de la llena
    return abs(fase(f) - 0.5) < 0.05

# ---------- Método 3: ZODIACO OCCIDENTAL ----------
SIGNOS = [(20,1,'Acuario'),(19,2,'Piscis'),(21,3,'Aries'),(20,4,'Tauro'),(21,5,'Geminis'),
          (21,6,'Cancer'),(23,7,'Leo'),(23,8,'Virgo'),(23,9,'Libra'),(23,10,'Escorpio'),
          (22,11,'Sagitario'),(22,12,'Capricornio')]
ELEMENTO = {'Aries':'fuego','Leo':'fuego','Sagitario':'fuego','Tauro':'tierra','Virgo':'tierra',
            'Capricornio':'tierra','Geminis':'aire','Libra':'aire','Acuario':'aire',
            'Cancer':'agua','Escorpio':'agua','Piscis':'agua'}
COMPATIBLES = {'fuego':{'fuego','aire'}, 'aire':{'aire','fuego'},
               'tierra':{'tierra','agua'}, 'agua':{'agua','tierra'}}

def signo(dt):
    for d, m, s in reversed(SIGNOS):
        if (dt.month, dt.day) >= (m, d):
            return s
    return 'Capricornio'

def regla_zodiaco(p):
    el_dia = ELEMENTO[signo(p['fecha'])]
    af_l = ELEMENTO[signo(fund[p['local']])] in COMPATIBLES[el_dia]
    af_v = ELEMENTO[signo(fund[p['visita']])] in COMPATIBLES[el_dia]
    if af_l and not af_v: return 'H'
    if af_v and not af_l: return 'A'
    return None

# ---------- Motor de evaluación ----------
def evaluar(regla, nombre):
    picks, aciertos = [], []
    for p in partidos:
        r = regla(p)
        if r is None: continue
        picks.append(p); aciertos.append(r == p['res'])
    if not picks: 
        print(f"{nombre:<38} sin predicciones"); return
    n = len(picks); dist = Counter(x['res'] for x in picks)
    random.seed(42)
    azar = sum(random.choice(list(dist.elements())) == x['res'] for x in picks)/n*100
    local = dist['H']/n*100
    fav = sum(('H','D','A')[x['odds'].index(min(x['odds']))] == x['res'] for x in picks)/n*100
    acc = sum(aciertos)/n*100
    print(f"{nombre:<38} picks {n:>5} ({n/len(partidos)*100:>3.0f}%)  acierto {acc:5.1f}%  "
          f"[azar {azar:.1f} | local {local:.1f} | cuotas {fav:.1f}]")

print(f"=== LABORATORIO ESOTÉRICO · LaLiga 2020-25 · {len(partidos)} partidos ===\n")
evaluar(regla_bio('fisico'), "Biorritmos: ciclo físico (23 días)")
evaluar(regla_bio('combinado'), "Biorritmos: 3 ciclos combinados")
evaluar(regla_luna, "Luna: creciente=local, menguante=visita")
evaluar(regla_zodiaco, "Zodiaco: elemento afín al día")

# ---------- Folclore lunar ----------
llenas = [p for p in partidos if es_llena(p['fecha'])]
resto  = [p for p in partidos if not es_llena(p['fecha'])]
def stats(sub):
    d = Counter(x['res'] for x in sub); g = sum(x['golL']+x['golV'] for x in sub)/len(sub)
    fav_ok = sum(('H','D','A')[x['odds'].index(min(x['odds']))] == x['res'] for x in sub)
    return d['H']/len(sub)*100, d['D']/len(sub)*100, d['A']/len(sub)*100, g, fav_ok/len(sub)*100

hL,dL,aL,gL,fL = stats(llenas); hR,dR,aR,gR,fR = stats(resto)
print(f"\nFolclore lunar — ¿la luna llena trae caos? ({len(llenas)} partidos en luna llena)")
print(f"  Con llena : local {hL:.0f}% empate {dL:.0f}% visita {aL:.0f}% | goles/partido {gL:.2f} | favorito gana {fL:.0f}%")
print(f"  Sin llena : local {hR:.0f}% empate {dR:.0f}% visita {aR:.0f}% | goles/partido {gR:.2f} | favorito gana {fR:.0f}%")
