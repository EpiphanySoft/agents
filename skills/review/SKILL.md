---
name: review
description: Code review of a project against its requirements, and filing what it finds. Use when starting, proposing or running a review (Phase 0, the documents, the units, checking, the sweep), when filing a review's findings as issues and private advisories, when taking a finding up after a review, or when adopting this method in a project. Covers the choices, the branch and work pad, the pieces and their briefs, claim kinds, checking and confirmations, the owner's questions attended or unattended, models and effort, and the filing script.
---

# Code review

A review reads a project's requirements and other documents first, then its code area by area
against the sections that describe it. It answers three questions for each part of the code: are its
requirements built, does its code have requirements, and does the code do what they say. Along the
way it looks for bugs, most of all in what changed since the last review.

The method is built around one limit: no single session can hold the requirements, the documents and
the code at once. So the work is cut into **pieces** that each fit with room to think, every piece
writes what it finds to a file as it goes, and what passes between pieces is files, never a session's
memory.

A review ends at **findings with agreed resolutions**. It changes no requirement and no code; acting
on what it finds belongs to whatever follows (a sweep step, a fix pull request), under the project's
own process.

## What a project supplies

This skill is the method. Each project's own `docs/REVIEW.md` holds only what is its own, and points
here for the rest:

- **its requirements** with their ids, and how code cites them;
- **the Phase 1 blocks**: which documents are read together, and the glossary terms are checked
    against;
- **its areas**: the labels with a prefix, or a command that lists them, and the area for documents
    or tooling if it has one;
- **its sensitive code**: what keys, sign-in, secrets, links or money depend on, read whole whenever
    any of it changed;
- **its mechanical-check command** and what it reports;
- **its run and test commands** a claim may use to reproduce, and those a review never starts;
- **the time cap for an unattended run** of a command over a minute (10 minutes, say);
- **its settled records**: rejected ideas, and the labels for won't do, later and gap;
- **claim kinds of its own**, if any (a project that handles money may add one for wrong figures);
- **its target branch**, question label and labels, which must exist in the repository;
- **its filing config**, `docs/review.json` (see *Filing*).

## Before Phase 0: the method lands

The project's `docs/REVIEW.md`, its `docs/review.json` and the pin of the shared skills that carries
this skill are on the target branch at the review's commit. The summary issue records the skill's
commit. A fix to the method found during a review waits for the next review, unless the owner stops
the review to take it.

## The choices

A review makes three choices at Phase 0, and its summary issue records them.

1. **Scope.**
    - **Full**: all the code is read whole against its sections.
    - **Incremental**: the code changed since the last review's commit is read, with enough of what
        surrounds it to judge it. Sensitive code is read whole whenever any of it changed.
2. **Checking.**
    - **Checked**: every claim is checked by a second, independent context before it enters the
        review (*Checking*).
    - **Quick**: no second pass. Each claim enters at 0 confirmations and is confirmed before anyone
        acts on it.
3. **How it runs**: proposed by the coordinator and chosen by the owner (*How a review runs*).

**Recommending.** Phase 0 recommends scope and checking, and the owner confirms either way:

| Choice | Recommended when |
|---|---|
| Incremental | under about 25% of the code's lines changed, and no unit over about 50% |
| Full | anything more, the last review too old to build on, or a project's first review |
| Quick | a small delta, as triage or a look at one area |
| Checked | a release-readiness review, or any change to sensitive code |

Moves, renames and file splits count as changed: they have to be read again.

**A project's first review** is full, with no delta and no earlier findings in the briefs. Its second
blind discovery run covers only the listed sensitive code. Later reviews use the delta, and run the
second blind run on sensitive code and on code new since the last review.

**Severity**: **High** blocks the next release, **Med** is needed before it, **Low** can follow it.

## The branch and the work pad

| Where | What |
|---|---|
| `code-review-<nnnn>` | the review's branch, from the target at the review's commit; `<nnnn>` the review's number in four digits |
| `review/<nnnn>/` on it | the work pad: everything a session needs from earlier ones |
| issues and private advisories | the review's outcome, each standing on its own (*Filing*) |

**Local only.** The branch and work pad are never pushed and never merged: a fork may be public, and
unchecked claims must not publish before the owner's read. The branch is kept until the next review
has read it (its digests and rejected claims); the summary issue names the branch and its last
commit; after that it may be deleted locally.

