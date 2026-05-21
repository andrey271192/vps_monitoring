#!/usr/bin/env python3
"""Sync keenetic.json with canonical import list (names, web_url, anydesk)."""
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

IMPORT = [
    ("Лилиана Лофт", "https://loftliliana.netcraze.pro", "1020687391"),
    ("Артем vtb126", "https://vtb126.netcraze.club", ""),
    ("Артем Квартира Подмосковный", "http://95.165.93.46:777", "1527495291"),
    ("Артем Квартира 2", "https://pomidor.netcraze.pro:5443", ""),
    ("Артем Малаховка", "https://malahovka1.netcraze.pro:5083", ""),
    ("Арсен Квартира", "https://arsen53.netcraze.link", "1633258458"),
    ("Вишневый Сад", "https://visheviisad.netcraze.link", "135128054"),
    ("Антоновка", "https://antonovka.netcraze.pro:5083", "1356582394"),
    ("Цехомский Николай Дом", "https://peredelkino15.netcraze.link", "1726497286"),
    ("Цехомский Домик Истра", "https://utrodomik.netcraze.club:5443", "451325164"),
    ("Маршала Жукова Квартира", "https://marshalaszukova.netcraze.pro", "1677737879"),
    ("Ломакин Квартира", "https://lomakinkvartira.netcraze.pro", ""),
    ("Ломакин Дача", "https://lomakindacha.netcraze.pro:8443/", "815142240"),
    ("КАСТАНАЕВСКАЯ", "https://kastanaevskaya.netcraze.link", "1627649255"),
    ("Чиверево Меламед", "https://chiverevo.netcraze.pro", "846367657"),
    ("Рав Гедалья Меламед", "https://ravged.netcraze.pro", ""),
    ("Кургин Дом", "https://kurgin.netcraze.link", "709243112"),
    ("Таланова Дом", "https://talanovadom.netcraze.pro", "951049627"),
    ("Загорье Дом", "https://zagorie.netcraze.link", "249788953"),
]


def normalize_web_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def host_from_url(url: str) -> str:
    parsed = urlparse(normalize_web_url(url))
    return parsed.netloc or url.replace("https://", "").replace("http://", "").rstrip("/")


IMPORT_HOSTS = {host_from_url(url) for _, url, _ in IMPORT}


def make_device(name, keenetic_url, login, password, anydesk="", added=None):
    keenetic_url = normalize_web_url(keenetic_url)
    host = host_from_url(keenetic_url)
    return {
        "name": name,
        "host": host,
        "web_url": keenetic_url,
        "anydesk": (anydesk or "").strip(),
        "login": login,
        "password": password,
        "added": added or datetime.now().isoformat(),
    }


def sync_file(path: Path, default_password: str):
    with open(path) as f:
        old = json.load(f)

    by_host = {d.get("host", ""): d for d in old}
    path.with_suffix(".json.bak").write_text(
        json.dumps(old, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    result = []
    for name, url, ad in IMPORT:
        host = host_from_url(url)
        prev = by_host.get(host, {})
        login = prev.get("login", "admin")
        password = prev.get("password") or default_password
        added = prev.get("added")
        result.append(make_device(name, url, login, password, ad, added))

    for d in old:
        host = d.get("host", "")
        if host in IMPORT_HOSTS:
            continue
        if not d.get("web_url") and host:
            h = host
            d["web_url"] = normalize_web_url(
                h if h.startswith("http") else ("http://" if h[0].isdigit() else "https://") + h
            )
        result.append(d)

    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(result)} devices ({len(IMPORT)} import + {len(result) - len(IMPORT)} extra)")


if __name__ == "__main__":
    p = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/vps-monitoring/data/keenetic.json")
    pwd = sys.argv[2] if len(sys.argv) > 2 else "Ipadipad1"
    sync_file(p, pwd)
