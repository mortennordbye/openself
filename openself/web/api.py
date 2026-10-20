"""The web API on top of a profile folder: read it, edit it, add and remove entries, answer flags,
and go back in time. Every write is checked against the version the browser started from,
rebuilds INDEX.md and is committed to the profile's history with the owner as the actor.

Each function takes the profile folder and returns (http status, json body), so any HTTP server
can expose it. openself.web.server is the one OpenSelf ships; other tools can mount the same
functions under their own routes.
"""

import os
import re
import threading

from .. import assistant, history, importer, index, lint, model, schema, write

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,80}$")
REV_RE = re.compile(r"^[0-9a-f]{4,40}$")
_locks = {}
_locks_guard = threading.Lock()


def lock_for(root):
    with _locks_guard:
        return _locks.setdefault(os.path.realpath(root), threading.Lock())


class Refused(Exception):
    def __init__(self, status, message, **extra):
        super().__init__(message)
        self.status, self.message, self.extra = status, message, extra


def guarded(fn):
    def run(*a, **kw):
        try:
            return 200, fn(*a, **kw)
        except Refused as e:
            return e.status, dict({"ok": False, "message": e.message}, **e.extra)
        except write.Conflict as e:
            return 409, {"ok": False, "message": "changed elsewhere while you were editing",
                         "current_text": e.current_text, "current_sha": e.current_sha}
        except (ValueError, FileNotFoundError, RuntimeError) as e:
            return 400, {"ok": False, "message": str(e)}
    run.__name__ = fn.__name__
    return run


def exists(root):
    return os.path.isfile(os.path.join(root, model.MANIFEST))


def readonly(root):
    return bool(model.read_manifest(root).get("readonly"))


def need(root):
    if not exists(root):
        raise Refused(404, "no profile here")
    return root


def writable(root):
    need(root)
    if readonly(root):
        raise Refused(403, "this profile is read-only (readonly in openself.json)")
    return root


def keep_outside_changes(root):
    """Commit edits made outside the web app (by an assistant or by hand) before writing, so
    that even an overwritten version stays in the history."""
    if history.is_repo(root):
        index.write_all(root)
        history.commit(root, history.message("profile", "changes made outside the web app", "tool"))


def finish(root, id_, what, actor="owner"):
    index.write_all(root)
    rev = history.commit(root, history.message(id_, what, actor))
    return {"ok": True, "rev": rev, "version": model.version(root)}


def entry_json(e, file_prefix=""):
    fl, bad = model.flags(e.body)
    return {"id": e.id, "type": e.type, "rel": e.rel, "file": file_prefix + e.rel, "sha": e.sha,
            "error": e.error, "removed": e.removed, "meta": e.meta, "text": e.text,
            "sections": [{"id": s.id, "heading": s.heading, "text": s.text, "known": s.known}
                         for s in (model.sections(e.body, e.type) if e.type in schema.TYPES else [])],
            "flags": [{"type": f.type, "text": f.text, "raw": f.raw, "open": f.open, "resolved": f.resolved} for f in fl],
            "bad_flags": [b for _, b in bad]}


def schema_json():
    out = {}
    for t in schema.TYPES:
        s = schema.load(t)
        out[t] = {"fields": [dict(name=k, type=v.get("type"), enum=v.get("enum") or v.get("items", {}).get("enum"),
                                  integer=v.get("x-coerce") == "integer", description=v.get("description", ""),
                                  scaffold=v.get("x-scaffold", True))
                             for k, v in s["properties"].items()],
                  "sections": s["x-sections"], "table": s.get("x-body", {}).get("table"),
                  "required": s.get("required", [])}
    return out


@guarded
def data(root, file_prefix=""):
    need(root)
    prof = model.load_profile(root)
    canon, _ = lint.tech_names()
    ev = index.tech_evidence(prof)
    return {"ok": True, "version": model.version(root), "readonly": readonly(root), "lang": prof.lang,
            "path": os.path.abspath(root), "manifest": prof.manifest, "labels": schema.labels(prof.lang),
            "schema": schema_json(), "history": history.is_repo(root),
            "entries": [entry_json(e, file_prefix) for e in list(prof.entries.values()) + list(prof.removed.values())],
            "issues": [i.__dict__ for i in lint.lint(prof)],
            "tech": [{"name": t, "months": len(m), "ids": sorted(ids, reverse=True), "ongoing": bool(o)}
                     for t, (m, ids, o) in sorted(ev.items(), key=lambda kv: (-len(kv[1][0]), kv[0].lower()))],
            "tech_names": sorted(canon, key=str.lower)}


