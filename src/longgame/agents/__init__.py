"""Agents and the loop that runs one through a lifetime.

Write your own by subclassing :class:`Agent` and implementing ``act``::

    from longgame import Action, Agent, evaluate

    class MyAgent(Agent):
        name = "my-agent"

        def act(self, obs):
            return Action.UP

    print(evaluate(MyAgent()))
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Union

from ..actions import Action
from ..lifetime import Observation, Scorecard, make


class Agent:
    """Base class. ``act`` is called once per action; ``start`` and ``finish`` bracket the lifetime.

    The same agent object plays the whole lifetime and is never reset by the toolkit: whatever it keeps between
    levels and worlds is what it remembers.
    """

    name = "agent"

    def start(self, obs: Observation) -> None:
        """Called once with the first observation of the lifetime."""

    def act(self, obs: Observation) -> Union[Action, int, str]:
        raise NotImplementedError

    def finish(self, scorecard: Scorecard) -> None:
        """Called once when the lifetime is over."""


def evaluate(agent: Agent, lifetime: Any = "practice-v0", record: Union[None, str, Path] = None,
             render_mode: Optional[str] = None, max_actions: Optional[int] = None) -> Scorecard:
    """Run ``agent`` through a whole lifetime and return its scorecard."""
    env = make(lifetime, render_mode=render_mode, record=record, agent=getattr(agent, "name", type(agent).__name__))
    with env:
        obs = env.reset()
        agent.start(obs)
        n = 0
        while not obs.done:
            if max_actions is not None and n >= max_actions:
                break
            obs = env.step(agent.act(obs))
            n += 1
        card = env.scorecard()
    agent.finish(card)
    return card


BUILTIN = {"random": "longgame.agents.random_agent:RandomAgent",
           "explorer": "longgame.agents.explorer:ExplorerAgent",
           "solver": "longgame.agents.solver:SolverAgent"}


def load_agent(spec: str, options: Optional[Dict[str, Any]] = None) -> Agent:
    """Build an agent from ``random``, ``explorer``, ``solver``, ``package.module:Class`` or ``path/file.py:Class``."""
    target = BUILTIN.get(spec, spec)
    if ":" not in target:
        raise ValueError(f"Unknown agent {spec!r}: use {', '.join(BUILTIN)}, module:Class or file.py:Class")
    where, cls_name = target.rsplit(":", 1)
    if where.endswith(".py"):
        path = Path(where).resolve()
        if not path.exists():
            raise ValueError(f"No such file: {where}")
        mod_spec = importlib.util.spec_from_file_location(path.stem, path)
        if mod_spec is None or mod_spec.loader is None:
            raise ValueError(f"Cannot load {path}")
        module = importlib.util.module_from_spec(mod_spec)
        sys.modules[path.stem] = module
        mod_spec.loader.exec_module(module)
    else:
        if os.getcwd() not in sys.path:  # like `python -m`, find modules in the current folder
            sys.path.insert(0, os.getcwd())
        try:
            module = importlib.import_module(where)
        except ImportError as e:
            raise ValueError(f"Cannot import {where!r}: {e}") from None
    cls = getattr(module, cls_name, None)
    if cls is None:
        raise ValueError(f"{where!r} has no {cls_name!r}")
    try:
        return cls(**(options or {}))
    except TypeError as e:
        raise ValueError(f"Cannot create {cls_name} with {options or {}}: {e}") from None


__all__ = ["Agent", "evaluate", "load_agent", "BUILTIN"]
