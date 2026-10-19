"""The guard on a home repository: nothing unencrypted is ever committed or pushed.

A home repository (SPEC section 7) may hold only the encrypted profile, the public keys and the
tools around them. `check` looks at what is staged (before a commit) or at the commits about to be
pushed, and refuses when:

- a file outside the allow list is there, and above all anything from profile/ (the plaintext);
- profile.age is not age ciphertext, or it carries readable profile text;
- .openself/recipients holds anything but comments and age public keys.

`install` puts pre-commit and pre-push hooks in the repository that run this check; push and pull
install them on every run, so a home is guarded from its first sync. More allowed paths can be
listed, one glob per line, in .openself/allow.
"""

import fnmatch
import os
import subprocess

ALLOWED = ["profile.age", ".openself/recipients", ".openself/allow", ".gitignore", ".gitmodules", "openself",
           "self", "Makefile", "README.md", "AGENTS.md", "CLAUDE.md", "LICENSE"]
AGE_HEADER = b"age-encryption.org/v1\n"
PLAINTEXT = (b"OPENSELF-BUNDLE-1", b"\nschema: 1\n", b"---\nschema:", b"PACK\x00\x00\x00")
ZERO = "0" * 40
MARK = "openself guard"


def git(home, *args, data=False):
    r = subprocess.run(["git", "-C", home, *args], capture_output=True)
    if r.returncode != 0:
        return None
    return r.stdout if data else r.stdout.decode().strip()


def allow_list(home, extra_text=None):
    pats = list(ALLOWED)
    text = extra_text
    if text is None and os.path.exists(os.path.join(home, ".openself", "allow")):
        with open(os.path.join(home, ".openself", "allow"), encoding="utf-8") as f:
            text = f.read()
    for line in (text or "").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("profile"):
            pats.append(line)
    return pats


def problems_in(files, read, home, extra_allow=None):
    """Problems with a set of paths, given read(path) -> bytes or None for their content."""
    out = []
    pats = allow_list(home, extra_allow)
    for f in sorted(files):
        if f == "profile" or f.startswith("profile/"):
            out.append(f"{f}: the decrypted profile must never be committed")
        elif not any(fnmatch.fnmatch(f, p) for p in pats):
            out.append(f"{f}: not allowed in a home repository (add it to .openself/allow if it is safe)")
    if "profile.age" in files:
        blob = read("profile.age") or b""
        if not blob.startswith(AGE_HEADER):
            out.append("profile.age: not age-encrypted (no age header)")
        elif any(m in blob for m in PLAINTEXT):
            out.append("profile.age: contains readable profile data")
    if ".openself/recipients" in files:
        for n, line in enumerate((read(".openself/recipients") or b"").decode("utf-8", "replace").splitlines(), 1):
            s = line.strip()
            if s and not s.startswith("#") and not s.startswith("age1"):
                out.append(f".openself/recipients:{n}: only age public keys (age1...) and # comments belong here")
    return out


def check_staged(home):
    """What the next commit would contain: the index."""
    files = set((git(home, "ls-files", "-z") or "").split("\0")) - {""}
    allow = git(home, "show", ":.openself/allow", data=True)
    return problems_in(files, lambda p: git(home, "show", f":{p}", data=True), home,
                       allow.decode() if allow else "")


def check_commit(home, rev):
    files = set((git(home, "ls-tree", "-r", "-z", "--name-only", rev) or "").split("\0")) - {""}
    allow = git(home, "show", f"{rev}:.openself/allow", data=True)
    return [f"{rev[:7]}: {p}" for p in problems_in(files, lambda p: git(home, "show", f"{rev}:{p}", data=True), home,
                                                    allow.decode() if allow else "")]


def outgoing(home, stdin_text):
    """The commits a push would send, from the lines git gives a pre-push hook."""
    revs = []
    for line in stdin_text.splitlines():
        parts = line.split()
        if len(parts) != 4 or parts[1] == ZERO:
            continue
        local, remote = parts[1], parts[3]
        rng = [local, "--not", "--remotes"] if remote == ZERO else [f"{remote}..{local}"]
        revs += (git(home, "rev-list", *rng) or "").split()
    return revs


def check(home, hook=None, stdin_text=""):
    if hook == "pre-push":
        out = []
        for rev in outgoing(home, stdin_text):
            out += check_commit(home, rev)
        return out
    if hook == "pre-commit":
        return check_staged(home)
    head = git(home, "rev-parse", "HEAD")
    return check_staged(home) + (check_commit(home, head) if head else [])


HOOK = """#!/bin/sh
# {mark}: refuses a commit or push that would publish anything unencrypted. Installed by openself;
# reinstalled on every push and pull.
root=$(git rev-parse --show-toplevel)
PYTHONPATH="$root/openself:{pkg}" exec python3 -m openself guard --hook {name} "$root"
"""


def install(home):
    """Put the guard hooks in place. A hook someone else wrote is left alone and reported."""
    hooks = git(home, "rev-parse", "--git-path", "hooks")
    if hooks is None:
        return []
    hooks = hooks if os.path.isabs(hooks) else os.path.join(home, hooks)
    os.makedirs(hooks, exist_ok=True)
    pkg = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    skipped = []
    for name in ("pre-commit", "pre-push"):
        path = os.path.join(hooks, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8", errors="replace") as f:
                if MARK not in f.read():
                    skipped.append(path)
                    continue
        with open(path, "w", encoding="utf-8") as f:
            f.write(HOOK.format(mark=MARK, pkg=pkg, name=name))
        os.chmod(path, 0o755)
    return skipped
