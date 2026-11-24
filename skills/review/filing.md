# Reporting: the records and the script

`file_review.py`, beside this file, lays out a review's sweep (Planning, `plan`), cuts a step that
is full into parts (`split`), files the review from two records the filing pass writes in the work pad, and files the owner's questions while
an unattended review runs. Its `pr` commands post a pull request review's passes (the `pr-review`
skill; see *A pull request: `pr`*), and `respond` the author's answers (the `pr-respond` skill; see
*The author's round: `respond`*). It parses no markdown: the unit files are read by the model pass,
which writes the records. Python 3 standard library and the `gh` CLI, signed in to an account that
may create labels, issues and security advisories in the repository.

```
python3 <skill>/file_review.py plan [--dry-run] [--sweep CR1] [--config docs/review.json]
python3 <skill>/file_review.py split <area> <parts> [--dry-run] [--sweep CR1] [--config ...]
python3 <skill>/file_review.py dry-run [--sweep CR1] [--config docs/review.json] [--pad review/<N>]
python3 <skill>/file_review.py post    [--sweep CR1] [--config docs/review.json] [--pad review/<N>]
python3 <skill>/file_review.py question <question.json> [--sweep CR1] [--config ...] [--pad ...]
python3 <skill>/file_review.py pr post <n> [--config ...] [--pad review/pr-<n>]
python3 <skill>/file_review.py pr file <n> (<id> ... | --all) [--config ...] [--pad ...]
python3 <skill>/file_review.py respond <n> [--config ...] [--pad review/pr-<n>]
```

Run from the repository's root. `<skill>` is this folder, wherever the project's pin of the shared
skills puts it.

**Which review.** A review is named `<prefix><N>`, `CR1`: the prefix is the config's, and `N` its
sweep's. `split`, `dry-run`, `post` and `question` take it from `--sweep CR1`, else from the branch
they run on, `code-review-<N>`, and refuse when there is neither. The work pad defaults to `review/<N>`.
Nothing about the sweep is kept in the work pad or the config: the sweep is its label and its issues.

## The config: `docs/review.json`

Checked against [`review-config.schema.json`](review-config.schema.json); the script refuses a config
that doesn't match, naming the field (`config.prefix: must be string`).

| Field | | What |
|---|---|---|
| `repo` | required | `owner/name` |
| `prefix` | optional | default `CR`, letters only: the start of every review's name, `CR1`, whose number comes from its sweep |
| `area_prefix` | required | the start of every area label, such as `area:` |
| `areas_command` | optional | a command printing the areas, one name a line, without the prefix, in their order; without it, the areas are the repository's labels that start with `area_prefix`, sorted by name |
| `labels` | optional | labels added to every issue the script makes: the anchor, the steps, the findings and the questions |
| `kind_prefix` | optional | when set, each finding also gets the label `<kind_prefix><kind>`, such as `kind:bug`; without it, the kind is in the body only |
| `question_label` | optional | default `question`: a question issue |
| `refine_label` | optional | default `refine`: a finding that is a choice for the owner, until the owner decides |
| `dismiss_label` | optional | default `dismiss`: a finding the work showed to be no defect (the `review-triage` skill) |
| `schedule`, `unit_size`, `open_units`, `shared_at` | optional | the work schedule's path and limits, read by the `review-triage` skill's `triage.py` |
| `text_check` | optional | a command with `{file}`, run on every title and body before posting; a non-zero exit stops the post |
| `advisory_package` | optional | `{"ecosystem", "name"}` an advisory names; default `other` and the repository's name |

Commands are split into words as a shell would, with no shell features; wrap one in `sh -c '...'` to
use them. Every label must already exist in the repository: the script makes none but the sweep's,
in `plan`.

## Planning: `plan`

Planning's first step, the coordinator's, before the review's branch exists. The coordinator runs it
on the target branch at the review's commit, having checked for itself that the pin of the shared
skills there carries this skill (the script can't tell which pin does). `plan --dry-run` prints what
it would make and makes nothing; `plan` makes it:

1. **The prerequisites.** Before anything else, both `plan` and `plan --dry-run` refuse (exit 2),
    making and reading nothing on GitHub, unless `docs/REVIEW.md` and the config file (`--config`,
    `docs/review.json` by default) are tracked in the commit they run on, `HEAD`: a file on disk
    that isn't committed doesn't count.
2. **The sweep.** `N` is one more than the highest among the repository's `sweep:<prefix><N>`
    labels, or 1, and `plan` makes the label `sweep:<prefix><N>` (`gh label create`). A label that
    exists already when it is made stops the run. When the highest label's sweep has no anchor yet (a
    plan that stopped after making its label), `plan` finishes that one instead of starting another.
