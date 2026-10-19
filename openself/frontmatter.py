"""Frontmatter: a small, strict subset of YAML, read and written with the standard library.

Every value is a string or a list of strings, the way yaml.BaseLoader reads it. The subset is
flat `key: value` lines with plain, "double" (JSON escapes) or 'single' quoted scalars, inline
`[a, b]` lists and block `- item` lists. Anything else is refused with a line number, so a file
either means exactly one thing or is reported.
"""

import json
import re

KEY_RE = re.compile(r"[a-z][a-z0-9_]*|x-[a-z0-9][a-z0-9-]*")
ITEM_RE = re.compile(r"^\s*- (.*)$|^\s*-$")
BOOLISH = {"y", "n", "yes", "no", "true", "false", "on", "off", "null", "~", "=", "<<",
           ".inf", "-.inf", "+.inf", ".nan"}
NUMBERISH = re.compile(r"^[-+]?(\.?\d|0[box])[\d_.:eExXa-fA-F+-]*$")
PLAIN_INT = re.compile(r"^(0|[1-9]\d*)$")
DATEISH = re.compile(r"^\d{4}-\d\d?-\d\d?([Tt]|\s)")
FIRST_SPECIAL = set("-?:,[]{}#&*!|>'\"%@`")


class FrontmatterError(ValueError):
    def __init__(self, line, msg):
        super().__init__(f"line {line}: {msg}")
        self.line = line
        self.msg = msg


def split(text):
    """Split a file into (frontmatter lines, body, first body line number). No frontmatter: ([], text, 1)."""
    if not text.startswith("---\n"):
        return [], text, 1
    lines = text.split("\n")
    for i in range(1, len(lines)):
        if lines[i] == "---":
            return lines[1:i], "\n".join(lines[i + 1:]), i + 2
    raise FrontmatterError(1, "frontmatter starts with --- but never ends")


def parse(text):
    """Parse a file into (meta, body). Raises FrontmatterError."""
    fm, body, _ = split(text)
    meta = {}
    open_key = None  # a key written as `key:` whose block list items may follow
    for n, line in enumerate(fm, start=2):
        if not line.strip():
            continue
        item = ITEM_RE.match(line)
        if item:
            if open_key is None:
                raise FrontmatterError(n, "list item without a list key above it")
            if meta[open_key] == "":
                meta[open_key] = []
            meta[open_key].append(scalar(item.group(1), n) if item.group(1) else "")
            continue
        if line[0] in " \t":
            raise FrontmatterError(n, "nested values are not allowed; use a flat key: value")
        k, sep, rest = line.partition(":")
        if not sep or not KEY_RE.fullmatch(k):
            raise FrontmatterError(n, f"expected 'key: value', got {line!r}")
        if k in meta:
            raise FrontmatterError(n, f"key '{k}' appears twice")
        if rest and not rest.startswith(" "):
            raise FrontmatterError(n, "put a space after the colon")
        value = rest.strip()
        open_key = k if value == "" else None
        if value == "":
            meta[k] = ""
        elif value.startswith("["):
            meta[k] = inline_list(value, n)
        else:
            meta[k] = scalar(value, n)
    return meta, body


def scalar(value, n, in_list=False):
    value = value.strip()
    if value.startswith('"'):
        try:
            s, end = json.JSONDecoder().raw_decode(value)
        except json.JSONDecodeError as e:
            raise FrontmatterError(n, f"bad double-quoted value: {e.msg}") from None
        if not isinstance(s, str) or value[end:].strip():
            raise FrontmatterError(n, "text after the closing quote")
        return s
    if value.startswith("'"):
        m = re.fullmatch(r"'((?:[^']|'')*)'", value)
        if not m:
            raise FrontmatterError(n, "bad single-quoted value")
        return m.group(1).replace("''", "'")
    if value[0] in "{&*!|>%@`" or value.startswith(("- ", "? ", ": ")):
        raise FrontmatterError(n, f"value {value!r} needs quotes")
    if ": " in value or value.endswith(":"):
        raise FrontmatterError(n, f"value {value!r} contains ': '; put it in double quotes")
    if " #" in value or value.startswith("#"):
        raise FrontmatterError(n, "comments are not allowed; quote a value that contains ' #'")
    if in_list and any(c in value for c in ",[]{}"):
        raise FrontmatterError(n, f"list item {value!r} needs quotes")
    return value


def inline_list(value, n):
    if not value.endswith("]"):
        raise FrontmatterError(n, "inline list must end with ]")
    inner = value[1:-1].strip()
    if not inner:
        return []
    items, buf, quote, i = [], "", None, 0
    while i < len(inner):
        c = inner[i]
        if quote == '"':
            buf += c
            if c == "\\":
                buf += inner[i + 1:i + 2]
                i += 1
            elif c == '"':
                quote = None
        elif quote == "'":
            buf += c
            if c == "'":
                if inner[i + 1:i + 2] == "'":
                    buf += "'"
                    i += 1
                else:
                    quote = None
        elif c in "\"'" and not buf.strip():
            quote = c
            buf += c
        elif c == ",":
            items.append(buf.strip())
            buf = ""
        else:
            buf += c
        i += 1
    if quote:
        raise FrontmatterError(n, "unclosed quote in list")
    items.append(buf.strip())
    if any(not it for it in items):
        raise FrontmatterError(n, "empty item in list")
    return [scalar(it, n, in_list=True) for it in items]


def needs_quote(s, in_list=False):
    if s == "":
        return in_list
    if s != s.strip() or s[0] in FIRST_SPECIAL:
        return True
    if ": " in s or s.endswith(":") or " #" in s:
        return True
    if s.lower() in BOOLISH:
        return True
    if NUMBERISH.match(s) and not PLAIN_INT.match(s) and not re.fullmatch(r"\d{4}-\d\d(-\d\d)?", s):
        return True
    if DATEISH.match(s):
        return True
    if in_list and any(c in s for c in ",[]{}"):
        return True
    return any(ord(c) < 32 or c in "  ﻿" for c in s)


def quote(s, in_list=False):
    if "\n" in s or "\r" in s:
        raise ValueError("values cannot contain line breaks")
    return json.dumps(s, ensure_ascii=False) if needs_quote(s, in_list) else s


def dump(meta, order=()):
    """Write meta as frontmatter (with the --- lines). Keys in `order` first, then the rest as given."""
    keys = [k for k in order if k in meta] + [k for k in meta if k not in order]
    out = ["---"]
    for k in keys:
        if not KEY_RE.fullmatch(k):
            raise ValueError(f"bad key {k!r}")
        v = meta[k]
        if v is None:
            v = ""
        if isinstance(v, (list, tuple)):
            items = [quote(str(x), in_list=True) for x in v]
            line = f"{k}: [{', '.join(items)}]"
            if len(line) <= 100 or not items:
                out.append(line)
            else:
                out.append(f"{k}:")
                out.extend(f"  - {quote(str(x))}" for x in v)
        else:
            v = quote(str(v))
            out.append(f"{k}: {v}" if v else f"{k}:")
    out.append("---")
    return "\n".join(out) + "\n"
