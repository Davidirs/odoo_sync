import os
import json
import xmlrpc.client
import secrets
from datetime import timedelta, datetime
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from dotenv import load_dotenv
import groq

load_dotenv()

app = Flask(__name__)
# Secret key for signing cookies
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

# Enhanced Session Cookie Security
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=6),
)

ODOO_URL = os.environ.get("ODOO_URL", "https://esmtcx.odoo.com").rstrip("/")
ODOO_DB = os.environ.get("ODOO_DB", "esmtcx")

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "integrations_config.json")

# In-memory server-side session cache to avoid exposing passwords in client cookies
# Structure: { sid: { "uid": int, "user": str, "password": str, "name": str, "expires": datetime } }
SERVER_SESSIONS = {}


def get_active_server_session():
    """Retrieve and validate server-side session."""
    sid = session.get("sid")
    if not sid or sid not in SERVER_SESSIONS:
        return None
    
    sess_data = SERVER_SESSIONS[sid]
    if datetime.utcnow() > sess_data.get("expires", datetime.min):
        SERVER_SESSIONS.pop(sid, None)
        session.clear()
        return None
    return sess_data


def load_integrations_config():
    """Load settings from JSON file or environment."""
    config = {
        "groq_api_key": os.environ.get("GROQ_API_KEY", ""),
        "groq_base_url": os.environ.get("GROQ_BASE_URL", ""),
        "groq_model": os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
        "groq_system_prompt": (
            "Eres un asistente de soporte técnico senior experto en Odoo Helpdesk y atención al cliente. "
            "Tu tarea es analizar el ticket de soporte proporcionado y entregar un análisis estructurado en español, "
            "claro, conciso y profesional, que incluya: 1. Resumen clave del caso, 2. Nivel de urgencia/impacto y posible causa técnica, "
            "3. Pasos recomendados de resolución para el agente, 4. Borrador de respuesta cordial y empática para enviarle al cliente."
        )
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                config.update(saved)
        except Exception as e:
            print(f"Error loading config file: {e}")
    return config


def save_integrations_config(data):
    """Save integrations configuration to JSON file."""
    config = load_integrations_config()
    config.update(data)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False


def get_odoo_connection(user, password):
    """Authenticate against Odoo XML-RPC and return (uid, models) or (None, None)."""
    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(ODOO_DB, user, password, {})
        if uid:
            models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)
            return uid, models
    except Exception as e:
        print(f"Error authenticating with Odoo: {e}")
    return None, None


@app.route("/")
def index():
    return render_template(
        "index.html",
        odoo_url=ODOO_URL,
        odoo_db=ODOO_DB
    )


@app.route("/health", methods=["GET"])
@app.route("/healthz", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "service": "odoo-ticket-hub"})


@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify({
        "odoo_url": ODOO_URL,
        "odoo_db": ODOO_DB
    })


@app.route("/api/auth/status", methods=["GET"])
def auth_status():
    sess_data = get_active_server_session()
    if sess_data:
        return jsonify({
            "authenticated": True,
            "user": sess_data.get("user"),
            "uid": sess_data.get("uid"),
            "name": sess_data.get("name", sess_data.get("user")),
            "db": ODOO_DB,
            "url": ODOO_URL
        })
    return jsonify({"authenticated": False})


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"success": False, "error": "Usuario y contraseña requeridos"}), 400

    uid, models = get_odoo_connection(username, password)
    if not uid:
        return jsonify({"success": False, "error": "Credenciales inválidas o error de conexión con Odoo"}), 401

    user_name = username
    try:
        user_res = models.execute_kw(
            ODOO_DB,
            uid,
            password,
            "res.users",
            "read",
            [[uid]],
            {"fields": ["name", "email"]}
        )
        if user_res:
            user_name = user_res[0].get("name", username)
    except Exception:
        pass

    # Generate secure random session ID (Server-Side Session)
    sid = secrets.token_urlsafe(32)
    session.permanent = True
    session["sid"] = sid

    SERVER_SESSIONS[sid] = {
        "uid": uid,
        "user": username,
        "password": password,
        "name": user_name,
        "expires": datetime.utcnow() + timedelta(hours=6)
    }

    return jsonify({
        "success": True,
        "user": username,
        "name": user_name,
        "uid": uid
    })


