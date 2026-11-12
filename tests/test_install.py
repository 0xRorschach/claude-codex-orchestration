"""Tests for install.sh.

Every test runs install.sh in its own temporary HOME (HOME, CLAUDE_CONFIG_DIR, CODEX_HOME, XDG_STATE_HOME and
XDG_CACHE_HOME all point inside it) under a macOS sandbox profile that denies outbound network. PATH is a
temporary bin folder holding only the tools a test wants, so "only Claude" or "only Codex" is real.

The real claude / codex binaries are used when they are on PATH; tests that need one are skipped otherwise.
Run from the repo root: python3 -m unittest discover -s tests -v
"""
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INSTALL = REPO / "install.sh"
PLUGIN_ID = "orchestration@claude-codex-orchestration"
MARK = "skills/orchestration/hooks/"
SANDBOX = "(version 1)(allow default)(deny network-outbound (remote ip))"

CLAUDE = shutil.which("claude")
CODEX = shutil.which("codex")
NODE = shutil.which("node")
SANDBOX_EXEC = shutil.which("sandbox-exec")
CODEX_OK = bool(CODEX and NODE)

need_claude = unittest.skipUnless(CLAUDE, "claude not on PATH")
need_codex = unittest.skipUnless(CODEX_OK, "codex (and node) not on PATH")
need_both = unittest.skipUnless(CLAUDE and CODEX_OK, "claude and codex both needed")


def snapshot_without_state(root):
    """snapshot() minus ~/.local (the install record and backups live under .local/state)."""
    return {k: v for k, v in snapshot(root).items() if k != ".local" and not k.startswith(".local" + os.sep)}


def fragment_group(name, event, script):
    """The group of a hook fragment whose command runs script."""
    frag = json.loads((REPO / "skills/orchestration/hooks" / name).read_text())
    return next(g for g in frag["hooks"][event] if script in g["hooks"][0]["command"])


def snapshot(root):
    """Every path under root with type, size and mtime: equal snapshots mean nothing was written."""
    out = {}
    # Apple's /usr/bin/python3 keeps its bytecode cache in Library/Caches/com.apple.python under HOME: the interpreter
    # writes it on any run, so it says nothing about what install.sh wrote.
    skip = os.path.join(str(root), "Library", "Caches", "com.apple.python")
    for dirpath, dirnames, filenames in os.walk(root):
        if dirpath == skip or dirpath.startswith(skip + os.sep):
            continue
        for name in dirnames + filenames:
            p = os.path.join(dirpath, name)
            if p == skip or os.path.dirname(skip).startswith(p):
                continue
            st = os.lstat(p)
            # A folder's mtime is left out: it changes when anything inside is created and removed again (the
            # install lock does that in the state folder), and its entries are compared one by one anyway.
            isdir = stat.S_ISDIR(st.st_mode)
            out[os.path.relpath(p, root)] = (st.st_mode, 0 if isdir else st.st_size, 0 if isdir else st.st_mtime_ns)
    return out


class Base(unittest.TestCase):
    tools = ("claude", "codex")

    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="orch-install-")).resolve()
        real_home = Path(os.path.expanduser("~")).resolve()
        # Safety: the temporary HOME must never be (or sit inside) the real HOME.
        assert real_home not in self.home.parents and self.home != real_home, self.home
        self.bin = self.home / "_bin"
        self.bin.mkdir()
        os.symlink(sys.executable, self.bin / "python3")
        if "claude" in self.tools and CLAUDE:
            os.symlink(CLAUDE, self.bin / "claude")
        if "codex" in self.tools and CODEX_OK:
            os.symlink(CODEX, self.bin / "codex")
            os.symlink(NODE, self.bin / "node")
        self.claude_dir = self.home / ".claude"
        self.codex_dir = self.home / ".codex"
        self.skill = self.home / ".agents" / "skills" / "orchestration"

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def env(self):
        keep = {k: v for k, v in os.environ.items()
                if k in ("LANG", "LC_ALL", "TERM", "TMPDIR", "USER", "LOGNAME", "SHELL")}
        keep.update({
            "HOME": str(self.home),
            "CLAUDE_CONFIG_DIR": str(self.claude_dir),
            "CODEX_HOME": str(self.codex_dir),
            "XDG_STATE_HOME": str(self.home / ".local" / "state"),
            "XDG_CACHE_HOME": str(self.home / ".cache"),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "PATH": "%s:/usr/bin:/bin:/usr/sbin:/sbin" % self.bin,
        })
        return keep

    def sh(self, *args, env_ek=None, stdin=None, cwd=None):
        cmd = list(args)
        if SANDBOX_EXEC:
            cmd = [SANDBOX_EXEC, "-p", SANDBOX] + cmd
        env = self.env()
        env.update(env_ek or {})
        return subprocess.run(cmd, capture_output=True, text=True, env=env, input=stdin,
                              cwd=str(cwd or self.home), timeout=300)

    def fake_tool(self, name, code=0):
        """An executable stand-in for claude/codex that exits with code (user-level mode never calls the tools)."""
        p = self.bin / name
        if p.exists() or p.is_symlink():
            p.unlink()
        p.write_text("#!/bin/sh\necho \"fake %s $*\"\nexit %d\n" % (name, code))
        p.chmod(0o755)

    @property
    def record(self):
        return self.home / ".local/state/claude-codex-orchestration/install-record.json"

    def install(self, *flags):
        return self.sh("bash", str(INSTALL), *flags)

    def ok(self, p):
        self.assertEqual(p.returncode, 0, "stdout:\n%s\nstderr:\n%s" % (p.stdout, p.stderr))
        return p

    def our_hook_commands(self, path):
        if not path.exists():
            return []
        data = json.loads(path.read_text())
        return [h["command"] for gs in data.get("hooks", {}).values() for g in gs for h in g["hooks"]
                if MARK in h["command"]]

    def claude_installed(self):
        f = self.claude_dir / "plugins" / "installed_plugins.json"
        return f.exists() and PLUGIN_ID in json.loads(f.read_text()).get("plugins", {})

    def codex_installed(self):
        f = self.codex_dir / "config.toml"
        return f.exists() and '[plugins."%s"]' % PLUGIN_ID in f.read_text()

    def codex_roles(self):
        d = self.codex_dir / "agents"
        return sorted(p.name for p in d.glob("*.toml")) if d.exists() else []


