import os
import json
import xmlrpc.client
import secrets
from datetime import timedelta, datetime
from flask import Flask, render_template, request, jsonify, session, Response
from flask_cors import CORS
from dotenv import load_dotenv
import requests
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
    env_ds_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    
    config = {
        "groq_api_key": env_ds_key if env_ds_key else os.environ.get("GROQ_API_KEY", ""),
        "groq_base_url": "https://api.deepseek.com" if env_ds_key else os.environ.get("GROQ_BASE_URL", ""),
        "groq_model": "deepseek-v4-flash" if env_ds_key else os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
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

def perform_ai_completion(api_key, base_url, model, messages, temperature=0.3, max_tokens=1000, response_format=None):
    """Execute AI completion: If DEEPSEEK_API_KEY exists in env, prioritize DeepSeek and ignore Groq."""
    env_deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    
    # 1. PRIORITY: If DEEPSEEK_API_KEY is defined in .env, use DeepSeek directly
    if env_deepseek_key:
        target_model = model if ("deepseek" in str(model).lower()) else "deepseek-v4-flash"
        try:
            return _call_openai_compatible(
                api_key=env_deepseek_key,
                base_url="https://api.deepseek.com",
                model=target_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format
            )
        except Exception as ds_err:
            print(f"⚠️ DeepSeek falló ({ds_err}).")
            # If user also has Groq configured, attempt Groq fallback
            if api_key and ("gsk_" in str(api_key) or not base_url):
                print("🔄 Reintentando con Groq como respaldo...")
                client = groq.Groq(api_key=api_key)
                extra = {"response_format": response_format} if response_format else {}
                c = client.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **extra
                )
                return c.choices[0].message.content
            raise ds_err

    # 2. STANDARD ROUTING: If no DEEPSEEK_API_KEY in env, use configured key/endpoint
    api_key = str(api_key or "").encode("ascii", "ignore").decode("ascii").strip()
    base_url = str(base_url or "").encode("ascii", "ignore").decode("ascii").strip()
    is_groq = (not base_url or "groq.com" in base_url)
    
    if is_groq:
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        client = groq.Groq(**kwargs)
        extra = {"response_format": response_format} if response_format else {}
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **extra
        )
        return completion.choices[0].message.content
    else:
        return _call_openai_compatible(
            api_key=api_key,
            base_url=base_url,
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format
        )


