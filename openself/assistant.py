"""Requests to an assistant, and the heartbeat that says one is listening.

The web app's "ask me about this" buttons store a request; `openself assistant watch`, run as a
background monitor by an assistant session (Claude Code or another), prints each new one and keeps
a heartbeat file fresh, so the web app can show whether an assistant is connected. The assistant
interviews the owner, writes the answers into the profile in the owner's words, and marks the
request done.

Requests and the heartbeat live in the profile's .git folder (openself/), so they are never
committed, encrypted or pushed. A profile without git keeps them in .openself-local/.
"""

import json
import os
import sys
import threading
import time

from . import model

STALE = 5  # seconds without a heartbeat before the web app says no assistant is connected
STATUSES = ("open", "done", "archived")
_lock = threading.Lock()


def folder(root):
    git = os.path.join(root, ".git")
    return os.path.join(git, "openself") if os.path.isdir(git) else os.path.join(root, ".openself-local")


def requests_file(root):
    return os.path.join(folder(root), "requests.json")


def heartbeat_file(root):
    return os.path.join(folder(root), "assistant.json")


def prompt(command):
    """What to tell an assistant so it connects: the same words for `make ai` and the web app."""
    return (f"Watch the OpenSelf web app for requests: run '{command}' as a background monitor for this whole "
            "session, start it again whenever it stops, and handle each request as AGENTS.md says "
            "(openself/SPEC.md: the owner's own words, never guesses).")


def load(root):
    try:
        with open(requests_file(root), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _store(root, items):
    os.makedirs(folder(root), exist_ok=True)
    tmp = requests_file(root) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, requests_file(root))


def add(root, entry="", comment="", quote=""):
    """Store a request about an entry ("" for the whole profile). The same open request again is
    not stored twice. Returns the request."""
    entry, comment, quote = entry.strip(), " ".join(comment.split())[:2000], " ".join(quote.split())[:1500]
    if entry and not model.find(root, entry):
        raise ValueError(f"no entry with id '{entry}'")
    with _lock:
        items = load(root)
        for i in items:
            if i.get("status") == "open" and (i.get("entry"), i.get("comment"), i.get("quote")) == (entry, comment, quote):
                return i
        item = {"n": max([i.get("n", 0) for i in items] + [0]) + 1, "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "entry": entry, "file": model.find(root, entry) if entry else "", "comment": comment, "quote": quote,
                "status": "open", "note": ""}
        items.append(item)
        _store(root, items)
    return item


def set_status(root, n, status, note=None):
    if status not in STATUSES:
        raise ValueError("status must be one of " + ", ".join(STATUSES))
    with _lock:
        items = load(root)
        for i in items:
            if i.get("n") == n:
                i["status"] = status
                if note is not None:
                    i["note"] = " ".join(note.split())[:2000]
                _store(root, items)
                return i
    raise ValueError(f"no request #{n}")


def state(root, now=None):
    """Whether a watcher is running (fresh heartbeat), since when, and the requests it has shown."""
    try:
        with open(heartbeat_file(root), encoding="utf-8") as f:
            beat = json.load(f)
        if (now or time.time()) - float(beat.get("beat", 0)) <= STALE:
            return {"connected": True, "since": beat.get("since", ""), "seen": [int(n) for n in beat.get("seen", [])]}
    except (OSError, ValueError, TypeError):
        pass
    return {"connected": False, "since": "", "seen": []}


def line(i, prefix=""):
    """One line per request: what a watching assistant sees as a notification."""
    where = f"entry={i['entry']} file={i.get('file') or '?'}" if i.get("entry") else "the whole profile"
    about = f" | about: {i['quote'][:200]}" if i.get("quote") else ""
    return (f"{prefix}REQUEST #{i['n']} {where}: {i.get('comment') or 'interview me about it'}{about} "
            f"(AGENTS.md; mark it done with: openself assistant done {i['n']} --note '<what changed>')")


def watch(root, out=None, interval=1.0, rounds=None):
    """Print every open request (those open at the start once, then each new one) and keep the
    heartbeat fresh until stopped. rounds limits the loop, for tests."""
    out = out or sys.stdout
    beat, me, started = heartbeat_file(root), os.getpid(), time.strftime("%Y-%m-%dT%H:%M:%S")
    seen, first, n = set(), True, 0
    try:
        while rounds is None or n < rounds:
            for i in load(root):
                if i.get("status") == "open" and i.get("n") not in seen:
                    seen.add(i.get("n"))
                    print(line(i, "ALREADY OPEN: " if first else ""), file=out, flush=True)
            first = False
            os.makedirs(folder(root), exist_ok=True)
            with open(beat + ".tmp", "w", encoding="utf-8") as f:
                json.dump({"pid": me, "since": started, "beat": time.time(), "seen": sorted(seen)}, f)
            os.replace(beat + ".tmp", beat)
            n += 1
            if rounds is None or n < rounds:
                time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            with open(beat, encoding="utf-8") as f:
                if json.load(f).get("pid") == me:
                    os.remove(beat)
        except (OSError, ValueError):
            pass