ROLES = ["explorer.toml", "researcher.toml", "scanner.toml", "worker.toml"]
AGENTS = ["explorer.md", "fable-reviewer.md", "researcher.md", "scanner.md", "worker.md"]


class TestPluginMode(Base):
    @need_both
    def test_both_tools(self):
        p = self.ok(self.install())
        self.assertTrue(self.claude_installed())
        self.assertTrue(self.codex_installed())
        self.assertEqual(self.codex_roles(), ROLES)
        self.assertIn("Keep this clone", p.stdout)
        self.assertIn("/hooks", p.stdout)
        d = self.ok(self.sh("claude", "plugin", "details", PLUGIN_ID)).stdout
        self.assertIn("Skills (1)", d)
        self.assertIn("Agents (5)", d)
        self.assertIn("SessionStart, PreToolUse, PostToolUse", d)
        pi = self.ok(self.sh("codex", "debug", "prompt-input", "x")).stdout
        self.assertRegex(pi, r"file: r\d+/orchestration/[^/]+/skills/orchestration/SKILL\.md")
        # Nothing user-level was written.
        self.assertFalse(self.skill.exists())
        self.assertEqual(self.our_hook_commands(self.claude_dir / "settings.json"), [])

    @need_both
    def test_second_run_changes_nothing(self):
        self.ok(self.install())
        before = snapshot(self.home)
        p = self.ok(self.install())
        self.assertIn("already installed", p.stdout)
        self.assertIn("Already installed: nothing changed.", p.stdout)
        self.assertEqual(snapshot(self.home), before)

    @need_both
    def test_dry_run_writes_nothing(self):
        before = snapshot(self.home)
        p = self.ok(self.install("--dry-run"))
        self.assertIn("[dry-run] claude plugin install", p.stdout)
        self.assertIn("[dry-run] codex plugin add", p.stdout)
        self.assertEqual(snapshot(self.home), before)

    @need_both
    def test_uninstall(self):
        self.ok(self.install())
        self.ok(self.install("--uninstall"))
        self.assertFalse(self.claude_installed())
        self.assertFalse(self.codex_installed())
        self.assertEqual(self.codex_roles(), [])
        self.assertIn("Nothing to uninstall.", self.ok(self.install("--uninstall")).stdout)

    @need_codex
    def test_uninstall_keeps_changed_role(self):
        self.ok(self.install("--codex-only"))
        role = self.codex_dir / "agents" / "worker.toml"
        role.write_text(role.read_text() + "\n# local edit\n")
        p = self.ok(self.install("--uninstall", "--codex-only"))
        self.assertTrue(role.exists())
        self.assertIn("worker.toml was changed after install: left in place", p.stderr)

    @need_codex
    def test_existing_role_is_backed_up(self):
        (self.codex_dir / "agents").mkdir(parents=True)
        (self.codex_dir / "agents" / "worker.toml").write_text('name = "mine"\n')
        p = self.ok(self.install("--codex-only"))
        self.assertIn("backed up", p.stdout)
        backups = list((self.home / ".local/state/claude-codex-orchestration/backups").rglob("worker.toml"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), 'name = "mine"\n')


