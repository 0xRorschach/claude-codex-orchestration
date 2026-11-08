---
name: orchestration
description: "Agent-type and model tree, delegation rules, cross-family critic and second-opinion (audit) rules, and the superpowers mapping, for Claude Code and Codex. Load it before spawning any subagent (Agent, Workflow, spawn_agent, codex exec / claude -p), when gathering context at project start, when planning parallel work, when a second opinion or audit is needed, before superpowers dispatches an agent, or when the user says '/orchestration', 'orchestration' or 'use subagents'."
---

# Orchestration: model tree and delegation

**Names.** File and env names are Turkish in origin and kept on purpose (renaming would ripple through tests,
hook registrations and this file): `okuma_butcesi` = read budget, `aile_elestirmen` = family
critic, `paralel-is-hatirlatici` = parallel-work reminder, `agent-tip-kapisi` = agent-type gate,
`superpowers_surum_bekcisi` = superpowers version guard, `gorsel_uret` = image generation,
`orkestrasyon_hatirlatici` = orchestration load reminder, `K1` / `K2` = critic layer 1 / 2.
Paths below are relative to this skill's folder (`hooks/`, `scripts/`).

One file serves Claude Code and Codex (install paths: see README); it is self-contained. Read **Shared policy**
first, then your app's section. Use it directly in any project or one-off task; role policy does not depend on how
the project was started, and finishing a project setup never by itself grants permission to implement (a permission
the user already gave still holds). Items marked **[profile]** are defaults; change them in your profile (see
`profile/profile.example.md`).

## Tree

**Model names are family names** ("Fable", "Opus", "Sonnet", "Haiku", "Astra", "Sol", "Luna": the newest model of
that family). No version numbers in rule text; versions live only in dated records and the resolution line below.

| | Claude Code | Codex |
|---|---|---|
| Main session: decide, brief, review, synthesize | Opus · high | Astra · high |
| Subagents (`explorer` / `worker` / `researcher`) | Opus · medium | Sol · medium |
| Scanner (read-only search / map / raw-output summary) | Sonnet · medium (`scanner`) | Sol · medium (`scanner` role; Luna not measured) |
| Lower tier, for any other work **only if the user says so** [profile] | Sonnet | Luna |
| Second opinion (audit), key points only | Astra · medium · read-only; methodology gates high; task-boundary K2 (task flagged `K2: yes`) Sol | Claude Opus · read-only |
| Advisor | Fable (`advisor` tool) | none |

Resolution [measured 2026-10-08]: Opus → Opus 5.5 · Fable → Fable 5.1 · Sonnet → Sonnet 5.5 · Haiku → Haiku 5.5 ·
Astra → `gpt-6-astra` · Sol → `gpt-6.1-sol` · Luna → `gpt-6-luna`. Model IDs live in `scripts/modeller.json` and the
agent files (Claude agent `.md`, Codex role `.toml`; see README); update them when a new model ships. If you have no access
to one of these families, put your own models in those same files; the rules below keep working by role.

Summary: **plan, decide and review in the main session; delegate execution at medium; ask the other family for a
second opinion.** If the user names another model for a job, use it for that job, then return to this tree.

## Shared policy

### Goal: working as a team

The goal is not to restrict agents but to make them work efficiently as a team. A single agent sees the context only
from its own perspective and can be misled along its own path; adding a few perspectives counters that. Work this way
even when the skill was not triggered: many agents, one orchestrator in control. The rules are tools for this goal,
not a checklist. On an important decision, add a **genuinely different** view:

| Source | Who | What breaks it |
|---|---|---|
| Different information: an eye that has not seen the author's reasoning | fresh `explorer` | writing your own conclusion into its brief |
| Different role: one who filters, not produces | a reviewer agent separate from the implementer | trusting the report instead of the evidence |
| Different family: other training, other blind spots | second opinion (Astra from Claude, Claude Opus from Codex) | putting it on every step (see convergence rule) |

The advisor sees the whole conversation: a stronger eye, but not an independent one. Asking the same agent the same
question twice is not a new view. The trigger is the kind of decision, not whether orchestration is switched on.

### Delegation: default is delegate

- **Default:** whenever a subagent can be used, use it. Exploration, reading, implementation, tests and documents go
  to subagents; the main session's context is not filled for nothing. why: saves context and wall-clock time. If the
  user says "use subagents" or "do it yourself", that wins. Delegation permission is standing (not asked each time)
  [profile]. This skill answers "which type, which tier".
- **Start of multi-step work:** first load this skill and the relevant superpowers skill (e.g.
  subagent-driven-development); do not postpone it to the first subagent call. why: context fills fast.
- **Main session (Claude: Opus · high unless the user names another model):** does no active work and keeps its
  context lean. It hands work to subagents, organizes, stays in contact with the user (also through intermediate
  steps that need no subagent), explains when needed, orchestrates, decides, reviews and consults the advisor when
  due. When a handoff stalls or is unreliable it re-delegates with a new brief or asks the advisor; it does not take
  the work over.
- **Codex exception:** hard or precision work where Sol subagents fall short may stay in the Codex main session
  (Astra); mechanical and narrow work goes to Sol. why: Sol is weaker than Opus [observed 2026-09-25].
