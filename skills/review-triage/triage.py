#!/usr/bin/env python3
"""A sweep's work schedule: gather a posted review's open findings, check the schedule made from
them, and say which of its work units can start. See SKILL.md beside this script.

    triage.py gather      [--sweep CR1] [--config docs/review.json] [--pad review/<N>]
    triage.py sorted [<file> ...] [--step <step>,...] [--sweep CR1] [--config ...] [--pad review/<N>]
    triage.py check       [--sweep CR1] [--config ...] [--schedule <file>] [--offline]
    triage.py next        [--sweep CR1] [--config ...] [--schedule <file>] [--started U08,U09]
    triage.py guard <unit> --base <ref> [--on <unit>] [--sweep CR1] [--config ...] [--schedule <file>]
    triage.py unscheduled [--sweep CR1] [--config ...] [--schedule <file>]

The sweep is <prefix><N> (CR1): named by --sweep, else by the branch code-review-<N>, else by the
one schedule file the project holds. The schedule is the project's `schedule` path (docs/review.json;
docs/remediation/<sweep>-schedule.json by default), checked against schedule.schema.json.

`gather` writes the sweep's open findings, read from their issues, to <pad>/triage/findings.json:
what the sort reads, each with its body and the comments of the project's owners, members and
collaborators, where a decision is recorded. It writes them once more a step, as
findings-<area>.json, so a sort piece reads its own step and no more.

`sorted` checks the sort's files in <pad>/triage: every line of every sort-*.jsonl and check*.jsonl
against sort.schema.json (a choice with its ask, a not now with its why), every gathered finding
sorted once, every High and Med one judged once by the checker, and every finding a record names a
gathered one. It lists where the checker differs from the sorter, which makes the finding a choice,
and writes <pad>/triage/sorted.json: each finding's record with that settled. A record of
decided.jsonl, written once the owner has decided a finding, stands in the sorter's place. Given
files, it checks only their lines, so a piece checks its own file before it ends. Given --step, it
holds only those steps' findings to the check, each step named by its area or its issue's number,
and writes nothing: a step is checked as its pieces end.

`check` checks a schedule: against the schema, against itself (a finding in one unit only, each
with its record, a unit's files holding its findings' files, a dependency on an earlier unit, no
unit over the project's unit_size without its reason, a shared file changed by the project's
shared_at units or more) and, unless --offline, against GitHub (every open finding in a unit or set
aside). It notes a file that many units change and the schedule doesn't list as shared, and a
dependency on a finding no unit holds.

`next` says, for each unit in order, whether it is merged, open (and what it is stacked on), can
start, can start stacked on an open unit, or what it waits on. A unit is held back by an earlier
unit it depends on, one that holds a finding one of its own depends on, and one it shares a file
with; two units that share only the schedule's shared files don't hold one another back, unless a
finding of one is related to, or depends on, a finding of the other in such a file. A unit waits
while a unit that holds it back is neither merged nor open. It starts stacked when it overlaps an
open unit (one that holds it back, or one it shares a file with, a shared file included): on the
branch that holds every open unit it overlaps, at any depth. It waits when no branch holds them
all: two open units, neither stacked on the other. A unit's state is its pull request's, found by the marker
`<!-- remediation CR1 U07 -->` in its description; what an open unit is stacked on is that
description's line "Stacked on #N"; and --started names units begun with no pull request yet.

`guard` compares the files a unit's branch changed since <ref> with the unit's plan, and stops
(exit 1) on a file outside it that another unmerged unit claims, unless it is a shared file or the
unit is stacked on every unit that claims it (--on <unit>, or its pull request's "Stacked on #N").
`unscheduled` lists the open findings the schedule doesn't hold.

It reads GitHub through the gh CLI and writes nothing there. Python 3 standard library, and the
review skill's file_review.py for the config, the schema checker and the sweep's names.

Exit status: 0 done; 1 the sort or the schedule has problems, a guard stopped, or a gh or git call
failed; 2 refused (a bad config, schedule or argument).
"""

import sys

sys.dont_write_bytecode = True  # importing the review skill's script leaves no __pycache__ beside it

import argparse  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "review"))

import file_review as fr  # noqa: E402

SCHEMA = HERE / "schedule.schema.json"
SORT_SCHEMA = HERE / "sort.schema.json"
FINDINGS_FILE = "findings.json"
SORTED_FILE = "sorted.json"
DECIDED_FILE = "decided.jsonl"
UNIT_MARKER = re.compile(r"<!-- remediation (\S+) (\S+) -->")
# A stacked unit's description says so on a line of its own: "Stacked on #40: its own change ...".
STACKED_ON = re.compile(r"(?im)^[\s>*_-]*stacked on #([0-9]+)")
SEVERITY = re.compile(r"^(?:\[[^\]\n]*\] )?severity (High|Med|Low)\b")
SEVERITIES = ("High", "Med", "Low")

