"""A lifetime: one agent plays every level of every world in a fixed order and is never reset.

A level ends when it is finished or its action budget runs out; either way the lifetime moves on. Nothing wipes the
agent's memory between worlds, so a learner can carry what it worked out into remixes and return visits. That is the
point: the score shows whether it did.

Scoring (v0): a level scores ``par / actions`` (capped at 1) when finished and 0 when its budget runs out, where
par is the fewest actions possible. Every action counts, including restarts and actions that change nothing. A
phase's score is the mean over its levels; the lifetime score is the mean of the phase scores.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

from . import engine
from .actions import ENGINE_MOVE, KEYS_AND_RESET, Action, InvalidAction


# --- lifetime specifications ----------------------------------------------------------------------------------------

@dataclass(frozen=True)
class LevelSpec:
    par: int
    map: Sequence[str]


@dataclass(frozen=True)
class Visit:
    world: str
    phase: str
    levels: Sequence[LevelSpec]


@dataclass(frozen=True)
class LifetimeSpec:
    id: str
    title: str
    description: str
    phases: Sequence[str]
    visits: Sequence[Visit]
    budget_minimum: int = 100
    budget_per_par: int = 20

    @property
    def total_levels(self) -> int:
        return sum(len(v.levels) for v in self.visits)

    def budget(self, par: int) -> int:
        """Actions allowed on a level before it ends unfinished: max(100, 20 x par) in v0."""
        return max(self.budget_minimum, self.budget_per_par * par)

    @property
    def digest(self) -> str:
        """SHA-256 of the levels, budgets and order, so a recording names exactly what was played."""
        body = {"phases": list(self.phases), "budget": [self.budget_minimum, self.budget_per_par],
                "visits": [{"world": v.world, "phase": v.phase,
                            "levels": [{"par": lv.par, "map": list(lv.map)} for lv in v.levels]} for v in self.visits]}
        return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LifetimeSpec":
        """Build and fully check a spec: every map must parse and every par be a positive whole number. (Whether a
        par is the true minimum is checked by ``longgame check``, which has to solve every level.)"""
        try:
            return cls._from_dict(d)
        except (KeyError, TypeError, AttributeError) as e:
            raise ValueError(f"Malformed lifetime: {e!r}") from None

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> "LifetimeSpec":
        if not isinstance(d, dict):
            raise ValueError("A lifetime must be a JSON object")
        if not isinstance(d.get("id"), str) or not d["id"]:
            raise ValueError('A lifetime needs an "id" (a non-empty string)')
        if not isinstance(d.get("visits"), list) or not d["visits"]:
            raise ValueError('A lifetime needs a non-empty "visits" list')
        visits = []
        for i, v in enumerate(d["visits"]):
            where = f"visit {i + 1}"
            if not isinstance(v.get("world"), str) or not isinstance(v.get("phase"), str):
                raise ValueError(f'{where} needs "world" and "phase" strings')
            if not isinstance(v.get("levels"), list) or not v["levels"]:
                raise ValueError(f"{where} needs at least one level")
            levels = []
            for j, lv in enumerate(v["levels"]):
                par, rows = lv.get("par"), lv.get("map")
                if not isinstance(par, int) or isinstance(par, bool) or par < 1:
                    raise ValueError(f"{where} level {j + 1}: par must be a whole number of at least 1")
                if not isinstance(rows, list) or not all(isinstance(r, str) for r in rows):
                    raise ValueError(f"{where} level {j + 1}: map must be a list of strings")
                try:
                    engine.parse_level(rows)
                except ValueError as e:
                    raise ValueError(f"{where} level {j + 1}: {e}") from None
                levels.append(LevelSpec(par, tuple(rows)))
            visits.append(Visit(v["world"], v["phase"], tuple(levels)))
        phases = tuple(d.get("phases") or dict.fromkeys(v.phase for v in visits))
        unknown = {v.phase for v in visits} - set(phases)
        if unknown:
            raise ValueError(f"Visits use phases not listed in 'phases': {sorted(unknown)}")
        empty = [p for p in phases if not any(v.phase == p for v in visits)]
        if empty:
            raise ValueError(f"Phases with no levels would always score 0: {empty}")
        budget = d.get("budget", {})
        minimum, per_par = budget.get("minimum", 100), budget.get("per_par", 20)
        if not all(isinstance(x, int) and not isinstance(x, bool) and x >= 1 for x in (minimum, per_par)):
            raise ValueError("budget minimum and per_par must be whole numbers of at least 1")
        return cls(id=d["id"], title=str(d.get("title", d["id"])), description=str(d.get("description", "")),
                   phases=phases, visits=tuple(visits), budget_minimum=minimum, budget_per_par=per_par)


def lifetimes() -> List[str]:
    """Ids of the lifetimes that ship with the toolkit."""
    folder = resources.files("longgame") / "lifetimes"
    return sorted(p.name[:-5] for p in folder.iterdir() if p.name.endswith(".json"))


def load_spec(lifetime: Union[str, Path, Dict[str, Any], LifetimeSpec] = "practice-v0") -> LifetimeSpec:
    """A shipped lifetime by id, a path to a lifetime JSON file, a dict in that format, or a spec (returned as is)."""
    if isinstance(lifetime, LifetimeSpec):
        return lifetime
    if isinstance(lifetime, dict):
        return LifetimeSpec.from_dict(lifetime)
    path = Path(lifetime)
    if path.suffix == ".json" and path.exists():
        return LifetimeSpec.from_dict(json.loads(path.read_text(encoding="utf-8")))
    name = str(lifetime)
    if name not in lifetimes():
        raise ValueError(f"Unknown lifetime {name!r}; available: {', '.join(lifetimes())} (or a path to a .json file)")
    text = (resources.files("longgame") / "lifetimes" / f"{name}.json").read_text(encoding="utf-8")
    return LifetimeSpec.from_dict(json.loads(text))


# --- what an agent sees and what it scored --------------------------------------------------------------------------

@dataclass(frozen=True)
class LevelResult:
    """How one level went."""

    visit: int  # index of the visit in the lifetime
    level: int  # index of the level within the visit
    world: str
    phase: str
    par: int
    actions: int
    cleared: bool
    score: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Observation:
    """What the agent sees before choosing its next action.

    ``grid`` is the screen a person sees: rows of colour ids 0-15, the last row a status bar. ``result`` is set when
    the action that led here ended a level (finished or out of budget); ``grid`` then already shows the next level.
    ``played`` counts levels left behind so far, ``cleared`` the ones finished. When ``done`` is true the lifetime is
    over and ``grid`` is empty.
    """

    grid: List[List[int]]
    world: str
    phase: str
    visit: int
    visits: int
    level: int
    levels: int
    actions: int
    budget: int
    played: int
    total: int
    cleared: int
    done: bool
    available_actions: List[Action]
    result: Optional[LevelResult] = None
    lifetime: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["available_actions"] = [int(a) for a in self.available_actions]
        return d


@dataclass(frozen=True)
class Scorecard:
    """Scores between 0 and 1 for each phase, and overall (the mean of the phases)."""

    lifetime: str
    digest: str
    phases: Dict[str, float]
    overall: float
    played: int
    total: int
    results: List[LevelResult] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.played == self.total

    def to_dict(self) -> Dict[str, Any]:
        return {"lifetime": self.lifetime, "digest": self.digest, "phases": dict(self.phases), "overall": self.overall,
                "played": self.played, "total": self.total, "complete": self.complete,
                "results": [r.to_dict() for r in self.results]}

    def summary(self) -> str:
        parts = "  ".join(f"{p} {100 * s:.1f}%" for p, s in self.phases.items())
        cleared = sum(r.cleared for r in self.results)
        return (f"{self.lifetime}: overall {100 * self.overall:.1f}%  ({parts})  "
                f"{cleared} of {self.played} levels finished, {self.played} of {self.total} played")

    def __str__(self) -> str:
        return self.summary()


def level_score(par: int, actions: int, cleared: bool) -> float:
    """``par / actions`` capped at 1 when finished, else 0."""
    return min(1.0, par / actions) if cleared else 0.0


def score_results(results: Iterable[LevelResult], spec: LifetimeSpec) -> Scorecard:
    results = list(results)

    def mean(xs: List[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    phases = {p: mean([r.score for r in results if r.phase == p]) for p in spec.phases}
    return Scorecard(spec.id, spec.digest, phases, mean(list(phases.values())), len(results), spec.total_levels,
                     results)


# --- the environment ------------------------------------------------------------------------------------------------

class Lifetime:
    """One never-reset run through a lifetime of worlds. Create it with :func:`longgame.make`.

    >>> env = make("practice-v0")
    >>> obs = env.reset()
    >>> while not obs.done:
    ...     obs = env.step(choose(obs))
    >>> print(env.scorecard())
    """

    def __init__(self, spec: LifetimeSpec, render_mode: Optional[str] = None, recorder=None):
        if render_mode not in (None, "terminal", "ascii"):
            raise ValueError("render_mode must be None, 'terminal' or 'ascii'")
        self.spec = spec
        self.render_mode = render_mode
        self.recorder = recorder
        self._started = False
        self._begin()

    # state

    def _begin(self) -> None:
        self.visit = 0
        self.level = 0
        self.actions = 0
        self.results: List[LevelResult] = []
        self.history: List[int] = []
        self._level_actions: List[int] = []
        self._load()

    def _load(self) -> None:
        if self.done:
            return
        self._current = engine.parse_level(self._spec_level.map)
        self._state = self._current.start
        self.actions = 0
        self._level_actions = []

    @property
    def done(self) -> bool:
        return self.visit >= len(self.spec.visits)

    @property
    def started(self) -> bool:
        """True once reset() has been called."""
        return self._started

    @property
    def _cleared(self) -> int:
        return sum(r.cleared for r in self.results)

    @property
    def _spec_level(self) -> LevelSpec:
        return self.spec.visits[self.visit].levels[self.level]

    @property
    def available_actions(self) -> List[Action]:
        return [] if self.done else list(KEYS_AND_RESET)

    # API

    def reset(self) -> Observation:
        """Start the lifetime from its first level (a fresh lifetime; the agent's own memory is its business)."""
        self._begin()
        self._started = True
        if self.recorder:
            self.recorder.start(self.spec)
        obs = self.observe()
        self._render(obs)
        return obs

    def observe(self, result: Optional[LevelResult] = None) -> Observation:
        spec = self.spec
        if self.done:
            last = spec.visits[-1]
            return Observation([], last.world, last.phase, len(spec.visits) - 1, len(spec.visits),
                               len(last.levels) - 1, len(last.levels), 0, 0, len(self.results), spec.total_levels,
                               self._cleared, True, [], result, spec.id)
        v = spec.visits[self.visit]
        return Observation(engine.render(self._current, self._state), v.world, v.phase, self.visit, len(spec.visits),
                           self.level, len(v.levels), self.actions, spec.budget(self._spec_level.par),
                           len(self.results), spec.total_levels, self._cleared, False, self.available_actions, result,
                           spec.id)

    def step(self, action: Union[Action, int, str]) -> Observation:
        """Take one action. Returns the next observation; its ``result`` is set if this action ended a level."""
        if not self._started:
            raise RuntimeError("Call reset() before step()")
        if self.done:
            raise RuntimeError("The lifetime is over; call reset() to play it again")
        a = Action.coerce(action)
        if a not in self.available_actions:
            raise InvalidAction(f"{a.name} is not available here; available: "
                                f"{', '.join(x.name for x in self.available_actions)}")
        self.history.append(int(a))
        self._level_actions.append(int(a))
        self.actions += 1
        self._state, won = engine.step(self._current, self._state, ENGINE_MOVE[a])
        par = self._spec_level.par
        result = None
        if won or self.actions >= self.spec.budget(par):
            v = self.spec.visits[self.visit]
            result = LevelResult(self.visit, self.level, v.world, v.phase, par, self.actions, won,
                                 level_score(par, self.actions, won))
            finished_actions = self._level_actions
            self.results.append(result)
            self.level += 1
            if self.level >= len(v.levels):
                self.visit += 1
                self.level = 0
            self._load()  # maps were all checked when the spec loaded, so this cannot fail half way
            if self.recorder:  # the game state is complete before anything is written
                self.recorder.level(result, finished_actions)
                if self.done:
                    self.recorder.finish(self.scorecard())
        obs = self.observe(result)
        self._render(obs)
        return obs

    def scorecard(self) -> Scorecard:
        return score_results(self.results, self.spec)

    def render(self, color: bool = True) -> str:
        """The current screen as text (coloured for a terminal, or plain map characters)."""
        from .render import render_text
        return render_text(self.observe(), color=color)

    def close(self) -> None:
        if self.recorder:
            self.recorder.close()

    def __enter__(self) -> "Lifetime":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _render(self, obs: Observation) -> None:
        if self.render_mode:
            from .render import render_text
            print(render_text(obs, color=self.render_mode == "terminal"), flush=True)


def replay(actions: Iterable[Union[Action, int]], lifetime: Union[str, Path, LifetimeSpec] = "practice-v0"
           ) -> Lifetime:
    """Rebuild a lifetime from its action history (the rules are deterministic)."""
    env = Lifetime(load_spec(lifetime))
    env.reset()
    for a in actions:
        if env.done:
            raise ValueError("The recording has actions after the lifetime ended")
        env.step(a)
    return env


def make(lifetime: Union[str, Path, Dict[str, Any], LifetimeSpec] = "practice-v0", render_mode: Optional[str] = None,
         record: Union[None, str, Path] = None, agent: str = "") -> Lifetime:
    """Create a lifetime environment.

    ``lifetime``: a shipped id (see :func:`lifetimes`), a path to a lifetime JSON file, or a dict in that format.
    ``render_mode``: ``None``, ``"terminal"`` (coloured frames printed after every action) or ``"ascii"``.
    ``record``: a path; every finished level is appended there as JSON lines, verifiable with ``longgame verify``.
    """
    recorder = None
    if record is not None:
        from .recording import Recorder
        recorder = Recorder(record, agent=agent)
    return Lifetime(load_spec(lifetime), render_mode=render_mode, recorder=recorder)