@app.route("/api/logout", methods=["POST"])
def logout():
    sid = session.get("sid")
    if sid:
        SERVER_SESSIONS.pop(sid, None)
    session.clear()
    return jsonify({"success": True})


@app.route("/api/tickets", methods=["GET"])
def get_tickets():
    sess_data = get_active_server_session()
    if not sess_data:
        return jsonify({"error": "No autorizado. Inicia sesión primero."}), 401

    password = sess_data["password"]
    uid = sess_data["uid"]

    try:
        limit = int(request.args.get("limit", 10))
        limit = max(1, min(limit, 50))

        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)
        
        fields = [
            "id",
            "name",
            "stage_id",
            "priority",
            "partner_id",
            "user_id",
            "create_date",
            "write_date",
            "description",
            "ticket_type_id",
            "team_id",
            "kanban_state"
        ]

        tickets = models.execute_kw(
            ODOO_DB,
            uid,
            password,
            "helpdesk.ticket",
            "search_read",
            [[]],
            {"limit": limit, "order": "id desc", "fields": fields}
        )

        formatted_tickets = []
        stats = {
            "total": len(tickets),
            "new": 0,
            "in_progress": 0,
            "waiting": 0,
            "solved": 0,
            "closed": 0,
            "high_priority": 0
        }

        for t in tickets:
            stage_data = t.get("stage_id")
            stage_id = stage_data[0] if stage_data else 0
            stage_name = stage_data[1] if stage_data else "Sin etapa"

            partner_data = t.get("partner_id")
            client_name = partner_data[1] if partner_data else "Sin cliente"
            client_id = partner_data[0] if partner_data else None

            user_data = t.get("user_id")
            assigned_name = user_data[1] if user_data else "Sin asignar"
            assigned_id = user_data[0] if user_data else None

            team_data = t.get("team_id")
            team_name = team_data[1] if team_data else "General"

            type_data = t.get("ticket_type_id")
            ticket_type = type_data[1] if type_data else "Soporte"

            try:
                priority = int(t.get("priority", "0"))
            except (ValueError, TypeError):
                priority = 0

            if priority >= 3:
                stats["high_priority"] += 1

            # Stage categorization
            stage_lower = stage_name.lower()
            if "new" in stage_lower or "nuevo" in stage_lower:
                stats["new"] += 1
                stage_category = "new"
            elif "progress" in stage_lower or "progreso" in stage_lower or "work" in stage_lower:
                stats["in_progress"] += 1
                stage_category = "in_progress"
            elif "wait" in stage_lower or "espera" in stage_lower or "customer" in stage_lower or "vendor" in stage_lower:
                stats["waiting"] += 1
                stage_category = "waiting"
            elif "solved" in stage_lower or "resuelto" in stage_lower:
                stats["solved"] += 1
                stage_category = "solved"
            elif "closed" in stage_lower or "cerrado" in stage_lower:
                stats["closed"] += 1
                stage_category = "closed"
            else:
                stage_category = "other"

            ticket_id = t.get("id")
            odoo_ticket_url = f"{ODOO_URL}/web#id={ticket_id}&cids=1&menu_id=352&action=475&model=helpdesk.ticket&view_type=form"

            formatted_tickets.append({
                "id": ticket_id,
                "name": t.get("name") or "(Sin asunto)",
                "stage": {
                    "id": stage_id,
                    "name": stage_name,
                    "category": stage_category
                },
                "priority": priority,
                "client": {
                    "id": client_id,
                    "name": client_name
                },
                "assigned": {
                    "id": assigned_id,
                    "name": assigned_name
                },
                "team": team_name,
                "type": ticket_type,
                "create_date": t.get("create_date"),
                "write_date": t.get("write_date"),
                "description": t.get("description") or "Sin descripción detallada.",
                "kanban_state": t.get("kanban_state"),
                "odoo_url": odoo_ticket_url
            })

        return jsonify({
            "success": True,
            "tickets": formatted_tickets,
            "stats": stats,
            "db": ODOO_DB
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tickets/<int:ticket_id>", methods=["GET"])
def get_ticket_detail(ticket_id):
    sess_data = get_active_server_session()
    if not sess_data:
        return jsonify({"error": "No autorizado"}), 401

    password = sess_data["password"]
    uid = sess_data["uid"]

    try:
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)
        ticket = models.execute_kw(
            ODOO_DB,
            uid,
            password,
            "helpdesk.ticket",
            "read",
            [[ticket_id]]
        )
        if not ticket:
            return jsonify({"success": False, "error": "Ticket no encontrado"}), 404
        
        t = ticket[0]
        t["odoo_url"] = f"{ODOO_URL}/web#id={ticket_id}&cids=1&menu_id=352&action=475&model=helpdesk.ticket&view_type=form"
        return jsonify({"success": True, "ticket": t})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================
# SETTINGS & GROQ AI INTEGRATION ENDPOINTS
# ==========================================

@app.route("/api/settings", methods=["GET"])
def get_settings():
    config = load_integrations_config()
    api_key = config.get("groq_api_key", "")
    masked_key = ""
    if api_key:
        masked_key = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "********"

    return jsonify({
        "success": True,
        "groq_configured": bool(api_key),
        "groq_masked_key": masked_key,
        "groq_base_url": config.get("groq_base_url", ""),
        "groq_model": config.get("groq_model", "openai/gpt-oss-120b"),
        "groq_system_prompt": config.get("groq_system_prompt", "")
    })


@app.route("/api/settings/groq", methods=["POST"])
def save_groq_settings():
    data = request.get_json() or {}
    api_key = data.get("api_key", "").strip()
    base_url = data.get("base_url", "").strip()
    model = data.get("model", "openai/gpt-oss-120b").strip()
    prompt = data.get("system_prompt", "").strip()

    update_payload = {
        "groq_model": model or "openai/gpt-oss-120b",
        "groq_base_url": base_url
    }
    if prompt:
        update_payload["groq_system_prompt"] = prompt

    if api_key:
        update_payload["groq_api_key"] = api_key

    ok = save_integrations_config(update_payload)
    if ok:
        return jsonify({"success": True, "message": "Configuración de Groq guardada exitosamente."})
    return jsonify({"success": False, "error": "No se pudo guardar la configuración."}), 500


@app.route("/api/settings/groq/test", methods=["POST"])
def test_groq_connection():
    data = request.get_json() or {}
    api_key = data.get("api_key", "").strip()
    base_url = data.get("base_url", "").strip()
    config = load_integrations_config()
    
    if not api_key:
        api_key = config.get("groq_api_key", "")
    if not base_url:
        base_url = config.get("groq_base_url", "")

    if not api_key:
        return jsonify({"success": False, "error": "No se ha proporcionado una API Key de Groq."}), 400

    model = data.get("model") or config.get("groq_model", "openai/gpt-oss-120b")

    try:
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        client = groq.Groq(**kwargs)
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a connectivity test assistant."},
                {"role": "user", "content": "Responde únicamente: 'Conexión a Groq exitosa.'"}
            ],
            max_tokens=30,
            temperature=0.2
        )
        msg = completion.choices[0].message.content.strip()
        return jsonify({"success": True, "message": msg})
    except Exception as e:
        return jsonify({"success": False, "error": f"Error de conexión con Groq: {str(e)}"}), 500


