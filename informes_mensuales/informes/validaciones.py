"""Validaciones automáticas del borrador. Producen revision.md para la persona que revisa.

Niveles: 'error' (no enviar sin corregir), 'aviso' (revisar), 'ok' (verificado).
"""
import re

from .render import PENDIENTE

TELEFONO = re.compile(r"(?<![\d#])(?:\+?\d[\d\s\-]{7,}\d)(?!\d)")
CORREO = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
# Frases que dan el caso por terminado. "Los chats se cerraban" no cuenta; "el caso se cerró" sí.
RESUELTO = re.compile(r"\b(resuel[tv][oa]s?|se resolvi[óo]|solucionad[oa]s?|se solucion[óo]|se cerr[óo]|"
                      r"(?:caso|ticket|requerimiento|incidente|solicitud) (?:fue |qued[óo] |queda |está )?(?:cerrad[oa]|atendid[oa]))\b", re.I)
# Frases que niegan el sobreuso ("sin generar sobreuso", "no hubo excedente", "dentro del fair use").
# Solo se usan cuando BYOC no tiene excedente, para no confundirlas con una atribución de sobreuso.
NIEGA_SOBREUSO = re.compile(r"\bsin (?:\w+ ){0,2}(?:sobreuso|excedente|exced\w*)|"
                            r"\bno (?:se )?(?:presenta|hay|hubo|registra|registró|tiene|tuvo|genera|generó|existe|supera|superó)\b|"
                            r"dentro del? (?:fair use|límite)", re.I)
RESPALDO = ("conforme a lo acordado con el cliente", "completando la atención y validación correspondiente")


def _r(nivel, tema, mensaje, corregible=False):
    """corregible: problema de redacción que la IA puede corregir (ver problemas_redaccion)."""
    r = {"nivel": nivel, "tema": tema, "mensaje": mensaje}
    if corregible:
        r["corregible"] = True
    return r


def _privacidad(texto):
    hallazgos = []
    for nombre, patron in (("teléfono", TELEFONO), ("correo", CORREO), ("ID de conversación", UUID)):
        for m in patron.findall(texto):
            hallazgos.append(f"{nombre} «{m.strip()}»")
    return hallazgos