class TestInstalledHooks(Base):
    """The hooks must run from where they were installed and behave on sample input."""

    def gate(self, script, tip):
        girdi = {"session_id": "s1", "transcript_path": str(self.home / "t.jsonl"), "cwd": str(self.home),
                 "hook_event_name": "PreToolUse", "tool_name": "Agent",
                 "tool_input": {"description": "d", "prompt": "p", "subagent_type": tip}}
        return self.sh("python3", str(script), stdin=json.dumps(girdi),
                       env_ek={"ORCH_LOG_DIR": str(self.home / "logs")})

    def check_hooks(self, hooks_dir, env_ek=None):
        gate = hooks_dir / "agent-tip-kapisi.py"
        p = self.gate(gate, "general-purpose")
        self.assertEqual(p.returncode, 0, p.stderr)
        out = json.loads(p.stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        p = self.gate(gate, "orchestration:explorer")
        self.assertEqual((p.returncode, p.stdout.strip()), (0, ""), p.stderr)
        start = json.dumps({"session_id": "s1", "hook_event_name": "SessionStart", "source": "startup"})
        for tool in ("claude", "codex"):
            p = self.sh("python3", str(hooks_dir / "superpowers_surum_bekcisi.py"), tool, stdin=start, env_ek=env_ek)
            self.assertEqual((p.returncode, p.stdout.strip(), p.stderr.strip()), (0, "", ""), tool)
        post = json.dumps({"session_id": "s1", "hook_event_name": "PostToolUse", "tool_name": "Bash",
                           "tool_input": {"command": "ls"}, "tool_response": {"stdout": "a"}})
        p = self.sh("python3", str(hooks_dir / "okuma_butcesi.py"), "claude", stdin=post, env_ek=env_ek)
        self.assertEqual((p.returncode, p.stdout.strip()), (0, ""), p.stderr)
        # Load reminder: a transcript without a load trace must give the note. Exit 0 alone would prove nothing,
        # because the hook also exits 0 silently when its helper module fails to import.
        transcript = self.home / ("reminder-%d.jsonl" % len(list(self.home.glob("reminder-*.jsonl"))))
        # A main-session Codex header first (Codex reads it to tell the main session from a subagent), then a plain line.
        transcript.write_text(json.dumps({"type": "session_meta", "payload": {"id": "main", "source": "cli"}}) + "\n"
                              + json.dumps({"type": "user", "message": {"content": "hello"}}) + "\n")
        state = {"ORCH_LOG_DIR": str(self.home / "reminder-state" / transcript.stem)}
        for tool, name in (("claude", "Agent"), ("codex", "spawn_agent")):
            pre = {"session_id": "s-" + tool, "transcript_path": str(transcript), "cwd": str(self.home),
                   "hook_event_name": "PreToolUse", "tool_name": name, "tool_input": {"prompt": "p"}}
            if tool == "codex":
                pre["turn_id"] = "t1"
            p = self.sh("python3", str(hooks_dir / "orkestrasyon_hatirlatici.py"), tool, stdin=json.dumps(pre),
                        env_ek=dict(env_ek or {}, **state))
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("orchestration skill was not loaded",
                          json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"], tool)

    @need_both
    def test_plugin_install_location(self):
        self.ok(self.install())
        plugins = json.loads((self.claude_dir / "plugins" / "installed_plugins.json").read_text())["plugins"]
        claude_root = Path(plugins[PLUGIN_ID][0]["installPath"])
        self.check_hooks(claude_root / "skills/orchestration/hooks", {"CLAUDE_PLUGIN_ROOT": str(claude_root)})
        codex_roots = list((self.codex_dir / "plugins" / "cache").glob("*/orchestration/*"))
        self.assertEqual(len(codex_roots), 1)
        self.check_hooks(codex_roots[0] / "skills/orchestration/hooks", {"PLUGIN_ROOT": str(codex_roots[0])})

    @need_claude
    def test_user_level_install_location(self):
        self.ok(self.install("--user-level", "--claude-only"))
        self.check_hooks(self.claude_dir / "skills/orchestration/hooks")


class TestUserLevel(Base):
    @need_both
    def test_both_tools(self):
        self.ok(self.install("--user-level"))
        self.assertTrue((self.skill / "SKILL.md").is_file())
        self.assertFalse(self.skill.is_symlink())
        link = self.claude_dir / "skills" / "orchestration"
        self.assertTrue(link.is_symlink())
        self.assertEqual(Path(os.readlink(link)), self.skill)
        self.assertEqual(sorted(p.name for p in (self.claude_dir / "agents").glob("*.md")), AGENTS)
        self.assertEqual(len(self.our_hook_commands(self.claude_dir / "settings.json")), 5)
        self.assertEqual(len(self.our_hook_commands(self.codex_dir / "hooks.json")), 3)
        self.assertEqual(self.codex_roles(), ROLES)
        self.assertFalse(self.claude_installed())
        self.assertFalse(self.codex_installed())
        pi = self.ok(self.sh("codex", "debug", "prompt-input", "x")).stdout
        # Codex prints skill roots as aliases (r0, r1 ...): a user-level skill shows as rN/orchestration/SKILL.md.
        self.assertRegex(pi, r"file: r\d+/orchestration/SKILL\.md")

    @need_both
    def test_second_run_changes_nothing(self):
        self.ok(self.install("--user-level"))
        before = snapshot(self.home)
        p = self.ok(self.install("--user-level"))
        self.assertIn("Already installed: nothing changed.", p.stdout)
        self.assertEqual(snapshot(self.home), before)

    @need_both
    def test_dry_run_writes_nothing(self):
        before = snapshot(self.home)
        p = self.ok(self.install("--user-level", "--dry-run"))
        self.assertIn("[dry-run]", p.stdout)
        self.assertEqual(snapshot(self.home), before)

    @need_both
    def test_uninstall_keeps_existing_config(self):
        self.claude_dir.mkdir()
        self.codex_dir.mkdir()
        settings = {"theme": "dark", "hooks": {"PostToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo other"}]}]}}
        codex_hooks = {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}
        (self.claude_dir / "settings.json").write_text(json.dumps(settings))
        (self.codex_dir / "hooks.json").write_text(json.dumps(codex_hooks))
        self.ok(self.install("--user-level"))
        merged = json.loads((self.claude_dir / "settings.json").read_text())
        self.assertEqual(merged["theme"], "dark")
        self.assertEqual(len(merged["hooks"]["PostToolUse"]), 3)
        self.ok(self.install("--uninstall"))
        self.assertEqual(json.loads((self.claude_dir / "settings.json").read_text()), settings)
        self.assertEqual(json.loads((self.codex_dir / "hooks.json").read_text()), codex_hooks)
        self.assertFalse(self.skill.exists())
        self.assertFalse((self.claude_dir / "skills" / "orchestration").is_symlink())
        self.assertEqual(list((self.claude_dir / "agents").glob("*.md")), [])
        self.assertEqual(self.codex_roles(), [])

    @need_both
    def test_dry_run_uninstall_writes_nothing(self):
        self.ok(self.install("--user-level"))
        before = snapshot(self.home)
        self.ok(self.install("--uninstall", "--dry-run"))
        self.assertEqual(snapshot(self.home), before)