**The commit.** A review reads one commit, recorded in `log.md` when Phase 0 starts. If something
merges to the target while it runs, the pieces still read the review's commit (`git show
<commit>:<path>`), and the delta runs to it.

**Read only.** A review changes nothing but its work pad. Nothing is fixed along the way, however
small: the review describes the commit it read.

**Commits.** The way the review runs decides who commits (in a relay, agents commit and the
coordinator checks). Each piece's work is committed before the next piece starts, and at the end.

| File | Written by | What |
|---|---|---|
| `log.md` | every session | one line a session: start and end (from `date`), the piece, its model and effort, what it wrote, what is left; failures as they happen |
| `checks.txt` | Phase 0 | the mechanical checks' report |
| `delta.txt` | Phase 0 | the change since the last review, per unit |
| `map.md` | Phase 0 | the units: sections, code paths, tests, lines |
| `docs-<block>.md` | Phase 1 | a block's claims and its claims digest |
| `docs-compare.md` | Phase 1 | the conflicts between the digests |
| `decisions.md` | the coordinator | each agreed resolution, after its walk thru's final approval |
| `unit-<nn>-<name>.md` | Phase 2 | a unit's brief, claims, verdicts and what was found while checking ([template](unit-template.md)) |
| `sweep.md` | the sweep | the verdicts on what was found while checking |
| `exploitable.json` | the coordinator | the ids of the claims flagged exploitable if public |
| `questions.md` | the coordinator | unattended: questions that could not be filed, and those that must stay private |
| `findings.jsonl`, `summary.json` | filing | the records the filing script reads ([filing.md](filing.md)) |
| `filing-dry-run.md`, `filing-state.json` | the script | the dry run the owner reads, and what was posted |

The ids in the work pad are its own: `D1-4` for the fourth claim of Phase 1's first block, `U07-12`
for unit 7's twelfth. A finding's lasting id is its issue's number, given when it is filed.

## A session's habits

1. **Start from the work pad.** Read `log.md`, the brief for the piece, and only the files it names.
    Never rely on another session's memory.
2. **Write as you go.** Each claim goes into the work pad when it is made, not at the end, so a long
    session that is summarised loses nothing.
3. **Read whole what you judge; search for the rest.** The sections and code a piece reviews are read
    whole. A search agent may locate callers or uses elsewhere, but its excerpts are never the
    evidence for a claim.
4. **Keep large output out of the conversation.** Test runs, diffs and listings go to a file in the
    work pad or a scratch directory, and only their summary is read.
5. **Every claim carries its evidence**: the file and line, the quoted lines of code or document, and
    the requirement id. Re-read the cited lines before writing the claim.
6. **The settled stays settled.** The project's settled records, open questions and a review's
    decisions are not raised again without a new reason, which the claim states.
7. **Run little.** A claim may be reproduced with one test or one command the project names.
    - **Attended**, anything that takes over a minute is asked first.
    - **Unattended**, it runs anyway, capped: one command the project names, in the background, within
        the machine's limits, under the project's time cap. Its start, PID and end go in `log.md`, and
        at the cap it is stopped by its own PID. A claim whose run hit the cap says so, and rests on
        reading.
8. **End with the log.** A session's last act is its line in `log.md` and its commit.
9. **Scratch stays out of the repository**, even for a moment.

## Phase 0: the checks, the map, the delta, the proposal

Phase 0 runs in the coordinating session, or its agent writes the proposal and the coordinator asks.

1. **The mechanical checks.** The project's command reports what needs no judgement (citations of
    missing ids, broken tables, stale references) into `checks.txt`, so no agent spends its context
    finding them by reading. What remains becomes Phase 1 claims.
2. **The map.** One session builds `map.md`: for each requirement section, the code that builds it,
    the tests that check it, and their sizes, starting from the code's citations and filling the rest
    from its layout and imports. It cuts the code into **units** of about 10,000 lines each:
    - a unit never crosses an area;
    - a big area is split by module or section into parts of the same area;
    - small areas are joined only when they share code;
    - code that cites no section and serves none is listed as **untraced**, with the unit it sits
        beside, whose session judges it;
    - units follow the project's own order (requirement order where the areas follow it), with the
        **tooling unit** last (*Phase 2*).
3. **The delta.** From the last review's commit to this one's, per unit, renames found:
    `git diff -M --numstat <last>..<commit> -- <unit's paths>`. Summed against each unit's lines, it
    gives the share changed that the choices are recommended from. A first review has none.
4. **The proposal.** Scope and checking; how the review runs; the models and effort for every piece;
    and, for a large review, whether it will run unattended, unless the owner has already said. The
    owner's answers go into `log.md`.

