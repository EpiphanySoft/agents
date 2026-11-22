# AI Agent Configuration

Personal Claude configuration (`CLAUDE.md`, shared hooks, and the scripts), and the skills in `skills/`:

- `skills/relay`: a coordinating session hands fixed batches of a large, uniform job to one agent at a time.
- `skills/mutation`: mutation testing, from the baseline and its records to settling each surviving change.
- `skills/review`: a code review against the requirements, from Phase 0's proposal to filing its findings.
- `skills/pr-review`: a review of one open pull request against its requirements, posted on it as COMMENT reviews.
- `skills/pr-respond`: the author's side of a pull request: answering its open comments by fixing, replying and pushing.
