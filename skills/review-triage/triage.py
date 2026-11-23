#!/usr/bin/env python3
"""A sweep's work schedule: gather a posted review's open findings, check the schedule made from
them, and say which of its work units can start. See SKILL.md beside this script.

    triage.py gather      [--sweep CR1] [--config docs/review.json] [--pad review/<N>]
    triage.py check       [--sweep CR1] [--config ...] [--schedule <file>] [--offline]
    triage.py next        [--sweep CR1] [--config ...] [--schedule <file>] [--started U08,U09]
    triage.py guard <unit> --base <ref> [--sweep CR1] [--config ...] [--schedule <file>]
    triage.py unscheduled [--sweep CR1] [--config ...] [--schedule <file>]

The sweep is <prefix><N> (CR1): named by --sweep, else by the branch code-review-<N>, else by the
one schedule file the project holds. The schedule is the project's `schedule` path (docs/review.json;
docs/remediation/<sweep>-schedule.json by default), checked against schedule.schema.json.

`gather` writes the sweep's open findings, read from their issues, to <pad>/triage/findings.json:
what the sort reads, each with its body and the comments of the project's owners, members and
collaborators, where a decision is recorded. `check` checks a schedule: against the schema, against itself (a finding in one
unit only, each with its record, a unit's files holding its findings' files, a dependency on an
earlier unit, no unit over the project's unit_size without its reason) and, unless --offline, against
GitHub (every open finding in a unit or set aside). `next` says, for each unit in order, whether it
is merged, open, can start, can start on top of one open unit, or what it waits on; a unit's state
is its pull request's, found by the marker `<!-- remediation CR1 U07 -->` in its description, and
--started names units begun with no pull request yet. `guard` compares the files a unit's branch
changed since <ref> with the unit's plan, and stops (exit 1) on a file outside it that another
unmerged unit claims. `unscheduled` lists the open findings the schedule doesn't hold.

It reads GitHub through the gh CLI and writes nothing there. Python 3 standard library, and the
review skill's file_review.py for the config, the schema checker and the sweep's names.

Exit status: 0 done; 1 the schedule has problems, a guard stopped, or a gh or git call failed;
2 refused (a bad config, schedule or argument).
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
FINDINGS_FILE = "findings.json"
UNIT_MARKER = re.compile(r"<!-- remediation (\S+) (\S+) -->")
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
    """{unit id: {"state": "open" or "merged", "pr": n}}, from the pull requests whose description
    carries the unit's marker. One closed without a merge counts for nothing."""
    out = fr.run(["gh", "pr", "list", "--repo", config["repo"], "--state", "all", "--limit", "1000",
                  "--json", "number,state,body"], "gh pr list")
    states = {}
    for pr in json.loads(out):
        state = pr["state"].lower()
        if state == "closed":
            continue
        for m in UNIT_MARKER.finditer(pr.get("body") or ""):
            if m.group(1) == name and (m.group(2) not in states or state == "merged"):
                states[m.group(2)] = {"state": state, "pr": pr["number"]}
    return states


# ---- gather ----

def cmd_gather(config, pad):
    findings = [f for f in findings_of(config, sweep_issues(config)) if f["state"] == "open"]
    folder = pad / "triage"
    folder.mkdir(exist_ok=True)
    keep = ("number", "id", "title", "severity", "area", "step", "labels", "body", "comments")
    (folder / FINDINGS_FILE).write_text(
        json.dumps([{k: f[k] for k in keep} for f in findings], indent=1) + "\n", encoding="utf-8")
    counts = ", ".join(f"{sum(1 for f in findings if f['severity'] == s)} {s}" for s in SEVERITIES)
    unrated = sum(1 for f in findings if f["severity"] is None)
    print(f"wrote {folder / FINDINGS_FILE}: {len(findings)} open findings ({counts}"
          + (f", {unrated} with no severity" if unrated else "") + ")")
    return 0


# ---- check ----

def problems_within(schedule, config):
    """What is wrong with the schedule read on its own."""
    out = []
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
    return out, place, aside


def cmd_check(config, schedule, offline):
    out, place, aside = problems_within(schedule, config)
    notes = []
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

def waits(units, merged):
    """{unit id: {an earlier unit not merged: why the unit waits on it}}: it depends on it, or they
    share a file."""
    out = {}
    for k, u in enumerate(units):
        why = {d: "it depends on it" for d in u.get("depends_on", []) if d not in merged}
        for e in units[:k]:
            shared = sorted(set(e["files"]) & set(u["files"]))
            if shared and e["id"] not in merged:
                more = f" and {len(shared) - 1} more" if len(shared) > 1 else ""
                why.setdefault(e["id"], f"they share {shared[0]}{more}")
        out[u["id"]] = why
    return out


