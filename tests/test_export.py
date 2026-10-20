import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.dirname(HERE)
EXAMPLE = os.path.join(SPEC, "example")
sys.path.insert(0, SPEC)

from openself import export, model  # noqa: E402

NDA = """---
schema: 1
id: 2020-01-hemmelig-kunde-utvikler
type: assignment
kind: client
employment: 2017-08-nordlys-drift-driftstekniker
customer: Hemmelig Kunde AS
customers: []
customer_public: nda
customer_alias:
sector: forsvar
role: Utvikler
start: 2020-01
end: 2020-06
tech: [Kubernetes, Rust]
confidence: stated
status: active
last_reviewed: 2026-09-14
---

## Hva oppdraget var

Noe vi ikke kan snakke om.
"""


class PublicView(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        shutil.copytree(EXAMPLE, self.dir, dirs_exist_ok=True)
        with open(os.path.join(self.dir, "assignments", "2020-01-hemmelig-kunde-utvikler.md"), "w", encoding="utf-8") as f:
            f.write(NDA)
        self.profile = model.load_profile(self.dir)
        self.view = export.public_view(self.profile)
        self.text = json.dumps(self.view, ensure_ascii=False)

    def test_nda_assignment_left_out(self):
        self.assertNotIn("hemmelig", self.text.lower())
        self.assertNotIn("Noe vi ikke kan snakke om", self.text)
        rust = next(t for t in self.view["tech"] if t["name"] == "Rust")
        self.assertEqual(rust["entries"], [])  # counted as experience, but no hidden entry to point at
        self.assertEqual(rust["assignments"], 1)

    def test_anonymised_customer_never_named(self):
        a = next(a for a in self.view["assignments"] if a["id"] == "2021-04-vestkraft-skymigrering")
        self.assertEqual(a["customer"], "et regionalt kraftselskap")
        self.assertNotIn("vestkraft", a["slug"])
        self.assertEqual(a["slug"], "2021-04-skyarkitekt")
        public = {k: v for k, v in a.items() if k != "id"}
        self.assertEqual(export.leaks(json.dumps(public, ensure_ascii=False), self.profile), [])

    def test_reference_flags_and_own_words_never_copied(self):
        self.assertNotIn("Kari Fiktiv", self.text)
        self.assertNotIn("⚑", self.text)
        ids = {s["id"] for e in self.view["employments"] + self.view["assignments"] for s in e["sections"]}
        self.assertLessEqual(ids, {"summary", "challenge", "contribution", "outcome"})

    def test_omit_keeps_facts_drops_text(self):
        e = next(e for e in self.view["employments"] if e["id"] == "2017-08-nordlys-drift-driftstekniker")
        self.assertTrue(e["omit"])
        self.assertEqual(e["sections"], [])
        self.assertEqual(e["title"], "Driftstekniker")
        self.assertIn("Linux", e["tech"])

    def test_removed_entries_left_out(self):
        self.assertNotIn("fjordsky-pilot", self.text)

    def test_leaks_finds_hidden_values(self):
        self.assertEqual(export.leaks("<p>Worked for Vestkraft AS</p>", self.profile), ["Vestkraft AS"])
        self.assertIn("Hemmelig Kunde AS", export.leaks("hemmelig kunde as", self.profile))
        self.assertEqual(export.leaks("<p>Worked for a power company</p>", self.profile), [])

    def test_public_elsewhere_is_not_hidden(self):
        # A portfolio entry keeps its list anonymised, but one of its customers is named in an entry of its own.
        with open(os.path.join(self.dir, "assignments", "2018-01-eksempel-bygg-driftstekniker.md"), "w", encoding="utf-8") as f:
            f.write(NDA.replace("2020-01-hemmelig-kunde-utvikler", "2018-01-eksempel-bygg-driftstekniker")
                    .replace("Hemmelig Kunde AS", "Eksempel Bygg AS").replace("customer_public: nda", "customer_public: public"))
        profile = model.load_profile(self.dir)
        self.assertNotIn("Eksempel Bygg AS", export.hidden(profile))
        self.assertIn("Fiktiv Regnskap AS", export.hidden(profile))

    def test_tables(self):
        self.assertEqual(self.view["certifications"][0]["name"], "Certified Kubernetes Administrator (CKA)")
        self.assertEqual(set(self.view["education"][0]), {"degree", "school", "from", "to"})

    def test_cli(self):
        out = subprocess.run([sys.executable, "-m", "openself", "export", self.dir], cwd=SPEC,
                             capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out)["format"], "openself-public-1")


if __name__ == "__main__":
    unittest.main()
