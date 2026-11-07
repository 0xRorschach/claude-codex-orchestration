#!/usr/bin/env python3
"""SessionStart hook: warns when the installed superpowers version differs from the one the orchestration mapping
table was written for.

Why: the orchestration SKILL.md section "With superpowers" maps superpowers skills to agent types. When
superpowers is updated, skill names and templates can change and the table silently goes stale. This hook makes the
difference visible with one line at session start. It does not block; it only adds context.

Input/output [docs: code.claude.com/docs/en/hooks, learn.chatgpt.com/docs/hooks]: the event JSON arrives on stdin;
output is {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ...}}. Both tools add plain
SessionStart stdout to the context, so output is written only when there is a warning; otherwise nothing is printed.

Version source:
- Claude Code [measured, 2.1.319]: <config>/plugins/installed_plugins.json > plugins > "superpowers@<marketplace>"
  keys, each a list of {version, installPath, ...}; without version, <installPath>/.claude-plugin/plugin.json.
  An install explicitly set to false in settings.json > enabledPlugins is not counted.
- Codex [measured, codex-cli 0.166.0]: <CODEX_HOME>/plugins/cache/<marketplace>/superpowers/<version>/.codex-plugin/
  plugin.json (else the folder name). A marketplace with [plugins."superpowers@<marketplace>"] enabled = false in
  config.toml is not counted. This filter needs tomllib (Python 3.11+); on older Python the Codex branch reads no
  version at all and stays silent: no warning was chosen over a false warning based on a disabled marketplace.
The highest of the remaining versions is used. The registration command passes the `codex` argument for Codex.

Environment variables: ORCH_SURUM_BEKCISI=0 disables. ORCH_PLUGINS_DIR and ORCH_SURUM_TABLOSU override the paths
(for tests and other layouts). Every error path exits silently (exit 0): the watcher must never break a session.
This includes import errors and a closed stdout.
"""
import sys

try:
    import json
    import os
    from pathlib import Path

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import kanca_girdisi as kg
except BaseException:  # if the helper or a standard module cannot be loaded, the watcher does nothing
    kg = None

OLAY = "SessionStart"
METIN = ("superpowers {kurulu} is installed, but the orchestration mapping table was written for {tablo}: "
         "re-check the table (orchestration > With superpowers)")


def json_oku(yol):
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def surum_demeti(metin):
    """'7.0.10' -> (7, 0, 10). None if any part is non-numeric: no comparison is made when it cannot be trusted."""
    try:
        return tuple(int(p) for p in str(metin).strip().split("."))
    except (ValueError, AttributeError):
        return None


def manifest_surumu(kurulum_yolu, alt_dizin):
    m = json_oku(Path(kurulum_yolu) / alt_dizin / "plugin.json")
    return m.get("version") if isinstance(m, dict) else None


def claude_surumleri(yap, plugins):
    kayit = json_oku(plugins / "installed_plugins.json")
    if not isinstance(kayit, dict):
        return []
    eklentiler = kayit.get("plugins", kayit)
    ayarlar = json_oku(yap / "settings.json")
    etkin = ayarlar.get("enabledPlugins", {}) if isinstance(ayarlar, dict) else {}
    surumler = []
    for anahtar, kurulumlar in (eklentiler.items() if isinstance(eklentiler, dict) else []):
        if not str(anahtar).startswith("superpowers@") or etkin.get(anahtar) is False:
            continue
        for k in kurulumlar if isinstance(kurulumlar, list) else []:
            if not isinstance(k, dict):
                continue
            surum = k.get("version") or (k.get("installPath") and manifest_surumu(k["installPath"], ".claude-plugin"))
            if surum:
                surumler.append(str(surum))
    return surumler


def codex_kapali_pazarlar(yap):
    """Names of disabled marketplaces; None without tomllib (Python 3.10 and older): the filter cannot be applied."""
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        return None
    try:
        with open(yap / "config.toml", "rb") as f:
            ayar = tomllib.load(f)
    except Exception:
        return set()
    kapali = set()
    for anahtar, deger in (ayar.get("plugins") or {}).items():
        if str(anahtar).startswith("superpowers@") and isinstance(deger, dict) and deger.get("enabled") is False:
            kapali.add(str(anahtar).split("@", 1)[1])
    return kapali


def codex_surumleri(yap, plugins):
    kapali = codex_kapali_pazarlar(yap)
    if kapali is None:
        return []  # reading without the filter could count a disabled marketplace: silence instead of a false warning
    surumler = []
    for kurulum in sorted((plugins / "cache").glob("*/superpowers/*")):
        if not kurulum.is_dir() or kurulum.parent.parent.name in kapali:
            continue
        surumler.append(str(manifest_surumu(kurulum, ".codex-plugin") or kurulum.name))
    return surumler


def kurulu_surum(hangi):
    yap = kg.yapilandirma_dizini(hangi)
    plugins = Path(os.environ.get("ORCH_PLUGINS_DIR") or (yap / "plugins"))
    surumler = codex_surumleri(yap, plugins) if hangi == kg.CODEX else claude_surumleri(yap, plugins)
    demetler = [(surum_demeti(s), s) for s in surumler]
    if not demetler or any(d is None for d, _ in demetler):
        return None
    return max(demetler)[1]


def main():
    if kg is None or os.environ.get("ORCH_SURUM_BEKCISI", "1").strip() == "0":
        return
    veri = kg.girdi_oku()  # content is used only to detect the tool; failing to read it does not stop the watcher
    tablo_yolu = os.environ.get("ORCH_SURUM_TABLOSU") or (Path(__file__).resolve().parent / "superpowers_surum.json")
    tablo = json_oku(tablo_yolu)
    tablo_surumu = tablo.get("tablo_surumu") if isinstance(tablo, dict) else None
    kurulu = kurulu_surum(kg.arac(veri))
    if not tablo_surumu or not kurulu or surum_demeti(tablo_surumu) is None:
        return
    if surum_demeti(kurulu) == surum_demeti(tablo_surumu):
        return
    print(kg.baglam_ciktisi(OLAY, METIN.format(kurulu=kurulu, tablo=tablo_surumu)))


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        pass
    # With a closed stdout the buffer flush at shutdown exits 120: it is caught here and shutdown is skipped via os._exit.
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
