"""INDEX.md and README.md: generated overviews, so a reader (person or AI) sees the whole career
in a couple of thousand tokens before opening single entries."""

import os

from . import model, schema
from .write import write_atomic

TOP_TECH = 5


def customer_label(e, labels):
    """How the index shows the customer: the name only when it may be named, otherwise the alias."""
    kind = e.get("kind")
    if kind == "internal":
        return "(" + labels["enums"]["kind"]["internal"] + ")"
    if kind == "portfolio":
        names = e.list("customers")
        if e.get("customer_public") != "public":
            return e.get("customer_alias") or f"{len(names)} " + labels["fields"]["customers"].lower()
        return ", ".join(names) or e.get("customer")
    if e.get("customer_public") == "public":
        return e.get("customer") or "?"
    return e.get("customer_alias") or e.get("sector") or "?"


def cell(s):
    return " ".join(str(s).replace("|", "/").split())


def newest_first(entries):
    return sorted(entries, key=lambda e: (model.month(e.get("start")) or 0, e.id), reverse=True)


def tech_evidence(profile):
    """canonical tech -> (months, [assignment ids], [ongoing ids]) from the assignments' tech lists."""
    out = {}
    for e in profile.of_type("assignment"):
        # An ongoing assignment counts up to its last review, so the index does not change by itself
        # every month.
        until = (e.get("last_reviewed") or e.get("start"))[:7]
        for t in e.list("tech"):
            months, ids, ongoing = out.setdefault(t, (set(), [], []))
            months |= model.months(e, ongoing_until=until)
            ids.append(e.id)
            if e.get("end") == "ongoing":
                ongoing.append(e.id)
    return out


def open_items(profile):
    rows = []
    for e in sorted(profile.entries.values(), key=lambda e: e.rel):
        fl, _ = model.flags(e.body)
        for f in fl:
            if f.open:
                rows.append((e.id, f.type, f.text))
    return rows


def build_index(profile):
    lab = schema.labels(profile.lang)
    ix, fields = lab["index"], lab["fields"]
    ongoing = fields["ongoing"]
    out = [f"<!-- {ix['generated']} digest: {model.digest(profile)} -->", "",
           f"# {ix['title']}: {profile.manifest.get('owner', '')}".rstrip(": "), ""]

    person = profile.entries.get("person")
    if person and not person.error:
        bits = [person.get("title"), ", ".join(person.list("languages")),
                f"{fields['clearance']}: {person.get('clearance')}" if person.get("clearance") else ""]
        if any(bits):
            out += [" · ".join(b for b in bits if b), ""]

    out += [f"## {ix['employments']}", "",
            f"| {ix['id']} | {ix['period']} | {fields['employer']} | {fields['title']} |", "|---|---|---|---|"]
    for e in newest_first(profile.of_type("employment")):
        out.append(f"| {e.id} | {cell(model.period(e, ongoing))} | {cell(e.get('employer'))} | {cell(e.get('title'))} |")

    out += ["", f"## {ix['assignments']}", "",
            f"| {ix['id']} | {ix['period']} | {fields['employment']} | {fields['customer']} | {fields['role']} | % | {ix['top_tech']} |",
            "|---|---|---|---|---|---|---|"]
    for e in newest_first(profile.of_type("assignment")):
        tech = e.list("tech")
        more = f" +{len(tech) - TOP_TECH}" if len(tech) > TOP_TECH else ""
        out.append(f"| {e.id} | {cell(model.period(e, ongoing))} | {cell(e.get('employment'))} | "
                   f"{cell(customer_label(e, lab))} | {cell(e.get('role'))} | {cell(e.get('allocation'))} | "
                   f"{cell(', '.join(tech[:TOP_TECH]) + more)} |")

    out += ["", f"## {ix['tech']}", "", f"| {fields['tech']} | {ix['months']} | {ix['evidence']} |", "|---|---|---|"]
    ev = tech_evidence(profile)
    for t in sorted(ev, key=lambda t: (-len(ev[t][0]), t.lower())):
        months, ids, ongoing_ids = ev[t]
        out.append(f"| {cell(t)} | {len(months)}{'+' if ongoing_ids else ''} | {', '.join(sorted(ids, reverse=True))} |")
    out += ["", ix["months_note"]]

    out += ["", f"## {ix['open']}", ""]
    items = open_items(profile)
    out += [f"- {i} · {lab['flags'][t]}: {cell(text)}" for i, t, text in items] or [ix["none"]]

    out += ["", f"## {ix['removed']}", "", str(len(profile.removed)), ""]
    return "\n".join(out)


def build_readme(profile):
    owner = profile.manifest.get("owner") or "the owner"
    return f"""# OpenSelf profile: {owner}

This folder is an OpenSelf profile, schema {profile.manifest.get('schema', 1)}.
It is the only source of facts about {owner}'s career. Only {owner} adds or changes facts.

- Start with `INDEX.md` (generated): every employment and assignment, technology with evidence,
  and open questions.
- `person.md`, `certifications.md`, `education.md`: one file each.
- `employments/<id>.md`, `assignments/<id>.md`: one file per entry. The file name is the id; cite
  it as `<id>` or `<id>#<section>`.
- `_removed/`: removed entries, kept so their ids are never reused.

Specification: {profile.manifest.get('spec', 'profile-spec/SPEC.md')}
"""


def write_all(root):
    """Rewrite INDEX.md and README.md when their content changed. Returns True if either did."""
    profile = model.load_profile(root)
    changed = False
    for name, text in (("INDEX.md", build_index(profile)), ("README.md", build_readme(profile))):
        path = os.path.join(root, name)
        old = None
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                old = f.read()
        if old != text:
            write_atomic(path, text)
            changed = True
    return changed


def stale(profile):
    text = profile.generated.get("INDEX.md", "")
    return f"digest: {model.digest(profile)} " not in text.split("\n", 1)[0]
