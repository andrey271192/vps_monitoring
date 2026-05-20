# 🖥 VPS Monitoring

Платформа мониторинга VPS серверов с веб-интерфейсом, SSH терминалом и Telegram ботом.

## Возможности

- **Мониторинг** — CPU, RAM, Disk, Network, Uptime, Load Average
- **SSH терминал** — подключение к серверам прямо из браузера
- **Telegram бот** — статус, алерты, управление (перезагрузка)
- **Telegram Mini App** — мобильная панель прямо в Telegram
- **Алерты** — уведомления при превышении порогов (CPU/RAM/Disk)
- **Управление** — добавление/удаление серверов, перезагрузка
- **Авторизация** — защита паролем с возможностью смены

## Установка (одна команда)

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

## После установки

- **Панель:** `http://YOUR_IP:7272`
- **Логин:** `admin` / `admin`
- **Telegram:** бот запускается автоматически

## Управление

```bash
# Статус
systemctl status vps-monitoring

# Перезапуск
systemctl restart vps-monitoring

# Логи
journalctl -u vps-monitoring -f

# Обновление
cd /opt/vps-monitoring && git pull && systemctl restart vps-monitoring
```

## Telegram бот

Команды:
- `/start` — главное меню
- Кнопки: статус серверов, управление, перезагрузка
- Mini App: полная панель в Telegram

## API

| Endpoint | Method | Описание |
|----------|--------|----------|
| `/api/servers` | GET | Список серверов |
| `/api/servers` | POST | Добавить сервер |
| `/api/servers/{id}` | DELETE | Удалить сервер |
| `/api/servers/{id}/reboot` | POST | Перезагрузить |
| `/api/servers/{id}/exec` | POST | Выполнить команду |
| `/api/settings` | GET/PUT | Настройки |
| `/api/health` | GET | Health check |
| `/ws/ssh/{id}` | WS | SSH терминал |

## Архитектура

```
FastAPI (Python) → SSH (asyncssh) → Target Servers
     ↕                    ↕
  Web UI (HTML/JS)    Telegram Bot
     ↕
  xterm.js (SSH in browser)
```

## Переменные окружения

| Переменная | Описание |
|-----------|----------|
| `TELEGRAM_BOT_TOKEN` | Токен Telegram бота |
| `TELEGRAM_CHAT_ID` | ID чата для алертов |

## Автор

**@Iot_andrey**

- [GitHub](https://github.com/andrey271192)
- [Boosty](https://boosty.to/iot_andrey)
- [Поддержка](https://t.me/Iot_andrey)
- Telegram: [@Iot_andrey](https://t.me/Iot_andrey)

## Лицензия

MIT