def _numeros(texto):
    return {float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", texto)}


def _valores_lic(lic):
    """Todas las cifras que existen en los datos de licenciamiento (para cotejar la narrativa)."""
    vals = set()

    def recorrer(x):
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            vals.update({round(x, 1), round(x), round(x, 2)})
        elif isinstance(x, dict):
            for v in x.values():
                recorrer(v)
        elif isinstance(x, list):
            for v in x:
                recorrer(v)
        elif isinstance(x, str):
            vals.update(_numeros(x))
    recorrer(lic)
    return vals


def validar(datos, textos):
    r = []
    s = datos["soporte"]

    # --- Coherencia de cifras de soporte
    suma_tipo = sum(x["cantidad"] for x in s["por_tipo"])
    suma_etapa = sum(x["cantidad"] for x in s["por_etapa"])
    r.append(_r("ok" if suma_tipo == s["total"] else "error", "Soporte", f"Casos por tipo suman {suma_tipo} de {s['total']}."))
    r.append(_r("ok" if suma_etapa == s["total"] else "error", "Soporte",
                f"Casos por estado suman {suma_etapa} de {s['total']}" + ("" if suma_etapa == s["total"] else
                " (hay etapas fuera de la tabla, p. ej. Cancelled u On Hold)") + "."))
    horas = round(sum(t["horas"] for t in s["tickets"]), 2)
    r.append(_r("ok" if abs(horas - s["horas_total"]) < 0.01 else "error", "Soporte", f"Total de horas {s['horas_total']:.2f}."))

    exc = s.get("excluidos") or {}
    if exc.get("no_encontradas"):
        r.append(_r("error", "Soporte", f"Empresas a excluir que no existen en Odoo (revisar el nombre exacto): "
                                       f"{', '.join(exc['no_encontradas'])}."))
    if exc.get("empresas"):
        r.append(_r("ok", "Soporte", f"Excluidos {len(exc['tickets_mes'])} tickets del mes de {', '.join(exc['empresas'])}"
                                    + (f": {', '.join(map(str, exc['tickets_mes']))}." if exc["tickets_mes"] else ".")))

    inferidos = [t["id"] for t in s["tickets"] if t["tipo_inferido"]]
    if inferidos:
        r.append(_r("aviso", "Soporte", f"{len(inferidos)} tickets sin tipo en Odoo (ni campo ni etiqueta), contados como "
                                       f"Requerimiento: {', '.join(map(str, inferidos))}. Conviene etiquetarlos en Odoo."))
    sin_horas = [t["id"] for t in s["tickets"] if t["cerrado"] and t["resuelto"] and not t["horas"]]
    if sin_horas:
        r.append(_r("aviso", "Soporte", f"Tickets cerrados sin horas registradas: {', '.join(map(str, sin_horas))}."))

    # --- Textos de tickets
    resumenes = {int(t["id"]): t["resumen"] for t in (textos.get("soporte") or {}).get("tickets", [])}
    for t in s["tickets"]:
        txt = resumenes.get(t["id"], "")
        if not txt or txt == PENDIENTE:
            r.append(_r("error", f"Ticket #{t['id']}", "Sin resumen redactado.", True))
            continue
        if any(f in txt for f in RESPALDO):
            r.append(_r("error", f"Ticket #{t['id']}", "Usa el texto genérico de respaldo; redactar un resumen real.", True))
        if t["en_curso"] and RESUELTO.search(txt):
            r.append(_r("error", f"Ticket #{t['id']}", f"Está en curso ({t['etapa']}) pero el resumen dice "
                                                      f"«{RESUELTO.search(txt).group(0)}».", True))
        pii = _privacidad(txt)
        if pii:
            r.append(_r("error", f"Ticket #{t['id']}", "Datos sensibles en el resumen: " + ", ".join(pii) + ".", True))
        if len(txt) > 700:
            r.append(_r("aviso", f"Ticket #{t['id']}", f"Resumen largo ({len(txt)} caracteres)."))
    extras = set(resumenes) - {t["id"] for t in s["tickets"]}
    if extras:
        r.append(_r("error", "Soporte", f"Hay resúmenes de tickets que no son del mes: {sorted(extras)}.", True))

    # --- Logo
    if not datos.get("logo"):
        r.append(_r("error", "Portada", "No hay logo del cliente (ni en Odoo ni en logos/)."))
    elif datos.get("logo_origen") != "odoo":
        r.append(_r("aviso", "Portada", "El logo sale de la carpeta logos/, no de Odoo (helpdesk.team.x_studio_logo vacío)."))

    # --- Licenciamiento
    lic = datos.get("licenciamiento")
    if datos.get("licenciamiento_omitido"):
        r.append(_r("aviso", "Licenciamiento", "Informe sin la sección de licenciamiento (se generó sin License Manager)."))
    elif not lic:
        r.append(_r("error", "Licenciamiento", "Sin datos de License Manager: " + (datos.get("errores", {}).get("licenciamiento") or "no configurado") + "."))
    else:
        k = lic["kpis"]
        fin = (k["periodo"]["fin"] or "")[:7]
        esperado = f"{datos['anio']:04d}-{datos['mes']:02d}"
        r.append(_r("ok" if fin == esperado else "aviso", "Licenciamiento",
                    f"Periodo de facturación {k['periodo']['inicio'][:10]} a {k['periodo']['fin'][:10]}"
                    + ("" if fin == esperado else f"; no termina en el mes del informe ({esperado})") + "."))
        narrativa = " ".join((textos.get("licenciamiento") or {}).get("resumen", []) + (textos.get("licenciamiento") or {}).get("alertas", []))
        if not narrativa.strip():
            r.append(_r("error", "Licenciamiento", "Sin resumen ejecutivo redactado.", True))
        else:
            conocidos = _valores_lic(lic) | {float(datos["anio"])}
            raros = sorted(n for n in _numeros(narrativa) if n >= 10 and n not in conocidos and round(n) not in conocidos)
            if raros:
                r.append(_r("aviso", "Licenciamiento", f"Cifras del texto que no aparecen en los datos: {', '.join(f'{x:,.1f}' for x in raros)}.", True))
            b = k["byoc"]
            # Oración por oración (el punto decimal de "92,697.7" no corta la oración).
            oraciones = re.split(r"(?<=[.!?;])\s+", narrativa)
            sobreuso_byoc = [o for o in oraciones if "byoc" in o.lower()
                             and re.search(r"sobreuso|exced|excede|por encima", o, re.I)
                             and not NIEGA_SOBREUSO.search(o)]
            if b["existe"] and not b["excedente"] and sobreuso_byoc:
                r.append(_r("error", "Licenciamiento", f"El texto atribuye sobreuso a BYOC, pero está al {b['pct']}% de su fair use "
                                                       f"({b['usado']:,.1f} de {b['limite_fair_use']:,.0f} min).", True))
            if any(a["nivel"] == "alta" for a in lic["alertas"]) and not re.search(r"sobreuso|exce|por encima", narrativa, re.I):
                r.append(_r("aviso", "Licenciamiento", "Hay alertas de sobreuso que el resumen no menciona."))
            pii = _privacidad(narrativa)
            if pii:
                r.append(_r("error", "Licenciamiento", "Datos sensibles en el texto: " + ", ".join(pii) + ".", True))
        errores_hist = [h for h in lic.get("historico", []) if h.get("error")]
        if errores_hist:
            r.append(_r("aviso", "Licenciamiento", f"{len(errores_hist)} periodos del histórico no se pudieron consultar."))

    # --- Disponibilidad
    est = datos.get("estado")
    if not est:
        r.append(_r("error", "Disponibilidad", "Sin datos de status.mypurecloud.com: " + (datos.get("errores", {}).get("estado") or "") + "."))
    else:
        if not est["mes_publicado"]:
            r.append(_r("aviso", "Disponibilidad", "Genesys aún no publica la disponibilidad del mes."))
        if datos.get("region_origen") == "por_defecto":
            r.append(_r("aviso", "Disponibilidad", f"Región supuesta ({est['region']}): no vino de License Manager; confirmar la región del cliente."))
        n = len(est["incidentes_region"])
        r.append(_r("ok", "Disponibilidad", f"{n} {'incidente publicado' if n == 1 else 'incidentes publicados'} para {est['region']}."))

    origen = textos.get("origen", "sin textos")
    r.append(_r("ok" if textos else "error", "Redacción", f"Textos: {origen}."))
    return r


def problemas_redaccion(datos, textos):
    """Problemas de la redacción que se le devuelven a la IA para que los corrija (autocorrección)."""
    return [x for x in validar(datos, textos) if x.get("corregible") and x["nivel"] != "ok"]


def revisar_docx(ruta):
    """Revisa el Word generado: nada que Word vaya a descargar de internet al actualizar campos."""
    import zipfile

    r = []
    with zipfile.ZipFile(ruta) as z:
        for nombre in z.namelist():
            if not nombre.startswith("word/"):
                continue
            xml = z.read(nombre).decode("utf-8", errors="ignore")
            if "INCLUDEPICTURE" in xml.upper() or "INCLUDETEXT" in xml.upper():
                r.append(_r("error", "Documento", f"{nombre} tiene campos que descargan contenido de internet al abrir (INCLUDEPICTURE)."))
            if nombre.endswith(".rels") and re.search(r'Type="[^"]*/image"[^>]*TargetMode="External"', xml):
                r.append(_r("error", "Documento", f"{nombre} enlaza imágenes externas."))
    if not r:
        r.append(_r("ok", "Documento", "Sin campos ni imágenes que dependan de internet."))
    return r


def semaforo(resultados):
    if any(x["nivel"] == "error" for x in resultados):
        return "🔴"
    if any(x["nivel"] == "aviso" for x in resultados):
        return "🟡"
    return "🟢"


def escribir_revision(ruta, datos, resultados, archivo_docx):
    iconos = {"error": "🔴", "aviso": "🟡", "ok": "🟢"}
    orden = {"error": 0, "aviso": 1, "ok": 2}
    lineas = [
        f"# Revisión — {datos['cliente']['nombre']} · {datos['periodo_txt']}",
        "",
        f"Estado: {semaforo(resultados)}  ·  Documento: `{archivo_docx}`  ·  Datos al {datos['fecha_corte']}",
        "",
        "| | Tema | Detalle |",
        "|---|---|---|",
    ]
    for x in sorted(resultados, key=lambda x: orden[x["nivel"]]):
        lineas.append(f"| {iconos[x['nivel']]} | {x['tema']} | {x['mensaje'].replace('|', '/')} |")
    lineas += ["", "El PDF ya trae el índice con números de página. Si editas el Word, al abrirlo acepta «actualizar campos».", ""]
    ruta.write_text("\n".join(lineas), encoding="utf-8")
