import xmlrpc.client
import requests
import os
import time
from dotenv import load_dotenv

# Cargar variables desde el archivo .env
load_dotenv()

# --- CONFIGURACIÓN ---
ODOO_URL = os.environ.get("ODOO_URL")
ODOO_DB = os.environ.get("ODOO_DB")
ODOO_USER = os.environ.get("ODOO_USER")
ODOO_PASSWORD = os.environ.get("ODOO_PASSWORD")

# Whatsapp API Config
WHAI_URL = os.environ.get("WHAI_URL")
WHAI_CLIENT_KEY = os.environ.get("WHAI_CLIENT_KEY")
WHAI_BOT_ID = os.environ.get("WHAI_BOT_ID")
WHAI_GROUP_ID = os.environ.get("WHAI_GROUP_ID")

# Estado persistente: si estamos en Docker usamos /app/data, si es local usamos la carpeta actual
if os.path.exists("/app/data"):
    STATE_FILE = "/app/data/last_ticket_id.txt"
else:
    STATE_FILE = os.path.join(os.path.dirname(__file__), "last_ticket_id.txt")


def get_last_processed_id():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return int(f.read().strip())
    return 0


def save_last_processed_id(ticket_id):
    with open(STATE_FILE, "w") as f:
        f.write(str(ticket_id))


def main():
    try:
        # 1. Autenticación
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})

        if not uid:
            print("Error: Fallo la autenticación con Odoo.")
            return

        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

        # 2. Leer el estado actual
        last_id = get_last_processed_id()

        # Si es la primera vez (last_id == 0), buscamos el ticket más reciente para establecer el punto de partida
        if last_id == 0:
            latest_ticket = models.execute_kw(
                ODOO_DB,
                uid,
                ODOO_PASSWORD,
                "helpdesk.ticket",
                "search",
                [[]],
                {"limit": 1, "order": "id desc"},
            )
            if latest_ticket:
                save_last_processed_id(latest_ticket[0])
                print(
                    f"Estado inicial configurado. Ignorando tickets anteriores al ID: {latest_ticket[0]}"
                )
            return

        # 3. Buscar tickets nuevos
        domain = [("id", ">", last_id)]

        # Aseguramos el orden ascendente para procesar del más viejo al más nuevo
        new_ticket_ids = models.execute_kw(
            ODOO_DB,
            uid,
            ODOO_PASSWORD,
            "helpdesk.ticket",
            "search",
            [domain],
            {"order": "id asc"},
        )

        if not new_ticket_ids:
            print("No hay tickets nuevos.")
            return

        # 4. Obtener los detalles de los tickets nuevos
        # 4. Obtener los detalles de los tickets nuevos
        # Incluimos 'user_id', 'partner_id' y 'priority'
        tickets_data = models.execute_kw(
            ODOO_DB,
            uid,
            ODOO_PASSWORD,
            "helpdesk.ticket",
            "read",
            [new_ticket_ids],
            {
                "fields": [
                    "id",
                    "name",
                    "stage_id",
                    "description",
                    "user_id",
                    "partner_id",
                    "priority",
                ]
            },
        )

        # 5. Procesar e iterar
        for ticket in tickets_data:
            # Solo procesar si está en etapa "Nuevo" (Ajusta el nombre de la etapa según tu Odoo)
            stage_name = ticket.get("stage_id", [0, ""])[1]

            if "New" in stage_name or "Nuevo" in stage_name:
                # 1. Extraer Cliente (partner_id)
                partner_data = ticket.get("partner_id")
                cliente = partner_data[1] if partner_data else "Sin cliente"

                # 2. Extraer Asignado a (user_id)
                user_data = ticket.get("user_id")
                assigned_to = user_data[1] if user_data else "Sin asignar"

                # 3. Convertir Prioridad a Estrellas
                try:
                    prioridad_num = int(ticket.get("priority", "0"))
                    estrellas = (
                        "⭐" * prioridad_num if prioridad_num > 0 else "🤍 Normal"
                    )
                except (ValueError, TypeError):
                    estrellas = "🤍 Normal"

                # 4. Construir el mensaje formateado para WhatsApp
                message = (
                    f"🆕 Ticket: *{ticket['id']}* - {estrellas}\n"
                    f"{ticket['name']} - {cliente}\n"
                    f"🙋‍♂️ asignado a *{assigned_to}*"
                )

                headers = {
                    "Content-Type": "application/json",
                    "x-client-key": WHAI_CLIENT_KEY,
                    "x-client-botid": WHAI_BOT_ID,
                }

                payload = {
                    "to": WHAI_GROUP_ID,
                    "message": message,
                    "fromMe": "Script de Alerta",
                }

                # Ejecutar tu POST
                response = requests.post(
                    WHAI_URL, headers=headers, json=payload, timeout=10
                )
                response.raise_for_status()
                print(f"POST exitoso para el ticket {ticket['id']} - {ticket['name']}")
            else:
                print(f"Ticket {ticket['id']} ignorado (Etapa: {stage_name})")

            # Importante: Guardar el ID actualizado independientemente de si se envió el POST o no,
            # para no volver a evaluarlo en el futuro.
            save_last_processed_id(ticket["id"])

    except requests.exceptions.RequestException as re:
        print(f"Error de red al enviar el webhook: {re}")
    except Exception as e:
        print(f"Error crítico en la ejecución: {e}")


if __name__ == "__main__":
    print("🚀 Iniciando Worker de Odoo Sync...")
    while True:
        main()
        time.sleep(60)
