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
"""

import argparse
import sys

from . import history, index, lint, model, write


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
    a = ap.parse_args(argv)

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
