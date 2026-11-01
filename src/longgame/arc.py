"""Bridges to ARC-AGI-3 conventions, so agents written for the ARC-AGI toolkit need few changes.

Action ids already match (see :mod:`longgame.actions`). :func:`frame_data` turns an observation into a dict shaped
like ARC-AGI-3's ``FrameData``: the grid padded to 64 x 64, the game state, levels played in the current game and
the available action ids. Here a "game" is one visit to a world.
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
