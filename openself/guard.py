"""The guard on a home repository: nothing unencrypted is ever committed or pushed.

A home repository (SPEC section 7) may hold only the encrypted profile, the encrypted vaults (more
folders of any files, listed in .openself/config as `vaults = cv, docs`), the public keys and the
tools around them. `check` looks at what is staged (before a commit) or at the commits about to be
pushed, and refuses when:

- a file outside the allow list is there, and above all anything from profile/ or a vault folder
  (the plaintext);
- an allowed file carries text from the profile: the person's name, email or phone, an employer
  or a customer (only where the decrypted profile is on this machine);
- profile.age or a vault's <name>.age is not an age file, or it carries readable text;
- .openself/recipients holds anything but comments and age public keys.

Anything git cannot read counts as a problem, so the guard fails closed. `install` puts pre-commit
and pre-push hooks in the repository that run this check; push and pull install them on every run,
so a home is guarded from its first sync. More allowed paths can be listed, one glob per line, in
.openself/allow; each must start with a fixed folder or file name (docs/*, not *.md).
"""

import fnmatch
import os
import re
import subprocess

from . import model

ALLOWED = ["profile.age", ".openself/recipients", ".openself/allow", ".openself/config", ".gitignore", ".gitmodules", "openself",
           "self", "Makefile", "README.md", "AGENTS.md", "CLAUDE.md", "LICENSE", ".github/workflows/guard.yml"]
AGE_HEADER = b"age-encryption.org/v1\n"
PLAINTEXT = (b"OPENSELF-BUNDLE-1", b"\nschema: 1\n", b"---\nschema:", b"PACK\x00\x00\x00")
STANZA_BODY = re.compile(rb"[A-Za-z0-9+/]{0,64}")
READABLE = re.compile(rb"[\t\n\r\x20-\x7e]{48,}")  # 48 printable bytes in a row: never by chance in ciphertext
SENSITIVE = {"person": ("name", "email", "phone"), "employment": ("employer",),
             "assignment": ("customer", "customers")}
GITLINK = "160000"
VAULT_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")
NOT_VAULTS = ("profile", "openself", "self", "tools")
ZERO = "0" * 40
MARK = "openself guard"


def git(home, *args, data=False):
    r = subprocess.run(["git", "-C", home, *args], capture_output=True)
    if r.returncode != 0:
        return None
    return r.stdout if data else r.stdout.decode().strip()


def vault_names(config_text):
    """The vault folders a home declares: `vaults = cv, docs` in .openself/config. Names that are not
    plain lower-case folder names, or that clash with the home's own files, are ignored."""
    for line in (config_text or "").splitlines():
        k, sep, v = line.partition("=")
        if sep and k.strip() == "vaults" and not k.lstrip().startswith("#"):
            names = [n.strip() for n in v.replace(",", " ").split()]
            return [n for n in dict.fromkeys(names) if VAULT_NAME.fullmatch(n) and n not in NOT_VAULTS]
    return []


