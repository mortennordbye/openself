import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from openself import assistant, history  # noqa: E402
from openself.web import api  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
           "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


class Assistant(unittest.TestCase):
    def setUp(self):
        env = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(env)))
        os.environ.update(GIT_ENV)  # the web API commits in this process; CI has no git identity
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root = os.path.join(self.tmp, "p")
        shutil.copytree(os.path.join(ROOT, "example"), self.root)
        env = dict(os.environ, **GIT_ENV)
        subprocess.run(["git", "init", "-q", self.root], check=True, env=env)
        subprocess.run(["git", "-C", self.root, "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", self.root, "commit", "-qm", "start"], check=True, env=env)

    def test_requests_live_outside_the_profile_history(self):
        i = assistant.add(self.root, "2021-04-vestkraft-skymigrering", "  hvor  mange servere? ", "rundt 60")
        self.assertEqual((i["n"], i["comment"], i["file"]), (1, "hvor mange servere?", "assignments/2021-04-vestkraft-skymigrering.md"))
        self.assertEqual(assistant.add(self.root, "2021-04-vestkraft-skymigrering", "hvor mange servere?", "rundt 60")["n"], 1)
        self.assertEqual(assistant.add(self.root, "", "intervju meg")["n"], 2)
        self.assertTrue(assistant.requests_file(self.root).startswith(os.path.join(self.root, ".git")))
        self.assertIsNone(history.commit(self.root, history.message("profile", "nothing", "tool")))  # nothing to commit
        with self.assertRaises(ValueError):
            assistant.add(self.root, "no-such-entry")
        assistant.set_status(self.root, 1, "done", "team size added")
        self.assertEqual([(x["n"], x["status"], x["note"]) for x in assistant.load(self.root)],
                         [(1, "done", "team size added"), (2, "open", "")])
        with self.assertRaises(ValueError):
            assistant.set_status(self.root, 1, "maybe")

    def test_watch_prints_requests_and_keeps_a_heartbeat(self):
        assistant.add(self.root, "person", "språk?")
        self.assertFalse(assistant.state(self.root)["connected"])
        out = io.StringIO()
        assistant.watch(self.root, out, interval=0, rounds=2)
        self.assertIn("ALREADY OPEN: REQUEST #1 entry=person file=person.md: språk?", out.getvalue())
        self.assertFalse(os.path.exists(assistant.heartbeat_file(self.root)))  # removed when it stops
        with open(assistant.heartbeat_file(self.root), "w") as f:
            json.dump({"pid": 1, "since": "x", "beat": time.time(), "seen": [1]}, f)
        self.assertEqual(assistant.state(self.root), {"connected": True, "since": "x", "seen": [1]})
        self.assertFalse(assistant.state(self.root, now=time.time() + assistant.STALE + 1)["connected"])

    def test_web_api(self):
        code, j = api.request(self.root, {"id": "person", "comment": "tittel?"})
        self.assertEqual((code, j["request"]["n"], j["connected"]), (200, 1, False))
        self.assertEqual(api.request(self.root, {"id": "../x"})[0], 400)
        code, s = api.assistant_state(self.root)
        self.assertEqual((s["open"], s["connected"], [x["n"] for x in s["items"]]), (1, False, [1]))
        self.assertEqual(api.requeststatus(self.root, {"n": 1, "status": "archived"})[0], 200)
        self.assertEqual(api.assistant_state(self.root)[1]["items"], [])
        self.assertEqual(api.requeststatus(self.root, {"n": "1", "status": "done"})[0], 400)

    def test_an_answer_in_the_web_app_reaches_the_assistant(self):
        rel = "assignments/2021-04-vestkraft-skymigrering.md"
        with open(os.path.join(self.root, rel), encoding="utf-8") as f:
            text = f.read()
        raw = next(ln for ln in text.split("\n") if "⚑ konflikt:" in ln or "⚑ conflict:" in ln)
        code, j = api.flag(self.root, {"id": "2021-04-vestkraft-skymigrering", "raw": raw, "answer": "60, den gamle CV-en tok feil",
                                       "base_sha": __import__("openself").model.sha(text)})
        self.assertEqual(code, 200, j)
        i = assistant.load(self.root)[-1]
        self.assertEqual((i["kind"], i["entry"], i["comment"]), ("answer", "2021-04-vestkraft-skymigrering", "60, den gamle CV-en tok feil"))
        self.assertIn("50 servere", i["quote"])
        self.assertTrue(assistant.line(i).startswith("ANSWER #1 entry=2021-04-vestkraft-skymigrering"))

    def test_cli(self):
        env = dict(os.environ, PYTHONPATH=ROOT)
        assistant.add(self.root, "person", "x")
        r = subprocess.run([sys.executable, "-m", "openself", "assistant", "done", "1", self.root, "--note", "fikset"],
                           env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = subprocess.run([sys.executable, "-m", "openself", "assistant", "list", self.root], env=env, capture_output=True, text=True)
        self.assertIn("done", r.stdout)
        self.assertIn("-> fikset", r.stdout)


if __name__ == "__main__":
    unittest.main()
