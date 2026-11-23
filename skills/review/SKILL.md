---
name: review
description: "Code review of a project against its requirements, and reporting what it finds. Use when starting, proposing or running a review (its stages: Prerequisites, Planning, Doc Review, Doc Rulings, Initial Code Review, Confirmation, Cross-check, Reporting, Finalization), when filing a review's findings as issues and private advisories, when taking a finding up after a review, or when adopting this method in a project. Covers the choices, the branch and work pad, the sweep and its anchor, the pieces and their briefs, claim kinds, confirmation and confirmations, the owner's questions attended or unattended, models and effort, refusals and model changes, and the filing script."
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

A review runs in stages, in this order: **Prerequisites**, **Planning**, **Doc Review**, **Doc
Rulings**, **Initial Code Review**, **Confirmation**, **Cross-check**, **Reporting** and
**Finalization**.

A review ends at **findings with agreed resolutions**. It changes no requirement and no code; acting
on what it finds belongs to whatever follows (a sweep step, a fix pull request), under the project's
own process.

## What a project supplies

This skill is the method. Each project's own `docs/REVIEW.md` holds only what is its own, and points
here for the rest:

- **its requirements** with their ids, and how code cites them;
- **the document groups**: which documents are read together, and the glossary terms are
    checked against;
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
- **its filing config**, `docs/review.json` (see *Reporting*).

## Prerequisites

The project's `docs/REVIEW.md`, its `docs/review.json` and the pin of the shared skills that carries
this skill are on the target branch at the review's commit. They are checked first, by Planning,
which stops before making anything if one is missing: `plan` checks the two files, and the
coordinator checks the pin. The summary records the skill's commit. A fix to the method found during a review waits for the next review, unless the owner stops
the review to take it.

## The choices

A review makes three choices at Planning, and its summary records them.

1. **Scope.**
    - **Full**: all the code is read whole against its sections.
    - **Incremental**: the code changed since the last review's commit is read, with enough of what
        surrounds it to judge it. Sensitive code is read whole whenever any of it changed.
2. **Checking.**
    - **Checked**: every claim is checked by a second, independent context before it enters the
        review (*Confirmation*).
    - **Quick**: no second pass. Each claim enters at 0 confirmations and is confirmed before anyone
        acts on it.
3. **How it runs**: proposed by the coordinator and chosen by the owner (*How a review runs*).

**Recommending.** Planning recommends scope and checking, and the owner confirms either way:

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
| `code-review-<N>` | the review's branch, from the target at the review's commit; `<N>` the review's number, from its sweep (`code-review-1` for CR1) |
| `review/<N>/` on it | the work pad: everything a session needs from earlier ones |
| the sweep: its label, its anchor issue and the steps under it | made by Planning |
| issues under the steps, and private advisories | the review's outcome, each standing on its own (*Reporting*) |

**Local only.** The branch and work pad are never pushed and never merged: a fork may be public, and
unchecked claims must not publish before the owner's read. The branch is kept until the next review
has read it (its digests and rejected claims); the summary names the branch and its last
commit; after that it may be deleted locally.

