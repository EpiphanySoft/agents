#!/usr/bin/env python3
"""Tests for file_review.py, with a stub `gh` on PATH in a temp directory. Nothing reaches GitHub.

    python3 skills/review/test_file_review.py        (or: python3 -m unittest discover -s skills/review)
"""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "file_review.py"

STUB_GH = textwrap.dedent("""\
    #!/usr/bin/env python3
    # A stand-in for gh that keeps what it "posts" in store.json, so listing it back works.
    # STUB_FAIL_AT=n fails the n-th create before making it; STUB_LOSE_AT=n makes it, then fails.
    import json, os, sys
    root = os.environ["STUB_ROOT"]
    args = sys.argv[1:]
    with open(os.path.join(root, "gh-calls.jsonl"), "a") as log:
        log.write(json.dumps(args) + "\\n")
    path = os.path.join(root, "store.json")
    store = json.load(open(path)) if os.path.exists(path) else {"creates": 0, "issues": [],
                                                                  "advisories": []}
    def save():
        json.dump(store, open(path, "w"))
    def creating():
        store["creates"] += 1
        save()
        if os.environ.get("STUB_FAIL_AT") == str(store["creates"]):
            sys.stderr.write("HTTP 502: stub failure\\n")
            sys.exit(1)
    def made():
        save()
        if os.environ.get("STUB_LOSE_AT") == str(store["creates"]):
            sys.stderr.write("stub: connection lost after the create\\n")
            sys.exit(1)
    def value(flag):
        return args[args.index(flag) + 1]
    if args[:2] == ["label", "list"]:
        print(json.dumps([{"name": n} for n in ["area:core", "area:docs", "review", "question",
                                                "bug", "kind:bug", "kind:differs"]]))
    elif args[:2] == ["issue", "list"]:
        print(json.dumps([{k: i[k] for k in ("number", "url", "body")} for i in store["issues"]]))
    elif args[:2] == ["issue", "create"]:
        creating()
        n = 100 + len(store["issues"]) + 1
        url = f"https://github.com/owner/proj/issues/{n}"
        labels = [args[i + 1] for i, a in enumerate(args) if a == "--label"]
        store["issues"].append({"number": n, "url": url, "title": value("--title"),
                                "body": open(value("--body-file")).read(), "labels": labels})
        made()
        print(url)
    elif args[:3] == ["api", "--method", "POST"]:
        creating()
        payload = json.load(open(value("--input")))
        k = len(store["advisories"]) + 1
        adv = {"ghsa_id": f"GHSA-stub-{k}", "summary": payload["summary"],
               "description": payload["description"],
               "html_url": f"https://github.com/owner/proj/security/advisories/GHSA-stub-{k}"}
        store["advisories"].append(adv)
        made()
        print(json.dumps(adv))
    elif args[:2] == ["api", "--paginate"]:
        # Two pages, as gh prints them: one JSON array after another.
        half = len(store["advisories"]) // 2
        print(json.dumps(store["advisories"][:half]))
        print(json.dumps(store["advisories"][half:]))
    else:
        sys.stderr.write("stub gh: unexpected call\\n")
        sys.exit(3)
    """)

CHECKER = textwrap.dedent("""\
    import sys
    text = open(sys.argv[1]).read()
    if "FORBIDDEN" in text:
        print("found a listed word: FORBIDDEN")
        sys.exit(1)
    """)


def finding(fid, title, **extra):
    record = {
        "id": fid, "title": title, "severity": "Med", "kind": "bug", "area": "core",
        "requirements": ["R1.2"],
        "code": [{"file": "src/core.py", "line": 12, "quote": "if n < limit:\n    keep(n)"}],
        "what_goes_wrong": "A value exactly on the limit is dropped.",
        "how_run": "Read only.", "remedy": "Use <=.", "confirmations": 1,
    }
    record.update(extra)
    return record


SUMMARY = {
    "commit": "a1b2c3d", "base_commit": None, "skill_commit": "e4f5a6b", "branch_commit": "c7d8e9f",
    "scope": "full", "checking": "checked", "how_it_ran": "one session",
    "models": "Standard", "verdict": "Sound, with one Med bug in core.",
    "matters_most": ["The limit check."], "checked_and_sound": ["Parsing."],
    "where_things_stand": ["Everything read."],
}


class FileReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        stub_dir = self.root / "bin"
        stub_dir.mkdir()
        gh = stub_dir / "gh"
        gh.write_text(STUB_GH)
        gh.chmod(0o755)
        (self.root / "checker.py").write_text(CHECKER)
        (self.root / "docs").mkdir()
        self.pad = self.root / "review" / "0001"
        self.pad.mkdir(parents=True)
        self.env = dict(os.environ, PATH=f"{stub_dir}{os.pathsep}{os.environ['PATH']}",
                        STUB_ROOT=str(self.root))
        self.env.pop("STUB_FAIL_AT", None)
        self.env.pop("STUB_LOSE_AT", None)
        self.config = {
            "repo": "owner/proj", "name": {"prefix": "CR", "number": 1},
            "area_prefix": "area:", "labels": ["review"],
            "text_check": f"{sys.executable} {self.root / 'checker.py'} {{file}}",
        }
        self.findings = [
            finding("U01-1", "A value on the limit is dropped."),
            finding("U01-2", "A forged token is accepted.", kind="security", severity="High",
                    exploitable=True),
            finding("D1-1", "Two documents give different timeouts.", kind="differs",
                    area="docs", code=[], question=True),
        ]
        self.write_inputs()

    def tearDown(self):
        self.tmp.cleanup()

    def write_inputs(self):
        (self.root / "docs" / "review.json").write_text(json.dumps(self.config))
        (self.pad / "findings.jsonl").write_text(
            "".join(json.dumps(f) + "\n" for f in self.findings))
        (self.pad / "summary.json").write_text(json.dumps(SUMMARY))

    def run_script(self, *args, **env):
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.root,
                              env=dict(self.env, **env), capture_output=True, text=True)

    def calls(self):
        path = self.root / "gh-calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]

    def posting_calls(self):
        """The calls that make something: issue create and the advisory POST."""
        return [c for c in self.calls()
                if c[:2] == ["issue", "create"] or c[:3] == ["api", "--method", "POST"]]

    def store(self):
        path = self.root / "store.json"
        return json.loads(path.read_text()) if path.exists() else {"issues": [], "advisories": []}

    def state(self):
        return json.loads((self.pad / "filing-state.json").read_text())["posted"]

    # ---- dry run ----

    def test_dry_run_writes_every_item_and_posts_nothing(self):
        done = self.run_script("dry-run")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.posting_calls(), [])
        text = (self.pad / "filing-dry-run.md").read_text()
        self.assertIn("plan sha256: ", text)
        for f in self.findings:
            self.assertIn(f"- title: {f['title']}", text)
        self.assertIn("## 1. U01-1: public issue", text)
        self.assertIn("## 2. U01-2: draft security advisory, private", text)
        self.assertIn("- labels: review, area:docs, question", text)
        self.assertIn("- labels: review, area:core", text)
        self.assertEqual(text.count("- parent: none"), 4)
        self.assertIn("- title: CR1: summary", text)
        self.assertIn("#<U01-1>", text)
        self.assertIn("Text check: passed", text)
        self.assertFalse((self.pad / "filing-state.json").exists())

    def test_kind_labels_only_with_a_kind_prefix(self):
        self.run_script("dry-run")
        self.assertNotIn("kind:", (self.pad / "filing-dry-run.md").read_text())
        self.config["kind_prefix"] = "kind:"
        self.write_inputs()
        self.assertEqual(self.run_script("dry-run").returncode, 0)
        text = (self.pad / "filing-dry-run.md").read_text()
        self.assertIn("- labels: review, area:core, kind:bug\n", text)
        self.assertIn("- labels: review, area:docs, kind:differs, question\n", text)

    def test_advisory_follows_the_mark_unless_set(self):
        self.run_script("dry-run")
        text = (self.pad / "filing-dry-run.md").read_text()
        self.assertIn("## 2. U01-2: draft security advisory, private, severity high", text)
        self.assertIn("- exploitable if public: yes\n", text)
        self.assertEqual(text.count("- exploitable if public: no\n"), 2)
        # The owner changes a mark at the read: advisory overrides it, and the dry run says so.
        self.findings[1]["advisory"] = False
        self.findings[0]["advisory"] = True
        self.write_inputs()
        self.run_script("dry-run")
        text = (self.pad / "filing-dry-run.md").read_text()
        self.assertIn("## 1. U01-1: draft security advisory", text)
        self.assertIn("## 2. U01-2: public issue", text)
        self.assertIn("filed as a public issue anyway (`advisory: false`)", text)
        self.assertIn("filed as an advisory anyway (`advisory: true`)", text)

    def test_dry_run_flags_a_mark_lost_since_the_review(self):
        (self.pad / "exploitable.json").write_text(json.dumps(["U01-2", "U01-1"]))
        self.assertEqual(self.run_script("dry-run").returncode, 0)
        text = (self.pad / "filing-dry-run.md").read_text()
        self.assertIn("Check the marks: U01-1 flagged in `exploitable.json`", text)

    def test_body_starts_with_severity_and_holds_the_finding(self):
        self.run_script("dry-run")
        text = (self.pad / "filing-dry-run.md").read_text()
        body = text.split("## 1. U01-1")[1].split("```markdown\n")[1]
        self.assertTrue(body.startswith("severity Med\n"))
        for part in ("**Kind:** bug", "**Requirements:** R1.2", "`src/core.py:12`",
                     "if n < limit:", "**What goes wrong**", "**How it was run**", "**Remedy**"):
            self.assertIn(part, body)

    def test_dry_run_reports_a_failing_text_check(self):
        self.findings[0]["remedy"] = "Use FORBIDDEN."
        self.write_inputs()
        done = self.run_script("dry-run")
        self.assertEqual(done.returncode, 1)
        self.assertIn("Text check: FAILED for U01-1", (self.pad / "filing-dry-run.md").read_text())
        self.assertEqual(self.posting_calls(), [])

    # ---- post ----

    def test_post_files_issues_the_advisory_and_the_summary(self):
        self.assertEqual(self.run_script("dry-run").returncode, 0)
        done = self.run_script("post")
        self.assertEqual(done.returncode, 0, done.stderr)
        calls = self.posting_calls()
        self.assertEqual([c[0] for c in calls], ["issue", "api", "issue", "issue"])
        self.assertEqual(calls[1][:4], ["api", "--method", "POST",
                                        "repos/owner/proj/security-advisories"])
        self.assertIn("question", calls[2])
        state = self.state()
        self.assertEqual(set(state), {"U01-1", "U01-2", "D1-1", "summary"})
        self.assertEqual(state["U01-2"]["type"], "advisory")
        summary_call = calls[3]
        self.assertEqual(summary_call[summary_call.index("--title") + 1], "CR1: summary")

    def test_summary_links_findings_and_keeps_advisories_private(self):
        self.run_script("dry-run")
        self.assertEqual(self.run_script("post").returncode, 0)
        summary = self.store()["issues"][-1]["body"]
        self.assertIn("- #101 severity Med, bug, area core: A value on the limit is dropped.", summary)
        self.assertIn("- #102 severity Med, differs, area docs:", summary)
        self.assertNotIn("forged", summary)
        self.assertIn("1 more finding is filed as a draft security advisory, private", summary)
        self.assertNotIn("#<", summary)

    def test_every_body_ends_with_its_marker(self):
        self.run_script("dry-run")
        self.run_script("post")
        store = self.store()
        bodies = [i["body"] for i in store["issues"]] + [a["description"] for a in store["advisories"]]
        for item_id in ("U01-1", "D1-1", "summary", "U01-2"):
            self.assertEqual(sum(b.endswith(f"<!-- review CR1 {item_id} -->\n") for b in bodies), 1)

    def test_rerun_after_a_create_that_was_not_recorded(self):
        self.run_script("dry-run")
        # The second create (the advisory) is made, then gh fails before the script records it.
        done = self.run_script("post", STUB_LOSE_AT="2")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(set(self.state()), {"U01-1"})
        self.assertEqual(len(self.store()["advisories"]), 1)
        done = self.run_script("post")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("U01-2: found already posted", done.stdout)
        store = self.store()
        self.assertEqual(len(store["advisories"]), 1)
        self.assertEqual(len(store["issues"]), 3)
        self.assertEqual(self.state()["U01-2"]["ghsa_id"], "GHSA-stub-1")
        self.assertTrue(self.state()["U01-2"]["found"])

    def test_lost_issue_create_is_found_and_linked(self):
        self.run_script("dry-run")
        self.assertEqual(self.run_script("post", STUB_LOSE_AT="1").returncode, 1)
        self.assertNotIn("U01-1", self.state() if (self.pad / "filing-state.json").exists() else {})
        self.assertEqual(self.run_script("post").returncode, 0)
        store = self.store()
        self.assertEqual([i["number"] for i in store["issues"]], [101, 102, 103])
        self.assertIn("- #101 severity Med", store["issues"][-1]["body"])

    def test_post_needs_a_dry_run_that_matches(self):
        done = self.run_script("post")
        self.assertEqual(done.returncode, 2)
        self.assertIn("no dry run", done.stderr)
        self.run_script("dry-run")
        self.findings[0]["title"] = "Changed after the read."
        self.write_inputs()
        done = self.run_script("post")
        self.assertEqual(done.returncode, 2)
        self.assertIn("run dry-run again", done.stderr)
        self.assertEqual(self.posting_calls(), [])

    def test_rerun_after_a_partial_post_skips_what_was_posted(self):
        self.run_script("dry-run")
        done = self.run_script("post", STUB_FAIL_AT="2")
        self.assertEqual(done.returncode, 1)
        self.assertIn("stub failure", done.stderr)
        self.assertEqual(set(self.state()), {"U01-1"})
        done = self.run_script("post")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(set(self.state()), {"U01-1", "U01-2", "D1-1", "summary"})
        created = [c for c in self.posting_calls() if c[:2] == ["issue", "create"]]
        titles = [c[c.index("--title") + 1] for c in created]
        self.assertEqual(titles.count("A value on the limit is dropped."), 1)
        # A third run posts nothing new.
        before = len(self.posting_calls())
        self.assertEqual(self.run_script("post").returncode, 0)
        self.assertEqual(len(self.posting_calls()), before)

    def test_post_stops_on_a_failing_text_check(self):
        self.run_script("dry-run")
        # The check fails on the third item only once posting has started.
        (self.root / "checker.py").write_text(CHECKER.replace(
            '"FORBIDDEN" in text', '"FORBIDDEN" in text or "different timeouts" in text'))
        done = self.run_script("post")
        self.assertEqual(done.returncode, 1)
        self.assertIn("text check failed for D1-1", done.stderr)
        self.assertEqual(set(self.state()), {"U01-1", "U01-2"})
        self.assertEqual(len(self.posting_calls()), 2)

    def test_never_closes_or_edits(self):
        self.run_script("dry-run")
        self.run_script("post")
        for call in self.calls():
            self.assertNotIn(call[:2], (["issue", "close"], ["issue", "edit"]))
            if call[:2] == ["api", "--method"]:
                self.assertEqual(call[2:4], ["POST", "repos/owner/proj/security-advisories"])

    # ---- question ----

    QUESTION = {
        "question": "Should a value on the limit be kept?",
        "options": [{"option": "Keep it", "means": "the limit is inclusive"},
                    {"option": "Drop it", "means": "the limit is exclusive, as the code does"}],
        "recommendation": "Keep it: R1.2 says up to and including.",
        "claim": "U01-1",
    }

    def ask(self, question=None, **env):
        path = self.root / "q.json"
        path.write_text(json.dumps(question or self.QUESTION))
        return self.run_script("question", str(path), **env)

    def questions_md(self):
        path = self.pad / "questions.md"
        return path.read_text() if path.exists() else ""

    def test_question_is_filed_as_a_walk_thru_item(self):
        done = self.ask()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("filed: https://github.com/owner/proj/issues/101", done.stdout)
        issue = self.store()["issues"][0]
        self.assertEqual(issue["title"], "CR1 question: Should a value on the limit be kept?")
        self.assertEqual(issue["labels"], ["review", "question"])
        for part in ("**Question:** Should", "1. **Keep it**: the limit is inclusive",
                     "2. **Drop it**:", "**Recommendation:** Keep it", "**Claim:** U01-1"):
            self.assertIn(part, issue["body"])
        self.assertEqual(self.questions_md(), "")

    def test_question_on_an_exploitable_claim_stays_private(self):
        (self.pad / "exploitable.json").write_text(json.dumps(["U01-1"]))
        done = self.ask()
        self.assertEqual(done.returncode, 0, done.stderr)
        issue = self.store()["issues"][0]
        self.assertEqual(issue["title"], "CR1 question: a private question is waiting")
        for text in (issue["title"], issue["body"]):
            self.assertNotIn("limit", text)
            self.assertNotIn("U01-1", text)
        kept = self.questions_md()
        self.assertIn("private: claim U01-1 is flagged exploitable", kept)
        self.assertIn("**Recommendation:** Keep it", kept)

    def test_question_that_cannot_be_filed_is_kept(self):
        done = self.ask(STUB_FAIL_AT="1")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(self.store()["issues"], [])
        kept = self.questions_md()
        self.assertIn("it could not be filed", kept)
        self.assertIn("stub failure", kept)
        self.assertIn("**Question:** Should a value on the limit be kept?", kept)

    def test_question_failing_the_text_check_is_kept_not_filed(self):
        question = dict(self.QUESTION, recommendation="Keep it, says FORBIDDEN.")
        done = self.ask(question)
        self.assertEqual(done.returncode, 1)
        self.assertEqual(self.posting_calls(), [])
        kept = self.questions_md()
        self.assertIn("text check failed", kept)
        self.assertIn("FORBIDDEN", kept)

    def test_private_notice_that_cannot_be_filed_is_kept_too(self):
        (self.pad / "exploitable.json").write_text(json.dumps(["U01-1"]))
        done = self.ask(STUB_FAIL_AT="1")
        self.assertEqual(done.returncode, 1)
        kept = self.questions_md()
        self.assertIn("private: claim U01-1", kept)
        self.assertIn("the notice for the private question above could not be filed", kept)

    def test_bad_question_names_its_field(self):
        question = dict(self.QUESTION, options=[{"option": "Only one", "means": "no choice"}])
        done = self.ask(question)
        self.assertEqual(done.returncode, 2)
        self.assertIn("question.options: needs at least 2 items", done.stderr)
        self.assertEqual(self.posting_calls(), [])

    # ---- refusals ----

    def refused(self, needle):
        done = self.run_script("dry-run")
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertIn(needle, done.stderr)
        self.assertEqual(self.posting_calls(), [])

    def test_bad_config_missing_field(self):
        del self.config["repo"]
        self.write_inputs()
        self.refused("config.repo: missing")

    def test_bad_config_wrong_type(self):
        self.config["name"]["number"] = "1"
        self.write_inputs()
        self.refused("config.name.number: must be integer")

    def test_bad_config_unknown_field(self):
        self.config["lables"] = ["x"]
        self.write_inputs()
        self.refused("config.lables: not a known field")

    def test_bad_config_text_check_without_file(self):
        self.config["text_check"] = "true"
        self.write_inputs()
        self.refused("config.text_check:")

    def test_bad_config_not_json(self):
        (self.root / "docs" / "review.json").write_text("{\"repo\": ")
        self.refused("not JSON")

    def test_finding_in_an_unknown_area(self):
        self.findings[0]["area"] = "nowhere"
        self.write_inputs()
        self.refused("U01-1.area: 'nowhere' is not one of the project's areas")

    def test_bad_finding_names_its_line_and_field(self):
        self.findings[1]["severity"] = "Critical"
        self.write_inputs()
        self.refused("findings.jsonl line 2.severity: must be one of High, Med, Low")

    def test_a_finding_may_not_take_the_summary_id(self):
        self.findings[0]["id"] = "summary"
        self.write_inputs()
        self.refused("line 1.id: \"summary\" is the summary's own")

    def test_areas_from_a_command(self):
        self.config["areas_command"] = f"{sys.executable} -c \"print('core'); print('docs')\""
        self.write_inputs()
        self.assertEqual(self.run_script("dry-run").returncode, 0)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
