#!/usr/bin/env python3
"""Tests for file_review.py, with a stub `gh` on PATH in a temp directory. Nothing reaches GitHub.
FileReviewTest covers a full review's filing and questions; PrReviewTest a pull request's passes.

    python3 skills/review/test_file_review.py        (or: python3 -m unittest discover -s skills/review)
"""

import json
import os
import re
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
    # gh-inputs.jsonl keeps every file passed with --input or --body-file, as it was at the call.
    import json, os, re, sys
    root = os.environ["STUB_ROOT"]
    args = sys.argv[1:]
    with open(os.path.join(root, "gh-calls.jsonl"), "a") as log:
        log.write(json.dumps(args) + "\\n")
    for flag in ("--input", "--body-file"):
        if flag in args:
            with open(os.path.join(root, "gh-inputs.jsonl"), "a") as log:
                log.write(json.dumps(open(args[args.index(flag) + 1]).read()) + "\\n")
    path = os.path.join(root, "store.json")
    store = json.load(open(path)) if os.path.exists(path) else {"creates": 0, "issues": [],
                                                                  "advisories": []}
    store.setdefault("reviews", [])
    store.setdefault("comments", [])
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
    elif args[:3] == ["api", "--method", "POST"] and re.search(r"/pulls/\\d+/reviews$", args[3]):
        creating()
        payload = json.load(open(value("--input")))
        review = {"id": 500 + len(store["reviews"]) + 1, "body": payload["body"],
                  "event": payload["event"], "commit_id": payload["commit_id"],
                  "author_association": "OWNER",
                  "html_url": f"https://github.com/owner/proj/pull/74#review-{len(store['reviews'])}"}
        store["reviews"].append(review)
        for c in payload["comments"]:
            k = 900 + len(store["comments"]) + 1
            store["comments"].append(dict(c, id=k, in_reply_to_id=None, author_association="OWNER",
                                          pull_request_review_id=review["id"],
                                          html_url=f"https://github.com/owner/proj/pull/74#c{k}"))
        made()
        print(json.dumps(review))
    elif args[:3] == ["api", "--method", "POST"] and re.search(r"/comments/\\d+/replies$", args[3]):
        to = int(args[3].split("/")[-2])
        if not any(c["id"] == to and not c["in_reply_to_id"] for c in store["comments"]):
            sys.stderr.write("HTTP 404: no such thread\\n")
            sys.exit(1)
        creating()
        k = 900 + len(store["comments"]) + 1
        reply = {"id": k, "body": json.load(open(value("--input")))["body"], "in_reply_to_id": to,
                 "author_association": "OWNER", "html_url": f"https://github.com/owner/proj/pull/74#c{k}"}
        store["comments"].append(reply)
        made()
        print(json.dumps(reply))
    elif args[:4] == ["api", "--method", "POST", "repos/owner/proj/security-advisories"]:
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
        kind = re.search(r"(security-advisories|pulls/74/reviews|pulls/74/comments)\\?", args[2])
        items = store[{"security-advisories": "advisories", "pulls/74/reviews": "reviews",
                       "pulls/74/comments": "comments"}[kind.group(1)]]
        half = len(items) // 2
        print(json.dumps(items[:half]))
        print(json.dumps(items[half:]))
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


HEAD1 = "1" * 40
HEAD2 = "2" * 40


def pr_finding(fid, title, line, **extra):
    record = finding(fid, title, **extra)
    record.pop("area")
    record["at"] = {"file": "src/core.py", "line": line}
    return record


def first_pass():
    return {
        "pr": 74, "pass": 1, "head": HEAD1, "base": "abcdef0", "skill_commit": "e4f5a6b",
        "level": "Standard", "checking": "checked",
        "verdict": "Built to R1, with one Med bug.",
        "read": ["R1 at the head", "unit core: src/core.py, the delta and what surrounds it"],
        "pieces": [{"piece": "discovery", "model": "model-a", "effort": "high", "tokens": 120000},
                   {"piece": "checking", "model": "model-b", "effort": "high", "tokens": 40000}],
        "findings": [
            pr_finding("P1-1", "A value on the limit is dropped.", 12),
            pr_finding("P1-2", "A forged token is accepted.", 30, kind="security",
                       severity="High", exploitable=True,
                       what_goes_wrong="A forged token opens the admin page."),
            pr_finding("P1-3", "The retry has no test.", 40, kind="test gap", severity="Low",
                       question=True),
        ],
        "outside": [
            finding("P1-4", "Two documents give different timeouts.", kind="differs",
                    area="docs", code=[]),
            finding("P1-5", "An old helper is never called.", kind="untraced", severity="Low"),
            finding("P1-6", "A replayed request is accepted.", kind="security", severity="High",
                    exploitable=True, what_goes_wrong="A replayed request moves the money twice."),
        ],
        "replies": [],
    }


