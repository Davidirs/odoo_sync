"""Macro Python que LibreOffice ejecuta dentro de su propio proceso (no se importa desde el proyecto).

pdf.py la copia al perfil temporal (user/Scripts/python/) y arranca soffice headless con
vnd.sun.star.script:informes_pdf.py$exportar. Recibe las rutas por variables de entorno:
  INFORME_ENTRADA  .docx a convertir
  INFORME_SALIDA   .pdf de destino
  INFORME_ESTADO   archivo donde deja {"ok": ..., "indices": n} o {"ok": false, "error": ...}

Abre el documento oculto, actualiza índices (TOC) y campos, exporta a PDF y cierra soffice.
"""
import json
import os
import traceback

import uno
from com.sun.star.beans import PropertyValue


def _prop(nombre, valor):
    p = PropertyValue()
    p.Name, p.Value = nombre, valor
    return p


def exportar(*_):
    desktop = XSCRIPTCONTEXT.getDesktop()  # noqa: F821 (lo inyecta LibreOffice)
    estado = {"ok": False}
    try:
        doc = desktop.loadComponentFromURL(uno.systemPathToFileUrl(os.environ["INFORME_ENTRADA"]), "_blank", 0,
                                           (_prop("Hidden", True),))
        if doc is None:
            raise RuntimeError("LibreOffice no pudo abrir el documento")
        try:
            # Dos pasadas: la primera rellena el índice (puede cambiar la paginación), la segunda fija los números.
            for _ in range(2):
                indices = doc.getDocumentIndexes()
                for i in range(indices.getCount()):
                    indices.getByIndex(i).update()
                doc.getTextFields().refresh()
            doc.storeToURL(uno.systemPathToFileUrl(os.environ["INFORME_SALIDA"]),
                           (_prop("FilterName", "writer_pdf_Export"),))
            estado = {"ok": True, "indices": indices.getCount()}
        finally:
            doc.close(True)
    except Exception:
        estado = {"ok": False, "error": traceback.format_exc()[-1500:]}
    finally:
        with open(os.environ["INFORME_ESTADO"], "w", encoding="utf-8") as f:
            json.dump(estado, f)
        desktop.terminate()


g_exportedScripts = (exportar,)
