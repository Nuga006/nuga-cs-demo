# Nuga CS Demo — модуль разбора демки.
# Здесь вся логика анализа. Сервер (app.py) просто вызывает analyze_demo().

import gzip
import shutil
from pathlib import Path

import pandas as pd
from demoparser2 import DemoParser

# Каждый какой тик сохранять позиции для реплея.
# Демки FACEIT идут с частотой 64 тика в секунду, значит шаг 8 = 8 кадров в секунду.
REPLAY_STEP = 8


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


def normalize_side(value) -> str:
    """Победитель раунда может прийти как 2/3 или как 'T'/'CT' — приводим к 'T' или 'CT'."""
    v = str(value).strip().upper()
    if v in ("2", "T", "TERRORIST"):
        return "T"
    if v in ("3", "CT"):
        return "CT"
    return ""


def build_rounds(parser: DemoParser) -> list[dict]:
    """Находим начало (конец закупки) и конец каждого раунда."""
    freeze = drop_warmup(parser.parse_event("round_freeze_end", other=["is_warmup_period"]))
    ends = drop_warmup(parser.parse_event("round_end", other=["is_warmup_period", "total_rounds_played"]))
    if freeze.empty or ends.empty:
        return []

    # Оставляем только настоящие раунды — где победила T или CT.
    # Служебные события (рестарт после разминки и т.п.) победителя не имеют.
    ends = ends.copy()
    ends["side"] = ends["winner"].map(normalize_side) if "winner" in ends.columns else ""
    ends = ends[ends["side"] != ""]

    # Если конец одного и того же раунда записан дважды — оставляем первый
    if "total_rounds_played" in ends.columns:
        ends = ends.sort_values("tick").drop_duplicates(subset="total_rounds_played", keep="first")

    starts = sorted(int(t) for t in freeze["tick"])
    rounds = []
    for _, e in ends.sort_values("tick").iterrows():
        end_tick = int(e["tick"])
        before = [s for s in starts if s < end_tick]
        if not before:
            continue
        start_tick = max(before)
        # Защита от дублей: раунд должен начинаться после конца предыдущего
        if rounds and start_tick < rounds[-1]["end"]:
            continue
        rounds.append({
            "start": start_tick,
            "end": end_tick,
            "winner": e["side"],
        })
    return rounds


def build_replay(parser: DemoParser, rounds: list[dict], player_ids: list[str], kills: pd.DataFrame) -> dict:
    """Собираем позиции игроков по кадрам для каждого раунда."""
    index = {sid: i for i, sid in enumerate(player_ids)}

    # Список нужных тиков: внутри раундов с шагом REPLAY_STEP
    wanted = []
    for r in rounds:
        wanted.extend(range(r["start"], r["end"] + 1, REPLAY_STEP))
    if not wanted:
        return {"step": REPLAY_STEP, "rounds": []}

    props = ["X", "Y", "team_num", "is_alive", "health", "active_weapon_name"]
    ticks_df = parser.parse_ticks(props, ticks=wanted)
    ticks_df["steamid"] = ticks_df["steamid"].astype(str)
    for col in props:
        if col not in ticks_df.columns:      # на случай, если в демке нет какого-то поля
            ticks_df[col] = None

    # by_tick[тик] = список позиций всех игроков в этот момент
    by_tick: dict[int, list] = {}
    cols = ["tick", "steamid", "X", "Y", "team_num", "is_alive", "health", "active_weapon_name"]
    for tick, sid, x, y, team, alive, hp, weapon in ticks_df[cols].itertuples(index=False):
        i = index.get(sid)
        if i is None or pd.isna(x) or pd.isna(y):
            continue
        frame = by_tick.setdefault(int(tick), [None] * len(player_ids))
        # [x, y, жив ли (1/0), команда (2 = T, 3 = CT), HP, оружие в руках]
        frame[i] = [
            round(float(x)),
            round(float(y)),
            1 if alive else 0,
            int(team) if not pd.isna(team) else 0,
            int(hp) if not pd.isna(hp) else 0,
            str(weapon) if isinstance(weapon, str) else "",
        ]

    bomb = bomb_events(parser)

    replay_rounds = []
    for r in rounds:
        ticks = [t for t in range(r["start"], r["end"] + 1, REPLAY_STEP) if t in by_tick]
        round_kills = kills[(kills["tick"] >= r["start"]) & (kills["tick"] <= r["end"])]
        replay_rounds.append({
            **r,
            "ticks": ticks,
            "frames": [by_tick[t] for t in ticks],
            "kills": [
                {
                    "tick": int(k.tick),
                    "attacker": str(k.attacker_name),
                    "victim": str(k.user_name),
                    "weapon": str(k.weapon),
                    "headshot": bool(k.headshot),
                    "x": round(float(k.user_X)) if not pd.isna(k.user_X) else None,
                    "y": round(float(k.user_Y)) if not pd.isna(k.user_Y) else None,
                }
                for k in round_kills.itertuples(index=False)
            ],
            "bomb": [b for b in bomb if r["start"] <= b["tick"] <= r["end"] + 64 * 3],
        })

    return {"step": REPLAY_STEP, "rounds": replay_rounds}


def bomb_events(parser: DemoParser) -> list[dict]:
    """События с бомбой: установка, разминирование, взрыв."""
    result = []
    for event, kind in (("bomb_planted", "planted"), ("bomb_defused", "defused"), ("bomb_exploded", "exploded")):
        try:
            df = drop_warmup(parser.parse_event(event, player=["X", "Y"], other=["is_warmup_period"]))
        except Exception:
            continue  # такого события в демке нет
        for row in df.to_dict("records"):
            x, y = row.get("user_X"), row.get("user_Y")
            result.append({
                "type": kind,
                "tick": int(row["tick"]),
                "player": str(row.get("user_name") or ""),
                "x": round(float(x)) if x is not None and not pd.isna(x) else None,
                "y": round(float(y)) if y is not None and not pd.isna(y) else None,
            })
    return sorted(result, key=lambda b: b["tick"])


def analyze_demo(demo_path: Path) -> dict:
    """Разбирает демку и возвращает словарь, который сервер отдаст сайту в виде JSON."""
    parser = DemoParser(str(demo_path))
    header = parser.parse_header()

    # События из демки. X и Y — координаты на карте (нужны для отметок смертей в реплее).
    deaths = drop_warmup(parser.parse_event("player_death", player=["team_num", "X", "Y"], other=["is_warmup_period"]))
    hurts = drop_warmup(parser.parse_event("player_hurt", player=["team_num"], other=["is_warmup_period"]))
    rounds = build_rounds(parser)
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

    # 2D-реплей: игроки в том же порядке, что и в player_rows
    replay = build_replay(parser, rounds, [p["steamid"] for p in player_rows], kills)

    return {
        "map": header.get("map_name", "?"),
        "rounds": len(rounds),
        "players": player_rows,
        "duels": duels,
        "replay": replay,
    }