def second_pass():
    return {
        **first_pass(), "pass": 2, "head": HEAD2, "base": HEAD1[:7],
        "verdict": "The bug is fixed; the test gap holds.",
        "findings": [pr_finding("P2-1", "The new branch leaks a file.", 55, severity="Low")],
        "outside": [],
        "replies": [
            {"id": "P1-1", "status": "fixed", "sha": "3333333",
             "evidence": "`src/core.py:12` now reads `if n <= limit:`."},
            {"id": "P1-3", "status": "holds", "evidence": "No test reaches the retry yet."},
            {"id": "P1-2", "status": "holds", "evidence": "The forged token still opens it."},
        ],
    }


class PrReviewTest(unittest.TestCase):
    setUp = FileReviewTest.setUp
    tearDown = FileReviewTest.tearDown
    run_script = FileReviewTest.run_script
    calls = FileReviewTest.calls
    store = FileReviewTest.store
    write_inputs = FileReviewTest.write_inputs

    def write_pass(self, record):
        self.pr_pad = self.root / "review" / "pr-74"
        self.pr_pad.mkdir(parents=True, exist_ok=True)
        (self.pr_pad / f"pass-{record['pass']}.json").write_text(json.dumps(record))

    def pr(self, *args, **env):
        return self.run_script("pr", *args, **env)

    def posts(self):
        return [c for c in self.calls() if c[:3] == ["api", "--method", "POST"]
                or c[:2] == ["issue", "create"]]

    def pr_state(self):
        return json.loads((self.pr_pad / "pr-state.json").read_text())["posted"]

    def everything_sent(self):
        """Every argument and every input file of every gh call, as one text."""
        inputs = self.root / "gh-inputs.jsonl"
        files = [json.loads(line) for line in inputs.read_text().splitlines()] \
            if inputs.exists() else []
        return json.dumps(self.calls()) + "\n".join(files)

    def post_first(self):
        self.write_pass(first_pass())
        done = self.pr("post", "74")
        self.assertEqual(done.returncode, 0, done.stderr)
        return done

    # ---- a first pass ----

    def test_first_pass_is_one_comment_review_with_line_comments(self):
        done = self.post_first()
        self.assertEqual(len(self.posts()), 1)
        self.assertEqual(self.posts()[0][3], "repos/owner/proj/pulls/74/reviews")
        review = self.store()["reviews"][0]
        self.assertEqual(review["event"], "COMMENT")
        self.assertEqual(review["commit_id"], HEAD1)
        body = review["body"]
        for part in ("**pr-review, pass 1**", "from the merge base (abcdef0)",
                     "**Verdict:** Built to R1", "High 0, Med 1, Low 1", "## What was read",
                     "- R1 at the head", "## Outside this PR",
                     "- severity Med, the documents: Two documents give different timeouts.",
                     "- severity Low, `src/core.py:12`: An old helper is never called.",
                     "**Level:** Standard, checked", "the `pr-review` skill at e4f5a6b",
                     "- discovery: model-a, high, 120,000 tokens"):
            self.assertIn(part, body)
        self.assertTrue(body.endswith("<!-- pr-review 74 pass 1 -->\n"))
        comments = self.store()["comments"]
        self.assertEqual([(c["path"], c["line"], c["side"]) for c in comments],
                         [("src/core.py", 12, "RIGHT"), ("src/core.py", 40, "RIGHT")])
        self.assertTrue(comments[0]["body"].startswith(
            "severity Med\n\n**A value on the limit is dropped.**\n"))
        for part in ("**Kind:** bug", "if n < limit:", "**What goes wrong**", "**Remedy**"):
            self.assertIn(part, comments[0]["body"])
        self.assertIn("**A choice for the owner:**", comments[1]["body"])
        self.assertTrue(comments[0]["body"].endswith("<!-- pr-review 74 P1-1 -->\n"))
        self.assertIn("kept in the work pad, flagged exploitable: P1-2, P1-6", done.stdout)
        self.assertEqual(set(self.pr_state()), {"pass 1"})
        # Run again: nothing more is posted.
        self.assertEqual(self.pr("post", "74").returncode, 0)
        self.assertEqual(len(self.posts()), 1)

    def test_a_multi_line_finding_spans_its_lines(self):
        record = first_pass()
        record["findings"][0]["at"].update(start_line=10, side="LEFT")
        self.write_pass(record)
        self.assertEqual(self.pr("post", "74").returncode, 0)
        c = self.store()["comments"][0]
        self.assertEqual((c["start_line"], c["line"], c["side"], c["start_side"]),
                         (10, 12, "LEFT", "LEFT"))

    # ---- a second pass ----

    def test_second_pass_replies_on_the_threads_and_posts_a_new_review(self):
        self.post_first()
        self.write_pass(second_pass())
        done = self.pr("post", "74")
        self.assertEqual(done.returncode, 0, done.stderr)
        store = self.store()
        self.assertEqual(len(store["reviews"]), 2)
        body = store["reviews"][1]["body"]
        self.assertIn("from pass 1's head, leaving out what came in with a merge of the target "
                      f"({HEAD1[:7]})", body)
        self.assertIn("**Earlier findings:** 1 fixed, 1 still hold", body)
        self.assertIn("High 0, Med 0, Low 1", body)
        self.assertEqual(store["reviews"][1]["event"], "COMMENT")
        threads = {c["body"].rsplit("<!-- pr-review 74 ", 1)[1].split(" ")[0]: c["id"]
                   for c in store["comments"] if not c["in_reply_to_id"]}
        replies = [c for c in store["comments"] if c["in_reply_to_id"]]
        self.assertEqual(len(replies), 2)
        self.assertEqual(replies[0]["in_reply_to_id"], threads["P1-1"])
        self.assertTrue(replies[0]["body"].startswith("fixed in 3333333\n\n`src/core.py:12`"))
        self.assertEqual(replies[1]["in_reply_to_id"], threads["P1-3"])
        self.assertTrue(replies[1]["body"].startswith(f"still holds at {HEAD2}"))
        self.assertTrue(replies[1]["body"].endswith("<!-- pr-review 74 P1-3 reply 2 -->\n"))
        self.assertEqual(set(self.pr_state()),
                         {"pass 1", "pass 2", "P1-1 reply 2", "P1-3 reply 2"})

    def test_rerun_after_a_partial_post(self):
        self.post_first()
        self.write_pass(second_pass())
        # Creates: 1 the first review, 2 the second, 3 the first reply (fails before it is made).
        done = self.pr("post", "74", STUB_FAIL_AT="3")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(set(self.pr_state()), {"pass 1", "pass 2"})
        done = self.pr("post", "74")
        self.assertEqual(done.returncode, 0, done.stderr)
        store = self.store()
        self.assertEqual(len(store["reviews"]), 2)
        self.assertEqual(sum(1 for c in store["comments"] if c["in_reply_to_id"]), 2)

    def test_rerun_after_a_review_made_but_not_recorded(self):
        self.write_pass(first_pass())
        self.assertEqual(self.pr("post", "74", STUB_LOSE_AT="1").returncode, 1)
        self.assertFalse((self.pr_pad / "pr-state.json").exists())
        done = self.pr("post", "74")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("pass 1: found already posted", done.stdout)
        self.assertEqual(len(self.store()["reviews"]), 1)
        self.assertTrue(self.pr_state()["pass 1"]["found"])

    def test_markers_by_others_are_never_read(self):
        # Someone outside the project plants the pass's marker and a fake thread for P1-1.
        self.post_first()
        store = self.store()
        store["reviews"].append({"id": 777, "body": "<!-- pr-review 74 pass 2 -->",
                                 "author_association": "CONTRIBUTOR", "html_url": "x"})
        store["comments"].insert(0, {"id": 1, "body": "<!-- pr-review 74 P1-1 -->",
                                     "in_reply_to_id": None, "author_association": "NONE",
                                     "html_url": "y"})
        (self.root / "store.json").write_text(json.dumps(store))
        self.write_pass(second_pass())
        done = self.pr("post", "74")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("left unread: 2 reviews and comments by others on #74", done.stdout)
        store = self.store()
        self.assertEqual(sum("pass 2 -->" in r["body"] for r in store["reviews"]), 2)
        reply = next(c for c in store["comments"] if c["in_reply_to_id"])
        self.assertNotEqual(reply["in_reply_to_id"], 1)

    # ---- filing outside findings ----

    def test_files_only_the_outside_findings_the_owner_chose(self):
        self.post_first()
        done = self.pr("file", "74", "P1-4")
        self.assertEqual(done.returncode, 0, done.stderr)
        issues = self.store()["issues"]
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["title"], "Two documents give different timeouts.")
        self.assertEqual(issues[0]["labels"], ["review", "area:docs"])
        body = issues[0]["body"]
        self.assertTrue(body.startswith("severity Med\n"))
        self.assertIn("**Found by:** the review of #74, pass 1, outside its diff; work-pad id P1-4",
                      body)
        self.assertTrue(body.endswith("<!-- pr-review 74 P1-4 issue -->\n"))
        # --all files the rest of the latest pass's list, never the exploitable one.
        done = self.pr("file", "74", "--all")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual([i["title"] for i in self.store()["issues"]],
                         ["Two documents give different timeouts.",
                          "An old helper is never called."])
        self.assertEqual(self.store()["advisories"], [])
        self.assertIn("kept in the work pad, flagged exploitable: P1-6", done.stdout)

    def test_an_exploitable_finding_named_by_the_owner_is_a_private_advisory(self):
        self.post_first()
        done = self.pr("file", "74", "P1-2")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.store()["issues"], [])
        advisory = self.store()["advisories"][0]
        self.assertEqual(advisory["summary"], "A forged token is accepted.")
        self.assertTrue(advisory["description"].endswith("<!-- pr-review 74 P1-2 advisory -->\n"))

    def test_file_refuses_a_finding_on_the_diff_or_an_unknown_one(self):
        self.post_first()
        for fid, needle in (("P1-1", "posted on its line, not filed"),
                            ("P9-9", "no such finding")):
            done = self.pr("file", "74", fid)
            self.assertEqual(done.returncode, 2)
            self.assertIn(needle, done.stderr)
        self.assertEqual(len(self.posts()), 1)

    def test_file_refuses_ids_with_all(self):
        self.write_pass(first_pass())
        self.assertEqual(self.pr("file", "74", "P1-4", "--all").returncode, 2)
        self.assertEqual(self.pr("file", "74").returncode, 2)

    # ---- the gates ----

    def test_a_failing_text_check_posts_nothing(self):
        record = first_pass()
        record["findings"][2]["remedy"] = "Add a FORBIDDEN test."
        self.write_pass(record)
        done = self.pr("post", "74")
        self.assertEqual(done.returncode, 1)
        self.assertIn("text check failed for P1-3", done.stderr)
        self.assertEqual(self.calls(), [])
        # The outside list is in the review's body, so a bad title stops the review too.
        record["findings"][2]["remedy"] = "Add a test."
        record["outside"][1]["title"] = "A FORBIDDEN helper."
        self.write_pass(record)
        self.assertEqual(self.pr("post", "74").returncode, 1)
        self.assertEqual(self.calls(), [])
        # Changed after the review was posted, it stops the filing.
        self.post_first()
        self.write_pass(record)
        done = self.pr("file", "74", "--all")
        self.assertEqual(done.returncode, 1)
        self.assertIn("text check failed for P1-5 issue", done.stderr)
        self.assertEqual(len(self.posts()), 1)

    def test_a_failing_reply_text_check_posts_nothing_of_the_pass(self):
        self.post_first()
        record = second_pass()
        record["replies"][1]["evidence"] = "FORBIDDEN"
        self.write_pass(record)
        self.assertEqual(self.pr("post", "74").returncode, 1)
        self.assertEqual(len(self.posts()), 1)

    def test_exploitable_claims_never_reach_gh(self):
        (self.root / "review" / "pr-74").mkdir(parents=True)
        # P1-5 is flagged only in exploitable.json: it is kept back too.
        (self.root / "review" / "pr-74" / "exploitable.json").write_text(json.dumps(["P1-5"]))
        self.post_first()
        self.assertEqual(self.pr("file", "74", "--all").returncode, 0)
        self.write_pass(second_pass())
        self.assertEqual(self.pr("post", "74").returncode, 0)
        sent = self.everything_sent()
        for text in ("forged", "replayed", "P1-2", "P1-6", "old helper", "P1-5"):
            self.assertNotIn(text, sent)
        self.assertIn("High 0, Med 1, Low 1", self.store()["reviews"][0]["body"])
        self.assertEqual(len(self.store()["issues"]), 1)

    def test_no_forbidden_call_is_ever_made(self):
        self.post_first()
        self.assertEqual(self.pr("file", "74", "--all").returncode, 0)
        self.write_pass(second_pass())
        self.assertEqual(self.pr("post", "74").returncode, 0)
        self.assertEqual(self.pr("file", "74", "P1-2").returncode, 0)
        reviews = "repos/owner/proj/pulls/74/reviews"
        allowed_posts = re.compile(r"^repos/owner/proj/(pulls/74/reviews|pulls/74/comments/\d+/"
                                   r"replies|security-advisories)$")
        allowed_lists = re.compile(r"^repos/owner/proj/(pulls/74/reviews|pulls/74/comments|"
                                   r"security-advisories)\?per_page=100$")
        for call in self.calls():
            if call[0] == "api" and call[1] == "--method":
                self.assertEqual(call[2], "POST", call)
                self.assertRegex(call[3], allowed_posts)
            elif call[0] == "api":
                self.assertEqual(call[1], "--paginate", call)
                self.assertRegex(call[2], allowed_lists)
            else:
                self.assertIn(call[:2], (["issue", "create"], ["issue", "list"],
                                         ["label", "list"]), call)
        inputs = [json.loads(line) for line in
                  (self.root / "gh-inputs.jsonl").read_text().splitlines()]
        review_posts = [c for c in self.calls() if c[:4] == ["api", "--method", "POST", reviews]]
        events = [json.loads(i)["event"] for i in inputs if i.startswith("{") and
                  '"commit_id"' in i]
        self.assertEqual(len(review_posts), 2)
        self.assertEqual(events, ["COMMENT", "COMMENT"])
        made = [c[:2] for c in self.posts()]
        self.assertEqual(made.count(["issue", "create"]), 2)
        self.assertEqual(made.count(["api", "--method"]), 5)

    # ---- refusals ----

    def test_refusals_name_the_record(self):
        self.post_first()
        cases = [
            (dict(second_pass(), base="9999999"), "pass-2.json.base: 9999999 is not pass 1's head"),
            (dict(second_pass(), findings=[pr_finding("P1-1", "Again.", 3)]),
             "P1-1: the id is used twice"),
            (dict(second_pass(), replies=[{"id": "P1-4", "status": "holds", "evidence": "x"}]),
             "reply P1-4: not an earlier pass's finding in the diff"),
            (dict(second_pass(), replies=[{"id": "P1-1", "status": "fixed", "evidence": "x"}]),
             "reply P1-1.sha: a fixed finding names its commit"),
            (dict(second_pass(), pr=75), "pass-2.json.pr: 75, not 74"),
            (dict(second_pass(), level="Gold"), "pass-2.json.level: must be one of"),
        ]
        for record, needle in cases:
            self.write_pass(record)
            done = self.pr("post", "74")
            self.assertEqual(done.returncode, 2, record)
            self.assertIn(needle, done.stderr)
        (self.pr_pad / "pass-2.json").unlink()
        self.write_pass(dict(second_pass(), **{"pass": 3}))
        self.assertIn("not 1, 2, ... without a gap", self.pr("post", "74").stderr)
        self.assertEqual(len(self.posts()), 1)

    def test_a_reply_with_no_thread_is_refused_before_posting(self):
        self.post_first()
        store = self.store()
        store["comments"] = [c for c in store["comments"] if "P1-3 -->" not in c["body"]]
        (self.root / "store.json").write_text(json.dumps(store))
        self.write_pass(second_pass())
        done = self.pr("post", "74")
        self.assertEqual(done.returncode, 2)
        self.assertIn("P1-3 reply 2: no thread of P1-3 on #74", done.stderr)
        self.assertEqual(len(self.posts()), 1)


if __name__ == "__main__":
    unittest.main()
