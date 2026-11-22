# Filing a review: the records and the script

`file_review.py`, beside this file, files a review from two records the filing pass writes in the
work pad. It parses no markdown: the unit files are read by the model pass, which writes the records.
Python 3 standard library and the `gh` CLI, signed in to an account that may create issues and
security advisories in the repository.

```
python3 <skill>/file_review.py dry-run [--config docs/review.json] [--pad review/<nnnn>]
python3 <skill>/file_review.py post    [--config docs/review.json] [--pad review/<nnnn>]
```

Run from the repository's root. `<skill>` is this folder, wherever the project's pin of the shared
skills puts it. The work pad defaults to `review/<nnnn>` from the config's number.

## The config: `docs/review.json`

Checked against [`review-config.schema.json`](review-config.schema.json); the script refuses a config
that doesn't match, naming the field (`config.name.number: must be integer`).

| Field | | What |
|---|---|---|
| `repo` | required | `owner/name` |
| `name` | required | `{"prefix": "CR", "number": 1}`: the summary is "CR1: summary", the branch `code-review-0001`, the work pad `review/0001/` |
| `area_prefix` | required | the start of every area label, such as `area:` |
| `areas_command` | optional | a command printing the areas, one name a line, without the prefix; without it, the areas are the repository's labels that start with `area_prefix` |
| `labels` | optional | labels added to every finding's issue |
| `kind_prefix` | optional | when set, each finding also gets the label `<kind_prefix><kind>`, such as `kind:bug`; without it, the kind is in the body only |
| `question_label` | optional | default `question`: a finding that is a choice for the owner, and a question issue |
| `text_check` | optional | a command with `{file}`, run on every title and body before posting; a non-zero exit stops the post |
| `advisory_package` | optional | `{"ecosystem", "name"}` an advisory names; default `other` and the repository's name |

Commands are split into words as a shell would, with no shell features; wrap one in `sh -c '...'` to
use them. Every label must already exist in the repository: the script makes none.

## The findings: `findings.jsonl`

One JSON object a line, one line per surviving finding (confirmed, corrected, or, in a quick review,
made), in the map's order: Phase 1's, then the units', then the tooling unit's. Rejected claims, and
claims of a reading the owner rejected, are not in it.

| Field | | What |
|---|---|---|
| `id` | required | the work-pad id, `U07-12`; each once |
| `title` | required | one sentence, one line |
| `severity` | required | `High`, `Med` or `Low` |
| `kind` | required | the claim's kind |
| `area` | required | one of the project's areas, or `null` when no area owns it (see the skill's *Filing*) |
| `requirements` | required | the requirement ids, `[]` for untraced |
| `code` | required | `[{"file", "line", "quote"}]`, the quoted lines exactly; `[]` for a document claim |
| `what_goes_wrong` | required | the concrete case |
| `how_run` | required | the test or command and what it showed, or "Read only." |
| `remedy` | required | |
| `alternatives` | optional | a list |
| `decision` | optional | the agreed resolution, from `decisions.md` |
| `confirmations` | required | the count, 0 or more |
| `question` | optional | `true` when it is a choice for the owner: adds the question label |
| `exploitable` | optional | `true` when the review flagged it exploitable if public; default `false` |
| `advisory` | optional | `true` files it as a private draft security advisory instead of an issue; defaults to `exploitable`, and is set only where the owner changed a mark at the read |

**`exploitable.json`**, which the coordinator keeps in the work pad while the review runs, lists the
ids of the claims flagged exploitable: `["U07-12", "U09-3"]`. The dry run names any id in it whose
finding isn't `exploitable`, so a lost mark is seen at the read.

## The summary: `summary.json`

| Field | What |
|---|---|
| `commit` | the commit the review read |
| `base_commit` | the last review's commit the delta runs from, or `null` for a project's first review |
| `skill_commit` | the shared skills' commit the review followed |
| `branch_commit` | the review branch's commit that holds the finished claims |
| `scope` | `full` or `incremental` |
| `checking` | `checked`, `quick`, or `quick, checked later` |
| `how_it_ran` | the way the owner chose (one session, a relay, ...) |
| `models` | the level and any piece changed from it |
| `verdict` | one line |
| `matters_most` | a list: what matters most |
| `checked_and_sound` | a list: what was looked at closely and found right, so the next review need not repeat it |
| `where_things_stand` | a list: what was left unread or read lightly, and where to start |

## What the script does

- **`dry-run`** checks the config and both records, lists the areas, and writes
    `filing-dry-run.md`: every issue and advisory it would make, with its title, labels, parent (always
    none), exploitable mark and full body, the summary last with a placeholder for each link, and the plan's hash. It runs
    the text check on each, lists any failure at the top and exits 1. It posts nothing.
- **`post`** builds the plan again and refuses unless its hash matches the dry run's, so it posts
    exactly what the owner read. Then, in order: each finding not yet posted, after its text check; an
    issue through `gh issue create`, or an advisory through `gh api` (`POST
    repos/<repo>/security-advisories`, which makes it a draft); then the summary, with each finding's
    issue link, and only a count of the advisories. Each one is written to `filing-state.json` as soon
    as it is made.
- **Again after a stop.** A failed text check or `gh` call stops the run (exit 1) and keeps the state.
    Run `post` again and it skips what the state holds. A finding posted and changed since is left as it
    is, and said so. A stop between a post and its state line can leave one copy unrecorded: check the
    repository's newest issue before running again.
- **Never** closes or edits an issue.
- A bad config or record is refused (exit 2) before anything is posted.

## The issue body

```
severity Med

**Kind:** bug
**Requirements:** R1.2
**Confirmations:** 1
**Review:** CR1, work-pad id U07-12

**Code**  (each quoted place)
**What goes wrong**
**How it was run**
**Remedy**
**Alternatives**  (when there are any)
**Decision**  (when there is one)
```

## Tests

`test_file_review.py` runs the script against a stub `gh` on `PATH` in a temp directory, so nothing
reaches GitHub: the dry run, a post, a run again after a partial post, bad configs and records, a
failing text check, and that nothing is closed or edited.

```
python3 skills/review/test_file_review.py
```