class TestDoubleInstall(Base):
    @need_both
    def test_plugin_after_user_level(self):
        self.ok(self.install("--user-level"))
        before = snapshot(self.home)
        p = self.install()
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertIn("twice", p.stderr)
        self.assertEqual(snapshot(self.home), before)

    @need_both
    def test_user_level_after_plugin(self):
        self.ok(self.install())
        before = snapshot(self.home)
        p = self.install("--user-level")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertEqual(snapshot(self.home), before)

    @need_claude
    def test_existing_agents_skill_copy_blocks_plugin(self):
        self.skill.mkdir(parents=True)
        (self.skill / "SKILL.md").write_text("x")
        self.assertEqual(self.install("--claude-only").returncode, 3)
        self.assertFalse(self.claude_installed())


class TestOnlyClaude(Base):
    tools = ("claude",)

    @need_claude
    def test_plugin(self):
        p = self.ok(self.install())
        self.assertIn("codex not found: skipping Codex", p.stdout)
        self.assertTrue(self.claude_installed())
        self.assertFalse(self.codex_dir.exists())

    @need_claude
    def test_user_level(self):
        self.ok(self.install("--user-level"))
        self.assertTrue((self.claude_dir / "skills" / "orchestration" / "SKILL.md").is_file())
        self.assertFalse(self.codex_dir.exists())
        self.ok(self.install("--uninstall"))
        self.assertFalse(self.skill.exists())


class TestOnlyCodex(Base):
    tools = ("codex",)

    @need_codex
    def test_plugin(self):
        p = self.ok(self.install())
        self.assertIn("claude not found: skipping Claude Code", p.stdout)
        self.assertTrue(self.codex_installed())
        self.assertEqual(self.codex_roles(), ROLES)
        self.assertFalse(self.claude_dir.exists())

    @need_codex
    def test_user_level(self):
        self.ok(self.install("--user-level"))
        self.assertTrue((self.skill / "SKILL.md").is_file())
        self.assertFalse(self.claude_dir.exists())
        self.assertEqual(len(self.our_hook_commands(self.codex_dir / "hooks.json")), 3)


class TestNoTools(Base):
    tools = ()

    def test_no_tool_exits_1(self):
        p = self.install()
        self.assertEqual(p.returncode, 1)
        self.assertIn("neither claude", p.stderr)

    def test_help(self):
        p = self.ok(self.install("--help"))
        self.assertIn("--user-level", p.stdout)

    def test_unknown_option(self):
        self.assertEqual(self.install("--force").returncode, 2)

class FakeTools(Base):
    """User-level installs and uninstalls never call claude/codex, so stand-ins are enough and these tests always run."""
    tools = ()

    def setUp(self):
        super().setUp()
        self.fake_tool("claude")
        self.fake_tool("codex")


class TestSymlinkedTargets(FakeTools):
    """Finding A: an existing target that is a symlink must be replaced by a file, never written through."""

    def link_case(self, dest, relative, flags):
        outside = self.home / "dotfiles"
        outside.mkdir()
        mine = outside / dest.name
        mine.write_text("mine\n")
        dest.parent.mkdir(parents=True)
        target = os.path.relpath(mine, dest.parent) if relative else str(mine)
        os.symlink(target, dest)
        p = self.ok(self.install("--user-level", *flags))
        self.assertEqual(mine.read_text(), "mine\n", "the file behind the link was written through")
        self.assertFalse(dest.is_symlink())
        self.assertIn("symlink to %s" % target, p.stdout)
        rec = json.loads(self.record.read_text())
        item = next(i for i in rec["items"] if i.get("path") == str(dest))
        self.assertEqual((item["backup"]["type"], item["backup"]["link_target"]), ("symlink", target))
        self.assertEqual(Path(item["backup"]["path"]).read_text(), "mine\n")
        self.ok(self.install("--uninstall", *flags))
        self.assertTrue(dest.is_symlink())
        self.assertEqual(os.readlink(dest), target)
        self.assertEqual(mine.read_text(), "mine\n")

    def test_codex_role_absolute_link(self):
        self.link_case(self.codex_dir / "agents" / "worker.toml", False, ("--codex-only",))

    def test_codex_role_relative_link(self):
        self.link_case(self.codex_dir / "agents" / "worker.toml", True, ("--codex-only",))

    def test_claude_agent_absolute_link(self):
        self.link_case(self.claude_dir / "agents" / "worker.md", False, ("--claude-only",))

    def test_claude_agent_relative_link(self):
        self.link_case(self.claude_dir / "agents" / "worker.md", True, ("--claude-only",))


