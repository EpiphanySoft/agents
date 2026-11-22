# Unit <nn>: <name>

The unit's file in the work pad, `unit-<nn>-<name>.md`. The brief is written at the top before the
unit's session starts, by whoever ran the piece before it; the session writes its claims below it as
it goes, and the checker adds a verdict beside each.

## Brief

- **Review**: <prefix><N>, work pad `review/<N>/` on `code-review-<N>`, commit `<commit>`.
- **Run on**: <model>, <effort>. Discovery run <1 | 2, blind to run 1>.
- **Sections**: <requirement ids>, read whole.
- **Code**: <paths>, about <lines> lines; read <whole | the delta and what surrounds it>.
- **Tests**: <paths>.
- **Delta**: <from delta.txt, or "none: first review">. Read it first: recent changes are where the
    bugs are.
- **Earlier findings in its area**: <issue links and state, or "none: first review">. Re-check that
    what was marked done still holds.
- **Phase 1 claims and decisions on its sections**: <ids, and the lines of decisions.md>.
- **Untraced code given to it**: <paths, or none>.
- **Open questions it hangs on** (unattended): <question issue links, or none>. Review under each
    reading and tag each claim that depends on one.
- **Run little**: <the project's commands a claim may use to reproduce, what not to start, and the
    time cap for an unattended run>.

## Claims

### U<nn>-<k>

- **Kind**: not built | untraced | differs | security | privacy | bug | test gap | <a project kind>
- **Severity**: High | Med | Low
- **Requirement**: <id, or — for untraced>
- **Where**: `<file>:<line>`

    ```
    <the quoted lines, re-read before writing the claim>
    ```

- **What goes wrong**: <a concrete case where there is one>
- **How it was run**: <the test or command, and what it showed> | read only
- **Remedy**: <what would fix it>
- **Alternatives**: <other reasonable remedies, or none>
- **Reading** (unattended, when it hangs on an open question): <question issue>, reading <A | B>
- **Exploitable if public**: yes | no (a security or privacy claim only; yes adds its id to
    `exploitable.json`)
- **Second run**: <the id of the same claim from the other blind run, if it found it too>

**Verdict** (the checker's): confirmed | corrected: <what changed, the exploitable flag included> |
plausible: <the question> | rejected: <the reason>. **Confirmations**: <n>.

## Found while checking

The checker's notes on what no claim covers, each in the claim format above and unverified. The
cross-check checks them; nothing here enters the review on the checker's word.
