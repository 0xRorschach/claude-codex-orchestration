# Orchestration (Türkçe)

Bu dosya SKILL.md'nin Türkçe okuma kopyasıdır; model SKILL.md'yi yükler. İki dosya ayrışırsa SKILL.md geçerlidir.

**Adlar.** Dosya ve env adları Türkçe kökenlidir ve bilerek korunur (ad değiştirmek testlere, kanca kayıtlarına
ve bu dosyaya yayılırdı): `okuma_butcesi` = okuma bütçesi, `aile_elestirmen` = aile
eleştirmeni, `paralel-is-hatirlatici` = paralel iş hatırlatıcısı, `agent-tip-kapisi` = ajan tipi kapısı,
`superpowers_surum_bekcisi` = superpowers sürüm bekçisi, `gorsel_uret` = görsel üretimi,
`orkestrasyon_hatirlatici` = orkestrasyon yükleme hatırlatıcısı, `K1` / `K2` = eleştirmen katmanı 1 / 2.
Aşağıdaki yollar bu skill'in klasörüne göredir (`hooks/`, `scripts/`).

Tek dosya hem Claude Code'a hem Codex'e hizmet eder (kurulum yolları: README); kendi içinde tamdır. Önce **Ortak
ilke**'yi, sonra kendi uygulamanın bölümünü oku. Her projede ya da tek seferlik işte doğrudan kullan; rol ilkesi
projenin nasıl başlatıldığına bağlı değildir ve bir proje kurulumunu bitirmek tek başına uygulama izni vermez
(kullanıcının önceden verdiği izin geçerli kalır). **[profil]** işaretli maddeler varsayılandır; profilinde değiştir
(bkz. `profile/profile.example.md`).

## Ağaç

**Model adları aile adıdır** ("Fable", "Opus", "Sonnet", "Haiku", "Astra", "Sol", "Luna": o ailenin en yeni modeli).
Kural metninde sürüm numarası yok; sürümler yalnız tarihli kayıtlarda ve aşağıdaki çözümleme satırında durur.

| | Claude Code | Codex |
|---|---|---|
| Ana oturum: karar, brief, denetim, sentez | Opus · high | Astra · high |
| Alt ajanlar (`explorer` / `worker` / `researcher`) | Opus · medium | Sol · medium |
| Tarayıcı (salt-okur arama / yapı dökümü / ham çıktı özeti) | Sonnet · medium (`scanner`) | Sol · medium (`scanner` rolü; Luna ölçülmedi) |
| Alt kademe, başka her iş için **yalnız kullanıcı söylerse** [profil] | Sonnet | Luna |
| İkinci görüş (audit), yalnız kilit noktalar | Astra · medium · salt-okur; metodoloji kapılarında high; görev sınırı K2 (`K2: yes` işaretli görev) Sol | Claude Opus · salt-okur |
| Danışman | Fable (`advisor` aracı) | yok |

Çözümleme [ölçüm 2026-10-08]: Opus → Opus 5.5 · Fable → Fable 5.1 · Sonnet → Sonnet 5.5 · Haiku → Haiku 5.5 ·
Astra → `gpt-6-astra` · Sol → `gpt-6.1-sol` · Luna → `gpt-6-luna`. Model kimlikleri `scripts/modeller.json`'da ve
ajan dosyalarında durur (Claude ajanı `.md`, Codex rolü `.toml`; bkz. README); yeni model çıkınca bunları güncelle. Bu
ailelerden birine erişimin yoksa kendi modellerini aynı dosyalara yaz; aşağıdaki kurallar rol üzerinden çalışmaya devam
eder.

Özet: **planlama, karar ve denetim ana oturumda; yürütme medium düzeyde devredilir; ikinci görüş öbür aileden
istenir.** Kullanıcı bir iş için başka model söylerse o işte onu kullan, sonra bu ağaca dön.

## Ortak ilke

### Amaç: takım halinde çalışmak

Amaç ajanları kısıtlamak değil, takım halinde verimli çalışmalarını sağlamaktır. Tek bir ajan bağlamı yalnız kendi
bakışından görür ve kendi yolunda yanılabilir; birkaç bakış eklemek buna karşı koyar. Skill tetiklenmediğinde de böyle
çalış: çok ajan, denetimi elinde tutan tek orkestratör. Kurallar bu amacın araçlarıdır, kontrol listesi değil. Önemli
bir kararda **gerçekten farklı** bir bakış ekle:

| Kaynak | Kim | Neyi bozar |
|---|---|---|
| Farklı bilgi: yazarın akıl yürütmesini görmemiş bir göz | taze `explorer` | brief'ine kendi sonucunu yazmak |
| Farklı rol: üreten değil, eleyen | uygulayıcıdan ayrı bir inceleyici ajan | kanıt yerine rapora güvenmek |
| Farklı aile: başka eğitim, başka kör noktalar | ikinci görüş (Claude'dan Astra, Codex'ten Claude Opus) | her adıma koymak (bkz. yakınsama kuralı) |

Danışman bütün sohbeti görür: daha güçlü bir göz, ama bağımsız değil. Aynı ajana aynı soruyu iki kez sormak yeni bakış
değildir. Tetik kararın türüdür, orkestrasyonun açık olup olmadığı değil.

### Devir: varsayılan devretmektir

- **Varsayılan:** alt ajan kullanılabiliyorsa kullan. Keşif, okuma, uygulama, test ve belge alt ajanlara gider; ana
  oturumun bağlamı boş yere doldurulmaz. neden: bağlamdan ve gerçek süreden kazandırır. Kullanıcı "subagent kullan"
  ya da "kendin yap" derse o geçerlidir. Devir izni kalıcıdır (her seferinde sorulmaz) [profil]. Bu skill "hangi tip,
  hangi kademe" sorusunu yanıtlar.
- **Çok adımlı işin başı:** önce bu skill'i ve ilgili superpowers skill'ini (ör. subagent-driven-development) yükle;
  ilk alt ajan çağrısına erteleme. neden: bağlam hızlı dolar.
- **Ana oturum (Claude: kullanıcı başka model söylemedikçe Opus · high):** aktif iş yapmaz ve bağlamını yalın tutar.
  İşi alt ajanlara verir, düzenler, kullanıcıyla iletişimde kalır (alt ajan gerektirmeyen ara adımlarda da), gerekince
  açıklar, orkestre eder, karar verir, denetler ve sırası gelince danışmana danışır. Bir devir tıkanınca ya da
  güvenilmez çıkınca yeni brief'le yeniden devreder ya da danışmana sorar; işi kendisi üstlenmez.
- **Codex istisnası:** Sol alt ajanlarının yetmediği zor ya da hassas iş Codex ana oturumunda (Astra) kalabilir;
  mekanik ve dar iş Sol'e gider. neden: Sol, Opus'tan zayıftır [gözlem 2026-09-25].
- **Aktif iş ve izinli iş.** İzinli (ana oturumda kalır): kayıt yazmak (STATE, defter, not sistemin), brief yazmak,
  motor ve kapı komutları, commit / push / merge, aileler arası çağrılar (`scripts/aile_elestirmen.py`) ve alt ajanın
  tarayıcı erişimi yoksa kullanıcıyla eşzamanlı tarayıcı işi. Aktif (alt ajana gider): dosya okuyarak keşif (`cat`,
  `sed -n`, `grep`, Read), test koşmak, belge dönüştürmek (pandoc, textutil), kod ya da teslim dosyası düzenlemek. Bir
  alt ajanın kanıtı eksikse ana oturum kendi grep'ini koşmaz; taze bir inceleyici açar.
