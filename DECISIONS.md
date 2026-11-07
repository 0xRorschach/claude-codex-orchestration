# Decisions

This file keeps the reasons behind the orchestration rules so they are not lost when the rules are edited.
`skills/orchestration/SKILL.md` carries the mechanism; this file carries the history: when each rule was adopted, why, and what was measured.
Before changing a rule, read its entry here first. If the recorded reason still holds, the rule probably still holds too.
Entries are in date order. Measurements are tagged `[measured ...]`, documentation claims `[documented]`; rules whose source gives no reason are not recorded here.

### 2026-09-22 · Briefs to sub-agents stay short

- **Rule:** A sub-agent brief keeps only the reasoning that changes the work (measured facts, exact commands and values, the consequence of a constraint) and drops background that only helps understanding.
- **Why:** Long explanations belong in the conversation with the user, not in agent-to-agent traffic; the explanation discipline that governs user-facing text does not bind briefs, and a sub-agent does not redefine its goal.

### 2026-09-25 · Rules name model families, configs name full IDs

- **Rule:** Rule text refers to model families (the newest model of that family); version numbers appear only in dated records and in one resolution line, while configuration files carry full model IDs.
- **Why:** Family names keep the rules valid across model releases; Codex has no floating alias, so its configuration needs the full ID [measured 2026-09-25].

### 2026-09-25 · Agent type gate rejects built-in and fork agents

- **Rule:** A PreToolUse hook (`hooks/agent-tip-kapisi.py`) rejects `general-purpose`, `Explore`, `Plan`, `claude`, `fork`, an empty type and any non-Opus `model` parameter, including inside sub-agents.
- **Why:** The built-in agents carry no effort setting and silently inherit the main session's high effort; `fork` ignores the model setting and clones the main session.

### 2026-09-25 · Nested agents: helpers yes, managers no

- **Rule:** A sub-agent may open helper agents of the allowed types for its own task but never becomes an orchestrator; in practice only `worker` has the agent tool.
- **Why:** The orchestrator is the main session; a single orchestrator sub-agent running the whole loop would duplicate that role.

### 2026-09-25 · Superpowers decides how, this tree decides who

- **Rule:** Superpowers supplies the process (plan, test first, fresh agent per task, separate review, no unevidenced done); agent type and model come only from this tree, and on conflict this skill wins (added 2026-10-02).
- **Why:** The `general-purpose` slot in superpowers is a placeholder and its Model Selection is a savings default for users it does not know; superpowers itself ranks user instructions above skills.
- **Alternatives rejected:** Removing superpowers; an internal project's first large plan ran successfully through its process.

### 2026-09-25 · Codex has no advisor, and it is not consulted by hand

- **Rule:** The Claude advisor is not called manually from Codex sessions; on Codex, the branch-end cross-family critic and the main session's synthesis stand in for it.
- **Why:** Advisor capacity is scarce and is reserved for the Claude side.

### 2026-09-25 · Codex sub-agents get narrow briefs

- **Rule:** Codex sub-agent briefs are narrow and explicit with concrete acceptance criteria, and hard or precision work may stay in the Codex main session (exception kept 2026-10-17).
- **Why:** The Codex sub-agent family was observed to be weaker than Opus at the time; to be re-checked with new releases.

### 2026-09-26 · Cross-family audit only at key points

- **Rule:** A second-opinion audit runs once per key point (schema or state contract change, gate logic, hard-to-reverse decision, final draft before the user sees it, outward-facing output), never after every task, and never decides readiness.
- **Why:** [measured 2026-09-26, 5 audits in 20 h] new-finding curve 12, 5, 1, 2, 1; every brief asked whether the plan was ready and every report said no. The audit was not the slowdown; turning it into a gate was (the first audit did catch a real bug). Fewer audits must not mean fewer sub-agents: sub-agents absorb context and save time.
- **Alternatives rejected:** Audit as a readiness gate; repeated audit rounds until clean (a rising round count is treated as a design signal and the open gaps go to the user).

### 2026-09-26 · Execution method is not re-asked per plan

- **Rule:** The inline option of writing-plans is not offered; execution defaults to subagent-driven, while approval of plan content remains a separate question.
- **Why:** Execution method is a standing decision already recorded in the setup; asking it for every plan repeats a settled question.

