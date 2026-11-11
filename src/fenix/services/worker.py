"""Consumidor asíncrono del buffer SQS con ledger idempotente y reparación por etapas."""

import json
import logging
from typing import Any, Dict

from fenix.config.settings import Settings
from fenix.services.events import validate
from fenix.services.notifications import notify
from fenix.services.remediation import repair
from fenix.services.sqs import get_sqs_client, retry_later
from fenix.utils.errors import FenixError, ResourceNotFoundError, ValidationError
from fenix.utils.state import read_json_state, write_json_state

logger = logging.getLogger("fenix.worker")


def handle_event(
    settings: Settings,
    event_data: Dict[str, Any],
    inventory: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Orquesta el flujo de negocio por etapas durables:
    1. Comprueba o inicializa el registro en data/events.json.
    2. Simula fallas controladas (simulate_failures).
    3. Ejecuta repair si repair_done no está marcado.
    4. Envía notificación externa si notified no está marcado.
    """
    event_id = event_data["event_id"]
    ledger = read_json_state(settings.ledger_path)

    # 1. Recuperar o registrar entrada en el ledger
    if event_id not in ledger:
        record = {
            "event_id": event_id,
            "attempts": 0,
            "payload": event_data,
            "repair_done": False,
            "repair_result": None,
            "notified": False,
            "status": "processing",
        }
        ledger[event_id] = record
    else:
        record = ledger[event_id]
        # Detectar alteración de payload con mismo event_id (conflicto)
        if record.get("payload") != event_data:
            logger.warning("Conflicto de payload para el event_id '%s'. Conservando original.", event_id)

    record["attempts"] += 1
    write_json_state(settings.ledger_path, ledger)

    # 2. Simulación de fallas de laboratorio (simulate_failures)
    sim_failures = event_data.get("simulate_failures", 0)
    if record["attempts"] <= sim_failures:
        raise FenixError(
            f"Falla simulada {record['attempts']}/{sim_failures} para {event_id}."
        )

    # 3. Etapa de reparación convergente
    if not record.get("repair_done"):
        resource_id = event_data["resource_id"]
        resource_info = inventory[resource_id]
        repair_res = repair(settings, resource_info)
        record["repair_done"] = True
        record["repair_result"] = repair_res
        write_json_state(settings.ledger_path, ledger)
        logger.info("Reparación confirmada para %s (%s).", resource_id, event_id)
    else:
        logger.info("Reparación ya realizada previamente para %s. Omitiendo.", event_id)

    # 4. Etapa de notificación externa
    if not record.get("notified"):
        msg = (
            f"Proyecto Fénix - Alerta Resuelta\n"
            f"Evento: {event_id}\n"
            f"Recurso: {event_data['resource_id']}\n"
            f"Tipo: {event_data['event_type']}\n"
            f"Intentos: {record['attempts']}"
        )
        notify(settings, msg)
        record["notified"] = True
        record["status"] = "completed"
        write_json_state(settings.ledger_path, ledger)
        logger.info("Notificación externa confirmada para %s.", event_id)
    else:
        logger.info("Notificación ya realizada previamente para %s. Omitiendo.", event_id)

    return record


def run(settings: Settings, once: bool = False) -> None:
    """
    Bucle principal del worker:
    - Long Polling de 10s sobre la cola SQS.
    - Manejo de visibilidad y backoff.
    - Borrado explícito (ACK) tras completar etapas.
    """
    sqs = get_sqs_client(settings)
    inventory = read_json_state(settings.inventory_path)

    logger.info("Worker iniciado. Escuchando cola: %s", settings.queue_url)

    while True:
        try:
            resp = sqs.receive_message(
                QueueUrl=settings.queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=10,
                VisibilityTimeout=45,
                AttributeNames=["ApproximateReceiveCount"],
            )
        except Exception as exc:
            logger.error("Error al consultar SQS: %s. Esperando 2 segundos.", exc)
            if once:
                break
            continue

        messages = resp.get("Messages", [])
        if not messages:
            if once:
                break
            continue

        msg = messages[0]
        receipt_handle = msg["ReceiptHandle"]
        receive_count = int(msg.get("Attributes", {}).get("ApproximateReceiveCount", 1))

        try:
            body = json.loads(msg["Body"])
            validated = validate(body, inventory)
            handle_event(settings, validated, inventory)

            # Confirmación explícita (ACK) únicamente tras completar las etapas
            sqs.delete_message(
                QueueUrl=settings.queue_url,
                ReceiptHandle=receipt_handle,
            )
            logger.info("ACK exitoso en SQS para mensaje: %s", msg.get("MessageId"))

        except Exception as exc:
            logger.warning(
                "Fallo procesando mensaje (intento %d): %s. Programando backoff.",
                receive_count,
                exc,
            )
            try:
                retry_later(sqs, settings.queue_url, receipt_handle, receive_count)
            except Exception as backoff_err:
                logger.error("Error aplicando backoff sobre visibilidad: %s", backoff_err)

        if once:
            break