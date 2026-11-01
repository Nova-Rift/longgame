"""Text rendering for terminals: coloured blocks (24-bit ANSI) or plain map characters."""

from __future__ import annotations

from typing import List, Sequence

# One colour per cell id, matching the browser player.
PALETTE = {
    0: "#1d1b25", 1: "#5d5a6b", 2: "#4c8ff7", 3: "#1f9d55", 4: "#1f6b3f", 5: "#b8682a", 6: "#d29a35", 7: "#f0b443",
    8: "#f5d02f", 9: "#8a6a12", 10: "#a8e4f0", 11: "#e2559c", 12: "#7a4ad8", 13: "#4f3a7c", 14: "#e5484d",
    15: "#f3f3f3",
}
# (glyph, glyph colour or None, background) per id: background colours tiles, glyphs draw things standing on them.
_STYLE = {
    0: ("  ", None, 0), 1: ("  ", None, 1), 2: ("()", 2, 0), 3: ("  ", None, 3), 4: ("[]", 4, 0), 5: ("[]", 5, 0),
    6: ("<>", 6, 0), 7: ("[]", 7, 6), 8: ("<>", 8, 0), 9: ("||", 0, 9), 10: ("  ", None, 10), 11: ("()", 11, 0),
    12: ("  ", None, 12), 13: (": ", 13, 0), 14: ("()", 14, 0), 15: (" o", 15, 0),
}
# Plain characters, the same as the map format (e = closed exit, g/G = open/closed gate, * = crate on a pad).
ASCII = {0: ".", 1: "#", 2: "@", 3: "E", 4: "e", 5: "$", 6: "o", 7: "*", 8: "k", 9: "D", 10: "_", 11: "S", 12: "G",
         13: "g", 14: "T", 15: "c"}
_HUD_BG = "#2c2a36"


def _rgb(hex_colour: str) -> str:
    h = hex_colour.lstrip("#")
    return ";".join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))


def grid_lines(grid: Sequence[Sequence[int]], color: bool = True) -> List[str]:
    lines = []
    for y, row in enumerate(grid):
        hud = y == len(grid) - 1
        if not color:
            lines.append("".join(ASCII.get(c, "?") for c in row))
            continue
        out = []
        for c in row:
            glyph, fg, bg = _STYLE.get(c, ("??", None, 0))
            bg_hex = _HUD_BG if hud and c == 1 else PALETTE[bg]
            fg_code = f"\x1b[38;2;{_rgb(PALETTE[fg])}m" if fg is not None else ""
            out.append(f"\x1b[48;2;{_rgb(bg_hex)}m{fg_code}{glyph}")
        lines.append("".join(out) + "\x1b[0m")
    return lines


def render_text(obs, color: bool = True) -> str:
    """A frame with a one-line header: world, phase, level and actions used."""
    if obs.done:
        return "Lifetime complete."
    head = (f"world {obs.world} · {obs.phase} · level {obs.level + 1}/{obs.levels} · "
            f"{obs.actions}/{obs.budget} actions · {obs.played}/{obs.total} levels played")
    if obs.result is not None:
        r = obs.result
        head = (f"[{r.world} level {r.level + 1}: {'finished' if r.cleared else 'out of actions'} in {r.actions}, "
                f"par {r.par}, score {100 * r.score:.0f}%]\n") + head
    return "\n".join([head, *grid_lines(obs.grid, color)])
