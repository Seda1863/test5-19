# E-Dönüşüm Modülü V2 Test Dokümanı — Teknik Ekip

**Modül:** edonusum (MindDX Lokalizasyon)  
**Versiyon:** 18.18.78  
**Platform:** Odoo 18  
**Tarih:** Haziran 2025 (V2) / Nisan 2026 (V2.1 — Hata Yönetimi) / Temmuz 2025 (V2.2 — İrsaliye Güncellemeleri)  

---

## 1. Test Ortamı Hazırlığı

### 1.1 Ön Koşullar

1. Temiz bir Odoo 18 veritabanı oluşturun veya mevcut test DB'yi kullanın
2. `l10n_tr` modülünü kurun
3. `edonusum` modülünü kurun / güncelleyin (`-u edonusum`)
4. Şirket ayarlarında QNB eFinans bağlantı bilgilerini girin:
   - **Test Modu:** Açık
   - **Test URL:** QNB test ortamı adresi
   - **Üretim URL:** (boş bırakılabilir)
5. En az 2 partner (müşteri) oluşturun:
   - Bir tanesi VKN: `7640235439` (SGK testi için)
   - Bir tanesi TCKN'li (TEKNOLOJIDESTEK testi için)

### 1.2 Modül Güncelleme Testi

```bash
# Modül güncelleme
./odoo-bin -d test_db -u edonusum --stop-after-init

# Beklenen: Hata olmadan tamamlanır
# Kontrol: 4 yeni senaryo, 6 yeni tip kaydı oluşmuş olmalı
```

**Kontrol Sorguları:**
```sql
-- Yeni senaryolar
SELECT id, name, code, active FROM mdx_ebelge_senaryo WHERE code IN ('ILAC_TIBBICIHAZ', 'YATIRIMTESVIK', 'IDIS', 'IDISIRSALIYE');
-- 4 kayıt döndürmeli (hepsi active=True)

-- Eski İlaç/Tıbbi Cihaz
SELECT id, name, code, active FROM mdx_ebelge_senaryo WHERE code = 'ILAC_TIBBICIHAZ_ESKI';
-- 1 kayıt, active=False

-- Yeni tipler
SELECT id, name, code FROM mdx_ebelge_tipleri WHERE code IN ('TEKNOLOJIDESTEK', 'YTBSATIS', 'YTBIADE', 'YTBISTISNA', 'YTBTEVKIFAT', 'YTBTEVKIFATIADE');
-- 6 kayıt döndürmeli

-- SQL constraint
SELECT conname FROM pg_constraint WHERE conname = 'account_move_efatura_uuid_unique';
-- 1 kayıt döndürmeli

-- Cron job
SELECT id, name, active FROM ir_cron WHERE name ILIKE '%süre aşımı%';
-- 1 kayıt, active=True
```

---

## 2. Veri Modeli Testleri (FAZ 1)

### TEST-DM-001: Yeni Senaryo Kayıtları

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Fatura formunda senaryo dropdown'ını açın | ILAC_TIBBICIHAZ, YATIRIMTESVIK, IDIS, IDISIRSALIYE görünmeli |
| 2 | Eski İlaç/Tıbbi Cihaz kaydını arayın | `ILAC_TIBBICIHAZ_ESKI` → Listede görünMEMEli (active=False) |

### TEST-DM-002: Yeni Tip Kayıtları

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | e-Arşiv senaryosu seçin | 20 tip görünmeli (eski 14 + 6 yeni) |
| 2 | TEKNOLOJIDESTEK tipini seçin | Seçilebilmeli |

---

## 3. Validasyon Testleri (FAZ 2)

### TEST-VAL-001: Matris Validasyonu — Pozitif

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Senaryo: TICARIFATURA, Tip: SATIS → Onayla | ✅ Hata yok |
| 2 | Senaryo: HKS, Tip: HKSSATIS → Onayla | ✅ Hata yok |
| 3 | Senaryo: YATIRIMTESVIK, Tip: SATIS, ytb_no: B/025/001 → Onayla | ✅ Hata yok |
| 4 | Senaryo: IDIS, Tip: SATIS, idis_sevkiyat_no: SE-1234567 → Onayla | ✅ Hata yok |

### TEST-VAL-002: Matris Validasyonu — Negatif

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Senaryo: TICARIFATURA, Tip: IADE → Onayla | ❌ ValidationError: "Geçersiz senaryo-tip kombinasyonu" |
| 2 | Senaryo: IHRACAT, Tip: TEVKIFAT → Onayla | ❌ ValidationError |
| 3 | Senaryo: HKS, Tip: SATIS → Onayla | ❌ ValidationError |
| 4 | Senaryo: ENERJI, Tip: IADE → Onayla | ❌ ValidationError |

### TEST-VAL-003: KAMU IBAN Kontrolü

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Senaryo: KAMU, Tip: SATIS, kamu_iban: boş → Onayla | ❌ "KAMU senaryosunda IBAN zorunludur" |
| 2 | Senaryo: KAMU, Tip: SATIS, kamu_iban: TR12... → Onayla | ✅ Hata yok |

