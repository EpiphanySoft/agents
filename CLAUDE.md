# Hooks

Ensure all of these hold:

Below, `$CLAUDE_CONFIG_DIR` is Claude Code's config folder: the value of that variable when it is set,
`~/.claude` otherwise.

- The hooks in the adjacent `shared-hooks.json` are *merged* into `$CLAUDE_CONFIG_DIR/settings.json`.
- `$CLAUDE_CONFIG_DIR/hooks/block-selfkill.sh`, which the `PreToolUse` hook in that file runs, exists. Link it to
    the adjacent `block-selfkill.sh` (`ln -s`) so there is one copy. The script needs `jq`.
- `$CLAUDE_CONFIG_DIR/skills/<name>` exists for each adjacent `skills/<name>` folder. Link it to that folder
    (`ln -s`) so there is one copy.

# Killing processes

- Never `pkill -f` / `killall` with a bare pattern: it matches this shell's own command line and kills the
    session or script running it.
- The `block-selfkill.sh` hook (see Hooks) blocks `pkill -f` with an unbracketed pattern, and `kill` aimed
    at `-1`, `0`, `$$` or `$PPID`. It does not catch `killall`, so that rule is yours to keep.
- Kill by PID or pidfile. Find the PID first (`pgrep -x name`, `lsof -ti :PORT`), look at it, then `kill PID`.
- If a pattern is unavoidable, bracket one character (`pkill -f '[f]oo'`) and never match your own script's name.

# Walk thru

A "walk thru" is how we go through a batch of decisions that need to be made, such as
review findings, design choices or questions:

1. One item at a time, in plain chat. Each item has the question, the options and what
    each one means, and the recommendation clearly called out so a response of "Ok" or
    "Agree" or "Approve" is never ambiguous. Alternatives are split out and never
    presented as optional parts of the recommendation.
1.1. A question with a choice of answers labels them A, B, C and so on, and names its
    recommendation by that letter. "Yes" is read as "Agree", so no answer's own wording
    starts with "Yes" or "No".
2. A counter on each item. Every item starts with "(X of Y)", where X is the item's
    place and Y is the number of items. It goes in the timestamp, like
    "Oct 31, 10:07 AM (1 of 3): ".
3. We discuss the item until approved by a decision. "OK", "Agree" or "Approve" are
    shorthand for accepting the recommendation for the current round. Then go to the next one.
3.1. When one answer is locked in, do not summarize that decision when moving on to the next
    item. Save it for the final summary.
4. A summary at the end. Once every item is decided, list all the decisions together
    and ask for final approval of the whole set.
5. A single item needs no summary round. Its one approval is enough.
6. If an item needs to be split, it gets subsection numbering. For example, a split of 4
    would produce 4.1, 4.2, 4.3, ... etc. A split of 4.2 would produce 4.2.1, 4.2.2, etc.
6.1. A split starts a sub-walk-thru on the split items, including a lock in for the split
    item at the end of the subitems.
6.2. For example, a split of 4 would walk thru its subitems 4.1, 4.2, and 4.3. At the end
    of 4.3, a summary and final lock in of item 4 is done, only then proceed to 5.
6.3. The numbering rule for a split would be "(4.2: 1 of 3)" which would cover 4.2.1,
    4.2.2, and 4.2.3
7. If a round has multiple questions, number them 1, 2, 3 and so on, and give each one a
    recommendation that can be unambiguously approved or discussed.
7.1. For example, if 4.2 had 3 questions, you would ask them like so:
```
Questions I have for you:
1. Words go here? (Recommend: B)
    A. One answer, and what it means
    B. Another answer, and what it means
2. More words ...? (Recommend: A)
    A. ...
    B. ...
    C. ...
3. A question with no list of answers? (Recommend: 42)
```
7.2. A reply gives each question's number and its answer's letter, like "1-A 2-C 3-42".
    "Agree" takes every recommendation.
7.3. If a split is requested, these are the sub-items. Otherwise, each can be targeted
    in a reply but don't move on until all questions are answered.

What not to do:
- No AskUserQuestion-style forms; use numbered questions as described here instead.
- No acting early. Nothing in the batch starts until the final approval, or the single
    item's approval when there's only one. Research is appropriate only as it relates to
    the walk thru, not doing the actual work, unless a question were asked to that effect.
    The key is that no code or document changes are started until the walk thru is complete.
- Don't combine previous or upcoming questions with the current question or the final summary;
    only ask one question at a time, don't recap each item as it is locked in, don't describe
    what is coming next unless it is relevant to answering the current question

When it's used:
- When you say "walk thru"
- For any batch of decisions that need to be made.
- When I come back after I tell you I will be away: Questions hit while I am gone get
    saved and opened as a walk thru on my return, so they don't block the work.

# Relay

A relay is a coordinating session handing fixed batches of a large, uniform job to one agent at a time.
The adjacent `skills/relay` skill describes how to run one.

- A relay runs only when I ask for one for that piece of work.
- Choices that are mine, such as a walk thru's questions, stay with the coordinator, never an agent.

