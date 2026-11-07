#!/usr/bin/env bash
# Install the orchestration skill, agents and hooks for Claude Code and/or Codex CLI.
#
# Modes (pick one; default --plugin):
#   --plugin       register this clone as a local marketplace and install the plugin in each tool found;
#                  Codex roles (codex/agents/*.toml) are copied to the Codex agents folder.
#   --user-level   no plugin: copy the skill to ~/.agents/skills/orchestration, symlink it into Claude Code,
#                  copy agents/roles and register the hooks in settings.json / hooks.json.
#   --uninstall    remove what this script installed (as listed in its install record).
# Options: --dry-run, --claude-only, --codex-only, --help.
#
# Exit codes: 0 done (or nothing to do), 1 missing prerequisite, unreadable JSON or a failed claude/codex command,
#   2 usage error, 3 would install twice (or a path this script did not install is in the way).
# Install record: ${XDG_STATE_HOME:-~/.local/state}/claude-codex-orchestration/install-record.json lists every
#   file, link, hook entry and plugin this script added, with checksums and backups; --uninstall removes only those,
#   only while unchanged, and puts the backed-up originals back.
# Paths honour CLAUDE_CONFIG_DIR, CODEX_HOME and XDG_STATE_HOME. No sudo, no network of its own.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKETPLACE="claude-codex-orchestration"
PLUGIN="orchestration"
PLUGIN_ID="${PLUGIN}@${MARKETPLACE}"
# Marker of hook commands that run this skill's hooks (used only to spot entries the record does not cover).
HOOK_MARK="skills/orchestration/hooks/"

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CODEX_DIR="${CODEX_HOME:-$HOME/.codex}"
AGENTS_SKILL="$HOME/.agents/skills/orchestration"
CLAUDE_LINK="$CLAUDE_DIR/skills/orchestration"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/claude-codex-orchestration"
RECORD="$STATE_DIR/install-record.json"
BACKUP_DIR="$STATE_DIR/backups/$(date +%Y%m%d-%H%M%S)"

MODE="plugin"
DRY=0
WANT_CLAUDE=1
WANT_CODEX=1
CHANGED=0