- **Okuma bütçesi kancası** `hooks/okuma_butcesi.py` (PostToolUse; yalnız not ekler, hiç engellemez) ana oturumun
  Read/Bash/Grep/Glob çıktısında yalnız modele giden alanları oturum başına toplar (Bash `stdout` + `stderr`, Read
  dosya içeriği; Claude Code'un eklediği `bashEditDiff` alanı sayılmaz; Codex'te yalnız kabuk komutları). Toplam
  `ORCH_OKUMA_ESIGI` değerini (varsayılan 40000 karakter) ve sonra her katını geçince keşif ile doğrulamayı
  explorer/scanner'a devretme notu ekler. Alt ajanların içinde sessizdir. Sayılmayanlar: `git commit` / `git push` /
  `git log -1`, `codex exec`, `aile_elestirmen.py`, `ORCH_MUAF_BETIKLER` içindeki ek script'ler (virgülle ayrılmış
  dosya adları, ör. kendi not CLI'n), `.md`'ye yazan heredoc'lar, `--help` / `--version` (bileşik komut ve `git log`
  ayrıntısı: `hooks/README.md`). `ORCH_OKUMA_BUTCESI=0` kancayı kapatır. Kayıt için bkz. README; zaman aşımı iki
  uygulamada da 5 s (PostToolUse) ve 10 s (SessionStart). Eşik [ölçüm 2026-11-07, n=107 ana oturum]: Agent sonucu
  medyanı 16k, Bash iş çıktısı medyanı 44k karakter; 40k ikisinin arasında durur ve oturumların yaklaşık yarısında
  uyarır (bu ölçüm yanıttaki bütün alanları saydığı için `bashEditDiff` ile şişmiş olabilir; izin listesiyle henüz
  yeniden ölçülmedi). neden: "aktif iş" tanımı olmadan Bash ile okuma ana oturumun en büyük iş sınıfı olarak kaldı.
- **Yükleme hatırlatıcısı.** Ana oturum bir alt ajan açarsa ve bu skill o oturumda yüklenmemişse
  `hooks/orkestrasyon_hatirlatici.py` (PreToolUse; Claude `Agent|Task`, Codex `^(spawn_agent|Agent)$`) bir kez hatırlatır
  ve hiç engellemez. `ORCH_HATIRLATICI=0` kancayı kapatır. Claude'da not (additionalContext) ilk Agent çağrısının sonucuyla
  gelir; bu yüzden ilk açılışı değil, sonrakileri biçimlendirir. [ölçüm 2026-11-07, n=152 ana oturum: %44,7 kendiliğinden
  yükledi, %11,2 kullanıcı tetikledi, %44,1 hiç yüklemedi (çoğu tek ajanlı oturum)]
- **Bağımsız işi çoğalt.** Dağıtmadan önce bağımlılıkları çıkar; bağımsız görevler, senaryolar ya da sorular ayrı alt
  ajanlara paralel gider (ayrı klasör/worktree, ayrı sonuç dosyası, birleştirme ana oturumda). Claude Code'da
  `hooks/paralel-is-hatirlatici.py` (PostToolUse `Agent|Task`) her ajan başlangıcında "bu ajanı beklemeyen iş var mı?"
  diye sorar (mesaj başına bir kez: son uyarıdan 5 sn içindeki başlangıçlar sessiz kalır). Uyarı gelince ya bağımsız
  işi aynı turda başlat ya da neden başlatmadığını kullanıcıya tek cümleyle söyle; sıralı motor adımı gerekçe istemez.
  `ORCH_PARALEL_HATIRLATICI=0` kancayı kapatır.

### Karar kimde

