# Proyecto Fénix — Sistema de Remediación Automatizada de Infraestructura Cloud

### Información Institucional
* **Institución:** Instituto Técnico Superior
* **Carrera:** Tecnicatura Superior en Ciencia de Datos e Inteligencia Artificial
* **Materia:** Programación para Automatización II (2026 — 2° Cuatrimestre)
* **Estudiante:** Carlos Ríos
* **Matrícula / Legajo:** [Tu Matrícula]
* **Correo Institucional:** carlos.rios@naranjax.com
* **Repositorio Oficial:** https://github.com/carlosrios-beep/fenix

---

## 1. Tabla de Roles Técnicos y Responsabilidades

> **Nota de desarrollo individual:** La totalidad de los módulos, contratos de mensajería, remediaciones convergentes y suites automatizadas fueron diseñados, desarrollados y testeados de forma integral por un único autor.

| Rol Técnico | Responsable | Módulos Principales | Pruebas y Cobertura Defendida |
| :--- | :--- | :--- | :--- |
| **I1: Entradas y Excepciones** | Carlos Ríos | `fenix/utils/errors.py`<br>`fenix/utils/validation.py`<br>`fenix/services/events.py` | Contratos estrictos (`identifier`, `utc_text`, `ttl_seconds`), esquemas válidos y rechazo de recursos ajenos. |
| **I2: Mensajería e Inventario** | Carlos Ríos | `fenix/services/sqs.py`<br>`fenix/services/demo.py`<br>`fenix/config/settings.py` | Creación de colas SQS con RedrivePolicy (DLQ), gestión de inventario (`data/inventory.json`) y setup de recursos mock. |
| **I3: Webhook y Reparación** | Carlos Ríos | `fenix/utils/crypto.py`<br>`fenix/services/receiver.py`<br>`fenix/services/remediation.py` | Verificación HMAC-SHA256 sobre raw bytes (300 s), endpoint FastAPI (HTTP 202) y remediación convergente para EC2 y S3. |
| **I4: Observabilidad y Avisos** | Carlos Ríos | `fenix/utils/logging_json.py`<br>`fenix/services/notifications.py` | Pipeline no bloqueante con QueueListener, logs JSON estructurados en UTC, rotación comprimida en gzip y notificador de consola. |
| **I5: Worker y CLI** | Carlos Ríos | `fenix/services/worker.py`<br>`fenix/cli.py` | Long Polling, backoff acotado, idempotencia con ledger atómico (`data/events.json`) y borrado explícito (ACK) en SQS. |
| **I6: Pruebas y Diagnóstico** | Carlos Ríos | `tests/test_base.py`<br>`tests/test_contracts.py`<br>`tests/test_fenix.py`<br>`tests/test_scenarios.py` | Matriz F01-F16: inyección de fallas, duplicados idempotentes, redrive efectivo a DLQ y suite completa en verde (16 passed). |
# Plantillas del proyecto Fenix

Leer Guia.md o la consigna PDF antes de ejecutar. Este es un punto de partida didáctico: los TODO y NotImplementedError son tareas del equipo, no una aplicación terminada.

## Inicio

Crear y activar un entorno virtual Python 3.11 o superior. Desde esta carpeta ejecutar `python -m pip install -e .`, copiar `.env.example` a `.env`, completar variables y usar la instalación LocalStack validada por la cátedra. El compose de referencia usa EC2 mock, sin VM real. Python corre en el host.

`python -m pytest -m base -q` verifica el apoyo ya implementado. `python -m pytest -m pendiente -q` falla inicialmente hasta completar contratos. No confundir esas marcas con aprobación del TP.

La guía contiene los comandos exactos, matriz de pruebas, roles y requisitos del README definitivo que debe escribir el equipo. Reemplazar este README inicial por su documentación completa.
