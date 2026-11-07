#!/usr/bin/env python3
"""Core that calls Claude (a different model family, seen from a Codex session) read-only. Standard library only.

Same contract as `codex_cagri.cagir`: (exit code, last message, event stream path). The flags were taken from
`claude --help` (Claude Code 2.1.319, 2026-11-07; help text only, no real call was made with this flag set):
- `--restricted`: ignores user, project and local settings files (so hooks and enabled plugins from there are not
  loaded), confines file tools to the working folder (cwd and --add-dir), refuses bypassPermissions. Chosen because
  one flag gives the three wanted properties (no settings, no hooks, confined to cwd) without breaking OAuth login.
  Rejected: according to its help text `--bare` never reads OAuth or the keychain and accepts only
  ANTHROPIC_API_KEY; for a user logged in with a subscription the call fails. The earlier `--setting-sources
  project` loaded project hooks and was removed. `--safe-mode` (which also disables CLAUDE.md and plugins) was not
  added: its behaviour together with `--restricted` and `-p` was not measured.
- `--tools Read,Grep,Glob`: narrows the available tool set; Edit/Write/Bash are never offered to the model. This is
  stricter than the allow list (`--allowedTools`): an allow list does not remove tools, it only runs them without
  asking.
- `--permission-mode dontAsk`: anything that would ask for permission is denied without asking (nobody will answer,
  -p).
- `--json-schema` takes inline JSON (a file path was rejected; measured in an earlier internal project),
  `--output-format stream-json --verbose`: the event stream is written to a file; `structured_output` on the last
  `type=result` line is the last message.
- `--no-session-persistence --strict-mcp-config`: the session is not written to disk, no MCP server is loaded (the
  help text recommends `--strict-mcp-config` together with `--restricted`).
- The working folder is given explicitly via `calisma_dizini` (process cwd); file tools are confined to it.

Environment: allow list (`claude_ortami`). Parent session markers (CLAUDECODE, CLAUDE_CODE_ENTRYPOINT,
CLAUDE_CODE_SSE_PORT and the like) and unrelated secrets do not pass; variables needed for credentials do. The Codex
direction's deny-list filter (`codex_cagri.cocuk_ortami`) is separate and unchanged.

Environment variables: ORCH_CLAUDE_BIN (claude binary to run, default `claude`; an absolute path must be an
executable file, a bare name is looked up on PATH; use it to bypass a wrapper on PATH).
ORCH_CLAUDE_EK_ORTAM: variable names to pass in addition to the allow list, comma-separated (for example a corporate
certificate path).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping

import codex_cagri as _ortak

SALT_OKUR_ARACLAR = "Read,Grep,Glob"

# Allow list. Names: basic shell environment, network/certificates (to reach the API on a corporate network),
# credentials. CLAUDE_CONFIG_DIR passes because it can move the credential file; --restricted already ignores the
# settings files in that folder.
_GECEN_ADLAR = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "TMPDIR", "TERM",
    "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy",
    "NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "SSL_CERT_DIR",
    "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CONFIG_DIR",
    "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
    "CLAUDE_CODE_SKIP_BEDROCK_AUTH", "CLAUDE_CODE_SKIP_VERTEX_AUTH", "CLAUDE_CODE_SKIP_FOUNDRY_AUTH",
})
_GECEN_ONEKLER = ("LC_", "ANTHROPIC_")
# Cloud provider variables pass only while the matching USE_ flag is set: AWS and Google credentials must not leak
# into a call that does not use Bedrock/Vertex (keep the leak surface small).
_SAGLAYICI_ONEKLERI = {
    "CLAUDE_CODE_USE_BEDROCK": ("AWS_",),
    "CLAUDE_CODE_USE_VERTEX": ("GOOGLE_", "CLOUDSDK_", "CLOUD_ML_", "VERTEX_REGION_", "GCLOUD_"),
}
EK_ORTAM_DEGISKENI = "ORCH_CLAUDE_EK_ORTAM"
# Alias: the Claude CLI resolves "opus" to the family's newest model [DOCS claude --help > --model], so there is no
# version id to update here.
MODELLER = ("opus",)


def _bayrak_dolu(deger: str | None) -> bool:
    return bool(deger) and deger.strip().lower() not in ("0", "false", "no", "")


def claude_ortami(ortam: Mapping[str, str] | None = None) -> dict[str, str]:
    """Allow-listed copy of the environment (module docs > Environment)."""
    ortam = os.environ if ortam is None else ortam
    onekler = list(_GECEN_ONEKLER)
    for bayrak, ekler in _SAGLAYICI_ONEKLERI.items():
        if _bayrak_dolu(ortam.get(bayrak)):
            onekler.extend(ekler)
    ek = {a.strip() for a in (ortam.get(EK_ORTAM_DEGISKENI) or "").split(",") if a.strip()}
    return {k: v for k, v in ortam.items() if k in _GECEN_ADLAR or k in ek or k.startswith(tuple(onekler))}


def model_kimligi(olay_yolu: Path | str) -> str | None:
    """The `model` field of the `system/init` event in the event stream (resolved full id). `result.modelUsage` is
    not used because it also lists other models used for side tasks [MEASURED 2026-11-07: haiku and opus together in
    modelUsage]."""
    try:
        akis = Path(olay_yolu).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for satir in akis.splitlines():
        try:
            olay = json.loads(satir)
        except json.JSONDecodeError:
            continue
        if isinstance(olay, dict) and olay.get("type") == "system" and olay.get("subtype") == "init":
            model = olay.get("model")
            return model if isinstance(model, str) and model else None
    return None


def _sonuc_satiri(akis: str) -> dict | None:
    son = None
    for satir in akis.splitlines():
        satir = satir.strip()
        if not satir.startswith("{"):
            continue
        try:
            olay = json.loads(satir)
        except json.JSONDecodeError:
            continue
        if isinstance(olay, dict) and olay.get("type") == "result":
            son = olay
    return son


def cagir(model: str, effort: str, istem: str, cikti_semasi: Path | str | dict | None = None,
          *, calisma_dizini: Path | str | None = None,
          zaman_asimi: float = _ortak.ZAMAN_ASIMI) -> tuple[int, str, str]:
    if model not in MODELLER:
        raise ValueError(f"unknown Claude model: {model!r} (defined: {', '.join(MODELLER)})")
    olay_yolu = _ortak.yeni_olay_yolu(f"claude-{model}")
    claude = _ortak.calistirilabilir_bul("claude", "ORCH_CLAUDE_BIN")
    if claude is None:
        olay_yolu.write_text("", encoding="utf-8")
        return _ortak.KOD_ARAC_YOK, "claude not found (ORCH_CLAUDE_BIN must be an absolute executable path or a " \
                                    "name on PATH; default `claude`)", str(olay_yolu)
    argv = [claude, "-p", "--model", model, "--effort", effort, "--tools", SALT_OKUR_ARACLAR,
            "--permission-mode", "dontAsk", "--output-format", "stream-json", "--verbose",
            "--no-session-persistence", "--strict-mcp-config", "--restricted"]
    if cikti_semasi is not None:
        sema = cikti_semasi if isinstance(cikti_semasi, dict) else \
            json.loads(Path(cikti_semasi).read_text(encoding="utf-8"))
        argv += ["--json-schema", json.dumps(sema, ensure_ascii=False)]
    cwd = str(Path(calisma_dizini).resolve()) if calisma_dizini is not None else None
    # Prompt on stdin (-p without a prompt argument reads stdin; measured in an earlier internal project).
    kod, stderr = _ortak._calistir(argv, istem, olay_yolu, cwd, claude_ortami(), zaman_asimi)
    sonuc = _sonuc_satiri(olay_yolu.read_text(encoding="utf-8", errors="replace"))
    if sonuc is None:
        return (kod or 1), (stderr.strip()[-2000:] or "no claude result line"), str(olay_yolu)
    if sonuc.get("is_error") or sonuc.get("subtype", "success") != "success":
        return (kod or 1), f"claude reported an error: {str(sonuc.get('result'))[:2000]}", str(olay_yolu)
    yapili = sonuc.get("structured_output")
    son = json.dumps(yapili, ensure_ascii=False) if isinstance(yapili, (dict, list)) else str(sonuc.get("result", ""))
    return kod, son, str(olay_yolu)
