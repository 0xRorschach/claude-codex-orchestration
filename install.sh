#!/usr/bin/env bash
# Install the orchestration skill, agents and hooks for Claude Code and/or Codex CLI.
#
# Modes (pick one; default --plugin):
#   --plugin       register this clone as a local marketplace and install the plugin in each tool found;
#                  Codex roles (codex/agents/*.toml) are copied to the Codex agents folder.
#   --user-level   no plugin: copy the skill to ~/.agents/skills/orchestration, symlink it into Claude Code,
#                  copy agents/roles and register the hooks in settings.json / hooks.json.
#   --uninstall    detect what this script installed and remove it.
# Options: --dry-run, --claude-only, --codex-only, --help.
#
# Exit codes: 0 done (or nothing to do), 1 missing prerequisite, 2 usage error, 3 would install twice.
# Paths honour CLAUDE_CONFIG_DIR, CODEX_HOME and XDG_STATE_HOME. No sudo, no network of its own.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKETPLACE="claude-codex-orchestration"
PLUGIN="orchestration"
PLUGIN_ID="${PLUGIN}@${MARKETPLACE}"
# Marker that identifies our hook entries in settings.json / hooks.json (user-level and uninstall).
HOOK_MARK="skills/orchestration/hooks/"

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CODEX_DIR="${CODEX_HOME:-$HOME/.codex}"
AGENTS_SKILL="$HOME/.agents/skills/orchestration"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/claude-codex-orchestration"
BACKUP_DIR="$STATE_DIR/backups/$(date +%Y%m%d-%H%M%S)"

MODE="plugin"
DRY=0
WANT_CLAUDE=1
WANT_CODEX=1
CHANGED=0

usage() {
  sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

say() { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$1" >&2; exit "${2:-1}"; }

# run CMD...: execute, or only print it under --dry-run.
run() {
  CHANGED=1
  if [ "$DRY" = 1 ]; then
    say "  [dry-run] $*"
  else
    "$@"
  fi
}

backup() { # backup FILE_OR_DIR: copy it under the backup folder, keeping its absolute path.
  local src="$1"
  [ -e "$src" ] || [ -L "$src" ] || return 0
  if [ "$DRY" = 1 ]; then
    say "  [dry-run] back up $src -> $BACKUP_DIR$src"
    return 0
  fi
  mkdir -p "$BACKUP_DIR$(dirname "$src")"
  cp -RP "$src" "$BACKUP_DIR$src"
  say "  backed up $src -> $BACKUP_DIR$src"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --plugin) MODE="plugin" ;;
    --user-level) MODE="user" ;;
    --uninstall) MODE="uninstall" ;;
    --dry-run) DRY=1 ;;
    --claude-only) WANT_CODEX=0 ;;
    --codex-only) WANT_CLAUDE=0 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown option: $1" 2 ;;
  esac
  shift
done
[ "$WANT_CLAUDE" = 0 ] && [ "$WANT_CODEX" = 0 ] && die "--claude-only and --codex-only exclude each other" 2

# --- prerequisites ---------------------------------------------------------------------------------------------
command -v python3 >/dev/null 2>&1 || die "python3 not found: the hooks need Python 3.9 or newer"
PYV="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
  || die "python3 is $PYV: the hooks need Python 3.9 or newer"
if python3 -c 'import sys; sys.exit(0 if sys.version_info < (3, 11) else 1)'; then
  warn "python3 is $PYV: the Codex version guard stays silent below 3.11 (no tomllib)"
fi

HAVE_CLAUDE=0; HAVE_CODEX=0
[ "$WANT_CLAUDE" = 1 ] && command -v claude >/dev/null 2>&1 && HAVE_CLAUDE=1
[ "$WANT_CODEX" = 1 ] && command -v codex >/dev/null 2>&1 && HAVE_CODEX=1
if [ "$HAVE_CLAUDE" = 0 ] && [ "$HAVE_CODEX" = 0 ]; then
  die "neither claude (Claude Code) nor codex (Codex CLI) found on PATH for the selected tools"
fi
[ "$WANT_CLAUDE" = 1 ] && [ "$HAVE_CLAUDE" = 0 ] && say "claude not found: skipping Claude Code"
[ "$WANT_CODEX" = 1 ] && [ "$HAVE_CODEX" = 0 ] && say "codex not found: skipping Codex"

