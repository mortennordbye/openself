"""`python3 -m openself serve`: the OpenSelf web app for one profile, on 127.0.0.1 only.

In a home folder (one with .openself/, see openself.sync) it also offers key setup and the
encrypted push and pull.
"""

import json
import os
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .. import sync
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
            return 200, dict(r, message=f"Encrypted ({r['size'] // 1024} KiB)" + (" and pushed" if r["uploaded"] else ""))
        r = sync.pull(home)
        return 200, dict(r, message=r["result"])
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
            return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

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


def serve(root, port=8765, open_browser=True, home=None):
    root = os.path.abspath(root)
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(root, port, home))
    url = f"http://127.0.0.1:{port}/"
    print(f"OpenSelf: {root}\n{url}  (Ctrl+C to stop)", flush=True)
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
