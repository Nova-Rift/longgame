"""The JSON-lines protocol: play from any language over stdin/stdout (``longgame serve``).

One JSON object per line in, one per line out::

    {"cmd": "reset"}                      -> {"observation": {...}}
    {"cmd": "step", "action": 1}          -> {"observation": {...}}   (action: id 0-7 or a name like "up")
    {"cmd": "observe"}                    -> {"observation": {...}}
    {"cmd": "score"}                      -> {"scorecard": {...}}
    {"cmd": "lifetimes"}                  -> {"lifetimes": ["practice-v0", ...]}
    {"cmd": "make", "lifetime": "..."}    -> {"ok": true}             (switch lifetime; then reset)

The observation's ``result`` is set when that action ended a level. Errors come back as ``{"error": "..."}`` and
change nothing.
"""

from __future__ import annotations

import json
import sys
from typing import IO, Any, Dict, Optional

from .lifetime import Lifetime, lifetimes, make


def handle(env: Lifetime, msg: Dict[str, Any], record: Optional[str] = None) -> Any:
    cmd = msg.get("cmd")
    if cmd is None:
        raise ValueError('Each request needs "cmd" (reset, step, observe, score, lifetimes or make)')
    if cmd == "reset":
        return {"observation": env.reset().to_dict()}
    if cmd == "step":
        if "action" not in msg:
            raise ValueError('step needs "action"')
        if not env.started:
            raise ValueError('Send {"cmd": "reset"} before the first step')
        return {"observation": env.step(msg["action"]).to_dict()}
    if cmd == "observe":
        return {"observation": env.observe().to_dict()}
    if cmd == "score":
        return {"scorecard": env.scorecard().to_dict()}
    if cmd == "lifetimes":
        return {"lifetimes": lifetimes()}
    if cmd == "make":
        new = make(msg.get("lifetime", "practice-v0"), record=record, agent=str(msg.get("agent", "")))
        env.close()  # only once the new one exists, so a bad request leaves the current game untouched
        return new
    raise ValueError(f"Unknown cmd {cmd!r}")


def serve(lifetime: str = "practice-v0", record: Optional[str] = None, stdin: IO[str] = sys.stdin,
          stdout: IO[str] = sys.stdout) -> None:
    env = make(lifetime, record=record)

    def send(obj: Any) -> None:
        stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
        stdout.flush()

    for line in stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
            if not isinstance(msg, dict):
                raise ValueError("Each line must be a JSON object")
            out = handle(env, msg, record)
            if isinstance(out, Lifetime):
                env = out
                out = {"ok": True}
            send(out)
        except Exception as e:  # report and keep serving
            send({"error": str(e)})
    env.close()
