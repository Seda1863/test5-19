# E-Dönüşüm Modülü V2 Güncelleme Dokümanı — Teknik Ekip

**Modül:** edonusum (MindDX Lokalizasyon)  
**Versiyon:** 18.18.78  
**Platform:** Odoo 18 Community/Enterprise  
**Standart:** GIB UBL-TR 1.2.1 / Kod Listeleri V1.42  
**Entegrasyon:** QNB eFinans SOAP API  
**Tarih:** Haziran 2025 (V2) / Nisan 2026 (V2.1 — Hata Yönetimi) / Temmuz 2025 (V2.2 — İrsaliye Güncellemeleri)  

---

## 1. Genel Bakış

V2 güncellemesi, GIB'in Ocak 2025 tarihli UBL-TR 1.2.1 güncellemelerini ve Kod Listeleri V1.42 kapsamındaki tüm değişiklikleri içerir. 8 faz (FAZ 1-8) halinde gerçekleştirilmiştir. V2.1 ile kapsamlı bir hata yönetimi altyapısı (işlem takibi, ön doğrulama, atomik seri yönetimi, otomatik retry) eklenmiştir. V2.2 ile e-İrsaliye tür/profil güncellemeleri, GIB standardına uyum düzeltmeleri ve ProfileID ↔ DespatchAdviceTypeCode validasyon matrisi eklenmiştir. Bu doküman her fazda yapılan kod değişikliklerini, etkilenen dosyaları ve teknik detayları içerir.

---

## 2. Etkilenen Dosyalar

| # | Dosya | FAZ | Değişiklik Tipi |
|---|-------|-----|-----------------|
| 1 | `data/initial_data.xml` | FAZ 1, V2.2 | Yeni senaryo/tipi kayıtları, eski kayıt deaktivasyonu, MATBUDAN düzeltmesi |
| 2 | `models/mdx_inh_account_move.py` | FAZ 2, 4, 5, 8, V2.1 | VALID_PROFILE_TYPE_MATRIX, yeni alanlar, constraint'ler, cron, hata yönetimi alanları, action_send_einvoice yeniden yazımı |
| 3 | `models/mdx_inh_account_move_line.py` | FAZ 4 | 14 yeni satır alanı |
| 4 | `models/mdx_inh_res_company.py` | FAZ 5 | 4 yeni şirket alanı |
| 5 | `models/mdx_utility_mixin.py` | FAZ 3, 7, 8, V2.2 | XML üretimi, QNB retry, sanitizasyon, MATBUDAN düzeltmesi |
| 6 | `views/mdx_inh_account_move_views.xml` | FAZ 6, V2.1 | Senaryo detayları, GIB iletim, satır alanları, hata banner, smart button |
| 7 | `views/mdx_inh_res_company_views.xml` | FAZ 6 | Şirket ayarları |
| 8 | `data/cron_jobs.xml` | FAZ 8, V2.1 | Zamanlı görevler (süre aşımı, retry queue, günlük hata raporu) |
| 9 | `models/mdx_efatura_islem.py` | V2.1 | **YENİ** — İşlem takip modeli |
| 10 | `models/mdx_pre_validation_mixin.py` | V2.1 | **YENİ** — Ön doğrulama mixin |
| 11 | `models/mdx_series_manager_mixin.py` | V2.1 | **YENİ** — Atomik seri yönetimi (SAVEPOINT) |
| 12 | `models/mdx_retry_manager_mixin.py` | V2.1 | **YENİ** — Otomatik retry yönetimi |
| 13 | `wizard/mdx_efatura_retry_wizard.py` | V2.1 | **YENİ** — Manuel retry sihirbazı |
| 14 | `views/mdx_efatura_islem_views.xml` | V2.1 | **YENİ** — İşlem takip list/form/search views |
| 15 | `views/mdx_efatura_wizard_views.xml` | V2.1 | **YENİ** — Retry wizard form view |
| 16 | `views/mdx_lokalizasyon_menu_views.xml` | V2.1 | İşlem Takip menü bölümü eklendi |
| 17 | `security/ir.model.access.csv` | V2.1 | 2 yeni erişim kaydı |
| 18 | `__manifest__.py` | V2.1, V2.2 | Versiyon 18.18.78, yeni view dosyaları |
| 19 | `models/mdx_inh_stock_picking.py` | V2.2 | VALID_DESPATCH_PROFILE_TYPE_MATRIX, irsaliye senaryo-tip validasyonu, IDIS sevkiyat no alanı, HKS/IDIS satır validasyonları |
| 20 | `models/mdx_inh_stock_move.py` | V2.2 | HKS künye no, İDİS etiket no satır alanları |
| 21 | `views/mdx_inh_stock_picking_views.xml` | V2.2 | İDİS sevkiyat no, MATBUDAN koşullu görünürlük, HKS/IDIS satır alanları |

---

## 3. FAZ 1 — Veri Modeli Düzeltmeleri (initial_data.xml)

### 3.1 Eski Senaryo Deaktivasyonu

`ILAC_TIBBICIHAZ` eski senaryo kaydı deaktif edilmiştir:
- `active` → `False`
- `code` → `ILAC_TIBBICIHAZ_ESKI`

### 3.2 Yeni Senaryo Kayıtları (mdx.ebelge.senaryo)

| XML ID | Kod | Açıklama |
|--------|-----|----------|
| `mdx_senaryo_12` | `ILAC_TIBBICIHAZ` | İlaç ve Tıbbi Cihaz (yeni versiyon) |
| `mdx_senaryo_13` | `YATIRIMTESVIK` | Yatırım Teşvik |
| `mdx_senaryo_14` | `IDIS` | İDİS (İthalatta Damga Vergisi İstisna Sistemi) |
| `mdx_senaryo_15` | `IDISIRSALIYE` | İDİS İrsaliye |

