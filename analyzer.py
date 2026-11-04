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


def build_replay(parser: DemoParser, rounds: list[dict], player_ids: list[str],
                 kills: pd.DataFrame, deaths: pd.DataFrame) -> dict:
    """Собираем позиции игроков по кадрам для каждого раунда."""
    index = {sid: i for i, sid in enumerate(player_ids)}

    # Список нужных тиков: внутри раундов с шагом REPLAY_STEP
    wanted = []
    for r in rounds:
        wanted.extend(range(r["start"], r["end"] + 1, REPLAY_STEP))
    if not wanted:
        return {"step": REPLAY_STEP, "rounds": []}

    # Что достаём о каждом игроке в каждом кадре:
    #   yaw — куда смотрит (градусы), balance — деньги, inventory — что лежит в карманах
    base_props = ["X", "Y", "team_num", "is_alive", "health", "active_weapon_name", "yaw", "balance", "armor_value",
                  "current_equip_value"]
    try:
        ticks_df = parser.parse_ticks(base_props + ["inventory"], ticks=wanted)
    except Exception:
        ticks_df = parser.parse_ticks(base_props, ticks=wanted)   # старые демки без инвентаря
    ticks_df["steamid"] = ticks_df["steamid"].astype(str)
    for col in base_props + ["inventory"]:
        if col not in ticks_df.columns:      # на случай, если в демке нет какого-то поля
            ticks_df[col] = None

    # by_tick[тик] = список состояний всех игроков в этот момент
    by_tick: dict[int, list] = {}
    cols = ["tick", "steamid"] + base_props + ["inventory"]
    for tick, sid, x, y, team, alive, hp, weapon, yaw, money, armor, equip, inv in ticks_df[cols].itertuples(index=False):
        i = index.get(sid)
        if i is None or pd.isna(x) or pd.isna(y):
            continue
        nades, has_bomb = parse_inventory(inv)
        frame = by_tick.setdefault(int(tick), [None] * len(player_ids))
        # [0 x, 1 y, 2 жив (1/0), 3 команда (2 = T, 3 = CT), 4 HP, 5 оружие в руках,
        #  6 куда смотрит, 7 деньги, 8 гранаты ("sfh..."), 9 несёт бомбу (1/0), 10 броня,
        #  11 стоимость снаряжения в руках и карманах]
        frame[i] = [
            round(float(x)),
            round(float(y)),
            1 if alive else 0,
            num(team),
            num(hp),
            str(weapon) if isinstance(weapon, str) else "",
            round(float(yaw)) if not is_missing(yaw) else None,
            num(money),
            nades,
            has_bomb,
            num(armor),
            num(equip),
        ]

    bomb = bomb_events(parser)
    grenades = grenade_events(parser)
    shots = shot_events(parser)

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
            # Гранаты, которые хотя бы частично действовали в этом раунде
            "grenades": [g for g in grenades if g["end"] >= r["start"] and g["start"] <= r["end"]],
            # Выстрелы: [тик, x, y, угол, команда]
            "shots": [s for s in shots if r["start"] <= s[0] <= r["end"]],
        })

    highlights = find_highlights(replay_rounds, player_ids, kills, deaths)
    return {"step": REPLAY_STEP, "rounds": replay_rounds, "highlights": highlights}


def find_highlights(replay_rounds: list[dict], player_ids: list[str],
                    kills: pd.DataFrame, deaths: pd.DataFrame) -> list[dict]:
    """Ищем яркие моменты: мульти-киллы (3K, 4K, ACE) и выигранные клатчи (1vN)."""
    index = {sid: i for i, sid in enumerate(player_ids)}
    side_name = {2: "T", 3: "CT"}
    result = []

    for ri, r in enumerate(replay_rounds):
        if not r["frames"]:
            continue
        # За какую сторону играет каждый игрок в этом раунде — по первому кадру
        first = r["frames"][0]
        side = {i: p[3] for i, p in enumerate(first) if p}
        alive = {i for i in side}

        # --- Мульти-киллы ---
        rk = kills[(kills["tick"] >= r["start"]) & (kills["tick"] <= r["end"])]
        for sid, group in rk.groupby("attacker_steamid"):
            n = len(group)
            if n >= 3 and sid in index:
                result.append({
                    "round": ri,
                    "tick": int(group["tick"].min()),
                    "type": {3: "3K", 4: "4K"}.get(n, "ACE"),
                    "player": index[sid],
                    "detail": f"{n} убийства" if n < 5 else f"{n} убийств",
                })

        # --- Клатчи: проходим по смертям по порядку и следим, кто остался жив ---
        rd = deaths[(deaths["tick"] >= r["start"]) & (deaths["tick"] <= r["end"])].sort_values("tick")
        clutch = None          # (игрок, против скольких, тик)
        for row in rd.itertuples(index=False):
            vi = index.get(str(row.user_steamid))
            if vi is None:
                continue
            alive.discard(vi)
            if clutch:
                continue
            for team in (2, 3):
                mine = [i for i in alive if side.get(i) == team]
                enemies = [i for i in alive if side.get(i) not in (team, None)]
                if len(mine) == 1 and len(enemies) >= 1:
                    clutch = (mine[0], len(enemies), int(row.tick))
                    break

        if clutch:
            player, vs, tick = clutch
            if side_name.get(side.get(player)) == r["winner"]:
                result.append({
                    "round": ri,
                    "tick": tick,
                    "type": f"1v{vs}",
                    "player": player,
                    "detail": f"клатч 1 против {vs}",
                })

    # Сначала самые крутые: ACE, 1v5 ... потом по раунду
    order = {"ACE": 0, "1v5": 1, "1v4": 2, "4K": 3, "1v3": 4, "3K": 5, "1v2": 6, "1v1": 7}
    result.sort(key=lambda h: (order.get(h["type"], 9), h["round"]))
    return result


