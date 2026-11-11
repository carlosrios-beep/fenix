"""Configuración del laboratorio mock en LocalStack (EC2 y S3) e inyección de fallas."""

from typing import Any, Dict
import boto3
from fenix.config.settings import Settings, get_settings
from fenix.services.cloud_support import (
    create_bucket,
    create_group,
    create_instance,
    mock_inputs,
)
from fenix.utils.errors import RemediationError
from fenix.utils.state import read_json_state, write_json_state


def get_ec2_client(settings: Settings):
    """Retorna cliente Boto3 para EC2 en LocalStack."""
    return boto3.client(
        "ec2",
        endpoint_url=settings.endpoint_url,
        region_name=settings.aws_default_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


def get_s3_client(settings: Settings):
    """Retorna cliente Boto3 para S3 en LocalStack."""
    return boto3.client(
        "s3",
        endpoint_url=settings.endpoint_url,
        region_name=settings.aws_default_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


def setup_demo(settings: Settings) -> Dict[str, Any]:
    """
    Inicializa o recupera los recursos mock de laboratorio.
    Es idempotente: si ya existen en inventory.json, no los duplica.
    """
    inventory = read_json_state(settings.inventory_path)
    expected_tags = {
        "ManagedBy": "ppa2",
        "Project": "fenix",
        "GroupId": settings.group_id,
        "Owner": settings.group_id,
    }

    # 1. Configurar nodo EC2 (node-01)
    if "node-01" not in inventory:
        vpc_id, image_id = mock_inputs()
        # Firma: create_group(name: str, vpc_id: str, tags: dict[str, str])
        sg_id = create_group(f"{settings.group_id}-sg", vpc_id, expected_tags)
        # Firma: create_instance(image_id: str, group_id: str, token: str, tags: dict[str, str])
        instance_id = create_instance(
            image_id,
            sg_id,
            f"{settings.group_id}-token",
            expected_tags,
        )
        inventory["node-01"] = {
            "type": "ec2",
            "id": instance_id,
            "security_group_id": sg_id,
            "expected_tags": expected_tags,
        }

    # 2. Configurar bucket S3 (bucket-01)
    if "bucket-01" not in inventory:
        bucket_name = f"fenix-{settings.group_id}-bucket"
        # Firma: create_bucket(name: str, tags: dict[str, str])
        create_bucket(bucket_name, expected_tags)
        inventory["bucket-01"] = {
            "type": "s3",
            "id": bucket_name,
            "expected_tags": expected_tags,
        }

    write_json_state(settings.inventory_path, inventory)
    return inventory


def inject_fault(settings: Settings, resource_alias: str) -> str:
    """Simula una falla en el recurso especificado (node-01 -> stopped, bucket-01 -> pierde Owner)."""
    inventory = read_json_state(settings.inventory_path)
    if resource_alias not in inventory:
        raise RemediationError(f"Recurso '{resource_alias}' no inventariado.")

    info = inventory[resource_alias]
    if info["type"] == "ec2":
        ec2 = get_ec2_client(settings)
        ec2.stop_instances(InstanceIds=[info["id"]])
        return f"Instancia {info['id']} ({resource_alias}) detenida (stopped)."

    elif info["type"] == "s3":
        s3 = get_s3_client(settings)
        tags_without_owner = [
            {"Key": k, "Value": v}
            for k, v in info["expected_tags"].items()
            if k != "Owner"
        ]
        s3.put_bucket_tagging(
            Bucket=info["id"],
            Tagging={"TagSet": tags_without_owner},
        )
        return f"Bucket {info['id']} ({resource_alias}) modificado: se eliminó la etiqueta 'Owner'."

    raise RemediationError(f"Tipo de recurso no soportado: {info['type']}")