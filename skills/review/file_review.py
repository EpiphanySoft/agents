#!/usr/bin/env python3
"""File a code review's findings: one issue per finding, each a sub-issue of its area's step in the
review's sweep, a draft security advisory for each finding marked exploitable, and the summary as a
comment on the review's own step; and post a pull request review's passes. See filing.md beside this
script.

    file_review.py dry-run [--config docs/review.json] [--pad review/<nnnn>]
    file_review.py post    [--config docs/review.json] [--pad review/<nnnn>]
    file_review.py question <question.json> [--config docs/review.json] [--pad review/<nnnn>]
    file_review.py pr post <n> [--config docs/review.json] [--pad review/pr-<n>]
    file_review.py pr file <n> (<id> ... | --all) [--config docs/review.json] [--pad review/pr-<n>]
    file_review.py respond <n> [--config docs/review.json] [--pad review/pr-<n>]

`dry-run` writes the whole plan to <pad>/filing-dry-run.md, each finding's parent and numbered title
included, and posts nothing; it reads the sweep label and the review's own step from <pad>/sweep.json.
`post` posts exactly that plan through the gh CLI: each finding is filed, then attached under its
parent, both kept in <pad>/filing-state.json so a run that stopped does only what is missing; the
marker each body ends with lets it find, rather than repeat, an item it made but didn't record.
`question` files one question for the owner as a walk-thru issue under its area's step, or keeps it in
<pad>/questions.md when it can't be filed or its claim is flagged exploitable. `pr post` posts a pull
request review's latest pass, <pad>/pass-<k>.json, as one review with event COMMENT and its replies on
earlier findings' threads; `pr file` files the additional findings the owner chose, in the sweep of the
pull request's sweep label if it has one. Both keep <pad>/pr-state.json, find what an earlier run
posted by its marker, and leave out every claim flagged exploitable and every question for the owner.
`respond` posts the author's round, <pad>/round-<k>.json: its replies on the reviewers' threads and one
comment on the pull request, refusing any commit not on the pull request's branch, keeping
<pad>/respond-state.json. The `pr` and `respond` commands, and the summary's lookup on its step, read
only the comments of the project's owners, members and collaborators. It never closes or edits an
issue, never makes a parent, and never resolves, approves or requests changes. Python 3 standard
library only.

Exit status: 0 done; 1 a text check, a parent search or a gh call failed (what was posted is kept; a
question is kept in questions.md); 2 refused (a bad config or input, or a plan that doesn't match the
dry run).
"""

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_SCHEMA = HERE / "review-config.schema.json"

DRY_RUN_FILE = "filing-dry-run.md"
STATE_FILE = "filing-state.json"
FINDINGS_FILE = "findings.jsonl"
SUMMARY_FILE = "summary.json"
EXPLOITABLE_FILE = "exploitable.json"
SWEEP_FILE = "sweep.json"
QUESTIONS_FILE = "questions.md"
CHECK_FILE = ".text-check.md"

SEVERITY_FOR_ADVISORY = {"High": "high", "Med": "medium", "Low": "low"}

_TEXT = {"type": "string", "minLength": 1}
_TEXTS = {"type": "array", "items": _TEXT}

FINDING_SCHEMA = {
    "type": "object",
    "required": ["id", "title", "severity", "kind", "area", "requirements", "code",
                 "what_goes_wrong", "how_run", "remedy", "confirmations"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "pattern": r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"},
        "title": {"type": "string", "minLength": 1, "pattern": r"^[^\n]+$"},
        "severity": {"type": "string", "enum": ["High", "Med", "Low"]},
        "kind": _TEXT,
        "area": {"type": ["string", "null"], "minLength": 1},
        "requirements": _TEXTS,
        "code": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["file", "line", "quote"],
                "additionalProperties": False,
                "properties": {
                    "file": _TEXT,
                    "line": {"type": ["integer", "string"]},
                    "quote": {"type": "string"},
                },
            },
        },
        "what_goes_wrong": _TEXT,
        "how_run": _TEXT,
        "remedy": _TEXT,
        "alternatives": _TEXTS,
        "decision": _TEXT,
        "confirmations": {"type": "integer", "minimum": 0},
        "question": {"type": "boolean"},
        "exploitable": {"type": "boolean"},
        "advisory": {"type": "boolean"},
    },
}

SUMMARY_SCHEMA = {
    "type": "object",
    "required": ["commit", "base_commit", "skill_commit", "branch_commit", "scope", "checking",
                 "how_it_ran", "models", "verdict", "matters_most", "checked_and_sound",
                 "where_things_stand"],
    "additionalProperties": False,
    "properties": {
        "commit": {"type": "string", "pattern": r"^[0-9a-f]{7,40}$"},
        "base_commit": {"type": ["string", "null"], "pattern": r"^[0-9a-f]{7,40}$"},
        "skill_commit": {"type": "string", "pattern": r"^[0-9a-f]{7,40}$"},
        "branch_commit": {"type": "string", "pattern": r"^[0-9a-f]{7,40}$"},
        "scope": {"type": "string", "enum": ["full", "incremental"]},
        "checking": {"type": "string", "enum": ["checked", "quick", "quick, checked later"]},
        "how_it_ran": _TEXT,
        "models": _TEXT,
        "verdict": {"type": "string", "minLength": 1, "pattern": r"^[^\n]+$"},
        "matters_most": _TEXTS,
        "checked_and_sound": _TEXTS,
        "where_things_stand": _TEXTS,
    },
}


class Refused(Exception):
    """A bad config or input: nothing is posted (exit 2)."""


class Failed(Exception):
    """A text check or gh call failed part-way (exit 1)."""


# ---- a small JSON Schema checker: the keywords the schemas here use ----

_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def _is(value, name):
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, _TYPES[name])