ISSUES_QUERY = """query($owner: String!, $name: String!, $label: String!, $endCursor: String) {
  repository(owner: $owner, name: $name) {
    issues(first: 100, after: $endCursor, labels: [$label]) {
      nodes { number title body state parent { number } labels(first: 100) { nodes { name } }
              comments(first: 100) { nodes { body authorAssociation } } }
      pageInfo { hasNextPage endCursor }
    }
  }
}"""


# ---- the sweep and its schedule ----

def sweep_number(config, given):
    """The sweep's number: --sweep's, the branch's, else that of the one schedule file there is."""
    try:
        return fr.find_sweep(config, given)
    except fr.Refused:
        if given:
            raise
    prefix = fr.prefix_of(config)
    before, after = config["schedule"].split("{sweep}", 1)
    pattern = re.compile(re.escape(before) + rf"{re.escape(prefix)}([1-9][0-9]*)" + re.escape(after))
    found = sorted({int(m.group(1)) for p in Path().glob(before + "*" + after)
                    for m in [pattern.fullmatch(p.as_posix())] if m})
    if len(found) != 1:
        raise fr.Refused(f"which sweep? Name it (--sweep {prefix}<N>), run on its branch "
                         f"code-review-<N>, or keep one schedule file ({len(found)} found)")
    return found[0]


def schedule_path(config, given):
    return Path(given or config["schedule"].replace("{sweep}", fr.review_name(config)))


def load_schedule(config, path):
    schedule = fr.load_json(path, "schedule")
    fr.check_schema(schedule, fr.load_json(SCHEMA, "schema"), "schedule")
    if schedule["sweep"] != fr.review_name(config):
        raise fr.Refused(f"schedule {path}: it is {schedule['sweep']}'s, not "
                         f"{fr.review_name(config)}'s")
    return schedule


# ---- what GitHub holds ----

def sweep_issues(config):
    """Every issue with the sweep label, in any state."""
    owner, name = config["repo"].split("/")
    label = fr.sweep_label(config)
    out = fr.run(["gh", "api", "graphql", "--paginate", "-f", f"query={ISSUES_QUERY}",
                  "-f", f"owner={owner}", "-f", f"name={name}", "-f", f"label={label}"],
                 f"gh api graphql (the issues labelled {label})")
    return [{"number": n["number"], "title": n["title"], "body": n.get("body") or "",
             "state": n["state"].lower(), "parent": (n.get("parent") or {}).get("number"),
             "labels": [x["name"] for x in n["labels"]["nodes"]],
             # A decision is a comment: only those of the project's own people are read.
             "comments": [c["body"] for c in (n.get("comments") or {}).get("nodes", [])
                          if c.get("authorAssociation") in fr.TRUSTED]}
            for page in fr.json_values(out) for n in page["data"]["repository"]["issues"]["nodes"]]


def findings_of(config, issues):
    """The sweep's findings among its issues: every one that is not the anchor, a step or a part
    of one, or a question issue. Each gets its severity (its body's first line), its area (its area
    label), its step (the step it sits below, at any depth) and its id in the review's work pad
    (its marker's), by which other findings name it."""
    name = fr.review_name(config)
    roots = [i for i in issues if i["parent"] is None
             and any(m.group(1) == name and m.group(2) == "anchor"
                     for m in fr.PLAN_MARKER.finditer(i["body"]))]
    if len(roots) != 1:
        raise fr.Refused(f"the sweep {fr.sweep_label(config)} has {len(roots)} issues with its "
                         "anchor's marker and no parent; it needs one, which the review's Planning "
                         "makes")
    anchor = roots[0]["number"]
    by_number = {i["number"]: i for i in issues}
    steps = {i["number"] for i in issues if i["parent"] == anchor and fr.is_step(i["body"])}
    prefix = config["area_prefix"]
    out = []
    for i in issues:
        if i["number"] == anchor or i["number"] in steps or config["question_label"] in i["labels"]:
            continue
        at, seen = i, set()
        while at and at["parent"] not in steps and at["parent"] is not None \
                and at["number"] not in seen:
            seen.add(at["number"])
            at = by_number.get(at["parent"])
        m = SEVERITY.match(i["body"])
        areas = [x[len(prefix):] for x in i["labels"] if x.startswith(prefix)]
        ids = [k.group(2) for k in fr.MARKER.finditer(i["body"])
               if k.group(1) == name and k.group(2) not in fr.PLAN_KEYS]
        out.append(dict(i, severity=m.group(1) if m else None, area=areas[0] if areas else None,
                        step=at["parent"] if at and at["parent"] in steps else None,
                        id=ids[0] if ids else None))
    return sorted(out, key=lambda f: f["number"])


