"""Utilidades criptográficas para autenticación de webhooks mediante HMAC-SHA256."""

import hashlib
import hmac
import time
from fenix.utils.errors import AuthenticationError


def compute_signature(secret: str, timestamp: int, raw_body: bytes) -> str:
    """Calcula la firma HMAC-SHA256 sobre b'{timestamp}.' + raw_body."""
    if isinstance(secret, str):
        secret_bytes = secret.encode("utf-8")
    else:
        secret_bytes = secret

    to_sign = str(timestamp).encode("utf-8") + b"." + raw_body
    return hmac.new(secret_bytes, to_sign, hashlib.sha256).hexdigest()


def verify(
    secret: str,
    signature_header: str | None,
    raw_body: bytes,
    tolerance_seconds: int = 300,
) -> int:
    """
    Verifica la cabecera X-Webhook-Signature.
    
    Formato esperado: t=<epoch>,v1=<hex_sha256>
    Retorna el timestamp validado si la firma es correcta y está dentro de la ventana.
    Lanza AuthenticationError ante cualquier fallo de autenticación.
    """
    if not signature_header:
        raise AuthenticationError("Cabecera X-Webhook-Signature ausente.")

    # Parseo estricto evitando claves duplicadas
    parts = signature_header.split(",")
    parsed = {}
    for part in parts:
        kv = part.strip().split("=", 1)
        if len(kv) != 2:
            raise AuthenticationError(f"Segmento de firma malformado: '{part}'.")
        key, value = kv[0].strip(), kv[1].strip()
        if key in parsed:
            raise AuthenticationError(f"Clave duplicada '{key}' en cabecera de firma.")
        parsed[key] = value

    if "t" not in parsed or "v1" not in parsed:
        raise AuthenticationError("Cabecera incompleta: requiere campos 't' y 'v1'.")

    # Validar entero de timestamp
    try:
        timestamp = int(parsed["t"])
    except ValueError as exc:
        raise AuthenticationError("El campo 't' de la firma debe ser un timestamp entero.") from exc

    received_sig = parsed["v1"]
    if len(received_sig) != 64:
        raise AuthenticationError("La firma v1 debe contener exactamente 64 caracteres hexadecimales.")

    # 1. Ventana de tolerancia temporal (300 s)
    now = int(time.time())
    if abs(now - timestamp) > tolerance_seconds:
        raise AuthenticationError(
            f"Firma fuera de ventana de tolerancia ({abs(now - timestamp)}s > {tolerance_seconds}s)."
        )

    # 2. Validación de firma en tiempo constante
    expected_sig = compute_signature(secret, timestamp, raw_body)
    if not hmac.compare_digest(expected_sig, received_sig):
        raise AuthenticationError("Firma HMAC-SHA256 no coincide.")

    return timestamp