def allow_list(home, extra_text=None, vaults=()):
    """(patterns, problems): the built-in allow list plus .openself/allow, minus lines that are refused."""
    pats, bad = list(ALLOWED) + [f"{v}.age" for v in vaults], []
    text = extra_text
    if text is None and os.path.exists(os.path.join(home, ".openself", "allow")):
        with open(os.path.join(home, ".openself", "allow"), encoding="utf-8") as f:
            text = f.read()
    for n, line in enumerate((text or "").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("profile") or any(line == v or line.startswith(v + "/") for v in vaults):
            bad.append(f".openself/allow:{n}: {line.split('/')[0]}/ can never be allowed")
        elif any(c in line.split("/")[0] for c in "*?["):
            bad.append(f".openself/allow:{n}: a pattern must start with a fixed name (docs/*, not {line})")
        else:
            pats.append(line)
    return pats, bad


def age_problem(blob):
    """Why blob is not an age file with only ciphertext after its header, or None."""
    if not blob.startswith(AGE_HEADER):
        return "not age-encrypted (no age header)"
    end = blob.find(b"\n--- ")
    stop = blob.find(b"\n", end + 1) if end >= 0 else -1
    if stop < 0:
        return "not age-encrypted (the header does not end)"
    for line in blob[len(AGE_HEADER):end].split(b"\n"):
        if not line.startswith(b"-> ") and not STANZA_BODY.fullmatch(line):
            return "not age-encrypted (unexpected text in the header)"
    payload = blob[stop + 1:]
    if len(payload) < 32 or any(m in blob for m in PLAINTEXT) or READABLE.search(payload):
        return "contains readable data, not only ciphertext"
    return None


def needles(home):
    """(pattern, where) for the profile's identifying values: the person, employers, customers.
    Empty when the decrypted profile is not on this machine."""
    p = os.path.join(home, "profile")
    if not os.path.isfile(os.path.join(p, model.MANIFEST)):
        return []
    prof = model.load_profile(p)
    out, seen = [], set()
    for e in list(prof.entries.values()) + list(prof.removed.values()):
        for key in SENSITIVE.get(e.type, ()):
            for v in e.list(key):
                v = str(v).strip()
                if len(v) < 3 or v.lower() in seen:
                    continue
                seen.add(v.lower())
                flags = re.IGNORECASE if len(v) >= 5 else 0
                out.append((re.compile(r"(?<!\w)" + re.escape(v) + r"(?!\w)", flags), f"the {key} in {e.rel}"))
    return out


def problems_in(files, read, home, extra_allow=None, found=(), vaults=()):
    """Problems with {path: mode}, given read(path) -> bytes or None for their content."""
    pats, out = allow_list(home, extra_allow, vaults)
    encrypted = {"profile.age"} | {f"{v}.age" for v in vaults}
    for f in sorted(files):
        top = f.split("/", 1)[0]
        if top == "profile":
            out.append(f"{f}: the decrypted profile must never be committed")
        elif top in vaults:
            out.append(f"{f}: the decrypted vault {top}/ must never be committed")
        elif not any(fnmatch.fnmatch(f, p) for p in pats):
            out.append(f"{f}: not allowed in a home repository (add it to .openself/allow if it is safe)")
        elif f in encrypted:
            blob = read(f)
            why = "could not be read, so it cannot be checked" if blob is None else age_problem(blob)
            if why:
                out.append(f"{f}: {why}")
        elif files[f] != GITLINK:
            blob = read(f)
            if blob is None:
                out.append(f"{f}: could not be read, so it cannot be checked")
                continue
            text = blob.decode("utf-8", "replace")
            hits = sorted({where for pat, where in found if pat.search(text)})
            if hits:
                out.append(f"{f}: contains text from the profile ({', '.join(hits)})")
            if f == ".openself/recipients":
                for n, line in enumerate(text.splitlines(), 1):
                    s = line.strip()
                    if s and not s.startswith("#") and not s.startswith("age1"):
                        out.append(f".openself/recipients:{n}: only age public keys (age1...) and # comments belong here")
    return out


def listing(out):
    """{path: mode} from `git ls-files -s -z` or `git ls-tree -r -z` output, or None."""
    if out is None:
        return None
    files = {}
    for rec in out.split("\0"):
        if "\t" in rec:
            meta, path = rec.split("\t", 1)
            files[path] = meta.split()[0]
    return files


def check_staged(home, found=None):
    """What the next commit would contain: the index."""
    files = listing(git(home, "ls-files", "-s", "-z"))
    if files is None:
        return ["could not read the index, so it cannot be checked"]
    allow = git(home, "show", ":.openself/allow", data=True)
    config = git(home, "show", ":.openself/config", data=True)
    return problems_in(files, lambda p: git(home, "show", f":{p}", data=True), home,
                       allow.decode() if allow else "", needles(home) if found is None else found,
                       vault_names(config.decode() if config else ""))


def check_commit(home, rev, found=None):
    files = listing(git(home, "ls-tree", "-r", "-z", rev))
    if files is None:
        return [f"{rev[:7]}: could not read the commit, so it cannot be checked"]
    allow = git(home, "show", f"{rev}:.openself/allow", data=True)
    config = git(home, "show", f"{rev}:.openself/config", data=True)
    return [f"{rev[:7]}: {p}" for p in problems_in(files, lambda p: git(home, "show", f"{rev}:{p}", data=True), home,
                                                    allow.decode() if allow else "",
                                                    needles(home) if found is None else found,
                                                    vault_names(config.decode() if config else ""))]


def outgoing(home, stdin_text):
    """(commits a push would send, problems), from the lines git gives a pre-push hook. When the
    remote's tip is not here (a force push over commits not fetched), everything not yet on a
    remote is checked."""
    revs, bad = [], []
    for line in stdin_text.splitlines():
        parts = line.split()
        if len(parts) != 4 or parts[1] == ZERO:
            continue
        local, remote = parts[1], parts[3]
        out = git(home, "rev-list", f"{remote}..{local}") if remote != ZERO else None
        if out is None:
            out = git(home, "rev-list", local, "--not", "--remotes")
        if out is None:
            bad.append(f"{local[:7]}: could not list the commits to push, so they cannot be checked")
        else:
            revs += out.split()
    return revs, bad


def unpushed(home, found=None):
    """Problems in every commit on HEAD that no remote has yet: what a plain `git push` sends."""
    out = git(home, "rev-list", "HEAD", "--not", "--remotes")
    if out is None:
        return ["could not list the commits to push, so they cannot be checked"]
    found = needles(home) if found is None else found
    return [p for rev in out.split() for p in check_commit(home, rev, found)]


def check_history(home):
    """Problems in every commit reachable from HEAD (what CI runs on a fresh clone)."""
    out = git(home, "rev-list", "HEAD")
    if out is None:
        return ["could not list the history, so it cannot be checked"]
    found = needles(home)
    return [p for rev in out.split() for p in check_commit(home, rev, found)]


def check(home, hook=None, stdin_text=""):
    found = needles(home)
    if hook == "pre-push":
        revs, out = outgoing(home, stdin_text)
        for rev in revs:
            out += check_commit(home, rev, found)
        return out
    if hook == "pre-commit":
        return check_staged(home, found)
    head = git(home, "rev-parse", "HEAD")
    return check_staged(home, found) + (check_commit(home, head, found) if head else [])


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
