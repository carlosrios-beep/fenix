"""Lectura y escritura atómica de archivos de estado JSON."""

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict


def read_json_state(path: Path | str) -> Dict[str, Any]:
    """
    Lee un archivo JSON devolviendo un diccionario vacío si el archivo no existe.
    Si el archivo existe pero contiene JSON inválido, propaga json.JSONDecodeError
    para no enmascarar corrupción de datos.
    """
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json_state(path: Path | str, data: Dict[str, Any]) -> None:
    """
    Escribe atómicamente un diccionario en formato JSON.
    Cierra explícitamente el descriptor de archivo antes del renombramiento
    y reintenta la operación para prevenir colisiones de bloqueo en Windows.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    temp_dir = p.parent
    temp_file = tempfile.NamedTemporaryFile(
        "w",
        dir=temp_dir,
        delete=False,
        encoding="utf-8",
    )
    temp_path = Path(temp_file.name)

    try:
        json.dump(data, temp_file, indent=2, ensure_ascii=False)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_file.close()

        for attempt in range(5):
            try:
                os.replace(temp_path, p)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.1)
    except Exception:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise


# Alias exigidos por las pruebas base de la cátedra
load = read_json_state
save = write_json_state