# Nuga CS Demo — модуль разбора демки.
# Здесь вся логика анализа. Сервер (app.py) просто вызывает analyze_demo().

import gzip
import shutil
from pathlib import Path

import pandas as pd
from demoparser2 import DemoParser


def prepare_demo(path: Path) -> Path:
    """Если файл сжат (.gz или .zst), распаковываем его рядом в .dem и возвращаем новый путь."""
    if path.suffix not in (".gz", ".zst"):
        return path

    dem_path = path.with_suffix("")  # match.dem.zst -> match.dem
    if dem_path.exists():
        return dem_path

    if path.suffix == ".gz":
        with gzip.open(path, "rb") as src, open(dem_path, "wb") as dst:
            shutil.copyfileobj(src, dst)
    else:
        import zstandard
        with open(path, "rb") as src, open(dem_path, "wb") as dst:
            zstandard.ZstdDecompressor().copy_stream(src, dst)
    return dem_path


def drop_warmup(df: pd.DataFrame) -> pd.DataFrame:
    """Убираем события из разминки (warmup)."""
    if df.empty or "is_warmup_period" not in df.columns:
        return df
    return df[~df["is_warmup_period"].fillna(False).astype(bool)]


def analyze_demo(demo_path: Path) -> dict:
    """Разбирает демку и возвращает словарь, который сервер отдаст сайту в виде JSON."""
    parser = DemoParser(str(demo_path))
    header = parser.parse_header()

    # События из демки
    deaths = drop_warmup(parser.parse_event("player_death", player=["team_num"], other=["is_warmup_period"]))
    hurts = drop_warmup(parser.parse_event("player_hurt", player=["team_num"], other=["is_warmup_period"]))
    rounds = drop_warmup(parser.parse_event("round_end", other=["is_warmup_period"]))
    num_rounds = max(len(rounds), 1)

    # SteamID всегда как строки
    for df in (deaths, hurts):
        for col in ("attacker_steamid", "user_steamid", "assister_steamid"):
            if col in df.columns:
                df[col] = df[col].astype(str)

    # Убийства только противников (без самоубийств и тимкиллов)
    kills = deaths[
        deaths["attacker_steamid"].notna()
        & (deaths["attacker_steamid"] != "None")
        & (deaths["attacker_steamid"] != deaths["user_steamid"])
        & (deaths["attacker_team_num"] != deaths["user_team_num"])
    ]

    # Урон по противникам, один удар не больше 100 HP
    enemy_hurts = hurts[hurts["attacker_team_num"] != hurts["user_team_num"]].copy()
    enemy_hurts["dmg"] = enemy_hurts["dmg_health"].clip(upper=100)

    # Игроки: оставляем только тех, кто был в командах (без зрителей)
    players = parser.parse_player_info()
    players["steamid"] = players["steamid"].astype(str)
    if "team_number" in players.columns:
        players = players[players["team_number"].isin([2, 3])]

    player_rows = []
    for _, p in players.iterrows():
        sid = p["steamid"]
        k = int((kills["attacker_steamid"] == sid).sum())
        d = int((deaths["user_steamid"] == sid).sum())
        a = int((deaths.get("assister_steamid", pd.Series(dtype=str)) == sid).sum())
        hs = int(kills.loc[kills["attacker_steamid"] == sid, "headshot"].sum())
        dmg = float(enemy_hurts.loc[enemy_hurts["attacker_steamid"] == sid, "dmg"].sum())

        player_rows.append({
            "steamid": sid,
            "name": str(p["name"]),
            "team": int(p.get("team_number", 0)),
            "kills": k,
            "deaths": d,
            "assists": a,
            "kd": round(k / d, 2) if d else float(k),
            "hs": round(hs / k * 100) if k else 0,
            "adr": round(dmg / num_rounds, 1),
        })

    # Дуэли: duels[убийца][жертва] = сколько раз
    duels: dict[str, dict[str, int]] = {}
    for (att, vic), n in kills.groupby(["attacker_steamid", "user_steamid"]).size().items():
        duels.setdefault(att, {})[vic] = int(n)

    return {
        "map": header.get("map_name", "?"),
        "rounds": len(rounds),
        "players": player_rows,
        "duels": duels,
    }
