# Contributing to Long Game

Thanks for helping. Agents, worlds, bug reports and results are all welcome.

## Set up

```bash
git clone https://github.com/Nova-Rift/longgame && cd longgame
python -m pip install -e ".[gym]"
python -m unittest discover -s tests
```

## Ground rules

- **Practice lifetimes never change.** Scores on `practice-v0` must stay comparable forever, so its levels, pars,
  budgets and rules are frozen; `tests/test_parity.py` replays traces recorded from the original engine to hold
  them in place. New levels or rule changes go in a new lifetime (`practice-v1`, …).
- **Same screen for people and AI.** Agents get exactly the grid a person sees, and nothing a person doesn't.
- **No instructions, core knowledge only.** No words, letters or numbers as symbols, no cultural icons. A world must
  be learnable by playing it.
- **Every level must be solvable, with an honest par.** `longgame check my-lifetime.json` solves every level and
  compares its par.
- **Never commit hidden evaluation levels.** Anything in this repository is public practice material.

## Adding worlds

Worlds are levels in a [lifetime file](docs/api.md#lifetime-files). Write the maps, set each `par` from the solver,
run `longgame check`, and play them yourself with `longgame play path/to/lifetime.json`. New mechanics (new map
characters and rules) need engine changes: add them with tests in `tests/test_engine.py`, a new colour id only if one
is free, and keep `practice-v0` untouched.

## Submitting results

Run your agent with `--record`, check the file with `longgame verify`, and open an issue with the recording, a short
description of the agent and the compute it used. Results on practice levels are for comparison and debugging, not
official scores.
