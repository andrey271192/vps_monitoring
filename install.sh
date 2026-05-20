#!/bin/bash
set -e

# VPS Monitoring — One-command installer
# Usage: curl -sSL https://raw.githubusercontent.com/andrey271192/vps_monitoring/main/install.sh | bash
# Custom port: curl -sSL ... | bash -s -- --port 9090

echo "================================================"
echo "  🖥  VPS Monitoring — Установка"
echo "================================================"
echo ""

APP_DIR="/opt/vps-monitoring"
REPO_URL="https://github.com/andrey271192/vps_monitoring.git"
SERVICE_NAME="vps-monitoring"
PORT=7272

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --port|-p)
            PORT="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

echo "🔌 Порт: $PORT"
echo ""

# Check root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Запустите от root: sudo bash install.sh"
    exit 1
fi

echo "📦 Обновление системы..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git curl > /dev/null 2>&1

# Clone or update repo
if [ -d "$APP_DIR" ]; then
    echo "📂 Обновление существующей установки..."
    cd "$APP_DIR"
    git pull --ff-only || true
else
    echo "📥 Клонирование репозитория..."
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# Python virtual environment
echo "🐍 Настройка Python окружения..."
python3 -m venv venv
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Create data directory
mkdir -p data

# Setup environment variables
if [ ! -f .env ]; then
    echo "⚙️  Создание конфигурации..."
    cat > .env << ENVEOF
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}
TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID:-}
PORT=${PORT}
ENVEOF
fi

# Install systemd service with custom port
echo "🔧 Установка systemd сервиса (порт $PORT)..."
sed "s/--port 7272/--port $PORT/" systemd/vps-monitoring.service > /etc/systemd/system/vps-monitoring.service
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl restart $SERVICE_NAME

# Firewall
if command -v ufw &> /dev/null; then
    ufw allow ${PORT}/tcp > /dev/null 2>&1 || true
fi

# Get server IP
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')

echo ""
echo "================================================"
echo "  ✅ Установка завершена!"
echo "================================================"
echo ""
echo "  🌐 Панель:     http://${SERVER_IP}:${PORT}"
echo "  👤 Логин:      admin"
echo "  🔑 Пароль:     admin"
echo ""
echo "  📱 Telegram бот активен"
echo "  🔄 Авто-обновление: systemctl restart $SERVICE_NAME"
echo ""
echo "  📋 Команды управления:"
echo "     systemctl status $SERVICE_NAME"
echo "     systemctl restart $SERVICE_NAME"
echo "     journalctl -u $SERVICE_NAME -f"
echo ""
echo "  💡 Кастомный порт при установке:"
echo "     curl -sSL <URL> | bash -s -- --port 9090"
echo ""
echo "  ⚠️  Смените пароль в настройках панели!"
echo "================================================"