## Phase 1: the documents

One session per block, each reading its block whole. Each looks for:

- contradictions within the block;
- terms used other than the glossary defines them;
- behaviour named and never specified (a candidate gap);
- the same thing specified twice, differently;
- references to removed or renumbered items;
- the project's documented rules the documents break;
- what a mockup shows against what its sections say, from its text.

It turns `checks.txt`'s problems for its block into claims. Each block also writes a **claims
digest**: one line per fact another block could contradict, with its id. A fact is a term and what it
means, a limit or default, a state and what moves it, who may do what, and what is sent or stored
where. A further session reads only the digests and writes `docs-compare.md`: the conflicts between
blocks, each a claim with both ids. An incremental review reads only the sections changed since, and
compares their new digests with the last review's, read from its branch.

In a checked review, Phase 1's claims are checked like the units', each block's at the end of its
session.

## The gate

A High claim from Phase 1 that two documents disagree on behaviour the code will be checked against
is decided before the units that depend on it, in a walk thru (the shared `CLAUDE.md` rule). The
decision is the finding's agreed resolution: written to `decisions.md` after the walk thru's final
approval, given to the briefs that judge code against it, and carried onto the finding's issue at
filing. The requirements themselves are changed by whatever follows the review. A unit waits only
while such a claim touches its own sections; Med and Low claims hold nothing up. Unattended, a
decision lands once the owner answers its question issue.

## Phase 2: the units

One session per unit, in the map's order. Its brief is written at the top of its file before it
starts ([`unit-template.md`](unit-template.md)):

1. the unit's sections, code paths and tests, from `map.md`;
2. its delta, read first: recent changes are where the bugs are;
3. the earlier reviews' findings in its area, with their state, to re-check that what was marked
    done still holds;
4. the Phase 1 claims and `decisions.md` lines on its sections;
5. the untraced code the map gave it;
6. unattended, the open questions it hangs on.

The session reads its sections whole, then its code (whole in a full review; the delta and what
surrounds it in an incremental one), and writes a claim for each:

| Kind | The question |
|---|---|
| **not built** | an item of its sections that no code builds and no plan schedules |
| **untraced** | code that serves no requirement: dead, left over, or a requirement never written down |
| **differs** | the code does something other than what its requirement says |
| **security** | secrets, keys, transport, injection, a forged or replayed request |
| **privacy** | one user seeing or changing what isn't theirs |
| **bug** | a fault no requirement names: errors, races, a failure part-way, a resource left open |
| **test gap** | a requirement, or a fix from an earlier review, that no test holds |

A project may add kinds of its own. A claim has its id, kind, severity, requirement (`—` for
untraced), file and line with the quoted lines, what goes wrong as a concrete case where there is one,
the remedy, and alternatives where there are reasonable ones. It says how it was run, or that it rests
on reading alone.

**Exploitable if public.** The unit session flags any security or privacy claim that would be
exploitable if public, from the moment it is made, and the coordinator adds its id to the work pad's
`exploitable.json`. The checker may change the flag, as a correction. The flag keeps a question about
the claim private, and sets how it is filed (*Filing*).

**The second blind run.** Where the choices call for one, a second discovery run reads the same unit
from the same brief, blind to the first, on its own model. Its claims join the unit's file under their
own ids, and the checker judges both runs' claims.

**The tooling unit** comes after the code units: CI configuration, build and release scripts, test
tooling, read against the project's own docs for them. It takes the same brief, claim kinds and
checking, and is cut like any unit.

## Checking

In a checked review, when a unit's claims are written, one **checker** starts: a fresh context given
the claims file, the review's commit and this section, and nothing of the session's reasoning. For
each claim it reads the cited code and requirement for itself, looks for what would make the claim
false (a guard elsewhere, a caller that never passes the case, a reading of the requirement that
allows it), and gives one verdict:

| Verdict | Meaning |
|---|---|
| **confirmed** | the claim holds as written |
| **corrected** | it holds once its severity, scope, lines or remedy change, which the verdict gives; a claim may be split or two joined |
| **plausible** | the code does what the claim says, but whether that is wrong depends on how a requirement is read: it becomes a question |
| **rejected** | it does not hold, with the reason |

The checker writes what it noticed that no claim covers under **Found while checking**, unverified,
in the claim format. It never adds them to the claims: nothing enters the review on the word of the
context that found it. Rejected claims stay in the unit's file with their reasons, so the next review
doesn't raise them again without new evidence.

