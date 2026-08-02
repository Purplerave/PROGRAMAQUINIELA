
import json
import argparse
from pathlib import Path
from datetime import datetime

def generate_api_contract(jornada: int):
    # Rutas
    paquete_path = Path(f"SALIDAS/paquete_jornada_J{jornada}.json")
    if not paquete_path.exists():
        print(f"Error: No se encuentra el paquete de la jornada {jornada} en SALIDAS/")
        return
    
    with open(paquete_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    api_out = {
        "jornada": jornada,
        "fecha_generacion": data.get("fecha_generacion"),
        "modelo_version": data.get("modelo_info", {}).get("version", "unknown"),
        "partidos": [],
        "pleno15": None
    }
    
    # Procesar partidos 1-14
    for p in data.get("partidos", []):
        num = p.get("num")
        if num == 15:
            # Procesar Pleno 15
            mm = p.get("modelo_maestro", {})
            if mm.get("disponible"):
                sel = mm.get("seleccion", {})
                api_out["pleno15"] = {
                    "local": p.get("local"),
                    "visitante": p.get("visitante"),
                    "marcador": mm.get("marcador_predicho"),
                    "pronostico_local": sel.get("local"),
                    "pronostico_visitante": sel.get("visitante")
                }
            else:
                # Fallback a diagnostico Q15 si el modelo no está disponible
                diag = data.get("pleno15", {}).get("diagnostico_q15", {})
                api_out["pleno15"] = {
                    "local": p.get("local"),
                    "visitante": p.get("visitante"),
                    "marcador": diag.get("top_marcadores", [{}])[0].get("score") if diag.get("top_marcadores") else None,
                    "pronostico_local": "1", # Default fallback
                    "pronostico_visitante": "1"
                }
            continue
            
        rm = p.get("recomendacion_modelo", {})
        pm = p.get("probabilidades", {}).get("modelo") or {}
        
        match_out = {
            "numero": num,
            "local": p.get("local"),
            "visitante": p.get("visitante"),
            "probabilidades": {
                "1": pm.get("1", 0.333),
                "X": pm.get("X", 0.333),
                "2": pm.get("2", 0.333)
            },
            "signo_maestro": rm.get("signo_principal"),
            "apuesta": rm.get("apuesta_recomendada"),
            "tipo": rm.get("tipo_apuesta"),
            "confianza": rm.get("confianza_modelo")
        }
        api_out["partidos"].append(match_out)
        
    # Ordenar partidos por número
    api_out["partidos"].sort(key=lambda x: x["numero"])
    
    # Guardar salida
    out_path = Path(f"SALIDAS/api_maestros_J{jornada}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(api_out, f, ensure_ascii=False, indent=2)
    
    print(f"Contrato API generado: {out_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--jornada", "-j", type=int, required=True)
    args = parser.parse_args()
    generate_api_contract(args.jornada)
