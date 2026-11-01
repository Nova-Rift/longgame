"""The world maker: endless new levels and lifetimes, every one checked by the solver, with some rules held out.

Every level comes from a seed, so a name always means the same levels on any computer. ``train-v1-42`` and
``heldout-v1-42`` work anywhere a lifetime id does (``longgame.make``, ``longgame play``, ``longgame run``,
recordings and ``longgame verify``)::

    import longgame
    from longgame import worlds

    env = longgame.make("train-v1-42")               # a whole generated lifetime (28 levels)
    level = worlds.level(["keys", "ice"], tier=3, seed=7)   # one level: .map and .par
    for rules, tier, level in worlds.levels("train"):       # an endless stream of training levels
        ...

**Held-out rules.** Training material never contains coins, and never combines crates with gates, keys with ice,
or gates with the twin. Held-out lifetimes always use them: coins are one of their learn worlds, and every remix is
a held-out pair. So a score on ``heldout-v1-*`` after training on ``train-v1-*`` measures picking up a rule never
seen in training, and combining rules never seen together.

**Every level is checked.** The solver finds its fewest actions (the par, which must fall in the level's difficulty
range), and each rule in it must matter: with that rule taken out the level gets shorter (by two actions or more
after a world's first level), or the old way of finishing it stops working. Clutter checks (every crate is pushed,
every key picked up) keep levels clean.

Generation is versioned (``v1``): later versions get new names, so ``train-v1-42`` never changes.
"""

from __future__ import annotations

import hashlib
import operator
import re
from collections import deque
from functools import lru_cache
from itertools import combinations
from typing import Dict, Iterator, List, Optional, Sequence, Set, Tuple

from . import engine
from .lifetime import LevelSpec, LifetimeSpec, Visit

VERSION = "v1"

MAZE = "maze"  # the world with no rules but walls and an exit
MECHANICS = ("crates", "keys", "ice", "gates", "twin", "coins")
HELD_OUT_MECHANICS = ("coins",)
TRAIN_MECHANICS = tuple(m for m in MECHANICS if m not in HELD_OUT_MECHANICS)
HELD_OUT_PAIRS = (("crates", "gates"), ("keys", "ice"), ("gates", "twin")) + tuple(
    (m, "coins") for m in TRAIN_MECHANICS)
TRAIN_PAIRS = tuple(p for p in combinations(TRAIN_MECHANICS, 2) if p not in HELD_OUT_PAIRS)
SPLITS = ("train", "heldout")
FRAME = 12  # every generated level fits a 12x12 frame (11x11 at most, plus the status row)

# What each rule looks like on a map (see engine.py).
CHARS = {"crates": "$o*", "keys": "kD", "ice": "_", "gates": "GgS", "twin": "T", "coins": "c"}

_ID = re.compile(r"(train|heldout)-v1-(0|[1-9][0-9]{0,8})")  # used with fullmatch

Grid = List[List[str]]
Cell = Tuple[int, int]


# --- names and splits ------------------------------------------------------------------------------------------------

def rules(mechanics: Sequence[str] = ()) -> Tuple[str, ...]:
    """The canonical form of a set of rules: known names, no repeats, in :data:`MECHANICS` order."""
    names = [mechanics] if isinstance(mechanics, str) else list(mechanics)
    names = [m for m in names if m != MAZE]
    unknown = sorted(set(names) - set(MECHANICS))
    if unknown:
        raise ValueError(f"Unknown rules {unknown}; known: {', '.join(MECHANICS)} (or none, for a maze)")
    return tuple(m for m in MECHANICS if m in names)


def split_of(mechanics: Sequence[str]) -> str:
    """``"heldout"`` if these rules include a held-out rule or a held-out pair, else ``"train"``."""
    r = rules(mechanics)
    if any(m in HELD_OUT_MECHANICS for m in r) or any(p in HELD_OUT_PAIRS for p in combinations(r, 2)):
        return "heldout"
    return "train"


def recipes(split: str) -> List[Tuple[str, ...]]:
    """Every rule set a split's levels are made from: the maze, single rules and pairs."""
    if split == "train":
        return [()] + [(m,) for m in TRAIN_MECHANICS] + [rules(p) for p in TRAIN_PAIRS]
    if split == "heldout":
        return [(m,) for m in HELD_OUT_MECHANICS] + [rules(p) for p in HELD_OUT_PAIRS]
    raise ValueError(f"split must be one of {SPLITS}, got {split!r}")


