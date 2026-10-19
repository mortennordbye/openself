"""Versioning: the profile folder is its own git repository. Every change is a commit with the
subject '<id>: <what> [<actor>]', a restore is a new commit (history is never rewritten), and the
whole profile can be read as it was on any date."""

import difflib
import json
import os
import re
import subprocess

from . import model

ACTORS = ("owner", "claude", "tool")


def git(root, *args, check=True, input=None):
    r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, input=input)
    if check and r.returncode:
        raise RuntimeError(r.stderr.strip() or f"git {args[0]} failed")
    return r.stdout


def is_repo(root):
    return os.path.isdir(os.path.join(root, ".git"))


def message(id_, what, actor):
    return f"{id_}: {' '.join(what.split())} [{actor if actor in ACTORS else 'tool'}]"


def commit(root, msg):
    """Commit everything in the profile. Returns the new short hash, or None if nothing changed."""
    if not is_repo(root):
        return None
    git(root, "add", "-A")
    if not git(root, "status", "--porcelain"):
        return None
    git(root, "commit", "-q", "-m", msg)
    return git(root, "rev-parse", "--short", "HEAD").strip()


def tag(root, name, msg=None):
    git(root, "tag", "-a", name, "-m", msg or name)


def log(root, id_=None, limit=200):
    """Commits touching one entry (following moves to _removed/), or the whole profile."""
    args = ["log", f"-n{limit}", "--format=%H%x1f%h%x1f%aI%x1f%s"]
    if id_:
        rel = model.find(root, id_)
        if not rel:
            return []
        args += ["--follow", "--", rel]
    out = []
    for line in git(root, *args, check=False).splitlines():
        full, short, date, subject = line.split("\x1f", 3)
        m = re.search(r"\[(\w+)\]$", subject)
        out.append({"rev": full, "short": short, "date": date, "subject": subject,
                    "actor": m.group(1) if m else ""})
    return out


def tags(root):
    out = {}
    for line in git(root, "tag", "--format=%(objectname) %(*objectname) %(refname:short)", check=False).splitlines():
        parts = line.split()
        if len(parts) == 3:
            out.setdefault(parts[1], []).append(parts[2])
        elif len(parts) == 2:
            out.setdefault(parts[0], []).append(parts[1])
    return out


def files_at(root, rev):
    """{rel: text} of every profile file at a revision, plus the manifest."""
    names = [n for n in git(root, "ls-tree", "-r", "--name-only", rev).splitlines()
             if model.type_for(n) or n == model.MANIFEST]
    if not names:
        return {}
    r = subprocess.run(["git", "-C", root, "cat-file", "--batch"], capture_output=True,
                       input="".join(f"{rev}:{n}\n" for n in names).encode())
    data, out, pos = r.stdout, {}, 0
    for n in names:
        header_end = data.index(b"\n", pos)
        size = int(data[pos:header_end].split()[2])
        out[n] = data[header_end + 1:header_end + 1 + size].decode("utf-8")
        pos = header_end + 1 + size + 1
    return out


def load_at(root, rev):
    files = files_at(root, rev)
    manifest = json.loads(files.pop(model.MANIFEST, "{}") or "{}")
    return model.load_files(files, manifest, root)


def rev_at(root, date):
    """The last commit on or before a date (YYYY-MM-DD), or None."""
    out = git(root, "rev-list", "-1", f"--before={date} 23:59:59", "HEAD", check=False).strip()
    return out or None


def show(root, id_, rev):
    """(rel, text) of an entry at a revision, wherever it lived then."""
    for rel, text in files_at(root, rev).items():
        if os.path.basename(rel) == f"{id_}.md":
            return rel, text
    raise FileNotFoundError(f"{id_} did not exist at {rev[:7]}")


def restore(root, id_, rev, actor="owner"):
    """Put an entry back as it was at rev, as a new commit. Returns the new short hash."""
    old_rel, text = show(root, id_, rev)
    cur = model.find(root, id_)
    if cur and cur != old_rel:
        os.unlink(os.path.join(root, cur))
    from .write import write_atomic
    write_atomic(os.path.join(root, old_rel), text)
    from . import index
    index.write_all(root)
    short = git(root, "rev-parse", "--short", rev).strip()
    return commit(root, message(id_, f"restored to version {short}", actor))


def word_diff(a, b):
    """[[op, text]] where op is '=', '-' or '+', on word boundaries."""
    tok = re.compile(r"\s+|\w+|[^\w\s]")
    x, y = tok.findall(a), tok.findall(b)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, x, y, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(["=", "".join(x[i1:i2])])
        else:
            if i2 > i1:
                out.append(["-", "".join(x[i1:i2])])
            if j2 > j1:
                out.append(["+", "".join(y[j1:j2])])
    return out