### TEST-VAL-004: İade BillingReference Kontrolü

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Tip: IADE, referans fatura bilgisi boş → Onayla | ❌ "İade faturalarında referans fatura bilgisi zorunludur" |
| 2 | Tip: YTBIADE, referans fatura bilgisi boş → Onayla | ❌ Aynı hata |
| 3 | Tip: YTBTEVKIFATIADE, referans fatura bilgisi boş → Onayla | ❌ Aynı hata |
| 4 | Tip: IADE, referans fatura dolu → Onayla | ✅ Hata yok |

### TEST-VAL-005: SGK Alıcı VKN Kontrolü

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Tip: SGK, alıcı VKN: 1234567890 → Onayla | ❌ "SGK faturalarında alıcı VKN 7640235439 olmalıdır" |
| 2 | Tip: SGK, alıcı VKN: 7640235439 → Onayla | ✅ Hata yok |

### TEST-VAL-006: TEKNOLOJIDESTEK TCKN Kontrolü

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Tip: TEKNOLOJIDESTEK, alıcıda TCKN yok → Onayla | ❌ "TEKNOLOJIDESTEK faturalarında alıcı TCKN zorunludur" |
| 2 | Tip: TEKNOLOJIDESTEK, alıcıda TCKN var → Onayla | ✅ Hata yok |

### TEST-VAL-007: Yatırım Teşvik No Kontrolü

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Senaryo: YATIRIMTESVIK, ytb_no: boş → Onayla | ❌ YTB No zorunlu hatası |
| 2 | Senaryo: YATIRIMTESVIK, ytb_no: "ABC" → Onayla | ❌ Format hatası |
| 3 | Senaryo: YATIRIMTESVIK, ytb_no: "B/025/001" → Onayla | ✅ Hata yok |

### TEST-VAL-008: İDİS Sevkiyat No Kontrolü

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Senaryo: IDIS, idis_sevkiyat_no: boş → Onayla | ❌ Sevkiyat No zorunlu hatası |
| 2 | Senaryo: IDIS, idis_sevkiyat_no: "ABC" → Onayla | ❌ Format hatası |
| 3 | Senaryo: IDIS, idis_sevkiyat_no: "SE-1234567" → Onayla | ✅ Hata yok |

### TEST-VAL-009: Satır Validasyonları

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | ILAC_TIBBICIHAZ, satırlarda ilac_item_type yok → Onayla | ❌ "En az 1 satırda ilaç/tıbbi cihaz türü zorunludur" |
| 2 | TEKNOLOJIDESTEK, satırlarda teknoloji_cihaz_tipi yok → Onayla | ❌ "En az 1 satırda cihaz tipi zorunludur" |
| 3 | HKS, satırlarda hks_kunye_no yok → Onayla | ❌ "En az 1 satırda künye no zorunludur" |

### TEST-VAL-010: UUID Benzersizlik

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | İki faturaya aynı UUID girin → Kaydet | ❌ SQL IntegrityError: UNIQUE constraint |

### TEST-VAL-011: Onchange Testi

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Senaryo: TICARIFATURA, Tip: SATIS seçin | ✅ |
| 2 | Senaryo: HKS olarak değiştirin | Tip alanı otomatik temizlenmeli |
| 3 | Tip dropdown'ını açın | Sadece HKSSATIS, HKSKOMISYONCU görünmeli |

---

## 4. XML Üretimi Testleri (FAZ 3)

### TEST-XML-001: Temel XML Yapısı

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | TICARIFATURA/SATIS faturası oluşturup XML üretin | Geçerli UBL-TR 1.2.1 XML |
| 2 | ProfileID elemanını kontrol edin | `TICARIFATURA` değeri |
| 3 | InvoiceTypeCode elemanını kontrol edin | `SATIS` değeri |

### TEST-XML-002: BillingReference (İade Faturaları)

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | IADE faturası, referans fatura ile XML üretin | `<cac:BillingReference>` mevcut |
| 2 | YTBIADE faturası ile XML üretin | `<cac:BillingReference>` mevcut |
| 3 | YTBTEVKIFATIADE faturası ile XML üretin | `<cac:BillingReference>` mevcut |

### TEST-XML-003: YATIRIMTESVIK XML Elemanları

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | YATIRIMTESVIK faturası XML üretin | `<cac:ContractDocumentReference>` → YTB No |
| 2 | Satırda harcama tipi girin | `<cac:CommodityClassification>` → harcama kodu |
| 3 | Satırda makine bilgisi girin | `<cac:ItemInstance>` → makine bilgileri |

### TEST-XML-004: İDİS XML Elemanları

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | İDİS faturası XML üretin | `<cac:PartyIdentification>` → Sevkiyat No |
| 2 | Satırda etiket no girin | `<cac:AdditionalItemIdentification>` → etiket no |

### TEST-XML-005: YOLCUBERABERFATURA XML

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | YOLCUBERABERFATURA, pasaport+uyruk girin → XML | `<cac:TaxRepresentativeParty>` → pasaport, uyruk |

