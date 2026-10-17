"""Extracción de licenciamiento desde la API de LicenseManager.

Usa los mismos endpoints que el dashboard (login → subscriptionoverview) y replica
en el servidor los cálculos que hoy solo hace el frontend (genesys-dashboard.tsx):
fair use de BYOC Cloud y de Outbound, asignación de IVR y porcentajes de uso.
Si esas reglas cambian en el dashboard, hay que cambiarlas aquí también; el paso
siguiente recomendado es exponer este cálculo como endpoint en la propia API.
"""
import time
from datetime import datetime, timezone

import requests

BYOC = "Genesys Cloud BYOC Cloud"
IVR = "Genesys Cloud IVR Basic Per Minute Charge"
API_RESOURCE = "Genesys Cloud API Resource"
TRANSCRIPCION = "Genesys Cloud Voice Transcription"

# Minutos / intentos de fair use por licencia (mismas constantes que el dashboard).
BYOC_NOMINAL, BYOC_CONCURRENTE = 5000, 6500
OUTBOUND_NOMINAL, OUTBOUND_CONCURRENTE = 15000, 19500


class LicenseManager:
    def __init__(self, url, usuario, password, timeout=60):
        self.url, self.usuario, self.password, self.timeout = url, usuario, password, timeout
        self.sesion = self.org_token = self.region = None

    def login(self, org):
        r = requests.post(f"{self.url}/api/login", timeout=self.timeout,
                          json={"orgname": org, "username": self.usuario, "password": self.password})
        datos = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code != 200 or not datos.get("success"):
            raise RuntimeError(f"LicenseManager rechazó el login para '{org}': {datos.get('message') or r.status_code}")
        user = datos["user"]
        self.sesion, self.org_token, self.region = datos["sessionToken"], user.get("orgToken"), user.get("region") or "us-east-1"
        if not self.org_token:
            raise RuntimeError(f"La organización '{org}' no devolvió token de Genesys (¿existe en LicenseManager?).")
        return user

    def _headers(self):
        return {"Authorization": f"Bearer {self.sesion}"}

    def _post(self, ruta, cuerpo):
        r = requests.post(f"{self.url}{ruta}", json=cuerpo, headers=self._headers(), timeout=self.timeout)
        datos = r.json()
        if r.status_code != 200 or datos.get("success") is False:
            raise RuntimeError(f"{ruta}: {datos.get('error') or datos.get('message') or r.status_code}")
        return datos

    def resumen(self, fin_periodo="previous", intentos=3):
        # La API corta a los 20 s la consulta a Genesys; un reintento suele bastar.
        for i in range(intentos):
            try:
                return self._post("/api/subscriptionoverview",
                                  {"endDate": fin_periodo, "accessToken": self.org_token, "region": self.region})["customer"]
            except (RuntimeError, requests.RequestException):
                if i == intentos - 1:
                    raise
                time.sleep(3 * (i + 1))

    def periodos(self):
        return self._post("/api/billing/periods", {"accessToken": self.org_token, "region": self.region})["periods"]

    def intentos_outbound(self, inicio, fin, zona="America/Mexico_City"):
        r = requests.get(f"{self.url}/api/reports/outbound-attempts", headers=self._headers(), timeout=self.timeout,
                         params={"startDate": inicio, "endDate": fin, "timezone": zona,
                                 "region": self.region, "accessToken": self.org_token})
        datos = r.json()
        return datos if datos.get("success") else None


