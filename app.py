import os
import json
import xmlrpc.client
import secrets
from datetime import timedelta, datetime
from flask import Flask, render_template, request, jsonify, session, redirect, make_response, send_from_directory
from dotenv import load_dotenv
import requests
import groq

load_dotenv()

try:
    from informes_web import puede_generar, registrar as registrar_informes  # noqa: E402 (después de load_dotenv)
except ModuleNotFoundError as e:
    raise SystemExit(
        f"Falta el módulo '{e.name}' (informe mensual). Arranca con el entorno del proyecto: "
        ".venv/bin/python app.py — o crea el entorno con: "
        "python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    ) from e

# Estado persistente: en Docker el volumen /app/data; en local, ./data
DATA_DIR = "/app/data" if os.path.isdir("/app/data") else os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)


def _secret_key():
    """FLASK_SECRET_KEY o una clave persistida en DATA_DIR, para que las sesiones sobrevivan a reinicios."""
    if os.environ.get("FLASK_SECRET_KEY"):
        return os.environ["FLASK_SECRET_KEY"]
    ruta = os.path.join(DATA_DIR, "flask_secret.txt")
    if not os.path.exists(ruta):
        with open(ruta, "w") as f:
            f.write(secrets.token_hex(32))
        os.chmod(ruta, 0o600)
    with open(ruta) as f:
        return f.read().strip()


app = Flask(__name__)
# Secret key for signing cookies
app.secret_key = _secret_key()

# Enhanced Session Cookie Security
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=6),
    TEMPLATES_AUTO_RELOAD=True,
)

ODOO_URL = os.environ.get("ODOO_URL", "https://esmtcx.odoo.com").rstrip("/")
ODOO_DB = os.environ.get("ODOO_DB", "esmtcx")
ODOO_USER = os.environ.get("ODOO_USER", "")
ODOO_PASSWORD = os.environ.get("ODOO_PASSWORD", "")

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


# In-memory cache for helpdesk tags to avoid repetitive network overhead
TAGS_CACHE = {"data": {}, "expires": datetime.min}


def get_helpdesk_tags_map(models, uid, password):
    """Fetch and cache helpdesk.tag records (id -> {id, name, color}) for 10 minutes."""
    global TAGS_CACHE
    now = datetime.utcnow()
    if TAGS_CACHE["data"] and now < TAGS_CACHE["expires"]:
        return TAGS_CACHE["data"]
    try:
        tags = models.execute_kw(
            ODOO_DB, uid, password,
            "helpdesk.tag", "search_read",
            [[]],
            {"fields": ["id", "name", "color"]}
        )
        tag_map = {t["id"]: {"id": t["id"], "name": t["name"], "color": t.get("color", 0)} for t in tags}
        TAGS_CACHE = {"data": tag_map, "expires": now + timedelta(minutes=10)}
        return tag_map
    except Exception as e:
        print(f"Error fetching helpdesk.tag map: {e}")
        return TAGS_CACHE.get("data", {})


