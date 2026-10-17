"""Renderiza el informe Word a partir de datos.json + textos.json y la plantilla ESMT."""
from collections import Counter
from datetime import datetime
from pathlib import Path

from docx.shared import Mm
from docxtpl import DocxTemplate, InlineImage
from PIL import Image

from . import graficas
from .config import MESES, RAIZ

PLANTILLA = RAIZ / "plantilla" / "informe_esmt.docx"
PENDIENTE = "[PENDIENTE DE REDACCIÓN]"
IMPACTO = {"none": "Sin impacto", "minor": "Menor", "major": "Mayor", "critical": "Crítico", "maintenance": "Mantenimiento"}
PLURAL = {"Requerimiento": "requerimientos", "Incidente": "incidentes", "Cambio": "cambios",
          "Pregunta": "preguntas", "Problema": "problemas", "Soporte": "soportes"}


# ------------------------------------------------------------------ formato
def num(v, dec=0):
    return "—" if v is None else f"{v:,.{dec}f}"


def compacto(v):
    if v is None:
        return "—"
    if abs(v) >= 1e6:
        return f"{v / 1e6:.2f} M"
    if abs(v) >= 1e4:
        return f"{v / 1e3:.1f} k"
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.1f}"


def pct(p):
    if p is None:
        return "—"
    # Mismo valor que en el texto (98.7%, no 99%); los enteros sin decimal (118%).
    return f"{p:.0f}%" if float(p).is_integer() else f"{p:.1f}%"


def fecha(s):
    """'2026-09-01 16:07:12' o ISO 8601 → '01/09/2026'."""
    if not s:
        return ""
    return datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T")).strftime("%d/%m/%Y")


def lista_es(partes):
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]


def _plural(tipo, n):
    return f"{n} {tipo.lower() if n == 1 else PLURAL.get(tipo, tipo.lower() + 's')}"