- **Active work vs permitted work.** Permitted (stays in the main session): writing records (STATE, ledger, your notes
  system), writing briefs, engine and gate commands, commit / push / merge, cross-family calls
  (`scripts/aile_elestirmen.py`), and browser work in sync with the user when the subagent has no browser access.
  Active (goes to a subagent): exploring by reading files (`cat`, `sed -n`, `grep`, Read), running tests, converting
  documents (pandoc, textutil), editing code or deliverables. If a subagent's evidence is missing, the main session
  does not run its own grep; it opens a fresh reviewer.
- **Read-budget hook** `hooks/okuma_butcesi.py` (PostToolUse; only adds a note, never blocks) sums, per session, only
  the fields of the main session's Read/Bash/Grep/Glob output that reach the model (Bash `stdout` + `stderr`, Read
  file content, without the line number prefix the model sees, so slightly under-counted; the `bashEditDiff` field
  Claude Code adds is not counted; in Codex, shell commands only). When the total crosses `ORCH_OKUMA_ESIGI` (default
  40000 characters) and then each multiple, it adds a note to delegate exploration and verification to
  explorer/scanner. Silent inside subagents. Not counted: `git commit` / `git push` / `git log -1`, `codex exec`,
  `aile_elestirmen.py`, extra scripts in `ORCH_MUAF_BETIKLER` (comma-separated file names, e.g. your own notes CLI),
  heredocs writing to `.md`, `--help` / `--version` (compound-command and `git log` details: `hooks/README.md`). Off:
  `ORCH_OKUMA_BUTCESI=0`. Registration: see README; timeouts 5 s (PostToolUse) and 10 s (SessionStart) in both apps.
  Threshold [measured 2026-11-07, n=107 main sessions]: median Agent result 16k, median Bash work output 44k
  characters; 40k sits between them and warns about half the sessions (that measurement counted every response field,
  so it may be inflated by `bashEditDiff`; not yet re-measured with the allowlist). why: without a definition of
  "active work", Bash reading stayed the main session's largest work class.
- **Load reminder.** If the main session opens a subagent and this skill was not loaded in that session,
  `hooks/orkestrasyon_hatirlatici.py` (PreToolUse; Claude `Agent|Task`, Codex `^(spawn_agent|Agent)$`) reminds once
  and never blocks. Off: `ORCH_HATIRLATICI=0`. In Claude the note (additionalContext) arrives with the first Agent
  call's result, so it shapes the later spawns, not the first one. [measured 2026-11-07, n=152 main sessions: 44.7%
  loaded on their own, 11.2% user-triggered, 44.1% never loaded (mostly single-agent sessions)]
- **Multiply independent work.** Extract dependencies before dispatching; independent tasks, scenarios or questions go
  to separate subagents in parallel (separate folder/worktree, separate result file, merge in the main session). In
  Claude Code `hooks/paralel-is-hatirlatici.py` (PostToolUse `Agent|Task`) asks on every agent start "is there work
  that does not wait for this agent?" (calls that complete within 5 s of the last warning stay silent, so agents
  started in the background together get one warning; foreground agents that finish at different times can each warn).
  When it fires, either start the independent work in the same turn or tell the user why not in one sentence; a
  sequential engine step needs no reason. Off: `ORCH_PARALEL_HATIRLATICI=0`.

### Who decides

- **Agent:** implementation and technical choices that research can justify and that are reversible: research,
  choose, write the reason. Also the application of an already written rule or plan, and a reversible choice backed by
  your reasoned recommendation: apply it, record it, and present it to the user as **"decisions I took"**. For these
  delegated choices, wait only for one that turns out to be hard to reverse, outward-facing, needs payment or an
  account, or changes the core of a frozen protocol. why: when most questions come back as "follow your
  recommendation" (14 of 15 in one document [measured]), waiting for them only stalls the work.
- **User:** scientific/clinical thresholds (analysis plan, exclusion criterion, clinical cut-off), personal
  preferences, and decisions that are hard to reverse or outward-facing always go to the user, even when a written
  rule or plan seems to cover them: write them to a file and ask with a reasoned recommendation. why: a threshold
  chosen silently becomes a value nobody questions.

### Limits

- **Concurrency threshold 15** [profile] (`ORCH_PARALEL_ESIK` sets the number quoted by the reminder hook). It is a
  threshold, not a wall: it counts agents running **at the same time**, not the session total; above it, write the
  reason to the user before opening more (nested ones included). why: cost (even an empty subagent ~26k tokens
  [measured n=1]) and the main session's review capacity; the technical limit is nesting depth, not count (default 3
  levels [doc]).
- **Nesting:** a spawned agent follows the same type rules; **it may open helpers, it may not become a manager**. In
  practice only `worker` can spawn; `explorer`, `researcher`, `scanner` have no agent tool.
- **Irreversible actions, two tiers.** A subagent does not push, delete remotes, delete untracked files, or write
  outside the workspace or to an external service; it returns to the main session. Outward-facing or hard-to-reverse
  actions also need the user's approval: the main session's approval does not replace the user's. Local edits need no
  stop. The worker commits task work on its own worktree/feature branch; merging to main and pushing are the main
  session's job. The main session asks before committing [profile]; committing without asking is a profile option
  (`profile/profile.example.md`). A written explicit exception in the project's
  CLAUDE.md/AGENTS.md wins (e.g. "the agent may merge to main and push").
