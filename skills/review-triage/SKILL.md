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
3. **No collisions.** Two units that change the same file never run side by side, unless the file
    is one the schedule lists as shared and their findings in it are unrelated (*Shared files*).

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
| `shared_at` | 3 | how many units change a file before the schedule lists it as shared |
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

## How it runs

The skill runs in the **coordinating session**, never as a sub-agent of one. The walk thrus with the
owner, the scheduling across units and the sweep's state from day to day are the coordinator's, and
a choice that is the owner's never goes to an agent (the shared `CLAUDE.md`). So this skill's own
header sets no `context: fork`, no `model` and no `effort`: it runs inline, on the session's model.

Its **pieces** are separate contexts, each started with a short prompt that names the sweep, the
piece, its model and effort, and this skill:

| Piece | Reads | Writes |
|---|---|---|
| **a sort piece** | at most about 40 findings of one area step, from the step's file `triage/findings-<area>.json`, and the code they cite | `triage/sort-<area>.jsonl`, with `-<k>` when a step is split |
| **the checker** | the High and Med findings alone, blind to the sort | `triage/check.jsonl`: its readiness for each |
| **a unit** | its entry in the schedule, its findings' issues, the project's rules for a fix | its branch and its pull request |
| **a `pr-review` pass** | as that skill says | as that skill says |

```
Triage of CR4 (review/4/triage/ on the local code-review-4 branch), with the review-triage skill:
sort the findings of step CR4.3, the first 40, on <model> at <effort>. Start from the review's log.md.
```

```
CR4's schedule (docs/remediation/CR4-schedule.json), with the review-triage skill:
run the unit U07 from <the target branch, or the unit it starts on>, on <model> at <effort>.
```

Sort pieces run several at once, within the project's machine limits; units as *What can start*
allows. Each piece is checked for a refusal or a model change when it ends, as the `review` skill
says, before its work is taken.

## Models and effort

Each piece runs on a named model and a named effort, never a tool's default, as the `review` skill
says. The proposal names today's models for that skill's three levels, **strongest**, **next** and
**cheaper**, with the estimated tokens by model.

- **The sort never runs on the cheaper model or below high effort.** A finding wrongly sorted as
    ready is what stalls a unit later, so the sort is where the stronger model is spent.
- **The checker never runs on the sorter's model.** Where they differ the finding is the owner's
    choice, so a checker that is wrong costs the owner a minute, and no unit stalls.
- **A unit's `pr-review` pass never runs on the unit's model.**

| Piece | Standard | Plus |
|---|---|---|
| Coordinating: the walk thru's items, batching, ordering, scheduling as it runs | next, high | strongest, high |
| Sort | next, high | strongest, high |
| Checker of High and Med readiness | cheaper, high | next, high |
| A unit's fixes | next, high | strongest, high |
| A unit that holds a High finding or changes sensitive code | strongest, high | strongest, high |
| The `pr-review` pass | that skill's table, on a model other than the unit's | the same |

Recommend **Standard** by default, and **Plus** for a project's first sweep or one heavy in sensitive
code. Any piece can be adjusted in the proposal.

# Part 1: Triage

Triage runs in six stages: **Gather**, **Sort**, **The owner's choices**, **Batch**, **Order** and
**The schedule**. Its working files are in the review's work pad, under `review/<N>/triage/`, on the
review's local branch; only the approved schedule goes to the target branch. Each session's line
goes in the review's `log.md`.

Before it starts, the coordinator proposes how the sort will run: its pieces, the level (*Models
and effort*) with today's model and effort for each, and an estimate in tokens, as a review's
proposal does. The owner's answer goes in `log.md`.

## Gather

`triage.py gather` reads the sweep's issues from GitHub and writes its open findings to
`triage/findings.json`: each one's number, its id in the review's work pad (by which other findings
name it), title, severity, area, step, labels, whole body, and the comments of the project's owners,
members and collaborators, where a decision is recorded. The issues are the record: a finding
closed, decided or filed since the review is read as it now stands. The anchor, the steps and their
parts, and question issues are no findings.

It writes them once more a step, as `triage/findings-<area>.json`: a step is named by its area, so
a step in parts is one file. A sort piece reads its own step's file and no more.

