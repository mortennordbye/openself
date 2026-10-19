import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.dirname(HERE)
EXAMPLE = os.path.join(SPEC, "example")
sys.path.insert(0, SPEC)

from openself import frontmatter, history, index, lint, model, schema, write  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
           "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

try:
    import yaml
except ImportError:
    yaml = None

TRICKY = ["no", "on", "Yes", "~", "null", "#1", "a: b", "a #b", "- x", "[x]", "{x}", "'q'", '"q"',
          "1.5", "010", "0x1f", "1e3", "2024", "2024-02", "2026-10-19", "2026-10-19 12:00",
          "Rådgiver: drift", "æøå ÆØÅ", "emoji 🚀", "C#", ".NET", "tab\there", "back\\slash",
          "ends with colon:", " padded ", "%x", "@x", "`x`", "?", "=", ".inf"]


def entry_text(**meta):
    return write.render(meta, "", meta.get("type", "assignment"))


class Frontmatter(unittest.TestCase):
    def test_round_trip_tricky_values(self):
        for v in TRICKY:
            with self.subTest(v=v):
                text = frontmatter.dump({"a": v, "b": [v, "x"]})
                meta, _ = frontmatter.parse(text + "body")
                self.assertEqual(meta, {"a": v, "b": [v, "x"]})

    @unittest.skipIf(yaml is None, "PyYAML not installed")
    def test_dump_is_yaml_read_as_strings(self):
        for v in TRICKY:
            with self.subTest(v=v):
                text = frontmatter.dump({"a": v, "b": [v, "x"], "c": "", "d": []})
                self.assertEqual(yaml.load(text.split("---\n")[1], Loader=yaml.BaseLoader),
                                 {"a": v, "b": [v, "x"], "c": "", "d": []})

    @unittest.skipIf(yaml is None, "PyYAML not installed")
    def test_example_files_read_the_same_with_yaml(self):
        p = model.load_profile(EXAMPLE)
        for e in list(p.entries.values()) + list(p.removed.values()):
            with self.subTest(e=e.rel):
                theirs = yaml.load("\n".join(frontmatter.split(e.text)[0]), Loader=yaml.BaseLoader)
                self.assertEqual(theirs, e.meta)

    def test_block_list_and_empty(self):
        meta, body = frontmatter.parse("---\na:\n  - x\n  - \"y: z\"\nb:\nc: []\n---\nhello\n")
        self.assertEqual(meta, {"a": ["x", "y: z"], "b": "", "c": []})
        self.assertEqual(body, "hello\n")

    def test_no_frontmatter(self):
        self.assertEqual(frontmatter.parse("just text\n"), ({}, "just text\n"))

    def test_rejects(self):
        bad = {
            "---\na: b\n": "never ends",
            "---\na: b: c\n---\n": "contains ': '",
            "---\na:\n  b: c\n---\n": "nested",
            "---\na: b # comment\n---\n": "comments",
            "---\na: |\n  x\n---\n": "needs quotes",
            "---\na: b\na: c\n---\n": "twice",
            "---\nA: b\n---\n": "expected",
            "---\na:b\n---\n": "space after",
            "---\n- x\n---\n": "without a list key",
            "---\na: [x, y\n---\n": "must end",
            "---\na: \"x\" y\n---\n": "after the closing quote",
            "---\na: &anchor x\n---\n": "needs quotes",
        }
        for text, msg in bad.items():
            with self.subTest(text=text):
                with self.assertRaises(frontmatter.FrontmatterError) as cm:
                    frontmatter.parse(text)
                self.assertIn(msg, str(cm.exception))
                self.assertTrue(str(cm.exception).startswith("line "))

    def test_refuses_newlines(self):
        with self.assertRaises(ValueError):
            frontmatter.dump({"a": "x\ny"})

    def test_long_list_goes_block(self):
        text = frontmatter.dump({"a": ["word %d" % i for i in range(20)]})
        self.assertIn("a:\n  - word 0\n", text)


