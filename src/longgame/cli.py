"""The ``longgame`` command.

    longgame play                     play in your browser (progress is saved)
    longgame play --terminal          play in the terminal
    longgame run random               run an agent through a lifetime and print its scorecard
    longgame run my_agent.py:MyAgent --record runs/mine.jsonl
    longgame verify runs/mine.jsonl   replay a recording and confirm its score
    longgame serve                    JSON lines on stdin/stdout, for agents in any language
    longgame list                     lifetimes that ship with the toolkit, and the generated ones
    longgame show train-v1-42 --maps  what is in a lifetime (worlds, rules, pars, maps); --save writes it as JSON
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
    from . import worlds
    for name in lifetimes():
        spec = load_spec(name)
        print(f"{name}: {spec.title} — {len(spec.visits)} visits, {spec.total_levels} levels. {spec.description}")
    held = ", ".join("+".join(p) for p in worlds.HELD_OUT_PAIRS if not set(p) & set(worlds.HELD_OUT_MECHANICS))
    print(f"train-{worlds.VERSION}-<seed>: generated training lifetimes, any seed from 0 to 999999999 — 14 visits, "
          f"28 levels, made by the world maker. They never use {', '.join(worlds.HELD_OUT_MECHANICS)}, or {held}.")
    print(f"heldout-{worlds.VERSION}-<seed>: generated held-out lifetimes — the same shape, but with the rules kept "
          f"out of training: {', '.join(worlds.HELD_OUT_MECHANICS)} in a learn world, and held-out pairs in every "
          f"remix.")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    from .worlds import world_rules
    spec = load_spec(args.lifetime)
    if args.save:
        Path(args.save).write_text(json.dumps(spec.to_dict(), indent=1) + "\n", encoding="utf-8")
        print(f"wrote {args.save}")
    print(f"{spec.id}: {spec.title} — {len(spec.visits)} visits, {spec.total_levels} levels")
    rules = world_rules(spec)
    for i, v in enumerate(spec.visits):
        pars = ", ".join(str(lv.par) for lv in v.levels)
        print(f"{i + 1:>3}. world {v.world}  {v.phase:<7} {'+'.join(rules[v.world]) or 'maze':<14} par {pars}")
        if args.maps:
            maps = [list(lv.map) for lv in v.levels]
            for r in range(max(len(m) for m in maps)):
                print("     " + "   ".join(m[r] if r < len(m) else " " * len(m[0]) for m in maps))
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
            from .worlds import is_generated
            named = args.lifetime in lifetimes() or is_generated(args.lifetime)
            custom = "" if named else f" --lifetime {args.lifetime}"
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
    table = compute(seeds=args.seeds, generated=args.generated)
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

    s = sub.add_parser("list", help="lifetimes that ship with the toolkit, and the generated ones")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("show", help="what is in a lifetime: worlds, rules, pars (and maps)")
    s.add_argument("lifetime", help="lifetime id (e.g. practice-v0, train-v1-42) or path to a lifetime .json")
    s.add_argument("--maps", action="store_true", help="print every level's map")
    s.add_argument("--save", metavar="FILE", help="also write the lifetime as JSON (e.g. to edit or share it)")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("check", help="check a lifetime's levels: parse, solvable, par is the true minimum")
    s.add_argument("lifetime", help="lifetime id or path to a lifetime .json")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("baselines", help="recompute the built-in agents' scores")
    s.add_argument("--seeds", type=int, default=20, help="random-agent seeds on shipped lifetimes")
    s.add_argument("--generated", type=int, default=10, help="generated lifetimes per family (train, heldout)")
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