def to_schedule(config, findings):
    """The open findings a schedule must hold: those not proposed for dismissal."""
    return {f["number"] for f in findings
            if f["state"] == "open" and config["dismiss_label"] not in f["labels"]}


def unit_states(config, name):
    """{unit id: {"state": "open" or "merged", "pr": n, "on": m, "on_merged": bool}}, from the pull
    requests whose description carries the unit's marker. One closed without a merge counts for
    nothing. "on" is the pull request the description says the unit is stacked on ("Stacked on
    #m"), or None, and "on_merged" whether that one has merged."""
    out = fr.run(["gh", "pr", "list", "--repo", config["repo"], "--state", "all", "--limit", "1000",
                  "--json", "number,state,body"], "gh pr list")
    prs = json.loads(out)
    merged = {pr["number"] for pr in prs if pr["state"].lower() == "merged"}
    states = {}
    for pr in prs:
        state = pr["state"].lower()
        if state == "closed":
            continue
        body = pr.get("body") or ""
        on = STACKED_ON.search(body)
        on = int(on.group(1)) if on else None
        for m in UNIT_MARKER.finditer(body):
            if m.group(1) == name and (m.group(2) not in states or state == "merged"):
                states[m.group(2)] = {"state": state, "pr": pr["number"], "on": on,
                                      "on_merged": on in merged}
    return states


def stack_below(uid, states):
    """The open units whose work a unit's branch holds below its own, nearest first: the unit its
    pull request says it is stacked on, the unit that one is stacked on, and so on down. A unit
    with no pull request yet names none, and a merged one ends the stack: the target holds it."""
    by_pr = {s["pr"]: i for i, s in states.items() if s.get("pr")}
    below, at = [], uid
    while True:
        at = by_pr.get(states.get(at, {}).get("on"))
        if at is None or at == uid or at in below or states[at]["state"] != "open":
            return below
        below.append(at)


# ---- gather ----

def step_file(f):
    """The file of a finding's step: findings-<area>.json, the step named by its area."""
    return "findings-" + re.sub(r"[^A-Za-z0-9._-]", "-", f["area"] or "no-area") + ".json"


def step_names(f):
    """The names a finding's step goes by: its area, and the number of the step's issue."""
    return {x for x in (f["area"], f["step"] and str(f["step"])) if x}


def cmd_gather(config, pad):
    findings = [f for f in findings_of(config, sweep_issues(config)) if f["state"] == "open"]
    folder = pad / "triage"
    folder.mkdir(exist_ok=True)
    keep = ("number", "id", "title", "severity", "area", "step", "labels", "body", "comments")
    kept = [{k: f[k] for k in keep} for f in findings]
    (folder / FINDINGS_FILE).write_text(json.dumps(kept, indent=1) + "\n", encoding="utf-8")
    # One file a step as well, named by its area, so a sort piece reads its own step and no more.
    for old in folder.glob("findings-*.json"):
        old.unlink()
    steps = {}
    for f in kept:
        steps.setdefault(step_file(f), []).append(f)
    for name, of_step in steps.items():
        (folder / name).write_text(json.dumps(of_step, indent=1) + "\n", encoding="utf-8")
    counts = ", ".join(f"{sum(1 for f in findings if f['severity'] == s)} {s}" for s in SEVERITIES)
    unrated = sum(1 for f in findings if f["severity"] is None)
    print(f"wrote {folder / FINDINGS_FILE}: {len(findings)} open findings ({counts}"
          + (f", {unrated} with no severity" if unrated else "") + f"), and {len(steps)} "
          f"file{'' if len(steps) == 1 else 's'} of one step each (findings-<area>.json)")
    return 0


# ---- sorted ----

