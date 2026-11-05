# Nuga CS Demo — веб-сервер.
# Запуск:  uvicorn app:app --reload
# Потом откройте в браузере http://127.0.0.1:8000

import gzip
import hashlib
import json
import os
import re
import time
import shutil
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

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

app = FastAPI(title="Nuga CS Demo")

# Раздаём файлы из папки static (картинки радаров и т.п.) по адресу /static/...
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


@app.get("/")
def index():
    """Главная страница сайта."""
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
        # Статистика каждого игрока — для раздела «Моя статистика» по всем матчам
        "stats": [
            {k: p.get(k) for k in ("name", "kills", "deaths", "assists", "adr", "hs", "kast", "rating", "fk", "fd")}
            | {"team": teams.index(p["team"]) if p["team"] in teams else -1}
            for p in players
        ],
    }


def save_match(mid: str, data: dict) -> None:
    with gzip.open(MATCHES / f"{mid}.json.gz", "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"), default=to_plain)
    (MATCHES / f"{mid}.meta.json").write_text(
        json.dumps(match_summary(mid, data), ensure_ascii=False, default=to_plain), encoding="utf-8")


def saved_match_response(mid: str) -> Response:
    """Отдаём сохранённый разбор как есть, в сжатом виде — браузер сам распакует."""
    return Response(content=(MATCHES / f"{mid}.json.gz").read_bytes(), media_type="application/json",
                    headers={"Content-Encoding": "gzip"})


def run_analysis(raw: Path):
    """Если такую демку уже разбирали — сразу отдаём сохранённое. Иначе разбираем, сохраняем и удаляем демку."""
    dem = None
    try:
        mid = file_id(raw)
        if (MATCHES / f"{mid}.json.gz").exists():
            return saved_match_response(mid)
        dem = prepare_demo(raw)
        data = analyze_demo(dem)
        data["id"] = mid
        save_match(mid, data)
        return saved_match_response(mid)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Не удалось разобрать демку: {e}")
    finally:
        raw.unlink(missing_ok=True)
        if dem is not None and dem != raw:
            dem.unlink(missing_ok=True)


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
    (MATCHES / f"{mid}.meta.json").write_text(json.dumps(new, ensure_ascii=False, default=to_plain), encoding="utf-8")
    return new


@app.get("/api/matches")
def list_matches():
    """Все сохранённые матчи, новые сверху."""
    metas = []
    for path in MATCHES.glob("*.meta.json"):
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
            if "stats" not in meta:
                meta = upgrade_meta(meta)
            metas.append(meta)
        except (OSError, ValueError):
            continue
    return sorted(metas, key=lambda m: m.get("created", 0), reverse=True)[:200]


@app.post("/api/chunk")
def upload_chunk(
    upload_id: str = Form(...),
    index: int = Form(...),
    total: int = Form(...),
    filename: str = Form(...),
    file: UploadFile = File(...),
):
    """Загрузка демки по кусочкам: так файл проходит даже через сервисы с лимитом 100 МБ на запрос.
    Кусочки приходят по порядку, мы дописываем их в один файл, а после последнего — разбираем демку."""
    # Номер загрузки придумывает браузер — проверяем, что там только буквы и цифры (защита от путей вроде ../)
    if not re.fullmatch(r"[a-f0-9]{32}", upload_id):
        raise HTTPException(400, "Неверный номер загрузки")
    suffix = next((x for x in ALLOWED if filename.lower().endswith(x)), None)
    if suffix is None:
        raise HTTPException(400, "Нужен файл .dem, .dem.gz или .dem.zst")
    if not (0 <= index < total <= 100):
        raise HTTPException(400, "Неверный номер кусочка")

    part = UPLOADS / f"{upload_id}.part"
    if index == 0:
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
    return run_analysis(raw)


@app.post("/api/analyze")
def analyze(file: UploadFile = File(...)):
    """Принимает демку, разбирает её и возвращает статистику в JSON."""
    name = (file.filename or "").lower()
    suffix = next((s for s in ALLOWED if name.endswith(s)), None)
    if suffix is None:
        raise HTTPException(400, "Нужен файл .dem, .dem.gz или .dem.zst")

    # Сохраняем под случайным именем, чтобы файлы разных людей не перепутались
    raw = UPLOADS / f"{uuid.uuid4().hex}{suffix}"
    with raw.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    return run_analysis(raw)


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