- **Worktree lifecycle.** Open it inside the project repo, in a gitignored `.worktrees/<name>` or the tool's in-project
  folder (Claude Code `EnterWorktree`: `.claude/worktrees/` [measured 2026-10-17]); never as a sibling folder next to
  your projects (it looks like a separate project). Once the branch is merged to main and review is closed, the
  session that opened it removes it (either location): first `git status --porcelain --ignored` to find gitignored but
  non-reproducible data (not venv/cache) and move it to `<archive-dir>/<project>-<name>-<folder>` [profile]; then
  `git worktree remove` without `--force` (even plain remove deletes gitignored files [measured 2026-10-17]). Delete
  the branch only with `git branch -d` once merged; never `-D` (merged commits are on main; `-d` refuses unmerged).
- **Workflow** (multi-agent script) is a separate permission the user grants explicitly each time; this skill does not
  authorize it [profile]. **The model brings the proposal**, regardless of the task [profile]. No always-on ultracode
  mode (it clashes with the convergence rule, Opus · medium delegation and this permission rule). At a key point that
  exceeds one session's context or needs independent lenses (whole-branch review before merge, a many-item
  acceptance/evidence matrix, a wide scan) the agent **proposes it on its own** in the question box: reason, agent
  count, estimated cost, limits; types `explorer`/`worker`, effort medium, at most 2-3 lenses per finding,
  convergence rule kept (if it keeps producing findings, stop and bring it to the user). Nothing runs before approval;
  "ultracode" in a question or record instruction is not permission. why: in one task, different views (fresh
  explorer + real measurement 4 errors, Astra 1) caught what single-lens reviews missed; fan-out gains nothing in
  sequential work sharing the same file.
- **Lower tier (Sonnet / Haiku / Luna) only if the user says so** [profile]; never drop down because "it is simple".
  The one exception is `scanner`: the drop happens by agent type, not by judgment at call time.
- **`scanner` or `explorer`:** "where / called from / map / summarize this output" → `scanner`; anything with
  judgment (spec compliance, is the code right, is the plan sound) → `explorer`. [measured n=2, blind scoring] in
  search Sonnet ≈ Opus; in document verification Sonnet made a factual error → `researcher` stays on Opus; review and
  implementation were not measured, so they stay on Opus. Haiku 5.5 was tried as a single-artifact scanner and made
  more false "none" claims than Sonnet in a blind comparison (9 runs each, 1-0); not adopted [measured 2026-10-08].
- **`scanner` mechanical work.** Work whose verdict comes from code or output goes to `scanner`: running a script and
  relaying its output verbatim (audit script, word count), test/log summaries, inventory / symbol location / call
  trace (quote the line itself for every `path:line`). If a script prints an error (`HATA` or similar), the fix is the
  `worker`'s; `scanner` adds no "clean" comment. Checklist-bound format checks are in scope too. Every `scanner`
  brief contains: "do not write notes outside the template; fill only the requested fields". Document, API and source
  verification never go to Sonnet; they stay with `researcher`. [measured 2026-11-07, blind comparison n=3/cell, 24
  runs: accuracy Sonnet 96/96, Opus 95/96; out-of-template note errors Sonnet 1, Opus 7; Sonnet 26-34% faster] Task
  definitions for Sonnet/Sol can be formatted this way.
- **Layered option when evaluating models.** When a new or cheap model is evaluated, do not only ask "should the whole
  role move"; design, measure and present layered use by task type too (e.g. single file/single output → cheap model,
  multi-file trace → strong model). why: in one pilot layering was dropped early as "routing confusion" and not
  revisited when the data showed that pattern.

### Brief, review, synthesis

- **Brief contents:** narrow scope + context + output format + acceptance criterion.
- **Orchestrator ↔ subagent talk is minimal.** Keep reasoning that changes what the agent will do (measured fact,
  exact command/value, consequence of a constraint); drop story that only helps understanding. Explanation discipline
  binds text written to the user, not subagent briefs. A subagent does not redefine the goal.
- **Evidence format.** Ask for the command run, exit code, pass/fail counts, names of failing tests, diffstat and
  file:line; the summary comes back as finding · evidence · uncertainty. No long logs, pointers instead. "Tests
  passed" is not evidence.
- **Review the output critically:** factual error, unsupported claim, missed requirement. Resolve contradictions
  yourself, never forward raw output, synthesize one result. If a model, agent or tool was not available, do not
  present it as if it ran; report the technical limit plainly.
- **Brief order for an independent eye.** Give the reviewer or second opinion the question, context and evidence
  first; not your conclusion. Task: "find the weakest point; if there is no significant weakness, say 'none'." The
  second sentence is required: without it every round must produce findings and the convergence rule breaks (why: the
  pull toward a stated view). Not applicable to the advisor.
- If output is insufficient, **re-delegate with a new brief or ask the advisor**; do not take the work into the main
  session.
- **Conflicts:** the main session resolves conflicts between agents. Exception: in a **scientific/clinical decision**
  the main session weighs them and presents both views plus its own recommendation to the user.

### Stage tracking with the existing plan

A stage is a piece of work that closes with an observable output and an acceptance criterion. Use project stage
tracking in multi-stage work: an existing stage record, or else the authoritative plan/ledger, is enough. If tracking
helps, the main session defines narrow stages in that record; a one-off task needs no new document and an existing
project need not migrate to STATE/BACKLOG. Keep stage status in one authoritative place only (two records drift
apart). If the project uses a STATE schema:

- The single current table is the top `>>> … <<<` block: id, goal, output/path, prerequisite stages and critical
  input/version, observable acceptance criterion, status, evidence link. Unknown input or version stays `unknown`; no
  real prerequisite is written `none`. Status vocabulary: `planned`, `active`, `in review`, `accepted`, `blocked`,
  `deferred`, `re-review needed`.
