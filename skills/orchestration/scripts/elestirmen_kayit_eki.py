#!/usr/bin/env python3
"""Decision suffix for a cross-family record line: `· applied (why)` or `· parked (why)`.

aile_elestirmen.py `--kayit` writes one line to the project ledger; once the main session has weighed the findings, it
appends the decision to the end of that same line. why: when the decision goes on a separate line, its effect cannot
be counted by script. This command finds the line by time + event, only appends to its end and opens no new line.

Usage:
  elestirmen_kayit_eki.py --kayit docs/STATE.md --zaman "2026-01-02 03:04" --olay "plan" --karar applied [--neden "..."]
  elestirmen_kayit_eki.py --kayit docs/log.md --zaman "2026-01-02 03:04" --olay "plan" --karar parked --neden "..."
Exit: 0 appended · 1 line not found (also when the file is missing) · 4 several lines matched · 5 the line already has
a decision · 6 record lock not taken · 7 record unreadable · 2 usage error.

Concurrency: the read-modify-write runs under fcntl.flock on
`~/.cache/orchestration/kayit-kilit/<first 16 hex digits of the sha256 of the real path>.lock`; the aile_elestirmen.py
`--kayit` append takes the same lock through `kayda_ekle` (without it, the atomic replace could drop a line appended in
between). The lock file is permanent; it lives in the cache, not next to the ledger, so no untracked `*.lock` files
show up in project repositories.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import os
import re
import sys
import tempfile
import time
from pathlib import Path

KARARLAR = ("applied", "parked")
KOD_YOK, KOD_COK, KOD_EKLI, KOD_KILIT, KOD_OKUNAMADI = 1, 4, 5, 6, 7
# Decision suffixes the rule book uses (`· applied / parked (why)`, the advisor's `· applied / not applied (why)`),
# bare or followed by `(...)` or `: ...`. If one of them is present, the line counts as already decided.
EK_VAR = re.compile(r" · (applied|not applied|parked)\b")
# A single append takes milliseconds; 10 s waits for a few agents writing at once without hanging forever on a stuck
# process. Tests shorten it.
KILIT_BEKLEME_SN = 10.0
KILIT_ARALIK_SN = 0.05


class KilitAlinamadi(Exception):
    """The record lock could not be taken (timeout, or the lock file could not be opened)."""


def gercek_yol(yol: str | os.PathLike) -> Path:
    """Symlinks are resolved: the link and its target take the same lock, the write goes to the target, the link stays."""
    return Path(os.path.realpath(yol))


def kilit_yolu(yol: str | os.PathLike) -> Path:
    """Same real path -> same lock; the name is the first 16 hex digits of the real path's sha256 (short, no practical
    collisions)."""
    ad = hashlib.sha256(str(gercek_yol(yol)).encode("utf-8")).hexdigest()[:16]
    return Path(os.path.expanduser("~")) / ".cache" / "orchestration" / "kayit-kilit" / f"{ad}.lock"


@contextlib.contextmanager
def kayit_kilidi(yol: str | os.PathLike):
    """Advisory exclusive lock (kilit_yolu); KilitAlinamadi if it is not taken within KILIT_BEKLEME_SN or the lock
    file cannot be opened."""
    gercek = gercek_yol(yol)
    kilit = kilit_yolu(gercek)
    try:
        kilit.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(kilit, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError as e:
        raise KilitAlinamadi(f"could not open {kilit}: {e.__class__.__name__}") from None
    try:
        bitis = time.monotonic() + KILIT_BEKLEME_SN
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= bitis:
                    raise KilitAlinamadi(f"{kilit}, {KILIT_BEKLEME_SN:g} s") from None
                time.sleep(KILIT_ARALIK_SN)
        yield gercek
    finally:
        os.close(fd)  # also releases the lock


def kayda_ekle(yol: str | os.PathLike, satir: str) -> None:
    """One line at the end of the file, under the record lock (aile_elestirmen.py `--kayit`). The line ending follows
    the file's: CRLF if the first line ends in CRLF, otherwise LF."""
    with kayit_kilidi(yol) as gercek:
        try:
            icerik = gercek.read_bytes()
        except FileNotFoundError:
            icerik = b""
        ilk = icerik.find(b"\n")
        sonu = "\r\n" if ilk > 0 and icerik[ilk - 1:ilk] == b"\r" else "\n"
        with open(gercek, "a", encoding="utf-8", newline="") as f:
            f.write(("" if icerik[-1:] in (b"", b"\n") else sonu) + satir + sonu)


