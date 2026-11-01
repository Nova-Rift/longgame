"""A Gymnasium loop over one whole lifetime (needs: pip install gymnasium numpy). The return is the lifetime score."""

import gymnasium as gym

import longgame.gym  # noqa: F401  (registers LongGame/practice-v0)

env = gym.make("LongGame/practice-v0")
obs, info = env.reset(seed=0)
total, done = 0.0, False
while not done:
    obs, reward, done, truncated, info = env.step(env.action_space.sample())
    total += reward
print(f"return {total:.4f} = lifetime score {info['scorecard']['overall']:.4f}")
