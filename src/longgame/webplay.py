"""Play in the browser (``longgame play``): a small local server around the same engine agents use.

The page shows exactly the grid an agent gets. Progress is saved after every action as the list of actions taken
(the rules are deterministic, so that list *is* the game), and a finished lifetime is saved as a recording that
``longgame verify`` accepts. Only this computer can reach the server (it listens on 127.0.0.1), and every request
must carry a random token from the page, so other web pages cannot play for you.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .lifetime import Lifetime, LifetimeSpec, load_spec, replay

STATIC = {"player.js": "text/javascript; charset=utf-8", "player.css": "text/css; charset=utf-8",
          "favicon.svg": "image/svg+xml"}


def home() -> Path:
    """Where progress and human recordings are kept: $LONGGAME_HOME or ~/.longgame."""
    return Path(os.environ.get("LONGGAME_HOME") or Path.home() / ".longgame")


def baselines() -> Dict[str, Any]:
    return json.loads((resources.files("longgame") / "baselines.json").read_text(encoding="utf-8"))


class Session:
    """One person's lifetime, saved after every action."""

    def __init__(self, spec: LifetimeSpec, fresh: bool = False, save_dir: Optional[Path] = None,
                 source: Optional[str] = None):
        self.spec = spec
        self.source = source  # the lifetime file, when it did not ship with the toolkit
        self.dir = save_dir or home()
        self.progress = self.dir / "progress" / f"{spec.id}.json"
        self.lock = threading.Lock()
        self.env = Lifetime(spec)
        self.env.reset()
        self.recording: Optional[Path] = None
        if not fresh:
            self._resume()

    def _resume(self) -> None:
        try:
            saved = json.loads(self.progress.read_text(encoding="utf-8"))
            if saved.get("digest") == self.spec.digest:
                self.env = replay(saved.get("actions", []), self.spec)
                self.recording = Path(saved["recording"]) if saved.get("recording") else None
        except (OSError, ValueError, KeyError):
            pass  # no usable save: start fresh

    def _save(self) -> None:
        self.progress.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.progress.with_suffix(".tmp")
        tmp.write_text(json.dumps({"lifetime": self.spec.id, "digest": self.spec.digest, "actions": self.env.history,
                                   "recording": str(self.recording) if self.recording else None}), encoding="utf-8")
        tmp.replace(self.progress)

    def _write_recording(self) -> None:
        from .recording import Recorder
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = self.dir / "recordings" / f"human-{self.spec.id}-{stamp}.jsonl"
        env = Lifetime(self.spec, recorder=Recorder(path, agent="human"))
        env.reset()
        for a in self.env.history:
            env.step(a)
        env.close()
        self.recording = path

    def state(self, last: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        obs = self.env.observe()
        card = self.env.scorecard()
        return {"lifetime": {"id": self.spec.id, "title": self.spec.title, "phases": list(self.spec.phases),
                             "visits": len(self.spec.visits)},
                "observation": obs.to_dict(), "scorecard": {k: v for k, v in card.to_dict().items() if k != "results"},
                "phases_played": sorted({r.phase for r in card.results}), "last": last,
                "moves": len(self.env.history), "recording": str(self.recording) if self.recording else None,
                "verify": (f'longgame verify "{self.recording}"' + (f' --lifetime "{self.source}"' if self.source else "")
                           if self.recording else None),
                "baselines": {name: b["overall"] for name, b in baselines().get(self.spec.id, {}).items()}}

    def step(self, action: Any) -> Dict[str, Any]:
        with self.lock:
            if self.env.done:
                return self.state()
            obs = self.env.step(action)
            if self.env.done and self.recording is None:
                self._write_recording()
            self._save()
            return self.state(obs.result.to_dict() if obs.result else None)

    def start_over(self) -> Dict[str, Any]:
        with self.lock:
            self.env = Lifetime(self.spec)
            self.env.reset()
            self.recording = None
            self._save()
            return self.state()


def _handler(session: Session, token: str, hosts: set):
    page = (resources.files("longgame") / "web" / "index.html").read_text(encoding="utf-8").replace("{{TOKEN}}", token)

    class Handler(BaseHTTPRequestHandler):
        server_version = "longgame"

        def log_message(self, *args: Any) -> None:  # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: Any) -> None:
            self._send(code, json.dumps(obj).encode(), "application/json")

        def _authorised(self) -> bool:
            given = self.headers.get("X-Longgame-Token", "").encode("utf-8", "replace")
            if hmac.compare_digest(given, token.encode()):
                return True
            self._json(403, {"error": "missing or wrong token; reload the page"})
            return False

        def _local_host(self) -> bool:
            # Pages from other sites that rename themselves to 127.0.0.1 (DNS rebinding) send their own Host header.
            if self.headers.get("Host", "") in hosts:
                return True
            self._json(403, {"error": "open the player at http://127.0.0.1"})
            return False

        def do_GET(self) -> None:
            if not self._local_host():
                return
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self._send(200, page.encode(), "text/html; charset=utf-8")
            elif path.startswith("/static/") and path[8:] in STATIC:
                body = (resources.files("longgame") / "web" / path[8:]).read_bytes()
                self._send(200, body, STATIC[path[8:]])
            elif path == "/api/state":
                if self._authorised():
                    with session.lock:
                        self._json(200, session.state())
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if not self._local_host() or not self._authorised():
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if not 0 <= length <= 10_000:
                    raise ValueError("request body too large")
                msg = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(msg, dict):
                    raise ValueError("the request body must be a JSON object")
                if self.path == "/api/step":
                    self._json(200, session.step(msg.get("action")))
                elif self.path == "/api/start-over":
                    self._json(200, session.start_over())
                else:
                    self._json(404, {"error": "not found"})
            except ValueError as e:
                self._json(400, {"error": str(e)})

    return Handler


def start_server(lifetime: Any = "practice-v0", port: int = 8765, fresh: bool = False,
                 save_dir: Optional[Path] = None) -> Tuple[ThreadingHTTPServer, str, Session]:
    """Start the player in a background thread. Returns (server, url, session); call server.shutdown() to stop."""
    from .lifetime import lifetimes
    source = None if isinstance(lifetime, str) and lifetime in lifetimes() else str(lifetime)
    session = Session(load_spec(lifetime), fresh=fresh, save_dir=save_dir, source=source)
    token = secrets.token_urlsafe(18)
    hosts: set = set()
    server = ThreadingHTTPServer(("127.0.0.1", port), _handler(session, token, hosts))
    bound = server.server_address[1]
    hosts.update({f"127.0.0.1:{bound}", f"localhost:{bound}"})
    url = f"http://127.0.0.1:{bound}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, url, session


def play_in_browser(lifetime: Any = "practice-v0", port: int = 8765, open_browser: bool = True,
                    fresh: bool = False) -> None:
    try:
        server, url, session = start_server(lifetime, port, fresh)
    except OSError:
        server, url, session = start_server(lifetime, 0, fresh)  # port busy: take any free one
    print(f"Long Game is running at {url}  (Ctrl+C to stop; progress is saved in {session.progress})", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print()
    finally:
        server.shutdown()
