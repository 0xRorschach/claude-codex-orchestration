"""Tests for install.sh.

Every test runs install.sh in its own temporary HOME (HOME, CLAUDE_CONFIG_DIR, CODEX_HOME, XDG_STATE_HOME and
XDG_CACHE_HOME all point inside it) under a macOS sandbox profile that denies outbound network. PATH is a
temporary bin folder holding only the tools a test wants, so "only Claude" or "only Codex" is real.

The real claude / codex binaries are used when they are on PATH; tests that need one are skipped otherwise.
Run from the repo root: python3 -m unittest discover -s tests -v
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
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
            out[os.path.relpath(p, root)] = (st.st_mode, st.st_size if not os.path.isdir(p) else 0, st.st_mtime_ns)
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


ROLES = ["explorer.toml", "researcher.toml", "tarayici.toml", "worker.toml"]
AGENTS = ["explorer.md", "researcher.md", "tarayici.md", "worker.md"]


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
        self.assertIn("Agents (4)", d)
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
        self.assertIn("differs", p.stderr)

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


if __name__ == "__main__":
    unittest.main()
