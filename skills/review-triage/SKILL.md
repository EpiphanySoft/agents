---
name: review-triage
description: "Turn a posted code review's findings into an ordered schedule of work units, one pull request each, and run it. Use when the owner asks what follows a review, to triage or schedule its findings, which unit is next or can start, or how to run a sweep's fixes. Covers gathering the open findings, sorting each one (ready, choice, check, not now), the owner's choices asked up front, batching by the files that change together, the schedule file and its checks, what may run side by side, the standing rules for what comes up mid-work, the question, refine and dismiss labels, a pull request's merge-readiness, and changing the schedule."
---

# Review triage

A review ends at findings with agreed resolutions, each its own issue. Triage is what follows: it
turns those findings into a **schedule** of **work units**, one pull request each, in an order that
lets as much as possible run side by side without two units colliding. Then the schedule is run.

It serves three goals, and every choice the coordinator makes while scheduling is judged by them:

1. **The fewest trips back to the owner.** What the owner must decide is asked up front, together.
    What comes up later follows a standing rule, or is set aside without stopping the work.
2. **As far as possible within the limits.** Units run side by side wherever their files allow and
    the project's limits permit.
3. **No collisions.** Two units that change the same file never run side by side.

The skill has two parts. **Triage** ends at a schedule the owner has approved; it changes no code and
no requirement. **Running the schedule** is how each unit goes from branch to merge, and how the
schedule changes on the way.

The `review` skill's terms hold here and are not restated: the sweep, its anchor and steps, the work
pad, a session's habits, pieces and their briefs, the walk thru, models and effort, and refusals and
model changes.

## What a project supplies

In its review config, `docs/review.json`, beside what the `review` skill reads there:

| Field | Default | What |
|---|---|---|
| `schedule` | `docs/remediation/{sweep}-schedule.json` | where a sweep's schedule is kept |
| `unit_size` | 20 | the most findings a unit holds without giving a reason |
| `open_units` | 3 | the most units open at once: started and not yet merged |
| `question_label` | `question` | a question issue |
| `refine_label` | `refine` | a finding that waits on the owner's decision |
| `dismiss_label` | `dismiss` | a finding the work showed to be no defect |

The three labels exist in the repository. The project's own documents say how a fix is made and
proven (its tests, its containers and VMs, its commit and push rules); this skill adds none.

## The labels

| Label | On | Open | Closed |
|---|---|---|---|
| `question` | a question issue | it waits for the owner's answer | answered; the label stays |
| `refine` | a finding | it can't be worked until the owner decides something about it | never: the label comes off when the decision is recorded |
| `dismiss` | a finding | proposed for dismissal, with the evidence on the issue | dismissed by the owner; the label stays |

A finding is work, so it never carries `question`. What waits on the owner is the open issues with
any of the three labels.

# Part 1: Triage

Triage runs in six stages: **Gather**, **Sort**, **The owner's choices**, **Batch**, **Order** and
**The schedule**. Its working files are in the review's work pad, under `review/<N>/triage/`, on the
review's local branch; only the approved schedule goes to the target branch. Each session's line
goes in the review's `log.md`.

Before it starts, the coordinator proposes how the sort will run: its pieces, the model and effort
of each, and an estimate in tokens, as a review's proposal does. The owner's answer goes in `log.md`.

## Gather

`triage.py gather` reads the sweep's issues from GitHub and writes its open findings to
`triage/findings.json`: each one's number, title, severity, area, step, labels and whole body. The
issues are the record: a finding closed, decided or filed since the review is read as it now stands.
The anchor, the steps and their parts, and question issues are no findings.

## Sort

Each finding gets a record:

| Part | What |
|---|---|
| **readiness** | `ready`: the remedy is clear and nothing in it is the owner's to choose. `choice`: it needs the owner's decision, written as a walk-thru item (the question, the options, the recommendation). `check`: it can't be sorted until a fact is known, such as whether it reproduces. `not now`: proposed as later work or as not planned, with the reason. |
| **files** | every file its fix changes: code, tests, requirement sections, shared test data |
| **depends on** | the findings that must be fixed first, and those the same change fixes |
| **size** | small, medium or large |
| **proof** | what proving the fix needs: a test, a container, a VM |

- **In doubt, it is the owner's.** When the sorter can't tell whether a choice is the owner's or the
    implementer's, the finding is a `choice`. A question asked up front costs the owner a minute; one
    found mid-work stalls a unit.
- **A choice is the owner's** when the remedies differ in what the user sees or in what a
    requirement says, or when the finding asks whether to build, write down or remove something. A
    choice between two ways to get the same behaviour is the implementer's.
- **A check** that one test or one command settles is made during the sort, under the `review`
    skill's rule for running little. One that needs more stays a `check`, and is the first thing its
    unit does.

