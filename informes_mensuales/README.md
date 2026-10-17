# Informes mensuales ESMT

Genera el borrador del informe mensual de cada cliente (soporte en Odoo, licenciamiento en License Manager y disponibilidad de Genesys Cloud) en Word y PDF, con la plantilla ESMT, y deja una revisión automática para que una persona lo apruebe.

Vive dentro de odoo_sync (`odoo_sync/informes_mensuales/`) y es un paquete instalable (`informes`): odoo_sync lo usa para el botón «Generar informe» de cada helpdesk (ver `../informes_web.py`) y este CLI sigue funcionando por su cuenta. La lógica está una sola vez, en `informes/` (`generador.py` orquesta las etapas).

```
clientes.yaml ─┐
.env ──────────┤
               ▼
generar.py ── datos ──► Odoo (XML-RPC, solo lectura)            ┐
          │            License Manager API (KPIs + fair use)    ├─► datos.json
          │            status.mypurecloud.com (tabla + API)     ┘
          ├── textos ─► API de Claude o DeepSeek, o encargo para Claude Code ─► textos.json
          ├── docx ───► plantilla/informe_esmt.docx + gráficas ──► INFORME MENSUAL <MES> <CLIENTE>.docx
          │             validaciones ───────────────────────────► revision.md, revision.json, _REVISION_GENERAL.md
          └── pdf ────► LibreOffice headless (índice actualizado) ─► INFORME MENSUAL <MES> <CLIENTE>.pdf
```

## Instalación

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # instala el paquete en modo editable
cp .env.example .env   # y completar credenciales
```

Para el PDF hace falta LibreOffice y fuentes métricamente compatibles con las de Word (si no, la paginación y el índice no coinciden con Word):

```bash
brew install --cask libreoffice font-carlito font-liberation          # macOS
apt-get install libreoffice-writer-nogui libreoffice-script-provider-python fonts-crosextra-carlito fonts-liberation   # Debian
```

## Uso

```bash
.venv/bin/python generar.py --mes 2026-09 --cliente STEREN     # un cliente
.venv/bin/python generar.py --mes 2026-09 --todos              # todos los activos
.venv/bin/python generar.py --mes 2026-09 --cliente STEREN --etapas docx,pdf   # re-renderizar tras editar textos.json
.venv/bin/python generar.py --mes 2026-09 --cliente NUEVO --sin-licenciamiento   # cliente sin organización en License Manager
```

Con Claude Code, la skill `/informe-mensual` hace el ciclo completo: datos, redacción, documento y revisión.

Salida en `salida/AAAA-MM/<CLIENTE>/`:

| Archivo | Qué es |
|---|---|
| `INFORME MENSUAL <MES> <CLIENTE>.pdf` | El borrador en PDF, con el índice y sus números de página. |
| `INFORME MENSUAL <MES> <CLIENTE>.docx` | El mismo borrador editable. Al abrirlo en Word, aceptar «actualizar campos» para el índice. |
| `revision.md` / `revision.json` | Semáforo y lista de errores/avisos para quien revisa. |
| `datos.json` | Foto de los datos usados (trazabilidad: de dónde sale cada número). |
| `textos.json` | Textos redactados; se pueden editar a mano y re-renderizar. |
| `graficas/` | PNG de las gráficas. |

## Qué decide el código y qué redacta la IA

- **Código (determinista):** conteos, horas, días, estados, tablas, alertas de licenciamiento, fair use de BYOC/Outbound, disponibilidad e incidentes, y las frases con cifras (introducción, promedio, estados).
- **IA (acotada):** el resumen de cada ticket, una frase de patrones del mes y la lectura ejecutiva del licenciamiento. No tiene acceso a herramientas ni credenciales; recibe JSON y devuelve JSON. Con DeepSeek (`IA_PROVIDER=deepseek`) la respuesta se valida contra el esquema y se reintenta con los errores; si sigue sin cuadrar, no hay texto de respaldo: el documento lleva «[PENDIENTE DE REDACCIÓN]», queda `redaccion_error.json` y la revisión sale en rojo.
- **Validaciones:** sumas que cuadran, ningún ticket en curso descrito como resuelto, sin teléfonos/correos/IDs en los textos, cifras de la narrativa presentes en los datos, BYOC no llamado sobreuso si está dentro del fair use, periodo de facturación correcto, logo, región.

## Configuración

- **Alta de cliente:** en odoo_sync, el campo «Shortname en Genesys Cloud» de cada helpdesk (se guarda en `data/informes_clientes.json`, precargado desde `clientes.yaml`). Para el CLI, una entrada en `clientes.yaml` (helpdesk de Odoo, `orgname` de License Manager y logo).
- **Plantilla:** `plantilla/informe_esmt.docx` se puede editar en Word (textos fijos, estilos, colores) sin tocar las etiquetas `{{ ... }}` / `{%p ... %}`. La sección de licenciamiento va entre `{%p if not lic_omitido %}` … `{%p endif %}` para los informes sin licenciamiento. Si se rediseña desde un informe nuevo: `.venv/bin/python plantilla/construir_plantilla.py "<informe aprobado>.docx"`.
- **Reglas de licenciamiento:** `informes/license_manager.py` replica el cálculo del dashboard (`genesys-dashboard.tsx`). Si el dashboard cambia, hay que cambiarlo aquí; lo ideal es exponer ese cálculo como endpoint en la API de License Manager.

## Comparar con un informe manual

```bash
.venv/bin/python comparar.py "/ruta/INFORME MENSUAL SEPTIEMBRE STEREN.docx" salida/2026-09/STEREN
```
