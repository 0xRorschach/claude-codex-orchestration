import contextlib
import io
import json
import os
import re
from pathlib import Path
from unittest import mock

from ortak import BETIKLER, SahteCodexTesti, beklenen_kilit

import aile_elestirmen

GECERLI = {"zayiflik_var": True, "bulgular": [
    {"bulgu": "a", "onem": "yuksek", "kanit": "k", "oneri": "o"},
    {"bulgu": "b", "onem": "dusuk", "kanit": "k", "oneri": "o"}], "belirsizlik": ""}
EK = "Task: find the weakest point. If there is no significant weakness, say 'none'."


class BriefHazirlama(SahteCodexTesti):
    def test_kalip_yoksa_iki_cumle_eklenir(self):
        self.assertTrue(aile_elestirmen.brief_hazirla("Review this plan.").rstrip().endswith(EK))

    def test_kalip_varsa_eklenmez(self):
        metin = "Find the WEAKEST part of the plan; say NONE if there is no weakness."
        self.assertEqual(aile_elestirmen.brief_hazirla(metin), metin)

    def test_yalniz_biri_varsa_eklenir(self):
        self.assertIn(EK, aile_elestirmen.brief_hazirla("find the weakest point"))

    def test_hazir_mi_sorusu_eklenmez(self):
        self.assertNotIn("ready", aile_elestirmen.brief_hazirla("review").lower())


class KayitSatiri(SahteCodexTesti):
    def test_bicim(self):
        import datetime
        satir = aile_elestirmen.kayit_satiri(datetime.datetime(2026, 1, 2, 3, 4), "plan", "astra (gpt-x-astra)",
                                             "high", GECERLI, "/tmp/c.json")
        self.assertEqual(satir, "Cross-family 2026-01-02 03:04 · plan · astra (gpt-x-astra) · high · findings 2 "
                                "(high 1) · /tmp/c.json")

    def test_model_etiketi(self):
        self.assertEqual(aile_elestirmen.model_etiketi("astra", "gpt-x-astra"), "astra (gpt-x-astra)")
        self.assertEqual(aile_elestirmen.model_etiketi("opus", None), "opus")
        self.assertEqual(aile_elestirmen.model_etiketi("opus", "opus"), "opus")


class Sema(SahteCodexTesti):
    def test_sema_yapilandirilmis_cikti_kurallarina_uyar(self):
        sema = json.loads((BETIKLER / "elestirmen_sema.json").read_text(encoding="utf-8"))

        def denetle(n):
            if n.get("type") == "object":
                self.assertIs(n.get("additionalProperties"), False)
                self.assertEqual(sorted(n["required"]), sorted(n["properties"]))
                for alt in n["properties"].values():
                    denetle(alt)
            if n.get("type") == "array":
                denetle(n["items"])

        denetle(sema)
        self.assertEqual(sema["properties"]["bulgular"]["items"]["properties"]["onem"]["enum"],
                         ["yuksek", "orta", "dusuk"])

    def test_dogrulama(self):
        self.assertIsNone(aile_elestirmen.sonuc_hatasi(GECERLI))
        self.assertIsNotNone(aile_elestirmen.sonuc_hatasi({"zayiflik_var": "yes", "bulgular": [],
                                                           "belirsizlik": ""}))
        kotu = json.loads(json.dumps(GECERLI))
        kotu["bulgular"][0]["onem"] = "kritik"
        self.assertIsNotNone(aile_elestirmen.sonuc_hatasi(kotu))


class AileTespiti(SahteCodexTesti):
    def test_claude_oturumunda_karsit_codex(self):
        self.assertEqual(aile_elestirmen.varsayilan_aile({"CLAUDECODE": "1"}), "codex")

    def test_codex_oturumunda_karsit_claude(self):
        self.assertEqual(aile_elestirmen.varsayilan_aile({"CODEX_THREAD_ID": "t"}), "claude")
        self.assertEqual(aile_elestirmen.varsayilan_aile({"CODEX_SESSION_ID": "s", "CODEX_CI": "1"}), "claude")

    def test_codex_home_tek_basina_isaret_degil(self):
        self.assertIsNone(aile_elestirmen.varsayilan_aile({"CODEX_HOME": "/x"}))

    def test_belirsizse_none(self):
        self.assertIsNone(aile_elestirmen.varsayilan_aile({}))
        self.assertIsNone(aile_elestirmen.varsayilan_aile({"CLAUDECODE": "1", "CODEX_THREAD_ID": "t"}))

    def test_tespit_edilemezse_aile_istenir(self):
        for ad in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
            os.environ.pop(ad, None)
        for ad in [k for k in os.environ if k.startswith("CLAUDE_CODE_") or k in aile_elestirmen.CODEX_ISARETLERI]:
            os.environ.pop(ad)
        brief = self.kok / "b.md"
        brief.write_text("review", encoding="utf-8")
        hata = io.StringIO()
        with contextlib.redirect_stderr(hata), self.assertRaises(SystemExit) as c:
            aile_elestirmen.ana(["--effort", "medium", "--brief", str(brief), "--cikti", str(self.kok / "c")])
        self.assertNotEqual(c.exception.code, 0)
        self.assertIn("--aile", hata.getvalue())


