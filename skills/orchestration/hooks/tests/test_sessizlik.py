"""Checks that the hooks exit silently with 0 on every path: closed stdout (B2), missing helper module (B3)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from ortak import ATILAN, KANCA_DIZINI  # noqa: E402


def uyari_ureten_girdi():
    return json.dumps({"session_id": "s", "transcript_path": "/h/.claude/projects/p/s.jsonl", "cwd": "/h",
                       "hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "cat a"},
                       "tool_response": {"stdout": "x" * 5000, "stderr": ""}})


class Sessizlik(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.kok = Path(self.tmp.name)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("ORCH_") and k not in ATILAN}
        self.env.update({"HOME": str(self.kok), "XDG_CACHE_HOME": str(self.kok / "cache"),
                         "ORCH_OKUMA_ESIGI": "1000"})

    def tearDown(self):
        self.tmp.cleanup()

    def kapali_borulu_kos(self, betik, girdi, argumanlar=()):
        """stdout is a pipe whose read end is closed: writes raise EPIPE/BrokenPipeError (smoke test B2: exit 120)."""
        oku, yaz = os.pipe()
        os.close(oku)
        try:
            p = subprocess.run([sys.executable, str(betik)] + list(argumanlar), input=girdi.encode(),
                               stdout=yaz, stderr=subprocess.PIPE, env=self.env, timeout=30)
        finally:
            os.close(yaz)
        return p

    def test_okuma_butcesi_kapali_boruda_exit_0(self):
        p = self.kapali_borulu_kos(KANCA_DIZINI / "okuma_butcesi.py", uyari_ureten_girdi(), ("claude",))
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_okuma_butcesi_kapali_fd_ile_exit_0(self):
        p = subprocess.run([sys.executable, str(KANCA_DIZINI / "okuma_butcesi.py"), "claude"],
                           input=uyari_ureten_girdi().encode(), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                           env=self.env, timeout=30, preexec_fn=lambda: os.close(1))
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_surum_bekcisi_kapali_boruda_exit_0(self):
        plugins = self.kok / "plugins"
        plugins.mkdir()
        (plugins / "installed_plugins.json").write_text(json.dumps(
            {"plugins": {"superpowers@p": [{"version": "9.9.9"}]}}))
        tablo = self.kok / "tablo.json"
        tablo.write_text(json.dumps({"tablo_surumu": "7.0.0"}))
        self.env.update({"ORCH_PLUGINS_DIR": str(plugins), "ORCH_SURUM_TABLOSU": str(tablo)})
        p = self.kapali_borulu_kos(KANCA_DIZINI / "superpowers_surum_bekcisi.py",
                                   json.dumps({"session_id": "s", "hook_event_name": "SessionStart"}), ("claude",))
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_yardimci_modul_yoksa_exit_0_sessiz(self):
        # B3: if `import kanca_girdisi` is outside the try, the ImportError exits 1.
        for ad in ("okuma_butcesi.py", "superpowers_surum_bekcisi.py", "orkestrasyon_hatirlatici.py"):
            with self.subTest(kanca=ad):
                yalniz = self.kok / ("yalniz-" + ad.split(".")[0])
                yalniz.mkdir()
                shutil.copy(KANCA_DIZINI / ad, yalniz / ad)
                p = subprocess.run([sys.executable, str(yalniz / ad), "claude"], input=uyari_ureten_girdi(),
                                   capture_output=True, text=True, env=self.env, timeout=30)
                self.assertEqual((p.returncode, p.stdout), (0, ""), p.stderr)


if __name__ == "__main__":
    unittest.main()
