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
        return "до 1-го раунда"
    for r in rounds:
        if r["start"] <= tick <= r["end"]:
            return "в раунде"
    return "после конца раунда"


deaths["phase"] = deaths["tick"].map(phase)
enemy = (deaths["attacker_steamid"] != deaths["user_steamid"]) & (deaths["attacker_team_num"] != deaths["user_team_num"])
flash = deaths["assistedflash"].fillna(False).astype(bool) if "assistedflash" in deaths.columns else pd.Series(False, index=deaths.index)

print("\nВсего событий по периодам:")
print(deaths["phase"].value_counts().to_string())

print(f"\n{'Игрок':<18}{'K в раунде':>11}{'K вне':>7}{'D в раунде':>11}{'D вне':>7}{'A':>4}{'A флеш':>8}")
for sid, name in names.items():
    k = deaths[enemy & (deaths["attacker_steamid"] == sid)]
    d = deaths[deaths["user_steamid"] == sid]
    a = deaths[deaths["assister_steamid"] == sid]
    if k.empty and d.empty:
        continue
    print(f"{name[:17]:<18}{(k.phase == 'в раунде').sum():>11}{(k.phase != 'в раунде').sum():>7}"
          f"{(d.phase == 'в раунде').sum():>11}{(d.phase != 'в раунде').sum():>7}"
          f"{len(a):>4}{int(flash[a.index].sum()):>8}")
