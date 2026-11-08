# orchestration hooks

This folder holds the hooks (a hook is a script the tool runs by itself on a given event) that support the
orchestration skill. There are two kinds:

- **Shared hooks** (`superpowers_surum_bekcisi.py`, `okuma_butcesi.py`, `orkestrasyon_hatirlatici.py`): run in both Claude Code and Codex CLI,
  never block anything, and only add a one-line note to the model context. On any error they exit silently
  (exit code 0) and do not break the session, including when the helper module cannot be loaded or stdout is closed.
- **Claude Code hooks** (`agent-tip-kapisi.py`, `paralel-is-hatirlatici.py`): run on the `Agent`/`Task` tool. The
  type gate can deny a subagent call; the parallel-work reminder only adds context.

Requirements: Python 3.9+ (the Codex version filter needs 3.11+). Locks are taken with `fcntl`, so this is for
macOS and Linux.

## What they do

### superpowers_surum_bekcisi.py (SessionStart)

The mapping table in orchestration SKILL.md > "With superpowers" is written against a specific superpowers
version. That version lives in `superpowers_surum.json`:

```json
{"tablo_surumu": "7.0.0", "tarih": "2026-11-07"}
```

At session start the installed superpowers version is read. If it differs, this note is added:

> superpowers 7.1.0 is installed, but the orchestration mapping table was written for 7.0.0: re-check the table (orchestration > With superpowers)

If the versions match or the version cannot be read, nothing is written. After re-checking the table, update the
`tablo_surumu` and `tarih` fields in `superpowers_surum.json`.

Where the installed version is read from:

- Claude Code: `~/.claude/plugins/installed_plugins.json` (or `$CLAUDE_CONFIG_DIR/plugins/`), `superpowers@...`
  keys. An install disabled in `settings.json > enabledPlugins` is not counted.
- Codex: `~/.codex/plugins/cache/<marketplace>/superpowers/<version>/.codex-plugin/plugin.json` (or `$CODEX_HOME`).
  A marketplace with `enabled = false` in `config.toml` is not counted. This filter needs `tomllib` (Python 3.11+);
  on older Python the Codex branch reads no version and stays silent, so it never warns based on a disabled install.
- If there are several installs, the highest version wins.

### okuma_butcesi.py (PostToolUse)

Sums, per session, the character count of the text that reaches the model in the main session's Read, Bash, Grep and
Glob output (allowlist: Bash `stdout` + `stderr`; Read `file.content`; Grep `content` + `filenames`; Glob `filenames`;
Codex shell output is plain text and is counted as is). Read counts the raw `file.content`; the line number prefix the
model sees (`cat -n` style) is not added, so Read is slightly under-counted (not measured). The `bashEditDiff` field
that Claude Code adds to the Bash response does not reach the model and is not counted. A Read image (`base64`) counts
0; another Read shape without `content` (PDF parts, for example) falls back to the recursive sum. Claude Code saves
large Bash output to a file and sends the model a short preview (the response carries `persistedOutputPath`); stdout
then counts at most 2500 characters (measured n=8: counted 27,618-30,000, preview sent to the model 1,930-2,533). A
response with none of these fields is counted by summing all its strings (over-counting is cheaper than missing
silently). When the total crosses the threshold, and then once at each multiple (2x, 3x ...), this note is added:

> The main session has collected ~41k characters of read/command output this session. Delegate exploration and verification to explorer/scanner (orchestration > Delegation).

- Threshold: `ORCH_OKUMA_ESIGI` (characters, default 40000). Rationale: in a measurement the main session's Bash work
  output was twice the size of the subagent results; the measured median starting context was about 80k tokens.
  That measurement counted every field of the response, so it may be inflated by `bashEditDiff`; not yet re-measured
  with the allowlist.
- Silent inside a subagent (a helper agent opened by the main session). A subagent's own reading is its job.
- Not counted (Bash commands only): `git commit`, `git push`, a single-commit `git log` (`-1`, `-n 1`, `-n1` or
  `--max-count=1`; alongside only `--format=`, `--pretty=`, `--oneline`, `--date=`; any other flag such as `-p`,
  `--stat`, `--numstat`, `-n 500` is counted), `codex exec`, `aile_elestirmen.py`, heredocs writing to a `.md` file
  (like `cat > docs/STATE.md <<'EOF'`), `--help`, `--version` (even with trailing punctuation). Reading a `.md` file
  with Read is counted.