def is_missing(v) -> bool:
    """Пустое значение (None или NaN)."""
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def num(v) -> int:
    """Число или 0, если значения нет."""
    return 0 if is_missing(v) else int(v)


# Какие буквы ставить для гранат в таблице игроков
NADE_CODES = [
    ("smoke", "s"),
    ("flash", "f"),
    ("high explosive", "h"), ("hegrenade", "h"), ("he grenade", "h"),
    ("molotov", "m"), ("incendiary", "m"),
    ("decoy", "d"),
]


def parse_inventory(inv) -> tuple[str, int]:
    """Из списка предметов игрока делаем строку гранат (например 'sfh') и флаг «несёт бомбу»."""
    if inv is None or isinstance(inv, float):
        return "", 0
    nades, has_bomb = "", 0
    for item in list(inv):
        name = str(item).lower()
        if "c4" in name:
            has_bomb = 1
            continue
        for key, code in NADE_CODES:
            if key in name:
                nades += code
                break
    return "".join(sorted(nades)), has_bomb


def grenade_events(parser: DemoParser) -> list[dict]:
    """Смоки и молотовы (с началом и концом действия), флешки и HE (короткая вспышка)."""
    def safe(event):
        try:
            return drop_warmup(parser.parse_event(event, other=["is_warmup_period"]))
        except Exception:
            return pd.DataFrame()

    result = []
    # Смоки и молотовы: связываем начало и конец по entityid гранаты
    for start_ev, end_ev, kind, default_len in (
        ("smokegrenade_detonate", "smokegrenade_expired", "smoke", 18 * 64),
        ("inferno_startburn", "inferno_expire", "molotov", 7 * 64),
    ):
        starts, ends = safe(start_ev), safe(end_ev)
        end_by_id = {}
        if not ends.empty and "entityid" in ends.columns:
            for row in ends.to_dict("records"):
                end_by_id.setdefault(row["entityid"], []).append(int(row["tick"]))
        for row in starts.to_dict("records"):
            x, y = row.get("x"), row.get("y")
            if is_missing(x) or is_missing(y):
                continue
            t0 = int(row["tick"])
            later = [t for t in end_by_id.get(row.get("entityid"), []) if t > t0]
            result.append({
                "type": kind,
                "start": t0,
                "end": min(later) if later else t0 + default_len,
                "x": round(float(x)),
                "y": round(float(y)),
            })

    # Флешки и HE — показываем вспышку на полсекунды
    for event, kind in (("flashbang_detonate", "flash"), ("hegrenade_detonate", "he")):
        for row in safe(event).to_dict("records"):
            x, y = row.get("x"), row.get("y")
            if is_missing(x) or is_missing(y):
                continue
            t0 = int(row["tick"])
            result.append({"type": kind, "start": t0, "end": t0 + 32,
                           "x": round(float(x)), "y": round(float(y))})
    return result


# Оружие, выстрелы из которого не рисуем (ножи, гранаты, бомба)
NOT_GUNS = ("knife", "bayonet", "grenade", "flashbang", "smoke", "molotov", "incendiary", "decoy", "c4", "taser")


def shot_events(parser: DemoParser) -> list[list]:
    """Все выстрелы: тик, позиция стрелка, угол и его команда."""
    try:
        df = drop_warmup(parser.parse_event("weapon_fire", player=["X", "Y", "yaw", "team_num"],
                                            other=["is_warmup_period"]))
    except Exception:
        return []
    shots = []
    for row in df.to_dict("records"):
        weapon = str(row.get("weapon", "")).lower()
        if any(w in weapon for w in NOT_GUNS):
            continue
        x, y, yaw = row.get("user_X"), row.get("user_Y"), row.get("user_yaw")
        if is_missing(x) or is_missing(y) or is_missing(yaw):
            continue
        shots.append([int(row["tick"]), round(float(x)), round(float(y)), round(float(yaw)), num(row.get("user_team_num"))])
    return shots


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


UTILITY_WEAPONS = ("hegrenade", "inferno", "molotov", "incgrenade")
TRADE_TICKS = 5 * 64      # смерть считается «разменянной», если убийцу убили в течение 5 секунд


