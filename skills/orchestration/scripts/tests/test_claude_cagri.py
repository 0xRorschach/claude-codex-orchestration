import json
import os
from pathlib import Path

from ortak import SAHTE_CLAUDE, SahteCodexTesti

import claude_cagri
import codex_cagri


class ClaudeCagri(SahteCodexTesti):
    SAHTE_CLAUDE = SAHTE_CLAUDE

    def test_kisitli_kip_ve_ayar_kaynagi_yok(self):
        kod, son, _ = claude_cagri.cagir("opus", "medium", "x")
        self.assertEqual(kod, 0)
        argv = self.cagri_kaydi()["argv"]
        self.assertIn("--restricted", argv)
        self.assertNotIn("--setting-sources", argv)
        self.assertNotIn("--bare", argv)
        self.assertIn("--strict-mcp-config", argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "Read,Grep,Glob")

    def test_calisma_dizini_cwd(self):
        hedef = self.kok / "proje"
        hedef.mkdir()
        claude_cagri.cagir("opus", "medium", "x", calisma_dizini=hedef)
        self.assertEqual(Path(self.cagri_kaydi()["cwd"]).resolve(), hedef.resolve())

    def test_ortam_beyaz_liste(self):
        os.environ.update({"CLAUDE_CODE_OAUTH_TOKEN": "fake-token", "ANTHROPIC_API_KEY": "fake-key",
                           "LC_ALL": "en_US.UTF-8", "ORCH_TEST_GIZLI": "must-not-leak", "CLAUDE_CODE_SSE_PORT": "1",
                           "AWS_REGION": "eu-x", "GOOGLE_APPLICATION_CREDENTIALS": "/g.json"})
        os.environ.pop("CLAUDE_CODE_USE_BEDROCK", None)
        os.environ.pop("CLAUDE_CODE_USE_VERTEX", None)
        claude_cagri.cagir("opus", "medium", "x")
        env = self.cagri_kaydi()["env"]
        self.assertEqual(env["CLAUDE_CODE_OAUTH_TOKEN"], "fake-token")
        self.assertEqual(env["ANTHROPIC_API_KEY"], "fake-key")
        self.assertEqual(env["LC_ALL"], "en_US.UTF-8")
        self.assertEqual(env["PATH"], os.environ["PATH"])
        self.assertEqual(env["HOME"], os.environ["HOME"])
        for ad in ("ORCH_TEST_GIZLI", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT",
                   "CODEX_HOME", "AWS_REGION", "GOOGLE_APPLICATION_CREDENTIALS"):
            self.assertIsNone(env[ad], ad)

    def test_bulut_saglayici_degiskenleri_yalniz_bayrakla(self):
        os.environ.update({"CLAUDE_CODE_USE_BEDROCK": "1", "AWS_REGION": "eu-x", "AWS_PROFILE": "p",
                           "CLAUDE_CODE_USE_VERTEX": "1", "GOOGLE_APPLICATION_CREDENTIALS": "/g.json",
                           "CLOUD_ML_REGION": "europe"})
        claude_cagri.cagir("opus", "medium", "x")
        env = self.cagri_kaydi()["env"]
        self.assertEqual((env["CLAUDE_CODE_USE_BEDROCK"], env["AWS_REGION"], env["AWS_PROFILE"]), ("1", "eu-x", "p"))
        self.assertEqual((env["CLAUDE_CODE_USE_VERTEX"], env["GOOGLE_APPLICATION_CREDENTIALS"],
                          env["CLOUD_ML_REGION"]), ("1", "/g.json", "europe"))

    def test_ek_ortam_acikca_gecirilir(self):
        os.environ["SAHTE_EK"] = "e"
        os.environ["ORCH_CLAUDE_EK_ORTAM"] += ", SAHTE_EK"
        claude_cagri.cagir("opus", "medium", "x")
        self.assertEqual(self.cagri_kaydi()["env"]["SAHTE_EK"], "e")

    def test_codex_suzgeci_degismedi(self):
        # The Codex direction keeps its deny-list filter: the user environment (e.g. proxy, non-CODEX_*) passes.
        os.environ["ORCH_TEST_GIZLI"] = "passes-to-codex"
        ortam = codex_cagri.cocuk_ortami()
        self.assertEqual(ortam["ORCH_TEST_GIZLI"], "passes-to-codex")
        self.assertNotIn("CLAUDECODE", ortam)

    def test_claude_bin_ad_path_uzerinden(self):
        # ORCH_CLAUDE_BIN may be a bare name looked up on PATH; a missing name gives KOD_ARAC_YOK
        klasor = self.kok / "bin"
        klasor.mkdir()
        os.symlink(self.SAHTE_CLAUDE, klasor / "my-claude")
        os.environ["PATH"] = str(klasor) + os.pathsep + os.environ.get("PATH", "")
        os.environ["ORCH_CLAUDE_BIN"] = "my-claude"
        kod, _, _ = claude_cagri.cagir("opus", "medium", "x")
        self.assertEqual(kod, 0)
        self.assertTrue(self.argv_dosyasi.exists())
        os.environ["ORCH_CLAUDE_BIN"] = "claude-that-does-not-exist"
        kod, son, _ = claude_cagri.cagir("opus", "medium", "x")
        self.assertEqual(kod, codex_cagri.KOD_ARAC_YOK)
        self.assertIn("ORCH_CLAUDE_BIN", son)

    def test_tam_model_kimligi_init_olayindan(self):
        _, _, akis = claude_cagri.cagir("opus", "medium", "x")
        self.assertEqual(claude_cagri.model_kimligi(akis), "claude-sahte-opus-1")
        bos = self.kok / "bos.jsonl"
        bos.write_text("", encoding="utf-8")
        self.assertIsNone(claude_cagri.model_kimligi(bos))