- Extra exempt scripts: `ORCH_MUAF_BETIKLER` takes comma-separated file names (for example
  `ORCH_MUAF_BETIKLER=notes.py,sync.py`). A script is exempt when it is the command (`sync.py ...`) or the first
  non-flag argument of a `python*` interpreter (`python3 ~/tools/notes.py ...`); only the base name is compared.
- Compound commands: after heredoc bodies are removed (a `<<END` inside quotes is not a heredoc: `echo "x <<EOF"`
  does not swallow the following lines), the command is split on `&&`, `||`, `;`, `|`, a single `&` (background)
  and newlines outside quotes; the `2>&1`, `>&2`, `&>` redirections do not split (`git push & cat big.log` is
  counted). A command is exempt only if all its parts are: `cat big.log; git commit` is counted. A `cd` part is
  neutral since it produces no output (`cd /a && git push` is not counted). The pattern is matched in command
  position: `rg 'git push' src` is counted. Piping an exempt command's output through a filter
  (`codex exec ... | tail`) is counted, because the `tail` part is not exempt.
- A command longer than 16 KB is not parsed and is not exempt: parsing slowed down quadratically on large input
  (2 MB heredoc 33-71 s). What is counted is the output, not the command itself.
- State file: `<plugin data>/okuma/<session_id>.json` when `CLAUDE_PLUGIN_DATA` or `PLUGIN_DATA` is set (plugin
  mode), otherwise `${XDG_CACHE_HOME:-$HOME/.cache}/orchestration/okuma/<session_id>.json`. So parallel calls do not lose
  counts, updates run under a `<session_id>.lock` lock. `.json`, `.lock` and leftover `.tmp` files older than 7 days
  are removed silently.
- In Codex, file reads are also shell commands, so only `Bash` is counted there; Read, Grep and Glob have no Codex
  counterpart.

### orkestrasyon_hatirlatici.py (PreToolUse)

When the main session opens a subagent (Claude Code: `Agent` or `Task`; Codex: `spawn_agent`) and the orchestration
skill was not loaded in this session, this note is added once per session:

> The orchestration skill was not loaded in this session. Load it before opening subagents (Skill: orchestration); the way of working is defined there.

The call is never blocked. Why: in a measurement of 152 sessions (2026-11-07) the skill was never loaded in 44.1% of
sessions; in every session where it loaded on its own, it loaded before the first subagent.

- Traces counted as loaded, in the raw text of a transcript (`transcript_path`) line: in Claude Code a Skill tool
  call (`"skill":"orchestration"`, also with a plugin prefix such as `orchestration:orchestration`), the
  `Base directory for this skill: .../orchestration` text where the skill body is injected, and
  `<command-name>/orchestration</command-name>` (also with a plugin prefix). Codex has no Skill tool: a tool-call
  record (`custom_tool_call` or `function_call`) that contains `/orchestration/SKILL.md` (the model reads the file
  with a shell command), or the built-in `<skill>\n<name>orchestration` injection. The bare word "orchestration"
  does not count: CLAUDE.md and briefs carry it often. Codex's skill list at session start does not count either.
- Speed: the transcript is read line by line as bytes from the start, reading stops at the first match, no JSON is
  parsed. Measured (2026-11-07): 0.14-0.17 s on a 52 MB synthetic transcript without a match, 0.06 s on a 45 MB real
  transcript.
- State: `hatirlatici/<session_id>` in `$ORCH_LOG_DIR`, else `$CLAUDE_PLUGIN_DATA` / `$PLUGIN_DATA`, else
  `${XDG_CACHE_HOME:-$HOME/.cache}/orchestration/hatirlatici/`. The file is created with `O_EXCL` before the scan: of
  several parallel subagent calls in the same message only one scans, so at most one warning appears. The result
  (loaded or warned) holds for the whole session; if the transcript cannot be read, no warning is given and the next
  call retries. State files older than 7 days are removed.
- Silent inside subagents (`kanca_girdisi.alt_ajan_mi`).
- Claude Code: the note (additionalContext) arrives with the first Agent call's result, so it shapes the later
  spawns, not the first one.
- Codex tool name: the docs say `spawn_agent` is seen in PreToolUse as a local function tool and also matches the
  `Agent` alias; in rollout files the call appears as `spawn_agent` (namespace `collaboration`) [measured,
  codex-cli 0.166.0]. Matcher `^(spawn_agent|Agent)$`. That the hook really fires in Codex is not verified: a new
  hook does not run until it is approved with `/hooks`.

