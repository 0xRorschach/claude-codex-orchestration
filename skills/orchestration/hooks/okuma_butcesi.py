#!/usr/bin/env python3
"""PostToolUse hook (Read|Bash|Grep|Glob): accumulates the main session's own read/command output per session.
Only the response fields that reach the model are counted (allowlist in MODEL_ALANLARI, see uzunluk).

Why: in orchestration the main session coordinates; exploration and verification go to subagents. In a measurement
the main session's Bash work output was twice the size of the subagent results; the rule was written down but not
visible at decision time. This hook reminds once the accumulation crosses a threshold. It does not block; it only
adds context.

Threshold: ORCH_OKUMA_ESIGI (characters, default 40000). Why 40000: the measured median starting context is ~80k
tokens; 40k characters (~10k tokens) is a noticeable but early share of that, early enough for a delegation
decision. It warns once when the threshold is crossed and then once at each multiple (2x, 3x, ...); skipping several
multiples in one call still gives a single warning.

Subagent detection and the Claude Code/Codex input difference live in one place, kanca_girdisi.py. In Claude Code a
hook inside a subagent carries `agent_id` [docs]; in Codex the transcript header is read as an extra path (details
there). In Codex, file reads are also shell commands; Codex PostToolUse input arrives with tool_name "Bash" [docs],
there is no Read/Grep/Glob counterpart.

Exempt (not counted, Bash commands only): git commit/push, a single-commit `git log` (`-1`, `-n 1`, `-n1` or
`--max-count=1`; alongside only the `--format=`, `--pretty=`, `--oneline`, `--date=` flags), codex exec (cross-family
call), aile_elestirmen.py, extra scripts listed in ORCH_MUAF_BETIKLER (comma-separated file names), heredocs writing
to a .md file (writing a record, not reading), --help/--version. Heredoc bodies are removed first (only a `<<END`
outside quotes counts as a heredoc), then the command is split on `&&`, `||`, `;`, `|`, a single `&` (background)
and newlines outside quotes; the `2>&1`, `>&2`, `&>` redirections do not split. A command is exempt only if all its
parts are exempt (B1: `cat big.log; git commit` used to pass as exempt). A command longer than AZAMI_KOMUT is not
parsed and is not exempt (parsing was quadratic on large input). A `cd` part is neutral since it produces no output.
The pattern is matched in command position: `rg 'git push' src` is not exempt. Reading a .md file with Read is not
exempt: that is a real read.

State: <plugin data>/okuma/<session_id>.json when CLAUDE_PLUGIN_DATA or PLUGIN_DATA is set (plugin mode), otherwise
${XDG_CACHE_HOME:-$HOME/.cache}/orchestration/okuma/<session_id>.json. Parallel PostToolUse calls update the
same file (B5): read-modify-write runs under fcntl.flock on `<session_id>.lock`, and the temporary file is unique via
mkstemp. .json, .tmp and .lock files older than 7 days are removed silently.
Disable: ORCH_OKUMA_BUTCESI=0. Every error path exits silently (exit 0), including import errors and a closed stdout
(B2, B3).
"""
import sys

try:
    import fcntl
    import json
    import os
    import re
    import shlex
    import tempfile
    import time
    from pathlib import Path

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import kanca_girdisi as kg

    HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
    # The target token is taken whole and its `.md` ending is checked in code: the old `[^...]+\.md\b` backtracked
    # inside the token. Because the token class includes `.`, `a.md.bak` no longer counts as a .md target.
    MD_HEDEF = re.compile(r"(?:>>?|\btee\b)\s*(?:-a\s+)?['\"]?([^\s'\"<>|;&]+)")
    YORUMLAYICI = re.compile(r"^python[0-9.]*$")
    MUAF_BETIKLER = {"aile_elestirmen.py"}  # extend via ORCH_MUAF_BETIKLER (comma-separated file names)
    # git log: a single commit + format-only flags is exempt; any flag printing diffs, stats or many commits is a read.
    TEK_KAYIT = {"-1", "-n1", "--max-count=1"}
    BICIM_ONEKLERI = ("--format=", "--pretty=", "--date=")
except BaseException:  # if the helper or a standard module cannot be loaded, the hook does nothing (B3)
    kg = None