def _call_openai_compatible(api_key, base_url, model, messages, temperature=0.3, max_tokens=2500, response_format=None):
    """Execute completion against OpenAI-compatible REST API (DeepSeek, etc)."""
    api_key = str(api_key or "").encode("ascii", "ignore").decode("ascii").strip()
    base_url = str(base_url or "").encode("ascii", "ignore").decode("ascii").strip()

    clean_url = base_url.rstrip("/")
    if not clean_url.endswith("/chat/completions"):
        clean_url = f"{clean_url}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max(max_tokens, 2500)
    }
    if response_format:
        payload["response_format"] = response_format

    resp = requests.post(clean_url, headers=headers, json=payload, timeout=90)
    if resp.status_code != 200:
        err_msg = resp.text
        try:
            err_json = resp.json()
            if "error" in err_json:
                err_msg = err_json["error"].get("message", resp.text)
        except Exception:
            pass
        raise Exception(f"API Error ({resp.status_code}): {err_msg}")

    data = resp.json()
    msg_obj = data["choices"][0]["message"]
    content = msg_obj.get("content") or ""
    
    # If model only returned reasoning_content and empty content
    if not content.strip() and msg_obj.get("reasoning_content"):
        content = msg_obj.get("reasoning_content")

    return content



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
        api_key = config.get("groq_api_key", "").strip()
    if not base_url:
        base_url = config.get("groq_base_url", "").strip()

    # Clean any non-ascii characters from key/url if accidentally pasted
    api_key = api_key.encode('ascii', 'ignore').decode('ascii').strip()
    base_url = base_url.encode('ascii', 'ignore').decode('ascii').strip()

    if not api_key:
        return jsonify({"success": False, "error": "No se ha proporcionado una API Key válida."}), 400

    model = data.get("model") or config.get("groq_model", "openai/gpt-oss-120b")

    try:
        msg = perform_ai_completion(
            api_key=api_key,
            base_url=base_url,
            model=model,
            messages=[
                {"role": "system", "content": "You are a connectivity test assistant."},
                {"role": "user", "content": "Responde únicamente: 'Conexión a IA exitosa.'"}
            ],
            temperature=0.2,
            max_tokens=100
        )
        return jsonify({"success": True, "message": msg.strip()})
    except Exception as e:
        return jsonify({"success": False, "error": f"Error de conexión con la IA: {str(e)}"}), 500


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
            "error": "La IA no está configurada. Ve a Ajustes > Integraciones para ingresar tu API Key."
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
        ai_response = perform_ai_completion(
            api_key=api_key,
            base_url=base_url,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        return jsonify({
            "success": True,
            "analysis": ai_response.strip(),
            "model_used": model
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Error al procesar con IA: {str(e)}"}), 500


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

        total_days_sum = 0
        stage_counts = {
            "New": 0,
            "Work in Progress": 0,
            "Waiting for Customer": 0,
            "Waiting for Vendor": 0,
            "Solved": 0,
            "Closed": 0,
            "Archived": 0
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
            stage_name = stage_data[1] if stage_data else "Closed"
            
            # Match standard stage counts
            matched_stage = False
            for st_k in stage_counts.keys():
                if st_k.lower() in stage_name.lower():
                    stage_counts[st_k] += 1
                    matched_stage = True
                    break
            if not matched_stage:
                stage_counts["Closed"] += 1

            partner_data = t.get("partner_id")
            client_contact = partner_data[1] if partner_data else "Sin contacto"

            create_date_str = t.get("create_date") or ""
            end_date_str = t.get("close_date") or t.get("write_date") or create_date_str

            # Calculate calendar days
            days_spent = 1
            if create_date_str and end_date_str:
                try:
                    c_dt = datetime.strptime(create_date_str, "%Y-%m-%d %H:%M:%S")
                    e_dt = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S")
                    days_spent = max(1, round((e_dt - c_dt).total_seconds() / 86400))
                except Exception:
                    days_spent = 1
            total_days_sum += days_spent

            desc_clean = strip_html_tags(t.get("description", ""))

            # Extract real human conversation messages (comments and emails, exclude notifications, internal notes and bots)
            recent_notes = []
            try:
                msgs = models.execute_kw(
                    ODOO_DB,
                    uid,
                    password,
                    "mail.message",
                    "search_read",
                    [[
                        ["res_id", "=", ticket_id],
                        ["model", "=", "helpdesk.ticket"],
                        ["message_type", "in", ["comment", "email"]]
                    ]],
                    {"fields": ["author_id", "body", "date", "subtype_id"], "order": "id asc", "limit": 20}
                )

                for m in msgs:
                    # Skip internal log notes (subtype Note/Nota)
                    subtype_data = m.get("subtype_id")
                    subtype_name = (subtype_data[1] if subtype_data else "").lower()
                    if "nota" in subtype_name or "note" in subtype_name:
                        continue

                    b = strip_html_tags(m.get("body", ""))
                    author = m.get("author_id", ["", ""])[1] if m.get("author_id") else "Sistema"

                    # Skip bot auto-replies or empty text
                    if not b or "OdooBot" in author or "Archivos adjuntos" in b or len(b) < 6:
                        continue

                    # Clean email reply headers like "El vie, 28 ago... escribió:" or "On ... wrote:"
                    clean_b = re.split(r'El \w+,\s+\d+.*|On \w+,\s+\d+.*|<div data-o-mail-quote|--|Atentamente|Saludos cordiales', b, flags=re.IGNORECASE)[0].strip()
                    clean_b = clean_b.split("Ver documento")[0].split("Descargar")[0].strip()

                    if clean_b and len(clean_b) > 4:
                        recent_notes.append(f"{author}: {clean_b[:220]}")
            except Exception as msg_err:
                print(f"Error fetching chatter for ticket {ticket_id}: {msg_err}")

            odoo_url = f"{ODOO_URL}/web#id={ticket_id}&cids=1&menu_id=352&action=475&model=helpdesk.ticket&view_type=form"

            formatted_tickets.append({
                "id": ticket_id,
                "name": t.get("name") or "(Sin Asunto)",
                "type": type_name,
                "stage": stage_name,
                "contact": client_contact,
                "create_date": create_date_str,
                "end_date": end_date_str,
                "days_spent": days_spent,
                "hours_spent": hours,
                "description": desc_clean[:250],
                "notes": recent_notes[-3:], # Only top 3 clean messages
                "odoo_url": odoo_url
            })

        month_label = f"{MONTH_NAMES_ES[month]} de {year}"
        avg_days = round(total_days_sum / len(formatted_tickets)) if formatted_tickets else 0

        return jsonify({
            "success": True,
            "period": month_label,
            "month_name": MONTH_NAMES_ES[month],
            "year": year,
            "month": month,
            "total_tickets": len(formatted_tickets),
            "total_hours": round(total_hours, 2),
            "avg_days": avg_days,
            "stage_counts": stage_counts,
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
    model = config.get("groq_model", "openai/gpt-oss-120b")
    if not api_key:
        return jsonify({
            "success": False,
            "error": "Groq / DeepSeek IA no está configurado. Ve a Ajustes > Integraciones para ingresar tu API Key."
        }), 400

    data = request.get_json() or {}
    client_name = data.get("client_name", "Cliente")
    period_label = data.get("period_label", "este mes")
    tickets = data.get("tickets") or []

    if not tickets:
        return jsonify({"success": False, "error": "No hay tickets para generar el resumen."}), 400

    # Build tickets payload for Groq / DeepSeek
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
Genera la sección '1. RESUMEN DE SOPORTE' mensual para el cliente '{client_name}' del período '{period_label}'.

Datos estadísticos:
- Total casos aperturados en el mes: {len(tickets)}
- Desglose por tipo: {type_breakdown_str}

Casos registrados en Odoo con sus logs y notas de resolución:
{chr(10).join(tickets_prompt_list)}

Instrucciones estrictas:
1. 'section_header': Debe ser '1. RESUMEN DE SOPORTE'
2. 'intro': Un párrafo con el estilo: 'Durante el mes de {period_label} se aperturaron {len(tickets)} casos para {client_name}, {type_breakdown_str}, un breve resumen de ellos es el siguiente:'
3. 'tickets': Una lista ordenada donde para CADA ticket devuelves:
   - 'id': número de ID
   - 'title': título exacto del caso
   - 'summary': 1 o 2 párrafos ejecutivos, claros, en español neutro profesional, explicando exactamente la acción realizada o cómo quedó solucionado el caso según las notas y logs del ticket.

Responde ÚNICAMENTE en formato JSON válido con esta estructura:
{{
  "section_header": "1. RESUMEN DE SOPORTE",
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

    # Check if client requested streaming SSE
    is_stream = request.args.get("stream", "false").lower() in ("true", "1")

    if not is_stream:
        # Regular JSON response (backward compatibility)
        try:
            BATCH_SIZE = 15
            all_summaries = []
            intro_prompt = f"""
Genera únicamente la introducción ejecutiva del reporte de soporte para {client_name} del período {period_label}.
Datos:
- Total casos aperturados en el mes: {len(tickets)}
- Desglose por tipo: {type_breakdown_str}

Responde ÚNICAMENTE en JSON con formato:
{{"intro": "Durante el mes de {period_label} se aperturaron {len(tickets)} casos para {client_name}, {type_breakdown_str}, un breve resumen de ellos es el siguiente:"}}
"""
            intro_raw = perform_ai_completion(
                api_key=api_key,
                base_url=base_url,
                model=model,
                messages=[
                    {"role": "system", "content": "Eres un asistente experto que responde estrictamente en JSON válido."},
                    {"role": "user", "content": intro_prompt}
                ],
                temperature=0.2,
                max_tokens=600,
                response_format={"type": "json_object"}
            )
            try:
                intro_clean = intro_raw.strip()
                s_i = intro_clean.find("{")
                e_i = intro_clean.rfind("}")
                if s_i != -1 and e_i != -1:
                    intro_clean = intro_clean[s_i:e_i+1]
                intro_text = json.loads(intro_clean).get("intro", f"Durante el mes de {period_label} se aperturaron {len(tickets)} casos para {client_name}, {type_breakdown_str}, un breve resumen de ellos es el siguiente:")
            except Exception:
                intro_text = f"Durante el mes de {period_label} se aperturaron {len(tickets)} casos para {client_name}, {type_breakdown_str}, un breve resumen de ellos es el siguiente:"

            for i in range(0, len(tickets), BATCH_SIZE):
                chunk = tickets[i:i + BATCH_SIZE]
                chunk_prompt_list = []
                for c_idx, t in enumerate(chunk, i + 1):
                    ttype = t.get("type", "Requerimiento")
                    notes_str = "\n   - ".join(t.get("notes") or []) if t.get("notes") else "Sin notas adicionales."
                    desc_str = (t.get("description") or "Sin descripción provista.")[:200]
                    chunk_prompt_list.append(
                        f"{c_idx}. #{t['id']} - {t['name']} (Tipo: {ttype})\n"
                        f"   Descripción: {desc_str}\n"
                        f"   Notas/Logs: {notes_str[:300]}"
                    )

                batch_prompt = f"""
Genera el resumen de resolución de estos {len(chunk)} casos de soporte para {client_name}:
{chr(10).join(chunk_prompt_list)}

Para CADA ticket redacta 'summary' (1 o 2 líneas ejecutivas explicando la resolución según las notas/logs).
Responde ÚNICAMENTE en JSON con formato:
{{
  "tickets": [
    {{
      "id": {chunk[0]['id']},
      "title": "{chunk[0]['name'].replace('"', '')[:50]}",
      "summary": "Resumen claro y profesional..."
    }}
  ]
}}
"""
                batch_raw = perform_ai_completion(
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                    messages=[
                        {"role": "system", "content": "Eres un redactor técnico que responde estrictamente en JSON válido con la lista 'tickets'."},
                        {"role": "user", "content": batch_prompt}
                    ],
                    temperature=0.2,
                    max_tokens=2500,
                    response_format={"type": "json_object"}
                )

                b_clean = batch_raw.strip()
                s_idx = b_clean.find("{")
                e_idx = b_clean.rfind("}")
                if s_idx != -1 and e_idx != -1:
                    b_clean = b_clean[s_idx:e_idx+1]
                batch_data = json.loads(b_clean)
                all_summaries.extend(batch_data.get("tickets", []))

            return jsonify({
                "success": True,
                "report": {
                    "section_header": "1. RESUMEN DE SOPORTE",
                    "intro": intro_text,
                    "tickets": all_summaries
                },
                "model_used": model
            })
        except Exception as e:
            return jsonify({"success": False, "error": f"Error al generar informe con IA: {str(e)}"}), 500

    # STREAMING SSE MODE
    def generate_events():
        try:
            BATCH_SIZE = 15
            total_batches = (len(tickets) + BATCH_SIZE - 1) // BATCH_SIZE

            # Event 1: Starting
            yield f"data: {json.dumps({'type': 'start', 'total_tickets': len(tickets), 'total_batches': total_batches})}\n\n"

            # 1. Generate Intro
            yield f"data: {json.dumps({'type': 'step', 'message': 'Redactando introducción ejecutiva...', 'progress': 5})}\n\n"
            intro_prompt = f"""
Genera únicamente la introducción ejecutiva del reporte de soporte para {client_name} del período {period_label}.
Datos:
- Total casos aperturados en el mes: {len(tickets)}
- Desglose por tipo: {type_breakdown_str}

Responde ÚNICAMENTE en JSON con formato:
{{"intro": "Durante el mes de {period_label} se aperturaron {len(tickets)} casos para {client_name}, {type_breakdown_str}, un breve resumen de ellos es el siguiente:"}}
"""
            intro_text = f"Durante el mes de {period_label} se aperturaron {len(tickets)} casos para {client_name}, {type_breakdown_str}, un breve resumen de ellos es el siguiente:"
            try:
                intro_raw = perform_ai_completion(
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                    messages=[
                        {"role": "system", "content": "Eres un asistente experto que responde estrictamente en JSON válido."},
                        {"role": "user", "content": intro_prompt}
                    ],
                    temperature=0.2,
                    max_tokens=600,
                    response_format={"type": "json_object"}
                )
                intro_clean = intro_raw.strip()
                s_i = intro_clean.find("{")
                e_i = intro_clean.rfind("}")
                if s_i != -1 and e_i != -1:
                    intro_clean = intro_clean[s_i:e_i+1]
                intro_text = json.loads(intro_clean).get("intro", intro_text)
            except Exception:
                pass

            yield f"data: {json.dumps({'type': 'intro', 'intro': intro_text, 'progress': 15})}\n\n"

            # 2. Process in chunks and stream items as they finish
            processed_count = 0
            for batch_num, i in enumerate(range(0, len(tickets), BATCH_SIZE), 1):
                chunk = tickets[i:i + BATCH_SIZE]
                chunk_prompt_list = []
                for c_idx, t in enumerate(chunk, i + 1):
                    ttype = t.get("type", "Requerimiento")
                    notes_str = "\n   - ".join(t.get("notes") or []) if t.get("notes") else "Sin notas adicionales."
                    desc_str = (t.get("description") or "Sin descripción provista.")[:200]
                    chunk_prompt_list.append(
                        f"{c_idx}. #{t['id']} - {t['name']} (Tipo: {ttype})\n"
                        f"   Descripción: {desc_str}\n"
                        f"   Notas/Logs: {notes_str[:300]}"
                    )
                first_id = chunk[0].get("id")
                last_id = chunk[-1].get("id")
                step_msg = f"Analizando bloque {batch_num}/{total_batches} (tickets #{first_id} a #{last_id})..."
                step_pct = 15 + int((batch_num - 1) / total_batches * 80)
                yield f"data: {json.dumps({'type': 'step', 'message': step_msg, 'progress': step_pct})}\n\n"

                batch_prompt = f"""
Actúa como un consultor senior de soporte técnico redactando el informe mensual ejecutivo para {client_name}.
Analiza la solicitud y mensajes de resolución de cada uno de los siguientes {len(chunk)} casos:

{chr(10).join(chunk_prompt_list)}

INSTRUCCIÓN DE REDACCIÓN PARA CADA CASO:
- En 'summary' redacta un resumen ejecutivo en tiempo pasado (1 o 2 oraciones, estilo corporativo) que explique QUÉ SE SOLICITÓ y QUÉ SE HIZO o resolvió.
- NUNCA incluyas saludos informales ("hola", "saludos", "buenas"), ni nombres de personas, ni firmas de correos.
- Ejemplos del estilo esperado:
  * "Se habilitó el campo de Flows en la plataforma para la medición del BO tras la configuración técnica y confirmación del cliente."
  * "La cuenta de WhatsApp fue vinculada y los usuarios correspondientes quedaron activados en la plataforma SocialHub."
  * "Se atendió el requerimiento configurando los parámetros solicitados y validando el funcionamiento en el ambiente del cliente."

Responde ÚNICAMENTE en JSON con formato:
{{
  "tickets": [
    {{
      "id": {chunk[0]['id']},
      "title": "{chunk[0]['name'].replace('"', '')[:50]}",
      "summary": "Explicación clara de lo realizado o configurado..."
    }}
  ]
}}
"""
                batch_raw = perform_ai_completion(
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                    messages=[
                        {"role": "system", "content": "Eres un redactor técnico de soporte senior que redacta resúmenes ejecutivos en JSON estricto."},
                        {"role": "user", "content": batch_prompt}
                    ],
                    temperature=0.2,
                    max_tokens=2500,
                    response_format={"type": "json_object"}
                )

                batch_items = []
                try:
                    b_clean = batch_raw.strip()
                    s_idx = b_clean.find("{")
                    e_idx = b_clean.rfind("}")
                    if s_idx != -1 and e_idx != -1:
                        b_clean = b_clean[s_idx:e_idx+1]
                    batch_data = json.loads(b_clean)

                    # Check multiple common key names (tickets, casos, items, data)
                    for possible_key in ["tickets", "casos", "items", "data", "resumenes"]:
                        if isinstance(batch_data.get(possible_key), list) and batch_data.get(possible_key):
                            batch_items = batch_data[possible_key]
                            break

                    # If model returned a direct list
                    if not batch_items and isinstance(batch_data, list):
                        batch_items = batch_data
                except Exception as parse_err:
                    print(f"⚠️ Error parseando batch JSON: {parse_err}. Creando resúmenes estructurados de respaldo...")

                # Ensure EVERY ticket in the chunk has an entry with valid id, title and executive summary
                final_batch_items = []
                for t in chunk:
                    t_id = t.get("id")
                    matched = next((item for item in batch_items if str(item.get("id")) == str(t_id)), None)
                    
                    if matched and matched.get("summary") and len(matched.get("summary")) > 15 and not matched.get("summary").lower().startswith("hola"):
                        final_batch_items.append({
                            "id": t_id,
                            "title": matched.get("title") or t.get("name") or f"Caso #{t_id}",
                            "summary": matched.get("summary")
                        })
                    else:
                        # Clean synthesis from ticket description
                        desc = (t.get("description") or "").strip()
                        t_name = t.get("name") or "Requerimiento"
                        if desc and len(desc) > 10 and not desc.lower().startswith("hola"):
                            clean_desc = desc[:160].rstrip(".")
                            fallback_summary = f"Se gestionó la solicitud ({clean_desc}), completando la atención y validación correspondiente."
                        else:
                            fallback_summary = f"Se atendió y resolvió el requerimiento de {t_name} conforme a lo acordado con el cliente."

                        final_batch_items.append({
                            "id": t_id,
                            "title": t.get("name") or f"Caso #{t_id}",
                            "summary": fallback_summary
                        })

                processed_count += len(final_batch_items)

                # Stream these tickets to UI immediately
                pct = 15 + int((batch_num / total_batches) * 80)
                yield f"data: {json.dumps({'type': 'batch_tickets', 'items': final_batch_items, 'processed': processed_count, 'total': len(tickets), 'progress': pct})}\n\n"

            # Event: Finished
            yield f"data: {json.dumps({'type': 'done', 'progress': 100, 'message': 'Informe completado exitosamente'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return Response(generate_events(), mimetype="text/event-stream")


@app.route("/api/reports/regenerate-single-summary", methods=["POST"])
def regenerate_single_summary():
    sess_data = get_active_server_session()
    if not sess_data:
        return jsonify({"error": "No autorizado"}), 401

    config = load_integrations_config()
    api_key = config.get("groq_api_key")
    base_url = config.get("groq_base_url")
    if not api_key:
        return jsonify({"success": False, "error": "La IA no está configurada."}), 400

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
        summary = perform_ai_completion(
            api_key=api_key,
            base_url=base_url,
            model=model,
            messages=[
                {"role": "system", "content": "Eres un redactor técnico que resume casos en 1 párrafo claro."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=300
        )
        return jsonify({"success": True, "summary": summary.strip()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1")
    print(f"✨ Odoo Ticket Hub iniciado en http://localhost:{port} (Debug: {debug_mode})")
    app.run(host="0.0.0.0", port=port, debug=debug_mode)

