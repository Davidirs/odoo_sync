FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo el código de la aplicación (templates, static, scripts)
COPY . .

# Dar permisos de ejecución al entrypoint
RUN chmod +x /app/entrypoint.sh

# Carpeta para datos persistentes
RUN mkdir -p /app/data

# Puerto por defecto para la interfaz web
EXPOSE 5050

# Iniciar sincronizador y servidor web simultáneamente
CMD ["/app/entrypoint.sh"]
