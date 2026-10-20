"""The public view of a profile: everything a tool may show to others, and nothing more (SPEC
section 8). A CV, a portfolio site or a form reads this instead of the profile, so they all leave
out the same things:

- assignments with an `nda` customer,
- customer names the profile does not allow (`customer_public`; the alias or sector is used), or
  every customer name when the output hides them (`names=False`, for a public website),
- the private `reference` section, the owner's own words, the flags and sections no tool writes from,
- the text of an entry with an open `omit` wish (its title, period and technology stay),
- removed entries (_removed/).

Each entry keeps its `id`, for citing `<id>#<section>` in local tools, and gets a `slug` that is safe
to put on a public page: an id holds the customer's name, which an anonymised entry must not show.
`confidence` is passed on so a tool can decide what to say about entries the owner has not confirmed.
The result is plain JSON data (`openself export DIR`).
"""

import re

from . import index, model, schema

SECTIONS = {"person": ("about",), "employment": ("summary",),
            "assignment": ("summary", "challenge", "contribution", "outcome")}
PERSON = ("name", "title", "location", "languages", "email", "phone", "linkedin", "github", "links")
EMPLOYMENT = ("employer", "title", "title_en", "location", "employment_type", "start", "end", "breaks", "tech")
ASSIGNMENT = ("kind", "employment", "sector", "role", "role_en", "start", "end", "breaks", "allocation",
              "team_size", "tech", "methods")
LISTS = {"languages", "links", "breaks", "tech", "methods"}
CERT_COLUMNS = ("name", "issuer", "date", "expires")
EDU_COLUMNS = ("degree", "school", "from", "to")


def omitted(e):
    """The standing omit wishes on an entry (not resolved)."""
    return [f.text for f in model.flags(e.body)[0] if f.type == "omit" and not f.resolved]


def public(e):
    """True when an entry may be shown at all."""
    return not (e.type == "assignment" and e.get("customer_public") == "nda")


def text_sections(e):
    """[{id, text}] of the exportable sections, in profile order, without flag lines. None when the
    owner asked to leave the text out."""
    if omitted(e):
        return []
    out = []
    for s in model.sections(e.body, e.type):
        if s.id in SECTIONS.get(e.type, ()):
            text = "\n".join(ln for ln in s.text.split("\n") if "⚑" not in ln).strip("\n")
            if text.strip():
                out.append({"id": s.id, "text": text})
    return out


def fields(e, names):
    return {k: (e.list(k) if k in LISTS else e.get(k)) for k in names}


def customer(e, labels, names=True):
    """The customer as it may be shown, or "" (internal work, or nothing allowed). Without names,
    never the real name: the alias, else the sector (or the number of customers in a portfolio)."""
    if e.get("kind") == "internal":
        return ""
    if not names:
        n = len(e.list("customers"))
        if e.get("kind") == "portfolio":
            return e.get("customer_alias") or (f"{n} " + labels["fields"]["customers"].lower() if n else "")
        return e.get("customer_alias") or e.get("sector") or ""
    label = index.customer_label(e, labels)
    return "" if label == "?" else label


def named(e, names=True):
    """True when the entry's id may be shown (it names nobody the output keeps hidden)."""
    return e.type != "assignment" or e.get("kind") == "internal" or (names and e.get("customer_public") == "public")


def slugs(entries, names=True):
    """id -> a slug for public pages: the id itself, or the start and role when the id would name a
    customer the profile keeps hidden."""
    out, taken = {}, set()
    for e in sorted(entries, key=lambda e: e.id):
        if named(e, names):
            out[e.id] = e.id
            taken.add(e.id)
    for e in sorted(entries, key=lambda e: e.id):
        if e.id in out:
            continue
        role = (e.get("role_en") or e.get("role") or e.type).lower()
        role = role.replace("æ", "ae").replace("ø", "o").replace("å", "a")
        base = "-".join(x for x in (e.get("start"), model.slug_heading(role)) if x)
        slug, n = base, 2
        while slug in taken:
            slug, n = f"{base}-{n}", n + 1
        out[e.id] = slug
        taken.add(slug)
    return out


