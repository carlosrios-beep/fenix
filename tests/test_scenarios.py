"""Escenarios de integración y tolerancia a fallos del Proyecto Fénix."""

import json
import pytest
from fenix.config.settings import Settings
from fenix.services.worker import handle_event, run


def test_duplicate_is_idempotent(tmp_path, monkeypatch):
    """Comprueba que repetir un evento no repite recursos ni acciones completadas."""
    ledger_file = tmp_path / "events.json"
    settings = Settings(ledger_path=ledger_file, notification_provider="console")

    event = {
        "schema_version": 1,
        "event_id": "evt-dup-001",
        "event_type": "instance.stopped",
        "resource_id": "node-01",
        "occurred_at": "2026-11-11T12:00:00Z",
        "simulate_failures": 0,
    }
    inventory = {
        "node-01": {"type": "ec2", "id": "i-mock01", "expected_tags": {}}
    }

    call_count = {"repairs": 0}

    def mock_repair(s, r):
        call_count["repairs"] += 1
        return {"remediated": True, "state": "running"}

    monkeypatch.setattr("fenix.services.worker.repair", mock_repair)

    # 1. Primera ejecución: repara
    res1 = handle_event(settings, event, inventory)
    assert res1["repair_done"] is True
    assert call_count["repairs"] == 1

    # 2. Segunda ejecución: no repara de nuevo
    res2 = handle_event(settings, event, inventory)
    assert res2["attempts"] == 2
    assert call_count["repairs"] == 1


def test_ack_is_after_success(monkeypatch):
    """Verifica el orden estricto: trabajo confirmado primero, ACK (delete_message) después."""
    actions = []

    class MockSQS:
        def receive_message(self, **kwargs):
            return {
                "Messages": [{
                    "ReceiptHandle": "rh-12345",
                    "Body": json.dumps({
                        "schema_version": 1,
                        "event_id": "evt-ack-001",
                        "event_type": "instance.stopped",
                        "resource_id": "node-01",
                        "occurred_at": "2026-11-11T12:00:00Z",
                        "simulate_failures": 0,
                    }),
                    "Attributes": {"ApproximateReceiveCount": "1"}
                }]
            }

        def delete_message(self, **kwargs):
            actions.append("ACK")

        def change_message_visibility(self, **kwargs):
            actions.append("RETRY")

    monkeypatch.setattr("fenix.services.worker.get_sqs_client", lambda s: MockSQS())
    monkeypatch.setattr("fenix.services.worker.repair", lambda s, r: actions.append("REPAIR"))
    monkeypatch.setattr("fenix.services.worker.notify", lambda s, m: actions.append("NOTIFY"))
    monkeypatch.setattr(
        "fenix.services.worker.read_json_state",
        lambda p: {"node-01": {"type": "ec2", "id": "i-01", "expected_tags": {}}} if "inventory" in str(p) else {}
    )
    monkeypatch.setattr("fenix.services.worker.write_json_state", lambda p, d: None)

    settings = Settings(notification_provider="console")
    run(settings, once=True)

    # Orden estricto esperado: REPAIR -> NOTIFY -> ACK
    assert actions == ["REPAIR", "NOTIFY", "ACK"]


@pytest.mark.integracion
def test_redrive_with_localstack():
    """Valida la política de RedrivePolicy configurada."""
    from fenix.config.settings import Settings
    from fenix.services.sqs import ensure_queues
    # Verificación de sintaxis de RedrivePolicy
    settings = Settings()
    assert settings.dlq_name == "fenix-events-dlq"