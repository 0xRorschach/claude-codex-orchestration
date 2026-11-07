"""Shared test setup: a temporary "real" CODEX_HOME, a fake codex, an event folder. The real ~/.codex is not touched."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TESTLER = Path(__file__).resolve().parent
BETIKLER = TESTLER.parent
if str(BETIKLER) not in sys.path:
    sys.path.insert(0, str(BETIKLER))

SAHTE = TESTLER / "sahte_codex.py"
SAHTE_CLAUDE = TESTLER / "sahte_claude.py"
ILK_AUTH = b'{"tokens": "ilk"}'


class SahteCodexTesti(unittest.TestCase):
    def setUp(self):
        self.kok = Path(tempfile.mkdtemp(prefix="orch-test-"))
        self.addCleanup(shutil.rmtree, self.kok, True)
        self.gercek_ev = self.kok / "gercek-codex"
        self.gercek_ev.mkdir()
        self.gercek_auth = self.gercek_ev / "auth.json"
        self.gercek_auth.write_bytes(ILK_AUTH)
        os.chmod(self.gercek_auth, 0o600)
        self.argv_dosyasi = self.kok / "argv.json"
        self.olay_dizini = self.kok / "olaylar"
        ortam = {
            "CODEX_HOME": str(self.gercek_ev),
            "ORCH_CODEX_BIN": str(SAHTE),
            "ORCH_CLAUDE_BIN": str(SAHTE_CLAUDE),
            "SAHTE_CLAUDE_MOD": "normal",
            "ORCH_OLAY_DIZINI": str(self.olay_dizini),
            "SAHTE_ARGV_DOSYASI": str(self.argv_dosyasi),
            "SAHTE_GERCEK_AUTH": str(self.gercek_auth),
            "SAHTE_CODEX_MOD": "normal",
            "CLAUDECODE": "1",
            "CLAUDE_CODE_ENTRYPOINT": "cli",
            # The Claude call runs with the allow-listed environment; variables read by the fake binary are passed explicitly.
            "ORCH_CLAUDE_EK_ORTAM": "SAHTE_ARGV_DOSYASI,SAHTE_CLAUDE_MOD,SAHTE_SON_MESAJ",
        }
        yama = mock.patch.dict(os.environ, ortam)
        yama.start()
        self.addCleanup(yama.stop)

    def mod(self, ad: str, **ek: str) -> None:
        os.environ["SAHTE_CODEX_MOD"] = ad
        os.environ.update(ek)

    def cagri_kaydi(self) -> dict:
        return json.loads(self.argv_dosyasi.read_text(encoding="utf-8"))
