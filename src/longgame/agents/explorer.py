"""A systematic explorer with no long-term memory: the baseline every learner should beat.

Within a level it maps what each action does to the screen and heads for the nearest screen with an untried action,
restarting the level when everything reachable is tried. It forgets the map at every new level, so it never gets
better at a world it has seen before: its return-visit score shows what zero retention looks like.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Tuple

from ..actions import Action
from . import Agent

Frame = Tuple[Tuple[int, ...], ...]
MOVES = (Action.UP, Action.RIGHT, Action.DOWN, Action.LEFT, Action.USE)


class ExplorerAgent(Agent):
    name = "explorer"

    def __init__(self) -> None:
        self._forget()

    def _forget(self) -> None:
        self.edges: Dict[Frame, Dict[Action, Frame]] = {}
        self.prev: Optional[Tuple[Frame, Action]] = None
        self.plan: List[Action] = []
        self.where = None

    def act(self, obs):
        here = (obs.visit, obs.level)
        if obs.result is not None or here != self.where:
            self._forget()
            self.where = here
        frame: Frame = tuple(tuple(r) for r in obs.grid)
        if self.prev is not None:
            f, a = self.prev
            self.edges.setdefault(f, {})[a] = frame
        self.edges.setdefault(frame, {})
        if self.plan:
            nxt = self.plan.pop(0)
            self.prev = (frame, nxt)
            return nxt
        untried = [a for a in MOVES if a not in self.edges[frame]]
        if untried:
            choice = untried[0]
        else:
            path = self._path_to_untried(frame)
            if path:
                choice, self.plan = path[0], path[1:]
            else:
                self.prev = None  # restarting: the next frame is the level's start, not a result of an action here
                return Action.RESET
        self.prev = (frame, choice)
        return choice

    def _path_to_untried(self, start: Frame) -> List[Action]:
        """Shortest known action sequence from ``start`` to a screen that still has an untried action."""
        back: Dict[Frame, Optional[Tuple[Frame, Action]]] = {start: None}
        queue = deque([start])
        while queue:
            f = queue.popleft()
            if f != start and any(a not in self.edges.get(f, {}) for a in MOVES):
                path: List[Action] = []
                while back[f] is not None:
                    f, a = back[f]  # type: ignore[misc]
                    path.append(a)
                return path[::-1]
            for a, g in self.edges.get(f, {}).items():
                if g not in back:
                    back[g] = (f, a)
                    queue.append(g)
        return []