usage() { # the header comment above, without the leading "# "
  awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "${BASH_SOURCE[0]}"
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

# run_tool LABEL CMD...: like run, for a claude/codex command; a failure stops the script with exit 1 and names it.
run_tool() {
  local label="$1"
  shift
  CHANGED=1
  if [ "$DRY" = 1 ]; then
    say "  [dry-run] $*"
    return 0
  fi
  local rc=0
  "$@" || rc=$?
  [ "$rc" = 0 ] || die "$label failed (exit $rc)"
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
if [ "$MODE" != "uninstall" ] && python3 -c 'import sys; sys.exit(0 if sys.version_info < (3, 11) else 1)'; then
  warn "python3 is $PYV: the Codex version guard stays silent below 3.11 (no tomllib)"
fi

HAVE_CLAUDE=0; HAVE_CODEX=0
[ "$WANT_CLAUDE" = 1 ] && command -v claude >/dev/null 2>&1 && HAVE_CLAUDE=1
[ "$WANT_CODEX" = 1 ] && command -v codex >/dev/null 2>&1 && HAVE_CODEX=1
if [ "$MODE" != "uninstall" ]; then
  # Uninstall works without the tools: recorded files and hook entries are removed all the same.
  if [ "$HAVE_CLAUDE" = 0 ] && [ "$HAVE_CODEX" = 0 ]; then
    die "neither claude (Claude Code) nor codex (Codex CLI) found on PATH for the selected tools"
  fi
  [ "$WANT_CLAUDE" = 1 ] && [ "$HAVE_CLAUDE" = 0 ] && say "claude not found: skipping Claude Code"
  [ "$WANT_CODEX" = 1 ] && [ "$HAVE_CODEX" = 0 ] && say "codex not found: skipping Codex"
fi

# --- helper: every write, the install record, JSON merge/remove, backups and restores ---------------------------
# One Python program with subcommands. Exit 0 = nothing changed, 10 = changed (or would change under --dry-run),
# 3 = refused (would install twice), anything else = error (message already printed).
helper() {
  OI_DRY="$DRY" OI_RECORD="$RECORD" OI_BACKUP_DIR="$BACKUP_DIR" OI_MODE="$MODE" OI_MARK="$HOOK_MARK" \
    python3 - "$@" <<'PY'
import copy
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import time

DRY = os.environ["OI_DRY"] == "1"
RECORD = os.environ["OI_RECORD"]
BACKUP_DIR = os.environ["OI_BACKUP_DIR"]
MODE = os.environ["OI_MODE"]
MARK = os.environ["OI_MARK"]
CHANGED = 10


class Fail(Exception):
    pass


def say(msg):
    print(msg, flush=True)


def warn(msg):
    print("warning: " + msg, file=sys.stderr, flush=True)


def umask():
    m = os.umask(0)
    os.umask(m)
    return m


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def regular_file(path):
    return os.path.isfile(path) and not os.path.islink(path)


def tree_sha(root):
    """Checksum of a folder: relative names, file contents, exec bits and symlink targets; __pycache__ ignored."""
    h = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        h.update(b"D\0" + rel.encode() + b"\0")
        links = sorted(d for d in dirnames if os.path.islink(os.path.join(dirpath, d)))
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__" and d not in links)
        for name in sorted(filenames + links):
            p = os.path.join(dirpath, name)
            if os.path.islink(p):
                h.update(b"L\0" + name.encode() + b"\0" + os.readlink(p).encode() + b"\0")
            else:
                x = b"x" if os.stat(p).st_mode & 0o111 else b"-"
                h.update(b"F\0" + name.encode() + b"\0" + x + sha_file(p).encode() + b"\0")
    return h.hexdigest()


def atomic_write(target, data, mode):
    """Write data to target through a 0600 temporary file in the same folder, set mode, then rename over target.
    The rename replaces a symlink at target itself; the file it pointed to is not touched."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target) or ".", prefix="." + os.path.basename(target) + ".")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_object(path, what="JSON"):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise Fail("cannot parse %s: %s; fix or move it and rerun" % (path, e))
    if not isinstance(data, dict):
        raise Fail("cannot parse %s: the top level is not a %s object; fix or move it and rerun" % (path, what))
    return data


def load_hooks_file(path):
    data = load_object(path)
    hooks = data.get("hooks")
    if hooks is not None:
        ok = isinstance(hooks, dict) and all(
            isinstance(gs, list) and all(isinstance(g, dict) and isinstance(g.get("hooks", []), list) for g in gs)
            for gs in hooks.values())
        if not ok:
            raise Fail('cannot parse %s: "hooks" is not an object of hook lists; fix or move it and rerun' % path)
    return data


# --- the install record -----------------------------------------------------------------------------------------
class Record:
    def __init__(self):
        self.exists = os.path.lexists(RECORD)
        if self.exists:
            data = load_object(RECORD, "install record")
            if data.get("version") != 1 or not isinstance(data.get("items"), list) \
                    or not all(isinstance(i, dict) and "kind" in i for i in data["items"]):
                raise Fail("cannot parse %s: not an install record of this script; fix or move it and rerun"
                           % RECORD)
        else:
            data = {"version": 1, "modes": [], "tools": [], "items": []}
        self.data = data
        self.before = json.dumps(data, sort_keys=True)

    @property
    def items(self):
        return self.data["items"]

    def find(self, kind, path):
        for i in self.items:
            if i["kind"] == kind and i.get("path") == path:
                return i
        return None

    def add(self, item):
        item.setdefault("mode", MODE)
        self.items.append(item)
        if MODE not in self.data["modes"]:
            self.data["modes"].append(MODE)
        for t in [item.get("tool")] + list(item.get("users") or []):
            if t in ("claude", "codex") and t not in self.data["tools"]:
                self.data["tools"].append(t)

    def drop(self, item):
        self.items.remove(item)

    def save(self, uninstall=False):
        if DRY or json.dumps(self.data, sort_keys=True) == self.before:
            return
        if uninstall and not any(i["kind"] != "dir" for i in self.items):
            # Only folders this script created but could not remove (something else lives in them) are left:
            # nothing of ours remains, so the record goes.
            if os.path.lexists(RECORD):
                os.unlink(RECORD)
            return
        self.data["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.data.setdefault("created", self.data["updated"])
        os.makedirs(os.path.dirname(RECORD), mode=0o700, exist_ok=True)
        atomic_write(RECORD, (json.dumps(self.data, indent=2, sort_keys=True) + "\n").encode(), 0o600)
        self.before = json.dumps(self.data, sort_keys=True)


def ensure_dirs(path, tool, rec):
    """Create path and missing parents; each folder created is recorded so uninstall can remove it if empty."""
    missing = []
    p = os.path.abspath(path)
    while not os.path.lexists(p):
        missing.append(p)
        p = os.path.dirname(p)
    for d in reversed(missing):
        if not DRY:
            os.mkdir(d)
        if rec.find("dir", d) is None:
            rec.add({"kind": "dir", "path": d, "tool": tool})


# --- backups ----------------------------------------------------------------------------------------------------
def backup(path):
    """Copy path under the backup folder (keeping its absolute path) and describe it for the record.
    A symlink is saved as its target path plus, when it points to a file, that file's content."""
    st = os.lstat(path)
    dest = BACKUP_DIR + os.path.abspath(path)
    info = {"path": None, "type": None, "mode": None, "link_target": None}
    if stat.S_ISLNK(st.st_mode):
        info["type"] = "symlink"
        info["link_target"] = os.readlink(path)
        if os.path.isfile(path):
            info["path"] = dest
            info["mode"] = "%04o" % stat.S_IMODE(os.stat(path).st_mode)
    elif stat.S_ISDIR(st.st_mode):
        info.update(type="dir", path=dest, mode="%04o" % stat.S_IMODE(st.st_mode))
    else:
        info.update(type="file", path=dest, mode="%04o" % stat.S_IMODE(st.st_mode))
    if DRY:
        say("  [dry-run] back up %s -> %s" % (path, dest))
        return info
    if not os.path.isdir(BACKUP_DIR):
        os.makedirs(BACKUP_DIR, mode=0o700)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if info["type"] == "dir":
        shutil.copytree(path, dest, symlinks=True)
    elif info["path"]:
        shutil.copy2(path, dest)  # follows a symlink: the content it points to is what gets saved
    if info["type"] == "symlink":
        say("  backed up %s (symlink to %s) -> %s" % (path, info["link_target"], info["path"] or "record only"))
    else:
        say("  backed up %s -> %s" % (path, dest))
    return info


def restore(path, info):
    """Put a backed-up original back at path (only when path is free)."""
    if not info or not info.get("type"):
        return False
    where = info.get("path") or info.get("link_target")
    if os.path.lexists(path):
        warn("%s is in use, so your earlier version was not put back: it is at %s" % (path, where))
        return False
    if info["type"] != "symlink" and not (info.get("path") and os.path.lexists(info["path"])):
        warn("the backup of %s is missing (%s): not restored" % (path, info.get("path")))
        return False
    if DRY:
        say("  [dry-run] restore %s" % path)
        return True
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if info["type"] == "symlink":
        os.symlink(info["link_target"], path)
        say("  restored %s (symlink to %s)" % (path, info["link_target"]))
        return True
    if info["type"] == "dir":
        shutil.copytree(info["path"], path, symlinks=True)
    else:
        with open(info["path"], "rb") as f:
            atomic_write(path, f.read(), int(info["mode"], 8))
    say("  restored %s from %s" % (path, info["path"]))
    return True


def remove_path(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        os.unlink(path)


# --- install steps ----------------------------------------------------------------------------------------------
def cmd_copy_file(src, dest, tool):
    rec = Record()
    item = rec.find("file", dest)
    with open(src, "rb") as f:
        data = f.read()
    new = sha_bytes(data)
    if regular_file(dest) and sha_file(dest) == new:
        return 0
    if os.path.lexists(dest):
        ours = item is not None and regular_file(dest) and sha_file(dest) == item.get("sha256")
        if not ours:
            info = backup(dest)
            if item is None:
                item = {"kind": "file", "path": dest, "tool": tool, "backup": info}
                rec.add(item)
            else:
                warn("%s was changed after install; that version was backed up before the update" % dest)
    elif item is None:
        item = {"kind": "file", "path": dest, "tool": tool, "backup": None}
        rec.add(item)
    if regular_file(dest):
        mode = stat.S_IMODE(os.stat(dest).st_mode)
    else:
        mode = stat.S_IMODE(os.stat(src).st_mode) & ~umask()
    if DRY:
        say("  [dry-run] copy %s -> %s" % (os.path.basename(src), dest))
    else:
        ensure_dirs(os.path.dirname(dest), tool, rec)
        atomic_write(dest, data, mode)
        say("  copied %s -> %s" % (os.path.basename(src), dest))
    item["sha256"] = new
    rec.save()
    return CHANGED


def cmd_copy_tree(src, dest, *users):
    rec = Record()
    item = rec.find("tree", dest)
    new = tree_sha(src)
    if os.path.lexists(dest) and item is None:
        raise Fail("%s exists but is not in this script's install record" % dest)
    if item is not None and os.path.isdir(dest) and not os.path.islink(dest) and tree_sha(dest) == new:
        for u in users:
            if u not in item["users"]:
                item["users"].append(u)
        rec.save()
        say("  already installed (%s)" % dest)
        return 0
    if item is None:
        item = {"kind": "tree", "path": dest, "users": [], "backup": None}
        rec.add(item)
    elif os.path.lexists(dest) and not (os.path.isdir(dest) and tree_sha(dest) == item.get("sha256")):
        backup(dest)
        warn("%s was changed after install; that version was backed up before the update" % dest)
    for u in users:
        if u not in item["users"]:
            item["users"].append(u)
    if DRY:
        say("  [dry-run] copy skill -> %s" % dest)
    else:
        parent = os.path.dirname(dest)
        ensure_dirs(parent, "shared", rec)
        tmpdir = tempfile.mkdtemp(dir=parent, prefix=".orchestration-install.")
        try:
            staged = os.path.join(tmpdir, "new")
            shutil.copytree(src, staged, symlinks=True, ignore=shutil.ignore_patterns("__pycache__"))
            if os.path.lexists(dest):
                os.rename(dest, os.path.join(tmpdir, "old"))
            os.rename(staged, dest)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        say("  copied skill -> %s" % dest)
    item["sha256"] = new
    rec.save()
    return CHANGED


def cmd_link(link, target, tool):
    rec = Record()
    item = rec.find("link", link)
    if os.path.islink(link) and os.readlink(link) == target:
        if item is None:
            # Points exactly at our recorded skill copy: count it as ours, with nothing to restore.
            rec.add({"kind": "link", "path": link, "target": target, "tool": tool, "backup": None})
            rec.save()
        return 0
    info = None
    if os.path.lexists(link):
        info = backup(link)
        if not DRY:
            remove_path(link)
    if item is None:
        item = {"kind": "link", "path": link, "tool": tool, "backup": info}
        rec.add(item)
    item["target"] = target
    if DRY:
        say("  [dry-run] link %s -> %s" % (link, target))
    else:
        ensure_dirs(os.path.dirname(link), tool, rec)
        os.symlink(target, link)
        say("  linked %s -> %s" % (link, target))
    rec.save()
    return CHANGED


def write_hooks_file(path, data):
    """Atomic write that keeps the file's mode (a new file gets 0666 minus umask). A symlinked config file (a
    dotfiles repo, say) is written through to the file it points to, so the link stays."""
    real = os.path.realpath(path)
    mode = stat.S_IMODE(os.stat(real).st_mode) if os.path.exists(real) else 0o666 & ~umask()
    atomic_write(real, (json.dumps(data, indent=2) + "\n").encode(), mode)


def cmd_json_merge(path, frag, tool):
    rec = Record()
    existed = os.path.exists(path)
    data = load_hooks_file(path) if existed else {}
    with open(frag, encoding="utf-8") as f:
        add = json.load(f)["hooks"]
    had_hooks = "hooks" in data
    hooks = data.setdefault("hooks", {})
    added = []
    for event, groups in add.items():
        cur = hooks.setdefault(event, [])
        have = {h.get("command") for g in cur for h in g.get("hooks") or []}
        for g in groups:
            if not any(h["command"] in have for h in g["hooks"]):
                cur.append(copy.deepcopy(g))
                added.append((event, g))
        if not cur:
            del hooks[event]
    if not had_hooks and not hooks:
        del data["hooks"]
    if not added:
        return 0
    if existed:
        backup(path)
    for event, g in added:
        rec.add({"kind": "json", "path": path, "tool": tool, "event": event, "entry": g})
    if not existed and rec.find("jsonfile", path) is None:
        rec.add({"kind": "jsonfile", "path": path, "tool": tool})
    if DRY:
        say("  [dry-run] merge our hook entries in %s" % path)
    else:
        ensure_dirs(os.path.dirname(path), tool, rec)
        write_hooks_file(path, data)
        say("  merged our hook entries in %s" % path)
    rec.save()
    return CHANGED


def cmd_ensure_dir(path, tool):
    if os.path.lexists(path):
        return 0
    rec = Record()
    if DRY:
        say("  [dry-run] mkdir -p %s" % path)
    ensure_dirs(path, tool, rec)
    rec.save()
    return CHANGED


# --- uninstall --------------------------------------------------------------------------------------------------
def remove_json_entries(path, entries):
    """Remove each entry (event, group) from path once, comparing whole groups. Returns (changed, missing)."""
    data = load_hooks_file(path)
    hooks = data.get("hooks") or {}
    removed, missing = 0, []
    for event, entry in entries:
        lst = hooks.get(event) or []
        idx = next((k for k, g in enumerate(lst) if g == entry), None)
        if idx is None:
            missing.append(event)
            continue
        del lst[idx]
        removed += 1
        if not lst:
            del hooks[event]
    if removed and "hooks" in data and not data["hooks"]:
        del data["hooks"]
    return data, removed, missing


def remove_then_restore(path, info):
    if DRY:
        say("  [dry-run] remove %s" % path)
        if info and info.get("type"):
            say("  [dry-run] restore %s" % path)
        return
    os.unlink(path)
    say("  removed %s" % path)
    restore(path, info)


def cmd_uninstall_recorded(*scope):
    rec = Record()
    if not rec.exists:
        return 0
    changed = False
    in_scope = lambda i: i.get("tool") in scope
    for item in [i for i in rec.items if i["kind"] == "file" and in_scope(i)]:
        p = item["path"]
        if not os.path.lexists(p):
            changed |= restore(p, item.get("backup"))
        elif regular_file(p) and sha_file(p) == item.get("sha256"):
            remove_then_restore(p, item.get("backup"))
            changed = True
        else:
            warn("%s was changed after install: left in place" % p)
            if item.get("backup") and item["backup"].get("type"):
                warn("  your version from before the install is at %s"
                     % (item["backup"].get("path") or item["backup"].get("link_target")))
        rec.drop(item)
    for item in [i for i in rec.items if i["kind"] == "link" and in_scope(i)]:
        p = item["path"]
        if os.path.islink(p) and os.readlink(p) == item["target"]:
            remove_then_restore(p, item.get("backup"))
            changed = True
        elif not os.path.lexists(p):
            changed |= restore(p, item.get("backup"))
        else:
            warn("%s no longer points to %s: left in place" % (p, item["target"]))
        rec.drop(item)
    for item in [i for i in rec.items if i["kind"] == "tree"]:
        # The shared skill copy goes when its last user goes (Codex reads it directly, Claude Code via the link).
        item["users"] = [u for u in item["users"] if u not in scope]
        if item["users"]:
            continue
        p = item["path"]
        if not os.path.lexists(p):
            pass
        elif os.path.isdir(p) and not os.path.islink(p) and tree_sha(p) == item.get("sha256"):
            if DRY:
                say("  [dry-run] remove %s" % p)
            else:
                shutil.rmtree(p)
                say("  removed %s" % p)
            changed = True
        else:
            warn("%s was changed after install: left in place" % p)
        rec.drop(item)
    files = []
    for i in rec.items:
        if i["kind"] in ("json", "jsonfile") and in_scope(i) and i["path"] not in files:
            files.append(i["path"])
    for path in files:
        mine = [i for i in rec.items if i["kind"] == "json" and i["path"] == path and in_scope(i)]
        created = next((i for i in rec.items if i["kind"] == "jsonfile" and i["path"] == path), None)
        if not os.path.exists(path):
            for i in mine:
                rec.drop(i)
            if created:
                rec.drop(created)
            continue
        data, removed, missing = remove_json_entries(path, [(i["event"], i["entry"]) for i in mine])
        for event in missing:
            warn("our %s hook entry in %s was changed or removed after install: left as is" % (event, path))
        for i in mine:
            rec.drop(i)
        drop_file = created is not None and data == {} \
            and not any(i["kind"] == "json" and i["path"] == path for i in rec.items)
        if created is not None and not any(i["kind"] == "json" and i["path"] == path for i in rec.items):
            rec.drop(created)
        if not removed and not drop_file:
            continue
        changed = True
        if DRY:
            say("  [dry-run] remove our hook entries from %s" % path)
            continue
        backup(path)
        if drop_file:
            os.unlink(path)
            say("  removed our hook entries from %s (the file was created by this script: removed)" % path)
        else:
            write_hooks_file(path, data)
            say("  removed our hook entries from %s" % path)
    for item in sorted([i for i in rec.items if i["kind"] == "dir"], key=lambda i: -i["path"].count(os.sep)):
        p = item["path"]
        if not os.path.isdir(p) or os.path.islink(p):
            rec.drop(item)
        elif not os.listdir(p):
            if not DRY:
                os.rmdir(p)
            rec.drop(item)
            changed = True
    rec.save(uninstall=True)
    return CHANGED if changed else 0


def cmd_legacy_remove_file(src, dest):
    """No record (an older install): remove dest only when it is byte-identical to our src."""
    if not os.path.lexists(dest):
        return 0
    if regular_file(dest) and sha_file(dest) == sha_file(src):
        if DRY:
            say("  [dry-run] remove %s" % dest)
        else:
            os.unlink(dest)
            say("  removed %s" % dest)
        return CHANGED
    warn("%s differs from this repo's copy: left in place" % dest)
    return 0


def cmd_legacy_json_remove(path, frag):
    """No record: remove only groups exactly equal to a group of our fragment."""
    if not os.path.exists(path):
        return 0
    with open(frag, encoding="utf-8") as f:
        ours = json.load(f)["hooks"]
    entries = [(event, g) for event, gs in ours.items() for g in gs]
    data = load_hooks_file(path)
    present = data.get("hooks") or {}
    entries = [(e, g) for e, g in entries if g in (present.get(e) or [])]
    if not entries:
        left = [h.get("command") for gs in present.values() for g in gs for h in g.get("hooks") or []
                if MARK in str(h.get("command", ""))]
        if left:
            warn("%s has hook entries that run %s scripts but differ from this repo's: left in place" % (path, MARK))
        return 0
    data, removed, _ = remove_json_entries(path, entries)
    if DRY:
        say("  [dry-run] remove our hook entries from %s" % path)
        return CHANGED
    backup(path)
    write_hooks_file(path, data)
    say("  removed our hook entries from %s" % path)
    return CHANGED


# --- queries (exit 0 = yes, 1 = no) and record edits ------------------------------------------------------------
def cmd_preflight(*paths):
    Record()
    for p in paths:
        if os.path.exists(p):
            load_hooks_file(p)
    return 0


def cmd_record_json_paths(*scope):
    rec = Record()
    for p in sorted({i["path"] for i in rec.items if i["kind"] in ("json", "jsonfile") and i.get("tool") in scope}):
        print(p)
    return 0


def cmd_owned(kind, path):
    return 0 if Record().find(kind, path) is not None else 1


def cmd_has_user_level():
    return 0 if any(i["kind"] in ("tree", "link", "json") for i in Record().items) else 1


def cmd_has_plugin(tool, what):
    rec = Record()
    return 0 if any(i["kind"] == "plugin" and i["tool"] == tool and i["what"] == what for i in rec.items) else 1


def cmd_add_plugin(tool, what, ident):
    rec = Record()
    if any(i["kind"] == "plugin" and i["tool"] == tool and i["what"] == what for i in rec.items):
        return 0
    rec.add({"kind": "plugin", "tool": tool, "what": what, "id": ident})
    rec.save()
    return 0


def cmd_drop_plugin(tool, what):
    rec = Record()
    for i in [i for i in rec.items if i["kind"] == "plugin" and i["tool"] == tool and i["what"] == what]:
        rec.drop(i)
    rec.save()
    return 0


COMMANDS = {
    "copy-file": cmd_copy_file, "copy-tree": cmd_copy_tree, "link": cmd_link, "json-merge": cmd_json_merge,
    "ensure-dir": cmd_ensure_dir, "uninstall-recorded": cmd_uninstall_recorded,
    "legacy-remove-file": cmd_legacy_remove_file, "legacy-json-remove": cmd_legacy_json_remove,
    "preflight": cmd_preflight, "record-json-paths": cmd_record_json_paths, "owned": cmd_owned,
    "has-user-level": cmd_has_user_level, "has-plugin": cmd_has_plugin, "add-plugin": cmd_add_plugin,
    "drop-plugin": cmd_drop_plugin,
}

try:
    sys.exit(COMMANDS[sys.argv[1]](*sys.argv[2:]))
except Fail as e:
    print("error: %s" % e, file=sys.stderr)
    sys.exit(1)
except OSError as e:
    print("error: %s" % e, file=sys.stderr)
    sys.exit(1)
PY
}

py() { # py SUBCOMMAND ARGS...: run a helper step; 10 marks a change, any other non-zero status stops the script.
  local rc=0
  helper "$@" || rc=$?
  case "$rc" in
    0) ;;
    10) CHANGED=1 ;;
    3) exit 3 ;;
    *) exit 1 ;;
  esac
}

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
user_level_present() { # anything a user-level install leaves, recorded or not (legacy uninstall uses this)
  [ -e "$AGENTS_SKILL" ] || [ -L "$AGENTS_SKILL" ] || [ -e "$CLAUDE_LINK" ] || [ -L "$CLAUDE_LINK" ] \
    || hooks_have_ours "$CLAUDE_DIR/settings.json" || hooks_have_ours "$CODEX_DIR/hooks.json"
}
owned() { helper owned "$1" "$2"; }
exists() { [ -e "$1" ] || [ -L "$1" ]; }