3. **The anchor**: an issue titled `<prefix><N> Code review` ("CR1 Code review"), labelled with the
    sweep label and `labels`, no area label, its body listing the steps and ending
    `<!-- review CR1 anchor -->`. It is the review's own step: the summary is a comment on it, and a
    question about the review, a private question's notice and a finding with no area go under it.
4. **The steps**: one per area, in the areas' order (`areas_command`'s, else the area labels sorted
    by name), titled `<prefix><N>.<n> <area>` ("CR1.1 core"), labelled with the area's label, the
    sweep label and `labels`, each ending `<!-- review CR1 step <area> -->`, and each made a sub-issue
    of the anchor.

Every title and body it would make passes the text check before anything is made; a failure makes
nothing (exit 1). Each item is found again by its marker (`gh issue list`, every state) and a step
already among the anchor's sub-issues isn't attached again, so a run after a stop makes only what is
missing: `plan --sweep CR1` finishes CR1, as the stop's message says. `--sweep` names only the sweep
that exists or the next one. It prints the branch and work pad the review then uses.

## A step in parts: `split`

A parent takes 100 sub-issues and no more (GitHub's limit), so the step of an area with more
findings than that is cut into **parts**. The parts are one step: they share its id and its area,
and one run of numbers crosses them. `split <area> <parts>` gives the area's step that many parts,
2 or more:

1. **The parts** are found by their markers, in every state: the first is the step Planning made
    (`<!-- review CR1 step <area> -->`), and part `k` ends `<!-- review CR1 part <k> <area> -->`.
2. **Each missing part** is made: titled like the step, labelled like it (the area's label, the
    sweep label and `labels`), and made a sub-issue of the anchor.
3. **Its place.** Each part after the first is moved to directly follow the part before it among
    the anchor's sub-issues (`PATCH repos/<repo>/issues/<anchor>/sub_issues/priority`), so the
    anchor lists a step's parts together, ahead of the next area's step.
4. **The titles.** Every part is titled the step's title and its place, `<title> (<k> of <parts>)`:
    "CR1.11 docs (1 of 2)", "CR1.11 docs (2 of 2)". This retitling (`gh issue edit --title`) is the
    one edit the script ever makes.

Every title and body passes the text check before anything is made, and `--dry-run` says what it
would make and retitle. Run again with the same number it makes only what is missing, as the stop's
message says; with a higher one it adds parts and retitles them all; a lower one is refused, since
a part is never removed. Between a part's attach and the last retitle the two issues are not yet
one step's parts, and the parent search fails until the split is finished.

`dry-run` names the split to run: a finding with no room has no parent, and its line gives the
command with the number of parts that makes room for every finding of the plan.

## The findings: `findings.jsonl`

One JSON object a line, one line per surviving finding (confirmed, corrected, or, in a quick review,
made), in the map's order: Doc Review's, then the units', then the tooling unit's. Rejected claims, and
claims of a reading the owner rejected, are not in it.

| Field | | What |
|---|---|---|
| `id` | required | the work-pad id, `U07-12`; each once |
| `title` | required | one sentence, one line |
| `severity` | required | `High`, `Med` or `Low` |
| `kind` | required | the claim's kind |
| `area` | required | one of the project's areas, or `null` when no area owns it (see the skill's *Reporting*) |
| `requirements` | required | the requirement ids, `[]` for untraced |
| `code` | required | `[{"file", "line", "quote"}]`, the quoted lines exactly; `[]` for a document claim |
| `what_goes_wrong` | required | the concrete case |
| `how_run` | required | the test or command and what it showed, or "Read only." |
| `remedy` | required | |
| `alternatives` | optional | a list |
| `decision` | optional | the agreed resolution, from `decisions.md` |
| `confirmations` | required | the count, 0 or more |
| `question` | optional | `true` when it is a choice for the owner: adds the refine label |
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
| `models` | the level, any piece changed from it, and any refusal or model change (the model that ran, and what was done about it) |
| `verdict` | one line |
| `matters_most` | a list: what matters most |
| `checked_and_sound` | a list: what was looked at closely and found right, so the next review need not repeat it |
| `where_things_stand` | a list: what was left unread or read lightly, and where to start |

## Parents and titles