# --- detection (files only, so --dry-run never calls the tools) ------------------------------------------------
json_has_key() { # json_has_key FILE TOPKEY KEY: is KEY inside the object at TOPKEY (or top level when TOPKEY="")?
  [ -f "$1" ] || return 1
  python3 - "$1" "$2" "$3" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
if sys.argv[2]:
    d = d.get(sys.argv[2], {}) if isinstance(d, dict) else {}
sys.exit(0 if isinstance(d, dict) and sys.argv[3] in d else 1)
PY
}

hooks_have_ours() { # hooks_have_ours FILE: does a hook command in FILE point into our skill?
  [ -f "$1" ] || return 1
  python3 - "$1" "$HOOK_MARK" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
for groups in (d.get("hooks") or {}).values():
    for g in groups or []:
        for h in g.get("hooks") or []:
            if sys.argv[2] in str(h.get("command", "")):
                sys.exit(0)
sys.exit(1)
PY
}

claude_marketplace_known() { json_has_key "$CLAUDE_DIR/plugins/known_marketplaces.json" "" "$MARKETPLACE"; }
claude_plugin_installed() { json_has_key "$CLAUDE_DIR/plugins/installed_plugins.json" plugins "$PLUGIN_ID"; }
codex_marketplace_known() { [ -f "$CODEX_DIR/config.toml" ] && grep -Fq "[marketplaces.$MARKETPLACE]" "$CODEX_DIR/config.toml"; }
codex_plugin_installed() { [ -f "$CODEX_DIR/config.toml" ] && grep -Fq "[plugins.\"$PLUGIN_ID\"]" "$CODEX_DIR/config.toml"; }

plugin_present() {
  claude_plugin_installed || claude_marketplace_known || codex_plugin_installed || codex_marketplace_known
}
user_level_present() {
  [ -e "$AGENTS_SKILL" ] || [ -L "$AGENTS_SKILL" ] || [ -e "$CLAUDE_DIR/skills/orchestration" ] \
    || [ -L "$CLAUDE_DIR/skills/orchestration" ] || hooks_have_ours "$CLAUDE_DIR/settings.json" \
    || hooks_have_ours "$CODEX_DIR/hooks.json"
}

# --- shared file helpers ---------------------------------------------------------------------------------------
same_tree() { diff -rq -x __pycache__ "$1" "$2" >/dev/null 2>&1; }

copy_file() { # copy_file SRC DEST: copy unless identical; back up a different existing file first.
  local src="$1" dest="$2"
  if [ -f "$dest" ] && cmp -s "$src" "$dest"; then
    return 0
  fi
  if [ -e "$dest" ]; then backup "$dest"; fi
  run mkdir -p "$(dirname "$dest")"
  run cp "$src" "$dest"
  [ "$DRY" = 1 ] || say "  copied $(basename "$src") -> $dest"
}

remove_if_ours() { # remove_if_ours SRC DEST: delete DEST only when it is byte-identical to our SRC.
  local src="$1" dest="$2"
  [ -e "$dest" ] || return 0
  if cmp -s "$src" "$dest"; then
    run rm -f "$dest"
    [ "$DRY" = 1 ] || say "  removed $dest"
  else
    warn "$dest differs from this repo's copy: left in place"
  fi
}

copy_set() { # copy_set SRCDIR GLOB DESTDIR
  local f
  for f in "$1"/$2; do copy_file "$f" "$3/$(basename "$f")"; done
}
remove_set() {
  local f
  for f in "$1"/$2; do remove_if_ours "$f" "$3/$(basename "$f")"; done
}