### 2026-09-28 · Route search to `scanner`, judgment to `explorer`

- **Rule:** Lookup, call-site, map and output-summary tasks go to `scanner` (Sonnet); anything with judgment goes to `explorer`, and document verification stays with `researcher` on Opus.
- **Why:** [measured, n=2, blind scoring] Sonnet roughly matched Opus on search but made a factual error on document verification; review and implementation were not measured, so they stay on Opus.

### 2026-10-02 · Rules serve teamwork, not restriction

- **Rule:** At an important decision, add a genuinely different perspective: different information (fresh `explorer`), different role (a reviewer separate from the implementer) or different model family (cross-family critic).
- **Why:** A single agent sees the context only from its own path and can be misled by it; extra perspectives counter that. The advisor sees the whole conversation, so it is stronger but not independent, and asking the same agent twice is not a new view.

### 2026-10-02 · Advisor trigger follows decision type

- **Rule:** Whether to consult the advisor depends on the kind of decision, not on whether orchestration mode is active.
- **Why:** An important decision went without consultation because in-session orchestration was not running.

### 2026-10-02 · Parallelize independent work

- **Rule:** Before dispatching, extract dependencies; independent tasks, scenarios or questions go to separate sub-agents in the same turn (separate folder or worktree, separate output file, merge in the main session), with a reminder hook (`hooks/paralel-is-hatirlatici.py`).
- **Why:** Independent tests and tasks were being run one after another, which took longer; the instruction had to be repeated across sessions, so a hook now asks at every agent launch.

### 2026-10-02 · Concurrent agent cap of 15 is a threshold

- **Rule:** Up to 15 agents may run at the same time; exceeding it needs a stated reason, and the cap counts concurrent agents, not the session total (clarified 2026-10-04).
- **Why:** Cost (even an empty sub-agent costs about 26k tokens [measured, n=1]) and the main session's capacity to audit results; the technical limit is nesting depth (3 levels by default [documented]), not count. The previous cap was 10.
- **Alternatives rejected:** A hard wall.

### 2026-10-02 · Conflicts resolved in the main session, except scientific ones

- **Rule:** The main session resolves conflicts between agents, except in scientific or clinical decisions, where it weighs both views and presents them with its own recommendation to the user.
- **Why:** A clinical threshold chosen silently becomes a value nobody questions later.

### 2026-10-02 · Independent reviewer brief: question first, no conclusion

- **Rule:** A reviewer or second opinion receives question, context and evidence but not the main session's conclusion, plus the fixed task line `find the weakest point; if there is no significant weakness, say none`.
- **Why:** Reviewers drift toward a stated view; without the second clause every round is forced to produce findings and the convergence rule breaks. Evidence is requested as command, exit code, pass/fail counts, diffstat and file:line, with pointers instead of long logs.

### 2026-10-02 · Clean cross-family Codex call

- **Rule:** The fallback audit command runs Codex in a temporary home with hooks and memories disabled, ephemeral, with model, effort and sandbox stated on the command line and stdin closed (`< /dev/null`).
- **Why:** `--ignore-user-config` does not keep hooks and the user-level instruction file out, and the temporary home has no config; [measured 2026-10-02] instruction leakage 4/4 before, 0/4 with this pattern.

### 2026-10-08 · Haiku not adopted as scanner

- **Rule:** The `scanner` role stays on Sonnet; Haiku is not used as a single-artifact scanner.
- **Why:** [measured 2026-10-08, blind comparison, 9 runs] Haiku made more false absence claims than Sonnet (1-0).
- **Alternatives rejected:** Haiku as the scanner tier.

### 2026-10-08 · Evaluate cheap models as a tiered option

- **Rule:** When evaluating a new or cheaper model, design, measure and present tiered use by task type (single file or single output on the cheap model, multi-file traces on the strong one), not only whether it replaces a whole role.
- **Why:** In the Haiku pilot tiering was dismissed early as routing confusion and was not revisited when the data showed exactly that pattern.
- **Alternatives rejected:** All-or-nothing role replacement as the only question asked.

### 2026-10-11 · Advisor consulted at a core list of events

