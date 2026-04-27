# E-Dönüşüm Modülü V2 Test Dokümanı — Danışman Ekip

**Modül:** E-Dönüşüm (edonusum)  
**Platform:** Odoo 18  
**Güncellenme Tarihi:** Haziran 2025 (V2) / Nisan 2026 (V2.1 — Hata Yönetimi) / Temmuz 2025 (V2.2 — İrsaliye Güncellemeleri)  

---

## 1. Test Öncesi Hazırlık

### 1.1 Gerekli Bilgiler

Test öncesinde aşağıdaki bilgilerin hazır olduğundan emin olun:

- Odoo test ortamına erişim (kullanıcı adı / şifre)
- En az 2 müşteri kaydı (biri VKN'li, biri TCKN'li)
- En az 3 ürün kaydı
- QNB eFinans test hesabı bilgileri (test modunda çalışılacak)

### 1.2 Şirket Ayarları Kontrolü

| Ayar | Kontrol Noktası |
|------|----------------|
| KDV Tevkifat Alt Sınır | 6.900 TL olarak ayarlanmış mı? |
| QNB Test Modu | "Açık" konumda mı? |
| QNB Test URL | Dolu mu? |

---

## 2. Senaryo Testleri

### TEST-S01: Ticari Fatura — Satış

**Amaç:** Mevcut temel akışın çalıştığını doğrulamak

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Muhasebe → Müşteri Faturaları → Yeni | Fatura formu açılır |
| 2 | Müşteri seçin | Müşteri bilgileri yüklenir |
| 3 | Senaryo: **Ticari Fatura** | Senaryo seçilir |
| 4 | Tip: **Satış** | Tip seçilir |
| 5 | En az 1 satır ekleyin (ürün + miktar + fiyat) | Satır eklenir |
| 6 | **Onayla** butonuna basın | Fatura onaylanır, hata yok |
| 7 | **e-Fatura Gönder** butonuna basın | GIB'e gönderilir (test ortamı) |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-S02: Temel Fatura — İade

**Amaç:** İade faturasında referans fatura zorunluluğunu test etmek

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Yeni fatura oluşturun | - |
| 2 | Senaryo: **Temel Fatura**, Tip: **İade** | - |
| 3 | Referans fatura alanını **boş bırakın** | - |
| 4 | **Onayla** butonuna basın | ❌ **HATA bekleniyor:** "İade faturalarında referans fatura bilgisi zorunludur" |
| 5 | Referans fatura bilgisini doldurun | - |
| 6 | Tekrar **Onayla** butonuna basın | ✅ Fatura onaylanır |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-S03: İhracat Faturası — Geçersiz Tip

**Amaç:** Yanlış senaryo-tip kombinasyonunun engellendiğini test etmek

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Yeni fatura oluşturun | - |
| 2 | Senaryo: **İhracat** | - |
| 3 | Tip: **Tevkifat** seçmeye çalışın | Tip listesinde Tevkifat görünMEMEli |
| 4 | (Eğer bir şekilde seçebildiyseniz) **Onayla** butonuna basın | ❌ **HATA bekleniyor:** "Geçersiz senaryo-tip kombinasyonu" |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-S04: Kamu Faturası — IBAN Kontrolü

**Amaç:** Kamu senaryosunda IBAN zorunluluğunu test etmek

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Yeni fatura, Senaryo: **Kamu**, Tip: **Satış** | - |
| 2 | "Senaryo Detayları" bölümünde **Kamu IBAN** alanını görün | Alan görünür olmalı |
| 3 | IBAN alanını **boş bırakarak** Onayla | ❌ **HATA:** "KAMU senaryosunda IBAN zorunludur" |
| 4 | IBAN alanını doldurun (örn: TR330006100519786457841326) | - |
| 5 | Tekrar Onayla | ✅ Fatura onaylanır |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-S05: Yatırım Teşvik Faturası (YENİ)

