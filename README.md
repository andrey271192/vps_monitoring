# VPS Monitoring

Платформа мониторинга VPS, Keenetic-роутеров, Synology, Home Assistant и Windows PC с веб-панелью, SSH-терминалом и Telegram-ботом.

## Возможности

- **VPS** — CPU, RAM, Disk, Network, Uptime, Load Average, SSH-терминал
- **Keenetic** — мониторинг роутеров через KeenDNS/RCI API, VPN-туннели, AnyDesk-ссылки
- **Synology / HA / PC** — дополнительные вкладки мониторинга
- **Telegram** — бот, Mini App, алерты (offline, CPU/RAM, VPN down 5+ мин)
- **KeenDNS edit** — изменение web URL прямо из карточки роутера

## Установка

```bash
curl -sSL https://raw.githubusercontent.com/andrey271192/vps_monitoring/main/install.sh | bash
```

Кастомный порт:
```bash
curl -sSL https://raw.githubusercontent.com/andrey271192/vps_monitoring/main/install.sh | bash -s -- --port 9090
```

### Требования

- Ubuntu 20.04+ / Debian 11+
- Python 3.10+
- 512 MB RAM минимум

### Ручная установка

```bash
git clone https://github.com/andrey271192/vps_monitoring.git /opt/vps-monitoring
cd /opt/vps-monitoring
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # заполните TELEGRAM_*
mkdir -p data
```

Systemd unit (`/etc/systemd/system/vps-monitoring.service`):

- `WorkingDirectory=/opt/vps-monitoring`
- `ExecStart=/opt/vps-monitoring/venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 7272`

```bash
systemctl daemon-reload && systemctl enable --now vps-monitoring
```

## После установки

- **Панель:** `http://YOUR_IP:7272`
- **Логин:** `admin` / `admin` (смените в настройках)
- **Health:** `GET /api/health`

## Переменные окружения

| Переменная | Описание |
|-----------|----------|
| `TELEGRAM_BOT_TOKEN` | Токен Telegram-бота |
| `TELEGRAM_CHAT_ID` | ID чата для алертов |

Задаются в systemd unit (`Environment=...`) или в `data/settings.json`. См. `.env.example`.

Дополнительные настройки в `data/settings.json`: пороги CPU/RAM/Disk, `keenetic_interval`, `muted_devices`.

## Keenetic — импорт роутеров

### Формат import (TSV/CSV)

Колонки: `Address`, `Keenetic`, `AnyDesk` (заголовок опционален).

```
Address	Keenetic	AnyDesk
Москва Сити	https://moscowcity.netcraze.pro:5443	
Лофт	https://loftliliana.netcraze.pro	1020687391
Подмосковный	http://95.165.93.46:777	1527495291
```

`POST /api/keenetic/import` — body: `{"login":"admin","password":"...","tsv":"..."}`.

### Скрипт синхронизации (24 роутера)

```bash
./venv/bin/python3 scripts/sync_keenetic_import.py /opt/vps-monitoring/data/keenetic.json
```

### HTTP/HTTPS и порты

- URL сохраняется как есть: `https://host:5443`, `http://91.77.164.164`
- Схема по умолчанию — `https` для KeenDNS, `http` для IP
- Порт входит в `host` и `web_url` (например `malahovka1.netcraze.pro:5083`)
- Кнопка **Веб** на карточке использует точный `web_url`

### KeenDNS edit (dashboard)

1. Карточка роутера → **✏️ KeenDNS**
2. Введите URL (`https://example.netcraze.pro:8443`)
3. **Сохранить** → `PATCH /api/keenetic/{name}` обновляет `keenetic.json` и делает refresh

### Проверка доступности с VPS

```bash
cd /opt/vps-monitoring
./venv/bin/python3 scripts/quick_auth_check.py   # быстрая auth-проверка
./venv/bin/python3 scripts/check_keenetic.py     # полная (медленнее)
```

## Telegram алерты

Настройка: `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` в systemd или settings.

Keenetic алерты:
- Router offline 5+ мин (sustained + re-verify) / back online
- No internet
- CPU/RAM > 90%
- **VPN down 5+ минут** (sustained, deduplicated)

Per-device mute: 🔔/🔕 на карточке → `POST /api/notifications/mute-device`.

Тест: `POST /api/notifications/test/telegram`.

## API (основное)

| Endpoint | Method | Описание |
|----------|--------|----------|
| `/api/login` | POST | Авторизация |
| `/api/keenetic/list` | GET | Список роутеров |
| `/api/keenetic/import` | POST | Импорт TSV/CSV |
| `/api/keenetic/{name}` | PATCH | Обновить web_url |
| `/api/keenetic/refresh/{name}` | POST | Обновить один |
| `/api/keenetic/refresh-all` | POST | Обновить все |
| `/api/servers` | GET | VPS серверы |
| `/api/health` | GET | Health check |

## Troubleshooting

| Симптом | Причина | Действие |
|---------|---------|----------|
| `ConnectionTimeoutError` | VPS не достучался до роутера (сеть/VPN/firewall) | Проверить KeenDNS, порт, доступность с VPS: `curl -m 10 URL` |
| `Authentication failed` / 401 | Неверный login/password | Проверить credentials в keenetic.json |
| `Name or service not known` | DNS не резолвится | Проверить KeenDNS имя, TTL |
| Панель не отвечает | Сервис упал / перегрузка polling | `systemctl restart vps-monitoring`, `journalctl -u vps-monitoring -n 50` |
| Медленный refresh-all | 24 роутера × 3 retry × timeout | Использовать `quick_auth_check.py`, увеличить `keenetic_interval` |

```bash
systemctl status vps-monitoring
journalctl -u vps-monitoring --since "1 hour ago" -p err
ss -tlnp | grep 7272
```

## Обновление

```bash
cd /opt/vps-monitoring && git pull && systemctl restart vps-monitoring
```

## Автор

**@PCAdministration** — [GitHub](https://github.com/andrey271192) · [Telegram](https://t.me/PCAdministration)

MIT