- Task detail and tracking stay in the plan (the superpowers plan if any); STATE points to its path/task. BACKLOG holds
  half-done, blocked and deferred work by stage id: remaining work, reason, plan link, unblock or revisit condition.
  STATE open items point to these; do not duplicate stage status in BACKLOG or debt detail in STATE. Closing BACKLOG
  debt is not stage acceptance. STATE Done is only a summary link to the stage/plan evidence, not a second record.
- The STATE table is not plan approval: the required superpowers plan-content approval stays; the same approved
  transition is not re-approved. Without this schema, keep the debt/evidence record in the existing ledger.
- STATE keeps its three headings: Done · Open items · Next. Claude Code can load it with a SessionStart hook if you
  have one; Codex reads it manually at the start.

Rules:
- **Pick ready work:** prerequisites met, critical input specific enough, within current authority. Delegate
  independent ready work in parallel; do not start work that waits on another's output. If uncertainty blocks, link it
  to BACKLOG with a concrete resolution condition and continue other ready work. The agent may pick technical criteria
  within scope; clinical/scientific and personal criteria are the user's (Who decides). Record the authority/source;
  never loosen a required goal or criterion just to accept. No per-stage approval.
- **Accept with evidence:** output first goes `in review`; no `accepted` without review separate from the implementer
  and evidence meeting the criterion. The evidence record names the input and criterion version; never invent the
  unknown. Separate review follows the existing superpowers/review policy; no new audit per stage, key-point rules
  unchanged.
- **Track impact of change:** if a critical input/version, goal or criterion changes materially, record the authority,
  set the affected acceptance to `re-review needed`, follow the effect on dependent stages; re-check only the affected
  criterion/evidence and record why. Unrelated change does not invalidate acceptance; never delete old evidence, keep
  the version it belongs to.
- **Separate blockage from measurement:** a check that did not run because a tool/provider was missing is
  `undetermined`, not a real rejection. Blocker and condition go to BACKLOG, the measurement record to the evidence
  link. If the check blocks acceptance, the stage is `blocked`; independent authorized work continues. Do not repeat
  the same call blindly; re-check narrowly only on new information or changed conditions, otherwise pick ready work.
- **Close a stage:** every item in scope is accepted or explicitly deferred; keep remaining debt visible with its link.
  A deferral that misses a required goal is no ground for acceptance without an authorized scope change. With partial
  deferral and a missing required criterion, no acceptance; a fully deferred stage is `deferred`. On an authorized
  scope/criterion change, write the source and the current criterion and re-verify. A consumer stage that needs a
  deferred output is not ready; independent work whose prerequisites are truly met continues.
- **Final close:** compare the original goal/scope with what was delivered; show acceptance evidence, open debt,
  `undetermined` measurements and deferral authority. Never infer "done" from stage counts or plan checkboxes; the
  decision is the main session's / the user's. Earlier explicit permissions hold, no new approval per stage; new
  scientific/clinical, outward-facing or hard-to-reverse decisions follow the approval rules (Who decides).
- **Done condition:** every new job states its done condition in the chat as `Done when: <one sentence>`; that line is
  the job's acceptance criterion.

These are document rules the agent applies, not an automatic engine: they create no mandatory lifecycle file, hook or
external tool dependency, and existing projects are not migrated automatically.

### Critic family: K1 same family, K2 other family

| Layer | Who | When | Looks at |
|---|---|---|---|
| K1, same family | fresh `explorer` per task (SDD task reviewer); final review at branch end | every subagent delivery | spec compliance + code quality |
| K2, other family | from Claude: Codex (Sol at task boundary, Astra at branch end and key points); from Codex: Claude Opus (only option) | **required** for the work types below; also at key points (Second opinion) | the other family's blind spot, against the worker's test evidence |

A same-family critic is fine, but an other-family critic must also be there; it pays off after important, large work.

- **K2 required work types:** multi-task plan execution; multi-file change outside an engine; schema / state contract
  or gate change; outward-facing output. For a routine single-file fix K1 is enough.
- **Placement:** default branch end. In SDD Final Review the `explorer` subagent does the last branch review; K2 runs
  in parallel on the same `review-package` file (`run_in_background`); the main session synthesizes both and asks the
  advisor before "done". Codex has no advisor; there the branch-end K2 (Claude Opus) result plus the main session's
  synthesis take its place, and Fable is not consulted manually from Codex. Task-boundary K2 opens only for a task
  flagged `K2: yes` in the plan's Global Constraints: after the task review comes back clean, before the ledger's
  "complete" line. It is an SDD step, not a hook; it does not run on every tool call or agent stop. Superpowers
  templates are not edited.
- **Model split:** task-boundary K2 defaults to Sol (`--model sol`); branch-end and key-point K2 is Astra (the script's
  default). From Codex, K2 is Claude Opus. [measured 2026-11-07, 10 deliveries × n=2, 5 known defects: catch rate
  Sol/Astra/Opus 10/10; false positives Sol 2, Astra 2, Opus 5; easy set (ceiling effect), cost not measured]
- **External signal:** K2 does not judge by reading alone. The worker supplies test evidence (command run, exit code,
  diff or `review-package`); K2 checks that evidence against the spec. K2 does not run tests itself; it verifies the
  worker's evidence and may propose a reproduction step. why: without test or run output, self-critique does not
  reliably improve accuracy [literature]; see Known limits for the sandbox reason.
