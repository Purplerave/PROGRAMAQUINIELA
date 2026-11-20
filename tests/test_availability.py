from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "motor"))
from availability import construir_disponibilidad

def test_construir_disponibilidad():
    df = construir_disponibilidad(Path(__file__).resolve().parents[1] / "salida" / "highlightly_2025_full.json")
    assert len(df) == 100
    assert "hl_home_starters" in df.columns
    assert "hl_match_id" in df.columns
