# Тест анализатора: разбираем настоящую демку и сверяем с разбором, сохранённым раньше.
# Запуск:  python -m unittest test_analyzer -v
# Нужны демка в папке CS2 (game/csgo/nuga/<id>.dem) и её разбор в matches/<id>.json.gz.
# Если их нет — тест пропускается. Сверяются только поля из STATS: новые поля разбора тест не ломают.
# Если ты намеренно поменял подсчёт этих полей — разбери матч заново на сайте, и тест снова станет зелёным.

import gzip
import json
import unittest
from pathlib import Path

from analyzer import analyze_demo, drop_warmup, normalize_side, round_stats
import pandas as pd

BASE = Path(__file__).resolve().parent
STATS = ("kills", "deaths", "assists", "hs", "adr", "rating", "kast", "fk", "fd", "k2", "k3", "k4", "k5")


def demo_dir() -> Path | None:
    try:
        import clips3d
        return clips3d.find_cs2(None) / "game" / "csgo" / "nuga"
    except SystemExit:
        return None


class Helpers(unittest.TestCase):
    def test_normalize_side(self):
        self.assertEqual([normalize_side(v) for v in (2, "3", "t", "CT", "TERRORIST", 0)], ["T", "CT", "T", "CT", "T", ""])

    def test_round_stats(self):
        # Игрок 0 за T, игрок 1 за CT. Раунд 0 — пистолетка, раунд 1 — у T эко ($900), у CT полный закуп.
        frame = lambda eq0, eq1: [[0, 0, 1, 2, 100, "", 0, 0, "", 0, 0, eq0], [0, 0, 1, 3, 100, "", 0, 0, "", 0, 0, eq1]]
        data = {"players": [{}, {}], "replay": {"rounds": [
            {"start": 0, "winner": "T", "frames": [frame(800, 800)]},
            {"start": 1000, "winner": "CT", "frames": [frame(900, 5000)]},
        ]}, "kill_events": [
            [0, 640, 0, 1, 0, 0, 0, 0, "glock", False],        # 10 с — T убил CT
            [1, 1000 + 64 * 30, 1, 0, 0, 0, 0, 0, "m4a1", True],   # 30 с — CT убил T
        ]}
        s = round_stats(data)
        self.assertEqual(s[1]["dt"], [1, 0, 0])
        self.assertEqual(s[0]["dt"], [0, 1, 0])
        self.assertEqual(s[0]["side"]["T"], {"r": 2, "k": 1, "d": 1, "w": 1, "fk": 1, "fd": 1})
        self.assertEqual(s[0]["buy"]["eco"]["r"], 1)
        self.assertEqual(s[1]["buy"]["full"], {"r": 1, "k": 1, "d": 0, "w": 1, "fk": 0, "fd": 0})
        self.assertEqual(s[1]["buy"]["pistol"]["d"], 1)

    def test_drop_warmup(self):
        df = pd.DataFrame({"tick": [1, 2, 3], "is_warmup_period": [True, None, False]})
        self.assertEqual(list(drop_warmup(df)["tick"]), [2, 3])


class SavedMatches(unittest.TestCase):
    def test_matches_saved_analysis(self):
        folder = demo_dir()
        pairs = []
        for saved in sorted((BASE / "matches").glob("*.json.gz")):
            mid = saved.name.split(".")[0]
            dem = folder / f"{mid}.dem" if folder else None
            if dem and dem.exists():
                pairs.append((dem, saved))
        if not pairs:
            self.skipTest("нет пары демка + сохранённый разбор")

        dem, saved = min(pairs, key=lambda p: p[0].stat().st_size)   # самая маленькая — быстрее
        want = json.loads(gzip.open(saved).read())

        got = analyze_demo(dem)
        self.assertEqual(got["map"], want["map"])
        self.assertEqual(got["rounds"], want["rounds"])
        self.assertEqual(got["duels"], want["duels"])
        want_players = {p["steamid"]: p for p in want["players"]}
        self.assertEqual(set(p["steamid"] for p in got["players"]), set(want_players))
        for p in got["players"]:
            for key in STATS:
                with self.subTest(player=p["name"], stat=key):
                    self.assertEqual(p.get(key), want_players[p["steamid"]].get(key))


if __name__ == "__main__":
    unittest.main()