- **Ajan:** araştırmayla gerekçelendirilebilen ve geri alınabilen uygulama ve teknik seçimler: araştır, seç, gerekçeyi
  yaz. Önceden yazılmış bir kuralın ya da planın uygulanması ve gerekçeli önerine dayanan geri alınabilir seçim de
  ajandadır: uygula, kayda geçir ve kullanıcıya **"aldığım kararlar"** olarak sun. Devredilen bu seçimlerde yalnız geri
  dönüşü zor çıkan, dışa dönük olan, ödeme ya da hesap gerektiren ya da dondurulmuş bir protokolün çekirdeğini
  değiştiren için bekle. neden: soruların çoğu "önerine uy" diye dönünce (bir belgede 15'te 14 [ölçüm]) onları beklemek
  yalnız işi durdurur.
- **Kullanıcı:** bilimsel/klinik eşikler (analiz planı, dışlama ölçütü, klinik kesim değeri), kişisel tercihler ve
  geri dönüşü zor ya da dışa dönük kararlar, yazılı bir kural ya da plan onları kapsıyor gibi görünse de her zaman
  kullanıcıya gider: bir dosyaya yaz ve gerekçeli önerinle sor. neden: sessizce seçilen eşik kimsenin sorgulamadığı bir
  değere dönüşür.

### Sınırlar

- **Eşzamanlılık eşiği 15** [profil] (`ORCH_PARALEL_ESIK` hatırlatıcı kancanın andığı sayıyı ayarlar). Eşiktir, duvar
  değil: oturum toplamını değil, **aynı anda** çalışan ajanları sayar; üstüne çıkacaksan açmadan önce gerekçeyi
  kullanıcıya yaz (iç içe açılanlar dahil). neden: maliyet (boş bir alt ajan bile ~26k token [ölçüm n=1]) ve ana
  oturumun denetim kapasitesi; teknik sınır sayı değil, iç içe derinliktir (varsayılan 3 düzey [doküman]).
- **İç içe:** açılan ajan aynı tip kurallarına uyar; **yardımcı açabilir, yönetici olamaz**. Pratikte yalnız `worker`
  ajan açabilir; `explorer`, `researcher`, `scanner`'ın ajan aracı yoktur.
- **Geri alınamaz eylem, iki kademe.** Alt ajan push etmez, uzak dal silmez, izlenmeyen dosya silmez, çalışma alanı
  dışına ya da dış bir servise yazmaz; ana oturuma döner. Dışa dönük ya da geri dönüşü zor eylem ayrıca kullanıcının
  onayını ister: ana oturumun onayı kullanıcınınkinin yerine geçmez. Yerel düzenleme durak istemez. Worker görev işini
  kendi worktree'sinde/özellik dalında commit eder; main'e birleştirme ve push ana oturumun işidir. Ana oturum commit
  etmeden önce sorar [profil]; sormadan commit profilde seçilebilir (`profile/profile.example.md`). Projenin CLAUDE.md/AGENTS.md'sinde yazılı açık bir istisna varsa o geçerlidir (ör. "ajan
  main'e birleştirip push edebilir").
- **Worktree yaşam döngüsü.** Proje deposunun içinde, gitignore'lu `.worktrees/<name>` klasöründe ya da aracın proje içi
  klasöründe aç (Claude Code `EnterWorktree`: `.claude/worktrees/` [ölçüm 2026-10-17]); asla projelerinin yanında kardeş
  klasör olarak açma (ayrı bir proje gibi görünür). Dal main'e birleşip inceleme kapanınca onu açan oturum kaldırır
  (iki konumda da): önce `git status --porcelain --ignored` ile gitignore'lu ama yeniden üretilemeyen veriyi bul
  (venv/önbellek değil) ve `<archive-dir>/<project>-<name>-<folder>` altına taşı [profil]; sonra `--force` olmadan
  `git worktree remove` (düz remove bile gitignore'lu dosyaları siler [ölçüm 2026-10-17]). Dalı yalnız birleştikten
  sonra `git branch -d` ile sil; asla `-D` kullanma (birleşmiş commit'ler main'dedir; `-d` birleşmemiş dalı reddeder).
- **Workflow** (çok ajanlı script) kullanıcının her seferinde açıkça verdiği ayrı bir izindir; bu skill ona yetki
  vermez [profil]. **Öneriyi model getirir**, görev ne olursa olsun [profil]. Sürekli açık ultracode modu yok
  (yakınsama kuralıyla, Opus · medium devriyle ve bu izin kuralıyla çatışır). Tek oturumun bağlamını aşan ya da
  bağımsız mercekler isteyen bir kilit noktada (merge öncesi bütün dal incelemesi, çok maddeli kabul/kanıt matrisi,
  geniş tarama) ajan bunu soru kutusunda **kendiliğinden önerir**: gerekçe, ajan sayısı, tahmini maliyet, sınırlar;
  tipler `explorer`/`worker`, effort medium, bulgu başına en çok 2-3 mercek, yakınsama kuralı korunur (bulgu üretmeye
  devam ederse dur ve kullanıcıya getir). Onaydan önce hiçbir şey koşmaz; bir soruda ya da kayıt talimatında geçen
  "ultracode" izin değildir. neden: bir görevde farklı bakışlar (taze explorer + gerçek ölçüm 4 hata, Astra 1) tek
  mercekli incelemelerin kaçırdığını yakaladı; aynı dosyayı paylaşan sıralı işte dağıtmak bir şey kazandırmaz.
- **Alt kademe (Sonnet / Haiku / Luna) yalnız kullanıcı söylerse** [profil]; "basit" diye asla aşağı inme. Tek istisna
  `scanner`'dır: iniş çağrı anındaki yargıyla değil, ajan tipiyle olur.
- **`scanner` mı `explorer` mı:** "nerede / nereden çağrılıyor / yapı dökümü / bu çıktıyı özetle" → `scanner`; yargı içeren
  her şey (spec'e uyum, kod doğru mu, plan sağlam mı) → `explorer`. [ölçüm n=2, kör puanlama] aramada Sonnet ≈ Opus;
  belge doğrulamada Sonnet olgu hatası yaptı → `researcher` Opus'ta kalır; inceleme ve uygulama ölçülmedi, o yüzden
  Opus'ta kalır. Haiku 5.5 tek dosyalık tarayıcı olarak denendi ve kör karşılaştırmada Sonnet'ten fazla yanlış "yok"
  iddiası üretti (her biri 9 koşu, 1-0); benimsenmedi [ölçüm 2026-10-08].
- **`scanner` mekanik işi.** Hükmü koddan ya da çıktıdan gelen iş `scanner`'a gider: bir script'i koşup çıktısını
  aynen aktarmak (denetim script'i, kelime sayımı), test/log özetleri, envanter / sembol yeri / çağrı izi (her
  `path:line` için satırın kendisini alıntıla). Script bir hata basarsa (`HATA` ya da benzeri) düzeltme `worker`'ındır;
  `scanner` "temiz" yorumu eklemez. Kontrol listesine bağlı biçim denetimi de kapsamdadır. Her `scanner` brief'i şunu
  içerir: "şablon dışında not yazma; yalnız istenen alanları doldur". Belge, API ve kaynak doğrulaması asla Sonnet'e
  gitmez; `researcher`'da kalır. [ölçüm 2026-11-07, kör karşılaştırma n=3/hücre, 24 koşu: doğruluk Sonnet 96/96, Opus
  95/96; şablon dışı not hatası Sonnet 1, Opus 7; Sonnet %26-34 daha hızlı] Sonnet/Sol için görev tanımları bu biçimde
  yazılabilir.
- **Model değerlendirirken katmanlı seçenek.** Yeni ya da ucuz bir model değerlendirilirken yalnız "bütün rol taşınsın
  mı" diye sorma; görev türüne göre katmanlı kullanımı da tasarla, ölç ve sun (ör. tek dosya/tek çıktı → ucuz model,
  çok dosyalı iz → güçlü model). neden: bir pilotta katmanlama erkenden "yönlendirme karmaşası" diye bırakıldı ve veri
  o örüntüyü gösterdiğinde yeniden ele alınmadı.

### Brief, denetim, sentez

- **Brief içeriği.** Dar kapsam + bağlam + çıktı biçimi + kabul ölçütü.
- **Orkestratör ile alt ajan arasındaki konuşma en azdadır.** Ajanın ne yapacağını değiştiren gerekçeyi koru (ölçülmüş
  olgu, tam komut/değer, bir kısıtın sonucu); yalnız anlamaya yarayan hikayeyi çıkar. Anlatım disiplini kullanıcıya
  yazılan metni bağlar, alt ajan brief'lerini değil. Alt ajan hedefi yeniden tanımlamaz.
- **Kanıt biçimi.** Koşulan komutu, çıkış kodunu, geçen/kalan sayısını, kalan testlerin adını, diffstat'ı ve file:line'ı
  iste; özet bulgu · kanıt · belirsizlik olarak döner. Uzun log yok, onun yerine işaretçi. "Testler geçti" kanıt
  değildir.
- **Çıktıyı eleştirel denetle:** olgu hatası, kanıtsız iddia, kaçan gereksinim. Çelişkiyi kendin çöz, ham çıktıyı asla
  iletme, tek sonuç sentezle. Bir model, ajan ya da araç kullanılamadıysa çalışmış gibi sunma; teknik sınırı açıkça
  raporla.
- **Bağımsız göz için brief sırası.** İnceleyiciye ya da ikinci görüşe önce soruyu, bağlamı ve kanıtı ver; kendi
  sonucunu değil. Görev: "find the weakest point; if there is no significant weakness, say 'none'." (en zayıf noktayı
  bul; kayda değer bir zayıflık yoksa 'none' de). İkinci cümle zorunludur: o olmadan her tur bulgu üretmek zorunda
  kalır ve yakınsama kuralı bozulur (neden: dile getirilmiş bir görüşe doğru çekim). Danışmana uygulanmaz.
- Çıktı yetersizse **yeni brief'le yeniden devret ya da danışmana sor**; işi ana oturuma alma.
- **Çatışmalar.** Ajanlar arasındaki çatışmayı ana oturum çözer. Tek istisna **bilimsel/klinik bir karardır**; orada ana
  oturum görüşleri tartar ve iki görüşü kendi önerisiyle birlikte kullanıcıya sunar.

### Mevcut planla aşama takibi

Aşama, gözlenebilir bir çıktı ve bir kabul ölçütüyle kapanan iş parçasıdır. Çok aşamalı işte projenin aşama takibini
kullan: mevcut bir aşama kaydı, o yoksa yetkili plan/defter yeterlidir. Takip işe yarıyorsa ana oturum o kayıtta dar
aşamalar tanımlar; tek seferlik bir iş yeni belge istemez ve mevcut bir proje STATE/BACKLOG'a geçmek zorunda değildir.
Aşama durumunu yalnız tek bir yetkili yerde tut (iki kayıt birbirinden uzaklaşır). Proje bir STATE şeması
kullanıyorsa:

- Tek güncel tablo en üstteki `>>> … <<<` bloğudur: kimlik, hedef, çıktı/yol, önkoşul aşamalar ve kritik girdi/sürüm,
  gözlenebilir kabul ölçütü, durum, kanıt bağlantısı. Bilinmeyen girdi ya da sürüm `unknown` kalır; gerçek önkoşulu
  olmayan `none` yazılır. Durum sözlüğü: `planned`, `active`, `in review`, `accepted`, `blocked`, `deferred`,
  `re-review needed`.
- Görev ayrıntısı ve takibi planda kalır (varsa superpowers planında); STATE onun yoluna/görevine işaret eder.
  BACKLOG yarım kalan, engellenen ve ertelenen işi aşama kimliğine göre tutar: kalan iş, gerekçe, plan bağlantısı,
  engelin kalkma ya da yeniden bakma koşulu. STATE açık işleri bunlara işaret eder; aşama durumunu BACKLOG'da, borç
  ayrıntısını STATE'te tekrarlama. BACKLOG borcunu kapatmak aşama kabulü değildir. STATE Done yalnız aşama/plan
  kanıtına giden bir özet bağlantıdır, ikinci bir kayıt değil.
- STATE tablosu plan onayı değildir: zorunlu superpowers plan içeriği onayı kalır; onaylanmış aynı geçiş yeniden
  onaylanmaz. Bu şema yoksa borç/kanıt kaydını mevcut defterde tut.
- STATE üç başlığını korur: Done · Open items · Next. Claude Code, varsa bir SessionStart kancasıyla onu yükleyebilir;
  Codex başta elle okur.

Kurallar:
- **Hazır işi seç:** önkoşullar karşılanmış, kritik girdi yeterince belirli, mevcut yetki içinde. Bağımsız hazır işi
  paralel devret; başkasının çıktısını bekleyen işi başlatma. Belirsizlik engelliyorsa onu somut bir çözüm koşuluyla
  BACKLOG'a bağla ve öteki hazır işlere devam et. Ajan kapsam içindeki teknik ölçütleri seçebilir; klinik/bilimsel ve
  kişisel ölçütler kullanıcınındır (Karar kimde). Yetkiyi/kaynağı kaydet; yalnız kabul etmek için zorunlu bir hedefi ya
  da ölçütü asla gevşetme. Aşama başına onay yok.
- **Kanıtla kabul et:** çıktı önce `in review` olur; uygulayıcıdan ayrı inceleme ve ölçütü karşılayan kanıt olmadan
  `accepted` yok. Kanıt kaydı girdinin ve ölçütün sürümünü adlandırır; bilinmeyeni asla uydurma. Ayrı inceleme mevcut
  superpowers/inceleme ilkesine uyar; aşama başına yeni audit yok, kilit nokta kuralları değişmez.
- **Değişikliğin etkisini izle:** kritik bir girdi/sürüm, hedef ya da ölçüt esaslı biçimde değişirse yetkiyi kaydet,
  etkilenen kabulü `re-review needed` yap, bağımlı aşamalardaki etkiyi izle; yalnız etkilenen ölçütü/kanıtı yeniden
  denetle ve nedenini kaydet. İlgisiz değişiklik kabulü geçersiz kılmaz; eski kanıtı asla silme, ait olduğu sürümle
  tut.
- **Engeli ölçümden ayır:** bir araç/sağlayıcı eksik olduğu için koşmayan denetim gerçek bir red değil, `undetermined`
  sonucudur. Engel ve koşulu BACKLOG'a, ölçüm kaydı kanıt bağlantısına gider. Denetim kabulü engelliyorsa aşama
  `blocked` olur; bağımsız yetkili iş sürer. Aynı çağrıyı körlemesine tekrarlama; yalnız yeni bilgi ya da değişen koşul
  varsa dar biçimde yeniden denetle, yoksa hazır iş seç.
- **Aşamayı kapat:** kapsamdaki her madde kabul edilmiş ya da açıkça ertelenmiş olur; kalan borcu bağlantısıyla
  görünür tut. Zorunlu bir hedefi kaçıran erteleme, yetkili bir kapsam değişikliği olmadan kabul gerekçesi değildir.
  Kısmi erteleme ve eksik zorunlu ölçütle kabul yok; tamamen ertelenen aşama `deferred` olur. Yetkili bir
  kapsam/ölçüt değişikliğinde kaynağı ve güncel ölçütü yaz, yeniden doğrula. Ertelenmiş bir çıktıya ihtiyaç duyan
  tüketici aşama hazır değildir; önkoşulları gerçekten karşılanmış bağımsız iş sürer.
- **Son kapanış:** özgün hedef/kapsamı teslim edilenle karşılaştır; kabul kanıtını, açık borcu, `undetermined`
  ölçümleri ve erteleme yetkisini göster. "Bitti" sonucunu asla aşama sayısından ya da plan kutucuklarından çıkarma;
  karar ana oturumun / kullanıcının. Önceki açık izinler geçerlidir, aşama başına yeni onay yok; yeni
  bilimsel/klinik, dışa dönük ya da geri dönüşü zor kararlar onay kurallarına uyar (Karar kimde).
- **Bitti koşulu:** her yeni iş bitti koşulunu sohbette `Done when: <one sentence>` olarak söyler; bu satır işin kabul
  ölçütüdür.

Bunlar ajanın uyguladığı belge kurallarıdır, otomatik bir motor değil: zorunlu bir yaşam döngüsü dosyası, kanca ya da
dış araç bağımlılığı yaratmazlar ve mevcut projeler kendiliğinden taşınmaz.

### Eleştirmen ailesi: K1 aynı aile, K2 öbür aile

| Katman | Kim | Ne zaman | Neye bakar |
|---|---|---|---|
| K1, aynı aile | görev başına taze `explorer` (SDD görev inceleyicisi); dal sonunda son inceleme | her alt ajan teslimi | spec'e uyum + kod kalitesi |
| K2, öbür aile | Claude'dan: Codex (görev sınırında Sol, dal sonunda ve kilit noktalarda Astra); Codex'ten: Claude Opus (tek seçenek) | aşağıdaki iş türlerinde **zorunlu**; kilit noktalarda da (İkinci görüş) | öbür ailenin kör noktası, worker'ın test kanıtına karşı |

Aynı aileden eleştirmen iyidir ama öbür aileden bir eleştirmen de bulunmalı; önemli ve büyük işten sonra karşılığını
verir.

- **K2 zorunlu iş türleri:** çok görevli plan yürütmesi; motor dışında çok dosyalı değişiklik; şema / durum sözleşmesi
  ya da kapı değişikliği; dışa dönük çıktı. Rutin tek dosyalık düzeltmede K1 yeter.
- **Yerleşim:** varsayılan dal sonu. SDD Final Review'da son dal incelemesini `explorer` alt ajanı yapar; K2 aynı
  `review-package` dosyası üzerinde paralel koşar (`run_in_background`); ana oturum ikisini sentezler ve "bitti"
  demeden önce danışmana sorar. Codex'te danışman yoktur; orada dal sonu K2 (Claude Opus) sonucu ve ana oturumun
  sentezi onun yerini tutar ve Codex'ten Fable'a elle danışılmaz. Görev sınırı K2 yalnız planın Global
  Constraints'inde `K2: yes` işaretli görev için açılır: görev incelemesi temiz döndükten sonra, defterin "complete"
  satırından önce. Bu bir SDD adımıdır, kanca değil; her araç çağrısında ya da her ajan durduğunda koşmaz. Superpowers
  şablonları düzenlenmez.
- **Model ayrımı:** görev sınırı K2 varsayılan olarak Sol'dur (`--model sol`); dal sonu ve kilit nokta K2 Astra'dır
  (script'in varsayılanı). Codex'ten K2 Claude Opus'tur. [ölçüm 2026-11-07, 10 teslim × n=2, bilinen 5 kusur: yakalama
  oranı Sol/Astra/Opus 10/10; yanlış pozitif Sol 2, Astra 2, Opus 5; kolay set (tavan etkisi), maliyet ölçülmedi]
- **Dış sinyal:** K2 yalnız okuyarak hüküm vermez. Worker test kanıtını sağlar (koşulan komut, çıkış kodu, diff ya da
  `review-package`); K2 bu kanıtı spec'e karşı denetler. K2 testleri kendisi koşmaz; worker'ın kanıtını doğrular ve
  bir yeniden üretim adımı önerebilir. neden: test ya da koşu çıktısı olmadan öz eleştiri doğruluğu güvenilir biçimde
  artırmıyor [literatür]; sandbox nedeni için bkz. Bilinen sınırlar.
- **Bulgular** SDD'nin tek düzeltme dalgasına ve tek dar yeniden incelemesine girer; K2 yeniden koşmaz; düzeltmeyi
  testler + `explorer` doğrular. Yakınsama ve "hazır kararı eleştirmenin değil" kuralları geçerlidir (İkinci görüş,
  kural 3-4).
- **Çağrı:** `scripts/aile_elestirmen.py --effort medium|high --brief <file> --cikti <json> [--calisma-dizini <dir>]`
  (effort zorunlu; metodoloji kapılarında high; çalışma dizini varsayılan olarak geçerli dizindir). Codex yönü
  salt-okurdur: yazamaz, ama okuma çalışma dizinine kapalı değildir (sandbox okumayı değil yazmayı kısıtlar; buna geçici
  ev dizinindeki kimlik bilgisi kopyası da dahildir; dizin dışı okuma test edilmedi): brief'e ya da çalışma dizinine
  sır koyma. Öbür aile oturumdan çıkarılır (Claude'dan Codex, Codex'ten Claude); çıkarılamazsa `--aile codex|claude`.
  Claude'dan `--model astra|sol` (varsayılan astra). Claude yönü yalnız Read/Grep/Glob ile `--restricted` modunda koşar,
  dosya araçları çalışma dizinine kapalıdır. Sarmalayıcı temiz çağrıyı kurar, brief'te yoksa "find the weakest point
  ... say 'none'" cümlesini ekler, çıktıyı `scripts/elestirmen_sema.json`'a bağlar ve Codex kimlik bilgisi dosyasını
  güvenle geri yazar. Şemaya uymayan yanıt `undetermined` sayılır (çıkış 3); çıkış 77 "refresh token was already
  used" demektir: yeniden deneme, `codex login` koş. Elle kurulan komut (Claude Code'da › İkinci görüş) yedek yoldur;
  ayrıntı `scripts/README.md`'de.
- **Kayıt:** her aileler arası çağrıdan sonra projenin STATE'ine/defterine tek satır (SDD içinde plan defterine).
  `--kayit <file> --olay <short name>` ile (ikisi birlikte zorunlu) sarmalayıcı satırı kendisi yazar:
  `Cross-family <YYYY-MM-DD HH:MM> · <event> · <family> (<full id>) · <effort> · findings <n> (high <k>) · <output path>`
  (yanıt şema dışıysa bulgu sayısı yerine `undetermined (<reason>)`). Tarttıktan sonra ana oturum
  `· applied / parked (why)` ekler. neden: kayıt olmadan etkisi sonradan ölçülemez.

neden dal sonu: çok görevli bir plan yürütmesinde görev başı incelemeler temiz döndü, dal sonu okuması ise 8 (Astra) ve
4 (explorer) gerçek açık buldu [doküman]. Astra'nın varsayılan olması, audit rolünde ölçülen modelin o olmasındandır.

### İkinci görüş (audit): yalnız kilit noktalarda

Kilit nokta audit'i K2'nin özel bir halidir (Eleştirmen ailesi): aynı sarmalayıcı, aynı kayıt satırı. Kural 1, 3 ve 4
ikisine de uygulanır; bir K2 bulgusunun düzeltmesi yeniden K2 ile değil, testler ve `explorer` ile doğrulanır. K2'nin
zorunlu iş türleri kilit nokta listesine eklenir, onun yerine geçmez. Bir kilit nokta dal sonuyla çakışırsa tek K2
çağrısı ikisini de karşılar; aynı dalda ikinci audit yok; görev sınırı K2 (Sol) dal sonu K2'yi (Astra) iptal etmez.

Her işten sonra audit yok; ikinci bakışı mimari için önemli kilit noktalarda iste. Amaç ana oturumun ve danışmanın
kaçırabileceğini yakalamaktır (öbür ailenin kör noktası); kapı bekçisi değildir. **Alt ajanları kısmaz:** alt ajanlar
bağlam toplar, ana oturumu yalın tutar ve zaman kazandırır; daha az audit asla daha az devir ya da daha az inceleme
demek değildir.

Kilit noktalar:
- veri şeması / durum sözleşmesi değişikliği; kapı ya da güvence mantığı;
- geri dönüşü zor karar (mimari, veri kaybı riski, dışa dönük sözleşme);
- **kullanıcıya gitmeden önce bir planın ya da tasarımın son hali**, istatistiksel analiz planı, dışlama ölçütü, eksik
  veri planı taslağı dahil: karar kullanıcınındır; audit önce kör noktaları arar;
- dışa dönük çıktının son denetimi (makale, sunum, sürüm).

Kilit nokta olmayanlar: yerel düzeltmeler, görev başına inceleme (o `explorer`'ındır; `K2: yes` işaretli görevde ek
olarak K2), önceki bir audit'in bulgusunu kapatan düzeltme. Bunlar testlerle ve `explorer` ile ölçülür.

Kurallar:
1. **Kilit nokta başına tek audit.** Ana oturum bulguları tartar (asla körlemesine uygulamaz); kabul edilen düzeltmeler
   audit yeniden koşularak değil, **testler + `explorer`** ile doğrulanır.
2. **En çok bir dar yeniden denetim**, yalnız bir bulgu bir mekanizmanın yeniden yazılmasını zorladıysa; kapsam o
   mekanizmadır.
3. **Yakınsama kuralı:** turlar yeni bulgu üretmeye devam ediyorsa bu bir tasarım sinyalidir. Yeni tur açma; kalan
   açıkları gerekçeleriyle bir karar olarak kullanıcıya getir.
4. **"Hazır mı" kararı audit'in değildir**; ana oturum ve kullanıcı karar verir. Brief asla "ready to execute: yes/no"
   diye sormaz; bulgu, şiddet ve kanıt ister.

neden [ölçüm 2026-09-26, çok aşamalı tek plan]: 20 saatte 5 audit, yeni bulgu eğrisi 12 → 5 → 1 → 2 → 1; her brief
"hazır mı?" diye sordu, her rapor "hayır" dedi. İşi yavaşlatan audit'in kendisi değil, audit'i kapı yapmaktı (ilki
gerçek bir hata yakaladı).

İnceleyiciler tek adıma üst üste konmaz; istisna, dal sonu paketini paralel okuyan K1 ve K2'dir. Kim ve ne zaman:
Eleştirmen ailesi tablosu; danışman (Claude'da Fable: yön, yaklaşım, takılma): "Danışman (Claude tarafı)".

### Superpowers ile: "nasıl" oradan, "kim" bu ağaçtan

Superpowers süreci sağlar (plan, önce test, görev başına taze ajan, ayrı inceleme, kanıtsız "bitti" yok); onu koru.
Ajan tipi ve model **yalnız bu ağaçtan** gelir: `Subagent (general-purpose):` bir yer tutucudur ve "Model Selection"
tanımadığı kullanıcılar için tasarruflu bir varsayılandır; superpowers kullanıcı talimatlarını skill'lerin üstünde
tutar. Superpowers'ı kaldırmak reddedildi (büyük bir plan bu süreçle yürüdü). Tetiklenmediğinde de ikisini birlikte
kullan.

Tablo superpowers 7.0.0 (2026-11-07) için yazıldı. Sürüm bekçisi `hooks/superpowers_surum_bekcisi.py` (SessionStart,
Claude ve Codex) kurulu sürüm farklıysa "re-audit the mapping table" notu ekler; yeniden denetledikten sonra
`hooks/superpowers_surum.json` içindeki `tablo_surumu` ve `tarih` alanlarını güncelle. `ORCH_SURUM_BEKCISI=0` kancayı kapatır.

| Superpowers'ta | Burada |
|---|---|
| implementer / task executor | `worker` |
| task reviewer (tek inceleyici, spec + kalite) ve kapsamı daraltılmış yeniden inceleme | `explorer` (salt-okur) |
| brainstorming "builder check" (taze okur) | `explorer`; writing-plans öz incelemesi ajan açmaz |
| dispatching-parallel-agents ajanları | `worker` (salt-okursa `explorer`) |
| son bütün dal incelemesi, SDD Final Review ("most capable model") | `explorer` alt ajanı (ana oturum aktif iş yapmaz); zorunlu iş türünde ya da kilit noktada aynı `review-package` üzerinde paralel K2 (Eleştirmen ailesi); ana oturum ikisini sentezler, "bitti"den önce danışman (Codex karşılığı: Eleştirmen ailesi › Yerleşim) |
| "Model Selection" (cheap / standard / most capable) | yok say; model ajan dosyasından gelir; `model` parametresi yazma |
| bütün SDD döngüsünü yürüten tek orkestratör alt ajanı | kullanma; orkestratör ana oturumdur (kendi işi için yardımcı açan alt ajan sorun değil) |
| SDD "Always specify the model explicitly" | `model` parametresi yazma; ajan dosyası belirler (kapı Opus dışını reddeder) |
| düzeltme döngüsünde SDD "escalate to a more capable model" | yükseltme yok (alt ajanlar için Opus'un üstü yok); tıkanan görevi yeni brief'le yeniden devret ya da danışmana sor |
| SDD "the controller never fixes a finding itself" | düzeltmeyi worker yapar; devir güvenilmezse ana oturum yeni brief'le yeniden devreder ya da danışmana sorar, asla kendisi düzeltmez |
| writing-plans "Native: I implement each task myself" seçeneği | sunma; yürütme varsayılan olarak alt ajan güdümlüdür ve yürütme yöntemi sorulmaz; plan içeriği onayı ayrı bir kapıdır ve sorulur |
| using-git-worktrees konum seçimi | proje içi `.worktrees/` ya da aracın proje içi klasörü (Claude Code `.claude/worktrees/`); merge sonrası kaldır (Sınırlar › Worktree) |
| finishing-a-development-branch temizliği | `git worktree remove` öncesi `git status --porcelain --ignored` taraması + arşiv (Sınırlar › Worktree); dal yalnız `-d`, asla `-D` |
| brainstorming "MUST use before any creative work" | geçerli; her yeni iş önce **bitti koşulunu** (gözlenebilir, tek cümle) ve **neyi yapmayacağını** (kapsam dışı) yazar; öğrenme kipi durakları [profil] |
| implementer "Commit your work", writing-plans görev başı commit adımı | geçerli: worker kendi worktree'sinde/özellik dalında commit eder; main'e birleştirme ve push ana oturumundur (Sınırlar) |
| implementer ve reviewer ajan açamaz ("You Do Not Dispatch Subagents") | SDD içinde superpowers kuralı geçerli; SDD dışında worker yardımcı açabilir (Sınırlar › İç içe) |
| SDD "Never dispatch multiple implementation subagents in parallel" | aynı plan ve ağaç içinde sıralı; bağımsız bir alanda ya da ayrı worktree'de "Bağımsız işi çoğalt" geçerli |
| SDD "Rulings, not stalls": yalnız dört durma nedeni | ek olarak bilimsel/klinik eşiklerde, dışlama ölçütlerinde, kişisel tercihlerde ve dondurulmuş protokol çekirdeğinde dur; karar kullanıcıya gider (Karar kimde) |
| Codex: her `spawn_agent`'a `model` ve `reasoning_effort` yaz (using-superpowers Codex araç notu) | model/effort'u rol dosyası taşır; açılışta geçersiz kılma yok, `fork_turns="none"` geçir, asla `default` rolü (Codex'te) |
| plan Global Constraints `K2: yes` (controller okur) | işaretli görevler için görev sınırı K2; işaretsizlere yok (Eleştirmen ailesi) |

**Çatışmada bu skill kazanır.** Tabloda olmayan yeni bir çatışma çıkarsa bu skill'in kuralını uygula ve bir satır ekle.
Superpowers ayrı bir eklenti olarak kalır ve bu skill'e katılmaz: katmak sürümlü bir eklentiyi çatallar ve upstream
güncellemelerini kaybettirir; çatışmalar bu tabloyla çözülür, eskimeyi sürüm bekçisi yakalar. Görev başına
taze ajan, uygulayıcıdan farklı bir inceleyici ve inceleme kapısı geçilmeden sonraki göreve geçmeme kuralı korunur. Codex
aynı rol adlarını kullanır.

### Danışman (Claude tarafı)

Koşullu: Claude Code'un `advisor` aracını ister (`advisorModel` ayarlı; yalnız Anthropic API). Sende yoksa bu bölümü
atla; "danışmana sor" geçen her yerde Codex karşılığını kullan (dal sonu K2 artı ana oturum sentezi).

Ana oturum şu olaylardan **hemen önce** danışır (karşılığını plan/mimari kararlarında verir):

| Aile | Olay |
|---|---|
| Kullanıcı görmeden önce | yöntem/mimari düzeyinde yaklaşım seçimi (her tasarım alt sorusu değil) · son spec/tasarım · bilimsel/klinik seçenekler (SAP, eşik, dışlama) |
| Yürütme başlamadan önce | onaylı kapsamda yeni bileşen/yazma yolu/yetenek (değişiklik paketi başına bir kez) · plan commit → ilk worker · şema/durum sözleşmesi/kapı mantığı birleştirmesi (değişiklik başına bir kez) · bir inceleme bulgusu mekanizmanın yeniden yazılmasını zorlar · kullanıcının süreç düzeltmesi yöntemi değiştirir |
| Geri dönülmezden önce | devir notu · "bitti" / main'e birleştirme · push/sürüm |
| Takılınca | aynı hata ikinci kez · bulgular yakınsamıyor |

- **Bir şeye danışmak sonrakini kapsamaz:** yaklaşım, spec, kapsam değişikliği, plan, sözleşme birleştirmesi ve devir
  ayrı olaylardır. Aynı olay için ikinci çağrı yalnız yeni kanıtla. Kural kitabı, sözleşme ya da geri dönüşü zor
  değişiklik sohbet içinde verilse de "büyük plan" sayılır. neden [ölçüm 2026-10-11, oturum logları]: 8 oturumun 5'inde
  son danışma oturumun ilk %59'luk kısmında kaldı; bir aşamada 6 saat 1 danışmayla geçti, kapsam büyümesi ve 22 görevlik plan
  danışmasız kaldı (çıkarım: eski üç tetik bir kez karşılanınca "yapıldı" sayıldı).
- **Astra ile sıra:** spec ve bilimsel/klinik seçeneklerde önce danışman ("doğru yaklaşım bu mu"), sonra Astra ("son
  metinde ne yanlış"); aynı soruyu tekrarlamazlar.
- **Kayıt:** her danışmadan sonra projenin STATE'ine/defterine tek satır:
  `Advisor <date time> · <event> · <advice summary> · applied / not applied (why)`. neden: tavsiye metni logda
  şifrelidir; kayıt olmadan etkisi ölçülemez.
- **Kendi mesajında çağır:** başka bir araç çağrısıyla aynı mesaja konan danışman çağrısı koşmaz ve yeniden
  gönderilmesi gerekir [ölçüm n=3 oturum, 2026-10-11; mekanizma belgelenmemiş].
- "Bitti"den önce çıktıyı önce dosyaya yaz, sonra danış. Araç bu oturumda yoksa kullanıcıya söyle; asla danışmış gibi
  davranma. `/advisor` modeli seçer (fable/opus/sonnet/off); bir soru sorma yolu değildir.
- **Maliyet:** danışman çağıranın transkriptini önbelleksiz yeniden okur [doküman code.claude.com/docs/en/advisor];
  çağrı başına maliyet transkript boyuyla büyür (bir oturum: 119k → 652k) [ölçüm]. Uzun bir geçmiş aşamaya geriye dönük
  bakıldığında çekirdek liste ≈7 çağrı / ≈3 M token, 12 olaylık tam liste 21 / ≈7,2 M token demekti; bu yüzden
  çekirdek liste seçildi.
- **Alt ajanlar serbestçe danışır.** Zaten teknik bir kilit yok: `tools`/`disallowedTools` sunucu aracını etkilemez ve
  tek anahtar (`CLAUDE_CODE_DISABLE_ADVISOR_TOOL`) ana oturum için de kapatır [doküman + ölçüm 2026-10-11].

### Görsel üretimi

Görsel gerektiren her iş Codex modellerini kullanır; Claude modelleri görsel üretmez. Her iki durumda da çizimi
Codex'in yerleşik görsel aracı yapar; istemi ve denetimi model belirler. Önem kademesinde [profil] dışa dönük ya da
önemli görseller Astra'ya, rutin olanlar Sol'e gider. Claude'dan ajan görseli Bash üzerinden bir Codex çağrısıyla ister;
ayrı ajan tipi yok: `scripts/gorsel_uret.py` (`--istem` ya da `--istem-dosyasi`, `--cikti` PNG yolu, `-i` referans
görsel, tekrarlanabilir; `--model astra|sol`, varsayılan astra; `--effort low|medium|high`). Görsel aracı Sol'de çalışır
[ölçüm 2026-11-07, `gorsel_uret.py --model sol`, 30 s].

## Claude Code'da

- Alt ajanlar **`explorer` / `worker` / `researcher`** (`model: opus`, `effort: medium`) ve salt-okur
  arama/yapı dökümü/özet için `scanner`'dır (`model: sonnet`, `effort: medium`). Kullanıcı düzeyi kurulum
  (`~/.claude/agents/`): düz adlar (`explorer`); eklenti kurulumu: `orchestration:explorer`, `orchestration:worker`,
  `orchestration:researcher`, `orchestration:scanner`. İki biçim de aynı ajandır; bu dosyadaki çıplak adlar ikisini de
  kapsar. Kendi uzman ajanlarını (ör. bir literatür tarayıcısı) aynı ayarlarla ekle; kapı yerleşik olmayan her tipe
  izin verir.
- **Yerleşik `Explore` / `general-purpose` kullanma**: `effort` taşımazlar ve ana oturumun high düzeyini miras alırlar.
  **`fork` kullanma**: model ayarını yok sayar ve ana oturumu kopyalar.
- **Kapı:** `hooks/agent-tip-kapisi.py` (PreToolUse `Agent|Task`) `general-purpose`, `Explore`, `Plan`, `claude`,
  `fork` ve boş tipi reddeder (büyük-küçük harf ayrımı yok; `<eklenti>:<ajan>` biçimindeki tipte son parçaya bakılır).
  Değeri `opus` olmayan ve `claude-opus-` ile başlamayan her `model` parametresini de reddeder, alt ajanların içinde
  de. Düz adları da `orchestration:` önekli ajan adlarını da kabul eder. `ORCH_TIP_KAPISI=0` kapıyı kapatır
  (kullanıcının anahtarıdır, aracın başladığı ortamda ayarlanır; her ret mesajı bunu söyler). Reddederse doğru tiple
  yeniden aç; kullanıcı başka bir tip istediyse ona kapıyı anlat, kapıyı asla kendin gevşetme.
- `model` parametresi yazma; modeli ajan dosyası belirler (kapı Opus dışını reddeder). Sonnet gerekirse parametre değil
  `scanner` tipini kullan. Fable asla alt ajan olarak açılmaz; yalnız danışmandır.
- **Danışman:** `advisor` aracı (`~/.claude/settings.json` → `advisorModel: "fable"`); `/advisor` değişikliği geçerli
  sohbette ancak `/clear` ya da `/compact` sonrasında etkili olur.
- **Effort mirası:** üst düzey `effortLevel`'ı asla high'ın altına ayarlama: `modelSettings` girdisi olmayan yeni bir
  Opus/Fable sessizce o değere düşer. Yeni sürümde effort'u sürecin içinden ölç (`printenv CLAUDE_EFFORT`).
- **İkinci görüş, Astra audit'i.** Yalnız script kullanılamıyorsa ve aynı anda başka bir Codex çağrısı koşmuyorsa
  yedek yol: script (`scripts/aile_elestirmen.py`) kimlik bilgisi yazımını kilitler, bu blok kilitlemez.
  `ORCH_CODEX_BIN` gerçek `codex` ikili dosyasını gösterir, böylece PATH üzerindeki bir sarmalayıcı atlanır.
  ```bash
  R=~/.codex/auth.json; H=$(mktemp -d); cp "$R" "$H"/ && chmod 600 "$H"/auth.json; S0=$(shasum -a 256 < "$H"/auth.json)
  CODEX_HOME="$H" "${ORCH_CODEX_BIN:-codex}" exec --skip-git-repo-check --ephemeral --disable hooks --disable memories \
    -m gpt-6-astra -c model_reasoning_effort=medium --sandbox read-only "<audit brief>" < /dev/null
  if [ -f "$H"/auth.json ] && ! cmp -s "$H"/auth.json "$R"; then
    if [ "$(shasum -a 256 < "$R")" = "$S0" ]; then cp "$H"/auth.json "$R.tmp.$$" && chmod 600 "$R.tmp.$$" && mv "$R.tmp.$$" "$R"
    else echo "WARNING: auth.json changed in another process during the call; not written back (run codex login if needed)" >&2; fi
  fi; rm -rf "$H"
  ```
  Geri yazma zorunludur: geçici ev dizininde yenilenen token yalnız orada kalır; eski refresh token tek kullanımlıktır,
  bu yüzden `~/.codex/auth.json` geçersizleşir ve sonraki her çağrı "refresh token was already used" hatasıyla düşer
  (çözümü `codex login`). Yalnız gerçek dosya çağrı başladığından beri değişmediyse, atomik olarak (`mv`), 0600 ile
  geri yaz; başka bir oturumun yenilemesinin üstüne asla yazma (kilitsiz; yalnız aynı anda başka Codex çağrısı
  koşmuyorsa güvenli; script yolu kilitlidir). [ölçüm 2026-11-06, tek oturum: ilk Astra çağrısı geçti, ikincisi düştü]
  neden temiz çağrı: PATH üzerindeki bir sarmalayıcı kancaları zorla açabilir (`--enable hooks`), bu yüzden açık
  `--disable hooks`; `--ignore-user-config` kancaları ya da `~/.codex/AGENTS.md`'yi dışarıda tutmaz; geçici ev
  dizininde yapılandırma yoktur, bu yüzden model/effort/sandbox komut satırına yazılır; `< /dev/null` zorunludur (yoksa
  stdin'i bekler). [ölçüm 2026-10-02, sızıntı denetimi 4/4 → bu kalıp 0/4] `run_in_background` ile aç ve bağımsız işe
  devam et. Effort'u her zaman yaz (`medium`; metodoloji kapılarında `high`): bazı filo araçları ve sarmalayıcılar
  varsayılan olarak high kullanır.
- **Codex uygulayıcısı (Sol):** dar brief'li mekanik işte Sol uygulayabilir: ayrı worktree, somut kabul ölçütü,
  `worker` gibi test kanıtı döner (komut, çıkış kodu, diffstat, file:line). Zor ya da hassas iş Opus `worker`'da kalır.
  (gözleme dayanarak gevşetildi, pilot yapılmadan)
- **Bağlam tasarrufu araçları yarışır:** bir komut koşup yalnız özet döndüren bir MCP aracıyla işi böl: geniş dosya
  keşfi → alt ajan; tek komutun büyük çıktısı → o araç. Aynı işi asla iki kez yapma.

## Codex'te

- Alt ajanlar **`explorer` / `worker` / `researcher` / `scanner`** rolleridir (`~/.codex/agents/*.toml`, hepsi Sol,
  `medium`); Codex eklentisi ajan rolü taşıyamaz, bu yüzden `install.sh` onları deponun `codex/agents/` klasöründen
  oraya kopyalar (bkz. README). Kendi rollerini de aynı yolla ekle. Rol dosyasında bir `model` satırı olmalı; rol
  modeli yalnız `spawn_agent` üzerinde `fork_turns="none"` ile uygulanır (aşağıda). **`default` rolünü kullanma**: ana
  oturumun modelini (Astra high) miras alır.
- **Rol ajanlarını `fork_turns="none"` ile aç.** `fork_turns` yazılmazsa ya da `"all"` ise çocuk ajan ebeveynin modelini
  ve effort'unu miras alır (Astra ana oturum Astra alt ajan verir); `"none"` ile rol dosyasının modeli ve effort'u
  uygulanır. Gereken bağlamı brief'e koy. `model` / `reasoning_effort` geçersiz kılması yazma. [ölçüm 2026-11-07, 59
  alt ajan oturumu: `"none"` 28/28 Sol; Astra ebeveynle yazılmamış ya da `"all"` 30/30 Astra; Sol ebeveynle `"all"` 1
  oturum, çocuk Sol (ebeveyn modeli miras)]; kaynak kod dayanağı doğrulanmadı.
- **Sol, Opus'tan zayıftır** (Sol 6 / Opus 5.5 ile gözlendi; yeni sürümlerde yeniden denetle): dar, açık brief'ler,
  somut kabul ölçütleri. Mekanik iş ayrı worktree'de test kanıtıyla `worker`'a (Sol) gider; zor/hassas iş ana oturumda
  kalır (Devir › Codex istisnası).
- Birden çok ajanla çalışırken her birine yalnız olmadığını ve başkalarının işini geri almaması gerektiğini söyle; alt
  ajanlar yalnız bu rolleri açar. Biten ajanları kapat. Yeni rol yeni oturum ister.
- **Model kimliği:** Codex'te kayan takma ad yok [ölçüm 2026-09-25]; yapılandırmaya aile adını değil tam kimliği yaz
  (`scripts/modeller.json`, rol dosyaları).
- **Danışman yok.** Codex'ten Fable'a elle danışılmaz (Fable kıt kalır). "Bitti öncesi danışman" yerine: Eleştirmen
  ailesi › Yerleşim.
- **Eleştirmen ailesi:** K1 = taze Sol `explorer`; K2 = `scripts/aile_elestirmen.py` üzerinden Claude Opus (Codex
  oturumundan öbür aile kendiliğinden Claude'dur; çıkarılamazsa `--aile claude`). Zorunlu iş türleri, yerleşim (dal
  sonu, `K2: yes` işareti), dış sinyal, tek düzeltme dalgası ve kayıt satırı Ortak ilke › Eleştirmen ailesi'ndeki
  gibidir; kilit nokta audit'i K2'nin özel halidir.
- **Aktif iş ve izinli iş:** Devir listesi Codex ana oturumu (Astra) için de geçerlidir. Okuma bütçesi kancası
  (`hooks/okuma_butcesi.py`) Codex'te de koşar ve yalnız kabuk komutlarını sayar (orada dosya okumaları kabuk
  komutudur). Onu `hooks/codex-parcasi.json`'dan Codex'in `hooks.json` dosyasına kaydet; Codex yeni ya da değişmiş bir
  kancayı ancak Codex içinde `/hooks` ile güvendikten sonra koşar (`hooks/README.md`).
- **Mekanik iş:** `scanner` rolü (Sol) script çıktısı aktarımını, test/log özetlerini, envanteri ve çağrı izlerini
  alır; belge/kaynak doğrulaması `researcher`'ındır. Luna ölçülmedi; alt kademe kuralı geçerli (yalnız kullanıcı
  söylerse) [profil].
- **Görsel üretimi:** ana oturum yerleşik görsel aracını doğrudan kullanır (önemli görseller); gerekirse Sol'de bir alt
  ajan (rutin görseller) [ölçüm 2026-11-07, `gorsel_uret.py --model sol`, 30 s].
- **Superpowers sürüm bekçisi:** `hooks/superpowers_surum_bekcisi.py` Codex'te de SessionStart'ta koşar (kayıt ve
  `/hooks` güveni okuma bütçesindeki gibi); sürümler farklıysa "re-audit the table" notu ekler.
- **Yükleme hatırlatıcısı:** `hooks/orkestrasyon_hatirlatici.py` Codex'te de PreToolUse'da koşar
  (`^(spawn_agent|Agent)$`); kayıt ve `/hooks` güveni okuma bütçesindeki gibi (ancak güvendikten sonra koşar).
- **İkinci görüş, Claude audit'i.** `scripts/aile_elestirmen.py` kullanılamıyorsa yedek yol:
  ```bash
  claude -p --model opus --tools Read,Grep,Glob --permission-mode dontAsk --no-session-persistence \
    --strict-mcp-config --restricted "<audit brief>"
  ```
  Brief'te salt-okur olduğunu ve dosya değiştirmemesi gerektiğini açıkça yaz. Claude erişimi yoksa Codex'ten K2 yok;
  aileler arası denetimleri sessizce atlamak yerine `undetermined` olarak kaydet.

## Bilinen sınırlar

- **Codex salt-okur sandbox'ı:** okumayı değil yazmayı kısıtlar (okuma çalışma dizinine kapalı değildir) ve test
  koşamaz ("No usable temporary directory") [ölçüm 2026-11-07]. K2'nin test koşmak yerine worker'ın kanıtını
  doğrulamasının nedeni budur.
- **Claude `--restricted` ve CLAUDE.md:** `--restricted` ayar dosyalarını yok sayar, ama CLAUDE.md belleğinin (kullanıcı
  ve proje) yüklenmesini de durdurup durdurmadığı doğrulanmadı. Durdurmuyorsa eleştirmen yazar oturumun talimatlarını
  paylaşır ve o ölçüde daha az bağımsızdır.
- **Python:** script'ler ve kancalar Python 3.9+ ister; `tomllib` (3.11+) yalnız superpowers sürüm bekçisinin Codex
  dalında kullanılır. 3.9-3.10'da o dal sessiz kalır.