@app.route("/api/ai/analyze-ticket", methods=["POST"])
def analyze_ticket_with_ai():
    sess_data = get_active_server_session()
    if not sess_data:
        return jsonify({"error": "No autorizado"}), 401

    config = load_integrations_config()
    api_key = config.get("groq_api_key")
    base_url = config.get("groq_base_url")
    if not api_key:
        return jsonify({
            "success": False,
            "error": "Groq IA no está configurado. Ve a Ajustes > Integraciones para ingresar tu API Key de Groq."
        }), 400

    data = request.get_json() or {}
    ticket = data.get("ticket") or {}

    ticket_id = ticket.get("id", "N/A")
    ticket_name = ticket.get("name", "N/A")
    client_name = ticket.get("client", {}).get("name", "Sin cliente")
    assigned_name = ticket.get("assigned", {}).get("name", "Sin asignar")
    stage_name = ticket.get("stage", {}).get("name", "N/A")
    priority = ticket.get("priority", 0)
    raw_desc = ticket.get("description", "Sin descripción.")

    model = config.get("groq_model", "openai/gpt-oss-120b")
    system_prompt = config.get("groq_system_prompt")

    user_prompt = f"""
Analiza el siguiente ticket de soporte técnico:

Caso: #{ticket_id} - {ticket_name}
Cliente: {client_name}
Asesor asignado: {assigned_name}
Etapa: {stage_name} | Prioridad: {priority}/3
Detalle:
{raw_desc}

Genera un reporte técnico claro y profesional con las siguientes secciones:
### Resumen del Caso
(Síntesis clara en 2 líneas)

### Diagnóstico y Severidad
(Causa raíz técnica y nivel de impacto)

### Plan de Acción
(Pasos concretos para resolver en Odoo o plataformas)

### Propuesta de Respuesta al Cliente
(Borrador directo y empático listo para enviar por WhatsApp o correo)
"""

    try:
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        client = groq.Groq(**kwargs)
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        ai_response = completion.choices[0].message.content.strip()
        return jsonify({
            "success": True,
            "analysis": ai_response,
            "model_used": model
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Error al procesar con Groq IA: {str(e)}"}), 500


# ==========================================
# MONTHLY CLIENT REPORTING ENDPOINTS
# ==========================================

MONTH_NAMES_ES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]


def strip_html_tags(text):
    """Clean HTML tags and compress whitespaces."""
    import re
    if not text:
        return ""
    cleaned = re.sub(r'<[^>]+>', ' ', text)
    return ' '.join(cleaned.split())


@app.route("/api/reports/clients", methods=["GET"])
def get_report_clients():
    sess_data = get_active_server_session()
    if not sess_data:
        return jsonify({"error": "No autorizado"}), 401

    password = sess_data["password"]
    uid = sess_data["uid"]

    try:
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)
        teams = models.execute_kw(
            ODOO_DB,
            uid,
            password,
            "helpdesk.team",
            "search_read",
            [[["active", "=", True]]],
            {"fields": ["id", "name"], "order": "name asc"}
        )
        return jsonify({"success": True, "clients": teams})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/reports/tickets", methods=["GET"])
