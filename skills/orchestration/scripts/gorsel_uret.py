#!/usr/bin/env python3
"""Produces a PNG with Codex's image generation tool. Codex direction only (Claude has no image generation tool); in
a Codex main session this script is unnecessary, the image tool can be used directly.

Usage:
  gorsel_uret.py --istem "..." | --istem-dosyasi FILE  --cikti PATH.png  [-i REFERENCE ...]  [--model astra|sol]
Model: astra (default) for important or outward-facing images, sol for routine images.
Exit: 0 image written · 4 image not found · 77 codex login required · other: codex's own code.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

import codex_cagri

KOD_GORSEL_YOK = 4
DOSYA_ADI = "gorsel.png"
KAYDET = (f"\n\nUse the image generation tool and save the result as a PNG named {DOSYA_ADI} in this working "
          f"folder. Do not create any other file.")


def en_yeni_png(kok: Path) -> Path | None:
    """`<home>/generated_images/<session>/exec-*.png`, nested; the newest by mtime [MEASURED 2026-11-07, the
    existing layout under ~/.codex]."""
    adaylar = [p for p in (kok / "generated_images").rglob("*.png") if p.is_file()]
    return max(adaylar, key=lambda p: p.stat().st_mtime) if adaylar else None


def ana(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate a PNG with the Codex image tool.")
    p.add_argument("--model", choices=("astra", "sol"), default="astra")
    p.add_argument("--effort", choices=("low", "medium", "high"), default="medium")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--istem")
    g.add_argument("--istem-dosyasi")
    p.add_argument("--cikti", required=True, help="target PNG path")
    p.add_argument("-i", "--referans", action="append", default=[], help="reference image (repeatable)")
    a = p.parse_args(argv)

    istem = a.istem if a.istem is not None else Path(a.istem_dosyasi).read_text(encoding="utf-8")
    hedef = Path(a.cikti).resolve()
    referanslar = [Path(r).resolve() for r in a.referans]
    for r in referanslar:
        if not r.is_file():
            p.error(f"reference image not found: {r}")
    hedef.parent.mkdir(parents=True, exist_ok=True)
    kaynak = {}

    with tempfile.TemporaryDirectory(prefix="orch-gorsel-") as calisma:
        calisma_yolu = Path(calisma)

        def al(ev: Path) -> None:
            # Called before the temporary home is deleted: if the model did not save the file, fall back to the tool's own output.
            aday = calisma_yolu / DOSYA_ADI
            if aday.is_file() and aday.stat().st_size > 0:
                kaynak["yol"], kaynak["tur"] = aday, "working folder"
            elif (yedek := en_yeni_png(ev)) is not None:
                kaynak["yol"], kaynak["tur"] = yedek, "temporary home generated_images"
            if kaynak:
                shutil.copyfile(kaynak["yol"], hedef)

        # Sandbox workspace-write: the model must be able to write the file into the -C working folder. Under
        # read-only, model commands cannot write files [DOCS codex exec --help > --sandbox]; image generation with
        # workspace-write + an empty temporary -C worked in an earlier internal project [MEASURED 2026-09-27]. Write
        # access is only to this temporary folder; the --cikti folder is not opened (--add-dir), the script copies
        # the file there.
        kod, son, akis = codex_cagri.cagir(a.model, a.effort, istem.rstrip() + KAYDET, sandbox="workspace-write",
                                           girdi_gorselleri=referanslar, calisma_dizini=calisma_yolu,
                                           ev_kancasi=al)
    if kod == codex_cagri.KOD_LOGIN_GEREKLI:
        print(son, file=sys.stderr)
        return kod
    if not kaynak:
        print(f"image not found (codex exit {kod}); event stream: {akis}", file=sys.stderr)
        if son:
            print(son[-1000:], file=sys.stderr)
        return kod if kod != 0 else KOD_GORSEL_YOK
    print(f"Image written: {hedef} (source: {kaynak['tur']}, model {codex_cagri.model_coz(a.model)}) · "
          f"event stream: {akis}")
    return 0


if __name__ == "__main__":
    sys.exit(ana())
