"""Presses random keys (never restart). Learns nothing, so it scores about the same in every phase."""

from __future__ import annotations

import random

from ..actions import Action
from . import Agent


class RandomAgent(Agent):
    name = "random"

    def __init__(self, seed: int = 1):
        self.rng = random.Random(seed)

    def act(self, obs):
        return self.rng.choice([a for a in obs.available_actions if a != Action.RESET])