@guarded
def state(root):
    return {"ok": True, "version": model.version(need(root))}


def check_id(id_):
    if not (ID_RE.match(id_) or id_ in schema.SINGLETONS):
        raise Refused(400, "bad id")


def clean_meta(meta, type_):
    """Form values from the browser: strings and lists of strings only, each on one line."""
    out = {}
    for k, v in (meta or {}).items():
        if not isinstance(k, str):
            continue
        if isinstance(v, list):
            out[k] = [" ".join(str(x).split()) for x in v if str(x).strip()]
        else:
            out[k] = " ".join(str(v if v is not None else "").split())
    for k in list(out):
        if schema.is_list(type_, k) and not isinstance(out[k], list):
            out[k] = [x.strip() for x in out[k].split(",") if x.strip()]
    return out


def body_from(sections, type_, lang):
    secs = []
    for s in sections or []:
        text = str(s.get("text", ""))
        secs.append(model.Section(str(s.get("id", "")), str(s.get("heading", "")),
                                  model.normalize_text(text).strip("\n") if text.strip() else ""))
    return model.join_sections(secs, type_, lang)


@guarded
def init(root, d):
    if exists(root):
        raise Refused(409, "there is already a profile here")
    langs = [x for x in (d.get("languages") or ["en"]) if re.fullmatch(r"[a-z]{2}", str(x))] or ["en"]
    write.init(root, owner=" ".join(str(d.get("owner", "")).split()), languages=langs, git=True)
    return finish(root, "profile", "created")


@guarded
def save(root, d, actor="owner"):
    writable(root)
    id_ = str(d.get("id", ""))
    check_id(id_)
    with lock_for(root):
        keep_outside_changes(root)
        rel = model.find(root, id_)
        if not rel or rel.startswith("_removed/"):
            raise Refused(404, "no such entry")
        type_ = model.type_for(rel)
        base = str(d.get("base_sha", ""))
        if "text" in d:
            _, err = write.save_text(root, id_, str(d["text"]), base)
            return finish(root, id_, "edited (whole file)", actor) | {"error": err}
        meta = clean_meta(d.get("meta"), type_)
        meta.update(schema="1", id=id_, type=type_)
        problems = [f"{f}: {m}" for f, m in schema.validate(meta, type_) if m != "required, but empty"]
        if problems:
            raise Refused(400, "; ".join(problems))
        prof = model.load_profile(root)
        old = prof.entries.get(id_)
        if d.get("verified"):
            meta["confidence"] = "verified"
        elif old is not None and "confidence" in old.meta:
            meta["confidence"] = old.meta["confidence"]
        write.save(root, id_, meta, body_from(d.get("sections"), type_, prof.lang), base)
        return finish(root, id_, "edited" + (", verified" if d.get("verified") else ""), actor)


@guarded
def new(root, d, actor="owner"):
    writable(root)
    type_ = d.get("type")
    if type_ not in schema.COLLECTIONS:
        raise Refused(400, "unknown type")
    with lock_for(root):
        keep_outside_changes(root)
        fields = clean_meta(d.get("fields"), type_)
        fields["confidence"] = fields.get("confidence") or "stated"
        fields = {k: v for k, v in fields.items() if v not in ("", [])}
        problems = [f"{f}: {m}" for f, m in schema.validate(dict(fields, schema="1", id="x-x-x", type=type_), type_)
                    if m != "required, but empty" and f != "id"]
        if problems:
            raise Refused(400, "; ".join(problems))
        secs = {str(k): str(v) for k, v in (d.get("sections") or {}).items() if str(v).strip()}
        id_ = write.scaffold(root, type_, fields, secs, lang=model.load_profile(root).lang)
        return finish(root, id_, f"new {type_}", actor) | {"id": id_}


@guarded
def remove(root, d, actor="owner"):
    writable(root)
    id_ = str(d.get("id", ""))
    check_id(id_)
    reason = str(d.get("reason", "")).strip()
    if not reason:
        raise Refused(400, "say why")
    with lock_for(root):
        keep_outside_changes(root)
        write.remove(root, id_, reason, expected_sha=str(d.get("base_sha", "")) or None)
        return finish(root, id_, "removed", actor)


