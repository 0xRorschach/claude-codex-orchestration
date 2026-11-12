# Cross-family scripts

A model reviewing its own work with a model from its own family shares the same blind spots. These scripts send the
work to the opposite family: from Claude to Codex (Astra, Sol) or from Codex to Claude (Opus). They use only the
Python standard library and need Python 3.9+. Locks are taken with `fcntl`, so this is for macOS and Linux.

| File | What it does |
|---|---|
| `codex_cagri.py` | Core that calls Codex cleanly (`cagir(...)`) |
| `claude_cagri.py` | Core that calls Claude read-only, same contract |
| `aile_elestirmen.py` | Sends a brief to the opposite family, gets structured findings |
| `gorsel_uret.py` | Produces a PNG with Codex's image tool |
| `modeller.json` | Family name -> full Codex model id |
| `elestirmen_sema.json` | JSON schema of the critique output |
| `elestirmen_kayit_eki.py` | Appends the decision (`· applied / parked (why)`) to a cross-family record line |

## Use from Claude

In a Claude Code session the opposite family is Codex; no need to pass `--aile`.

```bash
python3 aile_elestirmen.py --effort medium --brief brief.md --cikti findings.json \
  --kayit docs/STATE.md --olay "plan"
python3 aile_elestirmen.py --model sol --effort high --brief brief.md --cikti findings.json \
  --calisma-dizini ../project
python3 gorsel_uret.py --istem "a plain flow chart" --cikti figure.png -i draft.png
```

## Use from Codex

In a Codex session the opposite family is Claude (Opus). Claude works only with the `Read`, `Grep`, `Glob` tools and
cannot change files. It runs in `--restricted` mode: user, project and local settings files (and the hooks there) are
not loaded, and file tools are confined to the working folder.

Known limit (not verified): `--restricted` ignores settings files, but it is not documented to disable CLAUDE.md
memory. If it does not, the critic reads the user's `~/.claude/CLAUDE.md` rules and the project CLAUDE.md in the
working folder; it shares instructions with the session that wrote the reviewed work, which reduces its independence
to that extent. `--safe-mode` may disable this, but its behaviour together with `--restricted` and `-p` was not
measured.

```bash
python3 aile_elestirmen.py --effort medium --brief brief.md --cikti findings.json
```

In a Codex main session this script is not needed for images: the image tool can be used directly. `gorsel_uret.py`
is for reaching Codex's image tool from Claude.

## Behaviour

- **Direction:** detected from session environment variables (`CLAUDECODE` for Claude, `CODEX_THREAD_ID` /
  `CODEX_SESSION_ID` / `CODEX_CI` for Codex). If none is present, or both are, the script stops and asks for
  `--aile codex|claude`.
- **Working folder:** `--calisma-dizini` (default: the current working directory) is passed explicitly in both
  directions: `-C` for Codex, the process working directory for Claude. The critic reads this folder. In the Codex
  direction reading is not confined to this folder: `--sandbox read-only` restricts writing, not reading; the
  credential copy in the temporary home is readable too (reading outside the folder was not tested); do not put
  secrets in the brief or the working folder. In the Claude direction `--restricted` confines file tools to this
  folder.
- **Brief:** unless "weakest" and "none" both appear, this is appended: "Task: find the weakest point. If there is no
  significant weakness, say 'none'." No "is it ready" question is added to the brief; the readiness decision belongs
  to the caller.
- **Output:** `{"zayiflik_var", "bulgular": [{"bulgu", "onem", "kanit", "oneri"}], "belirsizlik"}` (has weakness,
  findings: finding, severity, evidence, suggestion; uncertainty), with `onem` one of `yuksek` (high), `orta`
  (medium) or `dusuk` (low). A response that does not match the schema is written raw and the result counts as
  `undetermined` (exit 3). A valid result whose record lock could not be taken returns exit 6 (see Record lock).
- **Record:** with `--kayit`, one line is appended to the file:
  `Cross-family 2026-01-02 03:04 · plan · astra (gpt-6-astra) · medium · findings 2 (high 1) · findings.json`
  The model field has the form `family (full id)` in both directions. In the Claude direction the full id is read
  from the event stream's `system/init` event; in the Codex direction the event stream does not carry the model, so
  the requested id from `modeller.json` is written. If no full id is found, only the family name is written. An
  invalid result writes `undetermined (<reason>)` in place of the findings count.
  The record file is the project's STATE or ledger (the plan ledger in SDD), not a scratchpad: a scratchpad goes away
  with the session, and the effect can no longer be counted. `--olay` must be one line without the ` · ` field
  separator; otherwise the call stops before the critic runs (exit 2), because a "plan" lookup would also match a
  "plan · phase 2" line. A valid result whose line cannot be written for another file system reason returns exit 7
  (the line is printed to stderr).
