# Usar una imagen oficial de Python ligera
FROM python:3.11-slim

# Establecer el directorio de trabajo
WORKDIR /app

# Copiar los requerimientos e instalarlos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el script
COPY odoo_sync.py .

# Crear la carpeta data donde vivirá el estado persistente
RUN mkdir -p /app/data

# Comando para ejecutar el script
CMD ["python", "-u", "odoo_sync.py"]
