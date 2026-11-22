# Filing a review: the records and the script

`file_review.py`, beside this file, files a review from two records the filing pass writes in the
work pad, and files the owner's questions while an unattended review runs. Its `pr` commands post a
pull request review's passes (the `pr-review` skill; see *A pull request: `pr`*), and `respond` the
author's answers (the `pr-respond` skill; see *The author's round: `respond`*). It parses no markdown: the unit files are read by the model pass, which writes the records.
Python 3 standard library and the `gh` CLI, signed in to an account that may create issues and
security advisories in the repository.

```
python3 <skill>/file_review.py dry-run [--config docs/review.json] [--pad review/<nnnn>]
python3 <skill>/file_review.py post    [--config docs/review.json] [--pad review/<nnnn>]
python3 <skill>/file_review.py question <question.json> [--config ...] [--pad ...]
python3 <skill>/file_review.py pr post <n> [--config ...] [--pad review/pr-<n>]
python3 <skill>/file_review.py pr file <n> (<id> ... | --all) [--config ...] [--pad ...]
python3 <skill>/file_review.py respond <n> [--config ...] [--pad review/pr-<n>]
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
ids of the claims flagged exploitable: `["U07-12", "U09-3"]`. The `question` command reads it, and the
dry run names any id in it whose finding isn't `exploitable`, so a lost mark is seen at the read. It,
not `findings.jsonl`, is what `question` reads, because questions come while the review runs, before
the filing pass writes `findings.jsonl`.

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
    is, and said so.
- **No copies.** Every body ends with a hidden marker naming the review and the item,
    `<!-- review CR1 U07-12 -->` (the summary's is `<!-- review CR1 summary -->`). Before it creates
    anything the state doesn't hold, `post` reads the repository's issues in every state (`gh issue
    list`) and its security advisories (`gh api`), once a run, and an item whose marker it finds there is
    recorded in the state as found, not posted again. So a run that stopped between making an item and
    recording it leaves no copy.
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

<!-- review CR1 U07-12 -->
```

## A question: `question`

Unattended, the coordinator files each question for the owner with `question`, from a JSON file it
writes (in the work pad or a scratch directory):

```json
{
  "question": "Is a value on the limit kept?",
  "options": [
    {"option": "Keep it", "means": "the limit is inclusive"},
    {"option": "Drop it", "means": "the limit is exclusive, as the code does"}
  ],
  "recommendation": "Keep it: R1.2 says up to and including.",
  "claim": "U07-12"
}
```

`question`, `options` (two or more, each with what it means) and `recommendation` are required;
`claim`, a work-pad id, is optional. The issue is titled "CR1 question: <the question's first line>",
written as a walk-thru item (the question, the numbered options, the recommendation, the claim), and
labelled with `question_label` and `labels`. Its title and body pass the text check first.

- **Private.** When `claim` is in `exploitable.json`, the question is appended to the work pad's
    `questions.md`, and the issue filed says only that a private question is waiting, with no content.
- **Not filed.** When the text check fails or `gh` does, the question is appended to `questions.md`
    with the reason, and the command exits 1. For a private question, the notice that couldn't be
    filed is noted there too.

Each entry in `questions.md` is headed by its title and says why it is kept there. The coordinator
logs every exit 1 in `log.md`.

## A pull request: `pr`

A pull request review's work pad is `review/pr-<n>/`, local and untracked. Each pass writes one
record, `pass-<k>.json`, numbered from 1 without a gap; the config is the same `docs/review.json`,
whose `name` the `pr` commands don't use. There is no dry run: the gates below are the check.

