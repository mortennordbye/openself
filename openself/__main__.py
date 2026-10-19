"""Command line: python3 -m openself <command> <profile folder> ...

  init DIR [--owner NAME] [--lang nb,en] [--no-git]   create an empty profile
  index DIR                                       rewrite INDEX.md and README.md
  lint DIR [--strict] [--quiet]                   check; exit 1 on errors (and warnings with --strict)
  fmt DIR [--check]                               rewrite every entry in canonical form
  new DIR TYPE key=value ... [--section id=text]  create an employment or assignment; prints its id
  remove DIR ID --reason TEXT                     move an entry to _removed/
  commit DIR ID WHAT [--actor owner|claude|tool]  reindex and commit as '<id>: <what> [<actor>]'
  log DIR [ID]                                    history of the profile or one entry
  show DIR ID REV                                 an entry as it was at a revision
  restore DIR ID REV [--actor ...]                bring an old version back as a new commit
  as-of DIR DATE                                  the index as the profile was on DATE (YYYY-MM-DD)

  serve [DIR] [--port 8765] [--no-browser]        the web app for a profile
  home [DIR]                                      make DIR a home: .openself/, profile/, .gitignore
  keys [HOME]                                     make this machine's key and add it to HOME's recipients
  push [HOME]                                     encrypt profile/ into profile.age, commit and push
  pull [HOME]                                     fetch profile.age, decrypt it into profile/

In a home folder (one with .openself/), DIR defaults to its profile/ and HOME to the home.
"""

import argparse
import sys

import os

from . import history, index, lint, model, sync, write


