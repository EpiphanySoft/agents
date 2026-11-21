# Relay brief: <the work, in a few words>

Temporary: `docs/relay/` is deleted before PR #<n> merges. Read this whole brief, then
`docs/relay/progress.md`, then your batch file. Nothing else from earlier agents.

## Goal

<What the relay achieves and why, in a paragraph. Where the items came from (a run, a search,
a review) and how the batches are split: which batches cover which files or modules.>

Your batch is one file, `docs/relay/batch-N.txt` <and its bare names in `batch-N.names`>. Its
first lines name where its items came from. The code at the head of `<branch>` is the code
the items were taken from.

## The rule

<For each item, exactly one outcome, each with what the agent does and what it lists. Keep it
to the outcomes the counts below name.>

1. **<Outcome>**: <what to do>.
2. **<Outcome>**: <what to list, with one line saying why>.

<Hints that apply to many items, such as "one test per behaviour, not one per item".>

## What you may change

- **Only** <the files an agent may touch, such as the test files under `tests/`>. Never
    <what it may not touch>, not even for a moment to try something by hand.
- <Where a new piece goes: the existing file that covers it first, a new file only when none
    fits, and how it is named.>
- <The project's conventions that the work must keep: fixtures, speed, comment style, ids.>

## Checks before you commit (all must pass)

1. <The touched files' tests, run whole: the exact command.>
2. <Formatting and lint: the exact command. If it reformats, run 1 again.>
3. <The batch's own check, such as the tool that found the items run on just the batch's items:
    the exact command, how long it takes, and that it runs as a background command whose own
    completion is waited for, never by a loop that searches the process list.>

## Commit and report

1. Commit on `<branch>` (never push, never another branch, never amend or rebase), with only
    your files and `docs/relay/progress.md`. Message: <the project's style>, ending with the
    `Co-Authored-By:` line the branch's commits carry. Let git sign it; if signing fails, stop
    and report.
2. Append to `docs/relay/progress.md`, under `## Batch N`: the files you touched; the counts
    (<outcome>, <outcome>, …, still left); each listed item's name and its one line; then your
    doubts for the coordinator.
3. Your final message to the coordinator: the commit's hash, the counts and the doubts. Keep it
    short; the progress file holds the detail.

The machine is shared. Leave no process running when you finish.
