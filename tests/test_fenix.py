"""Suite de pruebas unitarias para validación, criptografía y ledger (Matriz Fénix)."""

import json
import time
import pytest
from fenix.utils.crypto import compute_signature, verify
from fenix.utils.errors import (
    AuthenticationError,
    ResourceNotFoundError,
    ValidationError,
)
from fenix.services.events import validate
from fenix.services.worker import handle_event
from fenix.config.settings import Settings


SECRET = "clave_de_prueba_secreta_super_segura_32bytes"
MOCK_INVENTORY = {
    "node-01": {"type": "ec2", "id": "i-mock123", "expected_tags": {}},
    "bucket-01": {"type": "s3", "id": "fenix-bucket", "expected_tags": {}},
}


# --- F04: Firma ausente o alterada / Timestamp expirado ---
def test_f04_invalid_or_missing_signature():
    """F04: Cabecera ausente o firma alterada debe lanzar AuthenticationError."""
    payload = b'{"hello": "world"}'
    ts = int(time.time())

    # Cabecera ausente
    with pytest.raises(AuthenticationError):
        verify(SECRET, None, payload)

    # Firma alterada
    with pytest.raises(AuthenticationError):
        verify(SECRET, f"t={ts},v1={'0'*64}", payload)


def test_f04_expired_timestamp():
    """F04: Timestamp fuera de la ventana de 300 s (Replay Attack) debe ser rechazado."""
    payload = b'{"hello": "world"}'
    old_ts = int(time.time()) - 3600  # 1 hora atrás
    sig = compute_signature(SECRET, old_ts, payload)

    with pytest.raises(AuthenticationError):
        verify(SECRET, f"t={old_ts},v1={sig}", payload, tolerance_seconds=300)


# --- F05: Bytes alterados tras firmar ---
def test_f05_tampered_payload_bytes():
    """F05: Mismos datos conceptuales pero con bytes o espacios distintos invalidan el HMAC."""
    original_payload = b'{"schema_version": 1}'
    tampered_payload = b'{"schema_version":  1}'  # Espacio adicional
    ts = int(time.time())
    sig = compute_signature(SECRET, ts, original_payload)

    with pytest.raises(AuthenticationError):
        verify(SECRET, f"t={ts},v1={sig}", tampered_payload)


# --- F06: JSON no es diccionario o es una lista ---
def test_f06_reject_non_dict_json():
    """F06: Una lista JSON o tipo no objeto debe ser rechazada con ValidationError."""
    with pytest.raises(ValidationError):
        validate([{"schema_version": 1}], MOCK_INVENTORY)

    with pytest.raises(ValidationError):
        validate("un_string_simple", MOCK_INVENTORY)


# --- F07: Alias ajeno al inventario y claves extra ---
def test_f07_foreign_resource_and_extra_keys():
    """F07: Rechazo de recursos no declarados y campos no contemplados (contrato cerrado)."""
    valid_event = {
        "schema_version": 1,
        "event_id": "evt-001",
        "event_type": "instance.stopped",
        "resource_id": "node-99",  # No existe en MOCK_INVENTORY
        "occurred_at": "2026-11-11T12:00:00Z",
        "simulate_failures": 0,
    }

    # Recurso ajeno
    with pytest.raises(ResourceNotFoundError):
        validate(valid_event, MOCK_INVENTORY)

    # Clave extra
    event_with_extra = valid_event.copy()
    event_with_extra["resource_id"] = "node-01"
    event_with_extra["campo_extra_no_permitido"] = "valor"

    with pytest.raises(ValidationError):
        validate(event_with_extra, MOCK_INVENTORY)


# --- F11: Evento válido procesado por el worker e idempotencia ---
def test_f11_worker_event_handling_and_idempotency(tmp_path, monkeypatch):
    """F11: Verifica procesamiento por etapas y que repetir el evento omita acciones ya hechas."""
    ledger_file = tmp_path / "events.json"
    settings = Settings(ledger_path=ledger_file, notification_provider="console")

    event = {
        "schema_version": 1,
        "event_id": "evt-node-001",
        "event_type": "instance.stopped",
        "resource_id": "node-01",
        "occurred_at": "2026-11-11T12:00:00Z",
        "simulate_failures": 0,
    }

    # Evitar llamadas reales a EC2 en test unitario
    monkeypatch.setattr(
        "fenix.services.worker.repair",
        lambda s, r: {"remediated": True, "state": "running"},
    )

    # Primera ejecución: repara y marca el ledger
    res1 = handle_event(settings, event, MOCK_INVENTORY)
    assert res1["repair_done"] is True
    assert res1["notified"] is True
    assert res1["attempts"] == 1

    # Segunda ejecución con el mismo evento: no debe re-reparar
    res2 = handle_event(settings, event, MOCK_INVENTORY)
    assert res2["attempts"] == 2
    assert res2["repair_done"] is True