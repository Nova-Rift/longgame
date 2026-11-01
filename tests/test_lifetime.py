"""Lifetimes, actions, scoring, recordings and the built-in agents."""

import json
import tempfile
import unittest
from pathlib import Path

import longgame
from longgame import Action, InvalidAction, evaluate, make, replay, verify
from longgame.agents.explorer import ExplorerAgent
from longgame.agents.random_agent import RandomAgent
from longgame.agents.solver import SolverAgent

TINY = {"id": "tiny", "phases": ["learn"], "visits": [
    {"world": "X", "phase": "learn", "levels": [{"par": 4, "map": ["######", "#@$o.#", "#...E#", "######"]}]}]}


class TestActions(unittest.TestCase):
    def test_ids_match_arc_agi_3(self):
        self.assertEqual([int(a) for a in (Action.RESET, Action.ACTION1, Action.ACTION2, Action.ACTION3,
                                           Action.ACTION4, Action.ACTION5, Action.ACTION6, Action.ACTION7)],
                         list(range(8)))
        self.assertIs(Action.ACTION1, Action.UP)
        self.assertIs(Action.ACTION4, Action.RIGHT)

    def test_coerce_accepts_ids_names_and_aliases(self):
        self.assertIs(Action.coerce(3), Action.LEFT)
        self.assertIs(Action.coerce("up"), Action.UP)
        self.assertIs(Action.coerce("ACTION5"), Action.USE)
        self.assertIs(Action.coerce("restart"), Action.RESET)
        for bad in (8, -1, "jump", 1.5, True):
            with self.assertRaises(InvalidAction):
                Action.coerce(bad)


class TestLifetime(unittest.TestCase):
    def test_first_observation(self):
        env = make()
        obs = env.reset()
        self.assertEqual((obs.world, obs.phase, obs.visit, obs.level, obs.levels), ("A", "learn", 0, 0, 2))
        self.assertEqual((obs.actions, obs.budget, obs.played, obs.total, obs.done), (0, 200, 0, 28, False))
        self.assertEqual(len(obs.grid), 6)
        self.assertEqual(obs.available_actions, [Action.RESET, Action.UP, Action.DOWN, Action.LEFT, Action.RIGHT,
                                                 Action.USE])
        json.dumps(obs.to_dict())

    def test_step_needs_reset_and_rejects_unavailable_actions_for_free(self):
        env = make()
        with self.assertRaises(RuntimeError):
            env.step(Action.UP)
        env.reset()
        for bad in (Action.CLICK, Action.UNDO, 9):
            with self.assertRaises(InvalidAction):
                env.step(bad)
        self.assertEqual(env.observe().actions, 0)

    def test_every_action_counts_and_the_level_score_is_par_over_actions(self):
        env = make(TINY)
        env.reset()
        for a in (Action.USE, Action.RIGHT, Action.DOWN, Action.RIGHT):
            self.assertIsNone(env.step(a).result)
        obs = env.step(Action.RIGHT)
        self.assertEqual((obs.result.cleared, obs.result.actions, obs.result.score), (True, 5, 0.8))
        self.assertTrue(obs.done)
        self.assertEqual(obs.grid, [])
        with self.assertRaises(RuntimeError):
            env.step(Action.UP)

    def test_running_out_of_budget_scores_zero_and_moves_on(self):
        env = make()
        env.reset()
        for _ in range(199):  # level A1: par 10, budget max(100, 20 x 10) = 200
            self.assertIsNone(env.step(Action.USE).result)
        obs = env.step(Action.USE)
        self.assertEqual((obs.result.cleared, obs.result.score, obs.level, obs.actions), (False, 0.0, 1, 0))

    def test_scores_per_phase_and_overall(self):
        card = evaluate(SolverAgent())
        self.assertEqual(card.phases, {"learn": 1.0, "remix": 1.0, "return": 1.0})
        self.assertEqual((card.overall, card.played, card.total, card.complete), (1.0, 28, 28, True))
        self.assertEqual(longgame.level_score(10, 40, True), 0.25)
        self.assertEqual(longgame.level_score(10, 5, True), 1.0)
        self.assertEqual(longgame.level_score(10, 5, False), 0.0)
        empty = make().scorecard()
        self.assertEqual((empty.overall, empty.played, empty.total), (0.0, 0, 28))

    def test_replay_rebuilds_a_lifetime_from_its_actions(self):
        env = make()
        env.reset()
        agent = RandomAgent(seed=3)
        obs = env.observe()
        for _ in range(500):
            obs = env.step(agent.act(obs))
        again = replay(env.history)
        self.assertEqual(again.results, env.results)
        self.assertEqual(again.observe(), env.observe())

    def test_reset_starts_over(self):
        env = make()
        env.reset()
        env.step(Action.RIGHT)
        obs = env.reset()
        self.assertEqual((obs.actions, obs.played, env.history), (0, 0, []))

    def test_lifetimes_and_specs(self):
        self.assertIn("practice-v0", longgame.lifetimes())
        spec = longgame.load_spec("practice-v0")
        self.assertEqual((spec.total_levels, len(spec.visits), spec.budget(10), spec.budget(3)), (28, 14, 200, 100))
        self.assertEqual(len(spec.digest), 64)
        with self.assertRaises(ValueError):
            longgame.load_spec("no-such-lifetime")
        with self.assertRaisesRegex(ValueError, "always score 0"):
            longgame.load_spec({**TINY, "phases": ["learn", "return"]})


class TestRecordings(unittest.TestCase):
    def test_a_recording_verifies_and_tampering_is_caught(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "run.jsonl"
            card = evaluate(RandomAgent(seed=2), record=path)
            report = verify(path)
            self.assertTrue(report.ok, report.problems)
            self.assertEqual(report.scorecard.overall, card.overall)
            self.assertEqual(report.agent, "random")
            rows = [json.loads(x) for x in path.read_text().splitlines()]
            self.assertEqual((rows[0]["type"], rows[-1]["type"], len(rows)), ("start", "end", 30))
            rows[1]["score"] = 1.0
            rows[1]["cleared"] = True
            path.write_text("".join(json.dumps(r) + "\n" for r in rows))
            report = verify(path)
            self.assertFalse(report.ok)
            self.assertTrue(any("score" in p for p in report.problems))

    def test_a_recording_of_other_levels_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "run.jsonl"
            evaluate(SolverAgent(), lifetime=TINY, record=path)
            self.assertTrue(verify(path, lifetime=TINY).ok)
            rows = path.read_text().splitlines()
            head = json.loads(rows[0])
            head["lifetime"] = "practice-v0"
            path.write_text("\n".join([json.dumps(head)] + rows[1:]) + "\n")
            report = verify(path)
            self.assertFalse(report.ok)
            self.assertIn("differ", report.problems[0])


class TestAgents(unittest.TestCase):
    def test_random_agent_never_restarts_and_learns_nothing(self):
        card = evaluate(RandomAgent(seed=1))
        self.assertTrue(card.complete)
        self.assertLess(card.overall, 0.05)

    def test_explorer_finishes_levels_but_does_not_improve_on_return(self):
        card = evaluate(ExplorerAgent())
        self.assertTrue(card.complete)
        self.assertGreater(card.overall, 0.05)
        self.assertGreater(sum(r.cleared for r in card.results), 14)

    def test_load_agent(self):
        self.assertIsInstance(longgame.load_agent("random"), RandomAgent)
        self.assertIsInstance(longgame.load_agent("longgame.agents.explorer:ExplorerAgent"), ExplorerAgent)
        with self.assertRaises(ValueError):
            longgame.load_agent("nobody")


if __name__ == "__main__":
    unittest.main()
