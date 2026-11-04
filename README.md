# Nuga CS Demo

Анализатор демок CS2 с FACEIT: статистика игроков и матрица дуэлей.
CS2 demo analyzer: player stats (K/D, ADR, HS%) and a duel matrix.

## Возможности

- Загрузка демки `.dem`, `.dem.gz` или `.dem.zst` через сайт
- Статистика по командам: убийства, смерти, ассисты, K/D, HS%, ADR
- Матрица дуэлей: кто кого сколько раз убил

## Запуск

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn app:app --reload
```

Откройте http://127.0.0.1:8000 и загрузите демку.

## Технологии

Python, FastAPI, [demoparser2](https://github.com/LaihoE/demoparser), pandas.

## Планы

- [ ] 2D-реплей раундов на радаре карты
- [ ] KAST, entry-киллы, клатчи
- [ ] Вход через FACEIT и автоимпорт матчей
