"""ARC-AGI-3 agents can play a lifetime: their own action objects, frame type and loop (with or without arcengine)."""

import importlib.util
import random
import unittest
from enum import Enum

import longgame
from longgame import Action
from longgame.arc import ArcEnvironment, ArcFrame

HAS_ARCENGINE = importlib.util.find_spec("arcengine") is not None


class FakeGameAction(Enum):
    """Shaped like arcengine's GameAction: a plain Enum whose value is the id."""
    RESET = 0
    ACTION1 = 1
    ACTION2 = 2
    ACTION3 = 3
    ACTION4 = 4
    ACTION5 = 5
    ACTION6 = 6
    ACTION7 = 7


def arc_random_agent(env, actions, max_actions=3000, seed=0):
    """The loop of the ARC-AGI-3 random agent: RESET when not playing or game over, else a random simple action."""
    rng = random.Random(seed)
    frame = env.reset()
    for _ in range(max_actions):
        if str(getattr(frame.state, "value", frame.state)) == "WIN":
            break
        if str(getattr(frame.state, "value", frame.state)) in ("NOT_PLAYED", "GAME_OVER"):
            action = actions.RESET
        else:
            action = rng.choice([a for a in env.action_space if int(getattr(a, "value", a)) != 0])
        frame = env.step(action)
    return frame


class TestArcAgents(unittest.TestCase):
    def test_foreign_action_enums_are_accepted(self):
        self.assertIs(Action.coerce(FakeGameAction.ACTION4), Action.RIGHT)
        env = longgame.make()
        env.reset()
        self.assertEqual(env.step(FakeGameAction.ACTION1).actions, 1)

    def test_an_arc_style_loop_plays_the_lifetime(self):
        env = ArcEnvironment()
        frame = env.reset()
        if not HAS_ARCENGINE:
            self.assertIsInstance(frame, ArcFrame)
        self.assertEqual((len(frame.frame[0]), len(frame.frame[0][0])), (64, 64))
        final = arc_random_agent(env, FakeGameAction, max_actions=20000)
        self.assertTrue(env.done)
        self.assertEqual(str(getattr(final.state, "value", final.state)), "GAME_OVER")
        card = env.scorecard()
        self.assertTrue(card.complete)
        self.assertEqual(env.step(FakeGameAction.RESET), final, "a finished lifetime stays finished")
        self.assertEqual(env.reset(), final)
        self.assertTrue(env.scorecard().complete)

    def test_reset_mid_lifetime_restarts_the_level_and_counts(self):
        env = ArcEnvironment()
        env.reset()
        env.step(4)
        env.reset()
        self.assertEqual(env.lifetime.history, [4, 0])

    def test_the_solver_wins(self):
        from longgame.agents.solver import SolverAgent
        env, agent = ArcEnvironment(), SolverAgent()
        frame = env.reset()
        while not env.done:
            frame = env.step(agent.act(env.lifetime.observe()))
        self.assertEqual(str(getattr(frame.state, "value", frame.state)), "WIN")
        self.assertEqual(env.scorecard().overall, 1.0)

    @unittest.skipUnless(HAS_ARCENGINE, "arcengine not installed (it needs Python 3.12+)")
    def test_with_the_real_arc_toolkit_types(self):
        from arcengine import FrameData, GameAction, GameState
        env = ArcEnvironment()
        frame = env.reset()
        self.assertIsInstance(frame, FrameData)
        self.assertIs(frame.state, GameState.NOT_FINISHED)
        self.assertEqual(env.action_space, [GameAction.RESET, GameAction.ACTION1, GameAction.ACTION2,
                                            GameAction.ACTION3, GameAction.ACTION4, GameAction.ACTION5])
        frame = env.step(GameAction.ACTION4)
        self.assertEqual(env.lifetime.history, [4])
        final = arc_random_agent(env, GameAction, max_actions=20000)
        self.assertIn(final.state, (GameState.WIN, GameState.GAME_OVER))
        self.assertTrue(env.scorecard().complete)


if __name__ == "__main__":
    unittest.main()
