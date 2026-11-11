"""Excepciones semánticas de dominio para el Proyecto Fénix."""


class FenixError(Exception):
    """Excepción base del sistema Fénix. Deriva estrictamente de Exception."""
    pass


class PermanentError(FenixError):
    """Describe un fallo no recuperable o un entorno mock no preparado."""
    pass


class TransientError(FenixError):
    """Describe una falla transitoria o temporal (reintentable con backoff)."""
    pass


class ValidationError(FenixError):
    """Error de validación de contrato o inventario."""
    pass


class AuthenticationError(FenixError):
    """Error de firma HMAC o timestamp fuera de ventana."""
    pass


class ResourceNotFoundError(FenixError):
    """El recurso o alias no existe en el inventario del laboratorio."""
    pass


class RemediationError(FenixError):
    """Fallo durante la reparación del recurso mock."""
    pass


class NotificationError(FenixError):
    """Fallo al enviar el aviso externo a Telegram o Slack."""
    pass


class SQSBrokerError(FenixError):
    """Fallo de comunicación o visibilidad con SQS/DLQ."""
    pass