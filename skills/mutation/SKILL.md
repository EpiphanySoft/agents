---
name: mutation
description: Mutation testing and settling what it finds. Use when making, reading or checking a mutation baseline, when settling an area's surviving changes (alone or in a relay), when a pull request changes code a baseline ran, or when adopting this process in a project. Covers the outcomes, the runs, the baseline and its records, tests a run can't use, staleness, how each survivor is settled and who decides, "no tests", the area's report and when an area is done.
---

# Mutation testing

Coverage says a line ran. A mutation run says whether any test would notice if the line were
wrong: the tool makes one small change to the code at a time (a `<` for a `<=`, a constant
changed, a call dropped) and runs the tests that reach it. A change no test notices is a
**survivor**, a gap in what the tests state.

This skill is the process. Each project's own docs name its commands, where its records live, how
its code is split into **areas** (the units a hardening sweep works through), and the cases it
always settles one way. The examples here use mutmut, a Python tool; its words (a change's
*name*, *no tests*, `# pragma: no mutate`) stand for whatever the project's tool calls them.

## The outcomes

| Outcome | Meaning | What follows |
|---|---|---|
| killed | a test failed: the change is noticed | nothing |
| timeout | far slower than the unchanged tests, usually a loop the change made endless | counts as caught |
| survived | every test passed with the change | settled (below) |
| no tests | no test calls the function in the tests' own process, so none of its changes ran | work for the sweep (below) |
| not run | the job ended first (out of time, stopped) | run in a later round; a baseline has none |
| other | ended any other way (a crash, a tool error) | looked into, each one |

## Runs

- **Never in the checkout.** The tool rewrites the code it tests, so a run works in a copy, laid out
    like the repository so a path a test takes from the root reads the same.
- **Fresh each time.** A run builds a new map of which tests reach which function. A map reused from
    an earlier run never tries the tests added since.
- **Fast tests only.** Every test that reaches a function runs once per change to it, so slow suites
    stay out; a rule is pinned by a fast test.
- **One change by hand.** The project has a way to run one test file against one change, with the
    changed code imported ahead of the installed one (without that every change seems to survive).
    Use it to try a test just written before a whole run.
- **When.** The baseline is made once, before the sweep. An area's sweep runs its stale modules
    again before working from their survivors (see *Staleness*). The **settled run** comes at the end
    of the area's sweep, once its other tests are in: a full run of every module in the area, never a
    rerun of chosen changes, which records only those.
- **The tools' own trial.** A pull request that changes the mutation tooling or its workflow runs a
    trial on one small module, so the whole chain is checked before it merges.

## The baseline

Every area's first run, made on CI before the sweep, so each area starts with its survivors in hand.

**What it must be:**

- every module of every area, run on one source state: runs gathered together must have seen the
    same content for each module, and gathering refuses an area where two runs saw it differently;
- nothing left unrun: jobs that ran out of time are followed by rounds that run only what they left,
    until nothing is;
- named: the records give the runs, the commit and the tool's version.

**The first one.** A workflow started by hand can be started only once its file is on the default
branch, which the pull request adding it isn't yet. Two ways round that:

1. **Merge first.** Merge the tooling, then make the baseline in a second pull request.
2. **A fork's run.** On a throwaway branch of a fork, one extra commit, in no pull request, adds a
    temporary trigger. The records name the fork's run and a commit of the pull request with the same
    code under test, checked file by file. Where the project's public-text rules forbid the fork's
    name, the records say "a fork". The throwaway branch lives until the baseline's pull request
    merges and goes with its cleanup. Where the workflow's concurrency group is its ref, two runs at
    once need two branches.

**Again.** The whole baseline after a new major version of the tool, a changed test map or
runners, or most of the code stale. Part of it: always whole areas, since a record is written per
area from the runs given, and a run over part of an area would record that part alone.

## The records

Committed, one set per area, in a folder the project names:

- **`baseline-<area>.json`**: the outcomes in total and by file; each file's content (its git blob id)
    as the runs mutated it; the runs, commit and tool version; the dropped tests (empty once
    committed, see below).
- **`survivors/<area>.json`**: one survivor a line, in the module's order: its name, file, function,
    line, and the lines it removed and added. A job stopped before it wrote its diffs leaves names
    alone; gathering makes those diffs again from the tool's own changes to the checkout (no tests
    run), for modules still as the run saw them. A survivor with no line (its lines appear more than
    once in its function, or not at all) is found by its name.
- **`<area>.json`**, the settled record, written after the settled run: its outcomes and content, the
    pull request that settled the area, the issues it found and the equivalents it left.

The run's artifacts expire (90 days on GitHub); the committed records don't.

**Checks that read tracked text.** Survivor records quote code exactly, case-changed copies
included. A check that wants something written in one place only (an address, a constant) skips
the survivors folder, and only that folder. A check for private names or secrets never skips it.