class Model(unittest.TestCase):
    def test_example_loads_cleanly(self):
        p = model.load_profile(EXAMPLE)
        self.assertEqual(p.errors, [])
        self.assertEqual(len(p.of_type("assignment")), 4)
        self.assertEqual(len(p.of_type("employment")), 2)
        self.assertEqual(list(p.removed), ["2021-03-fjordsky-pilot"])
        self.assertEqual(p.lang, "nb")

    def test_sections_map_labels_in_any_language(self):
        body = "intro\n\n## Eget bidrag\n\nA\n\n## Outcome\n\nB\n\n```\n## not a heading\n```\n\n## Odd one\n\nC\n"
        secs = model.sections(body, "assignment")
        self.assertEqual([s.id for s in secs], ["_intro", "contribution", "outcome", "odd-one"])
        self.assertIn("## not a heading", secs[2].text)
        self.assertFalse(secs[3].known)
        back = model.join_sections(secs, "assignment", "nb")
        self.assertIn("## Resultat\n\nB", back)
        self.assertTrue(back.index("Eget bidrag") < back.index("Resultat") < back.index("Odd one"))

    def test_flags_both_languages_and_bad_ones(self):
        body = ("- ⚑ question: a\n  - ⚑ spørsmål: b\n- ⚑ konflikt (løst 2026-01-02): c\n"
                "- ⚑ vekt: d\n- ⚑ wish: e\n- ⚑ no colon\n```\n- ⚑ in code\n```\n")
        fl, bad = model.flags(body)
        self.assertEqual([(f.type, f.open) for f in fl],
                         [("question", True), ("question", True), ("conflict", False), ("emphasis", False)])
        self.assertEqual([b[0] for b in bad], [5, 6])

    def test_resolve_flag(self):
        body = "## Flagg\n\n- ⚑ spørsmål: Hvor mange?\n"
        out = model.resolve_flag(body, "- ⚑ spørsmål: Hvor mange?", "Fire,  tror jeg", "nb", "2026-10-19")
        self.assertIn("- ⚑ spørsmål (løst 2026-10-19): Hvor mange? Svar: «Fire, tror jeg»", out)
        fl, bad = model.flags(out)
        self.assertFalse(fl[0].open)
        self.assertEqual(bad, [])
        with self.assertRaises(ValueError):
            model.resolve_flag(out, "- ⚑ spørsmål: Hvor mange?", "x", "nb")

    def test_table(self):
        rows = model.parse_table(model.dump_table([["a|b", "c"], ["d"]], ["X", "Y"]))
        self.assertEqual(rows, [["a/b", "c"], ["d", ""]])

    def test_months_and_breaks(self):
        e = model.Entry("x", "employment", "", "", meta={"start": "2020-01", "end": "2020-12", "breaks": ["2020-03/2020-04"]})
        self.assertEqual(len(model.months(e)), 10)
        self.assertEqual(len(model.months(e, with_breaks=True)), 12)
        e.meta["end"] = "ongoing"
        self.assertEqual(len(model.months(e, ongoing_until="2020-06")), 4)

    def test_normalize(self):
        nfd = unicodedata.normalize("NFD", "å  \r\nb")
        self.assertEqual(model.normalize_text(nfd), "å\nb\n")


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "profile")
        self.old_env = dict(os.environ)
        os.environ.update(GIT_ENV)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)
        shutil.rmtree(self.tmp)

    def copy_example(self, git=True):
        shutil.copytree(EXAMPLE, self.root)
        if git:
            subprocess.run(["git", "init", "-q", self.root], check=True)
            history.commit(self.root, history.message("profile", "start", "tool"))


