---
name: relay
description: Run a relay, where a coordinating session hands fixed batches of a large, uniform job to one agent at a time. Use when the user asks for a relay, or approves one for work too large for one session's context, such as hundreds of similar edits across a repository, citations rewritten in many files, or mutation-testing survivors settled in batches. Covers the brief, the batch files, the progress file, the checks after each batch and the final review.
---

# Relay

A relay is for work too large for one session's context: hundreds of similar edits across a
repository, done the same way everywhere. A clean session **coordinates**, and agents do the work
**one after another**, each on a fixed batch. The goal is the least total cost for consistent work:

- the ramp-up is paid as few times as possible;
- no agent runs close to its context limit, where late steps cost the most and slip first;
- the user's attention goes to the final diff only.

A relay runs only when the user asks for one for that piece of work. Choices that are the user's,
such as a walk thru's questions, stay with the coordinator, never an agent.

## The parts

All of the relay's files live in one temporary folder on the work branch, `docs/relay/` unless the
project says otherwise. The folder is deleted in its own commit before the pull request merges.

1. **The brief** (`brief.md`, from [`brief-template.md`](brief-template.md)): written once and given
    to every agent. It holds the goal, the rule to apply, how to find the batch's files, what an agent
    may and may not change, the checks to run before committing, and how to report.
2. **Fixed batches** (`batch-N.txt`, plus `batch-N.names` when a tool needs bare names): about 40
    files, one folder or about 100 items each, and never "as far as it can". No agent can see its own
    context, so a set size keeps every agent well inside it. The batch file's first lines say where its
    items came from (a run, a commit, a search) and which modules or folders they cover.
3. **Handoff through the branch**: each agent commits its batch to the work branch and appends its
    section to the progress file (`progress.md`, from [`progress-template.md`](progress-template.md)):
    the files it touched, its counts, the items it listed and why, and its doubts for the coordinator.
    The next agent reads the brief, the progress file and its own batch, never the earlier conversation.
    Agents commit but never push, never switch branches, and never amend or rebase.
4. **Mostly mechanical oversight**: after each batch, the coordinator
    - runs the checks that prove it: nothing left to change in those files, the linters and formatters,
        the touched tests run whole, and the batch's own check (the tool that found the items, run on
        just the batch's items);
    - skims a sample of the diff;
    - settles the agent's doubts, or carries them to the user, before the next batch starts;
    - then pushes.
5. **One full review** of the whole diff, by the coordinator, before the pull request opens or is
    marked ready.

## Running it

1. Plan the batches first, from the whole list of items: sizes even, items that share a file or a
    cause kept together, and the order chosen so later batches can build on earlier ones.
2. Write the brief and the batch files, commit them to the work branch, and give each agent only
    the brief's path and its batch number. Start one agent at a time.
3. When an agent reports, check its batch (step 4 above) before starting the next one. Fix a
    problem in the brief once, for every later batch, rather than in each agent's prompt.
4. Keep the counts in the progress file. The coordinator's own summary of the relay goes in the
    pull request body, where it outlives the folder.
5. Before the pull request merges, delete the relay folder in a commit of its own. Its history stays
    on the branch.

Leave no process running between batches: the machine is shared, and each agent must finish its own
background commands before it reports.

## Example: moving citations to new ids

A project renumbers its requirements, and every document that cites one must move to the new id.
Each batch is a list of files, each with the old ids it cites, and the map from old ids to new is
committed beside the brief. The rule gives every citation exactly one outcome, and the report counts
them:

| Outcome | What the agent does |
|---|---|
| moved | rewrites the citation to the id the map gives |
| ambiguous | the map gives several new ids and the text doesn't say which: lists it with the choices |
| gone | the map has no new id for it: lists it with the sentence around it, changes nothing |
| not a citation | the text only looks like an id (a version, a date): lists it, changes nothing |
| still left | anything the batch's check still finds, each with why |

The agent may change the batch's files only, and only their citations. The batch's check is the
project's citation checker on just those files, which must find no old id left except those listed.
Choices the map can't make, such as an ambiguous citation, go to the coordinator, never into the text.

These outcomes are an example. Each relay's brief sets its own rule and its own counts; a skill for
the kind of work, where there is one, supplies the rule.