- **The anchor** is the one open issue with the sweep label, no parent and no marker of a finding,
    a step or a part, found through GraphQL (`repository.issues(states: OPEN, labels: [<sweep label>])`, with each
    one's `parent`), once a run. A finding's marker is a review's `<!-- review <name> <id> -->`
    (a question's included) or a pull request review's `<!-- pr-review <n> <id> issue -->`; the
    anchor's and the steps' markers are not. None, or two or more, and the command is refused naming
    them: Planning makes the anchor.
- **The parent search.** A finding's parent is the one open sub-issue of the anchor that carries the
    finding's area label and is no finding. A finding with no area goes under the anchor. No match,
    or two or more that are not one step's parts, and the search fails naming the area and the
    issues. Reporting never makes a parent.
- **A step in parts.** Two or more such sub-issues are one step's parts when their titles are alike
    but for their ends, "(1 of 2)", "(2 of 2)", each place taken once (*A step in parts: `split`*).
    The parent is then the part that holds the item already, found by its marker among the parts'
    sub-issues, else the first part with room for one more of its 100, what the run has placed
    there counted. So findings fill the first part and go on in the next, and a run after a stop
    places each one where the run before did. No room in any part, or under the anchor, and the
    search fails naming the split that makes it; the anchor is never split.
- **The title rule.** A finding's title is `<step id>-<m> <sentence>`. The step id is the leading id
    of the parent's title: the sweep's own name (`CR1` of the anchor's "CR1 Code review") or the
    name and `.<n>` (`CR1.3` of "CR1.3 core"), at the start, followed by a space or the end. Any
    other title ("Fix2 things", another sweep's "CR2.3 core") has no id. `m` is one more than the
    highest `<step id>-<m>` among the titles of the parent's sub-issues and of those of the step's
    other parts, in every state (`GET repos/<repo>/issues/<parent>/sub_issues`), so a number is
    never used twice. Findings of one step take the next numbers in the plan's order. A parent whose title has no leading id
    gives the plain sentence. A sub-issue with the marker of an item being filed is left out of the
    count, so a run again after a stop gives the same numbers.
- **Attaching.** `POST repos/<repo>/issues/<parent>/sub_issues` with `sub_issue_id`, the issue's
    database id (`gh api repos/<repo>/issues/<n> --jq .id`). An issue already among the parent's
    sub-issues is recorded, not attached again.
- **Advisories** can't be sub-issues: a plain title, no parent, no number.

## What the script does

- **`dry-run`** checks the config and both records, finds the anchor, lists the areas, and writes
    `filing-dry-run.md`: every issue and advisory it would make, with its title, labels, parent (the
    issue and its title, or why the search failed), exploitable mark and full body, the summary last with a
    placeholder for each link, the plan's hash, and the records' hash. It runs the text check on each.
    A failed parent search or text check is listed at the top and against its item, and the dry run
    exits 1. It posts nothing.
- **`post`** builds the plan again: it refuses a plan whose parent search fails, and unless both
    hashes match the dry run's, so it posts exactly what the owner read; a parent or a number that
    changed in the repository since is named as such. Then, in order, each finding not yet done: an
    issue through `gh issue create`, after its text check, then its attach under its parent; or an
    advisory through `gh api` (`POST repos/<repo>/security-advisories`, which makes it a draft).
    Last, the summary, with each finding's issue link and only a count of the advisories: a comment on
    the anchor (`POST repos/<repo>/issues/<anchor>/comments`). Each filing and each attach is written
    to `filing-state.json` as soon as it is made.
- **Again after a stop.** A failed text check or `gh` call stops the run (exit 1) and keeps the state.
    Run `post` again and it does only what the state doesn't hold: a finding filed but not attached is
    only attached. A finding posted and changed since is left as it is, and said so.
- **No copies.** Every body ends with a hidden marker naming the review and the item,
    `<!-- review CR1 U07-12 -->` (the summary's is `<!-- review CR1 summary -->`). Before it creates
    anything the state doesn't hold, `post` reads the repository's issues in every state (`gh issue
    list`) and its security advisories (`gh api`), once a run, and an item whose marker it finds there is
    recorded in the state as found, not posted again. For the summary comment it reads the anchor's
    comments, only those whose `author_association` is `OWNER`, `MEMBER` or `COLLABORATOR`, so a
    marker someone else planted can't stop it. So a run that stopped between making an item and
    recording it leaves no copy.
- **Never** closes an issue, edits one but to retitle a step's parts in `split`, makes a parent
    outside `plan` and `split`, or reads or writes a project board.
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
  "claim": "U07-12",
  "area": "core"
}
```

`question`, `options` (two or more, each with what it means), `recommendation` and `area` are
required; `claim`, a work-pad id, is optional. `area` is the claim's area, or `null` for a question
about the review itself (Planning's, say). The issue is written as a walk-thru item (the question, the
numbered options, the recommendation, the claim), labelled with `question_label`, `labels`, the sweep
label and the area's label, and filed under the area's step by the parent search, as a finding is;
a question with `area` `null` goes under the anchor. Its title follows the title rule,
"CR1.1-3 Question: <the question's first line>" ("CR1-2 Question: ..." under the anchor), and its
body names the review and ends with its marker, `<!-- review CR1 question-<hash> -->`, the hash
taken from the question's file. It is filed, then attached. Its title and body pass the text check
first. Run again with the same file, `question` finds the issue by its marker and only attaches it if
it isn't yet.

- **Private.** When `claim` is in `exploitable.json`, the question is appended to the work pad's
    `questions.md`, and the issue filed says only that a private question is waiting, with no content
    and no area label, under the anchor: its area would say where to look.
- **Not filed.** When the parent search, the text check or `gh` fails, the question is appended to
    `questions.md` with the reason, and the command exits 1. A question filed but not attached is
    kept there too, with its link and its parent; `question` run again attaches it. For a private
    question, the notice that couldn't be filed is noted there too.

What becomes of a question issue once the owner answers is the skill's (*The owner's questions*,
"Once answered"): the coordinator closes it, or removes its label and retitles it; the script
doesn't.

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
| `pieces` | required | `[{"piece", "model", "effort", "tokens"}]`, what each piece ran on: the model that ran, read from the tool's record, not the one it was named |
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
    **The sweep only through the pull request:** it reads the pull request's labels
    (`gh api repos/<repo>/issues/<n>`), and when one is a sweep label each issue takes that label,
    the parent search under that sweep's anchor and the title rule of *Parents and titles*, and is
    filed, then attached, both recorded in `pr-state.json`. A pull request with no sweep label gives a plain title, no sweep
    label and no parent; one with two is refused. A failed parent search is refused before anything
    is filed.
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
question filed under its area's step or the anchor, kept private, not filed, with no parent, filed
but not attached and attached on a run again, and failing its text check, and that nothing is closed
or edited. For the sweep: the review named by its branch or `--sweep`, and refused with neither; the
one anchor, none and two refused; the one step found past issues of another sweep, closed, not under
the anchor or with a finding's marker; none and several failing the dry run, naming them; the
numbers from the parent's sub-issues in any state, and the plain title of a parent with no leading
id; a finding with no area under the anchor; post refusing a parent or a number changed since the
dry run; a stop between filing and attaching, and an attach made but not recorded; and the summary
comment posted once across runs, a planted marker ignored.

For `plan`: the dry run making nothing; the label, the anchor and the steps under it, and the review
filing under them; the next number after the highest label; a label made by someone else meanwhile
stopping it; a plan that stopped after its label, or between a step and its attach, finished by a
run again without a copy; the steps in `areas_command`'s order; a failing text check making nothing;
and refused names.

For `split`: a step with no room failing the dry run and naming the split, with the parts that
make room for every finding; the anchor never split; the dry run making nothing; the part made,
placed after the first and both retitled, with the title the only edit; a step split again into
more parts, and fewer refused; a split that stopped at each of its steps finished by a run again
without a copy; a failing text check making nothing; findings filling the first part and going on
in the next with one run of numbers, a later question after them; a post that stopped part-way
giving the same plan and going on in the same parts; and a question for a full step kept, naming
the split.

For `pr`: a first pass, a run again after a partial post and after a review made but not recorded, a
second pass replying on threads, filing the chosen additional findings, the classes and their
prefixes, a failing text check, markers planted by others, refused records, that questions for the
owner and exploitable claims reach no `gh` call, `pr file` following the pull request's sweep label
(plain without one, refused with two or with no parent, and a stop between filing and attaching),
and that no forbidden call is made.

For `respond`: a round's replies and its comment, a later round with the owner's decision, a run
again after a partial post and after a reply made but not recorded, a commit not pushed, comments by
others left unread and counted, a failing text check, refused records, and that no forbidden call is
made.

```
python3 skills/review/test_file_review.py
```
