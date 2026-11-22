#!/usr/bin/env python3
"""File a code review's findings: one issue per finding, a draft security advisory for each finding
marked exploitable, and a summary issue listing them by link. See filing.md beside this script.

    file_review.py dry-run [--config docs/review.json] [--pad review/<nnnn>]
    file_review.py post    [--config docs/review.json] [--pad review/<nnnn>]

`dry-run` writes the whole plan to <pad>/filing-dry-run.md and posts nothing. `post` posts exactly
that plan through the gh CLI, keeping <pad>/filing-state.json so a run that stopped can be run again.
It never closes or edits an issue. Python 3 standard library only.

Exit status: 0 done; 1 a text check or gh call failed (what was posted is kept); 2 refused (a bad
config or input, or a plan that doesn't match the dry run).
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
        if record["id"] in seen:
            raise Refused(f"{FINDINGS_FILE} line {n}.id: {record['id']} is used twice")
        seen.add(record["id"])
        findings.append(record)
    return findings


def load_summary(pad):
    summary = load_json(pad / SUMMARY_FILE, "summary")
    check_schema(summary, SUMMARY_SCHEMA, SUMMARY_FILE)
    return summary


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


def finding_body(config, f):
    lines = [f"severity {f['severity']}", ""]
    lines.append(f"**Kind:** {f['kind']}")
    lines.append(f"**Requirements:** {', '.join(f['requirements']) or 'none (untraced)'}")
    lines.append(f"**Confirmations:** {f['confirmations']}")
    lines.append(f"**Review:** {review_name(config)}, work-pad id {f['id']}")
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
    return "\n".join(lines) + "\n"


def link_placeholder(finding_id):
    return f"#<{finding_id}>"


def summary_body(config, summary, items, links):
    """links maps a finding's id to its issue link; ids not in it get a placeholder."""
    n = config["name"]["number"]
    branch = f"code-review-{n:04d}"
    lines = [
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
        lines.append(f"- {link} severity {f['severity']}, {f['kind']}, area {area}: {f['title']}")
    if not issues:
        lines.append("- none filed as issues")
    if advisories:
        filed = ("finding is filed as a draft security advisory" if len(advisories) == 1
                 else "findings are filed as draft security advisories")
        lines += ["", f"{len(advisories)} more {filed}, private to the maintainers."]
    for heading, key in (("Checked and sound", "checked_and_sound"),
                         ("Where things stand", "where_things_stand")):
        lines += ["", f"## {heading}", ""] + [f"- {t}" for t in summary[key]]
    return "\n".join(lines) + "\n"


def build_plan(config, pad):
    findings = load_findings(pad)
    summary = load_summary(pad)
    areas = list_areas(config)
    items = []
    for f in findings:
        if f["area"] is not None and f["area"] not in areas:
            raise Refused(f"{FINDINGS_FILE} {f['id']}.area: {f['area']!r} is not one of the "
                          f"project's areas ({', '.join(sorted(areas)) or 'none listed'})")
        body = finding_body(config, f)
        if f.get("advisory"):
            items.append({"id": f["id"], "type": "advisory", "title": f["title"], "body": body,
                          "labels": [], "severity": SEVERITY_FOR_ADVISORY[f["severity"]],
                          "finding": f})
            continue
        labels = list(config["labels"])
        if f["area"] is not None:
            labels.append(config["area_prefix"] + f["area"])
        if "kind_prefix" in config:
            labels.append(config["kind_prefix"] + f["kind"])
        if f.get("question"):
            labels.append(config["question_label"])
        items.append({"id": f["id"], "type": "issue", "title": f["title"], "body": body,
                      "labels": list(dict.fromkeys(labels)), "finding": f})
    return {
        "repo": config["repo"],
        "items": items,
        "summary": {"title": f"{review_name(config)}: summary",
                    "body": summary_body(config, summary, items, {}),
                    "data": summary},
    }


def plan_hash(plan):
    keep = {"repo": plan["repo"],
            "items": [{k: v for k, v in i.items() if k != "finding"} for i in plan["items"]],
            "summary": {"title": plan["summary"]["title"], "body": plan["summary"]["body"]}}
    return hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest()


def item_hash(title, body):
    return hashlib.sha256(f"{title}\n{body}".encode()).hexdigest()


# ---- dry-run ----

def write_dry_run(config, pad, plan, failures):
    out = [f"# {review_name(config)} filing: dry run", "",
           f"plan sha256: {plan_hash(plan)}", "",
           f"Repository: {plan['repo']}. Nothing was posted. `post` posts exactly this plan: to "
           f"change it, change `{FINDINGS_FILE}` or `{SUMMARY_FILE}` and run the dry run again.", ""]
    n_adv = sum(1 for i in plan["items"] if i["type"] == "advisory")
    n_issues = len(plan["items"]) - n_adv
    out.append(f"Findings: {n_issues} as public issues, {n_adv} as draft security advisories; "
               "then the summary issue.")
    out.append("")
    if "text_check" not in config:
        out.append("Text check: none configured.")
    elif failures:
        out.append("Text check: FAILED for " + ", ".join(failures) + ".")
    else:
        out.append("Text check: passed for every title and body.")
    out.append("")
    entries = plan["items"] + [{"id": "summary", "type": "summary", **plan["summary"],
                                "labels": []}]
    for k, item in enumerate(entries, 1):
        if item["type"] == "advisory":
            where = (f"draft security advisory, private (exploitable if public), "
                     f"severity {item['severity']}")
        elif item["type"] == "issue":
            where = "public issue"
        else:
            where = "public issue: the summary, posted last, with each finding's link"
        mark = fence(item["body"])
        out += [f"## {k}. {item['id']}: {where}", "",
                f"- title: {item['title']}",
                f"- labels: {', '.join(item['labels']) or 'none'}",
                "- parent: none", "",
                mark + "markdown", item["body"].rstrip("\n"), mark, ""]
    (pad / DRY_RUN_FILE).write_text("\n".join(out), encoding="utf-8")


def cmd_dry_run(config, pad):
    plan = build_plan(config, pad)
    failures = []
    for item in plan["items"] + [{"id": "summary", **plan["summary"]}]:
        result = text_check(config, pad, item["title"], item["body"])
        if result is not None:
            failures.append(item["id"])
            print(f"text check failed for {item['id']}:\n{result}", file=sys.stderr)
    write_dry_run(config, pad, plan, failures)
    print(f"wrote {pad / DRY_RUN_FILE}: {len(plan['items'])} findings and the summary; "
          "nothing posted")
    return 1 if failures else 0


# ---- post ----

def read_state(pad):
    path = pad / STATE_FILE
    if not path.exists():
        return {"posted": {}}
    return load_json(path, "state")


def write_state(pad, state):
    path = pad / STATE_FILE
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


def cmd_post(config, pad):
    plan = build_plan(config, pad)
    dry = pad / DRY_RUN_FILE
    if not dry.exists():
        raise Refused(f"no dry run: run dry-run first and read {dry}")
    m = re.search(r"^plan sha256: ([0-9a-f]{64})$", dry.read_text(encoding="utf-8"), re.M)
    if not m or m.group(1) != plan_hash(plan):
        raise Refused(f"the plan differs from {dry}: run dry-run again and read it before posting")
    state = read_state(pad)
    posted = state.setdefault("posted", {})
    body_path = pad / ".filing-body"
    try:
        for item in plan["items"]:
            done = posted.get(item["id"])
            if done:
                if done["hash"] != item_hash(item["title"], item["body"]):
                    print(f"{item['id']}: posted earlier as {done['url']}, and its text has "
                          "changed since; left as it is", file=sys.stderr)
                continue
            result = text_check(config, pad, item["title"], item["body"])
            if result is not None:
                raise Failed(f"text check failed for {item['id']}; nothing more posted:\n{result}")
            if item["type"] == "advisory":
                record = create_advisory(config, item, body_path)
            else:
                body_path.write_text(item["body"], encoding="utf-8")
                record = create_issue(plan["repo"], item["title"], body_path, item["labels"])
            record.update(type=item["type"], hash=item_hash(item["title"], item["body"]))
            posted[item["id"]] = record
            write_state(pad, state)
            print(f"{item['id']}: {record['url']}")
        if "summary" in posted:
            print(f"summary: posted earlier as {posted['summary']['url']}")
            return 0
        links = {i: f"#{r['number']}" for i, r in posted.items() if r.get("type") == "issue"}
        title = plan["summary"]["title"]
        body = summary_body(config, plan["summary"]["data"], plan["items"], links)
        result = text_check(config, pad, title, body)
        if result is not None:
            raise Failed(f"text check failed for the summary; it is not posted:\n{result}")
        body_path.write_text(body, encoding="utf-8")
        record = create_issue(plan["repo"], title, body_path, [])
        record.update(type="summary", hash=item_hash(title, body))
        posted["summary"] = record
        write_state(pad, state)
        print(f"summary: {record['url']}")
        return 0
    finally:
        body_path.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["dry-run", "post"])
    parser.add_argument("--config", default="docs/review.json",
                        help="the project's review config (default docs/review.json)")
    parser.add_argument("--pad", help="the work pad (default review/<nnnn> from the config)")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        pad = Path(args.pad or f"review/{config['name']['number']:04d}")
        if not pad.is_dir():
            raise Refused(f"work pad {pad}: not a folder")
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