hooks_json() { # hooks_json merge|remove TARGET [FRAGMENT]; prints "changed" when the file would change.
  python3 - "$@" "$HOOK_MARK" "$DRY" <<'PY'
import json, os, sys
op, target = sys.argv[1], sys.argv[2]
frag = sys.argv[3] if op == "merge" else None
mark, dry = sys.argv[-2], sys.argv[-1] == "1"
if os.path.exists(target):
    with open(target) as f:
        data = json.load(f)
else:
    data = {}
before = json.dumps(data, sort_keys=True)
hooks = data.setdefault("hooks", {})
if op == "merge":
    with open(frag) as f:
        add = json.load(f)["hooks"]
    for event, groups in add.items():
        cur = hooks.setdefault(event, [])
        have = {h.get("command") for g in cur for h in g.get("hooks") or []}
        for g in groups:
            if not any(h["command"] in have for h in g["hooks"]):
                cur.append(g)
else:
    for event in list(hooks):
        kept = []
        for g in hooks[event] or []:
            hs = [h for h in g.get("hooks") or [] if mark not in str(h.get("command", ""))]
            if hs:
                g["hooks"] = hs
                kept.append(g)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        del data["hooks"]
if json.dumps(data, sort_keys=True) != before:
    print("changed")
    if not dry:
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        tmp = target + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, target)
PY
}

update_hooks() { # update_hooks merge|remove TARGET [FRAGMENT]
  local op="$1" target="$2"
  local probe
  probe="$(hooks_json_probe "$@")"
  [ "$probe" = "changed" ] || return 0
  CHANGED=1
  backup "$target"
  if [ "$DRY" = 1 ]; then
    say "  [dry-run] $op our hook entries in $target"
  else
    hooks_json "$@" >/dev/null
    say "  ${op}d our hook entries in $target"
  fi
}
hooks_json_probe() { local d="$DRY"; DRY=1; hooks_json "$@"; DRY="$d"; }

# --- plugin mode -----------------------------------------------------------------------------------------------
install_plugin() {
  if user_level_present; then
    warn "a user-level install was found (~/.agents/skills/orchestration, the Claude skills folder, or our hooks in"
    warn "settings.json / hooks.json). Installing the plugin as well would load everything twice."
    warn "Run ./install.sh --uninstall first, then install again."
    exit 3
  fi
  if [ "$HAVE_CLAUDE" = 1 ]; then
    say "Claude Code:"
    if claude_plugin_installed; then
      say "  already installed ($PLUGIN_ID)"
    else
      claude_marketplace_known || run claude plugin marketplace add "$REPO"
      run claude plugin install "$PLUGIN_ID"
    fi
  fi
  if [ "$HAVE_CODEX" = 1 ]; then
    say "Codex:"
    if codex_plugin_installed; then
      say "  already installed ($PLUGIN_ID)"
    else
      # codex refuses to start when CODEX_HOME is set to a folder that does not exist yet.
      [ -d "$CODEX_DIR" ] || run mkdir -p "$CODEX_DIR"
      codex_marketplace_known || run codex plugin marketplace add "$REPO"
      run codex plugin add "$PLUGIN_ID"
    fi
    copy_set "$REPO/codex/agents" '*.toml' "$CODEX_DIR/agents"
  fi
  say ""
  say "Keep this clone: it is the marketplace source."
  if [ "$HAVE_CLAUDE" = 1 ]; then
    say "  Claude Code reads the plugin from this folder in place; 'git pull' updates it (restart the session)."
  fi
  if [ "$HAVE_CODEX" = 1 ]; then
    say "  Codex installs a cached copy: after 'git pull' run 'codex plugin add $PLUGIN_ID' to refresh it."
    say "  Codex runs new hooks only after you trust them: open Codex and approve them with /hooks."
  fi
}

uninstall_plugin() {
  if [ "$HAVE_CLAUDE" = 1 ]; then
    if claude_plugin_installed; then run claude plugin uninstall "$PLUGIN_ID"; fi
    if claude_marketplace_known; then run claude plugin marketplace remove "$MARKETPLACE"; fi
  fi
  if [ "$HAVE_CODEX" = 1 ]; then
    if codex_plugin_installed; then run codex plugin remove "$PLUGIN_ID"; fi
    if codex_marketplace_known; then run codex plugin marketplace remove "$MARKETPLACE"; fi
  fi
}

