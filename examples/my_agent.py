"""A starting point for your own agent. Run it with:

    longgame run examples/my_agent.py:MyAgent --record runs/my-agent.jsonl
    longgame verify runs/my-agent.jsonl

or `python examples/my_agent.py`.
"""

import random

from longgame import Action, Agent, evaluate


class MyAgent(Agent):
    """Remembers, per world, which first moves led to finished levels, and tries those first next time.

    A toy, but it shows the shape of the problem: the same object plays the whole lifetime, so anything it keeps on
    ``self`` carries over to remixes and return visits. That is the memory Long Game measures.
    """

    name = "my-agent"

    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)
        self.memory = {}  # world -> moves that were part of a finished level
        self.moves = []   # moves on the current level

    def act(self, obs):
        if obs.result is not None:  # the previous action ended a level
            if obs.result.cleared:
                self.memory.setdefault(obs.result.world, []).extend(self.moves)
            self.moves = []
        known = self.memory.get(obs.world)
        if known and self.rng.random() < 0.5:
            move = self.rng.choice(known)
        else:
            move = self.rng.choice([a for a in obs.available_actions if a != Action.RESET])
        self.moves.append(move)
        return move

    def finish(self, scorecard):
        print(f"remembered moves for worlds {sorted(self.memory)}")


if __name__ == "__main__":
    print(evaluate(MyAgent()))