**The commit.** A review reads one commit, recorded in `log.md` when Planning starts. If something
merges to the target while it runs, the pieces still read the review's commit (`git show
<commit>:<path>`), and the delta runs to it.

**Read only.** A review changes nothing but its work pad. Nothing is fixed along the way, however
small: the review describes the commit it read.

**Commits.** The way the review runs decides who commits (in a relay, agents commit and the
coordinator checks). Each piece's work is committed before the next piece starts, and at the end.

| File | Written by | What |
|---|---|---|
| `log.md` | every session | one line a session: start and end (from `date`), the piece, the model it ran on and its effort, what it wrote, what is left; failures as they happen, a refusal or a model change among them |
| `checks.txt` | Planning | the mechanical checks' report |
| `delta.txt` | Planning | the change since the last review, per unit |
| `map.md` | Planning | the units: sections, code paths, tests, lines |
| `docs-<group>.md` | Doc Review | a document group's claims and its claims digest |
| `docs-compare.md` | Doc Review | the conflicts between the digests |
| `decisions.md` | the coordinator | each agreed resolution, after its walk thru's final approval |
| `unit-<nn>-<name>.md` | Initial Code Review | a unit's brief, claims, verdicts and what was found while checking ([template](unit-template.md)) |
| `cross-check.md` | Cross-check | the verdicts on what was found while checking |
| `exploitable.json` | the coordinator | the ids of the claims flagged exploitable if public |
| `questions.md` | the coordinator | unattended: questions that could not be filed, and those that must stay private |
| `findings.jsonl`, `summary.json` | Reporting | the records the filing script reads ([filing.md](filing.md)) |
| `filing-dry-run.md`, `filing-state.json` | the script | the dry run the owner reads, and what was filed and attached |

The ids in the work pad are its own: `D1-4` for the fourth claim of Doc Review's first document group, `U07-12`
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

## Planning: the sweep, the checks, the map, the delta, the proposal

Planning runs in the coordinating session, or its agent writes the proposal and the coordinator asks.

The start of a review is the start of its **sweep**: the plan of the work its findings make. One
name, `<prefix><N>` (`CR1`, the prefix from the project's config, `CR` by default), runs through all
of it: the sweep label `sweep:CR1`, the anchor, the step ids `CR1.1`, the markers, the branch
`code-review-1` and the work pad `review/1/`.

1. **The sweep**, the coordinator's, before the review's branch exists, on the target branch at the
    review's commit: `file_review.py plan --dry-run`, then `file_review.py plan`
    ([filing.md](filing.md)). It checks the *Prerequisites* first and makes nothing if one is missing. `N` is one
    more than the highest among the `sweep:<prefix><N>` labels, or 1. It makes the label
    `sweep:<prefix><N>` (and stops if it exists already); the **anchor**, an issue titled "CR1 Code
    review" with the sweep label and no area label, which is the review's own step: its summary and
    the questions about the review go there; and one **step** per area, in the areas' order, as the
    anchor's sub-issues: `CR1.<n> <area>`, with the area's label and the sweep label. So an area has
    one step, and there are three levels: the anchor, its steps, their findings. (A step with more
    findings than a parent takes is cut into parts at Reporting; they are still one step.) A plan that stopped
    part-way is finished by running it again (`plan --sweep CR1`, as its stop says), never repeated.
    The coordinator then makes the branch `code-review-<N>` from the target. A later piece finds its review from its branch, or from
    an explicit `--sweep CR1`; nothing about the sweep is kept in the work pad or the config.
2. **The mechanical checks.** The project's command reports what needs no judgement (citations of
    missing ids, broken tables, stale references) into `checks.txt`, so no agent spends its context
    finding them by reading. What remains becomes Doc Review claims.
3. **The map.** One session builds `map.md`: for each requirement section, the code that builds it,
    the tests that check it, and their sizes, starting from the code's citations and filling the rest
    from its layout and imports. It cuts the code into **units** of about 10,000 lines each:
    - a unit never crosses an area;
    - a big area is split by module or section into parts of the same area;
    - small areas are joined only when they share code;
    - code that cites no section and serves none is listed as **untraced**, with the unit it sits
        beside, whose session judges it;
    - units follow the project's own order (requirement order where the areas follow it), with the
        **tooling unit** last (*Initial Code Review*).
4. **The delta.** From the last review's commit to this one's, per unit, renames found:
    `git diff -M --numstat <last>..<commit> -- <unit's paths>`. Summed against each unit's lines, it
    gives the share changed that the choices are recommended from. A first review has none.
5. **The proposal.** Scope and checking; how the review runs; the models and effort for every piece;
    and, for a large review, whether it will run unattended, unless the owner has already said. The
    owner's answers go into `log.md`.

## Doc Review

One session per document group, each reading its group whole. Each looks for:

- contradictions within the group;
- terms used other than the glossary defines them;
- behaviour named and never specified (a candidate gap);
- the same thing specified twice, differently;
- references to removed or renumbered items;
- the project's documented rules the documents break;
- what a mockup shows against what its sections say, from its text.