- **Rule:** The main session consults the advisor just before a fixed list of events (before the user sees an approach, spec or scientific option; before execution starts; before irreversible steps; when stuck), one call per event unless new evidence arrives, and logs one line per consultation in the project state file.
- **Why:** The advisor re-reads the caller's transcript uncached [documented], so cost grows with transcript size (one session: 119k to 652k) [measured]; retroactively on a long phase the core list meant about 7 calls and 3 M tokens versus 21 calls and 7.2 M for the full 12-event list. Separately, in 5 of 8 sessions the last consultation fell in the first 59% of the session [measured 2026-10-11, session logs]. The log line exists because advice text is opaque in logs.
- **Alternatives rejected:** The full 12-event list.

### 2026-10-11 · Advisor before cross-family audit

- **Rule:** For specs and scientific options, the advisor is asked first (is this the right approach) and the cross-family audit second (what is wrong in the final text), and they do not repeat each other's question.
- **Why:** The two answer different questions; asking both the same one wastes a scarce call.

### 2026-10-11 · Sub-agents may consult the advisor freely

- **Rule:** Sub-agents are not restricted from calling the advisor.
- **Why:** Most sub-agents are already Opus; no technical lock exists anyway, since `tools`/`disallowedTools` do not affect the server-side tool and the only off switch (`CLAUDE_CODE_DISABLE_ADVISOR_TOOL`) also disables it in the main session [documented + measured 2026-10-11].

### 2026-10-11 · Advisor call goes in its own message

- **Rule:** The advisor call is sent alone, never in the same message as another tool call, and output is written to disk before the call.
- **Why:** [measured 2026-10-11, n=3 sessions] an advisor call batched with other tool calls did not run and had to be resent; the mechanism is undocumented.

### 2026-10-17 · Main session does no active work

- **Rule:** The main session coordinates, decides, audits and talks to the user; when a delegated result is weak it re-delegates with a new brief or asks the advisor, and it never fixes findings itself.
- **Why:** Keep the main session's context from filling up so it can keep orchestrating.

### 2026-10-17 · Worktrees live inside the repo and are removed carefully

- **Rule:** Worktrees are opened in a gitignored `.worktrees/<name>` or the tool's in-repo folder (`.claude/worktrees/`), and after merge the opener scans `git status --porcelain --ignored`, archives non-reproducible ignored data, then runs `git worktree remove` without `--force` and deletes the branch only with `git branch -d`.
- **Why:** Sibling folders next to the repo look like separate projects; `git worktree remove` deletes gitignored files even without `--force` [measured 2026-10-17]; `-d` already refuses unmerged branches, so `-D` is never needed.

### 2026-11-03 · Multi-agent Workflow is proposed by the model, run on approval

- **Rule:** At a key point that does not fit one session or needs independent lenses, the agent proposes a Workflow itself (reason, agent count, estimated cost, limits; `explorer`/`worker` at medium, at most 2-3 lenses per finding) and runs it only after explicit approval.
- **Why:** On one task, different perspectives (fresh `explorer` plus a real measurement found 4 errors, the cross-family critic 1) caught what single-lens reviews missed; fan-out brings no gain on sequential work that shares one file.
- **Alternatives rejected:** An always-on fan-out mode (conflicts with the convergence rule, medium-effort delegation and the permission rule); treating the mere appearance of the mode's name in a message as permission.

### 2026-11-06 · Write the Codex credential back after a temporary-home call

- **Rule:** After a temporary-home Codex call, the refreshed credential file is copied back atomically with mode 0600, only if the real file has not changed since the call started.
- **Why:** The refresh token is single-use; if the renewed key stays in the temporary home, every later Codex call fails with a refresh-token-already-used error [measured 2026-11-06: in one session the first audit call passed, the second failed this way]. The wrapper script locks this write; the manual fallback block does not.

### 2026-11-07 · Active work versus allowed work, with a read budget

- **Rule:** The main session may write records and briefs, run engine and gate commands, commit, push, merge and call the cross-family critic, while reading files for discovery, running tests, converting documents and editing go to sub-agents; a PostToolUse hook (`hooks/okuma_butcesi.py`) adds a delegate-discovery note when the session's read output passes `ORCH_OKUMA_ESIGI` (default 40000 characters).
- **Why:** The earlier rule did not define active work, so Bash reading stayed the largest class of main-session work. Threshold: [measured 2026-11-07, n=107 main sessions] median Agent result 16k, median Bash work output 44k characters; 40k sits between them and warns in about half the sessions.