def logo_cuadrado(origen, destino):
    """El header reserva un recuadro cuadrado: se centra el logo sin deformarlo."""
    img = Image.open(origen).convert("RGBA")
    lado = max(img.size)
    lienzo = Image.new("RGBA", (lado, lado), (255, 255, 255, 0))
    lienzo.paste(img, ((lado - img.width) // 2, (lado - img.height) // 2), img)
    lienzo.save(destino)
    return destino


def _estado_recurso(disponible, usado, sobreuso, p):
    if sobreuso or (not disponible and usado):
        return "Sobreuso"
    if p is None:
        return "—"
    if p >= 85:
        return "Cerca del límite"
    if p < 15:
        return "Bajo uso"
    return "En rango"


# ------------------------------------------------------------------ secciones
def ctx_soporte(datos, textos, mes, anio):
    s = datos["soporte"]
    resumenes = {int(t["id"]): t["resumen"] for t in (textos.get("soporte") or {}).get("tickets", [])}
    tickets = []
    for t in s["tickets"]:
        tickets.append({**t,
                        "resumen": resumenes.get(t["id"]) or PENDIENTE,
                        "creado_fmt": fecha(t["creado"]),
                        "cierre_fmt": fecha(t["cierre"]) if t["cierre"] else f"En curso ({t['etapa']})",
                        "dias_fmt": f"{t['dias']}*" if t["en_curso"] else str(t["dias"]),
                        "horas_fmt": f"{t['horas']:.2f}"})
    corte = datos["fecha_corte"]
    cliente = datos["cliente"]["nombre"]
    if s["total"]:
        desglose = lista_es([_plural(x["tipo"], x["cantidad"]) for x in sorted(s["por_tipo"], key=lambda x: -x["cantidad"])])
        intro = [f"Durante el mes de {mes} de {anio} se aperturaron {s['total']} casos para {cliente}: {desglose}. "
                 f"A continuación, un breve resumen de cada uno."]
    else:
        intro = [f"Durante el mes de {mes} de {anio} no se aperturaron casos para {cliente}."]
    intro += (textos.get("soporte") or {}).get("destacados", [])

    abiertos, cerrados = s["abiertos"], s["cerrados"]
    if s["promedio_dias_cierre"] is not None:
        texto_prom = (f"El tiempo promedio desde la apertura hasta el cierre de los {s['tickets_cerrados_promedio']} casos "
                      f"cerrados de {mes} fue de {s['promedio_dias_cierre']} días calendario.")
    else:
        texto_prom = f"A la fecha de corte ({corte}) ninguno de los casos de {mes} se ha cerrado."
    if abiertos:
        texto_prom += f" {abiertos} {'caso sigue' if abiertos == 1 else 'casos siguen'} en curso."
    en_curso = Counter(t["etapa"] for t in s["tickets"] if t["en_curso"])
    detalle = lista_es([f"{n} en {etapa}" for etapa, n in en_curso.most_common()]) if en_curso else ""
    texto_estados = f"Al {corte}, {cerrados} de los {s['total']} casos abiertos en {mes} están cerrados"
    texto_estados += f" y {abiertos} continúan en curso ({detalle})." if abiertos else "."

    return {
        "tickets": tickets, "total": s["total"], "por_tipo": s["por_tipo"], "por_etapa": s["por_etapa"],
        "horas_fmt": f"{s['horas_total']:.2f}",
        "promedio_fmt": str(s["promedio_dias_cierre"]) if s["promedio_dias_cierre"] is not None else "—",
        "texto_promedio": texto_prom, "texto_estados": texto_estados,
        "nota_promedio": (f"* Casos en curso: días transcurridos hasta la fecha de corte ({corte}); "
                          "no se incluyen en el promedio.") if abiertos else "",
    }, intro


def ctx_licenciamiento(lic):
    k = lic["kpis"]
    licencias = [{**l, "nombre": l["nombre"], "contratadas_fmt": num(l["contratadas"]), "en_uso_fmt": num(l["en_uso"]),
                  "sobreuso_fmt": num(l["sobreuso"]) if l["sobreuso"] else "—",
                  "pct_fmt": pct(l["pct"]) if l["contratadas"] else ("Sin contratar" if l["en_uso"] else "—")}
                 for l in k["licencias"] + k["addons"] if l["contratadas"] or l["en_uso"]]

    filas, grafica = [], []

    def agregar(nombre, disponible, usado, sobreuso, p, corto=None, dec=0):
        if not (disponible or usado):
            return
        filas.append({"nombre": nombre, "disponible_fmt": num(disponible) if disponible else "—",
                      "en_uso_fmt": num(usado, dec), "pct_fmt": pct(p), "estado": _estado_recurso(disponible, usado, sobreuso, p)})
        grafica.append((corto or nombre, p if disponible else (float("inf") if usado else None)))

    for l in k["licencias"] + k["addons"]:
        if l["contratadas"] or l["en_uso"]:
            grafica.append((l["nombre"].replace("Genesys Cloud ", ""), l["pct"] if l["contratadas"] else float("inf")))
    b = k["byoc"]
    if b["existe"]:
        agregar("BYOC Cloud, minutos (fair use)", b["limite_fair_use"], b["usado"], b["excedente"], b["pct"], "BYOC Cloud", 1)
    i = k["ivr"]
    if i["existe"]:
        agregar("IVR Basic, minutos", i["asignado"], i["usado"], i["bajo_demanda"], i["pct"], "IVR Basic")
    for r in k["recursos"]:
        agregar(r["nombre"], r["comprometido"] + r["incluido"], r["en_uso"], r["sobreuso"], r["pct"], r["nombre"].replace("Genesys Cloud ", ""))
    st = k["storage"]
    agregar("Storage (GB)", st["comprometido"], st["en_uso"], st["sobreuso"], st["pct"], "Storage")
    t = k["ia_tokens"]
    agregar("AI Experience Tokens", t["prepagados"] + t["incluidos"], t["en_uso"], t["sobreuso"], t["pct"], "IA Tokens")
    o = k["outbound"]
    if o:
        agregar("Intentos outbound (fair use)", o["limite_fair_use"], o["intentos"], o["excedente"], o["pct"], "Outbound")

    principal = None
    historico = []
    for h in lic.get("historico") or []:
        if h.get("error"):
            continue
        principal = principal or h.get("licencia_principal")
        lp = h["licencias"].get(principal) or {}
        fin = datetime.fromisoformat(h["periodo"]["fin"].replace("Z", "+00:00"))
        celda = lambda x: f"{compacto(x['en_uso'])} ({pct(x['pct'])})" if x.get("pct") is not None else compacto(x.get("en_uso"))
        historico.append({"periodo": f"{MESES[fin.month].capitalize()} {fin.year}",
                          "licencia": celda(lp) if lp else "—", "byoc": celda(h["byoc"]), "ivr": celda(h["ivr"]),
                          "api": celda(h["api"]), "storage": celda(h["storage"]), "ia_tokens": celda(h["ia_tokens"]),
                          "transcripcion": celda(h["transcripcion"])})

    nota = (f"BYOC Cloud e intentos outbound se comparan contra el fair use: {b['nominales']} licencias nominales "
            f"y {b['concurrentes']} concurrentes (BYOC: 5,000 min por nominal y 6,500 por concurrente; "
            f"outbound: 15,000 y 19,500 intentos).")
    return {
        "organizacion": k["organizacion"],
        "periodo_txt": f"{fecha(k['periodo']['inicio'])} – {fecha(k['periodo']['fin'])}",
        "licencias": licencias, "recursos": filas, "alertas": lic["alertas"], "nota_recursos": nota,
        "historico": historico, "historico_licencia": (principal or "Licencia").replace("Genesys Cloud ", ""),
    }, grafica


def ctx_estado(est, mes, anio):
    region = est["region"]
    if est["mes_publicado"]:
        p1 = (f"Durante {mes} de {anio}, la disponibilidad de la plataforma Genesys Cloud publicada para la región "
              f"{region}, donde opera la organización, fue de {est['disponibilidad_mes_region']}.")
    else:
        p1 = f"Genesys aún no ha publicado la disponibilidad de {mes} de {anio}; la tabla muestra los meses publicados."
    n = len(est["incidentes_region"])
    p2 = (f"Genesys publicó {n} {'incidente que afectó' if n == 1 else 'incidentes que afectaron'} a la región durante el mes "
          f"(en todas las regiones se publicaron {est['incidentes_total_mes']})." if n else
          "No se publicaron incidentes que afectaran a la región durante el mes.")
    incidentes = []
    for i in est["incidentes_region"]:
        dur = ""
        if i["resuelto"]:
            m = int((datetime.fromisoformat(i["resuelto"]) - datetime.fromisoformat(i["fecha"])).total_seconds() // 60)
            dur = f"{m // 60} h {m % 60} min" if m >= 60 else f"{m} min"
        incidentes.append({"fecha": i["fecha"], "titulo": i["titulo"], "impacto": IMPACTO.get(i["impacto"], i["impacto"]),
                           "duracion": dur or "En curso"})
    return {
        "region": region, "parrafos": [p1, p2], "incidentes": incidentes,
        # Solo el año del informe, de enero al mes reportado.
        "disponibilidad": [{"mes": MESES[d["mes"]].capitalize(), "valor": d["valores"].get(region, "-")}
                           for d in sorted(est["disponibilidad"], key=lambda d: d["mes"]) if d["anio"] == anio],
    }


def indice(ctx):
    """Índice prellenado (sin números de página). El PDF lo regenera LibreOffice; Word, al actualizar campos."""
    secciones = [("RESUMEN DE SOPORTE", [f"{t['asunto']} (#{t['id']})" for t in ctx["soporte"]["tickets"]]),
                 ("VOLUMEN DE CASOS", ["TIEMPO PROMEDIO", "HISTORIAL DE HORAS", "ESTADO DE LOS TICKETS"])]
    if not ctx["lic_omitido"]:
        sub = []
        if ctx["lic"]:
            sub = ["Resumen ejecutivo de uso", "Estado de KPIs principales", "Alertas", "CAPACIDAD DISPONIBLE VS UTILIZADA"]
            if ctx["lic"]["historico"]:
                sub.append(f"HISTÓRICO DE CONSUMO {ctx['anio']}")
        secciones.append(("LICENCIAMIENTO (REPORTE DE USO)", sub))
    secciones += [("CASOS MES A MES", []), ("DISPONIBILIDAD GENERAL DEL SERVICIO", [])]
    e = []
    for n, (titulo, sub) in enumerate(secciones, 1):
        e.append({"nivel": 1, "texto": f"{n}. {titulo}"})
        e += [{"nivel": 2, "texto": x} for x in sub]
    return e


# ------------------------------------------------------------------ principal
def renderizar(datos, textos, carpeta: Path, destino: Path, empresa: dict):
    anio, nmes = datos["anio"], datos["mes"]
    mes = MESES[nmes]
    tpl = DocxTemplate(PLANTILLA)
    img_dir = carpeta / "graficas"
    img_dir.mkdir(exist_ok=True)

    soporte, intro = ctx_soporte(datos, textos, mes, anio)
    s = datos["soporte"]
    img = {
        "tipos": graficas.barras([x["tipo"] for x in s["por_tipo"]] or ["Sin casos"], [x["cantidad"] for x in s["por_tipo"]] or [0], img_dir / "tipos.png"),
        "estados": graficas.barras([x["etapa"] for x in s["por_etapa"]], [x["cantidad"] for x in s["por_etapa"]], img_dir / "estados.png", color=graficas.AZUL),
        "mes_a_mes": graficas.mes_a_mes(s["serie_anual"]["meses"], s["serie_anual"]["tipos"], img_dir / "mes_a_mes.png"),
    }

    lic, grafica_cap = (ctx_licenciamiento(datos["licenciamiento"]) if datos.get("licenciamiento") else (None, []))
    if lic:
        img["capacidad"] = graficas.capacidad(grafica_cap, img_dir / "capacidad.png")

    serie = []
    for m in s["serie_anual"]["meses"]:
        total = sum(v for k, v in m.items() if k != "mes")
        serie.append({"mes": MESES[m["mes"]].capitalize(), "incidente": m.get("Incidente", 0),
                      "requerimiento": m.get("Requerimiento", 0), "cambio": m.get("Cambio", 0), "total": total})
    serie_total = {k: sum(r[k] for r in serie) for k in ("incidente", "requerimiento", "cambio", "total")}

    ctx = {
        "mes": mes.capitalize(), "mes_mayus": mes.upper(), "anio": anio,
        "fecha_corte": datos["fecha_corte"], "empresa": empresa.get("nombre", "Grupo ESMT"),
        "preparado_por": empresa.get("preparado_por", "Support Team"),
        "soporte": soporte, "lic": lic, "lic_omitido": bool(datos.get("licenciamiento_omitido")),
        "serie": serie, "serie_total": serie_total,
        "estado": ctx_estado(datos["estado"], mes, anio) if datos.get("estado") else None,
        "textos": {"soporte": {"intro": intro},
                   "licenciamiento": {"resumen": (textos.get("licenciamiento") or {}).get("resumen") or [PENDIENTE],
                                      "alertas": (textos.get("licenciamiento") or {}).get("alertas") or []}},
    }
    ctx["indice"] = indice(ctx)
    ctx["img"] = {k: InlineImage(tpl, str(v), width=Mm(150)) for k, v in img.items() if v}

    logo = datos.get("logo")
    if logo:
        ctx["logo_cliente"] = InlineImage(tpl, str(carpeta / logo), width=Mm(55))
        tpl.replace_pic("logo_cliente", str(logo_cuadrado(carpeta / logo, img_dir / "logo_header.png")))
    else:
        ctx["logo_cliente"] = ""

    tpl.render(ctx, autoescape=True)
    tpl.save(destino)
    return ctx
