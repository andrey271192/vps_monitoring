#!/bin/bash
# Safe deploy: preserves data/ JSON files across git pull.
# Usage: cd /opt/vps-monitoring && bash scripts/deploy.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"

DATA_BACKUP="/tmp/vps-monitoring-data-backup-$(date +%Y%m%d_%H%M%S)"
DATA_FILES=(servers.json synology.json homeassistant.json pc_agents.json keenetic.json settings.json metrics.json notifications.json)

echo "📦 Backing up data/ → $DATA_BACKUP"
mkdir -p "$DATA_BACKUP"
for f in "${DATA_FILES[@]}"; do
    [ -f "data/$f" ] && cp "data/$f" "$DATA_BACKUP/$f"
done

echo "📥 git pull"
# Never use 'git stash -u' — it removes untracked data/*.json from disk.
git pull --ff-only origin main

echo "🔄 Restore data if missing"
for f in "${DATA_FILES[@]}"; do
    if [ ! -f "data/$f" ] && [ -f "$DATA_BACKUP/$f" ]; then
        echo "  restore $f"
        cp "$DATA_BACKUP/$f" "data/$f"
    fi
done

echo "🐍 pip install"
source venv/bin/activate
pip install -q -r requirements.txt

echo "♻️  restart vps-monitoring"
systemctl restart vps-monitoring
sleep 2
systemctl is-active vps-monitoring

echo "✅ Deploy done. Data backup: $DATA_BACKUP"