- **Findings** enter SDD's single fix wave and single narrow re-review; K2 does not run again; tests + `explorer`
  verify the fix. Convergence and "the ready decision is not the critic's" apply (Second opinion, rules 3-4).
- **Call:** `scripts/aile_elestirmen.py --effort medium|high --brief <file> --cikti <json> [--calisma-dizini <dir>]`
  (effort required; high at methodology gates; working dir defaults to the current dir). The Codex direction is
  read-only: it cannot write, but reading is not confined to the working dir (the sandbox restricts writes, not reads;
  this includes the credential copy in the temporary home; out-of-dir reads not tested): put no secrets in the brief
  or the working dir. The other family is inferred from the session (Codex from Claude, Claude from Codex); if not,
  `--aile codex|claude`. From Claude, `--model astra|sol` (default astra). The Claude direction runs in `--restricted`
  mode with Read/Grep/Glob only, file tools confined to the working dir. The wrapper builds the clean call, appends
  the "find the weakest point ... say 'none'" sentence if the brief lacks it, binds output to
  `scripts/elestirmen_sema.json`, and writes the Codex credential file back safely. A reply off the schema counts as
  `undetermined` (exit 3); exit 77 means "refresh token was already used": do not retry, run `codex login`. The
  hand-built command (In Claude Code › Second opinion) is the fallback; details in `scripts/README.md`.
- **Record:** after every cross-family call, one line in the project's STATE/ledger (inside SDD, the plan ledger). With
  `--kayit <file> --olay <short name>` (both required together) the wrapper writes it:
  `Cross-family <YYYY-MM-DD HH:MM> · <event> · <family> (<full id>) · <effort> · findings <n> (high <k>) · <output path>`
  (`undetermined (<reason>)` in place of the findings count when the reply is off-schema). After weighing, the main
  session appends `· applied / parked (why)`. why: without a record its effect cannot be measured later.

why branch end: in one multi-task plan execution the per-task reviews came back clean, while the branch-end read found
8 real gaps (Astra) and 4 (explorer) [doc]. Astra default: it is the model measured in the audit role.

### Second opinion (audit): key points only

The key-point audit is a special case of K2 (Critic family): same wrapper, same record line. Rules 1, 3 and 4 apply to
both; a K2 finding's fix is verified with tests and `explorer`, not with K2 again. K2's required work types add to the
key-point list, they do not replace it. If a key point coincides with branch end, one K2 call covers both; no second
audit on the same branch; a task-boundary K2 (Sol) does not cancel the branch-end K2 (Astra).

