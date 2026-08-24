#!/usr/bin/env python3
"""Calculadora de numerología futbolera con variantes de nombre.

Muestra cómo cambia el número según el nombre usado:
nombre común vs. nombre oficial completo.
Sistema pitagórico: A=1 ... I=9, J=1 ... (ciclo de 9).
"""

def reducir(n: int) -> int:
    while n > 9:
        n = sum(int(d) for d in str(n))
    return n

def numero_nombre(nombre: str) -> tuple[int, int]:
    letras = [c for c in nombre.upper() if c.isalpha()]
    total = sum(((ord(c) - ord('A')) % 9) + 1 for c in letras)
    return total, reducir(total)

def numero_fecha(dia: int, mes: int, anio: int) -> int:
    return reducir(dia + mes + reducir(sum(int(d) for d in str(anio))))

AMIGOS = {
    1: {1, 2, 3, 9}, 2: {1, 3, 5, 7}, 3: {1, 2, 3, 5, 6, 9},
    4: {4, 5, 6, 7}, 5: {1, 3, 5, 6}, 6: {3, 4, 5, 6, 9},
    7: {2, 5, 6, 7}, 8: {4, 5, 7, 8}, 9: {1, 2, 3, 9},
}

def afinidad(num_equipo: int, num_dia: int) -> str:
    if num_equipo == num_dia:
        return "MUY AFÍN (mismo número)"
    return "afín" if num_dia in AMIGOS[num_equipo] else "neutro/en contra"

if __name__ == "__main__":
    # Cada equipo con sus variantes de nombre (común, oficial, con/sin "de"...)
    clubes = {
        "Barcelona": [
            "BARCELONA",
            "FC BARCELONA",
            "FUTBOL CLUB BARCELONA",
        ],
        "Deportivo": [
            "DEPORTIVO",
            "RC DEPORTIVO",
            "REAL CLUB DEPORTIVO",
            "REAL CLUB DEPORTIVO DE LA CORUNA",
        ],
        "Real Madrid": [
            "REAL MADRID",
            "REAL MADRID CF",
            "REAL MADRID CLUB DE FUTBOL",
        ],
    }

    fecha_partido = (24, 8, 2026)
    dia_num = numero_fecha(*fecha_partido)
    print(f"Número del día del partido {fecha_partido[0]:02d}/{fecha_partido[1]:02d}/{fecha_partido[2]}: {dia_num}\n")

    for club, variantes in clubes.items():
        print(f"=== {club} ===")
        for nombre in variantes:
            total, n = numero_nombre(nombre)
            print(f"  {nombre:<38} suma {total:>3} -> número {n}  ({afinidad(n, dia_num)} al día {dia_num})")
        print()