def check_schema(value, schema, where):
    types = schema.get("type")
    if types is not None:
        names = types if isinstance(types, list) else [types]
        if not any(_is(value, n) for n in names):
            raise Refused(f"{where}: must be {' or '.join(names)}, not {json.dumps(value)}")
    if "enum" in schema and value not in schema["enum"]:
        raise Refused(f"{where}: must be one of {', '.join(map(str, schema['enum']))}, "
                      f"not {json.dumps(value)}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise Refused(f"{where}: must not be empty")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            raise Refused(f"{where}: {json.dumps(value)} does not match {schema['pattern']}")
    if _is(value, "integer") and "minimum" in schema and value < schema["minimum"]:
        raise Refused(f"{where}: must be at least {schema['minimum']}")
    if isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                raise Refused(f"{where}.{name}: missing")
        props = schema.get("properties", {})
        for name, item in value.items():
            if name in props:
                check_schema(item, props[name], f"{where}.{name}")
            elif schema.get("additionalProperties", True) is False:
                raise Refused(f"{where}.{name}: not a known field")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise Refused(f"{where}: needs at least {schema['minItems']} items")
        for i, item in enumerate(value):
            if "items" in schema:
                check_schema(item, schema["items"], f"{where}[{i}]")
        if schema.get("uniqueItems") and len({json.dumps(v) for v in value}) != len(value):
            raise Refused(f"{where}: has the same item twice")


def load_json(path, what):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise Refused(f"{what} {path}: {e.strerror}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise Refused(f"{what} {path}: not JSON (line {e.lineno}: {e.msg})")


def load_config(path):
    config = load_json(path, "config")
    check_schema(config, load_json(CONFIG_SCHEMA, "schema"), "config")
    config.setdefault("labels", [])
    config.setdefault("question_label", "question")
    return config


def load_findings(pad):
    path = pad / FINDINGS_FILE
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        raise Refused(f"findings {path}: {e.strerror}")
    findings, seen = [], set()
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as e:
            raise Refused(f"{FINDINGS_FILE} line {n}: not JSON ({e.msg})")
        check_schema(record, FINDING_SCHEMA, f"{FINDINGS_FILE} line {n}")
        if record["id"] == "summary":
            raise Refused(f"{FINDINGS_FILE} line {n}.id: \"summary\" is the summary's own")
        if record["id"] in seen:
            raise Refused(f"{FINDINGS_FILE} line {n}.id: {record['id']} is used twice")
        seen.add(record["id"])
        findings.append(record)
    return findings


EXPLOITABLE_SCHEMA = {"type": "array", "items": FINDING_SCHEMA["properties"]["id"],
                      "uniqueItems": True}


def load_exploitable(pad):
    """The claim ids the review has flagged exploitable if public, from exploitable.json."""
    path = pad / EXPLOITABLE_FILE
    if not path.exists():
        return set()
    ids = load_json(path, "exploitable")
    check_schema(ids, EXPLOITABLE_SCHEMA, EXPLOITABLE_FILE)
    return set(ids)


def load_summary(pad):
    summary = load_json(pad / SUMMARY_FILE, "summary")
    check_schema(summary, SUMMARY_SCHEMA, SUMMARY_FILE)
    return summary


SWEEP_PREFIX = "sweep:"

SWEEP_SCHEMA = {
    "type": "object",
    "required": ["label"],
    "additionalProperties": False,
    "properties": {
        "label": {"type": "string", "pattern": r"^sweep:\S+$"},
        "step": {"type": ["integer", "null"], "minimum": 1},
    },
}


def load_sweep(pad):
    """The review's sweep label and its own step, from sweep.json, which Phase 0 writes."""
    path = pad / SWEEP_FILE
    if not path.exists():
        raise Refused(f"{path}: missing; every review is a sweep: Phase 0 writes its sweep label "
                      f"(and the review's own step) there, as {{\"label\": \"sweep:H1\", "
                      f"\"step\": 41}}")
    sweep = load_json(path, "sweep")
    check_schema(sweep, SWEEP_SCHEMA, SWEEP_FILE)
    sweep.setdefault("step", None)
    return sweep


# ---- the sweep: parents and numbered titles ----

OPEN_ISSUES_QUERY = """query($owner: String!, $name: String!, $label: String!, $endCursor: String) {
  repository(owner: $owner, name: $name) {
    issues(first: 100, after: $endCursor, states: OPEN, labels: [$label]) {
      nodes { number title body parent { number } labels(first: 100) { nodes { name } } }
      pageInfo { hasNextPage endCursor }
    }
  }
}"""

STEP_ID = re.compile(r"^([A-Za-z]+[0-9]+(?:\.[0-9]+)+)(?=\s|$)")


def is_finding(body):
    """Whether an issue's body carries a finding's marker: a review's, or a pull request review's
    filed issue. A finding is never a parent."""
    return bool(MARKER.search(body)) or \
        any(m.group(2).endswith(" issue") for m in PR_MARKER.finditer(body))


def step_id(title):
    """The leading id of a step's title, "H1.6" of "H1.6 Trust and signatures", or None."""
    m = STEP_ID.match(title)
    return m.group(1) if m else None


class Sweep:
    """A sweep's open issues, read once a run: the issues that may be a parent are those with the
    sweep label, no parent of their own and no finding's marker. The script never makes one."""

    def __init__(self, config, label, step=None):
        self.config, self.label, self.step = config, label, None
        owner, name = config["repo"].split("/")
        out = run(["gh", "api", "graphql", "--paginate", "-f", f"query={OPEN_ISSUES_QUERY}",
                   "-f", f"owner={owner}", "-f", f"name={name}", "-f", f"label={label}"],
                  f"gh api graphql (the open issues labelled {label})")
        self.candidates = []
        for page in json_values(out):
            for node in page["data"]["repository"]["issues"]["nodes"]:
                if node.get("parent") or is_finding(node.get("body") or ""):
                    continue
                self.candidates.append({"number": node["number"], "title": node["title"],
                                        "labels": [x["name"] for x in node["labels"]["nodes"]]})
        self._subs = {}
        if step is not None:
            self.step = next((i for i in self.candidates if i["number"] == step), None)
            if self.step is None:
                raise Refused(f"{SWEEP_FILE}.step: #{step} is not an open issue labelled {label} "
                              "with no parent of its own and no finding's marker")

    def parent(self, area):
        """(issue, None), (None, None) when there is no parent, or (None, why) when the search
        fails. A finding no area owns goes under the review's own step, when there is one."""
        if area is None:
            return self.step, None
        label = self.config["area_prefix"] + area
        matches = [i for i in self.candidates if label in i["labels"]]
        if len(matches) == 1:
            return matches[0], None
        if not matches:
            return None, (f"area {area}: no open issue labelled {label} and {self.label} with no "
                          "parent of its own; the sweep's planning makes its steps")
        return None, (f"area {area}: {len(matches)} open issues could be its parent ("
                      + ", ".join(f"#{i['number']}" for i in matches)
                      + "); an area has at most one open step")

    def sub_issues(self, number):
        """The parent's sub-issues in every state, read once a run."""
        if number not in self._subs:
            out = run(["gh", "api", "--paginate",
                       f"repos/{self.config['repo']}/issues/{number}/sub_issues?per_page=100"],
                      f"gh api issues/{number}/sub_issues (list)")
            self._subs[number] = [{"number": i["number"], "title": i["title"],
                                   "body": i.get("body") or ""}
                                  for page in json_values(out) for i in page]
        return self._subs[number]

    def titles(self, entries, own):
        """entries: (key, parent or None, sentence), in filing order. The title is "<step id>-<m>
        <sentence>", m numbering on from the highest among the parent's sub-issues, those whose
        body own(body) says are these entries' (filed by an earlier run) left out; a parent title
        with no leading id, or no parent, gives the plain sentence. {key: title}."""
        next_m, titles = {}, {}
        for key, parent, sentence in entries:
            sid = step_id(parent["title"]) if parent else None
            if sid is None:
                titles[key] = sentence
                continue
            n = parent["number"]
            if n not in next_m:
                pattern = re.compile(rf"^{re.escape(sid)}-([0-9]+)(?=\s|$)")
                found = [int(m.group(1)) for s in self.sub_issues(n) if not own(s["body"])
                         for m in [pattern.match(s["title"])] if m]
                next_m[n] = max(found, default=0) + 1
            titles[key] = f"{sid}-{next_m[n]} {sentence}"
            next_m[n] += 1
        return titles


def attach(config, sweep, parent, record, body_path):
    """Make the issue in record a sub-issue of parent, unless it is one already."""
    n, repo = record["number"], config["repo"]
    if any(s["number"] == n for s in sweep.sub_issues(parent)):
        print(f"#{n}: a sub-issue of #{parent} already; recorded")
        return parent
    out = run(["gh", "api", f"repos/{repo}/issues/{n}", "--jq", ".id"], f"gh api issues/{n}")
    try:
        child = int(out.strip())
    except ValueError:
        raise Failed(f"gh api issues/{n}: no id in its answer:\n{out}")
    gh_post(f"repos/{repo}/issues/{parent}/sub_issues", {"sub_issue_id": child}, body_path,
            f"gh api issues/{parent}/sub_issues (#{n})")
    print(f"#{n}: a sub-issue of #{parent}")
    return parent


# ---- commands ----

def run(argv, what, stdin=None):
    try:
        done = subprocess.run(argv, input=stdin, capture_output=True, text=True)
    except OSError as e:
        raise Failed(f"{what}: cannot run {argv[0]}: {e.strerror}")
    if done.returncode != 0:
        raise Failed(f"{what} failed (exit {done.returncode}):\n{done.stdout}{done.stderr}".rstrip())
    return done.stdout


def list_areas(config):
    if "areas_command" in config:
        out = run(shlex.split(config["areas_command"]), "areas_command")
        return {line.strip() for line in out.splitlines() if line.strip()}
    out = run(["gh", "label", "list", "--repo", config["repo"], "--limit", "1000",
               "--json", "name"], "gh label list")
    prefix = config["area_prefix"]
    return {label["name"][len(prefix):] for label in json.loads(out)
            if label["name"].startswith(prefix)}


def text_check(config, pad, title, body):
    """None when the text passes (or there is no check), else the check's output."""
    if "text_check" not in config:
        return None
    path = pad / CHECK_FILE
    path.write_text(f"{title}\n\n{body}", encoding="utf-8")
    try:
        argv = [a.replace("{file}", str(path)) for a in shlex.split(config["text_check"])]
        done = subprocess.run(argv, capture_output=True, text=True)
    finally:
        path.unlink(missing_ok=True)
    if done.returncode == 0:
        return None
    return (done.stdout + done.stderr).strip() or f"exit {done.returncode}"


# ---- the plan ----

def review_name(config):
    return f"{config['name']['prefix']}{config['name']['number']}"


def fence(text, mark="`"):
    longest = max((len(m) for m in re.findall(f"{re.escape(mark)}+", text)), default=0)
    return mark * max(3, longest + 1)


def marker(config, item_id):
    """The hidden line every body ends with, so a re-run finds what an earlier run posted."""
    return f"<!-- review {review_name(config)} {item_id} -->"


MARKER = re.compile(r"<!-- review (\S+) (\S+) -->")


def finding_body(config, f, review=None, end=None, title=False):
    """review and end replace the review line and the marker; title puts the title first. A pull
    request's finding has a class: "[class] severity X" opens a line comment (title), and an issue's
    body has "severity X", then "class X"."""
    cls = f.get("class")
    if cls and title:
        lines = [f"[{cls}] severity {f['severity']}", ""]
    else:
        lines = [f"severity {f['severity']}"] + ([f"class {cls}"] if cls else []) + [""]
    if title:
        lines += [f"**{f['title']}**", ""]
    lines.append(f"**Kind:** {f['kind']}")
    lines.append(f"**Requirements:** {', '.join(f['requirements']) or 'none (untraced)'}")
    lines.append(f"**Confirmations:** {f['confirmations']}")
    lines.append(review or f"**Review:** {review_name(config)}, work-pad id {f['id']}")
    if f.get("question"):
        lines.append("**A choice for the owner:** walked thru before anyone acts on it.")
    if f["code"]:
        lines += ["", "**Code**"]
        for c in f["code"]:
            mark = fence(c["quote"])
            lines += ["", f"`{c['file']}:{c['line']}`", mark, c["quote"].rstrip("\n"), mark]
    lines += ["", "**What goes wrong**", "", f["what_goes_wrong"]]
    lines += ["", "**How it was run**", "", f["how_run"]]
    lines += ["", "**Remedy**", "", f["remedy"]]
    if f.get("alternatives"):
        lines += ["", "**Alternatives**", ""] + [f"- {a}" for a in f["alternatives"]]
    if f.get("decision"):
        lines += ["", "**Decision**", "", f["decision"]]
    lines += ["", end or marker(config, f["id"])]
    return "\n".join(lines) + "\n"


def link_placeholder(finding_id):
    return f"#<{finding_id}>"


def summary_body(config, summary, items, links, sweep):
    """links maps a finding's id to its issue link; ids not in it get a placeholder."""
    n = config["name"]["number"]
    branch = f"code-review-{n:04d}"
    lines = [
        f"**Sweep:** `{sweep['label']}`",
        f"**Commit read:** {summary['commit']}",
        "**Delta from:** " + (summary["base_commit"] or
                              "none: the project's first review, read in full"),
        f"**Method:** the `review` skill at {summary['skill_commit']}",
        f"**Work pad:** `review/{n:04d}/` on the local branch `{branch}`, last commit "
        f"{summary['branch_commit']}, kept until the next review has read it",
        f"**Scope:** {summary['scope']}",
        f"**Checking:** {summary['checking']}",
        f"**How it ran:** {summary['how_it_ran']}",
        f"**Models and effort:** {summary['models']}",
        "",
        f"**Verdict:** {summary['verdict']}",
    ]
    lines += ["", "## What matters most", ""] + [f"- {t}" for t in summary["matters_most"]]
    issues = [i for i in items if i["type"] == "issue"]
    advisories = [i for i in items if i["type"] == "advisory"]
    lines += ["", "## Findings", ""]
    for i in issues:
        f = i["finding"]
        area = f["area"] or "none"
        link = links.get(f["id"], link_placeholder(f["id"]))
        lines.append(f"- {link} severity {f['severity']}, {f['kind']}, area {area}: {i['title']}")
    if not issues:
        lines.append("- none filed as issues")
    if advisories:
        filed = ("finding is filed as a draft security advisory" if len(advisories) == 1
                 else "findings are filed as draft security advisories")
        lines += ["", f"{len(advisories)} more {filed}, private to the maintainers."]
    for heading, key in (("Checked and sound", "checked_and_sound"),
                         ("Where things stand", "where_things_stand")):
        lines += ["", f"## {heading}", ""] + [f"- {t}" for t in summary[key]]
    lines += ["", marker(config, "summary")]
    return "\n".join(lines) + "\n"


def issue_labels(config, f, sweep_label=None):
    labels = list(config["labels"])
    if sweep_label:
        labels.append(sweep_label)
    if f["area"] is not None:
        labels.append(config["area_prefix"] + f["area"])
    if "kind_prefix" in config:
        labels.append(config["kind_prefix"] + f["kind"])
    if f.get("question"):
        labels.append(config["question_label"])
    return list(dict.fromkeys(labels))


def check_area(f, areas, where):
    if f["area"] is not None and f["area"] not in areas:
        raise Refused(f"{where} {f['id']}.area: {f['area']!r} is not one of the "
                      f"project's areas ({', '.join(sorted(areas)) or 'none listed'})")


def own_markers(keys, ids):
    """own(body): whether a body carries the marker of one of ids, by keys(body)."""
    return lambda body: any(k in ids for k in keys(body))


def build_plan(config, pad):
    findings = load_findings(pad)
    summary = load_summary(pad)
    sweep_record = load_sweep(pad)
    areas = list_areas(config)
    flagged = load_exploitable(pad)
    sweep = Sweep(config, sweep_record["label"], sweep_record["step"])
    items, entries, failures = [], [], []
    for f in findings:
        check_area(f, areas, FINDINGS_FILE)
        body = finding_body(config, f)
        exploitable = f.get("exploitable", False)
        mark = {"exploitable": exploitable,
                "advisory_set": "advisory" in f and f["advisory"] != exploitable,
                "unflagged": f["id"] in flagged and not exploitable}
        if f.get("advisory", exploitable):
            # An advisory can't be a sub-issue: a plain title, no parent, not numbered.
            items.append({"id": f["id"], "type": "advisory", "title": f["title"], "body": body,
                          "labels": [], "severity": SEVERITY_FOR_ADVISORY[f["severity"]],
                          "parent": None, "mark": mark, "finding": f})
            continue
        parent, why = sweep.parent(f["area"])
        if why:
            failures.append(f"{f['id']}: {why}")
        entries.append((f["id"], parent, f["title"]))
        items.append({"id": f["id"], "type": "issue", "title": f["title"], "body": body,
                      "labels": issue_labels(config, f, sweep_record["label"]),
                      "parent": parent["number"] if parent else None,
                      "parent_title": parent["title"] if parent else None,
                      "mark": mark, "finding": f})
    ids = {i["id"] for i in items}
    titles = sweep.titles(entries, own_markers(review_keys(config), ids))
    for item in items:
        item["title"] = titles.get(item["id"], item["title"])
    step = sweep_record["step"]
    return {
        "repo": config["repo"],
        "sweep": sweep_record,
        "items": items,
        "failures": failures,
        "summary": {"title": f"{review_name(config)}: summary",
                    "body": summary_body(config, summary, items, {}, sweep_record),
                    "on": step, "data": summary},
        "records": {"findings": findings, "summary": summary, "sweep": sweep_record},
        "sweep_issues": sweep,
    }


def plan_hash(plan):
    keep = {"repo": plan["repo"],
            "items": [{k: v for k, v in i.items() if k != "finding"} for i in plan["items"]],
            "summary": {"title": plan["summary"]["title"], "body": plan["summary"]["body"],
                        "on": plan["summary"]["on"]}}
    return hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest()


def records_hash(plan):
    """The records alone: what the plan is built from, without what the repository gives it (the
    parents and the numbers)."""
    keep = {"repo": plan["repo"], **plan["records"]}
    return hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest()


def item_hash(title, body):
    return hashlib.sha256(f"{title}\n{body}".encode()).hexdigest()


# ---- dry-run ----

def parent_line(item):
    if item["type"] == "advisory":
        return "- parent: none (an advisory can't be a sub-issue)"
    if item["type"] == "summary":
        return "- parent: none"
    if item["parent"] is None:
        why = item.get("why")
        return f"- parent: FAILED: {why}" if why else \
            "- parent: none (no area, and no step for the review)"
    return f"- parent: #{item['parent']} {item['parent_title']}"


def write_dry_run(config, pad, plan, failures):
    sweep, step = plan["sweep"], plan["summary"]["on"]
    out = [f"# {review_name(config)} filing: dry run", "",
           f"plan sha256: {plan_hash(plan)}",
           f"records sha256: {records_hash(plan)}", "",
           f"Repository: {plan['repo']}. Nothing was posted. `post` posts exactly this plan: to "
           f"change it, change `{FINDINGS_FILE}`, `{SUMMARY_FILE}` or `{SWEEP_FILE}` and run the "
           "dry run again.", "",
           f"Sweep: `{sweep['label']}`; the review's own step: "
           + (f"#{step}." if step else "none given."), ""]
    n_adv = sum(1 for i in plan["items"] if i["type"] == "advisory")
    n_issues = len(plan["items"]) - n_adv
    out.append(f"Findings: {n_issues} as public issues, {n_adv} as draft security advisories; "
               + (f"then the summary, as a comment on #{step}." if step
                  else "then the summary issue."))
    out.append("")
    if plan["failures"]:
        out += ["Parents: FAILED, so `post` refuses this plan:", ""] + \
            [f"- {why}" for why in plan["failures"]] + [""]
    else:
        out += ["Parents: one found for every finding that has an area or goes under the review's "
                "own step.", ""]
    if "text_check" not in config:
        out.append("Text check: none configured.")
    elif failures:
        out.append("Text check: FAILED for " + ", ".join(failures) + ".")
    else:
        out.append("Text check: passed for every title and body.")
    out.append("")
    unflagged = [i["id"] for i in plan["items"] if i["mark"]["unflagged"]]
    if unflagged:
        out += [f"Check the marks: {', '.join(unflagged)} flagged in `{EXPLOITABLE_FILE}` but not "
                f"`exploitable` in `{FINDINGS_FILE}`.", ""]
    why = {w.split(":", 1)[0]: w.split(": ", 1)[1] for w in plan["failures"]}
    entries = [dict(i, why=why.get(i["id"])) for i in plan["items"]] + \
        [{"id": "summary", "type": "summary", **plan["summary"], "labels": []}]
    for k, item in enumerate(entries, 1):
        if item["type"] == "advisory":
            where = f"draft security advisory, private, severity {item['severity']}"
        elif item["type"] == "issue":
            where = "public issue"
        elif step:
            where = f"a comment on #{step}: the summary, posted last, with each finding's link"
        else:
            where = "public issue: the summary, posted last, with each finding's link"
        mark = fence(item["body"])
        out += [f"## {k}. {item['id']}: {where}", "",
                f"- title: {item['title']}",
                f"- labels: {', '.join(item['labels']) or 'none'}",
                parent_line(item)]
        if "mark" in item:
            m = item["mark"]
            line = f"- exploitable if public: {'yes' if m['exploitable'] else 'no'}"
            if m["advisory_set"]:
                line += ("; filed as a public issue anyway (`advisory: false`)"
                         if m["exploitable"] else "; filed as an advisory anyway (`advisory: true`)")
            if m["unflagged"]:
                line += f"; flagged in `{EXPLOITABLE_FILE}`"
            out.append(line)
        out += ["", mark + "markdown", item["body"].rstrip("\n"), mark, ""]
    (pad / DRY_RUN_FILE).write_text("\n".join(out), encoding="utf-8")


def cmd_dry_run(config, pad):
    plan = build_plan(config, pad)
    failures = []
    for item in plan["items"] + [{"id": "summary", **plan["summary"]}]:
        result = text_check(config, pad, item["title"], item["body"])
        if result is not None:
            failures.append(item["id"])
            print(f"text check failed for {item['id']}:\n{result}", file=sys.stderr)
    for why in plan["failures"]:
        print(f"no parent for {why}", file=sys.stderr)
    write_dry_run(config, pad, plan, failures)
    print(f"wrote {pad / DRY_RUN_FILE}: {len(plan['items'])} findings and the summary; "
          "nothing posted")
    return 1 if failures or plan["failures"] else 0


# ---- post ----

def read_state(pad, name=STATE_FILE):
    path = pad / name
    if not path.exists():
        return {"posted": {}}
    return load_json(path, "state")


def write_state(pad, state, name=STATE_FILE):
    path = pad / name
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def create_issue(repo, title, body_path, labels):
    argv = ["gh", "issue", "create", "--repo", repo, "--title", title, "--body-file", str(body_path)]
    for label in labels:
        argv += ["--label", label]
    out = run(argv, f"gh issue create ({title})")
    m = re.search(r"https://\S+/issues/(\d+)", out)
    if not m:
        raise Failed(f"gh issue create ({title}): no issue link in its output:\n{out}")
    return {"number": int(m.group(1)), "url": m.group(0)}


def create_advisory(config, item, body_path):
    package = config.get("advisory_package",
                         {"ecosystem": "other", "name": config["repo"].split("/")[1]})
    payload = {"summary": item["title"], "description": item["body"],
               "severity": item["severity"], "vulnerabilities": [{"package": package}]}
    body_path.write_text(json.dumps(payload), encoding="utf-8")
    out = run(["gh", "api", "--method", "POST", f"repos/{config['repo']}/security-advisories",
               "--input", str(body_path)], f"gh api security-advisories ({item['id']})")
    try:
        answer = json.loads(out)
        return {"ghsa_id": answer["ghsa_id"], "url": answer["html_url"]}
    except (json.JSONDecodeError, KeyError, TypeError):
        raise Failed(f"gh api security-advisories ({item['id']}): unexpected answer:\n{out}")


def json_values(text):
    """The JSON values in text, one after another (gh api --paginate prints one per page)."""
    decoder, values, at = json.JSONDecoder(), [], 0
    while True:
        while at < len(text) and text[at].isspace():
            at += 1
        if at == len(text):
            return values
        value, at = decoder.raw_decode(text, at)
        values.append(value)


def review_keys(config):
    name = review_name(config)
    return lambda text: [m.group(2) for m in MARKER.finditer(text) if m.group(1) == name]


def already_posted(config, keys=None):
    """What earlier runs posted, by the marker in its body: {item id: record}. keys(text) gives the
    ids a body's markers name; by default those of this review's own markers."""
    keys = keys or review_keys(config)
    repo, found = config["repo"], {}
    out = run(["gh", "issue", "list", "--repo", repo, "--state", "all", "--limit", "10000",
               "--json", "number,url,body"], "gh issue list")
    for issue in json.loads(out):
        for key in keys(issue.get("body") or ""):
            found.setdefault(key, {"number": issue["number"], "url": issue["url"]})
    out = run(["gh", "api", "--paginate", f"repos/{repo}/security-advisories?per_page=100"],
              "gh api security-advisories (list)")
    for page in json_values(out):
        for advisory in page:
            for key in keys(advisory.get("description") or ""):
                found.setdefault(key, {"ghsa_id": advisory["ghsa_id"],
                                       "url": advisory["html_url"]})
    return found


def step_comment_posted(config, step, key):
    """The comment on the step that carries this review's marker for key, read only from comments by
    an owner, member or collaborator; else None."""
    out = run(["gh", "api", "--paginate",
               f"repos/{config['repo']}/issues/{step}/comments?per_page=100"],
              f"gh api issues/{step}/comments (list)")
    keys = review_keys(config)
    for page in json_values(out):
        for c in page:
            if c.get("author_association") in TRUSTED and key in keys(c.get("body") or ""):
                return {"id": c["id"], "url": c.get("html_url")}
    return None


def cmd_post(config, pad):
    plan = build_plan(config, pad)
    dry = pad / DRY_RUN_FILE
    if not dry.exists():
        raise Refused(f"no dry run: run dry-run first and read {dry}")
    text = dry.read_text(encoding="utf-8")
    if plan["failures"]:
        raise Refused("no parent for " + "; ".join(plan["failures"])
                      + ": nothing posted; fix the steps or the records and run dry-run again")
    m = re.search(r"^plan sha256: ([0-9a-f]{64})$", text, re.M)
    r = re.search(r"^records sha256: ([0-9a-f]{64})$", text, re.M)
    if not m or not r or r.group(1) != records_hash(plan):
        raise Refused(f"the plan differs from {dry}: run dry-run again and read it before posting")
    if m.group(1) != plan_hash(plan):
        raise Refused(f"a parent or a number differs from {dry} (an issue changed in the "
                      "repository since): run dry-run again and read it before posting")
    state = read_state(pad)
    posted = state.setdefault("posted", {})
    body_path = pad / ".filing-body"
    sweep = plan["sweep_issues"]
    found = None

    def post_one(item_id, kind, title, body, create, lookup=None):
        nonlocal found
        done = posted.get(item_id)
        if done:
            if done["hash"] != item_hash(title, body):
                print(f"{item_id}: posted earlier as {done['url']}, and its text has changed "
                      "since; left as it is", file=sys.stderr)
            return done
        if lookup:
            record = lookup()
        else:
            if found is None:
                found = already_posted(config)
            record = found.get(item_id)
        if record:
            record = dict(record, found=True)
            print(f"{item_id}: found already posted as {record['url']}; recorded, not posted again")
        else:
            result = text_check(config, pad, title, body)
            if result is not None:
                raise Failed(f"text check failed for {item_id}; nothing more posted:\n{result}")
            record = create()
            print(f"{item_id}: {record['url']}")
        record.update(type=kind, hash=item_hash(title, body))
        posted[item_id] = record
        write_state(pad, state)
        return record

    def issue(title, body, labels):
        def create():
            body_path.write_text(body, encoding="utf-8")
            return create_issue(plan["repo"], title, body_path, labels)
        return create

    try:
        for item in plan["items"]:
            if item["type"] == "advisory":
                create = lambda item=item: create_advisory(config, item, body_path)
            else:
                create = issue(item["title"], item["body"], item["labels"])
            record = post_one(item["id"], item["type"], item["title"], item["body"], create)
            if item["parent"] and not record.get("attached"):
                record["attached"] = attach(config, sweep, item["parent"], record, body_path)
                write_state(pad, state)
        links = {i: f"#{r['number']}" for i, r in posted.items() if r.get("type") == "issue"}
        title = plan["summary"]["title"]
        body = summary_body(config, plan["summary"]["data"], plan["items"], links, plan["sweep"])
        step = plan["summary"]["on"]
        if step:
            post_one("summary", "comment", title, body,
                     lambda: gh_post(f"repos/{plan['repo']}/issues/{step}/comments",
                                     {"body": body}, body_path,
                                     f"gh api issues/{step}/comments (the summary)"),
                     lookup=lambda: step_comment_posted(config, step, "summary"))
        else:
            post_one("summary", "summary", title, body, issue(title, body, []))
        return 0
    finally:
        body_path.unlink(missing_ok=True)


# ---- question ----

QUESTION_SCHEMA = {
    "type": "object",
    "required": ["question", "options", "recommendation", "area"],
    "additionalProperties": False,
    "properties": {
        "question": _TEXT,
        "options": {
            "type": "array",
            "minItems": 2,
            "items": {
                "type": "object",
                "required": ["option", "means"],
                "additionalProperties": False,
                "properties": {"option": _TEXT, "means": _TEXT},
            },
        },
        "recommendation": _TEXT,
        "claim": FINDING_SCHEMA["properties"]["id"],
        "area": FINDING_SCHEMA["properties"]["area"],
    },
}


def question_title(config, q):
    first = q["question"].strip().splitlines()[0]
    if len(first) > 100:
        first = first[:97].rstrip() + "..."
    return f"{review_name(config)} question: {first}"


def question_body(config, q):
    lines = [f"**Question:** {q['question'].strip()}", "", "**Options**", ""]
    for k, o in enumerate(q["options"], 1):
        lines.append(f"{k}. **{o['option']}**: {o['means']}")
    lines += ["", f"**Recommendation:** {q['recommendation']}", ""]
    if "claim" in q:
        lines.append(f"**Claim:** {q['claim']}, in the work pad of review {review_name(config)}")
    else:
        lines.append(f"**Review:** {review_name(config)}")
    lines += ["", "Walked thru on the owner's return; the answer is a comment here."]
    return "\n".join(lines) + "\n"


def keep_in_questions_md(pad, title, body, reason):
    with open(pad / QUESTIONS_FILE, "a", encoding="utf-8") as f:
        f.write(f"## {title}\n\nKept here: {reason}\n\n{body}\n")
    print(f"kept in {pad / QUESTIONS_FILE}: {reason}")


def file_question_issue(config, pad, title, body, labels):
    """The new issue's record; Failed when the text check or gh refuses it."""
    result = text_check(config, pad, title, body)
    if result is not None:
        raise Failed(f"text check failed:\n{result}")
    body_path = pad / ".question-body"
    body_path.write_text(body, encoding="utf-8")
    try:
        return create_issue(config["repo"], title, body_path, labels)
    finally:
        body_path.unlink(missing_ok=True)


def cmd_question(config, pad, path):
    q = load_json(path, "question")
    check_schema(q, QUESTION_SCHEMA, "question")
    sweep_record = load_sweep(pad)
    title, body = question_title(config, q), question_body(config, q)
    private = "claim" in q and q["claim"] in load_exploitable(pad)
    area = q["area"]
    if private:
        keep_in_questions_md(pad, title, body,
                             f"private: claim {q['claim']} is flagged exploitable if public")
        title = f"{review_name(config)} question: a private question is waiting"
        body = ("A question about one of this review's claims is waiting in its local work pad. "
                "It is kept private, and walked thru on the owner's return.\n")
        area = None  # its area would say where to look: the notice goes under the review's step
    why_kept = (lambda e: f"the notice for the private question above could not be filed: {e}") \
        if private else (lambda e: f"it could not be filed: {e}")
    labels = list(config["labels"]) + [config["question_label"], sweep_record["label"]]
    try:
        if q["area"] is not None:
            areas = list_areas(config)
            if q["area"] not in areas:
                raise Refused(f"question.area: {q['area']!r} is not one of the project's areas "
                              f"({', '.join(sorted(areas)) or 'none listed'})")
        if area is not None:
            labels.append(config["area_prefix"] + area)
        sweep = Sweep(config, sweep_record["label"], sweep_record["step"])
        parent, why = sweep.parent(area)
        if why:
            raise Failed(f"no parent for the question's {why}")
        title = sweep.titles([("q", parent, title)], lambda body: False)["q"]
        record = file_question_issue(config, pad, title, body, list(dict.fromkeys(labels)))
    except (Failed, Refused) as e:
        keep_in_questions_md(pad, title, body, why_kept(e))
        return 1
    print(f"filed: {record['url']}")
    if parent:
        body_path = pad / ".question-body"
        try:
            attach(config, sweep, parent["number"], record, body_path)
        except Failed as e:
            keep_in_questions_md(pad, title, body, f"filed as {record['url']}, but not made a "
                                 f"sub-issue of #{parent['number']}: {e}")
            return 1
        finally:
            body_path.unlink(missing_ok=True)
    return 0


# ---- a pull request's passes: pr post, pr file ----

PASS_FILE = re.compile(r"^pass-([1-9][0-9]*)\.json$")
PR_STATE_FILE = "pr-state.json"
PR_MARKER = re.compile(r"<!-- pr-review (\d+) ([^<>]+?) -->")
TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}

_SHA = {"type": "string", "pattern": r"^[0-9a-f]{7,40}$"}

_CLASS = {"type": "string", "enum": ["regression", "latent"]}

ADDITIONAL_SCHEMA = {
    **FINDING_SCHEMA,
    "required": FINDING_SCHEMA["required"] + ["class"],
    "properties": {**FINDING_SCHEMA["properties"], "class": _CLASS},
}

PR_FINDING_SCHEMA = {
    **FINDING_SCHEMA,
    "required": [r for r in FINDING_SCHEMA["required"] if r != "area"] + ["class", "at"],
    "properties": {
        **FINDING_SCHEMA["properties"],
        "class": _CLASS,
        "at": {
            "type": "object",
            "required": ["file", "line"],
            "additionalProperties": False,
            "properties": {
                "file": _TEXT,
                "line": {"type": "integer", "minimum": 1},
                "start_line": {"type": "integer", "minimum": 1},
                "side": {"type": "string", "enum": ["RIGHT", "LEFT"]},
            },
        },
    },
}

PASS_SCHEMA = {
    "type": "object",
    "required": ["pr", "pass", "head", "base", "skill_commit", "level", "checking", "verdict",
                 "read", "pieces", "findings", "additional", "replies"],
    "additionalProperties": False,
    "properties": {
        "pr": {"type": "integer", "minimum": 1},
        "pass": {"type": "integer", "minimum": 1},
        "head": {"type": "string", "pattern": r"^[0-9a-f]{40}$"},
        "base": _SHA,
        "skill_commit": _SHA,
        "level": {"type": "string", "enum": ["Standard", "Plus", "Premium"]},
        "checking": {"type": "string", "enum": ["checked", "quick"]},
        "verdict": {"type": "string", "minLength": 1, "pattern": r"^[^\n]+$"},
        "read": _TEXTS,
        "pieces": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["piece", "model", "effort", "tokens"],
                "additionalProperties": False,
                "properties": {"piece": _TEXT, "model": _TEXT, "effort": _TEXT,
                               "tokens": {"type": "integer", "minimum": 0}},
            },
        },
        "findings": {"type": "array", "items": PR_FINDING_SCHEMA},
        "additional": {"type": "array", "items": ADDITIONAL_SCHEMA},
        "replies": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "status", "evidence"],
                "additionalProperties": False,
                "properties": {"id": FINDING_SCHEMA["properties"]["id"],
                               "status": {"type": "string", "enum": ["fixed", "holds"]},
                               "sha": _SHA, "evidence": _TEXT},
            },
        },
    },
}


