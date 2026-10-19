REM Macro de LibreOffice Basic que usa pdf.py (no se importa desde Python).
REM pdf.py la instala en el perfil temporal (user/basic/Standard/Informes.xba) y arranca soffice con
REM macro:///Standard.Informes.Exportar. Es Basic y no Python para no depender del script provider de
REM Python ni de qué libpython carga LibreOffice. Recibe las rutas por variables de entorno:
REM   INFORME_ENTRADA  .docx a convertir
REM   INFORME_SALIDA   .pdf de destino
REM   INFORME_ESTADO   archivo donde deja "ok" + número de índices, o "error" + mensaje
REM Abre el documento oculto, actualiza índices (TOC) y campos, exporta a PDF y cierra soffice.

Sub Exportar
    Dim estado As String, n As Integer, pasada As Integer, i As Integer
    Dim doc As Object, indices As Object
    estado = Environ("INFORME_ESTADO")
    On Error GoTo Fallo
    Dim abrir(0) As New com.sun.star.beans.PropertyValue
    abrir(0).Name = "Hidden"
    abrir(0).Value = True
    doc = StarDesktop.loadComponentFromURL(ConvertToURL(Environ("INFORME_ENTRADA")), "_blank", 0, abrir())
    If IsNull(doc) Then
        Escribir(estado, "error", "LibreOffice no pudo abrir el documento")
        StarDesktop.terminate()
        Exit Sub
    End If
    REM Dos pasadas: la primera rellena el índice (puede cambiar la paginación), la segunda fija los números.
    For pasada = 1 To 2
        indices = doc.getDocumentIndexes()
        For i = 0 To indices.getCount() - 1
            indices.getByIndex(i).update()
        Next i
        doc.getTextFields().refresh()
    Next pasada
    n = indices.getCount()
    Dim pdf(0) As New com.sun.star.beans.PropertyValue
    pdf(0).Name = "FilterName"
    pdf(0).Value = "writer_pdf_Export"
    doc.storeToURL(ConvertToURL(Environ("INFORME_SALIDA")), pdf())
    doc.close(True)
    Escribir(estado, "ok", CStr(n))
    StarDesktop.terminate()
    Exit Sub
Fallo:
    Escribir(estado, "error", "Basic, linea " & Erl & ": " & Error$)
    On Error Resume Next
    doc.close(True)
    StarDesktop.terminate()
End Sub

Sub Escribir(ruta As String, resultado As String, detalle As String)
    Dim f As Integer
    f = FreeFile
    Open ruta For Output As #f
    Print #f, resultado
    Print #f, detalle
    Close #f
End Sub
