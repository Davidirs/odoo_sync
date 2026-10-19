"""Word → PDF con LibreOffice headless, actualizando antes el índice (TOC) y los campos.

La conversión la hace una macro de LibreOffice Basic (pdf_macro.bas) que corre dentro del propio
soffice, con un perfil temporal: así el PDF sale con el índice y sus números de página y nadie tiene que aceptar
«actualizar campos». Las fuentes deben ser métricamente compatibles con las de Word (Carlito por
Calibri, Liberation por Times New Roman) para que la paginación coincida.

Si la macro falla, hay un respaldo: `soffice --convert-to pdf` sobre el .docx tal cual (índice
prellenado, sin números de página). docx_a_pdf lo indica en el resultado para que la revisión
lo marque como aviso.
"""
import atexit
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile
from pathlib import Path

from lxml import etree

MACRO = Path(__file__).with_name("pdf_macro.bas")
# Sustituciones que LibreOffice no trae: sin esto «Calibri Light» (fuente de títulos del tema de Word)
# cae en una serif. Calibri → Carlito ya viene por defecto; Arial y Times New Roman → Liberation los
# resuelve fontconfig en Linux.
SUSTITUCIONES = {"Calibri Light": "Carlito", "Calibri": "Carlito"}
# Una conversión a la vez por proceso: cada una arranca su propio soffice con un perfil del proceso
# (reutilizarlo evita el arranque en frío, que duplica el tiempo). Si una conversión falla, se descarta.
_candado = threading.Lock()
_perfil = {"ruta": None}
# En contenedores Linux: si RLIMIT_NOFILE es enorme soffice reserva memoria en proporción (se baja,
# nunca se sube); el HOME puede no existir o no ser escribible; y sin pantalla conviene el plugin
# gráfico «svp». En macOS no se toca nada (el HOME da acceso a las fuentes del usuario).
LINUX = sys.platform.startswith("linux")
MAX_ARCHIVOS = 65536


def _perfil_listo(soffice):
    if _perfil["ruta"] is None or not _perfil["ruta"].exists():
        perfil = _perfil["ruta"] = Path(tempfile.mkdtemp(prefix="informes_lo_"))
        atexit.register(shutil.rmtree, perfil, True)
        (perfil / "user").mkdir(parents=True)
        (perfil / "user" / "registrymodifications.xcu").write_text(_perfil_xcu(SUSTITUCIONES), encoding="utf-8")
        # Al crear el perfil, LibreOffice reemplaza la biblioteca Basic «Standard» por la suya (y se pierde
        # la macro): se inicializa primero y la macro se instala después.
        cmd, entorno = _soffice_cmd(soffice, perfil, ["--terminate_after_init"])
        r, salida_lo = _correr(cmd, entorno, 120, "inicializar perfil")
        if r is not None and r.returncode != 0:
            _log("inicializar perfil", f"código {r.returncode}", r.stdout, r.stderr)
    perfil = _perfil["ruta"]
    _instalar_macro(perfil / "user" / "basic")
    return perfil


LIB = '<!DOCTYPE library:{tipo} PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "{dtd}">'
NS = 'xmlns:library="http://openoffice.org/2000/library"'


def _instalar_macro(basic):
    """Biblioteca Basic «Standard» del perfil con el módulo Informes (pdf_macro.bas)."""
    from xml.sax.saxutils import escape

    (basic / "Standard").mkdir(parents=True, exist_ok=True)
    cabecera = '<?xml version="1.0" encoding="UTF-8"?>\n'
    for tipo, xlb in (("script", "script.xlb"), ("dialog", "dialog.xlb")):
        (basic / f"{tipo}.xlc").write_text(
            cabecera + LIB.format(tipo="libraries", dtd="libraries.dtd")
            + f'<library:libraries {NS} xmlns:xlink="http://www.w3.org/1999/xlink">'
            f'<library:library library:name="Standard" xlink:href="$(USER)/basic/Standard/{xlb}/" '
            'xlink:type="simple" library:link="false"/></library:libraries>\n', encoding="utf-8")
    elementos = '<library:element library:name="Informes"/>'
    for xlb, contenido in (("script.xlb", elementos), ("dialog.xlb", "")):
        (basic / "Standard" / xlb).write_text(
            cabecera + LIB.format(tipo="library", dtd="library.dtd")
            + f'<library:library {NS} library:name="Standard" library:readonly="false" '
            f'library:passwordprotected="false">{contenido}</library:library>\n', encoding="utf-8")
    (basic / "Standard" / "Informes.xba").write_text(
        cabecera + '<!DOCTYPE script:module PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "module.dtd">'
        '<script:module xmlns:script="http://openoffice.org/2000/script" script:name="Informes" '
        f'script:language="StarBasic">{escape(MACRO.read_text(encoding="utf-8"))}</script:module>\n', encoding="utf-8")


