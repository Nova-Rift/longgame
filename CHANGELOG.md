# Changelog

## 0.2.0 (2026-10-31)

The world maker: endless generated worlds for training, with held-out rules for testing.

- `longgame.worlds`: `level(rules, tier, seed)` makes one level from up to two rules (`crates`, `keys`, `ice`,
  `gates`, `twin`, `coins`; none for a maze) at tier 1-3; `levels(split)` streams them endlessly; `generate(split,
  seed)` makes a whole lifetime in practice-v0's shape. Every level is solver-checked: true par within its tier's
  range (tiers never overlap, so levels in a visit get longer), every rule matters, and no clutter (every crate
  pushed, every key picked up, every gate, switch and door changes the par).
- Generated lifetimes work anywhere an id does: `make("train-v1-42")`, `longgame play heldout-v1-7`, `run`, `serve`,
  the ARC bridge, and `verify` (rebuilt from the id, so no lifetime file is needed).
- Held-out rules: training never contains coins, or crates with gates, keys with ice, gates with the twin;
  `heldout-v1-*` lifetimes always do. v1 output is frozen and pinned by tests on every platform.
- Gymnasium: `LongGame/train-v1` and `LongGame/heldout-v1` play a new generated lifetime every episode
  (`reset(seed=n)` plays lifetime n; an unseeded reset draws one at random); `info["lifetime"]` names it.
- `longgame show` lists a lifetime's worlds, rules and pars (`--maps`, `--save`); `longgame list` describes the
  generated families; baselines include `train-v1` and `heldout-v1` (averaged over 10 lifetimes).
- `LifetimeSpec.to_dict()`.

## 0.1.1 (2026-10-31)

- ARC-AGI-3 agents can play directly: `longgame.arc.ArcEnvironment` has the ARC toolkit environment's interface
  and returns real `FrameData` objects when `arcengine` is installed; `step` accepts ARC's `GameAction` members
  (0.1.0 rejected them).
- Gymnasium environment declares `render_fps`.

## 0.1.0 (2026-10-31)

First public release.

- `practice-v0`: the Lifelong Arcade draft's 14 visits to 9 worlds (28 levels), unchanged: learn A-F, remix G-I,
  return to B-F.
- Pure-Python engine, checked frame by frame against the original TypeScript engine.
- `longgame.make` / `Lifetime` API with ARC-AGI-3 action ids, scorecards, verifiable JSON-lines recordings.
- Browser and terminal players with saved progress; `longgame` command (`play`, `run`, `verify`, `serve`, `check`,
  `list`, `baselines`).
- Gymnasium wrapper, JSON-lines protocol for any language, ARC-AGI-3 `FrameData` bridge.
- Baselines: random keys 1.2%, explorer 7.8%, solver 100%.
- `verify` only trusts levels it ships (or a lifetime file you pass), checks every field and reports malformed
  recordings instead of crashing; lifetime files are validated when loaded.
- Gymnasium episode return equals the lifetime score.