def pr_marker(n, key):
    return f"<!-- pr-review {n} {key} -->"


def pr_keys(n):
    return lambda text: [m.group(2) for m in PR_MARKER.finditer(text) if m.group(1) == str(n)]


def load_passes(pad, n):
    """{k: pass} from pass-<k>.json, and {id: (k, "findings" | "additional", record)} across them."""
    passes = {}
    for path in sorted(pad.iterdir()):
        m = PASS_FILE.match(path.name)
        if not m:
            continue
        record = load_json(path, "pass")
        check_schema(record, PASS_SCHEMA, path.name)
        if record["pass"] != int(m.group(1)):
            raise Refused(f"{path.name}.pass: {record['pass']} is not the file's number")
        if record["pr"] != n:
            raise Refused(f"{path.name}.pr: {record['pr']}, not {n}")
        if record["checking"] != "checked":
            raise Refused(f"{path.name}.checking: a pr-review pass is always checked; a quick look "
                          "is the built-in /code-review's")
        passes[record["pass"]] = record
    if not passes:
        raise Refused(f"work pad {pad}: no pass-<k>.json")
    if sorted(passes) != list(range(1, len(passes) + 1)):
        raise Refused(f"work pad {pad}: passes {sorted(passes)} are not 1, 2, ... without a gap")
    ids = {}
    for k in sorted(passes):
        p, where = passes[k], f"pass-{k}.json"
        if k > 1 and not passes[k - 1]["head"].startswith(p["base"]):
            raise Refused(f"{where}.base: {p['base']} is not pass {k - 1}'s head "
                          f"{passes[k - 1]['head']}")
        for part in ("findings", "additional"):
            for f in p[part]:
                if f["id"] in ids:
                    raise Refused(f"{where} {f['id']}: the id is used twice on this pull request")
                if part == "findings" and f["at"].get("start_line", 0) >= f["at"]["line"]:
                    raise Refused(f"{where} {f['id']}.at.start_line: must be before line")
                ids[f["id"]] = (k, part, f)
        replied = set()
        for r in p["replies"]:
            earlier = ids.get(r["id"])
            if not earlier or earlier[0] >= k or earlier[1] != "findings":
                raise Refused(f"{where} reply {r['id']}: not an earlier pass's finding in the diff")
            if r["id"] in replied:
                raise Refused(f"{where} reply {r['id']}: twice in one pass")
            if r["status"] == "fixed" and "sha" not in r:
                raise Refused(f"{where} reply {r['id']}.sha: a fixed finding names its commit")
            replied.add(r["id"])
    return passes, ids