### 3.3 Yeni Tip Kayıtları (mdx.ebelge.tipi)

| XML ID | Kod | Açıklama |
|--------|-----|----------|
| `mdx_tipi_18` | `TEKNOLOJIDESTEK` | Teknoloji Geliştirme Desteği |
| `mdx_tipi_19` | `YTBSATIS` | YTB Satış |
| `mdx_tipi_20` | `YTBIADE` | YTB İade |
| `mdx_tipi_21` | `YTBISTISNA` | YTB İstisna |
| `mdx_tipi_22` | `YTBTEVKIFAT` | YTB Tevkifat |
| `mdx_tipi_23` | `YTBTEVKIFATIADE` | YTB Tevkifat İade |

### 3.4 İstisna/Tevkifat Kodları

Mevcut `mdx.sabit.kod` kayıtlarında 308, 339, 555, 702 kodları doğrulandı.

---

## 4. FAZ 2 — Validasyon Kuralları (mdx_inh_account_move.py)

### 4.1 VALID_PROFILE_TYPE_MATRIX

Modül seviyesinde tanımlanmış 12 ProfileID × InvoiceTypeCode matris dict'i:

```python
VALID_PROFILE_TYPE_MATRIX = {
    'TICARIFATURA': ['SATIS', 'TEVKIFAT', 'TEVKIFATIADE', 'ISTISNA', 'OZELMATRAH', 'IHRACKAYITLI'],
    'TEMELFATURA': ['SATIS', 'IADE', 'TEVKIFAT', 'TEVKIFATIADE', 'ISTISNA', 'OZELMATRAH', 'IHRACKAYITLI'],
    'IHRACAT': ['SATIS', 'ISTISNA'],
    'KAMU': ['SATIS', 'IADE', 'TEVKIFAT', 'TEVKIFATIADE', 'ISTISNA', 'OZELMATRAH'],
    'OZELFATURA': ['SATIS', 'IADE', 'TEVKIFAT', 'TEVKIFATIADE', 'ISTISNA', 'OZELMATRAH'],
    'YOLCUBERABERFATURA': ['SATIS', 'ISTISNA'],
    'HKS': ['HKSSATIS', 'HKSKOMISYONCU'],
    'ENERJI': ['SARJ', 'SARJANLIK'],
    'ILAC_TIBBICIHAZ': ['SATIS', 'ISTISNA', 'TEVKIFAT', 'TEVKIFATIADE', 'IADE', 'IHRACKAYITLI'],
    'YATIRIMTESVIK': ['SATIS', 'ISTISNA', 'IADE', 'TEVKIFAT', 'TEVKIFATIADE'],
    'IDIS': ['SATIS', 'ISTISNA', 'IADE', 'TEVKIFAT', 'TEVKIFATIADE', 'IHRACKAYITLI'],
    'EARSIVFATURA': [
        'SATIS', 'IADE', 'TEVKIFAT', 'TEVKIFATIADE', 'ISTISNA', 'OZELMATRAH', 'IHRACKAYITLI',
        'SGK', 'KOMISYONCU', 'HKSSATIS', 'HKSKOMISYONCU', 'KONAKLAMAVERGISI',
        'SARJ', 'SARJANLIK', 'TEKNOLOJIDESTEK',
        'YTBSATIS', 'YTBIADE', 'YTBISTISNA', 'YTBTEVKIFAT', 'YTBTEVKIFATIADE',
    ],
}
```

### 4.2 Constraint Metotları (10 adet)

| # | Metot | Kural | Trigger Koşulu |
|---|-------|-------|----------------|
| 1 | `_check_profile_type_matrix` | Senaryo ↔ Tip geçerli kombinasyon kontrolü | Her kayıtta |
| 2 | `_check_kamu_iban` | KAMU senaryosunda `kamu_iban` zorunlu | `efatura_senaryo_id.code == 'KAMU'` |
| 3 | `_check_iade_billing_reference` | İADE/TEVKIFATIADE/YTBIADE/YTBTEVKIFATIADE → BillingReference zorunlu | İlgili tipler |
| 4 | `_check_sgk_receiver` | SGK tipi → alıcı VKN `7640235439` | `efatura_tipi_id.code == 'SGK'` |
| 5 | `_check_teknolojidestek_tckn` | TEKNOLOJIDESTEK → alıcıda TCKN zorunlu | `code == 'TEKNOLOJIDESTEK'` |
| 6 | `_check_yatirim_tesvik` | YATIRIMTESVIK → `ytb_no` zorunlu + format (`B/yyy/nnn`) | `code == 'YATIRIMTESVIK'` |
| 7 | `_check_idis` | İDİS → `idis_sevkiyat_no` zorunlu + format (`SE-nnnnnnn`) | `code in ('IDIS', 'IDISIRSALIYE')` |
| 8 | `_check_ilac_tibbi_cihaz_lines` | ILAC_TIBBICIHAZ → en az 1 satırda `ilac_item_type` | Senaryo kodu kontrol |
| 9 | `_check_teknolojidestek_lines` | TEKNOLOJIDESTEK → en az 1 satırda `teknoloji_cihaz_tipi` | Tip kodu kontrol |
| 10 | `_check_hks_kunyeno` | HKS → en az 1 satırda `hks_kunye_no` | Senaryo kodu kontrol |

### 4.3 SQL Constraint

```python
_sql_constraints = [
    ('efatura_uuid_unique', 'UNIQUE(efatura_uuid)', 'e-Fatura UUID değeri benzersiz olmalıdır!'),
]
```

