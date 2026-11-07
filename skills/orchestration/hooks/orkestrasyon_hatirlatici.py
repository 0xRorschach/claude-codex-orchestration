#!/usr/bin/env python3
"""PreToolUse hook (Claude Code: Agent|Task, Codex: spawn_agent): when the main session opens its first subagent and
the orchestration skill was not loaded in this session, it reminds once. It does not block; it only adds context.

Why: in a measurement (n=152 sessions, 2026-11-07) the skill loaded on its own in 44.7% of sessions, on a user
trigger in 11.2%, and never in 44.1%; every self-loaded session loaded it before the first subagent. The way of
working is defined in the skill; opening a subagent is the latest point to remind if it was not loaded.

Traces counted as loaded (in the raw text of a transcript line; nested escaped text, e.g. a quote in a brief, does
not match):
- Claude Code: a Skill tool call `"skill":"orchestration"` (also with a plugin prefix, e.g.
  `orchestration:orchestration`); the `"text":"Base directory for this skill: .../orchestration` line where the skill
  body is injected; `<command-name>/orchestration` (also with a plugin prefix). The bare word "orchestration" does
  not count: CLAUDE.md and briefs carry it many times.
- Codex [measured, codex-cli 0.166.0 rollout files]: Codex has no Skill tool; the model reads SKILL.md with a shell
  command. If a tool-call record (`"type":"custom_tool_call"` or `"type":"function_call"`) contains
  `/orchestration/SKILL.md`, it counts as loaded; the built-in skill injection is `"text":"<skill>\\n<name>orchestration`.
  The skill list at session start (world_state) does not count because it is not a tool call.

Speed: the transcript is read line by line as bytes from the start; a line without `orchestration` never reaches the
regex, and reading stops at the first match; no JSON is parsed. The result is resolved once per session: the state
file is created with O_EXCL BEFORE the scan, so of several parallel subagent calls in the same message only one scans
and at most one warning appears. If the transcript cannot be read, no warning is given and the state file is removed
(the next call retries): a false warning costs more than a missed one (same policy as kanca_girdisi.py).

State: <ORCH_LOG_DIR>/hatirlatici/<session_id> when ORCH_LOG_DIR is set, else <plugin data>/hatirlatici/<session_id>
when CLAUDE_PLUGIN_DATA or PLUGIN_DATA is set (plugin mode), otherwise
${XDG_CACHE_HOME:-$HOME/.cache}/orchestration/hatirlatici/<session_id>; files older than 7 days are removed silently.
Disable: ORCH_HATIRLATICI=0. Every error path exits silently (exit 0), including import errors and a closed stdout.
"""
import sys

try:
    import os
    import re
    import time
    from pathlib import Path

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import kanca_girdisi as kg

    ON_SUZGEC = b"orchestration"
    YUKLENDI = re.compile(
        rb'"skill"\s*:\s*"(?:[A-Za-z0-9_.-]+:)?orchestration"'
        rb'|"text"\s*:\s*"Base directory for this skill: [^"\\]*/orchestration(?=\\n|"|/)'
        rb'|<command-name>/?(?:[A-Za-z0-9_.-]+:)?orchestration</command-name>'
        rb'|"text"\s*:\s*"<skill>\\n<name>orchestration</name>'
    )
    CODEX_ARAC_CAGRISI = re.compile(rb'"type"\s*:\s*"(?:custom_tool_call|function_call)"')
    CODEX_SKILL_OKUMA = re.compile(rb'/orchestration/SKILL\.md')
except BaseException:  # if the helper or a standard module cannot be loaded, the hook does nothing
    kg = None

OLAY = "PreToolUse"
ARACLAR = {"Agent", "Task", "spawn_agent"}  # Codex: spawn_agent also matches the `Agent` alias [docs]
SAKLAMA_SN = 7 * 86400  # 7 days: state of closed sessions does not pile up, a running session is unaffected
METIN = ("The orchestration skill was not loaded in this session. Load it before opening subagents "
         "(Skill: orchestration); the way of working is defined there.")


def satir_yukleme_mi(satir):
    if ON_SUZGEC not in satir:
        return False
    if YUKLENDI.search(satir):
        return True
    return bool(CODEX_SKILL_OKUMA.search(satir) and CODEX_ARAC_CAGRISI.search(satir))


def yuklendi_mi(yol):
    """True loaded, False not loaded, None transcript could not be read."""
    try:
        with open(yol, "rb") as f:
            for satir in f:
                if satir_yukleme_mi(satir):
                    return True
    except Exception:
        return None
    return False


def durum_dizini():
    """ORCH_LOG_DIR, else the plugin data folder (CLAUDE_PLUGIN_DATA, then PLUGIN_DATA), else the XDG cache."""
    for ad in ("ORCH_LOG_DIR", "CLAUDE_PLUGIN_DATA", "PLUGIN_DATA"):
        deger = (os.environ.get(ad) or "").strip()
        if deger:
            return Path(deger).expanduser() / "hatirlatici"
    taban = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(taban) / "orchestration" / "hatirlatici"


def eskileri_temizle(dizin):
    sinir = time.time() - SAKLAMA_SN
    for f in dizin.iterdir():
        try:
            if f.is_file() and f.stat().st_mtime < sinir:
                f.unlink()
        except OSError:
            pass


def main():
    if kg is None or os.environ.get("ORCH_HATIRLATICI", "1").strip() == "0":
        return
    veri = kg.girdi_oku()
    if veri is None or veri.get("tool_name") not in ARACLAR or kg.alt_ajan_mi(veri, kg.arac(veri)):
        return
    dokum = str(veri.get("transcript_path") or "")
    if not dokum:
        return
    sid = re.sub(r"[^A-Za-z0-9_-]", "", str(veri.get("session_id") or ""))
    if not sid:
        return

    dizin = durum_dizini()
    dizin.mkdir(parents=True, exist_ok=True)
    eskileri_temizle(dizin)
    yol = dizin / sid
    try:
        fd = os.open(yol, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return  # this session is resolved (or a parallel call is resolving it)
    os.close(fd)
    sonuc = yuklendi_mi(dokum)
    if sonuc is None:
        try:
            yol.unlink()
        except OSError:
            pass
        return
    try:
        yol.write_text("yuklu" if sonuc else "uyarildi", encoding="utf-8")
    except OSError:
        pass
    if not sonuc:
        print(kg.baglam_ciktisi(OLAY, METIN))


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        pass
    # On a closed stdout, flushing the buffer at interpreter shutdown gives exit 120 with BrokenPipeError/EBADF: it
    # is caught here, then the shutdown flush is skipped with os._exit (same pattern as okuma_butcesi.py).
    for akis in (sys.stdout, sys.stderr):
        try:
            akis.flush()
        except BaseException:
            pass
    try:
        import os as _os
        _os._exit(0)
    except BaseException:
        sys.exit(0)