**Amaç:** Yeni Yatırım Teşvik senaryosunun tam akışını test etmek

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Yeni fatura, Senaryo: **Yatırım Teşvik** | Senaryo listesinde görünür |
| 2 | "Senaryo Detayları"nda **YTB No** alanını görün | Alan görünür, diğer alanlar (İDİS, Pasaport vb.) gizli |
| 3 | Tip: **Satış** seçin | Kullanılabilir tipler: Satış, İstisna, İade, Tevkifat, Tevkifat İade |
| 4 | YTB No'yu **boş bırakarak** Onayla | ❌ **HATA:** "YTB No zorunludur" |
| 5 | YTB No: **ABC** girin, Onayla | ❌ **HATA:** Format hatası |
| 6 | YTB No: **B/025/001** girin | - |
| 7 | Satıra ürün ekleyin, **Harcama Tipi** ve **Makine Adı** doldurun | - |
| 8 | Onayla | ✅ Fatura onaylanır |
| 9 | e-Fatura Gönder | ✅ XML üretilir ve gönderilir |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-S06: İDİS Faturası (YENİ)

**Amaç:** Yeni İDİS senaryosunun tam akışını test etmek

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Yeni fatura, Senaryo: **İDİS** | Senaryo listesinde görünür |
| 2 | "Senaryo Detayları"nda **İDİS Sevkiyat No** alanını görün | Alan görünür |
| 3 | Sevkiyat No: **boş** → Onayla | ❌ **HATA:** "Sevkiyat No zorunludur" |
| 4 | Sevkiyat No: **ABC** → Onayla | ❌ **HATA:** Format hatası |
| 5 | Sevkiyat No: **SE-1234567** girin | - |
| 6 | Satıra ürün ekleyin, **İDİS Etiket No** doldurun | - |
| 7 | Onayla | ✅ Fatura onaylanır |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-S07: İlaç / Tıbbi Cihaz Faturası (YENİ)

**Amaç:** Güncellenen İlaç/Tıbbi Cihaz senaryosunu test etmek

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Yeni fatura, Senaryo: **İlaç/Tıbbi Cihaz** (yeni sürüm) | Listede görünür |
| 2 | Eski "İlaç/Tıbbi Cihaz" kaydı | Listede görünMEMEli (deaktif) |
| 3 | Satırlarda **İlaç/Tıbbi Cihaz Türü** doldurmadan Onayla | ❌ **HATA:** "En az 1 satırda ilaç/tıbbi cihaz türü zorunludur" |
| 4 | Bir satırda Tür: **İlaç**, Karekod: bir değer girin | - |
| 5 | Onayla | ✅ Fatura onaylanır |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-S08: HKS Faturası — Künye No Kontrolü

**Amaç:** HKS senaryosunda künye numarası zorunluluğunu test etmek

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Yeni fatura, Senaryo: **HKS**, Tip: **HKS Satış** | - |
| 2 | Satırlarda **HKS Künye No** doldurmadan Onayla | ❌ **HATA:** "En az 1 satırda künye no zorunludur" |
| 3 | Bir satırda Künye No girin → Onayla | ✅ Fatura onaylanır |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-S09: Teknoloji Geliştirme Desteği (YENİ)

**Amaç:** Yeni TEKNOLOJIDESTEK tipini test etmek

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Yeni fatura, Senaryo: **e-Arşiv**, Tip: **Teknoloji Geliştirme Desteği** | - |
| 2 | Alıcı olarak **TCKN'si olmayan** partner seçin → Onayla | ❌ **HATA:** "TEKNOLOJIDESTEK faturalarında alıcı TCKN zorunludur" |
| 3 | Alıcı olarak **TCKN'li** partner seçin | - |
| 4 | Satırlarda **Teknoloji Cihaz Tipi** doldurmadan Onayla | ❌ **HATA:** "En az 1 satırda cihaz tipi zorunludur" |
| 5 | Bir satırda Cihaz Tipi: **Bilgisayar** seçin | - |
| 6 | Onayla | ✅ Fatura onaylanır |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-S10: YTB Satış / İade (e-Arşiv) (YENİ)

**Amaç:** Yeni YTB e-Arşiv tiplerini test etmek

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Yeni fatura, Senaryo: **e-Arşiv**, Tip: **YTB Satış** | Tip seçilebilir |
| 2 | Satır ekleyip Onayla | ✅ Fatura onaylanır |
| 3 | Yeni fatura, Senaryo: **e-Arşiv**, Tip: **YTB İade** | - |
| 4 | Referans fatura **boş** → Onayla | ❌ **HATA:** "İade faturalarında referans zorunludur" |
| 5 | Referans doldurup Onayla | ✅ |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-S11: SGK Faturası — VKN Kontrolü

