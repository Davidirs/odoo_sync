FROM python:3.13-slim

WORKDIR /app

# Informe mensual en PDF: LibreOffice (solo Writer, sin interfaz) y fuentes métricamente compatibles
# con las de Word: Carlito ↔ Calibri, Liberation ↔ Times New Roman / Arial. La macro que actualiza el
# índice es Basic: sin el script provider de Python, que traería un segundo libpython (el de Debian)
# junto al de esta imagen.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice-writer-nogui \
        fonts-crosextra-carlito fonts-liberation fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias. El generador del informe (informes_mensuales/) se instala en modo
# editable: lee su plantilla (plantilla/informe_esmt.docx) y logos desde /app/informes_mensuales.
COPY requirements.txt .
COPY informes_mensuales/pyproject.toml informes_mensuales/
COPY informes_mensuales/informes/ informes_mensuales/informes/
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo el código de la aplicación (templates, static, scripts, plantilla del informe)
COPY . .

# Dar permisos de ejecución al entrypoint
RUN chmod +x /app/entrypoint.sh

# Carpeta para datos persistentes (montar como volumen: sesiones, clientes e informes generados)
RUN mkdir -p /app/data

# Puerto por defecto para la interfaz web
EXPOSE 5050

# Iniciar sincronizador y servidor web simultáneamente
CMD ["/app/entrypoint.sh"]
