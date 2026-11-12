#!/usr/bin/env python3
"""Subagent type gate: PreToolUse (Agent/Task).

Model tree: a subagent's model and effort come from its agent file (`model:` / `effort:`): explorer/worker/researcher
Opus · medium, scanner Sonnet · medium, fable-reviewer Fable · high. Another model is chosen by agent type, not by the
call's `model` parameter. The built-in general-purpose types carry no effort and inherit the main session's high effort [measured 2026-09-25: Explore ->
high, explorer -> medium]. Superpowers templates write `general-purpose`, so the rule cannot be kept by text alone;
this gate enforces it.

Rules: (1) a `model` parameter is given and it is neither `opus` nor a full Opus id (`claude-opus-...`) -> deny; (2) a forbidden type (the set below, or an
empty type = general-purpose) -> deny. A plugin-qualified type `<plugin>:<agent>` is checked by its last part.
The hook also runs inside subagents [docs: code.claude.com/docs sub-agents], so an agent opened by a subagent is
subject to the same type rule. Nesting agents itself is allowed; the first version's agent_id denial was removed for
that reason.

Rule book: the orchestration SKILL.md > "With superpowers". Its path is quoted in the denial message:
${CLAUDE_PLUGIN_ROOT}/skills/orchestration/SKILL.md when running as a Claude Code plugin, otherwise derived from this
script's own location (<skill>/hooks/agent-tip-kapisi.py -> <skill>/SKILL.md).

Environment variables: ORCH_TIP_KAPISI=0 turns the gate off (every call passes, nothing is logged). ORCH_LOG_DIR
moves the denial log; otherwise CLAUDE_PLUGIN_DATA or PLUGIN_DATA (plugin mode), otherwise
~/.local/share/agent-tip-kapisi/.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Why this set: general-purpose types that inherit the main session's effort, plus fork, which ignores the model
# setting. claude-code-guide, statusline-setup and plugin agents are narrow-purpose and rare; deliberately allowed.
YASAK = {"general-purpose", "explore", "plan", "claude", "fork", ""}

# scanner (Sonnet, medium effort) and fable-reviewer (Fable, high effort): their model comes from the agent file, so
# they pass this gate; choosing another model through the `model` parameter stays closed.
ONERI = ("Use instead: search/map/raw-output summary -> `scanner`, review/judgement-heavy exploration -> `explorer`, "
         "implementation+tests -> `worker`, branch-end final review or the final read of a plan/spec that goes to "
         "the user -> `fable-reviewer`, "
         "docs/API verification -> `researcher`. "
         "If the user explicitly asked for another type for this job, tell them about this gate.")
# Last sentence of every denial: how to turn the gate off (same switch form as the other hooks).
KAPATMA = "To turn this gate off, set ORCH_TIP_KAPISI=0 in the environment Claude Code runs in."


def opus_mu(model):
    """`opus` (the alias) or a full Opus id such as `claude-opus-4-1`; `claude-opus` without a version is not one."""
    return model == "opus" or model.startswith("claude-opus-")


def kural_kitabi():
    """Path of the rule book quoted in denial messages: plugin root if set, else relative to this script."""
    kok = (os.environ.get("CLAUDE_PLUGIN_ROOT") or "").strip()
    if kok:
        return str(Path(kok) / "skills" / "orchestration" / "SKILL.md")
    return str(Path(__file__).resolve().parent.parent / "SKILL.md")


def log_dizini():
    """ORCH_LOG_DIR, else the plugin data folder (CLAUDE_PLUGIN_DATA, then PLUGIN_DATA), else the default."""
    for ad in ("ORCH_LOG_DIR", "CLAUDE_PLUGIN_DATA", "PLUGIN_DATA"):
        deger = (os.environ.get(ad) or "").strip()
        if deger:
            return os.path.expanduser(deger)
    return os.path.expanduser("~/.local/share/agent-tip-kapisi")


# Denial log. The prompt is not written: privacy + size.
LOG = os.path.join(log_dizini(), "ret.jsonl")


def logla(veri, neden):
    # If the log cannot be written, pass silently: the denial decision does not depend on the log.
    try:
        girdi = veri.get("tool_input") or {}
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "subagent_type": girdi.get("subagent_type"),
                "model": girdi.get("model"),
                "neden": neden,
                "cwd": veri.get("cwd") or os.getcwd(),
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass


def karar(neden):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": neden,
    }}, ensure_ascii=False))
    sys.exit(0)


def main():
    if os.environ.get("ORCH_TIP_KAPISI", "1").strip() == "0":
        sys.exit(0)
    try:
        veri = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # unreadable input: make no decision, let the normal flow continue
    if veri.get("tool_name") not in ("Agent", "Task"):
        sys.exit(0)

    # The `model` parameter of an Agent call overrides the agent file's model [docs: Agent tool schema].
    # Superpowers "Model Selection" produces exactly that (worker + haiku). Non-opus models are closed.
    model = ((veri.get("tool_input") or {}).get("model") or "").strip().lower()
    if model and not opus_mu(model):
        logla(veri, f"model {model} is not opus")
        karar(f"`model: {model}` is closed: a subagent's model comes from its agent file; the `model` parameter "
              "in the call overrides it. Remove the parameter. Another model is chosen by agent type, not by "
              "parameter: search/map/summary -> `scanner` (Sonnet · medium), branch-end final review or the final "
              "read of a plan/spec that goes to the user -> `fable-reviewer` (Fable · high). Non-Opus models for "
              f"other work only if the user says so; if they did, tell them about this gate. Rule book: {kural_kitabi()}. "
              f"{KAPATMA}")

    tip = ((veri.get("tool_input") or {}).get("subagent_type") or "").strip()
    # Plugin agents are named `<plugin>:<agent>` (e.g. `orchestration:explorer`): the check uses the last part, so
    # `orchestration:explorer` passes and `x:general-purpose` is denied like `general-purpose`.
    if tip.split(":")[-1].strip().lower() in YASAK:
        gorunen = tip or "(empty -> general-purpose)"
        logla(veri, f"forbidden type {gorunen}")
        karar(f"The `{gorunen}` type is closed: it inherits the main session's effort or ignores the model "
              f"setting (a subagent's model and effort must come from its agent file). {ONERI} Rule book: {kural_kitabi()}. "
              f"{KAPATMA}")
    sys.exit(0)


if __name__ == "__main__":
    main()