def cmd_next(config, schedule, started):
    units = schedule["units"]
    ids = {u["id"] for u in units}
    for uid in started:
        if uid not in ids:
            raise fr.Refused(f"--started {uid}: no such unit")
    states = unit_states(config, schedule["sweep"])
    for uid in started:
        states.setdefault(uid, {"state": "started", "pr": None})
    merged = {i for i in ids if states.get(i, {}).get("state") == "merged"}
    opened = {i for i in ids if states.get(i, {}).get("state") in ("open", "started")}
    label = config["refine_label"]
    refine = {f["number"] for f in findings_of(config, sweep_issues(config))
              if f["state"] == "open" and label in f["labels"]}
    why = waits(units, merged)
    limit = config["open_units"]
    room, can = limit - len(opened), 0
    lines = []
    for u in units:
        uid, blockers = u["id"], why[u["id"]]
        on_top = ""
        if blockers:
            on_top = "; its pull request opens after " + " and ".join(blockers) + " merge" + \
                ("s" if len(blockers) == 1 else "")
        if uid in merged:
            line = f"merged (#{states[uid]['pr']})"
        elif uid in opened:
            pr = states[uid]["pr"]
            line = (f"open (#{pr})" if pr else "started, no pull request yet") + \
                (on_top if not pr else "")
        else:
            held = [n for n in u["findings"] if n in refine]
            only = next(iter(blockers)) if len(blockers) == 1 else None
            if held:
                line = "waits on the owner: " + ", ".join(f"#{n}" for n in held) + \
                    f" carr{'ies' if len(held) == 1 else 'y'} the {label} label"
            elif blockers and not (only in opened and not why[only]):
                line = "waits on " + ", ".join(f"{i} ({w})" for i, w in blockers.items())
            elif room <= 0:
                line = f"waits for a place: the limit is {limit} open units"
            else:
                room, can = room - 1, can + 1
                line = "can start" + (f" on top of {only} ({blockers[only]}){on_top}"
                                      if only else "")
        lines.append(f"{uid} {u['name']}: {line}")
    print(f"{schedule['sweep']}: {len(units)} units: {len(merged)} merged, {len(opened)} open, "
          f"{can} can start")
    print("\n".join(lines))
    return 0


# ---- guard ----

def cmd_guard(config, schedule, path, uid, base):
    unit = next((u for u in schedule["units"] if u["id"] == uid), None)
    if unit is None:
        raise fr.Refused(f"guard {uid}: no such unit")
    out = fr.run(["git", "diff", "--name-only", f"{base}...HEAD"], f"git diff {base}...HEAD")
    changed = [line for line in out.splitlines() if line]
    outside = [f for f in changed if f not in set(unit["files"]) | {path.as_posix()}]
    if not outside:
        print(f"{uid}: all {len(changed)} changed files are in its plan")
        return 0
    states = unit_states(config, schedule["sweep"])
    stopped = False
    for f in outside:
        claimed = [o["id"] for o in schedule["units"] if o["id"] != uid and f in o["files"]
                   and states.get(o["id"], {}).get("state") != "merged"]
        if claimed:
            stopped = True
            print(f"stop: {f} is outside {uid}'s plan, and {', '.join(claimed)} "
                  f"claim{'s' if len(claimed) == 1 else ''} it", file=sys.stderr)
        else:
            print(f"outside the plan: {f} (no other unmerged unit claims it: add it to {uid}'s "
                  "files)")
    if stopped:
        print(f"{uid}: stopped until the schedule is corrected", file=sys.stderr)
    return 1 if stopped else 0


# ---- unscheduled ----

def cmd_unscheduled(config, schedule):
    _, place, aside = problems_within(schedule, config)
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
    parser.add_argument("command", choices=["gather", "check", "next", "guard", "unscheduled"])
    parser.add_argument("args", nargs="*", help="guard: the unit's id")
    parser.add_argument("--config", default="docs/review.json",
                        help="the project's review config (default docs/review.json)")
    parser.add_argument("--sweep", help="the sweep, <prefix><N> such as CR1 (default: from the "
                        "branch code-review-<N>, else from the one schedule file)")
    parser.add_argument("--pad", help="gather: the review's work pad (default review/<N>)")
    parser.add_argument("--schedule", help="the schedule file (default: the config's schedule path)")
    parser.add_argument("--base", help="guard: the commit the unit's branch is compared with")
    parser.add_argument("--started", default="", help="next: the ids of units begun with no pull "
                        "request yet, separated by commas")
    parser.add_argument("--offline", action="store_true",
                        help="check: the schedule alone, without reading GitHub")
    args = parser.parse_args(argv)
    try:
        config = fr.load_config(args.config)
        number = sweep_number(config, args.sweep)
        fr.name_review(config, number)
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
        return cmd_guard(config, schedule, path, args.args[0], args.base)
    except fr.Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    except fr.Failed as e:
        print(f"stopped: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
