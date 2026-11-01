# Long Game API

Everything here is importable from `longgame` unless a module is named. Python 3.9+, no dependencies (the Gymnasium
wrapper needs `gymnasium` and `numpy`). The examples in [examples/](../examples) come with a git clone, not with pip.

- [Lifetimes](#lifetimes) · [Observations](#observations) · [Actions](#actions) · [Scoring](#scoring)
- [Agents](#agents) · [Recordings](#recordings) · [Command line](#command-line)
- [JSON-lines protocol](#json-lines-protocol) · [Gymnasium](#gymnasium) · [ARC-AGI-3 bridge](#arc-agi-3-bridge)
- [Lifetime files](#lifetime-files)

## Lifetimes

```python
env = longgame.make(lifetime="practice-v0", render_mode=None, record=None, agent="")
```

- `lifetime`: a shipped id (`longgame.lifetimes()` lists them), a path to a [lifetime file](#lifetime-files), or a
  dict in that format.
- `render_mode`: `None`, `"terminal"` (coloured frames printed after every action) or `"ascii"` (map characters).
- `record`: a path; finished levels are appended there as JSON lines (see [Recordings](#recordings)). `agent` names
  the agent in the recording.

`make` returns a `Lifetime`:

| | |
|---|---|
| `reset() -> Observation` | Start the lifetime at its first level. Required before `step`. Starts a recording over. |
| `step(action) -> Observation` | Take one action (an `Action`, its id, or a name such as `"up"`). |
| `observe() -> Observation` | The current observation, without acting. |
| `scorecard() -> Scorecard` | Scores so far. |
| `render(color=True) -> str` | The current screen as text. |
| `done`, `history`, `results` | Lifetime over? All actions taken (ids); `LevelResult`s so far. |
| `close()` / `with make(...) as env:` | Closes the recording file. |

`longgame.replay(actions, lifetime)` rebuilds a `Lifetime` from a list of action ids. `longgame.load_spec(lifetime)`
returns the `LifetimeSpec`: `id`, `title`, `phases`, `visits` (each with `world`, `phase` and `levels`, each level
with `par` and `map`), `total_levels`, `budget(par)` and a `digest` naming exactly that content.

## Observations

`Observation` (frozen dataclass; `to_dict()` gives plain JSON types):

| Field | |
|---|---|
| `grid` | Rows of colour ids 0–15, the screen a person sees. The last row is a status bar (one key cell per key held). Empty when `done`. |
| `world`, `phase` | The world's letter and the lifetime phase (`learn`, `remix`, `return` in practice-v0). |
| `visit`, `visits` | Index of this visit in the lifetime, and the number of visits. |
| `level`, `levels` | Index of the level within this visit, and the number of levels in it. |
| `actions`, `budget` | Actions used on this level, and how many it allows. |
| `played`, `total` | Levels left behind so far in the lifetime (finished or out of budget), and in total. |
| `cleared` | Levels finished so far. |
| `done` | The lifetime is over. |
| `available_actions` | The `Action`s this world accepts. |
| `result` | A `LevelResult` when the action that led here ended a level (the grid already shows the next one), else `None`. |
| `lifetime` | The lifetime's id. |

The colour ids are fixed across worlds, so an agent can learn what each colour does, but nothing tells it: working
that out is part of the test. Worlds are named by letter so the name gives nothing away.

## Actions

`Action` is an `IntEnum` whose ids and names match ARC-AGI-3's `GameAction`:

| id | name | ARC-AGI-3 name | |
|---:|---|---|---|
| 0 | `RESET` | `RESET` | restart the current level (counts as an action) |
| 1 | `UP` | `ACTION1` | |
| 2 | `DOWN` | `ACTION2` | |
| 3 | `LEFT` | `ACTION3` | |
| 4 | `RIGHT` | `ACTION4` | |
| 5 | `USE` | `ACTION5` | interact |
| 6 | `CLICK` | `ACTION6` | reserved, no world uses it yet |
| 7 | `UNDO` | `ACTION7` | reserved, no world uses it yet |

`Action.coerce(x)` accepts an `Action`, an id or a name (`"up"`, `"ACTION1"`, `"restart"`, `"w"`). An action that is
not in `obs.available_actions` raises `InvalidAction` (a `ValueError`) and costs nothing.

## Scoring

- A level scores `min(1, par / actions)` when finished and 0 when its budget runs out (`longgame.level_score`). Par
  is the fewest actions that finish it, found by breadth-first search over every reachable state.
- Budget: `max(100, 20 × par)` actions in practice-v0. Every action counts, including restarts and actions that
  change nothing.
- A phase scores the mean of its levels; the lifetime score (`overall`) is the mean of the phase scores. A phase with
  no levels played yet counts as 0.

`Scorecard`: `phases` (dict), `overall`, `played`, `total`, `complete` (every level played), `results` (list of
`LevelResult`), `lifetime`, `digest`, `summary()`, `to_dict()`.

`LevelResult`: `visit`, `level`, `world`, `phase`, `par`, `actions` (how many), `cleared`, `score`.

## Agents

```python
class Agent:
    name = "agent"
    def start(self, obs): ...        # once, with the first observation
    def act(self, obs): ...          # every action: return an Action, id or name
    def finish(self, scorecard): ... # once, at the end

longgame.evaluate(agent, lifetime="practice-v0", record=None, render_mode=None, max_actions=None) -> Scorecard
longgame.load_agent("random" | "explorer" | "solver" | "package.module:Class" | "path/file.py:Class", options)
```

Built in: `longgame.agents.random_agent.RandomAgent(seed=1)`, `longgame.agents.explorer.ExplorerAgent()` and
`longgame.agents.solver.SolverAgent()` (uses the engine's rules: for checking harnesses, never as a result).

## Recordings

`make(..., record=path)`, `evaluate(..., record=path)` and `longgame run ... --record path` write JSON lines:

```text
{"type":"start","longgame":"0.1.0","lifetime":"practice-v0","digest":"…","agent":"my-agent","started":"…"}
{"type":"level","visit":0,"level":0,"world":"A","phase":"learn","par":10,"actions":[4,4,…],"cleared":true,"score":0.83}
…
{"type":"end","phases":{…},"overall":0.42,"played":28,"total":28}
```

A level line is written when the level ends; its `actions` is the list of action ids taken on that level.
`longgame.verify(path, lifetime=None)` (or `longgame verify path`)
replays every action against the rules and returns a `Verification` (`ok`, `scorecard`, `problems`, `agent`). It
fails if the levels' digest differs from the lifetime's, if any recorded result differs from the replay, or if
actions do not end exactly one level per line. A recording of a lifetime loaded from a file needs that file:
`longgame verify run.jsonl --lifetime my-lifetime.json`.

## Command line

```text
longgame play [LIFETIME] [--terminal] [--fresh] [--port 8765] [--no-browser] [--no-color]
longgame run AGENT [--lifetime ID|FILE] [--record PATH] [--render terminal|ascii] [--arg KEY=VALUE]...
                   [--max-actions N] [--json]
longgame verify RECORDING [--lifetime ID|FILE]
longgame serve [--lifetime ID|FILE] [--record PATH]
longgame check LIFETIME             every level parses, can be finished, and its par is the true minimum
longgame list
longgame baselines [--seeds 20] [--write]
```

`python -m longgame` works the same. `longgame play` keeps progress in `~/.longgame/progress/` (or
`$LONGGAME_HOME/progress/`) and saves a finished lifetime as a verifiable recording in `~/.longgame/recordings/`. The
player only listens on 127.0.0.1; on a remote machine, tunnel it: `ssh -L 8765:127.0.0.1:8765 host`, then open
http://127.0.0.1:8765/ locally.

## JSON-lines protocol

`longgame serve` reads one JSON object per line on stdin and answers with one per line on stdout:

| Request | Reply |
|---|---|
| `{"cmd": "reset"}` | `{"observation": {...}}` |
| `{"cmd": "step", "action": 1}` (id or name) | `{"observation": {...}}` |
| `{"cmd": "observe"}` | `{"observation": {...}}` |
| `{"cmd": "score"}` | `{"scorecard": {...}}` |
| `{"cmd": "lifetimes"}` | `{"lifetimes": ["practice-v0"]}` |
| `{"cmd": "make", "lifetime": "...", "agent": "..."}` | `{"ok": true}` (then `reset`) |

Observations use the field names above. A bad request gets `{"error": "..."}` and changes nothing. See
[examples/node_agent.mjs](../examples/node_agent.mjs).

## Gymnasium

```python
import gymnasium as gym
import longgame.gym  # registers LongGame/practice-v0

env = gym.make("LongGame/practice-v0")      # or longgame.gym.LongGameEnv(lifetime, size=None)
obs, info = env.reset()
obs, reward, terminated, truncated, info = env.step(env.action_space.sample())
```

Needs `pip install gymnasium numpy`. One episode is one whole lifetime. Observations are `uint8` arrays padded with
wall colour to a fixed square (by default the smallest that fits every level; `size=64` for ARC-sized frames).
`Discrete(6)` actions are the ids 0–5. When a level ends, the reward is its score divided by (number of phases ×
levels in its phase), so **an episode's return equals the lifetime score**; `info["level_score"]` has the plain level
score and the final `info` the full scorecard.

## ARC-AGI-3 bridge

```python
from arcengine import GameAction          # optional (needs Python 3.12+); plain ids 0-7 work too
from longgame.arc import ArcEnvironment

env = ArcEnvironment("practice-v0")
frame = env.reset()                       # an arcengine FrameData (or a look-alike ArcFrame without arcengine)
frame = env.step(GameAction.ACTION1)
env.action_space                          # [GameAction.RESET, GameAction.ACTION1, ..., GameAction.ACTION5]
print(env.scorecard())
```

`ArcEnvironment` has the ARC toolkit environment's `reset()`, `step(action, data=None, reasoning=None)`,
`action_space` and `observation_space`, so an ARC-AGI-3 agent loop can play a lifetime unchanged. Two differences:
the first `reset()` starts the lifetime and later ones restart the current level (counting an action, like RESET),
because a lifetime is never wiped; and once the lifetime is over, actions and resets change nothing (`env.done`).
`Lifetime.step` also accepts `GameAction` members directly.

`longgame.arc.frame_data(obs)` returns a dict shaped like ARC-AGI-3's `FrameData`: `game_id` (`lifetime/world`),
`frame` (a list holding one 64 × 64 grid padded with wall colour; empty once the lifetime is over), `state`
(`NOT_FINISHED`; at the end `WIN` if every level was finished, else `GAME_OVER`), `levels_completed` (levels of the
current visit already played, finished or not) and `win_levels` (levels in the visit), `available_actions` (ids).
With the shared action ids, an agent loop written against ARC-AGI-3 frames can drive a lifetime with small changes.

## Lifetime files

A lifetime is JSON:

```json
{
  "id": "my-lifetime",
  "title": "My lifetime",
  "phases": ["learn"],
  "budget": {"minimum": 100, "per_par": 20},
  "visits": [
    {"world": "A", "phase": "learn", "levels": [{"par": 4, "map": ["######", "#@$o.#", "#...E#", "######"]}]}
  ]
}
```

Every phase listed needs at least one level. Map characters: `#` wall, `.` floor, `@` player, `E` exit, `$` crate, `o` pad, `*` crate on a pad, `k` key, `D`
door, `_` ice, `S` switch, `G`/`g` gate closed/open, `T` twin, `c` coin. Maps must be rectangular and walled in.
`par` must be the fewest actions possible: `longgame check my-lifetime.json` checks every level.
