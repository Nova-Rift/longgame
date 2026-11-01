"""Forged or malformed input must be reported cleanly, never trusted and never crash (from the pre-release review)."""

import http.client
import io
import json
import math
import os
import tempfile
import unittest
from pathlib import Path

import longgame
from longgame import Action, InvalidAction, evaluate, protocol, verify
from longgame.agents.random_agent import RandomAgent
from longgame.agents.solver import SolverAgent

TINY = {"id": "tiny", "phases": ["learn"], "visits": [
    {"world": "X", "phase": "learn", "levels": [{"par": 1, "map": ["####", "#@E#", "####"]}]}]}


class Recorded(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.path = self.dir / "run.jsonl"
        evaluate(RandomAgent(seed=7), record=self.path)
        self.rows = [json.loads(x) for x in self.path.read_text().splitlines()]

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rows):
        self.path.write_text("".join((r if isinstance(r, str) else json.dumps(r)) + "\n" for r in rows))
        return verify(self.path)


class TestForgedRecordings(Recorded):
    def test_a_recording_cannot_bring_its_own_levels(self):
        easy = {"id": "practice-v0", "phases": ["learn"], "visits": [
            {"world": "A", "phase": "learn", "levels": [{"par": 1, "map": ["####", "#@E#", "####"]}] * 28}]}
        spec = longgame.load_spec(easy)
        for forged in (easy, str(self.dir / "easy.json")):
            (self.dir / "easy.json").write_text(json.dumps(easy))
            head = {**self.rows[0], "lifetime": forged, "digest": spec.digest}
            levels = [{"type": "level", "visit": 0, "level": i, "world": "A", "phase": "learn", "par": 1,
                       "actions": [4], "cleared": True, "score": 1.0} for i in range(28)]
            report = self.write([head, *levels])
            self.assertFalse(report.ok)
            self.assertIn("does not ship", report.problems[0])

    def test_malformed_lines_are_problems_not_crashes(self):
        level, end = self.rows[1], self.rows[-1]
        cases = {
            "not an object": [self.rows[0], "[1, 2]"],
            "null lifetime": [{**self.rows[0], "lifetime": None}],
            "numeric lifetime": [{**self.rows[0], "lifetime": 5}],
            "null score": [self.rows[0], {**level, "score": None}],
            "text score": [self.rows[0], {**level, "score": "x"}],
            "nan score": [self.rows[0], {**level, "score": math.nan}],
            "actions not a list": [self.rows[0], {**level, "actions": 5}],
            "bad action": [self.rows[0], {**level, "actions": [{"a": 1}]}],
            "null overall": [*self.rows[:-1], {**end, "overall": None}],
            "nan overall": [*self.rows[:-1], {**end, "overall": math.nan}],
            "wrong phases": [*self.rows[:-1], {**end, "phases": {"learn": 1.0}}],
            "wrong played": [*self.rows[:-1], {**end, "played": 3}],
        }
        for name, rows in cases.items():
            with self.subTest(name):
                report = self.write(rows)
                self.assertFalse(report.ok)
                self.assertTrue(report.problems)

    def test_actions_moved_between_lines_are_caught(self):
        rows = [dict(r) for r in self.rows]
        first, second = rows[1], rows[2]
        second["actions"] = first["actions"][-3:] + second["actions"]
        first["actions"] = first["actions"][:-3]
        report = self.write(rows)
        self.assertFalse(report.ok)
        rows = [dict(r) for r in self.rows]
        rows[1]["actions"] = rows[1]["actions"] + rows[2]["actions"][:2]
        rows[2]["actions"] = rows[2]["actions"][2:]
        self.assertFalse(self.write(rows).ok)

    def test_the_untouched_recording_still_verifies(self):
        self.assertTrue(verify(self.path).ok)