It turns `checks.txt`'s problems for its group into claims. Each group also writes a **claims
digest**: one line per fact another group could contradict, with its id. A fact is a term and what it
means, a limit or default, a state and what moves it, who may do what, and what is sent or stored
where. A further session reads only the digests and writes `docs-compare.md`: the conflicts between
groups, each a claim with both ids. An incremental review reads only the sections changed since, and
compares their new digests with the last review's, read from its branch.

In a checked review, Confirmation runs on Doc Review's claims too, each group's at the end of its
session.

## Doc Rulings

A High claim from Doc Review that two documents disagree on behaviour the code will be checked
against is decided before the units that depend on it, in a walk thru (the shared `CLAUDE.md` rule).
The decision is the finding's agreed resolution: written to `decisions.md` after the walk thru's
final approval, given to the briefs that judge code against it, and carried onto the finding's issue
at Reporting. The requirements themselves are changed by whatever follows the review. Unattended, a
decision lands once the owner answers its question issue.

Doc Rulings holds up only the units its conflicts touch, and only for High conflicts (Med and Low
hold nothing up); it is skipped when there are none; and a ruling is recorded like any other
decision, in `decisions.md`, and carried onto the finding's issue as its agreed resolution.

## Initial Code Review

One session per unit, in the map's order. Its brief is written at the top of its file before it
starts ([`unit-template.md`](unit-template.md)):

1. the unit's sections, code paths and tests, from `map.md`;
2. its delta, read first: recent changes are where the bugs are;
3. the earlier reviews' findings in its area, with their state, to re-check that what was marked
    done still holds;
4. the Doc Review claims and `decisions.md` lines on its sections;
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
the claim private, and sets how it is filed (*Reporting*).

**The second blind run.** Where the choices call for one, a second discovery run reads the same unit
from the same brief, blind to the first, on its own model. Its claims join the unit's file under their
own ids, and the checker judges both runs' claims.

**The tooling unit** comes after the code units: CI configuration, build and release scripts, test
tooling, read against the project's own docs for them. It takes the same brief, claim kinds and
checking, and is cut like any unit.

## Confirmation

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

Confirmation also runs after Doc Review, in a checked review, on each document group's claims, the
same way.

## Cross-check