### TEST-XML-006: KAMU IBAN XML

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | KAMU faturası IBAN ile → XML | `<cac:PaymentMeans>` → `<cac:PayeeFinancialAccount>` → IBAN |

### TEST-XML-007: KonaklamaVergisi XML

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | KONAKLAMAVERGISI faturası, 0059 kodu → XML | `<cac:TaxTotal>` → TaxScheme ID: 0059 |

### TEST-XML-008: AdditionalItemIdentification

| Senaryo | Beklenen XML |
|---------|-------------|
| ILAC_TIBBICIHAZ, ilac_karekod dolu | `<cac:AdditionalItemIdentification>` → karekod |
| İDİS, idis_etiket_no dolu | `<cac:AdditionalItemIdentification>` → etiket no |
| HKS, hks_kunye_no dolu | `<cac:AdditionalItemIdentification>` → künye no |
| TEKNOLOJIDESTEK, teknoloji_cihaz_tipi dolu | `<cac:AdditionalItemIdentification>` → cihaz tipi |
| İHRAÇKAYITLI, istisna kodu 702 | `<cac:AdditionalItemIdentification>` → DİB satır kodları |

### TEST-XML-009: XML Sanitizasyon

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Şirket adını `Test & Company <"örnek">` yapın → XML üretin | `&amp;`, `&lt;`, `&gt;`, `&quot;` dönüşmüş olmalı |
| 2 | Fatura açıklamasına `<script>alert('xss')</script>` girin | XML'de escape edilmiş olmalı |
| 3 | Satır açıklamasına kontrol karakteri (Char 0x00-0x1F) girin | XML'de temizlenmiş olmalı |

### TEST-XML-010: Tutar Yuvarlaması

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | 1/3 fiyatlı satır ekleyin (0.333333...) | XML'de `0.33` formatında |
| 2 | LineExtensionAmount'u kontrol edin | 2 ondalık |
| 3 | TaxTotal Amount'u kontrol edin | 2 ondalık |
| 4 | PriceAmount'u kontrol edin | `{:.2f}` formatında |

---

## 5. Alan Testleri (FAZ 4)

### TEST-FIELD-001: Header Alanları

Her bir yeni header alanı için:

| Alan | Test | Beklenen |
|------|------|----------|
| `ytb_no` | Değer gir, kaydet, yeniden aç | Değer korunmuş |
| `idis_sevkiyat_no` | Aynı | Aynı |
| `yolcu_pasaport_no` | Aynı | Aynı |
| `yolcu_uyruk` | Aynı | Aynı |
| `kamu_iban` | Aynı | Aynı |
| `gib_iletim_durumu` | Selection — 6 değer | Her değer seçilebilir |
| `gib_iletim_tarihi` | Datetime | Doğru kaydedilir |
| `gib_red_nedeni` | Text | Doğru kaydedilir |
| `efatura_xml_arsiv` | Binary upload | Dosya yüklenebilir/indirilebilir |
| `efatura_xml_hash` | Char(64) | 64 karakter SHA-256 |

### TEST-FIELD-002: Satır Alanları (14 adet)

Her satır alanı için: değer gir → kaydet → yeniden aç → değer korunmuş olmalı.

| Alan | Tip | Kontrol |
|------|-----|---------|
| `ilac_item_type` | Selection (ilac/tibbi_cihaz) | Seçenekler doğru |
| `ilac_karekod` | Char | Kaydedilir |
| `ytb_harcama_tipi` | Char | Kaydedilir |
| `ytb_makine_adi` | Char | Kaydedilir |
| `ytb_seri_no` | Char | Kaydedilir |
| `ytb_makine_id` | Char | Kaydedilir |
| `idis_etiket_no` | Char | Kaydedilir |
| `teknoloji_cihaz_tipi` | Selection (bilgisayar/tablet/yazici/diger) | Seçenekler doğru |
| `teknoloji_imei` | Char | Kaydedilir |
| `hks_kunye_no` | Char | Kaydedilir |
| `satici_dib_satir_kodu` | Char | Kaydedilir |
| `alici_dib_satir_kodu` | Char | Kaydedilir |

---

## 6. Şirket Ayarları Testi (FAZ 5)

### TEST-COMP-001: KDV Tevkifat Alt Sınır

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Şirket ayarlarını açın | `kdv_tevkifat_alt_sinir` alanı görünmeli, varsayılan 6900.0 |
| 2 | Değeri 7500.0 yapın → Kaydedin | Kaydedilir |
| 3 | Yeniden açın | 7500.0 görünmeli |

### TEST-COMP-002: QNB Bağlantı Ayarları

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Test Modu: Açık | Kaydedilir |
| 2 | Test URL girin | Kaydedilir |
| 3 | Üretim URL girin | Kaydedilir |
| 4 | Test Modu: Kapalı yapın, fatura gönderin | Üretim URL kullanılmalı |

---

## 7. View Testleri (FAZ 6)

### TEST-VIEW-001: Senaryo Detayları Görünürlük

