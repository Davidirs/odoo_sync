#!/bin/bash
set -e

# Puerto configurable (por defecto 5050)
PORT="${PORT:-5050}"

echo "================================================="
echo "🚀 Iniciando Odoo Hub en Producción"
echo "================================================="

# Iniciar el Worker de Sincronización en segundo plano
echo "🤖 [Worker] Iniciando sincronizador de tickets de WhatsApp (odoo_sync.py)..."
python -u odoo_sync.py &
WORKER_PID=$!

# Iniciar Servidor Web con Gunicorn
echo "🌐 [Gunicorn] Iniciando servidor web en el puerto ${PORT}..."
gunicorn -w 2 -b "0.0.0.0:${PORT}" --timeout 120 app:app &
WEB_PID=$!

# Manejador para apagar limpiamente ambos procesos ante SIGTERM o SIGINT
cleanup() {
    echo ""
    echo "🛑 Recibida señal de apagado. Terminando procesos limpiamente..."
    kill -TERM "$WORKER_PID" 2>/dev/null || true
    kill -TERM "$WEB_PID" 2>/dev/null || true
    wait "$WORKER_PID" 2>/dev/null || true
    wait "$WEB_PID" 2>/dev/null || true
    echo "👋 Apagado completado."
    exit 0
}

trap cleanup SIGTERM SIGINT

# Esperar a que finalice cualquiera de los procesos
wait -n "$WORKER_PID" "$WEB_PID"
EXIT_CODE=$?

echo "⚠️ Uno de los servicios finalizó (código: $EXIT_CODE). Deteniendo el resto..."
cleanup
