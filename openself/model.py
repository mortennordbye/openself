"""Loading a profile folder into entries, sections and flags."""

import datetime
import hashlib
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field

from . import frontmatter, schema

MANIFEST = "openself.json"
GENERATED = ("INDEX.md", "README.md")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,80}$")
FLAG_TYPES = ("question", "conflict", "emphasis", "omit", "correction")
OPEN_FLAG_TYPES = ("question", "conflict")
FLAG_RE = re.compile(r"^(?P<indent>\s*)- ⚑ (?P<kw>[^\s:()]+)"
                     r"(?: \((?P<rkw>[^\s)]+) (?P<date>\d{4}-\d{2}-\d{2})\))?: (?P<text>.*)$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


@dataclass
class Section:
    id: str
    heading: str
    text: str
    known: bool = True


@dataclass
class Flag:
    type: str
    text: str
    line: int
    raw: str
    resolved: str = ""

    @property
    def open(self):
        return self.type in OPEN_FLAG_TYPES and not self.resolved


@dataclass
class Entry:
    id: str
    type: str
    rel: str
    text: str
    meta: dict = field(default_factory=dict)
    body: str = ""
    error: str = ""
    removed: bool = False

    @property
    def sha(self):
        return sha(self.text)

    def get(self, key, default=""):
        v = self.meta.get(key, default)
        return default if v in ("", None) else v

    def list(self, key):
        v = self.meta.get(key, [])
        return v if isinstance(v, list) else ([] if v == "" else [v])


@dataclass
class Profile:
    root: str
    manifest: dict
    entries: dict = field(default_factory=dict)
    removed: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    generated: dict = field(default_factory=dict)

    @property
    def lang(self):
        return (self.manifest.get("languages") or ["en"])[0]

    def of_type(self, type_):
        return [e for e in self.entries.values() if e.type == type_]

    def all_ids(self):
        return set(self.entries) | set(self.removed)


def sha(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def normalize_text(s):
    s = unicodedata.normalize("NFC", s.replace("\r\n", "\n").replace("\r", "\n"))
    s = "\n".join(line.rstrip() for line in s.split("\n")).strip("\n")
    return s + "\n"


def today():
    return datetime.date.today().isoformat()


# ---- files -------------------------------------------------------------------------------

def type_for(rel):
    """Entry type implied by a file's place in the profile, or None for files that are not entries."""
    parts = rel.split("/")
    if len(parts) == 1:
        name = parts[0][:-3] if parts[0].endswith(".md") else None
        return name if name in schema.SINGLETONS else None
    if len(parts) == 2 and parts[1].endswith(".md") and not parts[1].startswith("."):
        for t, folder in schema.COLLECTIONS.items():
            if parts[0] == folder:
                return t
        if parts[0] == "_removed":
            return "removed"
    return None


def profile_files(root):
    """Repo-relative paths of every entry file in the profile folder."""
    out = []
    for name in sorted(os.listdir(root)):
        if name.startswith(".") or name in GENERATED:
            continue
        path = os.path.join(root, name)
        if os.path.isdir(path):
            if name in schema.COLLECTIONS.values() or name == "_removed":
                out += [f"{name}/{f}" for f in sorted(os.listdir(path))
                        if f.endswith(".md") and not f.startswith(".")]
        elif type_for(name):
            out.append(name)
    return out


def read_manifest(root):
    try:
        with open(os.path.join(root, MANIFEST), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def load_profile(root):
    root = os.path.abspath(root)
    files = {}
    for rel in profile_files(root):
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            files[rel] = f.read()
    generated = {}
    for name in GENERATED:
        p = os.path.join(root, name)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                generated[name] = f.read()
    return load_files(files, read_manifest(root), root, generated)


def load_files(files, manifest, root="", generated=None):
    """Build a Profile from {rel: text}. Used for the working tree and for old git revisions."""
    p = Profile(root=root, manifest=manifest, generated=generated or {})
    for rel in sorted(files):
        e = load_entry(rel, files[rel])
        if e is None:
            continue
        if e.error:
            p.errors.append((rel, e.error))
        target = p.removed if e.removed else p.entries
        if e.id in p.entries or e.id in p.removed:
            p.errors.append((rel, f"id '{e.id}' is used by more than one file"))
            continue
        target[e.id] = e
    return p


def load_entry(rel, text):
    t = type_for(rel)
    if t is None:
        return None
    file_id = os.path.basename(rel)[:-3]
    e = Entry(id=file_id, type=t, rel=rel, text=text, removed=(t == "removed"))
    try:
        e.meta, e.body = frontmatter.parse(text)
    except frontmatter.FrontmatterError as err:
        e.error = str(err)
        e.body = frontmatter.split(text)[1] if text.startswith("---\n") and "\n---\n" in text else text
        if e.removed:
            e.type = "assignment"
        return e
    if e.removed:
        e.type = e.meta.get("type") if e.meta.get("type") in schema.COLLECTIONS else "assignment"
    return e


def version(root):
    """Cheap fingerprint of the folder for polling: names, sizes and modification times."""
    h = hashlib.sha1()
    for rel in [MANIFEST] + profile_files(root):
        try:
            st = os.stat(os.path.join(root, rel))
        except OSError:
            continue
        h.update(f"{rel}\0{st.st_size}\0{st.st_mtime_ns}\n".encode())
    return h.hexdigest()[:16]


def digest(profile):
    """Content fingerprint of all entries, written into INDEX.md to tell when it is stale."""
    h = hashlib.sha1()
    for e in sorted(list(profile.entries.values()) + list(profile.removed.values()), key=lambda e: e.rel):
        h.update(f"{e.rel}\0{e.sha}\n".encode())
    h.update(json.dumps(profile.manifest, sort_keys=True).encode())
    return h.hexdigest()[:16]


def find(root, id_):
    """Path relative to the profile root of the file holding id_ (active or removed), or None."""
    if id_ in schema.SINGLETONS:
        return f"{id_}.md" if os.path.exists(os.path.join(root, f"{id_}.md")) else None
    if not ID_RE.match(id_):
        return None
    for folder in list(schema.COLLECTIONS.values()) + ["_removed"]:
        if os.path.exists(os.path.join(root, folder, f"{id_}.md")):
            return f"{folder}/{id_}.md"
    return None


# ---- sections and flags ------------------------------------------------------------------

def heading_map(type_):
    """Heading text (lowercase) -> section id, across every label language."""
    out = {}
    for lang in schema.label_languages():
        for sid, label in schema.labels(lang)["sections"].get(type_, {}).items():
            out[label.lower()] = sid
    for sid in schema.sections(type_):
        out[sid] = sid
    return out


def slug_heading(text):
    return re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", text.lower())
                  .encode("ascii", "ignore").decode()).strip("-") or "section"


def sections(body, type_):
    """Split a body into sections at '## ' headings outside code fences. Text before the first
    heading is a section with id '_intro'."""
    known = heading_map(type_) if type_ in schema.TYPES else {}
    out = [Section("_intro", "", "")]
    fence = False
    lines = []
    for line in body.split("\n"):
        if FENCE_RE.match(line):
            fence = not fence
        if not fence and line.startswith("## "):
            out[-1].text = "\n".join(lines).strip("\n")
            lines = []
            heading = line[3:].strip()
            sid = known.get(heading.lower())
            out.append(Section(sid or slug_heading(heading), heading, "", known=sid is not None))
        else:
            lines.append(line)
    out[-1].text = "\n".join(lines).strip("\n")
    if not out[0].text:
        out.pop(0)
    return out


def join_sections(secs, type_, lang):
    """Write sections back into a body. Known sections get the heading of the profile language
    and come in schema order; others keep their heading and place at the end."""
    labels = schema.labels(lang)["sections"].get(type_, {})
    order = schema.sections(type_)
    by_id = {s.id: s for s in secs}
    parts = []
    intro = by_id.get("_intro")
    if intro and intro.text.strip():
        parts.append(intro.text.strip("\n"))
    for sid in order:
        s = by_id.get(sid)
        if s and s.text.strip():
            parts.append(f"## {labels.get(sid, s.heading or sid)}\n\n{s.text.strip(chr(10))}")
    for s in secs:
        if s.id != "_intro" and s.id not in order and s.text.strip():
            parts.append(f"## {s.heading or s.id}\n\n{s.text.strip(chr(10))}")
    return "\n\n".join(parts) + "\n" if parts else ""


def flag_words():
    """keyword -> canonical flag type, and the set of words meaning 'resolved', across languages."""
    kinds = {t: t for t in FLAG_TYPES}
    resolved = {"resolved"}
    for lang in schema.label_languages():
        f = schema.labels(lang).get("flags", {})
        for t in FLAG_TYPES:
            if f.get(t):
                kinds[f[t]] = t
        if f.get("resolved"):
            resolved.add(f["resolved"])
    return kinds, resolved


def flags(body, start_line=1):
    """Flags in a body, plus a list of (line, text) for lines with ⚑ that are not valid flags."""
    kinds, resolved = flag_words()
    out, bad = [], []
    fence = False
    for i, line in enumerate(body.split("\n")):
        if FENCE_RE.match(line):
            fence = not fence
        if fence or "⚑" not in line:
            continue
        m = FLAG_RE.match(line)
        if not m or m.group("kw") not in kinds or (m.group("rkw") and m.group("rkw") not in resolved):
            bad.append((start_line + i, line.strip()))
            continue
        out.append(Flag(kinds[m.group("kw")], m.group("text"), start_line + i, line, m.group("date") or ""))
    return out, bad


def resolve_flag(body, raw_line, answer, lang, date=None):
    """Mark the flag on raw_line as resolved today, with the owner's answer quoted after it."""
    lines = body.split("\n")
    if raw_line not in lines:
        raise ValueError("the flag is no longer in the file")
    m = FLAG_RE.match(raw_line)
    if not m or m.group("date"):
        raise ValueError("not an open flag")
    words = schema.labels(lang)["flags"]
    text = m.group("text").rstrip()
    if answer.strip():
        text += f" {words['answer']}: «{' '.join(answer.split())}»"
    new = f"{m.group('indent')}- ⚑ {m.group('kw')} ({words['resolved']} {date or today()}): {text}"
    lines[lines.index(raw_line)] = new
    return "\n".join(lines)


def parse_table(body):
    """Rows of the first markdown table in body, as lists of cell strings (header excluded)."""
    rows, seen_header = [], False
    for line in body.split("\n"):
        s = line.strip()
        if not s.startswith("|"):
            if rows or seen_header:
                break
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not seen_header:
            seen_header = True
            continue
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        rows.append(cells)
    return rows


def retired(meta, body, type_):
    """What an older profile still carries that schema 1 no longer has: retired fields, and the
    Source column at the end of a certifications or education table."""
    out = [k for k in meta if k in schema.RETIRED]
    cols = schema.table_columns(type_)
    head = next((ln for ln in body.split("\n") if ln.strip().startswith("|")), "")
    if cols and head and len(head.strip().strip("|").split("|")) == len(cols) + 1:
        out.append("source column")
    return out


def drop_retired(meta, body, type_):
    """meta and body without what `retired` finds."""
    meta = {k: v for k, v in meta.items() if k not in schema.RETIRED}
    cols = schema.table_columns(type_)
    if cols and "source column" in retired({}, body, type_):
        lines, inside = body.split("\n"), False
        for i, ln in enumerate(lines):
            if not ln.strip().startswith("|"):
                if inside:
                    break
                continue
            inside = True
            cells = [c.strip() for c in ln.strip().strip("|").split("|")][:len(cols)]
            sep = all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c)
            lines[i] = "|" + "|".join("---" for _ in cols) + "|" if sep else "| " + " | ".join(cells) + " |"
        body = "\n".join(lines)
    return meta, body


def dump_table(rows, header):
    def cell(c):
        return " ".join(str(c).replace("|", "/").split())
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for r in rows:
        r = list(r) + [""] * (len(header) - len(r))
        out.append("| " + " | ".join(cell(c) for c in r[:len(header)]) + " |")
    return "\n".join(out)


# ---- periods -----------------------------------------------------------------------------

def month(s, end=False):
    """'2024-02' -> month number; '2024' -> January (or December when end); '' -> None."""
    if not s:
        return None
    if s == "ongoing":
        d = datetime.date.today()
        return d.year * 12 + d.month - 1
    m = re.fullmatch(r"(\d{4})(?:-(\d{2}))?", s)
    if not m:
        return None
    mo = int(m.group(2)) if m.group(2) else (12 if end else 1)
    return int(m.group(1)) * 12 + mo - 1


def ym(n):
    return f"{n // 12:04d}-{n % 12 + 1:02d}"


def months(e, ongoing_until=None, with_breaks=False):
    """Set of months an entry covers, breaks excluded. Empty when the start is unknown. An ongoing
    entry runs to this month, or to ongoing_until ('YYYY-MM') when given."""
    a = month(e.get("start"))
    end = e.get("end")
    if end == "ongoing" and ongoing_until:
        end = ongoing_until
    b = month(end, end=True) if end else a
    if a is None or b is None or b < a:
        return set()
    out = set(range(a, b + 1))
    for br in ([] if with_breaks else e.list("breaks")):
        x, _, y = br.partition("/")
        bx, by = month(x), month(y, end=True)
        if bx is not None and by is not None:
            out -= set(range(bx, by + 1))
    return out


def period(e, ongoing_word="ongoing"):
    s, t = e.get("start"), e.get("end")
    if not s:
        return "?"
    if t == "ongoing":
        return f"{s} – {ongoing_word}"
    return f"{s} – {t}" if t and t != s else s