| Senaryo | Görünür Alanlar | Gizli Alanlar |
|---------|----------------|---------------|
| YATIRIMTESVIK | ytb_no | idis_sevkiyat_no, pasaport, uyruk, iban |
| IDIS | idis_sevkiyat_no | ytb_no, pasaport, uyruk, iban |
| YOLCUBERABERFATURA | yolcu_pasaport_no, yolcu_uyruk | ytb_no, idis_sevkiyat_no, iban |
| KAMU | kamu_iban | ytb_no, idis_sevkiyat_no, pasaport, uyruk |
| TICARIFATURA | Hiçbiri | Tüm koşullu alanlar gizli |

### TEST-VIEW-002: GIB İletim Durumu Widget

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Fatura formunu açın | StatusBar widget'ı görünür |
| 2 | gib_iletim_durumu = 'red_edildi' yapın | gib_red_nedeni alanı görünür olur |
| 3 | gib_iletim_durumu = 'kabul_edildi' yapın | gib_red_nedeni alanı gizlenir |

### TEST-VIEW-003: Satır Alanları Tree View

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Fatura satırlarına gidin | 14 yeni kolon varsayılan gizli (optional="hide") |
| 2 | Kolon ayarlarından ilac_item_type'ı açın | Kolon görünür olur |
| 3 | column_invisible şartları kontrolü | İlgili senaryo olmadığında kolonlar optional bile olamaz |

---

## 8. QNB Entegrasyon Testleri (FAZ 7)

### TEST-QNB-001: Test/Prod URL Seçimi

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | qnb_test_mode = True → Fatura gönder | Test URL'e istek gider |
| 2 | qnb_test_mode = False → Fatura gönder | Prod URL'e istek gider |

### TEST-QNB-002: Retry Mekanizması

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | QNB URL'i geçersiz adresle değiştirin → Gönder | 3 deneme yapılır (2s, 4s, 8s bekleme) |
| 2 | Log'ları kontrol edin | Her retry loglanmış olmalı |
| 3 | 3. denemeden sonra | Kullanıcıya hata mesajı gösterilir |

### TEST-QNB-003: Hata Kodu Eşlemesi

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | QNB'den bilinen hata kodu döndüğünde | `QNB_ERROR_CODES`'daki Türkçe açıklama gösterilir |
| 2 | Bilinmeyen hata kodu döndüğünde | Ham hata mesajı gösterilir |

### TEST-QNB-004: Timeout

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Çok yavaş bir endpoint'e bağlanın | 60 saniye sonra timeout hatası |

---

## 9. Cron Testleri (FAZ 8)

### TEST-CRON-001: Süre Aşımı Kontrolü

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | 10 gün önce tarihli, posted, UUID'li ama gönderilmemiş fatura oluşturun | - |
| 2 | Cron'u manuel çalıştırın: `env['account.move']._cron_check_fatura_suresi_asimi()` | - |
| 3 | Faturayı yeniden açın | `fatura_suresi_asimi = True` |
| 4 | Logları kontrol edin | WARNING seviyesinde log kaydı |

### TEST-CRON-002: Süre Aşımı Olmayan Fatura

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Bugün tarihli fatura (henüz 7 gün geçmemiş) | - |
| 2 | Cron'u çalıştırın | `fatura_suresi_asimi` değişmemeli (False) |

### TEST-CRON-003: Zaten Gönderilmiş Fatura

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | 10 gün önce tarihli ama `gib_iletim_durumu = 'kabul_edildi'` | - |
| 2 | Cron'u çalıştırın | `fatura_suresi_asimi` değişmemeli |

---

## 10. Hata Yönetimi Testleri (V2.1)

### 10.1 Modül Güncelleme (V2.1)

```bash
./odoo-bin -d test_db -u edonusum --stop-after-init
# Beklenen: Hata olmadan tamamlanır
```

**Kontrol Sorguları:**
```sql
-- Yeni modeller
SELECT count(*) FROM ir_model WHERE model IN ('mdx.efatura.islem', 'mdx.efatura.retry.wizard');
-- 2 döndürmeli

-- İşlem takip sequence
SELECT id, code, prefix, padding FROM ir_sequence WHERE code = 'mdx.efatura.islem';
-- EFI- prefix, 6 padding

-- Yeni cron'lar
SELECT name, interval_number, interval_type, active FROM ir_cron WHERE name ILIKE '%retry%' OR name ILIKE '%hata raporu%';
-- 2 kayıt: retry queue (5 dakika), günlük hata raporu (1 gün)

-- Security
SELECT id, name FROM ir_model_access WHERE name IN ('access_mdx_efatura_islem', 'access_mdx_efatura_retry_wizard');
-- 2 kayıt
```

### 10.2 Ön Doğrulama Testleri

#### TEST-PRE-001: Şirket Bilgileri Doğrulama

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Şirketin VKN'sini boşaltın → e-Fatura gönder | ❌ EF0093: "Gönderici firma VKN/TCKN bilgisi eksik" |
| 2 | Şirketin adresini boşaltın → e-Fatura gönder | ❌ EF0095: "Gönderici firma adres bilgisi eksik" |
| 3 | Şirketin ülkesini boşaltın → e-Fatura gönder | ❌ EF0096: "Gönderici firma ülke bilgisi eksik" |
| 4 | Şirketin şehrini boşaltın → e-Fatura gönder | ❌ EF0097: "Gönderici firma şehir bilgisi eksik" |
| 5 | Tüm bilgileri doldurun → e-Fatura gönder | ✅ Şirket doğrulama geçer |

