"""Draws the README figures from the real engine and levels. Run from the repository root:

    PYTHONPATH=src python3 docs/figures/make_figures.py

Writes docs/figures/*.svg, play.gif and worlds.gif (the GIFs need Pillow).
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

from longgame import engine, load_spec, worlds
from longgame.engine import Cell

OUT = Path(__file__).resolve().parent
FONT = "Inter, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "'SF Mono', Menlo, Consolas, 'DejaVu Sans Mono', monospace"
PANEL, BOARD, FLOOR = "#15141c", "#0e0d13", "#1d1b25"
INK, INK2, MUTED, LINE = "#ecebf2", "#b4afc4", "#8f8aa0", "#2c2a36"
LEARN, REMIX, RETURN = "#4c8ff7", "#f0b443", "#1f9d55"
TRAIN, HELD = "#3987e5", "#d95926"  # validated pair on PANEL (CVD-safe)


# --- drawing primitives ------------------------------------------------------------------------------------------

def rect(x, y, w, h, r, fill, extra=""):
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r:.1f}" fill="{fill}"{extra}/>'


def ring(x, y, w, h, r, width, colour):
    o = width / 2
    return (f'<rect x="{x + o:.1f}" y="{y + o:.1f}" width="{w - width:.1f}" height="{h - width:.1f}" rx="{r:.1f}" '
            f'fill="none" stroke="{colour}" stroke-width="{width:.1f}"/>')


def circle(cx, cy, r, fill):
    return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}"/>'


def text(x, y, s, size=13, fill=INK, weight=400, anchor="start", family=FONT, extra=""):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}"{extra}>{escape(s)}</text>')


def cell_svg(c, x, y, s, hud=False):
    """One cell, drawn like the browser player."""
    r, b = max(1.5, s * 0.12), max(1.2, s * 0.09)
    base = {Cell.WALL: "#2c2a36" if hud else "#5d5a6b", Cell.EXIT: "#1f9d55", Cell.DOOR: "#8a6a12",
            Cell.ICE: "#a8e4f0", Cell.GATE_CLOSED: "#7a4ad8"}.get(c, FLOOR)
    out = [rect(x, y, s, s, r, base)]
    cx, cy = x + s / 2, y + s / 2
    if c == Cell.PLAYER:
        out.append(circle(cx, cy, s * 0.38, "#4c8ff7"))
    elif c == Cell.TWIN:
        out.append(circle(cx, cy, s * 0.38, "#e5484d"))
    elif c == Cell.EXIT_CLOSED:
        out.append(ring(x, y, s, s, r, b, "#1f6b3f"))
    elif c in (Cell.CRATE, Cell.CRATE_ON_PAD):
        if c == Cell.CRATE_ON_PAD:
            out.append(ring(x, y, s, s, r, b, "#d29a35"))
        i = s * 0.1
        fill, edge = ("#f0b443", "#b07a1d") if c == Cell.CRATE_ON_PAD else ("#b8682a", "#8a4b1c")
        out.append(rect(x + i, y + i, s - 2 * i, s - 2 * i, r * 0.7, fill))
        out.append(ring(x + i, y + i, s - 2 * i, s - 2 * i, r * 0.7, b, edge))
    elif c == Cell.PAD:
        out.append(ring(x, y, s, s, r, b, "#d29a35"))
    elif c == Cell.KEY:
        k = s * 0.32
        out.append(f'<rect x="{-k / 2:.1f}" y="{-k / 2:.1f}" width="{k:.1f}" height="{k:.1f}" rx="1.5" fill="#f5d02f" '
                   f'transform="translate({cx:.1f} {cy:.1f}) rotate(45)"/>')
    elif c == Cell.DOOR:
        out.append(rect(x + s * 0.42, y + s * 0.36, s * 0.16, s * 0.28, s * 0.06, "#3a2d06"))
    elif c == Cell.SWITCH:
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{s * 0.28:.1f}" fill="none" stroke="#e2559c" '
                   f'stroke-width="{b:.1f}"/>')
    elif c == Cell.GATE_OPEN:
        out.append(ring(x, y, s, s, r, max(1.0, b * 0.7), "#4f3a7c"))
    elif c == Cell.COIN:
        out.append(circle(cx, cy, s * 0.16, "#f3f3f3"))
    return "".join(out)


def board_svg(grid, x, y, cell, pad=None, hud=True):
    """A whole board; returns (svg, width, height). ``hud=False`` drops the status row."""
    rows = grid if hud else grid[:-1]
    pad = cell * 0.35 if pad is None else pad
    gap = max(1.0, cell * 0.08)
    w, h = len(rows[0]) * cell + 2 * pad, len(rows) * cell + 2 * pad
    out = [rect(x, y, w, h, max(4, cell * 0.3), BOARD)]
    for yy, row in enumerate(rows):
        for xx, c in enumerate(row):
            out.append(cell_svg(c, x + pad + xx * cell + gap / 2, y + pad + yy * cell + gap / 2, cell - gap,
                                hud and yy == len(rows) - 1))
    return "".join(out), w, h


def svg(width, height, body, label):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" '
            f'height="{height}" role="img" aria-label="{escape(label)}">'
            f'{rect(0, 0, width, height, 16, PANEL)}{body}</svg>\n')


def first_grid(rows):
    level = engine.parse_level(rows)
    return engine.render(level, level.start)


def arrow(x1, y1, x2, y2, colour=MUTED, width=1.6):
    """A straight line with a small arrowhead at (x2, y2)."""
    import math
    a = math.atan2(y2 - y1, x2 - x1)
    h = 7
    p1 = (x2 - h * math.cos(a - 0.45), y2 - h * math.sin(a - 0.45))
    p2 = (x2 - h * math.cos(a + 0.45), y2 - h * math.sin(a + 0.45))
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{colour}" stroke-width="{width}" '
            f'stroke-linecap="round"/><polygon points="{x2:.1f},{y2:.1f} {p1[0]:.1f},{p1[1]:.1f} '
            f'{p2[0]:.1f},{p2[1]:.1f}" fill="{colour}"/>')


# --- figures -----------------------------------------------------------------------------------------------------

def fig_lifetime():
    spec = load_spec("practice-v0")
    rows = [("1", "Learn", LEARN, "6 new worlds"), ("2", "Remix", REMIX, "rules combined"),
            ("3", "Return", RETURN, "old worlds, new levels")]
    mixes = {"G": "B + D", "H": "C + E", "I": "B + F"}
    cell, slot, x0, W = 8, 112, 196, 900
    body = [text(32, 46, "One lifetime", 22, INK, 700),
            text(32, 70, "practice-v0: 14 visits, 28 levels, played in order by one agent that is never reset",
                 13, INK2)]
    y = 96
    for num, phase, colour, note in rows:
        visits = [v for v in spec.visits if v.phase == phase.lower()]
        boards = [board_svg(first_grid(v.levels[0].map), 0, 0, cell, hud=False) for v in visits]
        row_h = max(h for _, _, h in boards)
        body.append(rect(32, y, 6, row_h + 30, 3, colour))
        body.append(text(50, y + 22, f"{num}  {phase}", 17, INK, 700))
        body.append(text(50, y + 42, note, 12, INK2))
        for i, (v, (_, w, h)) in enumerate(zip(visits, boards)):
            bx, by = x0 + i * slot + (slot - 16 - w) / 2, y + row_h - h
            body.append(board_svg(first_grid(v.levels[0].map), bx, by, cell, hud=False)[0])
            label = v.world if phase == "Learn" else (f"{v.world}  = {mixes[v.world]}" if phase == "Remix"
                                                      else f"{v.world} again")
            body.append(text(x0 + i * slot + (slot - 16) / 2, y + row_h + 22, label, 13, INK, 600, "middle"))
            if i < len(visits) - 1:
                ax = x0 + (i + 1) * slot - 12
                body.append(arrow(ax - 6, y + row_h / 2, ax + 2, y + row_h / 2))
        y += row_h + 58
    body.append(text(32, y + 4, "Remix worlds mix rules the agent met separately. Return worlds test whether it "
                                "still knows them after playing others.", 13, INK2))
    H = y + 30
    return svg(W, H, "".join(body), "One lifetime: learn six worlds, play three remixes, return to five")


def fig_gate():
    """The gate: a fact taught in one world is the only way to win a later one, so passing it proves learning."""
    GATE = "#d9534f"
    W, H = 900, 300
    body = [text(32, 46, "Gated worlds", 22, INK, 700),
            text(32, 70, "Every level is locked by the lesson of the one before it: pass it and the learning is "
                         "proven", 13, INK2)]

    def mark(x, y, s, kind, lit=False):
        """A square of the level: ground, a gate (hatched), or the switch (a ring), lit when the level points it out."""
        if kind == 4:
            out = [rect(x, y, s, s, 3, "#9b7fe0" if lit else "#6b5d8c"),
                   f'<circle cx="{x + s / 2:.1f}" cy="{y + s / 2:.1f}" r="{s * 0.3:.1f}" fill="none" '
                   f'stroke="#ffd166" stroke-width="3"/>', circle(x + s / 2, y + s / 2, s * 0.1, "#ffd166")]
            return "".join(out)
        if kind == 2:
            return (rect(x, y, s, s, 3, "#4a3a26") +
                    "".join(rect(x + s * k, y + 2, s * 0.16, s - 4, 1, "#a07a4a") for k in (0.1, 0.42, 0.74)))
        return rect(x, y, s, s, 3, "#2a2838")

    def world(x, y, title, colour, glyph_order, show_meter, clock, note):
        w, h = 236, 150
        out = [rect(x, y, w, h, 12, BOARD), rect(x, y, 6, h, 3, colour), text(x + 18, y + 24, title, 15, INK, 700)]
        s = 30
        for i, g in enumerate(glyph_order):
            out.append(mark(x + 18 + i * (s + 10), y + 40, s, g, lit=(g == 4 and show_meter)))
        if show_meter:
            out.append(rect(x + 18, y + 84, 150, 8, 4, LINE))
            out.append(rect(x + 18, y + 84, 110, 8, 4, LEARN))
            out.append(text(x + 176, y + 92, "meter", 11, INK2))
        else:
            out.append(text(x + 18, y + 92, "no meter, no examples", 11, MUTED))
        out.append(text(x + 18, y + 114, clock, 12, INK2))
        out.append(text(x + 18, y + 134, note, 11, MUTED))
        return "".join(out)

    body.append(world(32, 96, "Level n: the lesson", LEARN, [1, 2, 3, 4], True, "a switch opens the way out",
                      "the agent has to use it to get anywhere"))
    body.append(arrow(276, 171, 316, 171))
    body.append(rect(320, 140, 90, 62, 10, FLOOR))
    body.append(text(365, 166, "other", 12, INK2, 400, "middle"))
    body.append(text(365, 184, "worlds…", 12, INK2, 400, "middle"))
    body.append(arrow(416, 171, 456, 171))
    body.append(world(460, 96, "Level n+1: the gate", GATE, [2, 1, 4, 3], False, "the exit is behind a switch",
                      "nothing says so; the agent must know"))
    body.append(text(720, 128, "fresh agent", 12, INK2))
    body.append(rect(720, 136, 120, 10, 5, LINE))
    body.append(text(848, 145, "0%", 12, GATE, 700))
    body.append(text(720, 176, "agent that learned level n", 12, INK2))
    body.append(rect(720, 184, 120, 10, 5, LINE))
    body.append(rect(720, 184, 120, 10, 5, LEARN))
    body.append(text(848, 193, "wins", 12, LEARN, 700))
    body.append(text(720, 226, "Weights track: context is wiped", 11, MUTED))
    body.append(text(720, 242, "between visits, so only learning", 11, MUTED))
    body.append(text(720, 258, "that reached the weights passes.", 11, MUTED))
    body.append(text(32, 276, "Solvable levels still measure how much carries over; gated levels prove that something did.",
                     13, INK2))
    return svg(W, H, "".join(body), "Gated worlds: a level makes the agent use a mechanic, and a later level can only "
                                    "be finished with it; an agent that did not learn it scores 0")


def fig_skirmish():
    """The Skirmish battle: the enemy base behind a ring of gates; the three ways in, each learned by needing it."""
    W, H = 900, 330
    cell, ox, oy = 11, 32, 96
    cols, rows = 24, 16
    body = [text(32, 46, "Skirmish: the same test as a real-time battle", 22, INK, 700),
            text(32, 70, "14 battles against a scripted bot; the enemy base sits behind gates, and the way in is "
                         "something an earlier battle made you use", 13, INK2)]
    body.append(rect(ox, oy, cols * cell, rows * cell, 8, "#3a352d"))
    def sq(x, y, fill, extra=""):
        return rect(ox + x * cell, oy + y * cell, cell, cell, 2, fill, extra)
    # mines, walls, the middle
    for (x, y) in [(5, 1), (5, 2), (4, 4), (1, 5), (2, 5), (18, 14), (18, 13), (19, 11), (22, 10), (21, 10),
                   (18, 1), (18, 2), (19, 4), (22, 5), (21, 5), (5, 14), (5, 13), (4, 11), (1, 10), (2, 10)]:
        body.append(sq(x, y, "#f2c230"))
    for (x, y) in [(8, 1), (8, 2), (9, 2), (6, 6), (7, 6), (6, 7), (15, 1), (15, 2), (14, 2), (17, 6), (16, 6), (17, 7),
                   (15, 14), (15, 13), (14, 13), (17, 9), (16, 9), (17, 8), (8, 14), (8, 13), (9, 13), (6, 9), (7, 9), (6, 8)]:
        body.append(sq(x, y, "#77737f"))
    for (x, y) in [(11, 7), (12, 7), (11, 8), (12, 8)]:
        body.append(sq(x, y, "#8b877c"))
    # the enemy's ring (x >= 18, y >= 10) in red, its base, the player's base
    for x in range(17, 24):
        body.append(sq(x, 9, "#de4a4f"))
    for y in range(10, 16):
        body.append(sq(17, y, "#de4a4f"))
    body.append(rect(ox + 21 * cell, oy + 13 * cell, 2 * cell, 2 * cell, 3, "#de4a4f", ' stroke="#1d1b22"'))
    body.append(rect(ox + 1 * cell, oy + 1 * cell, 2 * cell, 2 * cell, 3, "#3d7be8", ' stroke="#1d1b22"'))
    # the three ways in: a portal pair, a switch, the hill
    for (x, y) in [(10, 1), (19, 15)]:
        body.append(f'<circle cx="{ox + x * cell + cell / 2:.1f}" cy="{oy + y * cell + cell / 2:.1f}" r="{cell * 0.36:.1f}" '
                    f'fill="none" stroke="#b77cff" stroke-width="2.5"/>')
    body.append(f'<circle cx="{ox + 21 * cell + cell / 2:.1f}" cy="{oy + 3 * cell + cell / 2:.1f}" r="{cell * 0.36:.1f}" '
                f'fill="none" stroke="#ffd166" stroke-width="2.5"/>')
    body.append(circle(ox + 21 * cell + cell / 2, oy + 3 * cell + cell / 2, cell * 0.12, "#ffd166"))
    lx = ox + cols * cell + 40
    items = [("#de4a4f", "Gates: only the enemy's units pass; its base cannot be hurt from outside"),
             ("#b77cff", "A portal: a unit sent onto it comes out at the other end, inside"),
             ("#ffd166", "A switch: stood on for ten seconds, it opens the ring it is wired to"),
             ("#8b877c", "The middle: held alone for a minute, it wins the battle outright")]
    for i, (colour, label) in enumerate(items):
        y = oy + 14 + i * 40
        body.append(rect(lx, y - 10, 14, 14, 3, colour))
        body.append(text(lx + 22, y + 1, label, 12, INK2))
    body.append(text(lx, oy + 14 + 4 * 40 + 2, "Battle 1 shows the middle's meter; battles 2 and 3 start you", 12, MUTED))
    body.append(text(lx, oy + 14 + 4 * 40 + 18, "inside a ring with a portal, then a switch, as the only way out.", 12, MUTED))
    body.append(text(lx, oy + 14 + 4 * 40 + 34, "After that nothing is explained. A bot that never learned", 12, MUTED))
    body.append(text(lx, oy + 14 + 4 * 40 + 50, "the mechanics wins 0 of 14 battles.", 12, MUTED))
    return svg(W, H, "".join(body), "The Skirmish battle: the enemy base behind a ring of gates with a portal, a switch "
                                    "and the middle as the ways in; a bot that never learned them wins none")


# --- Skirmish figures: the real-time battle, drawn from the same layout the site uses --------------------------------

SK_W, SK_H = 24, 16
SK_QUARTER = {"base": (1, 1), "gold": [(5, 1), (5, 2), (4, 4), (1, 5), (2, 5)],
              "walls": [(8, 1), (8, 2), (9, 2), (6, 6), (7, 6), (6, 7)], "mud": [(8, 4), (9, 4), (9, 5), (10, 5), (10, 6)]}
SK_MIDDLE = [(11, 7), (12, 7), (11, 8), (12, 8)]
SK_RINGS = {0: [(x, 9) for x in range(10)] + [(9, y) for y in range(9)],
            1: [(x, 6) for x in range(7)] + [(6, y) for y in range(6)],
            2: [(x, 5) for x in range(6)] + [(5, y) for y in range(5)]}
SK_SPOT = {"portalInInner": (4, 0), "portalInOuter": (8, 0), "portalOutside": (10, 1), "switchInsideOuter": (8, 7),
           "switchOutside": (2, 3), "exitPortalIn": (4, 0), "exitPortalOut": (7, 3), "exitSwitch": (0, 4)}
SK_SEATS = ["#3d7be8", "#d99a12", "#de4a4f", "#2f9a4c"]
SK_RUN = [("A", "learn", 0, 2, ["hill"], "hill"), ("B", "learn", 0, 2, ["hill"], "portal"),
          ("C", "learn", 0, 2, ["portal"], "switch"), ("D", "learn", 0, 2, ["switch"], None),
          ("E", "learn", 0, 2, ["portal"], None), ("F", "learn", 0, 2, ["hill"], None),
          ("G", "remix", 0, 2, ["switch", "portal"], None), ("H", "remix", 0, 2, ["portal", "switch"], None),
          ("I", "remix", 0, 2, ["switch", "portal"], None), ("B", "return", 1, 3, ["portal"], None),
          ("C", "return", 1, 3, ["switch"], None), ("D", "return", 1, 3, ["hill"], None),
          ("E", "return", 1, 3, ["switch"], None), ("F", "return", 1, 3, ["portal"], None)]
SK_WORLDS = {"A": {}, "B": {"mud": True}, "C": {"portals": True}, "D": {"archers": True}, "E": {"goal": "hill"},
             "F": {"goal": "gold"}, "G": {"mud": True, "archers": True}, "H": {"portals": True, "goal": "hill"},
             "I": {"archers": True, "goal": "gold"}}


def sk_mirror(x, y, seat):
    return (SK_W - 1 - x if seat in (1, 2) else x, SK_H - 1 - y if seat >= 2 else y)


def sk_map(battle):
    """The squares of one test battle: what kind sits where (engine.ts newGame, in miniature)."""
    world, _, you, enemy, need, teach = battle
    rules = SK_WORLDS[world]
    kinds = {}
    for seat in range(4):
        for c in SK_QUARTER["walls"]:
            kinds[sk_mirror(*c, seat)] = "wall"
        for c in SK_QUARTER["gold"]:
            kinds[sk_mirror(*c, seat)] = "gold"
        if rules.get("mud"):
            for c in SK_QUARTER["mud"]:
                kinds[sk_mirror(*c, seat)] = "mud"
    for c in SK_MIDDLE:
        kinds[c] = "hill" if "hill" in need else "gold"
    def ring(seat, r, kind):
        for c in SK_RINGS[r]:
            m = sk_mirror(*c, seat)
            if kinds.get(m) not in ("gold", "wall"):
                kinds[m] = kind
    at = lambda spot, seat: sk_mirror(*SK_SPOT[spot], seat)
    for k, way in enumerate(need):
        r = k if len(need) == 2 else 1
        inner, outer_too = r == 1, len(need) == 2
        ring(enemy, r, f"gate{enemy}")
        if way == "portal":
            out = at("portalInOuter", enemy) if inner and outer_too else at("portalOutside", you)
            inn = at("portalInInner" if inner else "portalInOuter", enemy)
            kinds[out] = kinds[inn] = "portal"
        elif way == "switch":
            c = at("switchInsideOuter", enemy) if inner and outer_too else at("switchOutside", (you + 1) % 4)
            kinds[c] = "switch"
    if teach in ("portal", "switch"):
        ring(you, 2, "gateX")
        if teach == "portal":
            kinds[at("exitPortalIn", you)] = kinds[at("exitPortalOut", you)] = "portal"
        else:
            kinds[at("exitSwitch", you)] = "switch"
    units = {}
    for seat in (you, enemy):
        bx, by = sk_mirror(*SK_QUARTER["base"], seat)
        bx2, by2 = sk_mirror(SK_QUARTER["base"][0] + 1, SK_QUARTER["base"][1] + 1, seat)
        units[(min(bx, bx2), min(by, by2))] = ("base", seat)
    return kinds, units


SK_FILL = {"wall": "#77737f", "gold": "#f2c230", "mud": "#56603a", "hill": "#8b877c", "gateX": "#8d80ad",
           "gate0": SK_SEATS[0], "gate1": SK_SEATS[1], "gate2": SK_SEATS[2], "gate3": SK_SEATS[3]}


def sk_minimap(battle, x, y, cell):
    kinds, units = sk_map(battle)
    body = [rect(x, y, SK_W * cell, SK_H * cell, cell * 0.7, "#3a352d")]
    for (cx, cy), kind in kinds.items():
        px, py = x + cx * cell, y + cy * cell
        if kind == "portal":
            body.append(f'<circle cx="{px + cell / 2:.1f}" cy="{py + cell / 2:.1f}" r="{cell * 0.36:.1f}" fill="none" '
                        f'stroke="#b77cff" stroke-width="{max(1.2, cell * 0.22):.1f}"/>')
        elif kind == "switch":
            body.append(f'<circle cx="{px + cell / 2:.1f}" cy="{py + cell / 2:.1f}" r="{cell * 0.36:.1f}" fill="none" '
                        f'stroke="#ffd166" stroke-width="{max(1.2, cell * 0.22):.1f}"/>')
        else:
            body.append(rect(px, py, cell, cell, min(2, cell * 0.2), SK_FILL[kind]))
    for (bx, by), (_, seat) in units.items():
        body.append(rect(x + bx * cell, y + by * cell, 2 * cell, 2 * cell, cell * 0.3, SK_SEATS[seat],
                         ' stroke="#1d1b22" stroke-width="0.8"'))
    return "".join(body)


def sk_pars():
    return json.loads((OUT / "skirmish-pars.json").read_text())


def sk_clock(ticks):
    sec = round(ticks / 10)
    return f"{sec // 60}:{sec % 60:02d}"


def fig_sk_run():
    """The 14 battles in order, with the way into each (never shown to the player)."""
    cell, slot, x0, W = 4, 112, 196, 900
    maph = SK_H * cell
    rows = [("1", "Learn", LEARN, "6 new worlds", "learn"), ("2", "Remix", REMIX, "two rules, two rings", "remix"),
            ("3", "Return", RETURN, "old worlds, other corner", "return")]
    way_name = {"hill": "hold the middle", "portal": "portal in", "switch": "switch"}
    shows = {"hill": "meter shown", "portal": "shows a portal", "switch": "shows a switch"}
    body = [text(32, 46, "One run", 22, INK, 700),
            text(32, 70, "14 battles in order against the same bot, by one player that is never reset. Under each: "
                         "the way in, which the battle itself never says.", 13, INK2)]
    y = 96
    for num, phase, colour, note, key in rows:
        battles = [b for b in SK_RUN if b[1] == key]
        body.append(rect(32, y, 6, maph + 30, 3, colour))
        body.append(text(50, y + 22, f"{num}  {phase}", 17, INK, 700))
        body.append(text(50, y + 42, note, 12, INK2))
        for i, b in enumerate(battles):
            bx = x0 + i * slot + (slot - 16 - SK_W * cell) / 2
            body.append(sk_minimap(b, bx, y, cell))
            label = b[0] if key != "return" else f"{b[0]} again"
            body.append(text(x0 + i * slot + (slot - 16) / 2, y + maph + 18, label, 13, INK, 600, "middle"))
            way = " + ".join(way_name[w] for w in b[4])
            body.append(text(x0 + i * slot + (slot - 16) / 2, y + maph + 32, way, 9, MUTED, 400, "middle"))
            if b[5]:
                body.append(text(x0 + i * slot + (slot - 16) / 2, y + maph + 44, shows[b[5]], 9, LEARN, 400, "middle"))
            if i < len(battles) - 1:
                ax = x0 + (i + 1) * slot - 12
                body.append(arrow(ax - 6, y + maph / 2, ax + 2, y + maph / 2))
        y += maph + 70
    body.append(text(32, y + 4, "Battle 1 shows the middle's meter. Battles 2 and 3 start you inside a ring, with a "
                                "portal and then a switch as the only way out.", 13, INK2))
    body.append(text(32, y + 24, "After that nothing is explained: the way in is always something you had to use before.",
                     13, INK2))
    return svg(W, y + 50, "".join(body), "One run: learn six worlds, play three remixes, return to five; the way into "
                                         "every battle is a mechanic an earlier battle made you use")


def fig_sk_same_screen():
    """The same battle as plain shapes for people and as numbers for AI."""
    kinds, units = sk_map(SK_RUN[3])
    cell, top, W = 14, 108, 900
    mapw = SK_W * cell
    body = [text(32, 46, "Same screen for people and AI", 22, INK, 700),
            text(32, 70, "Plain shapes, no names, no instructions. Nobody is told what a swirl, a ring or a plate does.",
                 13, INK2),
            text(32, top - 14, "What a person sees", 14, INK, 600), sk_minimap(SK_RUN[3], 32, top, cell)]
    ids = {None: 0, "wall": 1, "gold": 2, "mud": 3, "portal": 4, "hill": 6, "gate2": 8, "gate0": 7, "gateX": 8, "switch": 9}
    nx = 32 + mapw + 60
    body.append(text(nx, top - 14, "What an AI gets", 14, INK, 600))
    body.append(text(nx, top + 16, 'obs["terrain"]', 13, "#c9b8f0", 400, "start", MONO))
    for r in range(8, 16):
        row = " ".join(str(ids.get(kinds.get((c, r)), 0)) for c in range(13, 24))
        body.append(text(nx, top + 40 + (r - 8) * 19, "… " + row, 14, INK, 400, "start", MONO))
    body.append(text(nx, top + 40 + 8 * 19 + 10, "0 ground · 1 wall · 2 gold · 3 mud · 4 portal · 6 middle", 11, MUTED))
    body.append(text(nx, top + 40 + 8 * 19 + 26, "7 your gates · 8 gates you cannot pass · 9 a switch", 11, MUTED))
    return svg(W, top + SK_H * cell + 40, "".join(body), "The same battle shown as plain shapes for people and as a "
                                                           "grid of numbers for AI")


def fig_sk_scoring():
    pars = sk_pars()
    par = pars["battles"][0]["par"]
    W, x0, x1, top = 900, 220, 800, 128
    scale = (x1 - x0) / (2.4 * par)
    rows = [(f"Won in {sk_clock(par)}", par, True), (f"Won in {sk_clock(2 * par)}", 2 * par, True),
            (f"Never got in", 3600, False)]
    body = [text(32, 46, "How a battle is scored", 22, INK, 700),
            text(32, 70, "score = par ÷ your time. Par: the fastest win 216 scripted strategies found, by one that "
                         "knows the mechanics.", 13, INK2)]
    body.append(f'<path d="M{x0} {top - 10}v-6H{x0 + par * scale:.1f}v6" fill="none" stroke="{REMIX}" stroke-width="1.6"/>')
    body.append(text(x0 + par * scale / 2, top - 22, f"par = {sk_clock(par)}", 12, INK, 600, "middle"))
    for i, (label, t, won) in enumerate(rows):
        y = top + i * 44
        score = min(1, par / t) if won else 0
        body.append(text(32, y + 12, label, 14, INK))
        body.append(rect(x0, y, min(t * scale, x1 - x0), 15, 4, LEARN if won else "#5d5a6b", "" if won else ' opacity=".55"'))
        body.append(text(868, y + 13, f"{round(100 * score)}%", 18, INK, 700, "end"))
    body.append(text(32, top + 3 * 44 + 14, "Six minutes a battle; out of time is a draw and scores 0. A phase scores "
                                           "the mean of its battles; the run the mean of the phases.", 13, INK2))
    return svg(W, top + 3 * 44 + 48, "".join(body), "Scoring: par divided by your time; zero if you never get in")


def fig_sk_baselines():
    pars = sk_pars()
    series = [("the bot you fight, never having learned the mechanics", pars["scripted"], "#3987e5"),
              (f"random orders ({pars['random']['seeds']} runs)", pars["random"], "#d95926")]
    cats = [("Learn", "learn"), ("Remix", "remix"), ("Return", "return"), ("Overall", "overall")]
    W, x0, x1, top, bar, group = 900, 130, 800, 128, 14, 52
    bottom = top + len(cats) * group
    body = [text(32, 46, "Scores so far", 22, INK, 700),
            text(32, 70, "Higher is better. A player that knows the mechanics and plays at par scores 100% everywhere.",
                 13, INK2)]
    lx = 32
    for name, _, colour in series:
        body.append(rect(lx, 88, 12, 12, 3, colour))
        body.append(text(lx + 18, 99, name, 13, INK))
        lx += 34 + len(name) * 7.2
    for t in (0, 25, 50, 75, 100):
        gx = x0 + (x1 - x0) * t / 100
        body.append(f'<line x1="{gx:.1f}" y1="{top - 8}" x2="{gx:.1f}" y2="{bottom - 10}" stroke="{LINE}"/>')
        body.append(text(gx, bottom + 6, f"{t}%", 12, MUTED, 400, "middle"))
    for i, (label, key) in enumerate(cats):
        y = top + i * group
        body.append(text(x0 - 14, y + bar + 6, label, 14, INK, 600 if key == "overall" else 400, "end"))
        for j, (_, data, colour) in enumerate(series):
            v = 100 * data[key]
            by = y + j * (bar + 2)
            bw = (x1 - x0) * v / 100
            if bw > 0.5:
                body.append(rect(x0, by, bw, bar, 3, colour))
            body.append(text(x0 + bw + 6, by + bar - 3, f"{v:.1f}%", 12, INK2))
    body.append(text(32, bottom + 34, f"Neither wins a single battle of {pars['scripted']['total']}: without the "
                                      "mechanics there is no way in. A learner that carries them forward should.",
                     13, INK2))
    return svg(W, bottom + 58, "".join(body), "Bar chart of scores by phase: the bot that never learned the mechanics "
                                              "and random orders both score zero")


def fig_same_screen():
    rows = load_spec("practice-v0").visits[1].levels[0].map  # world B, level 1
    grid = first_grid(rows)
    cell = 38
    body = [text(32, 46, "Same screen for people and AI", 22, INK, 700),
            text(32, 70, "16 colours, no words, no instructions. Nobody is told what the colours do.", 13, INK2)]
    top = 108
    b, w, h = board_svg(grid, 32, top, cell)
    body.append(text(32, top - 14, "What a person sees", 14, INK, 600))
    body.append(b)
    nx = 32 + w + 90
    for dy in (-6, 6):  # an equals sign between the two
        body.append(rect(32 + w + 30, top + h / 2 + dy - 2.5, 30, 5, 2.5, INK2))
    body.append(text(nx, top - 14, "What an AI gets:", 14, INK, 600))
    body.append(text(nx + 118, top - 14, "obs.grid", 14, "#c9b8f0", 600, family=MONO))
    pad = cell * 0.35
    body.append(rect(nx, top, w, h, max(4, cell * 0.3), BOARD))
    for yy, row in enumerate(grid):
        for xx, c in enumerate(row):
            x, y = nx + pad + xx * cell, top + pad + yy * cell
            body.append(rect(x + 1.5, y + 1.5, cell - 3, cell - 3, 4, FLOOR))
            body.append(text(x + cell / 2, y + cell / 2 + 5, str(c), 14, INK if c != Cell.WALL else MUTED,
                             600 if c not in (Cell.FLOOR, Cell.WALL) else 400, "middle", MONO))
    H = top + h + 40
    W = nx + w + 32
    return svg(W, H, "".join(body), "The same grid of colours, shown as a picture and as numbers")


def fig_scoring():
    W = 900
    body = [text(32, 46, "How a level is scored", 22, INK, 700),
            text(32, 70, "score = par ÷ actions. Par is the fewest actions possible (found by searching every move).",
                 13, INK2)]
    sq, gap, x0 = 15, 3, 210
    rows = [("Done in 10 actions", 10, False, "100%", "#4c8ff7"), ("Done in 20 actions", 20, False, "50%", "#4c8ff7"),
            ("Ran out of actions", 22, True, "0%", "#5d5a6b")]
    y = 128
    # par bracket over the first 10 squares
    bx2 = x0 + 10 * (sq + gap) - gap
    body.append(f'<path d="M{x0} {y - 10} v-6 H{bx2} v6" fill="none" stroke="{REMIX}" stroke-width="1.6"/>')
    body.append(text((x0 + bx2) / 2, y - 22, "par = 10", 12, INK, 600, "middle"))
    for label, n, out, score, colour in rows:
        body.append(text(32, y + 12, label, 14, INK))
        for i in range(n):
            op = 1.0 if not out else max(0.15, 1 - i / n)
            body.append(rect(x0 + i * (sq + gap), y, sq, sq, 3, colour, f' opacity="{op:.2f}"'))
        if out:
            body.append(text(x0 + n * (sq + gap) + 6, y + 12, "… until the budget runs out", 12, INK2))
        body.append(text(W - 40, y + 13, score, 18, INK, 700, "end"))
        y += 44
    body.append(text(32, y + 14, "Every key press counts, restarts too. A phase scores the mean of its levels; the "
                                "lifetime score is the mean of the phases.", 13, INK2))
    return svg(W, y + 40, "".join(body), "Scoring: par divided by actions; zero if the budget runs out")


def fig_baselines():
    data = json.loads((OUT.parents[1] / "src" / "longgame" / "baselines.json").read_text())["practice-v0"]
    series = [("random keys", "random", "#3987e5"), ("explorer (forgets each level)", "explorer", "#d95926")]
    cats = [("Learn", "learn"), ("Remix", "remix"), ("Return", "return"), ("Overall", "overall")]
    W, x0, x1, top = 900, 130, 800, 128
    scale = 15.0  # percent at x1
    body = [text(32, 46, "Baseline scores on practice-v0", 22, INK, 700),
            text(32, 70, "Higher is better. The solver, which reads the rules from the code, scores 100% everywhere.",
                 13, INK2)]
    lx = 32
    for name, _, colour in series:  # legend
        body.append(rect(lx, 88, 12, 12, 3, colour))
        body.append(text(lx + 18, 99, name, 13, INK))
        lx += 26 + len(name) * 7.4
    bar, pair_gap, group = 14, 2, 52
    gy = top + len(cats) * group
    for t in (0, 5, 10, 15):  # gridlines
        gx = x0 + (x1 - x0) * t / scale
        body.append(f'<line x1="{gx:.1f}" y1="{top - 8}" x2="{gx:.1f}" y2="{gy - 10}" stroke="{LINE}" stroke-width="1"/>')
        body.append(text(gx, gy + 6, f"{t}%", 12, MUTED, 400, "middle"))
    for i, (label, key) in enumerate(cats):
        y = top + i * group
        body.append(text(x0 - 14, y + bar + 6, label, 14, INK, 600 if key == "overall" else 400, "end"))
        for j, (_, name, colour) in enumerate(series):
            v = 100 * data[name][key]
            by = y + j * (bar + pair_gap)
            bw = (x1 - x0) * v / scale
            if bw > 0.5:
                # square at the baseline, 4px rounded at the data end
                body.append(f'<path d="M{x0} {by} H{x0 + max(bw - 4, 0):.1f} q4 0 4 4 v{bar - 8} q0 4 -4 4 H{x0} Z" '
                            f'fill="{colour}"/>')
            shown = f"{v:.2f}%" if v < 1 else f"{v:.1f}%"
            body.append(text(x0 + bw + 6, by + bar - 3, shown, 12, INK2))
    body.append(text(32, gy + 34, "The explorer gains nothing from remixes or return visits: it remembers nothing between "
                                  "levels. A continual learner should.", 13, INK2))
    return svg(W, gy + 58, "".join(body), "Bar chart of baseline scores by phase for random keys and the explorer")


def fig_idea():
    W = 900
    body = [text(32, 46, "The question", 22, INK, 700)]

    def mini(x, y, cells, size=7, n=4):
        out = [rect(x, y, n * size + 4, n * size + 4, 3, BOARD)]
        for (cx, cy), colour in cells.items():
            out.append(rect(x + 2 + cx * size + 0.5, y + 2 + cy * size + 0.5, size - 1, size - 1, 1, colour))
        for cy in range(n):
            for cx in range(n):
                if (cx, cy) not in cells:
                    out.append(rect(x + 2 + cx * size + 0.5, y + 2 + cy * size + 0.5, size - 1, size - 1, 1, FLOOR))
        return "".join(out)

    # Row 1: tasks scored one at a time
    y1 = 92
    body.append(text(32, y1 + 18, "ARC-AGI", 17, INK, 700))
    body.append(text(32, y1 + 38, "Can it learn this?", 13, INK2))
    shapes = [({(0, 0): "#3987e5", (0, 1): "#3987e5", (1, 1): "#3987e5"},
               {(3, 0): "#3987e5", (3, 1): "#3987e5", (2, 1): "#3987e5"}),
              ({(1, 1): "#d95926", (2, 2): "#d95926"}, {(1, 1): "#d95926", (2, 2): "#d95926", (1, 2): "#eda100",
                                                         (2, 1): "#eda100"}),
              ({(0, 3): "#1baf7a", (1, 3): "#1baf7a"}, {(0, 3): "#1baf7a", (1, 3): "#1baf7a", (2, 3): "#1baf7a",
                                                         (3, 3): "#1baf7a"})]
    x = 230
    for a, b in shapes:
        body.append(rect(x - 10, y1 - 4, 178, 56, 10, "none", f' stroke="{LINE}" stroke-width="1.4"'))
        body.append(mini(x, y1 + 6, a))
        body.append(arrow(x + 40, y1 + 22, x + 62, y1 + 22))
        body.append(mini(x + 70, y1 + 6, b))
        body.append(text(x + 126, y1 + 30, "scored", 12, INK2))
        x += 200
    body.append(text(230, y1 + 76, "Each task or game is scored on its own, then the slate is wiped.", 13, INK2))

    # Row 2: one lifetime, things come back
    y2 = 246
    body.append(text(32, y2 + 18, "Long Game", 17, INK, 700))
    body.append(text(32, y2 + 38, "Does it keep it?", 13, INK2))
    spec = load_spec("practice-v0")
    picks = [(spec.visits[1].levels[0].map, "B"), (spec.visits[3].levels[0].map, "D"),
             (spec.visits[6].levels[0].map, "G = B + D"), (spec.visits[9].levels[0].map, "B again")]
    x, cell, xs = 230, 6, []
    for i, (rows, label) in enumerate(picks):
        b, w, h = board_svg(first_grid(rows), x, y2, cell, hud=False)
        body.append(b)
        body.append(text(x + w / 2, y2 + h + 18, label, 12, INK, 600, "middle"))
        xs.append((x, w, h))
        if i < len(picks) - 1:
            body.append(arrow(x + w + 10, y2 + h / 2, x + w + 44, y2 + h / 2))
        x += w + 56
    # curved "comes back" arrow from the last board to the first
    (fx, fw, fh), (lx, lw, lh) = xs[0], xs[-1]
    sx, ex, ty = lx + lw / 2, fx + fw / 2, y2 - 10
    body.append(f'<path d="M{sx:.1f} {ty:.1f} C{sx:.1f} {ty - 40:.1f} {ex:.1f} {ty - 40:.1f} {ex:.1f} {ty - 4:.1f}" '
                f'fill="none" stroke="{RETURN}" stroke-width="2" stroke-dasharray="5 4"/>')
    body.append(f'<polygon points="{ex:.1f},{ty:.1f} {ex - 5:.1f},{ty - 9:.1f} {ex + 5:.1f},{ty - 9:.1f}" fill="{RETURN}"/>')
    body.append(text((sx + ex) / 2, ty - 38, "it comes back", 12, INK, 600, "middle"))
    body.append(text(230, y2 + 92, "One agent, one lifetime, never reset: scored on what carries over.", 13, INK2))
    return svg(W, y2 + 118, "".join(body), "ARC-AGI scores each task alone; Long Game scores what carries over")


ICON = {"crates": Cell.CRATE, "keys": Cell.KEY, "ice": Cell.ICE, "gates": Cell.GATE_CLOSED, "twin": Cell.TWIN,
        "coins": Cell.COIN}
THUMBS = [(("crates", "ice"), 2, 4), (("keys", "gates"), 2, 1), (("keys", "ice"), 2, 5), (("twin", "coins"), 2, 2)]


def fig_worlds():
    """Which rule combinations are for training and which are held out, with levels the world maker made."""
    W = 900
    body = [text(32, 46, "The world maker", 22, INK, 700),
            text(32, 70, "Endless new levels, each built from a seed and checked by the solver. Some rules never "
                         "appear in training.", 13, INK2)]
    names = list(worlds.MECHANICS)
    S, g = 38, 5
    mx, my = 150, 158
    for i, m in enumerate(names):  # column headers: icon over name
        cx = mx + i * (S + g) + S / 2
        body.append(rect(cx - 13, my - 58, 26, 26, 6, BOARD))
        body.append(cell_svg(ICON[m], cx - 10, my - 55, 20))
        body.append(text(cx, my - 14, m, 11, INK2, 400, "middle"))
    for j, m in enumerate(names):  # row headers: icon then name
        cy = my + j * (S + g) + S / 2
        body.append(rect(32, cy - 13, 26, 26, 6, BOARD))
        body.append(cell_svg(ICON[m], 35, cy - 10, 20))
        body.append(text(66, cy + 4, m, 12, INK2))
        for i, n in enumerate(names):
            if i < j:
                continue
            held = worlds.split_of([m, n]) == "heldout"
            x, y = mx + i * (S + g), my + j * (S + g)
            body.append(rect(x, y, S, S, 6, HELD if held else TRAIN))
            if i == j:  # one rule on its own: a dot marks the diagonal
                body.append(circle(x + S / 2, y + S / 2, 4, "#ffffff"))
    ly = my + 6 * (S + g) + 18
    n_train, n_held = len(worlds.recipes("train")), len(worlds.recipes("heldout"))
    body.append(rect(32, ly, 14, 14, 3, TRAIN))
    body.append(text(54, ly + 12, f"training ({n_train} kinds of world, mazes included)", 13, INK))
    body.append(rect(32, ly + 24, 14, 14, 3, HELD))
    body.append(text(54, ly + 36, f"held out for testing ({n_held} kinds)", 13, INK))
    body.append(circle(39, ly + 55, 4, "#ffffff"))
    body.append(text(54, ly + 60, "one rule on its own; other squares mix two", 13, INK2))

    # example levels, two training and two held out
    tx, ty, slot_w, slot_h, cell = 470, 96, 210, 190, 14
    for k, (recipe, tier, seed) in enumerate(THUMBS):
        lv = worlds.level(recipe, tier, seed)
        held = worlds.split_of(recipe) == "heldout"
        x, y = tx + (k % 2) * slot_w, ty + (k // 2) * slot_h
        body.append(rect(x, y + 4, 12, 12, 3, HELD if held else TRAIN))
        body.append(text(x + 20, y + 15, " + ".join(recipe), 13, INK, 600))
        b, w, h = board_svg(first_grid(lv.map), x, y + 26, cell, hud=False)
        body.append(b)
        body.append(text(x, y + 26 + h + 16, f"seed {seed} · par {lv.par}", 11, MUTED))
    fy = max(ly + 92, ty + 2 * slot_h + 10)
    held_pairs = [" with ".join(p) for p in worlds.HELD_OUT_PAIRS if "coins" not in p]
    body.append(text(32, fy, f"Training never shows coins, or {', '.join(held_pairs[:-1])} or {held_pairs[-1]}. "
                             "Held-out lifetimes always do.", 13, INK2))
    return svg(W, fy + 26, "".join(body), "The world maker: a chart of which rule combinations are for training "
                                          "and which are held out for testing, next to four generated levels")


# --- animation ---------------------------------------------------------------------------------------------------

DEMO = ["###########", "#@k$.___o.#", "#.#####.###", "#.......DE#", "###########"]  # not in any lifetime


def _hex(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def pil_cell(d, c, x, y, s, hud=False):
    """One cell on a Pillow canvas, drawn like the browser player (and like cell_svg)."""
    r, b = s * 0.12, max(2, int(s * 0.09))
    base = {Cell.WALL: "#2c2a36" if hud else "#5d5a6b", Cell.EXIT: "#1f9d55", Cell.DOOR: "#8a6a12",
            Cell.ICE: "#a8e4f0", Cell.GATE_CLOSED: "#7a4ad8"}.get(c, FLOOR)
    d.rounded_rectangle([x, y, x + s, y + s], r, fill=_hex(base))
    cx, cy = x + s / 2, y + s / 2
    if c in (Cell.PLAYER, Cell.TWIN):
        colour = "#4c8ff7" if c == Cell.PLAYER else "#e5484d"
        d.ellipse([cx - s * .38, cy - s * .38, cx + s * .38, cy + s * .38], fill=_hex(colour))
    elif c == Cell.EXIT_CLOSED:
        d.rounded_rectangle([x, y, x + s, y + s], r, outline=_hex("#1f6b3f"), width=b)
    elif c in (Cell.CRATE, Cell.CRATE_ON_PAD):
        if c == Cell.CRATE_ON_PAD:
            d.rounded_rectangle([x, y, x + s, y + s], r, outline=_hex("#d29a35"), width=b)
        i = s * 0.1
        fill, edge = ("#f0b443", "#b07a1d") if c == Cell.CRATE_ON_PAD else ("#b8682a", "#8a4b1c")
        d.rounded_rectangle([x + i, y + i, x + s - i, y + s - i], r * .7, fill=_hex(fill), outline=_hex(edge),
                            width=b)
    elif c == Cell.PAD:
        d.rounded_rectangle([x, y, x + s, y + s], r, outline=_hex("#d29a35"), width=b)
    elif c == Cell.KEY:
        k = s * 0.23
        d.polygon([(cx, cy - k), (cx + k, cy), (cx, cy + k), (cx - k, cy)], fill=_hex("#f5d02f"))
    elif c == Cell.DOOR:
        d.rounded_rectangle([x + s * .42, y + s * .36, x + s * .58, y + s * .64], s * .06, fill=_hex("#3a2d06"))
    elif c == Cell.SWITCH:
        d.ellipse([cx - s * .28, cy - s * .28, cx + s * .28, cy + s * .28], outline=_hex("#e2559c"), width=b)
    elif c == Cell.GATE_OPEN:
        d.rounded_rectangle([x, y, x + s, y + s], r, outline=_hex("#4f3a7c"), width=max(1, int(b * 0.7)))
    elif c == Cell.COIN:
        d.ellipse([cx - s * .16, cy - s * .16, cx + s * .16, cy + s * .16], fill=_hex("#f3f3f3"))


def pil_board(d, grid, ox, oy, cell, gap, scale):
    for yy, row in enumerate(grid):
        hud = yy == len(grid) - 1
        for xx, c in enumerate(row):
            pil_cell(d, c, (ox + xx * cell + gap / 2) * scale, (oy + yy * cell + gap / 2) * scale,
                     (cell - gap) * scale, hud)


def solution_states(rows):
    level = engine.parse_level(rows)
    states = [level.start]
    for m in engine.solve(level):
        states.append(engine.step(level, states[-1], m)[0])
    return level, states


def fig_gif(path: Path) -> None:
    from PIL import Image, ImageDraw

    level, states = solution_states(DEMO)
    cell, pad, gap, scale = 40, 14, 3, 2
    grid0 = engine.render(level, level.start)
    W, H = len(grid0[0]) * cell + 2 * pad, len(grid0) * cell + 2 * pad

    def frame(state):
        img = Image.new("RGB", (W * scale, H * scale), _hex(BOARD))
        pil_board(ImageDraw.Draw(img), engine.render(level, state), pad, pad, cell, gap, scale)
        return img.resize((W, H), Image.LANCZOS)

    frames = [frame(s) for s in states]
    durations = [900] + [380] * (len(frames) - 2) + [1600]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)


# Levels for the world maker animation: (rules, tier, seed). Training rules first, then held-out ones.
GIF_LEVELS = [(("crates", "ice"), 2, 4), (("keys", "gates"), 2, 1), (("twin",), 3, 2), (("keys", "ice"), 2, 5),
              (("coins",), 2, 3)]


def fig_worlds_gif(path: Path) -> None:
    """The solver finishing a few levels straight from the world maker, labelled training or held out."""
    from PIL import Image, ImageDraw, ImageFont

    def font(size, bold=False):
        for name in (("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"), "Arial.ttf"):
            for folder in ("/usr/share/fonts/truetype/dejavu/", ""):
                try:
                    return ImageFont.truetype(folder + name, size)
                except OSError:
                    pass
        return ImageFont.load_default()

    cell, gap, scale, side, top = 34, 3, 2, 12, 64
    W, H = side * cell + 40, side * cell + top + 24
    title, small = font(19 * scale, True), font(13 * scale)
    frames, durations = [], []
    for recipe, tier, seed in GIF_LEVELS:
        spec = worlds.level(recipe, tier, seed)
        level, states = solution_states(spec.map)
        held = worlds.split_of(recipe) == "heldout"
        grid0 = engine.render(level, level.start)
        ox, oy = (W - len(grid0[0]) * cell) / 2, top + (side * cell - len(grid0) * cell) / 2
        for k, state in enumerate(states):
            img = Image.new("RGB", (W * scale, H * scale), _hex(PANEL))
            d = ImageDraw.Draw(img)
            name = " + ".join(recipe)
            d.text((20 * scale, 16 * scale), name, font=title, fill=_hex(INK))
            badge = "held out for testing" if held else "training"
            bw = d.textlength(badge, font=small) + 20 * scale
            bx = W * scale - 20 * scale - bw
            d.rounded_rectangle([bx, 15 * scale, bx + bw, 39 * scale], 12 * scale, fill=_hex(HELD if held else TRAIN))
            d.text((bx + 10 * scale, 19 * scale), badge, font=small, fill=_hex("#ffffff"))
            d.text((20 * scale, 42 * scale), f"made from seed {seed} · par {spec.par}", font=small, fill=_hex(MUTED))
            pil_board(d, engine.render(level, state), ox, oy, cell, gap, scale)
            frames.append(img.resize((W, H), Image.LANCZOS))
            durations.append(1100 if k == 0 else 1300 if k == len(states) - 1 else 230)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)


def main():
    figures = {"lifetime.svg": fig_lifetime(), "same-screen.svg": fig_same_screen(), "scoring.svg": fig_scoring(),
               "baselines.svg": fig_baselines(), "idea.svg": fig_idea(), "worlds.svg": fig_worlds(),
               "gate.svg": fig_gate(), "skirmish.svg": fig_skirmish(), "skirmish-run.svg": fig_sk_run(),
               "skirmish-same-screen.svg": fig_sk_same_screen(), "skirmish-scoring.svg": fig_sk_scoring(),
               "skirmish-baselines.svg": fig_sk_baselines()}
    for name, body in figures.items():
        (OUT / name).write_text(body)
    fig_gif(OUT / "play.gif")
    fig_worlds_gif(OUT / "worlds.gif")
    print("wrote", ", ".join([*figures, "play.gif", "worlds.gif"]))


if __name__ == "__main__":
    main()
