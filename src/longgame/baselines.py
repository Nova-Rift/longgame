"""Reference scores for the built-in agents (shipped as baselines.json; a test checks the file is current).

``random`` is averaged over seeds 1-20; ``explorer`` is deterministic; ``solver`` is 100% by construction.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any, Dict

from .agents import evaluate
from .agents.explorer import ExplorerAgent
from .agents.random_agent import RandomAgent
from .lifetime import Scorecard, lifetimes


def _row(cards: "list[Scorecard]") -> Dict[str, Any]:
    n = len(cards)

    def avg(f) -> float:
        return round(sum(f(c) for c in cards) / n, 4)

    first = cards[0]
    row: Dict[str, Any] = {p: avg(lambda c, p=p: c.phases[p]) for p in first.phases}
    row["overall"] = avg(lambda c: c.overall)
    row["cleared"] = round(sum(sum(r.cleared for r in c.results) for c in cards) / n, 1)
    row["levels"] = first.total
    row["runs"] = n
    return row


def compute(seeds: int = 20) -> Dict[str, Dict[str, Any]]:
    table: Dict[str, Dict[str, Any]] = {}
    for lifetime in lifetimes():
        table[lifetime] = {
            "random": _row([evaluate(RandomAgent(seed=s), lifetime) for s in range(1, seeds + 1)]),
            "explorer": _row([evaluate(ExplorerAgent(), lifetime)]),
        }
    return table


def path() -> Path:
    return Path(str(resources.files("longgame") / "baselines.json"))


def write(table: Dict[str, Dict[str, Any]]) -> Path:
    p = path()
    p.write_text(json.dumps(table, indent=1) + "\n", encoding="utf-8")
    return p