class WriteTests(Tmp):
    def test_slug_and_ids(self):
        self.assertEqual(write.slugify("Rådgiver Øst & Sør"), "radgiver-ost-sor")
        self.assertEqual(write.new_id(set(), "2024-02-15", "Acme Transport AS", "Platform engineer"), "2024-02-acme-transport-as-platform-engineer")
        taken = {"2024-02-a-b", "2024-02-a-b-2"}
        self.assertEqual(write.new_id(taken, "2024-02", "a", "b"), "2024-02-a-b-3")

    def test_scaffold_never_reuses_removed_ids(self):
        self.copy_example(git=False)
        id_ = write.scaffold(self.root, "assignment", {"kind": "client", "start": "2021-03", "customer": "fjordsky", "role": "pilot"})
        self.assertEqual(id_, "2021-03-fjordsky-pilot-2")
        e = model.load_profile(self.root).entries[id_]
        self.assertEqual(e.get("customer_public"), "unknown")
        self.assertEqual(e.error, "")

    def test_scaffold_internal_and_given_review_date(self):
        self.copy_example(git=False)
        id_ = write.scaffold(self.root, "assignment", {"kind": "internal", "start": "2024-01", "role": "dev",
                                                       "last_reviewed": "2026-01-02"})
        e = model.load_profile(self.root).entries[id_]
        self.assertEqual((e.get("customer_public"), e.get("last_reviewed")), ("", "2026-01-02"))

    def test_nda_customer_stays_out_of_id(self):
        self.copy_example(git=False)
        id_ = write.scaffold(self.root, "assignment", {"kind": "client", "start": "2024-01", "customer": "Secret Bank",
                                                       "customer_public": "nda", "customer_alias": "en bank", "role": "arkitekt"})
        self.assertEqual(id_, "2024-01-en-bank-arkitekt")

    def test_save_conflict_and_round_trip(self):
        self.copy_example(git=False)
        id_ = "2021-04-vestkraft-skymigrering"
        e = model.load_profile(self.root).entries[id_]
        meta = dict(e.meta, role="Skyarkitekt: lead")
        text = write.save(self.root, id_, meta, e.body, e.sha, today="2026-10-19")
        again = model.load_profile(self.root).entries[id_]
        self.assertEqual(again.get("role"), "Skyarkitekt: lead")
        self.assertEqual(again.get("last_reviewed"), "2026-10-19")
        self.assertEqual(again.text, text)
        with self.assertRaises(write.Conflict) as cm:
            write.save(self.root, id_, meta, e.body, e.sha)
        self.assertEqual(cm.exception.current_text, text)
        with self.assertRaises(ValueError):
            write.save(self.root, id_, dict(meta, id="other"), e.body, again.sha)

    def test_write_atomic_new_file_must_not_exist(self):
        path = os.path.join(self.tmp, "x.md")
        write.write_atomic(path, "a", expected_sha="")
        with self.assertRaises(write.Conflict):
            write.write_atomic(path, "b", expected_sha="")
        self.assertEqual(oct(os.stat(path).st_mode & 0o777), oct(0o666 & ~current_umask()))
        self.assertEqual([f for f in os.listdir(self.tmp) if f.startswith(".")], [])

    def test_remove(self):
        self.copy_example(git=False)
        id_ = "2022-01-intern-plattformkode"
        write.remove(self.root, id_, "  feil\n oppføring ", today="2026-10-19")
        p = model.load_profile(self.root)
        self.assertNotIn(id_, p.entries)
        self.assertEqual(p.removed[id_].get("removed_reason"), "feil oppføring")
        self.assertEqual([i for i in lint.lint(p, today="2026-10-19") if i.level == "error"], [])
        with self.assertRaises(FileNotFoundError):
            write.remove(self.root, id_, "again")

    def test_init_and_fmt_idempotent(self):
        write.init(self.root, "Kari", ["en"], git=False)
        p = model.load_profile(self.root)
        self.assertEqual(sorted(p.entries), ["certifications", "education", "person"])
        self.assertEqual([i for i in lint.lint(p) if i.level != "prompt"], [])
        from openself.__main__ import fmt
        self.assertEqual(fmt(self.root, check=True), 0)

    def test_example_is_canonical(self):
        from openself.__main__ import fmt
        self.assertEqual(fmt(EXAMPLE, check=True), 0)