## Sort

Each finding gets a record:

| Part | What |
|---|---|
| **readiness** | `ready`: the remedy is clear and nothing in it is the owner's to choose. `choice`: it needs the owner's decision, written as a walk-thru item (the question, the options, the recommendation). `check`: it can't be sorted until a fact is known, such as whether it reproduces. `not now`: proposed as later work or as not planned, with the reason. |
| **files** | every file its fix changes: code, tests, requirement sections, shared test data. Where a unit could extend either of two test files, the likelier one: the guard names what the list missed. |
| **depends on** | the findings that must be fixed first, and those the same change fixes |
| **related** | the findings that change the same function or turn on the same rule, with neither having to come first: batched together where they fit, and asked together where they are choices |
| **size** | small: one or two files and a test. medium: several files, or a proof that needs a container or a VM. large: a feature, or a change across a module. |
| **proof** | what proving the fix needs: the test and its case, a container, a VM. For a document correction, the project's document checks. |

A piece writes one JSON object a line, as it goes, in the form [`sort.schema.json`](sort.schema.json)
gives: the record as the schedule keeps it (`finding`, `readiness`, `files`, `depends_on`,
`related`, `size`, `proof`, `note`), and beside it, for what the owner will be asked:

- for a `choice`, `ask`: its `question`, its `options` (two or more, each an `option` and what it
    `means`) and its `recommendation`, the sorter's own pick with the reason, most often the
    finding's remedy;
- for a `not now`, and for a check that showed no defect, `why`.

A choice's `files`, `size` and `proof` are those of the recommended option, and its `note` says what
the other options would change. The coordinator rewrites the record once the owner has decided.

- **In doubt, it is the owner's.** When the sorter can't tell whether a choice is the owner's or the
    implementer's, the finding is a `choice`. A question asked up front costs the owner a minute; one
    found mid-work stalls a unit.
- **Judged from the stated remedy.** Nearly every finding lists alternatives, and that alone makes
    none of them a choice. A finding is `ready` when its stated remedy is one of these, even when a
    listed alternative isn't: the unit takes the remedy, and taking such an alternative later is a
    `refine`.
    - It makes the code do what a requirement already says, however visible the change.
    - It adds only small interface in a pattern the application already has: a message, a toast, a
        tooltip, a disabled state. The unit lists each one under **Needs your eye**, where the
        owner can still object.
    - It leaves what the requirements ask as it is, or corrects their text without changing what
        they ask: a stale reference, a wrong name.

    A choice between two ways to get the same behaviour is the implementer's.
- **A choice is the owner's** when the stated remedy adds a control, a dialog, a setting or a screen
    that no requirement describes; when it changes what a requirement asks; when the finding gives
    no remedy it prefers, or says in its own words that the choice is the owner's; when it waits on
    a question issue that is still open; or when it asks whether to build, write down or remove
    something. That last one is a `choice` even when the likely answer is "later": taking the text
    out of the requirements is a change made now.
- **Several parts, one of them the owner's.** A finding is one record, however many parts it has.
    When only a part of it is the owner's to choose, the finding is a `choice`: its `ask` covers
    that part alone, and its `note` names the parts that are ready as they stand.
- **Waiting on another finding's ruling.** A finding, or a part of one, that can't be settled until
    the owner has decided another finding names that finding under `related` and says so in its
    `note`. The two are asked together, and the record is written once both are decided.
    `depends_on` is for a fix that must come first.
- **Decided is ready.** A finding that carries the owner's decision, in its body or in a comment,
    is sorted with that decision as its remedy.
- **`not now`** is the sorter's own proposal that nothing be done in this sweep, and that nothing
    needs changing for that to hold.
- **A check** is a fact that decides the sort: whether it is a defect at all, or which remedy
    applies. A part of the claim that was never run, and that doesn't change the remedy, is no
    check: the unit's proof covers it. A check that one test or one command settles is made during
    the sort, under the `review` skill's rule for running little (the proposal says whether the
    sort runs attended). One that needs more stays a `check`, and is the first thing its unit does.

