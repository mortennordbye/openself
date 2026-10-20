import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GIT_ENV = {"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
           "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           # No background auto-gc: it can delete pack files while a test removes its folder.
           "GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "gc.auto", "GIT_CONFIG_VALUE_0": "0",
           "GIT_CONFIG_KEY_1": "maintenance.auto", "GIT_CONFIG_VALUE_1": "false"}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Web(unittest.TestCase):
    def start(self, folder):
        port = free_port()
        env = dict(os.environ, PYTHONPATH=ROOT, **GIT_ENV)
        p = subprocess.Popen([sys.executable, "-m", "openself", "serve", folder, "--port", str(port), "--no-browser"],
                             env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(p.wait)
        self.addCleanup(p.kill)
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), 0.1).close()
                break
            except OSError:
                time.sleep(0.1)
        return port

    def call(self, port, path, body=None, headers=None):
        h = {"Host": f"127.0.0.1:{port}"}
        if body is not None:
            h.update({"X-OpenSelf": "1", "Content-Type": "application/json"})
        h.update(headers or {})
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", None if body is None else json.dumps(body).encode(), h)
        try:
            with urllib.request.urlopen(req) as r:
                data = r.read()
                return r.status, json.loads(data) if r.headers.get_content_type() == "application/json" else data
        except urllib.error.HTTPError as e:
            with e:
                data = e.read()
            return e.code, json.loads(data) if data.startswith(b"{") else data

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_profile_edit_and_guards(self):
        prof = os.path.join(self.tmp, "p")
        shutil.copytree(os.path.join(ROOT, "example"), prof)
        subprocess.run(["git", "init", "-q", prof], check=True)
        port = self.start(prof)
        code, page = self.call(port, "/")
        self.assertEqual(code, 200)
        self.assertIn(b"OpenSelfUI", page)
        self.assertEqual(self.call(port, "/static/app.js")[0], 200)
        self.assertEqual(self.call(port, "/static/../api.py")[0], 404)
        code, d = self.call(port, "/api/profile")
        self.assertTrue(d["ok"])
        e = next(x for x in d["entries"] if x["id"] == "person")
        self.assertEqual(self.call(port, "/api/save", {"id": "person"}, {"X-OpenSelf": "0"})[0], 403)
        self.assertEqual(self.call(port, "/api/save", {"id": "person"}, {"Host": "evil:80"})[0], 403)
        self.assertEqual(self.call(port, "/api/profile", headers={"Host": "evil:80"})[0], 403)
        code, j = self.call(port, "/api/save", {"id": "person", "meta": dict(e["meta"], title="Arkitekt"),
                                                "sections": e["sections"], "base_sha": e["sha"]})
        self.assertEqual(code, 200, j)
        code, j = self.call(port, "/api/save", {"id": "person", "meta": e["meta"], "sections": e["sections"], "base_sha": e["sha"]})
        self.assertEqual(code, 409)
        code, log = self.call(port, "/api/log?id=person")
        self.assertEqual(log["items"][0]["subject"], "person: edited [owner]")
        self.assertEqual(self.call(port, "/api/sync")[1]["home"], None)
        code, j = self.call(port, "/api/request", {"id": "person", "comment": "tittel?"})
        self.assertEqual((code, j["connected"]), (200, False))
        code, a = self.call(port, "/api/assistant")
        self.assertEqual((a["open"], a["home"], a["command"]), (1, "", ""))
        self.assertIn("openself assistant watch", a["prompt"])

    def test_first_run_init(self):
        folder = os.path.join(self.tmp, "new")
        port = self.start(folder)
        code, d = self.call(port, "/api/profile")
        self.assertEqual(code, 404)
        code, j = self.call(port, "/api/init", {"owner": "Kari", "languages": ["nb", "en"]})
        self.assertEqual(code, 200, j)
        code, d = self.call(port, "/api/profile")
        self.assertEqual((d["manifest"]["owner"], d["lang"]), ("Kari", "nb"))
        self.assertEqual(self.call(port, "/api/init", {"owner": "x"})[0], 409)


if __name__ == "__main__":
    unittest.main()