**Amaç:** SGK faturasında alıcı VKN kontrolünü test etmek

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Yeni fatura, Senaryo: **e-Arşiv**, Tip: **SGK** | - |
| 2 | Alıcı olarak **rastgele** bir müşteri seçin → Onayla | ❌ **HATA:** "SGK faturalarında alıcı VKN 7640235439 olmalıdır" |
| 3 | Alıcı: VKN'si **7640235439** olan müşteri → Onayla | ✅ Fatura onaylanır |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-S12: Yolcu Beraber Faturası — Pasaport

**Amaç:** YOLCUBERABERFATURA senaryosunda pasaport bilgilerini test etmek

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Yeni fatura, Senaryo: **Yolcu Beraber** | - |
| 2 | "Senaryo Detayları"nda **Pasaport No** ve **Uyruk** alanlarını görün | Her iki alan görünür |
| 3 | Pasaport ve uyruk bilgilerini doldurun | - |
| 4 | Onayla → e-Fatura Gönder | ✅ Fatura onaylanır ve gönderilir |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

## 3. Senaryo Değişikliği Testi

### TEST-D01: Senaryo Değiştirme — Tip Temizlenmesi

**Amaç:** Senaryo değiştirildiğinde uyumsuz tipin temizlendiğini doğrulamak

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Senaryo: **Ticari Fatura**, Tip: **Satış** | - |
| 2 | Senaryoyu **HKS** olarak değiştirin | Tip alanı otomatik **temizlenir** |
| 3 | Tip alanını açın | Sadece **HKS Satış** ve **HKS Komisyoncu** görünür |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-D02: Koşullu Alanların Görünürlük Geçişi

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Senaryo: **Yatırım Teşvik** | YTB No alanı görünür |
| 2 | Senaryo: **İDİS** olarak değiştirin | YTB No gizlenir, Sevkiyat No görünür |
| 3 | Senaryo: **Kamu** olarak değiştirin | Sevkiyat No gizlenir, IBAN görünür |
| 4 | Senaryo: **Ticari Fatura** olarak değiştirin | Tüm koşullu alanlar gizlenir |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

## 4. GIB İletim Takibi Testleri

### TEST-G01: İletim Durum Çubuğu

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Onaylanmış faturayı açın | **İletim Durumu** bölümü görünür |
| 2 | Durum çubuğunu kontrol edin | Mevcut durum renklı olarak işaretli |
| 3 | İletim Tarihi | Gönderim sonrasında otomatik dolu |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-G02: Red Durumu

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Bir faturanın durumunu "Red Edildi" yapın | - |
| 2 | **Red Nedeni** alanını kontrol edin | Alan görünür olur |
| 3 | Red nedenini girin | Kaydedilir |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-G03: XML Arşiv İndirme

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Gönderilmiş bir faturayı açın | - |
| 2 | **XML Arşiv** alanını kontrol edin | İndirme butonu görünür |
| 3 | İndirin | Geçerli XML dosyası indirilir |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

## 5. Şirket Ayarları Testleri

### TEST-A01: KDV Tevkifat Alt Sınır

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Ayarlar → Şirketler → Şirket seçin → E-Dönüşüm Ek Ayarları | Bölüm görünür |
| 2 | "KDV Tevkifat Alt Sınır" alanını kontrol edin | Varsayılan: **6.900,00 TL** |
| 3 | Değeri **7.500,00** olarak değiştirin → Kaydedin → Yeniden açın | Değer korunmuş |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-A02: QNB Bağlantı Ayarları

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Ayarlar → Şirketler → QNB eFinans Bağlantı Ayarları | Bölüm görünür |
| 2 | Test Modu: Açık, Test URL doldurun → Kaydet | Kaydedilir |
| 3 | Yeniden açın | Değerler korunmuş |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

## 6. Satır Alanları Testleri

### TEST-L01: Opsiyonel Kolonları Açma

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Fatura satırları tablosunda sağ üst köşedeki kolon ayarlarını açın | - |
| 2 | "İlaç/Tıbbi Cihaz Türü" kolonunu açın | Kolon görünür |
| 3 | "YTB Harcama Tipi" kolonunu açın | Kolon görünür |
| 4 | Değer girin → Kaydedin → Yeniden açın | Değerler korunmuş |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

## 7. Süre Aşımı Kontrolü

