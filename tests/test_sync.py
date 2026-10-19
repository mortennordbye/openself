import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from openself import history, model, sync, write  # noqa: E402
from openself.__main__ import make_home  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
           "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           # No background auto-gc: it can delete pack files while a test removes its folder.
           "GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "gc.auto", "GIT_CONFIG_VALUE_0": "0",
           "GIT_CONFIG_KEY_1": "maintenance.auto", "GIT_CONFIG_VALUE_1": "false"}


@unittest.skipUnless(shutil.which("age") and shutil.which("age-keygen"), "age is not installed")
class Sync(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = dict(os.environ)
        key = os.path.join(self.tmp, "key.txt")
        with open(key, "w") as f:
            f.write(sync.new_key())
        os.environ.update(GIT_ENV, OPENSELF_IDENTITY=key)  # a throwaway key: the keychain is not touched
        self.a = os.path.join(self.tmp, "a")
        make_home(self.a)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env)
        shutil.rmtree(self.tmp)

    def test_push_pull_round_trip_keeps_history(self):
        pub, _, created = sync.keys_init(self.a)
        self.assertFalse(created)  # the key came from OPENSELF_IDENTITY
        self.assertIn(pub, sync.recipients(self.a))
        p = sync.profile_dir(self.a)
        shutil.copytree(os.path.join(ROOT, "example"), p)
        subprocess.run(["git", "init", "-q", "-b", "main", p], check=True)
        history.commit(p, history.message("profile", "start", "tool"))
        r = sync.push(self.a)
        self.assertTrue(r["commit"])
        self.assertEqual(os.path.getsize(os.path.join(self.a, "profile.age")) > 64 * 1024, True)
        with open(os.path.join(self.a, "profile.age"), "rb") as f:
            blob = f.read()
        self.assertNotIn(b"Vestkraft", blob)
        self.assertNotIn(b"assignments/", blob)
        tracked = subprocess.run(["git", "-C", self.a, "ls-files"], capture_output=True, text=True).stdout.split()
        self.assertEqual(sorted(tracked), [".gitignore", ".openself/recipients", "profile.age"])
        self.assertFalse(sync.status(self.a)["unpushed"])

        # A second machine: clone the home, pull, change, push; then the first pulls.
        b = os.path.join(self.tmp, "b")
        subprocess.run(["git", "clone", "-q", self.a, b], check=True)
        self.assertEqual(sync.pull(b, download=False)["result"], "cloned")
        pb = sync.profile_dir(b)
        self.assertEqual(len(history.log(pb)), 1)
        e = model.load_profile(pb).entries["person"]
        write.save(pb, "person", dict(e.meta, title="Arkitekt"), e.body, e.sha)
        history.commit(pb, history.message("person", "title", "owner"))
        sync.push(b, upload=False)
        subprocess.run(["git", "-C", self.a, "pull", "-q", b, "main"], check=True)
        self.assertEqual(sync.pull(self.a, download=False)["result"], "updated")
        self.assertEqual(model.load_profile(p).entries["person"].get("title"), "Arkitekt")
        self.assertIn("person: title [owner]", [c["subject"] for c in history.log(p)])

        # Diverged: both change without pulling.
        for home, title in ((self.a, "A"), (b, "B")):
            pp = sync.profile_dir(home)
            e = model.load_profile(pp).entries["person"]
            write.save(pp, "person", dict(e.meta, title=title), e.body, e.sha)
            history.commit(pp, history.message("person", title, "owner"))
        sync.push(b, upload=False)
        subprocess.run(["git", "-C", self.a, "fetch", "-q", b, "main"], check=True)
        subprocess.run(["git", "-C", self.a, "checkout", "-q", "FETCH_HEAD", "--", "profile.age"], check=True)
        with self.assertRaises(sync.SyncError):
            sync.pull(self.a, download=False)

    def test_needs_key_and_recipients(self):
        os.environ["OPENSELF_IDENTITY"] = os.path.join(self.tmp, "missing")
        with self.assertRaises(Exception):
            sync.pull(self.a, download=False)
        with self.assertRaises(sync.SyncError):
            sync.push(self.a)

    def test_pack_unpack_pads(self):
        packed = sync.pack(b"x" * 1000)
        self.assertEqual(len(packed) % sync.PAD, 0)
        self.assertEqual(sync.unpack(packed), b"x" * 1000)


if __name__ == "__main__":
    unittest.main()
