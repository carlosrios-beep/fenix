"""Validación estricta de esquemas y contratos de eventos para Proyecto Fénix."""

from typing import Any, Dict
from fenix.utils.errors import (
    ResourceNotFoundError,
    ValidationError,
)
from fenix.utils.validation import identifier, utc_text

REQUIRED_KEYS = {
    "schema_version",
    "event_id",
    "event_type",
    "resource_id",
    "occurred_at",
    "simulate_failures",
}

VALID_EVENT_TYPES = {
    "instance.stopped",
    "bucket.tags_missing",
}


def validate(event_data: Any, inventory: Dict[str, Any]) -> Dict[str, Any]:
    """
    Valida exhaustivamente un evento JSON según el contrato del Proyecto Fénix:
    - Es un diccionario no nulo.
    - Contiene exactamente las claves requeridas (sin claves faltantes ni extra).
    - schema_version es el entero 1 (rechazando booleanos).
    - event_id y resource_id cumplen [a-z0-9-]{3,32}.
    - event_type es conocido.
    - resource_id existe en el inventario.
    - occurred_at es una fecha ISO válida con zona UTC explícita.
    - simulate_failures es entero de 0 a 5 (rechazando booleanos).
    """
    if not isinstance(event_data, dict):
        raise ValidationError("El evento debe ser un objeto JSON (diccionario).")

    # Contrato cerrado: coincidencia exacta de claves
    actual_keys = set(event_data.keys())
    if actual_keys != REQUIRED_KEYS:
        missing = REQUIRED_KEYS - actual_keys
        extra = actual_keys - REQUIRED_KEYS
        msgs = []
        if missing:
            msgs.append(f"claves faltantes: {sorted(list(missing))}")
        if extra:
            msgs.append(f"claves no reconocidas: {sorted(list(extra))}")
        raise ValidationError(f"Violación de contrato en el evento ({', '.join(msgs)}).")

    # schema_version estricto
    schema_ver = event_data["schema_version"]
    if isinstance(schema_ver, bool) or schema_ver != 1:
        raise ValidationError(f"schema_version debe ser el entero 1 (recibido: {schema_ver}).")

    # Identificadores de formato
    event_id = identifier(event_data["event_id"])
    resource_id = identifier(event_data["resource_id"])

    # Tipo de evento permitido
    event_type = event_data["event_type"]
    if event_type not in VALID_EVENT_TYPES:
        raise ValidationError(f"event_type no reconocido: '{event_type}'.")

    # Existencia del recurso en el inventario conocido
    if resource_id not in inventory:
        raise ResourceNotFoundError(
            f"El recurso '{resource_id}' no pertenece al inventario del laboratorio."
        )

    # Coherencia recurso vs tipo de evento
    res_info = inventory[resource_id]
    if event_type == "instance.stopped" and res_info.get("type") != "ec2":
        raise ValidationError(f"El evento '{event_type}' no corresponde a un nodo EC2.")
    if event_type == "bucket.tags_missing" and res_info.get("type") != "s3":
        raise ValidationError(f"El evento '{event_type}' no corresponde a un bucket S3.")

    # Fecha UTC (valida formato y zona; preserva string ISO para serialización JSON segura)
    utc_dt = utc_text(event_data["occurred_at"])
    occurred_at_str = event_data["occurred_at"]

    # simulate_failures entre 0 y 5
    sim_fail = event_data["simulate_failures"]
    if isinstance(sim_fail, bool) or not isinstance(sim_fail, int) or not (0 <= sim_fail <= 5):
        raise ValidationError(
            f"simulate_failures debe ser un entero entre 0 y 5 (recibido: {sim_fail})."
        )

    return {
        "schema_version": schema_ver,
        "event_id": event_id,
        "event_type": event_type,
        "resource_id": resource_id,
        "occurred_at": occurred_at_str,
        "simulate_failures": sim_fail,
    }