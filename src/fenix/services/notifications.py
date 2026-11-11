"""Servicio de notificaciones externas para Telegram, Slack o salida por consola."""

import json
from typing import Any, Dict
import urllib.request
import urllib.error

from fenix.config.settings import Settings
from fenix.utils.errors import NotificationError, PermanentError, TransientError


def notify(settings: Settings, message: str) -> Dict[str, Any]:
    """
    Envía una notificación al canal configurado (telegram, slack o console).
    Aplica esperas acotadas (2s conexión / 5s lectura).
    No expone URLs privadas ni tokens ante errores.
    """
    provider = (settings.notification_provider or "console").lower()

    if provider == "console":
        print(f"\n[NOTIFICACIÓN CONSOLA]: {message}\n")
        return {"provider": "console", "delivered": True}

    elif provider == "telegram":
        token = settings.telegram_bot_token
        chat_id = settings.telegram_chat_id
        if not token or not chat_id:
            raise PermanentError("TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados.")

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                body = json.loads(response.read().decode("utf-8"))
                if not body.get("ok"):
                    raise NotificationError("Respuesta de Telegram sin ok=true.")
                return {"provider": "telegram", "delivered": True}
        except urllib.error.HTTPError as exc:
            # 400, 401, 403 son fallas de configuración permanentes
            if exc.code in (400, 401, 403):
                raise PermanentError(f"Error de credenciales en Telegram (HTTP {exc.code}).") from None
            raise TransientError(f"Falla transitoria en Telegram (HTTP {exc.code}).") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise TransientError("Falla transitoria de red al conectar con Telegram.") from None

    elif provider == "slack":
        webhook_url = settings.slack_webhook_url
        if not webhook_url:
            raise PermanentError("SLACK_WEBHOOK_URL no configurada.")

        payload = json.dumps({"text": message}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(webhook_url, data=payload, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                status_code = response.getcode()
                body_text = response.read().decode("utf-8").strip()
                if status_code != 200 or body_text != "ok":
                    raise NotificationError(f"Slack devolvió HTTP {status_code} con respuesta '{body_text}'.")
                return {"provider": "slack", "delivered": True}
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 403, 404):
                raise PermanentError(f"Error de configuración en Slack Webhook (HTTP {exc.code}).") from None
            raise TransientError(f"Falla transitoria en Slack (HTTP {exc.code}).") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise TransientError("Falla transitoria de red al conectar con Slack.") from None

    raise PermanentError(f"Proveedor de notificación '{provider}' no soportado.")