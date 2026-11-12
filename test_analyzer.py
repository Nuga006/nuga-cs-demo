# Тест анализатора: разбираем настоящую демку и сверяем с разбором, сохранённым раньше.
# Запуск:  python -m unittest test_analyzer -v
# Нужны демка в папке CS2 (game/csgo/nuga/<id>.dem) и её разбор в matches/<id>.json.gz.
# Если их нет — тест пропускается. После намеренного изменения подсчёта подними ANALYZER_VERSION в app.py:
# старые разборы станут «устаревшими», и тест их пропустит, пока матч не разберут заново.

import gzip
import json
import re
import unittest
from pathlib import Path

from analyzer import analyze_demo, drop_warmup, normalize_side
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

    def test_drop_warmup(self):
        df = pd.DataFrame({"tick": [1, 2, 3], "is_warmup_period": [True, None, False]})
        self.assertEqual(list(drop_warmup(df)["tick"]), [2, 3])


class SavedMatches(unittest.TestCase):
    def test_matches_saved_analysis(self):
        folder = demo_dir()
        version = int(re.search(r"^ANALYZER_VERSION\s*=\s*(\d+)", (BASE / "app.py").read_text(encoding="utf-8"), re.M)[1])
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
        if want.get("analyzer_version") != version:
            self.skipTest(f"{saved.name} разобран версией {want.get('analyzer_version')}, текущая {version}")

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
