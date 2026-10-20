"""Checks a profile. Errors break the format, warnings are probably mistakes, and prompts are gaps
worth asking the owner about (they make up the interview list)."""

import os
import re
from dataclasses import dataclass
from functools import lru_cache

from . import index, model, schema

STALE_MONTHS = 18
GAP_MONTHS = 3
# A source cited inline, left from before the profile itself was the source.
INLINE_SOURCE = re.compile(r"\[(?:kilde|source)\s*:", re.IGNORECASE)


@dataclass
class Issue:
    level: str  # error | warning | prompt
    id: str
    field: str
    message: str

    def __str__(self):
        where = self.id + (f".{self.field}" if self.field else "")
        return f"{self.level:7} {where}: {self.message}"


@lru_cache(maxsize=None)
def tech_names(path=None):
    """(canonical names, {lowercase alias or name: canonical}) from tech-names.txt."""
    path = path or os.path.join(schema.HERE, "tech-names.txt")
    canon, alias = set(), {}
    if not os.path.exists(path):
        return frozenset(), {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):  # whole-line comments only: C# is a name
                continue
            name, _, rest = line.partition("|")
            name = name.strip()
            canon.add(name)
            alias[name.lower()] = name
            for a in rest.split(","):
                if a.strip():
                    alias[a.strip().lower()] = name
    return frozenset(canon), alias


def lint(profile, today=None, tech_path=None):
    today = today or model.today()
    now = model.month(today[:7])
    canon, alias = tech_names(tech_path)
    out = []

    def add(level, id_, field, msg):
        out.append(Issue(level, id_, field, msg))

    for rel, err in profile.errors:
        add("error", os.path.basename(rel)[:-3], "", err)

    if profile.manifest.get("format") != "openself":
        add("error", "openself.json", "format", "missing or not 'openself'")
    if profile.manifest.get("schema") != schema.SCHEMA_VERSION:
        add("error", "openself.json", "schema", f"this openself reads schema {schema.SCHEMA_VERSION}")
    langs = profile.manifest.get("languages")
    if not isinstance(langs, list) or not langs or not all(isinstance(x, str) and re.fullmatch(r"[a-z]{2}", x) for x in langs):
        add("error", "openself.json", "languages", "a list of two-letter language codes, the main one first")
    elif langs[0] not in schema.label_languages():
        add("warning", "openself.json", "languages", f"no labels for '{langs[0]}', so headings are read in English")

    for t in schema.SINGLETONS:
        if t not in profile.entries:
            add("warning", t, "", f"{t}.md is missing")

    employments = {e.id: e for e in profile.of_type("employment")}
    for e in list(profile.entries.values()) + list(profile.removed.values()):
        if e.error:
            continue
        check_entry(e, profile, employments, canon, alias, now, add)

    check_overlaps(profile, add)
    check_employment_overlaps(employments, add)
    check_gaps(employments, now, add)

    if index.stale(profile):
        add("warning", "INDEX", "", "INDEX.md is out of date; run openself index")
    order = {"error": 0, "warning": 1, "prompt": 2}
    return sorted(out, key=lambda i: (order[i.level], i.id, i.field))