| Field | | What |
|---|---|---|
| `pr` | required | the pull request's number |
| `pass` | required | `k`, the file's own number |
| `head` | required | the full commit the pass read; the review's line comments are made on it |
| `base` | required | where the delta runs from: the merge base on pass 1, pass `k-1`'s `head` after |
| `skill_commit` | required | the shared skills' commit pinned on the target branch |
| `level` | required | `Standard`, `Plus` or `Premium` |
| `checking` | required | `checked`: a pass is always checked, and one marked `quick` is refused |
| `verdict` | required | one line |
| `read` | required | a list: what was read (sections, units, what was read whole) |
| `pieces` | required | `[{"piece", "model", "effort", "tokens"}]`, what each piece ran on |
| `findings` | required | the findings pinned to a changed line: the finding shape of `findings.jsonl`, with `area` optional, and `class` and `at` added |
| `additional` | required | the findings that can't be pinned to a changed line, of either class: the finding shape of `findings.jsonl`, with `class` added |
| `replies` | required | `[{"id", "status", "sha", "evidence"}]`, one per earlier finding on the diff re-checked: `status` `fixed` (with `sha`, the commit that fixed it) or `holds` |

`class` is `regression` (a bug the pull request introduces or makes worse, breakage in code it didn't
touch included) or `latent` (it is there at the merge base, and the pull request doesn't make it
worse). A line comment starts `[<class>] severity <severity>`, an entry of the review's *Additional
findings* list the same, and the body's counts are split by class and severity. An issue filed from
an additional finding keeps `severity <severity>` as its first line, with `class <class>` on the
next.

`at` is `{"file", "line", "start_line", "side"}`: the line of the diff at `head` the comment sits on,
`start_line` for a span, `side` `RIGHT` (the new code, the default) or `LEFT` (a removed line). A line
outside the diff makes GitHub refuse the whole review: the run stops, and the finding moves to a line
of the diff, or to `additional`. Ids are unique across the pull request's passes, such as `P2-3` for
pass 2's third.

**Exploitable.** A finding with `exploitable: true`, or whose id is in the work pad's
`exploitable.json`, is in no `gh` call of `pr post` or `pr file --all`: no comment, no count, no line
of the additional findings, no reply. Each run names the ids it kept back.

**Questions.** A finding with `question: true` is a plausible claim, a question for the owner: like
an exploitable one it is in no `gh` call of `pr post`, and `pr file` refuses it, `--all` included.
Each run names the ids it kept back. Once the owner says "post it", the next pass carries it as one
of its own findings, under a new id, with `decision`.

- **`pr post <n>`** posts the latest pass. It refuses records that don't hold together (a gap in the
    passes, a `base` that isn't the last `head`, an id used twice, a reply to anything but an earlier
    pass's finding on the diff, a `fixed` reply without its `sha`). It text-checks the review's body,
    every line comment and every reply, and posts nothing if any fails (exit 1). Then it posts one
    review, `POST repos/<repo>/pulls/<n>/reviews` with event `COMMENT`, its body the summary and each
    finding a line comment; then each reply on its finding's thread
    (`POST .../pulls/<n>/comments/<id>/replies`). A reply whose thread isn't found is refused before
    anything is posted.
- **`pr file <n> <id> ...`** files the additional findings the owner chose as issues, in the finding
    shape and labels of *The issue body* with its class, and a line saying which pass found it.
    `--all` takes every additional finding of the latest pass but the exploitable ones and the
    questions. An exploitable id, named on its own,
    is filed as a private draft security advisory, the way a full review files one. A finding on the
    diff is refused: it is on its line already. Every title and body is text-checked before anything
    is filed.
- **Markers.** The review's body ends `<!-- pr-review <n> pass <k> -->`, a line comment
    `<!-- pr-review <n> <id> -->`, a reply `<!-- pr-review <n> <id> reply <k> -->`, a filed issue or
    advisory `<!-- pr-review <n> <id> issue -->` or `... advisory -->`. What is posted is recorded in
    `pr-state.json` as it is made; before making anything the state doesn't hold, the script reads
    the pull request's reviews and comments (and, for `pr file`, the issues and advisories), and an
    item whose marker it finds is recorded as found, not posted again. So a run again after a stop
    posts only what is missing.