#### TEST-PRE-002: Müşteri Bilgileri Doğrulama

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Müşterinin VKN/TCKN'sini boşaltın → gönder | ❌ EF0089: "Alıcı VKN/TCKN bilgisi eksik" |
| 2 | Müşteri adresini boşaltın → gönder | ❌ EF0091: "Alıcı adres bilgisi eksik" |
| 3 | 10 haneli VKN girin | Tüzel kişi olarak tanınmalı |
| 4 | 11 haneli TCKN girin | Gerçek kişi olarak tanınmalı |
| 5 | TCKN'li müşterinin adını boşaltın → gönder | ❌ EF0122: "Alıcı ad bilgisi eksik" |

#### TEST-PRE-003: Satır Doğrulama

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Boş satır (ürün yok) → gönder | ❌ EF0099: "Satır ürün/hizmet adı eksik" |
| 2 | Miktar 0 olan satır → gönder | ❌ EF0100: "Satır miktarı eksik veya sıfır" |
| 3 | Birim olmayan satır → gönder | ❌ EF0101: "Satır birimi eksik" |
| 4 | Fiyat 0 olan satır → gönder | ❌ EF0102: "Satır birim fiyatı eksik veya sıfır" |

#### TEST-PRE-004: Vergi Doğrulama

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Vergi olmayan satırlı fatura → gönder | ❌ EF0130: "Vergi bilgisi eksik" |
| 2 | %0 KDV satırında istisna kodu olmadan → gönder | ❌ EF0150: "%0 KDV satırlarında istisna muafiyet kodu zorunludur" |
| 3 | %0 KDV satırında istisna kodu ile → gönder | ✅ Doğrulama geçer |

#### TEST-PRE-005: Seri Doğrulama

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Seri seçmeden → e-Fatura gönder | ❌ EF0290: "Fatura serisi seçilmemiş" |
| 2 | Geçerli seri seçip → e-Fatura gönder | ✅ Doğrulama geçer |

#### TEST-PRE-006: Belge Tipine Özel Doğrulama

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | İhracat faturası, GTB referansı boş → gönder | ❌ EF0311 uyarısı |
| 2 | e-Fatura alıcısı olmayan müşteriye e-fatura → gönder | ❌ EF0028: "Alıcı e-fatura mükellefi değil" |

### 10.3 Seri Yönetimi Testleri

#### TEST-SERIES-001: SAVEPOINT Mekanizması

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Geçerli fatura → e-Fatura gönder (başarılı) | Seri numarası artmış, `series_confirmed = True` |
| 2 | Seri tablosunda index değerini kontrol edin | 1 artmış olmalı |
| 3 | İşlem kaydında `series_number` alanını kontrol edin | Doğru numara atanmış |

#### TEST-SERIES-002: Seri Geri Alma (Hata Durumu)

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | QNB URL'yi geçersiz yapın → gönder | Hata oluşur |
| 2 | Seri tablosunda index değerini kontrol edin | **Artmamış** olmalı (ROLLBACK) |
| 3 | İşlem kaydında `series_confirmed` | `False` |

#### TEST-SERIES-003: Ardışık Seri Numarası

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Art arda 3 fatura gönderin (başarılı) | Seri numaraları ardışık (N, N+1, N+2) |
| 2 | Arada hata olan fatura gönderin | Hatalı faturanın seri numarası geri alınmış |
| 3 | Sonraki başarılı fatura | Hatalı numarayı atlamamış, doğru ardışık numara |

### 10.4 İşlem Takip Testleri

#### TEST-LOG-001: İşlem Kaydı Oluşturma

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Fatura → e-Fatura gönder (başarılı) | `mdx.efatura.islem` kaydı oluşmuş, state = `sent` |
| 2 | `name` alanını kontrol edin | EFI-000001 formatında |
| 3 | `document_ref` alanını kontrol edin | `account.move,<id>` formatında |
| 4 | `document_type` alanını kontrol edin | Doğru belge türü |

#### TEST-LOG-002: Hata Kaydı

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Hatalı fatura gönderin | `mdx.efatura.islem` kaydı, state = `error` |
| 2 | `error_code_id` alanını kontrol edin | Eşleşen hata kodu |
| 3 | `error_message` alanını kontrol edin | Ham hata mesajı dolu |
| 4 | `error_display` alanını kontrol edin | HTML formatında hata gösterimi |

#### TEST-LOG-003: Smart Button

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Gönderilmiş faturayı açın | Smart button'da işlem sayısı görünür |
| 2 | Smart button'a tıklayın | Filtrelenmiş işlem listesi açılır |
| 3 | Birden fazla fatura gönderin | Her faturanın kendi işlem sayısı doğru |