class IndexAndLint(Tmp):
    def test_example_index_is_current_and_deterministic(self):
        p = model.load_profile(EXAMPLE)
        self.assertFalse(index.stale(p))
        self.assertEqual(index.build_index(p), p.generated["INDEX.md"])
        self.assertEqual(index.build_index(p), index.build_index(model.load_profile(EXAMPLE)))

    def test_index_hides_names_that_may_not_be_named(self):
        text = model.load_profile(EXAMPLE).generated["INDEX.md"]
        self.assertIn("et regionalt kraftselskap", text)
        self.assertNotIn("Vestkraft AS", text)
        self.assertNotIn("Fiktiv Regnskap", text)
        self.assertIn("Statens testverk", text)

    def test_example_lints_clean(self):
        issues = lint.lint(model.load_profile(EXAMPLE), today="2026-10-19")
        self.assertEqual([str(i) for i in issues if i.level != "prompt"], [])
        prompts = [i.message for i in issues]
        self.assertIn("conflict: Gammel CV sier 50 servere, intervjuet sier rundt 60.", prompts)

    def lint_with(self, rel, meta=None, body=None, text=None):
        self.copy_example(git=False)
        path = os.path.join(self.root, rel)
        if text is None:
            with open(path, encoding="utf-8") as f:
                e = model.load_entry(rel, f.read())
            m = dict(e.meta, **(meta or {}))
            text = write.render(m, body if body is not None else e.body, model.type_for(rel))
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        index.write_all(self.root)
        return [(i.level, i.id, i.field, i.message) for i in lint.lint(model.load_profile(self.root), today="2026-10-19")]

    def has(self, issues, level, field, words):
        return any(lv == level and f == field and words in msg for lv, _, f, msg in issues)

    def test_rules(self):
        a = "assignments/2021-04-vestkraft-skymigrering.md"
        cases = [
            ({"end": "2020-01"}, "error", "end", "ends before"),
            ({"employment": "nope-nope"}, "error", "employment", "no employment"),
            ({"kind": "freelance"}, "error", "kind", "must be one of"),
            ({"start": "2021-13"}, "error", "start", "wrong format"),
            ({"allocation": "lots"}, "error", "allocation", "wrong format"),
            ({"breaks": ["2022-05/2022-01"]}, "error", "breaks", "bad break"),
            ({"tech": ["k8s"]}, "warning", "tech", "use 'Kubernetes'"),
            ({"tech": ["Frobnicator"]}, "warning", "tech", "not a canonical"),
            ({"start": "2020-01"}, "warning", "start", "outside employment"),
            ({"allocation": "90"}, "warning", "allocation", "110%"),
            ({"customer_public": "unknown"}, "prompt", "customer_public", "may the customer"),
            ({"confidence": "needs-confirmation"}, "prompt", "confidence", "needs confirmation"),
            ({"team_size": ""}, "prompt", "team_size", "not given"),
            ({"last_reviewed": "2024-01-01"}, "prompt", "last_reviewed", "18 months"),
            ({"start": "2021"}, "prompt", "start", "only the year"),
            ({"x-cvtool-hide": "yes"}, None, None, None),
            ({"surprise": "x"}, "error", "surprise", "unknown field"),
            ({"status": "removed"}, "error", "status", "not in _removed"),
        ]
        for meta, level, field, words in cases:
            with self.subTest(meta=meta):
                issues = self.lint_with(a, meta)
                shutil.rmtree(self.root)
                if level is None:
                    self.assertEqual([i for i in issues if i[0] == "error"], [])
                else:
                    self.assertTrue(self.has(issues, level, field, words), issues)

    def test_body_rules(self):
        a = "assignments/2021-04-vestkraft-skymigrering.md"
        issues = self.lint_with(a, body="## Eget bidrag\n\n\n## Something else\n\nx\n\n- ⚑ hmm: y\n")
        self.assertTrue(self.has(issues, "prompt", "", "no own contribution"))
        self.assertTrue(self.has(issues, "warning", "", "unknown section heading"))
        self.assertTrue(self.has(issues, "error", "", "malformed flag"))

    def test_parse_error_and_id_mismatch(self):
        issues = self.lint_with("assignments/2021-04-vestkraft-skymigrering.md", text="---\na: b: c\n---\n")
        self.assertTrue(any(lv == "error" and "line 2" in msg for lv, _, _, msg in issues))
        shutil.rmtree(self.root)
        issues = self.lint_with("assignments/2021-04-vestkraft-skymigrering.md", {"id": "something-else"})
        self.assertTrue(self.has(issues, "error", "id", "must equal"))

    def test_gaps_and_stale_index(self):
        self.copy_example(git=False)
        os.unlink(os.path.join(self.root, "employments/2021-03-fjordsky-seniorkonsulent.md"))
        issues = lint.lint(model.load_profile(self.root), today="2026-10-19")
        self.assertTrue(any(i.level == "prompt" and i.message.startswith("no employment 2021-01") for i in issues))
        self.assertTrue(any(i.level == "warning" and i.id == "INDEX" for i in issues))


