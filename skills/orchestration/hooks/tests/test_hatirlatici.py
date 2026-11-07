"""Tests for orkestrasyon_hatirlatici.py. Claude Code transcript lines follow the shape of real transcripts under
~/.claude/projects (Skill tool_use, the "Base directory for this skill" injection); Codex lines follow codex-cli 0.166.0
rollout files (SKILL.md read inside a custom_tool_call exec, the <skill> injection, the world_state skill list)."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from ortak import ATILAN, KANCA_DIZINI, baglam, kos  # noqa: E402

BETIK = "orkestrasyon_hatirlatici.py"
METIN = "The orchestration skill was not loaded in this session"


def satir(nesne):
    return json.dumps(nesne, ensure_ascii=False, separators=(",", ":"))


CLAUDE_DUZ = [
    satir({"type": "user", "message": {"role": "user", "content": "hello"}}),
    # The CLAUDE.md injection carries the word orchestration and the prose "(Skill: orchestration)": not a load.
    satir({"type": "attachment", "content": "In multi-step work, first load the `orchestration` skill "
                                            "(Skill: orchestration). No Base directory for this skill text."}),
    satir({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Skill", "input": {"skill": "superpowers:brainstorming"}}]}}),
]
CLAUDE_SKILL = satir({"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Skill", "input": {"skill": "orchestration"}}]}})
CLAUDE_ENJEKSIYON = satir({"type": "user", "isMeta": True, "message": {"role": "user", "content": [
    {"type": "text", "text": "Base directory for this skill: /h/.claude/skills/orchestration\n\n# Orchestration"}]}})
# A Skill call quoted in an Agent brief: nested escaped text, not a load.
CLAUDE_ALINTI = satir({"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Agent", "input": {"prompt": 'search for: {"skill":"orchestration"}'}}]}})

CODEX_DUZ = [
    satir({"type": "session_meta", "payload": {"id": "019a-ana", "source": "cli"}}),
    satir({"type": "world_state", "payload": {"skills": [["host", "host", "/h/.agents/skills/orchestration/SKILL.md"]]}}),
]
CODEX_OKUMA = satir({"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec",
                                                          "input": 'text(await tools.exec_command({cmd:"cat '
                                                                   '/h/.codex/skills/orchestration/SKILL.md"}))'}})
CODEX_ENJEKSIYON = satir({"type": "response_item", "payload": {"type": "message", "role": "user", "content": [
    {"type": "input_text", "text": "<skill>\n<name>orchestration</name>\n<path>/h/SKILL.md</path>"}]}})


class Hatirlatici(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.kok = Path(self.tmp.name)
        self.cache = self.kok / "cache"
        self.env = {"HOME": str(self.kok), "XDG_CACHE_HOME": str(self.cache)}
        self.sayac = 0

    def tearDown(self):
        self.tmp.cleanup()

    def temiz_env(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("ORCH_") and k not in ATILAN}
        env.update(self.env)
        return env

    def dokum(self, satirlar, ad=None):
        self.sayac += 1
        yol = self.kok / (ad or "d%d.jsonl" % self.sayac)
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
        return str(yol)

    def claude(self, dokum, sid="s1", arac="Agent", **ek):
        g = {"session_id": sid, "transcript_path": dokum, "cwd": "/h", "hook_event_name": "PreToolUse",
             "tool_name": arac, "tool_input": {"subagent_type": "worker", "prompt": "x"}, "tool_use_id": "t"}
        g.update(ek)
        return g

    def codex(self, dokum, sid="019a-ana", arac="spawn_agent", **ek):
        g = {"session_id": sid, "transcript_path": dokum, "cwd": "/h", "hook_event_name": "PreToolUse",
             "model": "gpt-x", "permission_mode": "default", "turn_id": "t1", "tool_name": arac,
             "tool_use_id": "call_1", "tool_input": {"message": "x"}}
        g.update(ek)
        return g

    def k(self, girdi, argumanlar=("claude",), env_ek=None, ham=None):
        env = dict(self.env)
        env.update(env_ek or {})
        p = kos(BETIK, girdi, env, ham_girdi=ham, argumanlar=argumanlar)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stderr, "")
        return p

    # Claude Code
    def test_claude_yuklenmemis_uyarir(self):
        p = self.k(self.claude(self.dokum(CLAUDE_DUZ)))
        self.assertIn(METIN, baglam(p))
        cikti = json.loads(p.stdout)["hookSpecificOutput"]
        self.assertEqual(cikti["hookEventName"], "PreToolUse")
        self.assertNotIn("permissionDecision", cikti)

    def test_claude_task_adi_da_uyarir(self):
        self.assertIn(METIN, baglam(self.k(self.claude(self.dokum(CLAUDE_DUZ), arac="Task"))))

    def test_claude_skill_cagrisi_sessiz(self):
        self.assertEqual(self.k(self.claude(self.dokum(CLAUDE_DUZ + [CLAUDE_SKILL]))).stdout, "")

    def test_claude_eklenti_onekli_skill_sessiz(self):
        s = CLAUDE_SKILL.replace('"orchestration"', '"pazar:orchestration"')
        self.assertEqual(self.k(self.claude(self.dokum(CLAUDE_DUZ + [s]))).stdout, "")

    def test_claude_eklenti_skill_adi_sessiz(self):
        # A plugin install shows the skill as `orchestration:orchestration`.
        s = CLAUDE_SKILL.replace('"orchestration"', '"orchestration:orchestration"')
        self.assertEqual(self.k(self.claude(self.dokum(CLAUDE_DUZ + [s]))).stdout, "")

    def test_claude_eklenti_slash_komutu_sessiz(self):
        s = satir({"type": "user", "message": {"content": "<command-name>/orchestration:orchestration</command-name>"}})
        self.assertEqual(self.k(self.claude(self.dokum(CLAUDE_DUZ + [s]))).stdout, "")

    def test_benzer_eklenti_adi_uyarir(self):
        s = CLAUDE_SKILL.replace('"orchestration"', '"orchestration:orchestration-old"')
        self.assertIn(METIN, baglam(self.k(self.claude(self.dokum(CLAUDE_DUZ + [s])))))

    def test_claude_enjeksiyon_sessiz(self):
        self.assertEqual(self.k(self.claude(self.dokum(CLAUDE_DUZ + [CLAUDE_ENJEKSIYON]))).stdout, "")

    def test_claude_slash_komutu_sessiz(self):
        s = satir({"type": "user", "message": {"content": "<command-name>/orchestration</command-name>"}})
        self.assertEqual(self.k(self.claude(self.dokum(CLAUDE_DUZ + [s]))).stdout, "")

    def test_yanlis_pozitifler_uyarir(self):
        benzer = CLAUDE_ENJEKSIYON.replace("skills/orchestration", "skills/orchestration-eski")
        for ad, ek in (("alinti", CLAUDE_ALINTI), ("benzer_ad", benzer)):
            with self.subTest(ad=ad):
                self.assertIn(METIN, baglam(self.k(self.claude(self.dokum(CLAUDE_DUZ + [ek]), sid="fp" + ad))))

    def test_alt_ajan_sessiz(self):
        d = self.dokum(CLAUDE_DUZ)
        self.assertEqual(self.k(self.claude(d, agent_id="a1")).stdout, "")
        alt = self.dokum(CLAUDE_DUZ, ad="p/s2/subagents/agent-1.jsonl")
        self.assertEqual(self.k(self.claude(alt, sid="s2")).stdout, "")
        self.assertFalse(self.cache.exists() and any(self.cache.rglob("*")), "a subagent must not write state")

    def test_ikinci_cagri_sessiz(self):
        d = self.dokum(CLAUDE_DUZ)
        self.assertIsNotNone(baglam(self.k(self.claude(d))))
        self.assertEqual(self.k(self.claude(d)).stdout, "")

    def test_yuklu_dalda_ikinci_cagri_taramaz(self):
        d = self.dokum(CLAUDE_DUZ + [CLAUDE_SKILL])
        self.assertEqual(self.k(self.claude(d)).stdout, "")
        Path(d).unlink()  # if the state file is read, the missing transcript makes no difference
        self.assertEqual(self.k(self.claude(d)).stdout, "")
        self.assertEqual((self.cache / "orchestration" / "hatirlatici" / "s1").read_text(), "yuklu")

    def test_paralel_cagrilarda_tek_uyari(self):
        d = self.dokum(CLAUDE_DUZ)
        girdi = json.dumps(self.claude(d, sid="par"))
        env = {k: v for k, v in os.environ.items() if not k.startswith("ORCH_") and k not in ATILAN}
        env.update(self.env)
        sureler = [subprocess.Popen([sys.executable, str(KANCA_DIZINI / BETIK), "claude"], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env) for _ in range(6)]
        ciktilar = [s.communicate(girdi.encode(), timeout=30)[0] for s in sureler]
        self.assertEqual(sum(1 for c in ciktilar if c.strip()), 1)

    def test_kapatma(self):
        p = self.k(self.claude(self.dokum(CLAUDE_DUZ)), env_ek={"ORCH_HATIRLATICI": "0"})
        self.assertEqual(p.stdout, "")

    def test_baska_arac_sessiz(self):
        self.assertEqual(self.k(self.claude(self.dokum(CLAUDE_DUZ), arac="Bash")).stdout, "")

    def test_bozuk_girdi_sessiz(self):
        for ham in ("", "{bozuk", "[]", "null", json.dumps({"tool_name": "Agent"})):
            with self.subTest(ham=ham):
                self.assertEqual(self.k(None, ham=ham).stdout, "")

    def test_okunamayan_dokum_sessiz_ve_yeniden_dener(self):
        yok = str(self.kok / "yok.jsonl")
        self.assertEqual(self.k(self.claude(yok, sid="r")).stdout, "")
        Path(yok).write_text("\n".join(CLAUDE_DUZ) + "\n", encoding="utf-8")
        self.assertIn(METIN, baglam(self.k(self.claude(yok, sid="r"))))

    def test_eski_durum_dosyasi_temizlenir(self):
        dizin = self.cache / "orchestration" / "hatirlatici"
        dizin.mkdir(parents=True)
        eski = dizin / "eski"
        eski.write_text("uyarildi")
        t = time.time() - 8 * 86400
        os.utime(eski, (t, t))
        self.k(self.claude(self.dokum(CLAUDE_DUZ)))
        self.assertFalse(eski.exists())

    def test_durum_dizini_sirasi(self):
        # Same order as the other hooks: ORCH_LOG_DIR, then CLAUDE_PLUGIN_DATA, then PLUGIN_DATA, then the XDG cache.
        log, cpd, pd = self.kok / "log", self.kok / "cpd", self.kok / "pd"
        durumlar = (
            ("log", {"ORCH_LOG_DIR": str(log), "CLAUDE_PLUGIN_DATA": str(cpd), "PLUGIN_DATA": str(pd)}, log),
            ("cpd", {"CLAUDE_PLUGIN_DATA": str(cpd), "PLUGIN_DATA": str(pd)}, cpd),
            ("pd", {"PLUGIN_DATA": str(pd)}, pd),
        )
        for sid, env_ek, beklenen in durumlar:
            with self.subTest(sid=sid):
                self.assertIn(METIN, baglam(self.k(self.claude(self.dokum(CLAUDE_DUZ), sid=sid), env_ek=env_ek)))
                self.assertEqual((beklenen / "hatirlatici" / sid).read_text(), "uyarildi")
        self.assertFalse(self.cache.exists(), "the XDG cache must not be used when a data folder is set")

    # Codex
    def test_codex_yuklenmemis_uyarir(self):
        # The world_state skill list carries the SKILL.md path but is not a tool call: a warning is expected.
        p = self.k(self.codex(self.dokum(CODEX_DUZ)), argumanlar=("codex",))
        self.assertIn(METIN, baglam(p))

    def test_codex_arguman_olmadan_turn_id_ile(self):
        self.assertIn(METIN, baglam(self.k(self.codex(self.dokum(CODEX_DUZ)), argumanlar=())))

    def test_codex_agent_takma_adi(self):
        self.assertIn(METIN, baglam(self.k(self.codex(self.dokum(CODEX_DUZ), arac="Agent"), argumanlar=("codex",))))

    def test_codex_skill_okuma_sessiz(self):
        p = self.k(self.codex(self.dokum(CODEX_DUZ + [CODEX_OKUMA])), argumanlar=("codex",))
        self.assertEqual(p.stdout, "")

    def test_codex_enjeksiyon_sessiz(self):
        p = self.k(self.codex(self.dokum(CODEX_DUZ + [CODEX_ENJEKSIYON])), argumanlar=("codex",))
        self.assertEqual(p.stdout, "")

    def test_codex_alt_ajan_dokumu_sessiz(self):
        alt = self.dokum([satir({"type": "session_meta", "payload": {"id": "019b", "parent_thread_id": "019a-ana",
                                                                     "source": {"subagent": {"x": 1}}}})])
        self.assertEqual(self.k(self.codex(alt), argumanlar=("codex",)).stdout, "")

    # Silence
    def test_kapali_stdout_exit_0(self):
        girdi = json.dumps(self.claude(self.dokum(CLAUDE_DUZ), sid="kapali")).encode()
        env = {k: v for k, v in os.environ.items() if not k.startswith("ORCH_") and k not in ATILAN}
        env.update(self.env)
        oku, yaz = os.pipe()
        os.close(oku)
        try:
            p = subprocess.run([sys.executable, str(KANCA_DIZINI / BETIK), "claude"], input=girdi, stdout=yaz,
                               stderr=subprocess.PIPE, env=env, timeout=30)
        finally:
            os.close(yaz)
        self.assertEqual(p.returncode, 0, p.stderr)
        girdi2 = json.dumps(self.claude(self.dokum(CLAUDE_DUZ), sid="kapali2")).encode()
        p = subprocess.run([sys.executable, str(KANCA_DIZINI / BETIK), "claude"], input=girdi2,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env, timeout=30,
                           preexec_fn=lambda: os.close(1))
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_yardimci_modul_yoksa_exit_0(self):
        import shutil
        yalniz = self.kok / "yalniz"
        yalniz.mkdir()
        shutil.copy(KANCA_DIZINI / BETIK, yalniz / BETIK)
        p = subprocess.run([sys.executable, str(yalniz / BETIK), "claude"],
                           input=json.dumps(self.claude(self.dokum(CLAUDE_DUZ))), capture_output=True, text=True,
                           env=self.temiz_env(), timeout=30)
        self.assertEqual((p.returncode, p.stdout), (0, ""), p.stderr)


if __name__ == "__main__":
    unittest.main()