#### TEST-LOG-004: Hata Banner

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Hatalı faturayı açın | Kırmızı hata banner'ı görünür |
| 2 | Banner'da hata mesajını kontrol edin | `efatura_hata_html` içeriği görünür |
| 3 | "Tekrar Dene" butonunu kontrol edin | `efatura_retry_possible = True` ise görünür |
| 4 | "İşlem Geçmişi" butonunu kontrol edin | `efatura_transaction_count > 0` ise görünür |

### 10.5 Retry Testleri

#### TEST-RETRY-001: Otomatik Retry Planlama

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Yeniden denenebilir hata kodlu fatura gönderin (hata) | İşlem state = `retry_scheduled` |
| 2 | `next_retry_date` kontrol edin | Şimdiden ~5 dakika sonrası |
| 3 | `retry_count` kontrol edin | 0 → 1 |
| 4 | 5 dakika bekleyin veya cron'u manuel çalıştırın | Retry çalışır |
| 5 | İkinci hata durumunda `next_retry_date` | ~15 dakika sonrası (exponential backoff) |

#### TEST-RETRY-002: Retry Limiti

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | `max_retry = 4` olan işlemi 4 kez başarısız yapın | `retry_count = 4` |
| 2 | 5. retry denemesi | `can_retry = False`, artık retry planlanmaz |
| 3 | İşlem state | `error` (retry_scheduled değil) |

#### TEST-RETRY-003: Yeniden Denenemez Hata

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | `is_retryable = False` olan hata kodu tetikleyin | `can_retry = False` |
| 2 | Retry planlanmaz | State: `error`, `next_retry_date` boş |

#### TEST-RETRY-004: Retry Cron

```python
# Shell'de test:
env['mdx.retry.manager.mixin'].process_retry_queue()
```

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | retry_scheduled işlem oluşturun (next_retry_date geçmiş) | - |
| 2 | Cron'u çalıştırın | İşlem yeniden denenir |
| 3 | Başarılı olursa | State → `sent`, fatura hata alanları temizlenir |
| 4 | Başarısız olursa | retry_count artar, yeni next_retry_date hesaplanır |

#### TEST-RETRY-005: Manuel Retry (Wizard)

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Hatalı faturada "Tekrar Dene" butonuna basın | Retry wizard açılır |
| 2 | Wizard'da hata bilgisini kontrol edin | Mevcut hata gösterilir |
| 3 | `force_new_uuid = True` bırakın → "Tekrar Gönder" | Yeni UUID üretilir, fatura yeniden gönderilir |
| 4 | `force_new_series = True` yapın → "Tekrar Gönder" | Fatura numarası sıfırlanır, yeni seri atanır |
| 5 | `can_retry = False` durumda | "Tekrar Gönder" gizli, "Zorla Gönder" görünür |

### 10.6 Günlük Hata Raporu Testi

#### TEST-REPORT-001: Günlük Rapor Cron

```python
env['mdx.efatura.islem'].send_daily_error_report()
```

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Birkaç hatalı işlem kaydı oluşturun | - |
| 2 | Cron'u manuel çalıştırın | Admin'e mail gider |
| 3 | Mail içeriğini kontrol edin | Hata özeti tablolu format |

### 10.7 İşlem Takip View Testleri

#### TEST-VIEW-V21-001: İşlem Listesi

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | E-Dönüşüm → İşlem Takip → E-Fatura İşlemleri | Liste açılır |
| 2 | Hatalı kayıtlar | Kırmızı decoration |
| 3 | Gönderilmiş kayıtlar | Yeşil decoration |
| 4 | Retry planlanmış kayıtlar | Sarı decoration |
| 5 | State alanı | Badge widget ile gösterilir |

#### TEST-VIEW-V21-002: İşlem Formu

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Bir işlem kaydını açın | Form görünümü düzgün açılır |
| 2 | Statusbar | Draft → Sending → Sent / Error gösterir |
| 3 | Hata Detayı tab | HTML formatında hata gösterimi |
| 4 | XML İçeriği tab | Gönderilen XML görünür |
| 5 | Yanıt İçeriği tab | Alınan yanıt görünür |

#### TEST-VIEW-V21-003: Filtre ve Gruplama

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | "Hatalı" filtresini uygulayın | Sadece state=error kayıtlar |
| 2 | "Yeniden Denenebilir" filtresini uygulayın | Sadece can_retry=True kayıtlar |
| 3 | "Durum"a göre gruplayın | State'e göre gruplar |
| 4 | "Hata Kodu"na göre gruplayın | Hata koduna göre gruplar |

#### TEST-VIEW-V21-004: Menü Yapısı

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | E-Dönüşüm menüsünü açın | "İşlem Takip" bölümü görünür |
| 2 | "E-Fatura İşlemleri" tıklayın | İşlem listesi açılır |
| 3 | "Hata Kodları" tıklayın | Hata kodu listesi açılır |

---

## 11. Güvenlik Testleri

### TEST-SEC-001: XML Injection

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Partner adı: `<![CDATA[test]]>` → XML üretin | Escape edilmiş olmalı |
| 2 | Fatura açıklaması: `&amp; < > " '` → XML üretin | Çift escape olmamalı, doğru encode |
| 3 | Ürün adı: `<script>alert(1)</script>` → XML üretin | Escape edilmiş |

