"""Remediación convergente de recursos de infraestructura mock (EC2 y S3)."""

from typing import Any, Dict
from fenix.config.settings import Settings
from fenix.services.demo import get_ec2_client, get_s3_client
from fenix.utils.errors import RemediationError


def repair(settings: Settings, resource_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ejecuta reparación convergente:
    - EC2: si está stopped pasa a running y verifica estado. Si ya estaba running no hace nada perjudicial.
    - S3: lee etiquetas existentes, mezcla con expected_tags y las aplica.
    """
    r_type = resource_info.get("type")
    r_id = resource_info.get("id")
    expected_tags = resource_info.get("expected_tags", {})

    if r_type == "ec2":
        ec2 = get_ec2_client(settings)
        desc = ec2.describe_instances(InstanceIds=[r_id])
        current_state = desc["Reservations"][0]["Instances"][0]["State"]["Name"]

        if current_state != "running":
            ec2.start_instances(InstanceIds=[r_id])
            # Comprobar estado tras solicitar start
            new_desc = ec2.describe_instances(InstanceIds=[r_id])
            final_state = new_desc["Reservations"][0]["Instances"][0]["State"]["Name"]
        else:
            final_state = current_state

        return {
            "resource_id": r_id,
            "type": "ec2",
            "previous_state": current_state,
            "current_state": final_state,
            "remediated": True,
        }

    elif r_type == "s3":
        s3 = get_s3_client(settings)
        try:
            tagging = s3.get_bucket_tagging(Bucket=r_id)
            current_tags = {t["Key"]: t["Value"] for t in tagging.get("TagSet", [])}
        except Exception:
            current_tags = {}

        # Fusión preservando etiquetas ajenas
        merged_tags = {**current_tags, **expected_tags}
        tag_set = [{"Key": k, "Value": v} for k, v in merged_tags.items()]

        s3.put_bucket_tagging(
            Bucket=r_id,
            Tagging={"TagSet": tag_set},
        )

        return {
            "resource_id": r_id,
            "type": "s3",
            "applied_tags": merged_tags,
            "remediated": True,
        }

    raise RemediationError(f"Tipo de recurso desconocido: {r_type}")