def resolve_ticket_type(ticket, tag_map=None):
    """
    Determine ticket type.
    In Odoo <18: ticket_type_id was a Many2one field.
    In Odoo >=18/19: ticket_type_id was deprecated/removed and types are stored in tag_ids ('Request', 'Incident', 'Change', etc.).
    """
    # 1. Legacy Many2one field if present in ticket dictionary
    tt_val = ticket.get("ticket_type_id")
    if tt_val:
        raw_name = tt_val[1] if isinstance(tt_val, (list, tuple)) and len(tt_val) > 1 else str(tt_val)
        low = raw_name.lower()
        if "inciden" in low:
            return "Incidente"
        if "cambio" in low or "change" in low:
            return "Cambio"
        if "problema" in low or "problem" in low:
            return "Problema"
        if "soporte" in low or "support" in low:
            return "Soporte"
        if "pregunta" in low or "question" in low:
            return "Pregunta"
        if "request" in low or "requerim" in low:
            return "Requerimiento"
        return raw_name

    # 2. Check tags (Odoo 18/19 pattern)
    tag_ids = ticket.get("tag_ids") or []
    if tag_map and tag_ids:
        for tid in tag_ids:
            tag_info = tag_map.get(tid)
            if not tag_info:
                continue
            tname = tag_info.get("name", "")
            low = tname.lower().strip()
            if "inciden" in low:
                return "Incidente"
            if "cambio" in low or "change" in low:
                return "Cambio"
            if "problema" in low or "problem" in low:
                return "Problema"
            if "soporte" in low or "support" in low:
                return "Soporte"
            if "pregunta" in low or "question" in low:
                return "Pregunta"
            if "request" in low or "requerim" in low:
                return "Requerimiento"

    return "Requerimiento"



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
            "puede_informes": puede_generar(sess_data),
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

    # Solo usuarios internos: Odoo también autentica por XML-RPC a usuarios portal (clientes).
    try:
        user_res = models.execute_kw(
            ODOO_DB,
            uid,
            password,
            "res.users",
            "read",
            [[uid]],
            {"fields": ["name", "email", "share"]}
        )
    except Exception as e:
        print(f"No se pudo verificar el usuario {uid} en Odoo: {e}")
        return jsonify({"success": False, "error": "No se pudo verificar el usuario en Odoo"}), 502
    if not user_res or user_res[0].get("share"):
        return jsonify({"success": False, "error": "Solo pueden entrar usuarios internos de Odoo"}), 403
    user_name = user_res[0].get("name") or username
    user_email = user_res[0].get("email") or ""

    # Generate secure random session ID (Server-Side Session)
    sid = secrets.token_urlsafe(32)
    session.permanent = True
    session["sid"] = sid

    SERVER_SESSIONS[sid] = {
        "uid": uid,
        "user": username,
        "email": user_email,
        "password": password,
        "name": user_name,
        "expires": datetime.utcnow() + timedelta(hours=6)
    }

    return jsonify({
        "success": True,
        "user": username,
        "name": user_name,
        "uid": uid,
        "puede_informes": puede_generar(SERVER_SESSIONS[sid])
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
            "team_id",
            "kanban_state",
            "tag_ids"
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

        tag_map = get_helpdesk_tags_map(models, uid, password)

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

            ticket_type = resolve_ticket_type(t, tag_map)

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
    if not get_active_server_session():
        return jsonify({"error": "No autorizado"}), 401
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
    sess_data = get_active_server_session()
    if not sess_data:
        return jsonify({"error": "No autorizado"}), 401
    if not puede_generar(sess_data):
        return jsonify({"success": False, "error": "Tu usuario no puede cambiar las integraciones (INFORMES_USUARIOS)."}), 403
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
    if not get_active_server_session():
        return jsonify({"error": "No autorizado"}), 401
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
# EXECUTIVE REPORT (DIAPOSITIVAS) ENDPOINTS
# El informe mensual por cliente está en informes_web.py
# ==========================================

MONTH_NAMES_ES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]


def get_auth_connection():
    """Returns (uid, password, models, user_name) from the logged-in session (no env fallback)."""
    sess_data = get_active_server_session()
    if sess_data:
        uid = sess_data["uid"]
        pwd = sess_data["password"]
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)
        return uid, pwd, models, sess_data.get("name", "Usuario")
    return None, None, None, None


