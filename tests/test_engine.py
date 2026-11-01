"""The rules, level by level (ported from the v0 test suite)."""

import unittest

from longgame import engine, load_spec
from longgame.engine import Cell, DOWN as D, LEFT as L, RESTART, RIGHT as R, UP as U, USE

parse, step, render, solve = engine.parse_level, engine.step, engine.render, engine.solve


def play(rows, moves):
    lv = parse(rows)
    s, won = lv.start, False
    for m in moves:
        s, won = step(lv, s, m)
    return lv, s, won


class TestLevels(unittest.TestCase):
    def test_every_level_is_solvable_and_its_par_is_the_fewest_actions(self):
        spec = load_spec("practice-v0")
        for v in spec.visits:
            for i, level in enumerate(v.levels):
                with self.subTest(world=v.world, level=i + 1, phase=v.phase):
                    path = solve(parse(level.map))
                    self.assertIsNotNone(path)
                    self.assertEqual(len(path), level.par)
                    self.assertTrue(play(level.map, path)[2])
        phases = [v.phase for v in spec.visits]
        self.assertEqual([p for i, p in enumerate(phases) if i == 0 or p != phases[i - 1]], ["learn", "remix", "return"])
        learned = {v.world for v in spec.visits if v.phase == "learn"}
        self.assertTrue(all(v.world in learned for v in spec.visits if v.phase == "return"))
        maps = ["\n".join(lv.map) for v in spec.visits for lv in v.levels]
        self.assertEqual(len(set(maps)), len(maps), "no level appears twice")

    def test_maps_must_be_walled_in_and_well_formed(self):
        with self.assertRaisesRegex(ValueError, "walled in"):
            parse(["###", "#@E", "###"])
        with self.assertRaisesRegex(ValueError, "same length"):
            parse(["####", "#@E#", "###"])
        with self.assertRaisesRegex(ValueError, "player"):
            parse(["####", "#..#", "####"])
        with self.assertRaisesRegex(ValueError, "Unknown"):
            parse(["#####", "#@?E#", "#####"])
        with self.assertRaisesRegex(ValueError, "exit"):
            parse(["####", "#@.#", "####"])
        with self.assertRaisesRegex(ValueError, "One player"):
            parse(["#####", "#@@E#", "#####"])


class TestRules(unittest.TestCase):
    def test_crates_push_one_at_a_time_slide_on_ice_and_pads_open_the_exit(self):
        rows = ["#######", "#@$.oE#", "#######"]
        lv, s, won = play(rows, [R])
        self.assertEqual(s.crates, (10,))
        self.assertEqual(render(lv, s)[1][5], Cell.EXIT_CLOSED)
        lv, s, won = play(rows, [R, R])
        self.assertEqual(s.crates, (11,))
        self.assertEqual(render(lv, s)[1][4], Cell.CRATE_ON_PAD)
        self.assertEqual(render(lv, s)[1][5], Cell.EXIT)
        self.assertFalse(won)
        self.assertEqual(play(["#######", "#@$$.E#", "#######"], [R])[1].player, 8, "two crates in a row do not move")
        self.assertEqual(play(["#######", "#@$___#", "#....E#", "#######"], [R])[1].crates, (12,),
                         "a crate keeps sliding on ice")
        self.assertEqual(play(["#######", "#@$.E.#", "#######"], [R, R])[1].crates, (10,), "crates never enter exits")

    def test_ice_slides_the_player_until_blocked_and_never_pushes_mid_slide(self):
        self.assertEqual(play(["#######", "#@___.#", "#....E#", "#######"], [R])[1].player, 12)
        self.assertEqual(play(["#######", "#@__#.#", "#....E#", "#######"], [R])[1].player, 10)
        _, s, _ = play(["########", "#@__$..#", "#.....E#", "########"], [R])
        self.assertEqual(s.player, 11)
        self.assertEqual(s.crates, (12,))

    def test_keys_open_doors_are_used_up_and_show_in_the_status_row(self):
        rows = ["#########", "#@kk.DDE#", "#########"]
        lv, s, _ = play(rows, [R, R])
        self.assertEqual(s.held, 2)
        self.assertEqual(render(lv, s)[3][:3], [Cell.KEY, Cell.KEY, Cell.WALL])
        lv, s, _ = play(rows, [R, R, R, R])
        self.assertEqual(s.held, 1)
        self.assertEqual(render(lv, s)[1][5], Cell.PLAYER)
        self.assertTrue(play(rows, [R, R, R, R, R, R])[2])
        self.assertEqual(play(["#######", "#@.D.E#", "#######"], [R, R])[1].player, 9, "no key, no entry")

    def test_use_on_a_switch_flips_every_gate_but_not_onto_a_crate(self):
        rows = ["########", "#@S.Gg.#", "#.....E#", "########"]
        lv = parse(rows)
        self.assertEqual(play(rows, [USE])[1].phase, 0, "use off a switch does nothing")
        _, s, _ = play(rows, [R, USE])
        self.assertEqual(s.phase, 1)
        self.assertEqual(render(lv, s)[1][4], Cell.GATE_OPEN)
        self.assertEqual(render(lv, s)[1][5], Cell.GATE_CLOSED)
        self.assertEqual(play(rows, [R, R, R])[1].player, 11, "a closed gate blocks")
        self.assertEqual(play(rows, [R, USE, R, R, R])[1].player, 12)
        jam = ["########", "#@S.$g.#", "#.....E#", "########"]
        self.assertEqual(play(jam, [R, R, R, L, L, USE])[1].phase, 0, "the crate in the open gate keeps it open")
        self.assertEqual(play(["########", "#@S..g.#", "#.....E#", "########"], [R, R, R, L, L, USE])[1].phase, 1)

    def test_the_twin_mirrors_left_and_right_even_when_the_player_is_blocked(self):
        rows = ["##########", "#E#@..T.E#", "##########"]
        _, s, _ = play(rows, [R])
        self.assertEqual((s.player, s.twin), (14, 15))
        _, s, _ = play(rows, [L])
        self.assertEqual((s.player, s.twin), (13, 17))
        self.assertFalse(play(["#########", "#E@..T.E#", "#########"], [L])[2], "both must stand on exits")
        self.assertTrue(play(["#########", "#E.@.T.E#", "#########"], [L, L])[2])

    def test_coins_must_all_be_collected_before_the_exit_opens(self):
        rows = ["#######", "#@c.cE#", "#######"]
        lv, s, won = play(rows, [R])
        self.assertEqual(render(lv, s)[1][5], Cell.EXIT_CLOSED)
        self.assertTrue(play(rows, [R, R, R, R])[2])

    def test_restart_puts_the_level_back(self):
        rows = ["######", "#@$o.#", "#...E#", "######"]
        lv, s, _ = play(rows, [R, D, RESTART])
        self.assertEqual(s, lv.start)
        self.assertEqual(len(solve(parse(rows))), 4)

    def test_step_is_pure_and_rejects_unknown_moves(self):
        lv = parse(["#####", "#@.E#", "#####"])
        start = lv.start
        step(lv, start, R)
        self.assertEqual(lv.start, start)
        with self.assertRaises(ValueError):
            step(lv, start, 6)
        self.assertEqual(step(lv, start, U)[0], start, "walking into a wall changes nothing")


if __name__ == "__main__":
    unittest.main()
