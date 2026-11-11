"""Configuración global y clientes de infraestructura para el Proyecto Fénix."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import boto3


@dataclass(frozen=True)
class Settings:
    """Valores de entorno y rutas del sistema."""

    # Seguridad y credenciales
    webhook_secret: str = os.getenv("WEBHOOK_SECRET", "fenix_secret_dev_key_32bytes_min")
    aws_access_key_id: str = os.getenv("AWS_ACCESS_KEY_ID", "mock")
    aws_secret_access_key: str = os.getenv("AWS_SECRET_ACCESS_KEY", "mock")
    aws_default_region: str = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

    # LocalStack (puerto 4566 estricto de cátedra)
    endpoint_url: str = os.getenv("AWS_ENDPOINT_URL", "http://127.0.0.1:4566")

    # Nombres de colas
    queue_name: str = os.getenv("QUEUE_NAME", "fenix-events-queue")
    dlq_name: str = os.getenv("DLQ_NAME", "fenix-events-dlq")
    queue_url: str = os.getenv(
        "QUEUE_URL",
        f"http://127.0.0.1:4566/000000000000/{os.getenv('QUEUE_NAME', 'fenix-events-queue')}",
    )
    dlq_url: str = os.getenv(
        "DLQ_URL",
        f"http://127.0.0.1:4566/000000000000/{os.getenv('DLQ_NAME', 'fenix-events-dlq')}",
    )

    # Identificación de grupo
    group_id: str = os.getenv("GROUP_ID", "grupo-01")

    # Rutas locales de runtime
    data_dir: Path = Path("data")
    inventory_path: Path = Path("data/inventory.json")
    ledger_path: Path = Path("data/events.json")

    # Proveedores de avisos externos
    notification_provider: str = os.getenv("NOTIFICATION_PROVIDER", "console")
    slack_webhook_url: str | None = os.getenv("SLACK_WEBHOOK_URL")
    telegram_bot_token: str | None = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str | None = os.getenv("TELEGRAM_CHAT_ID")


def get_settings() -> Settings:
    """Fábrica que entrega la configuración actual del sistema."""
    return Settings()


def client(service_name: str) -> Any:
    """
    Función de apoyo de cátedra requerida por cloud_support.py.
    Crea clientes Boto3 forzando LocalStack en loopback (127.0.0.1:4566).
    """
    cfg = get_settings()
    return boto3.client(
        service_name,
        endpoint_url=cfg.endpoint_url,
        region_name=cfg.aws_default_region,
        aws_access_key_id=cfg.aws_access_key_id,
        aws_secret_access_key=cfg.aws_secret_access_key,
    )