def read_lines(path, kind, schemas):
    """([(where, record)], problems) of a sort piece's file (kind "sort"), the checker's ("check")
    or the decided records' ("decided"): each line JSON, of its schema, and a record with what
    its readiness calls for."""
    records, problems = [], []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise fr.Refused(f"{path}: {e.strerror}")
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        where = f"{path.name}:{n}"
        try:
            r = json.loads(line)
        except json.JSONDecodeError as e:
            problems.append(f"{where}: not JSON ({e.msg})")
            continue
        try:
            fr.check_schema(r, schemas["check" if kind == "check" else "sort"], where)
        except fr.Refused as e:
            problems.append(str(e))
            continue
        if kind != "check":
            what = f"{where}: #{r['finding']}"
            if kind == "decided" and r["readiness"] == "choice":
                problems.append(f"{what} is still a choice: a decided record is what the owner's "
                                "decision made of it")
            elif r["readiness"] == "choice" and "ask" not in r:
                problems.append(f"{what} is a choice with no ask: the question, the options and "
                                "the recommendation")
            if r["readiness"] != "choice" and "ask" in r:
                problems.append(f"{what} has an ask and is sorted as \"{r['readiness']}\", not "
                                "as a choice")
            if r["readiness"] == "not now" and "why" not in r:
                problems.append(f"{what} is a not now with no why")
            if r["finding"] in r.get("depends_on", []) + r.get("related", []):
                problems.append(f"{what} names itself")
        records.append((where, r))
    return records, problems


def kind_of(path):
    if path.name == DECIDED_FILE:
        return "decided"
    return "check" if path.name.startswith("check") else "sort"


def cmd_sorted(pad, files, steps):
    schemas = fr.load_json(SORT_SCHEMA, "schema")["$defs"]
    if files:  # a piece's own check: the lines of the files named, and no more
        if steps:
            raise fr.Refused("sorted: --step checks whole steps; it goes with no file named")
        failed = False
        for path in map(Path, files):
            records, problems = read_lines(path, kind_of(path), schemas)
            for line in problems:
                print(f"problem: {line}", file=sys.stderr)
            failed = failed or bool(problems)
            print(f"{path.name}: {len(records)} lines read, "
                  + (f"{len(problems)} problems" if problems else "no problems"))
        return 1 if failed else 0
    folder = pad / "triage"
    findings = {f["number"]: f for f in fr.load_json(folder / FINDINGS_FILE, "findings")}
    # The findings held to the check: every gathered one, or those of the steps named. A record
    # may name any gathered finding, whatever its step.
    wanted = set(findings)
    if steps:
        for s in steps:
            if not any(s in step_names(f) for f in findings.values()):
                raise fr.Refused(f"--step {s}: no gathered finding is of that step; a step is "
                                 "named by its area or by its issue's number")
        wanted = {n for n, f in findings.items() if step_names(f) & set(steps)}
    paths = sorted(folder.glob("sort-*.jsonl")) + sorted(folder.glob("check*.jsonl"))
    if not any(kind_of(p) == "sort" for p in paths):
        raise fr.Refused(f"{folder}: no sort-*.jsonl file; the sort's pieces write them")
    if (folder / DECIDED_FILE).is_file():
        paths.append(folder / DECIDED_FILE)
    lines, problems = {"sort": {}, "check": {}, "decided": {}}, []
    for path in paths:
        records, bad = read_lines(path, kind_of(path), schemas)
        problems += bad
        for where, r in records:
            lines[kind_of(path)].setdefault(r["finding"], []).append((where, r))
    for kind, what in (("sort", "sorted"), ("check", "judged by the checker"),
                       ("decided", "decided")):
        for n, got in sorted(lines[kind].items()):
            if n not in findings:
                problems.append(f"{got[0][0]}: #{n} is no finding of {FINDINGS_FILE}")
            elif n in wanted and len(got) > 1:
                problems.append(f"#{n} is {what} {len(got)} times ("
                                + ", ".join(w for w, _ in got) + ")")
    for n in sorted(wanted):
        if n not in lines["sort"]:
            problems.append(f"#{n} has no sort record")
        elif findings[n]["severity"] in ("High", "Med") and n not in lines["check"]:
            problems.append(f"#{n} ({findings[n]['severity']}) has no line of the checker's")
    for kind in ("sort", "decided"):
        for n, got in sorted(lines[kind].items()):
            for where, r in got if n in wanted else []:
                for m in r.get("depends_on", []) + r.get("related", []):
                    if m not in findings:
                        problems.append(f"{where}: #{n} names #{m}, which is no finding of "
                                        f"{FINDINGS_FILE}")
    for line in problems:
        print(f"problem: {line}", file=sys.stderr)
    out, differ, decided, counts = [], 0, 0, {}
    for n in sorted(wanted & set(lines["sort"])):
        r = dict(lines["sort"][n][0][1])
        judged = lines["check"].get(n)
        settled = lines["decided"].get(n)
        if judged:
            r["checker"] = {k: judged[0][1][k] for k in ("readiness", "note")}
            if r["checker"]["readiness"] != r["readiness"]:
                # They differ: the finding is the owner's choice, whichever of them said what.
                differ += 1
                if not settled:
                    print(f"differs: #{n} is \"{r['readiness']}\" to the sorter and "
                          f"\"{r['checker']['readiness']}\" to the checker: a choice"
                          + ("" if "ask" in r else ", whose ask is still to write"))
                r["sorted_as"], r["readiness"] = r["readiness"], "choice"
        if settled:
            # The owner has decided: the record made of the decision stands in the sorter's place.
            decided += 1
            r = dict(settled[0][1], decided=True)
        counts[r["readiness"]] = counts.get(r["readiness"], 0) + 1
        out.append(r)
    print(f"{len(out)} of {len(wanted)} findings sorted"
          + (f" (of {', '.join(steps)} alone)" if steps else "") + ": "
          + ", ".join(f"{counts.get(k, 0)} {k}" for k in ("ready", "choice", "check", "not now"))
          + f"; the checker differs on {differ}; {decided} decided; "
          + (f"{len(problems)} problems" if problems else "no problems"))
    if problems:
        return 1
    if steps:  # a look at some steps: the whole check writes what the schedule is made from
        return 0
    (folder / SORTED_FILE).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {folder / SORTED_FILE}")
    return 0


