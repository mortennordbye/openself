"""Creating, saving and removing entries. Every write is atomic and can be checked against the
version the writer started from, so two editors cannot silently overwrite each other."""

import json
import os
import re
import subprocess
import tempfile
import unicodedata

from . import frontmatter, model, schema

TRANSLIT = str.maketrans({"æ": "ae", "ø": "o", "å": "a", "Æ": "ae", "Ø": "o", "Å": "a", "ß": "ss"})


class Conflict(Exception):
    """The file changed since the writer read it."""

    def __init__(self, current_text):
        super().__init__("the file was changed by someone else")
        self.current_text = current_text
        self.current_sha = model.sha(current_text) if current_text is not None else ""


def write_atomic(path, text, expected_sha=None):
    """Write text to path through a temporary file in the same folder. With expected_sha, refuse
    (Conflict) when the file on disk is not the version the caller based its change on. An
    expected_sha of "" means the file must not exist yet."""
    if expected_sha is not None:
        current = None
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                current = f.read()
        if (current is None and expected_sha != "") or (current is not None and model.sha(current) != expected_sha):
            raise Conflict(current)
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", dir=folder)
    try:
        # mkstemp makes the file private (0600); give it the mode a normal write would have.
        if os.path.exists(path):
            mode = os.stat(path).st_mode & 0o777
        else:
            umask = os.umask(0)
            os.umask(umask)
            mode = 0o666 & ~umask
        os.chmod(tmp, mode)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def slugify(s, limit=30):
    s = unicodedata.normalize("NFKD", s.translate(TRANSLIT).lower()).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > limit:
        s = s[:limit].rsplit("-", 1)[0] or s[:limit]
    return s


def new_id(taken, start, *parts):
    """Id for a new entry: <yyyy-mm>-<slug of each part>, with -2, -3... when it is taken.
    `taken` must include removed ids, which are never reused."""
    head = start[:7] if start else "undated"
    slug = "-".join(p for p in (slugify(x) for x in parts if x) if p) or "entry"
    base = f"{head}-{slug}"[:78].rstrip("-")
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


def render(meta, body, type_):
    """The file text for an entry: canonical frontmatter, then the body."""
    meta = dict(meta)
    for k in list(meta):
        if schema.is_list(type_, k) and meta[k] == "":
            meta[k] = []
    body = body.strip("\n")
    return model.normalize_text(frontmatter.dump(meta, schema.field_order(type_)) + ("\n" + body if body else ""))


def blank_meta(type_, id_):
    meta = {}
    for k in schema.scaffold_fields(type_):
        meta[k] = [] if schema.is_list(type_, k) else ""
    meta.update(schema="1", id=id_, type=type_, status="active")
    return meta


def scaffold(root, type_, fields, section_texts=None, lang=None, today=None):
    """Create a new employment or assignment file. Returns its id. fields may hold any schema
    field; section_texts maps section id to text."""
    profile = model.load_profile(root)
    lang = lang or profile.lang
    if type_ == "assignment":
        # An NDA customer's name stays out of the id (ids show up in file lists and commit messages).
        who = fields.get("customer") if fields.get("customer_public") != "nda" else (fields.get("customer_alias") or fields.get("sector"))
        id_ = new_id(profile.all_ids(), fields.get("start", ""), who or fields.get("kind", ""), fields.get("role", ""))
    elif type_ == "employment":
        id_ = new_id(profile.all_ids(), fields.get("start", ""), fields.get("employer", ""), fields.get("title", ""))
    else:
        raise ValueError(f"cannot create a new {type_}")
    meta = blank_meta(type_, id_)
    for k, v in fields.items():
        if k in ("schema", "id", "type"):
            continue
        meta[k] = v
    if type_ == "assignment" and not meta.get("customer_public") and meta.get("kind") != "internal":
        meta["customer_public"] = "unknown"
    meta["last_reviewed"] = fields.get("last_reviewed") or today or model.today()
    secs = [model.Section(sid, "", txt) for sid, txt in (section_texts or {}).items()]
    body = model.join_sections(secs, type_, lang)
    path = os.path.join(root, schema.COLLECTIONS[type_], f"{id_}.md")
    write_atomic(path, render(meta, body, type_), expected_sha="")
    return id_