def mechanics_in(rows: Sequence[str]) -> Tuple[str, ...]:
    """The rules a map uses, read from its characters."""
    text = "".join(rows)
    return tuple(m for m in MECHANICS if any(ch in text for ch in CHARS[m]))


def is_generated(name: object) -> bool:
    """True for generated lifetime ids such as ``train-v1-42`` or ``heldout-v1-7``."""
    return isinstance(name, str) and _ID.fullmatch(name) is not None


# --- deterministic randomness ----------------------------------------------------------------------------------------

def _seed(*parts: object) -> int:
    """A 32-bit seed from any parts; identical on every platform and Python version."""
    return int.from_bytes(hashlib.sha256("|".join(map(str, parts)).encode()).digest()[:4], "big")


class Rng:
    """mulberry32, the same generator as the v0 TypeScript engine's baselines, using integer maths only."""

    def __init__(self, seed: int):
        self.s = seed & 0xFFFFFFFF

    def u32(self) -> int:
        self.s = (self.s + 0x6D2B79F5) & 0xFFFFFFFF
        s = self.s
        t = ((s ^ (s >> 15)) * (1 | s)) & 0xFFFFFFFF
        t = ((t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) & 0xFFFFFFFF) ^ t
        return (t ^ (t >> 14)) & 0xFFFFFFFF

    def below(self, n: int) -> int:
        return (self.u32() * n) >> 32

    def between(self, lo: int, hi: int) -> int:
        return lo + self.below(hi - lo + 1)

    def chance(self, percent: int) -> bool:
        return self.below(100) < percent

    def choice(self, seq: Sequence):
        return seq[self.below(len(seq))]

    def shuffle(self, items: list) -> list:
        for i in range(len(items) - 1, 0, -1):
            j = self.below(i + 1)
            items[i], items[j] = items[j], items[i]
        return items

    def sample(self, seq: Sequence, k: int) -> list:
        return self.shuffle(list(seq))[:k]


# --- grids -----------------------------------------------------------------------------------------------------------

def _blank(w: int, h: int) -> Grid:
    return [["#"] * w] + [["#"] + ["."] * (w - 2) + ["#"] for _ in range(h - 2)] + [["#"] * w]


def _rows(g: Grid) -> List[str]:
    return ["".join(r) for r in g]


def _cells(g: Grid, chars: str = ".") -> List[Cell]:
    return [(y, x) for y in range(len(g)) for x in range(len(g[0])) if g[y][x] in chars]


def _around(c: Cell) -> List[Cell]:
    y, x = c
    return [(y - 1, x), (y, x + 1), (y + 1, x), (y, x - 1)]


def _reach(g: Grid, start: Cell, blocked: Set[Cell] = frozenset(), walls: str = "#") -> Dict[Cell, int]:
    """Walking distances from ``start``, treating ``walls`` characters and ``blocked`` cells as solid."""
    dist = {start: 0}
    queue = deque([start])
    while queue:
        c = queue.popleft()
        for n in _around(c):
            if n not in dist and n not in blocked and g[n[0]][n[1]] not in walls:
                dist[n] = dist[c] + 1
                queue.append(n)
    return dist


def _connected(g: Grid) -> bool:
    """Every open cell can be walked to from every other (and there is at least one)."""
    open_cells = _cells(g, ".@E$o*kD_SGgTc")
    return bool(open_cells) and len(_reach(g, open_cells[0])) == len(open_cells)


def _path(g: Grid, a: Cell, b: Cell, walls: str = "#") -> List[Cell]:
    """One shortest walking path from a to b (inclusive), or [] if there is none."""
    dist = _reach(g, a, walls=walls)
    if b not in dist:
        return []
    out = [b]
    while out[-1] != a:
        out.append(next(n for n in _around(out[-1]) if dist.get(n) == dist[out[-1]] - 1))
    return out[::-1]


def _cuts(g: Grid, a: Cell, b: Cell) -> List[Cell]:
    """Floor cells on every walking path from a to b, nearest to a first."""
    return [c for c in _path(g, a, b)[1:-1] if g[c[0]][c[1]] == "." and b not in _reach(g, a, blocked={c})]


def _doorway(g: Grid, c: Cell) -> bool:
    y, x = c
    return (g[y][x - 1] == "#" and g[y][x + 1] == "#") or (g[y - 1][x] == "#" and g[y + 1][x] == "#")


def _corner(g: Grid, c: Cell) -> bool:
    up, right, down, left = (g[n[0]][n[1]] == "#" for n in _around(c))
    return (up or down) and (left or right)