### agent-tip-kapisi.py (PreToolUse, Claude Code)

Enforces the agent type and model tree on every `Agent`/`Task` call, including calls made from inside a subagent:

- A `model` parameter is denied unless it is `opus` or a full Opus id starting with `claude-opus-` (for example
  `claude-opus-4-1`; case-insensitive): the subagent's model must come from its agent file. `claude-opus` without a
  version, `sonnet`, `haiku` and any other value are denied.
- The general-purpose types `general-purpose`, `Explore`, `Plan`, `claude`, `fork` and an empty type (which means
  `general-purpose`) are denied (case-insensitive): they inherit the main session's effort or ignore the model
  setting. The denial message suggests `scanner`, `explorer`, `worker` or `researcher`.
- A plugin-qualified type `<plugin>:<agent>` (for example `orchestration:explorer` when this repo is installed as
  a Claude Code plugin) is checked by its last part: `orchestration:explorer` passes, `x:general-purpose` is denied.
- Every other type passes, including plugin agents and narrow built-ins such as `claude-code-guide`.
- The denial message quotes the rule book path: `${CLAUDE_PLUGIN_ROOT}/skills/orchestration/SKILL.md` in plugin
  mode, otherwise `SKILL.md` one folder above this script.
- Every denial message ends with how to turn the gate off (`ORCH_TIP_KAPISI=0`).
- Off switch: `ORCH_TIP_KAPISI=0` lets every call pass and logs nothing.
- Denials are logged as one JSON line (without the prompt) to `ret.jsonl` in `$ORCH_LOG_DIR`, else
  `$CLAUDE_PLUGIN_DATA` / `$PLUGIN_DATA`, else `~/.local/share/agent-tip-kapisi/`. A log write failure never changes
  the decision.

### paralel-is-hatirlatici.py (PostToolUse, Claude Code)

After the main session starts a subagent, adds a reminder to start any independent work in the same turn with
separate subagents, or to state in one sentence why there is none. Silent inside subagents (input carries
`agent_id`). Never blocks.

- Off switch: `ORCH_PARALEL_HATIRLATICI=0` (no reminder, no log line).
- Threshold quoted in the reminder: `ORCH_PARALEL_ESIK` (concurrent agents, default 15; an invalid or non-positive
  value falls back to 15).
- Each trigger writes one tab-separated line (time, session id, tool, `subagent_type`, the first 60 characters of
  `description`) to `paralel-is-hatirlatici.log` in `$ORCH_LOG_DIR`, else `$CLAUDE_PLUGIN_DATA` / `$PLUGIN_DATA`, else
  `~/.claude/hooks/`.
- Same turn: a trigger within 5 s of the session's last warning does not warn again but is still logged. This
  groups agent calls that complete at about the same time (for example agents started in the background in one
  message) into one warning; foreground agents of the same message that finish at different times can each warn. The window runs from the last warning, so a suppressed trigger does not extend it.
  The last warning time is kept in `paralel-is/<session_id>.json` under `$ORCH_LOG_DIR`, else the plugin data folder,
  else `${XDG_CACHE_HOME:-$HOME/.cache}/orchestration/`, read and written under a `flock` lock; files older than 7 days
  are removed. If the state cannot be written, or on any unexpected error, the hook warns; the exit code is always 0.

### kanca_girdisi.py

Shared helper of the three shared hooks: reading stdin, telling Claude Code from Codex, subagent detection, output
format. The tool difference is kept in one place here. The last argument of the registration command (`claude` or
`codex`) names the tool; without an argument, input that carries `turn_id` is treated as Codex.

## How to register

This folder registers nothing by itself.

- Claude Code: add the `hooks.SessionStart`, `hooks.PreToolUse` and `hooks.PostToolUse` entries from
  `settings-parcasi.json` to the `hooks` object in `~/.claude/settings.json` (without deleting existing entries, in
  the same event lists).
- Codex: add the entries from `codex-parcasi.json` to the `hooks` object in `~/.codex/hooks.json`. Codex runs a new
  or changed hook only after it is marked trusted: after registering, review and approve the hook with `/hooks`
  inside Codex. The two Claude Code hooks have no Codex counterpart.