### 4.4 `_onchange_efatura_senaryo_id`

Senaryo değiştiğinde tip listesini VALID_PROFILE_TYPE_MATRIX'e göre dinamik filtreler. Mevcut tip matrise uymuyorsa otomatik temizler.

### 4.5 `action_post` Genişletmesi

`action_post` override'ına ~85 satır V2 validasyon kodu eklenmiştir:
- Matris kontrolü (Schematron uyumu)
- İstisna kodu zorunluluk kontrolü (ISTISNA/YTBISTISNA → `tax_exemption_reason_code` zorunlu)
- İhraç Kayıtlı kontrolleri
- KAMU → IBAN kontrolü
- SGK → alıcı VKN kontrolü
- KonaklamaVergisi → 0059 vergi kodu kontrolü
- TEKNOLOJIDESTEK → TCKN kontrolü
- YATIRIMTESVIK → YTB No kontrolü
- İDİS → Sevkiyat No kontrolü
- YTB İade tipleri → BillingReference kontrolü

---

## 5. FAZ 3 — XML Üretimi (mdx_utility_mixin.py)

`generate_invoice_xml()` metodunda 19 kritik değişiklik yapılmıştır:

### 5.1 Yapısal XML Değişiklikleri

| # | Değişiklik | Açıklama |
|---|-----------|----------|
| 1 | BillingReference genişletme | YTBIADE, YTBTEVKIFATIADE tipleri için iade referansı |
| 2 | ContractDocumentReference | YATIRIMTESVIK → YTB numarası |
| 3 | İDİS PartyIdentification | Sevkiyat No → AccountingCustomerParty |
| 4 | TaxRepresentativeParty | YOLCUBERABERFATURA → pasaport no, uyruk |
| 5 | PaymentMeans | KAMU → IBAN bilgisi |
| 6 | KonaklamaVergisi TaxTotal | 0059 vergi kodu |
| 7 | İstisna TaxTotal genişletme | ISTISNA + YTBISTISNA |
| 8 | WithholdingTaxTotal genişletme | YTB tevkifat tipleri |
| 9 | LegalMonetaryTotal genişletme | YTB tipleri |
| 10 | Satır-seviye İhraç Kayıtlı | TaxExemptionReason satır seviyesinde |
| 11 | Satır-seviye Tevkifat genişletme | YTB tevkifat tipleri eklendi |
| 12 | AllowanceCharge | Gerçek iskonto hesaplama mantığı |
| 13 | AdditionalItemIdentification | İLAÇ, İDİS, HKS, TEKNOLOJİDESTEK, İHRAÇKAYITLI 702 |
| 14 | CommodityClassification + ItemInstance | YATIRIMTESVIK harcama tipi, makine bilgileri |

### 5.2 Veri Güvenliği ve Doğruluk

| # | Değişiklik | Açıklama |
|---|-----------|----------|
| 15 | `_sanitize_xml_text()` | XML injection koruması (company_name, address, receiver, açıklama, satır açıklamaları) |
| 16 | 2 ondalık yuvarlama | LineExtensionAmount, AllowanceCharge, TaxTotal tutarları |
| 17 | PriceAmount format | `{:.2f}` formatı ayrıca uygulanır |
| 18 | SellersItemIdentification | `product_id.id` kullanımı |
| 19 | XML sanitizasyon entegrasyonu | Tüm kullanıcı girdileri `_sanitize_xml_text` ile temizlenir |

### 5.3 `_sanitize_xml_text` Statik Metot

```python
@staticmethod
def _sanitize_xml_text(text):
    """XML özel karakterlerini temizle, injection koruması"""
    if not text:
        return ''
    text = str(text)
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&apos;')
    # Control characters temizle
    import re
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    return text
```

---

## 6. FAZ 4 — Yeni Alanlar

### 6.1 Header Alanları (mdx_inh_account_move.py)

| Alan | Tip | Açıklama | Kullanım |
|------|-----|----------|----------|
| `ytb_no` | Char | Yatırım Teşvik Belgesi No | YATIRIMTESVIK senaryosu |
| `idis_sevkiyat_no` | Char | İDİS Sevkiyat No | İDİS/İDİSİRSALİYE |
| `yolcu_pasaport_no` | Char | Pasaport Numarası | YOLCUBERABERFATURA |
| `yolcu_uyruk` | Char | Yolcu Uyruk Bilgisi | YOLCUBERABERFATURA |
| `kamu_iban` | Char | Ödeme IBAN | KAMU senaryosu |
| `gib_iletim_durumu` | Selection | GIB İletim Durumu (6 durum) | Tüm e-faturalar |
| `gib_iletim_tarihi` | Datetime | GIB İletim Zaman Damgası | Tüm e-faturalar |
| `gib_red_nedeni` | Text | GİB Red Nedeni | Red durumunda |
| `fatura_suresi_asimi` | Boolean | Süre Aşımı İşareti | VUK 231/5 cron |
| `efatura_xml_arsiv` | Binary | XML Arşiv Kopyası | Tüm e-faturalar |
| `efatura_xml_hash` | Char(64) | SHA-256 XML Hash | Bütünlük doğrulaması |

### 6.2 `gib_iletim_durumu` Selection Değerleri

```python
[
    ('taslak', 'Taslak'),
    ('gonderildi', 'Gönderildi'),
    ('teslim_alindi', 'Teslim Alındı'),
    ('kabul_edildi', 'Kabul Edildi'),
    ('red_edildi', 'Red Edildi'),
    ('iptal', 'İptal'),
]
```

### 6.3 Satır Alanları (mdx_inh_account_move_line.py — 14 adet)

