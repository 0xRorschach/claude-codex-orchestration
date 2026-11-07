#!/usr/bin/env python3
"""PostToolUse(Agent|Task) hook: when the main session starts a subagent, reminds it to start independent work in
parallel.

Why: the rule "if tasks are independent, run them in parallel subagents" was written in the instruction files but was
not visible at decision time (right after starting an agent, when switching to waiting). This hook puts the reminder
exactly at that moment. It does not block; it only adds context.
It stays silent in helpers opened from inside a subagent (input carries agent_id). Each trigger writes one log line
(for measurement).

Environment variables: ORCH_PARALEL_ESIK sets the concurrent-agent threshold quoted in the reminder (default 15;
an invalid or non-positive value falls back to 15). The log goes to ORCH_LOG_DIR, otherwise CLAUDE_PLUGIN_DATA or
PLUGIN_DATA (plugin mode), otherwise ~/.claude/hooks/.
"""
import json
import os
import sys
import time
from pathlib import Path

VARSAYILAN_ESIK = 15  # default concurrent-agent threshold; configurable via ORCH_PARALEL_ESIK
METIN = (
    "[parallel-work hook] You started a subagent. Before switching to waiting, ask: is there other work that does NOT "
    "wait for this agent's result (the dependency table in the plan, the next task in a separate worktree, research, "
    "review, documentation)? If so, start it in the same turn with separate subagents (threshold: {esik} concurrent, "
    "default 15, configurable). If not, tell the user why in one sentence."
)


def esik():
    try:
        e = int(os.environ.get("ORCH_PARALEL_ESIK", VARSAYILAN_ESIK))
        return e if e > 0 else VARSAYILAN_ESIK
    except ValueError:
        return VARSAYILAN_ESIK


def log_yolu():
    for ad in ("ORCH_LOG_DIR", "CLAUDE_PLUGIN_DATA", "PLUGIN_DATA"):
        dizin = (os.environ.get(ad) or "").strip()
        if dizin:
            return Path(dizin).expanduser() / "paralel-is-hatirlatici.log"
    return Path.home() / ".claude" / "hooks" / "paralel-is-hatirlatici.log"


def main() -> int:
    try:
        veri = json.load(sys.stdin)
    except Exception:
        return 0
    if veri.get("agent_id"):          # helper opened from inside a subagent: not the main session
        return 0
    try:
        log = log_yolu()
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')}\t{veri.get('session_id', '')}\t{veri.get('tool_name', '')}\n")
    except OSError:
        pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": METIN.format(esik=esik())}},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
