#!/usr/bin/env python3
"""PostToolUse(Agent|Task) hook: when the main session starts a subagent, reminds it to start independent work in
parallel.

Why: the rule "if tasks are independent, run them in parallel subagents" was written in the instruction files but was
not visible at decision time (right after starting an agent, when switching to waiting). This hook puts the reminder
exactly at that moment. It does not block; it only adds context.
It stays silent in helpers opened from inside a subagent (input carries agent_id). Each trigger writes one log line
(for measurement): time, session_id, tool_name, subagent_type, the first 60 characters of description (so sequential
and parallel starts can be told apart later). A trigger that arrives within AYNI_TUR_SN of the session's last WARNING
does not warn again, but is still logged. This groups agent calls that complete at about the same time (for example
agents started in the background in one message); foreground agents of the same message that finish at different
times can each warn. The window is measured
from the last warning; a suppressed trigger does not extend it, so frequent starts do not stay silent one after
another. A sequential chain is not suppressed. On an error or in doubt the hook warns; the exit code is always 0.

State: the last warning time per session in <state dir>/paralel-is/<session_id>.json, where the state dir is
ORCH_LOG_DIR, else CLAUDE_PLUGIN_DATA or PLUGIN_DATA (plugin mode), else ${XDG_CACHE_HOME:-$HOME/.cache}/orchestration
(same order as the load reminder). A separate file instead of the log: PostToolUse calls of the same message can run
concurrently; a small per-session file read and written under fcntl.flock settles "the first one warns" without
scanning the growing log on every call. State files older than 7 days are removed.

Environment variables: ORCH_PARALEL_HATIRLATICI=0 turns the reminder off (no output, no log line).
ORCH_PARALEL_ESIK sets the concurrent-agent threshold quoted in the reminder (default 15; an invalid or non-positive
value falls back to 15). The log goes to ORCH_LOG_DIR, otherwise CLAUDE_PLUGIN_DATA or PLUGIN_DATA (plugin mode),
otherwise ~/.claude/hooks/.
"""
import fcntl
import json
import os
import re
import sys
import time
from pathlib import Path

VARSAYILAN_ESIK = 15  # default concurrent-agent threshold; configurable via ORCH_PARALEL_ESIK
# 5 s: triggers of agent calls that complete together (e.g. started in the background in one message) land in the log
# within the same second (measured: 3 lines in one second); the rest is margin for hook start-up delay. Foreground
# agents that finish further apart, and the next sequential start (at least one model turn later), usually fall
# outside it and warn again.
AYNI_TUR_SN = 5
SAKLAMA_SN = 7 * 86400  # 7 days: state of closed sessions does not pile up, a running session is unaffected
ACIKLAMA_UZUNLUGU = 60  # enough to recognise the task in the log, short enough to keep one line per trigger
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


def durum_dizini():
    """ORCH_LOG_DIR, else the plugin data folder (CLAUDE_PLUGIN_DATA, then PLUGIN_DATA), else the XDG cache."""
    for ad in ("ORCH_LOG_DIR", "CLAUDE_PLUGIN_DATA", "PLUGIN_DATA"):
        deger = (os.environ.get(ad) or "").strip()
        if deger:
            return Path(deger).expanduser() / "paralel-is"
    taban = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(taban) / "orchestration" / "paralel-is"


def alan(deger, uzunluk=None):
    """Log field: tabs and line breaks become a space (so the line format does not break)."""
    metin = re.sub(r"[\t\r\n]+", " ", str(deger or "")).strip()
    return metin[:uzunluk] if uzunluk else metin


def ayni_tur_mu(sid, saat=time.time):
    """True if within AYNI_TUR_SN of the last warning (time not updated); otherwise writes the last warning time and
    returns False. The time is read after the lock is taken, so concurrent calls that get the lock in reverse order do
    not break the order. A negative difference (the clock seems to have gone back) also counts as the same turn, so
    the stored time never moves backwards."""
    dizin = durum_dizini()
    dizin.mkdir(parents=True, exist_ok=True)
    sinir = time.time() - SAKLAMA_SN
    for f in dizin.glob("*.json"):
        try:
            if f.stat().st_mtime < sinir:
                f.unlink()
        except OSError:
            pass
    ad = re.sub(r"[^A-Za-z0-9_-]", "", sid) or "bilinmeyen"
    fd = os.open(str(dizin / (ad + ".json")), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        simdi = saat()
        try:
            son = float(json.loads(os.read(fd, 4096).decode("utf-8"))["son_uyari"])
        except Exception:
            son = None
        if son is not None and simdi - son < AYNI_TUR_SN:
            return True
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, json.dumps({"son_uyari": simdi}).encode("utf-8"))
        return False
    finally:
        os.close(fd)


def main() -> int:
    if os.environ.get("ORCH_PARALEL_HATIRLATICI", "1").strip() == "0":
        return 0
    try:
        veri = json.load(sys.stdin)
    except Exception:
        return 0
    if veri.get("agent_id"):          # helper opened from inside a subagent: not the main session
        return 0
    girdi = veri.get("tool_input") if isinstance(veri.get("tool_input"), dict) else {}
    sid = str(veri.get("session_id", "") or "")
    try:
        log = log_yolu()
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8", errors="replace") as f:  # an unpaired surrogate must not drop the line
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')}\t{alan(sid)}\t{alan(veri.get('tool_name'))}\t"
                    f"{alan(girdi.get('subagent_type'))}\t{alan(girdi.get('description'), ACIKLAMA_UZUNLUGU)}\n")
    except Exception:                 # the log is for measurement; failing to write it does not block the reminder
        pass
    try:
        if ayni_tur_mu(sid):
            return 0
    except Exception:                 # state file not writable: old behaviour, warn
        pass
    uyar()
    return 0


UYARILDI = False


def uyar():
    global UYARILDI
    if not UYARILDI:
        UYARILDI = True
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                                 "additionalContext": METIN.format(esik=esik())}},
                         ensure_ascii=False), flush=True)


if __name__ == "__main__":
    try:
        main()
    except BaseException:             # unexpected error: warn in doubt, exit code 0 in every case
        try:
            uyar()
        except BaseException:
            pass
    os._exit(0)
