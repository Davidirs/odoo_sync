"""Extracción de la sección de soporte desde Odoo Helpdesk (XML-RPC, solo lectura)."""
import html
import re
import xmlrpc.client
from collections import Counter, defaultdict
from datetime import datetime

TIPOS_ORDEN = ["Incidente", "Requerimiento", "Cambio", "Pregunta", "Problema", "Soporte"]
# Etapas que se muestran siempre en la tabla de estados, aunque tengan 0 tickets.
ETAPAS_BASE = ["New", "Work in Progress", "Waiting for Customer", "Waiting for Vendor", "Solved", "Closed"]
ETAPAS_RESUELTAS = {"solved", "closed"}
FMT = "%Y-%m-%d %H:%M:%S"


class Odoo:
    def __init__(self, url, db, user, password):
        self.db, self.password = db, password
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
        self.uid = common.authenticate(db, user, password, {})
        if not self.uid:
            raise RuntimeError("Odoo rechazó las credenciales (ODOO_USER / ODOO_PASSWORD).")
        self.models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)

    def call(self, model, method, *args, **kw):
        return self.models.execute_kw(self.db, self.uid, self.password, model, method, list(args), kw)


def limpiar_html(texto):
    texto = re.sub(r"<br\s*/?>|</p>|</div>", "\n", texto or "", flags=re.I)
    texto = html.unescape(re.sub(r"<[^>]+>", " ", texto))
    return re.sub(r"[ \t\xa0]+", " ", re.sub(r"\n\s*\n+", "\n", texto)).strip()


def quitar_citas(texto):
    """Corta el hilo citado de un correo ("El lun, 1 sept... escribió:", "On ... wrote:")."""
    patron = r"(El \w{3,9},? \d{1,2} .{0,80}escribió:|On .{0,80}wrote:|-----Original Message-----|De: .{0,80}Enviado:)"
    return re.split(patron, texto, maxsplit=1, flags=re.I | re.S)[0].strip()


def tipo_ticket(ticket, tags):
    """Devuelve (tipo, inferido). Prioriza el campo de Odoo; luego las etiquetas."""
    if ticket.get("x_studio_tipo_de_ticket"):
        return ticket["x_studio_tipo_de_ticket"], False
    for tid in ticket.get("tag_ids") or []:
        nombre = (tags.get(tid) or "").lower()
        if "inciden" in nombre:
            return "Incidente", False
        if "cambio" in nombre or "change" in nombre:
            return "Cambio", False
        if "request" in nombre or "requerim" in nombre:
            return "Requerimiento", False
        if "pregunta" in nombre or "question" in nombre:
            return "Pregunta", False
        if "problema" in nombre or "problem" in nombre:
            return "Problema", False
    return "Requerimiento", True


def _fecha(s):
    return datetime.strptime(s, FMT) if s else None


def _dias(desde, hasta):
    return max(1, round((hasta - desde).total_seconds() / 86400))


def _conversaciones(odoo, ticket_ids, corte):
    """Mensajes humanos (cliente, ESMT y notas internas) hasta la fecha de corte."""
    if not ticket_ids:
        return {}
    msgs = odoo.call(
        "mail.message", "search_read",
        [["model", "=", "helpdesk.ticket"], ["res_id", "in", ticket_ids],
         ["message_type", "in", ["comment", "email"]], ["date", "<=", corte.strftime(FMT)]],
        fields=["res_id", "date", "author_id", "body", "subtype_id"], order="id asc",
    )
    autores = {m["author_id"][0] for m in msgs if m.get("author_id")}
    internos = set()
    if autores:
        for p in odoo.call("res.partner", "read", list(autores), fields=["partner_share"]):
            if not p.get("partner_share"):
                internos.add(p["id"])
    salida = defaultdict(list)
    for m in msgs:
        autor_id, autor = (m["author_id"] or [0, "Sistema"])[:2]
        if "odoobot" in autor.lower():
            continue
        texto = quitar_citas(limpiar_html(m.get("body")))
        if len(texto) < 5:
            continue
        subtipo = ((m.get("subtype_id") or [0, ""])[1] or "").lower()
        if "note" in subtipo or "nota" in subtipo:
            origen = "nota_interna"
        else:
            origen = "esmt" if autor_id in internos else "cliente"
        salida[m["res_id"]].append({
            "fecha": m["date"][:16], "origen": origen, "autor": autor, "texto": texto[:700],
        })
    return salida


def _partes_horas(odoo, ticket_ids):
    if not ticket_ids:
        return {}
    lineas = odoo.call(
        "account.analytic.line", "search_read", [["helpdesk_ticket_id", "in", ticket_ids]],
        fields=["helpdesk_ticket_id", "date", "unit_amount", "name"], order="date asc",
    )
    salida = defaultdict(list)
    for l in lineas:
        salida[l["helpdesk_ticket_id"][0]].append(
            {"fecha": l["date"], "horas": l["unit_amount"], "descripcion": (l["name"] or "").strip()}
        )
    return salida