def main(argv=None):
    ap = argparse.ArgumentParser(prog="openself", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init"); p.add_argument("dir"); p.add_argument("--owner", default="")
    p.add_argument("--lang", default="en"); p.add_argument("--no-git", action="store_true")
    p = sub.add_parser("index"); p.add_argument("dir")
    p = sub.add_parser("lint"); p.add_argument("dir"); p.add_argument("--strict", action="store_true")
    p.add_argument("--quiet", action="store_true"); p.add_argument("--today")
    p = sub.add_parser("fmt"); p.add_argument("dir"); p.add_argument("--check", action="store_true")
    p = sub.add_parser("new"); p.add_argument("dir"); p.add_argument("type", choices=["employment", "assignment"])
    p.add_argument("fields", nargs="*", help="key=value; lists as key=a,b"); p.add_argument("--section", action="append", default=[])
    p = sub.add_parser("remove"); p.add_argument("dir"); p.add_argument("id"); p.add_argument("--reason", required=True)
    p = sub.add_parser("commit"); p.add_argument("dir"); p.add_argument("id"); p.add_argument("what")
    p.add_argument("--actor", default="claude", choices=history.ACTORS)
    p = sub.add_parser("log"); p.add_argument("dir"); p.add_argument("id", nargs="?")
    p = sub.add_parser("show"); p.add_argument("dir"); p.add_argument("id"); p.add_argument("rev")
    p = sub.add_parser("restore"); p.add_argument("dir"); p.add_argument("id"); p.add_argument("rev")
    p.add_argument("--actor", default="owner", choices=history.ACTORS)
    p = sub.add_parser("as-of"); p.add_argument("dir"); p.add_argument("date")
    p = sub.add_parser("serve"); p.add_argument("dir", nargs="?"); p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true")
    for name in ("home", "keys", "push", "pull"):
        sub.add_parser(name).add_argument("dir", nargs="?")
    a = ap.parse_args(argv)

    if a.cmd in ("serve", "keys", "push", "pull"):
        home = sync.find_home(a.dir or ".")
        try:
            if a.cmd == "serve":
                from .web.server import serve
                root = a.dir or (sync.profile_dir(home) if home else ".")
                serve(root, a.port, not a.no_browser, home if home and os.path.abspath(root) == sync.profile_dir(home) else None)
            elif not home:
                print("not in an OpenSelf home folder; run `openself home` first", file=sys.stderr)
                return 1
            elif a.cmd == "keys":
                pub, where, created = sync.keys_init(home)
                print(("created" if created else "found") + f" the key in {where}\npublic key added to {sync.recipients_file(home)}:\n{pub}")
                if created:
                    print("Back up the secret key now, for example in a password manager. Without it, profile.age cannot be read.")
            elif a.cmd == "push":
                r = sync.push(home)
                if r.get("unchanged"):
                    print("nothing changed since the last push")
                else:
                    print(f"profile.age: {r['size']} bytes" + (f", commit {r['commit']}" if r["commit"] else "") + (", pushed" if r["uploaded"] else ""))
            else:
                r = sync.pull(home)
                print(f"{r['result']} ({r['head']})")
        except sync.SyncError as e:
            print(e, file=sys.stderr)
            return 1
        return 0
    if a.cmd == "home":
        print(make_home(a.dir or "."))
        return 0

    if a.cmd == "init":
        write.init(a.dir, a.owner, [x.strip() for x in a.lang.split(",") if x.strip()], git=not a.no_git)
        print(f"profile ready in {a.dir}")
    elif a.cmd == "index":
        print("INDEX.md updated" if index.write_all(a.dir) else "INDEX.md already up to date")
    elif a.cmd == "lint":
        issues = lint.lint(model.load_profile(a.dir), today=a.today)
        for i in issues:
            if not (a.quiet and i.level == "prompt"):
                print(i)
        print(lint.summary(issues))
        if any(i.level == "error" or (a.strict and i.level == "warning") for i in issues):
            return 1
    elif a.cmd == "fmt":
        return fmt(a.dir, a.check)
    elif a.cmd == "new":
        fields = {}
        for kv in a.fields:
            k, _, v = kv.partition("=")
            fields[k] = [x.strip() for x in v.split(",") if x.strip()] if k in ("tech", "methods", "customers", "breaks", "sources") else v
        secs = dict(s.split("=", 1) for s in a.section)
        id_ = write.scaffold(a.dir, a.type, fields, secs)
        index.write_all(a.dir)
        print(id_)
    elif a.cmd == "remove":
        print(write.remove(a.dir, a.id, a.reason))
        index.write_all(a.dir)
    elif a.cmd == "commit":
        index.write_all(a.dir)
        print(history.commit(a.dir, history.message(a.id, a.what, a.actor)) or "nothing to commit")
    elif a.cmd == "log":
        tags = history.tags(a.dir)
        for c in history.log(a.dir, a.id):
            t = " (" + ", ".join(tags[c["rev"]]) + ")" if c["rev"] in tags else ""
            print(f"{c['short']}  {c['date'][:16].replace('T', ' ')}  {c['subject']}{t}")
    elif a.cmd == "show":
        print(history.show(a.dir, a.id, a.rev)[1], end="")
    elif a.cmd == "restore":
        print(history.restore(a.dir, a.id, a.rev, a.actor) or "already identical")
    elif a.cmd == "as-of":
        rev = history.rev_at(a.dir, a.date)
        if not rev:
            print(f"no version on or before {a.date}", file=sys.stderr)
            return 1
        print(f"<!-- as of {a.date}: {rev[:7]} -->")
        print(index.build_index(history.load_at(a.dir, rev)))
    return 0


HOME_GITIGNORE = """# The decrypted profile never goes in this repository; only profile.age does.
/profile/
.openself/pushed
.DS_Store
"""


def make_home(path):
    """Make path a home folder: .openself/, a .gitignore that keeps profile/ out, and git."""
    path = os.path.abspath(path)
    os.makedirs(os.path.join(path, ".openself"), exist_ok=True)
    rc = sync.recipients_file(path)
    if not os.path.exists(rc):
        with open(rc, "w", encoding="utf-8") as f:
            f.write("# age public keys that may decrypt profile.age, one per line (openself keys adds this machine's)\n")
    gi = os.path.join(path, ".gitignore")
    if not os.path.exists(gi):
        with open(gi, "w", encoding="utf-8") as f:
            f.write(HOME_GITIGNORE)
    if not os.path.isdir(os.path.join(path, ".git")):
        import subprocess
        subprocess.run(["git", "init", "-q", "-b", "main", path], check=True)
    return f"home ready in {path}; next: openself keys, then openself serve"


def fmt(root, check):
    """Rewrite every readable entry in canonical form; with check, only report which differ."""
    profile = model.load_profile(root)
    differ = []
    for e in list(profile.entries.values()) + list(profile.removed.values()):
        if e.error:
            continue
        canonical = write.render(e.meta, e.body, model.type_for(e.rel) if not e.removed else e.type)
        if canonical != e.text:
            differ.append(e.rel)
            if not check:
                write.write_atomic(f"{root}/{e.rel}", canonical)
    for rel in differ:
        print(("not canonical: " if check else "rewrote: ") + rel)
    return 1 if check and differ else 0


if __name__ == "__main__":
    sys.exit(main())
