# Nuga CS Demo — Telegram: бот и «агенты», которые сами ведут канал.
#
# Работает внутри сайта (app.py запускает start()), отдельных программ и библиотек не нужно.
# Настройки — в файле .env:
#   TELEGRAM_BOT_TOKEN=123456:ABC...     токен от @BotFather (без него всё ниже просто выключено)
#   TELEGRAM_CHANNEL=@nuga_cs_demo       канал, куда писать; бота нужно добавить в канал администратором
#   TELEGRAM_LINK=https://t.me/+xxxx     (необязательно) ссылка-приглашение, если канал закрытый
#   SITE_URL=https://ваш-сайт            (необязательно) постоянный адрес сайта — для кнопок «Смотреть»
#   TELEGRAM_DIGEST_HOUR=21              (необязательно) в котором часу публиковать «Итоги дня»
#
# Агенты (каждый — свой фоновый поток):
#   1. Отправитель  — очередь сообщений: соблюдает лимиты Telegram и повторяет при сбоях.
#   2. Публикатор   — каждый опубликованный на сайте клип сразу уходит постом в канал (с видео, если оно есть).
#   3. Итоги дня    — раз в день пишет в канал сводку: сколько матчей разобрано, игрок дня, новые клипы.
#   4. Собеседник   — отвечает людям в личке бота: /start, /clips, /help, /stop и привязка профиля сайта,
#                     после которой уведомления сайта (новый подписчик, новый клип) приходят в Telegram.

import html
import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

MAX_VIDEO = 49 * 1024 * 1024         # боты могут отправлять файлы до 50 МБ

_state: dict = {"token": None, "channel": None, "link": None, "username": None, "hooks": {}, "started": False}
_outbox: queue.Queue = queue.Queue()

esc = html.escape


def enabled() -> bool:
    """Бот подключён: есть токен, и Telegram его принял."""
    return bool(_state["username"])


def bot_username() -> str | None:
    return _state["username"]


def channel_url() -> str | None:
    """Ссылка «Наш Телеграм» для сайта: приглашение из TELEGRAM_LINK или открытый канал @имя."""
    if _state["link"]:
        return _state["link"]
    channel = _state["channel"] or os.environ.get("TELEGRAM_CHANNEL", "").strip()
    return f"https://t.me/{channel[1:]}" if channel.startswith("@") and len(channel) > 1 else None


# ---------- Запросы к Telegram ----------

def _api_base() -> str:
    return os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/")


