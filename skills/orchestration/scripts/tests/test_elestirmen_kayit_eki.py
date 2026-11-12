"""Tests for elestirmen_kayit_eki.py. The line format is produced by aile_elestirmen.kayit_satiri, so the prefix
cannot drift from the wrapper's."""
import contextlib
import datetime
import fcntl
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ortak import BETIKLER, KOK_KULLANICI, beklenen_kilit

import aile_elestirmen
import elestirmen_kayit_eki as eki

VERI = {"zayiflik_var": True, "bulgular": [{"bulgu": "a", "onem": "yuksek", "kanit": "k", "oneri": "o"}],
        "belirsizlik": ""}


def kayit(saat, olay):
    return aile_elestirmen.kayit_satiri(datetime.datetime(2026, 11, 12, *saat), olay, "astra (gpt-x-astra)",
                                        "medium", VERI, "docs/audit/b.json")


class KayitEki(unittest.TestCase):
    def setUp(self):
        self.kok = Path(tempfile.mkdtemp(prefix="orch-ek-"))
        self.addCleanup(shutil.rmtree, self.kok, True)
        ev = mock.patch.dict(os.environ, {"HOME": str(self.kok / "ev")})  # lock under ~/.cache; not the real home
        ev.start()
        self.addCleanup(ev.stop)
        os.environ.pop("XDG_CACHE_HOME", None)  # restored by ev.stop
        self.dosya = self.kok / "STATE.md"
        self.satir_a = kayit((9, 5), "plan")
        self.satir_b = kayit((10, 30), "branch end K2")
        self.dosya.write_text("# State\n\n" + self.satir_a + "\n- " + self.satir_b + "\nlast line\n", encoding="utf-8")

    def kos(self, *argv):
        cikti, hata = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(cikti), contextlib.redirect_stderr(hata):
            try:
                kod = eki.ana(["--kayit", str(self.dosya)] + list(argv))
            except SystemExit as e:
                kod = e.code
        return kod, cikti.getvalue(), hata.getvalue()

    def metin(self):
        return self.dosya.read_text(encoding="utf-8")

    def test_uygulandi_neden_ile_eklenir_yalniz_o_satira(self):
        kod, _, _ = self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "applied",
                             "--neden", "2/2, abc123")
        self.assertEqual(kod, 0)
        self.assertEqual(self.metin(), "# State\n\n" + self.satir_a + " · applied (2/2, abc123)\n- "
                         + self.satir_b + "\nlast line\n")

    def test_park_liste_imli_satira(self):
        kod, _, _ = self.kos("--zaman", "2026-11-12 10:30", "--olay", "branch end K2", "--karar", "parked",
                             "--neden", "waiting for the user")
        self.assertEqual(kod, 0)
        self.assertIn("- " + self.satir_b + " · parked (waiting for the user)\n", self.metin())

    def test_nedensiz_uygulandi(self):
        kod, _, _ = self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "applied")
        self.assertEqual(kod, 0)
        self.assertIn(self.satir_a + " · applied\n", self.metin())

    def test_iki_kez_eklenmez(self):
        argv = ("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "applied", "--neden", "x")
        self.assertEqual(self.kos(*argv)[0], 0)
        once = self.metin()
        kod, _, hata = self.kos(*argv)
        self.assertEqual(kod, eki.KOD_EKLI)
        self.assertIn("already", hata)
        self.assertEqual(self.metin(), once)

    def test_gercek_ek_bicimleri_zaten_ekli_sayilir(self):
        for ek in (" · applied", " · applied: K2 4/4", " · applied (2/2)", " · not applied (reason)",
                   " · parked (why)"):
            with self.subTest(ek=ek):
                self.dosya.write_text(self.satir_a + ek + "\n", encoding="utf-8")
                kod, _, _ = self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "parked",
                                     "--neden", "y")
                self.assertEqual(kod, eki.KOD_EKLI)
                self.assertEqual(self.metin(), self.satir_a + ek + "\n")

    def test_bulunamazsa_hata_kodu_dosya_degismez(self):
        once = self.metin()
        for zaman, olay in (("2026-11-12 09:06", "plan"), ("2026-11-12 09:05", "pla"), ("2026-11-12 09:05", "plan x")):
            with self.subTest(zaman=zaman, olay=olay):
                kod, _, hata = self.kos("--zaman", zaman, "--olay", olay, "--karar", "applied")
                self.assertEqual(kod, eki.KOD_YOK)
                self.assertIn("not found", hata)
        self.assertEqual(self.metin(), once)

    def test_dosya_yoksa_bulunamadi(self):
        self.dosya.unlink()
        kod, _, _ = self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "applied")
        self.assertEqual(kod, eki.KOD_YOK)
        self.assertFalse(self.dosya.exists())

    def test_birden_cok_eslesme_hata_kodu(self):
        self.dosya.write_text(self.satir_a + "\n" + self.satir_a + "\n", encoding="utf-8")
        once = self.metin()
        kod, _, _ = self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "applied")
        self.assertEqual(kod, eki.KOD_COK)
        self.assertEqual(self.metin(), once)

    def test_park_nedensiz_ve_bozuk_zaman_kullanim_hatasi(self):
        self.assertEqual(self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "parked")[0], 2)
        self.assertEqual(self.kos("--zaman", "2026-11-12", "--olay", "plan", "--karar", "applied")[0], 2)

    def test_komut_satirindan_calisir(self):
        p = subprocess.run([sys.executable, str(BETIKLER / "elestirmen_kayit_eki.py"), "--kayit", str(self.dosya),
                            "--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "applied"],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(self.satir_a + " · applied\n", self.metin())


    def test_not_applied_ekli_sayilir(self):
        for ek in (" · not applied", " · not applied (reason)"):
            with self.subTest(ek=ek):
                self.dosya.write_text(self.satir_a + ek + "\n", encoding="utf-8")
                kod, _, _ = self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "applied")
                self.assertEqual(kod, eki.KOD_EKLI)
                self.assertEqual(self.metin(), self.satir_a + ek + "\n")

    def test_park_sonra_uygulandi_tek_gecis(self):
        self.dosya.write_text(self.satir_a + " · parked (waiting)\n", encoding="utf-8")
        kod, _, _ = self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "applied", "--neden", "abc")
        self.assertEqual(kod, 0)
        self.assertEqual(self.metin(), self.satir_a + " · parked (waiting) · applied (abc)\n")
        once = self.metin()
        for karar, neden in (("applied", "x"), ("parked", "y")):
            with self.subTest(karar=karar):
                kod, _, _ = self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", karar, "--neden", neden)
                self.assertEqual(kod, eki.KOD_EKLI)
                self.assertEqual(self.metin(), once)

    def test_park_park_ve_uygulandi_park_reddedilir(self):
        for ek in (" · parked (a)", " · applied (b)"):
            with self.subTest(ek=ek):
                self.dosya.write_text(self.satir_a + ek + "\n", encoding="utf-8")
                kod, _, _ = self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "parked", "--neden", "c")
                self.assertEqual(kod, eki.KOD_EKLI)
                self.assertEqual(self.metin(), self.satir_a + ek + "\n")

    def test_crlf_korunur(self):
        self.dosya.write_bytes(("# State\r\n" + self.satir_a + "\r\nlast\r\n").encode("utf-8"))
        kod, _, _ = self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "applied")
        self.assertEqual(kod, 0)
        self.assertEqual(self.dosya.read_bytes(),
                         ("# State\r\n" + self.satir_a + " · applied\r\nlast\r\n").encode("utf-8"))

    def test_girintili_liste_satiri(self):
        self.dosya.write_text("- top\n  - " + self.satir_a + "\n", encoding="utf-8")
        kod, _, _ = self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "applied")
        self.assertEqual(kod, 0)
        self.assertEqual(self.metin(), "- top\n  - " + self.satir_a + " · applied\n")

    def test_dosya_kipi_korunur(self):
        os.chmod(self.dosya, 0o644)
        kod, _, _ = self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "applied")
        self.assertEqual(kod, 0)
        self.assertEqual(os.stat(self.dosya).st_mode & 0o7777, 0o644)

    def test_sembolik_bag_korunur_hedefe_yazilir(self):
        hedef = self.kok / "gercek.md"
        hedef.write_text(self.satir_a + "\n", encoding="utf-8")
        self.dosya.unlink()
        self.dosya.symlink_to(hedef)
        kod, _, _ = self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "applied")
        self.assertEqual(kod, 0)
        self.assertTrue(self.dosya.is_symlink())
        self.assertEqual(hedef.read_text(encoding="utf-8"), self.satir_a + " · applied\n")

    def test_okunamayan_dosya_ayri_kod(self):
        self.dosya.write_bytes(b"\xff\xfe broken " + self.satir_a.encode("utf-8") + b"\n")
        once = self.dosya.read_bytes()
        kod, _, hata = self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "applied")
        self.assertEqual(kod, eki.KOD_OKUNAMADI)
        self.assertNotEqual(eki.KOD_OKUNAMADI, eki.KOD_YOK)
        self.assertIn("unreadable", hata)
        self.assertEqual(self.dosya.read_bytes(), once)

    def test_kilit_tutuluyorsa_bekler_sonra_ayri_kod(self):
        kilit = self.kilidi_tut(self.dosya)
        once = self.metin()
        with mock.patch.object(eki, "KILIT_BEKLEME_SN", 0.3):
            kod, _, hata = self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "applied")
        self.assertEqual(kod, eki.KOD_KILIT)
        self.assertIn("lock not taken", hata)
        self.assertEqual(self.metin(), once)

    def test_kilit_sembolik_bagda_gercek_yolun_kilidi(self):
        hedef = self.kok / "gercek.md"
        hedef.write_text(self.satir_a + "\n", encoding="utf-8")
        self.dosya.unlink()
        self.dosya.symlink_to(hedef)
        self.kilidi_tut(hedef)
        with mock.patch.object(eki, "KILIT_BEKLEME_SN", 0.3):
            kod, _, _ = self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "applied")
        self.assertEqual(kod, eki.KOD_KILIT)

    def kilidi_tut(self, kayit):
        yol = beklenen_kilit(kayit)
        yol.parent.mkdir(parents=True, exist_ok=True)
        kilit = os.open(yol, os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(os.close, kilit)
        fcntl.flock(kilit, fcntl.LOCK_EX)
        return kilit

    def test_kilit_cache_altinda_defterin_yaninda_degil(self):
        kod, _, _ = self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "applied")
        self.assertEqual(kod, 0)
        self.assertTrue(beklenen_kilit(self.dosya).is_file())
        self.assertEqual(list(self.kok.glob("*.lock")), [])
        eki.kayda_ekle(self.dosya, "new")
        self.assertEqual(list(self.kok.glob("*.lock")), [])

    @unittest.skipIf(KOK_KULLANICI, "root ignores chmod 0o500")
    def test_kilit_klasoru_yazilamazsa_6_traceback_yok(self):
        klasor = beklenen_kilit(self.dosya).parent
        klasor.mkdir(parents=True)
        os.chmod(klasor, 0o500)
        self.addCleanup(os.chmod, klasor, 0o700)
        once = self.metin()
        kod, _, hata = self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "applied")
        self.assertEqual(kod, eki.KOD_KILIT)
        self.assertIn("lock not taken", hata)
        self.assertNotIn("Traceback", hata)
        self.assertEqual(self.metin(), once)
        with self.assertRaises(eki.KilitAlinamadi):
            eki.kayda_ekle(self.dosya, "new")

    def test_kilit_klasoru_kurulamazsa_6(self):
        (self.kok / "ev").mkdir()
        (self.kok / "ev" / ".cache").write_text("a file, not a folder", encoding="utf-8")
        kod, _, hata = self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "applied")
        self.assertEqual(kod, eki.KOD_KILIT)
        self.assertNotIn("Traceback", hata)

    def test_kayda_ekle_crlf_dosyaya_crlf(self):
        for once, sonra in (("a\r\nb\r\n", "a\r\nb\r\nnew\r\n"), ("a\r\nb", "a\r\nb\r\nnew\r\n"),
                            ("a\nb\n", "a\nb\nnew\n"), ("a\nb", "a\nb\nnew\n")):
            with self.subTest(once=once):
                self.dosya.write_bytes(once.encode("utf-8"))
                eki.kayda_ekle(self.dosya, "new")
                self.assertEqual(self.dosya.read_bytes(), sonra.encode("utf-8"))

    def test_eszamanli_ek_ve_kayit_kaybolmaz(self):
        satirlar = [kayit((11, d), f"event {d}") for d in range(8)]
        self.dosya.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
        betik = str(BETIKLER / "elestirmen_kayit_eki.py")
        ekleyici = ("import sys; sys.path.insert(0, %r); import elestirmen_kayit_eki as e; "
                    "e.kayda_ekle(sys.argv[1], sys.argv[2])" % str(BETIKLER))
        surecler = []
        for d in range(8):
            surecler.append(subprocess.Popen([sys.executable, betik, "--kayit", str(self.dosya), "--zaman",
                                              f"2026-11-12 11:{d:02d}", "--olay", f"event {d}", "--karar", "applied"]))
            surecler.append(subprocess.Popen([sys.executable, "-c", ekleyici, str(self.dosya), f"new {d}"]))
        for s in surecler:
            self.assertEqual(s.wait(timeout=60), 0)
        metin = self.metin()
        for d in range(8):
            self.assertIn(satirlar[d] + " · applied\n", metin)
            self.assertIn(f"\nnew {d}\n", metin)

    def test_olay_ayirici_ya_da_satir_sonu_kullanim_hatasi_dosya_degismez(self):
        once = self.metin()
        for olay, neden in (("plan · phase 2", None), ("plan\nx", None), ("plan\rx", None),
                            ("plan", "two\nlines"), ("plan", "a\rb")):
            with self.subTest(olay=olay, neden=neden):
                argv = ["--zaman", "2026-11-12 09:05", "--olay", olay, "--karar", "applied"]
                if neden:
                    argv += ["--neden", neden]
                kod, _, hata = self.kos(*argv)
                self.assertEqual(kod, 2)
                self.assertNotIn("Traceback", hata)
                self.assertEqual(self.metin(), once)

    def test_kilit_xdg_cache_home_altinda(self):
        cache = self.kok / "xdg"
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(cache)}):
            kod, _, _ = self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "applied")
            self.assertEqual(kod, 0)
            self.assertTrue(beklenen_kilit(self.dosya).is_file())
            self.assertTrue(str(beklenen_kilit(self.dosya)).startswith(str(cache)))
        self.assertFalse((self.kok / "ev" / ".cache").exists())

    @unittest.skipIf(KOK_KULLANICI, "root ignores chmod 0o500")
    def test_gecici_dosya_acilamazsa_7_traceback_yok(self):
        klasor = self.kok / "salt"
        klasor.mkdir()
        self.dosya = klasor / "STATE.md"
        self.dosya.write_text(self.satir_a + "\n", encoding="utf-8")
        os.chmod(klasor, 0o500)  # the file is readable, mkstemp next to it fails
        self.addCleanup(os.chmod, klasor, 0o700)
        kod, _, hata = self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "applied")
        self.assertEqual(kod, eki.KOD_OKUNAMADI)
        self.assertNotIn("Traceback", hata)
        self.assertIn("not written", hata)
        self.assertEqual(self.metin(), self.satir_a + "\n")

    def test_flock_baska_oserror_7_traceback_yok(self):
        once = self.metin()
        with mock.patch.object(eki.fcntl, "flock", side_effect=OSError(9, "Bad file descriptor")):
            kod, _, hata = self.kos("--zaman", "2026-11-12 09:05", "--olay", "plan", "--karar", "applied")
        self.assertEqual(kod, eki.KOD_OKUNAMADI)
        self.assertNotIn("Traceback", hata)
        self.assertEqual(self.metin(), once)


if __name__ == "__main__":
    unittest.main()
