# Nuga CS Demo — веб-сервер.
# Запуск:  uvicorn app:app --reload
# Потом откройте в браузере http://127.0.0.1:8000

import gzip
import hashlib
import hmac
import secrets
import sqlite3
import threading
import zipfile
from collections import defaultdict, deque
from contextlib import closing
from datetime import date
import json
import os
import re
import time
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

import clips3d
import telegram_bot
from analyzer import analyze_demo, prepare_demo

BASE = Path(__file__).parent
UPLOADS = BASE / "uploads"          # временная папка для загруженных демок
UPLOADS.mkdir(exist_ok=True)

ALLOWED = (".dem.zst", ".dem.gz", ".dem")
MAX_UPLOAD = 700 * 1024 * 1024        # больше 700 МБ не принимаем — защита от слишком больших файлов

MATCHES = BASE / "matches"           # сохранённые разборы: <id>.json.gz (весь разбор) и <id>.meta.json (карточка)
MATCHES.mkdir(exist_ok=True)
MATCH_ID = re.compile(r"[a-f0-9]{12}")


def load_env(path: Path) -> None:
    """Читаем секреты из файла .env (строки вида KEY=значение) в переменные окружения."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


load_env(BASE / ".env")
FACEIT_API = "https://open.faceit.com/data/v4"


def session_secret() -> bytes:
    """Секрет для подписи cookie входа. Если его ещё нет — создаём и дописываем в .env (он не попадает в git)."""
    value = os.environ.get("SESSION_SECRET")
    if not value:
        value = secrets.token_hex(32)
        with (BASE / ".env").open("a", encoding="utf-8") as f:
            f.write(f"\nSESSION_SECRET={value}\n")
        os.environ["SESSION_SECRET"] = value
    return value.encode()


SECRET = session_secret()

# ---------------- Пользователи и монеты ----------------
# Цены и бонусы — меняйте здесь
START_COINS = 20        # подарок при первом входе
DAILY_BONUS = 3         # ежедневный бонус
ANALYSIS_PRICE = 2      # разбор новой демки (повторное открытие бесплатно)

DB_PATH = Path(os.environ.get("NUGA_DB") or BASE / "nuga.db")   # файл базы SQLite — в .gitignore, там данные пользователей


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    return con


with closing(db()) as _con, _con:
    _con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            steam_id   TEXT PRIMARY KEY,
            name       TEXT,
            faceit     TEXT,
            coins      INTEGER NOT NULL,
            created    INTEGER NOT NULL,
            last_bonus TEXT
        );
        CREATE TABLE IF NOT EXISTS coin_log (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            steam_id TEXT NOT NULL,
            delta    INTEGER NOT NULL,
            reason   TEXT NOT NULL,
            ts       INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS user_matches (
            steam_id TEXT NOT NULL,
            match_id TEXT NOT NULL,
            added    INTEGER NOT NULL,
            PRIMARY KEY (steam_id, match_id)
        );
        CREATE TABLE IF NOT EXISTS free_reanalysis (
            steam_id TEXT NOT NULL,
            match_id TEXT NOT NULL,
            PRIMARY KEY (steam_id, match_id)
        );
        CREATE TABLE IF NOT EXISTS follows (
            follower TEXT NOT NULL,
            target   TEXT NOT NULL,
            ts       INTEGER NOT NULL,
            PRIMARY KEY (follower, target)
        );
        CREATE TABLE IF NOT EXISTS clips (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            steam_id  TEXT NOT NULL,
            match_id  TEXT NOT NULL,
            round     INTEGER NOT NULL,
            tick      INTEGER NOT NULL,
            type      TEXT NOT NULL,
            player    TEXT NOT NULL DEFAULT '',
            detail    TEXT NOT NULL DEFAULT '',
            map       TEXT NOT NULL DEFAULT '',
            title     TEXT NOT NULL DEFAULT '',
            video     TEXT NOT NULL DEFAULT '',
            public    INTEGER NOT NULL DEFAULT 0,
            created   INTEGER NOT NULL,
            published INTEGER,
            UNIQUE (steam_id, match_id, round, tick, type)
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            steam_id TEXT NOT NULL,
            kind     TEXT NOT NULL,
            actor    TEXT,
            clip_id  INTEGER,
            ts       INTEGER NOT NULL,
            read     INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS tg_links (
            steam_id TEXT PRIMARY KEY,
            chat_id  INTEGER NOT NULL,
            ts       INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tg_codes (
            code     TEXT PRIMARY KEY,
            steam_id TEXT NOT NULL,
            expires  INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS kv (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    if "avatar" not in {r["name"] for r in _con.execute("PRAGMA table_info(users)")}:
        _con.execute("ALTER TABLE users ADD COLUMN avatar TEXT")      # аватар нужен для публичного профиля


# ---------------- Резервные копии ----------------
# По умолчанию — папка backups рядом с проектом. Лучше указать в .env папку, которая синхронизируется
# с облаком (например BACKUP_DIR=G:\\Мой диск\\nuga-backups) — тогда копии переживут поломку ноутбука.
BACKUP_KEEP_DAYS = 14


def backup_dir() -> Path:
    d = Path(os.environ.get("BACKUP_DIR") or (BASE / "backups"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def make_backup() -> Path:
    """База — целиком в архив за день (она маленькая), разборы — докопируются только новые файлы."""
    out = backup_dir()
    stamp = date.today().isoformat()
    tmp = out / f"nuga-{stamp}.db.tmp"
    with closing(sqlite3.connect(DB_PATH)) as src, closing(sqlite3.connect(tmp)) as dst:
        src.backup(dst)                          # правильная копия, даже если база сейчас используется
    archive = out / f"nuga-db-{stamp}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(tmp, "nuga.db")
        for meta in MATCHES.glob("*.meta.json"):
            z.write(meta, f"matches/{meta.name}")
    tmp.unlink(missing_ok=True)
    # Полные разборы не меняются — копируем только те, которых ещё нет в копии
    mirror = out / "matches"
    mirror.mkdir(exist_ok=True)
    for f in MATCHES.glob("*.json.gz"):
        target = mirror / f.name
        if not target.exists() or target.stat().st_mtime < f.stat().st_mtime:
            shutil.copy2(f, target)
    # Старые архивы базы удаляем, оставляем последние BACKUP_KEEP_DAYS
    for old in sorted(out.glob("nuga-db-*.zip"))[:-BACKUP_KEEP_DAYS]:
        old.unlink(missing_ok=True)
    return archive


def backup_loop():
    while True:
        try:
            if not (backup_dir() / f"nuga-db-{date.today().isoformat()}.zip").exists():
                print("Резервная копия:", make_backup())
        except Exception as e:                   # копия не должна ронять сайт
            print("Не удалось сделать резервную копию:", e)
        time.sleep(3 * 3600)                     # проверяем раз в 3 часа, копия — раз в день


threading.Thread(target=backup_loop, daemon=True).start()


def get_user(steam_id: str) -> dict:
    """Пользователь из базы. При первом входе создаём его и дарим стартовые монеты."""
    with closing(db()) as con, con:
        row = con.execute("SELECT * FROM users WHERE steam_id = ?", (steam_id,)).fetchone()
        if row is None:
            now = int(time.time())
            con.execute("INSERT INTO users (steam_id, coins, created) VALUES (?, ?, ?)", (steam_id, START_COINS, now))
            con.execute("INSERT INTO coin_log (steam_id, delta, reason, ts) VALUES (?, ?, ?, ?)",
                        (steam_id, START_COINS, "Подарок за регистрацию", now))
            row = con.execute("SELECT * FROM users WHERE steam_id = ?", (steam_id,)).fetchone()
        return dict(row)


def change_coins(steam_id: str, delta: int, reason: str) -> bool:
    """Начислить (+) или списать (−) монеты. Списание не уводит баланс в минус — тогда вернём False."""
    with closing(db()) as con, con:
        cur = con.execute("UPDATE users SET coins = coins + ? WHERE steam_id = ? AND coins + ? >= 0",
                          (delta, steam_id, delta))
        if cur.rowcount != 1:
            return False
        con.execute("INSERT INTO coin_log (steam_id, delta, reason, ts) VALUES (?, ?, ?, ?)",
                    (steam_id, delta, reason, int(time.time())))
        return True


def add_user_match(steam_id: str, match_id: str) -> None:
    with closing(db()) as con, con:
        con.execute("INSERT OR IGNORE INTO user_matches (steam_id, match_id, added) VALUES (?, ?, ?)",
                    (steam_id, match_id, int(time.time())))

app = FastAPI(title="Nuga CS Demo")

# Раздаём файлы из папки static (картинки радаров и т.п.) по адресу /static/...
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


# ---------------- Защита: ограничение частоты запросов и заголовки безопасности ----------------

# (начало адреса, сколько запросов можно, за сколько секунд) — проверяются по порядку, срабатывает первое совпадение
RATE_RULES = [
    ("/api/chunk", 150, 600),     # кусочки демок: ~20 демок по 200 МБ за 10 минут
    ("/api/faceit/", 40, 60),     # запросы к FACEIT тратят лимит нашего ключа
    ("/auth/", 20, 60),
    ("/api/", 300, 60),
]
_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


def client_ip(request: Request) -> str:
    """Настоящий IP посетителя: через Cloudflare он приходит в заголовке CF-Connecting-IP."""
    return (request.headers.get("cf-connecting-ip")
            or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "?"))


@app.middleware("http")
async def protect(request: Request, call_next):
    path = request.url.path
    rule = next((r for r in RATE_RULES if path.startswith(r[0])), None)
    if rule:
        prefix, limit, window = rule
        key, now = f"{client_ip(request)}|{prefix}", time.time()
        with _hits_lock:
            q = _hits[key]
            while q and q[0] < now - window:
                q.popleft()
            if len(q) >= limit:
                wait = int(q[0] + window - now) + 1
                return Response(json.dumps({"detail": f"Слишком много запросов — подождите {wait} сек."}, ensure_ascii=False),
                                status_code=429, media_type="application/json", headers={"Retry-After": str(wait)})
            q.append(now)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


# Разбор демки занимает 1–2 ГБ памяти — одновременно делаем только один, остальные ждут своей очереди
ANALYSIS_SLOT = threading.BoundedSemaphore(1)
ANALYSIS_WAIT = 300   # сколько секунд можно ждать очереди


@app.get("/")
def landing():
    """Главная страница — рассказ о сервисе."""
    return FileResponse(BASE / "static" / "landing.html")


@app.get("/sw.js")
def service_worker():
    """Сервис-воркер должен лежать в корне сайта, чтобы управлять всеми страницами приложения."""
    return FileResponse(BASE / "static" / "sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache"})


@app.get("/app")
def index():
    """Само приложение: мои матчи, статистика, загрузка демки."""
    return FileResponse(BASE / "static" / "index.html")


@app.get("/app/{view}")
@app.get("/app/{view}/{rest:path}")
def app_view(view: str, rest: str = ""):
    """Разделы приложения (/app/stats, /app/upload, ...) — та же страница, она сама откроет нужный раздел."""
    return FileResponse(BASE / "static" / "index.html")


def file_id(path: Path) -> str:
    """Отпечаток файла: одинаковая демка всегда даёт одинаковый номер — так находим уже разобранные."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()[:12]