class TestRecord(FakeTools):
    """Finding B: uninstall removes only what the install added, and puts back what it replaced."""

    def test_record_lists_what_was_added(self):
        self.ok(self.install("--user-level"))
        self.assertEqual(stat.S_IMODE(self.record.stat().st_mode), 0o600)
        rec = json.loads(self.record.read_text())
        self.assertEqual((rec["version"], rec["modes"], sorted(rec["tools"])), (1, ["user"], ["claude", "codex"]))
        kinds = {}
        for i in rec["items"]:
            kinds[i["kind"]] = kinds.get(i["kind"], 0) + 1
        self.assertEqual((kinds["file"], kinds["tree"], kinds["link"], kinds["json"]), (9, 1, 1, 8))
        worker = self.claude_dir / "agents" / "worker.md"
        item = next(i for i in rec["items"] if i.get("path") == str(worker))
        self.assertEqual(item["sha256"], hashlib.sha256(worker.read_bytes()).hexdigest())
        self.assertIsNone(item["backup"])
        tree = next(i for i in rec["items"] if i["kind"] == "tree")
        self.assertEqual(sorted(tree["users"]), ["claude", "codex"])

    def test_preexisting_hook_entry_survives(self):
        group = fragment_group("settings-parcasi.json", "PreToolUse", "agent-tip-kapisi.py")
        self.claude_dir.mkdir()
        settings = {"hooks": {"PreToolUse": [group]}}
        (self.claude_dir / "settings.json").write_text(json.dumps(settings))
        self.ok(self.install("--user-level", "--claude-only"))
        merged = json.loads((self.claude_dir / "settings.json").read_text())
        self.assertEqual(len(self.our_hook_commands(self.claude_dir / "settings.json")), 5)
        self.assertEqual(merged["hooks"]["PreToolUse"].count(group), 1)
        self.ok(self.install("--uninstall", "--claude-only"))
        self.assertEqual(json.loads((self.claude_dir / "settings.json").read_text()), settings)

    def test_overwritten_user_file_comes_back(self):
        agents = self.claude_dir / "agents"
        agents.mkdir(parents=True)
        (agents / "worker.md").write_text("my worker\n")
        (agents / "worker.md").chmod(0o640)
        self.ok(self.install("--user-level", "--claude-only"))
        self.assertNotEqual((agents / "worker.md").read_text(), "my worker\n")
        self.ok(self.install("--uninstall", "--claude-only"))
        self.assertEqual((agents / "worker.md").read_text(), "my worker\n")
        self.assertEqual(stat.S_IMODE((agents / "worker.md").stat().st_mode), 0o640)
        self.assertEqual(sorted(p.name for p in agents.iterdir()), ["worker.md"])

    def test_file_changed_after_install_is_kept(self):
        self.ok(self.install("--user-level", "--claude-only"))
        explorer = self.claude_dir / "agents" / "explorer.md"
        explorer.write_text(explorer.read_text() + "\nmy note\n")
        p = self.ok(self.install("--uninstall", "--claude-only"))
        self.assertIn("explorer.md was changed after install: left in place", p.stderr)
        self.assertTrue(explorer.read_text().endswith("my note\n"))
        self.assertFalse((self.claude_dir / "agents" / "worker.md").exists())
        self.assertFalse(self.record.exists(), "nothing of ours is left, so the record goes")

    def test_skill_copy_changed_after_install_is_kept(self):
        self.ok(self.install("--user-level"))
        (self.skill / "SKILL.md").write_text("edited\n")
        p = self.ok(self.install("--uninstall"))
        self.assertIn("%s was changed after install: left in place" % self.skill, p.stderr)
        self.assertEqual((self.skill / "SKILL.md").read_text(), "edited\n")

    def test_full_cycle_leaves_home_as_it_was(self):
        before = snapshot_without_state(self.home)
        self.ok(self.install("--user-level"))
        self.ok(self.install("--uninstall"))
        self.assertEqual(snapshot_without_state(self.home), before)
        self.assertFalse(self.record.exists())

    def test_legacy_install_without_record(self):
        # An install by an older version of this script: same files, no record.
        self.ok(self.install("--user-level"))
        self.record.unlink()
        settings = self.claude_dir / "settings.json"
        data = json.loads(settings.read_text())
        data["hooks"]["SessionStart"].append({"hooks": [{"type": "command",
                                                         "command": "python3 /x/%sother.py" % MARK}]})
        settings.write_text(json.dumps(data))
        (self.codex_dir / "agents" / "worker.toml").write_text("mine\n")
        p = self.install("--user-level")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertIn("%s exists but is not in this script's install record" % self.skill, p.stderr)
        self.assertIn("./install.sh --uninstall", p.stderr)
        p = self.ok(self.install("--uninstall"))
        self.assertIn("no install record", p.stderr)
        self.assertIn("worker.toml differs from this repo's copy: left in place", p.stderr)
        self.assertEqual((self.codex_dir / "agents" / "worker.toml").read_text(), "mine\n")
        self.assertEqual(self.our_hook_commands(settings), ["python3 /x/%sother.py" % MARK])
        self.assertEqual(self.our_hook_commands(self.codex_dir / "hooks.json"), [])
        self.assertFalse(self.skill.exists())

    def test_legacy_changed_skill_keeps_its_link(self):
        self.ok(self.install("--user-level", "--claude-only"))
        self.record.unlink()
        (self.skill / "SKILL.md").write_text("edited\n")
        p = self.ok(self.install("--uninstall"))
        self.assertIn("differs from this repo's skill", p.stderr)
        link = self.claude_dir / "skills" / "orchestration"
        self.assertTrue(link.is_symlink())
        self.assertEqual((link / "SKILL.md").read_text(), "edited\n")


class TestPermissions(FakeTools):
    """Finding C: rewriting settings.json / hooks.json keeps their mode."""

    def test_private_config_stays_private(self):
        self.claude_dir.mkdir()
        self.codex_dir.mkdir()
        files = [(self.claude_dir / "settings.json", {"theme": "dark"}), (self.codex_dir / "hooks.json", {})]
        for f, data in files:
            f.write_text(json.dumps(data))
            f.chmod(0o600)
        self.ok(self.install("--user-level"))
        for f, _ in files:
            self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600, f)
        self.ok(self.install("--uninstall"))
        for f, data in files:
            self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600, f)
            self.assertEqual(json.loads(f.read_text()), data)
        self.assertEqual(list(self.home.glob(".*/.*.json.*")), [], "a temporary file was left behind")