**The pieces.** One piece sorts each area step's findings, at most about 40 a piece (a larger step
is split), reading them whole, with the code they cite where a file list needs it. A **checker** on
a different model then judges the readiness of every High and Med finding again, from the finding
alone and blind to the sorter's reasons: a finding wrongly sorted as ready is what stalls a unit
later. It reads each finding whole, takes what the finding says was run as run, judges neither the
severity nor the files, and writes one line a finding: `finding`, its `readiness` (any of the four)
and a `note` of one sentence. Where the two differ in any way, the finding is a `choice`.

A piece writes only its own file, as it goes (*How it runs*), and before it ends checks it with
`triage.py sorted <its file>`, which holds every line to the schema. It reads and writes nothing on
GitHub, labels nothing and commits nothing: the coordinator writes the line in `log.md` and commits.

**The sort is whole** when `triage.py sorted` passes, with no file named. It holds every piece's
file to the schema; every gathered finding sorted once, and every High and Med one judged once by
the checker; a choice with its question, a `not now` with its reason; and every finding a record
names a gathered one. It lists where the checker differs from the sorter, and writes
`triage/sorted.json`: each finding's record with that settled, a differing one as a `choice` whose
question the coordinator writes into the finding's line of the sort file. The owner's choices, the batching and the schedule are made from
that file, never from a piece's summary.

**A step at a time.** As a step's pieces end, `triage.py sorted --step <area>` holds that step's
findings alone to the same check, so a mistake shows when its step ends and not when the whole sort
does. A record may still name a finding of any step. It writes nothing: the whole check passes
before the walk thru, and a schedule is always made of the whole sweep, since findings of
different steps are fixed by the same change and change the same files.

## The owner's choices

Every `choice`, every `not now` and every finding a check showed to be no defect is the owner's, and
all of them are asked in **one walk thru before the schedule is made** (the shared `CLAUDE.md` rule).
The schedule is only as stable as the decisions under it.

- **Grouped.** Choices that turn on the same rule are one item, so one answer settles several
    findings. Small choices on Low findings (change the code or change the wording) come as one
    list with the recommended pick for each. The owner can split any item.
- **Labelled while they wait.** When the sort ends the coordinator gives each finding sorted as a
    `choice` the `refine` label, so the repository shows what waits on the owner.
- **Recorded.** After the walk thru's final approval, each decision goes on its finding as a
    comment and the `refine` label comes off. The coordinator writes the finding's record anew, as
    `ready` with the files, size and proof of what was decided, as a line of
    `triage/decided.jsonl`. `triage.py sorted` holds that file to the sort's schema and lays its
    records over the pieces' in `sorted.json`, so a decision outlasts the next run and the next
    session. A finding the owner sets aside for later goes to the project's later work; one that
    is no defect gets `dismiss` and is the owner's to close.
- **A decision that settles another finding.** When a decision is also the remedy of a finding
    elsewhere, in any step, it is recorded on that finding too, as a comment that points at the
    first, and the two go in one unit.

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

## Shared files

Some files are changed by many units: a module every screen calls, a test file many fixes add to.
Held to one unit at a time, such a file turns the schedule into one long chain. So the schedule
lists its **shared files**: the files that `shared_at` units or more change (3 by default), test
files included.

- Two units that share only shared files may run side by side, unless a finding of one is related
    to, or depends on, a finding of the other in such a file (the records' `related` and
    `depends_on`): those change the same code.
- Every other file keeps the rule: two units that change it never run side by side.
- Two units side by side on a shared file can still conflict now and then. The later one to merge
    settles it, with no trip to the owner (*A unit, from branch to merge*).

`check` refuses a listed file that fewer units change, and notes a file that many units change and
the list leaves out: the coordinator may leave one out, to keep its units one after another. The
owner sees the list when approving the schedule.

## The schedule

The schedule is one JSON file per sweep, at the project's `schedule` path, checked against
[`schedule.schema.json`](schedule.schema.json):

- **`units`**, in their order: each one's `id` ("U07"), `name`, `findings` (issue numbers), `files`
    (every file its fixes change) and, where it has them, `depends_on` and `oversize`;
- **`findings`**: each finding's record from the sort;
- **`shared_files`**: the files many units change (*Shared files*);
- **`set_aside`**: the open findings no unit holds, each with the reason.