- **Only the project's people.** Of the pull request's reviews and comments, only those whose
    `author_association` is `OWNER`, `MEMBER` or `COLLABORATOR` are read for markers and threads; the
    others are counted, never read, so a marker someone else planted can't stop a post or take a
    reply.
- **Never** closes or edits anything, resolves a thread, approves or requests changes: the only
    calls that make something are the review with event `COMMENT`, the replies, the issues and the
    advisories.

## The author's round: `respond`

The author's side keeps its records in the same local work pad, `review/pr-<n>/`: one
`round-<k>.json` per round, numbered from 1 without a gap, and `respond-state.json`, what was posted.
`respond <n>` posts the latest round.

| Field | | What |
|---|---|---|
| `pr` | required | the pull request's number |
| `round` | required | `k`, the file's own number |
| `head` | required | the full commit the round ends at, pushed |
| `replies` | required | one per answered thread: `{"thread", "outcome", ...}` (below) |
| `answers` | required | answers to comments that have no thread: `{"to": "review" \| "comment", "id", "text"}`, a review's body or a comment in the conversation, by its id; posted in the round's comment |
| `changed` | required | `[{"sha", "what"}]`, the round's commits, one line each |
| `waiting` | required | a list: what waits on the owner |
| `unanswered` | required | a list: the comments not answered, by link and why (by someone outside the project, say) |

A reply's `thread` is the id of the review comment that starts it; its `outcome` sets the rest:

| `outcome` | Needs | The reply |
|---|---|---|
| `fixed` | `sha`, `how` (one line), `test` | "Fixed in <sha>: <how>" and "Proved by <test>." |
| `done` | `sha`, `text` | "Already done in <sha>: <text>" |
| `answer` | `text` | the answer |
| `waiting` | (`text`) | "Waiting on the owner's decision." |

`decision`, on any reply, opens it with "The owner decided: <decision>", for the round after a walk
thru. `owner_asked: true`, on a reply or an answer, lets it go to a comment by someone outside the
project, which is refused without it.

- **Only pushed commits.** Every `sha` in the round, and its `head`, must be the pull request's head on
    GitHub or one of its ancestors (`gh api repos/<repo>/compare/<sha>...<head>`); a round naming any
    other is refused before anything is posted.
- **Only the project's people.** Of the pull request's review comments, conversation comments and
    reviews, only those whose `author_association` is `OWNER`, `MEMBER` or `COLLABORATOR` are read;
    the others keep only their id, thread and link, and are counted ("left unread: 3 ...").
- **The gates.** Every reply and the round's comment are text-checked before anything is posted. Then
    each reply goes on its thread (`POST .../pulls/<n>/comments/<thread>/replies`), and the round's
    comment, last, on the pull request (`POST .../issues/<n>/comments`): what changed, the answers,
    what waits on the owner, what was not answered. A reply ends
    `<!-- pr-respond <n> thread <thread> round <k> -->`, the comment `<!-- pr-respond <n> round <k> -->`;
    as with `pr`, a run again records what it finds by its marker rather than posting it twice.
- **Never** closes, edits, resolves, approves or requests changes, marks the pull request ready or
    asks for a review: replies and the one comment are all it makes.

## Tests

`test_file_review.py` runs the script against a stub `gh` on `PATH` in a temp directory, so nothing
reaches GitHub: the dry run, a post, a run again after a partial post or after an item made but not
recorded, bad configs and records, a failing text check, the kind labels and exploitable marks, a
question filed, kept private, not filed and failing its text check, and that nothing is closed or
edited. For `pr`: a first pass, a run again after a partial post and after a review made but not
recorded, a second pass replying on threads, filing the chosen additional findings, the classes and their prefixes, a failing text
check, markers planted by others, refused records, that questions for the owner and exploitable
claims reach no `gh` call, and
that no forbidden call is made. For `respond`: a round's replies and its comment, a later round with
the owner's decision, a run again after a partial post and after a reply made but not recorded, a
commit not pushed, comments by others left unread and counted, a failing text check, refused records,
and that no forbidden call is made.

```
python3 skills/review/test_file_review.py
```
