"""Long Game: can an AI keep learning new games without forgetting the old ones?

A continual-learning benchmark in the spirit of ARC-AGI. One agent plays a *lifetime*: many small grid worlds with
no instructions, one after another, never reset, including remixes of earlier worlds and returns to them.

Quick start::

    import longgame
    from longgame import Action

    env = longgame.make("practice-v0")   # or a generated lifetime: "train-v1-42", "heldout-v1-42"
    obs = env.reset()
    while not obs.done:
        obs = env.step(Action.UP)       # your agent decides here
    print(env.scorecard())
"""

__version__ = "0.2.0"

from . import arc, worlds
from .actions import Action, InvalidAction
from .agents import Agent, evaluate, load_agent
from .lifetime import (LevelResult, Lifetime, LifetimeSpec, Observation, Scorecard, level_score, lifetimes,
                       load_spec, make, replay)
from .recording import verify

__all__ = ["Action", "Agent", "InvalidAction", "LevelResult", "Lifetime", "LifetimeSpec", "Observation", "Scorecard",
           "__version__", "evaluate", "level_score", "lifetimes", "load_agent", "load_spec", "make", "replay",
           "verify", "worlds"]