- **Decision suffix:** once the findings are weighed, the decision is appended to the end of the same line; no new line
  is opened:
  `python3 elestirmen_kayit_eki.py --kayit docs/STATE.md --zaman "2026-01-02 03:04" --olay "plan" --karar applied|parked [--neden "..."]`
  (`--neden` is required for `parked`). The line is found by time + event (leading indentation and a `- ` list marker
  are allowed; LF/CRLF is kept).

  | Exit | Meaning |
  |---|---|
  | 0 | appended |
  | 1 | line not found (also when the record file is missing) |
  | 2 | usage error (also `--olay` with ` · ` or a line break, `--neden` with a line break; the record line stays one line) |
  | 4 | several lines matched; fix the file by hand |
  | 5 | the line already has a decision (`· applied`, `· not applied`, `· parked`); the one exception: `applied` is appended to a line whose only decision is `parked` (parked -> applied, once) |
  | 6 | the record lock was not taken within 10 s, or the lock file could not be opened; nothing appended |
  | 7 | the record could not be read (permissions, non-UTF-8 content, a folder and the like) or not written (temporary file, replace, another file system error); distinct from "line not found"; no traceback |

  On every error code the file is left unchanged. The write goes through a temporary file + `os.replace`; the old file
  mode is kept, and if the record is a symlink the real target is written and the link stays.
- **Record lock:** the decision suffix (read-modify-write) and the `aile_elestirmen.py --kayit` append take the same
  advisory lock: `${XDG_CACHE_HOME:-~/.cache}/orchestration/kayit-kilit/<first 16 hex digits of the sha256 of the
  record's real path>.lock` (`fcntl.flock`; the same cache base as the hooks; symlinks are resolved, so a link and its
  target take the same lock). The lock file is permanent and lives in the cache, so no `.lock` file lands in the
  project repository. The lock needs write access to that cache folder: in a sandbox without it the lock folder cannot
  be created or the lock file cannot be opened, the exit code is 6 and the reason goes to stderr. When `aile_elestirmen.py` cannot take the lock, the result is
  already written to `--cikti`; the line is not written, it is printed to stderr, and the exit code is 6. The `--kayit`
  append follows the file's line ending (CRLF for a CRLF file).
- **Credentials (Codex):** every call uses a temporary `CODEX_HOME` containing only a 0600 copy of `auth.json`; user
  configuration, hooks and memory do not leak in. If Codex refreshes the token during the call, the new copy is
  written to the real file atomically; if the real file changed in another process meanwhile, it is not overwritten
  and a warning is given. Comparison and write run under the `auth.json.lock` lock; this lock file stays in the
  Codex home permanently. The lock only coordinates this script's own calls: the Codex CLI itself does not take it.
  If another Codex session with the same account runs during a critic call, a refreshed token can be overwritten,
  or not written back, because there is an unlocked window between the comparison and the write. Advice: do not
  keep another Codex session open while a critic call runs; if a credential error follows, run `codex login`. A "refresh token was already used" error returns exit 77 and is not retried: `codex login`
  is needed. This error is searched only in stderr and in the event stream's error events (`error`, `turn.failed`,
  an error item); appearing in a model message or in command output does not return 77.
- **Environment (Claude):** allow list. Passed: `PATH`, `HOME`, `USER`, `LOGNAME`, `SHELL`, `TERM`, `LANG`, `LC_*`,
  `TMPDIR`, proxy and certificate variables, `ANTHROPIC_*`, `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CONFIG_DIR`,
  `CLAUDE_CODE_USE_BEDROCK` / `_VERTEX` / `_FOUNDRY`. `AWS_*` passes only while `CLAUDE_CODE_USE_BEDROCK` is set;
  `GOOGLE_*`, `CLOUD_ML_*` and `VERTEX_REGION_*` only while `CLAUDE_CODE_USE_VERTEX` is set. Parent session markers
  (`CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT` and the like) do not pass. The Codex direction uses a separate filter:
  parent session markers are dropped, everything else passes.
- **Image:** the model writes the file into a temporary working folder (sandbox `workspace-write`, write access only
  in that folder), the script copies it to `--cikti`. If the file is missing, the newest PNG in the temporary home's
  `generated_images/` folder is used. Model choice: `astra` (default) for important or outward-facing images, `sol`
  for routine images.

## Environment variables

| Name | Meaning |
|---|---|
| `ORCH_CODEX_BIN`, `ORCH_CLAUDE_BIN` | Binary to run (defaults `codex`, `claude`). An absolute path must be an executable file; a bare name is looked up on `PATH`; a relative path is rejected. Use these to bypass a wrapper script that is earlier on `PATH`. |
| `CODEX_HOME` | Real Codex home (default `$HOME/.codex`), only the `auth.json` source. |
| `ORCH_CLAUDE_EK_ORTAM` | Variable names to pass to the Claude call in addition to the allow list, comma-separated. |
| `ORCH_OLAY_DIZINI` | Event stream files. Default `${XDG_STATE_HOME:-$HOME/.local/state}/orchestration/olaylar`. |

## Model ids

`modeller.json` maps the family name to the full id. When a new version comes out, only this file changes. The
Claude direction uses the `opus` alias; the CLI resolves it to the family's newest model.

## Tests

No real model is called; the tests run with the fake `codex` and `claude` binaries under `tests/`, selected through
`ORCH_CODEX_BIN` and `ORCH_CLAUDE_BIN`. From the `scripts` folder of the skill (`skills/orchestration/scripts` in this
repo):

```bash
python3 -m unittest discover -s tests -t tests
```
