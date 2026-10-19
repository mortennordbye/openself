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
        branch = git(self.home, "symbolic-ref", "HEAD").stdout.strip()
        git(self.remote, "symbolic-ref", "HEAD", branch)  # so clones check out the home's branch

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
            f.write("docs/*\n")
        os.makedirs(os.path.join(self.home, "docs"))
        with open(os.path.join(self.home, "docs", "how.md"), "w") as f:
            f.write("how to\n")
        git(self.home, "add", ".openself/allow", "docs/how.md")
        self.assertEqual(guard.check(self.home, "pre-commit"), [])
        stage_plaintext(self.home)
        self.assertTrue(guard.check(self.home, "pre-commit"))  # profile/ can never be allowed

    def test_allow_list_refuses_profile_and_wildcards(self):
        with open(os.path.join(self.home, ".openself", "allow"), "w") as f:
            f.write("profile/sneaky.md\n*\n*.md\n")
        with open(os.path.join(self.home, "dump.md"), "w") as f:
            f.write("anything\n")
        git(self.home, "add", ".openself/allow", "dump.md")
        bad = guard.check(self.home, "pre-commit")
        self.assertIn(".openself/allow:1: profile/ can never be allowed", bad)
        self.assertTrue(any(b.startswith(".openself/allow:2: a pattern must start with a fixed name") for b in bad))
        self.assertTrue(any(b.startswith(".openself/allow:3:") for b in bad))
        self.assertTrue(any(b.startswith("dump.md: not allowed") for b in bad))

    def test_an_allowed_file_with_profile_text_is_refused(self):
        with open(os.path.join(self.home, "README.md"), "w") as f:
            f.write("Notes: Ola Eksempel worked at Eksempel Konsulent AS.\n")
        git(self.home, "add", "README.md")
        r = git(self.home, "commit", "-m", "readme", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("README.md: contains text from the profile", r.stderr)
        self.assertIn("the name in person.md", r.stderr)
        self.assertNotIn("Ola Eksempel", r.stderr)  # says where, never repeats the text

    def test_profile_age_with_text_after_the_header_is_refused(self):
        with open(os.path.join(self.home, "profile.age"), "wb") as f:
            f.write(b"age-encryption.org/v1\n-> X25519 abc\nAAAA\n--- mac\n" + b"plain words about a person " * 4)
        git(self.home, "add", "profile.age")
        self.assertIn("profile.age: contains readable data, not only ciphertext", guard.check(self.home, "pre-commit"))
        with open(os.path.join(self.home, "profile.age"), "wb") as f:
            f.write(b"age-encryption.org/v1\nname: Ola\n")
        git(self.home, "add", "profile.age")
        self.assertTrue(any("not age-encrypted" in b for b in guard.check(self.home, "pre-commit")))

    def test_pre_push_refuses_what_slipped_past_a_commit(self):
        stage_plaintext(self.home)
        git(self.home, "commit", "-q", "--no-verify", "-m", "oops")
        r = git(self.home, "push", "-q", "origin", "HEAD", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("decrypted profile must never be committed", r.stderr)
        self.assertEqual(git(self.remote, "log", "--format=%s", "-1", "main").stdout.strip(), "Encrypted profile snapshot")

    def test_pre_push_checks_a_force_push_over_commits_not_fetched(self):
        other = os.path.join(self.tmp, "other")
        subprocess.run(["git", "clone", "-q", self.remote, other], check=True)
        with open(os.path.join(other, "README.md"), "w") as f:
            f.write("hello\n")
        git(other, "add", "README.md")
        git(other, "commit", "-q", "--no-verify", "-m", "readme")
        git(other, "push", "-q", "--no-verify", "origin", "HEAD")
        with open(os.path.join(self.home, "leak.txt"), "w") as f:
            f.write("private\n")
        git(self.home, "add", "leak.txt")
        git(self.home, "commit", "-q", "--no-verify", "-m", "leak")
        r = git(self.home, "push", "-q", "-f", "origin", "HEAD", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("leak.txt: not allowed", r.stderr)

    def test_push_checks_every_outgoing_commit_not_just_the_last(self):
        with open(os.path.join(self.home, "leak.txt"), "w") as f:
            f.write("private\n")
        git(self.home, "add", "leak.txt")
        git(self.home, "commit", "-q", "--no-verify", "-m", "leak")
        git(self.home, "rm", "-q", "leak.txt")
        git(self.home, "commit", "-q", "--no-verify", "-m", "gone again")
        for name in ("pre-commit", "pre-push"):
            os.remove(os.path.join(self.home, ".git", "hooks", name))  # as if the hooks were never there
        self.touch_profile()
        with self.assertRaises(sync.SyncError) as e:
            sync.push(self.home)
        self.assertIn("leak.txt: not allowed", str(e.exception))
        self.assertNotIn("leak", git(self.remote, "log", "--format=%s", "HEAD").stdout)

    def test_push_refuses_when_another_hook_is_in_the_way(self):
        with open(os.path.join(self.home, ".git", "hooks", "pre-push"), "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        self.touch_profile()
        with self.assertRaises(sync.SyncError) as e:
            sync.push(self.home)
        self.assertIn("another tool's hook is in the way", str(e.exception))

    def test_push_commits_only_its_own_files(self):
        with open(os.path.join(self.home, "README.md"), "w") as f:
            f.write("staged, not meant for the snapshot\n")
        git(self.home, "add", "README.md")
        self.touch_profile()
        self.assertTrue(sync.push(self.home)["uploaded"])
        self.assertEqual(git(self.remote, "ls-tree", "--name-only", "HEAD", "README.md").stdout, "")
        self.assertIn("README.md", git(self.home, "diff", "--cached", "--name-only").stdout)  # still staged, still yours

    def test_a_recipient_that_arrives_with_a_pull_needs_approval(self):
        other = os.path.join(self.tmp, "other")
        subprocess.run(["git", "clone", "-q", self.remote, other], check=True)
        stranger = sync.public_key(sync.new_key())
        with open(os.path.join(other, ".openself", "recipients"), "a") as f:
            f.write("# key added 2026-10-19\n" + stranger + "\n")
        git(other, "commit", "-q", "--no-verify", "-am", "a key")
        git(other, "push", "-q", "--no-verify", "origin", "HEAD")
        sync.pull(self.home)
        self.touch_profile()
        with self.assertRaises(sync.SyncError) as e:
            sync.push(self.home)
        self.assertIn("keys this machine has not approved", str(e.exception))
        self.assertIn(sync.short_key(stranger), str(e.exception))
        self.assertEqual(sync.trust(self.home, [stranger]), [stranger])
        self.assertTrue(sync.push(self.home)["uploaded"])

    def test_history_check_finds_an_old_leak(self):
        self.assertEqual(guard.check_history(self.home), [])
        stage_plaintext(self.home)
        git(self.home, "commit", "-q", "--no-verify", "-m", "oops")
        git(self.home, "rm", "-q", "--cached", "profile/person.md")
        git(self.home, "commit", "-q", "--no-verify", "-m", "undo")
        self.assertTrue(any("decrypted profile must never be committed" in b for b in guard.check_history(self.home)))

    def test_push_through_a_pull_request(self):
        bindir = os.path.join(self.tmp, "bin")
        os.makedirs(bindir)
        log = os.path.join(self.tmp, "gh.log")
        with open(os.path.join(bindir, "gh"), "w") as f:  # stands in for the GitHub CLI
            f.write(f"""#!/bin/sh
echo "$*" >> {log}
case "$1 $2" in "pr create") echo https://github.com/o/r/pull/1;; esac
""")
        os.chmod(os.path.join(bindir, "gh"), 0o755)
        os.environ["PATH"] = bindir + os.pathsep + os.environ["PATH"]
        with open(os.path.join(self.home, ".openself", "config"), "w") as f:
            f.write("# how push uploads\npush = pull-request\n")
        main_before = git(self.remote, "rev-parse", "HEAD").stdout
        self.touch_profile()
        r = sync.push(self.home)
        self.assertEqual(r["pr"], "https://github.com/o/r/pull/1")
        self.assertEqual(git(self.remote, "rev-parse", "HEAD").stdout, main_before)  # main is left to GitHub
        self.assertEqual(git(self.remote, "rev-parse", sync.SNAPSHOT_BRANCH).stdout.strip(),
                         git(self.home, "rev-parse", "HEAD").stdout.strip())
        with open(log) as f:
            calls = f.read().splitlines()
        self.assertTrue(calls[1].startswith("pr create --base "))
        self.assertEqual(calls[2], "pr merge https://github.com/o/r/pull/1 --auto --merge")

    def touch_profile(self):
        p = sync.profile_dir(self.home)
        with open(os.path.join(p, "person.md"), "a") as f:
            f.write("\n")
        history.commit(p, history.message("person", "touch", "tool"))

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
