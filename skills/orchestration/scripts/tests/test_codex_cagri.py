import json
import os
import threading
from pathlib import Path

from ortak import BETIKLER, ILK_AUTH, SAHTE, SahteCodexTesti

import codex_cagri


class ModelCozumu(SahteCodexTesti):
    def test_depodaki_modeller_json_iki_aileyi_tasir(self):
        veri = json.loads((BETIKLER / "modeller.json").read_text(encoding="utf-8"))
        self.assertTrue(veri["astra"].startswith("gpt-"))
        self.assertTrue(veri["sol"].startswith("gpt-"))

    def test_aile_tam_kimlige_cozulur(self):
        yol = self.kok / "m.json"
        yol.write_text('{"astra": "gpt-9-astra", "sol": "gpt-9.1-sol"}', encoding="utf-8")
        self.assertEqual(codex_cagri.model_coz("astra", yol), "gpt-9-astra")
        self.assertEqual(codex_cagri.model_coz("SOL", yol), "gpt-9.1-sol")

    def test_bilinmeyen_aile_hata(self):
        with self.assertRaises(ValueError):
            codex_cagri.model_coz("luna-missing")

    def test_cagri_argvsi_cozulen_kimligi_ve_temiz_bayraklari_tasir(self):
        kod, son, akis = codex_cagri.cagir("astra", "medium", "hello")
        self.assertEqual(kod, 0)
        self.assertEqual(son, '{"tamam": true}')
        argv = self.cagri_kaydi()["argv"]
        beklenen = json.loads((BETIKLER / "modeller.json").read_text(encoding="utf-8"))["astra"]
        self.assertEqual(argv[argv.index("-m") + 1], beklenen)
        for bayrak in ("--skip-git-repo-check", "--ephemeral", "--json"):
            self.assertIn(bayrak, argv)
        self.assertIn("model_reasoning_effort=medium", argv)
        self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
        kapali = [argv[i + 1] for i, a in enumerate(argv) if a == "--disable"]
        self.assertIn("hooks", kapali)
        self.assertIn("memories", kapali)
        self.assertEqual(argv[-1], "-")
        self.assertEqual(self.cagri_kaydi()["stdin"], "hello")
        self.assertTrue(Path(akis).is_file())
        self.assertEqual(Path(akis).parent, self.olay_dizini)

    def test_cocuk_ortami_temiz_ve_gecici_evde(self):
        codex_cagri.cagir("sol", "high", "x")
        kayit = self.cagri_kaydi()
        env = kayit["env"]
        self.assertIsNone(env["CLAUDECODE"])
        self.assertIsNone(env["CLAUDE_CODE_ENTRYPOINT"])
        self.assertNotEqual(Path(env["CODEX_HOME"]), self.gercek_ev)
        self.assertEqual(kayit["ev_dosyalari"], ["auth.json"])
        self.assertEqual(kayit["auth_izin"], "0o600")
        self.assertFalse(Path(env["CODEX_HOME"]).exists(), "the temporary home must be deleted")

    def test_gorseller_istemden_ayri_esittir_bicimiyle_gider(self):
        g = self.kok / "ref.png"
        g.write_bytes(b"x")
        codex_cagri.cagir("astra", "medium", "x", girdi_gorselleri=[g])
        argv = self.cagri_kaydi()["argv"]
        self.assertIn(f"--image={g.resolve()}", argv)
        self.assertEqual(argv[-1], "-")

    def test_sema_dosyasi_output_schema_ile_gider(self):
        sema = self.kok / "s.json"
        sema.write_text("{}", encoding="utf-8")
        codex_cagri.cagir("astra", "medium", "x", cikti_semasi=sema)
        argv = self.cagri_kaydi()["argv"]
        self.assertEqual(argv[argv.index("--output-schema") + 1], str(sema.resolve()))

    def test_codex_bin_mutlak_olmali(self):
        # a relative path with a separator is rejected even if it exists relative to cwd
        goreli = self.kok / "goreli"
        goreli.mkdir()
        os.symlink(SAHTE, goreli / "codex")
        eski = os.getcwd()
        os.chdir(self.kok)
        try:
            os.environ["ORCH_CODEX_BIN"] = "goreli/codex"
            kod, son, _ = codex_cagri.cagir("astra", "medium", "x")
        finally:
            os.chdir(eski)
        self.assertEqual(kod, codex_cagri.KOD_ARAC_YOK)
        self.assertIn("ORCH_CODEX_BIN", son)
        self.assertFalse(self.argv_dosyasi.exists())

    def test_codex_bin_mutlak_ama_yok(self):
        os.environ["ORCH_CODEX_BIN"] = str(self.kok / "missing" / "codex")
        kod, _, _ = codex_cagri.cagir("astra", "medium", "x")
        self.assertEqual(kod, codex_cagri.KOD_ARAC_YOK)
        self.assertFalse(self.argv_dosyasi.exists())

    def test_codex_bin_ad_path_uzerinden(self):
        # a bare name (ORCH_CODEX_BIN or the default `codex`) is looked up on PATH
        klasor = self.kok / "bin"
        klasor.mkdir()
        os.symlink(SAHTE, klasor / "codex")
        os.symlink(SAHTE, klasor / "my-codex")
        os.environ["PATH"] = str(klasor) + os.pathsep + os.environ.get("PATH", "")
        for deger in ("my-codex", None):
            with self.subTest(deger=deger):
                if deger is None:
                    os.environ.pop("ORCH_CODEX_BIN", None)
                else:
                    os.environ["ORCH_CODEX_BIN"] = deger
                self.argv_dosyasi.unlink(missing_ok=True)
                kod, _, _ = codex_cagri.cagir("astra", "medium", "x")
                self.assertEqual(kod, 0)
                self.assertTrue(self.argv_dosyasi.exists())

    def test_codex_bin_ad_pathte_yoksa_arac_yok(self):
        os.environ["ORCH_CODEX_BIN"] = "codex-that-does-not-exist"
        kod, _, _ = codex_cagri.cagir("astra", "medium", "x")
        self.assertEqual(kod, codex_cagri.KOD_ARAC_YOK)


