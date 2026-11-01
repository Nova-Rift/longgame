"""The ``longgame`` command.

    longgame play                     play in your browser (progress is saved)
    longgame play --terminal          play in the terminal
    longgame run random               run an agent through a lifetime and print its scorecard
    longgame run my_agent.py:MyAgent --record runs/mine.jsonl
    longgame verify runs/mine.jsonl   replay a recording and confirm its score
    longgame serve                    JSON lines on stdin/stdout, for agents in any language
    longgame list                     lifetimes that ship with the toolkit
    longgame check my-lifetime.json   check every level parses and its par is the true minimum
    longgame baselines                recompute the built-in agents' scores
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .lifetime import lifetimes, load_spec


def _options(pairs: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep:
            raise SystemExit(f"--arg expects key=value, got {pair!r}")
        try:
            out[key] = json.loads(value)
        except ValueError:
            out[key] = value
    return out


def cmd_list(args: argparse.Namespace) -> int:
    for name in lifetimes():
        spec = load_spec(name)
        print(f"{name}: {spec.title} — {len(spec.visits)} visits, {spec.total_levels} levels. {spec.description}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from .agents import evaluate, load_agent
    agent = load_agent(args.agent, _options(args.arg))
    card = evaluate(agent, lifetime=args.lifetime, record=args.record, render_mode=args.render,
                    max_actions=args.max_actions)
    if args.json:
        print(json.dumps(card.to_dict(), indent=1))
    else:
        print(card.summary())
        if args.record:
            custom = "" if args.lifetime in lifetimes() else f" --lifetime {args.lifetime}"
            print(f"recording: {args.record}  (check it with: longgame verify {args.record}{custom})")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from .recording import verify
    report = verify(args.recording, lifetime=args.lifetime)
    print(report)
    return 0 if report.ok else 1


def cmd_serve(args: argparse.Namespace) -> int:
    from .protocol import serve
    serve(args.lifetime, record=args.record)
    return 0


def cmd_play(args: argparse.Namespace) -> int:
    if args.terminal:
        from .terminal import play_in_terminal
        return play_in_terminal(args.lifetime, fresh=args.fresh, color=not args.no_color)
    from .webplay import play_in_browser
    play_in_browser(args.lifetime, port=args.port, open_browser=not args.no_browser, fresh=args.fresh)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    from .engine import parse_level, solve
    spec = load_spec(args.lifetime)
    problems = 0
    for i, v in enumerate(spec.visits):
        for j, level in enumerate(v.levels):
            where = f"visit {i + 1} (world {v.world}, {v.phase}) level {j + 1}"
            try:
                path = solve(parse_level(level.map))
            except (ValueError, RuntimeError) as e:
                print(f"{where}: {e}")
                problems += 1
                continue
            if path is None:
                print(f"{where}: cannot be finished")
                problems += 1
            elif len(path) != level.par:
                print(f"{where}: par is {level.par} but the fewest actions is {len(path)}")
                problems += 1
    print(f"{spec.id}: {spec.total_levels} levels, {problems} problem{'s' if problems != 1 else ''}")
    return 1 if problems else 0


def cmd_baselines(args: argparse.Namespace) -> int:
    from .baselines import compute, write
    table = compute(seeds=args.seeds)
    if args.write:
        path = write(table)
        print(f"wrote {path}")
    print(json.dumps(table, indent=1))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="longgame", description="Long Game: can an AI keep learning without forgetting?")
    p.add_argument("--version", action="version", version=f"longgame {__version__}")
    sub = p.add_subparsers(dest="command", metavar="command")

    s = sub.add_parser("play", help="play in your browser (or --terminal)")
    s.add_argument("lifetime", nargs="?", default="practice-v0")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true", help="print the address instead of opening a browser")
    s.add_argument("--terminal", action="store_true", help="play in this terminal instead")
    s.add_argument("--no-color", action="store_true", help="terminal: plain characters")
    s.add_argument("--fresh", action="store_true", help="start over instead of resuming saved progress")
    s.set_defaults(func=cmd_play)

    s = sub.add_parser("run", help="run an agent through a lifetime")
    s.add_argument("agent", help="random, explorer, solver, package.module:Class or path/to/file.py:Class")
    s.add_argument("--lifetime", default="practice-v0", help="lifetime id or path to a lifetime .json")
    s.add_argument("--record", help="write a verifiable recording (JSON lines) here")
    s.add_argument("--render", choices=["terminal", "ascii"], help="print every frame")
    s.add_argument("--arg", action="append", default=[], metavar="KEY=VALUE", help="passed to the agent's constructor")
    s.add_argument("--max-actions", type=int, help="stop early after this many actions")
    s.add_argument("--json", action="store_true", help="print the full scorecard as JSON")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("verify", help="replay a recording and confirm its score")
    s.add_argument("recording")
    s.add_argument("--lifetime", help="lifetime id or .json path, if not the one named in the recording")
    s.set_defaults(func=cmd_verify)

    s = sub.add_parser("serve", help="JSON lines on stdin/stdout for agents in any language")
    s.add_argument("--lifetime", default="practice-v0")
    s.add_argument("--record", help="write a verifiable recording here")
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("list", help="lifetimes that ship with the toolkit")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("check", help="check a lifetime's levels: parse, solvable, par is the true minimum")
    s.add_argument("lifetime", help="lifetime id or path to a lifetime .json")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("baselines", help="recompute the built-in agents' scores")
    s.add_argument("--seeds", type=int, default=20)
    s.add_argument("--write", action="store_true", help="update the baselines file shipped with the package")
    s.set_defaults(func=cmd_baselines)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except (ValueError, OSError) as e:
        print(f"longgame: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
