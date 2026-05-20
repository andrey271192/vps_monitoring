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
                    <li>GET  /api/synology/list — Synology NAS</li>
                    <li>GET  /api/ha/list — Home Assistant</li>
                    <li>GET  /api/pc/list — PC agents</li>
                    <li>GET  /api/notifications/settings</li>
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
        theme: { background: '#000000', foreground: '#e8e8ff', cursor: '#6366f1' },
        fontSize: 14,
        fontFamily: 'Menlo, Monaco, "Courier New", monospace',
    });

    term.open(container);

    if (typeof FitAddon !== 'undefined') {
        const fitAddon = new FitAddon.FitAddon();
        term.loadAddon(fitAddon);
        setTimeout(() => fitAddon.fit(), 100);
        window.addEventListener('resize', () => fitAddon.fit());
    }

    currentTerminal = term;

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${location.host}/ws/ssh/${id}`);
    currentWs = ws;

    ws.onopen = () => term.write('\r\n\x1b[32mConnecting...\x1b[0m\r\n');
    ws.onmessage = (event) => term.write(event.data);
    ws.onerror = () => term.write('\r\n\x1b[31mConnection error\x1b[0m\r\n');
    ws.onclose = () => term.write('\r\n\x1b[33mConnection closed\x1b[0m\r\n');
    term.onData(data => { if (ws.readyState === WebSocket.OPEN) ws.send(data); });
}

function closeSSH() {
    if (currentWs) { currentWs.close(); currentWs = null; }
    if (currentTerminal) { currentTerminal.dispose(); currentTerminal = null; }
    closeModal('sshModal');
}

// Server actions
async function rebootServer(id) {
    if (!confirm(t('rebootConfirm'))) return;
    try {
        await fetch(`/api/servers/${id}/reboot`, {method: 'POST', credentials: 'include'});
        alert(t('rebootSent'));
    } catch (e) { alert('Error: ' + e.message); }
}

async function deleteServer(id) {
    if (!confirm(t('deleteConfirm'))) return;
    try {
        await fetch(`/api/servers/${id}`, {method: 'DELETE', credentials: 'include'});
        loadServers();
    } catch (e) { alert('Error: ' + e.message); }
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
    } catch (e) { alert('Error: ' + e.message); }
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
    } catch (e) { alert('Error: ' + e.message); }
});

// Utils
function closeModal(id) {
    document.getElementById(id).style.display = 'none';
}

function refreshAll() {
    if (activeTab === 'servers') loadServers();
    else if (activeTab === 'pc') loadPCs();
    else if (activeTab === 'synology') loadSynology();
    else if (activeTab === 'ha') loadHA();
}

async function logout() {
    await fetch('/api/logout', {method: 'POST', credentials: 'include'});
    window.location.href = '/login';
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        // Brief visual feedback
        const el = event.target;
        const orig = el.style.color;
        el.style.color = 'var(--accent)';
        setTimeout(() => el.style.color = orig, 500);
    });
}

// Click outside modal to close
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal')) {
        if (e.target.id === 'sshModal') closeSSH();
        else e.target.style.display = 'none';
    }
});

// ===================== TABS =====================
let activeTab = 'servers';
const allTabs = ['servers', 'pc', 'synology', 'ha'];

function switchTab(tab) {
    activeTab = tab;
    allTabs.forEach(t => {
        const tabBtn = document.getElementById('tab-' + t);
        const panel = document.getElementById('panel-' + t);
        if (tabBtn) tabBtn.classList.toggle('active', t === tab);
        if (panel) panel.style.display = t === tab ? '' : 'none';
    });

    if (tab === 'pc') loadPCs();
    else if (tab === 'synology') loadSynology();
    else if (tab === 'ha') loadHA();
}

// ===================== PC MONITORING =====================
let pcAgents = [];

async function loadPCs() {
    try {
        const resp = await fetch('/api/pc/list', {credentials: 'include'});
        if (resp.status === 401) return;
        pcAgents = await resp.json();
        renderPCs();
    } catch (e) { console.error('PC load error:', e); }
}

function renderPCs() {
    const grid = document.getElementById('pc-grid');

    if (!pcAgents.length) {
        grid.innerHTML = '<div style="text-align:center;padding:60px;opacity:0.5;grid-column:1/-1">Нет подключённых ПК. Нажмите "📥 Скачать агент".</div>';
        return;
    }

    grid.innerHTML = pcAgents.map(pc => {
        const m = pc.metrics || {};
        const isOnline = pc.online;
        const cpu = m.cpu_percent || 0;
        const ram = m.ram_percent || 0;
        const disk = m.disk_percent || 0;

        const cpuClass = cpu > 90 ? 'crit' : cpu > 70 ? 'warn' : '';
        const ramClass = ram > 90 ? 'crit' : ram > 70 ? 'warn' : '';
        const diskClass = disk > 90 ? 'crit' : disk > 70 ? 'warn' : '';

        const disksHtml = (m.disks || []).map(d =>
            `<div style="font-size:11px;color:var(--text-secondary);margin-top:2px">${d.drive} ${d.used_gb}/${d.total_gb} GB (${d.percent}%)</div>`
        ).join('');

        const procsHtml = (m.top_processes || []).slice(0, 3).map(p =>
            `<span style="font-size:10px;padding:2px 6px;background:var(--bg-primary);border-radius:4px;margin:1px">${p.name} ${p.ram_mb}MB</span>`
        ).join(' ');

        return `
            <div class="server-card ${isOnline ? 'online' : 'offline'}">
                <div class="server-card-header">
                    <div>
                        <div class="name">💻 ${pc.agent_name}</div>
                        <div class="host">${m.hostname || ''} • ${pc.ip || ''}</div>
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
                <div style="font-size:12px;color:var(--text-secondary);margin-bottom:8px">
                    ${m.uptime || ''} ${m.os ? '• ' + m.os.substring(0, 30) : ''}
                </div>
                ${m.gpu_name ? `<div style="font-size:11px;color:var(--text-secondary)">GPU: ${m.gpu_name}</div>` : ''}
                ${disksHtml}
                ${procsHtml ? `<div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:2px">${procsHtml}</div>` : ''}
                ` : '<div style="padding:20px 0;text-align:center;opacity:0.5">Нет данных</div>'}
                <div class="server-card-actions">
                    <button class="danger" onclick="deletePC('${pc.agent_name}')">🗑 Удалить</button>
                </div>
            </div>
        `;
    }).join('');
}