**The sweep.** After the last unit, one session checks everything found while checking, across all
units, the same way, and writes `sweep.md`. Each one it confirms goes to the unit it belongs to.

## Confirmations and status

A claim's **confirmations** count the independent contexts that found it holds:

- **0** when it is made;
- **+1** for each confirmation by an agent or session that did not make it and has not confirmed it
    before, by a test that reproduces it, or by the owner;
- a **corrected** verdict counts as a confirmation of the corrected claim;
- **plausible** adds nothing: the claim is a question until it is answered;
- **rejected** drops it.

A filed finding's **status** is its issue's: open; open with the question label, a choice for the
owner; closed as completed, by the pull request that fixed it; closed as not planned, by the owner,
with the reason. Confirmations and decisions after filing are comments on its issue.

## The owner's questions

- **Attended.** The coordinating session asks every question, in a walk thru (the shared `CLAUDE.md`
    rule). Agents may draft a recommendation; a piece that hits an owner question reports it and never
    decides it.
- **Unattended.** Every question is filed as an issue with the project's question label, written as a
    walk-thru item (the question, the options, the recommendation), and walked thru on the owner's
    return. `file_review.py question` files it ([filing.md](filing.md)), after the text check.
- **No unit waits.** A unit whose judgement hangs on an open question reviews under each reading and
    tags its claims with the question. Once the owner decides, the rejected reading's claims are
    dropped, recorded as rejected with the decision as the reason.
- **Kept private.** A question about a claim that would be exploitable if public (its id is in
    `exploitable.json`) is never filed publicly: `question` keeps it in `questions.md`, and the issue it
    files says only that one is waiting, without its content.
- **Through the dry run.** Unattended, the review runs through the filing dry run; only posting waits
    for the owner's read.
- **Failures don't halt it.** Unattended, a failure is an exception to the standing rule to stop when
    signing or pushing fails; its other half, never working around it, still holds. A commit that can't
    be signed stays uncommitted in the work pad (never unsigned, never another identity). A question
    that can't be filed, or fails the text check, is written to `questions.md` by `question`. Each failure is logged in `log.md` as it
    happens, and the report on the owner's return opens with them.

## How a review runs

The skill doesn't fix it. At Phase 0 the coordinator proposes the ways a large review could run and
recommends one:

| Way | What it buys |
|---|---|
| **one session** | the least overhead; fits a small review only |
| **a relay** (the `relay` skill) | each piece in a fresh context, one at a time; consistent, and checked between pieces |
| **parallel sub-agents** | the same pieces, several at once: less wall time, more of the machine |
| **a workflow** | one script runs the agents: the least of the owner's attention, cut by phase since it resumes only from the session that started it |
| **anything else that fits** | whatever the proposal says it buys |

Each option carries its estimated relative cost (tokens, wall time) and what it buys: control of each
context's size, speed, consistency, and how much of the owner's attention it takes. The owner's choice
is the ask the relay and workflow rules require, and the chosen way follows its own rules. A small
review may simply run in one session.

Whatever the way, the pieces are the same: the briefs, the work-pad files, the rule that only an
independent context confirms a claim, and the filing. Where pieces run at once: Phase 1's blocks
together, the comparison after all of them; units several at a time, within the project's machine
limits; a checker per claim rather than per unit; the sweep split by unit.

**Starting a piece.** Each piece starts with a short prompt naming the review, its branch, the piece
and this skill; the previous piece leaves the next brief written:

```
Code review CR4 (review/0004/ on the local code-review-0004 branch), with the review skill:
run unit 07 (Phase 2, then Checking), on <model> at <effort>. Start from log.md and the unit's brief.
```

## Models and effort