def extraer_soporte(odoo, team_id, anio, mes, corte, excluir_empresas=()):
    """Tickets del helpdesk creados en el mes (UTC), estado actual a la fecha de corte."""
    inicio = datetime(anio, mes, 1)
    fin = datetime(anio + (mes == 12), mes % 12 + 1, 1)

    equipo = odoo.call("helpdesk.team", "read", [team_id], fields=["name", "x_studio_logo"])[0]
    etapas = odoo.call("helpdesk.stage", "search_read", [], fields=["name", "fold", "sequence"], order="sequence asc, id asc")
    fold = {e["id"]: e["fold"] for e in etapas}

    # Helpdesks compartidos por varias entidades: se excluyen los tickets de las empresas indicadas.
    excluir_ids, no_encontradas = [], []
    for nombre in excluir_empresas:
        ids_empresa = odoo.call("res.partner", "search", [["name", "=", nombre]])
        excluir_ids += ids_empresa
        if not ids_empresa:
            no_encontradas.append(nombre)
    filtro = [["commercial_partner_id", "not in", excluir_ids]] if excluir_ids else []
    rango_mes = [["team_id", "=", team_id], ["create_date", ">=", inicio.strftime(FMT)], ["create_date", "<", fin.strftime(FMT)]]

    campos = ["id", "name", "stage_id", "create_date", "write_date", "close_date", "total_hours_spent",
              "tag_ids", "x_studio_tipo_de_ticket", "description", "partner_id", "user_id", "priority"]
    tickets = odoo.call("helpdesk.ticket", "search_read", rango_mes + filtro, fields=campos, order="id asc")
    excluidos_mes = odoo.call("helpdesk.ticket", "search_read", rango_mes + [["commercial_partner_id", "in", excluir_ids]],
                              fields=["id"]) if excluir_ids else []
    anuales = odoo.call(
        "helpdesk.ticket", "search_read",
        [["team_id", "=", team_id], ["create_date", ">=", datetime(anio, 1, 1).strftime(FMT)], ["create_date", "<", fin.strftime(FMT)]] + filtro,
        fields=["create_date", "tag_ids", "x_studio_tipo_de_ticket"],
    )
    tag_ids = sorted({t for x in tickets + anuales for t in (x.get("tag_ids") or [])})
    tags = {t["id"]: t["name"] for t in odoo.call("helpdesk.tag", "read", tag_ids, fields=["name"])} if tag_ids else {}

    ids = [t["id"] for t in tickets]
    conversaciones = _conversaciones(odoo, ids, corte)
    partes = _partes_horas(odoo, ids)

    lista = []
    for t in tickets:
        tipo, inferido = tipo_ticket(t, tags)
        etapa_id, etapa = (t["stage_id"] or [0, "Sin etapa"])[:2]
        cerrado = bool(fold.get(etapa_id))
        creado = _fecha(t["create_date"])
        cierre = _fecha(t["close_date"]) if cerrado else None
        lista.append({
            "id": t["id"],
            "asunto": (t["name"] or "(Sin asunto)").strip(),
            "tipo": tipo,
            "tipo_inferido": inferido,
            "etiquetas": [tags.get(x, "") for x in t.get("tag_ids") or []],
            "etapa": etapa,
            "cerrado": cerrado,
            "resuelto": etapa.lower() in ETAPAS_RESUELTAS,
            "creado": t["create_date"],
            "cierre": t["close_date"] if cerrado else None,
            "dias": _dias(creado, cierre or corte),
            "en_curso": not cerrado,
            "horas": round(float(t.get("total_hours_spent") or 0.0), 2),
            "solicitante": (t.get("partner_id") or [0, ""])[1],
            "responsable": (t.get("user_id") or [0, ""])[1],
            "descripcion": limpiar_html(t.get("description"))[:1500],
            "conversacion": conversaciones.get(t["id"], [])[-12:],
            "partes_horas": partes.get(t["id"], []),
        })

    por_tipo = Counter(t["tipo"] for t in lista)
    por_etapa = Counter(t["etapa"] for t in lista)
    tabla_etapas = [
        {"etapa": e["name"], "cantidad": por_etapa.get(e["name"], 0)}
        for e in etapas if por_etapa.get(e["name"]) or e["name"] in ETAPAS_BASE
    ]
    cerrados_resueltos = [t for t in lista if t["cerrado"] and t["resuelto"] and t["cierre"]]
    promedio = round(sum(t["dias"] for t in cerrados_resueltos) / len(cerrados_resueltos)) if cerrados_resueltos else None

    serie = defaultdict(Counter)
    for t in anuales:
        serie[int(t["create_date"][5:7])][tipo_ticket(t, tags)[0]] += 1
    tipos_serie = [x for x in TIPOS_ORDEN if any(serie[m][x] for m in serie)] or ["Incidente", "Requerimiento", "Cambio"]

    return {
        "equipo": {"id": team_id, "nombre": equipo["name"]},
        "logo_odoo_b64": equipo.get("x_studio_logo") or None,
        "rango_utc": [inicio.strftime(FMT), fin.strftime(FMT)],
        "excluidos": {"empresas": list(excluir_empresas), "no_encontradas": no_encontradas,
                      "tickets_mes": [t["id"] for t in excluidos_mes]},
        "tickets": lista,
        "total": len(lista),
        "por_tipo": [{"tipo": k, "cantidad": por_tipo[k]} for k in TIPOS_ORDEN if por_tipo.get(k)]
                    + [{"tipo": k, "cantidad": v} for k, v in por_tipo.items() if k not in TIPOS_ORDEN],
        "por_etapa": tabla_etapas,
        "horas_total": round(sum(t["horas"] for t in lista), 2),
        "abiertos": sum(1 for t in lista if t["en_curso"]),
        "cerrados": sum(1 for t in lista if t["cerrado"]),
        "promedio_dias_cierre": promedio,
        "tickets_cerrados_promedio": len(cerrados_resueltos),
        "serie_anual": {
            "tipos": tipos_serie,
            "meses": [{"mes": m, **{x: serie[m][x] for x in tipos_serie}} for m in range(1, mes + 1)],
        },
    }
