#!/usr/bin/env python3
"""Fake `codex` binary for tests. Calls no real model.

Behaviour is chosen with SAHTE_CODEX_MOD; the argv, stdin and selected environment variables it receives are written
as JSON to SAHTE_ARGV_DOSYASI. Unknown flags are swallowed.
Modes: normal · auth-yenile · auth-yenile-gercek-degisti · refresh-hata · refresh-hata-json · refresh-turn-failed ·
refresh-item-error · refresh-mesajda · refresh-komut-ciktisinda · gorsel-kaydet · gorsel-ev · gorsel-yok · bekle
Event types were taken from a real stream and from the codex binary's event names: thread.started, turn.started,
turn.completed, turn.failed, item.started/updated/completed, error.
"""
import json
import os
import sys
import time
from pathlib import Path

PNG = b"\x89PNG\r\n\x1a\n" + b"fake"


def deger(argv, ad):
    for i, a in enumerate(argv):
        if a == ad and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith(ad + "="):
            return a.split("=", 1)[1]
    return None


def yerinde_yaz(yol: Path, icerik: bytes) -> None:
    # Write-then-rename, like the real codex.
    gecici = yol.with_name(yol.name + ".yeni")
    gecici.write_bytes(icerik)
    os.replace(gecici, yol)


def main() -> int:
    argv = sys.argv[1:]
    if argv[:1] == ["--version"]:
        print("codex-cli 0.0.0-sahte")
        return 0
    stdin = sys.stdin.read() if "-" in argv else ""
    mod = os.environ.get("SAHTE_CODEX_MOD", "normal")
    ev = Path(os.environ["CODEX_HOME"])
    kayit = {
        "argv": argv, "stdin": stdin, "cwd": os.getcwd(),
        "env": {k: os.environ.get(k) for k in ("CODEX_HOME", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")},
        "ev_dosyalari": sorted(p.name for p in ev.iterdir()),
        "auth_izin": oct((ev / "auth.json").stat().st_mode & 0o777) if (ev / "auth.json").exists() else None,
    }
    if os.environ.get("SAHTE_ARGV_DOSYASI"):
        Path(os.environ["SAHTE_ARGV_DOSYASI"]).write_text(json.dumps(kayit, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({"type": "thread.started", "thread_id": "sahte"}))
    if mod == "bekle":
        time.sleep(30)
    if mod == "refresh-hata":
        sys.stderr.write("ERROR: Your access token could not be refreshed because your refresh token was "
                         "already used. Please log out and sign in again.\n")
        return 1
    if mod == "refresh-hata-json":
        print(json.dumps({"type": "error", "message": "Refresh Token Was Already Used; please run codex login"}))
        return 0
    if mod == "refresh-turn-failed":
        print(json.dumps({"type": "turn.failed", "error": {"message": "unexpected status 401: refresh token was "
                                                                      "already used"}}))
        return 1
    if mod == "refresh-item-error":
        print(json.dumps({"type": "item.completed", "item": {"type": "error", "message":
                          "Refresh Token Was Already Used; please run codex login"}}))
        return 0
    if mod == "refresh-komut-ciktisinda":
        print(json.dumps({"type": "item.completed", "item": {
            "type": "command_execution", "command": "rg refresh src", "exit_code": 0,
            "aggregated_output": "codex_cagri.py:40: refresh token was already used"}}))
    if mod == "refresh-mesajda":
        os.environ["SAHTE_SON_MESAJ"] = '{"bulgu": "code 77 is returned on the refresh token was already used error"}'
    if mod in ("auth-yenile", "auth-yenile-gercek-degisti"):
        yerinde_yaz(ev / "auth.json", b'{"tokens": "yenilendi"}')
    if mod == "auth-yenile-gercek-degisti":
        yerinde_yaz(Path(os.environ["SAHTE_GERCEK_AUTH"]), b'{"tokens": "baska-surec"}')
    cd = deger(argv, "-C")
    if mod == "gorsel-kaydet" and cd:
        (Path(cd) / "gorsel.png").write_bytes(PNG + b"-calisma")
    if mod == "gorsel-ev":
        eski = ev / "generated_images" / "oturum-eski" / "exec-eski.png"
        yeni = ev / "generated_images" / "oturum-yeni" / "exec-yeni.png"
        for yol, icerik, zaman in ((eski, PNG + b"-eski", 1_000_000), (yeni, PNG + b"-yeni", 2_000_000)):
            yol.parent.mkdir(parents=True, exist_ok=True)
            yol.write_bytes(icerik)
            os.utime(yol, (zaman, zaman))
    son = os.environ.get("SAHTE_SON_MESAJ", '{"tamam": true}')
    print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": son}}))
    print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}))
    cikti = deger(argv, "-o")
    if cikti:
        Path(cikti).write_text(son, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
