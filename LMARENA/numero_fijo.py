#!/usr/bin/env python3
"""Candidatos a 'número fijo' de un club: fechas que no cambian con el nombre.

Compara distintas "fechas de nacimiento" posibles para el mismo club
y calcula el número de camino de vida de cada una.
"""

def reducir(n: int) -> int:
    while n > 9:
        n = sum(int(d) for d in str(n))
    return n

def numero_fecha(dia: int, mes: int, anio: int) -> int:
    return reducir(dia + mes + reducir(sum(int(d) for d in str(anio))))

EVENTOS = {
    "DEPORTIVO": [
        ("Fundación (Club D. de la Sala Calvet)", 2, 3, 1906),
        ("Primer partido de su historia", 8, 12, 1906),
        ("Estatutos aprobados (registro oficial)", 11, 3, 1907),
        ("Concesión del título 'Real'", 7, 2, 1909),
        ("Adopta el nombre RCD La Coruña", 1, 1, 1912),
        ("Inauguración de Riazor", 28, 10, 1944),
        ("Conversión en S.A.D.", 30, 6, 1992),
    ],
    "REAL MADRID": [
        ("Primer partido registrado (Campo del Retiro)", 6, 10, 1901),
        ("Fundación oficial (Madrid Foot-ball Club)", 6, 3, 1902),
        ("Conversión en S.A.D.", None, None, None),  # no se convirtió: sigue siendo club de socios
        ("Inauguración del Bernabéu", 14, 12, 1947),
    ],
    "FC BARCELONA": [
        ("Fundación (Hans Gamper)", 29, 11, 1899),
        ("Inauguración del Camp Nou", 24, 9, 1957),
    ],
}

for club, eventos in EVENTOS.items():
    print(f"=== {club} ===")
    for nombre, d, m, a in eventos:
        if d is None:
            print(f"  {nombre:<45} -> no aplica")
            continue
        print(f"  {nombre:<45} {d:02d}/{m:02d}/{a} -> número {numero_fecha(d, m, a)}")
    print()
