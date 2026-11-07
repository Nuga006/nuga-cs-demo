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
names = {}
for r in parser.parse_player_info().itertuples():
    names.setdefault(str(r.steamid), r.name)
for col, ncol in (("attacker_steamid", "attacker_name"), ("user_steamid", "user_name")):
    if ncol in deaths.columns:
        for sid, nm in zip(deaths[col], deaths[ncol]):
            if sid not in ("None", "nan", "0"):
                names.setdefault(sid, str(nm))


def phase(tick: int) -> str:
    if tick < rounds[0]["start"]:
        return "pre"
    for r in rounds:
        if r["start"] <= tick <= r["end"]:
            return "in"
    return "end" if tick > rounds[-1]["end"] else "post"


deaths["phase"] = deaths["tick"].map(phase)
same = deaths["attacker_team_num"] == deaths["user_team_num"]
self_kill = deaths["attacker_steamid"] == deaths["user_steamid"]
enemy = ~same & ~self_kill
flash = deaths["assistedflash"].fillna(False).astype(bool) if "assistedflash" in deaths.columns else pd.Series(False, index=deaths.index)

print("pre = до 1-го раунда, in = внутри раунда, post = после конца раунда, end = после конца матча")
print("TK = убил своего, byTM = умер от своего, A_fl = флеш-ассисты, A_TK = ассист при убийстве своего\n")
cols = ["K_pre", "K_in", "K_post", "K_end", "TK", "D_pre", "D_in", "D_post", "D_end", "byTM", "A_pre", "A_in", "A_post", "A_fl", "A_TK"]
print(f"{'Игрок':<16}" + "".join(f"{c:>7}" for c in cols))
for sid, name in names.items():
    k = deaths[enemy & (deaths["attacker_steamid"] == sid)]
    d = deaths[deaths["user_steamid"] == sid]
    a = deaths[deaths["assister_steamid"] == sid]
    if k.empty and d.empty:
        continue
    vals = [(k.phase == "pre").sum(), (k.phase == "in").sum(), (k.phase == "post").sum(), (k.phase == "end").sum(),
            (same & ~self_kill & (deaths["attacker_steamid"] == sid)).sum(),
            (d.phase == "pre").sum(), (d.phase == "in").sum(), (d.phase == "post").sum(), (d.phase == "end").sum(),
            (same[d.index] & ~self_kill[d.index]).sum(),
            (a.phase == "pre").sum(), (a.phase == "in").sum(), (a.phase == "post").sum(),
            int(flash[a.index].sum()), int(same[a.index].sum())]
    print(f"{name[:15]:<16}" + "".join(f"{int(v):>7}" for v in vals))

# Каждое убийство вне раунда: после какого раунда и через сколько секунд после его конца
print("\nУбийства вне раунда:")
out = deaths[deaths["phase"].isin(["pre", "post", "end"])]
for e in out.itertuples(index=False):
    prev = [i for i, r in enumerate(rounds) if r["end"] < e.tick]
    after = f"после раунда {prev[-1] + 1} (+{(e.tick - rounds[prev[-1]]['end']) / 64:.1f} с)" if prev else "до 1-го раунда"
    att, vic = names.get(e.attacker_steamid, e.attacker_steamid), names.get(e.user_steamid, e.user_steamid)
    print(f"  {att} -> {vic}  [{getattr(e, 'weapon', '?')}]  {after}  ({e.phase})")
print(f"Всего раундов: {len(rounds)}, смена сторон после раунда 12")