**The pieces.** One piece sorts each area step's findings, reading them whole, with the code they
cite where a file list needs it. A **checker** on a different model then judges the readiness of every
High and Med finding again, from the finding alone and blind to the sorter's reasons: a finding
wrongly sorted as ready is what stalls a unit later. Where they differ, the finding is a `choice`.
Each piece writes `triage/sort-<step>.jsonl` as it goes, and is checked for a refusal or a model
change as the `review` skill says.

## The owner's choices

Every `choice`, every `not now` and every finding a check showed to be no defect is the owner's, and
all of them are asked in **one walk thru before the schedule is made** (the shared `CLAUDE.md` rule).
The schedule is only as stable as the decisions under it.

- **Grouped.** Choices that turn on the same rule are one item, so one answer settles several
    findings. Small choices on Low findings (change the code or change the wording) come as one
    list with the recommended pick for each. The owner can split any item.
- **Labelled while they wait.** A finding sorted as a `choice` gets the `refine` label when the sort
    ends, so the repository shows what waits on the owner.
- **Recorded.** After the walk thru's final approval, each decision goes on its finding as a
    comment and the `refine` label comes off. A finding the owner sets aside for later goes to the
    project's later work; one that is no defect gets `dismiss` and is the owner's to close.

## Batch

A **work unit** is one pull request. Findings are batched **by the files that change together**, not
by the area step they were filed under: findings whose fixes change the same files go in the same
unit, named for what it changes ("the sync loop"). A unit can close findings from several steps; each
finding stays under its step as an issue.

- **A requirement's text travels with its code.** When a fix changes code and the requirement it
    builds, both are in one unit, so the requirements are never ahead of the code. Document
    corrections with no code behind them get units of their own.
- **Size.** A unit holds at most `unit_size` findings. A High security finding may be a small unit
    of its own, so it merges fast. Plain document corrections may be batched larger; a unit over the
    limit says why (`oversize`).
- **Whole.** Findings one change fixes are in one unit. A finding and what it depends on are in one
    unit, or the dependency's unit comes first.

## Order

Units are ordered by:

1. **severity**: a unit takes the place of its most severe finding;
2. **what they hold back**: a unit on files many other units share goes early;
3. **dependencies**: a unit comes after every unit it depends on.

Inside a unit, findings are fixed most severe first.

## The schedule

The schedule is one JSON file per sweep, at the project's `schedule` path, checked against
[`schedule.schema.json`](schedule.schema.json):

- **`units`**, in their order: each one's `id` ("U07"), `name`, `findings` (issue numbers), `files`
    (every file its fixes change) and, where it has them, `depends_on` and `oversize`;
- **`findings`**: each finding's record from the sort;
- **`set_aside`**: the open findings no unit holds, each with the reason.

It holds the plan and nothing else. **Progress is read from GitHub**: a unit is open while its pull
request is, and done when that is merged; a finding is done when its issue is closed. So the file
never goes stale, and no pull request is made to tick a box.

`triage.py check` holds a schedule to its rules: every open finding is in exactly one unit or set
aside; every finding in a unit has its record, and is ready or needs a check; a unit's files hold its
findings' files; a dependency is on an earlier unit; no unit is over the limit without its reason.

The schedule reaches the target branch as a pull request the owner reads and merges: that merge is
the approval, and Part 1 ends there.

# Part 2: Running the schedule

## What can start

A unit may start when all of these hold:

1. every earlier unit that shares a file with it is merged;
2. every unit it depends on is merged;
3. none of its findings carries the `refine` label;
4. fewer than `open_units` units are open.

`triage.py next` computes it, the same in every session: for each unit, whether it is merged, open,
can start, or what it waits on. No lane is assigned by hand.

**One deep.** To use the time a review takes, a unit held back by exactly one unit, which is open and
itself sits on nothing unmerged, may start on top of that unit's branch. Its pull request opens only
after the first has merged and it has taken the target branch in by a merge, never a rebase.

## A unit, from branch to merge

1. **Start** from the target branch (or on top of the one open unit, as above). The unit's session
    reads the unit's entry in the schedule, its findings' issues and the project's own rules for a
    fix. It fixes most severe first.
2. **The guard**, before the pull request opens and before each push after: `triage.py guard <unit>
    --base <ref>` compares the files the branch changed with the unit's `files`. A file outside the
    plan that another unmerged unit claims stops the unit until the schedule is corrected. A file no
    other unit claims is added to the unit's `files`.
3. **The pull request** opens as a draft, with the sweep label, a "Closes #n" line for each finding
    it fixes, and the unit's marker at the end of its description: `<!-- remediation CR1 U07 -->`.
