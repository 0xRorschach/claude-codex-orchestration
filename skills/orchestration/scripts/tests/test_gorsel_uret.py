import contextlib
import io
from pathlib import Path

from ortak import SahteCodexTesti

import gorsel_uret


class GorselUret(SahteCodexTesti):
    def kos(self, *ek):
        self.cikti = self.kok / "out" / "resim.png"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return gorsel_uret.ana(["--istem", "a cat", "--cikti", str(self.cikti), *ek])

    def test_calisma_klasorune_kaydedileni_kopyalar(self):
        self.mod("gorsel-kaydet")
        self.assertEqual(self.kos(), 0)
        self.assertTrue(self.cikti.read_bytes().endswith(b"-calisma"))
        argv = self.cagri_kaydi()["argv"]
        self.assertEqual(argv[argv.index("--sandbox") + 1], "workspace-write")
        self.assertIn("astra", argv[argv.index("-m") + 1])
        self.assertIn("gorsel.png", self.cagri_kaydi()["stdin"])

    def test_yedek_yol_gecici_evdeki_en_yeni_png(self):
        self.mod("gorsel-ev")
        self.assertEqual(self.kos(), 0)
        self.assertTrue(self.cikti.read_bytes().endswith(b"-yeni"))
        self.assertFalse(Path(self.cagri_kaydi()["env"]["CODEX_HOME"]).exists(), "the temporary home must be deleted")

    def test_gorsel_yoksa_hata_kodu(self):
        self.mod("normal")
        self.assertEqual(self.kos(), gorsel_uret.KOD_GORSEL_YOK)
        self.assertFalse(self.cikti.exists())

    def test_referanslar_ve_sol(self):
        self.mod("gorsel-kaydet")
        r1, r2 = self.kok / "a.png", self.kok / "b.png"
        r1.write_bytes(b"a")
        r2.write_bytes(b"b")
        self.kos("-i", str(r1), "-i", str(r2), "--model", "sol")
        argv = self.cagri_kaydi()["argv"]
        self.assertIn(f"--image={r1.resolve()}", argv)
        self.assertIn(f"--image={r2.resolve()}", argv)
        self.assertIn("sol", argv[argv.index("-m") + 1])

    def test_istem_dosyasi(self):
        self.mod("gorsel-kaydet")
        d = self.kok / "istem.txt"
        d.write_text("prompt from file", encoding="utf-8")
        self.cikti = self.kok / "r.png"
        with contextlib.redirect_stdout(io.StringIO()):
            gorsel_uret.ana(["--istem-dosyasi", str(d), "--cikti", str(self.cikti)])
        self.assertIn("prompt from file", self.cagri_kaydi()["stdin"])
