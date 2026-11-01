"""Actions. The ids and names match ARC-AGI-3's ``GameAction`` (RESET = 0, ACTION1-ACTION7 = 1-7), so an agent
written for ARC-AGI-3 sends the same numbers here.

====  =========  ===========  ==============================================
 id   ARC name   Long Game    meaning
====  =========  ===========  ==============================================
 0    RESET      RESET        restart the current level (costs one action)
 1    ACTION1    UP           up
 2    ACTION2    DOWN         down
 3    ACTION3    LEFT         left
 4    ACTION4    RIGHT        right
 5    ACTION5    USE          use / interact
 6    ACTION6    CLICK        click a cell (x, y); not used by any world yet
 7    ACTION7    UNDO         undo; not used by any world yet
====  =========  ===========  ==============================================

Each observation lists the actions its world accepts in ``available_actions``. Sending any other action raises
:class:`InvalidAction` and costs nothing, like ARC-AGI-3's 400 response.
"""

from __future__ import annotations

import operator
from enum import Enum, IntEnum
from typing import Union

from . import engine


class Action(IntEnum):
    RESET = 0
    UP = 1
    DOWN = 2
    LEFT = 3
    RIGHT = 4
    USE = 5
    CLICK = 6
    UNDO = 7

    # ARC-AGI-3 names for the same ids.
    ACTION1 = 1
    ACTION2 = 2
    ACTION3 = 3
    ACTION4 = 4
    ACTION5 = 5
    ACTION6 = 6
    ACTION7 = 7

    @classmethod
    def coerce(cls, value: Union["Action", int, str]) -> "Action":
        """Accept an :class:`Action`, its id, a name such as ``"up"``, ``"ACTION1"`` or ``"restart"``, or another
        toolkit's action enum whose value is the id (such as ARC-AGI-3's ``GameAction.ACTION1``)."""
        if isinstance(value, cls):
            return value
        if isinstance(value, Enum) and isinstance(value.value, int) and not isinstance(value.value, bool):
            value = value.value
        if isinstance(value, bool):
            raise InvalidAction(f"Not an action: {value!r}")
        if isinstance(value, str):
            name = value.strip().upper()
            name = _ALIASES.get(name, name)
            if name in cls.__members__:
                return cls.__members__[name]
            raise InvalidAction(f"Unknown action name {value!r}")
        try:
            number = operator.index(value)  # ints, numpy integers, anything integer-like
        except TypeError:
            raise InvalidAction(f"Not an action: {value!r}") from None
        try:
            return cls(number)
        except ValueError:
            raise InvalidAction(f"Action ids are 0-7, got {number}") from None


class InvalidAction(ValueError):
    """An action that is not an action at all, or not available in the current world."""


_ALIASES = {"RESTART": "RESET", "INTERACT": "USE", "SPACE": "USE", "W": "UP", "S": "DOWN", "A": "LEFT", "D": "RIGHT",
            "E": "USE", "R": "RESET", "Z": "UNDO"}

# Public action -> engine move, for the worlds in this release (which use RESET and ACTION1-5).
ENGINE_MOVE = {Action.RESET: engine.RESTART, Action.UP: engine.UP, Action.DOWN: engine.DOWN,
               Action.LEFT: engine.LEFT, Action.RIGHT: engine.RIGHT, Action.USE: engine.USE}
KEYS_AND_RESET = (Action.RESET, Action.UP, Action.DOWN, Action.LEFT, Action.RIGHT, Action.USE)
