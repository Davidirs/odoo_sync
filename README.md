# Odoo Sync & Ticket Hub (Mobile-First + Groq IA)

Plataforma moderna y optimizada para móviles y desktop para gestionar y monitorear tickets de **Odoo Helpdesk**:
1. **Interfaz Web Mobile-First**:
   - **Modo Claro (Light Mode) por defecto** con interruptor instantáneo a **Modo Oscuro (Dark Mode)** y persistencia.
   - **Filtros completos por etapa**: ✨ *Nuevos*, ⚙️ *En Progreso*, ⏳ *En Espera*, ✅ *Resueltos*, 📁 *Cerrados*, y *Urgentes*.
   - **Botón "Ver Ticket"**: Acceso directo con 1 clic al formulario en vivo en Odoo (`https://esmtcx.odoo.com/web#id=...&model=helpdesk.ticket&view_type=form`).
   - **Asistente Inteligente Groq (IA)**: Diagnóstico en tiempo real del ticket, resumen ejecutivo y sugerencia de borrador de respuesta profesional.
   - **Ajustes e Integraciones**: Panel de configuración para Groq API Key, modelos (`llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `mixtral-8x7b-32768`, `gemma2-9b-it`) y prompts personalizados con prueba de conectividad.
   - **Copiado de Formato WhatsApp**: Con un toque copia el formato estándar con estrellas y emojis para compartir en grupos.
2. **Worker de Sincronización a WhatsApp**: Script continuo para notificar nuevos tickets entrantes.

---

## 🚀 Inicio Rápido

### 1. Iniciar la Interfaz Web
```bash
python3 app.py
```
👉 Abre en tu navegador móvil o de escritorio: **[http://localhost:5050](http://localhost:5050)**

### 2. Iniciar sesión
- **Usuario:** `ODOO_USER` configurado en tu `.env` o tu correo de Odoo.
- **Contraseña:** `ODOO_PASSWORD` de Odoo.

### 3. Configurar Groq (IA)
1. Toca el botón ⚙️ **Ajustes** en la barra superior.
2. Ingresa tu **API Key de Groq** (gratuita en [console.groq.com](https://console.groq.com/keys)).
3. Toca **Probar Conexión** y luego **Guardar Ajustes**.
4. ¡Listo! Ya puedes pulsar el botón **Groq IA** en cualquier ticket para obtener un análisis técnico y borrador de respuesta al instante.