`timeout` in the entries is in seconds (read budget and load reminder 5, the others 10; Claude Code hook docs: "Seconds before
canceling", default 600 for command hooks). The commands use `python3` and `$HOME`; if the skill lives elsewhere,
change the path. No matcher is given for SessionStart: the hook also runs on resume and after compaction, so the
warning shows up after compaction too.

## How to disable

Without removing the registration, via environment variables:

- `ORCH_OKUMA_BUTCESI=0`: the read budget hook does nothing.
- `ORCH_SURUM_BEKCISI=0`: the version watcher does nothing.
- `ORCH_HATIRLATICI=0`: the orchestration load reminder does nothing.
- `ORCH_TIP_KAPISI=0`: the subagent type gate lets every call pass.
- `ORCH_PARALEL_HATIRLATICI=0`: the parallel-work reminder does nothing.

Set them in the environment the tool starts in (for example your shell profile). This works the same in every install mode. In plugin mode the hook entries live in the plugin's
own `hooks/hooks.json`, not in your `settings.json` / `hooks.json`, so the environment switch is the way to turn one
hook off; to remove all of them, uninstall the plugin (`./install.sh --uninstall`). After a user-level install,
`./install.sh --uninstall` removes the entries it added; editing `settings.json` / `hooks.json` by hand also works.

## Environment variables

| Name | Meaning |
|---|---|
| `ORCH_OKUMA_ESIGI` | Read budget threshold in characters (default 40000). |
| `ORCH_OKUMA_BUTCESI` | `0` disables the read budget hook. |
| `ORCH_MUAF_BETIKLER` | Extra exempt script file names for the read budget, comma-separated. |
| `ORCH_SURUM_BEKCISI` | `0` disables the version watcher. |
| `ORCH_HATIRLATICI` | `0` disables the orchestration load reminder. |
| `ORCH_TIP_KAPISI` | `0` disables the subagent type gate (every call passes, nothing is logged). |
| `ORCH_PARALEL_HATIRLATICI` | `0` disables the parallel-work reminder. |
| `ORCH_PLUGINS_DIR`, `ORCH_SURUM_TABLOSU` | Override the plugin folder and the version table path (tests, other layouts). |
| `ORCH_PARALEL_ESIK` | Concurrent-agent threshold quoted by the parallel-work reminder (default 15). |
| `ORCH_LOG_DIR` | Folder for the type gate and parallel-work reminder logs and the load reminder state (wins over the plugin data folder). |
| `CLAUDE_PLUGIN_ROOT` | Set by Claude Code in plugin mode; locates the rule book quoted by the type gate. |
| `CLAUDE_PLUGIN_DATA`, `PLUGIN_DATA` | Plugin data folder; used for read budget and load reminder state and hook logs when set. |

## Tests

From the skill folder (`skills/orchestration` in this repo, or wherever the skill is installed):

```sh
python3 -m unittest discover -s hooks/tests -v
```

On Python 3.10 and older the Codex version watcher's warning tests are skipped (no `tomllib`).

The tests run the hooks in a subprocess with the real input format; they use temporary `HOME`, `XDG_CACHE_HOME`,
`CODEX_HOME` and `ORCH_LOG_DIR` and do not touch the real configuration.

## Known limits

- The Claude Code docs say the `agent_id` field arrives inside a subagent, but do not state explicitly that it is
  absent in the main session. As a fallback, `/subagents/` is searched for in `transcript_path`.
- The Codex docs do not list `agent_id` in the PostToolUse input and say subagent hooks use the main session's
  `session_id`. So the hook reads the first line of the `transcript_path` transcript: a subagent transcript contains
  `source.subagent` or `parent_thread_id`. If there is no transcript, it cannot be read, or its first line is not
  `session_meta`, the distinction is undetermined and the call is not counted (silent): a false warning costs more
  than a missed one. The price is that a warning can be missed in a Codex main session with an unreadable
  transcript. Which transcript Codex passes in a subagent's PostToolUse is not documented and not verified.
- The `tool_response` shapes are not documented; they were measured from transcripts (2026-11-08): Grep
  `{content, filenames, mode, numFiles, ...}` (n=32), Glob `{filenames, ...}` (n=3); in Grep content mode the count
  matches what the model sees, `filenames` is empty, no double count (30 results). If the shape differs, the fallback
  sums every string in the response.
- Load reminder: if Skill and a subagent are called in parallel in the same message, the Skill result may not be in
  the transcript yet; one false warning can appear. In a resumed session an earlier load also counts. In Codex, if
  the transcript header cannot be read, the call is treated as a subagent and the warning can be missed (same policy
  as the read budget). If the output of a command that scans transcripts carries exactly the
  `"text":"Base directory for this skill: .../orchestration` form, it can be taken for a load.