# ---- check ----

def problems_within(schedule, config):
    """What is wrong with the schedule read on its own, and what is worth a note."""
    out, notes = [], []
    units = schedule["units"]
    records, seen_records = {}, set()
    for r in schedule["findings"]:
        if r["finding"] in seen_records:
            out.append(f"#{r['finding']} has two records")
        seen_records.add(r["finding"])
        records[r["finding"]] = r
    place, order = {}, {}
    for k, u in enumerate(units):
        if u["id"] in order:
            out.append(f"two units are {u['id']}")
        order.setdefault(u["id"], k)
        for n in u["findings"]:
            if n in place:
                out.append(f"#{n} is in {place[n]} and in {u['id']}; a finding is in one unit")
            place.setdefault(n, u["id"])
    aside = {s["finding"] for s in schedule.get("set_aside", [])}
    for n in sorted(aside & set(place)):
        out.append(f"#{n} is set aside and in {place[n]}")
    changed, at = {}, config["shared_at"]
    for u in units:
        for f in u["files"]:
            changed.setdefault(f, []).append(u["id"])
    shared = schedule.get("shared_files", [])
    for f in shared:
        n = len(changed.get(f, []))
        if n < at:
            out.append(f"{f} is listed as shared and {n} unit{' changes' if n == 1 else 's change'}"
                       f" it: a shared file is one that {at} or more change")
    for f, ids in sorted(changed.items()):
        if len(ids) >= at and f not in shared:
            notes.append(f"{f} is changed by {len(ids)} units ({', '.join(ids)}) and is not listed "
                         "as shared: they start in the schedule's order")
    for k, u in enumerate(units):
        for d in u.get("depends_on", []):
            if d not in order:
                out.append(f"{u['id']} depends on {d}, which is no unit")
            elif order[d] >= k:
                out.append(f"{u['id']} depends on {d}, which comes no earlier")
        if len(u["findings"]) > config["unit_size"] and "oversize" not in u:
            out.append(f"{u['id']} holds {len(u['findings'])} findings, over the limit of "
                       f"{config['unit_size']}, and gives no reason (oversize)")
        files = set(u["files"])
        for n in u["findings"]:
            r = records.get(n)
            if r is None:
                out.append(f"#{n}, in {u['id']}, has no record")
                continue
            if r["readiness"] not in ("ready", "check"):
                out.append(f"#{n}, in {u['id']}, is sorted as \"{r['readiness']}\": a unit holds "
                           "only findings that are ready or need a check")
            for f in sorted(set(r["files"]) - files):
                out.append(f"{u['id']} lacks {f}, which #{n}'s fix changes")
            for d in r.get("depends_on", []):
                if d in aside:
                    out.append(f"#{n}, in {u['id']}, depends on #{d}, which is set aside")
                elif d in place and order[place[d]] > k:
                    out.append(f"#{n}, in {u['id']}, depends on #{d}, which is in the later "
                               f"{place[d]}")
                elif d not in place:
                    notes.append(f"#{n}, in {u['id']}, depends on #{d}, which no unit holds")
    return out, place, aside, notes