| Alan | Tip | Açıklama |
|------|-----|----------|
| `ilac_item_type` | Selection | İlaç/Tıbbi Cihaz Türü (ilac/tibbi_cihaz) |
| `ilac_karekod` | Char | İlaç Karekod (ITS/ÜTS) |
| `ytb_harcama_tipi` | Char | YTB Harcama Tipi Kodu |
| `ytb_makine_adi` | Char | Makine/Teçhizat Adı |
| `ytb_seri_no` | Char | Makine Seri Numarası |
| `ytb_makine_id` | Char | Makine Sicil Numarası |
| `idis_etiket_no` | Char | İDİS Etiket No |
| `teknoloji_cihaz_tipi` | Selection | Teknoloji Cihaz Tipi (bilgisayar/tablet/yazici/diger) |
| `teknoloji_imei` | Char | IMEI/Seri No |
| `hks_kunye_no` | Char | HKS Künye Numarası |
| `satici_dib_satir_kodu` | Char | Satıcı DİB Satır Kodu |
| `alici_dib_satir_kodu` | Char | Alıcı DİB Satır Kodu |

---

## 7. FAZ 5 — Şirket Ayarları (mdx_inh_res_company.py)

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `kdv_tevkifat_alt_sinir` | Float | 6900.0 | KDV Tevkifat Alt Sınır (TL) — yıllık güncellenir |
| `qnb_test_mode` | Boolean | - | QNB eFinans Test Modu açık/kapalı |
| `qnb_test_url` | Char | - | QNB Test Ortamı URL |
| `qnb_prod_url` | Char | - | QNB Üretim Ortamı URL |

---

## 8. FAZ 6 — Görünümler (Views)

### 8.1 Fatura Formu (mdx_inh_account_move_views.xml)

**Yeni Bölümler:**

1. **Senaryo Detayları** grubu:
   - `ytb_no` → `invisible="efatura_senaryo_id.code != 'YATIRIMTESVIK'"`
   - `idis_sevkiyat_no` → `invisible="efatura_senaryo_id.code not in ('IDIS', 'IDISIRSALIYE')"`
   - `yolcu_pasaport_no` → `invisible="efatura_senaryo_id.code != 'YOLCUBERABERFATURA'"`
   - `yolcu_uyruk` → `invisible="efatura_senaryo_id.code != 'YOLCUBERABERFATURA'"`
   - `kamu_iban` → `invisible="efatura_senaryo_id.code != 'KAMU'"`

2. **GIB İletim Durumu** grubu:
   - `gib_iletim_durumu` → statusbar widget
   - `gib_iletim_tarihi` → readonly
   - `gib_red_nedeni` → invisible (red durumu hariç)
   - `efatura_xml_arsiv` → download widget
   - `efatura_xml_hash` → readonly

3. **Satır Alanları** (tree view, `optional="hide"`):
   - 14 yeni alan, ilgili senaryo/tip seçimine göre `column_invisible` attrs

### 8.2 Şirket Ayarları (mdx_inh_res_company_views.xml)

1. **E-Dönüşüm Ek Ayarları**: `kdv_tevkifat_alt_sinir`
2. **QNB eFinans Bağlantı Ayarları**: `qnb_test_mode`, `qnb_test_url`, `qnb_prod_url`

---

## 9. FAZ 7 — QNB eFinans Entegrasyon Güçlendirmesi

### 9.1 QNB Hata Kodları

`QNB_ERROR_CODES` dict — sık karşılaşılan QNB SOAP hata kodları ve Türkçe açıklamaları.

### 9.2 Retry Mekanizması

`send_invoice_xml()` metodunda:
- `MAX_RETRY = 3`
- Exponential backoff: 2, 4, 8 saniye
- `timeout=60` (socket timeout)
- Test/prod URL seçimi: `company.qnb_test_mode` → `company.qnb_test_url` veya `company.qnb_prod_url`
- Hata kodu eşleme: QNB SOAP fault → `QNB_ERROR_CODES` → kullanıcı dostu Türkçe mesaj

---

## 10. FAZ 8 — Best Practices

### 10.1 Cron Job (data/cron_jobs.xml)

```xml
<record id="ir_cron_check_fatura_suresi_asimi" model="ir.cron">
    <field name="name">E-Fatura Süre Aşımı Kontrolü (VUK 231/5)</field>
    <field name="model_id" ref="account.model_account_move"/>
    <field name="state">code</field>
    <field name="code">model._cron_check_fatura_suresi_asimi()</field>
    <field name="interval_number">1</field>
    <field name="interval_type">days</field>
    <field name="nextcall">2025-01-01 05:00:00</field>
    <field name="numbercall">-1</field>
    <field name="active">True</field>
</record>
```

### 10.2 `_cron_check_fatura_suresi_asimi()` Metodu

- VUK Madde 231/5 uyarınca 7 günlük süre aşımını kontrol eder
- `posted` durumundaki, `efatura_uuid` olan ama `gib_iletim_durumu` henüz `gonderildi`/`teslim_alindi`/`kabul_edildi` olmayan faturaları bulur
- `fatura_suresi_asimi = True` işaretler
- `_logger.warning()` ile loglar

---

## 11. ProfileID × InvoiceTypeCode Tam Matris

