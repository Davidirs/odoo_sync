FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo el código de la aplicación (templates, static, scripts)
COPY . .

# Carpeta para datos persistentes
RUN mkdir -p /app/data

# Puerto por defecto para la interfaz web
EXPOSE 5050

# Iniciar servidor de producción con Gunicorn
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5050", "--timeout", "120", "app:app"]
