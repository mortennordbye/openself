import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from openself import guard, history, sync  # noqa: E402
from openself.__main__ import make_home  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
           "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "gc.auto", "GIT_CONFIG_VALUE_0": "0",
           "GIT_CONFIG_KEY_1": "maintenance.auto", "GIT_CONFIG_VALUE_1": "false"}

# Stands in for the Bitwarden CLI: notes live in a JSON file, the vault is always "unlocked".
FAKE_BW = r'''#!/usr/bin/env python3
import base64, json, os, sys
db = os.environ["FAKE_BW_DB"]
notes = json.load(open(db)) if os.path.exists(db) else {}
a = sys.argv[1:]
if a[:1] == ["status"]: print(json.dumps({"status": "unlocked"}))
elif a[:2] == ["get", "notes"]:
    if a[2] not in notes: sys.exit(1)
    print(notes[a[2]])
elif a[:3] == ["get", "template", "item"]: print(json.dumps({"type": 1, "name": "", "notes": None}))
elif a[:1] == ["encode"]: print(base64.b64encode(sys.stdin.read().encode()).decode())
elif a[:2] == ["create", "item"]:
    item = json.loads(base64.b64decode(sys.stdin.read()))
    notes[item["name"]] = item["notes"]; json.dump(notes, open(db, "w")); print("{}")
elif a[:1] in (["sync"], ["unlock"]): print("session")
else: sys.exit(2)
'''


def git(repo, *args, check=True, **kw):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=check, **kw)


def stage_plaintext(home):
    """Put profile/person.md in the home's index, the way a stray copy or a careless add would."""
    blob = git(home, "hash-object", "-w", os.path.join(home, "profile", "person.md")).stdout.strip()
    git(home, "update-index", "--add", "--cacheinfo", f"100644,{blob},profile/person.md")


@unittest.skipUnless(shutil.which("age") and shutil.which("age-keygen"), "age is not installed")
class Guard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = dict(os.environ)
        self.key = os.path.join(self.tmp, "key.txt")
        with open(self.key, "w") as f:
            f.write(sync.new_key())
        os.environ.update(GIT_ENV, OPENSELF_IDENTITY=self.key)
        self.home = os.path.join(self.tmp, "home")
        make_home(self.home)
        sync.keys_init(self.home)
        p = sync.profile_dir(self.home)
        shutil.copytree(os.path.join(ROOT, "example"), p)
        git(p, "init", "-q", "-b", "main")
        history.commit(p, history.message("profile", "start", "tool"))
        self.remote = os.path.join(self.tmp, "remote.git")
        subprocess.run(["git", "init", "-q", "--bare", self.remote], check=True)
        git(self.home, "remote", "add", "origin", self.remote)
        sync.push(self.home, upload=False)  # installs the hooks
        git(self.home, "push", "-q", "-u", "origin", "HEAD")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env)
        shutil.rmtree(self.tmp)

    def test_a_clean_home_passes(self):
        self.assertEqual(guard.check(self.home), [])
        self.assertTrue(os.path.exists(os.path.join(self.home, ".git", "hooks", "pre-commit")))

    def test_hook_refuses_the_plaintext_profile(self):
        stage_plaintext(self.home)
        r = git(self.home, "commit", "-m", "oops", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("decrypted profile must never be committed", r.stderr)

    def test_hook_refuses_an_unencrypted_profile_age(self):
        with open(os.path.join(self.home, "profile.age"), "w") as f:
            f.write("---\nschema: 1\nid: person\n")
        git(self.home, "add", "profile.age")
        r = git(self.home, "commit", "-m", "oops", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not age-encrypted", r.stderr)

    def test_hook_refuses_junk_in_recipients_and_unknown_files(self):
        with open(os.path.join(self.home, ".openself", "recipients"), "a") as f:
            f.write("AGE-SECRET-KEY-1NOTAPUBLICKEY\n")
        with open(os.path.join(self.home, "notes.txt"), "w") as f:
            f.write("private\n")
        git(self.home, "add", ".openself/recipients", "notes.txt")
        r = git(self.home, "commit", "-m", "oops", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("only age public keys", r.stderr)
        self.assertIn("notes.txt: not allowed", r.stderr)

    def test_hook_refuses_the_profile_repository_itself(self):
        r = git(self.home, "add", "-f", "profile", check=False)
        r = git(self.home, "commit", "-m", "oops", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("profile: the decrypted profile must never be committed", r.stderr)

    def test_allow_list_extends(self):
        with open(os.path.join(self.home, ".openself", "allow"), "w") as f:
            f.write("docs/*\nprofile/sneaky.md\n")
        os.makedirs(os.path.join(self.home, "docs"))
        with open(os.path.join(self.home, "docs", "how.md"), "w") as f:
            f.write("how to\n")
        git(self.home, "add", ".openself/allow", "docs/how.md")
        self.assertEqual(guard.check(self.home, "pre-commit"), [])
        stage_plaintext(self.home)
        self.assertTrue(guard.check(self.home, "pre-commit"))  # profile/ can never be allowed

    def test_pre_push_refuses_what_slipped_past_a_commit(self):
        stage_plaintext(self.home)
        git(self.home, "commit", "-q", "--no-verify", "-m", "oops")
        r = git(self.home, "push", "-q", "origin", "HEAD", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("decrypted profile must never be committed", r.stderr)
        self.assertEqual(git(self.remote, "log", "--format=%s", "-1", "main").stdout.strip(), "Encrypted profile snapshot")

    def test_push_refuses_to_upload_when_the_home_is_unsafe(self):
        stage_plaintext(self.home)
        git(self.home, "commit", "-q", "--no-verify", "-m", "oops")
        p = sync.profile_dir(self.home)
        with open(os.path.join(p, "person.md"), "a") as f:
            f.write("\n")
        history.commit(p, history.message("person", "touch", "tool"))
        with self.assertRaises(sync.SyncError) as e:
            sync.push(self.home)
        self.assertIn("decrypted profile must never be committed", str(e.exception))  # the commit or the upload refuses

    def test_key_moves_to_bitwarden_and_is_read_back_from_it(self):
        bindir = os.path.join(self.tmp, "bin")
        os.makedirs(bindir)
        with open(os.path.join(bindir, "bw"), "w") as f:
            f.write(FAKE_BW)
        os.chmod(os.path.join(bindir, "bw"), 0o755)
        cfg = os.path.join(self.tmp, "identity-command")
        os.environ.update(PATH=bindir + os.pathsep + os.environ["PATH"], FAKE_BW_DB=os.path.join(self.tmp, "bw.json"),
                          BW_SESSION="session")
        with mock.patch.object(sync, "IDENTITY_COMMAND_FILE", cfg):
            pub, where, created = sync.to_bitwarden(self.home, interactive=False)
            self.assertTrue(created)
            self.assertEqual(where, self.key)
            self.assertTrue(sync.to_bitwarden(self.home, interactive=False)[2] is False)  # already there, same key
            del os.environ["OPENSELF_IDENTITY"]
            secret, where = sync.find_identity()
            self.assertIn("bw get notes", where)
            self.assertEqual(sync.public_key(secret), pub)
            shutil.rmtree(sync.profile_dir(self.home))
            self.assertEqual(sync.pull(self.home, download=False)["result"], "cloned")


if __name__ == "__main__":
    unittest.main()
