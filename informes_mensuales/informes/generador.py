"""Etapas del informe (datos → textos → docx → pdf) en salida/AAAA-MM/<CLIENTE>/.

Las usan generar.py (CLI) y las apps que integran el generador (odoo_sync). `avance` es un
callback opcional avance(mensaje, porcentaje) para informar del progreso.
"""
import base64
import io
import json
import shutil
from datetime import datetime, timezone

from PIL import Image

from .config import MESES, carpeta_informe, nombre_archivo
from .estado_genesys import extraer_estado
from .license_manager import LicenseManager, extraer_licenciamiento
from .odoo import Odoo, extraer_soporte
from .redaccion import RedaccionFallida, construir_encargo, errores_esquema, escribir_encargo, redactar
from .render import renderizar
from .validaciones import _r, escribir_revision, problemas_redaccion, revisar_docx, semaforo, validar

ETAPAS = ("datos", "textos", "docx", "pdf")
# Rondas en que se le devuelven a la IA los problemas que encontró la revisión de su redacción.
RONDAS_CORRECCION = 2


def _nada(mensaje, pct=None):
    pass


def leer_json(ruta):
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def guardar_json(ruta, datos):
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def cortes(fecha=None):
    """(corte UTC sin zona, corte local) para una fecha AAAA-MM-DD o ahora.

    Odoo guarda fechas en UTC; la fecha que se muestra en el informe es la local.
    """
    if fecha:
        corte = datetime.strptime(fecha, "%Y-%m-%d").replace(hour=23, minute=59)
        return corte, corte
    return datetime.now(timezone.utc).replace(tzinfo=None), datetime.now()


def etapa_datos(cfg, cliente, anio, mes, corte, corte_local, carpeta, historico=True, licenciamiento=True, avance=_nada):
    errores = {}
    avance("Leyendo tickets, conversaciones y horas en Odoo", 5)
    odoo = Odoo(cfg.odoo_url, cfg.odoo_db, cfg.odoo_user, cfg.odoo_password)
    soporte = extraer_soporte(odoo, cliente.odoo_team_id, anio, mes, corte, cliente.excluir_empresas)

    logo, logo_origen = None, None
    b64 = soporte.pop("logo_odoo_b64", None)
    if b64:
        Image.open(io.BytesIO(base64.b64decode(b64))).save(carpeta / "logo.png")
        logo, logo_origen = "logo.png", "odoo"
    elif cliente.logo_path and cliente.logo_path.exists():
        logo = "logo" + cliente.logo_path.suffix
        shutil.copy(cliente.logo_path, carpeta / logo)
        logo_origen = "archivo"

    lic = None
    if not licenciamiento:
        avance("Sin licenciamiento: no se consulta License Manager", 15)
    elif not cfg.lm_configurado:
        errores["licenciamiento"] = "faltan LM_API_URL / LM_USER / LM_PASSWORD en .env"
    elif not cliente.genesys_org:
        errores["licenciamiento"] = "el cliente no tiene organización de Genesys Cloud (genesys_org / shortname)"
    else:
        avance(f"Consultando License Manager ({cliente.genesys_org}){' e histórico del año' if historico else ''}", 15)
        try:
            lic = extraer_licenciamiento(LicenseManager(cfg.lm_api_url, cfg.lm_user, cfg.lm_password),
                                         cliente.genesys_org, anio, historico=historico)
        except Exception as e:
            errores["licenciamiento"] = str(e)

    if cliente.region_genesys:
        region, region_origen = cliente.region_genesys, "clientes.yaml"
    elif lic:
        region, region_origen = lic["region"], "license_manager"
    else:
        region, region_origen = "us-east-1", "por_defecto"

    avance("Consultando disponibilidad e incidentes en status.mypurecloud.com", 45)
    estado = None
    try:
        estado = extraer_estado(anio, mes, region, corte)
    except Exception as e:
        errores["estado"] = str(e)

    datos = {
        "cliente": {"codigo": cliente.codigo, "nombre": cliente.nombre},
        "anio": anio, "mes": mes, "periodo_txt": f"{MESES[mes]} de {anio}",
        "fecha_corte": corte_local.strftime("%d/%m/%Y"), "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "logo": logo, "logo_origen": logo_origen, "region_origen": region_origen,
        "licenciamiento_omitido": not licenciamiento,
        "soporte": soporte, "licenciamiento": lic, "estado": estado, "errores": errores,
    }
    guardar_json(carpeta / "datos.json", datos)
    return datos


