import base64
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.dirname(HERE)
EXAMPLE = os.path.join(SPEC, "example")
sys.path.insert(0, SPEC)

from openself import export, lint, model, photos  # noqa: E402
from openself.web import api  # noqa: E402


def png(w=4, h=4):
    raw = b"".join(b"\x00" + b"\x80\x90\xa0" * w for _ in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


GIT_ENV = {"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
           "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32 + b"\xff\xd9"  # enough for the type check
RECIPE = {"format": photos.FORMAT, "photo": "studio.png", "crop": {"x": 0.1, "y": 0, "w": 0.8, "h": 0.9},
          "rotate": -2.5, "adjust": {"brightness": 10, "warmth": -5}, "background": {"mode": "color", "color": "#e8edf2",
          "tolerance": 30, "soft": 4}, "size": 800, "note": "lighter, for the bank"}


class Photos(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        shutil.copytree(EXAMPLE, self.dir, dirs_exist_ok=True)
        patch = mock.patch.dict(os.environ, GIT_ENV)
        patch.start()
        self.addCleanup(patch.stop)
        subprocess.run(["git", "init", "-q", self.dir], check=True)
        subprocess.run(["git", "-C", self.dir, "add", "-A"], check=True)
        subprocess.run(["git", "-C", self.dir, "commit", "-qm", "init"], check=True)

    def issues(self):
        return [i for i in lint.lint(model.load_profile(self.dir)) if i.level != "prompt" and i.id != "INDEX"]

    def test_add_edit_use(self):
        self.assertEqual(photos.add(self.dir, png(), "studio"), "photos/studio.png")
        with self.assertRaises(FileExistsError):
            photos.add(self.dir, png(), "studio")  # an original is never replaced
        with self.assertRaises(ValueError):
            photos.add(self.dir, b"GIF89a....", "other")
        code, body = api.photo_save(self.dir, {"name": "cv", "recipe": RECIPE, "use": True,
                                               "data": "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()})
        self.assertEqual(code, 200, body)
        self.assertEqual(body["file"], "photos/edits/cv.jpg")
        p = model.load_profile(self.dir)
        self.assertEqual(p.entries["person"].get("photo"), "photos/edits/cv.jpg")
        self.assertEqual(export.public_view(p)["person"]["photo"], "photos/edits/cv.jpg")
        with open(os.path.join(self.dir, "photos", "edits", "cv.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["note"], "lighter, for the bank")
        log = subprocess.run(["git", "-C", self.dir, "log", "--format=%s"], capture_output=True, text=True).stdout
        self.assertIn("photos: edit cv saved, now the photo [owner]", log)
        self.assertEqual(self.issues(), [])
        _, listed = api.photo_list(self.dir)
        self.assertEqual([e["name"] for e in listed["edits"]], ["cv"])
        self.assertEqual(listed["edits"][0]["recipe"]["photo"], "studio.png")

    def test_remove_refuses_what_is_in_use(self):
        photos.add(self.dir, png(), "studio")
        photos.save_edit(self.dir, "cv", RECIPE, JPEG)
        api.photo_use(self.dir, {"file": "photos/edits/cv.jpg"})
        self.assertEqual(api.photo_remove(self.dir, {"file": "photos/studio.png"})[0], 400)  # cv is made from it
        self.assertEqual(api.photo_remove(self.dir, {"file": "photos/edits/cv.jpg"})[0], 400)  # the person's photo
        api.photo_use(self.dir, {"file": ""})
        self.assertEqual(api.photo_remove(self.dir, {"file": "photos/edits/cv.jpg"})[0], 200)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "photos", "edits", "cv.json")))
        self.assertEqual(api.photo_remove(self.dir, {"file": "photos/studio.png"})[0], 200)
        self.assertEqual(api.photo_remove(self.dir, {"file": "../person.md"})[0], 404)

    def test_recipe_checks(self):
        self.assertEqual(photos.check_recipe(RECIPE), [])
        bad = dict(RECIPE, crop={"x": 0.5, "y": 0, "w": 0.8, "h": 1}, adjust={"glow": 3}, background={"mode": "sky"})
        self.assertEqual(len(photos.check_recipe(bad)), 3)
        with self.assertRaises(ValueError):
            photos.save_edit(self.dir, "cv", RECIPE, JPEG)  # the original is missing
        photos.add(self.dir, png(), "studio")
        with self.assertRaises(ValueError):
            photos.save_edit(self.dir, "cv", RECIPE, png())  # the result must be a JPEG
        with self.assertRaises(FileExistsError):
            photos.save_edit(self.dir, "studio", RECIPE, JPEG)  # a name says which photo it is

    def test_lint(self):
        os.makedirs(os.path.join(self.dir, "photos", "edits"))
        for rel, data in (("photos/fake.jpg", b"not an image"), ("photos/Notes.txt", b"x"),
                          ("photos/edits/old.jpg", JPEG)):
            with open(os.path.join(self.dir, rel), "wb") as f:
                f.write(data)
        with open(os.path.join(self.dir, "person.md"), encoding="utf-8") as f:
            text = f.read().replace("photo:\n", "photo: photos/gone.jpg\n")
        with open(os.path.join(self.dir, "person.md"), "w", encoding="utf-8") as f:
            f.write(text)
        found = {(i.level, i.id, i.field) for i in self.issues()}
        self.assertEqual(found, {("error", "photos/fake.jpg", ""), ("warning", "photos/Notes.txt", ""),
                                 ("warning", "photos/edits/old.jpg", ""), ("error", "person", "photo")})

    def test_photo_changes_the_version(self):
        before = model.version(self.dir)
        photos.add(self.dir, png(), "studio")
        self.assertNotEqual(model.version(self.dir), before)


if __name__ == "__main__":
    unittest.main()