def item(e, slug, names):
    return {"id": e.id, "slug": slug, "confidence": e.get("confidence"), "omit": bool(omitted(e)),
            **fields(e, names), "sections": text_sections(e)}


def table(e, columns):
    if not e or omitted(e):
        return []
    rows = [r for r in model.parse_table(e.body) if r and r[0].strip()]
    return [dict(zip(columns, (r + [""] * len(columns))[:len(columns)])) for r in rows]


def public_view(profile, names=True, lang=None):
    """The profile as it may be shown to others, as plain data. names=False never shows a real
    customer name, only the alias or sector (a public website). lang picks the language of the few
    generated words (such as "3 customers"); the default is the profile's."""
    labels = schema.labels(lang or profile.lang)
    jobs = index.newest_first(profile.of_type("employment"))
    work = [e for e in index.newest_first(profile.of_type("assignment")) if public(e)]
    slug = slugs(jobs + work, names)
    person = profile.entries.get("person")

    assignments = []
    for e in work:
        a = item(e, slug[e.id], ASSIGNMENT)
        a["customer"] = customer(e, labels, names)
        if a["employment"] not in slug:
            a["employment"] = ""
        assignments.append(a)

    # Technology across all assignments (it is the owner's experience, nda or not), most months
    # first, with the evidence limited to the entries shown here.
    shown = {e.id for e in work}
    tech = []
    for name, (months, ids, ongoing) in index.tech_evidence(profile).items():
        tech.append({"name": name, "months": len(months), "assignments": len(ids),
                     "ongoing": any(i in shown for i in ongoing),
                     "entries": [slug[i] for i in ids if i in shown]})
    tech.sort(key=lambda t: (-t["months"], t["name"]))

    return {
        "format": "openself-public-1",
        "lang": profile.lang,
        "names": names,
        "person": ({"id": "person", "slug": "person", "confidence": person.get("confidence"),
                    "omit": bool(omitted(person)), **fields(person, PERSON),
                    "sections": text_sections(person)} if person else None),
        "employments": [item(e, slug[e.id], EMPLOYMENT) for e in jobs],
        "assignments": assignments,
        "certifications": table(profile.entries.get("certifications"), CERT_COLUMNS),
        "education": table(profile.entries.get("education"), EDU_COLUMNS),
        "tech": tech,
    }


def strings(view):
    """Every string in a view, for checking what it would publish."""
    if isinstance(view, dict):
        for v in view.values():
            yield from strings(v)
    elif isinstance(view, list):
        for v in view:
            yield from strings(v)
    elif isinstance(view, str) and view:
        yield view


def hidden(profile, names=True):
    """Values the public view must never contain: the names of customers the profile keeps hidden
    (nda, anonymised or not decided, and named as public by no other entry; with names=False every
    customer that is not also an employer), and the private reference sections. A tool can check
    its output for them."""
    named, out = set(), set()
    if not names:
        named = {e.get("employer").lower() for e in profile.of_type("employment") if e.get("employer")}
    for e in profile.of_type("assignment"):
        found = {c for c in [e.get("customer")] + e.list("customers") if c}
        if e.get("kind") == "internal":
            pass
        elif names and e.get("customer_public") == "public":
            named |= {c.lower() for c in found}
        else:
            out |= found
        for s in model.sections(e.body, e.type):
            if s.id == "reference":
                out |= {ln.strip(" -*") for ln in s.text.split("\n") if len(ln.strip(" -*")) > 3}
    return sorted((h for h in out if h.lower() not in named), key=lambda s: (-len(s), s))


def leaks(text, profile, names=True):
    """The hidden values (see hidden) that occur in text, case-insensitively."""
    low = text.lower()
    return [h for h in hidden(profile, names) if re.search(r"(?<!\w)" + re.escape(h.lower()) + r"(?!\w)", low)]