No audit after every job; ask for a second look at key points that matter for the architecture. The aim is to catch
what the main session and the advisor may miss (the other family's blind spot); it is not a gatekeeper. **It does not
throttle subagents:** they gather context, keep the main session lean and save time; fewer audits never means less
delegation or less review.

Key points:
- data schema / state contract change; gate or safeguard logic;
- hard-to-reverse decision (architecture, data-loss risk, outward-facing contract);
- the **last version of a plan or design before it goes to the user**, including a statistical analysis plan,
  exclusion criterion, missing-data plan draft: the decision is the user's; the audit looks for blind spots first;
- final check of outward-facing output (paper, presentation, release).

Not key points: local fixes, per-task review (that is `explorer`'s; plus K2 for a task flagged `K2: yes`), a fix
closing a previous audit's finding. These are measured with tests and `explorer`.

Rules:
1. **One audit per key point.** The main session weighs findings (never applies them blindly); accepted fixes are
   verified with **tests + `explorer`**, not by rerunning the audit.
2. **At most one narrow re-check**, only if a finding forced a mechanism rewrite; scope is that mechanism.
3. **Convergence rule:** if rounds keep producing new findings, that is a design signal. Open no new round; bring the
   remaining gaps to the user as a decision, with reasons.
4. **"Is it ready" is not the audit's decision**; the main session and the user decide. The brief never asks
   "ready to execute: yes/no"; it asks for finding, severity, evidence.

why [measured 2026-09-26, one multi-stage plan]: 5 audits in 20 hours, new-finding curve 12 → 5 → 1 → 2 → 1; every
brief asked "ready?", every report said "no". What slowed things was making the audit a gate, not the audit (the first
one caught a real bug).

Reviewers are not stacked on one step, except K1 and K2 reading the same branch-end package in parallel. Who and when:
Critic family table; advisor (Fable on Claude: direction, approach, stuck): "Advisor (Claude side)".

### With superpowers: "how" from there, "who" from this tree

Superpowers supplies the process (plan, test first, fresh agent per task, separate review, no "done" without
evidence); keep it. Agent type and model come **only from this tree**: `Subagent (general-purpose):` is a placeholder,
and "Model Selection" is a saving default for users it does not know; superpowers ranks user instructions above
skills. Removing superpowers was rejected (a large plan ran on this process). Use both together even when not
triggered.

The table is written for superpowers 7.0.0 (2026-11-07). The version guard `hooks/superpowers_surum_bekcisi.py`
(SessionStart, Claude and Codex) adds a "re-audit the mapping table" note when the installed version differs; after
re-auditing, update `tablo_surumu` and `tarih` in `hooks/superpowers_surum.json`. Off: `ORCH_SURUM_BEKCISI=0`.

| In superpowers | Here |
|---|---|
| implementer / task executor | `worker` |
| task reviewer (single reviewer, spec + quality) and scoped re-review | `explorer` (read-only) |
| brainstorming "builder check" (fresh reader) | `explorer`; writing-plans self-review opens no agent |
| dispatching-parallel-agents agents | `worker` (`explorer` if read-only) |
| final whole-branch review, SDD Final Review ("most capable model") | `explorer` subagent (main session does no active work); for a required work type or key point, K2 in parallel on the same `review-package` (Critic family); main session synthesizes both, advisor before "done" (Codex equivalent: Critic family › Placement) |
| "Model Selection" (cheap / standard / most capable) | ignore; model comes from the agent file; do not write a `model` parameter |
| a single orchestrator subagent running the whole SDD loop | do not use; the main session is the orchestrator (a subagent opening helpers for its own work is fine) |
| SDD "Always specify the model explicitly" | do not write a `model` parameter; the agent file sets it (the gate rejects non-Opus) |
| SDD "escalate to a more capable model" in the fix loop | no escalation (nothing above Opus for subagents); re-delegate the stuck task with a new brief or ask the advisor |
| SDD "the controller never fixes a finding itself" | the worker fixes; if the handoff is unreliable the main session re-delegates with a new brief or asks the advisor, never fixes it itself |
| writing-plans "Native: I implement each task myself" option | do not offer it; execution defaults to subagent-driven and the execution method is not asked; plan-content approval is a separate gate and is asked |
| using-git-worktrees location choice | in-project `.worktrees/` or the tool's in-project folder (Claude Code `.claude/worktrees/`); remove after merge (Limits › Worktree) |
| finishing-a-development-branch cleanup | `git status --porcelain --ignored` scan + archive before `git worktree remove` (Limits › Worktree); branch only `-d`, never `-D` |
| brainstorming "MUST use before any creative work" | applies; every new job first writes its **done condition** (observable, one sentence) and **what it will not do** (out of scope); learning-mode stops [profile] |
| implementer "Commit your work", writing-plans per-task commit step | applies: the worker commits on its own worktree/feature branch; merge to main and push are the main session's (Limits) |
| implementer and reviewer may not spawn ("You Do Not Dispatch Subagents") | inside SDD the superpowers rule holds; outside SDD a worker may open helpers (Limits › Nesting) |
| SDD "Never dispatch multiple implementation subagents in parallel" | sequential within the same plan and tree; in an independent area or separate worktree "Multiply independent work" applies |
| SDD "Rulings, not stalls": only four stop reasons | in addition, stop at scientific/clinical thresholds, exclusion criteria, personal preferences and a frozen protocol core; the decision goes to the user (Who decides) |
| Codex: write `model` and `reasoning_effort` on every `spawn_agent` (using-superpowers Codex tool note) | the role file carries model/effort; no override at spawn, pass `fork_turns="none"`, never the `default` role (In Codex) |
| plan Global Constraints `K2: yes` (the controller reads it) | task-boundary K2 for flagged tasks; none for unflagged (Critic family) |

**On conflict this skill wins.** If a new conflict not in the table appears, apply this skill's rule and add a row.
Superpowers stays a separate plugin and is not merged into this skill: merging forks a versioned plugin and loses
upstream updates; conflicts are resolved through this table, and the version guard catches staleness. Preserved
structure: a fresh agent per task; the reviewer is a different agent from the implementer; no next task before the
review gate passes. Codex uses the same role names.

### Advisor (Claude side)

Conditional: needs Claude Code's `advisor` tool (`advisorModel` set; Anthropic API only). If you do not have it, skip
this section; wherever "ask the advisor" appears, use the Codex substitute (branch-end K2 plus main-session
synthesis).

The main session consults **right before** these events (plan/architecture decisions are where it pays):

| Family | Event |
|---|---|
| Before the user sees it | approach choice at method/architecture level (not every design sub-question) · final spec/design · scientific/clinical options (SAP, threshold, exclusion) |
| Before execution starts | new component/write path/capability in an approved scope (once per change package) · plan commit → first worker · schema/state contract/gate logic merge (once per change) · a review finding forces a mechanism rewrite · a user process correction changes the method |
| Before the irreversible | handoff note · "done" / merge to main · push/release |
| When stuck | same error a second time · findings do not converge |

- **Consulting on one thing does not cover the next:** approach, spec, scope change, plan, contract merge and handoff
  are separate events. A second call for the same event only with new evidence. A rulebook, contract or
  hard-to-reverse change counts as a "big plan" even when given in chat. why [measured 2026-10-11, session logs]: in
  5 of 8 sessions the last consultation fell in the first 59% of the session; in one stage 6 hours passed with 1
  consultation while scope growth and a 22-task plan went unconsulted (inference: the old three triggers counted as
  "done" once met).
- **Order with Astra:** for specs and scientific/clinical options, advisor first ("is this the right approach"), then
  Astra ("what is wrong in the final text"); they do not repeat the same question.
- **Record:** after each consultation, one line in the project's STATE/ledger:
  `Advisor <date time> · <event> · <advice summary> · applied / not applied (why)`. why: the advice text is encrypted
  in the log; without a record its effect cannot be measured.
- **Call in its own message:** an advisor call placed in the same message as another tool call does not run and must
  be resent [measured n=3 sessions, 2026-10-11; mechanism undocumented].
- Before "done", write the output to a file first, then consult. If the tool is missing this session, tell the user;
  never act as if you consulted. `/advisor` selects the model (fable/opus/sonnet/off); it is not a way to ask.
- **Cost:** the advisor rereads the caller's transcript uncached [doc code.claude.com/docs/en/advisor]; cost per call
  grows with transcript size (one session: 119k → 652k) [measured]. Retroactively on a long past stage the core list
  meant ≈7 calls / ≈3 M tokens versus 21 / ≈7.2 M for the full 12-event list, so the core list was chosen.
- **Subagents are free to consult.** There is no technical lock anyway: `tools`/`disallowedTools` do not affect the
  server tool, and the only switch (`CLAUDE_CODE_DISABLE_ADVISOR_TOOL`) also turns it off for the main session
  [doc + measured 2026-10-11].

### Image generation

Any job that needs an image uses Codex models; Claude models do not generate images. Codex's built-in image tool draws
in both cases; the model sets the prompt and the check. Importance tier [profile]: Astra for outward-facing or
important images, Sol for routine ones. From Claude, the agent requests the image via a Codex call from Bash; no
separate agent type: `scripts/gorsel_uret.py` (`--istem` or `--istem-dosyasi`, `--cikti` PNG path, `-i` reference
image, repeatable; `--model astra|sol`, default astra; `--effort low|medium|high`). The image tool works on Sol
[measured 2026-11-07, `gorsel_uret.py --model sol`, 30 s].

## In Claude Code

- Subagents are **`explorer` / `worker` / `researcher`** (`model: opus`, `effort: medium`) and read-only
  search/map/summary `scanner` (`model: sonnet`, `effort: medium`). User-level install (`~/.claude/agents/`): plain
  names (`explorer`); plugin install: `orchestration:explorer`, `orchestration:worker`, `orchestration:researcher`,
  `orchestration:scanner`. Both forms mean the same agent; the bare names in this file cover both. Add your own
  specialist agents (e.g. a literature screener) with the same settings; the gate allows any non-built-in type.
- **Do not use the built-in `Explore` / `general-purpose`**: they carry no `effort` and inherit the main session's
  high. **Do not use `fork`**: it ignores the model setting and clones the main session.
- **Gate:** `hooks/agent-tip-kapisi.py` (PreToolUse `Agent|Task`) rejects `general-purpose`, `Explore`, `Plan`,
  `claude`, `fork` and an empty type (case-insensitive; a `<plugin>:<agent>` type is checked by its last part), and
  any `model` parameter that is neither `opus` nor a full Opus id starting with `claude-opus-`, inside subagents too;
  it accepts both the plain and the `orchestration:`-prefixed agent names. Off: `ORCH_TIP_KAPISI=0` (the user's
  switch, set in the environment the tool starts in; every denial message names it). If rejected,
  reopen with the right type; if the user asked for another type, tell them about the gate, never loosen it yourself.
- Do not write a `model` parameter; the agent file sets the model (the gate rejects non-Opus). If Sonnet is needed,
  use the `scanner` type, not a parameter. Fable is never opened as a subagent; it is only the advisor.
- **Advisor:** the `advisor` tool (`~/.claude/settings.json` → `advisorModel: "fable"`); a `/advisor` change takes
  effect in the current chat only after `/clear` or `/compact`.
- **Effort inheritance:** never set the top-level `effortLevel` below high: a new Opus/Fable without a `modelSettings`
  entry silently drops to that value. On a new release measure effort from inside the process
  (`printenv CLAUDE_EFFORT`).
- **Second opinion, Astra audit.** Fallback only when the script cannot be used and no other Codex call runs at the same
  time: the script (`scripts/aile_elestirmen.py`) locks the credential write, this block does not.
  `ORCH_CODEX_BIN` points at the real `codex` binary so a wrapper on PATH is skipped.
  ```bash
  R=~/.codex/auth.json; H=$(mktemp -d); cp "$R" "$H"/ && chmod 600 "$H"/auth.json; S0=$(shasum -a 256 < "$H"/auth.json)
  CODEX_HOME="$H" "${ORCH_CODEX_BIN:-codex}" exec --skip-git-repo-check --ephemeral --disable hooks --disable memories \
    -m gpt-6-astra -c model_reasoning_effort=medium --sandbox read-only "<audit brief>" < /dev/null
  if [ -f "$H"/auth.json ] && ! cmp -s "$H"/auth.json "$R"; then
    if [ "$(shasum -a 256 < "$R")" = "$S0" ]; then cp "$H"/auth.json "$R.tmp.$$" && chmod 600 "$R.tmp.$$" && mv "$R.tmp.$$" "$R"
    else echo "WARNING: auth.json changed in another process during the call; not written back (run codex login if needed)" >&2; fi
  fi; rm -rf "$H"
  ```
  Write-back is required: a token refreshed inside the temporary home lands only there; the old refresh token is
  single-use, so `~/.codex/auth.json` goes invalid and every later call fails with "refresh token was already used"
  (fix: `codex login`). Write back only if the real file is unchanged since the call started, atomically (`mv`), 0600;
  never overwrite another session's refresh (unlocked; safe only when no other Codex call runs at the same time; the
  script path is locked). [measured 2026-11-06, one session: first Astra call passed, second failed]
  why a clean call: a wrapper on PATH may force hooks on (`--enable hooks`), hence explicit `--disable hooks`;
  `--ignore-user-config` does not keep hooks or `~/.codex/AGENTS.md` out; the temporary home has no config, so
  model/effort/sandbox go on the command line; `< /dev/null` is required (else it waits on stdin). [measured
  2026-10-02, leak check 4/4 → this pattern 0/4] Open it with `run_in_background` and continue with independent work.
  Always write effort (`medium`; `high` at methodology gates): some fleet tools and wrappers default to high.
- **Codex implementer (Sol):** in narrowly briefed mechanical work Sol may implement: separate worktree, concrete
  acceptance criterion, returns test evidence like `worker` (command, exit code, diffstat, file:line). Hard or
  precision work stays with the Opus `worker`. (loosened on observation, without a pilot)
- **Context-saving tools compete:** with an MCP tool that runs a command and returns only a summary, split the work:
  broad file exploration → subagent; one command's large output → that tool. Never do the same work twice.

## In Codex

- Subagents are the **`explorer` / `worker` / `researcher` / `scanner`** roles (`~/.codex/agents/*.toml`, all Sol,
  `medium`); a Codex plugin cannot carry agent roles, so `install.sh` copies them there from the repo's
  `codex/agents/` (see README). Add your own roles the same way. The role file must have a `model` line; the role
  model applies only
  with `fork_turns="none"` on `spawn_agent` (below). **Do not use the `default` role**: it inherits the main
  session's model (Astra high).
- **Open role agents with `fork_turns="none"`.** If `fork_turns` is omitted or `"all"`, the child inherits the parent's
  model and effort (an Astra main session yields an Astra subagent); with `"none"` the role file's model and effort
  apply. Put needed context in the brief. Do not write `model` / `reasoning_effort` overrides. [measured 2026-11-07,
  59 subagent sessions: `"none"` 28/28 Sol; omitted or `"all"` with an Astra parent 30/30 Astra; 1 session `"all"`
  with a Sol parent, child Sol (parent model inherited)]; source-code basis not verified.
- **Sol is weaker than Opus** (observed with Sol 6 / Opus 5.5; re-check on new releases): narrow, explicit briefs,
  concrete acceptance criteria. Mechanical work goes to `worker` (Sol) in a separate worktree with test evidence;
  hard/precision work stays in the main session (Delegation › Codex exception).
- With several agents, tell each that it is not alone and must not revert others' work; subagents spawn only these
  roles. Close finished agents. A new role needs a new session.
- **Model ID:** Codex has no floating alias [measured 2026-09-25]; write the full ID in config, not the family name
  (`scripts/modeller.json`, role files).
- **No advisor.** Fable is not consulted manually from Codex (Fable stays scarce). Instead of "advisor before done":
  Critic family › Placement.
- **Critic family:** K1 = fresh Sol `explorer`; K2 = Claude Opus via `scripts/aile_elestirmen.py` (from a Codex
  session the other family is Claude automatically; if not inferred, `--aile claude`). Required work types,
  placement (branch end, `K2: yes` flag), external signal, single fix wave and record line are as in Shared policy ›
  Critic family; the key-point audit is a special case of K2.
- **Active vs permitted work:** the Delegation list holds for the Codex main session (Astra) too. The read-budget hook
  (`hooks/okuma_butcesi.py`) runs in Codex as well and counts only shell commands (file reads are shell commands
  there). Register it in Codex's `hooks.json` from `hooks/codex-parcasi.json`; Codex runs a new or changed hook only
  after you trust it with `/hooks` inside Codex (`hooks/README.md`).
- **Mechanical work:** the `scanner` role (Sol) takes script-output relay, test/log summaries, inventory and call
  traces; document/source verification is `researcher`'s. Luna not measured; lower-tier rule applies (only if the user
  says so) [profile].