def cmd_check(config, schedule, offline):
    out, place, aside, notes = problems_within(schedule, config)
    if not offline:
        findings = {f["number"]: f for f in findings_of(config, sweep_issues(config))}
        for n in sorted(to_schedule(config, findings.values()) - set(place) - aside):
            out.append(f"#{n} is open and in no unit, nor set aside")
        for n in sorted(set(place) | aside):
            if n not in findings:
                out.append(f"#{n} is no finding of {schedule['sweep']}")
            elif findings[n]["state"] != "open":
                notes.append(f"#{n} is closed: it can be taken out")
            elif config["dismiss_label"] in findings[n]["labels"] and n in place:
                notes.append(f"#{n} carries the {config['dismiss_label']} label: it can be taken "
                             f"out of {place[n]}")
    for line in notes:
        print(f"note: {line}")
    for line in out:
        print(f"problem: {line}", file=sys.stderr)
    held = sum(len(u["findings"]) for u in schedule["units"])
    print(f"{schedule['sweep']}: {len(schedule['units'])} units holding {held} findings, "
          f"{len(aside)} set aside: " + (f"{len(out)} problems" if out else "no problems")
          + (" (not checked against GitHub)" if offline else ""))
    return 1 if out else 0


# ---- next ----

def linked(a, b):
    """Whether two findings' records name one another: related, or one depends on the other."""
    return b["finding"] in a.get("related", []) + a.get("depends_on", []) \
        or a["finding"] in b.get("related", []) + b.get("depends_on", [])


def between(e, u, records, shared):
    """Why the unit u can't run beside the earlier unit e, or None when it can. A finding of u
    depends on one of e; they share a file that isn't one of the schedule's shared files; or they
    share a shared file in which a finding of one is related to, or depends on, one of the other."""
    for n in u["findings"]:
        for d in records.get(n, {}).get("depends_on", []):
            if d in e["findings"]:
                return f"#{n} depends on #{d}"
    common = sorted(set(e["files"]) & set(u["files"]))
    own = [f for f in common if f not in shared]
    if own:
        return f"they share {own[0]}" + (f" and {len(own) - 1} more" if len(own) > 1 else "")
    for f in common:
        mine = [records[n] for n in u["findings"] if f in records.get(n, {}).get("files", [])]
        for a in (records[n] for n in e["findings"] if f in records.get(n, {}).get("files", [])):
            for b in mine:
                if linked(a, b):
                    return f"#{a['finding']} and #{b['finding']} are related and both change {f}"
    return None


def waits(schedule, merged):
    """{unit id: {an earlier unit not merged: why the unit waits on it}}: it depends on it, or
    they can't run side by side (see `between`)."""
    units, shared = schedule["units"], set(schedule.get("shared_files", []))
    records = {r["finding"]: r for r in schedule["findings"]}
    out = {}
    for k, u in enumerate(units):
        why = {d: "it depends on it" for d in u.get("depends_on", []) if d not in merged}
        for e in units[:k]:
            reason = e["id"] not in merged and between(e, u, records, shared)
            if reason:
                why.setdefault(e["id"], reason)
        out[u["id"]] = why
    return out


def sharing(a, b, shared):
    """How two units' files overlap, in words, or None when they share none. The files that aren't
    shared ones come first; shared ones are named as such."""
    common = sorted(set(a["files"]) & set(b["files"]))
    if not common:
        return None
    own = [f for f in common if f not in shared]
    more = len(own or common) - 1
    return f"they share {(own or common)[0]}" + ("" if own else ", a shared file") + \
        (f" and {more} more" if more else "")


def listed(names):
    """"U01", "U01 and U02", "U01, U02 and U03"."""
    names = list(names)
    return " and ".join(([", ".join(names[:-1])] if names[:-1] else []) + names[-1:])


