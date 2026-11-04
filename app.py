# Nuga CS Demo — веб-сервер.
# Запуск:  uvicorn app:app --reload
# Потом откройте в браузере http://127.0.0.1:8000

import json
import os
import shutil
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from analyzer import analyze_demo, prepare_demo

BASE = Path(__file__).parent
UPLOADS = BASE / "uploads"          # временная папка для загруженных демок
UPLOADS.mkdir(exist_ok=True)

ALLOWED = (".dem.zst", ".dem.gz", ".dem")


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

    dem = None
    try:
        dem = prepare_demo(raw)
        return analyze_demo(dem)
    except Exception as e:
        raise HTTPException(500, f"Не удалось разобрать демку: {e}")
    finally:
        # Демки большие — удаляем сразу после разбора
        raw.unlink(missing_ok=True)
        if dem is not None and dem != raw:
            dem.unlink(missing_ok=True)


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
