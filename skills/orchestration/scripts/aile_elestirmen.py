#!/usr/bin/env python3
"""Critic from a different model family: sends a brief to the opposite family read-only and gets structured findings.

Direction: from a Claude session the critic is Codex (Astra/Sol); from a Codex session it is Claude (Opus). `--aile`
selects it explicitly; if the session cannot be detected from the environment, `--aile` is required.

Usage:
  aile_elestirmen.py --effort medium --brief brief.md --cikti findings.json [--aile codex|claude]
                     [--model astra|sol|opus] [--calisma-dizini DIR] [--kayit docs/STATE.md --olay "plan"]
The working folder (default: the current cwd) is passed explicitly in both directions: `-C` for Codex, process cwd for
Claude. The critic reads only this folder (Codex read-only sandbox, Claude --restricted).
In the record and summary lines the model appears as `family (full id)`; just the family if the full id is unknown.
Exit: 0 valid result · 3 output does not match the schema (undetermined) · 6 valid result but the record lock was not
taken (line not written, printed to stderr) · 77 codex login required · other: the tool's own code.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Mapping

import claude_cagri
import codex_cagri
import elestirmen_kayit_eki

SEMA_YOLU = Path(__file__).resolve().parent / "elestirmen_sema.json"
EK_GOREV = "Task: find the weakest point. If there is no significant weakness, say 'none'."
SALT_OKUR_CUMLESI = "You are read-only; do not modify files."
KOD_GECERSIZ_CIKTI = 3
KOD_KAYIT_KILIDI = 6
ONEMLER = ("yuksek", "orta", "dusuk")

# Session markers [MEASURED 2026-11-07]: a Claude Code session's shell has CLAUDECODE=1 (`env`). In a Codex
# session's shell CODEX_CI and CODEX_SESSION_ID were seen (environment dump in one Codex session log, n=1);
# CODEX_THREAD_ID appears as an environment name in the codex-cli 0.166.0 binary (string scan, behaviour not
# verified). CODEX_HOME is not a marker: users may set it in their own shell too.
CLAUDE_ISARETLERI = ("CLAUDECODE",)
CODEX_ISARETLERI = ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_CI")


def varsayilan_aile(ortam: Mapping[str, str] | None = None) -> str | None:
    """The family opposite to the running tool; None if it cannot be detected or both markers are present."""
    ortam = os.environ if ortam is None else ortam
    claude = any(ortam.get(a) for a in CLAUDE_ISARETLERI)
    codex = any(ortam.get(a) for a in CODEX_ISARETLERI)
    if claude == codex:
        return None
    return "codex" if claude else "claude"


def brief_hazirla(metin: str) -> str:
    """Appends the task sentences unless "weakest" and "none" both appear. No "is it ready" question is added: the
    readiness decision belongs to the caller, not the critic."""
    kucuk = metin.lower()
    if "weakest" in kucuk and "none" in kucuk:
        return metin
    return metin.rstrip() + "\n\n" + EK_GOREV + "\n"


def sonuc_hatasi(veri: object) -> str | None:
    """Conformance to elestirmen_sema.json; the reason if it does not conform."""
    if not isinstance(veri, dict) or set(veri) != {"zayiflik_var", "bulgular", "belirsizlik"}:
        return "top-level fields do not match the schema"
    if not isinstance(veri["zayiflik_var"], bool) or not isinstance(veri["belirsizlik"], str):
        return "zayiflik_var must be a bool, belirsizlik a string"
    if not isinstance(veri["bulgular"], list):
        return "bulgular must be a list"
    for i, b in enumerate(veri["bulgular"]):
        if not isinstance(b, dict) or set(b) != {"bulgu", "onem", "kanit", "oneri"}:
            return f"bulgular[{i}] fields do not match the schema"
        if b["onem"] not in ONEMLER or not all(isinstance(b[k], str) for k in b):
            return f"bulgular[{i}] onem must be yuksek|orta|dusuk, fields strings"
    return None


def model_etiketi(aile_adi: str, tam_kimlik: str | None) -> str:
    """Same format in both directions: "astra (gpt-6-astra)", "opus (claude-opus-5-5)"; just the name if there is no
    id or it is identical."""
    return f"{aile_adi} ({tam_kimlik})" if tam_kimlik and tam_kimlik != aile_adi else aile_adi


def kayit_satiri(zaman: datetime.datetime, olay: str, model: str, effort: str, veri: dict | None,
                 cikti: str, neden: str | None = None) -> str:
    if veri is None:
        ozet = f"undetermined ({neden})"
    else:
        yuksek = sum(1 for b in veri["bulgular"] if b["onem"] == "yuksek")
        ozet = f"findings {len(veri['bulgular'])} (high {yuksek})"
    return f"Cross-family {zaman:%Y-%m-%d %H:%M} · {olay} · {model} · {effort} · {ozet} · {cikti}"


def _ayristirici() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Read-only critique from a different model family.")
    p.add_argument("--aile", choices=("codex", "claude"),
                   help="critic family (default: the opposite of the running tool)")
    p.add_argument("--model", help="codex: astra|sol (default astra) · claude: opus (default)")
    p.add_argument("--effort", required=True, choices=("medium", "high"))
    p.add_argument("--brief", required=True, help="brief file")
    p.add_argument("--cikti", required=True, help="result JSON file")
    p.add_argument("--calisma-dizini", default=None,
                   help="folder the critic reads (default: the current working directory)")
    p.add_argument("--kayit", help="project STATE/log file to append one line to")
    p.add_argument("--olay", help="short event name for the record line (required with --kayit)")
    return p


def ana(argv: list[str] | None = None) -> int:
    p = _ayristirici()
    a = p.parse_args(argv)
    if a.kayit and not a.olay:
        p.error("--olay is required when --kayit is given")
    aile = a.aile or varsayilan_aile()
    if aile is None:
        p.error("could not detect the running tool from the environment (CLAUDECODE or CODEX_THREAD_ID/"
                "CODEX_SESSION_ID/CODEX_CI); pass --aile codex|claude")
    if aile == "codex":
        model = a.model or "astra"
        if model not in ("astra", "sol"):
            p.error("for the codex family use --model astra|sol")
    else:
        model = a.model or "opus"
        if model not in claude_cagri.MODELLER:
            p.error(f"for the claude family use --model {'|'.join(claude_cagri.MODELLER)}")

    calisma = Path(a.calisma_dizini or os.getcwd()).resolve()
    if not calisma.is_dir():
        p.error(f"--calisma-dizini is not a folder: {calisma}")
    istem = brief_hazirla(Path(a.brief).read_text(encoding="utf-8"))
    if aile == "codex":
        # The Codex event stream does not carry the model [MEASURED smoke test 2026-11-07]: the requested id is written.
        model_kimligi = model_etiketi(model, codex_cagri.model_coz(model))
        kod, son, akis = codex_cagri.cagir(model, a.effort, istem, sandbox="read-only", cikti_semasi=SEMA_YOLU,
                                           calisma_dizini=calisma)
    else:
        # In Claude the tools are already read-only via --tools; the sentence also aligns the model's intent.
        istem = istem.rstrip() + "\n" + SALT_OKUR_CUMLESI + "\n"
        kod, son, akis = claude_cagri.cagir(model, a.effort, istem, cikti_semasi=SEMA_YOLU, calisma_dizini=calisma)
        model_kimligi = model_etiketi(model, claude_cagri.model_kimligi(akis))

    cikti = Path(a.cikti)
    cikti.parent.mkdir(parents=True, exist_ok=True)
    veri, neden = None, None
    if kod == 0:
        try:
            veri = json.loads(son)
            neden = sonuc_hatasi(veri)
        except json.JSONDecodeError:
            neden = "output is not JSON"
        if neden:
            veri = None
    else:
        neden = f"call exit code {kod}"
    cikti.write_text(json.dumps(veri, ensure_ascii=False, indent=2) + "\n" if veri is not None else son,
                     encoding="utf-8")

    kayit_kodu = 0
    if a.kayit:
        satir = kayit_satiri(datetime.datetime.now(), a.olay, model_kimligi, a.effort, veri, str(cikti), neden)
        try:  # same lock as the decision-suffix script: a concurrent read-modify-write must not drop this line
            elestirmen_kayit_eki.kayda_ekle(a.kayit, satir)
        except elestirmen_kayit_eki.KilitAlinamadi as e:
            print(f"record lock not taken ({e}); record not written, add the line by hand: {satir}", file=sys.stderr)
            kayit_kodu = KOD_KAYIT_KILIDI

    if veri is not None:
        yuksek = sum(1 for b in veri["bulgular"] if b["onem"] == "yuksek")
        print(f"Cross-family ({aile}, {model_kimligi}, {a.effort}): findings {len(veri['bulgular'])} (high {yuksek}), "
              f"weakness {'yes' if veri['zayiflik_var'] else 'no'}. Output: {cikti} · event stream: {akis}")
        return kayit_kodu
    print(f"Cross-family ({aile}, {model_kimligi}, {a.effort}): undetermined, {neden}. "
          f"Raw output: {cikti} · event stream: {akis}", file=sys.stderr)
    if kod != 0 and son:
        print(son[-1000:], file=sys.stderr)
    return kod if kod != 0 else KOD_GECERSIZ_CIKTI


if __name__ == "__main__":
    sys.exit(ana())
