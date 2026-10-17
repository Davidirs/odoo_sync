"""Informe mensual por cliente dentro de odoo_sync.

Usa el generador de informes_mensuales/ (paquete `informes`): datos de Odoo, License Manager y
status.mypurecloud.com, redacción con DeepSeek, Word con la plantilla ESMT y PDF con LibreOffice.
La generación tarda de 1 a 3 minutos: corre en un hilo de fondo (de uno en uno) y el avance se
sigue por SSE.

Persistencia en DATA_DIR (en Docker, el volumen /app/data):
  informes_clientes.json        helpdesk de Odoo → organización de Genesys Cloud y empresas a excluir
  informes/AAAA-MM/<CODIGO>/    datos.json, textos.json, revision.json, .docx y .pdf de cada informe
"""
import json
import os
import queue
import re
import threading
import traceback
import unicodedata
import uuid
import xmlrpc.client
from datetime import date, datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Blueprint, Response, jsonify, request, send_file

from informes.config import MESES, Cliente, carpeta_informe, config_desde_entorno, leer_clientes_yaml
from informes.generador import generar, guardar_textos, leer_json

bp = Blueprint("informes", __name__)
MES_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
CAMPOS_CLIENTE = ("codigo", "nombre", "genesys_org", "excluir_empresas", "region_genesys", "logo")

_ctx = {}  # sesion_activa, data_dir: los pone registrar()
_candado_clientes = threading.Lock()


def registrar(app, sesion_activa, data_dir):
    _ctx.update(sesion_activa=sesion_activa, data_dir=Path(data_dir))
    app.register_blueprint(bp)


# ------------------------------------------------------------------ acceso
def usuarios_informes():
    return {u.strip().lower() for u in (os.getenv("INFORMES_USUARIOS") or "").split(",") if u.strip()}


def puede_generar(sesion):
    lista = usuarios_informes()
    return bool(sesion) and bool({(sesion.get("user") or "").lower(), (sesion.get("email") or "").lower()} & lista)


def requiere_sesion(generar_informes=False):
    def decorador(f):
        @wraps(f)
        def envoltura(*args, **kwargs):
            sesion = _ctx["sesion_activa"]()
            if not sesion:
                return jsonify({"success": False, "error": "No autorizado. Inicia sesión."}), 401
            if generar_informes and not puede_generar(sesion):
                return jsonify({"success": False, "error": "Tu usuario no está autorizado para generar o editar informes "
                                                          "(INFORMES_USUARIOS)."}), 403
            return f(sesion, *args, **kwargs)
        return envoltura
    return decorador


# ------------------------------------------------------------------ configuración
def _salida():
    return _ctx["data_dir"] / "informes"


def config_informes():
    return config_desde_entorno(salida_dir=_salida(), ia_provider="deepseek")


def _ruta_clientes():
    return _ctx["data_dir"] / "informes_clientes.json"


def leer_clientes():
    """{team_id(str): {...}}. La primera vez se precarga desde informes_mensuales/clientes.yaml."""
    ruta = _ruta_clientes()
    with _candado_clientes:
        if not ruta.exists():
            clientes, _ = leer_clientes_yaml()
            datos = {str(c.odoo_team_id): {k: getattr(c, k) for k in CAMPOS_CLIENTE} for c in clientes}
            _guardar_clientes(datos)
        return json.loads(ruta.read_text(encoding="utf-8"))


def _guardar_clientes(datos):
    ruta = _ruta_clientes()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ruta)


