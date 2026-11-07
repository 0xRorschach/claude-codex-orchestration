import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from ortak import baglam, kos  # noqa: E402

BETIK = "superpowers_surum_bekcisi.py"
GIRDI = {"session_id": "s1", "hook_event_name": "SessionStart", "source": "startup"}


class SurumBekcisi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.kok = Path(self.tmp.name)
        self.plugins = self.kok / "plugins"
        self.plugins.mkdir()
        self.tablo = self.kok / "tablo.json"
        self.tablo.write_text(json.dumps({"tablo_surumu": "7.0.0", "tarih": "2026-11-07"}))
        self.env = {"HOME": str(self.kok), "ORCH_PLUGINS_DIR": str(self.plugins),
                    "ORCH_SURUM_TABLOSU": str(self.tablo)}

    def tearDown(self):
        self.tmp.cleanup()

    def kurulu(self, girdiler):
        (self.plugins / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": girdiler}))

    def test_ayni_surum_sessiz(self):
        self.kurulu({"superpowers@pazar": [{"version": "7.0.0", "installPath": "/x"}]})
        p = kos(BETIK, GIRDI, self.env)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "")

    def test_farkli_surum_uyari(self):
        self.kurulu({"superpowers@pazar": [{"version": "7.1.0", "installPath": "/x"}]})
        p = kos(BETIK, GIRDI, self.env)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(baglam(p), "superpowers 7.1.0 is installed, but the orchestration mapping table was written "
                                    "for 7.0.0: re-check the table (orchestration > With superpowers)")
        self.assertEqual(json.loads(p.stdout)["hookSpecificOutput"]["hookEventName"], "SessionStart")

    def test_birden_cok_kurulumda_en_yeni(self):
        self.kurulu({"superpowers@a": [{"version": "6.9.0"}, {"version": "7.0.10"}],
                     "superpowers@b": [{"version": "7.0.2"}]})
        p = kos(BETIK, GIRDI, self.env)
        self.assertIn("superpowers 7.0.10 is installed", baglam(p))

    def test_devre_disi_kurulum_sayilmaz(self):
        # an install set to false in settings.json > enabledPlugins is ignored.
        self.kurulu({"superpowers@a": [{"version": "9.0.0"}], "superpowers@b": [{"version": "7.0.0"}]})
        (self.kok / ".claude").mkdir()
        (self.kok / ".claude" / "settings.json").write_text(json.dumps(
            {"enabledPlugins": {"superpowers@a": False, "superpowers@b": True}}))
        p = kos(BETIK, GIRDI, self.env)
        self.assertEqual(p.stdout, "")

    def test_surum_alani_yoksa_manifestten(self):
        yol = self.kok / "kurulum"
        (yol / ".claude-plugin").mkdir(parents=True)
        (yol / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "superpowers", "version": "8.0.0"}))
        self.kurulu({"superpowers@pazar": [{"installPath": str(yol)}]})
        p = kos(BETIK, GIRDI, self.env)
        self.assertIn("superpowers 8.0.0 is installed", baglam(p))

    def test_kurulum_dosyasi_yok_sessiz(self):
        p = kos(BETIK, GIRDI, self.env)
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))

    def test_superpowers_kurulu_degilse_sessiz(self):
        # plain HOME with no plugin folder at all, default paths, plugin-mode variables set: silent, exit 0
        env = {"HOME": str(self.kok / "bos-ev"), "CLAUDE_PLUGIN_ROOT": str(self.kok / "eklenti"),
               "CLAUDE_PLUGIN_DATA": str(self.kok / "veri")}
        for arac in ("claude", "codex"):
            with self.subTest(arac=arac):
                p = kos(BETIK, GIRDI, env, argumanlar=(arac,))
                self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))

    def test_bozuk_json_sessiz(self):
        (self.plugins / "installed_plugins.json").write_text("{broken")
        p = kos(BETIK, GIRDI, self.env)
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))

    def test_tablo_yok_sessiz(self):
        self.kurulu({"superpowers@pazar": [{"version": "7.1.0"}]})
        self.tablo.unlink()
        p = kos(BETIK, GIRDI, self.env)
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))

    def test_sayisal_olmayan_surum_sessiz(self):
        self.kurulu({"superpowers@pazar": [{"version": "7.1.0-beta"}]})
        p = kos(BETIK, GIRDI, self.env)
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))

    def test_bozuk_stdin_sessiz(self):
        self.kurulu({"superpowers@pazar": [{"version": "7.1.0"}]})
        p = kos(BETIK, None, self.env, ham_girdi="")
        self.assertEqual(p.returncode, 0)

    def test_kapatma_degiskeni(self):
        self.kurulu({"superpowers@pazar": [{"version": "7.1.0"}]})
        p = kos(BETIK, GIRDI, dict(self.env, ORCH_SURUM_BEKCISI="0"))
        self.assertEqual((p.returncode, p.stdout), (0, ""))

    def test_varsayilan_tablo_dosyasi_okunur(self):
        # without ORCH_SURUM_TABLOSU the superpowers_surum.json next to the script is read.
        self.kurulu({"superpowers@pazar": [{"version": "1.0.0"}]})
        env = dict(self.env)
        del env["ORCH_SURUM_TABLOSU"]
        p = kos(BETIK, GIRDI, env)
        self.assertIn("table was written for 7.0.0", baglam(p))


if __name__ == "__main__":
    unittest.main()