Each piece runs on a named model and a named effort level, never a tool's default: defaults differ
between tools and change with releases. The Phase 0 proposal names them for every piece, with the
estimated tokens by model and a next-equivalent total (each model's tokens weighted by its price
relative to the next level's model), and `log.md` records what each piece ran on.

- Discovery never runs below high effort.
- Checking runs on a different model from discovery's, so they don't share blind spots. A severity
    the checker raises is a correction like any other.
- Two blind discovery runs find more than either alone.
- Reading prose may use a cheaper model at high effort.

Three levels, by role: **strongest**, **next**, **cheaper**. The proposal names today's models for
each.

| Piece | Standard | Plus | Premium |
|---|---|---|---|
| Coordinating, Phase 0 | next, high | next, high | strongest, high |
| Reading prose (Phase 1) | cheaper, high | cheaper, high | cheaper, high |
| Discovery | next, high | strongest, high | strongest, high |
| Second blind run: sensitive units | cheaper, high | cheaper, high | cheaper, xhigh |
| Second blind run: other units | none | none | cheaper, high |
| Checking and the sweep | cheaper, high | cheaper, high | next, high |
| Filing (dry run): the script, and a model pass writing the issue texts, the summary and the exploitable marks | next, high | next, high | next, high |

Recommend **Standard** by default, **Plus** when a review covers much sensitive or never-reviewed code
(a project's first review, say). **Premium** is the owner's call. Any piece can be adjusted in the
proposal.

## Filing

Filing places nothing into plans. Each finding is its own issue:

- **a title** of one sentence; a finding that needs more is two findings;
- **a body** that starts `severity High`, `severity Med` or `severity Low` and holds everything: kind,
    requirements, the quoted code, what goes wrong, how it was run, remedy, alternatives, and its
    agreed resolution if it has one. Nothing it needs is left in the work pad;
- **one area label** from the project's areas: that of the first code it names, else its section's.
    A finding no code area owns gets the project's documents or tooling area if it has one, else none;
- **a kind label**, `<kind_prefix><kind>`, when the project's config sets `kind_prefix`; without it,
    the kind is in the body only;
- **the question label** when it is a choice for the owner.

A **summary issue**, "<prefix><n>: summary", lists every finding by link (a list, not sub-issues, so
the one-parent slot stays free for planning) and records: the commit read and the last review's
commit; the skill's commit; the branch and its last commit; the three choices; the models; the
verdict in one line; what matters most; *checked and sound* (what was looked at closely and found
right, so the next review need not repeat it); and *where things stand* (what was left unread or read
lightly, and where to start). Steps, sub-issues under steps and project-board fields belong to the
project's planning, not the review.

**Exploitable findings.** A finding flagged exploitable if public (a security or privacy flaw)
is filed as a private draft security advisory instead of a public issue. The dry run shows each
finding's mark, and the owner confirms or changes each one at the read. The summary gives only their
count.

**The script.** `file_review.py`, in this folder, files a review from `findings.jsonl` and
`summary.json` in the work pad and the project's `docs/review.json` ([filing.md](filing.md)):

1. The filing pass (a model, see *Models and effort*) writes the two records from the work pad:
    every surviving claim, its issue text, its area, its exploitable mark, and the summary.
2. `file_review.py dry-run` writes every issue and advisory it would make to `filing-dry-run.md` and
    posts nothing. The owner reads it.
3. `file_review.py post` posts exactly what the dry run showed, text-checking each body first,
    and can be run again after a stop: a hidden marker in each body lets it find what an earlier run
    posted, so it never posts a copy.

A bug found by mutation testing (the `mutation` skill) is filed as a finding in the same shape, with
its area's label.

## After the review

The skill ends at agreed resolutions. What it keeps:

1. **Confirm before acting.** A claim at 0 confirmations is not fixed, decided or written into the
    requirements until someone confirms it: a test that reproduces it, or a reading of the code and
    requirement that doesn't lean on the claim. Whoever takes it up does this first, and it adds one.
2. **Walk thru** the plausible claims and the ones that need a choice (the shared `CLAUDE.md` rule).
    Each decision goes into `decisions.md` once the walk thru's final approval is given.
3. **Each confirmation or decision goes on its issue** as a comment. The only edit to a body after
    filing is a severity the owner changed in a walk thru, written as part of carrying out that
    decision.
4. **A quick review can be checked later**: a checking pass over its claims raises their
    confirmations, and its summary then reads "quick, checked later".
5. **A recommendation nobody takes up** gets an id in the project's gaps, questions or later work, so
    it isn't lost when the next review starts.

**Issues are the owner's to close.** Agents never close an issue unless the owner explicitly asks,
for that review. A pull request's "Closes #n" on the owner's merge is fine. Agents comment:
confirmations, decisions, "PR #n opened", "merged as <sha>". A page that would read "pull request" or
"done by" from an issue's body reads the linked pull request instead. Closing isn't part of cleanup
(the shared `CLAUDE.md` PR terms).

Acting on a finding (the pull request that fixes it, code citing requirements, a fix cycle's own
hardening) is the project's own process. Mutation testing is the `mutation` skill's.

## Adopting this skill

- A project's docs keep only their own commands, names and cases, and point here for the method.
- Each place a project's current review process differs from this skill is a walk-thru question for
    the owner, and nothing changes until it is answered.
- A rule the project keeps on purpose is written in its docs as an **override**, with its reason.
