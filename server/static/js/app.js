let servers = [];
let currentTerminal = null;
let currentWs = null;

// i18n render
function renderPage() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        el.textContent = t(key);
    });
    document.getElementById('langBtn').textContent = currentLang.toUpperCase();
    document.getElementById('addServerBtn').textContent = t('addServer');
    renderServers();
}

// Load servers
async function loadServers() {
    try {
        const resp = await fetch('/api/servers', {credentials: 'include'});
        if (resp.status === 401) {
            window.location.href = '/login';
            return;
        }
        servers = await resp.json();
        renderServers();
    } catch (e) {
        console.error('Load error:', e);
    }
}

function renderServers() {
    const grid = document.getElementById('servers-grid');
    const online = servers.filter(s => s.metrics?.online).length;
    const offline = servers.length - online;

    document.getElementById('total-count').textContent = servers.length;
    document.getElementById('online-count').textContent = online;
    document.getElementById('offline-count').textContent = offline;

    if (!servers.length) {
        grid.innerHTML = `<div style="text-align:center;padding:60px;opacity:0.5;grid-column:1/-1">${t('noServers')}</div>`;
        return;
    }

    grid.innerHTML = servers.map(srv => {
        const m = srv.metrics || {};
        const isOnline = m.online;
        const cpu = m.cpu_percent || 0;
        const ram = m.ram_percent || 0;
        const disk = m.disk_percent || 0;

        const cpuClass = cpu > 90 ? 'crit' : cpu > 70 ? 'warn' : '';
        const ramClass = ram > 90 ? 'crit' : ram > 70 ? 'warn' : '';
        const diskClass = disk > 90 ? 'crit' : disk > 70 ? 'warn' : '';

        const id = srv.id || srv.host;

        return `
            <div class="server-card ${isOnline ? 'online' : 'offline'}" onclick="showServerDetail('${id}')">
                <div class="server-card-header">
                    <div>
                        <div class="name">${srv.name}</div>
                        <div class="host">${srv.host}:${srv.port || 22}</div>
                    </div>
                    <span class="status-badge ${isOnline ? 'online' : 'offline'}">
                        <span class="status-dot ${isOnline ? 'online' : 'offline'}"></span>
                        ${isOnline ? 'Online' : 'Offline'}
                    </span>
                </div>
                ${isOnline ? `
                <div class="metrics-grid">
                    <div class="metric-item">
                        <span class="label">CPU</span>
                        <span class="value ${cpuClass}">${cpu}%</span>
                        <div class="progress-bar"><div class="fill ${cpuClass || 'ok'}" style="width:${cpu}%"></div></div>
                    </div>
                    <div class="metric-item">
                        <span class="label">RAM</span>
                        <span class="value ${ramClass}">${ram}%</span>
                        <div class="progress-bar"><div class="fill ${ramClass || 'ok'}" style="width:${ram}%"></div></div>
                    </div>
                    <div class="metric-item">
                        <span class="label">Disk</span>
                        <span class="value ${diskClass}">${disk}%</span>
                        <div class="progress-bar"><div class="fill ${diskClass || 'ok'}" style="width:${disk}%"></div></div>
                    </div>
                </div>
                ` : `<div style="padding:20px 0;text-align:center;opacity:0.5">${t('noData')}</div>`}
                <div class="server-card-actions">
                    <button onclick="event.stopPropagation(); openSSH('${id}', '${srv.name}')">💻 SSH</button>
                    <button onclick="event.stopPropagation(); rebootServer('${id}')">🔄 Reboot</button>
                    <button class="danger" onclick="event.stopPropagation(); deleteServer('${id}')">🗑</button>
                </div>
            </div>
        `;
    }).join('');
}

