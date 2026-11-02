# Long Game: the benchmark design

**Can an AI keep learning new games for a long time without forgetting the old ones?**

Long Game is a benchmark, and a training ground, made of small grid games with no instructions, played one
after another in a long stream: a *lifetime*. It shares the goal of [ARC-AGI](https://arcprize.org/arc-agi):
measure general intelligence as how efficiently a system picks up skills it has never seen, using tasks that are easy
for people and hard for AI. It adds what no ARC-AGI version scores today: whether those skills **last**, **build on
each other** and **survive change**. That is continual learning, and its classic failure, catastrophic forgetting.

> **Status (October 2026): v0.2 of the toolkit is out**, with one public practice lifetime (14 visits, 28 levels)
> and the world maker: endless generated lifetimes for training (`train-v1-*`) and for testing on held-out rules
> (`heldout-v1-*`). This document is the full plan; most of it is not built yet, and nothing here is a result.

## Why

ARC-AGI defines intelligence as skill-acquisition efficiency (Chollet, 2019). Every ARC-AGI task, and every
ARC-AGI-3 game, is scored on its own: the agent arrives, learns, is scored and moves on. Inside an ARC-AGI-3 game,
later levels build on earlier ones, but nothing measures what the agent still knows an hour, or a hundred games,
later.

People keep what they learn for years, pick up new things faster the more they know, and adjust when something
familiar changes without throwing the rest away. Neural networks trained on one task after another tend to do the
opposite. New learning overwrites old (catastrophic forgetting; McCloskey & Cohen, 1989), and after long training
they can lose the ability to learn at all (loss of plasticity; Dohare et al., 2024). Today's AI agents mostly avoid
the problem by never learning after deployment, or by keeping an ever-growing log of everything.

Long Game measures this directly, in the ARC style: novel games, no instructions, human-calibrated, scored on
efficiency.

## The idea in one picture

```
one agent, never reset, never told the rules ───────────────────────────────────────────►

  A       B       C       P1      A       D       B+D     C*      E       B       C
  new     new     new     puzzle  back    new     remix   changed new     back    back
                                                                          (long   (original
                                                                           gap)    rules)
```

- **new**: a game it has never seen. The first level is an easy tutorial.
- **back**: an earlier game, with new levels. Did it keep what it learned?
- **remix**: rules from two or more earlier games in one game. Can it combine them?
- **changed**: an earlier game with one rule altered. Does it notice and adapt, and when the original comes back,
  does it still remember the old rule?
- **puzzle**: an ARC-AGI-1/2 style puzzle room. Its rule families recur, remix and change too.

## What an agent faces

- **Worlds.** Each world is a small turn-based grid game with its own mechanics (crates to push onto pads, keys and
  doors, ice, switches that flip gates, a mirrored twin, …) and its own goal. Finishing a level is the only feedback.
- **Visits and levels.** A visit to a world is a few levels; later levels combine the world's mechanics.
- **Puzzle rooms.** The frame shows a few example input→output grids and a test input. The agent must produce the
  exact output grid, with two tries.
- **One lifetime.** The agent plays the whole stream in order and is never reset. It is told when a new visit
  starts, but not which world it is: recognising a returning world is part of the test.
- **The same screen as people.** Agents see what a person sees: frames of up to 64×64 cells in 16 colours. They
  choose from five keys (up, down, left, right, use), a click on a cell, undo, and restart level. That matches the
  ARC-AGI-3 format, so an ARC-AGI-3 agent can play through a thin adapter.

## What it measures

Every score is relative to people (see [Human baselines](#human-baselines)), so 100% means as good as a typical
person.

| Measure | Question | How |
|---|---|---|
| Acquisition | How fast does it pick up a new world? | Action efficiency on first visits against first-time players, using ARC-AGI-3's relative human action efficiency so the numbers are comparable |
| Retention | Does it still play an old world well when it comes back? | Efficiency on return visits against how it finished its last visit, plotted against the gap (worlds since): a forgetting curve |
| Relearning | When it has forgotten, does it relearn faster than the first time? | Actions to get back to its earlier efficiency against actions it needed at first ("savings", Ebbinghaus, 1885) |
| Learning to learn | Does it get faster at new worlds as its life goes on, or slower? | Acquisition by position in the lifetime, and against a fresh copy of the same agent (positive = transfer; falling = loss of plasticity) |
| Composition | Can it combine rules it learned separately? | Efficiency on remix worlds against the worlds they combine |
| Revision | When a rule changes, does it adapt and keep the old rule? | Actions to adapt to a changed world, then efficiency when the original returns (interference) |
| Cost | What did all that take? | Compute, wall-clock time and the size of the agent's saved state, reported with every score |

The **lifetime score** is the mean of acquisition, retention, composition and revision. The full profile is always
reported too: one number hides the trade-off between learning new things and keeping old ones.

## Tracks: where an agent may keep what it learns

This is the most important design choice. If an agent may keep an unlimited log, forgetting becomes a search problem
rather than a learning problem: a coding agent that stores everything in files forgets "selectively, not
catastrophically" (Wu et al., 2026). So scores are reported in three tracks.

1. **Weights (main track).** Working memory (context window, scratch files, buffers) is wiped at every visit
   boundary. Only the model's parameters carry over, and their number is fixed before the lifetime starts. Whatever
   the agent keeps, it learned into its weights while playing. This is where catastrophic forgetting bites, and the
   setting that matters for models that learn on the job. A model that cannot update its weights still plays, but
   starts every visit fresh: the baseline every learner must beat.
2. **Bounded memory.** Anything goes (weights, replay buffers, notes, retrieval), but the state the agent builds
   during its lifetime has a fixed size cap. A frozen pretrained model does not count against the cap but is named.
3. **Open.** No limits. Cost and saved-state size are reported, as ARC-AGI-2 reports cost per task.

## Everything ARC-AGI tests, and where it lives here

| ARC-AGI tests | Long Game tests it with |
|---|---|
| **ARC-AGI-1 (2019)** | |
| Learning a rule from about three examples; exact answers on a new input (grids 1×1 to 30×30, 10 colours) | Puzzle rooms, same format, exact match, two tries |
| Objectness: things hold together, persist and act by contact | Crates, keys, gates and blocks that move as objects |
| Goal-directedness: some things are agents with goals | Worlds with other agents: the mirrored twin, chasers, followers |
| Numbers and counting: count, compare, sort, add and subtract small numbers | Doors that need *n* keys, collect-all exits, counting puzzle families |
| Geometry and topology: lines, symmetry, rotation, translation, scaling, containment, connecting, copying | Mirror and rotation worlds; geometry puzzle families |
| **ARC-AGI-2 (2025)** | |
| Symbolic interpretation: symbols mean more than how they look | Marker cells whose meaning must be learned, reused across worlds |
| Compositional reasoning: several rules that interact | Multi-mechanic levels, remix worlds |
| Contextual rule application: the same rule applied differently by context | Changed worlds with a visual cue; context-dependent puzzle families |
| Every task solved by at least two people in two tries | Same rule for every level and puzzle |
| Efficiency reported alongside accuracy | Cost reported in every track |
| **ARC-AGI-3 (2026)** | |
| Exploration: getting information by acting | Every world: no instructions, no stated goals |
| Modelling: working out how the world works | Every world; return and changed worlds test whether the model was kept and updated |
| Goal-setting / goal acquisition: working out what winning is | Every world; some changed worlds change the goal |
| Planning and execution | Multi-step levels with an action budget |
| Memory | Within a level, across levels and, new here, across worlds and long gaps |
| Alignment (listed in ARC Prize's 2025 report without a definition; read here as acting on the goal the world actually rewards) | Changed-goal worlds, where the old goal no longer pays |
| Basic physics among the core priors | Pushing, sliding on ice, gravity worlds |
| Action efficiency against people; tutorial first level; several mechanics per game; difficulty through composition | Same per-level scoring and design rules |
| Public, semi-private and private sets | Same three-way split of lifetimes |
| **New in Long Game** | |
| (not scored by any ARC-AGI version) | Retention over long gaps, relearning savings, learning to learn and plasticity, revision without interference, recognising a world without labels, the three memory tracks |

## Design rules (inherited from ARC-AGI)

- **Core knowledge only.** No words, letters, digits used as symbols, or cultural icons. A person from anywhere can
  play.
- **Easy for people.** Every world is tried by at least ten fresh players and kept only if at least two finish every
  level (ARC-AGI-3's rule).
- **Novel.** Evaluation worlds use mechanics that never appear in training, and the evaluation lifetimes are hidden.
- **Fair.** Turn-based, the same seed gives the same game, and agents see exactly the frames people see.
- **Efficiency counts.** Each level has an action budget (5× the human baseline, as in ARC-AGI-3) and is scored on
  actions used. A solver confirms every level can be finished and gives its fewest possible actions.

## Human baselines

- **First play.** Each world is played fresh by ten or more people, as in ARC-AGI-3. These set the acquisition
  baseline.
- **Lifetime sessions.** People also play shorter lifetimes (about 90 minutes, then a return session days later), so
  return, remix, changed and puzzle visits have human baselines too. As a side result this gives human forgetting
  curves on games nobody has seen before.

## Built for training too

The engine that makes the test also makes unlimited training material:

- a **mechanic library** (starting with v0's crates and pads, keys and doors, ice, switches and gates, and the
  mirrored twin; growing to about 30, such as gravity, conveyors, teleporters, paint, counters and chasers);
- a **level generator and solver**, so every level is checked solvable and has a known fewest-actions count;
- a **lifetime generator** that varies order, gaps, remixes and rule changes.

Training worlds use only the public mechanics; evaluation worlds use mechanics held out from training, so a high score
cannot come from having seen the games before.

**Built so far (v0.2): the world maker.** It generates levels from the six v0 mechanics (crates and pads, keys and
doors, ice, switches and gates, the twin, coins) and mazes, one rule or two at a time, at three tiers of difficulty.
The solver checks every level, sets its par, and confirms each rule matters (without it, the level gets shorter or
plays differently). Lifetimes are named by seed (`train-v1-42`), so they are reproducible everywhere and recordings
of them verify by name. Held out from all training material: coins, and three pairs of training mechanics (crates
with gates, keys with ice, gates with the twin). `heldout-v1-*` lifetimes learn coins as a new world and remix only
held-out pairs. This is a first, public version of the held-out idea: the real evaluation worlds will use mechanics
that are not in the public code at all. One engine runs everywhere: fast and headless for reinforcement
learning, a Python (Gymnasium-style) API, a JSON-lines command line for any language, and a browser player for people.

## Gated worlds: levels that cannot be finished without what an earlier world taught

Direction from Clark (Nov 1, 2026). Today every level is solvable from scratch; earlier worlds only make an agent
faster, and the explorer baseline still scores about 7%. That measures carry-over as a gradient. A **gated** world adds
a hard yes/no signal: a later level depends on something that could only be learned earlier, with an action budget
too tight to rediscover it by search. Clark's rule (Nov 1, later the same day): not one gate but a chain, "between
each game": every level teaches a fact and the next level demands it. The form built first (Skirmish): each level
lights a pair of glyphs (a combination: first this square, then that), and the next level demands the previous pair
unlit, with the glyphs shuffled onto other squares; a wrong hold resets the lock, so the 56 pairs cannot be tried
out in time. An agent that did not play, or has forgotten, the earlier level cannot finish the next at all, so a
non-zero score on any level after the first is proof of retained learning rather than of search.

Gated worlds complement, not replace, the solvable ones: all-or-nothing cannot tell "forgot a little" from "forgot
everything", and that gradient is what the forgetting curves measure. In the weights track (context wiped at every
visit) a gated level is only passable through what reached the weights, which is the test Clark wants: continual
learning, not a long notebook. Hybrid agents (context for the current visit, weights for what keeps proving useful)
are scored in the bounded-memory track.

Built (Nov 1) in the real-time Skirmish test (code/sites-trial, src/skirmish): all 14 battles chained by locks; a bot
that reads the screen but remembers nothing wins at most the first; random orders win none. For the GPU farm's combat
game, see tools/gpu-farm/PLANNER.md, "Gated levels".

## Baselines (planned)

- Random actions (v0: 1.8% overall).
- The solver: the efficiency ceiling, not a learner.
- Frontier LLM agents in an ARC-AGI-3-style harness, in all three tracks.
- Reinforcement learning agents (PPO, [DreamerV3](https://github.com/Nova-Rift/dreamerv3-pytorch),
  [MuZero](https://github.com/Nova-Rift/muzero-pytorch)), each with plain fine-tuning, replay, EWC (Kirkpatrick et
  al., 2017) and continual backpropagation (Dohare et al., 2024).
- People (the human baselines above).

## Questions it is built to answer

- Can a transformer learn new game skills into its weights while deployed, without forgetting old ones?
- Do agents with a learned world model forget less than agents without one?
- Does short-term memory plus periodic consolidation into weights (a kind of sleep) beat either alone?
- Is forgetting here lost knowledge, or lost access to it (fast relearning would say access)?
- What predicts which skills survive: how often they were used, how recently, or how much later worlds share them?

## Roadmap

0. **Done: draft v0** (as "Lifelong Arcade"). 14 games in one run (learn six, remix three, return to five) with
   solver-checked levels.
1. **Done: toolkit v0.1.** The engine as a standalone Python package with ARC-AGI-3 action ids, a browser player,
   recordings anyone can verify, Gymnasium and JSON-lines interfaces, baselines and tests.
2. **Done: toolkit v0.2.** The world maker: a level generator and lifetime generator over the v0 mechanics, with
   held-out rules; the first training release. Still to come in this step: a bigger mechanic library.
3. Gated worlds (above), puzzle rooms, changed worlds, the full scorer and the three tracks.
4. Baseline agents.
5. Human study: first-play baselines and lifetime sessions.
6. Hidden semi-private and private lifetimes, a public leaderboard and a paper.

## Open questions

- Should world identities stay hidden (the agent must recognise a returning world), as planned, or be announced?
- How long should a lifetime be? Agents can play hundreds of worlds; people cannot. How should gaps for people
  (hours, days) be matched to gaps for agents (worlds played)?
- Weights track: do optimiser state and normalisation statistics count as parameters? Is a small fixed replay buffer
  allowed there, or only in the bounded-memory track?
- Should rule changes always come with a visual cue (contextual rules), never (the agent must notice), or both?
- Later versions: worlds with randomness, and worlds shared with other agents?
- How should the four parts of the lifetime score be weighted?

## Related work

- F. Chollet. [On the Measure of Intelligence](https://arxiv.org/abs/1911.01547). 2019.
- ARC Prize Foundation. [ARC-AGI-1](https://arcprize.org/arc-agi/1/), [ARC-AGI-2](https://arcprize.org/arc-agi/2/),
  and [ARC-AGI-3: A New Challenge for Frontier Agentic Intelligence](https://arxiv.org/abs/2603.24621), 2026.
- M. McCloskey and N. J. Cohen. Catastrophic interference in connectionist networks: the sequential learning problem.
  1989.
- R. M. French. Catastrophic forgetting in connectionist networks. *Trends in Cognitive Sciences*, 1999.
- J. Kirkpatrick et al. [Overcoming catastrophic forgetting in neural networks](https://arxiv.org/abs/1612.00796).
  *PNAS*, 2017.
- D. Lopez-Paz and M. Ranzato. [Gradient Episodic Memory for Continual Learning](https://arxiv.org/abs/1706.08840).
  NeurIPS 2017. (Backward and forward transfer measures.)
- K. Khetarpal, M. Riemer, I. Rish and D. Precup. [Towards Continual Reinforcement Learning: A Review and
  Perspectives](https://arxiv.org/abs/2012.13490). *JAIR*, 2022.
- D. Abel et al. [A Definition of Continual Reinforcement Learning](https://arxiv.org/abs/2307.11046). NeurIPS 2023.
- S. Dohare et al. Loss of plasticity in deep continual learning. *Nature*, 2024.
- M. Wołczyk et al. [Continual World](https://arxiv.org/abs/2105.10919). NeurIPS 2021. T. Tomilin et al.
  [COOM](https://proceedings.neurips.cc/paper_files/paper/2023/hash/d61d9f4fe4357296cb658795fd7999f0-Abstract.html).
  NeurIPS 2023. Continual RL benchmarks on robot and Doom tasks; not novel,
  instruction-free games with human baselines.
- C. Wu, J. Passenger and Y. Song. [Tracing the Thoughts of a Coding Agent Playing ARC-AGI-3: Lessons for Continual
  Learning](https://arxiv.org/abs/2610.11450). 2026.
- P. Asawa et al. [Continual Learning Bench](https://arxiv.org/abs/2606.05661). 2026. LLM systems on real-world
  stateful tasks.
- R. M. Battleday et al. [DiG-bench: Discovery in Games](https://arxiv.org/abs/2608.12593). 2026. Independent
  discovery games, no learning across games.

---

An independent research project by Clark Whitehead, not affiliated with or endorsed by the ARC Prize Foundation.
ARC-AGI is their benchmark. MIT licence.
