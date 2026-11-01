"""Train on generated lifetimes, then test on held-out ones. Run it with:

    python examples/train_then_test.py                       # the built-in explorer
    python examples/train_then_test.py my_agent.py:MyAgent   # yours (run from this folder)

One agent object plays every lifetime, so anything it learns while training carries into the test. The held-out
lifetimes add a rule never seen in training (coins) and pair rules never seen together, so the test score shows
whether what it learned generalises, not whether it remembers levels.
"""

import sys

from longgame import evaluate, load_agent


def mean(cards):
    return 100 * sum(c.overall for c in cards) / len(cards)


if __name__ == "__main__":
    agent = load_agent(sys.argv[1] if len(sys.argv) > 1 else "explorer")
    train = [evaluate(agent, f"train-v1-{seed}") for seed in range(5)]      # any seeds: there are a billion
    test = [evaluate(agent, f"heldout-v1-{seed}") for seed in range(5)]
    print(f"training lifetimes: {mean(train):.1f}%   held-out lifetimes: {mean(test):.1f}%")