# --- layouts ---------------------------------------------------------------------------------------------------------

def _divide(g: Grid, rng: Rng, gaps: int) -> bool:
    """Wall off the room with a full line of wall that has ``gaps`` openings."""
    h, w = len(g), len(g[0])
    lines = []
    for x in range(2, w - 2):
        col = [(y, x) for y in range(1, h - 1)]
        if all(g[y][x] == "." for y, x in col) and all("#" not in (g[y][x - 1], g[y][x + 1]) for y, x in col[1:-1]):
            lines.append(col)
    for y in range(2, h - 2):
        row = [(y, x) for x in range(1, w - 1)]
        if all(g[y][x] == "." for y, x in row) and all("#" not in (g[y - 1][x], g[y + 1][x]) for y, x in row[1:-1]):
            lines.append(row)
    if not lines:
        return False
    line = rng.choice(lines)
    for y, x in line:
        g[y][x] = "#"
    if line[0][1] == line[-1][1]:  # vertical: an opening needs floor to its left and right
        ok = [(y, x) for y, x in line if g[y][x - 1] == "." and g[y][x + 1] == "."]
    else:
        ok = [(y, x) for y, x in line if g[y - 1][x] == "." and g[y + 1][x] == "."]
    if len(ok) < gaps:
        return False
    for y, x in rng.sample(ok, gaps):
        g[y][x] = "."
    return True


def _blocks(g: Grid, rng: Rng, n: int) -> None:
    """Add up to ``n`` short wall segments, keeping every open cell reachable."""
    for _ in range(n):
        cells = _cells(g)
        if len(cells) < 8:
            return
        y, x = rng.choice(cells)
        dy, dx = (0, 1) if rng.below(2) else (1, 0)
        seg = [(y + i * dy, x + i * dx) for i in range(rng.between(1, 3))]
        if any(g[a][b] != "." for a, b in seg):
            continue
        for a, b in seg:
            g[a][b] = "#"
        if not _connected(g):
            for a, b in seg:
                g[a][b] = "."


