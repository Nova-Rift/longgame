"""The Python engine must play exactly like the original TypeScript engine (Lifelong Arcade v0).

fixtures/v0_traces.json was recorded from that engine by fixtures/make_v0_traces.mjs: for each of the 28 levels, the
solver's path and four action sequences (random, random without restarts, long random, solver path with detours),
with a hash of every frame. Plus a whole random run and the 20-seed random baseline, played with the same
pseudo-random generator (mulberry32), ported here bit for bit.
"""

import hashlib
import json
import unittest
from pathlib import Path

from longgame import Action, engine, load_spec, make

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "v0_traces.json").read_text())
# v0 action ids (0 up, 1 right, 2 down, 3 left, 4 use, 5 restart) as public actions.
V0 = [Action.UP, Action.RIGHT, Action.DOWN, Action.LEFT, Action.USE, Action.RESET]


def frame_hash(grid, won):
    canon = ";".join(",".join(str(c) for c in row) for row in grid) + "|" + ("1" if won else "0")
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


def mulberry32(seed):
    s = seed & 0xFFFFFFFF

    def rand():
        nonlocal s
        s = (s + 0x6D2B79F5) & 0xFFFFFFFF
        t = ((s ^ (s >> 15)) * (1 | s)) & 0xFFFFFFFF
        t = ((t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    return rand


def random_run(seed):
    env = make("practice-v0")
    env.reset()
    rand = mulberry32(seed)
    while not env.done:
        env.step(V0[int(rand() * 5)])
    return env


class TestParity(unittest.TestCase):
    def test_levels_are_the_v0_levels(self):
        spec = load_spec("practice-v0")
        flat = [(i, j, v, lv) for i, v in enumerate(spec.visits) for j, lv in enumerate(v.levels)]
        self.assertEqual(len(flat), len(FIXTURE["levels"]))
        for (i, j, v, lv), want in zip(flat, FIXTURE["levels"]):
            self.assertEqual((i, j, v.world, v.phase, lv.par), (want["segment"], want["level"], want["game"],
                                                                 want["phase"], want["par"]))

    def test_every_frame_matches_the_typescript_engine(self):
        spec = load_spec("practice-v0")
        maps = [lv.map for v in spec.visits for lv in v.levels]
        for rows, want in zip(maps, FIXTURE["levels"]):
            level = engine.parse_level(rows)
            for n, seq in enumerate(want["seqs"]):
                with self.subTest(world=want["game"], level=want["level"], sequence=n):
                    state = level.start
                    got = [frame_hash(engine.render(level, state), False)]
                    for a in seq["actions"]:
                        state, won = engine.step(level, state, a)
                        got.append(frame_hash(engine.render(level, state), won))
                    for k, (g, w) in enumerate(zip(got, seq["hashes"])):
                        if g != w:
                            self.fail(f"frame differs after {k} actions: {seq['actions'][:k]}")
                    self.assertEqual(len(got), len(seq["hashes"]))

    def test_solver_finds_the_same_shortest_paths(self):
        spec = load_spec("practice-v0")
        maps = [lv.map for v in spec.visits for lv in v.levels]
        for rows, want in zip(maps, FIXTURE["levels"]):
            with self.subTest(world=want["game"], level=want["level"]):
                self.assertEqual(engine.solve(engine.parse_level(rows)), want["path"])

    def test_a_whole_random_run_scores_the_same(self):
        env = random_run(1)
        want = FIXTURE["random_run_seed1"]
        got = [r.to_dict() for r in env.results]
        self.assertEqual(len(got), len(want["results"]))
        for g, w in zip(got, want["results"]):
            self.assertEqual((g["visit"], g["level"], g["world"], g["phase"], g["par"], g["actions"], g["cleared"]),
                             (w["segment"], w["level"], w["game"], w["phase"], w["par"], w["actions"], w["cleared"]))
            self.assertAlmostEqual(g["score"], w["score"], places=12)
        card = env.scorecard()
        for phase in ("learn", "remix", "return"):
            self.assertAlmostEqual(card.phases[phase], want["score"][phase], places=12)
        self.assertAlmostEqual(card.overall, want["score"]["overall"], places=12)
        self.assertEqual(len(env.history), want["history_length"])

    def test_the_v0_random_baseline_is_reproduced(self):
        cards = [random_run(seed).scorecard() for seed in range(1, 21)]
        want = FIXTURE["random_baseline_20"]

        def avg(f):
            return round(1e4 * sum(f(c) for c in cards) / 20) / 1e4

        for phase in ("learn", "remix", "return"):
            self.assertEqual(avg(lambda c: c.phases[phase]), want[phase])
        self.assertEqual(avg(lambda c: c.overall), want["overall"])
        self.assertEqual(round(10 * sum(sum(r.cleared for r in c.results) for c in cards) / 20) / 10, want["cleared"])


if __name__ == "__main__":
    unittest.main()
