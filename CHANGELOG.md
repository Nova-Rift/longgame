# Changelog

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
