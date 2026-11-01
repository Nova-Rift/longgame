"""The world maker: generated levels and lifetimes are reproducible, solver-checked, and keep held-out rules out of
training."""

import contextlib
import io
import json
import tempfile
import unittest
from itertools import combinations
from pathlib import Path

from longgame import engine, load_spec, make, verify, worlds
from longgame.agents import evaluate
from longgame.agents.solver import SolverAgent
from longgame.cli import main

# v1 must never change: a generated id names the same levels on every computer, forever. These digests are checked
# on Linux, macOS and Windows and on every supported Python. If one fails, generation changed: put the change in a
# new version (v2) instead.
PINNED = {
    "train-v1-0": "2f6db1dbf9e2e5a64fcce90984bdd680ff51c3bce75b5e5385623a0ede25f161",
    "train-v1-1": "1d503e82d9ab108d8394d0e6b931b68a4229cc64f48f2a98b2e80fadf57408d3",
    "train-v1-123456789": "2118cd206dc5ba364f3edfdf88f702d87e1084df477dad9a2cc8a7daf4cdaa91",
    "heldout-v1-0": "a243d67a8cf9aa099eb29a213a01d9a0d6e943b9308a55b37b3b6dda7be8bda4",
    "heldout-v1-1": "3b8e72a7283c85fd8c5b5269845e1609c05b8c77febdd143ad443a429696ed9f",
}
PINNED_LEVEL = {"par": 16, "map": [  # worlds.level(["keys", "ice"], tier=3, seed=7)
    "########",
    "#....#k#",
    "#.k__#.#",
    "#_####@#",
    "#.__.D.#",
    "####D###",
    "#__E_..#",
    "########"]}