def flagged(pad, ids):
    """Every id flagged exploitable: by its record, or in exploitable.json."""
    return {i for i, (_, _, f) in ids.items() if f.get("exploitable")} | load_exploitable(pad)


def asked(ids):
    """Every id that is a question for the owner (a plausible claim): never posted or filed."""
    return {i for i, (_, _, f) in ids.items() if f.get("question")}


def counts(findings):
    return "; ".join(
        f"{c} " + ", ".join(f"{s} {sum(f['class'] == c and f['severity'] == s for f in findings)}"
                            for s in ("High", "Med", "Low"))
        for c in ("regression", "latent"))


def where_of(f):
    return f"`{f['code'][0]['file']}:{f['code'][0]['line']}`" if f["code"] else "the documents"


def pr_review_body(n, p, findings, additional, replies):
    k = p["pass"]
    base = ("the merge base" if k == 1 else
            f"pass {k - 1}'s head, leaving out what came in with a merge of the target")
    lines = [f"**pr-review, pass {k}**: the head {p['head']}, from {base} ({p['base']})", "",
             f"**Verdict:** {p['verdict']}", "",
             f"**Findings:** {counts(findings + additional)} ({len(findings)} on their lines, "
             f"{len(additional)} additional)"]
    if k > 1:
        fixed = sum(r["status"] == "fixed" for r in replies)
        lines.append(f"**Earlier findings:** {fixed} fixed, {len(replies) - fixed} still hold, "
                     "in replies on their threads")
    lines += ["", "## What was read", ""] + [f"- {t}" for t in p["read"]]
    lines += ["", "## Additional findings", ""]
    lines += [f"- [{f['class']}] severity {f['severity']}, {where_of(f)}: {f['title']}"
              for f in additional] or ["- none"]
    if additional:
        lines += ["", "Filed as issues only when the owner says so."]
    lines += ["", "## How it ran", "",
              f"**Level:** {p['level']}, {p['checking']}. **Method:** the `pr-review` skill at "
              f"{p['skill_commit']}, as pinned on the target branch.", ""]
    lines += [f"- {x['piece']}: {x['model']}, {x['effort']}, {x['tokens']:,} tokens"
              for x in p["pieces"]]
    lines += ["", pr_marker(n, f"pass {k}")]
    return "\n".join(lines) + "\n"