class KimlikGeriYazma(SahteCodexTesti):
    def test_degismediyse_dokunulmaz(self):
        once = self.gercek_auth.stat().st_mtime_ns
        kod, _, _ = codex_cagri.cagir("astra", "medium", "x")
        self.assertEqual(kod, 0)
        self.assertEqual(self.gercek_auth.read_bytes(), ILK_AUTH)
        self.assertEqual(self.gercek_auth.stat().st_mtime_ns, once)

    def test_gecici_evde_yenilendiyse_atomik_0600_geri_yazilir(self):
        self.mod("auth-yenile")
        kod, _, _ = codex_cagri.cagir("astra", "medium", "x")
        self.assertEqual(kod, 0)
        self.assertEqual(self.gercek_auth.read_bytes(), b'{"tokens": "yenilendi"}')
        self.assertEqual(self.gercek_auth.stat().st_mode & 0o777, 0o600)
        # The lock file (auth.json.lock) is permanent; no temporary .tmp file may remain.
        self.assertEqual(sorted(p.name for p in self.gercek_ev.iterdir()), ["auth.json", "auth.json.lock"])
        self.assertEqual((self.gercek_ev / "auth.json.lock").stat().st_mode & 0o777, 0o600)

    def test_es_zamanli_iki_geri_yazma_tutarli(self):
        # Two calls start from the same initial auth.json and write back different refreshed copies at once: exactly
        # one writes, the other sees inside the lock that the real file changed and warns. Without the lock both could
        # write.
        sha0 = codex_cagri._sha256(self.gercek_auth)
        kopyalar = []
        for ad in ("a", "b"):
            k = self.kok / f"kopya-{ad}.json"
            k.write_bytes(ILK_AUTH)
            kopyalar.append((k, codex_cagri._sha256(k)))
            k.write_bytes(b'{"tokens": "yenilendi-' + ad.encode() + b'"}')
        engel = threading.Barrier(2)
        sonuc = {}

        def yaz(i):
            engel.wait()
            sonuc[i] = codex_cagri.auth_geri_yaz(kopyalar[i][0], self.gercek_auth, sha0, kopyalar[i][1])

        for _ in range(20):
            self.gercek_auth.write_bytes(ILK_AUTH)
            sonuc.clear()
            isler = [threading.Thread(target=yaz, args=(i,)) for i in range(2)]
            for t in isler:
                t.start()
            for t in isler:
                t.join()
            uyarilar = [u for u in sonuc.values() if u]
            self.assertEqual(len(uyarilar), 1, sonuc)
            self.assertIn("not written back", uyarilar[0])
            yazan = next(i for i, u in sonuc.items() if not u)
            self.assertEqual(self.gercek_auth.read_bytes(), kopyalar[yazan][0].read_bytes())
            self.assertEqual(list(self.gercek_ev.glob("*.tmp")), [])
            self.assertEqual(list(self.gercek_ev.glob(".auth.json-*")), [])

    def test_baska_surec_degistirdiyse_ezilmez_uyari_verilir(self):
        self.mod("auth-yenile-gercek-degisti")
        uyarilar = []
        kod, _, _ = codex_cagri.cagir("astra", "medium", "x", uyari=uyarilar.append)
        self.assertEqual(kod, 0)
        self.assertEqual(self.gercek_auth.read_bytes(), b'{"tokens": "baska-surec"}')
        self.assertTrue(any("not written back" in u for u in uyarilar), uyarilar)

    def test_kimlik_dosyasi_yoksa_codex_cagrilmaz(self):
        self.gercek_auth.unlink()
        kod, son, _ = codex_cagri.cagir("astra", "medium", "x")
        self.assertEqual(kod, codex_cagri.KOD_LOGIN_GEREKLI)
        self.assertIn("codex login required", son)
        self.assertFalse(self.argv_dosyasi.exists())