### TEST-SEC-002: SQL Injection

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | ytb_no: `'; DROP TABLE account_move; --` | ORM tarafından parametrize edilir, hata yok |

---

## 12. Regresyon Testleri

Mevcut senaryoların çalışmaya devam ettiğini doğrulayın:

| # | Senaryo | Tip | Kontrol |
|---|---------|-----|---------|
| 1 | TICARIFATURA | SATIS | Fatura oluştur → Onayla → XML üret → Gönder |
| 2 | TEMELFATURA | IADE | Fatura oluştur → Referans doldur → Onayla → XML üret |
| 3 | IHRACAT | SATIS | Fatura oluştur → Onayla → XML üret |
| 4 | HKS | HKSSATIS | Fatura oluştur → hks_kunye_no doldur → Onayla → XML üret |
| 5 | ENERJI | SARJ | Fatura oluştur → Onayla → XML üret |
| 6 | EARSIVFATURA | SATIS | e-Arşiv fatura → Onayla → XML üret → Gönder |

---

## 13. V2.2 İrsaliye Tür/Profil Testleri

### TEST-IRS-001: MATBUDAN Veri Düzeltmesi

```sql
SELECT id, name, code FROM mdx_ebelge_tipi WHERE code IN ('MATBUDAN', 'MATBUUDAN', 'SEVK');
```

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Yukarıdaki sorguyu çalıştırın | `MATBUDAN` aktif, `MATBUUDAN` kayıt yok |
| 2 | `SEVK` kaydını kontrol edin | `name=Sevk`, `code=SEVK`, `active=True` |
| 3 | `MATBUDAN` kaydını kontrol edin | `name=Matbudan`, `code=MATBUDAN`, `active=True` |

### TEST-IRS-002: VALID_DESPATCH_PROFILE_TYPE_MATRIX Doğrulama

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Stock picking → Senaryo: TEMELIRSALIYE, Tip: SEVK → Kaydet | ✅ Başarılı |
| 2 | Stock picking → Senaryo: TEMELIRSALIYE, Tip: MATBUDAN → Kaydet | ✅ Başarılı |
| 3 | Stock picking → Senaryo: HKSIRSALIYE, Tip: SEVK → Kaydet | ✅ Başarılı |
| 4 | Stock picking → Senaryo: HKSIRSALIYE, Tip: MATBUDAN → Kaydet | ✅ Başarılı |
| 5 | Stock picking → Senaryo: IDISIRSALIYE, Tip: SEVK → Kaydet | ✅ Başarılı |
| 6 | Stock picking → Senaryo: IDISIRSALIYE, Tip: MATBUDAN → Kaydet | ✅ Başarılı |

### TEST-IRS-003: Senaryo Değişikliğinde Tip Temizleme

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Senaryo: TEMELIRSALIYE, Tip: MATBUDAN seçin | Tip MATBUDAN kalır |
| 2 | Senaryoyu HKSIRSALIYE olarak değiştirin | Tip otomatik SEVK'e döner |
| 3 | Senaryoyu IDISIRSALIYE olarak değiştirin | Tip SEVK kalır |
| 4 | Senaryoyu TEMELIRSALIYE'ye geri çevirin | Tip SEVK kalır (uyumlu) |

### TEST-IRS-004: MATBUDAN Zorunlu Alan Kontrolü

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | Tip: MATBUDAN, Matbu Belge No: boş → Kaydet | ❌ ValidationError: "Matbu Belge No zorunlu" |
| 2 | Tip: MATBUDAN, Matbu Belge Tarihi: boş → Kaydet | ❌ ValidationError: "Matbu Belge Tarihi zorunlu" |
| 3 | Tip: MATBUDAN, her iki alan dolu → Kaydet | ✅ Başarılı |
| 4 | Tip: SEVK, Matbu alanları boş → Kaydet | ✅ Başarılı (zorunlu değil) |

### TEST-IRS-005: XML Üretimi — DespatchAdviceTypeCode

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | TEMELIRSALIYE + SEVK → XML üret | `<cbc:DespatchAdviceTypeCode>SEVK</cbc:DespatchAdviceTypeCode>` |
| 2 | TEMELIRSALIYE + MATBUDAN → XML üret | `<cbc:DespatchAdviceTypeCode>MATBUDAN</cbc:DespatchAdviceTypeCode>` |
| 3 | MATBUDAN XML'de AdditionalDocumentReference → kontrol | `<cbc:DocumentType>MATBU</cbc:DocumentType>` mevcut |
| 4 | SEVK XML'de AdditionalDocumentReference → kontrol | MATBU referansı yok, sadece XSLT referansı var |

### TEST-IRS-006: İrsaliye Regresyon

