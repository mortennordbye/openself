import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXAMPLE = os.path.join(ROOT, "example")
sys.path.insert(0, ROOT)

from openself import importer, model  # noqa: E402
from openself.web import api  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
           "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "gc.auto", "GIT_CONFIG_VALUE_0": "0",
           "GIT_CONFIG_KEY_1": "maintenance.auto", "GIT_CONFIG_VALUE_1": "false"}

CREDLY_URL = "https://www.credly.com/users/ola-eksempel"
MSLEARN_URL = "https://learn.microsoft.com/nb-no/users/olaeksempel-1234/transcript/abc123xyz"
# Shaped like the real answers, with made-up content.
CREDLY = {
    "https://www.credly.com/users/ola-eksempel/badges.json": {
        "data": [
            {"state": "accepted", "issued_at_date": "2023-05-02", "expires_at_date": "2026-05-02",
             "badge_template": {"name": "CKA: Certified Kubernetes Administrator"}, "issuer": {"entities": [{"entity": {"name": "The Linux Foundation"}}]}},
            {"state": "pending", "issued_at_date": "2024-01-01", "badge_template": {"name": "Not accepted yet"}, "issuer": {"entities": []}},
        ],
        "metadata": {"next_page_url": "https://www.credly.com/users/ola-eksempel/badges.json?page=2"}},
    "https://www.credly.com/users/ola-eksempel/badges.json?page=2": {
        "data": [{"state": "accepted", "issued_at_date": "2022-03-04", "expires_at_date": None,
                  "badge_template": {"name": "Fictional Cloud Basics"}, "issuer": {"entities": [{"entity": {"name": "Eksempel Academy"}}]}}],
        "metadata": {"next_page_url": None}},
}
MSLEARN = {"https://learn.microsoft.com/api/profiles/transcript/share/abc123xyz?locale=en-us": {
    "contactEmail": "ola@example.invalid", "certificationData": {
        "legalName": "Ola Eksempel",
        "activeCertifications": [
            {"name": "Microsoft Certified: Azure Administrator Associate", "dateEarned": "2021-11-20T10:00:00+00:00", "expiration": "2027-11-20T23:59:59+00:00"},
            {"name": "GitHub Actions", "dateEarned": "2025-06-01T10:00:00+00:00", "expiration": "2027-06-01T23:59:59+00:00"}],
        "historicalCertifications": [],
        "passedExams": [{"examNumber": "AZ-104", "examTitle": "Microsoft Azure Administrator", "examDateTaken": "2021-11-20T10:00:00+00:00"}]}}}
PAGES = dict(CREDLY, **MSLEARN)


def fake_get(url):
    return PAGES[url]