async function deletePC(name) {
    if (!confirm(`Удалить ПК "${name}" из мониторинга?`)) return;
    await fetch(`/api/pc/${encodeURIComponent(name)}`, {method: 'DELETE', credentials: 'include'});
    loadPCs();
}

function showPCSetup() {
    document.getElementById('pcSetupModal').style.display = 'flex';
}

function showPCDownload() {
    document.getElementById('pc-agent-name').value = '';
    document.getElementById('pc-generated-cmd').style.display = 'none';
    document.getElementById('pcDownloadModal').style.display = 'flex';
}

async function generatePCCommand() {
    const name = document.getElementById('pc-agent-name').value.trim() || 'MyPC';
    try {
        const resp = await fetch('/api/notifications/generate-pc-agent', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({agent_name: name}),
        });
        const data = await resp.json();
        if (data.command) {
            document.getElementById('pc-gen-code').textContent = data.command;
            document.getElementById('pc-generated-cmd').style.display = 'block';
        }
    } catch (e) { alert('Error: ' + e.message); }
}

// ===================== SYNOLOGY =====================
let synologyDevices = [];

async function loadSynology() {
    try {
        const resp = await fetch('/api/synology/list', {credentials: 'include'});
        if (resp.status === 401) return;
        synologyDevices = await resp.json();
        renderSynology();
    } catch (e) { console.error('Synology load error:', e); }
}