def _n(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def _pct(usado, total):
    return round(usado / total * 100, 1) if total else None


def licencias_nominales(licencias):
    """Nominales y concurrentes como los cuenta el dashboard (máx. entre contratado y usado)."""
    nominales = concurrentes = 0
    for l in licencias:
        cantidad = max(int(_n(l.get("prepayQuantity"))), int(_n(l.get("usageQuantity"))))
        nombre = l["name"].lower()
        if "concurrent" in nombre:
            concurrentes += cantidad
        elif not any(x in nombre for x in ("wallboard", "webrtc", "collaborate")):
            nominales += cantidad
    return nominales, concurrentes


def calcular_kpis(c, intentos=None):
    """Convierte la respuesta de subscriptionoverview en los KPIs del informe."""
    recursos = {r["name"]: r for r in c.get("resources") or []}
    nominales, concurrentes = licencias_nominales(c.get("licencias") or [])

    def fila(item):
        contratadas, en_uso = _n(item.get("prepayQuantity")), _n(item.get("usageQuantity"))
        return {"nombre": item["name"], "contratadas": contratadas, "en_uso": en_uso,
                "sobreuso": max(0.0, en_uso - contratadas), "pct": _pct(en_uso, contratadas)}

    licencias = [fila(l) for l in c.get("licencias") or []]
    addons = [fila(a) for a in c.get("addons") or []]

    byoc_r = recursos.get(BYOC)
    byoc_usado = _n(byoc_r and byoc_r.get("usageQuantity"))
    byoc_limite = nominales * BYOC_NOMINAL + concurrentes * BYOC_CONCURRENTE
    byoc = {
        "existe": bool(byoc_r), "usado": byoc_usado, "limite_fair_use": byoc_limite,
        "prepagado": _n(byoc_r and byoc_r.get("prepayQuantity")),
        "nominales": nominales, "concurrentes": concurrentes,
        "excedente": max(0.0, byoc_usado - byoc_limite),
        "pct": _pct(byoc_usado, byoc_limite) if byoc_limite else (100.0 if byoc_usado else 0.0),
    }

    ivr_r = recursos.get(IVR) or {}
    ivr_asignado = _n(ivr_r.get("prepayQuantity")) + _n(ivr_r.get("incluido"))
    ivr = {"existe": bool(ivr_r), "usado": _n(ivr_r.get("usageQuantity")), "asignado": ivr_asignado,
           "bajo_demanda": _n(ivr_r.get("overageQuantity")), "pct": _pct(_n(ivr_r.get("usageQuantity")), ivr_asignado)}

    otros = []
    for nombre, r in recursos.items():
        if nombre in (BYOC, IVR):
            continue
        comprometido, incluido, usado = _n(r.get("prepayQuantity")), _n(r.get("incluido")), _n(r.get("usageQuantity"))
        if not (comprometido or incluido or usado):
            continue
        otros.append({"nombre": nombre, "comprometido": comprometido, "incluido": incluido, "en_uso": usado,
                      "sobreuso": _n(r.get("overageQuantity")), "pct": _pct(usado, comprometido + incluido)})

    s = c.get("storage") or {}
    # Se recalcula: formatTrusteeBilling.js compara cantidades como texto ("1475" > "98" es falso)
    # y devuelve un sobreuso negativo (p. ej. -1,377) cuando hay subutilización.
    storage = {"comprometido": _n(s.get("comprometido")), "en_uso": _n(s.get("enUso"))}
    storage["sobreuso"] = max(0.0, storage["en_uso"] - storage["comprometido"])
    storage["pct"] = _pct(storage["en_uso"], storage["comprometido"])

    t = c.get("iaTokens") or {}
    tokens = {"nombre": t.get("name") or "AI Experience Tokens", "prepagados": _n(t.get("prepayQuantity")),
              "incluidos": _n(t.get("incluido")), "en_uso": _n(t.get("usageQuantity")), "sobreuso": _n(t.get("overageQuantity"))}
    tokens["disponible"] = tokens["prepagados"] + tokens["incluidos"]
    tokens["pct"] = _pct(tokens["en_uso"], tokens["disponible"])
    consumo_ia = [{"nombre": a["name"], "en_uso": _n(a.get("usageQuantity"))}
                  for a in c.get("aiExperience") or [] if _n(a.get("usageQuantity")) > 0]

    outbound = None
    if intentos is not None:
        limite = nominales * OUTBOUND_NOMINAL + concurrentes * OUTBOUND_CONCURRENTE
        total = _n(intentos.get("totalAttempts"))
        outbound = {"intentos": total, "limite_fair_use": limite, "excedente": max(0.0, total - limite),
                    "pct": _pct(total, limite), "campanias": len(intentos.get("campaigns") or [])}

    return {
        "organizacion": c.get("name"), "org_id": c.get("orgId"),
        "periodo": {"inicio": (c.get("facturacion") or {}).get("inicio"), "fin": (c.get("facturacion") or {}).get("final")},
        "licencias": licencias, "addons": addons, "byoc": byoc, "ivr": ivr, "recursos": otros,
        "storage": storage, "ia_tokens": tokens, "consumo_ia": consumo_ia, "outbound": outbound,
        "dispositivos": [fila(d) for d in c.get("devices") or [] if _n(d.get("usageQuantity"))],
    }


def alertas(k):
    """Alertas deterministas: los números salen de los datos, no de la IA."""
    lista = []
    for l in k["licencias"] + k["addons"]:
        if l["sobreuso"] > 0:
            lista.append({"nivel": "alta", "tema": l["nombre"],
                          "detalle": f"{l['en_uso']:,.0f} en uso frente a {l['contratadas']:,.0f} contratadas "
                                     f"({l['sobreuso']:,.0f} por encima)."})
        elif l["pct"] is not None and l["pct"] >= 90:
            lista.append({"nivel": "media", "tema": l["nombre"],
                          "detalle": f"{l['en_uso']:,.0f} en uso de {l['contratadas']:,.0f} contratadas "
                                     f"({l['pct']:.1f}%), cerca del límite."})
    b = k["byoc"]
    if b["existe"] and b["excedente"] > 0:
        lista.append({"nivel": "alta", "tema": "BYOC Cloud",
                      "detalle": f"{b['usado']:,.1f} minutos frente a un fair use de {b['limite_fair_use']:,.0f} "
                                 f"({b['excedente']:,.1f} por encima)."})
    o = k["outbound"]
    if o and o["excedente"] > 0:
        lista.append({"nivel": "alta", "tema": "Intentos outbound",
                      "detalle": f"{o['intentos']:,.0f} intentos frente a un fair use de {o['limite_fair_use']:,.0f}."})
    for r in k["recursos"]:
        if r["sobreuso"] > 0:
            lista.append({"nivel": "alta", "tema": r["nombre"],
                          "detalle": f"{r['en_uso']:,.0f} en uso, {r['sobreuso']:,.0f} por encima de lo comprometido."})
        elif r["pct"] is not None and r["pct"] >= 85:
            lista.append({"nivel": "media", "tema": r["nombre"], "detalle": f"Uso al {r['pct']:.1f}% de lo comprometido."})
    for nombre, x in (("Storage", k["storage"]), ("IA Tokens", k["ia_tokens"])):
        if x["sobreuso"] > 0:
            lista.append({"nivel": "alta", "tema": nombre, "detalle": f"Sobreuso de {x['sobreuso']:,.0f}."})
        elif x["pct"] is not None and x["pct"] >= 85:
            lista.append({"nivel": "media", "tema": nombre, "detalle": f"Uso al {x['pct']:.1f}% de lo disponible."})
    return lista


def _fila_historico(k):
    principal = max(k["licencias"], key=lambda l: (l["contratadas"], l["en_uso"]), default=None)
    recursos = {r["nombre"]: r for r in k["recursos"]}
    return {
        "periodo": k["periodo"],
        "licencias": {l["nombre"]: {"en_uso": l["en_uso"], "pct": l["pct"]} for l in k["licencias"] if l["en_uso"] or l["contratadas"]},
        "licencia_principal": principal and principal["nombre"],
        "byoc": {"en_uso": k["byoc"]["usado"], "pct": k["byoc"]["pct"]},
        "ivr": {"en_uso": k["ivr"]["usado"], "pct": k["ivr"]["pct"]},
        "api": {"en_uso": recursos.get(API_RESOURCE, {}).get("en_uso", 0), "pct": recursos.get(API_RESOURCE, {}).get("pct")},
        "transcripcion": {"en_uso": recursos.get(TRANSCRIPCION, {}).get("en_uso", 0), "pct": recursos.get(TRANSCRIPCION, {}).get("pct")},
        "storage": {"en_uso": k["storage"]["en_uso"], "pct": k["storage"]["pct"]},
        "ia_tokens": {"en_uso": k["ia_tokens"]["en_uso"], "pct": k["ia_tokens"]["pct"]},
    }


def extraer_licenciamiento(lm, org, anio, historico=True):
    """KPIs del último periodo de facturación cerrado y, opcionalmente, el histórico del año."""
    usuario = lm.login(org)
    actual = lm.resumen("previous")
    inicio, fin = (actual.get("facturacion") or {}).get("inicio"), (actual.get("facturacion") or {}).get("final")
    intentos = lm.intentos_outbound(inicio[:10], fin[:10]) if inicio and fin else None
    kpis = calcular_kpis(actual, intentos)

    filas = []
    if historico:
        fin_actual = datetime.fromisoformat(fin.replace("Z", "+00:00")) if fin else None
        for p in sorted(lm.periodos(), key=lambda p: p.get("endDate") or ""):
            fin_p = datetime.fromisoformat(p["endDate"].replace("Z", "+00:00"))
            if fin_p.year != anio or (fin_actual and fin_p > fin_actual):
                continue
            ts = int(fin_p.timestamp() * 1000)
            try:
                c = lm.resumen(str(ts))
                c.setdefault("facturacion", {})
                c["facturacion"]["inicio"], c["facturacion"]["final"] = p.get("startDate"), p.get("endDate")
                filas.append(_fila_historico(calcular_kpis(c)))
            except Exception as e:  # un periodo que falla no debe tumbar el informe
                filas.append({"periodo": {"inicio": p.get("startDate"), "fin": p.get("endDate")}, "error": str(e)})

    return {
        "region": lm.region, "ia_habilitada": usuario.get("aiEnabled"),
        "kpis": kpis, "alertas": alertas(kpis), "historico": filas,
        "extraido": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
