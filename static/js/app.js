/**
 * Odoo Ticket Hub - Mobile First & Client Monthly Reports
 * Supports Light/Dark Theme, Groq AI Analysis, Monthly Reports & Odoo Integration
 */

document.addEventListener("DOMContentLoaded", () => {
    // App State
    const state = {
        authenticated: false,
        user: null,
        currentView: "monitor", // "monitor" or "reports"
        
        // Monitor State
        tickets: [],
        filteredTickets: [],
        currentStageFilter: "all",
        searchQuery: "",
        limit: 10,
        selectedTicket: null,
        isRefreshing: false,
        
        // Reports State
        reportClients: [],
        selectedClientId: null,
        selectedMonth: 7,
        selectedYear: 2026,
        reportTickets: [],
        aiReport: null,
        isGeneratingReport: false,
        
        // Settings & Theme
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
        
        // Navigation Switcher
        tabNavMonitor: document.getElementById("tab-nav-monitor"),
        tabNavReports: document.getElementById("tab-nav-reports"),
        tabNavExecutive: document.getElementById("tab-nav-executive"),
        viewMonitor: document.getElementById("view-monitor"),
        viewReports: document.getElementById("view-reports"),
        viewExecutive: document.getElementById("view-executive"),

        // Dashboard Header
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
        groqBaseUrlInput: document.getElementById("groq-base-url"),
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
        
        // Report Elements
        reportClientSelect: document.getElementById("report-client-select"),
        reportMonthSelect: document.getElementById("report-month-select"),
        reportYearSelect: document.getElementById("report-year-select"),
        btnGenerateAiReport: document.getElementById("btn-generate-ai-report"),
        btnLoadReportTickets: document.getElementById("btn-load-report-tickets"),
        reportStatsRibbon: document.getElementById("report-stats-ribbon"),
        statClientName: document.getElementById("stat-client-name"),
        statPeriodName: document.getElementById("stat-period-name"),
        statTicketsCount: document.getElementById("stat-tickets-count"),
        statTotalHours: document.getElementById("stat-total-hours"),
        reportAiLoading: document.getElementById("report-ai-loading"),
        reportLoadingTitle: document.getElementById("report-loading-title"),
        reportLoadingSubtitle: document.getElementById("report-loading-subtitle"),
        reportProgressFill: document.getElementById("report-progress-fill"),
        reportProgressStatusText: document.getElementById("report-progress-status-text"),
        reportProgressCounter: document.getElementById("report-progress-counter"),
        executiveReportCard: document.getElementById("executive-report-card"),
        docSectionHeader: document.getElementById("doc-section-header"),
        docIntroText: document.getElementById("doc-intro-text"),
        docItemsContainer: document.getElementById("doc-items-container"),
        btnCopyReportText: document.getElementById("btn-copy-report-text"),
        btnPrintReport: document.getElementById("btn-print-report"),
        reportTableCard: document.getElementById("report-table-card"),
        tableCountBadge: document.getElementById("table-count-badge"),
        reportTableTbody: document.getElementById("report-table-tbody"),
        reportsEmptyState: document.getElementById("reports-empty-state"),

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
    // NAVIGATION SWITCHER (MONITOR VS INFORMES)
    // ==========================================

    function switchView(viewName) {
        state.currentView = viewName;
        if (viewName === "monitor") {
            elements.tabNavMonitor.classList.add("active");
            elements.tabNavReports.classList.remove("active");
            if (elements.tabNavExecutive) elements.tabNavExecutive.classList.remove("active");
            elements.viewMonitor.classList.remove("hidden");
            elements.viewReports.classList.add("hidden");
            if (elements.viewExecutive) elements.viewExecutive.classList.add("hidden");
        } else if (viewName === "reports") {
            elements.tabNavReports.classList.add("active");
            elements.tabNavMonitor.classList.remove("active");
            if (elements.tabNavExecutive) elements.tabNavExecutive.classList.remove("active");
            elements.viewReports.classList.remove("hidden");
            elements.viewMonitor.classList.add("hidden");
            if (elements.viewExecutive) elements.viewExecutive.classList.add("hidden");
            
            if (state.reportClients.length === 0) {
                fetchReportClients();
            }
        } else if (viewName === "executive") {
            if (elements.tabNavExecutive) elements.tabNavExecutive.classList.add("active");
            elements.tabNavMonitor.classList.remove("active");
            elements.tabNavReports.classList.remove("active");
            if (elements.viewExecutive) elements.viewExecutive.classList.remove("hidden");
            elements.viewMonitor.classList.add("hidden");
            elements.viewReports.classList.add("hidden");

            initExecutiveReport();
        }
        updateIcons();
    }

    if (elements.tabNavMonitor && elements.tabNavReports) {
        elements.tabNavMonitor.addEventListener("click", () => switchView("monitor"));
        elements.tabNavReports.addEventListener("click", () => switchView("reports"));
    }
    if (elements.tabNavExecutive) {
        elements.tabNavExecutive.addEventListener("click", () => switchView("executive"));
    }

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
    // TICKETS FETCH & RENDER (MONITOR)
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
        const cat = typeof stage === "object" ? (stage.category || "other") : "other";
        const name = typeof stage === "object" ? stage.name : stage;
        return `<span class="stage-badge stage-${cat}">${name}</span>`;
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
        document.querySelectorAll(".btn-card-detail").forEach((btn) => {
            btn.addEventListener("click", () => {
                const id = parseInt(btn.getAttribute("data-id"));
                const ticket = state.tickets.find((t) => t.id === id);
                if (ticket) openDetailModal(ticket);
            });
        });

        document.querySelectorAll(".btn-card-ai").forEach((btn) => {
            btn.addEventListener("click", () => {
                const id = parseInt(btn.getAttribute("data-id"));
                const ticket = state.tickets.find((t) => t.id === id);
                if (ticket) runAiAnalysis(ticket);
            });
        });

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
    // FILTERING & SEARCH (MONITOR)
    // ==========================================

    function applyFilters() {
        let list = [...state.tickets];

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

    elements.filterChips.forEach((chip) => {
        chip.addEventListener("click", () => {
            elements.filterChips.forEach((c) => c.classList.remove("active"));
            chip.classList.add("active");
            state.currentStageFilter = chip.getAttribute("data-stage");
            applyFilters();
        });
    });

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
    // MONTHLY REPORTS LOGIC
    // ==========================================

    async function fetchReportClients() {
        try {
            const res = await fetch("/api/reports/clients");
            const data = await res.json();
            if (data.success && data.clients) {
                state.reportClients = data.clients;
                let optionsHtml = "";
                data.clients.forEach(c => {
                    optionsHtml += `<option value="${c.id}">${escapeHtml(c.name)}</option>`;
                });
                elements.reportClientSelect.innerHTML = optionsHtml;

                // Pre-select Ajover or first client
                const ajover = data.clients.find(c => c.name.toLowerCase().includes("ajover"));
                if (ajover) {
                    elements.reportClientSelect.value = ajover.id;
                }
            }
        } catch (e) {
            console.error("Error loading report clients:", e);
        }
    }

    async function loadMonthlyReport(withAi = false) {
        const clientId = elements.reportClientSelect.value;
        const clientName = elements.reportClientSelect.options[elements.reportClientSelect.selectedIndex]?.text || "Cliente";
        const month = parseInt(elements.reportMonthSelect.value);
        const year = parseInt(elements.reportYearSelect.value);

        if (!clientId) {
            showToast("Por favor selecciona un cliente de Odoo");
            return;
        }

        elements.reportsEmptyState.classList.add("hidden");
        elements.executiveReportCard.classList.add("hidden");
        elements.reportTableCard.classList.add("hidden");
        elements.reportStatsRibbon.classList.remove("hidden");

        if (withAi) {
            elements.reportAiLoading.classList.remove("hidden");
            elements.btnGenerateAiReport.disabled = true;
        } else {
            elements.btnLoadReportTickets.disabled = true;
        }

        try {
            // 1. Fetch tickets for that client & month
            const res = await fetch(`/api/reports/tickets?client_id=${clientId}&year=${year}&month=${month}`);
            const data = await res.json();

            if (!data.success) {
                showToast(`❌ ${data.error || "Error al cargar tickets"}`);
                return;
            }

            state.reportTickets = data.tickets;
            elements.statClientName.textContent = clientName;
            elements.statPeriodName.textContent = data.period;
            elements.statTicketsCount.textContent = `${data.total_tickets} casos`;
            elements.statTotalHours.textContent = `${data.total_hours}h`;

            if (data.total_tickets === 0) {
                elements.reportTableCard.classList.remove("hidden");
                elements.reportTableTbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 24px;">No se encontraron tickets registrados para ${clientName} en ${data.period}.</td></tr>`;
                elements.tableCountBadge.textContent = "0 tickets";
                elements.reportAiLoading.classList.add("hidden");
                return;
            }

            // Render Table (Image 1 replica)
            renderReportTable(data.tickets);
            elements.reportTableCard.classList.remove("hidden");

            // Render Section 1 (Volumen de Casos Table & Chart)
            renderVolumeSection(data.type_counts || {}, data.total_tickets, data.month_name, data.year);

            // 2. Generate AI Report with real-time progress and live batch appending
            if (withAi) {
                // Initialize loading UI
                if (elements.reportProgressFill) elements.reportProgressFill.style.width = "0%";
                if (elements.reportProgressCounter) elements.reportProgressCounter.textContent = "0%";
                if (elements.reportLoadingTitle) elements.reportLoadingTitle.textContent = "Iniciando generación con IA...";
                if (elements.reportProgressStatusText) elements.reportProgressStatusText.textContent = "Preparando casos...";

                // Show report container and render stats immediately so user sees sections
                elements.docSectionHeader.innerHTML = "1. &nbsp; RESUMEN DE SOPORTE";
                elements.docIntroText.textContent = "Generando síntesis con IA...";
                elements.docItemsContainer.innerHTML = "";
                renderVolumeSection(data.type_counts || {}, data.total_tickets, data.month_name, data.year);
                renderAvgDaysSection(data.tickets, data.avg_days, data.month_name);
                renderHoursSection(data.tickets, data.total_hours, data.month_name, data.year);
                renderStagesSection(data.stage_counts, data.total_tickets, data.month_name, data.year);
                elements.executiveReportCard.classList.remove("hidden");

                const accumulatedTickets = [];

                // Fetch with SSE stream
                const response = await fetch("/api/reports/generate-ai-report?stream=true", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        client_name: clientName,
                        period_label: data.period,
                        tickets: data.tickets
                    })
                });

                if (!response.ok) {
                    const errJson = await response.json().catch(() => ({}));
                    throw new Error(errJson.error || `HTTP ${response.status}`);
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder("utf-8");
                let buffer = "";

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split("\n\n");
                    buffer = lines.pop(); // Keep unfinished line in buffer

                    for (const block of lines) {
                        const line = block.trim();
                        if (!line.startsWith("data:")) continue;
                        try {
                            const event = JSON.parse(line.substring(5).trim());

                            if (event.type === "step") {
                                if (elements.reportLoadingTitle) elements.reportLoadingTitle.textContent = event.message;
                                if (elements.reportProgressStatusText) elements.reportProgressStatusText.textContent = event.message;
                                if (elements.reportProgressFill) elements.reportProgressFill.style.width = `${event.progress}%`;
                                if (elements.reportProgressCounter) elements.reportProgressCounter.textContent = `${event.progress}%`;
                            } else if (event.type === "intro") {
                                elements.docIntroText.textContent = event.intro || "";
                                if (elements.reportProgressFill) elements.reportProgressFill.style.width = `${event.progress}%`;
                                if (elements.reportProgressCounter) elements.reportProgressCounter.textContent = `${event.progress}%`;
                            } else if (event.type === "batch_tickets") {
                                const newItems = event.items || [];
                                (newItems).forEach(t => {
                                    accumulatedTickets.push(t);
                                    const matchedRaw = data.tickets.find(r => r.id === t.id);
                                    const odooUrl = matchedRaw ? matchedRaw.odoo_url : "#";

                                    const div = document.createElement("div");
                                    div.className = "report-doc-item animate-fade-in";
                                    div.dataset.ticketId = t.id;
                                    div.innerHTML = `
                                        <a href="${odooUrl}" target="_blank" rel="noopener" class="report-item-title-link" title="Abrir #${t.id} en Odoo">
                                            <span>${escapeHtml(t.title || `Caso #${t.id}`)} (#${t.id})</span>
                                            <i data-lucide="external-link" style="width: 13px; height: 13px;"></i>
                                        </a>
                                        <p class="report-item-desc" contenteditable="true" title="Clic para editar">${escapeHtml(t.summary || "")}</p>
                                    `;
                                    elements.docItemsContainer.appendChild(div);
                                });
                                updateIcons();

                                const msg = `Completados ${event.processed} de ${event.total} tickets...`;
                                if (elements.reportLoadingSubtitle) elements.reportLoadingSubtitle.textContent = msg;
                                if (elements.reportProgressStatusText) elements.reportProgressStatusText.textContent = msg;
                                if (elements.reportProgressFill) elements.reportProgressFill.style.width = `${event.progress}%`;
                                if (elements.reportProgressCounter) elements.reportProgressCounter.textContent = `${event.progress}%`;
                            } else if (event.type === "done") {
                                if (elements.reportProgressFill) elements.reportProgressFill.style.width = "100%";
                                if (elements.reportProgressCounter) elements.reportProgressCounter.textContent = "100%";
                                showToast("✨ ¡Informe mensual generado con éxito!");
                            } else if (event.type === "error") {
                                throw new Error(event.error);
                            }
                        } catch (e) {
                            console.error("Error parsing SSE event:", e);
                        }
                    }
                }

                state.aiReport = {
                    section_header: "1. RESUMEN DE SOPORTE",
                    intro: elements.docIntroText.textContent,
                    tickets: accumulatedTickets
                };

            } else {
                // When only listing tickets without AI
                renderVolumeSection(data.type_counts || {}, data.total_tickets, data.month_name, data.year);
                renderAvgDaysSection(data.tickets, data.avg_days, data.month_name);
                renderHoursSection(data.tickets, data.total_hours, data.month_name, data.year);
                renderStagesSection(data.stage_counts, data.total_tickets, data.month_name, data.year);
                elements.executiveReportCard.classList.remove("hidden");
            }

        } catch (err) {
            console.error("Error generating report:", err);
            showToast("❌ Error de conexión al generar informe");
        } finally {
            elements.reportAiLoading.classList.add("hidden");
            elements.btnGenerateAiReport.disabled = false;
            elements.btnLoadReportTickets.disabled = false;
            updateIcons();
        }
    }

    function renderReportTable(tickets) {
        elements.tableCountBadge.textContent = `${tickets.length} tickets`;
        const rowsHtml = tickets.map(t => {
            const dateStr = t.create_date ? t.create_date.replace("T", " ") : "-";
            return `
            <tr>
                <td class="tbl-id">#${t.id}</td>
                <td class="tbl-name" title="${escapeHtml(t.name)}">${escapeHtml(t.name)}</td>
                <td><span class="badge-pill">${escapeHtml(t.type)}</span></td>
                <td><strong>${t.hours_spent ? t.hours_spent.toFixed(2) + "h" : "00:00"}</strong></td>
                <td>${dateStr}</td>
                <td>${getStageBadgeHtml(t.stage)}</td>
                <td>
                    <a href="${t.odoo_url}" target="_blank" rel="noopener" class="tbl-link" title="Abrir en Odoo">
                        <i data-lucide="external-link"></i>
                    </a>
                </td>
            </tr>
            `;
        }).join("");
        elements.reportTableTbody.innerHTML = rowsHtml;
        updateIcons();
    }

    let volumeChartInstance = null;
    let stagesChartInstance = null;

    function renderVolumeSection(typeCounts, totalTickets, monthName, year) {
        const monthLbl = document.getElementById("doc-volume-month-label");
        if (monthLbl) monthLbl.textContent = monthName;

        const tbody = document.getElementById("volume-table-tbody");
        const totalEl = document.getElementById("volume-total-val");
        
        let rowsHtml = "";
        const sortedKeys = Object.keys(typeCounts || {}).sort();
        sortedKeys.forEach(type => {
            rowsHtml += `
            <tr>
                <td>${escapeHtml(type)}</td>
                <td class="td-count">${typeCounts[type]}</td>
            </tr>
            `;
        });
        if (tbody) tbody.innerHTML = rowsHtml;
        if (totalEl) totalEl.textContent = totalTickets;

        const chartTitle = document.getElementById("volume-chart-title");
        if (chartTitle) chartTitle.textContent = `Tipo de caso - ${monthName} ${year}`;

        const canvas = document.getElementById("volume-chart-canvas");
        if (canvas && window.Chart) {
            if (volumeChartInstance) {
                volumeChartInstance.destroy();
            }

            const ctx = canvas.getContext("2d");
            const maxVal = Math.max(...Object.values(typeCounts || {}), 1);

            volumeChartInstance = new window.Chart(ctx, {
                type: "bar",
                data: {
                    labels: sortedKeys,
                    datasets: [{
                        label: "Tipo de caso",
                        data: sortedKeys.map(k => typeCounts[k]),
                        backgroundColor: "#3b82f6",
                        borderColor: "#2563eb",
                        borderWidth: 1,
                        borderRadius: 2,
                        barThickness: 38,
                        maxBarThickness: 45
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: 600 },
                    plugins: {
                        legend: {
                            display: true,
                            position: "bottom",
                            labels: {
                                font: { family: "Inter", size: 12 },
                                boxWidth: 12,
                                color: "#475569"
                            }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            suggestedMax: maxVal + 1,
                            ticks: { stepSize: 1, precision: 0, color: "#64748b" },
                            grid: { color: "#e2e8f0" }
                        },
                        x: {
                            ticks: { color: "#475569", font: { size: 12, weight: "500" } },
                            grid: { display: false }
                        }
                    }
                }
            });
        }
    }

    function renderAvgDaysSection(tickets, avgDays, monthName) {
        const monthLbl = document.getElementById("doc-avg-month-label");
        if (monthLbl) monthLbl.textContent = monthName;

        const daysNum = document.getElementById("doc-avg-days-num");
        if (daysNum) daysNum.textContent = avgDays;

        const daysFooter = document.getElementById("doc-avg-days-footer");
        if (daysFooter) daysFooter.textContent = avgDays;

        const tbody = document.getElementById("avg-days-table-tbody");
        if (tbody) {
            const rowsHtml = (tickets || []).map(t => {
                return `
                <tr>
                    <td><strong>${t.id}</strong></td>
                    <td title="${escapeHtml(t.name)}">${escapeHtml(t.name)}</td>
                    <td>${t.create_date ? t.create_date.replace("T", " ") : "-"}</td>
                    <td>${t.end_date ? t.end_date.replace("T", " ") : "-"}</td>
                    <td style="text-align: center;">${t.days_spent || 1}</td>
                </tr>
                `;
            }).join("");
            tbody.innerHTML = rowsHtml;
        }
    }

    function renderHoursSection(tickets, totalHours, monthName, year) {
        const monthLbl = document.getElementById("doc-hours-month-label");
        if (monthLbl) monthLbl.textContent = `${monthName} ${year}`;

        const totalVal = document.getElementById("doc-total-hours-val");
        if (totalVal) totalVal.textContent = totalHours.toFixed(2);

        const tbody = document.getElementById("hours-table-tbody");
        if (tbody) {
            const rowsHtml = (tickets || []).map(t => {
                return `
                <tr>
                    <td><strong>${t.id}</strong></td>
                    <td title="${escapeHtml(t.name)}">${escapeHtml(t.name)}</td>
                    <td>${escapeHtml(t.stage || "Closed")}</td>
                    <td style="text-align: center;">${(t.hours_spent || 0).toFixed(2)}</td>
                </tr>
                `;
            }).join("");
            tbody.innerHTML = rowsHtml;
        }
    }

    function renderStagesSection(stageCounts, totalTickets, monthName, year) {
        const monthLbl = document.getElementById("doc-stages-month-label");
        if (monthLbl) monthLbl.textContent = monthName;

        const totalVal = document.getElementById("doc-stages-total-val");
        if (totalVal) totalVal.textContent = totalTickets;

        const standardStages = [
            "New",
            "Work in Progress",
            "Waiting for Customer",
            "Waiting for Vendor",
            "Solved",
            "Closed",
            "Archived"
        ];

        const tbody = document.getElementById("stages-table-tbody");
        if (tbody) {
            let rowsHtml = "";
            standardStages.forEach(st => {
                const count = (stageCounts && stageCounts[st] !== undefined) ? stageCounts[st] : 0;
                rowsHtml += `
                <tr>
                    <td>${escapeHtml(st)}</td>
                    <td class="td-count">${count}</td>
                </tr>
                `;
            });
            tbody.innerHTML = rowsHtml;
        }

        const chartTitle = document.getElementById("stages-chart-title");
        if (chartTitle) chartTitle.textContent = `Estado de Tickets - ${monthName} ${year}`;

        const canvas = document.getElementById("stages-chart-canvas");
        if (canvas && window.Chart) {
            if (stagesChartInstance) {
                stagesChartInstance.destroy();
            }

            const ctx = canvas.getContext("2d");
            const values = standardStages.map(st => (stageCounts && stageCounts[st]) ? stageCounts[st] : 0);
            const maxVal = Math.max(...values, 1);

            stagesChartInstance = new window.Chart(ctx, {
                type: "bar",
                data: {
                    labels: standardStages,
                    datasets: [{
                        label: "Tickets por Estado",
                        data: values,
                        backgroundColor: "#f97316",
                        borderColor: "#ea580c",
                        borderWidth: 1,
                        borderRadius: 2,
                        barThickness: 28,
                        maxBarThickness: 34
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: 600 },
                    plugins: {
                        legend: {
                            display: true,
                            position: "bottom",
                            labels: { font: { family: "Inter", size: 12 }, boxWidth: 12, color: "#475569" }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            suggestedMax: maxVal + 1,
                            ticks: { stepSize: 1, precision: 0, color: "#64748b" },
                            grid: { color: "#e2e8f0" }
                        },
                        x: {
                            ticks: { color: "#475569", font: { size: 11, weight: "500" } },
                            grid: { display: false }
                        }
                    }
                }
            });
        }
    }

    function renderExecutiveReportDoc(report, rawTickets, fullData) {
        const typeCounts = fullData.type_counts || {};
        const totalTickets = fullData.total_tickets || 0;
        const monthName = fullData.month_name || "Mes";
        const year = fullData.year || 2026;
        const avgDays = fullData.avg_days || 0;
        const totalHours = fullData.total_hours || 0.0;
        const stageCounts = fullData.stage_counts || {};

        // SECTION 1: 1. RESUMEN DE SOPORTE (Image 1 & 2 exact order)
        elements.docSectionHeader.innerHTML = "1. &nbsp; RESUMEN DE SOPORTE";
        elements.docIntroText.textContent = report.intro || "";

        const itemsHtml = (report.tickets || []).map(t => {
            const matchedRaw = rawTickets.find(r => r.id === t.id);
            const odooUrl = matchedRaw ? matchedRaw.odoo_url : "#";
            
            return `
            <div class="report-doc-item" data-ticket-id="${t.id}">
                <a href="${odooUrl}" target="_blank" rel="noopener" class="report-item-title-link" title="Abrir #${t.id} en Odoo">
                    <span>${escapeHtml(t.title)} (#${t.id})</span>
                    <i data-lucide="external-link" style="width: 13px; height: 13px;"></i>
                </a>
                <p class="report-item-desc" contenteditable="true" title="Clic para editar">${escapeHtml(t.summary)}</p>
            </div>
            `;
        }).join("");
        elements.docItemsContainer.innerHTML = itemsHtml;

        // SECTION 2: 2. VOLUMEN DE CASOS (Image 3)
        renderVolumeSection(typeCounts, totalTickets, monthName, year);

        // SECTION 3: TIEMPO PROMEDIO (Image 4 Top)
        renderAvgDaysSection(rawTickets, avgDays, monthName);

        // SECTION 4: HISTORIAL DE HORAS (Image 4 Bottom & Image 5 Top)
        renderHoursSection(rawTickets, totalHours, monthName, year);

        // SECTION 5: ESTADO DE LOS TICKETS (Image 5 Bottom)
        renderStagesSection(stageCounts, totalTickets, monthName, year);

        updateIcons();
    }

    // Copy Full Report Text formatted for Word/Docs/Email (All 5 Sections)
    if (elements.btnCopyReportText) {
        elements.btnCopyReportText.addEventListener("click", () => {
            const sec1Header = elements.docSectionHeader?.innerText.trim() || "1. RESUMEN DE SOPORTE";
            const sec1Intro = elements.docIntroText?.innerText.trim() || "";
            
            // Section 1 Cases
            let sec1Cases = "";
            document.querySelectorAll(".report-doc-item").forEach(item => {
                const title = item.querySelector(".report-item-title-link")?.innerText.trim();
                const desc = item.querySelector(".report-item-desc")?.innerText.trim();
                if (title && desc) {
                    sec1Cases += `${title}\n${desc}\n\n`;
                }
            });

            // Section 2 Volume
            const volIntro = document.getElementById("doc-volume-intro")?.innerText.trim() || "";
            let volTableText = "Tipo de caso\tCantidad\n";
            document.querySelectorAll("#volume-table-tbody tr").forEach(tr => {
                const tds = tr.querySelectorAll("td");
                if (tds.length >= 2) {
                    volTableText += `${tds[0].innerText.trim()}\t${tds[1].innerText.trim()}\n`;
                }
            });
            const totalVal = document.getElementById("volume-total-val")?.innerText.trim() || "0";
            volTableText += `Total\t${totalVal}\n`;

            // Section 3 Tiempo Promedio
            const avgIntro = document.getElementById("doc-avg-days-intro")?.innerText.trim() || "";
            let avgTableText = "ID\tAsunto\tCreado el\tÚltima actualización\tDías\n";
            document.querySelectorAll("#avg-days-table-tbody tr").forEach(tr => {
                const tds = tr.querySelectorAll("td");
                if (tds.length >= 5) {
                    avgTableText += `${tds[0].innerText.trim()}\t${tds[1].innerText.trim()}\t${tds[2].innerText.trim()}\t${tds[3].innerText.trim()}\t${tds[4].innerText.trim()}\n`;
                }
            });
            const avgFooter = document.getElementById("doc-avg-days-footer")?.innerText.trim() || "0";
            avgTableText += `\t\t\tDías Promedio\t${avgFooter}\n`;

            // Section 4 Historial de Horas
            const hoursIntro = document.getElementById("doc-hours-intro")?.innerText.trim() || "";
            let hoursTableText = "ID\tAsunto\tEstado\tHoras\n";
            document.querySelectorAll("#hours-table-tbody tr").forEach(tr => {
                const tds = tr.querySelectorAll("td");
                if (tds.length >= 4) {
                    hoursTableText += `${tds[0].innerText.trim()}\t${tds[1].innerText.trim()}\t${tds[2].innerText.trim()}\t${tds[3].innerText.trim()}\n`;
                }
            });
            const totalHoursVal = document.getElementById("doc-total-hours-val")?.innerText.trim() || "0.00";
            hoursTableText += `\t\tTotal de horas\t${totalHoursVal}\n`;

            // Section 5 Estado de los tickets
            const stagesIntro = document.getElementById("doc-stages-intro")?.innerText.trim() || "";
            let stagesTableText = "Estado\tCantidad\n";
            document.querySelectorAll("#stages-table-tbody tr").forEach(tr => {
                const tds = tr.querySelectorAll("td");
                if (tds.length >= 2) {
                    stagesTableText += `${tds[0].innerText.trim()}\t${tds[1].innerText.trim()}\n`;
                }
            });
            const stagesTotalVal = document.getElementById("doc-stages-total-val")?.innerText.trim() || "0";
            stagesTableText += `Total\t${stagesTotalVal}\n`;

            const fullText = 
`${sec1Header}

${sec1Intro}

${sec1Cases}
2. VOLUMEN DE CASOS

${volIntro}

${volTableText}

TIEMPO PROMEDIO

${avgIntro}

${avgTableText}

HISTORIAL DE HORAS

${hoursIntro}

${hoursTableText}

ESTADO DE LOS TICKETS

${stagesIntro}

${stagesTableText}`;

            navigator.clipboard.writeText(fullText.trim()).then(() => {
                showToast("📋 Informe completo copiado al portapapeles");
            }).catch(() => {
                showToast("Error al copiar al portapapeles");
            });
        });
    }

    // Print Document / PDF Export
    if (elements.btnPrintReport) {
        elements.btnPrintReport.addEventListener("click", () => {
            window.print();
        });
    }

    if (elements.btnGenerateAiReport) {
        elements.btnGenerateAiReport.addEventListener("click", () => loadMonthlyReport(true));
    }

    if (elements.btnLoadReportTickets) {
        elements.btnLoadReportTickets.addEventListener("click", () => loadMonthlyReport(false));
    }

    // ==========================================
    // DETAIL MODAL (MONITOR)
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

                if (data.groq_base_url && elements.groqBaseUrlInput) {
                    elements.groqBaseUrlInput.value = data.groq_base_url;
                }

                if (data.groq_model && elements.groqModelSelect) {
                    elements.groqModelSelect.value = data.groq_model;
                }
                if (data.groq_system_prompt && elements.groqPromptInput) {
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
        const baseUrl = elements.groqBaseUrlInput ? elements.groqBaseUrlInput.value.trim() : "";
        const model = elements.groqModelSelect.value;

        elements.btnTestGroq.disabled = true;
        elements.btnTestGroq.innerHTML = `<span>Probando...</span>`;

        try {
            const res = await fetch("/api/settings/groq/test", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ api_key: apiKey, base_url: baseUrl, model: model })
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
        const baseUrl = elements.groqBaseUrlInput ? elements.groqBaseUrlInput.value.trim() : "";
        const model = elements.groqModelSelect.value;
        const prompt = elements.groqPromptInput.value.trim();

        elements.btnSaveGroq.disabled = true;

        try {
            const res = await fetch("/api/settings/groq", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ api_key: apiKey, base_url: baseUrl, model: model, system_prompt: prompt })
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
    // GROQ AI INDIVIDUAL TICKET ANALYSIS
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

        let text = raw.replace(/<think>[\s\S]*?<\/think>/gi, "").trim();
        text = text.replace(/^(?:###|##|#)\s*(?:[0-9️⃣]*\s*)?(.*?)$/gm, '<div class="ai-section-title">$1</div>');
        text = text.replace(/(?:^>[ \t]*(.*?)(?:\n|$))+/gm, (match) => {
            const inner = match.replace(/^>[ \t]*/gm, "").trim().replace(/\n/g, "<br>");
            return `<div class="ai-quote-box">${inner}</div>`;
        });
        text = text.replace(/^[ \t]*[-*•]\s+(.*?)$/gm, '<div class="ai-list-item"><span class="ai-bullet">▪</span><span>$1</span></div>');
        text = text.replace(/^[ \t]*(\d+)\.\s+(.*?)$/gm, '<div class="ai-list-item"><span class="ai-num">$1.</span><span>$2</span></div>');
        text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        text = text.replace(/(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');
        text = text.replace(/^---+$/gm, '<hr class="ai-divider">');

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

    // =========================================================
    // EXECUTIVE REPORT & SLIDES SYSTEM (IMAGEN 1 Y 2)
    // =========================================================

    const execState = {
        initialized: false,
        filterType: "team", // "team" or "partner"
        teams: [],
        partners: [],
        currentData: null,
        activeSlide: "slide1",
        donutChart: null,
        collabChart: null
    };

    function initExecutiveReport() {
        if (execState.initialized) return;
        execState.initialized = true;

        setupExecutiveDatePickers();
        setupExecutiveEventListeners();
        loadExecutiveFilters();
    }

    function setupExecutiveDatePickers() {
        const dStart = document.getElementById("exec-date-start");
        const dEnd = document.getElementById("exec-date-end");
        const hInput = document.getElementById("exec-contract-hours");

        // Load saved hours if any
        const savedHours = localStorage.getItem("odoo_contract_hours");
        if (savedHours && hInput) {
            hInput.value = savedHours;
        }

        // Set default to July 2026 (matching Tecniscan demo) or current month
        if (dStart && dEnd) {
            dStart.value = "2026-07-01";
            dEnd.value = "2026-07-31";
        }

        // Presets
        const pJuly = document.getElementById("preset-july-2026");
        const pThisMonth = document.getElementById("preset-this-month");
        const pLast30 = document.getElementById("preset-last-30");
        const pYear = document.getElementById("preset-year-2026");

        function clearPresetActive() {
            document.querySelectorAll(".exec-presets-chips .btn-chip").forEach(b => b.classList.remove("active"));
        }

        if (pJuly) {
            pJuly.addEventListener("click", () => {
                clearPresetActive();
                pJuly.classList.add("active");
                if (dStart && dEnd) {
                    dStart.value = "2026-07-01";
                    dEnd.value = "2026-07-31";
                    fetchExecutiveData();
                }
            });
        }

        if (pThisMonth) {
            pThisMonth.addEventListener("click", () => {
                clearPresetActive();
                pThisMonth.classList.add("active");
                const now = new Date();
                const y = now.getFullYear();
                const m = String(now.getMonth() + 1).padStart(2, "0");
                const d = String(now.getDate()).padStart(2, "0");
                if (dStart && dEnd) {
                    dStart.value = `${y}-${m}-01`;
                    dEnd.value = `${y}-${m}-${d}`;
                    fetchExecutiveData();
                }
            });
        }

        if (pLast30) {
            pLast30.addEventListener("click", () => {
                clearPresetActive();
                pLast30.classList.add("active");
                const now = new Date();
                const past = new Date(now.getTime() - (30 * 24 * 60 * 60 * 1000));
                const fmt = (dt) => `${dt.getFullYear()}-${String(dt.getMonth()+1).padStart(2,"0")}-${String(dt.getDate()).padStart(2,"0")}`;
                if (dStart && dEnd) {
                    dStart.value = fmt(past);
                    dEnd.value = fmt(now);
                    fetchExecutiveData();
                }
            });
        }

        if (pYear) {
            pYear.addEventListener("click", () => {
                clearPresetActive();
                pYear.classList.add("active");
                const y = new Date().getFullYear();
                if (dStart && dEnd) {
                    dStart.value = `${y}-01-01`;
                    dEnd.value = `${y}-12-31`;
                    fetchExecutiveData();
                }
            });
        }
    }

    function setupExecutiveEventListeners() {
        const entitySelect = document.getElementById("exec-entity-select");
        const btnGenerate = document.getElementById("btn-exec-generate");
        const btnCapture = document.getElementById("btn-exec-capture-mode");
        const btnPrint = document.getElementById("btn-exec-print");
        const hInput = document.getElementById("exec-contract-hours");

        // Generate Report Button
        if (btnGenerate) {
            btnGenerate.addEventListener("click", () => fetchExecutiveData());
        }

        // Entity Select Change (Helpdesk Team)
        if (entitySelect) {
            entitySelect.addEventListener("change", () => fetchExecutiveData());
        }

        // Dynamic Contract Hours Input Change (Instant recalculation without network call)
        if (hInput) {
            hInput.addEventListener("input", () => {
                const val = parseFloat(hInput.value) || 0;
                localStorage.setItem("odoo_contract_hours", val);
                recalculateExecutiveMetrics(val);
            });
        }

        // Capture Mode Toggle (16:9 Presentation View)
        if (btnCapture) {
            btnCapture.addEventListener("click", toggleCaptureMode);
        }

        // Print Report
        if (btnPrint) {
            btnPrint.addEventListener("click", () => {
                setTimeout(() => window.print(), 200);
            });
        }
    }

    function toggleCaptureMode() {
        const isCapture = document.body.classList.toggle("slide-capture-mode");
        let exitBtn = document.getElementById("btn-exit-capture-floating");

        if (isCapture) {
            if (!exitBtn) {
                exitBtn = document.createElement("button");
                exitBtn.id = "btn-exit-capture-floating";
                exitBtn.className = "btn-exit-capture";
                exitBtn.innerHTML = '<span>Salir de Modo Diapositiva (ESC)</span>';
                document.body.appendChild(exitBtn);
                exitBtn.addEventListener("click", toggleCaptureMode);
            }
            exitBtn.style.display = "flex";

            const escHandler = (e) => {
                if (e.key === "Escape") {
                    document.body.classList.remove("slide-capture-mode");
                    if (exitBtn) exitBtn.style.display = "none";
                    window.removeEventListener("keydown", escHandler);
                }
            };
            window.addEventListener("keydown", escHandler);
            showToast("📷 Modo Diapositiva activado (Presiona ESC para salir)");
        } else {
            if (exitBtn) exitBtn.style.display = "none";
        }
    }

    async function loadExecutiveFilters() {
        try {
            const res = await fetch("/api/executive/filters");
            const data = await res.json();
            if (data.success) {
                execState.teams = data.teams || [];
                execState.partners = data.partners || [];
                populateEntityDropdown();
                
                // Auto trigger initial load for Tecniscan
                fetchExecutiveData();
            }
        } catch (e) {
            console.error("Error loading executive filters:", e);
        }
    }

    function populateEntityDropdown() {
        const select = document.getElementById("exec-entity-select");
        if (!select) return;

        select.innerHTML = "";
        const list = execState.filterType === "team" ? execState.teams : execState.partners;

        if (list.length === 0) {
            select.innerHTML = '<option value="">Sin elementos disponibles</option>';
            return;
        }

        let defaultSelectedId = null;

        list.forEach(item => {
            const opt = document.createElement("option");
            opt.value = item.id;
            const extra = item.tickets_count ? ` (${item.tickets_count} tickets)` : "";
            opt.textContent = `${item.name}${extra}`;

            // Priority default: Tecniscan
            if (item.name.toLowerCase().includes("tecniscan") && !defaultSelectedId) {
                defaultSelectedId = item.id;
            }
            select.appendChild(opt);
        });

        if (defaultSelectedId) {
            select.value = defaultSelectedId;
        } else if (list.length > 0) {
            select.value = list[0].id;
        }
    }

    async function fetchExecutiveData() {
        const entitySelect = document.getElementById("exec-entity-select");
        const dStart = document.getElementById("exec-date-start");
        const dEnd = document.getElementById("exec-date-end");
        const hInput = document.getElementById("exec-contract-hours");
        const loadingCard = document.getElementById("exec-loading-state");
        const slidesContainer = document.getElementById("slides-master-container");

        if (!entitySelect || !entitySelect.value) return;

        const filterId = entitySelect.value;
        const startDate = dStart ? dStart.value : "";
        const endDate = dEnd ? dEnd.value : "";
        const contractHours = hInput ? (parseFloat(hInput.value) || 120.0) : 120.0;

        if (loadingCard) loadingCard.classList.remove("hidden");
        if (slidesContainer) slidesContainer.style.opacity = "0.4";

        try {
            const params = new URLSearchParams({
                filter_type: "team",
                filter_id: filterId,
                start_date: startDate,
                end_date: endDate,
                contract_hours: contractHours
            });

            const res = await fetch(`/api/executive/data?${params.toString()}`);
            const data = await res.json();

            if (data.success) {
                execState.currentData = data;
                renderMasterSlide(data);
            } else {
                showToast(`Error: ${data.error || "No se pudo cargar el reporte"}`);
            }
        } catch (err) {
            console.error("Error fetching executive report:", err);
            showToast("Error de conexión al cargar datos del reporte");
        } finally {
            if (loadingCard) loadingCard.classList.add("hidden");
            if (slidesContainer) slidesContainer.style.opacity = "1";
            updateIcons();
        }
    }

    // Dynamic In-Memory Recalculation (When changing Horas Totales Disponibles)
    function recalculateExecutiveMetrics(newContractHours) {
        if (!execState.currentData) return;
        const d = execState.currentData;
        const k = d.kpis;
        
        k.total_hours_available = newContractHours;
        k.total_hours_remaining = Math.max(0, parseFloat((newContractHours - k.total_hours_used).toFixed(2)));
        k.utilization_pct = newContractHours > 0 ? parseFloat(((k.total_hours_used / newContractHours) * 100).toFixed(2)) : 0;
        k.availability_pct = newContractHours > 0 ? parseFloat(((k.total_hours_remaining / newContractHours) * 100).toFixed(2)) : 0;

        // Update Top Ribbon KPI elements
        const elAvail = document.getElementById("s-kpi-total-avail");
        const elRem = document.getElementById("s-kpi-total-rem");
        const elUtil = document.getElementById("s-kpi-total-util");
        if (elAvail) elAvail.textContent = k.total_hours_available.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        if (elRem) elRem.textContent = k.total_hours_remaining.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        if (elUtil) elUtil.textContent = `${k.utilization_pct.toFixed(2)}%`;

        // Update Donut Center & Legend
        const donutCenter = document.getElementById("s-donut-center-hours");
        const legUsed = document.getElementById("s-leg-used");
        const legRem = document.getElementById("s-leg-rem");
        if (donutCenter) donutCenter.textContent = k.total_hours_available.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        if (legUsed) legUsed.textContent = `${k.total_hours_used.toFixed(2)} h (${k.utilization_pct.toFixed(2)}%)`;
        if (legRem) legRem.textContent = `${k.total_hours_remaining.toFixed(2)} h (${k.availability_pct.toFixed(2)}%)`;

        // Update Donut Chart
        if (execState.donutChart) {
            execState.donutChart.data.datasets[0].data = [k.total_hours_used, k.total_hours_remaining];
            execState.donutChart.update();
        }
    }

    // =========================================================
    // RENDER UNIFIED MASTER SLIDE (SINGLE FULL WIDESCREEN SLIDE)
    // =========================================================
    function renderMasterSlide(data) {
        const k = data.kpis;

        // Header Title & Period
        const sTitle = document.getElementById("s-main-title");
        const sPeriod = document.getElementById("s-main-period");
        if (sTitle) sTitle.textContent = `${data.entity_name} — Reporte Ejecutivo de Soporte y Horas`;
        if (sPeriod) sPeriod.textContent = `Período: ${data.period_label || data.period_month} · Genesys Cloud CX`;

        // Team / Helpdesk Logo Handling
        const iconBox = document.getElementById("s-header-icon-box");
        const teamLogoImg = document.getElementById("s-team-logo-img");
        const defaultIcon = document.getElementById("s-header-default-icon");

        if (data.has_team_logo && data.team_logo_url) {
            if (teamLogoImg) {
                teamLogoImg.src = data.team_logo_url;
                teamLogoImg.style.display = "block";
            }
            if (defaultIcon) defaultIcon.style.display = "none";
            if (iconBox) iconBox.classList.add("has-team-logo");
        } else {
            if (teamLogoImg) {
                teamLogoImg.style.display = "none";
                teamLogoImg.src = "";
            }
            if (defaultIcon) defaultIcon.style.display = "flex";
            if (iconBox) iconBox.classList.remove("has-team-logo");
        }

        const esmtLogoImg = document.querySelector(".sm-esmt-logo");
        if (esmtLogoImg && data.esmt_logo_url) {
            esmtLogoImg.src = data.esmt_logo_url;
        }

        // Top 7 KPI Ribbon
        const elAvail = document.getElementById("s-kpi-total-avail");
        const elUsed = document.getElementById("s-kpi-total-used");
        const elRem = document.getElementById("s-kpi-total-rem");
        const elUtil = document.getElementById("s-kpi-total-util");
        const elCases = document.getElementById("s-kpi-total-cases");
        const elBreakdown = document.getElementById("s-kpi-types-breakdown");
        const elClosedRatio = document.getElementById("s-kpi-closed-ratio");
        const elClosedPct = document.getElementById("s-kpi-closed-pct");
        const elAvgDays = document.getElementById("s-kpi-avg-days");
        const elLongestSub = document.getElementById("s-kpi-longest-sub");

        if (elAvail) elAvail.textContent = k.total_hours_available.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        if (elUsed) elUsed.textContent = k.total_hours_used.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        if (elRem) elRem.textContent = k.total_hours_remaining.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        if (elUtil) elUtil.textContent = `${k.utilization_pct.toFixed(2)}%`;
        if (elCases) elCases.textContent = k.total_cases;

        const reqItem = (data.type_distribution || []).find(x => x.type.toLowerCase().includes("requer")) || { count: 0 };
        const incItem = (data.type_distribution || []).find(x => x.type.toLowerCase().includes("inciden")) || { count: 0 };
        if (elBreakdown) elBreakdown.textContent = `${reqItem.count} req · ${incItem.count} incidente`;

        if (elClosedRatio) elClosedRatio.textContent = `${k.closed_cases} / ${k.total_cases}`;
        if (elClosedPct) elClosedPct.textContent = `${k.closed_pct.toFixed(1)}% resueltos`;
        if (elAvgDays) elAvgDays.textContent = `${k.avg_resolution_days} días`;
        if (elLongestSub) {
            elLongestSub.textContent = k.longest_ticket && k.longest_ticket.days ? `Max: ${k.longest_ticket.days} d` : `0 d`;
        }

        // ================= COLUMN 1: RESUMEN DE TICKETS =================
        const ticketBadge = document.getElementById("s-ticket-count-badge");
        if (ticketBadge) ticketBadge.textContent = k.total_cases;

        const ticketList = document.getElementById("s-ticket-list");
        if (ticketList) {
            ticketList.innerHTML = "";
            if (!data.tickets || data.tickets.length === 0) {
                ticketList.innerHTML = '<div style="padding: 16px; color: #94a3b8; text-align: center;">No hay tickets registrados en este período</div>';
            } else {
                data.tickets.forEach(t => {
                    const item = document.createElement("div");
                    item.className = "sm-ticket-item";

                    let badgeClass = "sm-badge-closed";
                    if (t.stage_category === "Waiting Customer") badgeClass = "sm-badge-waiting";
                    else if (t.stage_category === "Work in Progress") badgeClass = "sm-badge-wip";

                    const rawHours = typeof t.hours_spent === "number" ? t.hours_spent : (typeof t.unit_amount === "number" ? t.unit_amount : parseFloat(t.hours_spent || t.unit_amount || 0));
                    const ticketHours = isNaN(rawHours) ? "0.0" : (rawHours % 1 === 0 ? rawHours.toFixed(1) : (Number.isInteger(rawHours * 10) ? rawHours.toFixed(1) : rawHours.toFixed(2)));

                    item.innerHTML = `
                        <span class="sm-ticket-id"><a href="${t.odoo_url}" target="_blank" rel="noopener" style="color: inherit; text-decoration: none;">#${t.id}</a></span>
                        <span class="sm-ticket-name" title="${escapeHtml(t.name)}">${escapeHtml(t.name)}</span>
                        <span class="sm-badge-pill ${badgeClass}">${escapeHtml(t.stage)}</span>
                        <span class="sm-ticket-hours" title="${rawHours.toFixed(2)} h consumidas">${ticketHours}h</span>
                        <span class="sm-ticket-days">${t.days_spent} d</span>
                    `;
                    ticketList.appendChild(item);
                });
            }
        }

        const longestDesc = document.getElementById("s-longest-case-desc");
        if (longestDesc) {
            if (k.longest_ticket && k.longest_ticket.days) {
                longestDesc.textContent = `#${k.longest_ticket.id} - ${k.longest_ticket.name} (${k.longest_ticket.days} días)`;
            } else {
                longestDesc.textContent = "Sin tickets de larga duración";
            }
        }

        // ================= COLUMN 2: DETALLE POR COLABORADOR =================
        // A los colaboradores NO se les asigna cuota de horas, solo consumen según atención
        const collabTbody = document.getElementById("s-collab-tbody");
        if (collabTbody) {
            collabTbody.innerHTML = "";
            if (!data.collaborators || data.collaborators.length === 0) {
                collabTbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: #94a3b8; padding: 14px;">No se registraron horas por colaborador en este período</td></tr>';
            } else {
                data.collaborators.forEach(c => {
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td><strong>${escapeHtml(c.name)}</strong></td>
                        <td class="text-center">${c.tickets_count || 0}</td>
                        <td class="text-right"><strong>${c.hours_used.toFixed(2)} h</strong></td>
                        <td class="text-right" style="color: #0284c7; font-weight: 700;">${c.pct_of_total_used.toFixed(2)}%</td>
                    `;
                    collabTbody.appendChild(tr);
                });
            }
        }

        const collabTotCases = document.getElementById("s-collab-total-cases");
        const collabTotHours = document.getElementById("s-collab-total-hours");
        if (collabTotCases) collabTotCases.textContent = k.total_cases;
        if (collabTotHours) collabTotHours.textContent = `${k.total_hours_used.toFixed(2)} h`;

        renderMasterCollabBarChart(data.collaborators);

        // ================= COLUMN 3: DISTRIBUCIÓN & ESTADOS =================
        const donutCenter = document.getElementById("s-donut-center-hours");
        const legUsed = document.getElementById("s-leg-used");
        const legRem = document.getElementById("s-leg-rem");

        if (donutCenter) donutCenter.textContent = k.total_hours_available.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        if (legUsed) legUsed.textContent = `${k.total_hours_used.toFixed(2)} h (${k.utilization_pct.toFixed(2)}%)`;
        if (legRem) legRem.textContent = `${k.total_hours_remaining.toFixed(2)} h (${k.availability_pct.toFixed(2)}%)`;

        renderMasterDonutChart(k.total_hours_used, k.total_hours_remaining);

        // Type Distribution Table
        const typeTbody = document.getElementById("s-type-tbody");
        if (typeTbody) {
            typeTbody.innerHTML = "";
            (data.type_distribution || []).forEach(td => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${escapeHtml(td.type)}</td>
                    <td class="text-center"><strong>${td.count}</strong></td>
                    <td class="text-right" style="color: #0d9488; font-weight: 700;">${td.pct.toFixed(1)}%</td>
                `;
                typeTbody.appendChild(tr);
            });
        }

        // Estado de los Tickets (Horizontal Progress Bars)
        const stagesContainer = document.getElementById("s-stages-container");
        if (stagesContainer) {
            stagesContainer.innerHTML = "";
            (data.stage_distribution || []).forEach(st => {
                const row = document.createElement("div");
                row.className = "sm-stage-row";
                row.innerHTML = `
                    <div class="sm-stage-label-row">
                        <span>${escapeHtml(st.label)} &nbsp; <strong>${st.count}</strong></span>
                        <span>${st.pct.toFixed(1)}%</span>
                    </div>
                    <div class="sm-stage-track">
                        <div class="sm-stage-bar" style="width: ${Math.max(st.pct, st.count > 0 ? 4 : 0)}%; background: ${st.color};"></div>
                    </div>
                `;
                stagesContainer.appendChild(row);
            });
        }

        // Footer Source
        const fSource = document.getElementById("s-footer-source");
        if (fSource) {
            fSource.textContent = `Fuente: Odoo Helpdesk · ${data.entity_name} · ESMT Consulting · Informe Oficial Confidencial`;
        }
    }

    function renderMasterDonutChart(used, remaining) {
        const canvas = document.getElementById("s-donut-chart");
        if (!canvas) return;

        if (execState.donutChart) {
            execState.donutChart.destroy();
        }

        const ctx = canvas.getContext("2d");
        execState.donutChart = new Chart(ctx, {
            type: "doughnut",
            data: {
                labels: ["Horas Utilizadas", "Horas Disponibles Restantes"],
                datasets: [{
                    data: [used, remaining],
                    backgroundColor: ["#16a34a", "#eab308"],
                    borderWidth: 2,
                    borderColor: "#ffffff",
                    hoverOffset: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "68%",
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const val = context.raw || 0;
                                const total = used + remaining;
                                const pct = total > 0 ? ((val / total) * 100).toFixed(1) : 0;
                                return ` ${context.label}: ${val.toFixed(2)} hrs (${pct}%)`;
                            }
                        }
                    }
                }
            }
        });
    }

    function renderMasterCollabBarChart(collaborators) {
        const canvas = document.getElementById("s-collab-barchart");
        if (!canvas) return;

        if (execState.collabChart) {
            execState.collabChart.destroy();
        }

        const labels = (collaborators || []).map(c => {
            const parts = c.name.split(" ");
            return parts.length > 1 ? `${parts[0]} ${parts[1].charAt(0)}.` : c.name;
        });
        const values = (collaborators || []).map(c => c.hours_used);

        const ctx = canvas.getContext("2d");
        execState.collabChart = new Chart(ctx, {
            type: "bar",
            data: {
                labels: labels.length ? labels : ["Sin colaboradores"],
                datasets: [{
                    label: "Horas Consumidas",
                    data: values.length ? values : [0],
                    backgroundColor: "#0284c7",
                    borderRadius: 4,
                    barPercentage: 0.55
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                layout: {
                    padding: {
                        top: 22
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grace: "20%",
                        ticks: {
                            callback: value => `${value} h`,
                            font: { size: 10 }
                        },
                        grid: { color: "rgba(0,0,0,0.05)" }
                    },
                    x: {
                        ticks: { font: { size: 10, weight: "600" } },
                        grid: { display: false }
                    }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: context => ` Consumo: ${Number(context.raw || 0).toFixed(2)} hrs`
                        }
                    }
                }
            },
            plugins: [{
                id: "alwaysShowBarValues",
                afterDatasetsDraw(chart) {
                    const { ctx } = chart;
                    chart.data.datasets.forEach((dataset, i) => {
                        const meta = chart.getDatasetMeta(i);
                        meta.data.forEach((bar, index) => {
                            const val = dataset.data[index];
                            if (val === undefined || val === null) return;
                            const numStr = `${Number(val).toFixed(2)} h`;
                            ctx.save();
                            ctx.font = "bold 11px Inter, system-ui, -apple-system, sans-serif";
                            ctx.fillStyle = "#0369a1";
                            ctx.textAlign = "center";
                            ctx.textBaseline = "bottom";
                            ctx.fillText(numStr, bar.x, bar.y - 5);
                            ctx.restore();
                        });
                    });
                }
            }]
        });
    }

    // Start App
    checkAuthStatus();
});

