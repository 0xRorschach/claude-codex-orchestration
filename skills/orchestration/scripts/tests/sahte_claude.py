#!/usr/bin/env python3
"""Fake `claude` binary for tests. Calls no real model.

Writes argv, stdin and selected environment variables to SAHTE_ARGV_DOSYASI. SAHTE_CLAUDE_MOD: normal · hata.
Prints a few stream-json lines and a final `type=result` line.
"""
import json
import os
import sys
from pathlib import Path


def main() -> int:
    argv = sys.argv[1:]
    if argv[:1] in (["--version"], ["-v"]):
        print("0.0.0 (Claude Code)")
        return 0
    stdin = sys.stdin.read()
    if os.environ.get("SAHTE_ARGV_DOSYASI"):
        Path(os.environ["SAHTE_ARGV_DOSYASI"]).write_text(json.dumps({
            "argv": argv, "stdin": stdin, "cwd": os.getcwd(),
            "env": {k: os.environ.get(k) for k in (
                "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_OAUTH_TOKEN",
                "ANTHROPIC_API_KEY", "PATH", "HOME", "LC_ALL", "ORCH_TEST_GIZLI", "CODEX_HOME", "AWS_REGION",
                "AWS_PROFILE", "GOOGLE_APPLICATION_CREDENTIALS", "CLOUD_ML_REGION", "CLAUDE_CODE_USE_BEDROCK",
                "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_SSE_PORT", "SAHTE_EK")},
            "env_adlari": sorted(os.environ),
        }, ensure_ascii=False), encoding="utf-8")
    mod = os.environ.get("SAHTE_CLAUDE_MOD", "normal")
    print(json.dumps({"type": "system", "subtype": "init", "model": "claude-sahte-opus-1",
                      "tools": ["Read", "Grep", "Glob"]}))
    if mod == "hata":
        print(json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True,
                          "result": "something went wrong"}))
        return 1
    nesne = json.loads(os.environ.get("SAHTE_SON_MESAJ", '{"tamam": true}'))
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                      "result": json.dumps(nesne, ensure_ascii=False), "structured_output": nesne,
                      "modelUsage": {"claude-sahte-haiku-1": {}, "claude-sahte-opus-1": {}}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