- **Image generation:** the main session uses the built-in image tool directly (important images); a subagent on Sol
  if needed (routine images) [measured 2026-11-07, `gorsel_uret.py --model sol`, 30 s].
- **Superpowers version guard:** `hooks/superpowers_surum_bekcisi.py` also runs at SessionStart in Codex (registration
  and `/hooks` trust as for the read budget); it adds the "re-audit the table" note when versions differ.
- **Load reminder:** `hooks/orkestrasyon_hatirlatici.py` also runs in Codex at PreToolUse (`^(spawn_agent|Agent)$`);
  registration and `/hooks` trust as for the read budget (it runs only after you trust it).
- **Second opinion, Claude audit.** Fallback when `scripts/aile_elestirmen.py` cannot be used:
  ```bash
  claude -p --model opus --tools Read,Grep,Glob --permission-mode dontAsk --no-session-persistence \
    --strict-mcp-config --restricted "<audit brief>"
  ```
  State plainly in the brief that it is read-only and must not change files. Without Claude access there is no K2
  from Codex; record cross-family checks as `undetermined` rather than skipping them silently.

## Known limits

- **Codex read-only sandbox:** it restricts writes, not reads (reading is not confined to the working dir), and it
  cannot run tests ("No usable temporary directory") [measured 2026-11-07]. That is why K2 verifies the worker's
  evidence instead of running tests.
- **Claude `--restricted` and CLAUDE.md:** `--restricted` ignores settings files, but whether it also stops loading
  CLAUDE.md memory (user and project) is not verified. If it does not, the critic shares the author session's
  instructions and is that much less independent.
- **Python:** the scripts and hooks need Python 3.9+; `tomllib` (3.11+) is used only by the Codex branch of the
  superpowers version guard. On 3.9-3.10 that branch stays silent.
