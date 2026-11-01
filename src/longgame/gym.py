"""Gymnasium wrapper: one episode is one whole lifetime. Needs ``pip install gymnasium numpy``.

    import gymnasium as gym
    import longgame.gym  # registers the environments

    env = gym.make("LongGame/practice-v0")
    obs, info = env.reset()
    obs, reward, terminated, truncated, info = env.step(1)   # 1 = up

Observations are ``uint8`` arrays of colour ids, padded with wall colour to a fixed square (by default the smallest
that fits every level of the lifetime; pass ``size=64`` for ARC-AGI-3 sized frames). Actions are the public ids
0-5 (reset level, up, down, left, right, use). When a level ends the reward is its score weighted by
``1 / (number of phases x levels in its phase)``, else 0, so **an episode's return equals the lifetime score**
(the mean of the phase means), and maximising return optimises the benchmark itself. ``info`` carries world,
phase, level, actions used, budget, the result and the unweighted ``level_score``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

try:
    import gymnasium
    import numpy as np
    from gymnasium import spaces
except ImportError as e:  # pragma: no cover
    raise ImportError("The Gymnasium wrapper needs gymnasium and numpy: pip install gymnasium numpy") from e

from .actions import KEYS_AND_RESET, Action
from .arc import pad
from .engine import parse_level
from .lifetime import Lifetime, load_spec
from .render import render_text


class LongGameEnv(gymnasium.Env):
    metadata = {"render_modes": ["ansi"], "render_fps": 4}

    def __init__(self, lifetime: Any = "practice-v0", size: Optional[int] = None, render_mode: Optional[str] = None):
        self.spec_ = load_spec(lifetime)
        fit = max(max(lv.h + 1, lv.w) for lv in (parse_level(level.map) for v in self.spec_.visits
                                                 for level in v.levels))
        self.size = size or fit
        if self.size < fit:
            raise ValueError(f"size {self.size} is smaller than the largest level ({fit})")
        self.render_mode = render_mode
        self.observation_space = spaces.Box(0, 15, (self.size, self.size), dtype=np.uint8)
        self.action_space = spaces.Discrete(len(KEYS_AND_RESET))
        self._env = Lifetime(self.spec_)
        self._obs = None
        per_phase = {p: sum(len(v.levels) for v in self.spec_.visits if v.phase == p) for p in self.spec_.phases}
        self._weight = {p: 1.0 / (len(per_phase) * n) for p, n in per_phase.items()}

    def _array(self, obs) -> "np.ndarray":
        if obs.done:
            return np.ones((self.size, self.size), dtype=np.uint8)
        return np.asarray(pad(obs.grid, self.size), dtype=np.uint8)

    @staticmethod
    def _info(obs) -> Dict[str, Any]:
        return {"world": obs.world, "phase": obs.phase, "visit": obs.visit, "level": obs.level,
                "actions": obs.actions, "budget": obs.budget, "played": obs.played, "total": obs.total,
                "result": obs.result.to_dict() if obs.result else None}

    def reset(self, *, seed: Optional[int] = None, options: Optional[Dict[str, Any]] = None):
        super().reset(seed=seed)
        self._obs = self._env.reset()
        return self._array(self._obs), self._info(self._obs)

    def step(self, action):
        self._obs = self._env.step(Action(int(action)))
        result = self._obs.result
        reward = result.score * self._weight[result.phase] if result else 0.0
        info = self._info(self._obs)
        info["level_score"] = result.score if result else None
        if self._obs.done:
            info["scorecard"] = self._env.scorecard().to_dict()
        return self._array(self._obs), float(reward), self._obs.done, False, info

    def render(self):
        if self._obs is not None:
            return render_text(self._obs, color=False)
        return None

    def scorecard(self):
        return self._env.scorecard()


for _id in ("practice-v0",):
    if f"LongGame/{_id}" not in gymnasium.registry:
        gymnasium.register(f"LongGame/{_id}", entry_point="longgame.gym:LongGameEnv", kwargs={"lifetime": _id})