class History(Tmp):
    def test_commit_log_restore_as_of(self):
        self.copy_example()
        id_ = "2021-04-vestkraft-skymigrering"
        first = history.log(self.root)[0]["rev"]
        e = model.load_profile(self.root).entries[id_]
        write.save(self.root, id_, dict(e.meta, role="Arkitekt"), e.body, e.sha)
        index.write_all(self.root)
        self.assertTrue(history.commit(self.root, history.message(id_, "role changed", "owner")))
        self.assertIsNone(history.commit(self.root, "nothing"))
        log = history.log(self.root, id_)
        self.assertEqual([c["actor"] for c in log], ["owner", "tool"])
        self.assertEqual(log[0]["subject"], f"{id_}: role changed [owner]")
        self.assertIn("role: Skyarkitekt", history.show(self.root, id_, first)[1])

        history.restore(self.root, id_, first, "owner")
        self.assertEqual(model.load_profile(self.root).entries[id_].get("role"), "Skyarkitekt")
        self.assertEqual(len(history.log(self.root, id_)), 3)
        self.assertIn("restored to version", history.log(self.root)[0]["subject"])

        old = history.load_at(self.root, first)
        self.assertEqual(old.entries[id_].get("role"), "Skyarkitekt")
        self.assertEqual(sorted(old.entries), sorted(model.load_profile(EXAMPLE).entries))
        self.assertIsNone(history.rev_at(self.root, "1999-01-01"))
        self.assertTrue(history.rev_at(self.root, "2099-12-31"))

    def test_restore_removed_entry_and_follow(self):
        self.copy_example()
        id_ = "2022-01-intern-plattformkode"
        first = history.log(self.root)[0]["rev"]
        write.remove(self.root, id_, "test")
        history.commit(self.root, history.message(id_, "removed", "owner"))
        self.assertEqual(len(history.log(self.root, id_)), 2)
        history.restore(self.root, id_, first)
        self.assertEqual(model.find(self.root, id_), f"assignments/{id_}.md")
        self.assertFalse(os.path.exists(os.path.join(self.root, "_removed", f"{id_}.md")))

    def test_word_diff(self):
        d = history.word_diff("team of five people", "team of four people")
        self.assertEqual(d, [["=", "team of "], ["-", "five"], ["+", "four"], ["=", " people"]])

    def test_cli(self):
        env = dict(os.environ, PYTHONPATH=SPEC)
        run = lambda *a: subprocess.run([sys.executable, "-m", "openself", *a], capture_output=True, text=True, env=env)
        r = run("init", self.root, "--owner", "Kari", "--lang", "en")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run("new", self.root, "employment", "employer=Acme AS", "title=Dev", "start=2024-01", "end=ongoing")
        self.assertEqual(r.stdout.strip(), "2024-01-acme-as-dev")
        r = run("new", self.root, "assignment", "kind=client", "employment=2024-01-acme-as-dev", "customer=Beta",
                "start=2024-02", "end=ongoing", "tech=Kubernetes,Helm", "--section", "contribution=Built it.")
        self.assertEqual(r.returncode, 0, r.stderr)
        aid = r.stdout.strip()
        with open(os.path.join(self.root, "assignments", aid + ".md"), encoding="utf-8") as f:
            self.assertIn("## Own contribution\n\nBuilt it.", f.read())
        self.assertEqual(run("lint", self.root).returncode, 0)
        r = run("commit", self.root, aid, "added", "--actor", "owner")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"{aid}: added [owner]", run("log", self.root).stdout)
        self.assertIn("2024-02-beta", run("as-of", self.root, "2099-12-31").stdout)


def current_umask():
    m = os.umask(0)
    os.umask(m)
    return m


if __name__ == "__main__":
    unittest.main()
