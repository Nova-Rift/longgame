"""Play in a terminal (``longgame play --terminal``). Same saved progress as the browser player.

Keys: arrows or WASD move, space / E / Enter interact (the USE action; it works only in some spots), R restarts the
level, Q quits (progress is kept). Where single key presses cannot be read (Windows consoles, pipes), type keys and
press Enter instead.
"""

from __future__ import annotations

import sys
from typing import Callable, Iterator, Optional

from .actions import Action
from .lifetime import load_spec
from .render import render_text
from .webplay import Session

KEYMAP = {"w": Action.UP, "a": Action.LEFT, "s": Action.DOWN, "d": Action.RIGHT, " ": Action.USE, "e": Action.USE,
          "\r": Action.USE, "\n": Action.USE, "r": Action.RESET, "\x1b[A": Action.UP, "\x1b[B": Action.DOWN,
          "\x1b[C": Action.RIGHT, "\x1b[D": Action.LEFT}
QUIT = {"q", "\x03", "\x04"}


def _raw_keys() -> Optional[Iterator[str]]:
    """Single key presses from a POSIX terminal, or None if unavailable."""
    if not sys.stdin.isatty():
        return None
    try:
        import termios
        import tty
    except ImportError:
        return None

    def gen() -> Iterator[str]:
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            while True:
                ch = sys.stdin.read(1)
                if ch == "\x1b":
                    ch += sys.stdin.read(2)
                yield ch.lower() if len(ch) == 1 else ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    return gen()


def _line_keys(prompt: Callable[[str], str] = input) -> Iterator[str]:
    while True:
        try:
            line = prompt("keys (wasd move, e interact, r restart, q quit) > ")
        except EOFError:
            yield "q"
            return
        for ch in line.lower() or "\n":
            yield ch


def play_in_terminal(lifetime: str = "practice-v0", fresh: bool = False, color: bool = True,
                     keys: Optional[Iterator[str]] = None, out=sys.stdout) -> int:
    session = Session(load_spec(lifetime), fresh=fresh)
    raw_keys = _raw_keys() if keys is None else None
    raw = raw_keys is not None
    source = keys if keys is not None else raw_keys or _line_keys()
    try:
        return _loop(session, source, raw, color, out)
    finally:
        if raw_keys is not None:
            raw_keys.close()  # puts the terminal back to normal


def _loop(session: Session, keys: Iterator[str], raw: bool, color: bool, out) -> int:
    nl = "\r\n" if raw else "\n"
    note = "No instructions: work out each world by playing."
    while True:
        obs = session.env.observe()
        card = session.env.scorecard()
        screen = render_text(obs, color=color).split("\n")
        score = "  ".join(f"{p} {100 * s:.0f}%" for p, s in card.phases.items())
        if raw:
            out.write("\x1b[2J\x1b[H")
        out.write(nl.join(screen + ["", note, f"score so far: {score}  ({card.played}/{card.total} levels)", ""]))
        out.flush()
        if obs.done:
            out.write(f"Total {100 * card.overall:.1f}%. Recording: {session.recording}{nl}")
            return 0
        key = next(keys, "q")
        if key in QUIT:
            out.write(f"Progress saved in {session.progress}{nl}")
            return 0
        if key not in KEYMAP:
            continue
        state = session.step(KEYMAP[key])
        r = state["last"]
        if r:
            note = (f"World {r['world']} level {r['level'] + 1}: done in {r['actions']} (fewest {r['par']}), "
                    f"{100 * r['score']:.0f}%" if r["cleared"] else
                    f"World {r['world']} level {r['level'] + 1}: out of actions, 0%")
        else:
            note = "Every key press counts as an action."