def reply_body(n, k, p, r):
    head = f"fixed in {r['sha']}" if r["status"] == "fixed" else f"still holds at {p['head']}"
    key = f"{r['id']} reply {k}"
    return f"{head}\n\n{r['evidence'].rstrip()}\n\n{pr_marker(n, key)}\n"


def pr_threads(config, n):
    """What earlier runs posted on the pull request, by marker: ({key: record}, {id: comment id}
    of each finding's thread). Only reviews and comments by an owner, member or collaborator count;
    the others are never read, only counted."""
    repo, found, threads, skipped = config["repo"], {}, {}, 0
    for what, path in (("reviews", f"repos/{repo}/pulls/{n}/reviews?per_page=100"),
                       ("comments", f"repos/{repo}/pulls/{n}/comments?per_page=100")):
        out = run(["gh", "api", "--paginate", path], f"gh api pulls/{n}/{what} (list)")
        for page in json_values(out):
            for item in page:
                if item.get("author_association") not in TRUSTED:
                    skipped += 1
                    continue
                for key in pr_keys(n)(item.get("body") or ""):
                    found.setdefault(key, {f"{what[:-1]}_id": item["id"],
                                           "url": item.get("html_url")})
                    if what == "comments" and not item.get("in_reply_to_id"):
                        threads.setdefault(key, item["id"])
    if skipped:
        print(f"left unread: {skipped} reviews and comments by others on #{n}")
    return found, threads