# PR terms

"Confirm" and "cleanup" are what to do once a PR is merged; "confirm and cleanup" means both, in
that order. Squash is the only merge strategy, so a PR lands as one flat commit, and work branches
take the target in with merge commits (never a rebase) so line comments on their PRs aren't orphaned.

## Confirm

Check that the expected code (not commits) made it to the target branch.

- The target is the PR's base repository and branch (`gh pr view`), fetched fresh from the remote that
    points at that repository, whatever it is called locally; never a fork's copy, which can be stale.
- Look only at the PR's squash commit (`gh pr view --json mergeCommit`), ignoring anything merged after
    it, and compare changes, not files: the squash commit's diff from its parent must equal the branch's
    diff from the last target commit it took in.

```
            A   B   C   D   E   F   G
 master  ---o---o---o---o---o---o---o
             \           \         / (squash)
  work        o---o-------o-------/
              X   Y       Z (merge)
```

- The work branch started at A, made X and Y, and took in D with the merge Z. E and F landed on master
    after that, and the squash made G on top of F.
- G's diff from its parent (F to G) is only the branch's work: E and F were already in F.
- G's files do hold E and F, and Z's don't, so comparing the files of G and Z would show E and F as
    differences though the work landed intact. That's why the check compares diffs.
- The branch's diff runs from the last master commit it took in, D (`git merge-base Z F`), to its tip,
    Z. Confirmed when the two diffs match:
    `git diff F G | git patch-id --stable` equals `git diff D Z | git patch-id --stable`.
    When the branch was up to date at the squash (no E or F), the files of G and Z also match exactly.
- Any other difference: stop, report it (with the files), and ask before cleanup.

## Cleanup

Only after confirm passes, in this order:

1. Switch to the local target branch.
2. Fast-forward it from the target remote (`--ff-only`). If it can't fast-forward because it has commits
    of its own, stop and report: never merge or reset it.
3. Update the submodules (`git submodule update --init`).
4. Delete every copy of the PR's head branch: the local branch (`git branch -D`: after a squash git
    doesn't see it as merged; confirm is what makes the force safe), the branch on the remote the PR
    came from unless GitHub already deleted it, and any worktree checked out on it.
5. Fast-forward the fork's branch of the same name to the target by pushing it there (fast-forward
    only, no force), so nothing later reads a stale copy. If it can't fast-forward, stop and report.
    Skip this when there is no fork.
6. Clean up what the merged work left behind:
    - files made only for it: scratch scripts, stand-ins, probe output, logs;
    - the project's own temp-file cleanup script, if it has one;
    - background tasks, containers or VMs started for it that still run; shared ones follow the
        project's own rule.
    Never caches, images, VM disks, or anything shared or tracked by git. If unsure whether something
    belonged to the work or is still needed, ask.
7. Update memory and handoff notes that call the PR open or pending: merged, with its squash commit.
    Don't close or edit issues on GitHub; say which ones look ready to close.

# PR updates

Every update to me about an open PR ends with where its merge stands, as its last line:

- `Merge waits on ...`, naming each thing still in front of my pressing merge (a CI run, an answer
    from me, a fix, a sign-off), in the order it will happen, and ending with how long until only
    my merge is left and the time that is: `Merge waits on CI, then sign-off. ETA 1h 43m (3:30 PM)`.
    The time follows Message timestamps, without naming its zone. Time waiting on my answer isn't
    counted: the ETA then runs from my giving it (`ETA 25m after your answer`).
- `Merge is yours.` when nothing is left but my approving the PR and merging it.

With several PRs open, one line each, named by number.

# Message timestamps

A hook in `$CLAUDE_CONFIG_DIR/settings.json` adds `Now (Chicago): Oct 29, 8:10 AM` after every prompt
and every tool call.

- Start every message to me, progress notes included, with the time from the most recent of
those lines, copied verbatim, followed by `: `. For example, `Oct 29, 8:10 AM: `.
- Never type a time that isn't copied from that line or from a `date` run: no stamp carried
forward, added to, or guessed. If the line is missing, run
`TZ=America/Chicago date '+%b %-d, %-I:%M %p'` alone first.
- Every time you give me is Chicago time, never UTC. Convert others with `date`, whose flags
differ by platform. For example, `2026-11-04T20:28:00Z` (UTC) is `2:28 PM`:
- macOS (BSD `date`; no `-d`; write `Z` as `+0000`):
  `TZ=America/Chicago date -j -f '%Y-%m-%dT%H:%M:%S%z' '2026-11-04T20:28:00+0000' '+%-I:%M %p'`
  or from epoch seconds: `TZ=America/Chicago date -j -f '%s' 1793824080 '+%-I:%M %p'`
- Linux (GNU `date`): `TZ=America/Chicago date -d '2026-11-04T20:28:00Z' '+%-I:%M %p'`
- An estimate carries its distance from now: `around 10:40 AM (35 minutes from now)`.
- This prefix comes before any other prefix such as a walk thru sequence number. Prefixes
should be combined, space separated, prior to the `: ` separating prefixes from messages.