def _maze(rng: Rng, w: int, h: int, loops: int) -> Grid:
    """A maze carved by a randomised depth-first search on odd cells, with ``loops`` extra openings."""
    g = [["#"] * w for _ in range(h)]
    start = (2 * rng.below((h - 1) // 2) + 1, 2 * rng.below((w - 1) // 2) + 1)
    g[start[0]][start[1]] = "."
    stack = [start]
    while stack:
        y, x = stack[-1]
        options = [(y + dy, x + dx, y + dy // 2, x + dx // 2) for dy, dx in ((-2, 0), (0, 2), (2, 0), (0, -2))
                   if 0 < y + dy < h - 1 and 0 < x + dx < w - 1 and g[y + dy][x + dx] == "#"]
        if not options:
            stack.pop()
            continue
        ny, nx, wy, wx = rng.choice(options)
        g[wy][wx] = g[ny][nx] = "."
        stack.append((ny, nx))
    walls = [(y, x) for y in range(1, h - 1) for x in range(1, w - 1) if g[y][x] == "#" and (
        (g[y][x - 1] == "." and g[y][x + 1] == ".") or (g[y - 1][x] == "." and g[y + 1][x] == "."))]
    for y, x in rng.sample(walls, min(loops, len(walls))):
        g[y][x] = "."
    return g


# --- placing each rule's pieces --------------------------------------------------------------------------------------

class _Ctx:
    """The level being built: player and exit cells and the difficulty tier."""

    def __init__(self, rng: Rng, recipe: Tuple[str, ...], tier: int, player: Cell, exits: List[Cell]):
        self.rng, self.recipe, self.tier, self.player, self.exits = rng, recipe, tier, player, exits

    @property
    def exit(self) -> Cell:
        return self.exits[0]


def _gate_cells(g: Grid, ctx: _Ctx, n: int) -> Optional[List[Cell]]:
    """Up to ``n`` cells (at least one, never side by side) that every route from the player to the exit must
    cross, doorways preferred."""
    cuts = _cuts(g, ctx.player, ctx.exit)
    doors = [c for c in cuts if _doorway(g, c)]
    pool = doors if len(doors) >= n else cuts
    chosen: List[Cell] = []
    for c in ctx.rng.shuffle(list(pool)):
        if len(chosen) < n and all(abs(c[0] - d[0]) + abs(c[1] - d[1]) > 1 for d in chosen):
            chosen.append(c)
    if not chosen:
        return None
    return [c for c in pool if c in chosen]  # nearest the player first


def _regions(g: Grid, ctx: _Ctx, pieces: List[Cell]) -> List[List[Cell]]:
    """Floor cells first reachable from the player after passing 0, 1, 2, ... of ``pieces`` (nearest first)."""
    out: List[List[Cell]] = []
    seen: Set[Cell] = set()
    for i in range(len(pieces) + 1):
        reach = _reach(g, ctx.player, blocked=set(pieces[i:]))
        out.append([c for c in reach if c not in seen and g[c[0]][c[1]] == "."])
        seen |= set(reach)
    return out


def _spot(g: Grid, ctx: _Ctx, cells: List[Cell], off_route: int) -> Optional[Cell]:
    """A random cell from ``cells``, off the walking route to the exit ``off_route`` percent of the time if it can."""
    route = set(_path(g, ctx.player, ctx.exit))
    away = [c for c in cells if c not in route]
    pool = away if away and ctx.rng.chance(off_route) else cells
    return ctx.rng.choice(pool) if pool else None


def _place_keys(g: Grid, ctx: _Ctx) -> bool:
    """Doors where every route must pass, and each door's key before it (past the doors before that)."""
    rng = ctx.rng
    n = {1: 1, 2: rng.between(1, 2), 3: 2}[ctx.tier]
    doors = _gate_cells(g, ctx, n)
    if doors is None:
        return False
    for y, x in doors:
        g[y][x] = "D"
    for region in _regions(g, ctx, doors)[:-1]:
        spot = _spot(g, ctx, region, 75)
        if spot is None:
            return False
        g[spot[0]][spot[1]] = "k"
    return True


def _place_gates(g: Grid, ctx: _Ctx) -> bool:
    """Gates where every route must pass, starting closed, open, closed, ... so the player must flip them before each
    one, and a switch wherever a flip is needed."""
    rng = ctx.rng
    n = {1: 1, 2: rng.between(1, 2), 3: rng.between(2, 3)}[ctx.tier]
    gates = _gate_cells(g, ctx, n)
    if gates is None:
        return False
    for i, (y, x) in enumerate(gates):
        g[y][x] = "G" if i % 2 == 0 else "g"
    regions = _regions(g, ctx, gates)
    for i in range(len(gates)):
        spot = _spot(g, ctx, regions[i], 70)
        if spot is None:
            return False
        g[spot[0]][spot[1]] = "S"
    return True


def _place_crates(g: Grid, ctx: _Ctx) -> bool:
    rng = ctx.rng
    if len(ctx.recipe) > 1:
        n = 1 if ctx.tier == 2 or "twin" in ctx.recipe else rng.between(1, 2)
    else:
        n = {1: 1, 2: rng.between(1, 2), 3: 2}[ctx.tier]
    for _ in range(n):
        spots = _cells(g)
        if not spots:
            return False
        y, x = rng.choice(spots)
        g[y][x] = "o"
    for _ in range(n):  # crates start clear of walls if possible, and never where they could not move
        free = _cells(g)
        spots = [c for c in free if all(g[a][b] != "#" for a, b in _around(c))] or [
            (y, x) for y, x in free if not _corner(g, (y, x)) and (
                (g[y][x - 1] != "#" and g[y][x + 1] != "#") or (g[y - 1][x] != "#" and g[y + 1][x] != "#"))]
        if not spots:
            return False
        y, x = rng.choice(spots)
        g[y][x] = "$"
    return True


def _place_ice(g: Grid, ctx: _Ctx) -> bool:
    rng = ctx.rng
    h, w = len(g), len(g[0])
    if len(ctx.recipe) > 1 and rng.chance(50):  # a rink covering part of the room
        rw, rh = rng.between(max(2, (w - 2) // 2), w - 2), rng.between(max(2, (h - 2) // 2), h - 2)
        x0, y0 = rng.between(1, w - 1 - rw), rng.between(1, h - 1 - rh)
        area = [(y, x) for y in range(y0, y0 + rh) for x in range(x0, x0 + rw)]
    else:  # ice almost everywhere; the floor cells left are places to stop
        area = [(y, x) for y in range(1, h - 1) for x in range(1, w - 1)]
    keep = rng.between(8, 30)
    for y, x in area:
        if g[y][x] == "." and not rng.chance(keep):
            g[y][x] = "_"
    return bool(_cells(g, "_"))


def _place_coins(g: Grid, ctx: _Ctx) -> bool:
    rng = ctx.rng
    n = {1: rng.between(1, 2), 2: rng.between(2, 3), 3: rng.between(3, 4)}[ctx.tier]
    route = set(_path(g, ctx.player, ctx.exit, walls="#"))
    spots = [c for c in _cells(g) if c not in route] or _cells(g)
    if len(spots) < n:
        return False
    for y, x in rng.sample(spots, n):
        g[y][x] = "c"
    return True


_PLACE = {"keys": _place_keys, "gates": _place_gates, "crates": _place_crates, "ice": _place_ice,
          "coins": _place_coins}
_ORDER = ("keys", "gates", "crates", "coins", "ice")  # gating pieces first, while routes are easy to read


# --- candidates ------------------------------------------------------------------------------------------------------

def _size(rng: Rng, recipe: Tuple[str, ...], tier: int) -> Tuple[int, int]:
    if len(recipe) >= 2:
        if tier == 1:
            return rng.between(7, 9), rng.between(4, 6)
        if "crates" in recipe and "twin" in recipe:
            return rng.between(7, 8), rng.between(5, 6)
        if "crates" in recipe:
            return rng.between(7, 9), rng.between(5, 7)
        return rng.between(8, 11), rng.between(6, 8)
    if "crates" in recipe:
        return {1: (rng.between(7, 9), rng.between(4, 5)), 2: (rng.between(7, 8), rng.between(5, 7)),
                3: (rng.between(7, 9), rng.between(6, 7))}[tier]
    return {1: (rng.between(7, 11), rng.between(3, 5)), 2: (rng.between(8, 10), rng.between(5, 7)),
            3: (rng.between(9, 11), rng.between(6, 8))}[tier]


def _candidate(rng: Rng, recipe: Tuple[str, ...], tier: int) -> Optional[List[str]]:
    if not recipe:  # the maze world
        w, h = {1: (rng.choice((7, 9)), rng.choice((5, 7))), 2: (rng.choice((9, 11)), rng.choice((7, 9))),
                3: (11, rng.choice((9, 11)))}[tier]
        g = _maze(rng, w, h, loops={1: 0, 2: 1, 3: 2}[tier])
        cells = _cells(g)
        player = rng.choice(cells)
        dist = _reach(g, player)
        far = max(dist.values())
        exit_ = rng.choice([c for c in cells if dist[c] >= (far * 3) // 4 and c != player] or [player])
        if exit_ == player:
            return None
        g[player[0]][player[1]], g[exit_[0]][exit_[1]] = "@", "E"
        return _rows(g)

    w, h = _size(rng, recipe, tier)
    g = _blank(w, h)
    gating = any(m in recipe for m in ("keys", "gates"))
    if gating:
        for _ in range(1 if tier == 1 else rng.between(1, 2)):
            _divide(g, rng, gaps=1)
    elif h >= 5 and rng.chance(35):
        _divide(g, rng, gaps=rng.between(1, 2))
    _blocks(g, rng, {1: rng.between(0, 2), 2: rng.between(1, 4), 3: rng.between(2, 6)}[tier]
            + (2 * tier if "ice" in recipe else 0))  # on ice, walls are where slides stop
    if not _connected(g):
        return None

    cells = _cells(g)
    if len(cells) < 6:
        return None
    player = rng.choice(cells)
    dist = _reach(g, player)
    far = max(dist.values())
    if far < 3:
        return None
    exits = [rng.choice([c for c in cells if dist[c] >= max(2, far // 2)])]
    if "twin" in recipe:
        twin = (player[0], w - 1 - player[1])
        if twin == player or g[twin[0]][twin[1]] != "." or rng.chance(30):
            twin = rng.choice([c for c in cells if c != player])
        mirror = (exits[0][0], w - 1 - exits[0][1])
        if mirror in (player, twin) or g[mirror[0]][mirror[1]] != "." or rng.chance(40):
            options = [c for c in cells if c not in (player, twin, exits[0])]
            mirror = rng.choice(options)
        exits.append(mirror)
        g[twin[0]][twin[1]] = "T"
    if exits[0] == player:
        return None
    g[player[0]][player[1]] = "@"
    for y, x in exits:
        g[y][x] = "E"
    ctx = _Ctx(rng, recipe, tier, player, exits)
    for m in _ORDER:
        if m in recipe and not _PLACE[m](g, ctx):
            return None
    return _rows(g)


# --- checks ----------------------------------------------------------------------------------------------------------

# Fewest-actions ranges by tier. A rule's tiers never overlap, so each level of a visit takes more actions than the
# one before. Ice levels are shorter (a slide covers ground in one action), and so are twin levels.
_PAR = {1: (4, 10), 2: (11, 17), 3: (18, 26)}
_PAR_RULE = {"ice": {1: (3, 5), 2: (6, 8), 3: (9, 16)}, "twin": {1: (3, 7), 2: (8, 12), 3: (13, 20)},
             MAZE: {1: (6, 10), 2: (11, 17), 3: (18, 26)}}
_LIMIT = 40_000  # solver states per check; bigger levels are rejected rather than waited for
_ABLATE = {"crates": {"$": ".", "o": ".", "*": "."}, "keys": {"k": ".", "D": "."}, "ice": {"_": "."},
           "gates": {"G": ".", "g": ".", "S": "."}, "twin": {"T": "."}, "coins": {"c": "."}}
_PIECES = "GgSD"  # gates, switches and doors: taking away any one of them must change the par


def par_range(recipe: Sequence[str], tier: int) -> Tuple[int, int]:
    """The fewest-actions range a level of these rules and tier must fall in. For two rules it is the mean of their
    ranges, plus 3."""
    recipe = rules(recipe) or (MAZE,)
    tier = _whole(tier, "tier", 1, 4)
    ranges = [_PAR_RULE.get(m, _PAR)[tier] for m in recipe]
    if len(ranges) == 1:
        return ranges[0]
    return sum(r[0] for r in ranges) // len(ranges) + 3, sum(r[1] for r in ranges) // len(ranges) + 3


def without(rows: Sequence[str], mechanic: str) -> List[str]:
    """The same map with one rule's pieces taken out."""
    swap = _ABLATE[mechanic]
    return ["".join(swap.get(ch, ch) for ch in r) for r in rows]


class _TooBig(Exception):
    """The solver hit its state limit: the level's par cannot be confirmed cheaply."""


def _solve(rows: Sequence[str]) -> Optional[List[int]]:
    """The fewest moves, ``None`` if the level cannot be finished, or ``_TooBig``."""
    try:
        return engine.solve(engine.parse_level(rows), limit=_LIMIT)
    except RuntimeError:
        raise _TooBig from None


def _wins(rows: Sequence[str], moves: Sequence[int]) -> bool:
    L = engine.parse_level(rows)
    s = L.start
    for m in moves:
        s, won = engine.step(L, s, m)
        if won:
            return True
    return False


class _Trace:
    """What happened when the solution was played: slides, crates pushed, keys left, twin moves."""

    def __init__(self, rows: Sequence[str], moves: Sequence[int]):
        L = engine.parse_level(rows)
        s = L.start
        self.slides = self.desyncs = 0
        where = list(s.crates)  # each crate's cell, followed crate by crate
        moved = [False] * len(where)
        for m in moves:
            r, _ = engine.step(L, s, m)
            if m != engine.USE:
                py, px = divmod(s.player, L.w)
                ry, rx = divmod(r.player, L.w)
                if abs(py - ry) + abs(px - rx) > 1:
                    self.slides += 1
                if s.twin >= 0 and (s.player == r.player) != (s.twin == r.twin):
                    self.desyncs += 1
            gone = [c for c in s.crates if c not in r.crates]  # one move pushes at most one crate
            if gone:
                i = where.index(gone[0])
                where[i] = next(c for c in r.crates if c not in s.crates)
                moved[i] = True
            s = r
        self.idle_crates = moved.count(False)
        self.keys_left = bin(s.keys).count("1")


def check(rows: Sequence[str], recipe: Sequence[str], tier: int) -> Optional[int]:
    """The level's par if it passes every check for these rules and tier, else ``None``:

    - it can be finished, and its par (the fewest actions) is in :func:`par_range`;
    - every rule matters: without it the level is shorter (by 2 or more after tier 1), or for ice and the twin the
      old way of finishing it fails;
    - nothing is clutter: every crate gets pushed and every key picked up, and taking away any one gate, switch or
      door changes the par;
    - ice levels need a slide (two after tier 1), and twin levels after tier 1 need the twin and the player to part.
    """
    recipe = rules(recipe)
    try:
        return _check(rows, recipe, _whole(tier, "tier", 1, 4))
    except _TooBig:
        return None


def _stuck_crate(rows: Sequence[str]) -> bool:
    """True if there are no more crates than pads and some crate can never reach any pad even with only walls in the
    way, so the level cannot be finished: a quick test that saves solving hopeless levels. Pulling crates back from
    the pads finds every cell a crate could be pushed to a pad from."""
    pads, crates = _cells(rows, "o*"), _cells(rows, "$*")  # type: ignore[arg-type]
    if len(crates) > len(pads):
        return False  # a spare crate may stay where it is
    live = set(pads)
    queue = deque(pads)
    while queue:
        y, x = queue.popleft()
        for dy, dx in ((-1, 0), (0, 1), (1, 0), (0, -1)):
            cy, cx, py, px = y - dy, x - dx, y - 2 * dy, x - 2 * dx  # the crate came from c, pushed from p
            if (0 <= py < len(rows) and 0 <= px < len(rows[0]) and rows[cy][cx] != "#" and rows[py][px] != "#"
                    and (cy, cx) not in live):
                live.add((cy, cx))
                queue.append((cy, cx))
    return any(c not in live for c in crates)


def _check(rows: Sequence[str], recipe: Tuple[str, ...], tier: int) -> Optional[int]:
    if "crates" in recipe and _stuck_crate(rows):
        return None
    path = _solve(rows)
    if path is None:
        return None
    par = len(path)
    lo, hi = par_range(recipe, tier)
    if not lo <= par <= hi:
        return None
    trace = _Trace(rows, path)
    if trace.idle_crates or trace.keys_left:
        return None
    if "ice" in recipe and trace.slides < min(tier, 2):
        return None
    if "twin" in recipe and tier >= 2 and trace.desyncs < 1:
        return None
    for m in recipe:
        other = _solve(without(rows, m))
        if other is None:  # cannot happen for these rules, but never trust it
            return None
        if m != "ice" and len(other) <= par - (1 if tier == 1 else 2):
            continue  # the rule makes the level longer (past the first level, by more than one press)
        if m in ("ice", "twin") and not _wins(rows, other):
            continue  # the rule changes what works
        return None
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in _PIECES:
                other = _solve([*rows[:y], row[:x] + "." + row[x + 1:], *rows[y + 1:]])
                if other is not None and len(other) == par:
                    return None  # this piece changes nothing
    return par


# --- levels and lifetimes --------------------------------------------------------------------------------------------

_ATTEMPTS = 6000  # candidates per level; the slowest rule set and tier (crates+ice, 3) needs about 170 on average
SEEDS = 10 ** 9  # lifetime seeds per split: train-v1-0 to train-v1-999999999
LEVEL_SEEDS = 2 ** 32  # seeds for level() and levels()


def _whole(x: object, name: str, lo: int, hi: int) -> int:
    """``x`` as a plain int in [lo, hi), or ValueError. Normalised, so the seed text hashed is the same everywhere."""
    if isinstance(x, bool):
        raise ValueError(f"{name} must be a whole number, got {x!r}")
    try:
        v = int(operator.index(x))
    except TypeError:
        raise ValueError(f"{name} must be a whole number, got {x!r}") from None
    if not lo <= v < hi:
        raise ValueError(f"{name} must be from {lo} to {hi - 1}, got {v}")
    return v


def _split(split: object) -> str:
    if not isinstance(split, str) or split not in SPLITS:
        raise ValueError(f"split must be one of {', '.join(SPLITS)}, got {split!r}")
    return SPLITS[SPLITS.index(split)]


def level(mechanics: Sequence[str] = (), tier: int = 2, seed: int = 0) -> LevelSpec:
    """One generated level with these rules (none for a maze, or one or two of :data:`MECHANICS`) at difficulty
    ``tier`` 1 (a first, tutorial level), 2 or 3, from ``seed`` (0 to 2**32 - 1). The same arguments always give the
    same level."""
    recipe = rules(mechanics)
    if len(recipe) > 2:
        raise ValueError(f"The {VERSION} world maker combines at most two rules, got {'+'.join(recipe)}")
    tier = _whole(tier, "tier", 1, 4)
    seed = _whole(seed, "seed", 0, LEVEL_SEEDS)
    rng = Rng(_seed("level", VERSION, ",".join(recipe) or MAZE, tier, seed))
    for _ in range(_ATTEMPTS):
        rows = _candidate(rng, recipe, tier)
        if rows is None:
            continue
        par = check(rows, recipe, tier)
        if par is not None:
            return LevelSpec(par, tuple(rows))
    raise RuntimeError(f"Could not make a {'+'.join(recipe) or MAZE} level at tier {tier} from seed {seed}")


def levels(split: str = "train", seed: int = 0) -> Iterator[Tuple[Tuple[str, ...], int, LevelSpec]]:
    """An endless stream of ``(rules, tier, level)`` from one split's rule sets, in a seeded random order."""
    split, seed = _split(split), _whole(seed, "seed", 0, LEVEL_SEEDS)
    return _stream(split, seed)


def _stream(split: str, seed: int) -> Iterator[Tuple[Tuple[str, ...], int, LevelSpec]]:
    pool = recipes(split)
    rng = Rng(_seed("stream", VERSION, split, seed))
    i = 0
    while True:
        recipe, tier = rng.choice(pool), rng.between(1, 3)
        yield recipe, tier, level(recipe, tier, _seed("stream-level", VERSION, split, seed, i))
        i += 1


def _letters():
    return [chr(ord("A") + i) for i in range(26)]


def generate(split: str = "train", seed: int = 0) -> LifetimeSpec:
    """A generated lifetime in the shape of practice-v0: learn a maze and five rule worlds (2 + 5 x 3 levels), play
    three remixes of two learned rules (2 levels each), then return to the five rule worlds (1 new level each).
    Within a visit, levels get harder (tier 1, 2, 3) and each takes more actions than the one before."""
    split, seed = _split(split), _whole(seed, "seed", 0, SEEDS)
    rng = Rng(_seed("lifetime", VERSION, split, seed))
    if split == "train":
        learned = rng.shuffle(list(TRAIN_MECHANICS))
        remixes = [rules(p) for p in rng.sample(TRAIN_PAIRS, 3)]
    else:  # the new rule and four familiar ones; remixes mix familiar rules in new ways, and the new rule in
        learned = rng.shuffle(rng.sample(TRAIN_MECHANICS, 4) + list(HELD_OUT_MECHANICS))
        usable = [rules(p) for p in HELD_OUT_PAIRS if all(m in learned for m in p)]
        familiar = rng.shuffle([p for p in usable if not set(p) & set(HELD_OUT_MECHANICS)])
        novel = rng.shuffle([p for p in usable if set(p) & set(HELD_OUT_MECHANICS)])
        first = familiar[:1] + novel[:1]
        remixes = rng.shuffle(first + rng.sample(familiar[1:] + novel[1:], 3 - len(first)))
    letters = _letters()
    plan: List[Tuple[str, str, Tuple[str, ...], List[int]]] = [(letters[0], "learn", (), [1, 2])]
    world_of: Dict[Tuple[str, ...], str] = {}
    for i, m in enumerate(learned):
        world_of[(m,)] = letters[1 + i]
        plan.append((letters[1 + i], "learn", (m,), [1, 2, 3]))
    for i, r in enumerate(remixes):
        plan.append((letters[1 + len(learned) + i], "remix", r, [2, 3]))
    for m in rng.shuffle(list(learned)):
        plan.append((world_of[(m,)], "return", (m,), [3]))
    visits = tuple(Visit(world, phase, tuple(level(recipe, tier, _seed("lifetime-level", VERSION, split, seed, v, j))
                                             for j, tier in enumerate(tiers)))
                   for v, (world, phase, recipe, tiers) in enumerate(plan))
    kind = "training" if split == "train" else "held-out"
    described = "; ".join(f"{w} {'+'.join(r or (MAZE,))}" for w, _, r, _ in plan[:1 + len(learned) + len(remixes)])
    return LifetimeSpec(id=f"{split}-{VERSION}-{seed}", title=f"Generated {kind} lifetime {seed}",
                        description=(f"Made by the world maker ({VERSION}) from seed {seed}: learn six worlds, play "
                                     f"three remixes, return to five. Worlds: {described}."),
                        phases=("learn", "remix", "return"), visits=visits)


@lru_cache(maxsize=32)
def lifetime(name: str) -> LifetimeSpec:
    """The generated lifetime with this id, e.g. ``train-v1-42``."""
    m = _ID.fullmatch(name) if isinstance(name, str) else None
    if not m:
        raise ValueError(f"Not a generated lifetime id: {name!r} (expected e.g. train-v1-42 or heldout-v1-42)")
    try:
        return generate(m.group(1), int(m.group(2)))
    except RuntimeError as e:  # never seen; reported like any other bad lifetime
        raise ValueError(f"Could not generate {name}: {e}") from None


def world_rules(spec: LifetimeSpec) -> Dict[str, Tuple[str, ...]]:
    """Which rules each world of any lifetime uses (read from its maps); ``()`` is a maze."""
    out: Dict[str, Tuple[str, ...]] = {}
    for v in spec.visits:
        found = set(out.get(v.world, ()))
        for lv in v.levels:
            found |= set(mechanics_in(lv.map))
        out[v.world] = tuple(m for m in MECHANICS if m in found)
    return out
