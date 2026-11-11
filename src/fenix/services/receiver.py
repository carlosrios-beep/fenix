"""Receptor HTTP FastAPI para ingesta asíncrona de alertas del laboratorio."""

import json
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, Header, HTTPException, Request, status
from starlette.concurrency import run_in_threadpool

from fenix.config.settings import get_settings
from fenix.services.events import validate
from fenix.services.sqs import get_sqs_client, send_event
from fenix.utils.crypto import verify
from fenix.utils.errors import AuthenticationError, ResourceNotFoundError, SQSBrokerError, ValidationError
from fenix.utils.state import read_json_state

MAX_BODY_SIZE = 16 * 1024  # 16 KiB límite estricto de consigna


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Cargar inventario del laboratorio al iniciar
    settings = get_settings()
    try:
        app.state.inventory = read_json_state(settings.inventory_path)
    except Exception:
        app.state.inventory = {}
    yield


app = FastAPI(title="Fenix Alert Receiver", lifespan=lifespan)


@app.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def receive_webhook(
    request: Request,
    x_webhook_signature: str | None = Header(None, alias="X-Webhook-Signature"),
) -> Dict[str, Any]:
    """Endpoint de ingesta: valida firma, tamaño, contrato y encola en SQS."""
    settings = get_settings()

    # 1. Lectura de raw bytes e inspección de tamaño máximo
    raw_body = await request.body()
    if len(raw_body) > MAX_BODY_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Cuerpo de la petición excede el límite de 16 KiB.",
        )

    # 2. Verificación criptográfica HMAC-SHA256
    try:
        verify(settings.webhook_secret, x_webhook_signature, raw_body)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    # 3. Decodificación de JSON
    try:
        event_dict = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cuerpo no es un JSON o UTF-8 válido.",
        ) from exc

    # 4. Validación de contrato cerrado e inventario
    inventory = getattr(request.app.state, "inventory", {})
    if not inventory:
        # Recarga dinámica por si fue generado por setup_demo
        try:
            inventory = read_json_state(settings.inventory_path)
            request.app.state.inventory = inventory
        except Exception:
            inventory = {}

    try:
        validated_event = validate(event_dict, inventory)
    except (ValidationError, ResourceNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    # 5. Publicación asíncrona hacia SQS (delegada a threadpool para no bloquear FastAPI)
    try:
        sqs_client = get_sqs_client(settings)
        message_id = await run_in_threadpool(
            send_event,
            sqs_client,
            settings.queue_url,
            validated_event,
        )
    except (SQSBrokerError, Exception) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error al encolar en SQS: {exc}",
        ) from exc

    return {
        "status": "accepted",
        "event_id": validated_event["event_id"],
        "message_id": message_id,
    }