def gh_post(path, payload, body_path, what):
    body_path.write_text(json.dumps(payload), encoding="utf-8")
    out = run(["gh", "api", "--method", "POST", path, "--input", str(body_path)], what)
    try:
        answer = json.loads(out)
        return {"id": answer["id"], "url": answer.get("html_url")}
    except (json.JSONDecodeError, KeyError, TypeError):
        raise Failed(f"{what}: unexpected answer:\n{out}")


def text_gate(config, pad, items):
    """items: (label, title, body). Every one is checked before anything is posted."""
    failures = []
    for label, title, body in items:
        result = text_check(config, pad, title, body)
        if result is not None:
            failures.append(label)
            print(f"text check failed for {label}:\n{result}", file=sys.stderr)
    if failures:
        raise Failed(f"text check failed for {', '.join(failures)}; nothing posted")


def post_items(pad, todo, found, state_file=PR_STATE_FILE):
    """todo: (key, kind, text, create[, attach]). Skips what the state or a marker shows is posted.
    attach(record), when given, runs once the item is made and until the state records it."""
    state = read_state(pad, state_file)
    posted = state.setdefault("posted", {})
    for key, kind, text, create, *then in todo:
        record = posted.get(key)
        if record:
            if record["hash"] != item_hash(kind, text):
                print(f"{key}: posted earlier as {record['url']}, and its text has changed since; "
                      "left as it is", file=sys.stderr)
        else:
            if key in found:
                record = dict(found[key], found=True)
                print(f"{key}: found already posted as {record['url']}; recorded, not posted again")
            else:
                record = create()
                print(f"{key}: {record['url']}")
            record.update(type=kind, hash=item_hash(kind, text))
            posted[key] = record
            write_state(pad, state, state_file)
        if then and then[0] and not record.get("attached"):
            record["attached"] = then[0](record)
            write_state(pad, state, state_file)


def report_kept(kept, questions=()):
    if kept:
        print("kept in the work pad, flagged exploitable: " + ", ".join(kept))
    if questions:
        print("kept in the work pad, questions for the owner: " + ", ".join(questions))


def cmd_pr_post(config, pad, n):
    passes, ids = load_passes(pad, n)
    p = passes[max(passes)]
    k, private, questions = p["pass"], flagged(pad, ids), asked(ids)
    local = private | questions
    findings = [f for f in p["findings"] if f["id"] not in local]
    additional = [f for f in p["additional"] if f["id"] not in local]
    replies = [r for r in p["replies"] if r["id"] not in local]
    every = p["findings"] + p["additional"] + p["replies"]
    kept = [x["id"] for x in every if x["id"] in private]
    held = [x["id"] for x in every if x["id"] in questions and x["id"] not in private]
    comments = []
    for f in findings:
        c = {"path": f["at"]["file"], "line": f["at"]["line"],
             "side": f["at"].get("side", "RIGHT"),
             "body": finding_body(config, f, review=f"**Pass:** {k}, work-pad id {f['id']}",
                                  end=pr_marker(n, f["id"]), title=True)}
        if "start_line" in f["at"]:
            c.update(start_line=f["at"]["start_line"], start_side=c["side"])
        comments.append(c)
    review = {"commit_id": p["head"], "event": "COMMENT",
              "body": pr_review_body(n, p, findings, additional, replies), "comments": comments}
    bodies = [(f"{r['id']} reply {k}", r, reply_body(n, k, p, r)) for r in replies]
    text_gate(config, pad, [(f"pass {k}", "", review["body"])] +
              [(f["id"], "", c["body"]) for f, c in zip(findings, comments)] +
              [(key, "", body) for key, _, body in bodies])
    posted = read_state(pad, PR_STATE_FILE)["posted"]
    keys = [f"pass {k}"] + [key for key, _, _ in bodies]
    found, threads = ({}, {}) if all(key in posted for key in keys) else pr_threads(config, n)
    for key, r, _ in bodies:
        if key not in posted and key not in found and r["id"] not in threads:
            raise Refused(f"{key}: no thread of {r['id']} on #{n} to reply on")
    body_path = pad / ".pr-body"
    repo = config["repo"]
    todo = [(f"pass {k}", "review", json.dumps(review, sort_keys=True),
             lambda: gh_post(f"repos/{repo}/pulls/{n}/reviews", review, body_path,
                             f"gh api pulls/{n}/reviews (pass {k})"))]
    for key, r, body in bodies:
        todo.append((key, "reply", body,
                     lambda r=r, body=body, key=key: gh_post(
                         f"repos/{repo}/pulls/{n}/comments/{threads[r['id']]}/replies",
                         {"body": body}, body_path, f"gh api reply ({key})")))
    try:
        post_items(pad, todo, found)
    finally:
        body_path.unlink(missing_ok=True)
    report_kept(kept, held)
    return 0