def check_entry(e, profile, employments, canon, alias, now, add):
    t = e.type
    for field, msg in schema.validate(e.meta, t):
        add("error", e.id, field, msg)
    for what in model.retired(e.meta, e.body, t):
        add("warning", e.id, what if what in schema.RETIRED else "", f"{what} is no longer part of the format "
            "(the profile itself is the source; tools cite entry ids); run openself fmt")
    if e.meta.get("id") != e.id:
        add("error", e.id, "id", f"must equal the file name ({e.id})")
    if e.removed:
        if e.meta.get("status") != "removed":
            add("error", e.id, "status", "entries in _removed/ must have status: removed")
        return
    if e.meta.get("status") == "removed":
        add("error", e.id, "status", "status is removed, but the file is not in _removed/")

    fl, bad = model.flags(e.body)
    for line, text in bad:
        add("error", e.id, "", f"malformed flag on body line {line} (a flag is its own list item, "
                               f"'- ⚑ question: ...', with a known type): {text[:80]}")
    for f in fl:
        if f.open:
            add("prompt", e.id, "", f"{f.type}: {f.text}")

    secs = model.sections(e.body, t)
    for s in secs:
        if not s.known and s.id != "_intro":
            add("warning", e.id, "", f"unknown section heading '## {s.heading}' (allowed, but not one of the standard sections)")
    n = len(INLINE_SOURCE.findall(e.body))
    if n:
        add("warning", e.id, "", f"{n} inline source marker{'s' if n > 1 else ''} ('[kilde: ...]'); the profile is "
                                 "the source and history says who wrote what, so drop them")

    if t == "person":
        if not e.get("name"):
            add("warning", e.id, "name", "the person has no name")
        for k in ("title", "languages"):
            if not e.get(k) and not e.list(k):
                add("prompt", e.id, k, "not given")
        about = next((s for s in secs if s.id == "about"), None)
        if about is None or not about.text.strip():
            add("prompt", e.id, "", "no about text written")

    if t in ("employment", "assignment"):
        a, b = model.month(e.get("start")), model.month(e.get("end"), end=True)
        if e.get("start") and len(e.get("start")) == 4:
            add("prompt", e.id, "start", "only the year is known; ask for the month")
        if a is not None and b is not None and b < a:
            add("error", e.id, "end", "ends before it starts")
        if not e.get("end"):
            add("prompt", e.id, "end", "end is empty; give a month or 'ongoing'")
        for br in e.list("breaks"):
            x, _, y = br.partition("/")
            if model.month(x) is None or model.month(y) is None or model.month(y) < model.month(x):
                add("error", e.id, "breaks", f"bad break {br}")
            elif a is not None and b is not None and not (a <= model.month(x) and model.month(y) <= b):
                add("warning", e.id, "breaks", f"break {br} is outside the period")
        for name in e.list("tech"):
            if name not in canon:
                hint = alias.get(name.lower())
                add("warning", e.id, "tech", f"'{name}' is not a canonical name" + (f"; use '{hint}'" if hint else ""))
        quiet = [n for n in e.list("tech") if not mentioned(n, e.body, alias)]
        if quiet:
            add("prompt", e.id, "tech", "not mentioned in the text, so what was done with it is unknown: " + ", ".join(quiet))
        if e.get("confidence") == "needs-confirmation":
            add("prompt", e.id, "confidence", "needs confirmation from the owner")
        reviewed = model.month(e.get("last_reviewed")[:7]) if e.get("last_reviewed") else None
        if reviewed is not None and now is not None and now - reviewed > STALE_MONTHS:
            add("prompt", e.id, "last_reviewed", f"not reviewed in over {STALE_MONTHS} months")

    if t == "assignment":
        emp = employments.get(e.get("employment"))
        if e.get("employment") and emp is None:
            add("error", e.id, "employment", f"no employment with id '{e.get('employment')}'")
        elif emp is not None and model.months(e) and model.months(emp) and not model.months(e) <= model.months(emp):
            add("warning", e.id, "start", f"period reaches outside employment {emp.id} (breaks included)")
        if e.get("kind") != "internal":
            if e.get("customer_public") in ("", "unknown"):
                add("prompt", e.id, "customer_public", "may the customer be named?")
            if e.get("customer_public") in ("anonymised", "nda", "unknown") and not e.get("customer_alias"):
                add("prompt", e.id, "customer_alias", "how should the customer be described when not named?")
        if e.get("kind") == "portfolio" and not e.list("customers"):
            add("prompt", e.id, "customers", "a portfolio should list its customers")
        if e.get("kind") == "client" and not e.get("customer"):
            add("error", e.id, "customer", "a client assignment needs the customer")
        for k in ("role", "allocation", "team_size"):
            if not e.get(k):
                add("prompt", e.id, k, "not given")
        contribution = next((s for s in secs if s.id == "contribution"), None)
        if contribution is None or not contribution.text.strip():
            add("prompt", e.id, "", "no own contribution written")


def mentioned(name, text, alias):
    """Whether the text names the technology, by its canonical name or an alias, as a whole word."""
    words = {name.lower()} | {a for a, c in alias.items() if c == alias.get(name.lower(), name)}
    low = text.lower()
    # A version number may follow (RHEL9), a letter may not (Java is not JavaScript).
    return any(re.search(r"(?<![\w.])" + re.escape(w) + r"(?![^\W\d_])", low) for w in words)


def check_employment_overlaps(employments, add):
    """Employments in the same months (breaks left out): two jobs at once, or a missing break. A
    single shared month is a handover (one ends the month the other starts) and is not reported."""
    items = sorted((e for e in employments.values() if not e.error), key=lambda e: e.id)
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            both = sorted(model.months(a) & model.months(b))
            runs = [r for r in runs_of(both) if len(r) > 1]
            if runs:
                when = ", ".join(f"{model.ym(r[0])} to {model.ym(r[-1])}" for r in runs)
                add("prompt", a.id, "", f"overlaps {b.id} ({when}): two jobs at once, or a missing break?")


def runs_of(months):
    """Sorted month numbers split into runs of consecutive months."""
    out = []
    for m in months:
        if out and m == out[-1][-1] + 1:
            out[-1].append(m)
        else:
            out.append([m])
    return out


def check_overlaps(profile, add):
    """Assignments in the same months whose allocation adds up to more than 100%."""
    load = {}
    for e in profile.of_type("assignment"):
        if e.error or not e.get("allocation").isdigit():
            continue
        for m in model.months(e):
            load.setdefault(m, []).append((e.id, int(e.get("allocation"))))
    seen = set()
    for m in sorted(load):
        total = sum(p for _, p in load[m])
        ids = tuple(sorted(i for i, _ in load[m]))
        if total > 100 and ids not in seen:
            seen.add(ids)
            add("warning", ids[0], "allocation", f"{total}% in {model.ym(m)} together with {', '.join(ids[1:])}")


def check_gaps(employments, now, add):
    covered = set()
    for e in employments.values():
        if not e.error:
            covered |= model.months(e, with_breaks=True)  # leave is not a gap
    if not covered:
        return
    first, last = min(covered), max(max(covered), now or 0)
    gap = []
    for m in range(first, last + 1):
        if m in covered:
            if len(gap) > GAP_MONTHS:
                add("prompt", "employments", "", f"no employment {model.ym(gap[0])} to {model.ym(gap[-1])} ({len(gap)} months)")
            gap = []
        elif m < (now or last):
            gap.append(m)
    if len(gap) > GAP_MONTHS:
        add("prompt", "employments", "", f"no employment {model.ym(gap[0])} to {model.ym(gap[-1])} ({len(gap)} months)")


def summary(issues):
    counts = {k: sum(1 for i in issues if i.level == k) for k in ("error", "warning", "prompt")}
    return f"{counts['error']} errors, {counts['warning']} warnings, {counts['prompt']} prompts"

