"""Reads the rules from the toolkit's own engine and plays every level perfectly: the ceiling (100%), not an entry.

The screen shows everything that matters, so at the start of each level the agent turns the grid back into a map,
solves it with breadth-first search and plays the shortest solution. Use it to check a harness, never as a result.
"""

from __future__ import annotations

from typing import List

from .. import engine
from ..actions import Action
from ..engine import Cell
from ..render import ASCII
from . import Agent

_FROM_ENGINE = {engine.UP: Action.UP, engine.RIGHT: Action.RIGHT, engine.DOWN: Action.DOWN, engine.LEFT: Action.LEFT,
                engine.USE: Action.USE}
# Screen colours back to map characters; a closed exit is still an exit, a crate on a pad is '*'.
_TO_MAP = {**ASCII, Cell.EXIT_CLOSED: "E"}


def grid_to_map(grid) -> List[str]:
    """The level's map as it stands (drops the status row; only valid while no keys are held)."""
    return ["".join(_TO_MAP[c] for c in row) for row in grid[:-1]]


class SolverAgent(Agent):
    name = "solver"

    def __init__(self) -> None:
        self.plan: List[Action] = []

    def act(self, obs):
        if obs.actions == 0:
            path = engine.solve(engine.parse_level(grid_to_map(obs.grid)))
            self.plan = [_FROM_ENGINE[m] for m in (path or [])]
        return self.plan.pop(0) if self.plan else Action.USE