def to_plain(o):
    """numpy-числа и прочее превращаем в обычные значения для JSON."""
    return o.item() if hasattr(o, "item") else str(o)


def match_summary(mid: str, data: dict) -> dict:
    """Короткая карточка матча для списка на главной."""
    players = data.get("players", [])
    teams = sorted({p["team"] for p in players})
    score = [0, 0]
    for r in data.get("replay", {}).get("rounds", []):
        frame = r["frames"][0] if r.get("frames") else []
        i = next((i for i, p in enumerate(players) if teams and p["team"] == teams[0] and i < len(frame) and frame[i]), None)
        if i is None or not r.get("winner"):
            continue
        side = "T" if frame[i][3] == 2 else "CT"
        score[0 if r["winner"] == side else 1] += 1
    best = max(players, key=lambda p: p.get("rating") or 0, default=None)
    return {
        "id": mid,
        "map": data.get("map", "?"),
        "score": score,
        "created": int(time.time()),
        "mvp": {"name": best["name"], "rating": best.get("rating")} if best else None,
        "teams": [[p["name"] for p in players if p["team"] == t] for t in teams],
        "highlights": len(data.get("replay", {}).get("highlights", [])),
        # Подробности хайлайтов — для страницы «Клипы»: тип, игрок, раунд, тик
        "hl": [
            {"t": h.get("type"), "p": players[h["player"]]["name"] if 0 <= h.get("player", -1) < len(players) else "?",
             "r": h.get("round"), "k": h.get("tick"), "d": h.get("detail", "")}
            for h in data.get("replay", {}).get("highlights", [])
        ],
        # Статистика каждого игрока — для раздела «Моя статистика» по всем матчам
        "stats": [
            {k: p.get(k) for k in STAT_FIELDS}
            | {"team": teams.index(p["team"]) if p["team"] in teams else -1}
            | highlight_counts(data, i)
            for i, p in enumerate(players)
        ],
        "v": META_VERSION,
        "av": data.get("analyzer_version", 1),
    }


# Какие показатели игрока сохраняем в карточке матча (для «Статистики», «Рекордов» и «Сравнения»)
STAT_FIELDS = ("name", "kills", "deaths", "assists", "adr", "hs", "kast", "rating", "fk", "fd", "ud",
               "rounds", "k2", "k3", "k4", "k5", "trades", "traded", "shots", "hits",
               "noscope", "smoke", "wall", "blind", "plants", "defuses", "mvps", "clutch")

ANALYZER_VERSION = 7   # растёт, когда анализатор начинает считать новое; старые разборы можно обновить бесплатно
META_VERSION = 4     # меняем, когда в карточку матча добавляются новые поля — старые карточки пересоберутся сами


def highlight_counts(data: dict, i: int) -> dict:
    """Сколько у игрока эйсов, 4K, 3K и выигранных клатчей в матче — для «Рекордов»."""
    hls = [h for h in data.get("replay", {}).get("highlights", []) if h.get("player") == i]
    return {
        "aces": sum(h["type"] == "ACE" for h in hls),
        "k4": sum(h["type"] == "4K" for h in hls),
        "k3": sum(h["type"] == "3K" for h in hls),
        "clutches": sum(h["type"].startswith("1v") for h in hls),
    }


