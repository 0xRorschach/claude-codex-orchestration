"""Tests with Codex input samples. Field names come from the learn.chatgpt.com/docs/hooks tables; the transcript
header format was measured from codex-cli 0.166.0 rollout files."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from ortak import baglam, kos  # noqa: E402


def codex_bash(cikti, komut="cat src/a.py", sid="019a-ana", dokum="", **ek):
    g = {"session_id": sid, "transcript_path": dokum, "cwd": "/h", "hook_event_name": "PostToolUse",
         "model": "gpt-x", "permission_mode": "default", "turn_id": "t1", "tool_name": "Bash",
         "tool_use_id": "call_1", "tool_input": {"command": komut}, "tool_response": cikti}
    g.update(ek)
    return g


class CodexOkumaButcesi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.kok = Path(self.tmp.name)
        self.env = {"HOME": str(self.kok), "XDG_CACHE_HOME": str(self.kok / "cache"), "ORCH_OKUMA_ESIGI": "1000"}

    def tearDown(self):
        self.tmp.cleanup()

    def dokum(self, ad, payload):
        yol = self.kok / ad
        yol.write_text(json.dumps({"type": "session_meta", "payload": payload}) + "\n{\"type\":\"x\"}\n")
        return str(yol)

    def k(self, girdi, argumanlar=("codex",)):
        p = kos("okuma_butcesi.py", girdi, self.env, argumanlar=argumanlar)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p

    def ana_dokum(self):
        return self.dokum("ana.jsonl", {"id": "019a-ana", "source": "cli"})

    def test_metin_yanit_esik_ustu(self):
        p = self.k(codex_bash("x" * 1500, dokum=self.ana_dokum()))
        self.assertIn("~2k", baglam(p))
        self.assertEqual(json.loads(p.stdout)["hookSpecificOutput"]["hookEventName"], "PostToolUse")

    def test_kabuk_metni_oldugu_gibi_sayilir(self):
        # Codex shell output is plain text: counted as is, not through the Claude Code field allowlist.
        self.k(codex_bash("x" * 700, dokum=self.ana_dokum()))
        durum = json.loads((self.kok / "cache" / "orchestration" / "okuma" / "019a-ana.json").read_text())
        self.assertEqual(durum["toplam"], 700)

    def test_arguman_olmadan_turn_id_ile_codex(self):
        ana = self.dokum("ana.jsonl", {"id": "019a-ana", "source": "cli"})
        self.assertIsNotNone(baglam(self.k(codex_bash("x" * 1500, dokum=ana), argumanlar=())))

    def test_ana_dokum_sayilir(self):
        ana = self.dokum("ana.jsonl", {"id": "019a-ana", "session_id": "019a-ana", "source": "vscode"})
        self.assertIsNotNone(baglam(self.k(codex_bash("x" * 1500, dokum=ana))))

    def test_alt_ajan_dokumu_sessiz(self):
        alt = self.dokum("alt.jsonl", {"id": "019b", "session_id": "019a-ana",
                                       "source": {"subagent": {"other": "guardian"}},
                                       "parent_thread_id": "019a-ana"})
        self.assertEqual(self.k(codex_bash("x" * 5000, dokum=alt)).stdout, "")

    def test_parent_thread_id_tek_basina_yeter(self):
        alt = self.dokum("alt2.jsonl", {"id": "019c", "source": "exec", "parent_thread_id": "019a-ana"})
        self.assertEqual(self.k(codex_bash("x" * 5000, dokum=alt)).stdout, "")

    def test_agent_id_gelirse_sessiz(self):
        self.assertEqual(self.k(codex_bash("x" * 5000, agent_id="a1")).stdout, "")

    def test_belirsiz_dokum_sayilmaz(self):
        # B4: if the transcript is unreadable, empty or its header is not session_meta, main/sub is undetermined: not counted, silent.
        bozuk = self.kok / "bozuk.jsonl"
        bozuk.write_text("{broken\n")
        basliksiz = self.kok / "headerless.jsonl"
        basliksiz.write_text(json.dumps({"type": "event_msg", "payload": {}}) + "\n")
        for dokum in (str(self.kok / "missing.jsonl"), "", str(bozuk), str(basliksiz)):
            with self.subTest(dokum=dokum):
                self.assertEqual(self.k(codex_bash("x" * 5000, dokum=dokum, sid="b" + str(len(dokum)))).stdout, "")
        self.assertFalse(any((self.kok / "cache").rglob("*.json")), "an undetermined call must not write a state file")

    def test_codex_muaf_komut(self):
        self.assertEqual(self.k(codex_bash("x" * 5000, komut="codex exec 'review'", dokum=self.ana_dokum())).stdout,
                         "")

    def test_apply_patch_sayilmaz(self):
        self.assertEqual(self.k(codex_bash("x" * 5000, tool_name="apply_patch")).stdout, "")


class CodexSurumBekcisi(unittest.TestCase):
    GIRDI = {"session_id": "s", "transcript_path": "", "cwd": "/h", "hook_event_name": "SessionStart",
             "model": "gpt-x", "source": "startup"}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.kok = Path(self.tmp.name)
        self.codex = self.kok / "codex"
        self.tablo = self.kok / "tablo.json"
        self.tablo.write_text(json.dumps({"tablo_surumu": "7.0.0"}))
        self.env = {"HOME": str(self.kok), "CODEX_HOME": str(self.codex), "ORCH_SURUM_TABLOSU": str(self.tablo)}

    def tearDown(self):
        self.tmp.cleanup()

    def kur(self, pazar, klasor, manifest_surumu=None):
        yol = self.codex / "plugins" / "cache" / pazar / "superpowers" / klasor
        (yol / ".codex-plugin").mkdir(parents=True)
        if manifest_surumu:
            (yol / ".codex-plugin" / "plugin.json").write_text(json.dumps({"version": manifest_surumu}))

    def k(self):
        p = kos("superpowers_surum_bekcisi.py", self.GIRDI, self.env, argumanlar=("codex",))
        self.assertEqual(p.returncode, 0, p.stderr)
        return p

    def test_ayni_sessiz(self):
        self.kur("pazar", "7.0.0", "7.0.0")
        self.assertEqual(self.k().stdout, "")

    @unittest.skipIf(sys.version_info < (3, 11), "the Codex branch needs tomllib (3.11+); silent on older")
    def test_farkli_uyari(self):
        self.kur("pazar", "7.2.0", "7.2.0")
        self.assertEqual(baglam(self.k()), "superpowers 7.2.0 is installed, but the orchestration mapping table was "
                                           "written for 7.0.0: re-check the table (orchestration > With superpowers)")

    @unittest.skipIf(sys.version_info < (3, 11), "the Codex branch needs tomllib (3.11+); silent on older")
    def test_manifest_yoksa_klasor_adi(self):
        self.kur("pazar", "7.3.1")
        self.assertIn("superpowers 7.3.1 is installed", baglam(self.k()))

    def test_kapali_pazar_sayilmaz(self):
        self.kur("a", "9.0.0", "9.0.0")
        self.kur("b", "7.0.0", "7.0.0")
        self.codex.joinpath("config.toml").write_text(
            '[plugins."superpowers@a"]\nenabled = false\n\n[plugins."superpowers@b"]\nenabled = true\n')
        self.assertEqual(self.k().stdout, "")

    def test_tomllib_yoksa_codex_dali_sessiz(self):
        # Python 3.10 and older have no tomllib: the disabled-marketplace filter cannot run, so stay silent rather
        # than give a false warning. On 3.11+ the same situation is built by putting a fake tomllib on PYTHONPATH.
        self.kur("pazar", "9.0.0", "9.0.0")
        golge = self.kok / "golge"
        golge.mkdir()
        (golge / "tomllib.py").write_text("raise ImportError('test: no tomllib')\n")
        self.env["PYTHONPATH"] = str(golge)
        self.assertEqual(self.k().stdout, "")

    def test_kurulum_yok_sessiz(self):
        p = self.k()
        self.assertEqual((p.stdout, p.stderr), ("", ""))


if __name__ == "__main__":
    unittest.main()