def pr_sweep(config, n):
    """The sweep label the pull request carries, or None; two are refused."""
    out = run(["gh", "api", f"repos/{config['repo']}/issues/{n}"], f"gh api issues/{n}")
    try:
        labels = [x["name"] for x in json.loads(out)["labels"]]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise Failed(f"gh api issues/{n}: unexpected answer:\n{out}")
    sweeps = [x for x in labels if x.startswith(SWEEP_PREFIX)]
    if len(sweeps) > 1:
        raise Refused(f"#{n} carries {len(sweeps)} sweep labels ({', '.join(sweeps)}): a pull "
                      "request for a sweep's issues carries that one sweep's label")
    return sweeps[0] if sweeps else None


def cmd_pr_file(config, pad, n, chosen, every):
    passes, ids = load_passes(pad, n)
    private, questions = flagged(pad, ids), asked(ids)
    latest = passes[max(passes)]
    if every:
        chosen = [f["id"] for f in latest["additional"] if f["id"] not in private | questions]
        report_kept([f["id"] for f in latest["additional"] if f["id"] in private],
                    [f["id"] for f in latest["additional"]
                     if f["id"] in questions and f["id"] not in private])
    items, areas = [], None
    for fid in dict.fromkeys(chosen):
        if fid not in ids:
            raise Refused(f"{fid}: no such finding on #{n}")
        k, part, f = ids[fid]
        found_by = f"**Found by:** the review of #{n}, pass {k}, " + \
            ("one of its additional findings" if part == "additional" else "on its diff") + \
            f"; work-pad id {fid}"
        if fid in questions:
            raise Refused(f"{fid}: a question for the owner, never filed; once the owner decides, "
                          "it is a finding of the next pass")
        if fid in private:
            key = f"{fid} advisory"
            body = finding_body(config, f, review=found_by, end=pr_marker(n, key))
            items.append((key, "advisory", {"id": fid, "title": f["title"], "body": body,
                                            "severity": SEVERITY_FOR_ADVISORY[f["severity"]]}))
            continue
        if part != "additional":
            raise Refused(f"{fid}: a finding on the diff, posted on its line, not filed")
        if areas is None:
            areas = list_areas(config)
        check_area(f, areas, f"pass-{k}.json")
        key = f"{fid} issue"
        body = finding_body(config, f, review=found_by, end=pr_marker(n, key))
        items.append((key, "issue", {"id": fid, "title": f["title"], "body": body, "finding": f}))
    if not items:
        print("nothing to file")
        return 0
    # The sweep only through the pull request: its sweep label, the parent search, the title rule.
    label = pr_sweep(config, n) if any(kind == "issue" for _, kind, _ in items) else None
    sweep = Sweep(config, label) if label else None
    entries, failures = [], []
    for key, kind, i in items:
        if kind != "issue":
            continue
        i["labels"] = issue_labels(config, i.pop("finding"), label)
        parent = None
        if sweep:
            parent, why = sweep.parent(ids[i["id"]][2]["area"])
            if why:
                failures.append(f"{i['id']}: {why}")
        i["parent"] = parent["number"] if parent else None
        entries.append((key, parent, i["title"]))
    if failures:
        raise Refused("no parent for " + "; ".join(failures) + ": nothing filed")
    if sweep:
        keys = {key for key, _, _ in items}
        titles = sweep.titles(entries, own_markers(pr_keys(n), keys))
        for key, kind, i in items:
            i["title"] = titles.get(key, i["title"])
    text_gate(config, pad, [(key, i["title"], i["body"]) for key, _, i in items])
    posted = read_state(pad, PR_STATE_FILE)["posted"]
    found = {} if all(key in posted for key, _, _ in items) else \
        already_posted(config, keys=pr_keys(n))
    body_path = pad / ".pr-body"

    def create(kind, item):
        if kind == "advisory":
            return create_advisory(config, item, body_path)
        body_path.write_text(item["body"], encoding="utf-8")
        return create_issue(config["repo"], item["title"], body_path, item["labels"])

    def then(item):
        if not item.get("parent"):
            return None
        return lambda record: attach(config, sweep, item["parent"], record, body_path)

    try:
        post_items(pad, [(key, kind, f"{i['title']}\n{i['body']}",
                          lambda kind=kind, i=i: create(kind, i), then(i))
                         for key, kind, i in items], found)
    finally:
        body_path.unlink(missing_ok=True)
    return 0


# ---- the author's side: respond ----

ROUND_FILE = re.compile(r"^round-([1-9][0-9]*)\.json$")
RESPOND_STATE_FILE = "respond-state.json"
RESPOND_MARKER = re.compile(r"<!-- pr-respond (\d+) ([^<>]+?) -->")

_LINE = {"type": "string", "minLength": 1, "pattern": r"^[^\n]+$"}

ROUND_SCHEMA = {
    "type": "object",
    "required": ["pr", "round", "head", "replies", "answers", "changed", "waiting", "unanswered"],
    "additionalProperties": False,
    "properties": {
        "pr": {"type": "integer", "minimum": 1},
        "round": {"type": "integer", "minimum": 1},
        "head": {"type": "string", "pattern": r"^[0-9a-f]{40}$"},
        "replies": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["thread", "outcome"],
                "additionalProperties": False,
                "properties": {
                    "thread": {"type": "integer", "minimum": 1},
                    "outcome": {"type": "string", "enum": ["fixed", "answer", "done", "waiting"]},
                    "sha": _SHA, "how": _LINE, "test": _TEXT, "text": _TEXT,
                    "decision": _TEXT, "owner_asked": {"type": "boolean"},
                },
            },
        },
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["to", "id", "text"],
                "additionalProperties": False,
                "properties": {"to": {"type": "string", "enum": ["review", "comment"]},
                               "id": {"type": "integer", "minimum": 1}, "text": _TEXT,
                               "owner_asked": {"type": "boolean"}},
            },
        },
        "changed": {
            "type": "array",
            "items": {"type": "object", "required": ["sha", "what"], "additionalProperties": False,
                      "properties": {"sha": _SHA, "what": _LINE}},
        },
        "waiting": _TEXTS,
        "unanswered": _TEXTS,
    },
}

OUTCOME_NEEDS = {"fixed": ("sha", "how", "test"), "done": ("sha", "text"), "answer": ("text",),
                 "waiting": ()}


def respond_marker(n, key):
    return f"<!-- pr-respond {n} {key} -->"


def load_rounds(pad, n):
    rounds = {}
    for path in sorted(pad.iterdir()):
        m = ROUND_FILE.match(path.name)
        if not m:
            continue
        record = load_json(path, "round")
        check_schema(record, ROUND_SCHEMA, path.name)
        if record["round"] != int(m.group(1)):
            raise Refused(f"{path.name}.round: {record['round']} is not the file's number")
        if record["pr"] != n:
            raise Refused(f"{path.name}.pr: {record['pr']}, not {n}")
        rounds[record["round"]] = record
    if not rounds:
        raise Refused(f"work pad {pad}: no round-<k>.json")
    if sorted(rounds) != list(range(1, len(rounds) + 1)):
        raise Refused(f"work pad {pad}: rounds {sorted(rounds)} are not 1, 2, ... without a gap")
    r = rounds[max(rounds)]
    where = f"round-{r['round']}.json"
    threads = [x["thread"] for x in r["replies"]]
    if len(set(threads)) != len(threads):
        raise Refused(f"{where}: a thread has two replies in one round")
    for x in r["replies"]:
        for name in OUTCOME_NEEDS[x["outcome"]]:
            if name not in x:
                raise Refused(f"{where} thread {x['thread']}.{name}: a {x['outcome']} reply needs it")
    targets = [(a["to"], a["id"]) for a in r["answers"]]
    if len(set(targets)) != len(targets):
        raise Refused(f"{where}: a comment has two answers in one round")
    return r