def cli(*args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(list(args))
    return code, out.getvalue()


class TestNames(unittest.TestCase):
    def test_generated_ids(self):
        for good in ("train-v1-0", "train-v1-42", "heldout-v1-999999999"):
            self.assertTrue(worlds.is_generated(good), good)
        for bad in ("train-v1-01", "train-v1--1", "train-v2-1", "train-v1-1000000000", "test-v1-1", "practice-v0",
                    "train-v1-", "train-v1-1 ", "heldout-v1-2\n", "xtrain-v1-1", None, 5):
            self.assertFalse(worlds.is_generated(bad), repr(bad))
        with self.assertRaises(ValueError):
            load_spec("heldout-v1-2\n")

    def test_rules_are_canonical(self):
        self.assertEqual(worlds.rules(["ice", "keys", "ice"]), ("keys", "ice"))
        self.assertEqual(worlds.rules("maze"), ())
        self.assertEqual(worlds.rules("coins"), ("coins",))
        with self.assertRaises(ValueError):
            worlds.rules(["lava"])

    def test_every_pair_is_in_exactly_one_split(self):
        self.assertEqual(worlds.split_of(["coins"]), "heldout")
        self.assertEqual(worlds.split_of(["keys", "ice"]), "heldout")
        self.assertEqual(worlds.split_of(["crates", "ice"]), "train")
        self.assertEqual(worlds.split_of([]), "train")
        for split in worlds.SPLITS:
            for recipe in worlds.recipes(split):
                self.assertEqual(worlds.split_of(recipe), split)
        pairs = {worlds.rules(p) for p in combinations(worlds.MECHANICS, 2)}
        listed = [r for s in worlds.SPLITS for r in worlds.recipes(s) if len(r) == 2]
        self.assertEqual(len(listed), len(pairs))
        self.assertEqual(set(listed), pairs)
        with self.assertRaises(ValueError):
            worlds.recipes("test")


class TestLevels(unittest.TestCase):
    def test_same_arguments_same_level(self):
        a = worlds.level(["keys", "ice"], tier=3, seed=7)
        self.assertEqual(a, worlds.level(("ice", "keys"), tier=3, seed=7))
        self.assertNotEqual(a.map, worlds.level(["keys", "ice"], tier=3, seed=8).map)
        self.assertEqual({"par": a.par, "map": list(a.map)}, PINNED_LEVEL)

    def test_every_rule_set_at_every_tier(self):
        for split in worlds.SPLITS:
            for recipe in worlds.recipes(split):
                for tier in (1, 2, 3):
                    with self.subTest(recipe=recipe, tier=tier):
                        lv = worlds.level(recipe, tier, seed=1)
                        rows = list(lv.map)
                        self.assertEqual(worlds.mechanics_in(rows), recipe)
                        self.assertEqual(len(engine.solve(engine.parse_level(rows))), lv.par)  # the true minimum
                        lo, hi = worlds.par_range(recipe, tier)
                        self.assertTrue(lo <= lv.par <= hi, (lv.par, lo, hi))
                        self.assertEqual(worlds.check(rows, recipe, tier), lv.par)
                        self.assertLessEqual(max(len(rows) + 1, len(rows[0])), worlds.FRAME)

    def test_each_rule_matters(self):
        # Taking a rule out of a generated level makes it shorter (by 2 or more after tier 1), or, for ice and the
        # twin, makes the old way of finishing it fail.
        for recipe in [("crates",), ("keys",), ("gates",), ("coins",), ("ice",), ("twin",), ("crates", "keys"),
                       ("gates", "twin"), ("keys", "ice")]:
            lv = worlds.level(recipe, 2, seed=3)
            for m in recipe:
                plain = engine.solve(engine.parse_level(worlds.without(lv.map, m)))
                if m in ("ice", "twin") and not worlds._wins(lv.map, plain):
                    continue
                self.assertNotEqual(m, "ice", recipe)
                self.assertLessEqual(len(plain), lv.par - 2, (recipe, m))

    def test_bad_arguments(self):
        for args in [(["keys", "ice", "crates"], 2, 0), (["lava"], 2, 0), (["keys"], 4, 0), (["keys"], True, 0),
                     (["keys"], 2.0, 0), (["keys"], 2, -1), (["keys"], 2, 1.5), (["keys"], 2, 2 ** 32),
                     (["keys"], 2, "3")]:
            with self.assertRaises(ValueError, msg=args):
                worlds.level(*args)
        for args in [("test", 0), ("train", -1), ("train", 2.5), (None, 0)]:
            with self.assertRaises(ValueError, msg=args):
                worlds.levels(*args)  # checked when called, not at the first next()

    def test_equal_inputs_give_equal_levels(self):
        import enum

        class Seed(enum.IntEnum):
            SEVEN = 7

        class Split(str, enum.Enum):
            HELD = "heldout"

        self.assertEqual(worlds.level(["keys"], 2, Seed.SEVEN), worlds.level(["keys"], 2, 7))
        self.assertEqual(next(worlds.levels(Split.HELD, Seed.SEVEN)), next(worlds.levels("heldout", 7)))
        self.assertEqual(worlds.generate("train", Seed.SEVEN).digest, load_spec("train-v1-7").digest)

    def test_tiers_never_overlap(self):
        # so each level of a visit takes more actions than the one before
        every = [()] + [(m,) for m in worlds.MECHANICS] + [worlds.rules(p) for p in combinations(worlds.MECHANICS, 2)]
        for recipe in every:
            ranges = [worlds.par_range(recipe, tier) for tier in (1, 2, 3)]
            for (lo, hi), (lo2, hi2) in zip(ranges, ranges[1:]):
                self.assertLess(hi, lo2, recipe)
            self.assertTrue(all(lo <= hi for lo, hi in ranges), recipe)

    def test_a_crate_never_pushed_is_clutter(self):
        rows = ["########", "#..o...#", "#......#", "#.$....#", "#......#", "#...$..#", "#...@..#", "#E.....#",
                "########"]  # one pad, two crates: the solution pushes the lower crate up past the other
        path = engine.solve(engine.parse_level(rows))
        self.assertEqual(worlds._Trace(rows, path).idle_crates, 1)
        for tier in (1, 2, 3):
            self.assertIsNone(worlds.check(rows, ["crates"], tier))

    def test_every_gate_switch_and_door_matters(self):
        for recipe in [("gates",), ("keys",), ("keys", "gates"), ("gates", "twin")]:
            for tier in (2, 3):
                lv = worlds.level(recipe, tier, seed=2)
                for y, row in enumerate(lv.map):
                    for x, ch in enumerate(row):
                        if ch in "GgSD":
                            rows = [*lv.map[:y], row[:x] + "." + row[x + 1:], *lv.map[y + 1:]]
                            path = engine.solve(engine.parse_level(rows))
                            self.assertTrue(path is None or len(path) != lv.par, (recipe, tier, y, x))

    def test_endless_stream(self):
        a = worlds.levels("heldout", seed=3)
        b = worlds.levels("heldout", seed=3)
        for _ in range(6):
            recipe, tier, lv = next(a)
            self.assertEqual((recipe, tier, lv), next(b))
            self.assertEqual(worlds.split_of(recipe), "heldout")
            self.assertIn(tier, (1, 2, 3))
        recipe, _, _ = next(worlds.levels("train", seed=0))
        self.assertEqual(worlds.split_of(recipe), "train")


class TestLifetimes(unittest.TestCase):
    def test_pinned(self):
        for name, digest in PINNED.items():
            self.assertEqual(load_spec(name).digest, digest, name)

    def test_shape_and_held_out_rules(self):
        for seed in range(3):
            for split in worlds.SPLITS:
                spec = worlds.generate(split, seed)
                self.assertEqual(spec.id, f"{split}-v1-{seed}")
                self.assertEqual((len(spec.visits), spec.total_levels), (14, 28))
                self.assertEqual([v.phase for v in spec.visits], ["learn"] * 6 + ["remix"] * 3 + ["return"] * 5)
                rules = worlds.world_rules(spec)
                self.assertEqual(rules["A"], ())
                learned = [rules[v.world] for v in spec.visits[1:6]]
                self.assertTrue(all(len(r) == 1 for r in learned))
                for v in spec.visits[6:9]:
                    pair = rules[v.world]
                    self.assertEqual(len(pair), 2)
                    self.assertTrue(all((m,) in learned for m in pair))  # remixes combine learned rules
                    self.assertEqual(worlds.split_of(pair), split)
                self.assertEqual(sorted(v.world for v in spec.visits[9:]), sorted(v.world for v in spec.visits[1:6]))
                maps = [lv.map for v in spec.visits for lv in v.levels]
                self.assertEqual(len(set(maps)), len(maps))  # no level twice
                for v in spec.visits:  # each level of a visit takes more actions than the one before
                    pars = [lv.par for lv in v.levels]
                    self.assertEqual(pars, sorted(set(pars)), (spec.id, v.world))
                text = "".join("".join(m) for m in maps)
                if split == "train":
                    self.assertNotIn("c", text)  # never a coin in training
                    self.assertTrue(all(worlds.split_of(r) == "train" for r in rules.values()))
                else:
                    self.assertIn(("coins",), learned)
                    pairs = [rules[v.world] for v in spec.visits[6:9]]
                    self.assertTrue(any("coins" not in p for p in pairs))  # familiar rules, combined anew
                    self.assertTrue(any("coins" in p for p in pairs))

    def test_par_is_the_fewest_actions(self):
        code, out = cli("check", "heldout-v1-4")
        self.assertEqual(code, 0, out)
        self.assertIn("0 problems", out)

    def test_bad_seeds(self):
        for split, seed in (("train", -1), ("train", 10 ** 9), ("train", "3"), ("train", True), ("test", 1)):
            with self.assertRaises(ValueError):
                worlds.generate(split, seed)
        with self.assertRaises(ValueError) as e:
            load_spec("train-v2-1")
        self.assertIn("train-v1-0", str(e.exception))


class TestPlaying(unittest.TestCase):
    def test_solver_finishes_and_recording_verifies_by_name(self):
        with tempfile.TemporaryDirectory() as d:
            rec = Path(d) / "run.jsonl"
            card = evaluate(SolverAgent(), "heldout-v1-2", record=rec)
            self.assertEqual(card.overall, 1.0)
            report = verify(rec)  # no lifetime given: rebuilt from the id in the recording
            self.assertTrue(report.ok, report.problems)
            rows = rec.read_text().splitlines()
            head = json.loads(rows[0])
            head["lifetime"] = "heldout-v1-3"  # same recording, claimed for a different lifetime
            rec.write_text("\n".join([json.dumps(head)] + rows[1:]) + "\n")
            self.assertFalse(verify(rec).ok)

    def test_make_play_and_show(self):
        env = make("train-v1-5")
        obs = env.reset()
        self.assertEqual((obs.lifetime, obs.world, obs.phase, obs.total), ("train-v1-5", "A", "learn", 28))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "t5.json"
            code, out = cli("show", "train-v1-5", "--maps", "--save", str(path))
            self.assertEqual(code, 0)
            self.assertIn("world A  learn   maze", out)
            self.assertIn("remix", out)
            self.assertEqual(load_spec(path).digest, load_spec("train-v1-5").digest)
        code, out = cli("list")
        self.assertIn("train-v1-<seed>", out)
        self.assertIn("heldout-v1-<seed>", out)

    def test_world_rules_of_practice(self):
        rules = worlds.world_rules(load_spec("practice-v0"))
        self.assertEqual(rules["A"], ())
        self.assertEqual(rules["B"], ("crates",))
        self.assertEqual(rules["H"], ("keys", "gates"))
        self.assertTrue(all(worlds.split_of(r) == "train" for r in rules.values()))  # practice uses training rules


if __name__ == "__main__":
    unittest.main()
