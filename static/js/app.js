/**
 * Odoo Ticket Hub - Mobile First Application Logic
 * Supports Light/Dark Theme, Groq AI Analysis & Direct Odoo Links
 */

document.addEventListener("DOMContentLoaded", () => {
    // App State
    const state = {
        authenticated: false,
        user: null,
        tickets: [],
        filteredTickets: [],
        currentStageFilter: "all",
        searchQuery: "",
        limit: 10,
        selectedTicket: null,
        isRefreshing: false,
        groqConfigured: false,
        theme: localStorage.getItem("odoo_hub_theme") || "light"
    };

    // DOM Elements
    const elements = {
        html: document.documentElement,
        themeToggleBtns: document.querySelectorAll(".theme-toggle-btn"),
        loginSection: document.getElementById("login-section"),
        dashboardSection: document.getElementById("dashboard-section"),
        loginForm: document.getElementById("login-form"),
        usernameInput: document.getElementById("username"),
        passwordInput: document.getElementById("password"),
        togglePasswordBtn: document.getElementById("toggle-password"),
        eyeIcon: document.getElementById("eye-icon"),
        loginError: document.getElementById("login-error"),
        loginErrorMsg: document.getElementById("login-error-msg"),
        btnLogin: document.getElementById("btn-login"),
        loginSpinner: document.getElementById("login-spinner"),
        btnText: document.querySelector("#btn-login .btn-text"),
        btnArrow: document.querySelector("#btn-login .btn-arrow"),
        
        // Dashboard
        userDisplayName: document.getElementById("user-display-name"),
        userAvatar: document.getElementById("user-avatar"),
        userEmailLabel: document.getElementById("user-email-label"),
        dashServerBadge: document.getElementById("dash-server-badge"),
        totalCountPill: document.getElementById("total-count-pill"),
        btnLogout: document.getElementById("btn-logout"),
        btnRefresh: document.getElementById("btn-refresh"),
        limitSelect: document.getElementById("limit-select"),
        btnOpenSettings: document.getElementById("btn-open-settings"),
        
        // KPI Elements
        kpiTotal: document.getElementById("kpi-total"),
        kpiNew: document.getElementById("kpi-new"),
        kpiWip: document.getElementById("kpi-wip"),
        kpiWaiting: document.getElementById("kpi-waiting"),
        kpiResolved: document.getElementById("kpi-resolved"),
        kpiPriority: document.getElementById("kpi-priority"),
        
        // Search & Filters
        searchInput: document.getElementById("search-input"),
        clearSearchBtn: document.getElementById("clear-search"),
        filterChips: document.querySelectorAll(".filter-chip"),
        kpiCards: document.querySelectorAll(".kpi-card"),
        
        // Container & Empty State
        ticketsContainer: document.getElementById("tickets-container"),
        emptyState: document.getElementById("empty-state"),
        lastUpdatedText: document.getElementById("last-updated-text"),
        
        // Detail Modal Elements
        ticketModal: document.getElementById("ticket-modal"),
        modalCloseBtn: document.getElementById("modal-close-btn"),
        modalTicketId: document.getElementById("modal-ticket-id"),
        modalTicketName: document.getElementById("modal-ticket-name"),
        modalStageBadge: document.getElementById("modal-stage-badge"),
        modalPriorityBadge: document.getElementById("modal-priority-badge"),
        modalTypeBadge: document.getElementById("modal-type-badge"),
        modalClientName: document.getElementById("modal-client-name"),
        modalAgentName: document.getElementById("modal-agent-name"),
        modalCreatedDate: document.getElementById("modal-created-date"),
        modalDescriptionContent: document.getElementById("modal-description-content"),
        modalLinkOdoo: document.getElementById("modal-link-odoo"),
        modalBtnAi: document.getElementById("modal-btn-ai"),
        modalCopyWa: document.getElementById("modal-copy-wa"),

        // Settings Modal Elements
        settingsModal: document.getElementById("settings-modal"),
        settingsCloseBtn: document.getElementById("settings-close-btn"),
        settingsBtnDone: document.getElementById("settings-btn-done"),
        groqStatusBadge: document.getElementById("groq-status-badge"),
        groqApiKeyInput: document.getElementById("groq-api-key"),
        groqModelSelect: document.getElementById("groq-model-select"),
        groqPromptInput: document.getElementById("groq-prompt"),
        toggleGroqKeyBtn: document.getElementById("toggle-groq-key"),
        btnTestGroq: document.getElementById("btn-test-groq"),
        groqSettingsForm: document.getElementById("groq-settings-form"),
        btnSaveGroq: document.getElementById("btn-save-groq"),

        // AI Modal Elements
        aiModal: document.getElementById("ai-modal"),
        aiCloseBtn: document.getElementById("ai-close-btn"),
        aiTicketTitle: document.getElementById("ai-ticket-title"),
        aiLoading: document.getElementById("ai-loading"),
        aiContent: document.getElementById("ai-content"),
        aiTextBox: document.getElementById("ai-text-box"),
        aiBtnCopy: document.getElementById("ai-btn-copy"),
        
        // Toast
        toast: document.getElementById("toast-notification"),
        toastMsg: document.getElementById("toast-message")
    };

    // ==========================================
    // THEME MANAGEMENT (LIGHT BY DEFAULT)
    // ==========================================

    function applyTheme(theme) {
        state.theme = theme;
        elements.html.setAttribute("data-theme", theme);
        localStorage.setItem("odoo_hub_theme", theme);
        updateIcons();
    }

    elements.themeToggleBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            const newTheme = state.theme === "light" ? "dark" : "light";
            applyTheme(newTheme);
            showToast(`Tema ${newTheme === "light" ? "Claro" : "Oscuro"} activado`);
        });
    });

    applyTheme(state.theme);

    // Lucide Icon Helper
    function updateIcons() {
        if (window.lucide) {
            window.lucide.createIcons();
        }
    }

    updateIcons();

    // ==========================================
    // AUTHENTICATION LOGIC
    // ==========================================

    if (elements.togglePasswordBtn) {
        elements.togglePasswordBtn.addEventListener("click", () => {
            const isPassword = elements.passwordInput.type === "password";
            elements.passwordInput.type = isPassword ? "text" : "password";
            elements.eyeIcon.setAttribute("data-lucide", isPassword ? "eye-off" : "eye");
            updateIcons();
        });
    }

    async function checkAuthStatus() {
        try {
            const res = await fetch("/api/auth/status");
            const data = await res.json();
            if (data.authenticated) {
                setAuthenticated(data);
            } else {
                showLoginView();
            }
        } catch (e) {
            showLoginView();
        }
    }

    function showLoginView() {
        elements.dashboardSection.classList.add("hidden");
        elements.loginSection.classList.remove("hidden");
        updateIcons();
    }

    function showDashboardView() {
        elements.loginSection.classList.add("hidden");
        elements.dashboardSection.classList.remove("hidden");
        updateIcons();
    }

    function setAuthenticated(userData) {
        state.authenticated = true;
        state.user = userData;

        const displayName = userData.name || userData.user || "Usuario";
        elements.userDisplayName.textContent = displayName;
        elements.userEmailLabel.textContent = userData.user;

        const initials = displayName
            .split(" ")
            .map(n => n[0])
            .slice(0, 2)
            .join("")
            .toUpperCase() || "U";
        elements.userAvatar.textContent = initials;

        if (userData.db) {
            elements.dashServerBadge.textContent = userData.db;
        }

        showDashboardView();
        fetchTickets();
        loadSettings();
    }

    elements.loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const username = elements.usernameInput.value.trim();
        const password = elements.passwordInput.value.trim();

        if (!username || !password) return;

        elements.btnLogin.disabled = true;
        elements.btnText.textContent = "Conectando...";
        elements.btnArrow.classList.add("hidden");
        elements.loginSpinner.classList.remove("hidden");
        elements.loginError.classList.add("hidden");

        try {
            const res = await fetch("/api/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password })
            });

            const data = await res.json();

            if (res.ok && data.success) {
                setAuthenticated(data);
                showToast("¡Sesión iniciada con éxito en Odoo!");
            } else {
                elements.loginErrorMsg.textContent = data.error || "Credenciales incorrectas o servidor inalcanzable";
                elements.loginError.classList.remove("hidden");
            }
        } catch (err) {
            elements.loginErrorMsg.textContent = "Error de red al conectar con el servidor.";
            elements.loginError.classList.remove("hidden");
        } finally {
            elements.btnLogin.disabled = false;
            elements.btnText.textContent = "Iniciar Sesión";
            elements.btnArrow.classList.remove("hidden");
            elements.loginSpinner.classList.add("hidden");
            updateIcons();
        }
    });

    elements.btnLogout.addEventListener("click", async () => {
        try {
            await fetch("/api/logout", { method: "POST" });
        } catch (e) {
            console.error(e);
        }
        state.authenticated = false;
        state.tickets = [];
        showLoginView();
        showToast("Sesión cerrada");
    });

    // ==========================================
    // TICKETS FETCH & RENDER
    // ==========================================

    function renderSkeletons() {
        const count = parseInt(state.limit) || 10;
        let html = "";
        for (let i = 0; i < count; i++) {
            html += `<div class="skeleton-card glass-panel"></div>`;
        }
        elements.ticketsContainer.innerHTML = html;
    }

    async function fetchTickets() {
        if (state.isRefreshing) return;
        state.isRefreshing = true;
        elements.btnRefresh.classList.add("refreshing");

        if (state.tickets.length === 0) {
            renderSkeletons();
        }

        try {
            const limit = elements.limitSelect.value || 10;
            state.limit = limit;
            const res = await fetch(`/api/tickets?limit=${limit}`);
            if (res.status === 401) {
                showLoginView();
                return;
            }
            const data = await res.json();

            if (data.success) {
                state.tickets = data.tickets;
                updateKPIs(data.stats, data.tickets.length);
                applyFilters();
                
                const now = new Date();
                elements.lastUpdatedText.textContent = `Actualizado ${now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
            } else {
                console.error("Error fetching tickets:", data.error);
            }
        } catch (err) {
            console.error("Network error:", err);
        } finally {
            state.isRefreshing = false;
            elements.btnRefresh.classList.remove("refreshing");
        }
    }

    function updateKPIs(stats, total) {
        if (!stats) return;
        elements.kpiTotal.textContent = total;
        elements.kpiNew.textContent = stats.new || 0;
        elements.kpiWip.textContent = stats.in_progress || 0;
        elements.kpiWaiting.textContent = stats.waiting || 0;
        elements.kpiResolved.textContent = (stats.solved || 0) + (stats.closed || 0);
        elements.kpiPriority.textContent = stats.high_priority || 0;
        elements.totalCountPill.textContent = `${total} tickets`;
    }

    function getPriorityHtml(priority) {
        const p = parseInt(priority) || 0;
        if (p === 3) return `<span class="priority-stars" style="color: var(--accent-rose);" title="Alta Prioridad">⭐⭐⭐ Urgente</span>`;
        if (p === 2) return `<span class="priority-stars" style="color: var(--accent-amber);" title="Prioridad Media">⭐⭐ Media</span>`;
        if (p === 1) return `<span class="priority-stars" style="color: var(--accent-blue);" title="Prioridad Baja">⭐ Baja</span>`;
        return `<span class="priority-stars" style="color: var(--text-muted);" title="Prioridad Normal">🤍 Normal</span>`;
    }

    function getStageBadgeHtml(stage) {
        const cat = stage.category || "other";
        return `<span class="stage-badge stage-${cat}">${stage.name}</span>`;
    }

    function renderTicketCards(tickets) {
        if (!tickets || tickets.length === 0) {
            elements.ticketsContainer.innerHTML = "";
            elements.emptyState.classList.remove("hidden");
            return;
        }

        elements.emptyState.classList.add("hidden");

        const cardsHtml = tickets.map((t) => {
            const dateStr = t.create_date ? t.create_date.replace("T", " ") : "Reciente";
            return `
            <div class="ticket-card glass-panel" data-id="${t.id}">
                <div class="ticket-top">
                    <span class="ticket-id">#${t.id}</span>
                    <div class="ticket-top-badges">
                        ${getStageBadgeHtml(t.stage)}
                    </div>
                </div>

                <h3 class="ticket-title" title="${escapeHtml(t.name)}">${escapeHtml(t.name)}</h3>

                <div class="ticket-meta-box">
                    <div class="meta-row">
                        <i data-lucide="building"></i>
                        <span class="meta-lbl">Cliente:</span>
                        <strong class="meta-val" title="${escapeHtml(t.client.name)}">${escapeHtml(t.client.name)}</strong>
                    </div>
                    <div class="meta-row">
                        <i data-lucide="user"></i>
                        <span class="meta-lbl">Asesor:</span>
                        <span class="meta-val" title="${escapeHtml(t.assigned.name)}">${escapeHtml(t.assigned.name)}</span>
                    </div>
                    <div class="meta-row">
                        <i data-lucide="tag"></i>
                        <span class="meta-lbl">Prioridad:</span>
                        <span class="meta-val">${getPriorityHtml(t.priority)}</span>
                    </div>
                    <div class="meta-row">
                        <i data-lucide="calendar"></i>
                        <span class="meta-lbl">Fecha:</span>
                        <span class="meta-val">${dateStr}</span>
                    </div>
                </div>

                <!-- Action Buttons: Ver en Odoo, IA, Detalle, WhatsApp -->
                <div class="ticket-actions-grid">
                    <a href="${t.odoo_url}" target="_blank" rel="noopener" class="btn-odoo-link" title="Abrir directamente en Odoo">
                        <i data-lucide="external-link"></i>
                        <span>Ver Ticket</span>
                    </a>

                    <button class="btn-ai-action btn-card-ai" data-id="${t.id}" title="Analizar con IA (Groq)">
                        <i data-lucide="sparkles"></i>
                        <span>Groq IA</span>
                    </button>

                    <button class="btn-secondary btn-card-detail" data-id="${t.id}" title="Ver descripción completa">
                        <i data-lucide="eye"></i>
                        <span>Detalles</span>
                    </button>

                    <button class="btn-secondary btn-copy-wa" data-id="${t.id}" title="Copiar Formato WhatsApp">
                        <i data-lucide="share-2"></i>
                        <span>WhatsApp</span>
                    </button>
                </div>
            </div>
            `;
        }).join("");

        elements.ticketsContainer.innerHTML = cardsHtml;
        updateIcons();
        attachCardListeners();
    }

    function attachCardListeners() {
        // Detail View Buttons
        document.querySelectorAll(".btn-card-detail").forEach((btn) => {
            btn.addEventListener("click", () => {
                const id = parseInt(btn.getAttribute("data-id"));
                const ticket = state.tickets.find((t) => t.id === id);
                if (ticket) openDetailModal(ticket);
            });
        });

        // AI Analyze Buttons on Cards
        document.querySelectorAll(".btn-card-ai").forEach((btn) => {
            btn.addEventListener("click", () => {
                const id = parseInt(btn.getAttribute("data-id"));
                const ticket = state.tickets.find((t) => t.id === id);
                if (ticket) runAiAnalysis(ticket);
            });
        });

        // WhatsApp Copy Buttons
        document.querySelectorAll(".btn-copy-wa").forEach((btn) => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                const id = parseInt(btn.getAttribute("data-id"));
                const ticket = state.tickets.find((t) => t.id === id);
                if (ticket) copyWhatsAppFormat(ticket);
            });
        });
    }

    // ==========================================
    // FILTERING & SEARCH
    // ==========================================

    function applyFilters() {
        let list = [...state.tickets];

        // Filter by Stage (Includes 'new')
        if (state.currentStageFilter !== "all") {
            list = list.filter((t) => {
                if (state.currentStageFilter === "new") {
                    return t.stage.category === "new";
                }
                if (state.currentStageFilter === "in_progress") {
                    return t.stage.category === "in_progress";
                }
                if (state.currentStageFilter === "waiting") {
                    return t.stage.category === "waiting";
                }
                if (state.currentStageFilter === "solved") {
                    return t.stage.category === "solved";
                }
                if (state.currentStageFilter === "closed") {
                    return t.stage.category === "closed";
                }
                if (state.currentStageFilter === "high_priority") {
                    return t.priority >= 3;
                }
                return true;
            });
        }

        // Filter by Search Query
        if (state.searchQuery) {
            const q = state.searchQuery.toLowerCase();
            list = list.filter((t) => {
                const idMatch = t.id.toString().includes(q);
                const nameMatch = (t.name || "").toLowerCase().includes(q);
                const clientMatch = (t.client.name || "").toLowerCase().includes(q);
                const agentMatch = (t.assigned.name || "").toLowerCase().includes(q);
                const stageMatch = (t.stage.name || "").toLowerCase().includes(q);
                return idMatch || nameMatch || clientMatch || agentMatch || stageMatch;
            });
        }

        state.filteredTickets = list;
        renderTicketCards(list);
    }

    elements.searchInput.addEventListener("input", (e) => {
        state.searchQuery = e.target.value.trim();
        if (state.searchQuery) {
            elements.clearSearchBtn.classList.remove("hidden");
        } else {
            elements.clearSearchBtn.classList.add("hidden");
        }
        applyFilters();
    });

    elements.clearSearchBtn.addEventListener("click", () => {
        elements.searchInput.value = "";
        state.searchQuery = "";
        elements.clearSearchBtn.classList.add("hidden");
        applyFilters();
    });

    // Stage Filter Chips
    elements.filterChips.forEach((chip) => {
        chip.addEventListener("click", () => {
            elements.filterChips.forEach((c) => c.classList.remove("active"));
            chip.classList.add("active");
            state.currentStageFilter = chip.getAttribute("data-stage");
            applyFilters();
        });
    });

    // KPI Cards Click Filter
    elements.kpiCards.forEach((kpi) => {
        kpi.addEventListener("click", () => {
            const filter = kpi.getAttribute("data-filter");
            state.currentStageFilter = filter;
            elements.filterChips.forEach((chip) => {
                if (chip.getAttribute("data-stage") === filter) {
                    chip.classList.add("active");
                } else if (filter === "high_priority" && chip.getAttribute("data-stage") === "all") {
                    chip.classList.add("active");
                } else {
                    chip.classList.remove("active");
                }
            });
            applyFilters();
        });
    });

    elements.limitSelect.addEventListener("change", () => {
        fetchTickets();
    });

    elements.btnRefresh.addEventListener("click", () => {
        fetchTickets();
    });

    // ==========================================
    // DETAIL MODAL
    // ==========================================

    function openDetailModal(ticket) {
        state.selectedTicket = ticket;

        elements.modalTicketId.textContent = `#${ticket.id}`;
        elements.modalTicketName.textContent = ticket.name || "(Sin Asunto)";

        elements.modalStageBadge.className = `stage-badge stage-${ticket.stage.category}`;
        elements.modalStageBadge.textContent = ticket.stage.name;

        elements.modalPriorityBadge.innerHTML = getPriorityHtml(ticket.priority);
        elements.modalTypeBadge.textContent = ticket.type || "Soporte";

        elements.modalClientName.textContent = ticket.client.name || "Sin cliente";
        elements.modalAgentName.textContent = ticket.assigned.name || "Sin asignar";

        elements.modalCreatedDate.textContent = ticket.create_date ? ticket.create_date.replace("T", " ") : "N/A";

        if (ticket.description && ticket.description.trim()) {
            elements.modalDescriptionContent.innerHTML = sanitizeDescription(ticket.description);
        } else {
            elements.modalDescriptionContent.textContent = "Sin descripción provista en Odoo.";
        }

        // Direct Odoo link
        elements.modalLinkOdoo.href = ticket.odoo_url;

        elements.ticketModal.classList.remove("hidden");
        updateIcons();
    }

    function closeDetailModal() {
        elements.ticketModal.classList.add("hidden");
        state.selectedTicket = null;
    }

    elements.modalCloseBtn.addEventListener("click", closeDetailModal);
    elements.ticketModal.addEventListener("click", (e) => {
        if (e.target === elements.ticketModal) closeDetailModal();
    });

    elements.modalBtnAi.addEventListener("click", () => {
        if (state.selectedTicket) {
            closeDetailModal();
            runAiAnalysis(state.selectedTicket);
        }
    });

    elements.modalCopyWa.addEventListener("click", () => {
        if (state.selectedTicket) {
            copyWhatsAppFormat(state.selectedTicket);
        }
    });

    // ==========================================
    // SETTINGS & GROQ INTEGRATION
    // ==========================================

    async function loadSettings() {
        try {
            const res = await fetch("/api/settings");
            const data = await res.json();
            if (data.success) {
                state.groqConfigured = data.groq_configured;
                if (data.groq_configured) {
                    elements.groqStatusBadge.textContent = "Configurado";
                    elements.groqStatusBadge.className = "badge-status-active";
                    elements.groqApiKeyInput.placeholder = data.groq_masked_key || "gsk_••••••••••••";
                } else {
                    elements.groqStatusBadge.textContent = "No configurado";
                    elements.groqStatusBadge.className = "badge-status-inactive";
                }

                if (data.groq_model) {
                    elements.groqModelSelect.value = data.groq_model;
                }
                if (data.groq_system_prompt) {
                    elements.groqPromptInput.value = data.groq_system_prompt;
                }
            }
        } catch (e) {
            console.error("Error loading settings:", e);
        }
    }

    elements.btnOpenSettings.addEventListener("click", () => {
        loadSettings();
        elements.settingsModal.classList.remove("hidden");
        updateIcons();
    });

    function closeSettingsModal() {
        elements.settingsModal.classList.add("hidden");
    }

    elements.settingsCloseBtn.addEventListener("click", closeSettingsModal);
    elements.settingsBtnDone.addEventListener("click", closeSettingsModal);
    elements.settingsModal.addEventListener("click", (e) => {
        if (e.target === elements.settingsModal) closeSettingsModal();
    });

    if (elements.toggleGroqKeyBtn) {
        elements.toggleGroqKeyBtn.addEventListener("click", () => {
            const isPwd = elements.groqApiKeyInput.type === "password";
            elements.groqApiKeyInput.type = isPwd ? "text" : "password";
        });
    }

    // Test Groq Connection
    elements.btnTestGroq.addEventListener("click", async () => {
        const apiKey = elements.groqApiKeyInput.value.trim();
        const model = elements.groqModelSelect.value;

        elements.btnTestGroq.disabled = true;
        elements.btnTestGroq.innerHTML = `<span>Probando...</span>`;

        try {
            const res = await fetch("/api/settings/groq/test", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ api_key: apiKey, model: model })
            });
            const data = await res.json();

            if (data.success) {
                showToast(`✅ ${data.message || "Conexión a Groq exitosa"}`);
            } else {
                showToast(`❌ ${data.error || "Error al conectar con Groq"}`);
            }
        } catch (e) {
            showToast("❌ Error de red al probar Groq");
        } finally {
            elements.btnTestGroq.disabled = false;
            elements.btnTestGroq.innerHTML = `<i data-lucide="play-circle"></i><span>Probar Conexión</span>`;
            updateIcons();
        }
    });

    // Save Groq Settings
    elements.groqSettingsForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const apiKey = elements.groqApiKeyInput.value.trim();
        const model = elements.groqModelSelect.value;
        const prompt = elements.groqPromptInput.value.trim();

        elements.btnSaveGroq.disabled = true;

        try {
            const res = await fetch("/api/settings/groq", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ api_key: apiKey, model: model, system_prompt: prompt })
            });
            const data = await res.json();

            if (data.success) {
                showToast("✅ Configuración de Groq guardada con éxito");
                loadSettings();
            } else {
                showToast(`❌ ${data.error || "Error al guardar"}`);
            }
        } catch (e) {
            showToast("❌ Error de red al guardar");
        } finally {
            elements.btnSaveGroq.disabled = false;
        }
    });

    // ==========================================
    // GROQ AI TICKET ANALYSIS
    // ==========================================

    let lastAiResponseText = "";

    async function runAiAnalysis(ticket) {
        state.selectedTicket = ticket;
        elements.aiTicketTitle.textContent = `#${ticket.id} - ${ticket.name}`;
        
        elements.aiModal.classList.remove("hidden");
        elements.aiLoading.classList.remove("hidden");
        elements.aiContent.classList.add("hidden");
        updateIcons();

        try {
            const res = await fetch("/api/ai/analyze-ticket", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ ticket: ticket })
            });
            const data = await res.json();

            if (data.success) {
                lastAiResponseText = data.analysis;
                elements.aiTextBox.innerHTML = formatAiResponse(data.analysis);
                elements.aiLoading.classList.add("hidden");
                elements.aiContent.classList.remove("hidden");
            } else {
                elements.aiLoading.classList.add("hidden");
                elements.aiContent.classList.remove("hidden");
                elements.aiTextBox.innerHTML = `<span style="color: var(--accent-rose);">⚠️ ${data.error || "No se pudo generar el análisis."}</span><br><br>Por favor verifica tu API Key en Ajustes > Integraciones.`;
                lastAiResponseText = data.error || "";
            }
        } catch (e) {
            elements.aiLoading.classList.add("hidden");
            elements.aiContent.classList.remove("hidden");
            elements.aiTextBox.innerHTML = "<span style='color: var(--accent-rose);'>Error de red al comunicarse con Groq IA.</span>";
        }
        updateIcons();
    }

    function closeAiModal() {
        elements.aiModal.classList.add("hidden");
    }

    elements.aiCloseBtn.addEventListener("click", closeAiModal);
    elements.aiModal.addEventListener("click", (e) => {
        if (e.target === elements.aiModal) closeAiModal();
    });

    elements.aiBtnCopy.addEventListener("click", () => {
        if (lastAiResponseText) {
            const cleanText = cleanTextForClipboard(lastAiResponseText);
            navigator.clipboard.writeText(cleanText).then(() => {
                showToast("📋 Análisis copiado al portapapeles");
            });
        }
    });

    function formatAiResponse(raw) {
        if (!raw) return "";

        // Strip reasoning tags if present
        let text = raw.replace(/<think>[\s\S]*?<\/think>/gi, "").trim();

        // Convert headers (###, ##, #) to clean section titles
        text = text.replace(/^(?:###|##|#)\s*(?:[0-9️⃣]*\s*)?(.*?)$/gm, '<div class="ai-section-title">$1</div>');

        // Convert blockquotes (> ...) to response quote boxes
        text = text.replace(/(?:^>[ \t]*(.*?)(?:\n|$))+/gm, (match) => {
            const inner = match.replace(/^>[ \t]*/gm, "").trim().replace(/\n/g, "<br>");
            return `<div class="ai-quote-box">${inner}</div>`;
        });

        // Convert bullet points (- or *) to clean list items
        text = text.replace(/^[ \t]*[-*•]\s+(.*?)$/gm, '<div class="ai-list-item"><span class="ai-bullet">▪</span><span>$1</span></div>');

        // Convert numbered list items (1., 2., etc)
        text = text.replace(/^[ \t]*(\d+)\.\s+(.*?)$/gm, '<div class="ai-list-item"><span class="ai-num">$1.</span><span>$2</span></div>');

        // Bold **text** -> <strong>text</strong> (removes double asterisks)
        text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

        // Italic *text* -> <em>text</em>
        text = text.replace(/(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');

        // Clean up markdown divider lines ---
        text = text.replace(/^---+$/gm, '<hr class="ai-divider">');

        // Wrap loose paragraphs cleanly
        const blocks = text.split(/\n{2,}/).map(block => {
            block = block.trim();
            if (!block) return "";
            if (block.startsWith("<div") || block.startsWith("<hr") || block.startsWith("<strong")) {
                return block;
            }
            return `<p class="ai-paragraph">${block.replace(/\n/g, "<br>")}</p>`;
        }).filter(Boolean);

        return blocks.join("\n");
    }

    function cleanTextForClipboard(raw) {
        if (!raw) return "";
        return raw
            .replace(/<think>[\s\S]*?<\/think>/gi, "")
            .replace(/^(?:###|##|#)\s*/gm, "")
            .replace(/\*\*(.*?)\*\*/g, "$1")
            .replace(/(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)/g, "$1")
            .replace(/^---+$/gm, "----------------------------------------")
            .replace(/^>[ \t]*/gm, "")
            .trim();
    }

    // WhatsApp Format Copy
    function copyWhatsAppFormat(ticket) {
        let stars = "🤍 Normal";
        if (ticket.priority === 3) stars = "⭐⭐⭐ Urgente";
        else if (ticket.priority === 2) stars = "⭐⭐ Media";
        else if (ticket.priority === 1) stars = "⭐ Baja";

        const msg = `🆕 Ticket: *${ticket.id}* - ${stars}\n${ticket.name} - ${ticket.client.name || "Sin cliente"}\n🙋‍♂️ asignado a *${ticket.assigned.name || "Sin asignar"}\n🔗 ${ticket.odoo_url}*`;

        navigator.clipboard.writeText(msg).then(() => {
            showToast(`📋 WhatsApp copiado (#${ticket.id})`);
        }).catch(() => {
            showToast("No se pudo copiar");
        });
    }

    // ==========================================
    // UTILITIES
    // ==========================================

    function showToast(message) {
        elements.toastMsg.textContent = message;
        elements.toast.classList.remove("hidden");
        updateIcons();
        setTimeout(() => {
            elements.toast.classList.add("hidden");
        }, 2800);
    }

    function escapeHtml(str) {
        if (!str) return "";
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function sanitizeDescription(raw) {
        if (!raw) return "";
        if (raw.includes("<") && raw.includes(">")) {
            return raw;
        }
        return `<p>${escapeHtml(raw).replace(/\n/g, "<br>")}</p>`;
    }

    // Start App
    checkAuthStatus();
});
