"""Photos of the owner (SPEC section 2, Photos). An original is kept as the owner gave it; an edit is
a recipe (which original, crop, adjustments, background) next to the image a tool made from it, so
the same photo can be fitted to a new audience without losing the original or the earlier edits.

    photos/<name>.jpg|png|webp     an original, never changed
    photos/edits/<name>.json       the recipe, so a tool can open the edit again
    photos/edits/<name>.jpg        the result, what CVs and other outputs use

The result is the edit; the recipe says how it was made, in values every editor can read, but
another editor need not reproduce it pixel for pixel. This module only stores and checks: the
pixels are a tool's job (the library stays standard library only).
"""

import json
import os
import re
import tempfile

FOLDER = "photos"
EDITS = "photos/edits"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
EXTS = ("jpg", "jpeg", "png", "webp")
FORMAT = "openself-photo-edit-1"
LARGE = 3_000_000  # bytes; every photo travels inside profile.age, with every version of it
ADJUST = ("brightness", "contrast", "saturation", "warmth", "sharpen")
BACKGROUNDS = ("keep", "color", "blur")
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def sniff(data):
    """The image type of some bytes from their first bytes: jpg, png, webp, or None."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def head(path, n=16):
    try:
        with open(path, "rb") as f:
            return f.read(n)
    except OSError:
        return b""


def split(fname):
    """('name', 'ext') of a file name, ext lowercased; ('', '') when it has no extension."""
    name, dot, ext = fname.rpartition(".")
    return (name, ext.lower()) if dot else ("", "")


def originals(root):
    """[{name, file, bytes}] of the originals, by name."""
    out = []
    d = os.path.join(root, FOLDER)
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        name, ext = split(f)
        if os.path.isfile(os.path.join(d, f)) and NAME_RE.match(name) and ext in EXTS:
            out.append({"name": name, "file": f"{FOLDER}/{f}", "bytes": os.path.getsize(os.path.join(d, f))})
    return out


def edits(root):
    """[{name, file, recipe, bytes}] of the edits, by name: file is the result ("" when it is
    missing), recipe the parsed JSON (None when it is missing or unreadable)."""
    d = os.path.join(root, EDITS)
    names = set()
    for f in os.listdir(d) if os.path.isdir(d) else []:
        name, ext = split(f)
        if NAME_RE.match(name) and ext in ("json", "jpg"):
            names.add(name)
    out = []
    for name in sorted(names):
        img = os.path.join(d, f"{name}.jpg")
        out.append({"name": name, "file": f"{EDITS}/{name}.jpg" if os.path.isfile(img) else "",
                    "recipe": read_recipe(root, name), "bytes": os.path.getsize(img) if os.path.isfile(img) else 0})
    return out


def files(root):
    """Every file under photos/, profile-relative (for fingerprints and checks)."""
    out = []
    base = os.path.join(root, FOLDER)
    for dirpath, dirs, names in os.walk(base):
        dirs[:] = sorted(x for x in dirs if not x.startswith("."))
        for n in sorted(names):
            if not n.startswith("."):
                out.append(os.path.relpath(os.path.join(dirpath, n), root).replace(os.sep, "/"))
    return out


def read_recipe(root, name):
    try:
        with open(os.path.join(root, EDITS, f"{name}.json"), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def number(v, lo, hi):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi


def check_recipe(recipe, root=None):
    """What is wrong with a recipe, as a list of messages (empty when it is fine). With root, the
    original it names must exist."""
    if not isinstance(recipe, dict):
        return ["not a JSON object"]
    out = []
    if recipe.get("format") != FORMAT:
        out.append(f"format must be {FORMAT}")
    photo = recipe.get("photo")
    if not isinstance(photo, str) or split(photo)[1] not in EXTS or not NAME_RE.match(split(photo)[0]):
        out.append("photo must name an original in photos/ (name.jpg, .png or .webp)")
    elif root is not None and not os.path.isfile(os.path.join(root, FOLDER, photo)):
        out.append(f"the original photos/{photo} is missing")
    crop = recipe.get("crop")
    if crop is not None:
        if not (isinstance(crop, dict) and all(number(crop.get(k), 0, 1) for k in ("x", "y", "w", "h"))
                and crop["w"] > 0 and crop["h"] > 0 and crop["x"] + crop["w"] <= 1.0001 and crop["y"] + crop["h"] <= 1.0001):
            out.append("crop is {x, y, w, h}, fractions of the original between 0 and 1")
    if "rotate" in recipe and not number(recipe["rotate"], -180, 180):
        out.append("rotate is degrees between -180 and 180")
    if "flip" in recipe and not isinstance(recipe["flip"], bool):
        out.append("flip is true or false")
    adjust = recipe.get("adjust", {})
    if not isinstance(adjust, dict):
        out.append("adjust is an object")
    else:
        for k, v in adjust.items():
            if k not in ADJUST:
                out.append(f"adjust.{k} is not known (" + ", ".join(ADJUST) + ")")
            elif not number(v, -100, 100):
                out.append(f"adjust.{k} is a number between -100 and 100")
    bg = recipe.get("background", {"mode": "keep"})
    if not isinstance(bg, dict) or bg.get("mode", "keep") not in BACKGROUNDS:
        out.append("background.mode is one of " + ", ".join(BACKGROUNDS))
    else:
        if "color" in bg and not (isinstance(bg["color"], str) and HEX_RE.match(bg["color"])):
            out.append("background.color is #rrggbb")
        for k, hi in (("tolerance", 100), ("soft", 100), ("blur", 100)):
            if k in bg and not number(bg[k], 0, hi):
                out.append(f"background.{k} is a number between 0 and {hi}")
        paint = bg.get("paint", [])
        if not isinstance(paint, list) or not all(
                isinstance(s, dict) and s.get("mode") in ("background", "keep") and number(s.get("size"), 0, 1)
                and isinstance(s.get("points"), list) and s["points"]
                and all(isinstance(p, list) and len(p) == 2 and all(number(v, -1, 2) for v in p) for p in s["points"])
                for s in paint):
            out.append('background.paint is a list of strokes {"mode": "background" or "keep", "size": 0 to 1, '
                       '"points": [[x, y], ...]}
    if "size" in recipe and not (isinstance(recipe["size"], int) and 64 <= recipe["size"] <= 4096):
        out.append("size is the long side in pixels, 64 to 4096")
    if "note" in recipe and not isinstance(recipe["note"], str):
        out.append("note is text")
    return out


def write_bytes(path, data):
    """Write bytes through a temporary file in the same folder, like write.write_atomic."""
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", dir=folder)
    try:
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(tmp, 0o666 & ~umask)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def taken(root):
    """Names in use by an original or an edit (an original and an edit may not share one, so a name
    always says which photo it is)."""
    return {p["name"] for p in originals(root)} | {e["name"] for e in edits(root)}


def add(root, data, name):
    """Store an original. Returns its profile-relative path. Refuses a name already in use: an
    original is never replaced, a new photo gets a new name."""
    kind = sniff(data)
    if kind is None:
        raise ValueError("not a JPEG, PNG or WebP image")
    if not NAME_RE.match(name or ""):
        raise ValueError("a photo name is lower-case letters, digits and -")
    if name in taken(root):
        raise FileExistsError(name)
    rel = f"{FOLDER}/{name}.{kind}"
    write_bytes(os.path.join(root, rel), data)
    return rel


def save_edit(root, name, recipe, jpeg):
    """Store an edit: its recipe and the JPEG made from it. An edit of the same name is replaced (it
    is the same edit, made again); its earlier versions stay in the history."""
    if not NAME_RE.match(name or ""):
        raise ValueError("an edit name is lower-case letters, digits and -")
    if name in {p["name"] for p in originals(root)}:
        raise FileExistsError(name)
    problems = check_recipe(recipe, root)
    if problems:
        raise ValueError("; ".join(problems))
    if sniff(jpeg) != "jpg":
        raise ValueError("the result must be a JPEG")
    write_bytes(os.path.join(root, EDITS, f"{name}.jpg"), jpeg)
    text = json.dumps(recipe, indent=2, ensure_ascii=False) + "\n"
    write_bytes(os.path.join(root, EDITS, f"{name}.json"), text.encode("utf-8"))
    return f"{EDITS}/{name}.jpg"


def remove(root, rel, in_use=()):
    """Delete an original or an edit (both files). The history keeps it. Refuses an original that an
    edit is made from, and anything in in_use (the person's photo field)."""
    if rel in in_use:
        raise ValueError(f"{rel} is the person's photo; choose another first")
    name, ext = split(rel.rsplit("/", 1)[-1])
    if rel.startswith(EDITS + "/") and ext == "jpg" and NAME_RE.match(name):
        for f in (f"{name}.jpg", f"{name}.json"):
            if os.path.exists(os.path.join(root, EDITS, f)):
                os.unlink(os.path.join(root, EDITS, f))
        return
    if rel.count("/") != 1 or not rel.startswith(FOLDER + "/") or ext not in EXTS or not os.path.isfile(os.path.join(root, rel)):
        raise FileNotFoundError(rel)
    users = [e["name"] for e in edits(root) if (e["recipe"] or {}).get("photo") == rel.split("/", 1)[1]]
    if users:
        raise ValueError(f"{rel} is the original of the edit{'s' if len(users) > 1 else ''} " + ", ".join(users))
    os.unlink(os.path.join(root, rel))


def check(root, photo=""):
    """[(level, where, field, message)] for the photos folder and the person's photo field."""
    out = []
    names = {}
    for rel in files(root):
        parts = rel.split("/")
        name, ext = split(parts[-1])
        if len(parts) == 2 and ext in EXTS and NAME_RE.match(name):
            kind = sniff(head(os.path.join(root, rel)))
            if kind is None or kind != {"jpeg": "jpg"}.get(ext, ext):
                out.append(("error", rel, "", "the file is not the image its extension says"))
            names.setdefault(name, []).append(rel)
        elif len(parts) == 3 and parts[1] == "edits" and ext in ("jpg", "json") and NAME_RE.match(name):
            if ext == "jpg" and sniff(head(os.path.join(root, rel))) != "jpg":
                out.append(("error", rel, "", "an edit's result must be a JPEG"))
            continue
        else:
            out.append(("warning", rel, "", "not a photo (photos/<name>.jpg|png|webp, or photos/edits/<name>.jpg|json; "
                                        "a name is lower-case letters, digits and -)"))
            continue
        if os.path.getsize(os.path.join(root, rel)) > LARGE:
            out.append(("warning", rel, "", f"over {LARGE // 1_000_000} MB; every version of it goes into each upload of "
                                        "profile.age, so a smaller copy (2000 px is plenty) is kinder"))
    for name, rels in names.items():
        if len(rels) > 1:
            out.append(("error", rels[0], "", "more than one original named " + name + ": " + ", ".join(rels)))
    for e in edits(root):
        where = f"{EDITS}/{e['name']}"
        if e["name"] in names:
            out.append(("error", where + ".json", "", f"an original is also named {e['name']}"))
        if not e["file"]:
            out.append(("warning", where + ".json", "", "a recipe without its result (the .jpg); open it in an editor and save again"))
        if e["recipe"] is None:
            if os.path.exists(os.path.join(root, where + ".json")):
                out.append(("error", where + ".json", "", "not readable JSON"))
            else:
                out.append(("warning", where + ".jpg", "", "a result without its recipe, so it cannot be edited again"))
        else:
            for msg in check_recipe(e["recipe"], root):
                out.append(("error", where + ".json", "", msg))
    if photo and not os.path.isfile(os.path.join(root, photo)):
        out.append(("error", "person", "photo", f"{photo} does not exist"))
    return out
