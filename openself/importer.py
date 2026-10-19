"""Import certifications from public pages: a Credly profile and a Microsoft Learn transcript.

    rel, old, new, results = importer.run(root, urls)    # fetch every page, merge, nothing written yet
    certs, source = importer.fetch(url)                  # what one page lists
    text, summary = importer.merge(entry, certs, source) # certifications.md with them merged in

Only these two hosts are fetched, and only when the owner asks. A certificate that matches a row in
the table fills the row's empty cells, makes a year-month date exact when the two agree, and
becomes the row's source (hand-written labels such as raw.md give way to the account); a date that disagrees becomes a conflict flag for the owner, never an overwrite (SPEC
rule 2). Certificates not in the table are added as new rows.
"""

import json
import re
import unicodedata
import urllib.request
from dataclasses import dataclass

from . import model, schema, write

CREDLY_RE = re.compile(r"^https://(?:www\.)?credly\.com/users/([A-Za-z0-9._-]+)(?:/badges)?/?(?:[?#].*)?$")
MSLEARN_RE = re.compile(r"^https://learn\.microsoft\.com/(?:[a-z]{2}-[a-z]{2}/)?users/[A-Za-z0-9._-]+/transcript/([A-Za-z0-9]+)/?(?:[?#].*)?$")
NAMES = {"credly": "Credly", "mslearn": "Microsoft Learn"}
STOP = {"microsoft", "certified", "certification", "certificate", "exam", "the", "and", "of", "for", "a", "an", "in"}
WORDS = {
    "en": {"date": "the date", "expires": "the expiry date", "conflict": "{src} says {field} of «{name}» is {new}; the table says {old}."},
    "nb": {"date": "datoen", "expires": "utløpsdatoen", "conflict": "{src} sier at {field} for «{name}» er {new}; tabellen sier {old}."},
}


@dataclass
class Cert:
    name: str
    issuer: str
    date: str = ""
    expires: str = ""


def source_of(url):
    """('credly', user) or ('mslearn', share id) for a supported page, else ValueError."""
    url = (url or "").strip()
    m = CREDLY_RE.match(url)
    if m:
        return "credly", m.group(1)
    m = MSLEARN_RE.match(url)
    if m:
        return "mslearn", m.group(1)
    raise ValueError("not a Credly profile (credly.com/users/...) or a Microsoft Learn transcript link (learn.microsoft.com/.../transcript/...)")


def get_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "openself-import"})
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 (the host is checked by source_of)
        return json.load(r)


def fetch(url, get=get_json):
    """The certificates a supported page lists, and the source key ('credly' or 'mslearn')."""
    kind, key = source_of(url)
    if kind == "credly":
        return credly(key, get), kind
    return mslearn(key, get), kind


def credly(user, get=get_json):
    out, page, seen = [], f"https://www.credly.com/users/{user}/badges.json", 0
    while page and seen < 20:
        d = get(page)
        seen += 1
        for b in d.get("data") or []:
            if b.get("state") not in (None, "accepted"):
                continue
            ents = [e.get("entity", {}).get("name", "") for e in (b.get("issuer") or {}).get("entities") or []]
            out.append(Cert(" ".join(str((b.get("badge_template") or {}).get("name", "")).split()), next((x for x in ents if x), ""),
                            day(b.get("issued_at_date")), day(b.get("expires_at_date"))))
        nxt = (d.get("metadata") or {}).get("next_page_url") or ""
        page = nxt if nxt.startswith("https://www.credly.com/") else ""
    return [c for c in out if c.name]


def mslearn(share, get=get_json):
    d = get(f"https://learn.microsoft.com/api/profiles/transcript/share/{share}?locale=en-us")
    cd = d.get("certificationData") or {}
    out = []
    for c in (cd.get("activeCertifications") or []) + (cd.get("historicalCertifications") or []):
        name = " ".join(str(c.get("name", "")).split())
        if name:
            out.append(Cert(name, "GitHub" if name.lower().startswith("github") else "Microsoft", day(c.get("dateEarned")), day(c.get("expiration"))))
    return out


def day(s):
    m = re.match(r"\d{4}-\d{2}-\d{2}", str(s or ""))
    return m.group(0) if m else ""


def tokens(name):
    s = unicodedata.normalize("NFKD", name.lower())
    s = re.sub(r"\b([a-z]{2,5})-(\d{2,4})\b", r"\1\2", s)  # AZ-104 -> az104
    return set(re.findall(r"[a-z0-9]+", s)) - STOP


def score(a, b):
    """How well two certificate names match: 0 (not the same) to 3 (the same words)."""
    x, y = tokens(a), tokens(b)
    if not x or not y:
        return 0
    if x == y:
        return 3
    if {t for t in x & y if re.fullmatch(r"[a-z]+\d+", t)}:
        return 2.5  # a shared exam code: AZ-104, GH-300
    if (x <= y or y <= x) and min(len(x), len(y)) >= 2:
        return 2
    j = len(x & y) / len(x | y)
    return 1 + j if j >= 0.75 else 0


