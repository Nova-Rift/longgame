<p align="center"><img src="docs/banner.svg" alt="Long Game" width="660"></p>

<p align="center"><b>Can an AI keep learning new games without forgetting the old ones?</b><br>
An open continual-learning benchmark in the spirit of <a href="https://arcprize.org/arc-agi">ARC-AGI</a>.</p>

<p align="center"><img src="docs/figures/play.gif" alt="A short level being played: push the crate across the ice onto the pad, pick up the key, open the door, reach the exit" width="460"></p>

<p align="center"><img src="docs/figures/idea.svg" alt="ARC-AGI scores each task on its own; Long Game scores what carries over across one lifetime" width="860"></p>

<p align="center"><img src="docs/figures/lifetime.svg" alt="One lifetime: learn worlds A to F, play remixes G, H and I, return to B to F with new levels" width="860"></p>

<p align="center"><img src="docs/figures/same-screen.svg" alt="The same screen shown as a picture for people and as a grid of numbers for AI" width="700"></p>

<p align="center"><img src="docs/figures/scoring.svg" alt="A level scores par divided by actions, and zero if the budget runs out" width="860"></p>

<p align="center"><img src="docs/figures/baselines.svg" alt="Baseline scores: random keys 1.2% overall, explorer 7.8%; the explorer gets no better on remix or return" width="860"></p>

## Quick start

```bash
pip install "git+https://github.com/Nova-Rift/longgame"

longgame play            # play it yourself in the browser
longgame run explorer    # score a baseline agent
```

## Write an agent

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

One agent object plays the whole lifetime and is never reset, so what it keeps is what it remembers.
More in [examples/](examples/) and the [API reference](docs/api.md).

| Also works with | |
|---|---|
| Gymnasium | `import longgame.gym` then `gym.make("LongGame/practice-v0")` (needs `gymnasium`) |
| Any language | `longgame serve`: JSON lines on stdin/stdout ([Node example](examples/node_agent.mjs)) |
| ARC-AGI-3 agents | same action ids; `longgame.arc.frame_data(obs)` gives an ARC-style 64 × 64 frame |

## Roadmap

- [x] v0.1: practice lifetime, browser player, verifiable recordings, baselines
- [ ] Generated worlds for unlimited training, with held-out rules for testing
- [ ] Changed-rule worlds and long gaps between visits
- [ ] ARC-style picture puzzles inside lifetimes
- [ ] Human baselines, hidden test lifetimes, a leaderboard

The full plan, and how every ARC-AGI test maps onto Long Game: [docs/design.md](docs/design.md).

---

[Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [Cite](CITATION.cff) · MIT licence.
An independent project, not affiliated with the ARC Prize Foundation.