function showServerDetail(id) {
    const srv = servers.find(s => (s.id || s.host) === id);
    if (!srv) return;

    const m = srv.metrics || {};
    const modal = document.getElementById('serverDetailModal');
    document.getElementById('detail-title').textContent = srv.name;

    document.getElementById('detail-content').innerHTML = `
        <div style="display:grid;gap:12px">
            <div class="form-group">
                <label>Host</label>
                <div style="padding:8px;background:var(--input-bg);border-radius:6px;font-family:monospace">${srv.host}:${srv.port || 22}</div>
            </div>
            <div class="form-group">
                <label>${t('status')}</label>
                <div><span class="status-badge ${m.online ? 'online' : 'offline'}">
                    <span class="status-dot ${m.online ? 'online' : 'offline'}"></span>
                    ${m.online ? 'Online' : 'Offline'}
                </span></div>
            </div>
            ${m.online ? `
            <div class="form-group">
                <label>${t('uptime')}</label>
                <div style="padding:8px;background:var(--input-bg);border-radius:6px">${m.uptime || 'N/A'}</div>
            </div>
            <div class="form-group">
                <label>${t('load')}</label>
                <div style="padding:8px;background:var(--input-bg);border-radius:6px">${m.load_average || 'N/A'}</div>
            </div>
            <div class="form-group">
                <label>RAM</label>
                <div style="padding:8px;background:var(--input-bg);border-radius:6px">${(m.ram_used_mb||0).toFixed(0)} / ${(m.ram_total_mb||0).toFixed(0)} MB (${m.ram_percent||0}%)</div>
            </div>
            <div class="form-group">
                <label>Disk</label>
                <div style="padding:8px;background:var(--input-bg);border-radius:6px">${(m.disk_used_gb||0).toFixed(1)} / ${(m.disk_total_gb||0).toFixed(1)} GB (${m.disk_percent||0}%)</div>
            </div>
            <div class="form-group">
                <label>${t('network')}</label>
                <div style="padding:8px;background:var(--input-bg);border-radius:6px">↓ ${(m.network_in_mb||0).toFixed(0)} MB / ↑ ${(m.network_out_mb||0).toFixed(0)} MB</div>
            </div>
            ` : ''}
            ${srv.description ? `
            <div class="form-group">
                <label>${t('description')}</label>
                <div style="padding:8px;background:var(--input-bg);border-radius:6px">${srv.description}</div>
            </div>
            ` : ''}
        </div>
    `;

    modal.style.display = 'flex';
}

// Instructions
function showInstructions() {
    const content = document.getElementById('instructions-content');
    content.innerHTML = `
        <div class="instructions-section">
            <div class="instr-card">
                <h4>📥 ${t('instr_install')}</h4>
                <p>${t('instr_add_server_text').includes('Click') ? 'One command to install on any Ubuntu/Debian server:' : 'Одна команда для установки на Ubuntu/Debian:'}</p>
                <code>${t('instr_install_text')}</code>
            </div>
            <div class="instr-card">
                <h4>➕ ${t('instr_add_server')}</h4>
                <p>${t('instr_add_server_text')}</p>
            </div>
            <div class="instr-card">
                <h4>💻 ${t('instr_ssh')}</h4>
                <p>${t('instr_ssh_text')}</p>
            </div>
            <div class="instr-card">
                <h4>🤖 ${t('instr_telegram')}</h4>
                <p>${t('instr_telegram_text')}</p>
            </div>
            <div class="instr-card">
                <h4>🔄 ${t('instr_reboot')}</h4>
                <p>${t('instr_reboot_text')}</p>
            </div>
            <div class="instr-card">
                <h4>⚠️ ${t('instr_thresholds')}</h4>
                <p>${t('instr_thresholds_text')}</p>
            </div>
            <div class="instr-card">
                <h4>🔧 ${t('instr_commands')}</h4>
                <ul class="cmd-list">
                    <li>📊 ${t('instr_cmd_status')}</li>
                    <li>🔄 ${t('instr_cmd_restart')}</li>
                    <li>📋 ${t('instr_cmd_logs')}</li>
                    <li>⬆️ ${t('instr_cmd_update')}</li>
                </ul>
            </div>
            <div class="instr-card">
                <h4>🔌 ${t('instr_api')}</h4>
                <ul class="cmd-list">
                    <li>GET  /api/servers — list all</li>
                    <li>POST /api/servers — add server</li>
                    <li>DELETE /api/servers/{id} — remove</li>
                    <li>POST /api/servers/{id}/reboot — reboot</li>
                    <li>POST /api/servers/{id}/exec — run command</li>
                    <li>GET  /api/settings — get settings</li>
                    <li>PUT  /api/settings — update settings</li>
                    <li>WS   /ws/ssh/{id} — SSH terminal</li>
                </ul>
            </div>
        </div>
    `;
    document.getElementById('instructionsModal').style.display = 'flex';
}

