"""Shared test helpers: runs a hook in a subprocess with the real contract (stdin JSON, stdout, exit code)."""
import json
import os
import subprocess
import sys
from pathlib import Path

KANCA_DIZINI = Path(__file__).resolve().parent.parent
# Variables from the caller's environment that would redirect hook paths; tests set them explicitly when needed.
ATILAN = ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DATA", "PLUGIN_DATA")


def kos(betik, girdi, env_ek=None, ham_girdi=None, argumanlar=()):
    env = {k: v for k, v in os.environ.items() if not k.startswith("ORCH_") and k not in ATILAN}
    env.update(env_ek or {})
    veri = ham_girdi if ham_girdi is not None else json.dumps(girdi)
    p = subprocess.run([sys.executable, str(KANCA_DIZINI / betik)] + list(argumanlar), input=veri,
                       capture_output=True, text=True, env=env, timeout=30)
    return p


def baglam(p):
    """The additionalContext text from the hook output; None if there is no output."""
    if not p.stdout.strip():
        return None
    return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