class UctanUcaCodex(SahteCodexTesti):
    def kos(self, *ek):
        brief = self.kok / "brief.md"
        brief.write_text("Review this design.", encoding="utf-8")
        cikti = self.kok / "cikti.json"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            kod = aile_elestirmen.ana(["--aile", "codex", "--effort", "high", "--brief", str(brief),
                                       "--cikti", str(cikti), *ek])
        return kod, cikti, out.getvalue()

    def test_basarili_cagri_cikti_kayit_ozet(self):
        self.mod("normal", SAHTE_SON_MESAJ=json.dumps(GECERLI))
        kayit = self.kok / "STATE.md"
        kayit.write_text("# STATE\n", encoding="utf-8")
        kod, cikti, out = self.kos("--kayit", str(kayit), "--olay", "design")
        self.assertEqual(kod, 0)
        self.assertEqual(json.loads(cikti.read_text(encoding="utf-8")), GECERLI)
        cagri = self.cagri_kaydi()
        self.assertIn(EK, cagri["stdin"])
        self.assertEqual(cagri["argv"][cagri["argv"].index("--sandbox") + 1], "read-only")
        self.assertIn("--output-schema", cagri["argv"])
        satirlar = kayit.read_text(encoding="utf-8").splitlines()
        self.assertEqual(satirlar[0], "# STATE")
        self.assertRegex(satirlar[-1], r"^Cross-family \d{4}-\d\d-\d\d \d\d:\d\d · design · astra \(gpt-\S+astra\) · high · "
                                       r"findings 2 \(high 1\) · " + re.escape(str(cikti)) + "$")
        self.assertIn("findings 2", out)

    def test_calisma_dizini_varsayilan_cwd_ve_acik(self):
        self.mod("normal", SAHTE_SON_MESAJ=json.dumps(GECERLI))
        self.kos()
        cagri = self.cagri_kaydi()
        self.assertEqual(cagri["argv"][cagri["argv"].index("-C") + 1], str(Path.cwd().resolve()))
        hedef = self.kok / "proje"
        hedef.mkdir()
        self.kos("--calisma-dizini", str(hedef))
        cagri = self.cagri_kaydi()
        self.assertEqual(cagri["argv"][cagri["argv"].index("-C") + 1], str(hedef.resolve()))
        self.assertEqual(Path(cagri["cwd"]).resolve(), hedef.resolve())

    def test_varsayilan_model_astra(self):
        self.mod("normal", SAHTE_SON_MESAJ=json.dumps(GECERLI))
        self.kos()
        argv = self.cagri_kaydi()["argv"]
        self.assertIn("astra", argv[argv.index("-m") + 1])

    def test_sol_secilebilir(self):
        self.mod("normal", SAHTE_SON_MESAJ=json.dumps(GECERLI))
        self.kos("--model", "sol")
        argv = self.cagri_kaydi()["argv"]
        self.assertIn("sol", argv[argv.index("-m") + 1])

    def test_kayit_varsa_olay_zorunlu(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.kos("--kayit", str(self.kok / "k.md"))

    def test_effort_zorunlu(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            aile_elestirmen.ana(["--aile", "codex", "--brief", "b", "--cikti", "c"])

    def test_gecersiz_cikti_undetermined_kaydedilir(self):
        self.mod("normal", SAHTE_SON_MESAJ="plain text")
        kayit = self.kok / "k.md"
        kod, cikti, out = self.kos("--kayit", str(kayit), "--olay", "x")
        self.assertEqual(kod, aile_elestirmen.KOD_GECERSIZ_CIKTI)
        self.assertEqual(cikti.read_text(encoding="utf-8"), "plain text")
        self.assertIn("undetermined", kayit.read_text(encoding="utf-8"))

    def test_kayit_kilidi_tutuluyorsa_ayri_kod_kayit_degismez(self):
        import fcntl
        import elestirmen_kayit_eki
        self.mod("normal", SAHTE_SON_MESAJ=json.dumps(GECERLI))
        kayit = self.kok / "k.md"
        kayit.write_text("# STATE\n", encoding="utf-8")
        beklenen_kilit(kayit).parent.mkdir(parents=True, exist_ok=True)
        kilit = os.open(beklenen_kilit(kayit), os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(os.close, kilit)
        fcntl.flock(kilit, fcntl.LOCK_EX)
        hata = io.StringIO()
        with mock.patch.object(elestirmen_kayit_eki, "KILIT_BEKLEME_SN", 0.3), contextlib.redirect_stderr(hata):
            kod, cikti, _ = self.kos("--kayit", str(kayit), "--olay", "x")
        self.assertEqual(kod, aile_elestirmen.KOD_KAYIT_KILIDI)
        self.assertEqual(kayit.read_text(encoding="utf-8"), "# STATE\n")
        self.assertEqual(json.loads(cikti.read_text(encoding="utf-8")), GECERLI)
        self.assertIn("Cross-family", hata.getvalue())

    def test_kayit_kilit_klasoru_yazilamazsa_6_traceback_yok(self):
        import elestirmen_kayit_eki  # noqa: F401
        self.mod("normal", SAHTE_SON_MESAJ=json.dumps(GECERLI))
        kayit = self.kok / "k.md"
        kayit.write_text("# STATE\n", encoding="utf-8")
        klasor = beklenen_kilit(kayit).parent
        klasor.mkdir(parents=True)
        os.chmod(klasor, 0o500)
        self.addCleanup(os.chmod, klasor, 0o700)
        hata = io.StringIO()
        with contextlib.redirect_stderr(hata):
            kod, cikti, _ = self.kos("--kayit", str(kayit), "--olay", "x")
        self.assertEqual(kod, aile_elestirmen.KOD_KAYIT_KILIDI)
        self.assertEqual(kayit.read_text(encoding="utf-8"), "# STATE\n")
        self.assertEqual(json.loads(cikti.read_text(encoding="utf-8")), GECERLI)
        self.assertNotIn("Traceback", hata.getvalue())

    def test_login_hatasi_kodu_gecer(self):
        self.mod("refresh-hata")
        kod, _, _ = self.kos()
        import codex_cagri
        self.assertEqual(kod, codex_cagri.KOD_LOGIN_GEREKLI)


class UctanUcaClaude(SahteCodexTesti):
    def kos(self, *ek):
        brief = self.kok / "brief.md"
        brief.write_text("Review this design.", encoding="utf-8")
        cikti = self.kok / "cikti.json"
        with contextlib.redirect_stdout(io.StringIO()):
            kod = aile_elestirmen.ana(["--aile", "claude", "--effort", "medium", "--brief", str(brief),
                                       "--cikti", str(cikti), *ek])
        return kod, cikti

    def test_salt_okur_arac_listesi_sema_ve_cumle(self):
        os.environ["SAHTE_SON_MESAJ"] = json.dumps(GECERLI)
        kod, cikti = self.kos()
        self.assertEqual(kod, 0)
        self.assertEqual(json.loads(cikti.read_text(encoding="utf-8")), GECERLI)
        cagri = self.cagri_kaydi()
        argv = cagri["argv"]
        self.assertIn("-p", argv)
        self.assertEqual(argv[argv.index("--model") + 1], "opus")
        self.assertEqual(argv[argv.index("--tools") + 1], "Read,Grep,Glob")
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "dontAsk")
        self.assertEqual(argv[argv.index("--effort") + 1], "medium")
        self.assertEqual(json.loads(argv[argv.index("--json-schema") + 1])["type"], "object")
        self.assertIn("You are read-only; do not modify files.", cagri["stdin"])
        self.assertIn(EK, cagri["stdin"])
        self.assertIsNone(cagri["env"]["CLAUDECODE"])
        self.assertIsNone(cagri["env"]["CLAUDE_CODE_ENTRYPOINT"])

    def test_calisma_dizini_cwd_olarak_gider_ve_kayitta_tam_kimlik(self):
        os.environ["SAHTE_SON_MESAJ"] = json.dumps(GECERLI)
        hedef = self.kok / "proje"
        hedef.mkdir()
        kayit = self.kok / "k.md"
        kod, _ = self.kos("--calisma-dizini", str(hedef), "--kayit", str(kayit), "--olay", "x")
        self.assertEqual(kod, 0)
        self.assertEqual(Path(self.cagri_kaydi()["cwd"]).resolve(), hedef.resolve())
        self.assertIn(" · opus (claude-sahte-opus-1) · medium · ", kayit.read_text(encoding="utf-8"))

    def test_claude_hatasi_sifir_disi(self):
        os.environ["SAHTE_CLAUDE_MOD"] = "hata"
        kod, _ = self.kos()
        self.assertNotEqual(kod, 0)

    def test_codex_modeli_claude_ile_reddedilir(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.kos("--model", "astra")