### TEST-VUK-01: 7 Gün Kuralı

**Amaç:** VUK 231/5 uyarınca süre aşımı uyarısının çalıştığını doğrulamak

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | 10 gün önce tarihli bir fatura bulun (onaylı ama gönderilmemiş) | - |
| 2 | Zamanlı görevler menüsünden "E-Fatura Süre Aşımı Kontrolü" görevini bulun | Görev mevcut |
| 3 | Görevi manuel çalıştırın | Görev çalışır |
| 4 | Faturayı açın | "Süre Aşımı" işareti aktif olmalı |

> **Not:** Bu kontrol her gün otomatik olarak sabah 08:00'de çalışır.

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

## 8. Hata Yönetimi Testleri (V2.1)

### TEST-HY01: Gönderim Öncesi Kontroller — Eksik Bilgi

**Amaç:** Eksik şirket/müşteri bilgilerinin gönderim öncesi yakalandığını doğrulamak

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Müşterinin VKN/TCKN alanını boşaltın | - |
| 2 | Fatura oluşturup **e-Fatura Gönder** butonuna basın | ❌ **HATA:** "Alıcı VKN/TCKN bilgisi eksik" |
| 3 | Müşterinin VKN/TCKN alanını doldurun | - |
| 4 | Tekrar **e-Fatura Gönder** butonuna basın | ✅ Kontrol geçer, gönderim başlar |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-HY02: Gönderim Öncesi Kontroller — Satır Eksiklikleri

**Amaç:** Fatura satır kontrollerinin çalıştığını doğrulamak

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Faturada miktar **0** olan bir satır ekleyin | - |
| 2 | **e-Fatura Gönder** butonuna basın | ❌ **HATA:** "Satır miktarı eksik veya sıfır" |
| 3 | Miktarı düzeltin, vergi satırdan kaldırın | - |
| 4 | Tekrar **e-Fatura Gönder** butonuna basın | ❌ **HATA:** "Vergi bilgisi eksik" |
| 5 | Vergiyi ekleyin → Tekrar gönder | ✅ Kontrol geçer |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-HY03: Seri Seçimi Kontrolü

**Amaç:** Seri seçilmeden gönderime izin verilmediğini doğrulamak

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Faturada seri seçmeden **e-Fatura Gönder** butonuna basın | ❌ **HATA:** "Fatura serisi seçilmemiş" |
| 2 | Seri seçip tekrar gönderin | ✅ Kontrol geçer |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-HY04: Hata Banner Görünürlüğü

**Amaç:** Hatalı faturada hata banner'ının görüntülendiğini doğrulamak

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Hatalı bir e-fatura gönderimi yapın (veya test ortamında hata oluşturun) | - |
| 2 | Faturayı tekrar açın | 🔴 Formun üstünde **kırmızı hata banner'ı** görünür |
| 3 | Banner'da hata mesajını okuyun | Hatanın ne olduğu açıkça belirtilmiş |
| 4 | **"Tekrar Dene"** butonunu kontrol edin | Buton görünür (retry mümkün ise) |
| 5 | **"İşlem Geçmişi"** butonunu kontrol edin | Buton görünür |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-HY05: İşlem Geçmişi Smart Button

**Amaç:** İşlem geçmişi butonunun çalıştığını doğrulamak

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Gönderilmiş bir faturayı açın | Smart button alanında **"İşlem Geçmişi"** butonu ve sayısı görünür |
| 2 | Smart button'a tıklayın | Bu faturanın gönderim geçmişi listesi açılır |
| 3 | Listede kayıtları kontrol edin | Tarih, durum (başarılı/hatalı), hata kodu bilgileri görünür |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-HY06: Manuel Yeniden Deneme (Retry Wizard)

**Amaç:** Hatalı faturanın yeniden gönderilmesini test etmek

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Hatalı faturada **"Tekrar Dene"** butonuna basın | Yeniden deneme penceresi açılır |
| 2 | Mevcut hata bilgisini kontrol edin | Hata mesajı gösteriliyor |
| 3 | "Yeni UUID Üret" seçeneğini kontrol edin | Varsayılan: ✅ İşaretli |
| 4 | **"Tekrar Gönder"** butonuna basın | Fatura yeniden gönderilir |
| 5 | Sonucu kontrol edin | Başarılıysa hata banner'ı kaybolur; başarısızsa yeni hata gösterilir |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-HY07: İşlem Takip Ekranı

