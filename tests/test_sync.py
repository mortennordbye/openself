import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from openself import guard, history, model, sync, write  # noqa: E402
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
        self.assertTrue(sync.push(self.a)["unchanged"])  # nothing new: no new upload

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

    def start_profile(self, home):
        p = sync.profile_dir(home)
        shutil.copytree(os.path.join(ROOT, "example"), p)
        subprocess.run(["git", "init", "-q", "-b", "main", p], check=True)
        history.commit(p, history.message("profile", "start", "tool"))
        sync.keys_init(home)
        return p

    def test_vaults_round_trip_any_files(self):
        self.start_profile(self.a)
        v = sync.add_vault(self.a, "cv")
        self.assertEqual(sync.vaults(self.a), ["cv"])
        sync.add_vault(self.a, "cv")  # again: no second entry
        with open(os.path.join(self.a, ".openself", "config")) as f:
            self.assertEqual(f.read().count("vaults"), 1)
        with open(os.path.join(self.a, ".gitignore")) as f:
            self.assertIn("/cv/", f.read().splitlines())
        image = bytes(range(256)) * 300  # binary, like a photo or a PDF
        os.makedirs(os.path.join(v, "releases"))
        with open(os.path.join(v, "releases", "cv-v1.pdf"), "wb") as f:
            f.write(b"%PDF-1.7 Kari Hansen CV\n" + image)
        with open(os.path.join(v, "notes.md"), "w") as f:
            f.write("Applied to Vestkraft.\n")
        r = sync.push(self.a)
        self.assertEqual(sorted(r["encrypted"]), ["cv", "profile"])
        tracked = subprocess.run(["git", "-C", self.a, "ls-files"], capture_output=True, text=True).stdout.split()
        self.assertEqual(sorted(tracked), [".gitignore", ".openself/config", ".openself/recipients", "cv.age", "profile.age"])
        with open(os.path.join(self.a, "cv.age"), "rb") as f:
            blob = f.read()
        self.assertNotIn(b"Vestkraft", blob)
        self.assertNotIn(b"%PDF", blob)
        self.assertEqual(guard.check_history(self.a), [])
        self.assertTrue(sync.push(self.a)["unchanged"])

        # Only the vault changed: only cv.age is encrypted again.
        with open(os.path.join(v, "notes.md"), "a") as f:
            f.write("Interview booked.\n")
        r = sync.push(self.a)
        self.assertEqual(list(r["encrypted"]), ["cv"])
        self.assertEqual(len(history.log(v)), 3)  # created, first push, second push

        # A second machine gets every version of every file.
        b = os.path.join(self.tmp, "b")
        subprocess.run(["git", "clone", "-q", self.a, b], check=True)
        r = sync.pull(b, download=False)
        self.assertEqual((r["result"], r["vaults"]["cv"]["result"]), ("cloned", "cloned"))
        with open(os.path.join(b, "cv", "releases", "cv-v1.pdf"), "rb") as f:
            self.assertTrue(f.read().endswith(image))
        self.assertEqual(len(history.log(os.path.join(b, "cv"))), 3)
        self.assertEqual(sync.status(b)["vaults"]["cv"]["here"], True)

    def remote(self, home):
        bare = os.path.join(self.tmp, "remote.git")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", bare], check=True)
        subprocess.run(["git", "-C", home, "remote", "add", "origin", bare], check=True)
        return bare

    def test_push_uploads_a_snapshot_an_earlier_push_did_not_get_out(self):
        self.start_profile(self.a)
        bare = self.remote(self.a)
        subprocess.run(["git", "-C", self.a, "commit", "-q", "--allow-empty", "-m", "start"], check=True)
        subprocess.run(["git", "-C", self.a, "push", "-q", "-u", "origin", "main"], check=True)
        sync.push(self.a, upload=False)  # committed, but not uploaded (refused, offline)
        self.assertTrue(sync.unpublished(self.a))
        r = sync.push(self.a)
        self.assertTrue(r["unchanged"])  # nothing new to encrypt...
        self.assertTrue(r["uploaded"])  # ...but the waiting commit goes out
        self.assertFalse(sync.unpublished(self.a))
        mine = subprocess.run(["git", "-C", self.a, "rev-parse", "HEAD"], capture_output=True, text=True).stdout
        theirs = subprocess.run(["git", "-C", bare, "rev-parse", "main"], capture_output=True, text=True).stdout
        self.assertEqual(mine, theirs)

    def test_snapshot_branch_of_another_machine_is_not_replaced(self):
        self.start_profile(self.a)
        self.remote(self.a)
        sync.push(self.a, upload=False)
        subprocess.run(["git", "-C", self.a, "push", "-q", "-u", "origin", "main"], check=True)
        b = os.path.join(self.tmp, "b")
        subprocess.run(["git", "clone", "-q", os.path.join(self.tmp, "remote.git"), b], check=True)
        self.assertEqual(sync.snapshot_branch(self.a, "main"), ("", False))
        # Machine b pushes a snapshot branch that a does not have.
        subprocess.run(["git", "-C", b, "commit", "-q", "--allow-empty", "-m", "b's snapshot"], check=True)
        subprocess.run(["git", "-C", b, "push", "-q", "origin", f"HEAD:refs/heads/{sync.SNAPSHOT_BRANCH}"], check=True)
        theirs, foreign = sync.snapshot_branch(self.a, "main")
        self.assertTrue(theirs)
        self.assertTrue(foreign)
        # Once it is merged into main, a must pull before pushing again.
        subprocess.run(["git", "-C", b, "push", "-q", "origin", "HEAD:main"], check=True)
        with self.assertRaisesRegex(sync.SyncError, "pull"):
            sync.snapshot_branch(self.a, "main")
        # After pulling, the branch is a's own history: replacing it is fine.
        subprocess.run(["git", "-C", self.a, "pull", "-q", "origin", "main"], check=True)
        self.assertEqual(sync.snapshot_branch(self.a, "main")[1], False)

    def test_vault_not_here_is_left_alone(self):
        self.start_profile(self.a)
        v = sync.add_vault(self.a, "docs")
        with open(os.path.join(v, "a.txt"), "w") as f:
            f.write("x\n")
        sync.push(self.a)
        with open(os.path.join(self.a, "docs.age"), "rb") as f:
            before = f.read()
        shutil.rmtree(v)  # as on a machine that has not pulled it
        with open(os.path.join(sync.profile_dir(self.a), "person.md"), "a") as f:
            f.write("\n")
        r = sync.push(self.a)
        self.assertEqual(r["missing"], ["docs"])
        with open(os.path.join(self.a, "docs.age"), "rb") as f:
            self.assertEqual(f.read(), before)
        self.assertEqual(sync.pull(self.a, download=False)["vaults"]["docs"]["result"], "cloned")

    def test_bad_vault_names(self):
        for name in ("profile", "Cv", "../x", "a b", ""):
            with self.assertRaises(sync.SyncError):
                sync.add_vault(self.a, name)
        self.assertEqual(guard.vault_names("vaults = cv, docs,Bad, profile ../x\n# vaults = old"), ["cv", "docs"])

    def test_guard_refuses_plaintext_vault(self):
        self.start_profile(self.a)
        v = sync.add_vault(self.a, "cv")
        with open(os.path.join(v, "cv.html"), "w") as f:
            f.write("<p>hi</p>\n")
        sync.push(self.a, upload=False)
        subprocess.run(["git", "-C", self.a, "add", "-f", "cv"], check=True, capture_output=True)  # a vault is a repo: git links it
        bad = guard.check(self.a, "pre-commit")
        self.assertTrue(any(b.startswith("cv: the decrypted vault cv/") for b in bad), bad)
        subprocess.run(["git", "-C", self.a, "rm", "-q", "--cached", "-f", "cv"], check=True)
        with open(os.path.join(self.a, "cv.age"), "wb") as f:
            f.write(b"not encrypted at all\n")
        subprocess.run(["git", "-C", self.a, "add", "cv.age"], check=True)
        self.assertTrue(any(b.startswith("cv.age: not age-encrypted") for b in guard.check(self.a, "pre-commit")))

    def test_needs_key_and_recipients(self):
        os.environ["OPENSELF_IDENTITY"] = os.path.join(self.tmp, "missing")
        with self.assertRaises(Exception):
            sync.pull(self.a, download=False)
        with self.assertRaises(sync.SyncError):
            sync.push(self.a)

    def test_key_from_a_command(self):
        # A password manager's CLI prints the key; here `cat` stands in for `bw get notes ...`.
        key = os.environ.pop("OPENSELF_IDENTITY")
        os.environ["OPENSELF_IDENTITY_COMMAND"] = f"echo noise; cat {key}"
        self.assertTrue(sync.has_identity())
        secret, where = sync.find_identity()
        self.assertTrue(secret.startswith("AGE-SECRET-KEY"))
        self.assertEqual(secret.count("\n"), 1)
        self.assertIn("cat", where)
        p = sync.profile_dir(self.a)
        shutil.copytree(os.path.join(ROOT, "example"), p)
        subprocess.run(["git", "init", "-q", "-b", "main", p], check=True)
        history.commit(p, history.message("profile", "start", "tool"))
        sync.keys_init(self.a)
        sync.push(self.a, upload=False)
        shutil.rmtree(p)
        self.assertEqual(sync.pull(self.a, download=False)["result"], "cloned")

    def test_key_command_that_fails_says_why(self):
        os.environ.pop("OPENSELF_IDENTITY")
        os.environ["OPENSELF_IDENTITY_COMMAND"] = "bw-not-installed-here get notes x"
        self.assertTrue(sync.has_identity())  # configured; not run by the status check
        with self.assertRaises(sync.SyncError) as e:
            sync.identity()
        self.assertIn("could not get the key", str(e.exception))

    def test_pack_unpack_pads(self):
        packed = sync.pack(b"x" * 1000)
        self.assertEqual(len(packed) % sync.PAD, 0)
        self.assertEqual(sync.unpack(packed), b"x" * 1000)


if __name__ == "__main__":
    unittest.main()