function renderSynology() {
    const grid = document.getElementById('synology-grid');

    if (!synologyDevices.length) {
        grid.innerHTML = '<div style="text-align:center;padding:60px;opacity:0.5;grid-column:1/-1">Нет Synology NAS. Нажмите "+ Добавить NAS".</div>';
        return;
    }

    grid.innerHTML = synologyDevices.map(dev => {
        const m = dev.metrics || {};
        const isOnline = m.online;
        const cpu = m.cpu_percent || 0;
        const ram = m.ram_percent || 0;
        const temp = m.temperature || 0;

        const cpuClass = cpu > 90 ? 'crit' : cpu > 70 ? 'warn' : '';
        const ramClass = ram > 90 ? 'crit' : ram > 70 ? 'warn' : '';
        const tempClass = temp > 60 ? 'crit' : temp > 50 ? 'warn' : '';

        const vmsCount = (m.vms || []).length;
        const dockerCount = (m.docker || []).length;
        const volsHtml = (m.volumes || []).map(v => {
            const vc = v.percent > 90 ? 'crit' : v.percent > 70 ? 'warn' : '';
            return `<div style="font-size:11px;margin-top:4px">
                ${v.name}: ${v.used_gb}/${v.total_gb} GB
                <div class="progress-bar"><div class="fill ${vc || 'ok'}" style="width:${v.percent}%"></div></div>
            </div>`;
        }).join('');

        return `
            <div class="server-card ${isOnline ? 'online' : 'offline'}" onclick="showSynologyDetail('${dev.name}')">
                <div class="server-card-header">
                    <div>
                        <div class="name">📦 ${dev.name}</div>
                        <div class="host">${dev.host}:${dev.port || 5000} ${m.model ? '• ' + m.model : ''}</div>
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
                        <span class="label">🌡️</span>
                        <span class="value ${tempClass}">${temp}°C</span>
                    </div>
                </div>
                ${m.dsm_version ? `<div style="font-size:11px;color:var(--text-secondary);margin-bottom:4px">${m.dsm_version} • ${m.uptime || ''}</div>` : ''}
                ${vmsCount ? `<div style="font-size:11px;color:var(--accent)">🖥 ${vmsCount} VM</div>` : ''}
                ${dockerCount ? `<div style="font-size:11px;color:var(--accent)">🐳 ${dockerCount} контейнеров</div>` : ''}
                ${volsHtml}
                ` : '<div style="padding:20px 0;text-align:center;opacity:0.5">Нет данных — нажмите 🔄</div>'}
                <div class="server-card-actions">
                    <button onclick="event.stopPropagation(); refreshSynology('${dev.name}')">🔄 Обновить</button>
                    <button class="danger" onclick="event.stopPropagation(); deleteSynology('${dev.name}')">🗑</button>
                </div>
            </div>
        `;
    }).join('');
}

function showSynologyDetail(name) {
    const dev = synologyDevices.find(d => d.name === name);
    if (!dev || !dev.metrics) return;

    const m = dev.metrics;
    const modal = document.getElementById('synDetailModal');
    document.getElementById('syn-detail-title').textContent = `📦 ${name}`;

    let html = `<div style="display:grid;gap:12px">`;

    // System
    html += `<div class="instr-card"><h4>💻 Система</h4>
        <p>Модель: ${m.model || 'N/A'}<br>${m.dsm_version || ''}<br>Uptime: ${m.uptime || 'N/A'}<br>
        Температура: ${m.temperature || 0}°C<br>CPU: ${m.cpu_percent || 0}% | RAM: ${m.ram_percent || 0}% (${m.ram_used_mb || 0}/${m.ram_total_mb || 0} MB)</p></div>`;

    // Volumes
    if (m.volumes?.length) {
        html += `<div class="instr-card"><h4>💾 Тома</h4>`;
        m.volumes.forEach(v => {
            const vc = v.percent > 90 ? 'crit' : v.percent > 70 ? 'warn' : 'ok';
            html += `<div style="margin-bottom:8px"><b>${v.name}</b> — ${v.used_gb}/${v.total_gb} GB (${v.percent}%) ${v.status ? '• ' + v.status : ''}
                <div class="progress-bar"><div class="fill ${vc}" style="width:${v.percent}%"></div></div></div>`;
        });
        html += `</div>`;
    }

    // Disks
    if (m.disks?.length) {
        html += `<div class="instr-card"><h4>🔩 Диски</h4>`;
        m.disks.forEach(d => {
            html += `<div style="margin-bottom:4px">${d.name} — ${d.model || ''} (${d.size_gb} GB) 🌡${d.temp}°C ${d.smart_status ? '• SMART: ' + d.smart_status : ''} ${d.status || ''}</div>`;
        });
        html += `</div>`;
    }

    // VMs
    if (m.vms?.length) {
        html += `<div class="instr-card"><h4>🖥 Виртуальные машины</h4>`;
        m.vms.forEach(vm => {
            const st = vm.status === 'running' ? '🟢' : '🔴';
            html += `<div style="margin-bottom:4px">${st} ${vm.name} — ${vm.vcpu} vCPU, ${vm.ram_mb} MB RAM ${vm.autorun ? '• AutoStart' : ''}</div>`;
        });
        html += `</div>`;
    }

    // Docker
    if (m.docker?.length) {
        html += `<div class="instr-card"><h4>🐳 Docker контейнеры</h4>`;
        m.docker.forEach(c => {
            const st = c.state === 'running' ? '🟢' : '🔴';
            html += `<div style="margin-bottom:4px">${st} ${c.name} — ${c.image || ''}</div>`;
        });
        html += `</div>`;
    }

    html += `</div>`;
    document.getElementById('syn-detail-content').innerHTML = html;
    modal.style.display = 'flex';
}

function showAddSynology() {
    document.getElementById('addSynologyModal').style.display = 'flex';
}

document.getElementById('addSynologyForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const data = {
        name: form.name.value,
        host: form.host.value,
        port: parseInt(form.port.value) || 5000,
        https: form.querySelector('[name=https]').checked,
        username: form.username.value,
        password: form.password.value,
    };

    try {
        const resp = await fetch('/api/synology/add', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify(data),
        });
        if (resp.ok) {
            closeModal('addSynologyModal');
            form.reset();
            loadSynology();
        }
    } catch (e) { alert('Error: ' + e.message); }
});

async function refreshSynology(name) {
    try {
        await fetch(`/api/synology/refresh/${encodeURIComponent(name)}`, {method: 'POST', credentials: 'include'});
        loadSynology();
    } catch (e) { alert('Error: ' + e.message); }
}

async function refreshAllSynology() {
    try {
        await fetch('/api/synology/refresh-all', {method: 'POST', credentials: 'include'});
        loadSynology();
    } catch (e) { alert('Error: ' + e.message); }
}

async function deleteSynology(name) {
    if (!confirm(`Удалить Synology "${name}"?`)) return;
    await fetch(`/api/synology/${encodeURIComponent(name)}`, {method: 'DELETE', credentials: 'include'});
    loadSynology();
}

// ===================== HOME ASSISTANT =====================
let haInstances = [];

async function loadHA() {
    try {
        const resp = await fetch('/api/ha/list', {credentials: 'include'});
        if (resp.status === 401) return;
        haInstances = await resp.json();
        renderHA();
    } catch (e) { console.error('HA load error:', e); }
}

function renderHA() {
    const grid = document.getElementById('ha-grid');

    if (!haInstances.length) {
        grid.innerHTML = '<div style="text-align:center;padding:60px;opacity:0.5;grid-column:1/-1">Нет Home Assistant. Нажмите "+ Добавить HA".</div>';
        return;
    }

    grid.innerHTML = haInstances.map(inst => {
        const m = inst.metrics || {};
        const isOnline = m.online;
        const temps = (m.sensors?.temperature || []).filter(s => s.value !== null).slice(0, 4);
        const humidity = (m.sensors?.humidity || []).filter(s => s.value !== null).slice(0, 4);
        const doors = m.sensors?.door || [];
        const motion = m.sensors?.motion || [];
        const battery = (m.sensors?.battery || []).filter(s => s.value !== null && s.value < 20);
        const problems = (m.problem_entities || []).length;
        const updates = (m.updates_available || []).length;
        const persons = m.persons || [];

        return `
            <div class="server-card ${isOnline ? 'online' : 'offline'}" onclick="showHADetail('${inst.name}')">
                <div class="server-card-header">
                    <div>
                        <div class="name">🏠 ${inst.name}</div>
                        <div class="host">${m.location_name || inst.url || ''} ${m.version ? '• v' + m.version : ''}</div>
                    </div>
                    <span class="status-badge ${isOnline ? 'online' : 'offline'}">
                        <span class="status-dot ${isOnline ? 'online' : 'offline'}"></span>
                        ${isOnline ? 'Online' : 'Offline'}
                    </span>
                </div>
                ${isOnline ? `
                <div class="ha-summary">
                    <div class="ha-stat">📡 ${m.entities_count || 0} сущностей</div>
                    ${persons.length ? `<div class="ha-stat">👤 ${persons.map(p => `${p.name}: ${p.state === 'home' ? '🏠' : '🚗'}`).join(', ')}</div>` : ''}
                    ${temps.length ? `<div class="ha-stat">🌡 ${temps.map(s => s.name.substring(0, 15) + ': ' + s.value + s.unit).join(' | ')}</div>` : ''}
                    ${humidity.length ? `<div class="ha-stat">💧 ${humidity.map(s => s.name.substring(0, 15) + ': ' + s.value + '%').join(' | ')}</div>` : ''}
                    ${doors.length ? `<div class="ha-stat">🚪 ${doors.filter(d => d.state === 'on').length ? '<span style="color:var(--warning)">' + doors.filter(d => d.state === 'on').length + ' открыто</span>' : 'все закрыты ✅'}</div>` : ''}
                    ${motion.length ? `<div class="ha-stat">🏃 ${motion.filter(m => m.state === 'on').length ? '<span style="color:var(--warning)">движение!</span>' : 'нет движения'}</div>` : ''}
                    ${battery.length ? `<div class="ha-stat" style="color:var(--danger)">🔋 ${battery.length} устройств с низким зарядом</div>` : ''}
                    ${problems ? `<div class="ha-stat" style="color:var(--danger)">⚠️ ${problems} проблемных сущностей</div>` : ''}
                    ${updates ? `<div class="ha-stat" style="color:var(--warning)">📦 ${updates} обновлений</div>` : ''}
                </div>
                ` : '<div style="padding:20px 0;text-align:center;opacity:0.5">Нет данных — нажмите 🔄</div>'}
                <div class="server-card-actions">
                    <button onclick="event.stopPropagation(); refreshHA('${inst.name}')">🔄 Обновить</button>
                    <button class="danger" onclick="event.stopPropagation(); deleteHA('${inst.name}')">🗑</button>
                </div>
            </div>
        `;
    }).join('');
}

function showHADetail(name) {
    const inst = haInstances.find(i => i.name === name);
    if (!inst || !inst.metrics) return;

    const m = inst.metrics;
    const modal = document.getElementById('haDetailModal');
    document.getElementById('ha-detail-title').textContent = `🏠 ${name}`;

    let html = `<div style="display:grid;gap:12px">`;

    // System
    html += `<div class="instr-card"><h4>🔧 Система</h4>
        <p>Версия: ${m.version || 'N/A'}<br>Локация: ${m.location_name || 'N/A'}<br>
        Компоненты: ${m.components_count || 0}<br>Сущности: ${m.entities_count || 0}</p></div>`;

    // Temperatures
    const temps = m.sensors?.temperature || [];
    if (temps.length) {
        html += `<div class="instr-card"><h4>🌡️ Температура</h4>`;
        temps.forEach(s => {
            if (s.value === null) return;
            const cls = s.value > 30 ? 'style="color:var(--danger)"' : s.value < 10 ? 'style="color:var(--accent)"' : '';
            html += `<div ${cls}>${s.name}: <b>${s.value}${s.unit}</b></div>`;
        });
        html += `</div>`;
    }

    // Humidity
    const humid = m.sensors?.humidity || [];
    if (humid.length) {
        html += `<div class="instr-card"><h4>💧 Влажность</h4>`;
        humid.forEach(s => { if (s.value !== null) html += `<div>${s.name}: <b>${s.value}%</b></div>`; });
        html += `</div>`;
    }

    // Doors/Windows
    const doors = m.sensors?.door || [];
    if (doors.length) {
        html += `<div class="instr-card"><h4>🚪 Двери / Окна</h4>`;
        doors.forEach(d => {
            const icon = d.state === 'on' ? '🔓 Открыто' : '🔒 Закрыто';
            const cls = d.state === 'on' ? 'style="color:var(--warning)"' : '';
            html += `<div ${cls}>${d.name}: ${icon}</div>`;
        });
        html += `</div>`;
    }

    // Motion
    const motion = m.sensors?.motion || [];
    if (motion.length) {
        html += `<div class="instr-card"><h4>🏃 Движение</h4>`;
        motion.forEach(s => {
            const cls = s.state === 'on' ? 'style="color:var(--warning)"' : '';
            html += `<div ${cls}>${s.name}: ${s.state === 'on' ? '⚡ Обнаружено' : '—'}</div>`;
        });
        html += `</div>`;
    }

    // Battery
    const battery = m.sensors?.battery || [];
    if (battery.length) {
        html += `<div class="instr-card"><h4>🔋 Батареи</h4>`;
        battery.forEach(b => {
            if (b.value === null) return;
            const cls = b.value < 20 ? 'crit' : b.value < 50 ? 'warn' : '';
            html += `<div><span class="value ${cls}">${b.value}%</span> ${b.name}</div>`;
        });
        html += `</div>`;
    }

    // Climate
    if (m.climate?.length) {
        html += `<div class="instr-card"><h4>🌡 Климат</h4>`;
        m.climate.forEach(c => {
            html += `<div>${c.name}: ${c.state} (${c.current_temp || '?'}° → ${c.target_temp || '?'}°) ${c.hvac_action}</div>`;
        });
        html += `</div>`;
    }

    // Persons
    if (m.persons?.length) {
        html += `<div class="instr-card"><h4>👤 Люди</h4>`;
        m.persons.forEach(p => {
            const icon = p.state === 'home' ? '🏠 Дома' : '🚗 Не дома';
            html += `<div>${p.name}: ${icon}</div>`;
        });
        html += `</div>`;
    }

    // Automations
    if (m.automations?.length) {
        html += `<div class="instr-card"><h4>⚙️ Автоматизации (${m.automations.length})</h4>`;
        m.automations.slice(0, 20).forEach(a => {
            const st = a.state === 'on' ? '🟢' : '🔴';
            html += `<div style="font-size:12px">${st} ${a.name}</div>`;
        });
        html += `</div>`;
    }

    // Updates
    if (m.updates_available?.length) {
        html += `<div class="instr-card"><h4>📦 Доступные обновления</h4>`;
        m.updates_available.forEach(u => {
            html += `<div>${u.name}: ${u.installed} → ${u.latest}</div>`;
        });
        html += `</div>`;
    }

    // Problems
    if (m.problem_entities?.length) {
        html += `<div class="instr-card"><h4>⚠️ Проблемные сущности</h4>`;
        m.problem_entities.slice(0, 20).forEach(p => {
            html += `<div style="font-size:12px;color:var(--danger)">${p.entity_id}: ${p.state}</div>`;
        });
        html += `</div>`;
    }

    html += `</div>`;
    document.getElementById('ha-detail-content').innerHTML = html;
    modal.style.display = 'flex';
}

function showAddHA() {
    document.getElementById('addHAModal').style.display = 'flex';
}

document.getElementById('addHAForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const data = {
        name: form.name.value,
        url: form.url.value,
        token: form.token.value,
    };

    try {
        const resp = await fetch('/api/ha/add', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify(data),
        });
        if (resp.ok) {
            closeModal('addHAModal');
            form.reset();
            loadHA();
        }
    } catch (e) { alert('Error: ' + e.message); }
});

async function refreshHA(name) {
    try {
        await fetch(`/api/ha/refresh/${encodeURIComponent(name)}`, {method: 'POST', credentials: 'include'});
        loadHA();
    } catch (e) { alert('Error: ' + e.message); }
}

async function refreshAllHA() {
    try {
        await fetch('/api/ha/refresh-all', {method: 'POST', credentials: 'include'});
        loadHA();
    } catch (e) { alert('Error: ' + e.message); }
}

async function deleteHA(name) {
    if (!confirm(`Удалить Home Assistant "${name}"?`)) return;
    await fetch(`/api/ha/${encodeURIComponent(name)}`, {method: 'DELETE', credentials: 'include'});
    loadHA();
}

// ===================== NOTIFICATIONS =====================
async function showNotificationSettings() {
    try {
        const resp = await fetch('/api/notifications/settings', {credentials: 'include'});
        const data = await resp.json();

        const n = data.notifications || {};
        // Set checkboxes
        ['servers', 'pc', 'synology', 'ha'].forEach(cat => {
            const prefs = n[cat] || {};
            const tgEl = document.getElementById(`n-${cat}-tg`);
            const emEl = document.getElementById(`n-${cat}-email`);
            const waEl = document.getElementById(`n-${cat}-wa`);
            if (tgEl) tgEl.checked = prefs.telegram !== false;
            if (emEl) emEl.checked = !!prefs.email;
            if (waEl) waEl.checked = !!prefs.whatsapp;
        });

        // Email fields
        document.getElementById('n-smtp-host').value = data.email?.smtp_host || '';
        document.getElementById('n-smtp-port').value = data.email?.smtp_port || 587;
        document.getElementById('n-smtp-user').value = data.email?.smtp_user || '';
        document.getElementById('n-email-to').value = data.email?.email_to || '';

        // WhatsApp
        document.getElementById('n-wa-phone').value = data.whatsapp?.phone || '';

        // Status indicators
        document.getElementById('tg-status').innerHTML = data.telegram?.configured
            ? '<span style="color:var(--success)">✅ Настроен</span>'
            : '<span style="color:var(--danger)">❌ Не настроен (укажите Bot Token и Chat ID в ⚙️)</span>';

    } catch (e) { console.error(e); }

    document.getElementById('notifyModal').style.display = 'flex';
}

async function saveNotificationSettings() {
    const notifications = {};
    ['servers', 'pc', 'synology', 'ha'].forEach(cat => {
        notifications[cat] = {
            telegram: document.getElementById(`n-${cat}-tg`)?.checked || false,
            email: document.getElementById(`n-${cat}-email`)?.checked || false,
            whatsapp: document.getElementById(`n-${cat}-wa`)?.checked || false,
        };
    });

    const data = {
        notifications,
        smtp_host: document.getElementById('n-smtp-host').value,
        smtp_port: parseInt(document.getElementById('n-smtp-port').value) || 587,
        smtp_user: document.getElementById('n-smtp-user').value,
        smtp_password: document.getElementById('n-smtp-pass').value,
        email_to: document.getElementById('n-email-to').value,
        whatsapp_phone: document.getElementById('n-wa-phone').value,
        whatsapp_apikey: document.getElementById('n-wa-apikey').value,
    };

    // Don't send empty password
    if (!data.smtp_password) delete data.smtp_password;
    if (!data.whatsapp_apikey) delete data.whatsapp_apikey;

    try {
        await fetch('/api/notifications/settings', {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify(data),
        });
        closeModal('notifyModal');
        alert('Настройки уведомлений сохранены');
    } catch (e) { alert('Error: ' + e.message); }
}

async function testNotification(channel) {
    try {
        // Save first if email/whatsapp have new values
        if (channel !== 'telegram') {
            await saveNotificationSettings();
            // Re-open modal
            document.getElementById('notifyModal').style.display = 'flex';
        }

        const resp = await fetch(`/api/notifications/test/${channel}`, {
            method: 'POST', credentials: 'include'
        });
        const data = await resp.json();
        if (data.status === 'ok') {
            alert(`✅ Тестовое уведомление отправлено через ${channel}`);
        } else {
            alert(`❌ Ошибка отправки через ${channel}. Проверьте настройки.`);
        }
    } catch (e) { alert('Error: ' + e.message); }
}

// ===================== INIT =====================
document.addEventListener('DOMContentLoaded', () => {
    applyTheme(currentTheme);
    renderPage();
    loadServers();
});

setInterval(() => {
    if (activeTab === 'servers') loadServers();
    else if (activeTab === 'pc') loadPCs();
    else if (activeTab === 'synology') loadSynology();
    else if (activeTab === 'ha') loadHA();
}, 30000);