@app.route("/api/executive/filters", methods=["GET"])
def get_executive_filters():
    uid, pwd, models, _ = get_auth_connection()
    if not uid:
        return jsonify({"error": "No autorizado"}), 401

    try:
        # 1. Active Helpdesk Teams
        teams = models.execute_kw(
            ODOO_DB, uid, pwd,
            "helpdesk.team", "search_read",
            [[["active", "=", True]]],
            {"fields": ["id", "name"], "order": "name asc"}
        )
        
        # 2. Partners that have tickets
        partners = []
        try:
            partner_groups = models.execute_kw(
                ODOO_DB, uid, pwd,
                "helpdesk.ticket", "read_group",
                [[["partner_id", "!=", False]], ["partner_id"], ["partner_id"]],
                {"limit": 100, "orderby": "partner_id_count desc"}
            )
            seen_ids = set()
            for g in partner_groups:
                p_info = g.get("partner_id")
                if p_info and p_info[0] not in seen_ids:
                    seen_ids.add(p_info[0])
                    partners.append({
                        "id": p_info[0],
                        "name": p_info[1],
                        "tickets_count": g.get("partner_id_count", 0)
                    })
            partners.sort(key=lambda x: x["name"].lower())
        except Exception:
            raw_partners = models.execute_kw(
                ODOO_DB, uid, pwd,
                "res.partner", "search_read",
                [[["customer_rank", ">", 0]]],
                {"fields": ["id", "name"], "limit": 80, "order": "name asc"}
            )
            partners = [{"id": p["id"], "name": p["name"], "tickets_count": 0} for p in raw_partners]

        return jsonify({
            "success": True,
            "teams": teams,
            "partners": partners
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/executive/data", methods=["GET"])
def get_executive_report_data():
    uid, pwd, models, _ = get_auth_connection()
    if not uid:
        return jsonify({"error": "No autorizado"}), 401

    try:
        filter_type = request.args.get("filter_type", "team").lower()
        filter_id = int(request.args.get("filter_id", 0))
        start_date = request.args.get("start_date", "").strip()
        end_date = request.args.get("end_date", "").strip()
        contract_hours = float(request.args.get("contract_hours", 1200.0) or 1200.0)

        now = datetime.now()
        if not start_date:
            start_date = f"{now.year:04d}-{now.month:02d}-01"
        if not end_date:
            end_date = now.strftime("%Y-%m-%d")

        start_dt_str = f"{start_date} 00:00:00"
        end_dt_str = f"{end_date} 23:59:59"

        # Resolve entity name and team logo
        entity_name = "Cliente / Helpdesk"
        has_team_logo = False
        team_logo_url = None

        if filter_type == "partner":
            partner_res = models.execute_kw(
                ODOO_DB, uid, pwd,
                "res.partner", "read",
                [[filter_id]],
                {"fields": ["name", "image_128"]}
            )
            if partner_res:
                entity_name = partner_res[0].get("name", "Cliente")
                if partner_res[0].get("image_128"):
                    has_team_logo = True
                    team_logo_url = f"{ODOO_URL}/web/image?model=res.partner&id={filter_id}&field=image_128"
            domain_filter = ["|", ("partner_id", "=", filter_id), ("commercial_partner_id", "=", filter_id)]
        else:
            team_res = models.execute_kw(
                ODOO_DB, uid, pwd,
                "helpdesk.team", "read",
                [[filter_id]],
                {"fields": ["name", "x_studio_logo"]}
            )
            if team_res:
                entity_name = team_res[0].get("name", "Equipo Helpdesk")
                if team_res[0].get("x_studio_logo"):
                    has_team_logo = True
                    team_logo_url = f"/api/team_logo/{filter_id}"
            domain_filter = [("team_id", "=", filter_id)]

        domain = domain_filter + [
            ("create_date", ">=", start_dt_str),
            ("create_date", "<=", end_dt_str)
        ]

        fields = [
            "id", "name", "stage_id", "priority",
            "create_date", "close_date", "write_date", "total_hours_spent",
            "timesheet_ids", "user_id", "partner_id", "team_id", "description", "tag_ids"
        ]

        tickets = models.execute_kw(
            ODOO_DB, uid, pwd,
            "helpdesk.ticket", "search_read",
            [domain],
            {"fields": fields, "order": "id asc"}
        )

        # Batch-read tags for executive report
        all_tag_ids_exec = list({tid for t in tickets for tid in (t.get("tag_ids") or [])})
        tag_map_exec = {}
        if all_tag_ids_exec:
            try:
                tag_records_exec = models.execute_kw(
                    ODOO_DB, uid, pwd,
                    "helpdesk.tag", "read",
                    [all_tag_ids_exec],
                    {"fields": ["id", "name", "color"]}
                )
                for tr in tag_records_exec:
                    tag_map_exec[tr["id"]] = {"id": tr["id"], "name": tr["name"], "color": tr.get("color", 0)}
            except Exception as tag_err:
                print(f"Error reading tags (executive): {tag_err}")

        # Collect timesheet details
        all_ts_ids = []
        for t in tickets:
            all_ts_ids.extend(t.get("timesheet_ids") or [])

        timesheets_by_ticket = {}
        collaborator_hours = {}
        collaborator_tickets = {}

        if all_ts_ids:
            try:
                timesheet_records = models.execute_kw(
                    ODOO_DB, uid, pwd,
                    "account.analytic.line", "read",
                    [all_ts_ids],
                    {"fields": ["id", "user_id", "employee_id", "unit_amount", "name", "date", "helpdesk_ticket_id"]}
                )
                for ts in timesheet_records:
                    t_info = ts.get("helpdesk_ticket_id")
                    t_id = t_info[0] if t_info else 0
                    if t_id not in timesheets_by_ticket:
                        timesheets_by_ticket[t_id] = []
                    timesheets_by_ticket[t_id].append(ts)

                    u_info = ts.get("user_id") or ts.get("employee_id")
                    u_name = u_info[1] if u_info else "Sin Asignar"
                    hrs = float(ts.get("unit_amount") or 0.0)

                    collaborator_hours[u_name] = collaborator_hours.get(u_name, 0.0) + hrs
                    if u_name not in collaborator_tickets:
                        collaborator_tickets[u_name] = set()
                    if t_id:
                        collaborator_tickets[u_name].add(t_id)
            except Exception as ts_err:
                print(f"Error reading timesheets: {ts_err}")

        # If no timesheets found, fallback to ticket.user_id and ticket.total_hours_spent
        if not collaborator_hours:
            for t in tickets:
                u_info = t.get("user_id")
                u_name = u_info[1] if u_info else "Sin Asignar"
                hrs = float(t.get("total_hours_spent") or 0.0)
                collaborator_hours[u_name] = collaborator_hours.get(u_name, 0.0) + hrs
                if u_name not in collaborator_tickets:
                    collaborator_tickets[u_name] = set()
                collaborator_tickets[u_name].add(t["id"])

        type_counts = {}
        total_days_sum = 0
        max_days = 0
        longest_ticket = None
        closed_count = 0

        stage_counts = {
            "Closed": 0,
            "Waiting Customer": 0,
            "Work in Progress": 0,
            "Solved": 0,
            "New": 0
        }

        formatted_tickets = []
        total_hours_spent_calc = 0.0

        for t in tickets:
            t_id = t["id"]
            type_name = resolve_ticket_type(t, tag_map_exec)
            type_counts[type_name] = type_counts.get(type_name, 0) + 1

            stage_data = t.get("stage_id")
            stage_name = stage_data[1] if stage_data else "Closed"
            stage_lower = stage_name.lower()

            # Categorize stage
            if "wait" in stage_lower or "espera" in stage_lower or "customer" in stage_lower:
                stage_category = "Waiting Customer"
                stage_counts["Waiting Customer"] += 1
            elif "progress" in stage_lower or "progreso" in stage_lower or "work" in stage_lower or "wip" in stage_lower:
                stage_category = "Work in Progress"
                stage_counts["Work in Progress"] += 1
            elif "solved" in stage_lower or "resuelto" in stage_lower:
                stage_category = "Solved"
                stage_counts["Solved"] += 1
            elif "new" in stage_lower or "nuevo" in stage_lower:
                stage_category = "New"
                stage_counts["New"] += 1
            else:
                stage_category = "Closed"
                stage_counts["Closed"] += 1

            if stage_category in ("Closed", "Solved"):
                closed_count += 1

            # Resolution days
            c_date_str = t.get("create_date") or ""
            end_date_str = t.get("close_date") or t.get("write_date") or c_date_str
            days_spent = 1
            if c_date_str and end_date_str:
                try:
                    c_dt = datetime.strptime(c_date_str, "%Y-%m-%d %H:%M:%S")
                    e_dt = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S")
                    days_spent = max(1, round((e_dt - c_dt).total_seconds() / 86400))
                except Exception:
                    days_spent = 1

            total_days_sum += days_spent
            if days_spent > max_days:
                max_days = days_spent
                longest_ticket = {
                    "id": t_id,
                    "name": t.get("name") or "(Sin Asunto)",
                    "days": days_spent
                }

            # Hours spent on this ticket
            ts_list = timesheets_by_ticket.get(t_id, [])
            if ts_list:
                t_hours = sum(float(x.get("unit_amount") or 0.0) for x in ts_list)
            else:
                t_hours = float(t.get("total_hours_spent") or 0.0)
            total_hours_spent_calc += t_hours

            # Primary collaborator for this ticket
            collab_str = "Sin asignar"
            if ts_list:
                collab_names = list({(x.get("user_id") or x.get("employee_id") or [0, ""])[1] for x in ts_list if (x.get("user_id") or x.get("employee_id"))})
                collab_str = ", ".join(filter(None, collab_names)) or "Equipo"
            elif t.get("user_id"):
                collab_str = t["user_id"][1]

            partner_data = t.get("partner_id")
            contact_str = partner_data[1] if partner_data else "Cliente"

            odoo_url = f"{ODOO_URL}/web#id={t_id}&cids=1&menu_id=352&action=475&model=helpdesk.ticket&view_type=form"

            ticket_tags_exec = [tag_map_exec[tid] for tid in (t.get("tag_ids") or []) if tid in tag_map_exec]

            formatted_tickets.append({
                "id": t_id,
                "name": t.get("name") or "(Sin Asunto)",
                "type": type_name,
                "stage": stage_name,
                "stage_category": stage_category,
                "contact": contact_str,
                "collaborator": collab_str,
                "create_date": c_date_str,
                "end_date": end_date_str,
                "days_spent": days_spent,
                "hours_spent": round(t_hours, 2),
                "unit_amount": round(t_hours, 2),
                "tags": ticket_tags_exec,
                "odoo_url": odoo_url
            })

        total_cases = len(tickets)
        total_hours_spent = round(total_hours_spent_calc, 2)
        total_hours_remaining = round(max(0.0, contract_hours - total_hours_spent), 2)
        utilization_pct = round((total_hours_spent / contract_hours * 100), 2) if contract_hours > 0 else 0.0
        availability_pct = round((total_hours_remaining / contract_hours * 100), 2) if contract_hours > 0 else 0.0
        closed_pct = round((closed_count / total_cases * 100), 1) if total_cases > 0 else 0.0
        avg_days = round(total_days_sum / total_cases) if total_cases > 0 else 0

        # Collaborator details list (No quotas assigned to technicians, only consumed hours and % of effort)
        collab_rows = []
        for name, used_h in sorted(collaborator_hours.items(), key=lambda x: x[1], reverse=True):
            pct_effort = round((used_h / total_hours_spent * 100), 2) if total_hours_spent > 0 else 0.0
            t_count = len(collaborator_tickets.get(name, []))
            collab_rows.append({
                "name": name,
                "hours_used": round(used_h, 2),
                "pct_of_total_used": pct_effort,
                "tickets_count": t_count
            })

        # Type distribution formatted
        type_dist = []
        for t_name in ["Requerimientos", "Incidente", "Cambio", "Problema", "Preguntas"]:
            cnt = type_counts.get(t_name, 0)
            if t_name == "Requerimientos" and cnt == 0:
                cnt = type_counts.get("Requerimiento", 0)
            if cnt > 0 or t_name in ["Requerimientos", "Incidente", "Cambio"]:
                pct = round((cnt / total_cases * 100), 1) if total_cases > 0 else 0.0
                type_dist.append({"type": t_name, "count": cnt, "pct": pct})

        # Stage distribution formatted
        stage_dist = [
            {"stage": "Closed", "label": "Closed", "count": stage_counts["Closed"], "pct": round(stage_counts["Closed"]/total_cases*100, 1) if total_cases else 0, "color": "#14b8a6"},
            {"stage": "Waiting Customer", "label": "Waiting Customer", "count": stage_counts["Waiting Customer"], "pct": round(stage_counts["Waiting Customer"]/total_cases*100, 1) if total_cases else 0, "color": "#f59e0b"},
            {"stage": "Work in Progress", "label": "Work in Progress / New / Solved", "count": stage_counts["Work in Progress"] + stage_counts["New"] + stage_counts["Solved"], "pct": round((stage_counts["Work in Progress"] + stage_counts["New"] + stage_counts["Solved"])/total_cases*100, 1) if total_cases else 0, "color": "#3b82f6"}
        ]

        # Monthly History (Image 2 replica: "CASOS MES A MES")
        monthly_history = []
        try:
            ref_dt = datetime.strptime(start_date, "%Y-%m-%d")
            year_start = f"{ref_dt.year:04d}-01-01 00:00:00"
            year_end = f"{ref_dt.year:04d}-12-31 23:59:59"
            h_domain = domain_filter + [
                ("create_date", ">=", year_start),
                ("create_date", "<=", year_end)
            ]
            hist_tickets = models.execute_kw(
                ODOO_DB, uid, pwd,
                "helpdesk.ticket", "search_read",
                [h_domain],
                {"fields": ["id", "create_date", "tag_ids"]}
            )
            by_month = {}
            for ht in hist_tickets:
                c_d = ht.get("create_date")
                if c_d:
                    m_int = int(c_d[5:7])
                    tt = resolve_ticket_type(ht, tag_map_exec).lower()
                    cat = "Incidente" if "inciden" in tt else ("Cambio" if "cambio" in tt or "change" in tt else "Requerimiento")
                    if m_int not in by_month:
                        by_month[m_int] = {"Incidente": 0, "Requerimiento": 0, "Cambio": 0, "Total": 0}
                    by_month[m_int][cat] += 1
                    by_month[m_int]["Total"] += 1

            for m_idx in sorted(by_month.keys()):
                m_label = MONTH_NAMES_ES[m_idx] if 1 <= m_idx <= 12 else f"Mes {m_idx}"
                m_data = by_month[m_idx]
                monthly_history.append({
                    "month": m_label,
                    "month_num": m_idx,
                    "incidents": m_data["Incidente"],
                    "requests": m_data["Requerimiento"],
                    "changes": m_data["Cambio"],
                    "total": m_data["Total"]
                })
        except Exception as hist_err:
            print(f"Error building monthly history: {hist_err}")

        # Human period label
        try:
            p_s = datetime.strptime(start_date, "%Y-%m-%d")
            p_e = datetime.strptime(end_date, "%Y-%m-%d")
            if p_s.month == p_e.month and p_s.year == p_e.year:
                period_label = f"{p_s.day:02d} al {p_e.day:02d} de {MONTH_NAMES_ES[p_s.month].lower()} de {p_s.year}"
                period_month = f"{MONTH_NAMES_ES[p_s.month]} {p_s.year}"
            else:
                period_label = f"{p_s.strftime('%d/%m/%Y')} al {p_e.strftime('%d/%m/%Y')}"
                period_month = f"{MONTH_NAMES_ES[p_s.month]} - {MONTH_NAMES_ES[p_e.month]} {p_e.year}"
        except Exception:
            period_label = f"{start_date} al {end_date}"
            period_month = start_date

        return jsonify({
            "success": True,
            "entity_name": entity_name,
            "filter_type": filter_type,
            "filter_id": filter_id,
            "has_team_logo": has_team_logo,
            "team_logo_url": team_logo_url,
            "esmt_logo_url": "/api/esmt_logo",
            "start_date": start_date,
            "end_date": end_date,
            "period_label": period_label,
            "period_month": period_month,
            "kpis": {
                "total_cases": total_cases,
                "closed_cases": closed_count,
                "closed_pct": closed_pct,
                "total_hours_available": contract_hours,
                "total_hours_used": total_hours_spent,
                "total_hours_remaining": total_hours_remaining,
                "utilization_pct": utilization_pct,
                "availability_pct": availability_pct,
                "avg_resolution_days": avg_days,
                "max_resolution_days": max_days,
                "longest_ticket": longest_ticket or {"id": 0, "name": "-", "days": 0}
            },
            "collaborators": collab_rows,
            "collaborator_totals": {
                "total_available": contract_hours,
                "total_used": total_hours_spent,
                "total_remaining": total_hours_remaining,
                "overall_utilization_pct": utilization_pct
            },
            "type_distribution": type_dist,
            "stage_distribution": stage_dist,
            "monthly_history": monthly_history,
            "tickets": formatted_tickets
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/team_logo/<int:team_id>", methods=["GET"])
def get_team_logo(team_id):
    """Serve team logo directly as PNG with caching, or redirect to Odoo."""
    uid, pwd, models, _ = get_auth_connection()
    if uid and models:
        try:
            res = models.execute_kw(
                ODOO_DB, uid, pwd,
                "helpdesk.team", "read",
                [[team_id]],
                {"fields": ["x_studio_logo"]}
            )
            if res and res[0].get("x_studio_logo"):
                import base64
                img_bytes = base64.b64decode(res[0]["x_studio_logo"])
                resp = make_response(img_bytes)
                resp.headers.set("Content-Type", "image/png")
                resp.headers.set("Cache-Control", "public, max-age=86400")
                return resp
        except Exception as e:
            print(f"Error fetching team logo for {team_id}: {e}")
    return redirect(f"{ODOO_URL}/web/image?model=helpdesk.team&id={team_id}&field=x_studio_logo")


@app.route("/api/esmt_logo", methods=["GET"])
def get_esmt_logo():
    """Serve official ESMT logo directly as PNG."""
    return send_from_directory(os.path.join(app.root_path, "static", "img"), "company_logo.png", mimetype="image/png")


registrar_informes(app, get_active_server_session, DATA_DIR)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1")
    print(f"✨ Odoo Ticket Hub iniciado en http://localhost:{port} (Debug: {debug_mode})")
    app.run(host="0.0.0.0", port=port, debug=debug_mode)