It holds the plan and nothing else. **Progress is read from GitHub**: a unit is open while its pull
request is, and done when that is merged; a finding is done when its issue is closed. So the file
never goes stale, and no pull request is made to tick a box.

`triage.py check` holds a schedule to its rules: every open finding is in exactly one unit or set
aside; every finding in a unit has its record, and is ready or needs a check; a unit's files hold its
findings' files; a dependency is on an earlier unit; no unit is over the limit without its reason;
a shared file is one that `shared_at` units or more change. It notes a dependency on a finding no
unit holds.

The schedule reaches the target branch as a pull request the owner reads and merges: that merge is
the approval, and Part 1 ends there.

# Part 2: Running the schedule

## What can start

A unit may start when all of these hold:

1. every earlier unit that shares a file with it is merged, shared files aside (*Shared files*);
2. every unit it depends on is merged, and every earlier unit that holds a finding one of its own
    depends on;
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
    plan that another unmerged unit claims stops the unit until the schedule is corrected, unless it
    is a shared file. A shared file, or a file no other unit claims, is added to the unit's `files`.
3. **The pull request** opens as a draft, with the sweep label, a "Closes #n" line for each finding
    it fixes, and the unit's marker at the end of its description: `<!-- remediation CR1 U07 -->`.
4. **Ready for the owner** when all of these hold:
    - it has taken the target branch in, by a merge, since the last unit it shares a shared file
        with merged; a conflict in that file was the unit's to resolve, and the description says
        what was resolved;
    - CI is green, on that merge where there was one;
    - a `pr-review` pass has run on a different model from the one that did the work, and everything
        it raised is fixed or answered;
    - every finding of the unit is closed by the pull request, or set aside with `refine`,
        `question` or `dismiss`, and the description lists each one with its commit and its test;
    - the description opens with **Needs your eye**: only the commits that change what the user
        sees or what a requirement says, the small interface the sort left to the implementer
        among them.
5. **The owner merges**, every unit. After the merge: confirm and cleanup (the shared `CLAUDE.md` PR
    terms), then `next`.

**Where the merge stands.** Every update to the owner about a unit's pull request ends with it, as
the shared `CLAUDE.md` says (*PR updates*): "Merge waits on ...", naming what is still to come of
the list above, or "Merge is yours."

## What comes up mid-work

These are standing rules. None of them stops a unit to ask.

| What comes up | What the unit does |
|---|---|
| **A finding won't reproduce** | A tests-only commit shows the behaviour is right. The evidence goes on the issue, the finding gets `dismiss`, and it leaves the unit's "Closes" lines. The owner closes it, or says the point stands. |
| **The stated remedy is wrong, or an alternative fits better** | The implementer picks, and says so in the commit and on the issue, when the sort's rule would call the finding ready with what was picked (*Sort*, "Judged from the stated remedy"). Otherwise the finding gets `refine`. |
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
python3 <skill>/triage.py sorted [<file> ...] [--step <area>,...] [--sweep CR1] [--pad review/<N>]
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
- **`gather`** writes `findings.json`, and the same findings a step as `findings-<area>.json`.
- **`sorted`** reads the work pad's `triage/` folder: `findings.json`, every `sort-*.jsonl` and
    `check*.jsonl`, and `decided.jsonl` when there is one. With files named it checks their lines
    alone, and needs no sweep. With `--step` it holds those steps' findings alone to the whole
    check, each step named by its area or its issue's number, and writes nothing.
- **`check`** prints a note for what is worth a look and no problem: a file many units change that
    isn't listed as shared, and a dependency on a finding no unit holds.
- **`next`** says of a unit that can start which open units it shares a shared file with: it takes
    the target in as each merges.
- **`check --offline`** checks the schedule against its schema and itself, without GitHub.
- **Exit status**: 0 done; 1 the sort or the schedule has problems, a guard stopped, or a `gh` or
    `git` call failed; 2 refused (a bad config, schedule or argument).

`test_triage.py` runs it against a stub `gh` in a temp directory, so nothing reaches GitHub.

## Adopting this skill

A project adopts it once it has the `review` skill: it makes the `refine` and `dismiss` labels, sets
the fields above where the defaults don't fit, and may show the schedule on its own pages (the units
in order, each with its findings open and closed and its pull request).