After the last unit, one session checks everything found while checking, across all units, the same
way as Confirmation, and writes `cross-check.md`. Each one it confirms goes to the unit it belongs
to.

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
    return. It is labelled and placed like the claim that raised it: the sweep label and the claim's
    area label, a sub-issue of that area's step, titled like a finding (`CR1.1-3 Question: ...`; its
    body and marker name the review). A question about the review itself (Planning's, say) goes under
    the anchor.
    `file_review.py question` files it ([filing.md](filing.md)), after the text check.
- **No unit waits.** A unit whose judgement hangs on an open question reviews under each reading and
    tags its claims with the question. Once the owner decides, the rejected reading's claims are
    dropped, recorded as rejected with the decision as the reason.
- **Kept private.** A question about a claim that would be exploitable if public (its id is in
    `exploitable.json`) is never filed publicly: `question` keeps it in `questions.md`, and the issue it
    files says only that one is waiting, without its content or its area, under the anchor.
- **Through the dry run.** Unattended, the review runs through Reporting's dry run; only posting waits
    for the owner's read.
- **Failures don't halt it.** Unattended, a failure is an exception to the standing rule to stop when
    signing or pushing fails; its other half, never working around it, still holds. A commit that can't
    be signed stays uncommitted in the work pad (never unsigned, never another identity). A question
    that can't be filed, finds no parent, or fails the text check, is written to `questions.md` by
    `question`. A refusal, or a piece carried on by another model, is a failure too, handled as
    *Refusals and model changes* says. Each failure is logged in `log.md` as it happens, and the
    report on the owner's return opens with them.

## How a review runs

The skill doesn't fix it. At Planning the coordinator proposes the ways a large review could run and
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
independent context confirms a claim, and Reporting. Where pieces run at once: Doc Review's groups
together, the comparison after all of them; units several at a time, within the project's machine
limits; a checker per claim rather than per unit; Cross-check split by unit.

**Starting a piece.** Each piece starts with a short prompt naming the review, its branch, the piece
and this skill; the previous piece leaves the next brief written:

```
Code review CR4 (review/4/ on the local code-review-4 branch), with the review skill:
run unit 07 (Initial Code Review, then Confirmation), on <model> at <effort>. Start from log.md and the unit's brief.
```

## Models and effort

Each piece runs on a named model and a named effort level, never a tool's default: defaults differ
between tools and change with releases. The Planning proposal names them for every piece, with the
estimated tokens by model and a next-equivalent total (each model's tokens weighted by its price
relative to the next level's model), and `log.md` records what each piece ran on, read from the
tool's record of the piece (*Refusals and model changes*).

- Discovery never runs below high effort.
- A checker never runs on the model that made what it checks, so they don't share blind spots:
    Confirmation's model differs from that of the discovery run, the second blind run or the Doc Review
    group whose claims it checks, and Cross-check's from that of the checker that found each item. A
    severity the checker raises is a correction like any other.
- Two blind discovery runs find more than either alone.
- Reading prose may use a cheaper model at high effort.

Three levels, by role: **strongest**, **next**, **cheaper**. The proposal names today's models for
each.

| Piece | Standard | Plus | Premium |
|---|---|---|---|
| Coordinating, Planning | next, high | next, high | strongest, high |
| Reading prose (Doc Review) | cheaper, high | cheaper, high | cheaper, high |
| Discovery | next, high | strongest, high | strongest, high |
| Second blind run: sensitive units | cheaper, high | cheaper, high | cheaper, xhigh |
| Second blind run: other units | none | none | cheaper, high |
| Confirmation: discovery's claims | cheaper, high | cheaper, high | next, high |
| Confirmation: claims made on cheaper (Doc Review, the second blind run) | next, high | next, high | next, high |
| Cross-check: what a checker on cheaper found | next, high | next, high | next, high |
| Cross-check: what a checker on next found | cheaper, high | cheaper, high | cheaper, high |
| Reporting (dry run): the script, and a model pass writing the issue texts, the summary and the exploitable marks | next, high | next, high | next, high |

Recommend **Standard** by default, **Plus** when a review covers much sensitive or never-reviewed code
(a project's first review, say). **Premium** is the owner's call. Any piece can be adjusted in the
proposal.

## Refusals and model changes

A model can refuse a request, most often on security work: a sandbox escape, a forged request, a
secret. A tool may then carry the piece on with another model without saying so. Each breaks
something the method rests on: a piece that stopped early has not read what its brief names, a piece
on a lesser model is not the piece the owner approved, and a checker that fell onto the model that
made its claims shares their blind spots.

**Check each piece as it ends**, before its work is taken and before another piece starts from it:

1. **Read what it ran on from the tool's own record**, never from what the piece says of itself.
    `piece_models.py`, in this folder, reads Claude Code's sub-agent transcripts:
    `python3 <skill>/piece_models.py --models <the proposal's model ids> <the session's subagents folder>`.
    It names every piece that was refused, changed model, or ran on a model the proposal doesn't
    name. It exits 2 when it could read nothing, which is a failure, never a clean run. A
    coordinating session checks its own transcript the same way, at the end of each stage. With
    another tool, read the same three facts from its record.
2. **Log it as a failure, as it happens**: the piece, the time, the model that refused, the model
    that took over, how much of the piece that model ran, and what the piece was reading.

**What it means for the work:**

- **A checker on the wrong model.** The rule that a checker never runs on the model that made what
    it checks is applied to the model that ran. A verdict given after a change onto the claims' own
    model counts nothing, and those claims are checked again.
- **A piece on a model below its level.** What it wrote after the change is done again on the named
    model. The one exception is a result that rests on evidence the piece saved (a run's output, a
    screenshot, quoted lines): a context on the named model or a stronger one reads that evidence
    and gives the result, and the log says so.
- **A piece that stopped, or skipped part of its brief.** What it didn't cover is listed from its
    file against its brief, and asked again as below.
- **Nothing is taken as it stands.** A piece's work enters the review only once this is settled.

**Asking again.** A review reads the owner's own code to find what is wrong and say how to fix it.
A brief that says so plainly is refused less often than one that reads as a request to attack
something. In this order:

1. **Say what the work is.** The brief states at its top that this is a review of the owner's own
    project, asked for by the owner, that it changes nothing, that its findings go to the owner to
    be fixed, and that anything it runs is run in the project's own test environment.
2. **Ask for the fault and the fix, not the attack.** A claim needs what is wrong, where, the case
    that shows it and the remedy. It needs no working exploit, no payload and no steps against a
    real system. A reproduction is the smallest test that fails, in the project's test environment.
3. **Cut the piece smaller.** The part that was refused runs as a piece of its own, with only its
    sections and code, so the rest of the unit isn't lost with it.
4. **Keep other claims' detail out of the brief.** A brief names earlier claims by id and file. It
    doesn't carry their exploit descriptions, or a list of everything exploitable, into a context
    that doesn't need them.
5. **Try the named model once more**, with the brief so changed. If it refuses again, the piece runs
    on the stand-in the proposal names (below), still within the checker rule, and the log says so.
6. **Still refused: it is left unread, and said so.** The part goes in the summary's *where things
    stand* as not reviewed, with the reason. Attended, the coordinator asks the owner first.

A review never rewords a request to hide what it is, never splits it so that no part shows its
purpose, and never tells the model it is doing something else. Work that can't be asked for plainly
is not done by the review. Leaving a piece on whatever model the tool fell to is not an answer
either.

**In the proposal.** Where refusals are likely (sandboxing, keys, sign-in, whatever the project
lists as sensitive), the proposal names the stand-in for each level: the model a piece runs on when
its named model has refused twice, of the same level or stronger where there is one, and never the
claims' own model for a checker. Where the tool lets its fallback model be set or switched off, the
proposal says which, so that no change is silent.

**Unattended**, there is nobody to ask. The coordinator checks each piece as it ends, asks again by
the steps above, uses the stand-in, and leaves unread what is still refused. The report on the
owner's return opens with every refusal and model change, among its failures: what was refused, what
was done about it, and what is still unread.

## Reporting

Reporting makes no steps: Planning made them. Each finding is its own issue, a sub-issue of
its area's step:

- **a title** of one sentence, `<step id>-<m> <sentence>` (`CR1.3-2 A value on the limit is
    dropped.`): the step id leads its parent's title (`CR1` for the anchor), and `m` is one more than the highest among that
    parent's sub-issues in any state, so a number is never used twice. A parent whose title has no
    leading id gives the plain sentence. A finding that needs more is two findings;
- **a body** that starts `severity High`, `severity Med` or `severity Low` and holds everything: kind,
    requirements, the quoted code, what goes wrong, how it was run, remedy, alternatives, and its
    agreed resolution if it has one. Nothing it needs is left in the work pad;
- **one area label** from the project's areas: that of the first code it names, else its section's.
    A finding no code area owns gets the project's documents or tooling area if it has one, else none;
- **the sweep label**;
- **a kind label**, `<kind_prefix><kind>`, when the project's config sets `kind_prefix`; without it,
    the kind is in the body only;
- **the question label** when it is a choice for the owner;
- **a parent**: the one open sub-issue of the sweep's anchor that carries its area label and is no
    finding (no finding's marker in its body). The anchor is the one open issue with the sweep label,
    no parent and no finding's marker. A finding with no area goes under the anchor. No match, or two
    or more that are not one step's parts, and the dry run fails naming the area and the issues.

**A step in parts.** A parent takes 100 sub-issues, GitHub's limit, so an area with more findings
than its step has room for needs the step cut into parts. The dry run fails for each finding with
no room and names the command, `file_review.py split <area> <parts>`. The coordinator runs it (with
`--dry-run` first): it makes the missing parts under the anchor, each after the part before it,
and titles them all alike but for their ends, "CR1.11 docs (1 of 2)", "CR1.11 docs (2 of 2)". The
parts are one step: they share its id, one run of numbers crosses them, and findings fill the first
and go on in the next. Then the dry run again. This is the one case in which Reporting makes a
parent, and the one edit the script makes, the parts' titles. A question or a pull request's
finding that meets a full step is told the same command.

**The summary** is a comment on the anchor, posted last. It lists every finding by link
and records: the commit read and the last review's commit; the skill's commit; the branch and its last
commit; the three choices; the models each piece ran on, with any refusal or model change; the
verdict in one line; what matters most; *checked and sound*
(what was looked at closely and found right, so the next review need not repeat it); and *where things
stand* (what was left unread or read lightly, and where to start). Project boards are neither read
nor written.

**Exploitable findings.** A finding flagged exploitable if public (a security or privacy flaw)
is filed as a private draft security advisory instead of a public issue. An advisory can't be a
sub-issue: its title is the plain sentence, with no parent and no number. The dry run shows each
finding's mark, and the owner confirms or changes each one at the read. The summary gives only their
count.

**The script.** `file_review.py`, in this folder, plans the sweep (`plan`, *Planning*) and files a
review from `findings.jsonl` and `summary.json` in the work pad and the project's `docs/review.json`
([filing.md](filing.md)):

1. The filing pass (a model, see *Models and effort*) writes the two records from the work pad:
    every surviving claim, its issue text, its area, its exploitable mark, and the summary.
2. `file_review.py dry-run` writes every issue and advisory it would make, with its parent and its
    numbered title, to `filing-dry-run.md` and posts nothing. When it names a split (*A step in
    parts*), that is run and the dry run made again. The owner reads it.
3. `file_review.py post` posts exactly what the dry run showed: it finds each parent and number
    again and refuses if one changed, then files each finding, text-checked first, and attaches it
    under its parent. It can be run again after a stop: its state records each filing and each
    attach, and a hidden marker in each body and in the summary lets it find what an earlier run
    posted, so it does only what is missing and never posts a copy.

**Through a pull request.** A pull request for a sweep's issues carries the sweep label. A bug found
by mutation testing (the `mutation` skill), and an additional finding a pull request review files
(`pr file`), follow a sweep only through such a pull request: its sweep label, the same parent search
and the same title rule. Outside one, the issue has no sweep label, no parent and a plain title. The
script's `pr` commands post a pull request review's passes (the `pr-review` skill), and `respond` the
author's answers on it (the `pr-respond` skill), with the same text check and markers.

## Finalization

The skill ends at agreed resolutions. **Confirm before acting** is a standing rule, not a step: a
claim at 0 confirmations is not fixed, decided or written into the requirements until someone
confirms it, by a test that reproduces it or a reading of the code and requirement that doesn't lean
on the claim. Whoever takes it up does this first, and it adds one. The steps:

1. **Walk thru** the plausible claims and the ones that need a choice (the shared `CLAUDE.md` rule).
    Each decision goes into `decisions.md` once the walk thru's final approval is given.
2. **Each confirmation or decision goes on its issue** as a comment. The only edit to a body after
    filing is a severity the owner changed in a walk thru, written as part of carrying out that
    decision.
3. **A quick review can be checked later**: a Confirmation pass over its claims raises their
    confirmations, and its summary then reads "quick, checked later".
4. **A recommendation nobody takes up** gets an id in the project's gaps, questions or later work, so
    it isn't lost when the next review starts.

**Issues are the owner's to close.** Agents never close an issue unless the owner explicitly asks,
for that review. **"Closes #n" is the link to a fix**: a pull request that fixes a finding names it
so, and needs no other line in its body for it; its close on the owner's merge is fine. A pull
request for a sweep's issues carries the sweep label. Agents comment: confirmations, decisions,
"PR #n opened" (for people reading the issue), "merged as <sha>". A page that would read "pull request" or
"done by" from an issue's body reads the linked pull request instead. Closing isn't part of cleanup
(the shared `CLAUDE.md` PR terms).

Acting on a finding (the pull request that fixes it, code citing requirements, a fix cycle's own
hardening) is the project's own process. Mutation testing is the `mutation` skill's.

## Adopting this skill

- A project's docs keep only their own commands, names and cases, and point here for the method.
- Each place a project's current review process differs from this skill is a walk-thru question for
    the owner, and nothing changes until it is answered.
- A rule the project keeps on purpose is written in its docs as an **override**, with its reason.
