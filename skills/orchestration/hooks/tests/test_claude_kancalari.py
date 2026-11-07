"""Tests for the Claude Code-only hooks: agent-tip-kapisi.py (PreToolUse) and paralel-is-hatirlatici.py
(PostToolUse). Both run in a subprocess with HOME and ORCH_LOG_DIR pointing at a temporary directory, so no real
log is touched."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from ortak import baglam, kos  # noqa: E402

KAPI = "agent-tip-kapisi.py"
HATIRLATICI = "paralel-is-hatirlatici.py"


def agent_girdisi(tip=None, model=None, tool_name="Agent", **ek):
    girdi = {"description": "d", "prompt": "p"}
    if tip is not None:
        girdi["subagent_type"] = tip
    if model is not None:
        girdi["model"] = model
    g = {"session_id": "s1", "transcript_path": "/h/.claude/projects/p/s1.jsonl", "cwd": "/h",
         "hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": girdi}
    g.update(ek)
    return g


class TempOrtam(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.kok = Path(self.tmp.name)
        self.log_dizini = self.kok / "logs"
        self.env = {"HOME": str(self.kok), "ORCH_LOG_DIR": str(self.log_dizini)}

    def tearDown(self):
        self.tmp.cleanup()


class AgentTipKapisi(TempOrtam):
    def k(self, girdi):
        p = kos(KAPI, girdi, self.env)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p

    def karar(self, p):
        if not p.stdout.strip():
            return None
        cikti = json.loads(p.stdout)["hookSpecificOutput"]
        self.assertEqual(cikti["hookEventName"], "PreToolUse")
        return cikti

    def test_yasak_tipler_reddedilir(self):
        for tip in ("general-purpose", "Explore", "Plan", "claude", "fork", ""):
            with self.subTest(tip=tip):
                c = self.karar(self.k(agent_girdisi(tip)))
                self.assertIsNotNone(c, tip)
                self.assertEqual(c["permissionDecision"], "deny")
                self.assertIn("is closed", c["permissionDecisionReason"])

    def test_eklenti_onekli_tip_son_parcaya_gore(self):
        for tip in ("orchestration:explorer", "orchestration:scanner", "orchestration:worker"):
            with self.subTest(tip=tip):
                self.assertEqual(self.k(agent_girdisi(tip)).stdout, "")
        for tip in ("x:general-purpose", "orchestration:Explore", "x:fork"):
            with self.subTest(tip=tip):
                c = self.karar(self.k(agent_girdisi(tip)))
                self.assertEqual(c["permissionDecision"], "deny")
                self.assertIn("`%s`" % tip, c["permissionDecisionReason"])

    def test_tip_yoksa_general_purpose_sayilir(self):
        c = self.karar(self.k(agent_girdisi()))
        self.assertEqual(c["permissionDecision"], "deny")
        self.assertIn("empty -> general-purpose", c["permissionDecisionReason"])

    def test_opus_disi_model_reddedilir(self):
        for model in ("sonnet", "haiku", "Sonnet "):
            with self.subTest(model=model):
                c = self.karar(self.k(agent_girdisi("explorer", model=model)))
                self.assertEqual(c["permissionDecision"], "deny")
                self.assertIn("`model: %s`" % model.strip().lower(), c["permissionDecisionReason"])

    def test_izinli_tipler_gecer(self):
        for tip in ("explorer", "worker", "researcher", "scanner"):
            with self.subTest(tip=tip):
                self.assertEqual(self.k(agent_girdisi(tip)).stdout, "")

    def test_opus_modeli_gecer(self):
        self.assertEqual(self.k(agent_girdisi("worker", model="opus")).stdout, "")

    def test_tam_opus_kimligi_gecer(self):
        for model in ("claude-opus-4-1", "Claude-Opus-5-5", " claude-opus-4-1-20250805 "):
            with self.subTest(model=model):
                self.assertEqual(self.k(agent_girdisi("worker", model=model)).stdout, "")

    def test_opus_benzeri_ama_tam_kimlik_olmayan_reddedilir(self):
        for model in ("claude-opus", "claude-sonnet-4-5", "opus-mini", "claude-haiku-4-5", "anthropic/claude-opus-4"):
            with self.subTest(model=model):
                c = self.karar(self.k(agent_girdisi("worker", model=model)))
                self.assertEqual(c["permissionDecision"], "deny")

    def test_ret_mesaji_kapatmayi_soyler(self):
        for girdi in (agent_girdisi("general-purpose"), agent_girdisi("worker", model="sonnet")):
            with self.subTest(girdi=girdi["tool_input"]):
                neden = self.karar(self.k(girdi))["permissionDecisionReason"]
                self.assertTrue(neden.endswith("set ORCH_TIP_KAPISI=0 in the environment Claude Code runs in."), neden)

    def test_kapatma_anahtari(self):
        env = dict(self.env, ORCH_TIP_KAPISI="0")
        for girdi in (agent_girdisi("general-purpose"), agent_girdisi("worker", model="haiku"), agent_girdisi()):
            with self.subTest(girdi=girdi["tool_input"]):
                p = kos(KAPI, girdi, env)
                self.assertEqual((p.returncode, p.stdout), (0, ""), p.stderr)
        self.assertFalse(self.log_dizini.exists(), "a disabled gate must not log")
        # any other value keeps the gate on
        for deger in ("1", "", "no"):
            with self.subTest(deger=deger):
                c = self.karar(kos(KAPI, agent_girdisi("fork"), dict(self.env, ORCH_TIP_KAPISI=deger)))
                self.assertEqual(c["permissionDecision"], "deny")

    def test_eklenti_ajan_tipleri_gecer(self):
        # plugin and narrow-purpose agent types are deliberately left alone
        for tip in ("claude-code-guide", "statusline-setup", "someplugin:reviewer"):
            with self.subTest(tip=tip):
                self.assertEqual(self.k(agent_girdisi(tip)).stdout, "")

    def test_task_araci_da_denetlenir(self):
        c = self.karar(self.k(agent_girdisi("general-purpose", tool_name="Task")))
        self.assertEqual(c["permissionDecision"], "deny")

    def test_agent_disi_arac_gecer(self):
        g = {"session_id": "s1", "hook_event_name": "PreToolUse", "tool_name": "Bash",
             "tool_input": {"command": "ls", "subagent_type": "general-purpose", "model": "sonnet"}}
        self.assertEqual(self.k(g).stdout, "")

    def test_bozuk_stdin_sessiz(self):
        p = kos(KAPI, None, self.env, ham_girdi="broken")
        self.assertEqual((p.returncode, p.stdout), (0, ""))

    def test_ret_gunlugu_gecici_dizine_yazilir(self):
        self.k(agent_girdisi("general-purpose"))
        satirlar = (self.log_dizini / "ret.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(satirlar), 1)
        kayit = json.loads(satirlar[0])
        self.assertEqual(kayit["subagent_type"], "general-purpose")
        self.assertNotIn("prompt", kayit)
        self.assertFalse((self.kok / ".local").exists(), "the default log path must not be used")

    def test_ret_mesajinda_kural_kitabi_yolu(self):
        # without CLAUDE_PLUGIN_ROOT: derived from the script location (<skill>/hooks/.. -> <skill>/SKILL.md)
        beklenen = str(Path(__file__).resolve().parent.parent.parent / "SKILL.md")
        c = self.karar(self.k(agent_girdisi("general-purpose")))
        self.assertIn("Rule book: " + beklenen, c["permissionDecisionReason"])
        self.assertNotIn(".agents", c["permissionDecisionReason"])
        # with CLAUDE_PLUGIN_ROOT: plugin layout, for both denial kinds
        env = dict(self.env, CLAUDE_PLUGIN_ROOT=str(self.kok / "eklenti"))
        for girdi in (agent_girdisi("Explore"), agent_girdisi("worker", model="sonnet")):
            with self.subTest(girdi=girdi["tool_input"]):
                c = self.karar(kos(KAPI, girdi, env))
                self.assertIn("Rule book: " + str(self.kok / "eklenti" / "skills" / "orchestration" / "SKILL.md"),
                              c["permissionDecisionReason"])

    def test_eklenti_veri_dizinine_gunluk(self):
        veri = self.kok / "veri"
        env = {"HOME": str(self.kok), "CLAUDE_PLUGIN_DATA": str(veri)}
        self.assertEqual(kos(KAPI, agent_girdisi("fork"), env).returncode, 0)
        self.assertTrue((veri / "ret.jsonl").is_file())
        env = {"HOME": str(self.kok), "PLUGIN_DATA": str(self.kok / "veri2")}
        kos(KAPI, agent_girdisi("fork"), env)
        self.assertTrue((self.kok / "veri2" / "ret.jsonl").is_file())
        self.assertFalse((self.kok / ".local").exists())

    def test_kabul_gunluge_yazilmaz(self):
        self.k(agent_girdisi("explorer"))
        self.assertFalse(self.log_dizini.exists())


class ParalelIsHatirlatici(TempOrtam):
    def k(self, girdi, env=None):
        p = kos(HATIRLATICI, girdi, env or self.env)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p

    def girdi(self, **ek):
        g = {"session_id": "s1", "transcript_path": "/h/.claude/projects/p/s1.jsonl", "cwd": "/h",
             "hook_event_name": "PostToolUse", "tool_name": "Agent",
             "tool_input": {"subagent_type": "worker", "prompt": "p"}, "tool_response": {"content": "ok"}}
        g.update(ek)
        return g

    def test_ana_oturumda_baglam_ekler(self):
        p = self.k(self.girdi())
        self.assertEqual(json.loads(p.stdout)["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        metin = baglam(p)
        self.assertIn("[parallel-work hook]", metin)
        self.assertIn("threshold: 15 concurrent, default 15, configurable", metin)

    def test_alt_ajanda_susar(self):
        p = self.k(self.girdi(agent_id="ag1", agent_type="worker"))
        self.assertEqual(p.stdout, "")
        self.assertFalse(self.log_dizini.exists())

    def test_esik_ortamdan_ayarlanir(self):
        p = self.k(self.girdi(), dict(self.env, ORCH_PARALEL_ESIK="6"))
        self.assertIn("threshold: 6 concurrent", baglam(p))

    def test_gecersiz_esik_varsayilana_doner(self):
        for deger in ("abc", "0", "-3"):
            with self.subTest(deger=deger):
                p = self.k(self.girdi(), dict(self.env, ORCH_PARALEL_ESIK=deger))
                self.assertIn("threshold: 15 concurrent", baglam(p))

    def test_gunluk_gecici_dizine_yazilir(self):
        self.k(self.girdi())
        satirlar = (self.log_dizini / "paralel-is-hatirlatici.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(satirlar), 1)
        self.assertEqual(satirlar[0].split("\t")[1:], ["s1", "Agent"])
        self.assertFalse((self.kok / ".claude").exists(), "the default log path must not be used")

    def test_varsayilan_gunluk_yolu_home_altinda(self):
        env = {"HOME": str(self.kok)}
        self.k(self.girdi(), env)
        self.assertTrue((self.kok / ".claude" / "hooks" / "paralel-is-hatirlatici.log").is_file())

    def test_eklenti_veri_dizinine_gunluk(self):
        veri = self.kok / "veri"
        self.k(self.girdi(), {"HOME": str(self.kok), "CLAUDE_PLUGIN_DATA": str(veri)})
        self.assertTrue((veri / "paralel-is-hatirlatici.log").is_file())
        self.assertFalse((self.kok / ".claude").exists())
        # ORCH_LOG_DIR wins over the plugin data folder
        self.k(self.girdi(), dict(self.env, CLAUDE_PLUGIN_DATA=str(veri)))
        self.assertTrue((self.log_dizini / "paralel-is-hatirlatici.log").is_file())

    def test_kapatma_anahtari(self):
        p = self.k(self.girdi(), dict(self.env, ORCH_PARALEL_HATIRLATICI="0"))
        self.assertEqual(p.stdout, "")
        self.assertFalse(self.log_dizini.exists(), "a disabled reminder must not log")
        self.assertIn("[parallel-work hook]", baglam(self.k(self.girdi(), dict(self.env, ORCH_PARALEL_HATIRLATICI="1"))))

    def test_bozuk_stdin_sessiz(self):
        p = kos(HATIRLATICI, None, self.env, ham_girdi="")
        self.assertEqual((p.returncode, p.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
