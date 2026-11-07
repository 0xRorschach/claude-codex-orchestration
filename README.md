# claude-codex-orchestration

An orchestration skill, typed subagents and hooks for Claude Code and Codex CLI: the main session plans and reviews, subagents do the work, and a model from the other family critiques it.

![Flow diagram: the main session plans and briefs, typed subagents do the work, a same-family review (K1) checks each task, a cross-family critic (K2) checks key points, and irreversible actions wait for user approval](docs/assets/orchestration-flow.gif)

Static version: [docs/assets/orchestration-flow.svg](docs/assets/orchestration-flow.svg)

## What it does

- **The main session orchestrates.** It plans, decides, writes briefs, reviews what comes back and synthesizes one answer. It does no hands-on work (exploring, editing, testing); that goes to subagents, so its context stays free for coordination.
- **Typed subagents** at medium effort: `explorer` (read-only judgement: code review, spec checks), `worker` (applies a decided change and runs its tests), `researcher` (checks current library, API and CLI behaviour), `tarayici` (fast read-only search, maps and output summaries). General-purpose agent types are not used.
- **K1: same-family review** after each task, by a fresh subagent.
- **K2: cross-family critic.** From a Claude session the work goes to Codex (Astra or Sol); from a Codex session it goes to Claude Opus. It runs through `skills/orchestration/scripts/aile_elestirmen.py` and is mandatory for multi-task plans, multi-file changes, schema or gate changes and outbound output.
- **Advisor** (Claude only, optional): consulted before declaring work done.
- **Irreversible actions** (push, deleting untracked files, writing outside the workspace or to an external system) need the user's approval.
- **Hooks:** agent-type gate, parallel-work reminder, read budget for the main session, superpowers version guard, and a load reminder when a subagent is opened before the skill was loaded.
- **Image generation** through Codex's image tool (`skills/orchestration/scripts/gorsel_uret.py`).

The full rule book is `skills/orchestration/SKILL.md`; the reasons behind the rules are in `DECISIONS.md`.

## Requirements

