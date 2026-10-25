// Microsoft Rewards Gift Card Tracker Frontend Client (WhatsApp & Telegram Only)

let currentStatusData = null;
let pollTimer = null;

document.addEventListener("DOMContentLoaded", () => {
    fetchStatus();
    pollTimer = setInterval(fetchStatus, 3000);
});

async function fetchStatus() {
    try {
        const res = await fetch("/api/status");
        if (!res.ok) return;
        const data = await res.json();
        currentStatusData = data;
        updateUI(data);
    } catch (e) {
        console.error("Status fetch failed:", e);
    }
}

function updateUI(data) {
    // 1. Master Toggle & Banner
    const masterToggle = document.getElementById("masterToggle");
    const statusIndicator = document.getElementById("statusIndicator");
    const statusBadge = document.getElementById("statusBadge");
    const toggleLabel = document.getElementById("toggleLabel");
    const checkingBadge = document.getElementById("checkingBadge");

    if (masterToggle && document.activeElement !== masterToggle) {
        masterToggle.checked = data.enabled;
    }

    if (data.enabled) {
        statusIndicator.className = "spinner-grow spinner-grow-sm text-success";
        statusBadge.className = "badge bg-success-subtle text-success border border-success-subtle px-3 py-1 fs-6 fw-semibold";
        statusBadge.innerText = "MONITORING ACTIVE";
        toggleLabel.innerText = "Click to Pause Tracker";
    } else {
        statusIndicator.className = "spinner-grow spinner-grow-sm text-warning";
        statusBadge.className = "badge bg-warning-subtle text-warning-emphasis border border-warning-subtle px-3 py-1 fs-6 fw-semibold";
        statusBadge.innerText = "TRACKER PAUSED";
        toggleLabel.innerText = "Click to Resume Tracker";
    }

    if (data.is_checking) {
        checkingBadge.classList.remove("d-none");
    } else {
        checkingBadge.classList.add("d-none");
    }

    // 2. Points & Timing
    const pts = data.user_points || 29000;
    document.getElementById("userPointsText").innerText = pts.toLocaleString();
    document.getElementById("intervalText").innerText = `${data.check_interval_seconds || 90}s`;

    const summary = data.last_summary || {};
    document.getElementById("lastCheckTime").innerText = summary.timestamp || "Starting initial check...";

    // 3. Session Cookie Banner
    const cookieBanner = document.getElementById("cookieWarningBanner");
    const sessionStatusBadge = document.getElementById("sessionStatusBadge");

    if (data.has_session_cookie) {
        cookieBanner.classList.add("d-none");
        sessionStatusBadge.className = "badge bg-success text-white small";
        sessionStatusBadge.innerHTML = '<i class="bi bi-check-circle me-1"></i> Session Connected';
    } else {
        cookieBanner.classList.remove("d-none");
        sessionStatusBadge.className = "badge bg-warning text-dark small";
        sessionStatusBadge.innerHTML = '<i class="bi bi-exclamation-triangle me-1"></i> No Session Cookie';
    }

    // 4. Alert Channels summary (WhatsApp & Telegram)
    updateAlertBadges(data);

    // 5. Targets Cards
    renderTargets(data.targets || []);

    // 6. Activity Logs
    renderLogs(data.logs || []);
}

function updateAlertBadges(data) {
    const tg = data.telegram_config || {};
    const tgBadge = document.getElementById("badgeTelegram");
    if (tg.enabled && tg.configured) {
        tgBadge.className = "badge bg-success-subtle text-success";
        tgBadge.innerText = "Connected";
    } else if (tg.enabled && !tg.configured) {
        tgBadge.className = "badge bg-warning-subtle text-warning";
        tgBadge.innerText = "Token Missing";
    } else {
        tgBadge.className = "badge bg-secondary-subtle text-secondary";
        tgBadge.innerText = "Disabled";
    }

    const green = data.green_api_config || {};
    const wa = data.whatsapp_config || {};
    const waBadge = document.getElementById("badgeWhatsApp");
    if ((green.enabled && green.configured) || (wa.enabled && wa.configured)) {
        waBadge.className = "badge bg-success-subtle text-success";
        waBadge.innerText = "Connected";
    } else {
        waBadge.className = "badge bg-secondary-subtle text-secondary";
        waBadge.innerText = "Not Configured";
    }
}

