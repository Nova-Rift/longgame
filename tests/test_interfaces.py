"""The ways in: command line, JSON-lines protocol, browser player server, terminal, Gymnasium and ARC bridges."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import longgame
from longgame import Action, arc, baselines, protocol
from longgame.cli import main

SRC = str(Path(__file__).resolve().parents[1] / "src")


class TempHome(unittest.TestCase):
    """Keeps saved progress and recordings in a temporary folder."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("LONGGAME_HOME")
        os.environ["LONGGAME_HOME"] = self._tmp.name
        self.home = Path(self._tmp.name)

    def tearDown(self):
        if self._old is None:
            os.environ.pop("LONGGAME_HOME", None)
        else:
            os.environ["LONGGAME_HOME"] = self._old
        self._tmp.cleanup()


class TestCommandLine(TempHome):
    def run_cli(self, *args):
        env = {**os.environ, "PYTHONPATH": SRC + os.pathsep + os.environ.get("PYTHONPATH", "")}
        return subprocess.run([sys.executable, "-m", "longgame", *args], capture_output=True, text=True, env=env,
                              timeout=300)

    def test_run_record_verify(self):
        rec = self.home / "r.jsonl"
        out = self.run_cli("run", "random", "--arg", "seed=4", "--record", str(rec))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("overall", out.stdout)
        out = self.run_cli("verify", str(rec))
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(out.stdout.startswith("VERIFIED"))
        rec.write_text(rec.read_text().replace('"cleared":false', '"cleared":true', 1))
        out = self.run_cli("verify", str(rec))
        self.assertEqual(out.returncode, 1)

    def test_list_version_and_errors(self):
        out = self.run_cli("list")
        self.assertIn("practice-v0", out.stdout)
        self.assertIn(longgame.__version__, self.run_cli("--version").stdout)
        for args, message in ((["run", "nobody"], "Unknown agent"), (["run", "random", "--arg", "bogus=1"], "Cannot create"),
                              (["run", "nofile.py:X"], "No such file"), (["run", "longgame:Nope"], "has no 'Nope'"),
                              (["run", "not_a_module:X"], "Cannot import")):
            out = self.run_cli(*args)
            self.assertEqual(out.returncode, 2, args)
            self.assertIn(message, out.stderr)
            self.assertNotIn("Traceback", out.stderr)

    def test_check_a_lifetime_file(self):
        self.assertEqual(self.run_cli("check", "practice-v0").returncode, 0)
        bad = self.home / "bad.json"
        bad.write_text(json.dumps({"id": "bad", "visits": [{"world": "X", "phase": "learn", "levels": [
            {"par": 3, "map": ["#####", "#@.E#", "#####"]}, {"par": 1, "map": ["#####", "#@#E#", "#####"]}]}]}))
        out = self.run_cli("check", str(bad))
        self.assertEqual(out.returncode, 1)
        self.assertIn("par is 3 but the fewest actions is 2", out.stdout)
        self.assertIn("cannot be finished", out.stdout)

    def test_run_a_file_agent(self):
        agent = self.home / "mine.py"
        agent.write_text("from longgame import Agent, Action\n"
                         "class Mine(Agent):\n    name = 'mine'\n    def act(self, obs):\n        return Action.USE\n")
        out = self.run_cli("run", f"{agent}:Mine", "--max-actions", "50", "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout)["played"], 0)

    def test_main_in_process(self):
        buf = io.StringIO()
        old, sys.stdout = sys.stdout, buf
        try:
            self.assertEqual(main(["run", "solver"]), 0)
        finally:
            sys.stdout = old
        self.assertIn("overall 100.0%", buf.getvalue())


class TestProtocol(unittest.TestCase):
    def talk(self, *messages):
        stdin = io.StringIO("".join((m if isinstance(m, str) else json.dumps(m)) + "\n" for m in messages))
        stdout = io.StringIO()
        protocol.serve(stdin=stdin, stdout=stdout)
        return [json.loads(line) for line in stdout.getvalue().splitlines()]

    def test_reset_step_score(self):
        reset, step, named, bad, nojson, score, lts = self.talk(
            {"cmd": "reset"}, {"cmd": "step", "action": 4}, {"cmd": "step", "action": "up"},
            {"cmd": "step", "action": 6}, "not json", {"cmd": "score"}, {"cmd": "lifetimes"})
        self.assertEqual(reset["observation"]["world"], "A")
        self.assertEqual(step["observation"]["actions"], 1)
        self.assertIsNone(step["observation"]["result"])
        self.assertEqual(named["observation"]["actions"], 2)
        self.assertIn("not available", bad["error"])
        self.assertIn("error", nojson)
        self.assertEqual(score["scorecard"]["total"], 28)
        self.assertIn("practice-v0", lts["lifetimes"])
        early, nocmd = self.talk({"cmd": "step", "action": 1}, {"action": 1})
        self.assertIn('"reset"', early["error"])
        self.assertIn('needs "cmd"', nocmd["error"])

    def test_make_switches_lifetime(self):
        tiny = {"id": "tiny", "visits": [{"world": "X", "phase": "learn",
                                          "levels": [{"par": 1, "map": ["####", "#@E#", "####"]}]}]}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "tiny.json"
            path.write_text(json.dumps(tiny))
            ok, reset, step = self.talk({"cmd": "make", "lifetime": str(path)}, {"cmd": "reset"},
                                        {"cmd": "step", "action": "right"})
        self.assertEqual(ok, {"ok": True})
        self.assertEqual(reset["observation"]["lifetime"], "tiny")
        self.assertTrue(step["observation"]["done"])
        self.assertEqual(step["observation"]["result"]["score"], 1.0)


class TestBrowserPlayer(TempHome):
    def test_page_state_steps_token_and_resume(self):
        from longgame.webplay import start_server
        server, url, session = start_server(port=0)
        try:
            page = urllib.request.urlopen(url).read().decode()
            token = page.split('name="longgame-token" content="')[1].split('"')[0]
            self.assertGreater(len(token), 16)
            for asset in ("player.js", "player.css", "favicon.svg"):
                self.assertEqual(urllib.request.urlopen(url + "static/" + asset).status, 200)

            def call(path, body=None, tok=token):
                req = urllib.request.Request(url + path.lstrip("/"), method="POST" if body is not None else "GET",
                                             data=json.dumps(body).encode() if body is not None else None,
                                             headers={"X-Longgame-Token": tok, "Content-Type": "application/json"})
                return json.loads(urllib.request.urlopen(req).read())

            with self.assertRaises(urllib.error.HTTPError) as no:
                call("/api/state", tok="wrong")
            self.assertEqual(no.exception.code, 403)
            state = call("/api/state")
            self.assertEqual(state["observation"]["world"], "A")
            self.assertIn("random", state["baselines"])
            state = call("/api/step", {"action": 4})
            self.assertEqual((state["observation"]["actions"], state["moves"]), (1, 1))
            with self.assertRaises(urllib.error.HTTPError) as bad:
                call("/api/step", {"action": 7})
            self.assertEqual(bad.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
        saved = json.loads((self.home / "progress" / "practice-v0.json").read_text())
        self.assertEqual(saved["actions"], [4])
        server, url, session = start_server(port=0)  # resumes
        try:
            self.assertEqual(session.env.history, [4])
            session.start_over()
            self.assertEqual(session.env.history, [])
        finally:
            server.shutdown()
            server.server_close()

    def test_finishing_writes_a_verifiable_recording(self):
        from longgame.agents.solver import SolverAgent
        from longgame.webplay import Session
        session = Session(longgame.load_spec("practice-v0"), fresh=True)
        agent = SolverAgent()
        while not session.env.done:
            session.step(agent.act(session.env.observe()))
        self.assertIsNotNone(session.recording)
        report = longgame.verify(session.recording)
        self.assertTrue(report.ok, report.problems)
        self.assertEqual((report.agent, report.scorecard.overall), ("human", 1.0))


class TestTerminal(TempHome):
    def test_keys_play_and_quit_saves(self):
        from longgame.terminal import play_in_terminal
        out = io.StringIO()
        code = play_in_terminal(keys=iter(["d", "\x1b[C", "x", "e", "q"]), color=False, out=out)
        self.assertEqual(code, 0)
        self.assertIn("world A", out.getvalue())
        saved = json.loads((self.home / "progress" / "practice-v0.json").read_text())
        self.assertEqual(saved["actions"], [4, 4, 5])


class TestBridges(unittest.TestCase):
    def test_arc_frame_data(self):
        env = longgame.make()
        fd = arc.frame_data(env.reset())
        self.assertEqual(len(fd["frame"]), 1)
        self.assertEqual((len(fd["frame"][0]), len(fd["frame"][0][0])), (64, 64))
        self.assertEqual(fd["frame"][0][0][:7], [1] * 7)
        self.assertEqual(fd["available_actions"], [0, 1, 2, 3, 4, 5])
        self.assertEqual((fd["state"], fd["levels_completed"], fd["win_levels"]), ("NOT_FINISHED", 0, 2))
        with self.assertRaises(ValueError):
            arc.pad([[0] * 70], 64)
        from longgame.agents.solver import SolverAgent
        tiny = {"id": "t", "visits": [{"world": "X", "phase": "learn", "levels": [
            {"par": 1, "map": ["####", "#@E#", "####"]}, {"par": 1, "map": ["####", "#@E#", "####"]}]}]}
        won = longgame.make(tiny)
        obs = won.reset()
        while not obs.done:
            obs = won.step(SolverAgent().act(obs))
        self.assertEqual((arc.frame_data(obs)["state"], arc.frame_data(obs)["levels_completed"]), ("WIN", 2))
        lost = longgame.make(tiny)
        obs = lost.reset()
        while not obs.done:
            obs = lost.step(Action.USE)
        self.assertEqual((arc.frame_data(obs)["state"], arc.frame_data(obs)["frame"], obs.cleared), ("GAME_OVER", [], 0))

    @unittest.skipUnless(__import__("importlib").util.find_spec("gymnasium"), "gymnasium not installed")
    def test_gymnasium(self):
        import gymnasium as gym
        import longgame.gym  # noqa: F401 (registers)
        env = gym.make("LongGame/practice-v0")
        obs, info = env.reset(seed=0)
        self.assertEqual(obs.shape, (11, 11))
        self.assertEqual(info["world"], "A")
        self.assertTrue(env.observation_space.contains(obs))
        from longgame.agents.solver import SolverAgent
        agent, total, done = SolverAgent(), 0.0, False
        lifetime = env.unwrapped._env
        while not done:
            obs, reward, done, truncated, info = env.step(int(agent.act(lifetime.observe())))
            total += reward
        self.assertAlmostEqual(total, 1.0, places=9)  # the return is the lifetime score
        self.assertEqual(info["scorecard"]["overall"], 1.0)
        env = gym.make("LongGame/practice-v0")
        env.reset()
        total, done = 0.0, False
        rand = __import__("random").Random(5)
        while not done:
            obs, reward, done, truncated, info = env.step(rand.randrange(1, 6))
            total += reward
        self.assertAlmostEqual(total, info["scorecard"]["overall"], places=9)
        big = longgame.gym.LongGameEnv(size=64)
        self.assertEqual(big.reset()[0].shape, (64, 64))

    @unittest.skipUnless(__import__("importlib").util.find_spec("gymnasium"), "gymnasium not installed")
    def test_gymnasium_generated_family(self):
        import gymnasium as gym
        import longgame.gym  # noqa: F401 (registers)
        from gymnasium.utils.env_checker import check_env
        env = gym.make("LongGame/heldout-v1")
        obs, info = env.reset(seed=7)
        self.assertEqual((obs.shape, info["lifetime"]), ((12, 12), "heldout-v1-7"))
        obs2, info2 = env.reset(seed=7)  # the same seed is the same lifetime
        self.assertTrue((obs == obs2).all())
        self.assertEqual(env.unwrapped.scorecard().total, 28)
        drawn = [env.reset()[1]["lifetime"] for _ in range(2)]  # unseeded: drawn by the seeded generator
        env.reset(seed=7)
        self.assertEqual([env.reset()[1]["lifetime"] for _ in range(2)], drawn)
        self.assertEqual(len(set(drawn)), 2)
        self.assertEqual(env.reset(seed=2 ** 31 - 1)[1]["lifetime"], f"heldout-v1-{(2 ** 31 - 1) % 10 ** 9}")
        a, b = (longgame.gym.LongGameEnv("train-v1") for _ in range(2))
        self.assertNotEqual(a.reset()[1]["lifetime"], b.reset()[1]["lifetime"])  # unseeded copies differ
        with self.assertRaises(RuntimeError):
            longgame.gym.LongGameEnv("train-v1").step(1)
        check_env(longgame.gym.LongGameEnv("train-v1"), skip_render_check=True)
        self.assertEqual(longgame.gym.LongGameEnv("train-v1", size=64).reset(seed=3)[0].shape, (64, 64))


class TestBaselines(unittest.TestCase):
    def test_the_shipped_baselines_are_current(self):
        shipped = json.loads(baselines.path().read_text())
        self.assertEqual(shipped, baselines.compute(seeds=20, generated=10))
        self.assertLess(shipped["practice-v0"]["random"]["overall"], 0.05)
        self.assertEqual(shipped["heldout-v1"]["explorer"]["runs"], 10)


if __name__ == "__main__":
    unittest.main()