def pr_conversation(config, n):
    """The pull request's review comments, conversation comments and reviews. Those by anyone but an
    owner, member or collaborator keep only their id, thread and link: their text is never read."""
    repo, seen, skipped = config["repo"], {}, 0
    for what, path in (("comments", f"repos/{repo}/pulls/{n}/comments?per_page=100"),
                       ("conversation", f"repos/{repo}/issues/{n}/comments?per_page=100"),
                       ("reviews", f"repos/{repo}/pulls/{n}/reviews?per_page=100")):
        out = run(["gh", "api", "--paginate", path], f"gh api {what} of #{n} (list)")
        items = {}
        for page in json_values(out):
            for item in page:
                trusted = item.get("author_association") in TRUSTED
                skipped += not trusted
                items[item["id"]] = {"id": item["id"], "trusted": trusted,
                                     "in_reply_to_id": item.get("in_reply_to_id"),
                                     "url": item.get("html_url"),
                                     "body": (item.get("body") or "") if trusted else ""}
        seen[what] = items
    return seen, skipped


def on_branch(repo, sha, head):
    """Whether sha is head or one of its ancestors on GitHub."""
    argv = ["gh", "api", f"repos/{repo}/compare/{sha}...{head}", "--jq", ".status"]
    try:
        done = subprocess.run(argv, capture_output=True, text=True)
    except OSError as e:
        raise Failed(f"gh api compare: cannot run gh: {e.strerror}")
    if done.returncode != 0:
        if "404" in done.stdout + done.stderr or "Not Found" in done.stdout + done.stderr:
            return False
        raise Failed(f"gh api compare ({sha}) failed (exit {done.returncode}):\n"
                     f"{done.stdout}{done.stderr}".rstrip())
    return done.stdout.strip() in ("ahead", "identical")


def respond_reply_body(n, k, x):
    lines = [f"The owner decided: {x['decision']}", ""] if "decision" in x else []
    o = x["outcome"]
    if o == "fixed":
        lines += [f"Fixed in {x['sha']}: {x['how']}", "", f"Proved by {x['test']}."]
    elif o == "done":
        lines += [f"Already done in {x['sha']}: {x['text']}"]
    elif o == "waiting":
        lines += ["Waiting on the owner's decision."] + (["", x["text"]] if "text" in x else [])
    else:
        lines += [x["text"]]
    lines += ["", respond_marker(n, f"thread {x['thread']} round {k}")]
    return "\n".join(lines) + "\n"


def round_comment_body(n, r, answered):
    k = r["round"]
    lines = [f"**pr-respond, round {k}**: the head {r['head']}", "", "## What changed", ""]
    lines += [f"- {c['sha']}: {c['what']}" for c in r["changed"]] or ["- nothing"]
    if answered:
        lines += ["", "## Answers", ""] + [f"- To {url}: {text}" for url, text in answered]
    lines += ["", "## Waiting on the owner", ""] + ([f"- {t}" for t in r["waiting"]] or ["- nothing"])
    lines += ["", "## Not answered", ""] + ([f"- {t}" for t in r["unanswered"]] or ["- none"])
    lines += ["", respond_marker(n, f"round {k}")]
    return "\n".join(lines) + "\n"


def cmd_respond(config, pad, n):
    r = load_rounds(pad, n)
    k, repo = r["round"], config["repo"]
    out = run(["gh", "api", f"repos/{repo}/pulls/{n}", "--jq", ".head.sha"], f"gh api pulls/{n}")
    head = out.strip()
    shas = {r["head"]} | {x["sha"] for x in r["replies"] if "sha" in x} | \
        {c["sha"] for c in r["changed"]}
    for sha in sorted(shas):
        if not on_branch(repo, sha, head):
            raise Refused(f"{sha} is not on #{n}'s branch on GitHub (its head is {head}): "
                          "push it first; a reply never names a commit that isn't pushed")
    seen, skipped = pr_conversation(config, n)
    if skipped:
        print(f"left unread: {skipped} comments and reviews by others on #{n}")

    def target(items, item_id, owner_asked, what):
        item = items.get(item_id)
        if item is None:
            raise Refused(f"{what}: not on #{n}")
        if not item["trusted"] and not owner_asked:
            raise Refused(f"{what}: by someone outside the project; answered only when the owner "
                          "says so (owner_asked)")
        return item

    for x in r["replies"]:
        t = target(seen["comments"], x["thread"], x.get("owner_asked"), f"thread {x['thread']}")
        if t["in_reply_to_id"]:
            raise Refused(f"thread {x['thread']}: a reply, not the start of a thread")
    answered = [(target(seen["reviews" if a["to"] == "review" else "conversation"], a["id"],
                        a.get("owner_asked"), f"{a['to']} {a['id']}")["url"], a["text"])
                for a in r["answers"]]
    replies = [(f"thread {x['thread']} round {k}", x, respond_reply_body(n, k, x))
               for x in r["replies"]]
    comment = round_comment_body(n, r, answered)
    text_gate(config, pad, [(key, "", body) for key, _, body in replies] +
              [(f"round {k}", "", comment)])
    found = {}
    for items in seen.values():
        for item in items.values():
            for m in RESPOND_MARKER.finditer(item["body"]):
                if m.group(1) == str(n):
                    found.setdefault(m.group(2), {"id": item["id"], "url": item["url"]})
    body_path = pad / ".respond-body"
    todo = [(key, "reply", body,
             lambda x=x, body=body, key=key: gh_post(
                 f"repos/{repo}/pulls/{n}/comments/{x['thread']}/replies", {"body": body},
                 body_path, f"gh api reply ({key})"))
            for key, x, body in replies]
    todo.append((f"round {k}", "comment", comment,
                 lambda: gh_post(f"repos/{repo}/issues/{n}/comments", {"body": comment}, body_path,
                                 f"gh api issues/{n}/comments (round {k})")))
    try:
        post_items(pad, todo, found, RESPOND_STATE_FILE)
    finally:
        body_path.unlink(missing_ok=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["dry-run", "post", "question", "pr", "respond"])
    parser.add_argument("args", nargs="*", help="question: the question's JSON file; "
                        "pr: post <n>, or file <n> and the ids to file; respond: <n>")
    parser.add_argument("--all", action="store_true",
                        help="pr file: every additional finding of the latest pass")
    parser.add_argument("--config", default="docs/review.json",
                        help="the project's review config (default docs/review.json)")
    parser.add_argument("--pad", help="the work pad (default review/<nnnn> from the config, "
                        "or review/pr-<n>)")
    args = parser.parse_args(argv)
    try:
        if args.all and (args.command != "pr" or args.args[:1] != ["file"]):
            raise Refused("--all is for pr file only")
        config = load_config(args.config)
        if args.command == "respond":
            if len(args.args) != 1 or not re.fullmatch(r"[1-9][0-9]*", args.args[0]):
                raise Refused("respond: <n>, the pull request's number")
            n = int(args.args[0])
            pad = Path(args.pad or f"review/pr-{n}")
            if not pad.is_dir():
                raise Refused(f"work pad {pad}: not a folder")
            return cmd_respond(config, pad, n)
        if args.command == "pr":
            if len(args.args) < 2 or args.args[0] not in ("post", "file") or \
                    not re.fullmatch(r"[1-9][0-9]*", args.args[1]):
                raise Refused("pr: post <n>, or file <n> (<id> ... | --all)")
            action, n, rest = args.args[0], int(args.args[1]), args.args[2:]
            pad = Path(args.pad or f"review/pr-{n}")
            if not pad.is_dir():
                raise Refused(f"work pad {pad}: not a folder")
            if action == "post":
                if rest:
                    raise Refused("pr post takes no ids")
                return cmd_pr_post(config, pad, n)
            if bool(rest) == args.all:
                raise Refused("pr file: name the ids to file, or --all, not both")
            return cmd_pr_file(config, pad, n, rest, args.all)
        pad = Path(args.pad or f"review/{config['name']['number']:04d}")
        if not pad.is_dir():
            raise Refused(f"work pad {pad}: not a folder")
        if args.command == "question":
            if len(args.args) != 1:
                raise Refused("question: name the question's JSON file")
            return cmd_question(config, pad, args.args[0])
        if args.args:
            raise Refused(f"{args.command} takes no file")
        if args.command == "dry-run":
            return cmd_dry_run(config, pad)
        return cmd_post(config, pad)
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    except Failed as e:
        print(f"stopped: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