function renderTargets(targets) {
    const container = document.getElementById("targetsContainer");
    if (!targets.length) {
        container.innerHTML = `<div class="card border-0 shadow-sm rounded-3 p-4 text-center text-muted">No brands tracked. Add them in Settings.</div>`;
        return;
    }

    document.getElementById("targetsCountBadge").innerText = `${targets.filter(t => t.enabled).length} of ${targets.length} Active`;

    let html = "";
    targets.forEach(t => {
        let iconClass = "bi-gift";
        let brandClass = "brand-generic";
        const idLower = (t.id || "").toLowerCase();

        if (idLower.includes("flipkart")) {
            iconClass = "bi-bag-check-fill";
            brandClass = "brand-flipkart";
        } else if (idLower.includes("amazon")) {
            iconClass = "bi-cart-fill";
            brandClass = "brand-amazon";
        } else if (idLower.includes("croma")) {
            iconClass = "bi-tv-fill";
            brandClass = "brand-croma";
        }

        let statusBadgeHtml = "";
        let pulseClass = "";
        const st = t.last_status || "UNKNOWN";

        if (st === "IN_STOCK") {
            statusBadgeHtml = `<span class="badge badge-in-stock px-3 py-2 fw-bold pulse-green"><i class="bi bi-check-circle-fill me-1"></i> IN STOCK NOW</span>`;
            pulseClass = "border-success";
        } else if (st === "RESTOCKING") {
            statusBadgeHtml = `<span class="badge badge-restocking px-3 py-2 fw-semibold"><i class="bi bi-clock-history me-1"></i> Restocking Back Soon</span>`;
        } else if (st === "NOT_IN_CATALOG") {
            statusBadgeHtml = `<span class="badge badge-out-of-stock px-3 py-2"><i class="bi bi-slash-circle me-1"></i> Not in Catalog</span>`;
        } else {
            statusBadgeHtml = `<span class="badge badge-out-of-stock px-3 py-2">${st}</span>`;
        }

        const redeemUrl = t.url || "https://rewards.bing.com/redeem/";

        html += `
        <div class="card target-card rounded-4 p-4 ${pulseClass} ${!t.enabled ? 'opacity-50' : ''}">
            <div class="d-flex flex-column flex-sm-row align-items-sm-center justify-content-between gap-3">
                <div class="d-flex align-items-center gap-3">
                    <div class="brand-icon-box ${brandClass}">
                        <i class="bi ${iconClass}"></i>
                    </div>
                    <div>
                        <div class="d-flex align-items-center gap-2">
                            <h6 class="fw-bold mb-0 text-dark">${t.name}</h6>
                            ${!t.enabled ? '<span class="badge bg-light text-muted border small">Paused</span>' : ''}
                        </div>
                        <div class="text-secondary small mt-1">
                            <span>Keywords: <code>${(t.keywords || []).join(", ")}</code></span>
                        </div>
                    </div>
                </div>

                <div class="d-flex align-items-center gap-2">
                    ${statusBadgeHtml}
                    <a href="${redeemUrl}" target="_blank" class="btn btn-outline-primary btn-sm rounded-3 fw-semibold">
                        <i class="bi bi-box-arrow-up-right"></i>
                    </a>
                </div>
            </div>
        </div>
        `;
    });

    container.innerHTML = html;
}

function renderLogs(logs) {
    const container = document.getElementById("logsContainer");
    if (!logs.length) {
        container.innerHTML = `<div class="text-center text-muted py-3 small">No activity recorded yet.</div>`;
        return;
    }

    let html = "";
    logs.forEach(l => {
        const lvlClass = `level-${l.level || 'info'}`;
        html += `
        <div class="log-entry ${lvlClass} d-flex align-items-start gap-2">
            <span class="text-muted fw-bold">${l.time}</span>
            <span class="flex-grow-1">${escapeHtml(l.message)}</span>
        </div>
        `;
    });

    container.innerHTML = html;
}

function escapeHtml(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

async function toggleMonitoring() {
    try {
        const res = await fetch("/api/toggle", { method: "POST" });
        const data = await res.json();
        fetchStatus();
    } catch (e) {
        alert("Failed to toggle monitoring: " + e);
    }
}

async function triggerCheckNow() {
    const icon = document.getElementById("checkNowIcon");
    if (icon) icon.classList.add("spin");

    try {
        const res = await fetch("/api/check_now", { method: "POST" });
        const data = await res.json();
        setTimeout(fetchStatus, 1500);
    } catch (e) {
        alert("Check trigger failed: " + e);
    } finally {
        setTimeout(() => {
            if (icon) icon.classList.remove("spin");
        }, 1200);
    }
}

async function triggerSimulation() {
    if (!confirm("This will trigger a simulated IN-STOCK alert to your configured Telegram & WhatsApp. Proceed?")) return;

    try {
        const res = await fetch("/api/simulate_stock", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ target_id: "flipkart" })
        });
        const data = await res.json();
        alert("Simulated stock alert dispatched! Check your Telegram and WhatsApp.");
        fetchStatus();
    } catch (e) {
        alert("Simulation failed: " + e);
    }
}

async function testChannel(channel) {
    try {
        const res = await fetch("/api/test_alert", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ channel: channel })
        });
        const data = await res.json();
        const results = data.results || {};
        const chRes = results[channel] || results;
        if (chRes && chRes.error) {
            alert(`⚠️ Test for ${channel} notice:\n${chRes.error}`);
        } else {
            alert(`✅ Test for ${channel} successfully dispatched! Check your phone.`);
        }
        fetchStatus();
    } catch (e) {
        alert("Test failed: " + e);
    }
}