def get_monthly_tickets():
    sess_data = get_active_server_session()
    if not sess_data:
        return jsonify({"error": "No autorizado"}), 401

    password = sess_data["password"]
    uid = sess_data["uid"]

    try:
        client_id = int(request.args.get("client_id", 0))
        year = int(request.args.get("year", datetime.now().year))
        month = int(request.args.get("month", datetime.now().month))

        if not client_id or not (1 <= month <= 12):
            return jsonify({"success": False, "error": "Parámetros de cliente o mes inválidos"}), 400

        # Calculate month date range
        start_date = f"{year:04d}-{month:02d}-01 00:00:00"
        if month == 12:
            next_start = f"{year+1:04d}-01-01 00:00:00"
        else:
            next_start = f"{year:04d}-{month+1:02d}-01 00:00:00"

        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)

        domain = [
            ("team_id", "=", client_id),
            ("create_date", ">=", start_date),
            ("create_date", "<", next_start)
        ]

        fields = [
            "id",
            "name",
            "partner_id",
            "ticket_type_id",
            "stage_id",
            "create_date",
            "write_date",
            "close_date",
            "total_hours_spent",
            "description",
            "message_ids"
        ]

        tickets = models.execute_kw(
            ODOO_DB,
            uid,
            password,
            "helpdesk.ticket",
            "search_read",
            [domain],
            {"fields": fields, "order": "id asc"}
        )

        type_counts = {}
        total_hours = 0.0
        formatted_tickets = []

        TYPE_TRANSLATIONS = {
            "request": "Requerimiento",
            "incident": "Incidente",
            "question": "Preguntas",
            "change": "Cambio",
            "problem": "Problema",
            "support": "Soporte"
        }

        for t in tickets:
            ticket_id = t["id"]
            type_data = t.get("ticket_type_id")
            raw_type = type_data[1] if type_data else "Requerimiento"
            type_name = TYPE_TRANSLATIONS.get(raw_type.lower(), raw_type)
            type_counts[type_name] = type_counts.get(type_name, 0) + 1

            hours = float(t.get("total_hours_spent") or 0.0)
            total_hours += hours

            stage_data = t.get("stage_id")
            stage_name = stage_data[1] if stage_data else "Abierto"

            partner_data = t.get("partner_id")
            client_contact = partner_data[1] if partner_data else "Sin contacto"

            desc_clean = strip_html_tags(t.get("description", ""))

            # Extract recent chatter logs / notes excluding bot notices
            msg_ids = t.get("message_ids", [])
            recent_notes = []
            if msg_ids:
                msgs = models.execute_kw(
                    ODOO_DB,
                    uid,
                    password,
                    "mail.message",
                    "search_read",
                    [[["id", "in", msg_ids[:15]]]],
                    {"fields": ["author_id", "body", "date"], "order": "id asc"}
                )
                for m in msgs:
                    b = strip_html_tags(m.get("body", ""))
                    author = m.get("author_id", ["", ""])[1] if m.get("author_id") else "Sistema"
                    if b and "OdooBot" not in author and len(b) > 10:
                        recent_notes.append(f"{author}: {b}")

            odoo_url = f"{ODOO_URL}/web#id={ticket_id}&cids=1&menu_id=352&action=475&model=helpdesk.ticket&view_type=form"

            formatted_tickets.append({
                "id": ticket_id,
                "name": t.get("name") or "(Sin Asunto)",
                "type": type_name,
                "stage": stage_name,
                "contact": client_contact,
                "create_date": t.get("create_date"),
                "hours_spent": hours,
                "description": desc_clean,
                "notes": recent_notes[-4:], # Top 4 recent meaningful notes
                "odoo_url": odoo_url
            })

        month_label = f"{MONTH_NAMES_ES[month]} de {year}"

        return jsonify({
            "success": True,
            "period": month_label,
            "month_name": MONTH_NAMES_ES[month],
            "year": year,
            "month": month,
            "total_tickets": len(formatted_tickets),
            "total_hours": round(total_hours, 2),
            "type_counts": type_counts,
            "tickets": formatted_tickets
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/reports/generate-ai-report", methods=["POST"])
def generate_monthly_ai_report():
    sess_data = get_active_server_session()
    if not sess_data:
        return jsonify({"error": "No autorizado"}), 401

    config = load_integrations_config()
    api_key = config.get("groq_api_key")
    base_url = config.get("groq_base_url")
    if not api_key:
        return jsonify({
            "success": False,
            "error": "Groq IA no está configurado. Ve a Ajustes > Integraciones para ingresar tu API Key."
        }), 400

    data = request.get_json() or {}
    client_name = data.get("client_name", "Cliente")
    period_label = data.get("period_label", "este mes")
    tickets = data.get("tickets") or []

    if not tickets:
        return jsonify({"success": False, "error": "No hay tickets para generar el resumen."}), 400

    # Build tickets payload for Groq
    type_counts = {}
    tickets_prompt_list = []
    for idx, t in enumerate(tickets, 1):
        ttype = t.get("type", "Requerimiento")
        type_counts[ttype] = type_counts.get(ttype, 0) + 1
        
        notes_str = "\n   - ".join(t.get("notes") or []) if t.get("notes") else "Sin notas adicionales."
        desc_str = t.get("description") or "Sin descripción provista."
        
        tickets_prompt_list.append(
            f"{idx}. #{t['id']} - {t['name']} (Tipo: {ttype})\n"
            f"   Descripción: {desc_str[:300]}\n"
            f"   Notas/Logs de Resolución:\n   - {notes_str}"
        )

    # Breakdown text helper
    type_breakdown_parts = [f"{cnt} de ellos como {k.lower()}" if idx == 0 else f"{cnt} como {k.lower()}" for idx, (k, cnt) in enumerate(type_counts.items())]
    type_breakdown_str = ", ".join(type_breakdown_parts)

    prompt = f"""
Eres un redactor técnico senior de informes ejecutivos de soporte TI para clientes corporativos.
Genera la sección '2. RESUMEN DE SOPORTE' mensual para el cliente '{client_name}' del período '{period_label}'.

Datos estadísticos:
- Total casos aperturados en el mes: {len(tickets)}
- Desglose por tipo: {type_breakdown_str}

Casos registrados en Odoo con sus logs y notas de resolución:
{chr(10).join(tickets_prompt_list)}

Instrucciones estrictas:
1. 'section_header': Debe ser '2. RESUMEN DE SOPORTE'
2. 'intro': Un párrafo con el estilo: 'Durante el mes de {period_label} se aperturaron {len(tickets)} casos para {client_name}, {type_breakdown_str}, un breve resumen de ellos es el siguiente:'
3. 'tickets': Una lista ordenada donde para CADA ticket devuelves:
   - 'id': número de ID
   - 'title': título exacto del caso
   - 'summary': 1 o 2 párrafos ejecutivos, claros, en español neutro profesional, explicando exactamente la acción realizada o cómo quedó solucionado el caso según las notas y logs del ticket.

Responde ÚNICAMENTE en formato JSON válido con esta estructura:
{{
  "section_header": "2. RESUMEN DE SOPORTE",
  "intro": "Durante el mes de...",
  "tickets": [
    {{
      "id": 11239,
      "title": "Creación de Accesos SocialHub",
      "summary": "Habilitación de los usuarios solicitados..."
    }}
  ]
}}
"""

    model = config.get("groq_model", "openai/gpt-oss-120b")
    try:
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        client = groq.Groq(**kwargs)

        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Eres un asistente experto que responde estrictamente en JSON válido."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            response_format={"type": "json_object"}
        )

        raw_json = completion.choices[0].message.content.strip()
        parsed = json.loads(raw_json)

        return jsonify({
            "success": True,
            "report": parsed,
            "model_used": model
        })

    except Exception as e:
        return jsonify({"success": False, "error": f"Error al generar informe con IA: {str(e)}"}), 500


@app.route("/api/reports/regenerate-single-summary", methods=["POST"])
def regenerate_single_summary():
    sess_data = get_active_server_session()
    if not sess_data:
        return jsonify({"error": "No autorizado"}), 401

    config = load_integrations_config()
    api_key = config.get("groq_api_key")
    base_url = config.get("groq_base_url")
    if not api_key:
        return jsonify({"success": False, "error": "Groq IA no está configurado."}), 400

    data = request.get_json() or {}
    ticket = data.get("ticket") or {}

    notes_str = "\n- ".join(ticket.get("notes") or [])
    desc_str = ticket.get("description") or ""

    prompt = f"""
Sintetiza en un párrafo profesional (1 a 3 líneas) la resolución y actividades realizadas para el siguiente caso de soporte:
Caso: #{ticket.get('id')} - {ticket.get('name')} (Tipo: {ticket.get('type')})
Descripción: {desc_str[:400]}
Notas/Logs de resolución:
- {notes_str}

Responde ÚNICAMENTE con el párrafo del resumen en español neutro sin introducciones ni asteriscos.
"""

    model = config.get("groq_model", "openai/gpt-oss-120b")
    try:
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        client = groq.Groq(**kwargs)

        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Eres un redactor técnico que resume casos en 1 párrafo claro."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=300
        )
        summary = completion.choices[0].message.content.strip()
        return jsonify({"success": True, "summary": summary})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1")
    print(f"✨ Odoo Ticket Hub iniciado en http://localhost:{port} (Debug: {debug_mode})")
    app.run(host="0.0.0.0", port=port, debug=debug_mode)