def merge(entry, certs, source, lang=None, today=None):
    """certifications.md with the certificates merged in, and a summary of what changed."""
    lang = lang if lang in WORDS else "en"
    words, label = WORDS[lang], f"{NAMES[source]} {today or model.today()}"
    secs = model.sections(entry.body, "certifications")
    intro = next((s for s in secs if s.id == "_intro"), None)
    rows = [list(r) + [""] * (5 - len(r)) for r in model.parse_table(intro.text if intro else "")]
    header = schema.labels(lang)["tables"]["certifications"]
    first = next((ln for ln in (intro.text if intro else "").split("\n") if ln.strip().startswith("|")), "")
    if first:  # keep the table's own header (its text is free, SPEC section 2)
        cells = [c.strip() for c in first.strip().strip("|").split("|")]
        header = cells if len(cells) == len(header) else header
    summary = {"source": source, "found": len(certs), "added": [], "updated": [], "conflicts": [], "unchanged": 0}
    taken, flags = set(), []
    for c in certs:
        best, at = 0, -1
        for i, r in enumerate(rows):
            if i not in taken and score(c.name, r[0]) > best:
                best, at = score(c.name, r[0]), i
        if at < 0:
            rows.append([c.name, c.issuer, c.date, c.expires, label])
            taken.add(len(rows) - 1)
            summary["added"].append({"name": c.name, "issuer": c.issuer, "date": c.date, "expires": c.expires})
            continue
        taken.add(at)
        r, changes = rows[at], {}
        if not r[1] and c.issuer:
            changes["issuer"] = ["", c.issuer]
            r[1] = c.issuer
        for col, field in ((2, "date"), (3, "expires")):
            old, new = r[col], getattr(c, field)
            if not new or old == new:
                continue
            if not old or new.startswith(old):
                changes[field] = [old, new]
                r[col] = new
            else:
                text = words["conflict"].format(src=NAMES[source], field=words[field], name=r[0], new=new, old=old)
                flags.append(text)
                summary["conflicts"].append(text)
        # A confirmed row is sourced to the account: other accounts' labels stay, hand-written ones go,
        # and a label this account already gave is kept so importing again changes nothing.
        parts = [x.strip() for x in r[4].split(",") if x.strip()]
        accounts = [x for x in parts if any(x.startswith(n + " ") for n in NAMES.values())]
        src = ", ".join(accounts if any(x.startswith(NAMES[source] + " ") for x in accounts) else accounts + [label])
        if src != r[4]:
            changes["source"] = [r[4], src]
            r[4] = src
        if changes:
            summary["updated"].append({"name": r[0], "changes": changes})
        else:
            summary["unchanged"] += 1
    table = model.dump_table(rows, header)
    if intro:
        intro.text = table
    else:
        secs.insert(0, model.Section("_intro", "", table))
    if flags:
        kw = schema.labels(lang).get("flags", {}).get("conflict") or "conflict"
        fsec = next((s for s in secs if s.id == "flags"), None)
        if fsec is None:
            fsec = model.Section("flags", "", "")
            secs.append(fsec)
        have = fsec.text
        new_lines = [f"- ⚑ {kw}: {t}" for t in flags if t not in have]
        summary["conflicts"] = [t for t in flags if t not in have]
        fsec.text = "\n".join(x for x in (have.rstrip("\n"), *new_lines) if x)
    meta = dict(entry.meta)
    if summary["added"] or summary["updated"] or summary["conflicts"]:
        meta["sources"] = [s for s in meta.get("sources") or [] if not s.startswith(NAMES[source] + " ")] + [label]
        meta["last_reviewed"] = today or model.today()
    body = model.join_sections(secs, "certifications", lang)
    return write.render(meta, body, "certifications"), summary


def remember(text, urls):
    """certifications.md with the page links stored in `imports`, so the import can run again."""
    e = model.load_entry("certifications.md", text)
    have = list(e.meta.get("imports") or [])
    add = [u for u in urls if u not in have]
    if not add:
        return text
    return write.render(dict(e.meta, imports=have + add), e.body, "certifications")


def run(root, urls=None, get=None):
    """Fetch every page (the given links, else the ones stored in `imports`) and merge them into
    certifications.md. Returns (rel, old text, new text, one summary per page); writes nothing.
    A page that cannot be read gets a summary with `error` and changes nothing."""
    rel = model.find(root, "certifications")
    if not rel or rel.startswith("_removed/"):
        raise FileNotFoundError("certifications")
    with open(f"{root}/{rel}", encoding="utf-8") as f:
        old = f.read()
    e = model.load_entry(rel, old)
    if e.error:
        raise ValueError(f"{rel}: {e.error}")
    urls = [u.strip() for u in (urls or e.meta.get("imports") or []) if u.strip()]
    if not urls:
        raise ValueError("give a Credly profile or a Microsoft Learn transcript link")
    for u in urls:
        source_of(u)
    lang = model.load_profile(root).lang
    text, results = old, []
    for u in urls:
        try:
            certs, source = fetch(u, get or get_json)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            # One page that cannot be read does not stop the others.
            results.append({"url": u, "source": source_of(u)[0], "error": str(getattr(e, "reason", e)) or type(e).__name__,
                            "found": 0, "added": [], "updated": [], "conflicts": [], "unchanged": 0})
            continue
        text, summary = merge(model.load_entry(rel, text), certs, source, lang)
        results.append(dict(summary, url=u))
    return rel, old, remember(text, urls), results