# legacy_blocker: a skill copy or Claude link that the record does not cover. Under an older version of this script
# nothing was recorded, so updating in place would leave those files invisible to --uninstall.
legacy_blocker() {
  if exists "$AGENTS_SKILL" && ! owned tree "$AGENTS_SKILL"; then
    warn "$AGENTS_SKILL exists but is not in this script's install record ($RECORD)."
    warn "If an older version of this script installed it, run ./install.sh --uninstall; otherwise move it away."
    warn "Then install again."
    exit 3
  fi
  if [ "$HAVE_CLAUDE" = 1 ] && [ -L "$CLAUDE_LINK" ] && [ "$(readlink "$CLAUDE_LINK")" = "$AGENTS_SKILL" ] \
     && ! owned link "$CLAUDE_LINK"; then
    warn "$CLAUDE_LINK links to $AGENTS_SKILL but is not in this script's install record."
    warn "Run ./install.sh --uninstall, then install again."
    exit 3
  fi
}

# --- plugin mode -----------------------------------------------------------------------------------------------
install_plugin() {
  if helper has-user-level; then
    warn "a user-level install is recorded in $RECORD. Installing the plugin as well would load everything twice."
    warn "Run ./install.sh --uninstall first, then install again."
    exit 3
  fi
  legacy_blocker
  if exists "$CLAUDE_LINK"; then
    warn "$CLAUDE_LINK: not installed by this script; move it away. With the plugin as well, the skill would load twice."
    exit 3
  fi
  local f
  for f in "$CLAUDE_DIR/settings.json" "$CODEX_DIR/hooks.json"; do
    if hooks_have_ours "$f"; then
      warn "$f has hook entries that run $HOOK_MARK scripts; with the plugin as well they would run twice."
      warn "Remove those entries (./install.sh --uninstall removes the ones this script added), then install again."
      exit 3
    fi
  done
  if [ "$HAVE_CLAUDE" = 1 ]; then
    say "Claude Code:"
    if claude_plugin_installed; then
      say "  already installed ($PLUGIN_ID)"
    else
      if ! claude_marketplace_known; then
        run_tool "claude plugin marketplace add" claude plugin marketplace add "$REPO"
        [ "$DRY" = 1 ] || py add-plugin claude marketplace "$MARKETPLACE"
      fi
      run_tool "claude plugin install" claude plugin install "$PLUGIN_ID"
      [ "$DRY" = 1 ] || py add-plugin claude plugin "$PLUGIN_ID"
    fi
  fi
  if [ "$HAVE_CODEX" = 1 ]; then
    say "Codex:"
    if codex_plugin_installed; then
      say "  already installed ($PLUGIN_ID)"
    else
      # codex refuses to start when CODEX_HOME is set to a folder that does not exist yet.
      py ensure-dir "$CODEX_DIR" codex
      if ! codex_marketplace_known; then
        run_tool "codex plugin marketplace add" codex plugin marketplace add "$REPO"
        [ "$DRY" = 1 ] || py add-plugin codex marketplace "$MARKETPLACE"
      fi
      run_tool "codex plugin add" codex plugin add "$PLUGIN_ID"
      [ "$DRY" = 1 ] || py add-plugin codex plugin "$PLUGIN_ID"
    fi
    copy_set "$REPO/codex/agents" '*.toml' "$CODEX_DIR/agents" codex
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

copy_set() { # copy_set SRCDIR GLOB DESTDIR TOOL
  local f
  for f in "$1"/$2; do py copy-file "$f" "$3/$(basename "$f")" "$4"; done
}

# --- user-level mode -------------------------------------------------------------------------------------------
install_user() {
  if plugin_present; then
    warn "the $PLUGIN_ID plugin (or its marketplace) is installed. A user-level install as well would load"
    warn "everything twice. Run ./install.sh --uninstall first, then install again."
    exit 3
  fi
  legacy_blocker
  local users=()
  [ "$HAVE_CLAUDE" = 1 ] && users+=(claude)
  [ "$HAVE_CODEX" = 1 ] && users+=(codex)
  say "Skill:"
  py copy-tree "$REPO/skills/orchestration" "$AGENTS_SKILL" "${users[@]}"
  if [ "$HAVE_CLAUDE" = 1 ]; then
    say "Claude Code:"
    py link "$CLAUDE_LINK" "$AGENTS_SKILL" claude
    copy_set "$REPO/agents" '*.md' "$CLAUDE_DIR/agents" claude
    py json-merge "$CLAUDE_DIR/settings.json" "$REPO/skills/orchestration/hooks/settings-parcasi.json" claude
  fi
  if [ "$HAVE_CODEX" = 1 ]; then
    say "Codex:"
    copy_set "$REPO/codex/agents" '*.toml' "$CODEX_DIR/agents" codex
    py json-merge "$CODEX_DIR/hooks.json" "$REPO/skills/orchestration/hooks/codex-parcasi.json" codex
  fi
  say ""
  say "The skill is a copy: after 'git pull' run ./install.sh --user-level again to update it."
  if [ "$HAVE_CODEX" = 1 ]; then
    say "Codex runs new hooks only after you trust them: open Codex and approve them with /hooks."
  fi
}

# --- uninstall -------------------------------------------------------------------------------------------------
uninstall_recorded() {
  local scope=() tool
  [ "$WANT_CLAUDE" = 1 ] && scope+=(claude)
  [ "$WANT_CODEX" = 1 ] && scope+=(codex)
  for tool in "${scope[@]}"; do
    local have=0 installed=0 known=0
    if [ "$tool" = claude ]; then
      have="$HAVE_CLAUDE"; claude_plugin_installed && installed=1; claude_marketplace_known && known=1
    else
      have="$HAVE_CODEX"; codex_plugin_installed && installed=1; codex_marketplace_known && known=1
    fi
    if helper has-plugin "$tool" plugin; then
      if [ "$installed" = 1 ] && [ "$have" = 0 ]; then
        warn "$tool not found on PATH: the $PLUGIN_ID plugin is still registered there"
      else
        if [ "$installed" = 1 ]; then
          if [ "$tool" = claude ]; then run_tool "claude plugin uninstall" claude plugin uninstall "$PLUGIN_ID"
          else run_tool "codex plugin remove" codex plugin remove "$PLUGIN_ID"; fi
        fi
        [ "$DRY" = 1 ] || py drop-plugin "$tool" plugin
      fi
    elif [ "$installed" = 1 ]; then
      warn "$PLUGIN_ID is installed in $tool but not by this script: left in place"
    fi
    if helper has-plugin "$tool" marketplace; then
      if [ "$known" = 1 ] && [ "$have" = 0 ]; then
        warn "$tool not found on PATH: the $MARKETPLACE marketplace is still registered there"
      else
        if [ "$known" = 1 ]; then
          if [ "$tool" = claude ]; then run_tool "claude plugin marketplace remove" claude plugin marketplace remove "$MARKETPLACE"
          else run_tool "codex plugin marketplace remove" codex plugin marketplace remove "$MARKETPLACE"; fi
        fi
        [ "$DRY" = 1 ] || py drop-plugin "$tool" marketplace
      fi
    fi
  done
  py uninstall-recorded "${scope[@]}"
}

legacy_same_skill() { diff -rq -x __pycache__ "$REPO/skills/orchestration" "$AGENTS_SKILL" >/dev/null 2>&1; }

uninstall_legacy() { # no install record: an install by an older version of this script, removed conservatively
  if [ "$WANT_CLAUDE" = 1 ] && [ "$HAVE_CLAUDE" = 1 ]; then
    if claude_plugin_installed; then run_tool "claude plugin uninstall" claude plugin uninstall "$PLUGIN_ID"; fi
    if claude_marketplace_known; then
      run_tool "claude plugin marketplace remove" claude plugin marketplace remove "$MARKETPLACE"
    fi
  fi
  if [ "$WANT_CODEX" = 1 ] && [ "$HAVE_CODEX" = 1 ]; then
    if codex_plugin_installed; then run_tool "codex plugin remove" codex plugin remove "$PLUGIN_ID"; fi
    if codex_marketplace_known; then
      run_tool "codex plugin marketplace remove" codex plugin marketplace remove "$MARKETPLACE"
    fi
  fi
  local f
  if [ "$WANT_CLAUDE" = 1 ]; then
    if [ -L "$CLAUDE_LINK" ] && [ "$(readlink "$CLAUDE_LINK")" = "$AGENTS_SKILL" ]; then
      # Keep the link while the copy it points to stays (a changed copy is not removed below either).
      if legacy_same_skill; then run rm -f "$CLAUDE_LINK"
      else warn "$AGENTS_SKILL differs from this repo's skill: it and $CLAUDE_LINK are left in place"; fi
    fi
    for f in "$REPO"/agents/*.md; do py legacy-remove-file "$f" "$CLAUDE_DIR/agents/$(basename "$f")"; done
    py legacy-json-remove "$CLAUDE_DIR/settings.json" "$REPO/skills/orchestration/hooks/settings-parcasi.json"
  fi
  if [ "$WANT_CODEX" = 1 ]; then
    for f in "$REPO"/codex/agents/*.toml; do py legacy-remove-file "$f" "$CODEX_DIR/agents/$(basename "$f")"; done
    py legacy-json-remove "$CODEX_DIR/hooks.json" "$REPO/skills/orchestration/hooks/codex-parcasi.json"
  fi
  # The shared skill copy goes only when no tool still uses it: Codex reads it directly (kept under
  # --claude-only) and Claude Code reads it through the symlink (kept while the link is there).
  if [ -d "$AGENTS_SKILL" ] && [ ! -L "$AGENTS_SKILL" ] && [ "$WANT_CODEX" = 1 ] \
     && { [ "$DRY" = 1 ] || [ ! -L "$CLAUDE_LINK" ]; }; then
    if legacy_same_skill; then
      run rm -rf "$AGENTS_SKILL"
      [ "$DRY" = 1 ] || say "  removed $AGENTS_SKILL"
    elif [ "$WANT_CLAUDE" = 0 ] || [ ! -L "$CLAUDE_LINK" ]; then
      warn "$AGENTS_SKILL differs from this repo's skill: left in place"
    fi
  fi
}

legacy_anything() {
  plugin_present && return 0
  user_level_present && return 0
  local f
  for f in "$REPO"/agents/*.md; do exists "$CLAUDE_DIR/agents/$(basename "$f")" && return 0; done
  for f in "$REPO"/codex/agents/*.toml; do exists "$CODEX_DIR/agents/$(basename "$f")" && return 0; done
  return 1
}

# --- main ------------------------------------------------------------------------------------------------------
# Every check that can refuse runs before the first write: a broken settings.json, hooks.json or install record
# stops here with exit 1 and nothing changed.
PREFLIGHT=()
if [ "$MODE" = "user" ]; then
  [ "$HAVE_CLAUDE" = 1 ] && PREFLIGHT+=("$CLAUDE_DIR/settings.json")
  [ "$HAVE_CODEX" = 1 ] && PREFLIGHT+=("$CODEX_DIR/hooks.json")
elif [ "$MODE" = "uninstall" ]; then
  if [ -e "$RECORD" ] || [ -L "$RECORD" ]; then
    py preflight
    SCOPE=()
    [ "$WANT_CLAUDE" = 1 ] && SCOPE+=(claude)
    [ "$WANT_CODEX" = 1 ] && SCOPE+=(codex)
    while IFS= read -r f; do PREFLIGHT+=("$f"); done < <(helper record-json-paths "${SCOPE[@]}")
  else
    [ "$WANT_CLAUDE" = 1 ] && PREFLIGHT+=("$CLAUDE_DIR/settings.json")
    [ "$WANT_CODEX" = 1 ] && PREFLIGHT+=("$CODEX_DIR/hooks.json")
  fi
fi
py preflight ${PREFLIGHT[@]+"${PREFLIGHT[@]}"}

[ "$DRY" = 1 ] && say "Dry run: nothing will be written."
case "$MODE" in
  plugin) install_plugin ;;
  user) install_user ;;
  uninstall)
    if [ -e "$RECORD" ] || [ -L "$RECORD" ]; then
      uninstall_recorded
    elif legacy_anything; then
      warn "no install record at $RECORD (installed by an older version of this script?): removing only files"
      warn "identical to this repo's copies and hook entries identical to ours."
      uninstall_legacy
    fi
    ;;
esac
if [ "$CHANGED" = 0 ] && [ "$MODE" != "uninstall" ]; then
  say "Already installed: nothing changed."
elif [ "$CHANGED" = 0 ]; then
  say "Nothing to uninstall."
else
  if [ "$MODE" != "uninstall" ] && [ "$DRY" = 0 ]; then say "Install record: $RECORD"; fi
  if [ -d "$BACKUP_DIR" ]; then say "Backups: $BACKUP_DIR"; fi
fi
exit 0
