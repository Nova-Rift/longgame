"""Recordings: every action of a lifetime as JSON lines, so anyone can replay it and confirm the score.

The rules are deterministic, so a recording *is* the result: ``longgame verify run.jsonl`` replays the actions and
recomputes every level. Format, one JSON object per line::

    {"type": "start", "longgame": "0.1.0", "lifetime": "practice-v0", "digest": "<sha256>", "agent": "...", ...}
    {"type": "level", "visit": 0, "level": 0, "world": "A", "phase": "learn", "par": 10,
     "actions": [4, 4, ...], "cleared": true, "score": 1.0}
    ...
    {"type": "end", "phases": {...}, "overall": 0.42, "played": 28, "total": 28}

A level line is written when the level ends, so a recording of an unfinished lifetime holds its finished levels.
The levels are never taken from the recording itself: they come from the toolkit's own copy of the named lifetime
(a shipped one, or a generated one rebuilt from its id), or from a lifetime file given explicitly to ``verify``.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, Dict, List, Optional, Union

from .lifetime import LevelResult, Lifetime, LifetimeSpec, Scorecard, lifetimes, load_spec
from .worlds import is_generated


class Recorder:
    """Writes a recording as the lifetime is played. Each ``reset()`` starts the file over."""

    def __init__(self, path: Union[str, Path], agent: str = ""):
        self.path = Path(path)
        self.agent = agent
        self._file: Optional[IO[str]] = None

    def _write(self, obj: Dict[str, Any]) -> None:
        assert self._file is not None
        self._file.write(json.dumps(obj, separators=(",", ":")) + "\n")
        self._file.flush()

    def start(self, spec: LifetimeSpec) -> None:
        from . import __version__
        self.close()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.path, "w", encoding="utf-8")
        self._write({"type": "start", "longgame": __version__, "lifetime": spec.id, "digest": spec.digest,
                     "agent": self.agent, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

    def level(self, result: LevelResult, actions: List[int]) -> None:
        d = result.to_dict()
        self._write({"type": "level", **{k: d[k] for k in ("visit", "level", "world", "phase", "par")},
                     "actions": list(actions), "cleared": result.cleared, "score": result.score})

    def finish(self, card: Scorecard) -> None:
        self._write({"type": "end", "phases": card.phases, "overall": card.overall, "played": card.played,
                     "total": card.total})

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None


@dataclass
class Verification:
    ok: bool
    scorecard: Optional[Scorecard]
    problems: List[str] = field(default_factory=list)
    agent: str = ""

    def __str__(self) -> str:
        head = "VERIFIED" if self.ok else "NOT VERIFIED"
        lines = [f"{head}: {self.scorecard.summary()}" if self.scorecard else head]
        if self.agent:
            lines.append(f"agent: {self.agent}")
        lines += [f"  - {p}" for p in self.problems]
        return "\n".join(lines)


def read(path: Union[str, Path]) -> List[Any]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _same(recorded: Any, actual: float) -> bool:
    return (isinstance(recorded, (int, float)) and not isinstance(recorded, bool) and math.isfinite(recorded)
            and math.isclose(recorded, actual, rel_tol=0, abs_tol=1e-9))


def verify(path: Union[str, Path], lifetime: Union[None, str, Path, LifetimeSpec] = None) -> Verification:
    """Replay a recording and check every recorded level and the final score against the rules.

    The levels come from the toolkit's own copy of the lifetime the recording names (a shipped id, or a generated
    id rebuilt by the world maker), or from ``lifetime`` when given; never from the recording. Malformed recordings
    are reported, not raised.
    """
    try:
        rows = read(path)
    except (OSError, ValueError) as e:
        return Verification(False, None, [f"Could not read {path}: {e}"])
    if not rows or not isinstance(rows[0], dict) or rows[0].get("type") != "start":
        return Verification(False, None, ["The first line must be the start record"])
    head = rows[0]
    agent = head.get("agent") if isinstance(head.get("agent"), str) else ""
    if lifetime is None:
        name = head.get("lifetime")
        if not isinstance(name, str) or not (name in lifetimes() or is_generated(name)):
            return Verification(False, None, [f"The recording names lifetime {name!r}, which does not ship with this "
                                              f"toolkit. If it came from a file, pass it with --lifetime."], agent)
        lifetime = name
    try:
        spec = load_spec(lifetime)
    except ValueError as e:
        return Verification(False, None, [str(e)], agent)
    if head.get("digest") != spec.digest:
        return Verification(False, None, [f"Recorded levels (digest {str(head.get('digest'))[:12]}) differ from "
                                          f"{spec.id} (digest {spec.digest[:12]})"], agent)
    problems: List[str] = []
    env = Lifetime(spec)
    env.reset()
    end = None
    for n, row in enumerate(rows[1:], start=2):
        if not isinstance(row, dict):
            problems.append(f"Line {n}: not a JSON object")
            break
        kind = row.get("type")
        if kind == "end":
            end = row
            if n != len(rows):
                problems.append("Lines after the end record")
            break
        if kind != "level":
            problems.append(f"Line {n}: unknown record type {kind!r}")
            break
        actions = row.get("actions")
        if not isinstance(actions, list) or not actions:
            problems.append(f"Line {n}: actions must be a non-empty list")
            break
        got = None
        try:
            for i, a in enumerate(actions):
                if env.done:
                    raise ValueError("actions after the lifetime ended")
                obs = env.step(a)
                if obs.result is not None:
                    if i != len(actions) - 1:
                        raise ValueError(f"the level ended after {i + 1} actions but the line has {len(actions)}")
                    got = obs.result
        except (ValueError, TypeError) as e:
            problems.append(f"Line {n}: {e}")
            break
        if got is None:
            problems.append(f"Line {n}: these actions do not end the level")
            break
        for key in ("visit", "level", "world", "phase", "par", "cleared"):
            if row.get(key) != getattr(got, key):
                problems.append(f"Line {n}: recorded {key} {row.get(key)!r}, replay gives {getattr(got, key)!r}")
        if not _same(row.get("score"), got.score):
            problems.append(f"Line {n}: recorded score {row.get('score')!r}, replay gives {got.score}")
    card = env.scorecard()
    if end is not None:
        if not card.complete:
            problems.append("End record present but the lifetime is not finished")
        if not _same(end.get("overall"), card.overall):
            problems.append(f"End record says overall {end.get('overall')!r}, replay gives {card.overall}")
        phases = end.get("phases")
        if not isinstance(phases, dict) or set(phases) != set(card.phases) or not all(
                _same(phases[p], card.phases[p]) for p in card.phases):
            problems.append(f"End record phases {phases!r} differ from the replay's {card.phases}")
        if end.get("played") != card.played or end.get("total") != card.total:
            problems.append(f"End record says {end.get('played')!r} of {end.get('total')!r} levels, replay gives "
                            f"{card.played} of {card.total}")
    return Verification(not problems, card, problems, agent)
