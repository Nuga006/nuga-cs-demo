# Nuga CS Demo — веб-сервер.
# Запуск:  uvicorn app:app --reload
# Потом откройте в браузере http://127.0.0.1:8000

import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from analyzer import analyze_demo, prepare_demo

BASE = Path(__file__).parent
UPLOADS = BASE / "uploads"          # временная папка для загруженных демок
UPLOADS.mkdir(exist_ok=True)

ALLOWED = (".dem.zst", ".dem.gz", ".dem")

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