def advanced_stats(rounds: list[dict], deaths: pd.DataFrame, kills: pd.DataFrame,
                   enemy_hurts: pd.DataFrame, player_ids: list[str]) -> dict:
    """KAST, первые убийства/смерти, урон гранатами и Rating 1.0 (формула HLTV)."""
    n = max(len(rounds), 1)
    st = {sid: {"kast_rounds": 0, "fk": 0, "fd": 0, "mk": [0] * 6} for sid in player_ids}

    for r in rounds:
        in_round = lambda df: df[(df["tick"] >= r["start"]) & (df["tick"] <= r["end"])]
        rd = in_round(deaths).sort_values("tick")
        rk = in_round(kills)

        # Первая смерть раунда: убийца получает FK, погибший — FD
        first = rk.sort_values("tick").head(1)
        for row in first.itertuples(index=False):
            if row.attacker_steamid in st:
                st[row.attacker_steamid]["fk"] += 1
            if row.user_steamid in st:
                st[row.user_steamid]["fd"] += 1

        # Сколько убийств за раунд у каждого — для мульти-киллов
        for sid, cnt in rk.groupby("attacker_steamid").size().items():
            if sid in st:
                st[sid]["mk"][min(int(cnt), 5)] += 1

        died = set(rd["user_steamid"])
        killed = set(rk["attacker_steamid"])
        assisted = set(rd["assister_steamid"]) if "assister_steamid" in rd.columns else set()

        # Размены: игрока убили, а его убийцу в течение 5 секунд убил кто-то другой
        traded = set()
        rows = list(rd.itertuples(index=False))
        for i, d in enumerate(rows):
            for later in rows[i + 1:]:
                if later.tick - d.tick > TRADE_TICKS:
                    break
                if later.user_steamid == d.attacker_steamid:
                    traded.add(d.user_steamid)
                    break

        for sid in st:
            if sid in killed or sid in assisted or sid not in died or sid in traded:
                st[sid]["kast_rounds"] += 1

    # Урон гранатами по противникам
    util = {}
    if "weapon" in enemy_hurts.columns:
        u = enemy_hurts[enemy_hurts["weapon"].astype(str).str.lower().isin(UTILITY_WEAPONS)]
        util = u.groupby("attacker_steamid")["dmg"].sum().to_dict()

    result = {}
    for sid, s in st.items():
        k = int((kills["attacker_steamid"] == sid).sum())
        d = int((deaths["user_steamid"] == sid).sum())
        mk = s["mk"]
        # Rating 1.0: убийства, выживание и мульти-киллы, нормированные на средние значения
        kill_r = k / n / 0.679
        surv_r = (n - d) / n / 0.317
        multi_r = (mk[1] + 4 * mk[2] + 9 * mk[3] + 16 * mk[4] + 25 * mk[5]) / n / 1.277
        result[sid] = {
            "rating": round((kill_r + 0.7 * surv_r + multi_r) / 2.7, 2),
            "kast": round(s["kast_rounds"] / n * 100),
            "fk": s["fk"],
            "fd": s["fd"],
            "ud": round(float(util.get(sid, 0))),
        }
    return result


def kill_events(rounds: list[dict], deaths: pd.DataFrame, player_ids: list[str]) -> list[list]:
    """Все смерти матча с координатами — для хитмапов и страницы игрока.
    Формат: [раунд, тик, убийца (номер игрока или None), жертва, x убийцы, y убийцы, x жертвы, y жертвы, оружие, хедшот]."""
    index = {sid: i for i, sid in enumerate(player_ids)}

    def coord(v):
        return None if is_missing(v) else round(float(v))

    def round_of(tick):
        for ri, r in enumerate(rounds):
            if r["start"] <= tick <= r["end"]:
                return ri
        return None

    events = []
    for d in deaths.to_dict("records"):
        tick = int(d["tick"])
        ri = round_of(tick)
        vi = index.get(str(d.get("user_steamid")))
        if ri is None or vi is None:
            continue
        ai = index.get(str(d.get("attacker_steamid")))
        # Убийство засчитываем, только если убил противник (не сам себя и не свой)
        if ai == vi or d.get("attacker_team_num") == d.get("user_team_num"):
            ai = None
        events.append([
            ri, tick, ai, vi,
            coord(d.get("attacker_X")), coord(d.get("attacker_Y")),
            coord(d.get("user_X")), coord(d.get("user_Y")),
            str(d.get("weapon") or ""), bool(d.get("headshot")),
        ])
    return events


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

    adv = advanced_stats(rounds, deaths, kills, enemy_hurts, [str(x) for x in players["steamid"]])

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
            **adv.get(sid, {}),
        })

    # Дуэли: duels[убийца][жертва] = сколько раз
    duels: dict[str, dict[str, int]] = {}
    for (att, vic), n in kills.groupby(["attacker_steamid", "user_steamid"]).size().items():
        duels.setdefault(att, {})[vic] = int(n)

    # 2D-реплей: игроки в том же порядке, что и в player_rows
    replay = build_replay(parser, rounds, [p["steamid"] for p in player_rows], kills, deaths)

    return {
        "map": header.get("map_name", "?"),
        "rounds": len(rounds),
        "players": player_rows,
        "duels": duels,
        "replay": replay,
        "kill_events": kill_events(rounds, deaths, [p["steamid"] for p in player_rows]),
    }