def satir_oneki(zaman: str, olay: str) -> str:
    return f"Cross-family {zaman} · {olay} · "


def ek_metni(karar: str, neden: str | None) -> str:
    return f" · {karar} ({neden})" if neden else f" · {karar}"


def ekle(metin: str, zaman: str, olay: str, karar: str, neden: str | None) -> tuple[int, str]:
    """(exit code, new text). Leading indentation and a `- ` list marker are accepted; the line ending (LF/CRLF) is
    kept. If the line already has a decision, 5; the one exception is `applied` on a line whose only decision is
    `parked` (parked -> applied, once)."""
    onek = satir_oneki(zaman, olay)
    satirlar = metin.split("\n")
    eslesen = [i for i, s in enumerate(satirlar) if s.lstrip("- ").startswith(onek)]
    if not eslesen:
        return KOD_YOK, metin
    if len(eslesen) > 1:
        return KOD_COK, metin
    i = eslesen[0]
    sonu = "\r" if satirlar[i].endswith("\r") else ""
    govde = satirlar[i].rstrip()
    ekler = EK_VAR.findall(govde[govde.find(onek) + len(onek):])
    if ekler and not (ekler == ["parked"] and karar == "applied"):
        return KOD_EKLI, metin
    satirlar[i] = govde + ek_metni(karar, neden) + sonu
    return 0, "\n".join(satirlar)


def _yaz(yol: Path, metin: str, kip: int) -> None:
    """Temporary file + os.replace; mkstemp opens it 0600, the old mode is restored."""
    fd, gecici = tempfile.mkstemp(dir=yol.parent, prefix=yol.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(metin)
        os.chmod(gecici, kip)
        os.replace(gecici, yol)
    except BaseException:
        try:
            os.unlink(gecici)
        except OSError:
            pass
        raise


def ana(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Decision suffix for a cross-family record line.")
    p.add_argument("--kayit", required=True, help="project STATE/ledger file that holds the line")
    p.add_argument("--zaman", required=True, help='time on the line, "YYYY-MM-DD HH:MM"')
    p.add_argument("--olay", required=True, help="event name on the line (the same as given to --olay)")
    p.add_argument("--karar", required=True, choices=KARARLAR)
    p.add_argument("--neden", help="written in parentheses; required for parked")
    a = p.parse_args(argv)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", a.zaman):
        p.error('--zaman must have the form "YYYY-MM-DD HH:MM"')
    if a.karar == "parked" and not (a.neden or "").strip():
        p.error("--neden is required for parked")
    neden = (a.neden or "").strip() or None
    if not gercek_yol(a.kayit).exists():  # no lock is opened for a missing ledger
        print(f"no record file, line not found: {a.kayit}", file=sys.stderr)
        return KOD_YOK
    try:
        with kayit_kilidi(a.kayit) as yol:
            try:
                kip = os.stat(yol).st_mode & 0o7777
                with open(yol, encoding="utf-8", newline="") as f:
                    metin = f.read()
            except FileNotFoundError:
                print(f"no record file, line not found: {a.kayit}", file=sys.stderr)
                return KOD_YOK
            except (OSError, UnicodeDecodeError) as e:
                print(f"record unreadable: {e.__class__.__name__}", file=sys.stderr)
                return KOD_OKUNAMADI
            kod, yeni = ekle(metin, a.zaman, a.olay, a.karar, neden)
            mesaj = {KOD_YOK: "line not found", KOD_COK: "several lines matched, fix the file by hand",
                     KOD_EKLI: "the line already has a decision, nothing appended"}
            if kod:
                print(f"{mesaj[kod]}: {satir_oneki(a.zaman, a.olay)}", file=sys.stderr)
                return kod
            _yaz(yol, yeni, kip)
    except KilitAlinamadi as e:
        print(f"record lock not taken ({e}), nothing appended", file=sys.stderr)
        return KOD_KILIT
    print(f"appended: {satir_oneki(a.zaman, a.olay)}…{ek_metni(a.karar, neden)}")
    return 0


if __name__ == "__main__":
    sys.exit(ana())