| ProfileID | Geçerli InvoiceTypeCode'lar |
|-----------|----------------------------|
| TICARIFATURA | SATIS, TEVKIFAT, TEVKIFATIADE, ISTISNA, OZELMATRAH, IHRACKAYITLI |
| TEMELFATURA | SATIS, IADE, TEVKIFAT, TEVKIFATIADE, ISTISNA, OZELMATRAH, IHRACKAYITLI |
| IHRACAT | SATIS, ISTISNA |
| KAMU | SATIS, IADE, TEVKIFAT, TEVKIFATIADE, ISTISNA, OZELMATRAH |
| OZELFATURA | SATIS, IADE, TEVKIFAT, TEVKIFATIADE, ISTISNA, OZELMATRAH |
| YOLCUBERABERFATURA | SATIS, ISTISNA |
| HKS | HKSSATIS, HKSKOMISYONCU |
| ENERJI | SARJ, SARJANLIK |
| ILAC_TIBBICIHAZ | SATIS, ISTISNA, TEVKIFAT, TEVKIFATIADE, IADE, IHRACKAYITLI |
| YATIRIMTESVIK | SATIS, ISTISNA, IADE, TEVKIFAT, TEVKIFATIADE |
| IDIS | SATIS, ISTISNA, IADE, TEVKIFAT, TEVKIFATIADE, IHRACKAYITLI |
| EARSIVFATURA | SATIS, IADE, TEVKIFAT, TEVKIFATIADE, ISTISNA, OZELMATRAH, IHRACKAYITLI, SGK, KOMISYONCU, HKSSATIS, HKSKOMISYONCU, KONAKLAMAVERGISI, SARJ, SARJANLIK, TEKNOLOJIDESTEK, YTBSATIS, YTBIADE, YTBISTISNA, YTBTEVKIFAT, YTBTEVKIFATIADE |

---

## 12. Teknik Notlar

### 12.1 Veritabanı Göç (Migration)

- Yeni alanlar `store=True` olarak tanımlandığından Odoo otomatik `ALTER TABLE` yapacaktır.
- `initial_data.xml` içindeki yeni kayıtlar `noupdate="1"` olmadığından modül güncellemesinde otomatik yüklenecektir.
- `efatura_uuid` SQL UNIQUE constraint eklenmiştir — mevcut duplike kayıtlar varsa güncelleme önce temizlenmelidir.

### 12.2 Bağımlılıklar

- Yeni bir Python paketi **gerekmez**.
- Odoo standart modüllere bağımlılık değişmemiştir: `base`, `account`, `stock_account`, `sale_stock`, `hr`, `purchase`, `stock`, `stock_delivery`, `mail`, `l10n_tr`.
- `__manifest__.py`'de `data/cron_jobs.xml` mevcut manifest'te kayıtlıdır.

### 12.3 Performans

- `VALID_PROFILE_TYPE_MATRIX` modül seviyesinde dict olduğundan her kayıt için DB sorgusu yapılmaz.
- Cron günde 1 kez çalışır — performans etkisi minimumdur.
- QNB retry mekanizması exponential backoff ile sisteme aşırı yük binmesini önler.

---

## 13. V2.1 — Hata Yönetimi Altyapısı (Nisan 2026)

### 13.1 Genel Bakış

V2.1 güncellemesi ile kapsamlı bir hata yönetimi altyapısı eklenmiştir. Bu altyapı 4 AbstractModel mixin, 1 transaction log modeli, 1 wizard ve ilgili view/cron/security kayıtlarından oluşur.