def _leer_estado(ruta):
    """Lo que deja la macro: «ok» + número de índices, o «error» + mensaje. None si no llegó a escribirlo."""
    if not ruta.exists():
        return None
    lineas = ruta.read_text(encoding="utf-8", errors="replace").splitlines() + ["", ""]
    ok = lineas[0].strip() == "ok"
    return {"ok": ok, "indices": lineas[1].strip()} if ok else {"ok": False, "error": "\n".join(lineas[1:]).strip()}


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


def _soffice_cmd(soffice, perfil, argumentos, extra_env=None, linux=LINUX):
    """Comando y entorno de soffice. En Linux: límite de archivos acotado, HOME propio y plugin svp."""
    cmd = [soffice, "--headless", "--invisible", "--nologo", "--norestore", "--nolockcheck",
           f"-env:UserInstallation={perfil.as_uri()}", *argumentos]
    entorno = {**os.environ, **(extra_env or {})}
    if linux:
        home = perfil / "home"
        home.mkdir(parents=True, exist_ok=True)
        entorno.update(HOME=str(home), SAL_USE_VCLPLUGIN="svp")
        limitar = f'n=$(ulimit -n); if [ "$n" = unlimited ] || [ "$n" -gt {MAX_ARCHIVOS} ]; then ulimit -n {MAX_ARCHIVOS}; fi'
        cmd = ["/bin/sh", "-c", f'{limitar} 2>/dev/null; exec "$@"', "soffice", *cmd]
    return cmd, entorno


def _correr(cmd, entorno, timeout, etapa):
    """Ejecuta soffice; si falla, deja su salida completa en el log del servidor."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=entorno)
    except subprocess.TimeoutExpired as e:
        _log(etapa, f"no terminó en {timeout} s", e.stdout, e.stderr)
        return None, f"LibreOffice no terminó en {timeout} s"
    return r, ((r.stderr or "") + (r.stdout or "")).strip()


def _log(etapa, mensaje, stdout="", stderr=""):
    def texto(x):
        return x.decode(errors="replace") if isinstance(x, bytes) else (x or "")
    print(f"[informes.pdf] {etapa}: {mensaje}\n--- stdout ---\n{texto(stdout)}\n--- stderr ---\n{texto(stderr)}",
          file=sys.stderr, flush=True)


def _convertir_directo(soffice, perfil, docx, pdf, timeout):
    """Respaldo: conversión directa del .docx (índice prellenado, sin números de página)."""
    with tempfile.TemporaryDirectory(prefix="informes_pdf_directo_") as salida:
        cmd, entorno = _soffice_cmd(soffice, perfil, ["--convert-to", "pdf:writer_pdf_Export", "--outdir", salida, str(docx)])
        r, salida_lo = _correr(cmd, entorno, timeout, "conversión directa")
        generado = Path(salida) / (docx.stem + ".pdf")
        if r is None or r.returncode != 0 or not generado.exists():
            if r is not None:
                _log("conversión directa", f"código {r.returncode}", r.stdout, r.stderr)
            raise RuntimeError("LibreOffice no pudo convertir el documento: " + (salida_lo[-600:] or "sin salida"))
        shutil.move(str(generado), pdf)


def docx_a_pdf(docx, pdf, timeout=180):
    """Devuelve {"ruta", "respaldo", "detalle"}. respaldo=True: PDF sin números de página en el índice.

    timeout vale para cada intento (macro y respaldo). Una conversión normal tarda de 8 a 40 s; un error de
    Basic no atrapado abriría un diálogo invisible y soffice esperaría hasta el timeout.
    """
    soffice = _soffice()
    docx, pdf = Path(docx).resolve(), Path(pdf).resolve()
    pdf.unlink(missing_ok=True)
    with _candado, tempfile.TemporaryDirectory(prefix="informes_pdf_") as tmp:
        perfil = _perfil_listo(soffice)
        estado = Path(tmp) / "estado.txt"
        entrada = sin_indice_prellenado(docx, Path(tmp) / "entrada.docx")
        cmd, entorno = _soffice_cmd(
            soffice, perfil, ["--nodefault", "macro:///Standard.Informes.Exportar"],
            {"INFORME_ENTRADA": str(entrada), "INFORME_SALIDA": str(pdf), "INFORME_ESTADO": str(estado)})
        r, salida_lo = _correr(cmd, entorno, timeout, "macro")
        resultado = _leer_estado(estado)
        if resultado and resultado["ok"] and pdf.exists():
            return {"ruta": pdf, "respaldo": False, "detalle": None}

        if resultado is None:
            fallo = "LibreOffice no ejecutó la macro de exportación: " + (salida_lo[-600:] or f"código {getattr(r, 'returncode', '?')}")
        else:
            fallo = "LibreOffice no pudo exportar el PDF: " + resultado.get("error", "sin PDF")[-600:]
        if r is not None:
            _log("macro", fallo, r.stdout, r.stderr)
        _descartar_perfil()
        pdf.unlink(missing_ok=True)
        try:
            _convertir_directo(soffice, _perfil_listo(soffice), docx, pdf, timeout)
        except RuntimeError as e:
            _descartar_perfil()
            raise RuntimeError(f"{fallo} · Respaldo: {e}") from None
        return {"ruta": pdf, "respaldo": True, "detalle": fallo}