**Amaç:** Yeni İşlem Takip menüsünün çalıştığını doğrulamak

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | E-Dönüşüm → **İşlem Takip** → **E-Fatura İşlemleri** | İşlem listesi açılır |
| 2 | Renk kodlarını kontrol edin | 🟢 Yeşil: başarılı, 🔴 Kırmızı: hatalı, 🟡 Sarı: retry planlanmış |
| 3 | Bir kaydı tıklayın | Detay formu açılır (hata bilgisi, XML içeriği, yanıt) |
| 4 | **"Hatalı"** filtresini uygulayın | Sadece hatalı kayıtlar listelenir |
| 5 | E-Dönüşüm → İşlem Takip → **Hata Kodları** | Hata kodu listesi açılır |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-HY08: %0 KDV İstisna Kodu Kontrolü

**Amaç:** %0 KDV'li satırlarda istisna kodu zorunluluğunu test etmek

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Fatura satırına **%0 KDV** uygulayın, istisna kodu **boş** bırakın | - |
| 2 | **e-Fatura Gönder** butonuna basın | ❌ **HATA:** "%0 KDV satırlarında istisna muafiyet kodu zorunludur" |
| 3 | İstisna kodunu doldurun → Tekrar gönderin | ✅ Kontrol geçer |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

## 9. V2.2 İrsaliye Testleri

### TEST-IRS01: İrsaliye Tip Kodu Düzeltmesi

**Amaç:** MATBUUDAN → MATBUDAN düzeltmesinin doğru uygulandığını test etmek

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Stok Transferi → E-İrsaliye Tipi dropdown'ını açın | **Sevk** ve **Matbudan** görünür |
| 2 | "Matbuudan" (çift U) seçeneği arayın | ❌ Bulunmamalı — eski isim kaldırıldı |
| 3 | "Matbudan" seçeneğini seçin | ✅ Seçilebilir |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-IRS02: İrsaliye Senaryo-Tip Uyumu

**Amaç:** Senaryo ile uyumsuz tip seçildiğinde hata verilmesini test etmek

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Senaryo: **Temel İrsaliye**, Tip: **Sevk** → Kaydet | ✅ Başarılı |
| 2 | Senaryo: **Temel İrsaliye**, Tip: **Matbudan** → Kaydet | ✅ Başarılı |
| 3 | Senaryo: **Hal Kayıt Sistemi İrsaliye**, Tip: **Sevk** → Kaydet | ✅ Başarılı |
| 4 | Senaryo: **Hal Kayıt Sistemi İrsaliye**, Tip: **Matbudan** → Kaydet | ✅ Başarılı |
| 5 | Senaryo: **İDİS İrsaliye**, Tip: **Sevk** → Kaydet | ✅ Başarılı |
| 6 | Senaryo: **İDİS İrsaliye**, Tip: **Matbudan** → Kaydet | ✅ Başarılı |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-IRS03: İrsaliye Senaryo Değiştirme — Tip Temizleme

**Amaç:** Senaryo değiştirildiğinde uyumsuz tipin otomatik temizlendiğini test etmek

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Senaryo: **Temel İrsaliye**, Tip: **Matbudan** seçin | Tip Matbudan olarak kalır |
| 2 | Senaryoyu **Hal Kayıt Sistemi İrsaliye** olarak değiştirin | Tip otomatik **Sevk** olur |
| 3 | Senaryoyu **İDİS İrsaliye** olarak değiştirin | Tip **Sevk** kalır |
| 4 | Senaryoyu tekrar **Temel İrsaliye** yapın | Tip **Sevk** kalır (uyumlu) |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-IRS04: MATBUDAN — Zorunlu Alanlar

**Amaç:** MATBUDAN seçildiğinde matbu belge alanlarının zorunlu olmasını test etmek

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Tip: **Matbudan**, Matbu Belge No: **boş** → Kaydet | ❌ **HATA:** "MATBUDAN tipi seçildiğinde 'Matbu Belge No' alanı zorunludur" |
| 2 | Matbu Belge No doldurun, Matbu Belge Tarihi: **boş** → Kaydet | ❌ **HATA:** "MATBUDAN tipi seçildiğinde 'Matbu Belge Tarihi' alanı zorunludur" |
| 3 | Her iki alanı da doldurun → Kaydet | ✅ Başarılı |
| 4 | Tip: **Sevk**, Matbu alanları boş → Kaydet | ✅ Başarılı (zorunlu değil) |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-IRS05: HKSIRSALIYE — Künye No Zorunluluğu

