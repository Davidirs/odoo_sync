# Odoo Sync Worker

Este worker monitorea continuamente el módulo Helpdesk de Odoo en busca de nuevos tickets y envía notificaciones a un grupo de WhatsApp usando alguna API.

## Requisitos

- Python 3.11+
- Docker (opcional, para despliegues usando Easypanel o similar)

## Variables de Entorno

Crea un archivo `.env` en la raíz del proyecto con las siguientes variables:

```env
ODOO_URL=https://tu-odoo.com
ODOO_DB=tu_base_de_datos
ODOO_USER=tu_correo@empresa.com
ODOO_PASSWORD=tu_password_o_app_password
WHAI_CLIENT_KEY=tu_client_key
WHAI_BOT_ID=bot_xxxx
WHAI_GROUP_ID=xxxx-xxxx@g.us
```

## Uso Local

1. Instala las dependencias: `pip install -r requirements.txt`
2. Ejecuta el script: `python3 odoo_sync.py`

## Despliegue en Docker / Easypanel

El proyecto incluye un `Dockerfile` optimizado.
El estado (el último ID procesado) se guarda en la ruta `/app/data/last_ticket_id.txt`. Asegúrate de montar un volumen persistente en la ruta `/app/data` de tu contenedor para no perder el progreso al reiniciar.
