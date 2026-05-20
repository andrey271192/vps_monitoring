let currentTheme = localStorage.getItem('vps_theme') || 'dark';

function applyTheme(theme) {
    currentTheme = theme;
    localStorage.setItem('vps_theme', theme);
    document.documentElement.setAttribute('data-theme', theme);
    const btn = document.getElementById('themeToggleBtn');
    if (btn) btn.textContent = theme === 'dark' ? '☀️' : '🌙';
}

function toggleTheme() {
    applyTheme(currentTheme === 'dark' ? 'light' : 'dark');
}

// Apply on load
document.addEventListener('DOMContentLoaded', () => applyTheme(currentTheme));