class TestLifetimeFiles(unittest.TestCase):
    def test_bad_lifetimes_raise_value_errors(self):
        bad = [
            {"visits": TINY["visits"]},                                      # no id
            {"id": "x", "visits": []},                                       # no visits
            {"id": "x", "visits": [{"world": "X", "phase": "learn", "levels": []}]},
            {"id": "x", "visits": [{"world": "X", "phase": "learn", "levels": [{"par": -5, "map": ["####", "#@E#", "####"]}]}]},
            {"id": "x", "visits": [{"world": "X", "phase": "learn", "levels": [{"par": 1, "map": ["###", "#@E#", "####"]}]}]},
            {"id": "x", "visits": [{"world": "X", "phase": "learn", "levels": [{"par": 1, "map": "#@E#"}]}]},
            {"id": "x", "budget": {"minimum": 0}, "visits": TINY["visits"]},
            {"id": "x", "visits": [{"phase": "learn", "levels": TINY["visits"][0]["levels"]}]},
            ["not", "a", "dict"],
        ]
        for d in bad:
            with self.subTest(d=str(d)[:60]):
                with self.assertRaises(ValueError):
                    longgame.load_spec(d) if isinstance(d, dict) else longgame.LifetimeSpec.from_dict(d)


class TestActionsAndProtocol(unittest.TestCase):
    def test_integer_likes_are_actions(self):
        np = __import__("numpy")
        self.assertIs(Action.coerce(np.int64(4)), Action.RIGHT)
        env = longgame.make()
        env.reset()
        self.assertEqual(env.step(np.int32(4)).actions, 1)
        for bad in (None, 2.0, [1], np.float64(1.0)):
            with self.assertRaises(InvalidAction):
                Action.coerce(bad)

    def test_a_failed_make_leaves_the_game_running(self):
        with tempfile.TemporaryDirectory() as d:
            rec = Path(d) / "p.jsonl"
            lines = [{"cmd": "reset"}, {"cmd": "make", "lifetime": "typo"}] + [{"cmd": "step", "action": 5}] * 201
            out = io.StringIO()
            protocol.serve(record=str(rec), stdin=io.StringIO("".join(json.dumps(m) + "\n" for m in lines)),
                           stdout=out)
            replies = [json.loads(x) for x in out.getvalue().splitlines()]
            self.assertIn("Unknown lifetime", replies[1]["error"])
            self.assertTrue(all("observation" in r for r in replies[2:]), [r for r in replies[2:] if "error" in r][:2])
            self.assertEqual(replies[201]["observation"]["result"]["actions"], 200)
            self.assertEqual(replies[202]["observation"]["level"], 1)
            self.assertEqual(len(rec.read_text().splitlines()), 2)  # start + the one finished level


class TestPlayerServer(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("LONGGAME_HOME")
        os.environ["LONGGAME_HOME"] = self._tmp.name
        from longgame.webplay import start_server
        self.server, self.url, self.session = start_server(port=0, fresh=True)
        self.port = self.server.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        conn.request("GET", "/")
        page = conn.getresponse().read().decode()
        self.token = page.split('name="longgame-token" content="')[1].split('"')[0]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        if self._old is None:
            os.environ.pop("LONGGAME_HOME", None)
        else:
            os.environ["LONGGAME_HOME"] = self._old
        self._tmp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        hdrs = {"Host": f"127.0.0.1:{self.port}", "X-Longgame-Token": self.token, **(headers or {})}
        data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else b"")
        hdrs.setdefault("Content-Length", str(len(data)))
        for k, v in hdrs.items():
            conn.putheader(k, v)
        conn.endheaders(data)
        res = conn.getresponse()
        return res.status, res.read()

    def test_bad_requests_get_clean_errors(self):
        self.assertEqual(self.request("GET", "/api/state")[0], 200)
        self.assertEqual(self.request("GET", "/", headers={"Host": "evil.example:80"})[0], 403)
        self.assertEqual(self.request("POST", "/api/step", {"action": 1}, {"Host": "evil.example"})[0], 403)
        self.assertEqual(self.request("GET", "/api/state", headers={"X-Longgame-Token": "tök€n".encode()})[0], 403)
        self.assertEqual(self.request("POST", "/api/step", [1])[0], 400)
        self.assertEqual(self.request("POST", "/api/step", None, {"Content-Length": "-1"})[0], 400)
        self.assertEqual(self.request("POST", "/api/step", {"action": 1})[0], 200)
        self.assertEqual(self.session.env.history, [1])


class TestSolverOnFileLifetime(unittest.TestCase):
    def test_file_lifetime_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            life, rec = Path(d) / "tiny.json", Path(d) / "r.jsonl"
            life.write_text(json.dumps(TINY))
            evaluate(SolverAgent(), lifetime=str(life), record=rec)
            self.assertFalse(verify(rec).ok)
            self.assertTrue(verify(rec, lifetime=str(life)).ok)


if __name__ == "__main__":
    unittest.main()
