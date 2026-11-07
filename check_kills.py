# Проверка: откуда в разборе лишние убийства/ассисты по сравнению с FACEIT.
# Запуск:  python check_kills.py путь\к\демке.dem.zst
# Печатает для каждого игрока K / D / A, разложенные по периодам матча.

import sys
from pathlib import Path

import pandas as pd
from demoparser2 import DemoParser

from analyzer import build_rounds, drop_warmup, prepare_demo

dem = prepare_demo(Path(sys.argv[1]))
parser = DemoParser(str(dem))
rounds = build_rounds(parser)
print(f"Раундов найдено: {len(rounds)}")
if not rounds:
    sys.exit("Раунды не найдены")

deaths = drop_warmup(parser.parse_event("player_death", player=["team_num"], other=["is_warmup_period"]))
for col in ("attacker_steamid", "user_steamid", "assister_steamid"):
    if col in deaths.columns:
        deaths[col] = deaths[col].astype(str)
names = {str(r.steamid): r.name for r in parser.parse_player_info().itertuples()}


def phase(tick: int) -> str:
    if tick < rounds[0]["start"]:
        return "pre"
    for r in rounds:
        if r["start"] <= tick <= r["end"]:
            return "in"
    return "post"


deaths["phase"] = deaths["tick"].map(phase)
same = deaths["attacker_team_num"] == deaths["user_team_num"]
self_kill = deaths["attacker_steamid"] == deaths["user_steamid"]
enemy = ~same & ~self_kill
flash = deaths["assistedflash"].fillna(False).astype(bool) if "assistedflash" in deaths.columns else pd.Series(False, index=deaths.index)

print("pre = до 1-го раунда, in = внутри раунда, post = после конца раунда")
print("TK = убил своего, byTM = умер от своего, A_fl = флеш-ассисты, A_TK = ассист при убийстве своего\n")
cols = ["K_pre", "K_in", "K_post", "TK", "D_pre", "D_in", "D_post", "byTM", "A_pre", "A_in", "A_post", "A_fl", "A_TK"]
print(f"{'Игрок':<16}" + "".join(f"{c:>7}" for c in cols))
for sid, name in names.items():
    k = deaths[enemy & (deaths["attacker_steamid"] == sid)]
    d = deaths[deaths["user_steamid"] == sid]
    a = deaths[deaths["assister_steamid"] == sid]
    if k.empty and d.empty:
        continue
    vals = [(k.phase == "pre").sum(), (k.phase == "in").sum(), (k.phase == "post").sum(),
            (same & ~self_kill & (deaths["attacker_steamid"] == sid)).sum(),
            (d.phase == "pre").sum(), (d.phase == "in").sum(), (d.phase == "post").sum(),
            (same[d.index] & ~self_kill[d.index]).sum(),
            (a.phase == "pre").sum(), (a.phase == "in").sum(), (a.phase == "post").sum(),
            int(flash[a.index].sum()), int(same[a.index].sum())]
    print(f"{name[:15]:<16}" + "".join(f"{int(v):>7}" for v in vals))
