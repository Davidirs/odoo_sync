"""Disponibilidad e incidentes de Genesys Cloud desde status.mypurecloud.com (Atlassian Statuspage).

Sustituye las capturas de pantalla: la tabla mensual de disponibilidad viene en el HTML
de la página (pie personalizado) y los incidentes en la API pública de Statuspage.
"""
import html
import re
from datetime import datetime

import requests

BASE = "https://status.mypurecloud.com"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
MESES_EN = ["january", "february", "march", "april", "may", "june", "july",
            "august", "september", "october", "november", "december"]

# Región de la API de Genesys (como la guarda LicenseManager) → nombre en la página de estado.
REGIONES = {
    "us-east-1": "Americas (US East)", "us-west-2": "Americas (US West)", "sa-east-1": "Americas (Sao Paulo)",
    "ca-central-1": "Americas (Canada)", "mx-central-1": "Americas (Mexico)", "us-east-2": "FedRAMP",
    "ap-south-1": "Asia Pacific (Mumbai)", "ap-southeast-2": "Asia Pacific (Sydney)",
    "ap-northeast-1": "Asia Pacific (Tokyo)", "ap-northeast-2": "Asia Pacific (Seoul)",
    "ap-northeast-3": "Asia Pacific (Osaka)", "ap-southeast-1": "Asia Pacific (Singapore)",
    "eu-west-1": "EMEA (Dublin)", "eu-central-1": "EMEA (Frankfurt)", "eu-west-2": "EMEA (London)",
    "eu-central-2": "EMEA (Zurich)", "me-central-1": "EMEA (UAE)",
}


def nombre_region(region):
    return REGIONES.get(region, region or "Americas (US East)")


def _texto(celda):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<br\s*/?>", " ", re.sub(r"<(?!br)[^>]+>", "", celda)))).strip()


def tabla_disponibilidad(hoy):
    """Filas {anio, mes, valores{region: '100%'}} de la tabla 'Platform Availability'."""
    pagina = requests.get(BASE + "/", headers=UA, timeout=30).text
    i = pagina.find("custom-footer-container")
    i = pagina.find("system-availability-table", i if i > 0 else 0)
    if i < 0:
        raise RuntimeError("No se encontró la tabla de disponibilidad en status.mypurecloud.com")
    tabla = pagina[i:pagina.find("</table>", i)]
    # La página no cierra las filas (</tr>), así que se separa por la etiqueta de apertura.
    filas = [re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", f, re.S) for f in re.split(r"<tr[^>]*>", tabla)[1:]]
    encabezado = [_texto(c) for c in filas[0]][1:]
    resultado, anio, mes_previo = [], hoy.year, None
    for f in filas[1:]:
        celdas = [_texto(c) for c in f]
        if not celdas or celdas[0].lower() not in MESES_EN:
            continue
        mes = MESES_EN.index(celdas[0].lower()) + 1
        if mes_previo is None:
            anio = hoy.year if mes <= hoy.month else hoy.year - 1
        elif mes > mes_previo:  # de enero a diciembre: cambio de año
            anio -= 1
        mes_previo = mes
        resultado.append({"anio": anio, "mes": mes, "valores": dict(zip(encabezado, celdas[1:]))})
    return encabezado, resultado


def incidentes_mes(anio, mes, region_nombre):
    datos = requests.get(BASE + "/api/v2/incidents.json", headers=UA, timeout=30).json()
    salida = []
    for inc in datos.get("incidents", []):
        creado = datetime.fromisoformat(inc["created_at"].replace("Z", "+00:00"))
        if (creado.year, creado.month) != (anio, mes):
            continue
        componentes = sorted({c["name"] for c in inc.get("components") or []})
        salida.append({
            "fecha": creado.strftime("%Y-%m-%d %H:%M"),
            "resuelto": (inc.get("resolved_at") or "")[:16].replace("T", " "),
            "titulo": inc["name"], "impacto": inc.get("impact"), "estado": inc.get("status"),
            "componentes": componentes, "enlace": inc.get("shortlink"),
            "afecta_region": region_nombre in componentes,
        })
    return sorted(salida, key=lambda x: x["fecha"])


def extraer_estado(anio, mes, region, hoy):
    region_nombre = nombre_region(region)
    encabezado, filas = tabla_disponibilidad(hoy)
    grupo = region_nombre.split(" (")[0]
    columnas = [c for c in encabezado if c.startswith(grupo)] or [region_nombre]
    hasta = (anio, mes)
    ultimos = [f for f in filas if f["anio"] == anio and f["mes"] <= mes]
    incidentes = incidentes_mes(anio, mes, region_nombre)
    fila_mes = next((f for f in filas if (f["anio"], f["mes"]) == hasta), None)
    return {
        "region": region_nombre,
        "columnas": columnas,
        "disponibilidad": [{"anio": f["anio"], "mes": f["mes"], "valores": {c: f["valores"].get(c, "-") for c in columnas}}
                           for f in ultimos],
        "disponibilidad_mes_region": fila_mes and fila_mes["valores"].get(region_nombre),
        "mes_publicado": fila_mes is not None,
        "incidentes_region": [i for i in incidentes if i["afecta_region"]],
        "incidentes_total_mes": len(incidentes),
    }
