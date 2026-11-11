"""Interfaz por línea de comandos (CLI) y orquestación del ciclo de vida de Fénix."""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
import urllib.request
import urllib.error

from fenix.config.settings import get_settings
from fenix.services.demo import inject_fault, setup_demo
from fenix.services.sqs import ensure_queues
from fenix.services.worker import run as run_worker
from fenix.utils.crypto import compute_signature
from fenix.utils.errors import FenixError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("fenix.cli")


def cmd_init_queues(args: argparse.Namespace) -> None:
    settings = get_settings()
    logger.info("Inicializando colas en SQS...")
    res = ensure_queues(settings)
    print(f"Colas listas:\n - Principal: {res['queue_url']}\n - DLQ: {res['dlq_url']}")


def cmd_setup_demo(args: argparse.Namespace) -> None:
    settings = get_settings()
    logger.info("Configurando inventario y laboratorio mock...")
    inventory = setup_demo(settings)
    print(f"Inventario listo en {settings.inventory_path}:")
    print(json.dumps(inventory, indent=2))


def cmd_fault(args: argparse.Namespace) -> None:
    settings = get_settings()
    logger.info("Inyectando falla en el recurso '%s'...", args.resource)
    resultado = inject_fault(settings, args.resource)
    print(resultado)


def cmd_worker(args: argparse.Namespace) -> None:
    settings = get_settings()
    logger.info("Arrancando worker (modo once: %s)...", args.once)
    try:
        run_worker(settings, once=args.once)
    except KeyboardInterrupt:
        logger.info("Worker detenido manualmente por el operador (Ctrl + C).")
    finally:
        # Cumplimiento PEP 765: sin return, break o continue dentro de finally
        logger.info("Cierre ordenado de recursos del worker completado.")


def cmd_send(args: argparse.Namespace) -> None:
    settings = get_settings()
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: El archivo '{file_path}' no existe.", file=sys.stderr)
        sys.exit(1)

    raw_body = file_path.read_bytes()
    timestamp = int(time.time())
    sig = compute_signature(settings.webhook_secret, timestamp, raw_body)

    url = f"http://127.0.0.1:8000/webhook"
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": f"t={timestamp},v1={sig}",
    }

    req = urllib.request.Request(url, data=raw_body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status_code = resp.getcode()
            body = resp.read().decode("utf-8")
            print(f"Respuesta HTTP {status_code}: {body}")
    except urllib.error.HTTPError as exc:
        print(f"Error HTTP {exc.code}: {exc.read().decode('utf-8')}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Error de conexión con el receptor: {exc.reason}", file=sys.stderr)
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fenix",
        description="CLI de orquestación y operación del Proyecto Fénix",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init-queues
    subparsers.add_parser("init-queues", help="Crea y configura colas SQS y DLQ")

    # setup-demo
    subparsers.add_parser("setup-demo", help="Inicializa el laboratorio mock EC2 y S3")

    # fault
    fault_p = subparsers.add_parser("fault", help="Inyecta falla sobre un recurso (node-01 o bucket-01)")
    fault_p.add_argument("resource", choices=["node-01", "bucket-01"], help="Alias del recurso objetivo")

    # worker
    worker_p = subparsers.add_parser("worker", help="Inicia el bucle de procesamiento del worker")
    worker_p.add_argument("--once", action="store_true", help="Procesa solo los mensajes actuales y termina")

    # send
    send_p = subparsers.add_parser("send", help="Envía un evento firmado al webhook receptor")
    send_p.add_argument("file", help="Ruta al archivo JSON del evento")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    commands = {
        "init-queues": cmd_init_queues,
        "setup-demo": cmd_setup_demo,
        "fault": cmd_fault,
        "worker": cmd_worker,
        "send": cmd_send,
    }

    try:
        commands[args.command](args)
    except FenixError as exc:
        logger.error("Error operativo de Fénix: %s", exc)
        sys.exit(1)
    except Exception as exc:
        logger.error("Error inesperado en CLI: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()