# Номер матча FACEIT, например 1-cb983688-b6af-484f-b0a5-ef13ad422663 (так же называется файл демки)
FACEIT_ID_RE = re.compile(r"1-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def faceit_id_from(filename: str, explicit: str | None = None) -> str | None:
    """Берём номер матча FACEIT: если его прислал сайт — его, иначе ищем в имени файла демки."""
    if explicit and FACEIT_ID_RE.fullmatch(explicit):
        return explicit
    found = FACEIT_ID_RE.search((filename or "").lower())
    return found.group(0) if found else None


def write_meta(mid: str, meta: dict) -> None:
    (MATCHES / f"{mid}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, default=to_plain), encoding="utf-8")


def save_match(mid: str, data: dict, faceit_id: str | None = None) -> None:
    with gzip.open(MATCHES / f"{mid}.json.gz", "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"), default=to_plain)
    meta = match_summary(mid, data)
    if faceit_id:
        meta["faceit_id"] = faceit_id
    write_meta(mid, meta)


def link_faceit(mid: str, faceit_id: str | None) -> None:
    """Демку уже разбирали, но теперь знаем её матч FACEIT — допишем в карточку."""
    path = MATCHES / f"{mid}.meta.json"
    if not faceit_id or not path.exists():
        return
    meta = json.loads(path.read_text(encoding="utf-8"))
    if meta.get("faceit_id") != faceit_id:
        meta["faceit_id"] = faceit_id
        write_meta(mid, meta)


def saved_match_response(mid: str) -> Response:
    """Отдаём сохранённый разбор как есть, в сжатом виде — браузер сам распакует."""
    return Response(content=(MATCHES / f"{mid}.json.gz").read_bytes(), media_type="application/json",
                    headers={"Content-Encoding": "gzip"})


def run_analysis(raw: Path, steam_id: str, faceit_id: str | None = None):
    """Если такую демку уже разбирали — сразу отдаём сохранённое (бесплатно).
    Иначе проверяем монеты, разбираем, сохраняем, списываем монеты и удаляем демку."""
    dem = None
    try:
        mid = file_id(raw)
        meta_path = MATCHES / f"{mid}.meta.json"
        old = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else None
        if (MATCHES / f"{mid}.json.gz").exists() and old and old.get("av", 1) >= ANALYZER_VERSION:
            link_faceit(mid, faceit_id)
            add_user_match(steam_id, mid)
            return saved_match_response(mid)
        upgrade = (MATCHES / f"{mid}.json.gz").exists()     # разбор есть, но старой версии — переразберём бесплатно
        retry = has_free_reanalysis(steam_id, mid)          # сам удалил разбор — повтор тоже бесплатно
        upgrade = upgrade or retry
        faceit_id = faceit_id or (old or {}).get("faceit_id")
        if not upgrade and get_user(steam_id)["coins"] < ANALYSIS_PRICE:
            raise HTTPException(402, f"Не хватает монет: разбор стоит {ANALYSIS_PRICE}. Заберите ежедневный бонус!")
        if not ANALYSIS_SLOT.acquire(timeout=ANALYSIS_WAIT):
            raise HTTPException(503, "Сервер сейчас занят разбором других демок — попробуйте через пару минут")
        try:
            dem = prepare_demo(raw)
            data = analyze_demo(dem)
        finally:
            ANALYSIS_SLOT.release()
        data["id"] = mid
        data["analyzer_version"] = ANALYZER_VERSION
        save_match(mid, data, faceit_id)
        keep_demo(dem, mid)                                  # демка пригодится для 3D-клипов из CS2
        if old:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["created"] = old.get("created", meta["created"])    # дата разбора остаётся прежней
            write_meta(mid, meta)
        if retry:
            use_free_reanalysis(steam_id, mid)
        if not upgrade:
            change_coins(steam_id, -ANALYSIS_PRICE, f"Разбор матча {data.get('map', '')}")
        add_user_match(steam_id, mid)
        return saved_match_response(mid)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Не удалось разобрать демку: {e}")
    finally:
        raw.unlink(missing_ok=True)
        if dem is not None and dem != raw:
            dem.unlink(missing_ok=True)


@app.get("/u/{steam_id}")
def profile_page(steam_id: str):
    """Ссылка на профиль игрока — та же страница, она сама откроет профиль."""
    return FileResponse(BASE / "static" / "index.html")


@app.get("/match/{mid}")
def match_page(mid: str):
    """Ссылка на конкретный матч открывает ту же страницу — она сама загрузит разбор."""
    return FileResponse(BASE / "static" / "index.html")


@app.get("/api/match/{mid}")
def get_match(mid: str):
    if not MATCH_ID.fullmatch(mid) or not (MATCHES / f"{mid}.json.gz").exists():
        raise HTTPException(404, "Матч не найден")
    return saved_match_response(mid)


def upgrade_meta(meta: dict) -> dict:
    """Матчи, сохранённые старой версией, без статистики игроков: пересобираем карточку из полного разбора."""
    mid = meta["id"]
    with gzip.open(MATCHES / f"{mid}.json.gz", "rt", encoding="utf-8") as f:
        data = json.load(f)
    new = match_summary(mid, data)
    new["created"] = meta.get("created", new["created"])   # дату разбора оставляем прежней
    if meta.get("faceit_id"):
        new["faceit_id"] = meta["faceit_id"]
    write_meta(mid, new)
    return new


@app.get("/api/matches")
def list_matches(request: Request):
    """Мои матчи, новые сверху: которые я загрузил и в которых я играл (по нику FACEIT)."""
    steam_id = read_session(request)
    if not steam_id:
        return []
    user = get_user(steam_id)
    with closing(db()) as con:
        mine = {r["match_id"] for r in con.execute("SELECT match_id FROM user_matches WHERE steam_id = ?", (steam_id,))}
    nick = (user.get("faceit") or "").lower()

    metas = []
    for path in MATCHES.glob("*.meta.json"):
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
            if meta.get("v", 1) < META_VERSION:
                meta = upgrade_meta(meta)
            played = bool(nick) and any(str(p.get("name", "")).lower() == nick for p in meta.get("stats", []))
            if meta["id"] in mine or played:
                metas.append(meta)
        except (OSError, ValueError):
            continue
    return sorted(metas, key=lambda m: m.get("created", 0), reverse=True)[:200]


def has_free_reanalysis(steam_id: str, mid: str) -> bool:
    """Пользователь удалил свой разбор и загружает ту же демку снова — монеты не берём (один раз)."""
    with closing(db()) as con:
        return con.execute("SELECT 1 FROM free_reanalysis WHERE steam_id = ? AND match_id = ?",
                           (steam_id, mid)).fetchone() is not None


def use_free_reanalysis(steam_id: str, mid: str) -> None:
    with closing(db()) as con, con:
        con.execute("DELETE FROM free_reanalysis WHERE steam_id = ? AND match_id = ?", (steam_id, mid))


@app.delete("/api/match/{mid}")
def delete_match(mid: str, request: Request):
    """Удалить разбор, чтобы загрузить демку заново. Удалять может тот, кто его загрузил или играл в матче.
    Повторная загрузка той же демки будет бесплатной."""
    steam_id = require_login(request)
    meta_path = MATCHES / f"{mid}.meta.json"
    if not MATCH_ID.fullmatch(mid) or not meta_path.exists():
        raise HTTPException(404, "Матч не найден")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    nick = (get_user(steam_id).get("faceit") or "").lower()
    with closing(db()) as con:
        mine = con.execute("SELECT 1 FROM user_matches WHERE steam_id = ? AND match_id = ?", (steam_id, mid)).fetchone()
    played = bool(nick) and any(str(p.get("name", "")).lower() == nick for p in meta.get("stats", []))
    if not mine and not played:
        raise HTTPException(403, "Удалить можно только свой разбор")
    (MATCHES / f"{mid}.json.gz").unlink(missing_ok=True)
    meta_path.unlink(missing_ok=True)
    with closing(db()) as con, con:
        con.execute("DELETE FROM user_matches WHERE match_id = ?", (mid,))
        con.execute("DELETE FROM clips WHERE match_id = ?", (mid,))
        con.execute("INSERT OR IGNORE INTO free_reanalysis (steam_id, match_id) VALUES (?, ?)", (steam_id, mid))
    return {"ok": True}


def require_login(request: Request) -> str:
    steam_id = read_session(request)
    if not steam_id:
        raise HTTPException(401, "Войдите через Steam, чтобы разбирать демки")
    return steam_id


@app.post("/api/chunk")
def upload_chunk(
    request: Request,
    upload_id: str = Form(...),
    index: int = Form(...),
    total: int = Form(...),
    filename: str = Form(...),
    file: UploadFile = File(...),
    faceit_id: str = Form(""),
):
    """Загрузка демки по кусочкам: так файл проходит даже через сервисы с лимитом 100 МБ на запрос.
    Кусочки приходят по порядку, мы дописываем их в один файл, а после последнего — разбираем демку."""
    # Номер загрузки придумывает браузер — проверяем, что там только буквы и цифры (защита от путей вроде ../)
    steam_id = require_login(request)
    if not re.fullmatch(r"[a-f0-9]{32}", upload_id):
        raise HTTPException(400, "Неверный номер загрузки")
    suffix = next((x for x in ALLOWED if filename.lower().endswith(x)), None)
    if suffix is None:
        raise HTTPException(400, "Нужен файл .dem, .dem.gz или .dem.zst")
    if not (0 <= index < total <= 100):
        raise HTTPException(400, "Неверный номер кусочка")

    part = UPLOADS / f"{upload_id}.part"
    if index == 0:
        # Предупреждаем сразу, а не после загрузки 200 МБ
        if get_user(steam_id)["coins"] < ANALYSIS_PRICE:
            raise HTTPException(402, f"Не хватает монет: разбор стоит {ANALYSIS_PRICE}. Заберите ежедневный бонус!")
        part.unlink(missing_ok=True)
    elif not part.exists():
        raise HTTPException(400, "Загрузка не найдена — начните заново")

    with part.open("ab") as f:
        shutil.copyfileobj(file.file, f)
    if part.stat().st_size > MAX_UPLOAD:
        part.unlink(missing_ok=True)
        raise HTTPException(413, "Файл слишком большой")

    if index < total - 1:
        return {"ok": True}

    raw = UPLOADS / f"{upload_id}{suffix}"
    part.rename(raw)
    return run_analysis(raw, steam_id, faceit_id_from(filename, faceit_id))


@app.post("/api/analyze")
def analyze(request: Request, file: UploadFile = File(...)):
    """Принимает демку, разбирает её и возвращает статистику в JSON."""
    steam_id = require_login(request)
    name = (file.filename or "").lower()
    suffix = next((s for s in ALLOWED if name.endswith(s)), None)
    if suffix is None:
        raise HTTPException(400, "Нужен файл .dem, .dem.gz или .dem.zst")

    # Сохраняем под случайным именем, чтобы файлы разных людей не перепутались
    raw = UPLOADS / f"{uuid.uuid4().hex}{suffix}"
    with raw.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    return run_analysis(raw, steam_id, faceit_id_from(file.filename or ""))


# ---------------- 3D-клипы из самой CS2 ----------------
# Работает только на компьютере, где запущен сервер: он сам открывает CS2 через HLAE и записывает момент.

KEEP_DEMOS = 6                       # сколько последних демок хранить в папке CS2 для клипов (каждая ~400 МБ)
CLIP_JOB: dict = {"state": "idle"}   # одна запись за раз: CS2 на компьютере одна
CLIP_LOCK = threading.Lock()


def cs2_demo_dir() -> Path | None:
    """Папка game/csgo/nuga в CS2 — туда кладём демки для клипов. None, если CS2 на этом компьютере нет."""
    try:
        return clips3d.find_cs2(None) / "game" / "csgo" / "nuga"
    except SystemExit:
        return None


def keep_demo(dem: Path, mid: str) -> None:
    """После разбора не удаляем демку, а переносим в папку CS2 — чтобы потом делать 3D-клипы одной кнопкой."""
    try:
        folder = cs2_demo_dir()
        if folder is None or not dem.exists():
            return
        folder.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dem), str(folder / f"{mid}.dem"))
        old = sorted(folder.glob("*.dem"), key=lambda p: p.stat().st_mtime, reverse=True)[KEEP_DEMOS:]
        for p in old:
            p.unlink(missing_ok=True)
    except OSError:
        pass                         # не получилось сохранить — разбор от этого не страдает


