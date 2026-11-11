"""Validadores de formato para identificadores, marcas de tiempo UTC y helpers."""

import re
from datetime import datetime, timezone
from fenix.utils.errors import ValidationError

ID_PATTERN = re.compile(r"^[a-z0-9-]{3,32}$")


def identifier(value: str) -> str:
    """Valida que un ID (event_id, resource_id) cumpla con el formato [a-z0-9-]{3,32}."""
    if not isinstance(value, str) or not ID_PATTERN.match(value):
        raise ValidationError(
            f"Identificador inválido '{value}'. Debe ser string de 3 a 32 caracteres [a-z0-9-]."
        )
    return value


def utc_text(value: str):
    """
    Valida y retorna un objeto datetime UTC explícito.
    Rechaza fechas sin zona horaria o con desfase distinto de UTC cero.
    """
    if not isinstance(value, str):
        raise ValidationError("La fecha debe ser un string en formato ISO 8601 UTC.")

    if not (value.endswith("Z") or value.endswith("+00:00")):
        raise ValidationError(f"La fecha '{value}' debe indicar explícitamente zona UTC ('Z' o '+00:00').")

    try:
        iso_str = value[:-1] + "+00:00" if value.endswith("Z") else value
        dt = datetime.fromisoformat(iso_str)
        if dt.utcoffset() is None or dt.utcoffset().total_seconds() != 0:
            raise ValidationError(f"La fecha '{value}' no pertenece a UTC cero.")
        return dt
    except Exception as exc:
        raise ValidationError(f"Formato de fecha inválido '{value}': {exc}") from exc


def ttl_seconds(value: Any, min_val: int = 60, max_val: int = 600) -> int:
    """Valida y castea el TTL permitiendo strings numéricos pero rechazando booleanos."""
    if isinstance(value, bool):
        raise ValidationError("El TTL debe ser un número entero (no booleano).")

    try:
        val_int = int(value)
    except (ValueError, TypeError) as exc:
        raise ValidationError(f"Valor de TTL inválido '{value}'.") from exc

    if not (min_val <= val_int <= max_val):
        raise ValidationError(f"TTL fuera de rango: {val_int}. Debe estar entre {min_val} y {max_val} s.")
    return val_int