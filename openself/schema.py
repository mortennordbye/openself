"""The JSON Schemas in schema/v<N>/ and labels/ are the single source of truth. This module loads
them and validates frontmatter with the small part of JSON Schema they use."""

import json
import os
import re
from functools import lru_cache

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_VERSION = 1
TYPES = ("person", "certifications", "education", "employment", "assignment")
COLLECTIONS = {"employment": "employments", "assignment": "assignments"}
SINGLETONS = ("person", "certifications", "education")


@lru_cache(maxsize=None)
def load(type_, version=SCHEMA_VERSION):
    with open(os.path.join(HERE, "schema", f"v{version}", f"{type_}.schema.json"), encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=None)
def labels(lang):
    path = os.path.join(HERE, "labels", f"{lang}.json")
    if not os.path.exists(path):
        path = os.path.join(HERE, "labels", "en.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def label_languages():
    return sorted(f[:-5] for f in os.listdir(os.path.join(HERE, "labels")) if f.endswith(".json"))


def field_order(type_):
    return list(load(type_)["properties"])


def scaffold_fields(type_):
    return [k for k, v in load(type_)["properties"].items() if v.get("x-scaffold", True)]


def sections(type_):
    return load(type_)["x-sections"]


def table_columns(type_):
    return load(type_).get("x-body", {}).get("table")


def is_list(type_, key):
    return load(type_)["properties"].get(key, {}).get("type") == "array"


def validate(meta, type_):
    """Return a list of (field, message) for everything in meta the schema does not allow."""
    sch = load(type_)
    props = sch["properties"]
    out = []
    for k in sch.get("required", []):
        if k not in meta:
            out.append((k, "missing"))
        elif k not in ("schema", "id", "type") and meta[k] in ("", []):
            out.append((k, "required, but empty"))
    for k, v in meta.items():
        if k.startswith("x-"):
            continue
        p = props.get(k)
        if p is None:
            out.append((k, "unknown field"))
            continue
        if p["type"] == "array":
            if v == "":
                continue
            if not isinstance(v, list):
                out.append((k, "should be a list"))
                continue
            for item in v:
                msg = check_string(item, p["items"])
                if msg:
                    out.append((k, f"{item!r}: {msg}"))
        else:
            if isinstance(v, list):
                out.append((k, "should be a single value, not a list"))
                continue
            msg = check_string(v, p)
            if msg:
                out.append((k, f"{v!r}: {msg}"))
    return out


def check_string(v, p):
    if "enum" in p and v not in p["enum"]:
        return "must be one of " + ", ".join(x for x in p["enum"] if x)
    if "pattern" in p and not re.search(p["pattern"], v):
        return "wrong format"
    return None


def coerce(meta, type_):
    """Typed copy of meta: integers for x-coerce fields (None when empty), lists for list fields."""
    props = load(type_)["properties"]
    out = {}
    for k, v in meta.items():
        p = props.get(k, {})
        if p.get("x-coerce") == "integer":
            out[k] = int(v) if isinstance(v, str) and v.isdigit() else None
        elif p.get("type") == "array":
            out[k] = v if isinstance(v, list) else ([] if v == "" else [v])
        else:
            out[k] = v
    return out
