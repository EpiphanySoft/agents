# Hooks

Ensure both of these hold:

- The hooks in the adjacent `shared-hooks.json` are *merged* into ~/.claude/settings.json.
- `~/.claude/hooks/block-selfkill.sh`, which the `PreToolUse` hook in that file runs, exists. Link it to
    the adjacent `block-selfkill.sh` (`ln -s`) so there is one copy. The script needs `jq`.

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
7. If a round has multiple questions, number them and make a recommendation that can be
    unambiguously approved or discussed.
7.1. For example, if 4.2 had 4 questions, you would ask them like so:
```
Questions I have for you:
1. Words go here (Recommend: yes)
2. More words ... (Recommend: 42)
```
7.2. If a split is requested, these are the sub-items. Otherwise, each can be targeted
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

# Message timestamps

A hook in `~/.claude/settings.json` adds `Now (Chicago): Oct 29, 8:10 AM` after every prompt
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
