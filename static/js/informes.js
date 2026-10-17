/* Informe mensual por cliente (pestaña «Informes por Cliente»).
 * API en informes_web.py. La generación corre en el servidor y el avance llega por SSE.
 * Usa window.OdooHub (showToast, escapeHtml, updateIcons) que define app.js. */
(function () {
    const MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
        "Septiembre", "Octubre", "Noviembre", "Diciembre"];
    const NIVEL = { error: "🔴", aviso: "🟡", ok: "🟢" };

    const st = {
        usuario: null, puedeGenerar: false, cargado: false, datos: null,
        detalle: null, // { teamId, info }
        progreso: {},  // teamId → { jobId, mensaje, pct, fuente }
    };
    const $ = (id) => document.getElementById(id);
    const hub = () => window.OdooHub || { showToast: alert, escapeHtml: (t) => String(t ?? ""), updateIcons() {} };
    const esc = (t) => hub().escapeHtml(t == null ? "" : String(t));
    const toast = (m) => hub().showToast(m);

    // ------------------------------------------------------------------ utilidades
    function mesSeleccionado() {
        return `${$("inf-anio").value}-${String($("inf-mes").value).padStart(2, "0")}`;
    }

    function prepararFiltros() {
        const hoy = new Date();
        const anterior = new Date(hoy.getFullYear(), hoy.getMonth() - 1, 1);
        $("inf-mes").innerHTML = MESES.map((m, i) => `<option value="${i + 1}">${m}</option>`).join("");
        const anios = [];
        for (let a = hoy.getFullYear(); a >= hoy.getFullYear() - 2; a--) anios.push(a);
        $("inf-anio").innerHTML = anios.map((a) => `<option value="${a}">${a}</option>`).join("");
        $("inf-mes").value = anterior.getMonth() + 1;
        $("inf-anio").value = anterior.getFullYear();
        $("inf-mes").addEventListener("change", cargar);
        $("inf-anio").addEventListener("change", cargar);
        $("inf-buscar").addEventListener("input", pintarLista);
        $("inf-solo-config").addEventListener("change", pintarLista);
    }

    async function api(url, opciones = {}) {
        const res = await fetch(url, {
            ...opciones,
            headers: { "Content-Type": "application/json", ...(opciones.headers || {}) },
        });
        let data = {};
        try { data = await res.json(); } catch (e) { /* respuesta sin JSON */ }
        if (!res.ok || data.success === false) {
            const err = new Error(data.error || `Error ${res.status}`);
            err.detalle = data.detalle;
            throw err;
        }
        return data;
    }

    function fecha(iso) {
        if (!iso) return "";
        const d = new Date(iso);
        return isNaN(d) ? iso : d.toLocaleString("es", { dateStyle: "short", timeStyle: "short" });
    }

    function semaforoHtml(estado) {
        if (!estado) return `<span class="inf-semaforo inf-sem-vacio">Sin generar</span>`;
        const clase = estado.errores ? "inf-sem-rojo" : (estado.avisos ? "inf-sem-amarillo" : "inf-sem-verde");
        const partes = [];
        partes.push(`${estado.errores} ${estado.errores === 1 ? "error" : "errores"}`);
        partes.push(`${estado.avisos} ${estado.avisos === 1 ? "aviso" : "avisos"}`);
        return `<span class="inf-semaforo ${clase}">${estado.semaforo || ""} ${partes.join(" · ")}</span>`;
    }

    function enlacesArchivos(teamId, estado) {
        if (!estado) return "";
        const base = `/api/informes/${mesSeleccionado()}/${teamId}/archivo`;
        const pdf = estado.pdf
            ? `<a class="btn-secondary" href="${base}/pdf?ver=1" target="_blank" rel="noopener"><i data-lucide="file-text"></i> Ver PDF</a>
               <a class="btn-secondary" href="${base}/pdf"><i data-lucide="download"></i> PDF</a>`
            : (estado.pdf_error ? `<span class="inf-error-corto" title="${esc(estado.pdf_error)}">PDF no generado</span>` : "");
        return `${pdf}<a class="btn-secondary" href="${base}/docx"><i data-lucide="file-type"></i> DOCX</a>`;
    }

    function progresoHtml(teamId) {
        const p = st.progreso[teamId];
        if (!p) return "";
        const pct = Math.max(2, Math.min(100, p.pct || 0));
        return `<div class="inf-progreso">
            <div class="report-progress-bar-bg"><div class="report-progress-bar-fill" style="width:${pct}%"></div></div>
            <div class="report-progress-labels"><span>${esc(p.mensaje || "Trabajando…")}</span><span>${p.pct ? Math.round(p.pct) + "%" : ""}</span></div>
        </div>`;
    }

    // ------------------------------------------------------------------ lista de helpdesks
    async function cargar() {
        const lista = $("inf-lista");
        lista.innerHTML = `<div class="inf-vacio glass-panel">Cargando helpdesks de Odoo…</div>`;
        $("inf-detalle").classList.add("hidden");
        lista.classList.remove("hidden");
        try {
            st.datos = await api(`/api/informes/clientes?mes=${mesSeleccionado()}`);
            st.puedeGenerar = st.datos.puede_generar;
            st.cargado = true;
            pintarAvisos();
            pintarLista();
            st.datos.clientes.filter((c) => c.trabajo).forEach((c) => seguir(c.team_id, c.trabajo));
        } catch (e) {
            lista.innerHTML = `<div class="inf-vacio glass-panel inf-error">${esc(e.message)}</div>`;
        }
    }

    function pintarAvisos() {
        const d = st.datos;
        const avisos = [];
        if (!st.puedeGenerar) avisos.push(["aviso", "Solo lectura: tu usuario no está en INFORMES_USUARIOS, puedes ver y descargar pero no generar ni editar."]);
        if (!d.lm_configurado) avisos.push(["error", "License Manager no está configurado (LM_API_URL, LM_USER, LM_PASSWORD en .env): los informes con licenciamiento saldrán en rojo."]);
        if (!d.ia_configurada) avisos.push(["error", "DEEPSEEK_API_KEY no está configurada: los textos quedarán pendientes de redacción."]);
        if (!d.pdf_disponible) avisos.push(["error", "LibreOffice no está instalado en el servidor: solo se generará el Word."]);
        avisos.push(["info", `Redacción con ${d.ia_modelo || "DeepSeek"}. Las cifras, tablas y alertas las calcula el sistema; la IA solo redacta.`]);
        $("inf-avisos").innerHTML = avisos.map(([n, t]) => `<div class="inf-aviso inf-aviso-${n}">${esc(t)}</div>`).join("");
    }

    function pintarLista() {
        if (!st.datos) return;
        const filtro = $("inf-buscar").value.trim().toLowerCase();
        const soloConfig = $("inf-solo-config").checked;
        const clientes = st.datos.clientes
            .filter((c) => !filtro || c.helpdesk.toLowerCase().includes(filtro) || c.nombre.toLowerCase().includes(filtro))
            .filter((c) => !soloConfig || filtro || c.genesys_org || c.estado || st.progreso[c.team_id])
            .sort((a, b) => (!!b.genesys_org - !!a.genesys_org) || a.helpdesk.localeCompare(b.helpdesk));
        const lista = $("inf-lista");
        if (!clientes.length) {
            lista.innerHTML = `<div class="inf-vacio glass-panel">No hay helpdesks que mostrar${soloConfig ? " (desmarca el filtro para ver todos)" : ""}.</div>`;
            return;
        }
        lista.innerHTML = clientes.map(tarjetaHtml).join("");
        lista.querySelectorAll("[data-accion]").forEach((b) => b.addEventListener("click", accionTarjeta));
        hub().updateIcons();
    }

    function tarjetaHtml(c) {
        const ocupado = !!st.progreso[c.team_id];
        const dis = st.puedeGenerar ? "" : "disabled";
        const generar = !st.puedeGenerar ? "" : c.genesys_org
            ? `<button class="btn-primary btn-generate-report inf-btn" data-accion="generar" data-team="${c.team_id}" ${ocupado ? "disabled" : ""}>
                   <i data-lucide="file-cog"></i> Generar informe</button>`
            : `<button class="btn-secondary inf-btn" data-accion="generar-sin-lic" data-team="${c.team_id}" ${ocupado ? "disabled" : ""}>
                   <i data-lucide="file-minus"></i> Generar sin licenciamiento</button>`;
        const meta = c.web && c.web.generado
            ? `Generado ${fecha(c.web.generado)} por ${esc(c.web.generado_por || "")}${c.web.sin_licenciamiento ? " · sin licenciamiento" : ""}`
            : "";
        return `<article class="inf-tarjeta glass-panel" data-team="${c.team_id}">
            <div class="inf-tarjeta-cab">
                <img class="inf-logo" src="/api/team_logo/${c.team_id}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">
                <div class="inf-tarjeta-nombre">
                    <strong>${esc(c.helpdesk)}</strong>
                    <span>Código ${esc(c.codigo)}${c.genesys_org ? ` · Genesys Cloud: ${esc(c.genesys_org)}` : " · sin shortname"}</span>
                </div>
                ${semaforoHtml(c.estado)}
            </div>
            <form class="inf-config" data-team="${c.team_id}">
                <label class="inf-campo"><span>Shortname en Genesys Cloud</span>
                    <input class="inf-input" name="genesys_org" value="${esc(c.genesys_org)}" placeholder="p. ej. steren" ${dis} autocomplete="off"></label>
                <label class="inf-campo"><span>Nombre en el informe</span>
                    <input class="inf-input" name="nombre" value="${esc(c.nombre)}" ${dis} autocomplete="off"></label>
                <label class="inf-campo inf-campo-ancho"><span>Empresas a excluir (separadas por coma)</span>
                    <input class="inf-input" name="excluir_empresas" value="${esc((c.excluir_empresas || []).join(", "))}" placeholder="p. ej. Banesco USA" ${dis} autocomplete="off"></label>
                ${st.puedeGenerar ? `<button type="button" class="btn-secondary" data-accion="guardar" data-team="${c.team_id}"><i data-lucide="save"></i> Guardar</button>` : ""}
            </form>
            <div class="inf-acciones">
                ${generar}
                ${c.estado ? `<button class="btn-secondary" data-accion="revisar" data-team="${c.team_id}"><i data-lucide="clipboard-check"></i> Revisión y textos</button>` : ""}
                ${enlacesArchivos(c.team_id, c.estado)}
            </div>
            <div data-progreso="${c.team_id}">${progresoHtml(c.team_id)}</div>
            ${meta ? `<p class="inf-meta">${meta}</p>` : ""}
        </article>`;
    }

    function clienteDe(teamId) {
        return (st.datos?.clientes || []).find((c) => c.team_id === teamId);
    }

    async function accionTarjeta(ev) {
        const boton = ev.currentTarget;
        const teamId = Number(boton.dataset.team);
        const accion = boton.dataset.accion;
        if (accion === "guardar") return guardarConfig(teamId, boton);
        if (accion === "revisar") return abrirDetalle(teamId);
        if (accion === "generar" || accion === "generar-sin-lic") {
            const c = clienteDe(teamId);
            const sinLic = accion === "generar-sin-lic";
            const aviso = c && c.estado ? "\n\nSe vuelven a leer los datos y a redactar los textos; si los editaste, la versión anterior queda en textos.anterior.json." : "";
            if (!confirm(`¿Generar el informe de ${MESES[Number($("inf-mes").value) - 1].toLowerCase()} ${$("inf-anio").value} para ${c ? c.helpdesk : teamId}${sinLic ? " sin licenciamiento" : ""}?${aviso}`)) return;
            boton.disabled = true;
            try {
                const r = await api("/api/informes/generar", {
                    method: "POST", body: JSON.stringify({ team_id: teamId, mes: mesSeleccionado(), sin_licenciamiento: sinLic }),
                });
                seguir(teamId, r.job_id);
            } catch (e) {
                boton.disabled = false;
                toast(`❌ ${e.message}`);
            }
        }
    }

    async function guardarConfig(teamId, boton) {
        const form = document.querySelector(`.inf-config[data-team="${teamId}"]`);
        const datos = Object.fromEntries(new FormData(form).entries());
        boton.disabled = true;
        try {
            await api(`/api/informes/clientes/${teamId}`, { method: "PUT", body: JSON.stringify(datos) });
            toast("Configuración del helpdesk guardada");
            await cargar();
        } catch (e) {
            toast(`❌ ${e.message}`);
            boton.disabled = false;
        }
    }

    // ------------------------------------------------------------------ avance (SSE)
    function seguir(teamId, jobId) {
        if (st.progreso[teamId] && st.progreso[teamId].jobId === jobId) return;
        const fuente = new EventSource(`/api/informes/jobs/${jobId}/eventos`);
        st.progreso[teamId] = { jobId, mensaje: "Iniciando…", pct: 0, fuente };
        refrescarProgreso(teamId);
        fuente.onmessage = (ev) => {
            const e = JSON.parse(ev.data);
            const p = st.progreso[teamId];
            if (!p) return;
            if (e.tipo === "avance" || e.tipo === "cola") {
                p.mensaje = e.mensaje;
                if (e.pct != null) p.pct = e.pct;
                refrescarProgreso(teamId);
            } else if (e.tipo === "fin" || e.tipo === "error") {
                fuente.close();
                delete st.progreso[teamId];
                if (e.tipo === "fin") {
                    const r = e.estado || {};
                    toast(`${r.semaforo || "✔"} Informe listo: ${r.errores ?? "?"} errores, ${r.avisos ?? "?"} avisos${r.pdf ? "" : " · sin PDF"}`);
                } else {
                    toast(`❌ ${e.error}`);
                }
                terminado(teamId);
            }
        };
        fuente.onerror = () => {
            // El servidor cerró el flujo o se reinició: se deja de seguir y se recarga el estado.
            fuente.close();
            if (st.progreso[teamId] && st.progreso[teamId].jobId === jobId) {
                delete st.progreso[teamId];
                terminado(teamId);
            }
        };
    }

    function refrescarProgreso(teamId) {
        document.querySelectorAll(`[data-progreso="${teamId}"]`).forEach((n) => { n.innerHTML = progresoHtml(teamId); });
        document.querySelectorAll(`[data-team="${teamId}"][data-accion^="generar"], #inf-detalle [data-requiere-libre]`)
            .forEach((b) => { b.disabled = !!st.progreso[teamId]; });
    }

    async function terminado(teamId) {
        if (st.detalle && st.detalle.teamId === teamId && !$("inf-detalle").classList.contains("hidden")) {
            await abrirDetalle(teamId, true);
        }
        try {
            st.datos = await api(`/api/informes/clientes?mes=${mesSeleccionado()}`);
            pintarLista();
        } catch (e) { /* la lista se recarga al volver */ }
    }

    // ------------------------------------------------------------------ detalle: revisión y textos
    async function abrirDetalle(teamId, conservarScroll = false) {
        const panel = $("inf-detalle");
        const c = clienteDe(teamId);
        if (!conservarScroll) panel.innerHTML = `<div class="inf-vacio">Cargando revisión…</div>`;
        panel.classList.remove("hidden");
        $("inf-lista").classList.add("hidden");
        try {
            const info = await api(`/api/informes/${mesSeleccionado()}/${teamId}`);
            st.detalle = { teamId, info };
            panel.innerHTML = detalleHtml(teamId, c, info);
            panel.querySelector("[data-accion='volver']").addEventListener("click", cerrarDetalle);
            panel.querySelector("[data-accion='guardar-textos']")?.addEventListener("click", () => guardarTextos(teamId));
            panel.querySelector("[data-accion='redactar']")?.addEventListener("click", () => redactar(teamId));
            if (info.trabajo) seguir(teamId, info.trabajo);
            refrescarProgreso(teamId);
            hub().updateIcons();
            if (!conservarScroll) panel.scrollIntoView({ behavior: "smooth", block: "start" });
        } catch (e) {
            panel.innerHTML = `<button class="btn-secondary" data-accion="volver"><i data-lucide="arrow-left"></i> Volver</button>
                <div class="inf-vacio inf-error">${esc(e.message)}</div>`;
            panel.querySelector("[data-accion='volver']").addEventListener("click", cerrarDetalle);
            hub().updateIcons();
        }
    }

    function cerrarDetalle() {
        $("inf-detalle").classList.add("hidden");
        $("inf-lista").classList.remove("hidden");
        st.detalle = null;
        pintarLista();
    }

    function parrafos(lista) {
        return (lista || []).join("\n\n");
    }

    function detalleHtml(teamId, c, info) {
        const nombre = c ? c.helpdesk : `Helpdesk ${teamId}`;
        const periodo = `${MESES[Number($("inf-mes").value) - 1]} ${$("inf-anio").value}`;
        if (!info.existe) {
            return `<div class="inf-detalle-cab"><button class="btn-secondary" data-accion="volver"><i data-lucide="arrow-left"></i> Volver</button>
                <h3 class="inf-titulo">${esc(nombre)} · ${periodo}</h3></div>
                <div class="inf-vacio">Aún no hay informe de este mes.</div>`;
        }
        const r = info.resumen_datos;
        const t = info.textos || { soporte: { destacados: [], tickets: [] }, licenciamiento: { resumen: [], alertas: [] } };
        const resumenes = Object.fromEntries((t.soporte?.tickets || []).map((x) => [x.id, x.resumen]));
        const dis = st.puedeGenerar ? "" : "disabled";
        const lic = r.licenciamiento;
        const datosTxt = [`${r.tickets} tickets`, `${Number(r.horas).toFixed(2)} h`, `datos al ${esc(r.fecha_corte)}`,
            r.licenciamiento_omitido ? "sin licenciamiento" : (lic ? `licenciamiento de ${esc(r.organizacion || "")}` : "licenciamiento NO disponible")];
        const pendiente = info.redaccion_error
            ? `<div class="inf-aviso inf-aviso-error"><strong>Redacción pendiente.</strong> ${esc(info.redaccion_error.mensaje)}
                ${(info.redaccion_error.errores || []).length ? `<br><small>${esc(info.redaccion_error.errores.slice(0, 4).join("; "))}</small>` : ""}
                <br>El documento lleva «[PENDIENTE DE REDACCIÓN]». Vuelve a redactar con IA o escribe los textos aquí.</div>`
            : (!info.textos ? `<div class="inf-aviso inf-aviso-error"><strong>Sin textos.</strong> Vuelve a redactar con IA o escríbelos aquí.</div>` : "");

        return `
        <div class="inf-detalle-cab">
            <button class="btn-secondary" data-accion="volver"><i data-lucide="arrow-left"></i> Volver</button>
            <div class="inf-detalle-titulo">
                <h3 class="inf-titulo">${esc(nombre)} · ${periodo}</h3>
                <span class="inf-meta">${datosTxt.join(" · ")}${info.textos ? ` · textos: ${esc(info.textos.origen || "")}` : ""}</span>
            </div>
            ${semaforoHtml(info.estado)}
        </div>
        <div class="inf-acciones">
            ${enlacesArchivos(teamId, info.estado)}
            ${st.puedeGenerar ? `<button class="btn-secondary" data-accion="redactar" data-requiere-libre><i data-lucide="sparkles"></i> Volver a redactar con IA</button>` : ""}
        </div>
        <div data-progreso="${teamId}">${progresoHtml(teamId)}</div>
        ${info.estado && info.estado.pdf_error ? `<div class="inf-aviso inf-aviso-error"><strong>No se generó el PDF.</strong> ${esc(info.estado.pdf_error)}</div>` : ""}

        <h4 class="inf-seccion">Revisión automática</h4>
        <p class="inf-ayuda">Errores (🔴): no enviar sin corregir. Avisos (🟡): revisar. Los errores de datos se corrigen en Odoo o License Manager y se vuelve a generar.</p>
        <ul class="inf-revision">
            ${(info.revision || []).map((x) => `<li class="inf-nivel-${x.nivel}"><span>${NIVEL[x.nivel] || ""}</span><strong>${esc(x.tema)}</strong><span>${esc(x.mensaje)}</span></li>`).join("")}
        </ul>

        <h4 class="inf-seccion">Textos redactados</h4>
        <p class="inf-ayuda">Solo la redacción es editable; conteos, tablas y alertas los pone el sistema. Separa párrafos con una línea en blanco. Al guardar se regeneran el Word y el PDF.</p>
        ${pendiente}
        <div class="inf-textos">
            <label class="inf-campo inf-campo-ancho"><span>Patrones del mes (opcional)</span>
                <textarea class="inf-input" rows="3" data-campo="destacados" ${dis}>${esc(parrafos(t.soporte?.destacados))}</textarea></label>
            ${info.tickets.map((k) => `
            <div class="inf-ticket">
                <div class="inf-ticket-cab"><strong>${esc(k.asunto)} (#${k.id})</strong>
                    <span class="inf-etiqueta ${k.en_curso ? "inf-etiqueta-curso" : ""}">${esc(k.tipo)} · ${esc(k.etapa)}${k.en_curso ? " · en curso" : ""}</span></div>
                <textarea class="inf-input" rows="3" data-ticket="${k.id}" ${dis}>${esc(resumenes[k.id] || "")}</textarea>
            </div>`).join("")}
            ${lic ? `
            <label class="inf-campo inf-campo-ancho"><span>Licenciamiento · resumen ejecutivo</span>
                <textarea class="inf-input" rows="5" data-campo="lic_resumen" ${dis}>${esc(parrafos(t.licenciamiento?.resumen))}</textarea></label>
            <label class="inf-campo inf-campo-ancho"><span>Licenciamiento · lectura de las alertas (opcional)</span>
                <textarea class="inf-input" rows="3" data-campo="lic_alertas" ${dis}>${esc(parrafos(t.licenciamiento?.alertas))}</textarea></label>` : ""}
            ${st.puedeGenerar ? `<button class="btn-primary inf-btn" data-accion="guardar-textos" data-requiere-libre><i data-lucide="save"></i> Guardar textos y regenerar PDF</button>` : ""}
        </div>`;
    }

    function leerParrafos(selector) {
        const n = $("inf-detalle").querySelector(selector);
        return n ? n.value.split(/\n\s*\n/).map((p) => p.replace(/\s+/g, " ").trim()).filter(Boolean) : [];
    }

    async function guardarTextos(teamId) {
        const panel = $("inf-detalle");
        const textos = {
            soporte: {
                destacados: leerParrafos("[data-campo='destacados']"),
                tickets: [...panel.querySelectorAll("[data-ticket]")].map((n) => ({ id: Number(n.dataset.ticket), resumen: n.value.trim() })),
            },
            licenciamiento: { resumen: leerParrafos("[data-campo='lic_resumen']"), alertas: leerParrafos("[data-campo='lic_alertas']") },
        };
        try {
            const r = await api(`/api/informes/${mesSeleccionado()}/${teamId}/textos`, { method: "PUT", body: JSON.stringify({ textos }) });
            toast("Textos guardados; regenerando Word y PDF…");
            seguir(teamId, r.job_id);
        } catch (e) {
            toast(`❌ ${e.message}${e.detalle ? ": " + e.detalle.join("; ") : ""}`);
        }
    }

    async function redactar(teamId) {
        if (!confirm("¿Volver a redactar los textos con IA? Los textos actuales quedan en textos.anterior.json.")) return;
        try {
            const r = await api(`/api/informes/${mesSeleccionado()}/${teamId}/redactar`, { method: "POST", body: "{}" });
            seguir(teamId, r.job_id);
        } catch (e) {
            toast(`❌ ${e.message}`);
        }
    }

    // ------------------------------------------------------------------ API pública (app.js)
    window.InformesMensuales = {
        sesion(usuario) {
            st.usuario = usuario;
            st.puedeGenerar = !!(usuario && usuario.puede_informes);
            if (!usuario) {
                Object.values(st.progreso).forEach((p) => p.fuente && p.fuente.close());
                st.progreso = {};
                st.datos = null;
                st.cargado = false;
            }
        },
        mostrar() {
            if (!st.cargado) cargar();
        },
    };

    document.addEventListener("DOMContentLoaded", prepararFiltros);
})();
