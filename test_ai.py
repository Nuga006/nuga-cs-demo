# Тест AI-разбора и новых эндпоинтов без настоящего Claude и без настоящей базы.
# Запуск:  python -m unittest test_ai -v

import gzip
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import anthropic
from fastapi import HTTPException
from starlette.requests import Request

import app

ME, FOE = "1", "2"


def match(mid: str, kills: int) -> dict:
    return {
        "id": mid, "map": "de_mirage", "rounds": 20,
        "players": [{"steamid": ME, "name": "Nuga", "team": 2, "kills": kills, "deaths": 15, "rating": 1.12},
                    {"steamid": FOE, "name": "Foe", "team": 3, "kills": 15, "deaths": kills, "rating": 0.85}],
        "duels": {ME: {FOE: 7}, FOE: {ME: 4}},
        "kill_events": [[0, 100, 0, 1, 10, 20, 30, 40, "ak47", True], [1, 200, 1, 0, 50, 60, 70, 80, "awp", False]],
    }


def request(steam_id: str | None) -> Request:
    cookie = f"{app.SESSION_COOKIE}={app.make_session(steam_id)}" if steam_id else ""
    return Request({"type": "http", "headers": [(b"cookie", cookie.encode())]})


class FakeClient:
    calls = []

    def __init__(self, *a, **kw):
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        FakeClient.calls.append(kw)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="• Совет")])


class AIReview(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        metas = []
        for mid, kills in (("aaaaaaaaaaaa", 20), ("bbbbbbbbbbbb", 10)):
            with gzip.open(self.tmp / f"{mid}.json.gz", "wt", encoding="utf-8") as f:
                json.dump(match(mid, kills), f)
            metas.append({"id": mid, "map": "de_mirage", "created": 1_700_000_000,
                          "stats": [{"kills": kills, "deaths": 15, "rating": 1.0, "hs": 50, "fk": 2, "fd": 1}]})
            (self.tmp / f"{mid}.meta.json").write_text(json.dumps(metas[-1]), encoding="utf-8")
        FakeClient.calls = []
        self.coins = {"value": 5}
        self.charged = []
        self.patches = [
            mock.patch.object(app, "MATCHES", self.tmp),
            mock.patch.object(app, "list_matches", lambda req: metas),
            mock.patch.object(app, "get_user", lambda sid: {"coins": self.coins["value"]}),
            mock.patch.object(app, "change_coins", lambda sid, d, why: self.charged.append((sid, d))),
            mock.patch.object(anthropic, "Anthropic", FakeClient),
            mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}),
        ]
        for p in self.patches:
            p.start()
        app.AVG_CACHE.update(ts=0)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp)

    def status(self, fn, *args) -> int:
        with self.assertRaises(HTTPException) as e:
            fn(*args)
        return e.exception.status_code

    def test_errors(self):
        self.assertEqual(self.status(app.ai_review, "aaaaaaaaaaaa", request(None), {"player": 0}), 401)
        self.assertEqual(self.status(app.ai_review, "cccccccccccc", request(ME), {"player": 0}), 404)
        self.assertEqual(self.status(app.ai_review, "aaaaaaaaaaaa", request(ME), {"player": 5}), 400)
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            self.assertEqual(self.status(app.ai_review, "aaaaaaaaaaaa", request(ME), {"player": 0}), 503)
        self.coins["value"] = 0
        self.assertEqual(self.status(app.ai_review, "aaaaaaaaaaaa", request(ME), {"player": 0}), 402)
        self.assertEqual(FakeClient.calls, [])

    def test_match_review_charges_once(self):
        out = app.ai_review("aaaaaaaaaaaa", request(ME), {"player": 0, "lang": "ru"})
        self.assertEqual(out, {"text": "• Совет"})
        kw = FakeClient.calls[0]
        self.assertEqual(kw["model"], "claude-opus-5-5")
        facts = json.loads(kw["messages"][0]["content"])
        self.assertEqual(facts["player"], "Nuga")
        self.assertEqual(facts["player_duels"], {"Foe": {"убил": 7, "убит": 4}})
        self.assertEqual(self.charged, [(ME, -app.AI_PRICE)])

        app.ai_review("aaaaaaaaaaaa", request(ME), {"player": 0, "lang": "ru"})   # второй раз — из кэша, бесплатно
        self.assertEqual(len(FakeClient.calls), 1)
        self.assertEqual(len(self.charged), 1)
        app.ai_review("aaaaaaaaaaaa", request(ME), {"player": 0, "lang": "en"})   # другой язык — новый запрос
        self.assertTrue(FakeClient.calls[1]["messages"][0]["content"].endswith("Answer in English."))

    def test_form_review(self):
        out = app.ai_form(request(ME), {"lang": "ru"})
        self.assertEqual(out["matches"], 2)
        facts = json.loads(FakeClient.calls[0]["messages"][0]["content"])
        self.assertEqual([m["kills"] for m in facts["matches"]], [20, 10])
        self.assertEqual(facts["matches"][0]["team_rating"], 1.12)
        self.assertEqual(self.status(app.ai_form, request(FOE + "x"), {}), 400)   # не играл ни в одном матче

    def test_heat_and_averages(self):
        heat = app.my_heat(request(ME), map="de_mirage")
        self.assertEqual(heat, {"kills": [[10, 20]] * 2, "deaths": [[70, 80]] * 2, "matches": 2})   # по точке из каждого матча
        avg = app.site_averages()
        self.assertAlmostEqual(avg["kd"], 30 / 30)
        self.assertAlmostEqual(avg["opening"], 4 / 6 * 100)
        self.assertEqual(avg["players"], 2)


if __name__ == "__main__":
    unittest.main()