OLAY = "PostToolUse"
ARACLAR = {"Read", "Bash", "Grep", "Glob"}
VARSAYILAN_ESIK = 40000
# 16 KB: exempt commands (commit, push, record heredoc) are far below this; anything above is counted unparsed. The
# cost is small: what is counted is the output, not the command (`cat > STATE.md <<EOF` has empty output). Measured:
# parsing took 13 s on an 800 KB single token and 33-71 s on a 2 MB heredoc (two independent reviews, 2026-11-07).
AZAMI_KOMUT = 16384
SAKLAMA_SN = 7 * 86400  # 7 days: state of closed sessions does not pile up, a running session is unaffected
METIN = ("The main session has collected ~{n}k characters of read/command output this session. Delegate "
         "exploration and verification to explorer/scanner (orchestration > Delegation).")

NOKTALAMA = ".,;:!?)\"'"


def tirnak_disi_heredoclar(satir, tirnak=None):
    """Terminator names of `<<END` heredocs starting outside quotes on the line, and the quote state at line end.
    `echo "x <<EOF"` is not a heredoc; in `<<'EOF'` the quote is part of the terminator, so it is a heredoc."""
    adlar, i, n = [], 0, len(satir)
    while i < n:
        c = satir[i]
        if tirnak:
            if c == "\\" and tirnak == '"':
                i += 1
            elif c == tirnak:
                tirnak = None
        elif c == "\\":
            i += 1
        elif c in "'\"":
            tirnak = c
        elif c == "<":
            m = HEREDOC.match(satir, i)
            if m:
                adlar.append(m.group(2))
                i = m.end()
                continue
        i += 1
    return adlar, tirnak


def heredoc_govdelerini_cikar(komut):
    """Drops heredoc body lines started by `<<END`, terminator line included; the command line stays. Quote state
    is carried across lines: a `<<END` inside a multi-line quote is not a heredoc either."""
    kalan, beklenen, tirnak = [], [], None
    for satir in komut.split("\n"):
        if beklenen:
            if satir.strip() == beklenen[0]:
                beklenen.pop(0)
            continue
        kalan.append(satir)
        beklenen, tirnak = tirnak_disi_heredoclar(satir, tirnak)
    return "\n".join(kalan)


def parcalara_bol(komut):
    """Splits on `&&`, `||`, `;`, `|`, `|&`, a single `&` (background) and newlines outside quotes; empty parts are
    dropped. `2>&1`, `>&2`, `<&3`, `&>`, `&>>` are redirections and do not split."""
    parcalar, simdiki, tirnak, i = [], [], None, 0
    while i < len(komut):
        c = komut[i]
        if tirnak:
            simdiki.append(c)
            if c == "\\" and tirnak == '"' and i + 1 < len(komut):
                simdiki.append(komut[i + 1])
                i += 1
            elif c == tirnak:
                tirnak = None
        elif c == "\\" and i + 1 < len(komut):
            simdiki.append(komut[i:i + 2])
            i += 1
        elif c in "'\"":
            tirnak = c
            simdiki.append(c)
        elif c == "&" and (komut.startswith("&>", i) or (i > 0 and komut[i - 1] in "<>")):
            simdiki.append(c)
        elif c in ";\n|&":
            parcalar.append("".join(simdiki))
            simdiki = []
            if komut.startswith(("&&", "||", "|&"), i):
                i += 1
        else:
            simdiki.append(c)
        i += 1
    parcalar.append("".join(simdiki))
    return [p.strip() for p in parcalar if p.strip()]


def _belirtecler(parca):
    try:
        b = shlex.split(parca, posix=True)
    except ValueError:
        b = parca.split()
    while b and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", b[0]):  # leading VAR=value assignments
        b = b[1:]
    return b


def _git_alt_komutu(b):
    """`git [-C path] [-c a=b] <sub> ...` -> (sub, rest)."""
    i = 1
    while i < len(b) and b[i] in ("-C", "-c"):
        i += 2
    return (b[i], b[i + 1:]) if i < len(b) else (None, [])


def md_hedefi_var(parca):
    return any(m.group(1).endswith(".md") for m in MD_HEDEF.finditer(parca))


