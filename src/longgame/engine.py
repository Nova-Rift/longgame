"""The Long Game rules: small turn-based grid worlds with no instructions.

A level is an ASCII map. One pure function, :func:`step`, drives every way of playing: the browser player, agents in
Python, the JSON-lines protocol and the solver that sets each level's par. Players (people or AI) see only the colour
grid from :func:`render`.

This is a faithful port of the Lifelong Arcade v0 engine (TypeScript). ``tests/test_parity.py`` replays traces
recorded from that engine and checks every frame matches.

Map characters::

    #  wall          .  floor          @  player         E  exit
    $  crate         o  pad            *  crate on a pad
    k  key           D  door           _  ice            S  switch
    G  gate (closed) g  gate (open)    T  twin           c  coin

Maps must be rectangular and walled on every side.

Engine moves (internal; the public action ids are in :mod:`longgame.actions`): 0 up, 1 right, 2 down, 3 left,
4 use, 5 restart.
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

UP, RIGHT, DOWN, LEFT, USE, RESTART = range(6)
MOVES = ("up", "right", "down", "left", "use", "restart")


class Cell:
    """Colour ids in an observation grid (16 colours, as in ARC-AGI-3). The last row is a status bar."""

    FLOOR = 0
    WALL = 1
    PLAYER = 2
    EXIT = 3
    EXIT_CLOSED = 4
    CRATE = 5
    PAD = 6
    CRATE_ON_PAD = 7
    KEY = 8
    DOOR = 9
    ICE = 10
    SWITCH = 11
    GATE_CLOSED = 12
    GATE_OPEN = 13
    TWIN = 14
    COIN = 15


# Tile codes in a level's fixed layout.
_FLOOR, _WALL, _EXIT, _PAD, _ICE, _SWITCH, _GATE, _DOOR = range(8)
_MAX_ITEMS = 30


class State(NamedTuple):
    """Everything that changes while a level is played. Hashable, so the solver can use it as a key.

    ``keys``, ``doors`` and ``coins`` are bitmasks over the level's lists: a set bit means that key or coin is still
    on the map, or that door is still locked. ``held`` is the number of keys carried. ``phase`` flips every gate
    between its starting state and the opposite.
    """

    player: int
    twin: int  # -1 when the level has no twin
    crates: Tuple[int, ...]  # sorted cell indices
    held: int
    keys: int
    doors: int
    coins: int
    phase: int


class Level:
    """A parsed map: the fixed layout plus the starting :class:`State`."""

    __slots__ = ("w", "h", "tiles", "start", "keys", "doors", "coins", "gates", "gate_open", "pads", "exits",
                 "_key_bit", "_door_bit", "_coin_bit", "_gate_index", "_delta")

    def __init__(self, w: int, h: int, tiles: Tuple[int, ...], start: State, keys: Tuple[int, ...],
                 doors: Tuple[int, ...], coins: Tuple[int, ...], gates: Tuple[int, ...],
                 gate_open: Tuple[bool, ...], pads: Tuple[int, ...], exits: Tuple[int, ...]):
        self.w, self.h, self.tiles, self.start = w, h, tiles, start
        self.keys, self.doors, self.coins = keys, doors, coins
        self.gates, self.gate_open, self.pads, self.exits = gates, gate_open, pads, exits
        self._key_bit = {cell: bit for bit, cell in enumerate(keys)}
        self._door_bit = {cell: bit for bit, cell in enumerate(doors)}
        self._coin_bit = {cell: bit for bit, cell in enumerate(coins)}
        self._gate_index = {cell: j for j, cell in enumerate(gates)}
        self._delta = (-w, 1, w, -1)


def parse_level(rows: Sequence[str]) -> Level:
    """Parse an ASCII map (a list of equal-length rows) into a :class:`Level`. Raises ``ValueError`` if malformed."""
    h = len(rows)
    w = len(rows[0]) if h else 0
    if not h or any(len(r) != w for r in rows):
        raise ValueError("Level rows must all have the same length")
    tiles = [_FLOOR] * (w * h)
    keys: List[int] = []
    doors: List[int] = []
    coins: List[int] = []
    gates: List[int] = []
    gate_open: List[bool] = []
    pads: List[int] = []
    exits: List[int] = []
    crates: List[int] = []
    player = twin = -1
    for y in range(h):
        for x in range(w):
            i, c = y * w + x, rows[y][x]
            if (x == 0 or y == 0 or x == w - 1 or y == h - 1) and c != "#":
                raise ValueError(f"Level must be walled in (row {y}, column {x})")
            if c == "#":
                tiles[i] = _WALL
            elif c == ".":
                pass
            elif c == "@":
                if player >= 0:
                    raise ValueError("One player per level")
                player = i
            elif c == "T":
                if twin >= 0:
                    raise ValueError("One twin per level")
                twin = i
            elif c == "E":
                tiles[i] = _EXIT
                exits.append(i)
            elif c == "$":
                crates.append(i)
            elif c == "o":
                tiles[i] = _PAD
                pads.append(i)
            elif c == "*":
                tiles[i] = _PAD
                pads.append(i)
                crates.append(i)
            elif c == "k":
                keys.append(i)
            elif c == "D":
                tiles[i] = _DOOR
                doors.append(i)
            elif c == "_":
                tiles[i] = _ICE
            elif c == "S":
                tiles[i] = _SWITCH
            elif c in "Gg":
                tiles[i] = _GATE
                gates.append(i)
                gate_open.append(c == "g")
            elif c == "c":
                coins.append(i)
            else:
                raise ValueError(f'Unknown map character "{c}"')
    if player < 0:
        raise ValueError("Level needs a player (@)")
    if not exits:
        raise ValueError("Level needs an exit (E)")
    if max(len(keys), len(doors), len(coins)) > _MAX_ITEMS:
        raise ValueError(f"At most {_MAX_ITEMS} keys, doors or coins")

    def full(n: int) -> int:
        return (1 << n) - 1

    start = State(player, twin, tuple(sorted(crates)), 0, full(len(keys)), full(len(doors)), full(len(coins)), 0)
    return Level(w, h, tuple(tiles), start, tuple(keys), tuple(doors), tuple(coins), tuple(gates), tuple(gate_open),
                 tuple(pads), tuple(exits))


# --- rules -----------------------------------------------------------------------------------------------------------

def _has(mask: int, bit: int) -> bool:
    return bit >= 0 and (mask >> bit) & 1 == 1


def _clear(mask: int, bit: int) -> int:
    return mask & ~(1 << bit) if _has(mask, bit) else mask


class _Scratch:
    """A mutable copy of a State while one action is applied."""

    __slots__ = ("player", "twin", "crates", "held", "keys", "doors", "coins", "phase")

    def __init__(self, s: State):
        self.player, self.twin, self.crates, self.held = s.player, s.twin, list(s.crates), s.held
        self.keys, self.doors, self.coins, self.phase = s.keys, s.doors, s.coins, s.phase

    def freeze(self) -> State:
        return State(self.player, self.twin, tuple(self.crates), self.held, self.keys, self.doors, self.coins,
                     self.phase)


def _gate_closed(L: Level, phase: int, i: int) -> bool:
    j = L._gate_index.get(i)
    return j is not None and L.gate_open[j] == (phase == 1)


def _locked_door(L: Level, doors: int, i: int) -> bool:
    return L.tiles[i] == _DOOR and _has(doors, L._door_bit.get(i, -1))


def _item_at(L: Level, s, i: int) -> bool:
    return _has(s.keys, L._key_bit.get(i, -1)) or _has(s.coins, L._coin_bit.get(i, -1))


def _solid(L: Level, s, i: int) -> bool:
    return L.tiles[i] == _WALL or _gate_closed(L, s.phase, i) or _locked_door(L, s.doors, i)


def exit_open(L: Level, s) -> bool:
    """The exits open once every coin is collected and every pad holds a crate."""
    return s.coins == 0 and all(p in s.crates for p in L.pads)


def _push_crate(L: Level, s: _Scratch, at: int, a: int) -> bool:
    """Crates move one cell when pushed, then keep sliding while on ice. They never enter exits, switches or cells
    holding a key or coin."""
    d = L._delta[a]

    def free(i: int) -> bool:
        return (not _solid(L, s, i) and L.tiles[i] != _EXIT and L.tiles[i] != _SWITCH and not _item_at(L, s, i)
                and i not in s.crates and i != s.player and i != s.twin)

    if not free(at + d):
        return False
    pos = at + d
    while L.tiles[pos] == _ICE and free(pos + d):
        pos += d
    s.crates = sorted(pos if c == at else c for c in s.crates)
    return True


def _move_player(L: Level, s: _Scratch, a: int) -> None:
    """The player steps one cell (pushing a crate, or unlocking a door with a held key), picks up what is there, and
    keeps sliding while on ice. A slide stops at anything solid and never pushes crates."""
    d = L._delta[a]
    first = True
    while True:
        t = s.player + d
        if L.tiles[t] == _WALL or _gate_closed(L, s.phase, t) or t == s.twin:
            return
        if _locked_door(L, s.doors, t):
            if not s.held:
                return
            s.held -= 1
            s.doors = _clear(s.doors, L._door_bit[t])
        if t in s.crates and not (first and _push_crate(L, s, t, a)):
            return
        s.player = t
        k = L._key_bit.get(t, -1)
        if _has(s.keys, k):
            s.keys = _clear(s.keys, k)
            s.held += 1
        s.coins = _clear(s.coins, L._coin_bit.get(t, -1))
        if L.tiles[t] != _ICE:
            return
        first = False


def _move_twin(L: Level, s: _Scratch, a: int) -> None:
    """The twin copies each move with left and right swapped (even when the player is blocked). It cannot push,
    unlock or pick anything up, and slides on ice like the player."""
    d = L._delta[LEFT if a == RIGHT else RIGHT if a == LEFT else a]
    while True:
        t = s.twin + d
        if _solid(L, s, t) or t in s.crates or t == s.player:
            return
        s.twin = t
        if L.tiles[t] != _ICE:
            return


def _toggle_gates(L: Level, s: _Scratch) -> None:
    """Standing on a switch, "use" flips every gate, unless a gate that would close has something in it."""
    phase = 1 - s.phase
    for j, g in enumerate(L.gates):
        if L.gate_open[j] == (phase == 1) and (g == s.twin or g in s.crates):
            return
    s.phase = phase


def won(L: Level, s: State) -> bool:
    """A level is won when the exits are open and the player (and the twin, if any) stand on exits."""
    return exit_open(L, s) and L.tiles[s.player] == _EXIT and (s.twin < 0 or L.tiles[s.twin] == _EXIT)


def step(L: Level, state: State, move: int) -> Tuple[State, bool]:
    """Apply one engine move and return ``(new_state, won)``. Pure: ``state`` is not changed."""
    if move == RESTART:
        return L.start, False
    if move not in (UP, RIGHT, DOWN, LEFT, USE):
        raise ValueError(f"Engine move must be 0-5, got {move!r}")
    s = _Scratch(state)
    if move == USE:
        if L.tiles[s.player] == _SWITCH:
            _toggle_gates(L, s)
    else:
        _move_player(L, s, move)
        if s.twin >= 0:
            _move_twin(L, s, move)
    new = s.freeze()
    return new, won(L, new)


def render(L: Level, s: State) -> List[List[int]]:
    """The observation: one colour id per cell, plus a status row showing one key per key held."""
    grid: List[List[int]] = []
    crates = set(s.crates)
    open_ = exit_open(L, s)
    for y in range(L.h):
        row = []
        for x in range(L.w):
            i = y * L.w + x
            t = L.tiles[i]
            if i == s.player:
                c = Cell.PLAYER
            elif i == s.twin:
                c = Cell.TWIN
            elif i in crates:
                c = Cell.CRATE_ON_PAD if t == _PAD else Cell.CRATE
            elif _has(s.keys, L._key_bit.get(i, -1)):
                c = Cell.KEY
            elif _has(s.coins, L._coin_bit.get(i, -1)):
                c = Cell.COIN
            elif t == _WALL:
                c = Cell.WALL
            elif t == _EXIT:
                c = Cell.EXIT if open_ else Cell.EXIT_CLOSED
            elif t == _PAD:
                c = Cell.PAD
            elif t == _ICE:
                c = Cell.ICE
            elif t == _SWITCH:
                c = Cell.SWITCH
            elif t == _GATE:
                c = Cell.GATE_CLOSED if _gate_closed(L, s.phase, i) else Cell.GATE_OPEN
            elif t == _DOOR and _locked_door(L, s.doors, i):
                c = Cell.DOOR
            else:
                c = Cell.FLOOR
            row.append(c)
        grid.append(row)
    grid.append([Cell.KEY if x < s.held else Cell.WALL for x in range(L.w)])
    return grid


def solve(L: Level, limit: int = 2_000_000) -> Optional[List[int]]:
    """Breadth-first search over every reachable state. Returns the fewest engine moves that finish the level (its
    par is the length), or ``None`` if it cannot be finished. Raises ``RuntimeError`` past ``limit`` states."""
    start = L.start
    seen: Dict[State, Optional[Tuple[State, int]]] = {start: None}
    frontier = [start]
    while frontier:
        nxt: List[State] = []
        for s in frontier:
            for a in (UP, RIGHT, DOWN, LEFT, USE):
                if a == USE and L.tiles[s.player] != _SWITCH:
                    continue
                r, w = step(L, s, a)
                if r in seen:
                    continue
                seen[r] = (s, a)
                if w:
                    path: List[int] = []
                    at = r
                    link = seen[at]
                    while link is not None:
                        path.append(link[1])
                        at = link[0]
                        link = seen[at]
                    path.reverse()
                    return path
                if len(seen) > limit:
                    raise RuntimeError(f"Solver gave up after {limit} states")
                nxt.append(r)
        frontier = nxt
    return None