// SSH Terminal
function openSSH(id, name) {
    const modal = document.getElementById('sshModal');
    document.getElementById('ssh-title').textContent = `${t('sshTerminal')} — ${name}`;
    modal.style.display = 'flex';

    const container = document.getElementById('terminal-container');
    container.innerHTML = '';

    if (typeof Terminal === 'undefined') {
        container.innerHTML = '<div style="padding:20px;color:var(--danger)">xterm.js not loaded</div>';
        return;
    }

    const term = new Terminal({
        cursorBlink: true,
        theme: {
            background: '#000000',
            foreground: '#e8e8ff',
            cursor: '#6366f1',
        },
        fontSize: 14,
        fontFamily: 'Menlo, Monaco, "Courier New", monospace',
    });

    term.open(container);
    currentTerminal = term;

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${location.host}/ws/ssh/${id}`);
    currentWs = ws;

    ws.onopen = () => {
        term.write('\r\n\x1b[32mConnecting...\x1b[0m\r\n');
    };

    ws.onmessage = (event) => {
        term.write(event.data);
    };

    ws.onerror = () => {
        term.write('\r\n\x1b[31mConnection error\x1b[0m\r\n');
    };

    ws.onclose = () => {
        term.write('\r\n\x1b[33mConnection closed\x1b[0m\r\n');
    };

    term.onData(data => {
        if (ws.readyState === WebSocket.OPEN) {
            ws.send(data);
        }
    });
}

function closeSSH() {
    if (currentWs) {
        currentWs.close();
        currentWs = null;
    }
    if (currentTerminal) {
        currentTerminal.dispose();
        currentTerminal = null;
    }
    closeModal('sshModal');
}

// Server actions
async function rebootServer(id) {
    if (!confirm(t('rebootConfirm'))) return;
    try {
        await fetch(`/api/servers/${id}/reboot`, {method: 'POST', credentials: 'include'});
        alert(t('rebootSent'));
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function deleteServer(id) {
    if (!confirm(t('deleteConfirm'))) return;
    try {
        await fetch(`/api/servers/${id}`, {method: 'DELETE', credentials: 'include'});
        loadServers();
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

// Add server
function showAddServer() {
    document.getElementById('addServerModal').style.display = 'flex';
}

document.getElementById('addServerForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const data = {
        name: form.name.value,
        host: form.host.value,
        port: parseInt(form.port.value) || 22,
        username: form.username.value || 'root',
        password: form.password.value,
        description: form.description.value,
    };

    try {
        const resp = await fetch('/api/servers', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify(data),
        });
        if (resp.ok) {
            closeModal('addServerModal');
            form.reset();
            loadServers();
        } else {
            const err = await resp.json();
            alert(err.detail || 'Error');
        }
    } catch (e) {
        alert('Error: ' + e.message);
    }
});

// Settings
async function showSettings() {
    try {
        const resp = await fetch('/api/settings', {credentials: 'include'});
        const settings = await resp.json();

        document.getElementById('set_login').value = settings.admin_login || '';
        document.getElementById('set_tg_token').value = settings.telegram_bot_token || '';
        document.getElementById('set_tg_chat').value = settings.telegram_chat_id || '';
        document.getElementById('set_interval').value = settings.monitor_interval || 60;
        document.getElementById('set_cpu').value = settings.alert_cpu_threshold || 90;
        document.getElementById('set_ram').value = settings.alert_ram_threshold || 90;
        document.getElementById('set_disk').value = settings.alert_disk_threshold || 90;
    } catch (e) {}

    document.getElementById('settingsModal').style.display = 'flex';
}

document.getElementById('settingsForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const data = {};

    if (form.admin_login.value) data.admin_login = form.admin_login.value;
    if (form.admin_password.value) data.admin_password = form.admin_password.value;
    if (form.telegram_bot_token.value) data.telegram_bot_token = form.telegram_bot_token.value;
    if (form.telegram_chat_id.value) data.telegram_chat_id = form.telegram_chat_id.value;
    if (form.monitor_interval.value) data.monitor_interval = parseInt(form.monitor_interval.value);
    if (form.alert_cpu_threshold.value) data.alert_cpu_threshold = parseInt(form.alert_cpu_threshold.value);
    if (form.alert_ram_threshold.value) data.alert_ram_threshold = parseInt(form.alert_ram_threshold.value);
    if (form.alert_disk_threshold.value) data.alert_disk_threshold = parseInt(form.alert_disk_threshold.value);

    try {
        await fetch('/api/settings', {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify(data),
        });
        closeModal('settingsModal');
        alert(t('settingsSaved'));
    } catch (e) {
        alert('Error: ' + e.message);
    }
});

// Utils
function closeModal(id) {
    document.getElementById(id).style.display = 'none';
}

function refreshAll() {
    loadServers();
}

async function logout() {
    await fetch('/api/logout', {method: 'POST', credentials: 'include'});
    window.location.href = '/login';
}

// Click outside modal to close
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal')) {
        if (e.target.id === 'sshModal') {
            closeSSH();
        } else {
            e.target.style.display = 'none';
        }
    }
});

// Initial load
document.addEventListener('DOMContentLoaded', () => {
    applyTheme(currentTheme);
    renderPage();
    loadServers();
});

setInterval(loadServers, 30000);