class RefreshHatasi(SahteCodexTesti):
    def test_stderrdeki_hata_taninir(self):
        self.mod("refresh-hata")
        kod, son, _ = codex_cagri.cagir("astra", "medium", "x")
        self.assertEqual(kod, codex_cagri.KOD_LOGIN_GEREKLI)
        self.assertIn("codex login required", son)

    def test_cikis_sifir_olsa_da_akistaki_hata_taninir(self):
        self.mod("refresh-hata-json")
        kod, son, _ = codex_cagri.cagir("astra", "medium", "x")
        self.assertEqual(kod, codex_cagri.KOD_LOGIN_GEREKLI)

    def test_turn_failed_olayindaki_hata_taninir(self):
        self.mod("refresh-turn-failed")
        kod, _, _ = codex_cagri.cagir("astra", "medium", "x")
        self.assertEqual(kod, codex_cagri.KOD_LOGIN_GEREKLI)

    def test_hata_ogesindeki_hata_taninir(self):
        self.mod("refresh-item-error")
        kod, _, _ = codex_cagri.cagir("astra", "medium", "x")
        self.assertEqual(kod, codex_cagri.KOD_LOGIN_GEREKLI)

    def test_model_mesajinda_gecen_kalip_77_dondurmez(self):
        # The critic may quote the pattern while reviewing the script; a successful call must not get a false 77.
        self.mod("refresh-mesajda")
        kod, son, _ = codex_cagri.cagir("astra", "medium", "x")
        self.assertEqual(kod, 0)
        self.assertIn("refresh token was already used", son)

    def test_komut_ciktisinda_gecen_kalip_77_dondurmez(self):
        self.mod("refresh-komut-ciktisinda")
        kod, _, _ = codex_cagri.cagir("astra", "medium", "x")
        self.assertEqual(kod, 0)

    def test_tekrar_denenmez(self):
        self.mod("refresh-hata")
        sayac = self.kok / "sayac"
        gercek = codex_cagri._calistir

        def sayan(*a, **k):
            sayac.write_text(str(int(sayac.read_text() or 0) + 1) if sayac.exists() else "1")
            return gercek(*a, **k)

        codex_cagri._calistir = sayan
        try:
            codex_cagri.cagir("astra", "medium", "x")
        finally:
            codex_cagri._calistir = gercek
        self.assertEqual(sayac.read_text(), "1")


class EvKancasi(SahteCodexTesti):
    def test_kanca_gecici_ev_silinmeden_cagrilir(self):
        gorulen = {}

        def kanca(ev: Path):
            gorulen["var"] = ev.is_dir() and (ev / "auth.json").exists()
            gorulen["ev"] = ev

        codex_cagri.cagir("astra", "medium", "x", ev_kancasi=kanca)
        self.assertTrue(gorulen["var"])
        self.assertFalse(gorulen["ev"].exists())