- Claude Code and/or Codex CLI. It works with only one of them; the cross-family critic needs both.
- Python 3.9+. The Codex branch of the superpowers version guard needs 3.11+ (`tomllib`); below that it stays silent. Locks use `fcntl`, so macOS and Linux.
- The [superpowers](https://github.com/obra/superpowers) plugin is recommended. It is a separate project (MIT); this skill carries only a mapping table to it.
- Model access. Defaults are Opus and Sonnet on the Claude side and `gpt-6-astra` / `gpt-6.1-sol` on the Codex side. Change them in `skills/orchestration/scripts/modeller.json` and in the agent files (`agents/*.md`, `codex/agents/*.toml`).

## Install

Pick one mode. Do not install both the plugin and the user-level copy: the skill and hooks would load twice. `install.sh` refuses to do that.

### Claude Code (native plugin)

```
/plugin marketplace add OWNER/claude-codex-orchestration
/plugin install orchestration@claude-codex-orchestration
```

From the shell:

```sh
claude plugin install orchestration --marketplace OWNER/claude-codex-orchestration
```

Plugin agents appear with the plugin prefix: `orchestration:explorer`, `orchestration:worker`, `orchestration:researcher`, `orchestration:tarayici`. The agent-type gate checks the last part, so these pass.

### Codex

```sh
codex plugin marketplace add OWNER/claude-codex-orchestration
codex plugin add orchestration@claude-codex-orchestration
```

Codex plugins cannot ship agent roles, so copy `codex/agents/*.toml` to `~/.codex/agents/` (or use `install.sh`, below). Then open `/hooks` in Codex once and approve the new hooks: Codex skips hooks that are not trusted.

Updating: Claude Code reads the plugin from the clone in place, so `git pull` is enough there. Codex reads a cached copy of the plugin: after `git pull`, run `codex plugin add orchestration@claude-codex-orchestration` again (and approve changed hooks with `/hooks`).

### One step for both

```sh
git clone https://github.com/OWNER/claude-codex-orchestration
cd claude-codex-orchestration
./install.sh
```

By default this installs plugin mode from the local clone for the tool(s) it finds and copies the Codex roles. Keep the clone: Claude Code reads it in place, so `git pull` updates it there; Codex keeps a cached copy, so after `git pull` run `codex plugin add orchestration@claude-codex-orchestration` again. In `--user-level` mode the skill is a copy: run `./install.sh --user-level` again after `git pull`.

Options:

| Option | Effect |
|---|---|
| `--plugin` | Default. Registers the clone as a local marketplace, installs the plugin in each tool found and copies the Codex roles. |
| `--user-level` | No plugin. Copies the skill into `~/.agents/skills`, the agents and roles into `~/.claude/...` and `~/.codex/...`, and registers the hooks; existing config files are backed up first. |
| `--dry-run` | Shows what would change, changes nothing. |
| `--uninstall` | Removes what the script installed. |
| `--claude-only` | Claude Code only. |
| `--codex-only` | Codex only. |
| `--help` | Prints the usage text. |

`--plugin`, `--user-level` and `--uninstall` are modes: pick one. `--claude-only` and `--codex-only` exclude each other.

Exit codes: `0` done (or nothing to do), `1` missing prerequisite (for example neither `claude` nor `codex` found, or Python below 3.9), `2` usage error (unknown option, or `--claude-only` with `--codex-only`), `3` would install twice (plugin and user-level copy together).

### Verify

```sh
claude plugin details orchestration@claude-codex-orchestration
codex plugin list
```

## Profile

Some defaults are preferences, not mechanism: for example, lower model tiers only on request, a threshold of 15 concurrent agents, Workflow (multi-agent scripts) only with explicit permission. `profile/profile.example.md` lists them with how to change each. Copy what you want into your CLAUDE.md (Claude Code) or AGENTS.md (Codex); lines there take precedence over the skill's defaults.

## Configuration

Environment variables (full details in `skills/orchestration/hooks/README.md` and `skills/orchestration/scripts/README.md`):

| Name | Used by | Meaning | Default |
|---|---|---|---|
| `ORCH_OKUMA_ESIGI` | read budget hook | Threshold in characters of read/command output in the main session; the note repeats at each multiple. | `40000` |
| `ORCH_OKUMA_BUTCESI` | read budget hook | `0` disables the hook. | on |
| `ORCH_MUAF_BETIKLER` | read budget hook | Extra exempt script file names, comma-separated (base name compared). | none |
| `ORCH_SURUM_BEKCISI` | superpowers version guard | `0` disables the hook. | on |
| `ORCH_HATIRLATICI` | load reminder | `0` disables the hook. | on |
| `ORCH_PARALEL_ESIK` | parallel-work reminder | Concurrent-agent threshold quoted in the reminder; invalid or non-positive values fall back to the default. | `15` |
| `ORCH_LOG_DIR` | agent-type gate, parallel-work reminder, load reminder | Log folder (and the load reminder's state); wins over the plugin data folder. | plugin data folder, else a per-hook folder under the home directory |
| `ORCH_CODEX_BIN` | cross-family scripts | Codex binary to run. An absolute path must be executable; a bare name is looked up on `PATH`; a relative path is rejected. | `codex` |
| `ORCH_CLAUDE_BIN` | cross-family scripts | Claude binary to run, same rules. | `claude` |

## Names

File, agent and environment variable names are Turkish in origin and kept on purpose: renaming would ripple through tests and hook registrations. A short glossary:

| Name | Meaning |
|---|---|
| `tarayici` | scanner |
| `okuma_butcesi` | read budget |
| `aile_elestirmen` | family critic |
| `paralel-is-hatirlatici` | parallel-work reminder |
| `agent-tip-kapisi` | agent-type gate |
| `superpowers_surum_bekcisi` | superpowers version guard |
| `orkestrasyon_hatirlatici` | orchestration load reminder |
| `gorsel_uret` | image generation |
| `modeller` | models |
| K1 / K2 | critic layer 1 / critic layer 2 |

## Known limits

- The Codex read-only sandbox restricts writes, not reads: reading is not confined to the working directory. It also cannot run tests ("No usable temporary directory"), so the Codex critic verifies the worker's evidence instead of re-running the tests.
- Whether the Claude critic loads CLAUDE.md memory under `--restricted` is not verified. If it does, the critic shares instructions with the session that wrote the work, which reduces its independence.
- Codex plugins cannot ship agent roles; the roles are copied separately.
- Claude Code plugin agents get the `orchestration:` prefix.
- Measurements cited in `SKILL.md` and `DECISIONS.md` are small-n internal measurements, not benchmarks.
- `aile_elestirmen.py` copies `~/.codex/auth.json` into a private temporary home for each Codex call. If Codex refreshes the token, the new copy is written back only when the original file is unchanged. The script never prints or sends the token.
- The advisor tool is optional and exists only on the Claude side.
- Load reminder: in Claude Code the note arrives with the first Agent call's result, so it shapes the later spawns, not the first one. In Codex it runs only after you trust it with `/hooks`.
- Codex plugin hook loading via `${PLUGIN_ROOT}` not measured in a live session.

## Tests

Three suites, each run from its own folder:

```sh
# repository root: install script tests
python3 -m unittest discover -s tests

# skills/orchestration: hook tests
cd skills/orchestration && python3 -m unittest discover -s hooks/tests

# skills/orchestration/scripts: script tests
cd skills/orchestration/scripts && python3 -m unittest discover -s tests -t tests
```

The install tests run `install.sh` in a temporary home directory under a sandbox profile without network; tests that need the real `claude` or `codex` binary are skipped when it is not on `PATH`.

No real model is called; the script tests use fake `codex` and `claude` binaries, and the hook tests use a temporary home directory.

## Diagram

```sh
python3 tools/diagram/make_diagram.py
```

Regenerates `docs/assets/orchestration-flow.gif` and `docs/assets/orchestration-flow.svg`. Needs Pillow (`python3 -m pip install pillow`).

## Türkçe

Bu depo Claude Code ve Codex CLI için bir orkestrasyon skill'i, tipli alt ajanlar ve kancalar (hook) içerir. Ana oturum planlar, karar verir ve denetler; işi alt ajanlar yapar; önemli noktalarda öbür model ailesinden bir eleştirmen işi okur. Geri alınamaz eylemler (push, izlenmeyen dosya silme, dış sisteme yazma) kullanıcı onayı bekler.

Claude Code'a eklenti olarak kurmak için:

```
/plugin marketplace add OWNER/claude-codex-orchestration
/plugin install orchestration@claude-codex-orchestration
```

Codex'e eklenti olarak kurmak için:

```sh
codex plugin marketplace add OWNER/claude-codex-orchestration
codex plugin add orchestration@claude-codex-orchestration
```

Codex eklentisi ajan rollerini taşıyamadığı için `codex/agents/*.toml` dosyalarını `~/.codex/agents/` klasörüne kopyalayın ya da iki aracı tek adımda kurun:

```sh
git clone https://github.com/OWNER/claude-codex-orchestration
cd claude-codex-orchestration
./install.sh
```

Codex, kurulumdan sonra yeni kancaları siz Codex içinde bir kez `/hooks` açıp onlara güvenene kadar çalıştırmaz. Eklentiyi ve kullanıcı düzeyi kopyayı birlikte kurmayın, skill ve kancalar iki kez yüklenir (`install.sh` buna izin vermez).

Seçenekler, güncelleme ve doğrulama için [Install](#install), ayarlar için [Configuration](#configuration), bilinen sınırlar için [Known limits](#known-limits) bölümüne bakın. Kural kitabının Türkçe okuma kopyası [skills/orchestration/SKILL.tr.md](skills/orchestration/SKILL.tr.md) dosyasındadır; model İngilizce `SKILL.md`'yi yükler ve iki dosya ayrışırsa `SKILL.md` geçerlidir.

## Acknowledgements

- [superpowers](https://github.com/obra/superpowers) by Jesse Vincent (MIT). It is a separate plugin; this repository contains only a mapping table to its skills and copies no code from it.
- Inspiration: the Avenox video "Tek Ajan Yetmez: Ajan Ekibi Kurmanın 6 Seviyesi" (https://www.youtube.com/watch?v=zE_ggoUn7ao).

## License

MIT, see [LICENSE](LICENSE).