def etapa_textos(cfg, carpeta, datos, rehacer, avance=_nada):
    """Redacta textos.json. Si la IA falla no hay texto de respaldo: queda redaccion_error.json
    y el documento sale con «[PENDIENTE DE REDACCIÓN]» y la revisión en rojo."""
    ruta = carpeta / "textos.json"
    if ruta.exists() and not rehacer:
        return leer_json(ruta), "existente (no se sobrescribe; usa --rehacer-textos)"
    encargo = construir_encargo(datos)
    if not cfg.ia_configurada:
        escribir_encargo(carpeta, encargo)
        return None, "pendiente: ENCARGO_REDACCION.md para Claude Code"
    avance(f"Redactando con IA ({cfg.ia_provider}: {cfg.ia_model})", 55)
    if ruta.exists():
        # Los textos anteriores (quizá editados a mano) no se pierden ni se reutilizan con datos nuevos.
        ruta.replace(carpeta / "textos.anterior.json")
    try:
        textos = redactar(encargo, cfg)
    except RedaccionFallida as e:
        guardar_json(carpeta / "redaccion_error.json", {"mensaje": str(e), "errores": e.errores,
                                                        "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        return None, f"pendiente: {e}"
    textos = autocorregir(cfg, encargo, datos, textos, avance)
    guardar_json(ruta, textos)
    (carpeta / "redaccion_error.json").unlink(missing_ok=True)
    return textos, textos["origen"]


def autocorregir(cfg, encargo, datos, textos, avance=_nada):
    """Devuelve a la IA los problemas de su redacción (ticket en curso dado por resuelto, sobreuso de BYOC
    dentro del fair use, cifras que no están en los datos…) hasta RONDAS_CORRECCION veces. Lo que siga
    mal queda en la revisión, en rojo; nunca se sustituye por texto de respaldo."""
    rondas = []
    for ronda in range(1, RONDAS_CORRECCION + 1):
        problemas = [f"{p['tema']}: {p['mensaje']}" for p in problemas_redaccion(datos, textos)]
        if not problemas:
            break
        avance(f"Corrigiendo la redacción (ronda {ronda}: {len(problemas)} {'problema' if len(problemas) == 1 else 'problemas'})",
               60 + 5 * ronda)
        try:
            corregidos = redactar(encargo, cfg, anterior=textos, problemas=problemas)
        except RedaccionFallida as e:
            rondas.append({"ronda": ronda, "problemas": problemas, "fallo": str(e)})
            break
        rondas.append({"ronda": ronda, "problemas": problemas})
        textos = corregidos
    if rondas:
        pendientes = [f"{p['tema']}: {p['mensaje']}" for p in problemas_redaccion(datos, textos)]
        textos = {**textos, "autocorreccion": {"rondas": rondas, "pendientes": pendientes}}
    return textos


def guardar_textos(carpeta, textos, origen):
    """Guarda textos editados a mano. Devuelve los errores de forma (vacío si se guardó)."""
    textos = {k: v for k, v in textos.items() if k in ("soporte", "licenciamiento")}
    if errores := errores_esquema(textos):
        return errores
    guardar_json(carpeta / "textos.json", {**textos, "origen": origen,
                                           "generado": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    (carpeta / "redaccion_error.json").unlink(missing_ok=True)
    return []


def etapa_docx(cfg, carpeta, datos, anio, mes, cliente, avance=_nada):
    avance("Generando el Word y validando", 80)
    textos = leer_json(carpeta / "textos.json") or {}
    archivo = nombre_archivo(anio, mes, cliente)
    renderizar(datos, textos, carpeta, carpeta / archivo, cfg.empresa)
    resultados = validar(datos, textos) + revisar_docx(carpeta / archivo)
    fallo = leer_json(carpeta / "redaccion_error.json")
    if fallo and not textos:
        detalle = "; ".join(fallo.get("errores") or [])[:400]
        resultados.append(_r("error", "Redacción", f"La IA no pudo redactar: {fallo['mensaje']}" + (f" ({detalle})" if detalle else "")))
    return _guardar_revision(carpeta, datos, resultados, {"cliente": cliente.codigo, "archivo": archivo})


def _guardar_revision(carpeta, datos, resultados, resumen):
    escribir_revision(carpeta / "revision.md", datos, resultados, resumen["archivo"])
    guardar_json(carpeta / "revision.json", resultados)
    resumen = {**resumen, "semaforo": semaforo(resultados),
               "errores": sum(x["nivel"] == "error" for x in resultados),
               "avisos": sum(x["nivel"] == "aviso" for x in resultados)}
    guardar_json(carpeta / "_estado.json", resumen)
    return resumen


def etapa_pdf(carpeta, resumen, datos, avance=_nada):
    """PDF con LibreOffice (índice actualizado). Un fallo aquí no invalida el Word: queda como aviso."""
    from .pdf import docx_a_pdf

    avance("Convirtiendo a PDF (LibreOffice, índice con números de página)", 90)
    docx = carpeta / resumen["archivo"]
    aviso = None
    try:
        r = docx_a_pdf(docx, docx.with_suffix(".pdf"))
        resumen = {**resumen, "pdf": r["ruta"].name, "pdf_error": None, "pdf_respaldo": r["respaldo"]}
        if r["respaldo"]:
            aviso = _r("aviso", "PDF", "Se generó con la conversión directa de LibreOffice porque falló la actualización "
                                       f"del índice: el índice del PDF no tiene números de página. ({r['detalle'][:300]})")
    except Exception as e:
        docx.with_suffix(".pdf").unlink(missing_ok=True)
        resumen = {**resumen, "pdf": None, "pdf_error": str(e), "pdf_respaldo": False}
        aviso = _r("aviso", "PDF", f"No se generó el PDF (el Word sí): {str(e)[:300]}")
    resultados = [x for x in (leer_json(carpeta / "revision.json") or []) if x["tema"] != "PDF"]
    if aviso:
        resultados.append(aviso)
    return _guardar_revision(carpeta, datos, resultados, resumen)


def generar(cfg, cliente, anio, mes, etapas=ETAPAS, corte=None, corte_local=None, rehacer_textos=False,
            historico=True, licenciamiento=True, avance=_nada):
    """Ejecuta las etapas pedidas para un cliente. Devuelve el resumen (_estado.json) o None."""
    if corte is None:
        corte, corte_local = cortes()
    carpeta = carpeta_informe(cfg, anio, mes, cliente)
    carpeta.mkdir(parents=True, exist_ok=True)
    datos = leer_json(carpeta / "datos.json")
    if "datos" in etapas or datos is None:
        datos = etapa_datos(cfg, cliente, anio, mes, corte, corte_local, carpeta, historico, licenciamiento, avance)
    origen = None
    if "textos" in etapas:
        _, origen = etapa_textos(cfg, carpeta, datos, rehacer_textos, avance)
    resumen = leer_json(carpeta / "_estado.json")
    if "docx" in etapas:
        resumen = etapa_docx(cfg, carpeta, datos, anio, mes, cliente, avance)
    if "pdf" in etapas and resumen:
        resumen = etapa_pdf(carpeta, resumen, datos, avance)
    revision_general(cfg, anio, mes)
    avance("Listo", 100)
    return {**(resumen or {}), "carpeta": str(carpeta), "textos_origen": origen, "datos": datos}


def revision_general(cfg, anio, mes):
    base = cfg.salida_dir / f"{anio:04d}-{mes:02d}"
    filas = [leer_json(p) for p in sorted(base.glob("*/_estado.json"))]
    lineas = [f"# Informes de {MESES[mes]} {anio}", "", "| Estado | Cliente | Errores | Avisos | Documento |", "|---|---|---|---|---|"]
    lineas += [f"| {f['semaforo']} | {f['cliente']} | {f['errores']} | {f['avisos']} | `{f['cliente']}/{f['archivo']}` |" for f in filas]
    lineas += ["", "Detalle de cada cliente en `<CLIENTE>/revision.md`.", ""]
    base.mkdir(parents=True, exist_ok=True)
    (base / "_REVISION_GENERAL.md").write_text("\n".join(lineas), encoding="utf-8")