def git_log_tek_kayit_mi(kalan):
    """True if the `git log` arguments select a single commit with format-only flags. A non-flag positional argument
    (a revision, a redirection like `2>/dev/null`) does not add commits and passes; any other flag, `--` included,
    does not."""
    tek, i = False, 0
    while i < len(kalan):
        x = kalan[i]
        if x in TEK_KAYIT:
            tek = True
        elif x == "-n" and i + 1 < len(kalan) and kalan[i + 1] == "1":
            tek = True
            i += 1
        elif x == "--oneline" or x.startswith(BICIM_ONEKLERI):
            pass
        elif x.startswith("-"):
            return False
        i += 1
    return tek


def parca_muaf_mi(parca):
    if tirnak_disi_heredoclar(parca)[0] and md_hedefi_var(parca):
        return True
    b = _belirtecler(parca)
    if not b:
        return True
    if any(x.rstrip(NOKTALAMA) in ("--help", "--version") for x in b[1:]):
        return True
    ad = os.path.basename(b[0])
    if ad == "cd":
        return True  # produces no output; keep `cd /a && git push` exempt
    if ad == "git":
        alt, kalan = _git_alt_komutu(b)
        if alt in ("commit", "push"):
            return True
        return alt == "log" and git_log_tek_kayit_mi(kalan)
    if ad == "codex":
        return len(b) > 1 and b[1] == "exec"
    if YORUMLAYICI.match(ad):
        betik = next((x for x in b[1:] if not x.startswith("-")), "")
        return os.path.basename(betik) in muaf_betikler()
    return ad in muaf_betikler()


def muaf_betikler():
    """Built-in exempt scripts plus ORCH_MUAF_BETIKLER (comma-separated file names, e.g. `notes.py,sync.py`); read on
    every call so the variable can change without reloading. Only base names are compared."""
    ek = {os.path.basename(a.strip()) for a in os.environ.get("ORCH_MUAF_BETIKLER", "").split(",") if a.strip()}
    return MUAF_BETIKLER | ek


def muaf_mi(komut):
    if len(komut) > AZAMI_KOMUT:
        return False
    parcalar = parcalara_bol(heredoc_govdelerini_cikar(komut))
    return bool(parcalar) and all(parca_muaf_mi(p) for p in parcalar)


# Fields that reach the model (allowlist). Why: Claude Code adds `bashEditDiff` (the diff of the change a command made
# to a file) to the Bash response; the model never sees it, and in a measured session it was most of what the old
# recursive sum counted. Shapes measured from `toolUseResult` in transcripts (2026-11-08): Bash {stdout, stderr, ...},
# Read {type, file: {content, ...}}, Grep {content, filenames, mode, numFiles, ...} (n=32), Glob {filenames, ...}
# (n=3); in Grep content mode the count matches what the model sees, filenames is empty, no double count (30 results).
MODEL_ALANLARI = {"Bash": ("stdout", "stderr"), "Grep": ("content", "filenames"), "Glob": ("filenames",)}
# Claude Code saves large Bash output to a file and sends the model a short preview; the response then carries
# `persistedOutputPath`. 2500: measured (n=8, 14 days, 2026-11-08) counted stdout 27,618-30,000 characters, preview
# sent to the model 1,930-2,533; set near the top of that range.
ONIZLEME_AZAMI = 2500


def _toplam(deger):
    """Total length of all strings in a nested structure (the old behaviour; used only as the fallback)."""
    if isinstance(deger, str):
        return len(deger)
    if isinstance(deger, dict):
        return sum(_toplam(v) for v in deger.values())
    if isinstance(deger, (list, tuple)):
        return sum(_toplam(v) for v in deger)
    return 0