def cmd_next(config, schedule, started):
    units = schedule["units"]
    ids = {u["id"] for u in units}
    for uid in started:
        if uid not in ids:
            raise fr.Refused(f"--started {uid}: no such unit")
    states = {i: s for i, s in unit_states(config, schedule["sweep"]).items() if i in ids}
    for uid in started:
        states.setdefault(uid, {"state": "started", "pr": None, "on": None, "on_merged": False})
    merged = {i for i in ids if states.get(i, {}).get("state") == "merged"}
    opened = {i for i in ids if states.get(i, {}).get("state") in ("open", "started")}
    label = config["refine_label"]
    refine = {f["number"] for f in findings_of(config, sweep_issues(config))
              if f["state"] == "open" and label in f["labels"]}
    why = waits(schedule, merged)
    shared = set(schedule.get("shared_files", []))
    below = {i: stack_below(i, states) for i in opened}
    limit = config["open_units"]
    room, starting = limit - len(opened), []
    lines = []
    for u in units:
        uid, blockers = u["id"], why[u["id"]]
        if uid in merged:
            line = f"merged (#{states[uid]['pr']})"
        elif uid in opened:
            pr, on = states[uid]["pr"], states[uid]["on"]
            line = f"open (#{pr})" if pr else "started, no pull request yet"
            if below[uid]:
                line += f", stacked on {below[uid][0]} (#{on})"
            elif on:
                line += f", stacked on #{on}" + (", which has merged: it takes the target in"
                                                 if states[uid]["on_merged"] else "")
        else:
            held = [n for n in u["findings"] if n in refine]
            # The open units it overlaps, in the schedule's order: those that hold it back, and any
            # it shares a file with, a shared file included. It starts on the branch that holds
            # them all, so they must be one stack: one of them, with the others below it.
            need = {e["id"]: blockers.get(e["id"]) or sharing(e, u, shared) for e in units
                    if e["id"] in opened}
            need = {i: w for i, w in need.items() if w}
            tips = [t for t in need if set(need) <= {t, *below[t]}]
            bare = [i for i in need if not states[i]["pr"]]
            if held:
                line = "waits on the owner: " + ", ".join(f"#{n}" for n in held) + \
                    f" carr{'ies' if len(held) == 1 else 'y'} the {label} label"
            elif set(blockers) - opened:
                line = "waits on " + ", ".join(f"{i} ({w})" for i, w in blockers.items())
            elif bare or (need and not tips):
                line = "waits on " + ", ".join(f"{i} ({w})" for i, w in need.items()) + ": "
                if bare:
                    line += (f"{listed(bare)} {'has' if len(bare) == 1 else 'have'} no pull request "
                             "yet, and a unit is stacked only on one that has")
                elif len(need) == 2:
                    line += ("both are open and neither is stacked on the other, so it can't be "
                             "stacked on both")
                else:
                    line += ("they are open and no one of them is stacked on all the others, so it "
                             "can't be stacked on them all")
            elif room <= 0:
                line = f"waits for a place: the limit is {limit} open units"
            else:
                room -= 1
                line = "can start"
                if tips:
                    tip, under = tips[0], below[tips[0]]
                    line += f" stacked on {tip}" + \
                        (f", which is stacked on {', then '.join(under)}" if under else "") + \
                        (f" ({need[tip]})" if len(need) == 1 and not under else
                         " (" + "; ".join(f"{i}: {w}" for i, w in need.items()) + ")") + \
                        f"; it goes ready after {listed([*reversed(under), tip])} " + \
                        ("merge" if under else "merges")
                # Others that can start now and share a file with it (a shared one, or they would
                # hold it back): once one of them is open, the other is stacked on it.
                too = [e["id"] for e in starting if set(e["files"]) & set(u["files"])]
                if too:
                    line += (f"; it shares a shared file with {listed(too)}, which can start too: "
                             "the later to start is stacked on the earlier")
                starting.append(u)
        lines.append(f"{uid} {u['name']}: {line}")
    print(f"{schedule['sweep']}: {len(units)} units: {len(merged)} merged, {len(opened)} open, "
          f"{len(starting)} can start")
    print("\n".join(lines))
    return 0


# ---- guard ----

def cmd_guard(config, schedule, path, uid, base, on):
    unit = next((u for u in schedule["units"] if u["id"] == uid), None)
    if unit is None:
        raise fr.Refused(f"guard {uid}: no such unit")
    if on is not None and (on == uid or all(u["id"] != on for u in schedule["units"])):
        raise fr.Refused(f"guard {uid} --on {on}: " + ("a unit is stacked on another"
                                                       if on == uid else "no such unit"))
    out = fr.run(["git", "diff", "--name-only", f"{base}...HEAD"], f"git diff {base}...HEAD")
    changed = [line for line in out.splitlines() if line]
    outside = [f for f in changed if f not in set(unit["files"]) | {path.as_posix()}]
    if not outside:
        print(f"{uid}: all {len(changed)} changed files are in its plan")
        return 0
    states = unit_states(config, schedule["sweep"])
    # The open units it is stacked on: --on's and those below it, or what its pull request says.
    if on is None:
        under = stack_below(uid, states)
    else:
        under = [on, *stack_below(on, states)] if states.get(on, {}).get("state") == "open" else []
    stopped = False
    for f in outside:
        claimed = [o["id"] for o in schedule["units"] if o["id"] != uid and f in o["files"]
                   and states.get(o["id"], {}).get("state") != "merged"]
        beside = [i for i in claimed if i not in under]
        if f in schedule.get("shared_files", []):
            print(f"outside the plan: {f} (a shared file: add it to {uid}'s files)")
        elif beside:
            stopped = True
            print(f"stop: {f} is outside {uid}'s plan, and {', '.join(beside)} "
                  f"claim{'s' if len(beside) == 1 else ''} it", file=sys.stderr)
        elif claimed:
            print(f"outside the plan: {f} ({listed(claimed)} claim"
                  f"{'s' if len(claimed) == 1 else ''} it, and {uid} is stacked on "
                  f"{'it' if len(claimed) == 1 else 'them'}: add it to {uid}'s files)")
        else:
            print(f"outside the plan: {f} (no other unmerged unit claims it: add it to {uid}'s "
                  "files)")
    if stopped:
        print(f"{uid}: stopped until the schedule is corrected", file=sys.stderr)
    return 1 if stopped else 0


