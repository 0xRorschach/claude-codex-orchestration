# Orchestration profile (example)

The orchestration skill ships with defaults marked **[profile]**. This file lists them. To change one, copy the
block below into your own instruction file (Claude Code: your CLAUDE.md, user or project level; Codex: your
AGENTS.md) and edit the values. Instructions in those files take precedence over the skill's defaults, so a line
there is enough; you do not need to edit `SKILL.md`.

Each entry: **default** · what it means · how to change it.

## Defaults

1. **Lower model tier only on request.**
   Default: Sonnet / Haiku (Claude) and Luna (Codex) are used for general work only when you say so; the one
   built-in exception is the `tarayici` (scanner) agent type, which runs on Sonnet/Sol by design.
   Meaning: the agent never drops to a cheaper model because a task "looks simple".
   Change: "You may use Sonnet for <kind of work> without asking." Model IDs themselves live in
   `scripts/modeller.json` and the agent files.

2. **Standing delegation permission.**
   Default: the agent delegates to subagents without asking each time.
   Change: "Ask before opening subagents" (or limit it: "ask before more than 3 subagents").

3. **Concurrency threshold: 15 agents at once.**
   Default: up to 15 agents running at the same time; above that the agent writes you its reason first. It is not a
   session total. The reminder hook quotes the number from `ORCH_PARALEL_ESIK` (default 15).
   Change: "Concurrency threshold: 8." and set `ORCH_PARALEL_ESIK=8` in the hook's environment.

4. **Main session commits without asking.**
   Default: the main session may commit finished work in project repos without asking (workers commit on their own
   worktree/feature branch; merge to main and push stay gated).
   Change: "Ask before every commit." or "Commit only when I say commit."

5. **Workflow (multi-agent script) is a separate permission.**
   Default: no Workflow runs unless you approve it that time.
   Change: "Workflow is pre-approved for <kind of job>, up to <n> agents."

6. **The model proposes Workflow when useful.**
   Default: at a key point that exceeds one session's context, the agent proposes a Workflow with reason, agent
   count, estimated cost and limits, and waits for your answer.
   Change: "Never propose Workflow." or "Propose it only for branch-end reviews."

7. **Image importance tier.**
   Default: Astra for outward-facing or important images, Sol for routine images (`scripts/gorsel_uret.py --model`).
   Change: "Always use Sol for images." or "Always Astra."

8. **Worktree archive folder.**
   Default: `<archive-dir>` = `~/Projects/_archive`; non-reproducible gitignored data from a worktree is moved to
   `<archive-dir>/<project>-<name>-<folder>` before `git worktree remove`.
   Change: "Archive worktree leftovers under ~/Archive/worktrees."

9. **Learning mode (off unless you set it).**
   Example of a personal working style the skill supports: "I am learning while we build. After every meaningful step,
   stop: summarize in 2-3 plain sentences, ask whether to continue, and wait. Define each new technical term once,
   at most five new terms per message. During execution of an already approved plan, stop only at decision points."
   Change: add or remove that paragraph.

10. **Language and wording (example).**
    The skill is written in English and works in any language. Examples you can add: "Talk to me in Turkish.",
    "In Turkish text avoid em dashes; use a colon or a semicolon instead.", "Tag claims as [doc], [measured] or
    'not verified'."

11. **Extra trigger words (example).**
    The skill loads on "/orchestration", "orchestration" and "use subagents". If you talk in another language, add
    your own phrases, e.g. Turkish: "orkestrasyon", "subagent kullan".

## Copy block

```markdown
## Orchestration profile
- Lower model tier: only when I say so.
- Delegation: standing permission.
- Concurrency threshold: 15 agents at once (ORCH_PARALEL_ESIK=15).
- Main session commits: without asking.
- Workflow: ask each time; you may propose it.
- Images: Astra for important/outward-facing, Sol for routine.
- Worktree archive: ~/Projects/_archive
- Learning mode: off
```