def codigo_desde_nombre(nombre, team_id):
    base = unicodedata.normalize("NFKD", nombre or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", "_", base.upper()).strip("_") or f"HELPDESK_{team_id}"


def cliente_de(team_id, nombre_odoo, guardados):
    g = guardados.get(str(team_id)) or {}
    return Cliente(codigo=g.get("codigo") or codigo_desde_nombre(nombre_odoo, team_id),
                   nombre=g.get("nombre") or nombre_odoo, odoo_team_id=int(team_id),
                   genesys_org=g.get("genesys_org") or "", region_genesys=g.get("region_genesys") or "",
                   logo=g.get("logo") or "", excluir_empresas=list(g.get("excluir_empresas") or []))


def _equipos(sesion, ids=None):
    """Helpdesks activos de Odoo con las credenciales del usuario que consulta."""
    modelos = xmlrpc.client.ServerProxy(f"{os.environ.get('ODOO_URL', '').rstrip('/')}/xmlrpc/2/object", allow_none=True)
    dominio = [["active", "=", True]] + ([["id", "in", ids]] if ids else [])
    return modelos.execute_kw(os.environ.get("ODOO_DB", ""), sesion["uid"], sesion["password"], "helpdesk.team",
                              "search_read", [dominio], {"fields": ["id", "name"], "order": "name asc"})


def _mes(valor):
    if not MES_RE.match(valor or ""):
        raise ValueError("Mes inválido (AAAA-MM).")
    anio, mes = map(int, valor.split("-"))
    return anio, mes


def _mes_anterior():
    hoy = date.today()
    return f"{hoy.year - (hoy.month == 1):04d}-{(hoy.month - 2) % 12 + 1:02d}"


def _pdf_disponible():
    try:
        from informes.pdf import _soffice
        _soffice()
        return True
    except RuntimeError:
        return False


# ------------------------------------------------------------------ trabajos en segundo plano
class Trabajo:
    def __init__(self, team_id, mes, usuario, tipo, **opciones):
        self.id = uuid.uuid4().hex
        self.team_id, self.mes, self.usuario, self.tipo, self.opciones = team_id, mes, usuario, tipo, opciones
        self.eventos, self.terminado = [], False
        self.cond = threading.Condition()

    def emitir(self, tipo, **datos):
        with self.cond:
            self.eventos.append({"tipo": tipo, **datos})
            if tipo in ("fin", "error"):
                self.terminado = True
            self.cond.notify_all()


TRABAJOS = {}
_cola = queue.Queue()
_hilo = {"t": None}
_candado_cola = threading.Lock()


def _trabajo_activo(team_id, mes):
    return next((t for t in TRABAJOS.values() if t.team_id == team_id and t.mes == mes and not t.terminado), None)


def encolar(trabajo):
    with _candado_cola:
        TRABAJOS[trabajo.id] = trabajo
        if _hilo["t"] is None or not _hilo["t"].is_alive():
            _hilo["t"] = threading.Thread(target=_procesar_cola, name="informes", daemon=True)
            _hilo["t"].start()
        antes = sum(1 for t in TRABAJOS.values() if not t.terminado and t is not trabajo)
        trabajo.emitir("cola", mensaje=f"En cola ({antes} antes)" if antes else "Iniciando", pct=0)
        _cola.put(trabajo)


def _procesar_cola():
    while True:
        trabajo = _cola.get()
        try:
            _ejecutar(trabajo)
        except Exception as e:
            traceback.print_exc()
            trabajo.emitir("error", error=str(e) or e.__class__.__name__)
        finally:
            _cola.task_done()


ETAPAS_POR_TIPO = {"generar": ("datos", "textos", "docx", "pdf"), "redactar": ("textos", "docx", "pdf"), "renderizar": ("docx", "pdf")}


def _ejecutar(trabajo):
    anio, mes = _mes(trabajo.mes)
    cfg = config_informes()
    guardados = leer_clientes()
    cliente = cliente_de(trabajo.team_id, trabajo.opciones.get("nombre_odoo") or "", guardados)
    sin_lic = bool(trabajo.opciones.get("sin_licenciamiento"))
    carpeta = carpeta_informe(cfg, anio, mes, cliente)
    if trabajo.tipo != "generar" and not (carpeta / "datos.json").exists():
        raise RuntimeError("Primero hay que generar el informe de ese mes.")

    def avance(mensaje, pct=None):
        trabajo.emitir("avance", mensaje=mensaje, pct=pct)

    r = generar(cfg, cliente, anio, mes, ETAPAS_POR_TIPO[trabajo.tipo], rehacer_textos=trabajo.tipo in ("generar", "redactar"),
                licenciamiento=not sin_lic, avance=avance)
    web = leer_json(carpeta / "_web.json") or {}
    web.update({"ultimo": trabajo.tipo, "por": trabajo.usuario, "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    if trabajo.tipo == "generar":
        web.update({"generado_por": trabajo.usuario, "generado": web["fecha"], "sin_licenciamiento": sin_lic})
    (carpeta / "_web.json").write_text(json.dumps(web, ensure_ascii=False, indent=2), encoding="utf-8")
    trabajo.emitir("fin", estado={k: v for k, v in r.items() if k not in ("datos", "carpeta")}, pct=100)


# ------------------------------------------------------------------ rutas
@bp.route("/api/informes/clientes", methods=["GET"])
@requiere_sesion()
def listar_clientes(sesion):
    try:
        anio, mes = _mes(request.args.get("mes") or _mes_anterior())
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    try:
        equipos = _equipos(sesion)
    except Exception as e:
        return jsonify({"success": False, "error": f"No se pudieron leer los helpdesks de Odoo: {e}"}), 502
    cfg = config_informes()
    guardados = leer_clientes()
    filas = []
    for eq in equipos:
        c = cliente_de(eq["id"], eq["name"], guardados)
        carpeta = carpeta_informe(cfg, anio, mes, c)
        activo = _trabajo_activo(eq["id"], f"{anio:04d}-{mes:02d}")
        filas.append({
            "team_id": eq["id"], "helpdesk": eq["name"], "configurado": str(eq["id"]) in guardados,
            "codigo": c.codigo, "nombre": c.nombre, "genesys_org": c.genesys_org, "excluir_empresas": c.excluir_empresas,
            "estado": leer_json(carpeta / "_estado.json"), "web": leer_json(carpeta / "_web.json"),
            "trabajo": activo.id if activo else None,
        })
    return jsonify({"success": True, "mes": f"{anio:04d}-{mes:02d}", "periodo": f"{MESES[mes]} de {anio}", "clientes": filas,
                    "puede_generar": puede_generar(sesion), "lm_configurado": cfg.lm_configurado,
                    "ia_configurada": cfg.ia_configurada, "ia_modelo": cfg.ia_model, "pdf_disponible": _pdf_disponible()})


@bp.route("/api/informes/clientes/<int:team_id>", methods=["PUT"])
@requiere_sesion(generar_informes=True)
def guardar_cliente(sesion, team_id):
    d = request.get_json() or {}
    org = (d.get("genesys_org") or "").strip()
    if org and not re.match(r"^[A-Za-z0-9._-]{1,80}$", org):
        return jsonify({"success": False, "error": "Shortname inválido (letras, números, punto, guion o guion bajo)."}), 400
    excluir = d.get("excluir_empresas") or []
    if isinstance(excluir, str):
        excluir = excluir.split(",")
    excluir = [x.strip() for x in excluir if x and x.strip()]
    try:
        equipo = _equipos(sesion, [team_id])
    except Exception as e:
        return jsonify({"success": False, "error": f"No se pudo leer el helpdesk en Odoo: {e}"}), 502
    if not equipo:
        return jsonify({"success": False, "error": "Helpdesk no encontrado en Odoo."}), 404
    guardados = leer_clientes()
    actual = guardados.get(str(team_id)) or {}
    c = cliente_de(team_id, equipo[0]["name"], guardados)
    nuevo = {**{k: getattr(c, k) for k in CAMPOS_CLIENTE}, **actual, "genesys_org": org, "excluir_empresas": excluir,
             "nombre": (d.get("nombre") or "").strip() or c.nombre}
    with _candado_clientes:
        guardados = json.loads(_ruta_clientes().read_text(encoding="utf-8"))
        guardados[str(team_id)] = nuevo
        _guardar_clientes(guardados)
    return jsonify({"success": True, "cliente": nuevo})


def _lanzar(sesion, team_id, mes, tipo, **opciones):
    try:
        _mes(mes)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    activo = _trabajo_activo(team_id, mes)
    if activo:
        return jsonify({"success": True, "job_id": activo.id, "ya_en_curso": True})
    try:
        equipo = _equipos(sesion, [team_id])
    except Exception as e:
        return jsonify({"success": False, "error": f"No se pudo leer el helpdesk en Odoo: {e}"}), 502
    if not equipo:
        return jsonify({"success": False, "error": "Helpdesk no encontrado en Odoo."}), 404
    if tipo == "generar":
        # Un helpdesk sin configurar se guarda al generar, para que su carpeta (código) no cambie después.
        with _candado_clientes:
            guardados = json.loads(_ruta_clientes().read_text(encoding="utf-8"))
            if str(team_id) not in guardados:
                c = cliente_de(team_id, equipo[0]["name"], guardados)
                guardados[str(team_id)] = {k: getattr(c, k) for k in CAMPOS_CLIENTE}
                _guardar_clientes(guardados)
    trabajo = Trabajo(team_id, mes, sesion.get("user"), tipo, nombre_odoo=equipo[0]["name"], **opciones)
    encolar(trabajo)
    return jsonify({"success": True, "job_id": trabajo.id})


@bp.route("/api/informes/generar", methods=["POST"])
@requiere_sesion(generar_informes=True)
def lanzar_generacion(sesion):
    d = request.get_json() or {}
    try:
        team_id = int(d.get("team_id"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "team_id inválido."}), 400
    sin_lic = bool(d.get("sin_licenciamiento"))
    if not sin_lic and not (leer_clientes().get(str(team_id)) or {}).get("genesys_org"):
        return jsonify({"success": False, "error": "Este helpdesk no tiene shortname de Genesys Cloud: guárdalo o genera sin licenciamiento."}), 400
    return _lanzar(sesion, team_id, d.get("mes") or "", "generar", sin_licenciamiento=sin_lic)


@bp.route("/api/informes/jobs/<job_id>/eventos", methods=["GET"])
@requiere_sesion()
def eventos_trabajo(sesion, job_id):
    trabajo = TRABAJOS.get(job_id)
    if not trabajo:
        return jsonify({"success": False, "error": "Trabajo no encontrado (¿se reinició el servidor?)."}), 404

    def flujo():
        i = 0
        while True:
            with trabajo.cond:
                if i >= len(trabajo.eventos) and not trabajo.terminado:
                    trabajo.cond.wait(timeout=15)
                nuevos, fin = trabajo.eventos[i:], trabajo.terminado
                i += len(nuevos)
            for e in nuevos:
                yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"
            if fin and i >= len(trabajo.eventos):
                return
            if not nuevos:
                yield ": sigue\n\n"  # mantiene viva la conexión a través de proxies

    return Response(flujo(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _carpeta(team_id, mes, sesion):
    anio, m = _mes(mes)
    guardados = leer_clientes()
    nombre = (guardados.get(str(team_id)) or {}).get("nombre")
    if not nombre:
        equipo = _equipos(sesion, [team_id])
        nombre = equipo[0]["name"] if equipo else ""
    return carpeta_informe(config_informes(), anio, m, cliente_de(team_id, nombre, guardados))


@bp.route("/api/informes/<mes>/<int:team_id>", methods=["GET"])
@requiere_sesion()
def detalle(sesion, mes, team_id):
    try:
        carpeta = _carpeta(team_id, mes, sesion)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    datos = leer_json(carpeta / "datos.json")
    if not datos:
        return jsonify({"success": True, "existe": False})
    s = datos["soporte"]
    orden = {"error": 0, "aviso": 1, "ok": 2}
    return jsonify({
        "success": True, "existe": True, "estado": leer_json(carpeta / "_estado.json"), "web": leer_json(carpeta / "_web.json"),
        "revision": sorted(leer_json(carpeta / "revision.json") or [], key=lambda x: orden.get(x["nivel"], 3)),
        "textos": leer_json(carpeta / "textos.json"), "redaccion_error": leer_json(carpeta / "redaccion_error.json"),
        "tickets": [{"id": t["id"], "asunto": t["asunto"], "etapa": t["etapa"], "en_curso": t["en_curso"], "tipo": t["tipo"]}
                    for t in s["tickets"]],
        "resumen_datos": {"tickets": s["total"], "horas": s["horas_total"], "fecha_corte": datos["fecha_corte"],
                          "licenciamiento": bool(datos.get("licenciamiento")),
                          "licenciamiento_omitido": bool(datos.get("licenciamiento_omitido")),
                          "organizacion": ((datos.get("licenciamiento") or {}).get("kpis") or {}).get("organizacion"),
                          "errores": datos.get("errores") or {}},
        "trabajo": (lambda t: t.id if t else None)(_trabajo_activo(team_id, mes)),
    })


@bp.route("/api/informes/<mes>/<int:team_id>/textos", methods=["PUT"])
@requiere_sesion(generar_informes=True)
def guardar_textos_editados(sesion, mes, team_id):
    try:
        carpeta = _carpeta(team_id, mes, sesion)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    if not (carpeta / "datos.json").exists():
        return jsonify({"success": False, "error": "Primero hay que generar el informe."}), 400
    if _trabajo_activo(team_id, mes):
        return jsonify({"success": False, "error": "Hay una generación en curso para este informe; espera a que termine."}), 409
    textos = (request.get_json() or {}).get("textos")
    if not isinstance(textos, dict):
        return jsonify({"success": False, "error": "Faltan los textos."}), 400
    errores = guardar_textos(carpeta, textos, f"editado:{sesion.get('user')}")
    if errores:
        return jsonify({"success": False, "error": "Los textos no tienen la forma esperada.", "detalle": errores[:10]}), 400
    return _lanzar(sesion, team_id, mes, "renderizar")


@bp.route("/api/informes/<mes>/<int:team_id>/redactar", methods=["POST"])
@requiere_sesion(generar_informes=True)
def volver_a_redactar(sesion, mes, team_id):
    return _lanzar(sesion, team_id, mes, "redactar")


@bp.route("/api/informes/<mes>/<int:team_id>/archivo/<tipo>", methods=["GET"])
@requiere_sesion()
def descargar(sesion, mes, team_id, tipo):
    if tipo not in ("pdf", "docx"):
        return jsonify({"success": False, "error": "Tipo de archivo inválido."}), 400
    try:
        carpeta = _carpeta(team_id, mes, sesion)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    estado = leer_json(carpeta / "_estado.json") or {}
    nombre = estado.get("pdf") if tipo == "pdf" else estado.get("archivo")
    if not nombre or not (carpeta / nombre).exists():
        return jsonify({"success": False, "error": "El archivo no existe; genera el informe."}), 404
    mime = "application/pdf" if tipo == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return send_file(carpeta / nombre, mimetype=mime, as_attachment=request.args.get("ver") != "1", download_name=nombre)