**Mimari:**
- **14 hata kategorisi**: AUTH, VAL_RECEIVER, VAL_SENDER, VAL_LINE, VAL_TAX, FORMAT, SERIES, SYSTEM, EXPORT, TOURIST, SGK, PUBLIC, PAYMENT, DESPATCH
- **4 ciddiyet seviyesi**: CRITICAL, ERROR, WARNING, INFO
- **157 öntanımlı hata kodu** (`mdx.efatura.hata.kodu` — mevcut V2'den)
- **SAVEPOINT tabanlı atomik seri yönetimi**
- **Exponential backoff retry**: 5, 15, 60, 240 dakika

### 13.2 Yeni Modeller

#### 13.2.1 `mdx.efatura.islem` (İşlem Takip Modeli)

**Dosya:** `models/mdx_efatura_islem.py`

Tüm e-fatura gönderim işlemlerini kayıt altına alan transaction log modeli.

| Alan | Tip | Açıklama |
|------|-----|----------|
| `name` | Char | Otomatik sıra numarası (EFI-######) |
| `document_ref` | Reference | account.move / stock.picking referansı |
| `document_type` | Selection | EFATURA / EARSIV / EIHRACAT / EIRSALIYE |
| `state` | Selection | draft / validating / sending / sent / error / retry_scheduled / cancelled |
| `error_code_id` | Many2one | mdx.efatura.hata.kodu referansı |
| `error_message` | Text | Ham hata mesajı |
| `error_display` | Html (computed) | Formatlanmış hata gösterimi |
| `retry_count` | Integer | Mevcut deneme sayısı |
| `max_retry` | Integer | Maksimum deneme (varsayılan 4) |
| `last_attempt_date` | Datetime | Son deneme zamanı |
| `next_retry_date` | Datetime | Bir sonraki retry zamanı |
| `can_retry` | Boolean (stored computed) | Yeniden denenebilir mi |
| `series_id` | Many2one | Kullanılan seri |
| `series_number` | Integer | Seri numarası |
| `series_confirmed` | Boolean | Seri onaylandı mı |
| `xml_content` | Text | Gönderilen XML içeriği |
| `response_content` | Text | Alınan yanıt içeriği |

**Önemli Metotlar:**
- `_compute_error_display()`: Hata kodu + mesaj + ciddiyet bilgisini HTML formatında gösterir
- `_compute_can_retry()`: `error_code_id.is_retryable` ve `retry_count < max_retry` ve `state == 'error'` koşullarını kontrol eder
- `send_daily_error_report()`: Cron ile çalışan günlük hata raporu

#### 13.2.2 `mdx.pre.validation.mixin` (Ön Doğrulama)

**Dosya:** `models/mdx_pre_validation_mixin.py`

AbstractModel. e-Fatura gönderimi öncesinde kapsamlı doğrulama yapar.

**Ana Metot:** `validate_invoice_before_send(invoice)` → Tüm alt doğrulayıcıları çağırır, hata listesi döndürür.

| Metot | Kontrol | Hata Kodları |
|-------|---------|-------------|
| `_validate_company_info()` | Şirket VKN, adres, ülke, şehir | EF0093-EF0097 |
| `_validate_partner_info()` | Müşteri VKN/TCKN, adres, şehir, ad | EF0089-EF0092, EF0119-EF0122 |
| `_validate_line_items()` | Ürün adı, miktar, birim, fiyat | EF0099-EF0102, EF0129 |
| `_validate_tax_info()` | Vergi varlığı, %0 KDV istisna kodu | EF0130, EF0150 |
| `_validate_series()` | Seri seçimi | EF0290 |
| `_validate_document_type_specific()` | İhracat GTB, alıcı e-fatura kaydı | EF0311, EF0028 |

**VKN/TCKN Ayrımı:** Partner `vat` alanı uzunluğuna göre: 10 karakter = VKN (tüzel), 11 karakter = TCKN (gerçek kişi).

**Hata Gösterimi:** `display_validation_errors(errors)` — Ciddiyet seviyesine göre gruplar, CRITICAL/ERROR → `UserError raise`, WARNING → onay ile devam.

#### 13.2.3 `mdx.series.manager.mixin` (Atomik Seri Yönetimi)

**Dosya:** `models/mdx_series_manager_mixin.py`

AbstractModel. PostgreSQL SAVEPOINT mekanizması ile atomik seri tahsis/geri alma.

| Metot | İşlev |
|-------|-------|
| `reserve_series_number(series_record, invoice_record)` | SAVEPOINT oluşturur, satırı `FOR UPDATE` ile kilitler, seri index'ini artırır, fatura numarası üretir (`{code}{zfill(9)}`) |
| `release_series_number(reservation)` | Hata durumunda `ROLLBACK TO SAVEPOINT` — seri numarası serbest bırakılır |
| `confirm_series_number(reservation)` | Başarı durumunda `RELEASE SAVEPOINT` — değişiklik kalıcılaşır |
| `validate_series_sequence(series_record, expected)` | Ardışık seri numarası doğrulaması |

**Çalışma Prensibi:**
1. Seri tahsis → SAVEPOINT oluştur → satır kilitle → index artır
2. Fatura gönder
3. Başarı → RELEASE SAVEPOINT (kalıcılaştır) / Hata → ROLLBACK TO SAVEPOINT (geri al)

#### 13.2.4 `mdx.retry.manager.mixin` (Otomatik Retry)

**Dosya:** `models/mdx_retry_manager_mixin.py`

AbstractModel. Exponential backoff ile otomatik yeniden deneme.

```python
RETRY_DELAYS = [5, 15, 60, 240]  # dakika cinsinden
```

| Metot | İşlev |
|-------|-------|
| `can_retry_transaction(transaction)` | Hata kodunun yeniden denenebilir olup olmadığını kontrol eder |
| `schedule_retry(transaction, immediate=False)` | `next_retry_date` hesaplar, state → `retry_scheduled` |
| `execute_retry(transaction)` | `action_send_einvoice_retry(transaction)` çağırır, başarı/başarısızlık yönetir |
| `process_retry_queue()` | Cron metodu — zamanı gelen retry_scheduled işlemleri çalıştırır |

### 13.3 Wizard

#### `mdx.efatura.retry.wizard`

**Dosya:** `wizard/mdx_efatura_retry_wizard.py`

TransientModel. Kullanıcının fatura formundan manuel retry yapmasını sağlar.

| Alan | Açıklama |
|------|----------|
| `invoice_id` | Fatura referansı |
| `transaction_id` | Son hatalı işlem (otomatik) |
| `error_display` | Mevcut hata gösterimi (related) |
| `can_retry` | Yeniden denenebilir mi (related) |
| `force_new_uuid` | Yeni UUID üret (varsayılan: True) |
| `force_new_series` | Seri numarasını sıfırla (varsayılan: False) |

**Metotlar:**
- `default_get()`: Aktif faturanın son error/retry_scheduled transaction'ını bulur
- `action_retry()`: Opsiyonel UUID yenileme, opsiyonel seri sıfırlama, fatura yeniden gönderme

### 13.4 `mdx_inh_account_move.py` Değişiklikleri

#### Yeni Alanlar

| Alan | Tip | Açıklama |
|------|-----|----------|
| `efatura_hata_durumu` | Selection | error / retry_scheduled |
| `efatura_hata_html` | Html | Hata banner HTML içeriği |
| `efatura_retry_possible` | Boolean | Retry yapılabilir mi |
| `efatura_transaction_count` | Integer (computed) | İlişkili işlem sayısı |

#### `action_send_einvoice()` Yeniden Yazımı

Mevcut gönderim metodu tam olarak yeniden yazılmıştır. Yeni akış:

1. **Ön doğrulama** → `mdx.pre.validation.mixin.validate_invoice_before_send()`
2. **İrsaliye kontrolü** (mevcut mantık korundu)
3. **Seri tahsisi** → `mdx.series.manager.mixin.reserve_series_number()` + SAVEPOINT
4. **XML üretimi** → mevcut `generate_invoice_xml()` + error handler entegrasyonu
5. **İşlem kaydı oluşturma** → `mdx.efatura.islem` create
6. **Fatura gönderimi** → Hata durumunda `mdx.efatura.hata.kodu` eşleme + retry planlama
7. **Başarı** → Seri onaylama, işlem güncelleme, hata alanlarını temizleme
8. **Exception** → `finally` bloğunda seri reservation her zaman release edilir

#### Yeni Metotlar

| Metot | İşlev |
|-------|-------|
| `_compute_efatura_transaction_count()` | İlişkili `mdx.efatura.islem` sayısını hesaplar |
| `action_send_einvoice_retry(transaction)` | Retry manager tarafından çağrılır, `{success: bool}` döndürür |
| `action_retry_efatura()` | Retry wizard'ını açar |
| `action_view_efatura_transactions()` | İşlem geçmişi smart button action |
| `_write_error_fields(error_result)` | Hata bilgilerini account.move alanlarına yazar |
| `_find_error_record(error_code)` | `mdx.efatura.hata.kodu` tablosundan hata kaydı bulur |

### 13.5 View Değişiklikleri

#### Fatura Formu (`mdx_inh_account_move_views.xml`)

1. **Hata Banner'ı** (sheet öncesi):
   - `alert-danger` div — `efatura_hata_html` içeriği
   - "Tekrar Dene" butonu (`efatura_retry_possible` koşullu)
   - "İşlem Geçmişi" butonu (`efatura_transaction_count > 0` koşullu)

2. **Smart Button**:
   - `fa-history` ikon, `efatura_transaction_count` statinfo widget
   - Tıklandığında `action_view_efatura_transactions()` — filtrelenmiş işlem listesi

#### İşlem Takip Views (`mdx_efatura_islem_views.xml`)

- **List View**: decoration-danger/success/warning, badge widget ile durum gösterimi
- **Form View**: statusbar, belge/hata/retry/seri bilgi grupları, notebook (hata detayı, XML, yanıt)
- **Search View**: Hatalı, gönderildi, tekrar planlandı filtreler + grup-by (durum, belge türü, hata kodu)

#### Retry Wizard View (`mdx_efatura_wizard_views.xml`)

- Hata gösterimi, `force_new_uuid` / `force_new_series` checkbox'ları
- "Tekrar Gönder" (can_retry) ve "Zorla Gönder" (!can_retry) butonları

#### Menü (`mdx_lokalizasyon_menu_views.xml`)

Yeni **"İşlem Takip"** menü bölümü:
- E-Fatura İşlemleri → `action_mdx_efatura_islem`
- Hata Kodları → `action_mdx_efatura_hata_kodu`

### 13.6 Cron Jobs (V2.1)

| Cron | Sıklık | Metot | Açıklama |
|------|--------|-------|----------|
| E-Fatura Retry Queue | Her 5 dakika | `mdx.retry.manager.mixin.process_retry_queue()` | Zamanı gelen retry işlemlerini çalıştırır |
| E-Fatura Günlük Hata Raporu | Günlük 21:30 | `mdx.efatura.islem.send_daily_error_report()` | Yöneticilere hata özet raporu gönderir |

### 13.7 Security

`security/ir.model.access.csv`'ye eklenen kayıtlar:

| ID | Model | Grup | CRUD |
|----|-------|------|------|
| `access_mdx_efatura_islem` | `mdx.efatura.islem` | `base.group_user` | 1,1,1,1 |
| `access_mdx_efatura_retry_wizard` | `mdx.efatura.retry.wizard` | `base.group_user` | 1,1,1,1 |

### 13.8 `__manifest__.py`

- Versiyon: `18.18.76` → `18.18.77`
- `data` listesine eklenen: `views/mdx_efatura_islem_views.xml`, `views/mdx_efatura_wizard_views.xml`

---

## 14. V2.2 — İrsaliye Tür ve Profil Güncellemeleri

### 14.1 GIB Standart Uyumu — MATBUUDAN → MATBUDAN

**Problem:** Modülde `MATBUUDAN` (çift U) kullanılıyordu. GIB UBL-TR 1.2.1 Kod Listeleri ve resmi XML örneklerinde doğru yazım `MATBUDAN`'dır.

**Etkilenen Dosyalar:**

| Dosya | Değişiklik |
|-------|-----------|
| `data/initial_data.xml` | `mdx_ebelge_tipi_16`: code `MATBUUDAN` → `MATBUDAN`, name `Matbuudan` → `Matbudan` |
| `models/mdx_utility_mixin.py` | `irsaliye_tipi_id.code == "MATBUUDAN"` → `"MATBUDAN"` |
| `models/mdx_utility_mixin_030725.py` | Yedek dosyada aynı düzeltme |

### 14.2 VALID_DESPATCH_PROFILE_TYPE_MATRIX

`models/mdx_inh_stock_picking.py` dosyasına, faturalardaki `VALID_PROFILE_TYPE_MATRIX` benzeri bir irsaliye validasyon matrisi eklendi:

```python
VALID_DESPATCH_PROFILE_TYPE_MATRIX = {
    'TEMELIRSALIYE': ['SEVK', 'MATBUDAN'],
    'HKSIRSALIYE': ['SEVK', 'MATBUDAN'],
    'IDISIRSALIYE': ['SEVK', 'MATBUDAN'],
}
```

**GIB Kaynak:** UBL-TR 1.2.1 Schematron, GIB örnek XML dosyaları:
- `Irsaliye-Ornek1.xml`: TEMELIRSALIYE + SEVK
- `Irsaliye-Matbudan.xml`: TEMELIRSALIYE + MATBUDAN
- `IDIS_Irsaliye.xml`: IDISIRSALIYE + SEVK
- GIB Schematron'da MATBUDAN için profil kısıtlaması bulunmamaktadır (3 profil de MATBUDAN destekler)

### 14.3 Yeni Validasyon Metotları

| Metot | Tip | İşlev |
|-------|-----|-------|
| `_onchange_eirsaliye_senaryo_id()` | `@api.onchange` | Senaryo değiştiğinde uyumsuz irsaliye tipini temizler ve SEVK'e döndürür |
| `_check_despatch_profile_type()` | `@api.constrains` | ProfileID ↔ DespatchAdviceTypeCode matris validasyonu |
| `_check_matbudan_fields()` | `@api.constrains` | MATBUDAN seçildiğinde `matbuu_belge_no` ve `matbuu_belge_tarihi` zorunluluğu |
| `_check_idis_sevkiyat_no()` | `@api.constrains` | IDISIRSALIYE → `idis_sevkiyat_no` zorunlu + SE-NNNNNNN format kontrolü |
| `_check_hks_kunye_no()` | `@api.constrains` | HKSIRSALIYE → her satırda `hks_kunye_no` zorunlu (19 karakter) |
| `_check_idis_etiket_no()` | `@api.constrains` | IDISIRSALIYE → her satırda `idis_etiket_no` zorunlu (2 harf + 7 rakam) |

### 14.4 Yeni Alanlar

#### stock.picking (`mdx_inh_stock_picking.py`)

| Alan | Tip | Açıklama |
|------|-----|----------|
| `idis_sevkiyat_no` | `Char(size=10)` | İDİS Sevkiyat No (SE-NNNNNNN) — IDISIRSALIYE senaryosunda zorunlu |

#### stock.move (`mdx_inh_stock_move.py`)

| Alan | Tip | Açıklama |
|------|-----|----------|
| `hks_kunye_no` | `Char(size=19)` | HKS Künye No — HKSIRSALIYE senaryosunda her satır için zorunlu |
| `idis_etiket_no` | `Char(size=9)` | İDİS Etiket No (2 harf + 7 rakam) — IDISIRSALIYE senaryosunda her satır için zorunlu |

### 14.5 XML Üretimi Güncellemeleri (`mdx_utility_mixin.py`)

#### DespatchSupplierParty — SEVKIYATNO

IDISIRSALIYE senaryosunda, `DespatchSupplierParty > Party` içine VKN PartyIdentification'dan sonra SEVKIYATNO eklenir:

```xml
<cac:PartyIdentification>
    <cbc:ID schemeID="SEVKIYATNO">SE-0000001</cbc:ID>
</cac:PartyIdentification>
```

#### DespatchLine — KUNYENO (HKSIRSALIYE)

Her DespatchLine > Item içine AdditionalItemIdentification olarak:

```xml
<cac:AdditionalItemIdentification>
    <cbc:ID schemeID="KUNYENO">1234567890123456789</cbc:ID>
</cac:AdditionalItemIdentification>
```

#### DespatchLine — ETIKETNO (IDISIRSALIYE)

Her DespatchLine > Item içine AdditionalItemIdentification olarak:

```xml
<cac:AdditionalItemIdentification>
    <cbc:ID schemeID="ETIKETNO">AB1234567</cbc:ID>
</cac:AdditionalItemIdentification>
```

### 14.6 Görünüm Güncellemeleri (`mdx_inh_stock_picking_views.xml`)

| Değişiklik | Koşul |
|-----------|-------|
| `idis_sevkiyat_no` alanı E-İrsaliye Bilgileri grubuna eklendi | `eirsaliye_senaryo_id.code == 'IDISIRSALIYE'` olduğunda görünür |
| `matbuu_belge_no` / `matbuu_belge_tarihi` koşullu görünürlük | `irsaliye_tipi_id.code == 'MATBUDAN'` olduğunda görünür |
| `hks_kunye_no` / `idis_etiket_no` stock.move form'a eklendi | İlgili alan doluyken görünür |

### 14.7 İrsaliye Senaryo-Tip Kısıtlamaları

| Senaryo (ProfileID) | Kullanılabilir Tipler (DespatchAdviceTypeCode) | Ek Zorunluluklar |
|---------------------|-----------------------------------------------|------------------|
| TEMELIRSALIYE | SEVK, MATBUDAN | — |
| HKSIRSALIYE | SEVK, MATBUDAN | Her satırda `hks_kunye_no` (19 karakter) zorunlu |
| IDISIRSALIYE | SEVK, MATBUDAN | `idis_sevkiyat_no` (SE-NNNNNNN) zorunlu, her satırda `idis_etiket_no` (2 harf + 7 rakam) zorunlu |

### 14.8 `__manifest__.py`

- Versiyon: `18.18.77` → `18.18.78`

---

## 15. Uyumluluk Durumu

| FAZ | Açıklama | Uyumluluk |
|-----|----------|-----------|
| FAZ 1 | Veri Modeli Düzeltmeleri | ✅ %100 |
| FAZ 2 | ProfileID ↔ InvoiceTypeCode Validasyonları | ✅ %100 |
| FAZ 3 | XML Üretimi Güncellemeleri | ✅ %100 |
| FAZ 4 | Yeni Senaryolara Özel Alanlar | ✅ %100 |
| FAZ 5 | res.company ve Yasal Parametreler | ✅ %100 |
| FAZ 6 | Görünümler (Views) | ✅ %100 |
| FAZ 7 | QNB eFinans Entegrasyon Güçlendirmesi | ✅ %100 |
| FAZ 8 | Best Practices ve Cron Jobs | ✅ %100 |
| V2.1 | Hata Yönetimi Altyapısı | ✅ %100 |
| V2.2 | İrsaliye Tür/Profil Güncellemeleri | ✅ %100 |
| **TOPLAM** | | **✅ %100** |