def save(root, id_, meta, body, expected_sha, today=None, actor=None):
    """Replace an entry's content. The id and type cannot change. Returns the new text."""
    rel = model.find(root, id_)
    if not rel or rel.startswith("_removed/"):
        raise FileNotFoundError(id_)
    type_ = model.type_for(rel)
    if meta.get("id", id_) != id_ or meta.get("type", type_) != type_:
        raise ValueError("id and type cannot be changed")
    meta = dict(meta, id=id_, type=type_)
    if today is not False:
        meta["last_reviewed"] = today or model.today()
    text = render(meta, body, type_)
    check = model.load_entry(rel, text)  # round trip: what was written must read back cleanly
    if check.error:
        raise ValueError(check.error)
    write_atomic(os.path.join(root, rel), text, expected_sha=expected_sha)
    return text


def save_text(root, id_, text, expected_sha):
    """Replace an entry's whole file text (the raw-file editor). The id in it must match."""
    rel = model.find(root, id_)
    if not rel:
        raise FileNotFoundError(id_)
    text = model.normalize_text(text)
    check = model.load_entry(rel, text)
    if not check.error and check.meta.get("id") not in (None, "", id_):
        raise ValueError("the id in the file must stay " + id_)
    write_atomic(os.path.join(root, rel), text, expected_sha=expected_sha)
    return text, check.error


def remove(root, id_, reason, expected_sha=None, today=None):
    """Move an entry to _removed/ with the date and reason. Its id stays reserved."""
    rel = model.find(root, id_)
    if not rel or rel.startswith("_removed/") or id_ in schema.SINGLETONS:
        raise FileNotFoundError(id_)
    src = os.path.join(root, rel)
    with open(src, encoding="utf-8") as f:
        text = f.read()
    if expected_sha is not None and model.sha(text) != expected_sha:
        raise Conflict(text)
    e = model.load_entry(rel, text)
    type_ = model.type_for(rel)
    meta = dict(e.meta) if not e.error else {"schema": "1", "id": id_, "type": type_}
    meta.update(status="removed", removed=today or model.today(), removed_reason=" ".join(reason.split()))
    out = render(meta, e.body, type_) if not e.error else text
    write_atomic(os.path.join(root, "_removed", f"{id_}.md"), out, expected_sha="")
    os.unlink(src)
    return f"_removed/{id_}.md"


def init(root, owner="", languages=("en",), git=True):
    """Create an empty profile: manifest, person, certifications, education, folders, git repo.
    Leaves existing files alone."""
    os.makedirs(root, exist_ok=True)
    for folder in list(schema.COLLECTIONS.values()) + ["_removed"]:
        os.makedirs(os.path.join(root, folder), exist_ok=True)
        keep = os.path.join(root, folder, ".gitkeep")
        if not os.listdir(os.path.join(root, folder)):
            open(keep, "w").close()
    mpath = os.path.join(root, model.MANIFEST)
    if not os.path.exists(mpath):
        manifest = {"format": "openself", "schema": schema.SCHEMA_VERSION, "owner": owner,
                    "languages": list(languages), "readonly": False,
                    "spec": "https://github.com/mortennordbye/openself/blob/main/SPEC.md"}
        write_atomic(mpath, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    lang = languages[0]
    for t in schema.SINGLETONS:
        path = os.path.join(root, f"{t}.md")
        if os.path.exists(path):
            continue
        meta = blank_meta(t, t)
        meta.pop("status", None)
        if t == "person":
            meta["name"] = owner
        body = ""
        cols = schema.table_columns(t)
        if cols:
            body = model.dump_table([], schema.labels(lang)["tables"][t])
        write_atomic(path, render(meta, body, t))
    if git and not os.path.isdir(os.path.join(root, ".git")):
        subprocess.run(["git", "init", "-q", root], check=True)
    from . import index
    index.write_all(root)