def call(method: str, params: dict | None = None, file: tuple[str, Path] | None = None, timeout: int = 30) -> dict:
    """Один запрос к Bot API. file=("video", путь) — отправка файла. Ошибку Telegram отдаём исключением."""
    url = f"{_api_base()}/bot{_state['token']}/{method}"
    params = {k: v for k, v in (params or {}).items() if v is not None}
    if file:
        boundary = uuid.uuid4().hex
        parts = []
        for k, v in params.items():
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
        field, path = file
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"clip.mp4\"\r\n"
                     f"Content-Type: video/mp4\r\n\r\n".encode() + path.read_bytes() + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        req = urllib.request.Request(url, data=b"".join(parts),
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        timeout = 300
    else:
        req = urllib.request.Request(url, data=json.dumps(params).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            data = json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read().decode("utf-8"))
        except ValueError:
            data = {"ok": False, "description": f"HTTP {e.code}", "error_code": e.code}
    if not data.get("ok"):
        raise TelegramError(data.get("description", "ошибка Telegram"), data.get("error_code"),
                            (data.get("parameters") or {}).get("retry_after"))
    return data.get("result")


class TelegramError(Exception):
    def __init__(self, text: str, code: int | None = None, retry_after: int | None = None):
        super().__init__(text)
        self.code, self.retry_after = code, retry_after


def _button(text: str, url: str | None) -> str | None:
    """Кнопка-ссылка под сообщением. Telegram принимает только настоящие адреса (не localhost)."""
    if not url or not url.startswith("https://"):
        return None
    return json.dumps({"inline_keyboard": [[{"text": text, "url": url}]]}, ensure_ascii=False)


# ---------- Что можно попросить отправить (вызывает сайт) ----------

def send_message(chat_id, text: str, url: str | None = None, button: str = "Открыть на сайте") -> None:
    """Сообщение человеку или в канал — кладём в очередь, отправит агент-отправитель."""
    if _state["token"]:
        _outbox.put(("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                                     "disable_web_page_preview": True, "reply_markup": _button(button, url)}, None))


def post_clip(author: str, caption: str, detail: str, url: str | None, video: Path | None) -> None:
    """Агент-публикатор: новый клип с сайта — пост в канал. Если есть видео до 50 МБ, прикладываем его."""
    channel = _state["channel"]
    if not (_state["token"] and channel):
        return
    text = f"🎬 <b>{esc(caption)}</b>\n{esc(detail) + chr(10) if detail else ''}Автор: {esc(author)}\n\n#клип #cs2"
    markup = _button("▶ Смотреть на сайте", url)
    if video and video.exists() and video.stat().st_size <= MAX_VIDEO:
        _outbox.put(("sendVideo", {"chat_id": channel, "caption": text, "parse_mode": "HTML",
                                   "supports_streaming": "true", "reply_markup": markup}, ("video", video)))
    else:
        _outbox.put(("sendMessage", {"chat_id": channel, "text": text, "parse_mode": "HTML",
                                     "disable_web_page_preview": True, "reply_markup": markup}, None))


# ---------- Агент 1: отправитель ----------

def _sender() -> None:
    while True:
        method, params, file = _outbox.get()
        for attempt in range(4):
            try:
                call(method, params, file)
                break
            except TelegramError as e:
                if e.retry_after:                    # Telegram просит подождать
                    time.sleep(min(int(e.retry_after) + 1, 120))
                    continue
                print(f"Telegram: {method} не отправлен — {e}")
                break                                # бота заблокировали, нет прав в канале и т.п. — повтор не поможет
            except (urllib.error.URLError, OSError, ValueError) as e:
                print(f"Telegram: нет связи ({e}), попытка {attempt + 1}")
                time.sleep(5 * (attempt + 1))
        time.sleep(1.1)                              # не чаще одного сообщения в секунду


# ---------- Агент 3: итоги дня ----------

def _digest() -> None:
    hooks = _state["hooks"]
    hour = int(os.environ.get("TELEGRAM_DIGEST_HOUR", "21"))
    while True:
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            if _state["channel"] and datetime.now().hour >= hour and hooks["kv_get"]("tg_digest") != today:
                hooks["kv_set"]("tg_digest", today)          # отмечаем сразу, чтобы не написать дважды
                text = hooks["digest"]()
                if text:
                    send_message(_state["channel"], text, hooks.get("site") or None, "Открыть Nuga CS Demo")
        except Exception as e:                               # агент не должен останавливаться из-за одной ошибки
            print("Telegram: итоги дня не получились —", e)
        time.sleep(600)


# ---------- Агент 4: собеседник ----------

HELP = ("Я бот <b>Nuga CS Demo</b> — разбор матчей CS2.\n\n"
        "/clips — последние клипы игроков\n"
        "/help — что я умею\n"
        "/stop — отключить уведомления сайта\n\n"
        "Чтобы получать сюда уведомления (новый подписчик, новый клип от тех, на кого вы подписаны), "
        "откройте на сайте свой профиль и нажмите «Уведомления в Telegram».")


def _reply(chat_id: int, text: str, url: str | None = None, button: str = "Открыть сайт") -> None:
    send_message(chat_id, text, url, button)


def _handle(message: dict) -> None:
    hooks = _state["hooks"]
    chat = message.get("chat") or {}
    if chat.get("type") != "private":                # в группах и каналах бот молчит
        return
    chat_id = chat["id"]
    text = (message.get("text") or "").strip()
    command, _, arg = text.partition(" ")
    command = command.split("@")[0].lower()
    site = hooks.get("site") or None

    if command == "/start":
        if arg.strip():
            name = hooks["link"](arg.strip(), chat_id)
            if name:
                _reply(chat_id, f"✅ Готово, <b>{esc(name)}</b>! Уведомления сайта теперь приходят сюда.\n"
                                f"Отключить — команда /stop.", site)
            else:
                _reply(chat_id, "Эта ссылка уже не действует. Откройте профиль на сайте и нажмите "
                                "«Уведомления в Telegram» ещё раз.", site)
            return
        _reply(chat_id, "Привет! 👋\n\n" + HELP, channel_url() or site, "Наш канал" if channel_url() else "Открыть сайт")
    elif command == "/clips":
        clips = hooks["clips"]()
        if not clips:
            _reply(chat_id, "Пока никто не опубликовал клипы. Будьте первым!", site)
            return
        lines = ["🎬 <b>Последние клипы</b>", ""]
        for c in clips:
            line = f"{esc(c['caption'])} — {esc(c['author'])}"
            lines.append("• " + (f"<a href=\"{c['url']}\">{line}</a>" if c.get("url") else line))
        _reply(chat_id, "\n".join(lines), site)
    elif command == "/stop":
        _reply(chat_id, "Уведомления отключены." if hooks["unlink"](chat_id) else "Уведомления и так не были подключены.")
    else:
        _reply(chat_id, HELP, site)


def _poller() -> None:
    offset = None
    while True:
        try:
            updates = call("getUpdates", {"timeout": 25, "offset": offset, "allowed_updates": ["message"]}, timeout=40)
            for u in updates:
                offset = u["update_id"] + 1
                if "message" in u:
                    try:
                        _handle(u["message"])
                    except Exception as e:
                        print("Telegram: не смог ответить —", e)
        except TelegramError as e:
            # 409 — этим же ботом уже пользуется другая копия сайта; подождём и попробуем снова
            time.sleep(30 if e.code == 409 else 5)
        except (urllib.error.URLError, OSError, ValueError):
            time.sleep(5)


# ---------- Запуск ----------

def _connect() -> None:
    """Проверяем токен (getMe), ставим меню команд и запускаем агентов. Нет интернета — пробуем снова."""
    while True:
        try:
            me = call("getMe")
            break
        except TelegramError as e:
            print("Telegram: бот не подключён —", e, "(проверьте TELEGRAM_BOT_TOKEN в .env)")
            return
        except (urllib.error.URLError, OSError, ValueError):
            time.sleep(30)
    _state["username"] = me.get("username")
    try:
        call("setMyCommands", {"commands": [
            {"command": "clips", "description": "Последние клипы"},
            {"command": "help", "description": "Что умеет бот"},
            {"command": "stop", "description": "Отключить уведомления"},
        ]})
    except (TelegramError, urllib.error.URLError, OSError, ValueError):
        pass
    print(f"Telegram: бот @{_state['username']} подключён" +
          (f", канал {_state['channel']}" if _state["channel"] else " (канал не указан — TELEGRAM_CHANNEL)"))
    for agent in (_sender, _poller, _digest):
        threading.Thread(target=agent, daemon=True, name=f"tg{agent.__name__}").start()


def start(hooks: dict) -> bool:
    """Вызывается сайтом при запуске. hooks — функции сайта, которые нужны агентам (база, клипы, итоги дня)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or _state["started"]:
        return False
    _state.update(token=token, channel=os.environ.get("TELEGRAM_CHANNEL", "").strip() or None,
                  link=os.environ.get("TELEGRAM_LINK", "").strip() or None, hooks=hooks, started=True)
    threading.Thread(target=_connect, daemon=True, name="tg_connect").start()
    return True