| # | Senaryo | Tip | Kontrol |
|---|---------|-----|---------|
| 1 | TEMELIRSALIYE | SEVK | İrsaliye oluştur → XML üret → Gönder |
| 2 | TEMELIRSALIYE | MATBUDAN | İrsaliye oluştur → Matbu alanları doldur → XML üret → Gönder |
| 3 | HKSIRSALIYE | SEVK | İrsaliye oluştur → Künye no doldur → XML üret → Gönder |
| 4 | IDISIRSALIYE | SEVK | İrsaliye oluştur → Sevkiyat/etiket no doldur → XML üret → Gönder |

### TEST-IRS-007: IDISIRSALIYE — Sevkiyat No Validasyon

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | IDISIRSALIYE seçin, İDİS Sevkiyat No boş → Kaydet | ❌ ValidationError: "İDİS Sevkiyat No zorunlu" |
| 2 | İDİS Sevkiyat No: `ABC` → Kaydet | ❌ ValidationError: format hatası |
| 3 | İDİS Sevkiyat No: `SE-1234` → Kaydet | ❌ ValidationError: format hatası (7 rakam gerekli) |
| 4 | İDİS Sevkiyat No: `SE-0000001` → Kaydet | ✅ Başarılı |
| 5 | İDİS Sevkiyat No alanının formda görünürlüğü (TEMELIRSALIYE) | Alan görünmez |
| 6 | İDİS Sevkiyat No alanının formda görünürlüğü (IDISIRSALIYE) | Alan görünür |

### TEST-IRS-008: HKSIRSALIYE — Künye No Validasyon

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | HKSIRSALIYE, satırda hks_kunye_no boş → İrsaliye gönder | ❌ ValidationError: "HKS Künye No zorunlu" |
| 2 | hks_kunye_no: `12345` (5 karakter) → İrsaliye gönder | ❌ ValidationError: "19 karakter olmalı" |
| 3 | hks_kunye_no: `1234567890123456789` (19 karakter) → İrsaliye gönder | ✅ Başarılı |
| 4 | Birden fazla satır, biri eksik → İrsaliye gönder | ❌ ValidationError: eksik satır adı gösterilir |

### TEST-IRS-009: IDISIRSALIYE — Etiket No Validasyon

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | IDISIRSALIYE, satırda idis_etiket_no boş → İrsaliye gönder | ❌ ValidationError: "İDİS Etiket No zorunlu" |
| 2 | idis_etiket_no: `1234` → İrsaliye gönder | ❌ ValidationError: format hatası |
| 3 | idis_etiket_no: `ABC1234567` (10 karakter) → İrsaliye gönder | ❌ ValidationError: format hatası (2 harf + 7 rakam) |
| 4 | idis_etiket_no: `AB1234567` → İrsaliye gönder | ✅ Başarılı |

### TEST-IRS-010: XML Üretimi — HKSIRSALIYE KUNYENO

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | HKSIRSALIYE + SEVK, künye no dolu → XML önizleme | DespatchLine > Item içinde `<cac:AdditionalItemIdentification>` var |
| 2 | XML'de KUNYENO kontrolü | `<cbc:ID schemeID="KUNYENO">1234567890123456789</cbc:ID>` mevcut |
| 3 | Her satır için ayrı KUNYENO | Her DespatchLine'da kendi künye no'su var |

### TEST-IRS-011: XML Üretimi — IDISIRSALIYE SEVKIYATNO + ETIKETNO

| Adım | İşlem | Beklenen Sonuç |
|------|-------|----------------|
| 1 | IDISIRSALIYE + SEVK, sevkiyat + etiket no dolu → XML önizleme | DespatchSupplierParty'de SEVKIYATNO var |
| 2 | XML'de SEVKIYATNO kontrolü | `<cbc:ID schemeID="SEVKIYATNO">SE-0000001</cbc:ID>` mevcut |
| 3 | XML'de ETIKETNO kontrolü | Her DespatchLine > Item'da `<cbc:ID schemeID="ETIKETNO">AB1234567</cbc:ID>` mevcut |
| 4 | TEMELIRSALIYE → XML önizleme | SEVKIYATNO ve ETIKETNO yok |

---

## 14. Test Sonuç Matrisi

| Test Grubu | Test Sayısı | Geçti | Kaldı | Bloke |
|-----------|-------------|-------|-------|-------|
| Veri Modeli (DM) | 2 | | | |
| Validasyon (VAL) | 11 | | | |
| XML Üretimi (XML) | 10 | | | |
| Alan (FIELD) | 2 | | | |
| Şirket (COMP) | 2 | | | |
| View (VIEW) | 3 | | | |
| QNB Entegrasyon (QNB) | 4 | | | |
| Cron (CRON) | 3 | | | |
| Ön Doğrulama (PRE) | 6 | | | |
| Seri Yönetimi (SERIES) | 3 | | | |
| İşlem Takip (LOG) | 4 | | | |
| Retry (RETRY) | 5 | | | |
| Günlük Rapor (REPORT) | 1 | | | |
| V2.1 View (VIEW-V21) | 4 | | | |
| Güvenlik (SEC) | 2 | | | |
| Regresyon | 6 | | | |
| V2.2 İrsaliye (IRS) | 11 | | | |
| **TOPLAM** | **79** | | | |