@guarded
def flag(root, d, actor="owner"):
    writable(root)
    id_ = str(d.get("id", ""))
    check_id(id_)
    with lock_for(root):
        keep_outside_changes(root)
        rel = model.find(root, id_)
        if not rel:
            raise Refused(404, "no such entry")
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            text = f.read()
        if model.sha(text) != str(d.get("base_sha", "")):
            raise write.Conflict(text)
        lang = model.load_profile(root).lang
        new_text = model.resolve_flag(text, str(d.get("raw", "")), str(d.get("answer", "")), lang)
        e = model.load_entry(rel, new_text)
        if not e.error:
            e.meta["last_reviewed"] = model.today()
            new_text = write.render(e.meta, e.body, model.type_for(rel))
        write.write_atomic(os.path.join(root, rel), new_text, expected_sha=model.sha(text))
        return finish(root, id_, "question answered", actor)


@guarded
def import_(root, d, actor="owner"):
    """Import certifications from Credly or Microsoft Learn. With dry_run, only say what would change."""
    writable(root)
    urls = [str(u) for u in d.get("urls") or [] if str(u).strip()]
    try:
        rel, old, new, results = importer.run(root, urls)
    except FileNotFoundError:
        raise Refused(404, "this profile has no certifications.md")
    if results and all(r.get("error") for r in results):
        raise Refused(502, "could not read " + "; ".join(f"{importer.NAMES[r['source']]}: {r['error']}" for r in results), results=results)
    changed = new != old
    if d.get("dry_run") or not changed:
        return {"ok": True, "dry_run": bool(d.get("dry_run")), "changed": changed, "results": results}
    with lock_for(root):
        keep_outside_changes(root)
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            if f.read() != old:
                raise Refused(409, "certifications changed while importing; try again")
        write.write_atomic(os.path.join(root, rel), new, expected_sha=model.sha(old))
        what = "imported from " + ", ".join(dict.fromkeys(importer.NAMES[r["source"]] for r in results if not r.get("error")))
        return finish(root, "certifications", what, actor) | {"changed": True, "results": results}


@guarded
def log(root, id_=""):
    need(root)
    if id_:
        check_id(id_)
    if not history.is_repo(root):
        return {"ok": True, "items": []}
    tags = history.tags(root)
    items = history.log(root, id_ or None)
    for it in items:
        it["tags"] = tags.get(it["rev"], [])
    return {"ok": True, "items": items}


@guarded
def show(root, id_, rev):
    need(root)
    check_id(id_)
    if not REV_RE.match(rev):
        raise Refused(400, "bad version")
    rel, text = history.show(root, id_, rev)
    return {"ok": True, "rel": rel, "text": text}


@guarded
def restore(root, d, actor="owner"):
    writable(root)
    id_, rev = str(d.get("id", "")), str(d.get("rev", ""))
    check_id(id_)
    if not REV_RE.match(rev):
        raise Refused(400, "bad version")
    with lock_for(root):
        keep_outside_changes(root)
        new_rev = history.restore(root, id_, rev, actor)
        return {"ok": True, "rev": new_rev, "version": model.version(root)}


@guarded
def as_of(root, date, file_prefix=""):
    need(root)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise Refused(400, "date must be YYYY-MM-DD")
    rev = history.rev_at(root, date) if history.is_repo(root) else None
    if not rev:
        raise Refused(404, f"no version of the profile before {date}")
    prof = history.load_at(root, rev)
    return {"ok": True, "rev": rev[:7], "index": index.build_index(prof),
            "entries": [entry_json(e, file_prefix) for e in list(prof.entries.values()) + list(prof.removed.values())]}


@guarded
def assistant_state(root):
    """Whether an assistant is watching (openself assistant watch), and the requests: open ones and
    the last finished ones."""
    need(root)
    items = assistant.load(root)
    shown = [i for i in items if i.get("status") == "open"] + [i for i in items if i.get("status") == "done"][-10:]
    return dict(assistant.state(root), ok=True, items=sorted(shown, key=lambda i: -i.get("n", 0)),
                open=sum(1 for i in items if i.get("status") == "open"))


@guarded
def request(root, d):
    """Ask the assistant about an entry ("id"), or the whole profile (no id)."""
    need(root)
    id_ = str(d.get("id", ""))
    if id_:
        check_id(id_)
    i = assistant.add(root, id_, str(d.get("comment", "")), str(d.get("quote", "")))
    return {"ok": True, "request": i, "connected": assistant.state(root)["connected"]}


@guarded
def requeststatus(root, d):
    n = d.get("n")
    if not isinstance(n, int):
        raise ValueError("n must be a request number")
    return {"ok": True, "request": assistant.set_status(root, n, str(d.get("status", "")))}


GET = {"profile": data, "state": state, "log": log, "show": show, "asof": as_of, "assistant": assistant_state}
POST = {"init": init, "save": save, "new": new, "remove": remove, "flag": flag, "restore": restore, "import": import_,
        "request": request, "requeststatus": requeststatus}
