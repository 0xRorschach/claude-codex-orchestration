#!/usr/bin/env python3
"""Shared core that calls Codex (a different model family) cleanly and safely. Standard library only.

Clean call pattern (the Python counterpart of the command block in orchestration SKILL.md > In Claude Code >
Second opinion):
- Temporary CODEX_HOME containing only a 0600 copy of auth.json. The user's config.toml, AGENTS.md, hooks and memory
  do not leak into the call; model, effort and sandbox are therefore given explicitly on the command line.
- `--skip-git-repo-check --ephemeral --disable hooks --disable memories`, prompt on stdin (`-`), no other stdin.
- Credential write-back: if codex refreshes an expired access token in the temporary home, the new token is written
  only there; since the old refresh token is single-use, the real auth.json becomes invalid and every later call
  fails with "refresh token was already used". So at the end of the call, if the temporary copy changed and the
  real file has not changed since the call started (sha256), the new content is written to the real file atomically
  (temporary file in the same folder + os.replace) with mode 0600. If another process changed the real file, it is
  not overwritten and a warning is returned. Comparison and write run under fcntl.flock on `auth.json.lock`: two
  concurrent calls cannot both see the same old sha and both write. The lock file is permanent (deleting it does not
  break the lock, it is simply recreated). Adapted from an earlier internal project (which used a link, not a copy).
- Credential error detection ("refresh token was already used"): searched only in stderr and in the error events of
  the event stream (top-level `type` error or turn.failed, or `item.type` error). Model messages (agent_message) and
  command output (command_execution) are not scanned: when the critic reviewed this script and quoted the pattern, a
  successful call used to get a false 77. Event names [MEASURED 2026-11-07]: real streams show thread.started,
  turn.started, turn.completed, item.started/completed (agent_message, command_execution); the codex binary's event
  names also include turn.failed, item.updated and error. The inner fields of turn.failed and error are not
  verified: every string inside the event is scanned.

Environment variables:
  ORCH_CODEX_BIN    codex binary to run (default `codex`). An absolute path must be an executable file; a bare name
                    is looked up on PATH; a relative path is rejected. Use it to bypass a wrapper on PATH (tests
                    point it at a fake binary).
  CODEX_HOME        real Codex home (default ~/.codex). Read only as the auth.json source.
  ORCH_OLAY_DIZINI  folder for event stream (JSONL) files; default ${XDG_STATE_HOME:-~/.local/state}/orchestration/olaylar
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

BETIK_DIZINI = Path(__file__).resolve().parent
MODELLER_YOLU = BETIK_DIZINI / "modeller.json"

# Exit codes. 77 = EX_NOPERM (sysexits): credential problem; the user must run `codex login`, no automatic retry
# (the refresh token is single-use, retrying does not fix the state).
KOD_LOGIN_GEREKLI = 77
KOD_ARAC_YOK = 127        # shell convention: command not found
KOD_ZAMAN_ASIMI = 124     # timeout(1) convention
ZAMAN_ASIMI = 1800        # s; upper bound for long audits/image generation, only a guard against hanging

_REFRESH_HATASI = re.compile(r"refresh[ _-]?token\s+(?:was|has\s+been|is)\s+already\s+(?:been\s+)?used", re.I)
_ATILAN_ONEKLER = ("CLAUDE_CODE_",)
_ATILAN_ADLAR = frozenset({"CLAUDECODE", "CLAUDE_EFFORT", "CLAUDE_PID"})


def model_coz(aile: str, yol: Path | str | None = None) -> str:
    """Family name ("astra"/"sol") -> full model id, from `modeller.json`. Update the ids there when models change."""
    veri = json.loads(Path(yol or MODELLER_YOLU).read_text(encoding="utf-8"))
    anahtar = aile.strip().lower()
    if anahtar not in veri:
        raise ValueError(f"unknown model family: {aile!r} (defined: {', '.join(sorted(veri))})")
    return veri[anahtar]


def cocuk_ortami(ortam: Mapping[str, str] | None = None) -> dict[str, str]:
    """Copy of the environment without the parent Claude Code session markers (no nested-session detection, no hook
    interference)."""
    ortam = os.environ if ortam is None else ortam
    return {k: v for k, v in ortam.items() if k not in _ATILAN_ADLAR and not k.startswith(_ATILAN_ONEKLER)}


def calistirilabilir_bul(program: str, ortam_degiskeni: str, ortam: Mapping[str, str] | None = None) -> str | None:
    """Binary named by `ortam_degiskeni`, else `program`. An absolute path must be an executable file (else None, no
    fallback to PATH); a bare name is looked up on PATH; a relative path containing a separator is rejected (None)."""
    ortam = os.environ if ortam is None else ortam
    secim = (ortam.get(ortam_degiskeni) or "").strip() or program
    if os.path.isabs(secim):
        return secim if os.path.isfile(secim) and os.access(secim, os.X_OK) else None
    if os.sep in secim or (os.altsep and os.altsep in secim):
        return None
    return shutil.which(secim, path=ortam.get("PATH") or "")


def olay_dizini() -> Path:
    acik = os.environ.get("ORCH_OLAY_DIZINI")
    if acik:
        return Path(acik).expanduser()
    durum = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(durum) / "orchestration" / "olaylar"


def yeni_olay_yolu(onek: str) -> Path:
    dizin = olay_dizini()
    dizin.mkdir(parents=True, exist_ok=True)
    return dizin / f"{onek}-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-{time.monotonic_ns() % 10**6}.jsonl"


def _sha256(yol: Path) -> str:
    return hashlib.sha256(yol.read_bytes()).hexdigest()


def _kopyala_0600(kaynak: Path, hedef: Path) -> None:
    fd = os.open(hedef, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(kaynak.read_bytes())


def _oku_ya_da_none(yol: Path) -> bytes | None:
    try:
        return yol.read_bytes()
    except FileNotFoundError:
        return None


def auth_geri_yaz(kopya: Path, gercek: Path, gercek_sha0: str, kopya_sha0: str) -> str | None:
    """Three cases: (1) the copy did not change -> leave it; (2) the copy was refreshed, the real file did not change
    -> write back atomically with 0600; (3) the real file changed in another process during the call -> do not
    write, return a warning. None when there is no warning.
    Reading the real file, the sha comparison and os.replace happen inside one lock; each file is read once."""
    yeni = _oku_ya_da_none(kopya)
    if yeni is None or hashlib.sha256(yeni).hexdigest() == kopya_sha0:
        return None
    try:
        kilit_fd = os.open(gercek.with_name(gercek.name + ".lock"), os.O_RDWR | os.O_CREAT, 0o600)
    except OSError as e:
        return f"WARNING: could not open the auth.json lock ({e}); the refreshed credential was not written back, run `codex login` if needed"
    try:
        fcntl.flock(kilit_fd, fcntl.LOCK_EX)
        simdiki = _oku_ya_da_none(gercek)
        if simdiki == yeni:
            return None
        if simdiki is None or hashlib.sha256(simdiki).hexdigest() != gercek_sha0:
            return ("WARNING: codex refreshed auth.json but the real auth.json changed in another process during "
                    "the call; it was not written back to avoid overwriting it (run `codex login` if needed)")
        fd, gecici = tempfile.mkstemp(dir=gercek.parent, prefix=f".{gercek.name}-", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(yeni)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(gecici, 0o600)
            os.replace(gecici, gercek)
        except OSError as e:
            Path(gecici).unlink(missing_ok=True)
            return f"WARNING: the auth.json refreshed by codex could not be written to the real file ({e}); run `codex login` if needed"
        return None
    finally:
        os.close(kilit_fd)  # also releases the lock


_HATA_OLAYLARI = frozenset({"error", "turn.failed"})


def _metinler(deger: object) -> Iterable[str]:
    if isinstance(deger, str):
        yield deger
    elif isinstance(deger, dict):
        for v in deger.values():
            yield from _metinler(v)
    elif isinstance(deger, list):
        for v in deger:
            yield from _metinler(v)


def akista_kimlik_hatasi(akis: str) -> bool:
    """Whether the refresh error appears in the error events of the event stream only (module docs > Credential
    error detection)."""
    for satir in akis.splitlines():
        satir = satir.strip()
        if not satir.startswith("{"):
            continue
        try:
            olay = json.loads(satir)
        except json.JSONDecodeError:
            continue
        if not isinstance(olay, dict):
            continue
        oge = olay.get("item")
        hata = olay.get("type") in _HATA_OLAYLARI or (isinstance(oge, dict) and oge.get("type") == "error")
        if hata and any(_REFRESH_HATASI.search(m) for m in _metinler(olay)):
            return True
    return False


def _calistir(argv: Sequence[str], istem: str, olay_yolu: Path, cwd: str | None, ortam: dict[str, str],
              zaman_asimi: float) -> tuple[int, str]:
    """stdout streams to the event file; returns (exit code, stderr). The child starts in its own process group: on
    timeout the whole group is killed (codex.js starts the real binary as a child; killing only the direct child
    leaves the binary orphaned; measured in an earlier internal project, 2026-09-29)."""
    with open(olay_yolu, "wb") as akis:
        try:
            p = subprocess.Popen(list(argv), stdin=subprocess.PIPE, stdout=akis, stderr=subprocess.PIPE, cwd=cwd,
                                 env=ortam, start_new_session=True)
        except OSError as e:
            return KOD_ARAC_YOK, f"could not start {argv[0]}: {e}"
        try:
            _, err = p.communicate(input=istem.encode("utf-8"), timeout=zaman_asimi)
        except BaseException as e:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.wait()
            if isinstance(e, subprocess.TimeoutExpired):
                return KOD_ZAMAN_ASIMI, f"did not finish within {zaman_asimi:g} s, process group killed"
            raise
    return p.returncode, err.decode("utf-8", errors="replace")


def _stderr_uyari(metin: str) -> None:
    print(metin, file=sys.stderr)


def cagir(model_ailesi: str, effort: str, istem: str, sandbox: str = "read-only",
          cikti_semasi: Path | str | dict | None = None, ek_bayraklar: Iterable[str] = (),
          girdi_gorselleri: Iterable[Path | str] = (), *, calisma_dizini: Path | str | None = None,
          ev_kancasi: Callable[[Path], None] | None = None, uyari: Callable[[str], None] = _stderr_uyari,
          zaman_asimi: float = ZAMAN_ASIMI) -> tuple[int, str, str]:
    """Calls Codex once -> (exit code, last message, event stream path).

    cikti_semasi: JSON Schema file path or dict (`--output-schema`). calisma_dizini: `-C` and the process cwd.
    ev_kancasi: called with the temporary home path after codex finishes, before the temporary home is deleted (for
    example to fetch a generated image).
    Credential problem (no auth.json, or "refresh token was already used") -> KOD_LOGIN_GEREKLI, no retry."""
    model = model_coz(model_ailesi)
    olay_yolu = yeni_olay_yolu(f"codex-{model_ailesi.lower()}")
    codex = calistirilabilir_bul("codex", "ORCH_CODEX_BIN")
    if codex is None:
        olay_yolu.write_text("", encoding="utf-8")
        return KOD_ARAC_YOK, "codex not found (ORCH_CODEX_BIN must be an absolute executable path or a name on " \
                             "PATH; default `codex`)", str(olay_yolu)
    gercek_ev = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()
    gercek = gercek_ev / "auth.json"
    if not gercek.is_file():
        olay_yolu.write_text("", encoding="utf-8")
        return KOD_LOGIN_GEREKLI, "codex login required: no Codex credential file (auth.json)", str(olay_yolu)

    gecici = Path(tempfile.mkdtemp(prefix="orch-codex-"))
    ev = gecici / "ev"
    ev.mkdir()
    try:
        kopya = ev / "auth.json"
        gercek_sha0 = _sha256(gercek)
        _kopyala_0600(gercek, kopya)
        kopya_sha0 = _sha256(kopya)
        son_yol = gecici / "son-mesaj.txt"
        argv = [codex, "exec", "--skip-git-repo-check", "--ephemeral", "--disable", "hooks", "--disable", "memories",
                "-m", model, "-c", f"model_reasoning_effort={effort}", "--sandbox", sandbox, "--json",
                "-o", str(son_yol)]
        if cikti_semasi is not None:
            if isinstance(cikti_semasi, dict):
                sema_yolu = gecici / "sema.json"
                sema_yolu.write_text(json.dumps(cikti_semasi, ensure_ascii=False), encoding="utf-8")
            else:
                sema_yolu = Path(cikti_semasi).resolve()
            argv += ["--output-schema", str(sema_yolu)]
        cwd = str(Path(calisma_dizini).resolve()) if calisma_dizini is not None else None
        if cwd:
            argv += ["-C", cwd]
        argv += list(ek_bayraklar)
        # `-i/--image <FILE>...` is a multi-value flag; `--image=PATH` keeps it from swallowing the trailing `-`.
        argv += [f"--image={Path(g).resolve()}" for g in girdi_gorselleri]
        argv.append("-")   # prompt on stdin [DOCS codex exec --help: "-" reads stdin]
        ortam = cocuk_ortami()
        ortam["CODEX_HOME"] = str(ev)

        try:
            kod, stderr = _calistir(argv, istem, olay_yolu, cwd, ortam, zaman_asimi)
        finally:
            if (u := auth_geri_yaz(kopya, gercek, gercek_sha0, kopya_sha0)):
                uyari(u)
        if ev_kancasi is not None:
            ev_kancasi(ev)
        son = son_yol.read_text(encoding="utf-8") if son_yol.is_file() else ""
        akis = olay_yolu.read_text(encoding="utf-8", errors="replace")
        if _REFRESH_HATASI.search(stderr) or akista_kimlik_hatasi(akis):
            return (KOD_LOGIN_GEREKLI, "codex login required: the refresh token was already used; "
                                       "not retried", str(olay_yolu))
        if kod != 0 and not son:
            son = stderr.strip()[-2000:]
        return kod, son, str(olay_yolu)
    finally:
        shutil.rmtree(gecici, ignore_errors=True)