def find_demo(mid: str, meta: dict) -> Path | None:
    """Демка матча для клипа: уже лежит в папке CS2 или находится в «Загрузках» по номеру матча FACEIT."""
    folder = cs2_demo_dir()
    if folder is None:
        return None
    target = folder / f"{mid}.dem"
    if target.exists():
        return target
    fid = meta.get("faceit_id")
    if fid:
        for place in (Path.home() / "Downloads", folder.parent, folder.parent / "replays"):
            for src in sorted(place.glob(f"*{fid}*")) if place.is_dir() else []:
                if src.name.lower().endswith(ALLOWED):
                    clips3d.unpack_demo(src, target)
                    return target
    return None


def is_local(request: Request) -> bool:
    """Запрос пришёл с этого же компьютера, а не через публичную ссылку (Cloudflare добавляет свои заголовки)."""
    if any(h in request.headers for h in ("cf-connecting-ip", "cf-ray", "x-forwarded-for")):
        return False
    return bool(request.client) and request.client.host in ("127.0.0.1", "::1")


def clip3d_job(mid: str, out: Path, clips: list, data: dict, meta: dict, opts: dict) -> None:
    job = CLIP_JOB

    def step(text: str) -> None:
        text = text.strip()
        if text:
            job["step"] = text.splitlines()[-1]

    clips3d.ON_SAY = step
    try:
        cs2 = clips3d.find_cs2(None)
        hlae = clips3d.find_hlae(None)
        clips3d.ffmpeg_bin()
        wait_until = time.time() + 20             # после прошлой записи CS2 может ещё закрываться — подождём
        while clips3d.running("cs2.exe") and time.time() < wait_until:
            time.sleep(1)
        if clips3d.running("cs2.exe"):
            raise RuntimeError("CS2 уже запущена — закройте игру и нажмите ещё раз")
        step("Ищу демку матча…")
        dem = find_demo(mid, meta)
        if dem is None:
            raise RuntimeError("Нет демки этого матча. Загрузите её на сайт ещё раз (это бесплатно) — "
                               "после разбора демка сохранится для клипов.")
        work = clips3d.OUT / mid / "_job"
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        width, height = CLIP_RES[opts["res"]]
        voice = clips3d.voice_mask(dem, clips[0]["steamid"], opts.get("voice", "off"), clips[0]["start"])
        error = clips3d.capture(cs2, hlae, f"nuga/{mid}", clips, work, data.get("map"), opts["fps"], opts["hud"],
                                width, height, opts["xray"], voice)
        if error:
            raise RuntimeError(error)
        done = clips3d.assemble(work, vertical=opts["vertical"])
        if not done:
            raise RuntimeError("Видео не записалось")
        if len(done) != len(clips):
            raise RuntimeError("Записались не все моменты — попробуйте ещё раз")
        result = work / "montage.mp4" if len(done) > 1 else done[0]      # несколько моментов — берём общий ролик
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(result), str(out))
        shutil.rmtree(work, ignore_errors=True)
        job.update(state="done", step="Готово", url=f"/clips3d/{mid}/{out.name}")
    except (RuntimeError, SystemExit, OSError, subprocess.CalledProcessError) as e:
        job.update(state="error", step=str(e) or "Не получилось записать клип")
    finally:
        clips3d.ON_SAY = None


@app.get("/api/clip3d/status")
def clip3d_status(request: Request):
    """Можно ли на этом компьютере делать 3D-клипы и что сейчас с записью."""
    return {"available": is_local(request) and cs2_demo_dir() is not None, **CLIP_JOB}


CLIP_RES = {"720": (1280, 720), "1080": (1920, 1080)}
CLIP_MAX_SECONDS = 600               # длиннее 10 минут за один раз не пишем


@app.post("/api/match/{mid}/clip3d")
def clip3d_start(mid: str, request: Request, body: dict = Body(default={})):
    """Записать видео в самой CS2. Что писать (mode): moment — хайлайт игрока в раунде, compilation — все его
    хайлайты одним роликом, round — весь раунд от его лица, montage — выбранные убийства.
    Настройки: res 720/1080, fps 60/120, hud full/killfeed/none, xray, vertical (9:16),
    enemy — камера противника: off, each (после каждого убийства), end (все в конце),
    voice — голосовой чат из демки: off, all (обе команды), team (свои), enemy (противники).
    Одинаковый запрос второй раз отдаёт уже готовый клип."""
    require_login(request)
    if not is_local(request):
        raise HTTPException(403, "3D-клипы записываются только на компьютере, где запущен сайт")
    if not MATCH_ID.fullmatch(mid) or not (MATCHES / f"{mid}.json.gz").exists():
        raise HTTPException(404, "Матч не найден")
    try:
        opts = {
            "mode": str(body.get("mode", "moment")),
            "round": int(body.get("round", 0)),
            "player": int(body.get("player", 0)),
            "kills": sorted({int(t) for t in (body.get("kills") or [])})[:60],
            "res": str(body.get("res", "1080")),
            "fps": int(body.get("fps", 60)),
            "hud": str(body.get("hud", "full")),
            "xray": bool(body.get("xray", False)),
            "vertical": bool(body.get("vertical", False)),
            "enemy": str(body.get("enemy", "off")),
            "voice": str(body.get("voice", "off")),
        }
    except (TypeError, ValueError):
        raise HTTPException(400, "Неверные настройки записи")
    if (opts["mode"] not in ("moment", "compilation", "round", "montage") or opts["res"] not in CLIP_RES
            or opts["fps"] not in (60, 120) or opts["hud"] not in ("full", "killfeed", "none")
            or opts["enemy"] not in ("off", "each", "end") or opts["voice"] not in ("off", "all", "team", "enemy")):
        raise HTTPException(400, "Неверные настройки записи")

    key = hashlib.sha256(json.dumps(opts, sort_keys=True).encode()).hexdigest()[:16]
    ready = clips3d.OUT / mid / "site" / f"{key}.mp4"
    if ready.exists():
        return {"state": "done", "url": f"/clips3d/{mid}/{ready.name}"}

    with gzip.open(MATCHES / f"{mid}.json.gz", "rt", encoding="utf-8") as f:
        data = json.load(f)
    meta = json.loads((MATCHES / f"{mid}.meta.json").read_text(encoding="utf-8"))
    ri, pi = opts["round"], opts["player"]
    if not 0 <= pi < len(data.get("players", [])):
        raise HTTPException(400, "Нет такого игрока")
    mine = [c for c in clips3d.build_clips(data, None, None, None, 2) if c["player"] == pi]
    if opts["mode"] == "moment":
        clips = [c for c in mine if c["round"] == ri]
    elif opts["mode"] == "compilation":
        clips = mine
    elif opts["mode"] == "round":
        clips = [c for c in [clips3d.round_clip(data, ri, pi)] if c]
    else:
        clips = [c for c in [clips3d.kills_clip(data, pi, opts["kills"])] if c]
    if not clips:
        raise HTTPException(404, "Для такой записи у игрока нет моментов")
    if opts["enemy"] != "off":                               # те же убийства от лица противника
        clips = clips3d.add_enemy_views(data, clips, opts["enemy"])
    if sum(c["length"] for c in clips) > CLIP_MAX_SECONDS:
        raise HTTPException(400, "Слишком длинное видео — выберите меньше моментов")

    with CLIP_LOCK:
        if CLIP_JOB.get("state") == "running":
            raise HTTPException(409, "Уже идёт запись другого клипа — дождитесь её конца")
        CLIP_JOB.clear()
        CLIP_JOB.update(state="running", step="Запускаю CS2…", mid=mid, key=key,
                        seconds=round(sum(c["length"] for c in clips)))
        threading.Thread(target=clip3d_job, args=(mid, ready, clips, data, meta, opts), daemon=True).start()
    return dict(CLIP_JOB)


@app.get("/clips3d/{mid}/{name}")
def clip3d_file(mid: str, name: str):
    if not MATCH_ID.fullmatch(mid) or not re.fullmatch(r"[a-f0-9]{16}\.mp4", name):
        raise HTTPException(404, "Клип не найден")
    path = clips3d.OUT / mid / "site" / name
    if not path.exists():
        raise HTTPException(404, "Клип не найден")
    return FileResponse(path, media_type="video/mp4")


# ---------------- FACEIT ----------------

def faceit_get(path: str, params: dict | None = None) -> dict:
    """Запрос к FACEIT Data API. Ключ берётся из .env и никогда не уходит в браузер."""
    key = os.environ.get("FACEIT_API_KEY")
    if not key:
        raise HTTPException(500, "Нет ключа FACEIT: добавьте FACEIT_API_KEY в файл .env")
    url = f"{FACEIT_API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise HTTPException(404, "Игрок не найден на FACEIT")
        if e.code == 401:
            raise HTTPException(500, "FACEIT не принял ключ — проверьте FACEIT_API_KEY в .env")
        raise HTTPException(502, f"FACEIT ответил ошибкой {e.code}")
    except urllib.error.URLError:
        raise HTTPException(502, "Нет связи с FACEIT")


