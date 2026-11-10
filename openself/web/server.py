"""`python3 -m openself serve`: the OpenSelf web app for one profile, on 127.0.0.1 only.

In a home folder (one with .openself/, see openself.sync) it also offers key setup and the
encrypted push and pull.
"""

import errno
import json
import os
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .. import assistant, sync
from . import api

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}
MAX_BODY = 2_000_000


def sync_json(home):
    if not home:
        return 200, {"ok": True, "home": None}
    return 200, dict(sync.status(home), ok=True)


def sync_action(home, name):
    if not home:
        return 400, {"ok": False, "message": "not in an OpenSelf home folder (no .openself/)"}
    try:
        if name == "keys":
            pub, where, created = sync.keys_init(home)
            return 200, {"ok": True, "message": ("Key created in " if created else "Key found in ") + where, "public": pub}
        if name == "push":
            r = sync.push(home)
            if r.get("unchanged"):
                return 200, dict(r, message="Nothing changed since the last push")
            what = ", ".join(f"{n} ({b // 1024} KiB)" for n, b in r.get("encrypted", {}).items()) or "nothing new"
            return 200, dict(r, message=f"Encrypted {what}" + (" and pushed" if r["uploaded"] else "")
                          + (" as a pull request that merges once the guard passes" if r.get("pr") else ""))
        r = sync.pull(home)
        vs = "; ".join(f"{n}: {x['result']}" for n, x in r.get("vaults", {}).items())
        return 200, dict(r, message=r["result"] + (f" ({vs})" if vs else ""))
    except sync.SyncError as e:
        return 400, {"ok": False, "message": str(e)}


def make_handler(root, port, home):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def json(self, code, obj):
            self.send(code, json.dumps(obj).encode(), "application/json")

        def host_ok(self):
            bound = self.server.server_address[1]  # the real port, also when serve picked one
            return self.headers.get("Host", "") in (f"127.0.0.1:{bound}", f"localhost:{bound}")

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if not self.host_ok():
                return self.send(403, b"forbidden", "text/plain")
            if u.path in ("/", "/index.html"):
                return self.static("index.html")
            if u.path.startswith("/static/"):
                return self.static(u.path[len("/static/"):])
            name = u.path[len("/api/"):] if u.path.startswith("/api/") else ""
            if name == "sync":
                return self.json(*sync_json(home))
            fn = api.GET.get(name)
            if not fn:
                return self.send(404, b"not found", "text/plain")
            if name == "profile":
                code, body = fn(root)
                if code == 404:
                    body["path"] = os.path.abspath(root)
                return self.json(code, body)
            if name == "assistant":
                code, body = fn(root)
                # How to connect one: `make ai` in a home folder, else the watch command by hand.
                watch = "./self assistant watch" if home else f"python3 -m openself assistant watch {root}"
                body.update(home=home or "", command="make ai" if home else "", prompt=assistant.prompt(watch))
                return self.json(code, body)
            args = {"log": [q.get("id", "")], "show": [q.get("id", ""), q.get("rev", "")], "asof": [q.get("date", "")]}.get(name, [])
            self.json(*fn(root, *args))

        def static(self, rel):
            f = os.path.realpath(os.path.join(STATIC, rel))
            if not f.startswith(STATIC + os.sep) or not os.path.isfile(f):
                return self.send(404, b"not found", "text/plain")
            with open(f, "rb") as fh:
                self.send(200, fh.read(), TYPES.get(os.path.splitext(f)[1], "application/octet-stream"))

        def do_POST(self):
            # Only the page itself may act: a custom header (forces a CORS preflight) and a local Host.
            if self.headers.get("X-OpenSelf") != "1" or not self.host_ok():
                return self.send(403, b"forbidden", "text/plain")
            size = int(self.headers.get("Content-Length", "0") or 0)
            if size > MAX_BODY:
                return self.json(413, {"ok": False, "message": "too large"})
            try:
                data = json.loads(self.rfile.read(size) or b"{}")
            except ValueError:
                data = None
            if not isinstance(data, dict):
                return self.json(400, {"ok": False, "message": "bad request"})
            name = urlparse(self.path).path[len("/api/"):]
            if name in ("keys", "push", "pull"):
                return self.json(*sync_action(home, name))
            fn = api.POST.get(name)
            if not fn or not re.fullmatch(r"[a-z]+", name):
                return self.send(404, b"not found", "text/plain")
            self.json(*fn(root, data))
    return Handler


class PortInUse(Exception):
    pass


DEFAULT_PORT = 8765


def serve(root, port=None, open_browser=True, home=None, ready=None):
    """Serve the web app on `port`. With no port it uses 8765, or a free port when 8765 is
    busy. `ready` runs after the port is bound and before serving, so a password prompt there
    never happens for a server that cannot start."""
    root = os.path.abspath(root)
    chosen = port is not None
    port = DEFAULT_PORT if port is None else port
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(root, port, home))
    except OSError as e:
        if e.errno != errno.EADDRINUSE:
            raise
        if not chosen:
            srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(root, 0, home))
            print(f"port {port} is in use, so OpenSelf uses a free port", flush=True)
        else:
            raise PortInUse(f"port {port} is already in use by another program "
                            f"(see `lsof -nP -iTCP:{port} -sTCP:LISTEN`); stop it, use another "
                            f"port (--port {port + 1}), or leave out --port to get a free one") from None
    port = srv.server_address[1]
    if ready:
        try:
            ready()
        except BaseException:
            srv.server_close()
            raise
    url = f"http://127.0.0.1:{port}/"
    print(f"OpenSelf: {root}\n{url}  (Ctrl+C to stop)", flush=True)
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
