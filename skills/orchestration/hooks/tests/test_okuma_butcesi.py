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

BETIK = "okuma_butcesi.py"


def bash(cikti, komut="ls -la", sid="oturum-1", **ek):
    g = {"session_id": sid, "transcript_path": "/h/.claude/projects/p/%s.jsonl" % sid, "cwd": "/h",
         "hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": komut},
         "tool_response": {"stdout": cikti, "stderr": "", "interrupted": False, "isImage": False}}
    g.update(ek)
    return g


class OkumaButcesi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.kok = Path(self.tmp.name)
        self.env = {"HOME": str(self.kok), "XDG_CACHE_HOME": str(self.kok / "cache"), "ORCH_OKUMA_ESIGI": "1000"}
        self.durum_dizini = self.kok / "cache" / "orchestration" / "okuma"

    def tearDown(self):
        self.tmp.cleanup()

    def k(self, girdi, env=None):
        p = kos(BETIK, girdi, env or self.env)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p

    def test_esik_alti_sessiz(self):
        self.assertEqual(self.k(bash("x" * 999)).stdout, "")

    def test_esik_ustu_uyari(self):
        self.k(bash("x" * 600))
        p = self.k(bash("x" * 600))
        self.assertEqual(baglam(p), "The main session has collected ~1k characters of read/command output this "
                                    "session. Delegate exploration and verification to explorer/scanner "
                                    "(orchestration > Delegation).")
        self.assertEqual(json.loads(p.stdout)["hookSpecificOutput"]["hookEventName"], "PostToolUse")

    def test_katlarda_tek_uyari(self):
        sonuc = [baglam(self.k(bash("x" * 400))) is not None for _ in range(8)]  # toplam 400..3200
        # 1000 is crossed by call 3 (1200), 2000 by call 5 (2000), 3000 by call 8 (3200).
        self.assertEqual(sonuc, [False, False, True, False, True, False, False, True])

    def test_buyuk_sicrama_tek_uyari(self):
        p = self.k(bash("x" * 3500))
        self.assertIn("~4k", baglam(p))  # 3500 -> round(3.5) = 4
        self.assertIsNone(baglam(self.k(bash("x" * 100))))

    def test_stderr_de_sayilir(self):
        g = bash("x" * 500)
        g["tool_response"]["stderr"] = "y" * 600
        self.assertIsNotNone(baglam(self.k(g)))

    def test_read_grep_glob_sayilir(self):
        self.k({"session_id": "o", "tool_name": "Read", "tool_input": {"file_path": "/a.py"},
                "tool_response": {"type": "text", "file": {"filePath": "/a.py", "content": "x" * 400}}})
        self.k({"session_id": "o", "tool_name": "Grep", "tool_input": {"pattern": "a"}, "tool_response": "x" * 300})
        p = self.k({"session_id": "o", "tool_name": "Glob", "tool_input": {"pattern": "*"},
                    "tool_response": {"filenames": ["x" * 200, "y" * 200]}})
        self.assertIsNotNone(baglam(p))

    def test_baska_arac_sayilmaz(self):
        p = self.k({"session_id": "o", "tool_name": "Write", "tool_input": {}, "tool_response": {"c": "x" * 5000}})
        self.assertEqual(p.stdout, "")

    def test_oturumlar_ayri(self):
        self.k(bash("x" * 600, sid="a"))
        self.assertEqual(self.k(bash("x" * 600, sid="b")).stdout, "")

    def test_alt_ajanda_sessiz_agent_id(self):
        p = self.k(bash("x" * 5000, agent_id="ag1", agent_type="worker"))
        self.assertEqual(p.stdout, "")
        self.assertFalse(self.durum_dizini.exists() and any(self.durum_dizini.iterdir()))

    def test_alt_ajanda_sessiz_transcript_yedegi(self):
        g = bash("x" * 5000)
        g["transcript_path"] = "/h/.claude/projects/p/oturum-1/subagents/agent-1.jsonl"
        self.assertEqual(self.k(g).stdout, "")

    def test_agent_type_tek_basina_alt_ajan_sayilmaz(self):
        # a main session started with --agent also gets agent_type [docs]; agent_id is what tells them apart.
        p = self.k(bash("x" * 5000, agent_type="worker"))
        self.assertIsNotNone(baglam(p))

    def test_muaf_komutlar(self):
        komutlar = [
            "git commit -m 'x'", "cd /a && git push origin main", "git log -1", "git log -1 --format=%H",
            "git commit -m 'a; b | c'", "git -C /a log -1 --oneline", "codex exec --help.",
            "codex exec 'review'", "python3 aile_elestirmen.py a.md",
            "cat > docs/STATE.md <<'EOF'\ntext\nEOF", "cat <<EOF >> notes/report.md\nx\nEOF",
            "tee -a docs/STATE.md <<'EOF'\nx\nEOF", "claude --help", "python3 --version",
        ]
        for komut in komutlar:
            with self.subTest(komut=komut):
                self.assertEqual(self.k(bash("x" * 5000, komut=komut, sid="m")).stdout, "")

    def test_muaf_olmayanlar_sayilir(self):
        for i, komut in enumerate(["git log --oneline", "cat README.md", "cat <<EOF > a.py\nx\nEOF", "git status",
                                   # B1: a non-exempt part of a compound command makes the whole command count
                                   "cat big.log; git commit -m x", "cat big.log && codex exec 'review'",
                                   "cat x; cat <<E >> n.md\ntext\nE", "cat x.log || git push",
                                   "cat x.log | python3 aile_elestirmen.py", "cat a.log\ngit log -1",
                                   "rg 'git push' src", "grep -r 'codex exec' .", "echo aile_elestirmen.py",
                                   "git log -1 -p", "git log -1 --patch", "git log -1 --stat",
                                   "git commit -m x && cat <<E > a.py\nx.md\nE"]):
            with self.subTest(komut=komut):
                self.assertIsNotNone(baglam(self.k(bash("x" * 5000, komut=komut, sid="n%d" % i))))

    def test_ek_muaf_betikler_ortamdan(self):
        # ORCH_MUAF_BETIKLER adds comma-separated script names; without it the same commands are counted.
        komutlar = ["python3 ~/tools/notes.py context 'x'", "python3 sync.py", "sync.py --all"]
        for i, komut in enumerate(komutlar):
            with self.subTest(komut=komut):
                self.assertIsNotNone(baglam(self.k(bash("x" * 5000, komut=komut, sid="em%d" % i))))
        env = dict(self.env, ORCH_MUAF_BETIKLER="notes.py, sync.py,")
        for i, komut in enumerate(komutlar):
            with self.subTest(komut=komut, env="set"):
                self.assertEqual(self.k(bash("x" * 5000, komut=komut, sid="ems%d" % i), env).stdout, "")
        # an exempt script name in argument position still does not exempt the command
        self.assertIsNotNone(baglam(self.k(bash("x" * 5000, komut="echo notes.py", sid="emx"), env)))

    def test_eklenti_veri_dizini_varsa_durum_orada(self):
        for ad in ("CLAUDE_PLUGIN_DATA", "PLUGIN_DATA"):
            with self.subTest(ad=ad):
                veri = self.kok / ("data-" + ad)
                self.k(bash("x" * 10, sid="pd"), dict(self.env, **{ad: str(veri)}))
                self.assertTrue((veri / "okuma" / "pd.json").is_file())
        self.assertFalse(self.durum_dizini.exists(), "the XDG cache path must not be used in plugin mode")
        # CLAUDE_PLUGIN_DATA wins over PLUGIN_DATA
        a, b = self.kok / "a", self.kok / "b"
        self.k(bash("x", sid="oncelik"), dict(self.env, CLAUDE_PLUGIN_DATA=str(a), PLUGIN_DATA=str(b)))
        self.assertTrue((a / "okuma" / "oncelik.json").is_file())
        self.assertFalse(b.exists())

    def test_read_md_muaf_degil(self):
        p = self.k({"session_id": "r", "tool_name": "Read", "tool_input": {"file_path": "/docs/STATE.md"},
                    "tool_response": {"file": {"content": "x" * 5000}}})
        self.assertIsNotNone(baglam(p))

    def test_varsayilan_esik_40000(self):
        env = dict(self.env)
        del env["ORCH_OKUMA_ESIGI"]
        self.assertEqual(self.k(bash("x" * 39999), env).stdout, "")
        self.assertIsNotNone(baglam(self.k(bash("x"), env)))

    def test_gecersiz_esik_varsayilana_doner(self):
        env = dict(self.env, ORCH_OKUMA_ESIGI="abc")
        self.assertEqual(self.k(bash("x" * 5000), env).stdout, "")

    def test_kapatma_degiskeni(self):
        env = dict(self.env, ORCH_OKUMA_BUTCESI="0")
        self.assertEqual(self.k(bash("x" * 5000), env).stdout, "")
        self.assertFalse(self.durum_dizini.exists())

    def test_eski_durum_dosyalari_temizlenir(self):
        self.durum_dizini.mkdir(parents=True)
        eski, yeni = self.durum_dizini / "eski.json", self.durum_dizini / "yeni.json"
        for f in (eski, yeni):
            f.write_text("{}")
        gecmis = time.time() - 8 * 86400
        os.utime(eski, (gecmis, gecmis))
        self.k(bash("x"))
        self.assertFalse(eski.exists())
        self.assertTrue(yeni.exists())

    def test_session_id_temizlenir(self):
        self.k(bash("x", sid="../../escape"))
        self.assertFalse((self.kok / "cache" / "escape.json").exists())
        self.assertEqual(len(list(self.durum_dizini.glob("*.json"))), 1)

    def test_eski_tmp_artiklari_temizlenir(self):
        self.durum_dizini.mkdir(parents=True)
        eski, yeni = self.durum_dizini / "a.json.x1.tmp", self.durum_dizini / "b.json.x2.tmp"
        for f in (eski, yeni):
            f.write_text("{}")
        gecmis = time.time() - 8 * 86400
        os.utime(eski, (gecmis, gecmis))
        self.k(bash("x"))
        self.assertFalse(eski.exists())
        self.assertTrue(yeni.exists())

    def test_es_zamanli_cagrilar_sayim_kaybetmez(self):
        # B5: an unlocked read-modify-write and a fixed .tmp name lose counts under parallel PostToolUse.
        env = dict(self.env, ORCH_OKUMA_ESIGI="10000000")
        env = {**{k: v for k, v in os.environ.items() if not k.startswith("ORCH_") and k not in ATILAN}, **env}
        girdi = json.dumps(bash("x" * 100, sid="paralel"))
        surecler = [subprocess.Popen([sys.executable, str(KANCA_DIZINI / BETIK), "claude"], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env) for _ in range(12)]
        for s in surecler:
            s.stdin.write(girdi.encode())
            s.stdin.close()
        for s in surecler:
            self.assertEqual(s.wait(timeout=30), 0)
            s.stdout.close()
            s.stderr.close()
        durum = json.loads((self.durum_dizini / "paralel.json").read_text())
        self.assertEqual(durum["toplam"], 1200)
        self.assertEqual(list(self.durum_dizini.glob("*.tmp")), [])

    def test_bozuk_durum_dosyasi_sifirdan(self):
        self.durum_dizini.mkdir(parents=True)
        (self.durum_dizini / "oturum-1.json").write_text("{broken")
        self.assertIsNotNone(baglam(self.k(bash("x" * 1500))))

    def test_bozuk_stdin_sessiz(self):
        p = kos(BETIK, None, self.env, ham_girdi="broken")
        self.assertEqual((p.returncode, p.stdout), (0, ""))

    def test_yazilamayan_onbellek_sessiz(self):
        (self.kok / "cache").write_text("a file, not a directory")
        p = kos(BETIK, bash("x" * 5000), self.env)
        self.assertEqual((p.returncode, p.stdout), (0, ""))

    def _sureli(self, komut, sid):
        bas = time.monotonic()
        p = self.k(bash("x" * 5000, komut=komut, sid=sid))
        return time.monotonic() - bas, p

    def test_buyuk_komut_hizli_ve_sayilir(self):
        # Exemption parsing grew quadratically (800 KB single token 13 s, 2 MB heredoc 33-71 s).
        tek = "git commit -m " + "a" * 2_000_000
        heredoc = "cat > docs/STATE.md <<'EOF'\n" + ("line of text\n" * 170_000) + "EOF"
        for ad, komut in (("tek", tek), ("heredoc", heredoc)):
            with self.subTest(ad=ad):
                sure, p = self._sureli(komut, "buyuk-" + ad)
                self.assertLess(sure, 1.0)
                self.assertIsNotNone(baglam(p))  # a command over the limit is not exempt

    def test_tek_ampersan_bolme_noktasi(self):
        for i, komut in enumerate(["git push & cat huge.log", "git commit -m x &\ncat huge.log",
                                   "git push origin main & cat a.log &"]):
            with self.subTest(komut=komut):
                self.assertIsNotNone(baglam(self.k(bash("x" * 5000, komut=komut, sid="amp%d" % i))))
        for i, komut in enumerate(["git push origin main 2>&1", "git push &> /dev/null", "git push >&2",
                                   "git commit -m 'a & b'", "git push &>> /tmp/x.log"]):
            with self.subTest(komut=komut):
                self.assertEqual(self.k(bash("x" * 5000, komut=komut, sid="ampm%d" % i)).stdout, "")

    def test_parcalara_bol_yonlendirme(self):
        sys.path.insert(0, str(KANCA_DIZINI))
        import okuma_butcesi as ob
        self.assertEqual(ob.parcalara_bol("cmd 2>&1 | tail"), ["cmd 2>&1", "tail"])
        self.assertEqual(ob.parcalara_bol("a & b && c"), ["a", "b", "c"])
        self.assertEqual(ob.parcalara_bol("a &> x.log & b"), ["a &> x.log", "b"])
        self.assertEqual(ob.parcalara_bol("a |& b"), ["a", "b"])

    def test_git_log_1_yalniz_bicim_bayraklari(self):
        muaf = ["git log -1", "git log -n 1", "git log -n1", "git log --max-count=1", "git log -1 --format=%H",
                "git log -1 --pretty=format:%s --date=short", "git log --oneline -1", "git log -1 HEAD"]
        for i, komut in enumerate(muaf):
            with self.subTest(komut=komut):
                self.assertEqual(self.k(bash("x" * 5000, komut=komut, sid="gl%d" % i)).stdout, "")
        sayilir = ["git log -1 -n 500", "git log -n 500", "git log -1 --numstat", "git log -1 -p",
                   "git log -1 --stat", "git log -1 --name-only", "git log -1 --shortstat", "git log -n 2",
                   "git log --max-count=5", "git log -1 --all --graph", "git log -1 -U3"]
        for i, komut in enumerate(sayilir):
            with self.subTest(komut=komut):
                self.assertIsNotNone(baglam(self.k(bash("x" * 5000, komut=komut, sid="gs%d" % i))))

    def test_tirnak_icindeki_heredoc_sayilmaz(self):
        for i, komut in enumerate(['git commit -m "x <<EOF"\ncat huge.log',
                                   "git commit -m 'a <<END'\ncat huge.log\nEND",
                                   'git commit -m "multi\nline <<EOF"\ncat huge.log']):
            with self.subTest(komut=komut):
                self.assertIsNotNone(baglam(self.k(bash("x" * 5000, komut=komut, sid="tq%d" % i))))
        # a heredoc outside quotes and a quoted terminator name are still recognised
        komut = "git commit -m \"a <<b\" && cat > docs/STATE.md <<'EOF'\ncat huge.log\nEOF"
        self.assertEqual(self.k(bash("x" * 5000, komut=komut, sid="tqm")).stdout, "")


if __name__ == "__main__":
    unittest.main()