# --- user-level mode -------------------------------------------------------------------------------------------
install_user() {
  if plugin_present; then
    warn "the $PLUGIN_ID plugin (or its marketplace) is installed. A user-level install as well would load"
    warn "everything twice. Run ./install.sh --uninstall first, then install again."
    exit 3
  fi
  say "Skill:"
  if [ -d "$AGENTS_SKILL" ] && [ ! -L "$AGENTS_SKILL" ] && same_tree "$REPO/skills/orchestration" "$AGENTS_SKILL"; then
    say "  already installed ($AGENTS_SKILL)"
  else
    if [ -e "$AGENTS_SKILL" ] || [ -L "$AGENTS_SKILL" ]; then
      backup "$AGENTS_SKILL"
      run rm -rf "$AGENTS_SKILL"
    fi
    run mkdir -p "$(dirname "$AGENTS_SKILL")"
    run cp -R "$REPO/skills/orchestration" "$AGENTS_SKILL"
    run find "$AGENTS_SKILL" -name __pycache__ -type d -prune -exec rm -rf {} +
    [ "$DRY" = 1 ] || say "  copied skill -> $AGENTS_SKILL"
  fi
  if [ "$HAVE_CLAUDE" = 1 ]; then
    say "Claude Code:"
    local link="$CLAUDE_DIR/skills/orchestration"
    if [ -L "$link" ] && [ "$(readlink "$link")" = "$AGENTS_SKILL" ]; then
      :
    else
      if [ -e "$link" ] || [ -L "$link" ]; then backup "$link"; run rm -rf "$link"; fi
      run mkdir -p "$CLAUDE_DIR/skills"
      run ln -s "$AGENTS_SKILL" "$link"
    fi
    copy_set "$REPO/agents" '*.md' "$CLAUDE_DIR/agents"
    update_hooks merge "$CLAUDE_DIR/settings.json" "$REPO/skills/orchestration/hooks/settings-parcasi.json"
  fi
  if [ "$HAVE_CODEX" = 1 ]; then
    say "Codex:"
    copy_set "$REPO/codex/agents" '*.toml' "$CODEX_DIR/agents"
    update_hooks merge "$CODEX_DIR/hooks.json" "$REPO/skills/orchestration/hooks/codex-parcasi.json"
  fi
  say ""
  say "The skill is a copy: after 'git pull' run ./install.sh --user-level again to update it."
  if [ "$HAVE_CODEX" = 1 ]; then
    say "Codex runs new hooks only after you trust them: open Codex and approve them with /hooks."
  fi
}

uninstall_user() {
  if [ "$HAVE_CLAUDE" = 1 ]; then
    local link="$CLAUDE_DIR/skills/orchestration"
    if [ -L "$link" ] && [ "$(readlink "$link")" = "$AGENTS_SKILL" ]; then run rm -f "$link"; fi
    remove_set "$REPO/agents" '*.md' "$CLAUDE_DIR/agents"
    update_hooks remove "$CLAUDE_DIR/settings.json"
  fi
  if [ "$HAVE_CODEX" = 1 ]; then
    update_hooks remove "$CODEX_DIR/hooks.json"
  fi
  # The shared skill copy goes only when no tool still uses it: Codex reads it directly (kept under
  # --claude-only) and Claude Code reads it through the symlink (kept while the link is there).
  if [ -d "$AGENTS_SKILL" ] && [ ! -L "$AGENTS_SKILL" ] && [ "$WANT_CODEX" = 1 ] \
     && { [ "$DRY" = 1 ] || [ ! -L "$CLAUDE_DIR/skills/orchestration" ]; }; then
    if same_tree "$REPO/skills/orchestration" "$AGENTS_SKILL"; then
      run rm -rf "$AGENTS_SKILL"
      [ "$DRY" = 1 ] || say "  removed $AGENTS_SKILL"
    else
      warn "$AGENTS_SKILL differs from this repo's skill: left in place"
    fi
  fi
}

# --- main ------------------------------------------------------------------------------------------------------
[ "$DRY" = 1 ] && say "Dry run: nothing will be written."
case "$MODE" in
  plugin) install_plugin ;;
  user) install_user ;;
  uninstall)
    uninstall_plugin
    uninstall_user
    if [ "$HAVE_CODEX" = 1 ]; then remove_set "$REPO/codex/agents" '*.toml' "$CODEX_DIR/agents"; fi
    ;;
esac
if [ "$CHANGED" = 0 ] && [ "$MODE" != "uninstall" ]; then
  say "Already installed: nothing changed."
elif [ "$CHANGED" = 0 ]; then
  say "Nothing to uninstall."
elif [ -d "$BACKUP_DIR" ]; then
  say "Backups: $BACKUP_DIR"
fi
exit 0
