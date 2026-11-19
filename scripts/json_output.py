"""Escritura atómica de contratos JSON en el sistema de archivos local."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as tmp:
        temp_path = Path(tmp.name)
        try:
            json.dump(payload, tmp, ensure_ascii=False, indent=2, allow_nan=False)
            tmp.write("\n")
            tmp.close()
            temp_path.replace(path)
        finally:
            # Cerrar antes de unlink, también cuando la serialización falla en Windows.
            tmp.close()
            temp_path.unlink(missing_ok=True)
