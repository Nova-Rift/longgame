<p align="center"><img src="docs/banner.svg" alt="Long Game" width="660"></p>

# Can an AI keep learning new games without forgetting the old ones?

<p align="center"><img src="docs/figures/play.gif" alt="A short level being played: push the crate across the ice onto the pad, pick up the key, open the door, reach the exit" width="460"></p>

<p align="center"><img src="docs/figures/idea.svg" alt="ARC-AGI scores each task on its own; Long Game scores what carries over across one lifetime" width="860"></p>

Long Game is an open benchmark, and a training ground, in the spirit of [ARC-AGI](https://arcprize.org/arc-agi). It is
made of small grid games with no instructions. ARC-AGI asks whether an AI can learn a task it has never seen. Long Game
asks the next question: when the AI has learned that task, does it *keep* it? People hold on to what they learn for years,
pick up new things faster the more they know, and adapt when something familiar changes without throwing the rest away.
Neural networks trained on one thing after another tend to do the opposite: new learning overwrites old. Long Game
measures that directly, with games that are easy for people and hard for AI.

<br>

## One agent plays one long lifetime of tiny games, and is never reset.

<p align="center"><img src="docs/figures/lifetime.svg" alt="One lifetime: learn worlds A to F, play remixes G, H and I, return to B to F with new levels" width="860"></p>

<p align="center"><img src="docs/figures/same-screen.svg" alt="The same screen shown as a picture for people and as a grid of numbers for AI" width="700"></p>

A lifetime is a long stream of visits to small worlds, played in order by one agent object that is never reset. Every
world is a tiny turn-based grid game with its own rules: crates to push onto pads, keys and doors, ice you slide across,
switches that flip gates. Finishing a level is the only feedback. The stream comes in three kinds of visit. **Learn** is a
world the agent has never seen. **Remix** combines the rules of two earlier worlds in one. **Return** is an earlier
world with new levels: did it keep what it learned? The agent is told when a new visit starts, but not which world it
is, so recognising an old friend is part of the test. Agents see exactly what a person sees, a grid of coloured cells,
delivered as a grid of numbers, and press the same five keys. That matches the ARC-AGI-3 format, so ARC-AGI-3 agents
can play through a thin adapter.

<br>

### Scores count only what carries over.

<p align="center"><img src="docs/figures/scoring.svg" alt="A level scores par divided by actions, and zero if the budget runs out" width="860"></p>

<p align="center"><img src="docs/figures/baselines.svg" alt="Baseline scores: random keys 1.2% overall, explorer 7.8%; the explorer gets no better on remix or return" width="860"></p>

Each level has a par: the number of actions a solver that knows the rules needs. A level scores par divided by the
actions the agent actually took, and zero if the action budget runs out. Scores are then reported by phase. A learn score
says how fast the agent picks up something new. A remix score says whether it can combine what it knows. A return score
says whether it still has it. The two shipped baselines show why the phases matter: random key presses score about 1%,
and an explorer that searches each level from scratch scores about 8%, but the explorer gains *nothing* on remixes or
return visits, because it remembers nothing between levels. A continual learner should, and that gap is the whole point.
Every run can be recorded, and a recording replays every action, so a recording is proof of a score.

<br>

#### Endless worlds: a new lifetime from any seed, with rules held out for testing.

<p align="center"><img src="docs/figures/worlds.gif" alt="The solver finishing five levels made by the world maker: crates and ice, keys and gates, and the twin for training; keys and ice, and coins, held out for testing" width="460"></p>

<p align="center"><img src="docs/figures/worlds.svg" alt="A chart of which rule combinations are for training and which are held out for testing, next to four generated levels" width="860"></p>

The practice lifetime is fixed, which is good for comparing agents and bad for training them. The world maker fixes that.
Give it any seed and it builds a fresh 28-level lifetime from a pool of rules, every level checked by the solver so it is
always possible. Some rule combinations, such as keys with ice or coins to collect, are held out of training altogether.
Train on as many generated lifetimes as you like, then test on the held-out rules the agent has never met. That split is
what lets Long Game measure learning rather than memorising.

```python
import longgame

env = longgame.make("train-v1-42")       # any seed: a new 28-level lifetime, every level solver-checked
test = longgame.make("heldout-v1-42")    # rules kept out of training: test on these
```

<br>

##### Play it yourself, or write an agent in a few lines.

```bash
pip install "git+https://github.com/Nova-Rift/longgame"

longgame play            # play it yourself in the browser
longgame play train-v1-7 # a lifetime the world maker made from seed 7
longgame run explorer    # score a baseline agent
```

An agent is one class with one method. It receives the screen and how the last level went, and returns one of six
actions. The same object plays the whole lifetime, so whatever it stores between calls is its memory.

```python
from longgame import Action, Agent, evaluate

class MyAgent(Agent):
    def act(self, obs):          # obs.grid is the screen; obs.result says how the last level went
        return Action.UP         # 0 restart · 1 up · 2 down · 3 left · 4 right · 5 interact

if __name__ == "__main__":
    print(evaluate(MyAgent(), record="runs/mine.jsonl"))
```

```bash
longgame run my_agent.py:MyAgent --record runs/mine.jsonl
longgame verify runs/mine.jsonl  # replays every action: a recording is proof of a score
```

More in [examples/](examples/) (including [train, then test on held-out rules](examples/train_then_test.py)) and the
[API reference](docs/api.md).

| Also works with | |
|---|---|
| Gymnasium | `import longgame.gym` then `gym.make("LongGame/practice-v0")`, or `"LongGame/train-v1"` for a new generated lifetime every episode (needs `gymnasium`) |
| Any language | `longgame serve`: JSON lines on stdin/stdout ([Node example](examples/node_agent.mjs)) |
| ARC-AGI-3 agents | `longgame.arc.ArcEnvironment()` acts like the ARC toolkit's environment: `step(GameAction.ACTION1)` returns a `FrameData` with a 64 × 64 frame |

###### Roadmap

- [x] v0.1: practice lifetime, browser player, verifiable recordings, baselines
- [x] v0.2: the world maker, endless generated worlds for training, with held-out rules for testing
- [ ] More rules (gravity, conveyors, paint, chasers, …) for the world maker
- [ ] Changed-rule worlds and long gaps between visits
- [ ] ARC-style picture puzzles inside lifetimes
- [ ] Human baselines, hidden test lifetimes, a leaderboard

The full plan, and how every ARC-AGI test maps onto Long Game: [docs/design.md](docs/design.md).

---

[Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [Cite](CITATION.cff) · MIT licence.
An independent project, not affiliated with the ARC Prize Foundation.
