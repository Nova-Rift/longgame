"""Bridges to ARC-AGI-3 conventions, so agents written for the ARC-AGI toolkit need few changes.

Action ids already match (see :mod:`longgame.actions`), and ``env.step`` accepts ARC's own ``GameAction`` members.
:class:`ArcEnvironment` puts a lifetime behind the ARC toolkit's environment interface (``reset``, ``step``,
``action_space``) and returns real ``FrameData`` objects when ``arcengine`` is installed. :func:`frame_data` turns
one observation into a dict shaped like ``FrameData``: the grid padded to 64 x 64, the game state, levels played in
the current game and the available action ids. Here a "game" is one visit to a world.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .engine import Cell

ARC_SIZE = 64


def pad(grid: Sequence[Sequence[int]], size: int = ARC_SIZE, fill: int = Cell.WALL) -> List[List[int]]:
    """Place ``grid`` at the top left of a ``size`` x ``size`` frame filled with wall colour."""
    if grid and (len(grid) > size or len(grid[0]) > size):
        raise ValueError(f"A {len(grid[0])}x{len(grid)} grid does not fit in {size}x{size}")
    out = [[fill] * size for _ in range(size)]
    for y, row in enumerate(grid):
        out[y][:len(row)] = list(row)
    return out


def frame_data(obs, size: int = ARC_SIZE) -> Dict[str, Any]:
    """An ARC-AGI-3 style ``FrameData`` dict for one observation.

    ``state`` is ``NOT_FINISHED`` while the lifetime runs; at the end it is ``WIN`` if every level was finished and
    ``GAME_OVER`` otherwise (then ``frame`` is empty). ``levels_completed`` counts the current visit's levels already
    played, finished or not, since a Long Game level that runs out of actions is still left behind.
    """
    if obs.done:
        state = "WIN" if obs.cleared == obs.total else "GAME_OVER"
    else:
        state = "NOT_FINISHED"
    return {
        "game_id": f"{obs.lifetime}/{obs.world}",
        "frame": [] if obs.done else [pad(obs.grid, size)],
        "state": state,
        "levels_completed": obs.levels if obs.done else obs.level,
        "win_levels": obs.levels,
        "guid": None,
        "full_reset": False,
        "available_actions": [int(a) for a in obs.available_actions],
    }


class ArcFrame:
    """The fields of ARC-AGI-3's ``FrameData``, used when the ``arcengine`` package is not installed."""

    __slots__ = ("game_id", "frame", "state", "levels_completed", "win_levels", "guid", "full_reset",
                 "available_actions")

    def __init__(self, **fields: Any):
        for k in self.__slots__:
            setattr(self, k, fields.get(k))

    def __repr__(self) -> str:
        return (f"ArcFrame(game_id={self.game_id!r}, state={self.state!r}, levels_completed={self.levels_completed}, "
                f"win_levels={self.win_levels}, available_actions={self.available_actions})")


class ArcEnvironment:
    """A Long Game lifetime behind the ARC-AGI toolkit's environment interface, so ARC-AGI-3 agents can play it.

        from arcengine import GameAction          # optional; plain ids 0-7 work too
        from longgame.arc import ArcEnvironment

        env = ArcEnvironment("practice-v0")
        frame = env.reset()                       # FrameData (or ArcFrame without arcengine)
        frame = env.step(GameAction.ACTION1)      # up
        env.action_space                          # [GameAction.RESET, GameAction.ACTION1, ...]
        print(env.scorecard())

    Like ``EnvironmentWrapper``: ``reset()``, ``step(action, data=None, reasoning=None)``, ``action_space`` and
    ``observation_space`` (the last frame). Differences that matter for a lifetime: the first ``reset()`` starts it;
    after that ``reset()`` restarts the current level and counts as an action, exactly like the RESET action, because
    a lifetime is never wiped. When the lifetime is over the state is ``WIN`` if every level was finished, else
    ``GAME_OVER``, and further actions and resets change nothing (``done`` is True); the scorecard is the result.
    Make a new ``ArcEnvironment`` to play again.
    """

    def __init__(self, lifetime: Any = "practice-v0", size: int = ARC_SIZE, record: Any = None, agent: str = ""):
        from .lifetime import make
        self.lifetime = make(lifetime, record=record, agent=agent)
        self.size = size
        self._last: Any = None
        try:
            from arcengine import FrameData, GameAction  # type: ignore
            self._frame_cls, self._action_cls = FrameData, GameAction
        except Exception:  # not installed (it needs Python 3.12+): plain fields and ids
            self._frame_cls, self._action_cls = ArcFrame, None

    @property
    def done(self) -> bool:
        return self.lifetime.done

    def _frame(self, obs) -> Any:
        self._last = self._frame_cls(**frame_data(obs, self.size))
        return self._last

    def reset(self) -> Any:
        if not self.lifetime.started:
            return self._frame(self.lifetime.reset())
        if self.lifetime.done:  # never wipe a finished lifetime: its scorecard is the result
            return self._last
        return self.step(0)

    def step(self, action: Any, data: Any = None, reasoning: Any = None) -> Any:
        if not self.lifetime.started:
            return self.reset()
        if self.lifetime.done:
            return self._last
        return self._frame(self.lifetime.step(action))

    @property
    def observation_space(self) -> Any:
        return self._last

    @property
    def action_space(self) -> List[Any]:
        ids = [int(a) for a in self.lifetime.available_actions] if self.lifetime.started else []
        if not self._action_cls:
            return ids
        by_id = {a.value: a for a in self._action_cls}  # GameAction(i) is not reliable across Python versions
        return [by_id[i] for i in ids]

    def scorecard(self):
        return self.lifetime.scorecard()

    def close(self) -> None:
        self.lifetime.close()