4. **Ready for the owner** when all of these hold:
    - CI is green;
    - a `pr-review` pass has run on a different model from the one that did the work, and everything
        it raised is fixed or answered;
    - every finding of the unit is closed by the pull request, or set aside with `refine`,
        `question` or `dismiss`, and the description lists each one with its commit and its test;
    - the description opens with **Needs your eye**: only the commits that change what the user
        sees or what a requirement says.
5. **The owner merges**, every unit. After the merge: confirm and cleanup (the shared `CLAUDE.md` PR
    terms), then `next`.

**Merge-readiness, in every update.** Whenever the owner is told anything about a pull request, the
message says where its merge stands: "merge waits on CI and the review pass", naming each agreed
thing not yet done, or "merge is yours" when nothing is left but the owner's approval.

## What comes up mid-work

These are standing rules. None of them stops a unit to ask.

| What comes up | What the unit does |
|---|---|
| **A finding won't reproduce** | A tests-only commit shows the behaviour is right. The evidence goes on the issue, the finding gets `dismiss`, and it leaves the unit's "Closes" lines. The owner closes it, or says the point stands. |
| **The stated remedy is wrong, or an alternative fits better** | The implementer picks, and says so in the commit and on the issue, when what the user sees and what the requirement says are the same either way. When either differs, the finding gets `refine`. |
| **A new finding** | It is always filed as an issue under its step, with the sweep and area labels. It is fixed in this unit only when it is small and in the unit's own files; otherwise the schedule takes it in. A High one is reported to the owner at once. |
| **Something new for the owner** | A finding's own choice makes it `refine`. Anything else, a wider rule or something no finding covers, is a new question issue under its step (`file_review.py question`). |

**Set aside, never waited for.** A finding that gets `refine` is taken out of the unit: its commits
are left out and its "Closes" line goes. The unit goes on without it and opens its pull request.
What was set aside in every running unit is gathered and brought to the owner **together, as one
walk thru, each time a pull request is ready for review**, never one at a time. So the owner's input
is needed at two kinds of moment: the walk thru before the schedule, and when a pull request is ready.

Each answer is recorded as *The owner's choices* says, and the `review` skill's "Once answered" says
what becomes of a question issue.

## Changing the schedule

Scheduling is the coordinator's: it changes the schedule whenever the three goals are better served,
and asks the owner only when a decision that is the owner's is needed. The usual changes:

- a new finding, or one the owner has just decided, joins a unit that hasn't started and holds its
    files, or a new unit;
- a finding closed or carrying `dismiss` is taken out;
- a unit's `files` are corrected when the guard names a file;
- units are reordered, split or joined when that lets more run, or keeps a review small.

`triage.py unscheduled` lists the open findings the schedule doesn't hold, and `check` passes before
any change is used.

**A change rides in the next unit's pull request to open**, where the owner sees the schedule's
diff beside the work. Until that merges the coordinator works from its newest copy. A pull request
for the schedule alone is made only when no unit is about to open one.

**The sort is redone from scratch** only when the owner asks or a new review is posted. The
coordinator may suggest it when the schedule has drifted far from the findings, and never waits on
the answer.

## When it is done

The sweep's work is done when every finding is closed, or is open only with `dismiss` or as later
work the owner has set aside. The schedule file stays as the record of how it went. Issues are the
owner's to close, as the `review` skill says.

## The script

`triage.py`, in this folder, reads GitHub through the `gh` CLI and writes nothing there. Run it from
the repository's root:

```
python3 <skill>/triage.py gather      [--sweep CR1] [--pad review/<N>]
python3 <skill>/triage.py check       [--sweep CR1] [--schedule <file>] [--offline]
python3 <skill>/triage.py next        [--sweep CR1] [--schedule <file>] [--started U08,U09]
python3 <skill>/triage.py guard <unit> --base <ref> [--sweep CR1] [--schedule <file>]
python3 <skill>/triage.py unscheduled [--sweep CR1] [--schedule <file>]
```

- **Which sweep**: `--sweep`, else the branch `code-review-<N>`, else the one schedule file the
    project holds.
- **A unit's state** is its pull request's, found by the unit's marker in its description; one
    closed without a merge counts for nothing. `--started` names units begun with no pull request
    yet, such as one started on top of another.
- **`check --offline`** checks the schedule against its schema and itself, without GitHub.
- **Exit status**: 0 done; 1 the schedule has problems, a guard stopped, or a `gh` or `git` call
    failed; 2 refused (a bad config, schedule or argument).

`test_triage.py` runs it against a stub `gh` in a temp directory, so nothing reaches GitHub.

## Adopting this skill

A project adopts it once it has the `review` skill: it makes the `refine` and `dismiss` labels, sets
the fields above where the defaults don't fit, and may show the schedule on its own pages (the units
in order, each with its findings open and closed and its pull request).