def uzunluk(deger, arac=None):
    """Length of the text in tool_response that reaches the model. A plain-text response (Codex shell output, an
    error text) is counted as is. For Read only `file.content`; an image (`base64`) is not characters and counts 0.
    For Bash with `persistedOutputPath`, stdout counts at most ONIZLEME_AZAMI (the preview the model gets).
    An unknown shape (none of the allowed fields present) falls back to the recursive sum: over-counting brings the
    warning early, under-counting misses it silently; the first is the cheaper error."""
    if isinstance(deger, str):
        return len(deger)
    if not isinstance(deger, dict):
        return _toplam(deger)
    if arac == "Read" and isinstance(deger.get("file"), dict):
        dosya = deger["file"]
        if isinstance(dosya.get("content"), str):
            return len(dosya["content"])
        if deger.get("type") == "image" or "base64" in dosya:
            return 0  # an image does not reach the model as characters
        return _toplam(deger)  # unknown Read shape (e.g. PDF parts): fallback
    if arac == "Bash" and deger.get("persistedOutputPath") and isinstance(deger.get("stdout"), str):
        return min(len(deger["stdout"]), ONIZLEME_AZAMI) + _toplam(deger.get("stderr"))
    alanlar = MODEL_ALANLARI.get(arac, ())
    if any(a in deger for a in alanlar):
        return sum(_toplam(deger.get(a)) for a in alanlar)
    return _toplam(deger)


def esik():
    try:
        e = int(os.environ.get("ORCH_OKUMA_ESIGI", VARSAYILAN_ESIK))
        return e if e > 0 else VARSAYILAN_ESIK
    except ValueError:
        return VARSAYILAN_ESIK


def durum_dizini():
    for ad in ("CLAUDE_PLUGIN_DATA", "PLUGIN_DATA"):
        veri_dizini = (os.environ.get(ad) or "").strip()
        if veri_dizini:
            return Path(veri_dizini).expanduser() / "okuma"
    taban = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(taban) / "orchestration" / "okuma"


def eskileri_temizle(dizin):
    """Removes state (.json), lock (.lock) and leftover temporary (.tmp) files older than 7 days."""
    sinir = time.time() - SAKLAMA_SN
    for desen in ("*.json", "*.lock", "*.tmp"):
        for f in dizin.glob(desen):
            try:
                if f.stat().st_mtime < sinir:
                    f.unlink()
            except OSError:
                pass


def durumu_guncelle(dizin, sid, miktar):
    """Read-modify-write under the lock; returns (new total, whether a warning is due)."""
    yol = dizin / (sid + ".json")
    kilit_fd = os.open(dizin / (sid + ".lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(kilit_fd, fcntl.LOCK_EX)
        try:
            durum = json.loads(yol.read_text(encoding="utf-8"))
            toplam, son_kat = int(durum["toplam"]), int(durum["son_uyari_kati"])
        except Exception:
            toplam, son_kat = 0, 0
        toplam += miktar
        kat = toplam // esik()
        uyar = kat >= 1 and kat > son_kat
        if uyar:
            son_kat = kat
        fd, gecici = tempfile.mkstemp(dir=dizin, prefix=sid + ".json.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps({"toplam": toplam, "son_uyari_kati": son_kat}))
            os.replace(gecici, yol)
        except BaseException:
            try:
                os.unlink(gecici)
            except OSError:
                pass
            raise
        return toplam, uyar
    finally:
        os.close(kilit_fd)  # also releases the lock


def main():
    if kg is None or os.environ.get("ORCH_OKUMA_BUTCESI", "1").strip() == "0":
        return
    veri = kg.girdi_oku()
    if veri is None or veri.get("tool_name") not in ARACLAR or kg.alt_ajan_mi(veri, kg.arac(veri)):
        return
    if veri.get("tool_name") == "Bash" and muaf_mi(str((veri.get("tool_input") or {}).get("command") or "")):
        return
    miktar = uzunluk(veri.get("tool_response"), veri.get("tool_name"))
    sid = re.sub(r"[^A-Za-z0-9_-]", "", str(veri.get("session_id") or "")) or "unknown"

    dizin = durum_dizini()
    dizin.mkdir(parents=True, exist_ok=True)
    eskileri_temizle(dizin)
    toplam, uyar = durumu_guncelle(dizin, sid, miktar)
    if uyar:
        print(kg.baglam_ciktisi(OLAY, METIN.format(n=int(toplam / 1000 + 0.5))))


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        pass
    # With a closed stdout the buffer flush at interpreter shutdown exits 120 with BrokenPipeError/EBADF (B2):
    # it is caught here, then the shutdown flush is skipped via os._exit.
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