class Import(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "profile")
        shutil.copytree(EXAMPLE, self.root)

    def read(self):
        with open(os.path.join(self.root, "certifications.md"), encoding="utf-8") as f:
            return f.read()

    def entry(self):
        return model.load_profile(self.root).entries["certifications"]

    def test_links(self):
        self.assertEqual(importer.source_of(CREDLY_URL + "/badges"), ("credly", "ola-eksempel"))
        self.assertEqual(importer.source_of(MSLEARN_URL), ("mslearn", "abc123xyz"))
        for bad in ("http://www.credly.com/users/x", "https://evil.example/users/x", "https://credly.com.evil.example/users/x",
                    "https://learn.microsoft.com/en-us/users/x/achievements", ""):
            with self.assertRaises(ValueError):
                importer.source_of(bad)

    def test_credly_pages_and_states(self):
        certs, src = importer.fetch(CREDLY_URL, fake_get)
        self.assertEqual(src, "credly")
        self.assertEqual([c.name for c in certs], ["CKA: Certified Kubernetes Administrator", "Fictional Cloud Basics"])
        self.assertEqual((certs[0].issuer, certs[0].date, certs[0].expires), ("The Linux Foundation", "2023-05-02", "2026-05-02"))

    def test_mslearn_certifications_not_exams_or_personal_data(self):
        certs, _ = importer.fetch(MSLEARN_URL, fake_get)
        self.assertEqual([(c.name, c.issuer, c.date) for c in certs],
                         [("Microsoft Certified: Azure Administrator Associate", "Microsoft", "2021-11-20"), ("GitHub Actions", "GitHub", "2025-06-01")])
        text, _ = importer.merge(self.entry(), certs, "mslearn", "nb", today="2026-10-20")
        self.assertNotIn("example.invalid", text)
        self.assertNotIn("Ola Eksempel", text)

    def test_names_match_across_spellings(self):
        self.assertGreater(importer.score("Microsoft Certified: Azure Administrator Associate", "Azure Administrator Associate (AZ-104)"), 0)
        self.assertGreater(importer.score("CKA: Certified Kubernetes Administrator", "Certified Kubernetes Administrator (CKA)"), 0)
        self.assertGreater(importer.score("GitHub Copilot", "GitHub Copilot Certification"), 0)
        self.assertEqual(importer.score("Azure Solutions Architect Expert", "Azure Administrator Associate (AZ-104)"), 0)
        self.assertEqual(importer.score("Azure", "Azure Administrator Associate"), 0)

    def test_merge_fills_adds_and_flags(self):
        certs, _ = importer.fetch(MSLEARN_URL, fake_get)
        text, s = importer.merge(self.entry(), certs, "mslearn", "nb", today="2026-10-20")
        rows = model.parse_table(model.load_entry("certifications.md", text).body)
        az = next(r for r in rows if r[0].startswith("Azure Administrator"))
        # 2021-11 in the table and 2021-11-20 from the page agree: the date gets exact, the expiry is filled in.
        self.assertEqual(az[2:4], ["2021-11-20", "2027-11-20"])
        self.assertEqual(len(az), 4)  # no source column: the profile is the source
        self.assertEqual([a["name"] for a in s["added"]], ["GitHub Actions"])
        self.assertEqual(s["conflicts"], [])
        # The example's CKA row says 2023-05 to 2026-05; a page saying another month is a conflict, not an overwrite.
        other = [importer.Cert("CKA: Certified Kubernetes Administrator", "The Linux Foundation", "2023-07-01", "2026-05-02")]
        text2, s2 = importer.merge(self.entry(), other, "credly", "nb", today="2026-10-20")
        cka = next(r for r in model.parse_table(model.load_entry("certifications.md", text2).body) if "CKA" in r[0])
        self.assertEqual(cka[2], "2023-05")
        self.assertEqual(cka[3], "2026-05-02")
        self.assertEqual(len(s2["conflicts"]), 1)
        self.assertIn("- ⚑ konflikt: Credly sier at datoen for «Certified Kubernetes Administrator (CKA)» er 2023-07-01; tabellen sier 2023-05.", text2)
        self.assertEqual(model.load_entry("certifications.md", text2).error, "")

    def test_confirmed_row_is_unchanged(self):
        # A page that lists a row exactly as the table has it changes nothing.
        same = [importer.Cert("CKA: Certified Kubernetes Administrator", "The Linux Foundation", "2023-05", "2026-05")]
        text, s = importer.merge(self.entry(), same, "credly", "nb", today="2026-10-20")
        self.assertEqual((s["updated"], s["unchanged"]), ([], 1))
        self.assertEqual(text, self.entry().text)

    def test_merge_again_changes_nothing(self):
        certs, _ = importer.fetch(CREDLY_URL, fake_get)
        text, _ = importer.merge(self.entry(), certs, "credly", "en", today="2026-10-20")
        again, s = importer.merge(model.load_entry("certifications.md", text), certs, "credly", "en", today="2026-10-21")
        self.assertEqual(again, text)
        self.assertEqual((s["added"], s["updated"], s["conflicts"], s["unchanged"]), ([], [], [], 2))

    def test_api_preview_then_import_and_commit(self):
        subprocess.run(["git", "init", "-q", "-b", "main", self.root], check=True, env=dict(os.environ, **GIT_ENV))
        subprocess.run(["git", "-C", self.root, "add", "-A"], check=True, env=dict(os.environ, **GIT_ENV))
        subprocess.run(["git", "-C", self.root, "commit", "-qm", "start"], check=True, env=dict(os.environ, **GIT_ENV))
        before = self.read()
        with mock.patch.dict(os.environ, GIT_ENV), mock.patch.object(importer, "get_json", fake_get):
            st, j = api.import_(self.root, {"urls": [MSLEARN_URL, CREDLY_URL], "dry_run": True})
            self.assertEqual((st, j["ok"], j["changed"]), (200, True, True))
            self.assertEqual(self.read(), before)
            st, j = api.import_(self.root, {"urls": [MSLEARN_URL, CREDLY_URL]})
            self.assertEqual((st, j["ok"]), (200, True))
            st, j = api.import_(self.root, {"urls": []})  # the stored links, a second time: nothing new
            self.assertEqual((st, j["changed"]), (200, False))
            st, j = api.import_(self.root, {"urls": ["https://evil.example/x"]})
            self.assertEqual(st, 400)
        e = self.entry()
        self.assertEqual(e.meta["imports"], [MSLEARN_URL, CREDLY_URL])
        log = subprocess.run(["git", "-C", self.root, "log", "--format=%s", "-1"], capture_output=True, text=True).stdout.strip()
        self.assertEqual(log, "certifications: imported from Microsoft Learn, Credly [owner]")

    def test_network_failure_is_reported(self):
        def down(url):
            raise OSError("no network")
        with mock.patch.object(importer, "get_json", down):
            st, j = api.import_(self.root, {"urls": [CREDLY_URL], "dry_run": True})
        self.assertEqual(st, 502)
        self.assertIn("no network", j["message"])

    def test_one_page_down_does_not_stop_the_other(self):
        def half(url):
            if "credly" in url:
                raise OSError("credly is down")
            return fake_get(url)
        with mock.patch.object(importer, "get_json", half):
            st, j = api.import_(self.root, {"urls": [CREDLY_URL, MSLEARN_URL], "dry_run": True})
        self.assertEqual((st, j["changed"]), (200, True))
        self.assertEqual([(r["source"], r.get("error", "")) for r in j["results"]], [("credly", "credly is down"), ("mslearn", "")])


if __name__ == "__main__":
    unittest.main()