# ---- unscheduled ----

def cmd_unscheduled(config, schedule):
    _, place, aside, _ = problems_within(schedule, config)
    findings = findings_of(config, sweep_issues(config))
    missing = to_schedule(config, findings) - set(place) - aside
    left = [f for f in findings if f["number"] in missing]
    for f in left:
        tags = [x for x in (config["refine_label"],) if x in f["labels"]]
        print(f"#{f['number']} {f['severity'] or 'no severity'}"
              + (f" [{', '.join(tags)}]" if tags else "") + f" {f['title']}")
    print(f"{schedule['sweep']}: {len(left)} open findings the schedule doesn't hold")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command",
                        choices=["gather", "sorted", "check", "next", "guard", "unscheduled"])
    parser.add_argument("args", nargs="*", help="guard: the unit's id; sorted: the files to check "
                        "alone (default: every sort and check file of the work pad)")
    parser.add_argument("--config", default="docs/review.json",
                        help="the project's review config (default docs/review.json)")
    parser.add_argument("--sweep", help="the sweep, <prefix><N> such as CR1 (default: from the "
                        "branch code-review-<N>, else from the one schedule file)")
    parser.add_argument("--pad", help="gather, sorted: the review's work pad (default review/<N>)")
    parser.add_argument("--schedule", help="the schedule file (default: the config's schedule path)")
    parser.add_argument("--base", help="guard: the commit the unit's branch is compared with")
    parser.add_argument("--on", help="guard: the unit this one is stacked on, while its own pull "
                        "request isn't open to say so")
    parser.add_argument("--started", default="", help="next: the ids of units begun with no pull "
                        "request yet, separated by commas")
    parser.add_argument("--offline", action="store_true",
                        help="check: the schedule alone, without reading GitHub")
    parser.add_argument("--step", default="", help="sorted: check these steps alone, each named "
                        "by its area or its issue's number, separated by commas")
    args = parser.parse_args(argv)
    try:
        config = fr.load_config(args.config)
        steps = [s for s in args.step.split(",") if s]
        if steps and args.command != "sorted":
            raise fr.Refused(f"{args.command} takes no --step")
        if args.on and args.command != "guard":
            raise fr.Refused(f"{args.command} takes no --on")
        if args.command == "sorted" and (args.args or args.pad):
            pad = Path(args.pad or ".")  # the files named, or the pad named: no sweep is needed
            if not args.args and not (pad / "triage").is_dir():
                raise fr.Refused(f"work pad {pad}: no triage folder; gather makes it")
            return cmd_sorted(pad, args.args, steps)
        number = sweep_number(config, args.sweep)
        fr.name_review(config, number)
        if args.command == "sorted":
            return cmd_sorted(Path(f"review/{number}"), [], steps)
        if args.command != "guard" and args.args:
            raise fr.Refused(f"{args.command} takes no argument")
        if args.command == "gather":
            pad = Path(args.pad or f"review/{number}")
            if not pad.is_dir():
                raise fr.Refused(f"work pad {pad}: not a folder")
            return cmd_gather(config, pad)
        path = schedule_path(config, args.schedule)
        schedule = load_schedule(config, path)
        if args.command == "check":
            return cmd_check(config, schedule, args.offline)
        if args.command == "next":
            return cmd_next(config, schedule, [s for s in args.started.split(",") if s])
        if args.command == "unscheduled":
            return cmd_unscheduled(config, schedule)
        if len(args.args) != 1 or not args.base:
            raise fr.Refused("guard: <unit> --base <ref>, the unit's id and the commit its branch "
                             "is compared with")
        return cmd_guard(config, schedule, path, args.args[0], args.base, args.on)
    except fr.Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    except fr.Failed as e:
        print(f"stopped: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
