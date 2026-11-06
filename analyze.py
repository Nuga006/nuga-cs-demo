# Nuga CS Demo — первый скрипт анализа демки CS2
# Запуск:  python analyze.py имя_демки.dem
# Можно сразу давать .dem.zst или .dem.gz с FACEIT — скрипт сам распакует.

import gzip
import shutil
import sys
from pathlib import Path

import pandas as pd
from demoparser2 import DemoParser

# Чтобы таблицы в терминале печатались полностью, без "..."
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 50)


def prepare_demo(path: Path) -> Path:
    """Если файл сжат (.gz или .zst), распаковываем его рядом в .dem и возвращаем новый путь."""
    if path.suffix not in (".gz", ".zst"):
        return path

    dem_path = path.with_suffix("")  # match.dem.zst -> match.dem
    if dem_path.exists():
        return dem_path

    print(f"Распаковываю {path.name}...")
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as src, open(dem_path, "wb") as dst:
            shutil.copyfileobj(src, dst)
    else:
        import zstandard  # библиотека для формата .zst (pip install zstandard)
        with open(path, "rb") as src, open(dem_path, "wb") as dst:
            zstandard.ZstdDecompressor().copy_stream(src, dst)
    return dem_path


def drop_warmup(df: pd.DataFrame) -> pd.DataFrame:
    """Убираем события из разминки (warmup), чтобы они не портили статистику."""
    if df.empty or "is_warmup_period" not in df.columns:
        return df
    return df[~df["is_warmup_period"].fillna(False).astype(bool)]


def main():
    # 1. Проверяем, что пользователь указал файл
    if len(sys.argv) < 2:
        print("Использование: python analyze.py имя_демки.dem")
        return

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Файл не найден: {path}")
        return

    demo_path = prepare_demo(path)
    parser = DemoParser(str(demo_path))

    # 2. Общая информация о матче (карта, сервер)
    header = parser.parse_header()
    print(f"\nКарта: {header.get('map_name', '?')}")

    # 3. Достаём нужные события из демки.
    #    player=["team_num"] добавляет номер команды убийцы и жертвы,
    #    other=["is_warmup_period"] помечает события из разминки.
    deaths = parser.parse_event("player_death", player=["team_num"], other=["is_warmup_period"])
    hurts = parser.parse_event("player_hurt", player=["team_num"], other=["is_warmup_period"])
    rounds = parser.parse_event("round_end", other=["is_warmup_period"])

    deaths = drop_warmup(deaths)
    hurts = drop_warmup(hurts)
    rounds = drop_warmup(rounds)

    num_rounds = max(len(rounds), 1)
    print(f"Раундов: {len(rounds)}\n")

    # SteamID приводим к строкам, чтобы сравнения всегда работали
    for df in (deaths, hurts):
        for col in ("attacker_steamid", "user_steamid"):
            if col in df.columns:
                df[col] = df[col].astype(str)

    # 4. "Честные" убийства: был убийца, это не самоубийство и не убийство своего
    kills = deaths[
        deaths["attacker_steamid"].notna()
        & (deaths["attacker_steamid"] != "None")
        & (deaths["attacker_steamid"] != deaths["user_steamid"])
        & (deaths["attacker_team_num"] != deaths["user_team_num"])
    ]

    # Урон только по противникам. Один выстрел не может снять больше 100 HP,
    # поэтому обрезаем значение до 100 (это приблизительный ADR).
    enemy_hurts = hurts[hurts["attacker_team_num"] != hurts["user_team_num"]].copy()
    enemy_hurts["dmg"] = enemy_hurts["dmg_health"].clip(upper=100)

    # 5. Список игроков матча
    players = parser.parse_player_info()
    players["steamid"] = players["steamid"].astype(str)

    rows = []
    for _, p in players.iterrows():
        sid = p["steamid"]
        k = int((kills["attacker_steamid"] == sid).sum())
        d = int((deaths["user_steamid"] == sid).sum())
        hs = int(kills.loc[kills["attacker_steamid"] == sid, "headshot"].sum())
        dmg = enemy_hurts.loc[enemy_hurts["attacker_steamid"] == sid, "dmg"].sum()

        rows.append({
            "Игрок": p["name"],
            "Команда": p.get("team_number", ""),
            "K": k,
            "D": d,
            "K/D": round(k / d, 2) if d else float(k),
            "HS%": round(hs / k * 100) if k else 0,
            "ADR": round(dmg / num_rounds, 1),
        })

    stats = pd.DataFrame(rows).sort_values(["Команда", "K"], ascending=[True, False])
    print("=== Статистика игроков ===")
    print(stats.to_string(index=False))

    # 6. Матрица дуэлей: строка — кто убивал, столбец — кого убили
    print("\n=== Матрица дуэлей (строка убила столбец) ===")
    duels = pd.crosstab(kills["attacker_name"], kills["user_name"])
    print(duels.to_string())

    # Сохраняем результаты в CSV — пригодится для сайта и можно открыть в Excel
    stats.to_csv("stats.csv", index=False, encoding="utf-8-sig")
    duels.to_csv("duels.csv", encoding="utf-8-sig")
    print("\nСохранено: stats.csv и duels.csv")


if __name__ == "__main__":
    main()
