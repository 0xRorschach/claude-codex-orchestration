"""Abstracts the difference between Claude Code and Codex hook input in one place.

Shared [docs: code.claude.com/docs/en/hooks, learn.chatgpt.com/docs/hooks]: both pass the event JSON on stdin
(session_id, transcript_path, cwd, hook_event_name; on PostToolUse also tool_name, tool_input, tool_response), and
both add {"hookSpecificOutput": {"hookEventName": ..., "additionalContext": ...}} output to the model context.
A shell command arrives in Codex too as tool_name "Bash" with tool_input.command.

Different:
- Which tool: the registration command passes a `codex` argument; without an argument, input carrying turn_id is
  treated as Codex (Codex PostToolUse input contains turn_id [docs]; Claude Code input does not).
- Subagent detection: in Claude Code a hook running inside a subagent carries agent_id [docs]. The Codex docs do not
  list agent_id in the PostToolUse table and say "Subagent hooks use the parent session id"; so for Codex the first
  line (session_meta) of transcript_path is read as an extra path: a subagent transcript has payload.source
  {"subagent": ...} or a non-empty payload.parent_thread_id [measured, codex-cli 0.166.0 rollout files].
  Which transcript Codex passes in transcript_path for a subagent PostToolUse is not documented: not verified.
  If the transcript cannot be read, is empty, or its first line is not session_meta, the distinction is undetermined
  and the call is treated as a subagent (silent): in the read budget a false warning nudges the main session for
  nothing, while a missed warning only delays one reminder.
- Config directory: CLAUDE_CONFIG_DIR or ~/.claude for Claude Code, CODEX_HOME or ~/.codex for Codex.
"""
import json
import os
import sys
from pathlib import Path

CLAUDE, CODEX = "claude", "codex"
ILK_SATIR_SINIRI = 4 * 1024 * 1024  # the session_meta line also carries base instructions; it can be hundreds of KB


def girdi_oku():
    """stdin JSON; None if it cannot be read."""
    try:
        veri = json.load(sys.stdin)
    except Exception:
        return None
    return veri if isinstance(veri, dict) else None


def arac(veri, argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if CODEX in argv:
        return CODEX
    if CLAUDE in argv:
        return CLAUDE
    return CODEX if isinstance(veri, dict) and "turn_id" in veri else CLAUDE


def yapilandirma_dizini(hangi):
    if hangi == CODEX:
        return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))


def _codex_alt_ajan_dokumu(yol):
    """True subagent, False main session, None undetermined (transcript unreadable or header not session_meta)."""
    try:
        with open(yol, encoding="utf-8") as f:
            satir = f.readline(ILK_SATIR_SINIRI)
        kayit = json.loads(satir)
    except Exception:
        return None
    if not isinstance(kayit, dict) or kayit.get("type") != "session_meta" or not isinstance(kayit.get("payload"), dict):
        return None
    yuk = kayit["payload"]
    kaynak = yuk.get("source")
    return bool((isinstance(kaynak, dict) and "subagent" in kaynak) or yuk.get("parent_thread_id"))


def alt_ajan_mi(veri, hangi):
    if veri.get("agent_id"):
        return True
    dokum = str(veri.get("transcript_path") or "")
    if hangi == CLAUDE:
        # Fallback: subagent transcripts live under <session>/subagents/ [measured]. The docs say that for
        # SubagentStop transcript_path is the main session transcript; so this is only an extra safeguard.
        return "/subagents/" in dokum
    # Undetermined (None, including an empty transcript_path) counts as subagent: a false warning costs more (above).
    return _codex_alt_ajan_dokumu(dokum) is not False if dokum else True


def baglam_ciktisi(olay, metin):
    return json.dumps({"hookSpecificOutput": {"hookEventName": olay, "additionalContext": metin}},
                      ensure_ascii=False)
