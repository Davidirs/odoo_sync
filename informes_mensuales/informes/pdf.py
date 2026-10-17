"""Word → PDF con LibreOffice headless, actualizando antes el índice (TOC) y los campos.

La conversión la hace una macro Python (pdf_uno.py) que corre dentro del propio soffice, con un
perfil temporal: así el PDF sale con el índice y sus números de página y nadie tiene que aceptar
«actualizar campos». Las fuentes deben ser métricamente compatibles con las de Word (Carlito por
Calibri, Liberation por Times New Roman) para que la paginación coincida.
"""
import atexit
import json
import os
import shutil
import subprocess
import tempfile
import threading
import zipfile
from pathlib import Path

from lxml import etree

MACRO = Path(__file__).with_name("pdf_uno.py")
# Sustituciones que LibreOffice no trae: sin esto «Calibri Light» (fuente de títulos del tema de Word)
# cae en una serif. Calibri → Carlito ya viene por defecto; Arial y Times New Roman → Liberation los
# resuelve fontconfig en Linux.
SUSTITUCIONES = {"Calibri Light": "Carlito", "Calibri": "Carlito"}
# Una conversión a la vez por proceso: cada una arranca su propio soffice con un perfil del proceso
# (reutilizarlo evita el arranque en frío, que duplica el tiempo). Si una conversión falla, se descarta.
_candado = threading.Lock()
_perfil = {"ruta": None}


def _perfil_listo():
    if _perfil["ruta"] is None or not _perfil["ruta"].exists():
        _perfil["ruta"] = Path(tempfile.mkdtemp(prefix="informes_lo_"))
        atexit.register(shutil.rmtree, _perfil["ruta"], True)
    perfil = _perfil["ruta"]
    scripts = perfil / "user" / "Scripts" / "python"
    scripts.mkdir(parents=True, exist_ok=True)
    shutil.copy(MACRO, scripts / "informes_pdf.py")
    xcu = perfil / "user" / "registrymodifications.xcu"
    if not xcu.exists():
        xcu.write_text(_perfil_xcu(SUSTITUCIONES), encoding="utf-8")
    return perfil


def _descartar_perfil():
    if _perfil["ruta"] is not None:
        shutil.rmtree(_perfil["ruta"], ignore_errors=True)
        _perfil["ruta"] = None


def _soffice():
    # En macOS el soffice del PATH (Homebrew) es un script envoltorio: se prefiere el binario de la app.
    for c in (os.getenv("SOFFICE"), "/Applications/LibreOffice.app/Contents/MacOS/soffice",
              shutil.which("soffice"), shutil.which("libreoffice"), "/usr/lib/libreoffice/program/soffice"):
        if c and Path(c).exists():
            return c
    raise RuntimeError("No se encontró LibreOffice (soffice). Instálalo o define SOFFICE.")


def _perfil_xcu(sustituciones):
    pares = "".join(
        f'<node oor:name="p{i}" oor:op="replace">'
        f'<prop oor:name="Always" oor:op="fuse"><value>true</value></prop>'
        f'<prop oor:name="OnScreenOnly" oor:op="fuse"><value>false</value></prop>'
        f'<prop oor:name="ReplaceFont" oor:op="fuse"><value>{origen}</value></prop>'
        f'<prop oor:name="SubstituteFont" oor:op="fuse"><value>{destino}</value></prop></node>'
        for i, (origen, destino) in enumerate(sustituciones.items()))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            '<item oor:path="/org.openoffice.Office.Common/Font/Substitution">'
            '<prop oor:name="Replacement" oor:op="fuse"><value>true</value></prop></item>'
            f'<item oor:path="/org.openoffice.Office.Common/Font/Substitution/FontPairs">{pares}</item>'
            '</oor:items>\n')


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def sin_indice_prellenado(origen, destino):
    """Copia del .docx sin las entradas prellenadas del índice (las que pone render.py para Word).

    LibreOffice no las reconoce como parte del índice: al actualizarlo generaría el índice nuevo y
    dejaría debajo las entradas viejas. Se conservan el párrafo del campo TOC y el de cierre.
    """
    with zipfile.ZipFile(origen) as z:
        raiz = etree.fromstring(z.read("word/document.xml"))
        instr = next((t for t in raiz.iter(W + "instrText") if (t.text or "").strip().startswith("TOC")), None)
        if instr is not None:
            p = next(a for a in instr.iterancestors() if a.tag == W + "p")
            siguiente = p.getnext()
            while siguiente is not None and not any(f.get(W + "fldCharType") == "end" for f in siguiente.iter(W + "fldChar")):
                actual, siguiente = siguiente, siguiente.getnext()
                actual.getparent().remove(actual)
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as salida:
            for item in z.infolist():
                datos = etree.tostring(raiz, xml_declaration=True, encoding="UTF-8", standalone=True) \
                    if item.filename == "word/document.xml" else z.read(item.filename)
                salida.writestr(item, datos)
    return destino


def docx_a_pdf(docx, pdf, timeout=240):
    soffice = _soffice()
    docx, pdf = Path(docx).resolve(), Path(pdf).resolve()
    pdf.unlink(missing_ok=True)
    with _candado, tempfile.TemporaryDirectory(prefix="informes_pdf_") as tmp:
        perfil = _perfil_listo()
        estado = Path(tmp) / "estado.json"
        entrada = sin_indice_prellenado(docx, Path(tmp) / "entrada.docx")
        entorno = {**os.environ, "INFORME_ENTRADA": str(entrada), "INFORME_SALIDA": str(pdf), "INFORME_ESTADO": str(estado)}
        try:
            r = subprocess.run(
                [soffice, "--headless", "--invisible", "--nologo", "--norestore", "--nodefault", "--nolockcheck",
                 f"-env:UserInstallation={perfil.as_uri()}",
                 "vnd.sun.star.script:informes_pdf.py$exportar?language=Python&location=user"],
                capture_output=True, text=True, timeout=timeout, env=entorno)
        except subprocess.TimeoutExpired:
            _descartar_perfil()
            raise RuntimeError(f"LibreOffice no terminó en {timeout} s.")
        resultado = json.loads(estado.read_text(encoding="utf-8")) if estado.exists() else None
        if not (resultado and resultado["ok"]):
            _descartar_perfil()
    if not resultado:
        raise RuntimeError("LibreOffice no ejecutó la macro de exportación: "
                           + ((r.stderr or r.stdout).strip()[-600:] or f"código {r.returncode}"))
    if not resultado["ok"] or not pdf.exists():
        raise RuntimeError("LibreOffice no pudo exportar el PDF: " + resultado.get("error", "sin PDF"))
    return pdf