class TestUnreadableJson(FakeTools):
    """Finding D: a file that does not parse stops the run before anything is written."""

    def check_refused(self, flags, path):
        before = snapshot(self.home)
        p = self.install(*flags)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("error: cannot parse %s: " % path, p.stderr)
        self.assertIn("; fix or move it and rerun", p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        self.assertNotIn("merged", p.stdout)
        self.assertEqual(snapshot(self.home), before)

    def test_commented_settings_on_install(self):
        self.claude_dir.mkdir()
        (self.claude_dir / "settings.json").write_text('// my settings\n{"theme": "dark"}\n')
        self.check_refused(("--user-level",), self.claude_dir / "settings.json")

    def test_broken_codex_hooks_on_install(self):
        self.codex_dir.mkdir()
        (self.codex_dir / "hooks.json").write_text('{"hooks": [1, 2]}\n')
        self.check_refused(("--user-level",), self.codex_dir / "hooks.json")

    def test_broken_settings_on_uninstall(self):
        self.ok(self.install("--user-level"))
        (self.claude_dir / "settings.json").write_text("{not json\n")
        self.check_refused(("--uninstall",), self.claude_dir / "settings.json")

    def test_broken_settings_on_legacy_uninstall(self):
        self.ok(self.install("--user-level"))
        self.record.unlink()
        (self.claude_dir / "settings.json").write_text("{not json\n")
        self.check_refused(("--uninstall",), self.claude_dir / "settings.json")

    def test_broken_record(self):
        self.ok(self.install("--user-level"))
        self.record.write_text("[]\n")
        self.check_refused(("--uninstall",), self.record)


class TestClaudeOnlyCycle(FakeTools):
    """Finding E: --claude-only install and uninstall leave nothing behind and can be repeated."""

    def test_cycle(self):
        before = snapshot_without_state(self.home)
        for _ in range(2):
            self.ok(self.install("--user-level", "--claude-only"))
            self.assertTrue((self.skill / "SKILL.md").is_file())
            self.ok(self.install("--uninstall", "--claude-only"))
            self.assertFalse(self.skill.exists())
            self.assertEqual(snapshot_without_state(self.home), before)
        self.assertIn("Nothing to uninstall.", self.ok(self.install("--uninstall")).stdout)

    def test_codex_keeps_shared_copy(self):
        self.ok(self.install("--user-level"))
        self.ok(self.install("--uninstall", "--claude-only"))
        self.assertTrue((self.skill / "SKILL.md").is_file())
        self.assertFalse((self.claude_dir / "skills" / "orchestration").is_symlink())
        self.assertEqual(len(self.our_hook_commands(self.codex_dir / "hooks.json")), 3)
        self.ok(self.install("--uninstall", "--codex-only"))
        self.assertFalse(self.skill.exists())
        self.assertFalse(self.record.exists())

    def test_foreign_claude_skill_blocks_plugin(self):
        link = self.claude_dir / "skills" / "orchestration"
        link.mkdir(parents=True)
        (link / "SKILL.md").write_text("someone else's\n")
        p = self.install("--claude-only")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertIn("%s: not installed by this script; move it away" % link, p.stderr)

    def test_user_level_replaces_and_restores_foreign_claude_skill(self):
        link = self.claude_dir / "skills" / "orchestration"
        link.mkdir(parents=True)
        (link / "SKILL.md").write_text("someone else's\n")
        self.ok(self.install("--user-level", "--claude-only"))
        self.assertTrue(link.is_symlink())
        self.ok(self.install("--uninstall", "--claude-only"))
        self.assertFalse(link.is_symlink())
        self.assertEqual((link / "SKILL.md").read_text(), "someone else's\n")


class TestToolFailure(Base):
    """Finding H: a failing claude/codex command stops the script with its own message and exit 1."""
    tools = ()

    def test_claude_failure(self):
        self.fake_tool("claude", 5)
        p = self.install("--claude-only")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("error: claude plugin marketplace add failed (exit 5)", p.stderr)
        # The marketplace was recorded as pending before the command ran; uninstall settles it and the record goes.
        items = json.loads(self.record.read_text())["items"]
        self.assertEqual([(i["kind"], i["what"], i.get("pending")) for i in items], [("plugin", "marketplace", True)])
        self.ok(self.install("--uninstall", "--claude-only"))
        self.assertFalse(self.record.exists())

    def test_codex_failure(self):
        self.fake_tool("codex", 7)
        p = self.install("--codex-only")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("error: codex plugin marketplace add failed (exit 7)", p.stderr)
        self.assertEqual(self.codex_roles(), [], "nothing is copied after a failed tool command")


class TestRecordEdges(FakeTools):
    """Third round: legacy plugin installs, interrupted runs, plugin-only records, JSON formatting, broken links,
    folders in the way, the lock, backup names and record validation."""

    def state(self):
        return self.home / ".local/state/claude-codex-orchestration"

    # Y1
    def test_plugin_mode_role_without_record_blocks(self):
        roles = self.codex_dir / "agents"
        roles.mkdir(parents=True)
        shutil.copy(str(REPO / "codex/agents/worker.toml"), str(roles / "worker.toml"))
        before = snapshot(self.home)
        p = self.install("--codex-only")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertIn("found an install without a record: run ./install.sh --uninstall first", p.stderr)
        self.assertIn(str(roles / "worker.toml"), p.stderr)
        self.assertFalse(self.record.exists())
        self.assertEqual(snapshot(self.home), before)
        self.ok(self.install("--uninstall", "--codex-only"))
        self.assertFalse((roles / "worker.toml").exists())
        self.ok(self.install("--codex-only"))
        self.assertTrue(self.record.exists())

    def test_plugin_mode_registered_plugin_without_record_blocks(self):
        plugins = self.claude_dir / "plugins"
        plugins.mkdir(parents=True)
        (plugins / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {PLUGIN_ID: [{}]}}))
        p = self.install("--claude-only")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertIn("found an install without a record: run ./install.sh --uninstall first", p.stderr)
        self.assertFalse(self.record.exists())

    # Y2
    def test_interrupted_install_is_cleaned_up(self):
        self.claude_dir.mkdir()
        before = snapshot_without_state(self.home)
        agents = self.claude_dir / "agents"
        agents.mkdir()
        agents.chmod(0o500)  # the first agent copy fails half way through the run
        try:
            p = self.install("--user-level", "--claude-only")
        finally:
            agents.chmod(0o755)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        rec = json.loads(self.record.read_text())
        pending = [i["path"] for i in rec["items"] if i.get("pending")]
        self.assertEqual(pending, [str(agents / "explorer.md")])
        agents.rmdir()
        self.ok(self.install("--uninstall", "--claude-only"))
        self.assertFalse(self.record.exists())
        self.assertEqual(snapshot_without_state(self.home), before)

    def test_pending_item_with_original_content_is_left(self):
        agents = self.claude_dir / "agents"
        agents.mkdir(parents=True)
        (agents / "worker.md").write_text("mine\n")
        self.ok(self.install("--user-level", "--claude-only"))
        rec = json.loads(self.record.read_text())
        # As if the run had stopped right after recording the item, before writing it.
        (agents / "worker.md").write_text("mine\n")
        for i in rec["items"]:
            if i.get("path") == str(agents / "worker.md"):
                i["pending"] = True
        self.record.write_text(json.dumps(rec))
        p = self.ok(self.install("--uninstall", "--claude-only"))
        self.assertEqual((agents / "worker.md").read_text(), "mine\n")
        self.assertNotIn("worker.md was changed", p.stderr)

    def test_sweep_removes_unrecorded_copies_of_ours(self):
        self.ok(self.install("--user-level", "--claude-only"))
        rec = json.loads(self.record.read_text())
        worker = str(self.claude_dir / "agents" / "worker.md")
        rec["items"] = [i for i in rec["items"] if i.get("path") != worker
                        and not (i["kind"] == "json" and i["event"] == "SessionStart")]
        self.record.write_text(json.dumps(rec))
        p = self.ok(self.install("--uninstall", "--claude-only"))
        self.assertIn("worker.md is not in the install record but is identical to this repo's copy: removed",
                      p.stderr)
        self.assertIn("1 hook entry running this repo's hooks was not in the install record: removed", p.stderr)
        self.assertFalse(Path(worker).exists())
        self.assertEqual(self.our_hook_commands(self.claude_dir / "settings.json"), [])
        self.assertFalse(self.record.exists())

    def test_identical_file_there_before_install_stays(self):
        agents = self.claude_dir / "agents"
        agents.mkdir(parents=True)
        shutil.copy(str(REPO / "agents/worker.md"), str(agents / "worker.md"))
        self.ok(self.install("--user-level", "--claude-only"))
        p = self.ok(self.install("--uninstall", "--claude-only"))
        self.assertTrue((agents / "worker.md").is_file())
        self.assertNotIn("worker.md", p.stderr)
        self.assertEqual(sorted(x.name for x in agents.iterdir()), ["worker.md"])

    # Y3
    def test_plugin_only_record_goes_on_uninstall(self):
        p = self.ok(self.install("--claude-only"))
        self.assertIn("fake claude plugin install", p.stdout)
        kinds = [(i["kind"], i.get("pending")) for i in json.loads(self.record.read_text())["items"]]
        self.assertEqual(kinds, [("plugin", None), ("plugin", None)])
        self.ok(self.install("--uninstall", "--claude-only"))
        self.assertFalse(self.record.exists())

    # Y4
    def test_json_round_trip_is_byte_identical(self):
        self.claude_dir.mkdir()
        original = json.dumps({"theme": "ğüş", "hooks": {}}, indent=4, ensure_ascii=False) + "\n"
        settings = self.claude_dir / "settings.json"
        settings.write_bytes(original.encode("utf-8"))
        self.ok(self.install("--user-level", "--claude-only"))
        merged = settings.read_text(encoding="utf-8")
        self.assertIn('\n    "theme": "ğüş"', merged)
        self.assertIn('\n        "SessionStart": [', merged)
        self.ok(self.install("--uninstall", "--claude-only"))
        self.assertEqual(settings.read_bytes(), original.encode("utf-8"))

    def test_json_created_keys_go(self):
        self.claude_dir.mkdir()
        settings = self.claude_dir / "settings.json"
        settings.write_text('{"theme": "dark"}')
        self.ok(self.install("--user-level", "--claude-only"))
        self.ok(self.install("--uninstall", "--claude-only"))
        self.assertEqual(settings.read_text(), '{\n  "theme": "dark"\n}')

    # Y5
    def test_broken_symlink_config_refused(self):
        self.claude_dir.mkdir()
        settings = self.claude_dir / "settings.json"
        os.symlink(str(self.home / "dotfiles" / "missing.json"), settings)
        before = snapshot(self.home)
        p = self.install("--user-level", "--claude-only")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("error: %s is a broken symlink; fix it and rerun" % settings, p.stderr)
        self.assertEqual(snapshot(self.home), before)

    # Y6
    def test_folder_where_a_file_goes_refused(self):
        (self.claude_dir / "agents" / "worker.md").mkdir(parents=True)
        before = snapshot(self.home)
        p = self.install("--user-level", "--claude-only")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("worker.md is a directory, not a file; move it away and rerun", p.stderr)
        self.assertEqual(snapshot(self.home), before)

    def test_lock_blocks_a_second_run(self):
        lock = self.state() / "install.lock"
        lock.mkdir(parents=True)
        (lock / "pid").write_text("%d\n" % os.getpid())  # a live process
        before = snapshot(self.home)
        p = self.install("--user-level", "--claude-only")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("error: another install.sh is running (lock: %s)" % lock, p.stderr)
        self.assertEqual(snapshot(self.home), before)

    def test_stale_lock_is_taken_over(self):
        dead = subprocess.Popen(["true"])
        dead.wait()
        lock = self.state() / "install.lock"
        lock.mkdir(parents=True)
        (lock / "pid").write_text("%d\n" % dead.pid)
        p = self.ok(self.install("--user-level", "--claude-only"))
        self.assertIn("removing a stale lock", p.stderr)
        self.assertFalse(lock.exists(), "the lock is released on exit")

    def test_pidless_old_lock_is_taken_over(self):
        lock = self.state() / "install.lock"
        lock.mkdir(parents=True)
        old = time.time() - 3600
        os.utime(str(lock), (old, old))
        p = self.ok(self.install("--user-level", "--claude-only"))
        self.assertIn("removing a stale lock without a pid, older than 10 minutes", p.stderr)
        self.assertFalse(lock.exists())

    def test_pidless_fresh_lock_blocks(self):
        lock = self.state() / "install.lock"
        lock.mkdir(parents=True)
        p = self.install("--user-level", "--claude-only")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("if no install.sh is running, remove %s" % lock, p.stderr)
        self.assertTrue(lock.is_dir())

    def test_sweep_stays_inside_recorded_tools(self):
        # Codex-only user-level install; the user later copies our agent files and one of our hook entries into
        # Claude Code by hand. Uninstalling with claude on PATH must not touch them.
        self.fake_tool("claude", 0)
        (self.bin / "claude").unlink()
        self.ok(self.install("--user-level"))
        self.assertEqual(json.loads(self.record.read_text())["tools"], ["codex"])
        agents = self.claude_dir / "agents"
        agents.mkdir(parents=True)
        for f in sorted((REPO / "agents").glob("*.md")):
            shutil.copy(str(f), str(agents / f.name))
        group = fragment_group("settings-parcasi.json", "PreToolUse", "agent-tip-kapisi.py")
        settings = self.claude_dir / "settings.json"
        settings.write_text(json.dumps({"hooks": {"PreToolUse": [group]}}))
        self.fake_tool("claude")
        p = self.ok(self.install("--uninstall"))
        self.assertEqual(sorted(x.name for x in agents.iterdir()), AGENTS, p.stderr)
        self.assertEqual(json.loads(settings.read_text()), {"hooks": {"PreToolUse": [group]}})
        self.assertNotIn("not in the install record", p.stderr)
        self.assertFalse(self.record.exists())

    def test_lock_folders_removed_after_refusal(self):
        self.skill.mkdir(parents=True)  # a skill copy without a record: refused with exit 3
        p = self.install("--user-level", "--claude-only")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertFalse((self.home / ".local").exists(), "the folders made for the lock are removed again")

    def test_backup_folder_name(self):
        agents = self.claude_dir / "agents"
        agents.mkdir(parents=True)
        (agents / "worker.md").write_text("mine\n")
        p = self.ok(self.install("--user-level", "--claude-only"))
        names = [d.name for d in (self.state() / "backups").iterdir()]
        self.assertEqual(len(names), 1)
        self.assertRegex(names[0], r"^\d{8}-\d{6}-\d{6}-\d+$")
        self.assertIn("Backups: %s" % (self.state() / "backups" / names[0]), p.stdout)

    # The state folder goes with the record when nothing else is in it, and stays while it holds backups.
    def test_plugin_cycle_removes_state_folder(self):
        self.ok(self.install())
        self.assertTrue(self.record.exists())
        p = self.ok(self.install("--uninstall"))
        self.assertFalse(self.state().exists(), p.stdout + p.stderr)

    def test_user_level_cycle_removes_state_folder(self):
        self.ok(self.install("--user-level"))
        p = self.ok(self.install("--uninstall"))
        self.assertNotIn("backed up", p.stdout)
        self.assertFalse(self.state().exists(), p.stdout + p.stderr)

    def test_state_folder_with_backups_stays(self):
        self.claude_dir.mkdir()
        (self.claude_dir / "settings.json").write_text('{"theme": "dark"}')
        self.ok(self.install("--user-level", "--claude-only"))
        self.ok(self.install("--uninstall", "--claude-only"))
        self.assertFalse(self.record.exists())
        self.assertTrue(any((self.state() / "backups").rglob("settings.json")))

    def test_record_item_missing_field(self):
        self.ok(self.install("--user-level", "--claude-only"))
        rec = json.loads(self.record.read_text())
        n = next(k for k, i in enumerate(rec["items"]) if i["kind"] == "file")
        del rec["items"][n]["sha256"]
        self.record.write_text(json.dumps(rec))
        before = snapshot(self.home)
        p = self.install("--uninstall")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("error: cannot parse %s: item %d (file) lacks a valid 'sha256' field" % (self.record, n),
                      p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        self.assertEqual(snapshot(self.home), before)


class TestOnlyClaudeRecord(Base):
    tools = ("claude",)

    @need_claude
    def test_plugin_record_goes(self):
        self.ok(self.install())
        self.assertTrue(self.record.exists())
        self.ok(self.install("--uninstall"))
        self.assertFalse(self.claude_installed())
        self.assertFalse(self.record.exists())


if __name__ == "__main__":
    unittest.main()