## Tests a run can't use

Some tests fail only in the copy: they read a module's source (the copy holds the tool's rewrite),
ask git about a path the copy links, or start processes that inherit the tool's environment.

1. A run drops a test that fails in its copy automatically, so it never stops partway.
2. It proves each drop: the test runs once on the real tree. Failing there too, it is a real
    failure, and the run stops.
3. It keeps a short traceback for each drop and suggests an entry for the project's list of tests
    unfit for a mutation run, with a guess at the kind.
4. The agent that ran the tests resolves each suggestion; for a run on CI, the agent that commits
    its records. It either adds the test to the unfit list with its real reason, or changes the test
    so it no longer depends on the copy (reading the source from the real tree, say). It never
    deletes the test or weakens what it checks.
5. Its summary of the run lists every unfit-list addition and every test change, each with its
    reason, for the user to review.
6. A test keeps every committed record's dropped tests empty.

## Staleness

A record holds each module's content as it was mutated. A module whose content has changed since
its latest record (the baseline's, then the settled one's) is **stale**: its survivors' lines and
diffs no longer match it.

- The project has a command that names the stale modules. Wherever it shows its hardening (a
    page, a table), they are marked "baseline, changed since".
- Every step's pull request lists the modules it makes stale, or says none.
- A stale module runs again before anyone works from its survivors.
- A change to tests alone leaves the outcomes standing, unless it removes or weakens a test.

## Settling a survivor

Read every survivor, by function and line, and settle it one of three ways.

1. **A test.** Most survivors are a rule no test states, or test data that hides the change by
    giving the same answer either way. Write a fast test, with plain values where the code allows,
    named for the rule it pins, and data that tells the change apart: a value exactly on a bound, two
    parts of different sizes, a rounding remainder. One good test often kills several survivors that
    share a line or a cause.
2. **A change to the code.** A survivor on code that can't matter (a line never reached, a parameter
    never read, a guard that restates another) is a reason to remove the code, not to mark it. A
    survivor in a data shape nothing makes is a reason to make the shape impossible.
3. **A mark**, only where no output can differ, with the reason on the line above:

    ```python
    # Ids are unique, so the first four fields decide: no sort key changes the order.
    events.sort(key=lambda e: e[:4])  # pragma: no mutate
    ```

    mutmut honours a mark only at the end of a statement's first line, never inside brackets; a
    statement spread over lines takes `# pragma: no mutate start` and `# pragma: no mutate end`
    around it. A mark silences every change on its statement, the caught ones too: where its other
    changes are caught, leave it unmarked and list the survivor as an **equivalent** in the area's
    report. Code that runs only at import (a module constant, a class body's field built by a call)
    can't be changed in force, since the tool's workers start after the import: its result gets a
    test, and the code a mark saying so, the one mark for code whose output can differ.

A survivor that shows a wrong answer is a **bug**. It is filed the way the project's review process
files findings, gets a test that fails on the code as it was, and the settled record names its
issue.

## No tests

"No tests" is work for the sweep, and checked first: it may be the map missing a test that reaches
the code another way (through a server's API, or a process the test starts) rather than a real
gap. Each such function either gets a test that calls it in the tests' own process, after which its
changes run and are settled like any survivor, or is listed as reached only through a started
process, naming the test that reaches it.

## Who decides

- **Without asking:** a test that kills survivors and changes nothing the code does. The batch's or
    the area's mutation run proves it.
- **The user's, in the area's walk thru:** removing code, making a data shape impossible, a mark, a
    bug, an equivalent left unmarked, a test that would be slow, a function reached only through a
    started process. The agent lists each with its reason and changes nothing. In a relay the
    coordinator collects them across the batches, so each kind of question is asked once per area.

An area with more than about 200 survivors is settled in a relay (the `relay` skill). Its brief
carries this skill's rules, and its batch check is the mutation run on just the batch's names,
which must show every survivor it counts as killed as killed.

## The area's report, and done

The area's pull request carries:

- the outcomes by file, the baseline's and the settled run's;
- the survivors by function, with what was done about each;
- a table of what is done and what is left, nothing at the end;
- the equivalents left unmarked, each with why;
- the bugs, by issue;
- the modules it made stale, or none;
- every unfit-list addition and test change, from *Tests a run can't use*.

An area is **done** when its settled run (a full run of all its modules on the pull request's code)
leaves every survivor with a test, a change to the code, a mark or a listed equivalent, and its
settled record is committed with the area's work.

## Adopting this skill

- A project's own docs keep only what is its own: its commands, where its records live, its areas,
    and the cases it always settles one way. They link here for the rest rather than restating it.
- A project that already has a mutation process compares it with this skill first. Each place they
    disagree is a walk thru question for the user, and nothing changes until it is answered.
- A rule the project keeps on purpose is written in its docs as an **override**, with its reason.