# Скачивание демок: FACEIT выдаёт ссылку только ключам с доступом к Downloads API (его одобряют по заявке).
# Пока доступа нет, на своём компьютере берём демку из папки «Загрузки» — по номеру матча в имени файла.
FACEIT_DOWNLOAD_API = "https://open.faceit.com/download/v2/demos/download"
_downloads_denied_until = 0.0        # FACEIT ответил «нет доступа» — какое-то время не спрашиваем снова


def faceit_demo_download(faceit_id: str) -> Path | None:
    """Скачивает демку матча через FACEIT Downloads API в папку uploads. None — у ключа нет доступа."""
    global _downloads_denied_until
    if time.time() < _downloads_denied_until:
        return None
    urls = faceit_get(f"/matches/{faceit_id}").get("demo_url") or []
    if not urls:
        raise HTTPException(404, "У этого матча на FACEIT уже нет демки (они хранятся несколько недель)")
    req = urllib.request.Request(
        FACEIT_DOWNLOAD_API, data=json.dumps({"resource_url": urls[0]}).encode("utf-8"),
        headers={"Authorization": f"Bearer {os.environ.get('FACEIT_API_KEY', '')}",
                 "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            link = (json.loads(res.read().decode("utf-8")).get("payload") or {}).get("download_url")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):                 # «no valid scope provided» — заявку на Downloads API ещё не одобрили
            _downloads_denied_until = time.time() + 3600
            return None
        raise HTTPException(502, f"FACEIT не отдал демку (ошибка {e.code})")
    except urllib.error.URLError:
        raise HTTPException(502, "Нет связи с FACEIT")
    if not link or not link.startswith("https://"):
        raise HTTPException(502, "FACEIT не прислал ссылку на демку")

    suffix = next((x for x in ALLOWED if urllib.parse.urlparse(link).path.lower().endswith(x)), ".dem.zst")
    raw = UPLOADS / f"{uuid.uuid4().hex}{suffix}"
    try:
        with urllib.request.urlopen(link, timeout=60) as res, open(raw, "wb") as out:
            size = 0
            while block := res.read(1024 * 1024):
                size += len(block)
                if size > MAX_UPLOAD:
                    raise HTTPException(413, "Демка слишком большая")
                out.write(block)
    except (urllib.error.URLError, OSError):
        raw.unlink(missing_ok=True)
        raise HTTPException(502, "Не удалось скачать демку с FACEIT")
    except HTTPException:
        raw.unlink(missing_ok=True)
        raise
    return raw


def local_demo_copy(faceit_id: str) -> Path | None:
    """Демка этого матча из папки «Загрузки» (браузер называет файл номером матча). Копируем — оригинал не трогаем."""
    for src in sorted((Path.home() / "Downloads").glob(f"*{faceit_id}*")):
        suffix = next((x for x in ALLOWED if src.name.lower().endswith(x)), None)
        if suffix and src.is_file() and 0 < src.stat().st_size <= MAX_UPLOAD:
            raw = UPLOADS / f"{uuid.uuid4().hex}{suffix}"
            shutil.copyfile(src, raw)
            return raw
    return None


@app.post("/api/faceit/import")
def faceit_import(request: Request, faceit_id: str = Query(...)):
    """Кнопка «Загрузить» у матча: сами достаём демку (FACEIT Downloads API или «Загрузки» на этом компьютере)
    и разбираем её. Если демки нигде нет — отвечаем 409, сайт попросит скачать её в комнате матча."""
    steam_id = require_login(request)
    if not FACEIT_ID_RE.fullmatch(faceit_id):
        raise HTTPException(400, "Неверный номер матча")
    local = is_local(request)
    raw = local_demo_copy(faceit_id) if local else None
    if raw is None:
        raw = faceit_demo_download(faceit_id)
    if raw is None:
        raise HTTPException(409, {"need_demo": True, "local": local})
    return run_analysis(raw, steam_id, faceit_id)


def my_score(score: str | None, won: bool | None) -> str:
    """FACEIT пишет счёт в порядке команд ("4 / 13"). Разворачиваем: сначала раунды игрока."""
    if not score:
        return ""
    try:
        a, b = (int(x) for x in score.replace(" ", "").split("/"))
    except ValueError:
        return score
    if won is None:
        return f"{a} : {b}"
    hi, lo = max(a, b), min(a, b)
    return f"{hi} : {lo}" if won else f"{lo} : {hi}"


SUMMARY_CACHE: dict[str, tuple[float, dict]] = {}


def num_or_none(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@app.get("/api/faceit/summary")
def faceit_summary(nickname: str = Query(..., min_length=2, max_length=32), limit: int = Query(20, ge=5, le=50)):
    """Средние показатели игрока FACEIT за последние матчи — для «Сравнения»."""
    key = f"{nickname.lower()}:{limit}"
    cached = SUMMARY_CACHE.get(key)
    if cached and cached[0] > time.time():
        return cached[1]

    player = faceit_get("/players", {"nickname": nickname, "game": "cs2"})
    pid = player["player_id"]
    cs2 = (player.get("games") or {}).get("cs2") or {}
    items = faceit_get(f"/players/{pid}/games/cs2/stats", {"offset": 0, "limit": limit}).get("items", [])
    rows = [it.get("stats", {}) for it in items]

    def avg(field):
        vals = [x for x in (num_or_none(r.get(field)) for r in rows) if x is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    def total(field):
        return int(sum(num_or_none(r.get(field)) or 0 for r in rows))

    kills, deaths = total("Kills"), total("Deaths")
    results = [r.get("Result") for r in rows if r.get("Result") in ("0", "1")]
    summary = {
        "nickname": player.get("nickname"),
        "avatar": player.get("avatar"),
        "level": cs2.get("skill_level"),
        "elo": cs2.get("faceit_elo"),
        "matches": len(rows),
        "stats": {
            "winrate": round(100 * results.count("1") / len(results), 1) if results else None,
            "kd": round(kills / deaths, 2) if deaths else None,
            "kills": avg("Kills"),
            "adr": avg("ADR"),
            "hs": avg("Headshots %"),
            "kr": avg("K/R Ratio"),
            "assists": avg("Assists"),
            "mvps": avg("MVPs"),
            "triple": total("Triple Kills"),
            "quadro": total("Quadro Kills"),
            "penta": total("Penta Kills"),
        },
    }
    SUMMARY_CACHE[key] = (time.time() + 300, summary)
    return summary


@app.get("/api/faceit/player")
def faceit_player(nickname: str = Query(..., min_length=2, max_length=32), limit: int = Query(20, ge=1, le=50)):
    """Профиль игрока FACEIT по нику и его последние матчи CS2 со статистикой."""
    player = faceit_get("/players", {"nickname": nickname, "game": "cs2"})
    pid = player["player_id"]
    cs2 = (player.get("games") or {}).get("cs2") or {}

    history = faceit_get(f"/players/{pid}/history", {"game": "cs2", "offset": 0, "limit": limit})
    # Статистика по каждому матчу (убийства, ADR и т.д.) — отдельный запрос
    try:
        stats = faceit_get(f"/players/{pid}/games/cs2/stats", {"offset": 0, "limit": limit})
    except HTTPException:
        stats = {"items": []}
    by_match = {}
    for item in stats.get("items", []):
        st = item.get("stats", {})
        if st.get("Match Id"):
            by_match[st["Match Id"]] = st

    matches = []
    for m in history.get("items", []):
        mid = m.get("match_id")
        st = by_match.get(mid, {})
        # Выиграла ли команда игрока
        my_team = None
        for team_key, team in (m.get("teams") or {}).items():
            if any(p.get("player_id") == pid for p in team.get("players", [])):
                my_team = team_key
        winner = (m.get("results") or {}).get("winner")
        result = st.get("Result")
        # Главный источник — какая команда победила в матче; запасной — поле Result из статистики
        if my_team and winner:
            won = winner == my_team
        elif result in ("0", "1"):
            won = result == "1"
        else:
            won = None

        matches.append({
            "match_id": mid,
            "finished_at": m.get("finished_at"),
            "map": st.get("Map", ""),
            "won": won,
            "score": my_score(st.get("Score"), won),
            "kills": st.get("Kills"),
            "deaths": st.get("Deaths"),
            "assists": st.get("Assists"),
            "kd": st.get("K/D Ratio"),
            "adr": st.get("ADR"),
            "hs": st.get("Headshots %"),
            "url": (m.get("faceit_url") or f"https://www.faceit.com/{{lang}}/cs2/room/{mid}").replace("{lang}", "ru"),
        })

    return {
        "nickname": player.get("nickname"),
        "avatar": player.get("avatar"),
        "country": player.get("country"),
        "level": cs2.get("skill_level"),
        "elo": cs2.get("faceit_elo"),
        "url": (player.get("faceit_url") or "").replace("{lang}", "ru"),
        "matches": matches,
    }


# ---------------- Вход через Steam (OpenID 2.0) ----------------

STEAM_OPENID = "https://steamcommunity.com/openid/login"
STEAM_ID_RE = re.compile(r"^https://steamcommunity\.com/openid/id/(\d{17})$")
SESSION_COOKIE = "nuga_session"
SESSION_DAYS = 30


def site_url(request: Request) -> str:
    """Адрес сайта, как его видит пользователь (через туннель это https://....trycloudflare.com)."""
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def sign(value: str) -> str:
    return hmac.new(SECRET, value.encode(), hashlib.sha256).hexdigest()


def make_session(steam_id: str) -> str:
    """Cookie вида «steamid.срок.подпись». Подделать без секрета нельзя."""
    payload = f"{steam_id}.{int(time.time()) + SESSION_DAYS * 86400}"
    return f"{payload}.{sign(payload)}"


def read_session(request: Request) -> str | None:
    """Steam ID вошедшего пользователя или None."""
    raw = request.cookies.get(SESSION_COOKIE, "")
    parts = raw.split(".")
    if len(parts) != 3:
        return None
    steam_id, expires, signature = parts
    if not hmac.compare_digest(signature, sign(f"{steam_id}.{expires}")):
        return None
    if not expires.isdigit() or int(expires) < time.time():
        return None
    return steam_id


@app.get("/auth/steam")
def steam_login(request: Request):
    """Отправляем пользователя на страницу входа Steam."""
    base = site_url(request)
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": f"{base}/auth/steam/callback",
        "openid.realm": base,
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
    }
    return RedirectResponse(f"{STEAM_OPENID}?{urllib.parse.urlencode(params)}")


@app.get("/auth/steam/callback")
def steam_callback(request: Request):
    """Steam вернул пользователя. Проверяем ответ у самого Steam и только тогда пускаем."""
    params = dict(request.query_params)
    base = site_url(request)

    # 1) Ответ должен быть адресован именно нам и содержать Steam ID
    match = STEAM_ID_RE.match(params.get("openid.claimed_id", ""))
    if (params.get("openid.mode") != "id_res" or not match
            or params.get("openid.return_to", "").split("?")[0] != f"{base}/auth/steam/callback"
            or params.get("openid.op_endpoint") != STEAM_OPENID):
        return RedirectResponse("/app?login=error")

    # 2) Спрашиваем Steam: «этот ответ действительно от тебя?»
    check = dict(params, **{"openid.mode": "check_authentication"})
    try:
        req = urllib.request.Request(STEAM_OPENID, data=urllib.parse.urlencode(check).encode(),
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=15) as res:
            answer = res.read().decode("utf-8", "replace")
    except urllib.error.URLError:
        return RedirectResponse("/app?login=error")
    if "is_valid:true" not in answer:
        return RedirectResponse("/app?login=error")

    response = RedirectResponse("/app")
    response.set_cookie(SESSION_COOKIE, make_session(match.group(1)), max_age=SESSION_DAYS * 86400,
                        httponly=True, samesite="lax", secure=base.startswith("https"))
    return response


@app.post("/api/me/delete")
def delete_account(request: Request):
    """Удалить аккаунт: монеты, историю и список «моих матчей». Разборы матчей остаются —
    в них статистика всех 10 игроков, и их могут открывать по ссылке другие участники."""
    steam_id = require_login(request)
    with closing(db()) as con, con:
        con.execute("DELETE FROM coin_log WHERE steam_id = ?", (steam_id,))
        con.execute("DELETE FROM user_matches WHERE steam_id = ?", (steam_id,))
        con.execute("DELETE FROM users WHERE steam_id = ?", (steam_id,))
        con.execute("DELETE FROM follows WHERE follower = ? OR target = ?", (steam_id, steam_id))
        con.execute("DELETE FROM clips WHERE steam_id = ?", (steam_id,))
        con.execute("DELETE FROM notifications WHERE steam_id = ? OR actor = ?", (steam_id, steam_id))
        con.execute("DELETE FROM tg_links WHERE steam_id = ?", (steam_id,))
        con.execute("DELETE FROM tg_codes WHERE steam_id = ?", (steam_id,))
    PROFILE_CACHE.pop(steam_id, None)
    response = Response(json.dumps({"ok": True}), media_type="application/json")
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/privacy")
def privacy_page():
    return FileResponse(BASE / "static" / "privacy.html")


@app.get("/auth/logout")
def logout():
    response = RedirectResponse("/")
    response.delete_cookie(SESSION_COOKIE)
    return response


PROFILE_CACHE: dict[str, tuple[float, dict]] = {}


def steam_profile(steam_id: str) -> dict:
    """Имя и аватар из открытого профиля Steam (без API-ключа)."""
    try:
        url = f"https://steamcommunity.com/profiles/{steam_id}/?xml=1"
        with urllib.request.urlopen(url, timeout=10) as res:
            xml = res.read().decode("utf-8", "replace")
        name = re.search(r"<steamID><!\[CDATA\[(.*?)\]\]></steamID>", xml, re.S)
        avatar = re.search(r"<avatarMedium><!\[CDATA\[(.*?)\]\]></avatarMedium>", xml, re.S)
        return {"name": name.group(1) if name else None, "avatar": avatar.group(1) if avatar else None}
    except (urllib.error.URLError, ValueError):
        return {"name": None, "avatar": None}


@app.get("/api/me")
def me(request: Request):
    """Кто вошёл: Steam ID + профиль FACEIT (если есть) + имя из Steam."""
    steam_id = read_session(request)
    if not steam_id:
        return {"logged_in": False}

    cached = PROFILE_CACHE.get(steam_id)
    if cached and cached[0] > time.time():
        return with_coins(cached[1])

    profile = {"logged_in": True, "steam_id": steam_id, "faceit": None}
    try:
        player = faceit_get("/players", {"game": "cs2", "game_player_id": steam_id})
        cs2 = (player.get("games") or {}).get("cs2") or {}
        profile["faceit"] = {
            "nickname": player.get("nickname"),
            "avatar": player.get("avatar"),
            "level": cs2.get("skill_level"),
            "elo": cs2.get("faceit_elo"),
        }
    except HTTPException:
        pass                                    # нет аккаунта FACEIT или нет ключа — не страшно
    steam = steam_profile(steam_id)
    profile["name"] = (profile["faceit"] or {}).get("nickname") or steam["name"] or steam_id
    profile["avatar"] = (profile["faceit"] or {}).get("avatar") or steam["avatar"]

    PROFILE_CACHE[steam_id] = (time.time() + 600, profile)
    get_user(steam_id)
    with closing(db()) as con, con:      # запоминаем имя и ник FACEIT — по нику находим «мои матчи»
        con.execute("UPDATE users SET name = ?, faceit = ?, avatar = ? WHERE steam_id = ?",
                    (profile["name"], (profile["faceit"] or {}).get("nickname"), profile["avatar"], steam_id))
    return with_coins(profile)


def with_coins(profile: dict) -> dict:
    user = get_user(profile["steam_id"])
    return dict(profile, coins=user["coins"], bonus_ready=user["last_bonus"] != date.today().isoformat())


@app.get("/api/coins")
def coins(request: Request):
    """Баланс, история и цены."""
    steam_id = require_login(request)
    user = get_user(steam_id)
    with closing(db()) as con:
        log = [dict(r) for r in con.execute(
            "SELECT delta, reason, ts FROM coin_log WHERE steam_id = ? ORDER BY id DESC LIMIT 20", (steam_id,))]
    return {"coins": user["coins"], "bonus_ready": user["last_bonus"] != date.today().isoformat(),
            "daily_bonus": DAILY_BONUS, "analysis_price": ANALYSIS_PRICE, "start_coins": START_COINS, "log": log}


@app.post("/api/coins/bonus")
def daily_bonus(request: Request):
    """Ежедневный бонус — раз в календарный день."""
    steam_id = require_login(request)
    today = date.today().isoformat()
    with closing(db()) as con, con:
        cur = con.execute("UPDATE users SET last_bonus = ? WHERE steam_id = ? AND (last_bonus IS NULL OR last_bonus != ?)",
                          (today, steam_id, today))
        if cur.rowcount != 1:
            raise HTTPException(409, "Бонус сегодня уже получен — приходите завтра")
    change_coins(steam_id, DAILY_BONUS, "Ежедневный бонус")
    return coins(request)


# ---------------- Профили, подписки, клипы и уведомления ----------------

STEAM_ID64 = re.compile(r"\d{17}")
MAX_CLIPS = 300                      # столько клипов можно держать в одном профиле
CLIP_VIDEO_RE = re.compile(r"/clips3d/([a-f0-9]{12})/([a-f0-9]{16})\.mp4")
SITE_URL = (os.environ.get("SITE_URL") or "").rstrip("/")     # постоянный адрес сайта — для ссылок в Telegram


def user_row(steam_id: str) -> dict | None:
    """Пользователь из базы без создания нового (для чужих профилей)."""
    if not STEAM_ID64.fullmatch(steam_id or ""):
        return None
    with closing(db()) as con:
        row = con.execute("SELECT * FROM users WHERE steam_id = ?", (steam_id,)).fetchone()
    return dict(row) if row else None


def public_user(u: dict) -> dict:
    return {"steam_id": u["steam_id"], "name": u.get("name") or u["steam_id"], "avatar": u.get("avatar"),
            "faceit": u.get("faceit")}


def clip_dict(row) -> dict:
    c = dict(row)
    c["public"] = bool(c["public"])
    return c


def clip_caption(c: dict) -> str:
    """Подпись клипа: своя, а если её нет — «ACE · Nuga · Mirage»."""
    if c.get("title"):
        return c["title"]
    kind = "3D-клип" if c["type"] == "3D" else c["type"]
    return " · ".join(x for x in (kind, c.get("player"), (c.get("map") or "").replace("de_", "").capitalize()) if x)


def notify(steam_id: str, kind: str, actor: str | None = None, clip_id: int | None = None, text: str = "",
           link: str = "") -> None:
    """Уведомление на сайте (колокольчик) и, если привязан Telegram, сообщением от бота."""
    with closing(db()) as con, con:
        con.execute("INSERT INTO notifications (steam_id, kind, actor, clip_id, ts) VALUES (?, ?, ?, ?, ?)",
                    (steam_id, kind, actor, clip_id, int(time.time())))
        con.execute("DELETE FROM notifications WHERE steam_id = ? AND id NOT IN "
                    "(SELECT id FROM notifications WHERE steam_id = ? ORDER BY id DESC LIMIT 100)", (steam_id, steam_id))
        chat = con.execute("SELECT chat_id FROM tg_links WHERE steam_id = ?", (steam_id,)).fetchone()
    if chat and text:
        telegram_bot.send_message(chat["chat_id"], text, f"{SITE_URL}{link}" if SITE_URL and link else None)


@app.get("/api/config")
def site_config():
    """Что показать на сайте: ссылка «Наш Телеграм» и имя бота (если они настроены в .env)."""
    return {"telegram": telegram_bot.channel_url(), "bot": telegram_bot.bot_username()}


@app.get("/api/profile/{steam_id}")
def get_profile(steam_id: str, request: Request):
    """Профиль игрока: подписчики, подписки, опубликованные клипы. Владельцу — ещё и личные клипы."""
    u = user_row(steam_id)
    if not u:
        raise HTTPException(404, "Профиль не найден")
    viewer = read_session(request)
    is_me = viewer == steam_id
    with closing(db()) as con:
        followers = con.execute("SELECT COUNT(*) FROM follows WHERE target = ?", (steam_id,)).fetchone()[0]
        following = con.execute("SELECT COUNT(*) FROM follows WHERE follower = ?", (steam_id,)).fetchone()[0]
        is_following = bool(viewer) and con.execute(
            "SELECT 1 FROM follows WHERE follower = ? AND target = ?", (viewer, steam_id)).fetchone() is not None
        rows = con.execute("SELECT * FROM clips WHERE steam_id = ?" + ("" if is_me else " AND public = 1") +
                           " ORDER BY COALESCE(published, created) DESC, id DESC", (steam_id,)).fetchall()
        tg = is_me and con.execute("SELECT 1 FROM tg_links WHERE steam_id = ?", (steam_id,)).fetchone() is not None
    clips = [clip_dict(r) for r in rows]
    out = public_user(u) | {
        "followers": followers, "following": following, "is_me": is_me, "is_following": is_following,
        "logged_in": bool(viewer), "created": u["created"],
        "clips": [c for c in clips if c["public"]],
        "posts": sum(c["public"] for c in clips),
    }
    if is_me:
        out["private"] = [c for c in clips if not c["public"]]
        out["telegram"] = {"available": telegram_bot.enabled(), "linked": tg}
    return out


@app.get("/api/profile/{steam_id}/follows")
def profile_follows(steam_id: str, kind: str = Query("followers")):
    """Список подписчиков (followers) или подписок (following)."""
    if not user_row(steam_id):
        raise HTTPException(404, "Профиль не найден")
    a, b = ("follower", "target") if kind == "followers" else ("target", "follower")
    with closing(db()) as con:
        rows = con.execute(f"SELECT u.* FROM follows f JOIN users u ON u.steam_id = f.{a} "
                           f"WHERE f.{b} = ? ORDER BY f.ts DESC LIMIT 200", (steam_id,)).fetchall()
    return [public_user(dict(r)) for r in rows]


@app.post("/api/profile/{steam_id}/follow")
def follow(steam_id: str, request: Request):
    me_id = require_login(request)
    if me_id == steam_id:
        raise HTTPException(400, "На себя подписаться нельзя")
    if not user_row(steam_id):
        raise HTTPException(404, "Профиль не найден")
    my = get_user(me_id)
    with closing(db()) as con, con:
        new = con.execute("INSERT OR IGNORE INTO follows (follower, target, ts) VALUES (?, ?, ?)",
                          (me_id, steam_id, int(time.time()))).rowcount == 1
        # Подписался-отписался-подписался — второе уведомление за сутки не шлём
        recent = con.execute("SELECT 1 FROM notifications WHERE steam_id = ? AND kind = 'follow' AND actor = ? AND ts > ?",
                             (steam_id, me_id, int(time.time()) - 86400)).fetchone()
    if new and not recent:
        notify(steam_id, "follow", actor=me_id, link=f"/u/{me_id}",
               text=f"👤 <b>{telegram_bot.esc(my.get('name') or me_id)}</b> подписался на вас в Nuga CS Demo")
    return {"ok": True}


@app.delete("/api/profile/{steam_id}/follow")
def unfollow(steam_id: str, request: Request):
    me_id = require_login(request)
    with closing(db()) as con, con:
        con.execute("DELETE FROM follows WHERE follower = ? AND target = ?", (me_id, steam_id))
    return {"ok": True}


@app.post("/api/clips")
def save_clip(request: Request, body: dict = Body(...)):
    """Сохранить момент матча в свой профиль (в «Личные»). video — адрес записанного 3D-клипа, если он есть."""
    steam_id = require_login(request)
    mid = str(body.get("match_id", ""))
    meta_path = MATCHES / f"{mid}.meta.json"
    if not MATCH_ID.fullmatch(mid) or not meta_path.exists():
        raise HTTPException(404, "Матч не найден")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    video = str(body.get("video") or "")
    vm = CLIP_VIDEO_RE.fullmatch(video) if video else None
    if video and (not vm or vm.group(1) != mid or not (clips3d.OUT / mid / "site" / f"{vm.group(2)}.mp4").exists()):
        raise HTTPException(400, "Видео не найдено")
    try:
        rnd, tick, kind = int(body.get("round", -1)), int(body.get("tick", 0)), str(body.get("type", ""))
    except (TypeError, ValueError):
        raise HTTPException(400, "Неверный клип")
    h = next((x for x in meta.get("hl", []) if x.get("r") == rnd and x.get("k") == tick and x.get("t") == kind), None)
    if h:
        player, detail = str(h.get("p", "")), str(h.get("d", ""))
    elif vm:                                     # компиляция, раунд или монтаж — не один хайлайт, а просто видео
        rnd, tick, kind, detail = -1, int(vm.group(2)[:7], 16), "3D", ""
        names = [str(s.get("name", "")) for s in meta.get("stats", [])]
        player = str(body.get("player", "")) if str(body.get("player", "")) in names else ""
    else:
        raise HTTPException(400, "В этом матче нет такого момента")
    with closing(db()) as con, con:
        if con.execute("SELECT COUNT(*) FROM clips WHERE steam_id = ?", (steam_id,)).fetchone()[0] >= MAX_CLIPS:
            raise HTTPException(400, f"В профиле уже {MAX_CLIPS} клипов — удалите лишние")
        con.execute(
            "INSERT INTO clips (steam_id, match_id, round, tick, type, player, detail, map, video, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (steam_id, match_id, round, tick, type) DO UPDATE SET "
            "video = CASE WHEN excluded.video != '' THEN excluded.video ELSE clips.video END",
            (steam_id, mid, rnd, tick, kind, player, detail, str(meta.get("map", "")), video, int(time.time())))
        row = con.execute("SELECT * FROM clips WHERE steam_id = ? AND match_id = ? AND round = ? AND tick = ? AND type = ?",
                          (steam_id, mid, rnd, tick, kind)).fetchone()
    return clip_dict(row)


def own_clip(con, cid: int, steam_id: str) -> dict:
    row = con.execute("SELECT * FROM clips WHERE id = ? AND steam_id = ?", (cid, steam_id)).fetchone()
    if not row:
        raise HTTPException(404, "Клип не найден")
    return dict(row)


@app.post("/api/clips/{cid}/publish")
def publish_clip(cid: int, request: Request, body: dict = Body(default={})):
    """Опубликовать клип (public: true) или вернуть в личные (false). title — подпись, до 80 символов.
    При первой публикации подписчики получают уведомление, а клип уходит в Telegram-канал."""
    steam_id = require_login(request)
    public = bool(body.get("public", True))
    with closing(db()) as con, con:
        clip = own_clip(con, cid, steam_id)
        title = str(body["title"]).strip()[:80] if body.get("title") is not None else clip["title"]
        first = public and clip["published"] is None
        con.execute("UPDATE clips SET public = ?, title = ?, published = COALESCE(published, ?) WHERE id = ?",
                    (int(public), title, int(time.time()) if public else None, cid))
        clip = clip_dict(con.execute("SELECT * FROM clips WHERE id = ?", (cid,)).fetchone())
        followers = [r["follower"] for r in con.execute("SELECT follower FROM follows WHERE target = ?", (steam_id,))] if first else []
    if first:
        author = get_user(steam_id).get("name") or steam_id
        caption = clip_caption(clip)
        for f in followers:
            notify(f, "clip", actor=steam_id, clip_id=cid, link=f"/u/{steam_id}",
                   text=f"🎬 <b>{telegram_bot.esc(author)}</b> опубликовал клип: {telegram_bot.esc(caption)}")
        video = None
        if clip["video"]:
            vm = CLIP_VIDEO_RE.fullmatch(clip["video"])
            video = clips3d.OUT / vm.group(1) / "site" / f"{vm.group(2)}.mp4" if vm else None
        telegram_bot.post_clip(author, caption, clip["detail"],
                               f"{SITE_URL}/u/{steam_id}?clip={cid}" if SITE_URL else None, video)
    return clip


@app.delete("/api/clips/{cid}")
def delete_clip(cid: int, request: Request):
    steam_id = require_login(request)
    with closing(db()) as con, con:
        own_clip(con, cid, steam_id)
        con.execute("DELETE FROM clips WHERE id = ?", (cid,))
        con.execute("DELETE FROM notifications WHERE clip_id = ?", (cid,))
    return {"ok": True}


def recent_public_clips(limit: int, only_from: str | None = None, since: int = 0) -> list[dict]:
    """Последние опубликованные клипы с автором. only_from — только от тех, на кого подписан этот игрок."""
    sql = ("SELECT c.*, u.name AS author, u.avatar AS author_avatar FROM clips c JOIN users u ON u.steam_id = c.steam_id "
           "WHERE c.public = 1 AND c.published >= ?")
    args: list = [since]
    if only_from:
        sql += " AND c.steam_id IN (SELECT target FROM follows WHERE follower = ?)"
        args.append(only_from)
    with closing(db()) as con:
        return [clip_dict(r) for r in con.execute(sql + " ORDER BY c.published DESC, c.id DESC LIMIT ?", (*args, limit))]


@app.get("/api/feed")
def feed(request: Request, scope: str = Query("all")):
    """Лента: опубликованные клипы всех игроков (all) или только тех, на кого я подписан (following)."""
    viewer = read_session(request)
    if scope == "following":
        return recent_public_clips(60, only_from=viewer) if viewer else []
    return recent_public_clips(60)


@app.get("/api/notifications")
def notifications(request: Request):
    steam_id = read_session(request)
    if not steam_id:
        return {"unread": 0, "items": []}
    with closing(db()) as con:
        rows = con.execute(
            "SELECT n.id, n.kind, n.ts, n.read, n.actor, n.clip_id, u.name AS actor_name, u.avatar AS actor_avatar, "
            "c.title, c.type, c.player, c.map FROM notifications n LEFT JOIN users u ON u.steam_id = n.actor "
            "LEFT JOIN clips c ON c.id = n.clip_id WHERE n.steam_id = ? ORDER BY n.id DESC LIMIT 30", (steam_id,)).fetchall()
        unread = con.execute("SELECT COUNT(*) FROM notifications WHERE steam_id = ? AND read = 0", (steam_id,)).fetchone()[0]
    items = []
    for r in rows:
        r = dict(r)
        clip = clip_caption(r) if r["clip_id"] and r["type"] else ""
        items.append({"id": r["id"], "kind": r["kind"], "ts": r["ts"], "read": bool(r["read"]), "actor": r["actor"],
                      "actor_name": r["actor_name"] or "Игрок", "actor_avatar": r["actor_avatar"], "clip_id": r["clip_id"],
                      "clip": clip})
    return {"unread": unread, "items": items}


@app.post("/api/notifications/read")
def notifications_read(request: Request):
    steam_id = require_login(request)
    with closing(db()) as con, con:
        con.execute("UPDATE notifications SET read = 1 WHERE steam_id = ?", (steam_id,))
    return {"ok": True}


# ---------------- Telegram: привязка аккаунта и «агенты» канала ----------------

@app.post("/api/telegram/link")
def telegram_link(request: Request):
    """Ссылка на бота с одноразовым кодом: человек нажимает «Запустить» — и бот знает, чей это профиль."""
    steam_id = require_login(request)
    bot = telegram_bot.bot_username()
    if not bot:
        raise HTTPException(503, "Telegram-бот пока не подключён")
    code = secrets.token_urlsafe(12)
    with closing(db()) as con, con:
        con.execute("DELETE FROM tg_codes WHERE steam_id = ? OR expires < ?", (steam_id, int(time.time())))
        con.execute("INSERT INTO tg_codes (code, steam_id, expires) VALUES (?, ?, ?)", (code, steam_id, int(time.time()) + 900))
    return {"url": f"https://t.me/{bot}?start={code}"}


@app.delete("/api/telegram/link")
def telegram_unlink(request: Request):
    steam_id = require_login(request)
    with closing(db()) as con, con:
        con.execute("DELETE FROM tg_links WHERE steam_id = ?", (steam_id,))
    return {"ok": True}


def tg_link_code(code: str, chat_id: int) -> str | None:
    """Бот получил /start <код>: привязываем чат к профилю. Возвращаем имя игрока или None, если код не подошёл."""
    with closing(db()) as con, con:
        row = con.execute("SELECT steam_id FROM tg_codes WHERE code = ? AND expires > ?", (code, int(time.time()))).fetchone()
        if not row:
            return None
        con.execute("DELETE FROM tg_codes WHERE code = ?", (code,))
        con.execute("DELETE FROM tg_links WHERE chat_id = ?", (chat_id,))
        con.execute("INSERT OR REPLACE INTO tg_links (steam_id, chat_id, ts) VALUES (?, ?, ?)",
                    (row["steam_id"], chat_id, int(time.time())))
        user = con.execute("SELECT name FROM users WHERE steam_id = ?", (row["steam_id"],)).fetchone()
    return (user["name"] if user and user["name"] else row["steam_id"])


def tg_unlink_chat(chat_id: int) -> bool:
    with closing(db()) as con, con:
        return con.execute("DELETE FROM tg_links WHERE chat_id = ?", (chat_id,)).rowcount > 0


def tg_recent_clips() -> list[dict]:
    """Для команды /clips: последние опубликованные клипы."""
    return [{"caption": clip_caption(c), "author": c["author"] or "Игрок",
             "url": f"{SITE_URL}/u/{c['steam_id']}?clip={c['id']}" if SITE_URL else None}
            for c in recent_public_clips(5)]


def kv_get(key: str) -> str | None:
    with closing(db()) as con:
        row = con.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def kv_set(key: str, value: str) -> None:
    with closing(db()) as con, con:
        con.execute("INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)", (key, value))


def tg_digest() -> str | None:
    """Итоги дня для канала: сколько матчей разобрали, лучший матч и новые клипы. None — писать не о чем."""
    since = int(time.mktime(date.today().timetuple()))
    best, matches = None, 0
    for path in MATCHES.glob("*.meta.json"):
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if meta.get("created", 0) < since:
            continue
        matches += 1
        for st in meta.get("stats", []):
            if st.get("rating") and (best is None or st["rating"] > best[0]["rating"]):
                best = (st, meta)
    clips = recent_public_clips(5, since=since)
    if not matches and not clips:
        return None
    e = telegram_bot.esc
    lines = ["📊 <b>Итоги дня в Nuga CS Demo</b>", ""]
    if matches:
        lines.append(f"Разобрано матчей: <b>{matches}</b>")
    if best:
        st, meta = best
        lines.append(f"🏆 Игрок дня: <b>{e(st.get('name', '?'))}</b> — рейтинг {float(st['rating']):.2f}, "
                     f"{st.get('kills', 0)}/{st.get('deaths', 0)} на {e(str(meta.get('map', '')).replace('de_', '').capitalize())}")
    if clips:
        lines += ["", f"🎬 Новые клипы: <b>{len(clips)}</b>"]
        for c in clips:
            text = f"{e(clip_caption(c))} — {e(c['author'] or 'Игрок')}"
            lines.append("• " + (f"<a href=\"{SITE_URL}/u/{c['steam_id']}?clip={c['id']}\">{text}</a>" if SITE_URL else text))
    return "\n".join(lines)


telegram_bot.start({"link": tg_link_code, "unlink": tg_unlink_chat, "clips": tg_recent_clips, "digest": tg_digest,
                    "kv_get": kv_get, "kv_set": kv_set, "site": SITE_URL})