**Amaç:** HKS irsaliyesinde her satır için künye no zorunluluğunu test etmek

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Senaryo: **Hal Kayıt Sistemi İrsaliye** seçin, satırlarda **HKS Künye No** boş bırakın → İrsaliye Gönder | ❌ **HATA:** "HKSIRSALIYE senaryosunda her satır için 'HKS Künye No' zorunludur" |
| 2 | Satır detayına girin, **HKS Künye No**: 5 karakter girin → Kaydet | ❌ **HATA:** "HKS Künye No tam 19 karakter olmalıdır" |
| 3 | Satır detayına girin, **HKS Künye No**: 19 karakter girin → Kaydet | ✅ Başarılı |
| 4 | Birden fazla satır olduğunda tümünde künye no dolu → İrsaliye Gönder | ✅ Başarılı |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-IRS06: IDISIRSALIYE — Sevkiyat No ve Etiket No

**Amaç:** İDİS irsaliyesinde sevkiyat no ve satır bazlı etiket no zorunluluğunu test etmek

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Senaryo: **İDİS İrsaliye** seçin — formda **İDİS Sevkiyat No** alanı görünür mü? | ✅ Alan görünür |
| 2 | İDİS Sevkiyat No: **boş** → Kaydet | ❌ **HATA:** "IDISIRSALIYE senaryosunda 'İDİS Sevkiyat No' alanı zorunludur" |
| 3 | İDİS Sevkiyat No: `ABC` → Kaydet | ❌ **HATA:** format geçersiz |
| 4 | İDİS Sevkiyat No: `SE-0000001` → Kaydet | ✅ Başarılı |
| 5 | Satırlarda **İDİS Etiket No** boş bırakın → İrsaliye Gönder | ❌ **HATA:** "IDISIRSALIYE senaryosunda her satır için 'İDİS Etiket No' zorunludur" |
| 6 | Etiket No: `1234` → Kaydet | ❌ **HATA:** format geçersiz |
| 7 | Etiket No: `AB1234567` → Kaydet | ✅ Başarılı |
| 8 | Senaryo: **Temel İrsaliye** → İDİS Sevkiyat No alanı | Alan görünmez |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

### TEST-IRS07: Matbu Belge Alanları — Koşullu Görünürlük

**Amaç:** Matbu belge alanlarının sadece MATBUDAN tipinde görünür olmasını test etmek

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Tip: **Sevk** → Matbu Belge No ve Tarihi alanlarını arayın | Alanlar **görünmez** |
| 2 | Tip: **Matbudan** → Matbu Belge No ve Tarihi alanlarını arayın | Alanlar **görünür** |

**Sonuç:** ☐ Geçti ☐ Kaldı ☐ Bloke — Not: ________________

---

## 10. Test Özeti Tablosu