// Settings Modal Binding
const settingsModalEl = document.getElementById("settingsModal");
if (settingsModalEl) {
    settingsModalEl.addEventListener("show.bs.modal", () => {
        populateSettingsModal();
    });
}

function populateSettingsModal() {
    if (!currentStatusData) return;

    fetch("/api/status").then(r => r.json()).then(data => {
        currentStatusData = data;
        const cfg = data;

        // Interval & Points
        document.getElementById("inputInterval").value = cfg.check_interval_seconds || 90;
        document.getElementById("inputUserPoints").value = cfg.user_points || 29000;

        // Session Cookie
        document.getElementById("inputCookie").placeholder = cfg.has_session_cookie ? "Session cookie is currently SAVED and ACTIVE. Paste here to replace..." : "Paste your Cookie: header here...";

        // Telegram
        const tg = cfg.telegram_config || {};
        document.getElementById("checkTgEnabled").checked = tg.enabled;

        // Targets in settings
        renderSettingsTargets(cfg.targets || []);
    });
}

function renderSettingsTargets(targets) {
    const container = document.getElementById("settingsTargetsList");
    let html = "";
    targets.forEach((t, index) => {
        html += `
        <div class="card border rounded-3 p-3 bg-light">
            <div class="d-flex align-items-center justify-content-between">
                <div>
                    <h6 class="fw-bold mb-0 text-dark">${t.name}</h6>
                    <small class="text-muted">Keywords: ${(t.keywords || []).join(", ")}</small>
                </div>
                <div class="form-check form-switch">
                    <input class="form-check-input" type="checkbox" id="targetToggle_${index}" ${t.enabled ? 'checked' : ''}>
                </div>
            </div>
        </div>
        `;
    });
    container.innerHTML = html;
}

async function saveSettings() {
    const cookieVal = document.getElementById("inputCookie").value.trim();
    const intervalVal = parseInt(document.getElementById("inputInterval").value) || 90;
    const pointsVal = parseInt(document.getElementById("inputUserPoints").value) || 29000;
    const userAgentVal = document.getElementById("inputUserAgent").value.trim();

    const tgEnabled = document.getElementById("checkTgEnabled").checked;
    const tgToken = document.getElementById("inputTgToken").value.trim();
    const tgChatId = document.getElementById("inputTgChatId").value.trim();

    const greenEnabled = document.getElementById("checkGreenEnabled").checked;
    const greenId = document.getElementById("inputGreenId").value.trim();
    const greenToken = document.getElementById("inputGreenToken").value.trim();
    const greenPhone = document.getElementById("inputGreenPhone").value.trim();
    const greenHost = document.getElementById("inputGreenHost").value.trim();

    const waEnabled = document.getElementById("checkWaEnabled").checked;
    const waPhone = document.getElementById("inputWaPhone").value.trim();
    const waKey = document.getElementById("inputWaKey").value.trim();

    // Update targets enablement
    const targets = (currentStatusData && currentStatusData.targets) ? [...currentStatusData.targets] : [];
    targets.forEach((t, index) => {
        const toggleEl = document.getElementById(`targetToggle_${index}`);
        if (toggleEl) {
            t.enabled = toggleEl.checked;
        }
    });

    const payload = {
        check_interval_seconds: intervalVal,
        user_points: pointsVal,
        alerts: {
            telegram_message: tgEnabled,
            whatsapp_message: greenEnabled || waEnabled
        },
        targets: targets
    };

    if (cookieVal) {
        payload.session = { cookie: cookieVal };
        if (userAgentVal) payload.session.user_agent = userAgentVal;
    }

    if (tgToken || tgChatId || tgEnabled !== undefined) {
        payload.telegram = {
            enabled: tgEnabled,
            bot_token: tgToken || (currentStatusData.telegram_config && currentStatusData.telegram_config.bot_token) || "",
            chat_id: tgChatId || (currentStatusData.telegram_config && currentStatusData.telegram_config.chat_id) || ""
        };
    }

    if (greenId || greenToken || greenPhone || greenEnabled !== undefined) {
        payload.green_api = {
            enabled: greenEnabled,
            id_instance: greenId,
            api_token_instance: greenToken,
            phone: greenPhone,
            host_url: greenHost
        };
    }

    if (waPhone || waKey || waEnabled !== undefined) {
        payload.whatsapp = {
            enabled: waEnabled,
            phone: waPhone,
            callmebot_api_key: waKey
        };
    }

    try {
        const res = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            alert("Settings saved successfully!");
            const modalEl = document.getElementById("settingsModal");
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
            fetchStatus();
        } else {
            alert("Error saving settings: " + data.error);
        }
    } catch (e) {
        alert("Failed to save settings: " + e);
    }
}