### 2026-11-07 · Mechanical work goes to `scanner`

- **Rule:** Tasks whose verdict comes from code or output (running a script and relaying its output, test or log summaries, inventories, symbol locations, call traces with the quoted line, checklist-based format checks) go to `scanner`, whose brief includes the line `do not write notes outside the template; fill only the requested fields`.
- **Why:** [measured 2026-11-07, blind comparison, n=3 per cell, 24 runs] accuracy Sonnet 96/96, Opus 95/96; off-template note errors Sonnet 1, Opus 7; Sonnet 26-34% faster. Document, API and source verification still stays with `researcher`.

### 2026-11-07 · Critic families: K1 same family, K2 different family

- **Rule:** Every delivery gets a same-family reviewer (K1, fresh `explorer`); a different-family critic (K2) is mandatory for multi-task plan execution, multi-file changes outside an engine, schema, state-contract or gate changes and outward-facing output, by default at branch end in parallel with the final `explorer` review.
- **Why:** In one multi-task plan execution the per-task reviews came back clean, while the branch-end reading found 8 real gaps (cross-family) and 4 (`explorer`) [documented]; same-family review alone is acceptable, but a different family must also look after relatively large work.

### 2026-11-07 · K2 model split: lighter model at task boundary

- **Rule:** Task-boundary K2 (only on tasks flagged `K2: evet` in the plan) uses the lighter Codex model (`--model sol`); branch-end and key-point K2 uses the stronger one (the script default); on Codex, K2 is Claude Opus.
- **Why:** [measured 2026-11-07, 10 deliveries x n=2, 5 known defects] catch rate 10/10 for all three models; false positives 2, 2 and 5 (lighter Codex, stronger Codex, Opus). The set was easy (ceiling effect) and cost was not measured.

### 2026-11-07 · K2 verifies evidence, it does not run tests

- **Rule:** The worker supplies test evidence (command, exit code, diff or review package) and K2 checks it against the spec, proposing reproduction steps if needed instead of running tests.
- **Why:** The Codex read-only sandbox cannot run tests (`No usable temporary directory`) [measured 2026-11-07] and the Claude direction runs with Read/Grep/Glob only [documented]; self-critique without test or execution output does not reliably improve accuracy [literature].

### 2026-11-07 · Codex role agents open with `fork_turns="none"`

- **Rule:** Codex role agents are spawned with `fork_turns="none"` and no `model` or `reasoning_effort` override; needed context goes into the brief.
- **Why:** [measured 2026-11-07, 59 sub-agent sessions] with `"none"` 28/28 ran on the role's model; with the field missing or `"all"` under a stronger parent 30/30 inherited the parent's model; one `"all"` session under a lighter parent stayed light. The source-code basis was not verified.

### 2026-11-07 · Superpowers stays a separate plugin

- **Rule:** Superpowers is not merged into this skill; conflicts are resolved through the mapping table, and a SessionStart hook (`hooks/superpowers_surum_bekcisi.py`) flags when the installed version differs from the table's version.
- **Why:** Merging would fork a versioned plugin and lose upstream updates; the version watcher guards against the table going stale.
- **Alternatives rejected:** Merging superpowers into this skill.

### 2026-11-07 · Image generation goes to Codex models

- **Rule:** Any task that needs an image uses a Codex model through `scripts/gorsel_uret.py` (stronger model for important or outward-facing images, lighter model for routine ones); Codex's built-in image tool draws, the model shapes prompt and checks.
- **Why:** Claude models have no image generation; the image tool works on the lighter model too [measured 2026-11-07, `gorsel_uret.py --model sol`, 30 s].

### 2026-11-07 · Codex as a narrow implementer

- **Rule:** On narrowly briefed mechanical work, the lighter Codex model may act as implementer in its own worktree with concrete acceptance criteria and `worker`-style test evidence, while hard or precision work stays with the Opus `worker`.
- **Why:** Loosened on observation only; the planned pilot was not run, so this rule is unmeasured.
