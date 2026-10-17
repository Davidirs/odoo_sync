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
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # incluye informes_mensuales en modo editable
cp .env.example .env                                                 # y completar
.venv/bin/python app.py
```
👉 Abre en tu navegador móvil o de escritorio: **[http://localhost:5050](http://localhost:5050)**

### 2. Iniciar sesión
- Cada persona entra con **su usuario y contraseña de Odoo**. Solo usuarios internos (los usuarios portal de clientes no pueden entrar).
- La app ya no inicia sesión sola con `ODOO_USER`: ese usuario de servicio lo usan el worker de WhatsApp y el informe mensual.

## 📄 Informe mensual por cliente

Pestaña **Informes por Cliente**: un botón por helpdesk de Odoo que genera el informe del mes (Odoo + License Manager + status de Genesys Cloud, redacción con DeepSeek) en **PDF** y **DOCX**, con la revisión automática (semáforo) y los textos editables. El generador es `informes_mensuales/` (ver su README); la parte web está en `informes_web.py` y `static/js/informes.js`.

- **Quién puede:** cualquier usuario interno ve y descarga; generar, editar textos, el shortname y las integraciones solo los correos/usuarios de `INFORMES_USUARIOS`.
- **Shortname en Genesys Cloud:** la organización de License Manager de cada helpdesk (p. ej. `steren`), con las empresas a excluir (p. ej. Banesco excluye «Banesco USA»). Se guarda en `data/informes_clientes.json` (en Docker, el volumen `/app/data`). Sin shortname se puede generar sin licenciamiento.
- **Variables:** `DEEPSEEK_API_KEY`, `LM_API_URL`, `LM_USER`, `LM_PASSWORD`, `INFORMES_USUARIOS` (ver `.env.example`).
- **PDF:** LibreOffice headless actualiza el índice antes de exportar. En local: `brew install --cask libreoffice font-carlito font-liberation`. La imagen Docker ya los instala.
- Tarda de 1 a 3 minutos por cliente; los informes se generan de uno en uno y el avance se ve en pantalla. Nada se envía al cliente: el borrador lo revisa una persona.

### 3. Configurar Groq (IA)
1. Toca el botón ⚙️ **Ajustes** en la barra superior.
2. Ingresa tu **API Key de Groq** (gratuita en [console.groq.com](https://console.groq.com/keys)).
3. Toca **Probar Conexión** y luego **Guardar Ajustes**.
4. ¡Listo! Ya puedes pulsar el botón **Groq IA** en cualquier ticket para obtener un análisis técnico y borrador de respuesta al instante.