| # | Test ID | Test Adı | Sonuç | Not |
|---|---------|----------|-------|-----|
| 1 | TEST-S01 | Ticari Fatura — Satış | ☐ G ☐ K ☐ B | |
| 2 | TEST-S02 | Temel Fatura — İade | ☐ G ☐ K ☐ B | |
| 3 | TEST-S03 | İhracat — Geçersiz Tip | ☐ G ☐ K ☐ B | |
| 4 | TEST-S04 | Kamu — IBAN | ☐ G ☐ K ☐ B | |
| 5 | TEST-S05 | Yatırım Teşvik (YENİ) | ☐ G ☐ K ☐ B | |
| 6 | TEST-S06 | İDİS (YENİ) | ☐ G ☐ K ☐ B | |
| 7 | TEST-S07 | İlaç/Tıbbi Cihaz (YENİ) | ☐ G ☐ K ☐ B | |
| 8 | TEST-S08 | HKS — Künye No | ☐ G ☐ K ☐ B | |
| 9 | TEST-S09 | Teknoloji Desteği (YENİ) | ☐ G ☐ K ☐ B | |
| 10 | TEST-S10 | YTB Satış/İade (YENİ) | ☐ G ☐ K ☐ B | |
| 11 | TEST-S11 | SGK — VKN | ☐ G ☐ K ☐ B | |
| 12 | TEST-S12 | Yolcu Beraber — Pasaport | ☐ G ☐ K ☐ B | |
| 13 | TEST-D01 | Senaryo Değiştirme | ☐ G ☐ K ☐ B | |
| 14 | TEST-D02 | Koşullu Alan Görünürlüğü | ☐ G ☐ K ☐ B | |
| 15 | TEST-G01 | İletim Durum Çubuğu | ☐ G ☐ K ☐ B | |
| 16 | TEST-G02 | Red Durumu | ☐ G ☐ K ☐ B | |
| 17 | TEST-G03 | XML Arşiv İndirme | ☐ G ☐ K ☐ B | |
| 18 | TEST-A01 | KDV Tevkifat Alt Sınır | ☐ G ☐ K ☐ B | |
| 19 | TEST-A02 | QNB Bağlantı Ayarları | ☐ G ☐ K ☐ B | |
| 20 | TEST-L01 | Satır Opsiyonel Kolonlar | ☐ G ☐ K ☐ B | |
| 21 | TEST-VUK-01 | Süre Aşımı Kontrolü | ☐ G ☐ K ☐ B | |
| 22 | TEST-HY01 | Ön Kontrol — Eksik Bilgi | ☐ G ☐ K ☐ B | |
| 23 | TEST-HY02 | Ön Kontrol — Satır Eksiklikleri | ☐ G ☐ K ☐ B | |
| 24 | TEST-HY03 | Seri Seçimi Kontrolü | ☐ G ☐ K ☐ B | |
| 25 | TEST-HY04 | Hata Banner Görünürlüğü | ☐ G ☐ K ☐ B | |
| 26 | TEST-HY05 | İşlem Geçmişi Smart Button | ☐ G ☐ K ☐ B | |
| 27 | TEST-HY06 | Manuel Yeniden Deneme | ☐ G ☐ K ☐ B | |
| 28 | TEST-HY07 | İşlem Takip Ekranı | ☐ G ☐ K ☐ B | |
| 29 | TEST-HY08 | %0 KDV İstisna Kodu | ☐ G ☐ K ☐ B | |
| 30 | TEST-IRS01 | İrsaliye Tip Kodu Düzeltmesi | ☐ G ☐ K ☐ B | |
| 31 | TEST-IRS02 | İrsaliye Senaryo-Tip Uyumu | ☐ G ☐ K ☐ B | |
| 32 | TEST-IRS03 | İrsaliye Senaryo Değiştirme | ☐ G ☐ K ☐ B | |
| 33 | TEST-IRS04 | MATBUDAN Zorunlu Alanlar | ☐ G ☐ K ☐ B | |
| 34 | TEST-IRS05 | HKSIRSALIYE Künye No | ☐ G ☐ K ☐ B | |
| 35 | TEST-IRS06 | IDISIRSALIYE Sevkiyat/Etiket No | ☐ G ☐ K ☐ B | |
| 36 | TEST-IRS07 | Matbu Belge Koşullu Görünürlük | ☐ G ☐ K ☐ B | |

**G:** Geçti | **K:** Kaldı | **B:** Bloke

---

## 10. Hata Raporlama

Test sırasında karşılaşılan hatalar için aşağıdaki bilgileri not edin:

| Bilgi | Açıklama |
|-------|---------|
| **Test ID** | Hangi test sırasında oluştu |
| **Adım No** | Testin hangi adımında |
| **Beklenen** | Ne olması gerekiyordu |
| **Gerçekleşen** | Ne oldu |
| **Ekran Görüntüsü** | Mümkünse ekran görüntüsü alın |
| **Tarayıcı** | Chrome / Firefox / Edge |
| **Tarih/Saat** | Hatanın oluştuğu zaman |

---

## 11. Test Sonuç Onayı

| | |
|---|---|
| **Test Eden** | ___________________________ |
| **Tarih** | ___________________________ |
| **Toplam Test** | 33 |
| **Geçen** | ___ |
| **Kalan** | ___ |
| **Bloke** | ___ |
| **Genel Değerlendirme** | ☐ BAŞARILI ☐ KOŞULLU BAŞARILI ☐ BAŞARISIZ |
| **İmza** | ___________________________ |
