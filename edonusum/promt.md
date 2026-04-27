

# Gelen Fatura Renklendirme - Özet

## 🎯 Ne Yaptık?

Gelen Fatura listesinde satırları durumlarına göre renkli gösterme özelliği ekledik.

### Renk Kuralları:

| Renk | Anlam | Koşul |
|------|-------|-------|
| 🟢 Yeşil | Onaylanmış, kaydedilebilir fatura | `supplier_id` var VE `fatura_onay_statu` = '2' veya '-1' |
| 🔵 Mavi | Henüz onaylanmamış | `fatura_onay_statu` = '0' (Yanıt Bekleniyor) |
| 🔴 Kırmızı | VKN bulunamadı, cari eşleştirilemedi | `supplier_id` boş (False) |

---

## 📁 Değiştirilen Dosyalar

### 1. `models/mdx_gelen_fatura.py`
- **`fatura_durum_text`** computed field eklendi
- Her satırda durumu gösteriyor: ✅ Kaydedilebilir / ⏳ Onay Bekleniyor / ⛔ Cari Eşleştirilemedi
- **`create()`** metodu düzeltildi: API hatası artık kayıt oluşturmayı engellemez

### 2. `views/mdx_gelen_fatura_views.xml`
- `decoration-success` (yeşil), `decoration-info` (mavi), `decoration-danger` (kırmızı) eklendi
- **Durum** kolonu eklendi (fatura_durum_text alanı)
- `supplier_id` ve `fatura_onay_statu` gizli alanlar olarak eklendi (renklendirme koşulları için gerekli)

### 3. `static/src/css/gelen_fatura_colors.css` (YENİ)
- Dolgulu arka plan renkleri (yeşil/mavi/kırmızı)
- Sol kenarda kalın renk çubuğu
- Hover efektleri

### 4. `__manifest__.py`
- CSS dosyası `assets > web.assets_backend` olarak eklendi

---

## 🖥️ Odoo.sh Shell Kullanım Rehberi

### Shell'e Giriş:

```bash
# 1. Odoo.sh panelinde SHELL sekmesine tıkla
# 2. Bash terminali açılır. Python shell'e geçmek için:
odoo-bin shell
# 3. "In [1]:" yazısını gör = Python shell hazır!
```

### Temel Komutlar:

```python
# --- KAYIT ARAMA ---
# Tedarikçileri listele
partners = env['res.partner'].search([('supplier_rank', '>', 0)], limit=5)
for p in partners:
    print(f"VKN: {p.vat}, İsim: {p.name}")

# Gelen faturaları listele
faturalar = env['mdx.gelen.fatura'].search([], limit=10)
for f in faturalar:
    print(f"ID: {f.id}, Belge: {f.name}, Statu: {f.fatura_onay_statu}, Supplier: {f.supplier_id.name}")

# --- KAYIT OLUŞTURMA ---
yeni = env['mdx.gelen.fatura'].create({
    'name': 'TEST-001',
    'belge_sira_no': 9001,
    'belge_tarihi': '2026-02-24',
    'ettn': 'test-001',
    'gonderen_vkn_tckn': '0071976',
    'satici_unvan': 'Test Firma',
    'fatura_onay_statu': '-1',
    'odenecek_tutar': 1000.0,
})
env.cr.commit()  # Veritabanına kaydet!
print(f"Oluşturuldu: ID={yeni.id}")

# --- KAYIT GÜNCELLEME ---
kayit = env['mdx.gelen.fatura'].search([('ettn', '=', 'test-001')], limit=1)
kayit.write({'fatura_onay_statu': '0'})  # Statüyü değiştir
env.cr.commit()

# --- KAYIT SİLME ---
tests = env['mdx.gelen.fatura'].search([('ettn', 'like', 'test-')])
tests.unlink()
env.cr.commit()
print("Test kayıtları silindi")

# --- SHELL'DEN ÇIKIŞ ---
exit()
```

### Modül Güncelleme (Bash'te):

```bash
# View/model değişikliklerinden sonra:
odoo-update edonusum

# Servisi yeniden başlat:
odoosh-restart
```

---

## 🧪 Test Verisi Oluşturma

Shell'de 3 farklı renk için test kayıtları:

```python
# YEŞİL: supplier eşleşmiş + onay gerekmiyor
env['mdx.gelen.fatura'].create({
    'name': 'TEST-YESIL', 'belge_sira_no': 9001,
    'belge_tarihi': '2026-02-24', 'ettn': 'test-yesil',
    'gonderen_vkn_tckn': '0071976',  # varolan VKN
    'satici_unvan': 'Yeşil Test', 'fatura_onay_statu': '-1',
    'odenecek_tutar': 1000.0,
})

# KIRMIZI: supplier eşleşmemiş
env['mdx.gelen.fatura'].create({
    'name': 'TEST-KIRMIZI', 'belge_sira_no': 9003,
    'belge_tarihi': '2026-02-24', 'ettn': 'test-kirmizi',
    'gonderen_vkn_tckn': '0000000000',  # var olmayan VKN
    'satici_unvan': 'Kırmızı Test', 'fatura_onay_statu': '-1',
    'odenecek_tutar': 3000.0,
})
env.cr.commit()

# MAVİ: create metodu statüyü ezdiği için, sonradan güncelle
mavi = env['mdx.gelen.fatura'].create({
    'name': 'TEST-MAVI', 'belge_sira_no': 9002,
    'belge_tarihi': '2026-02-24', 'ettn': 'test-mavi',
    'gonderen_vkn_tckn': '0071976',
    'satici_unvan': 'Mavi Test', 'odenecek_tutar': 2000.0,
})
mavi.write({'fatura_onay_statu': '0'})  # Sonradan mavi yap
env.cr.commit()

print("✅ 3 test kaydı oluşturuldu!")
```

### Test Temizleme:
```python
tests = env['mdx.gelen.fatura'].search([('ettn', 'like', 'test-')])
tests.unlink()
env.cr.commit()
print("🗑️ Test kayıtları silindi")
```

Bakalım, edonusum modülünün tüm yapısını ve gelen fatura akışını inceleyelim:

Analyzed
edonusum
Analyzed
edonusum/models
3 results
2 results
Analyzed
6 results
0 results
Analyzed
Analyzed
12 results
Analyzed
İşte tüm akışın özeti:

🔄 Gelen Fatura Akışı - Nereden Tetikleniyor?
Tek Kaynak: QNB eFinans API (EFINANS_ALICI)
Gelen faturalar manuel oluşturulamaz çünkü tüm akış QNB eFinans web servisine bağlı:

QNB eFinans (SOAP API)
       ↓
  EFINANS_ALICI web servisi
       ↓
  mdx.utility.mixin.search_incoming_invoices()
       ↓
  mdx.gelen.fatura → create()
Tetikleme Yolları (2 yol):
Yol	Nasıl	Ne Yapar
1. Manuel buton	List view'da "E-Fatura Sorgula" butonuna tıkla	

action_search_incoming_invoice()
 → 

search_incoming_invoices()
2. Cron (Otomatik)	Her 5 dakikada bir	Sadece belge ekleri (HTML/PDF) için çalışıyor
Bağımlılıklar:
mdx.web.service tablosunda EFINANS_ALICI kaydı olmalı:

Alan	Açıklama
name	EFINANS_ALICI

url
QNB eFinans SOAP endpoint URL
username	eFinans kullanıcı adı
password	eFinans şifre
erp_code	ERP kodu
company_id	Doğru şirkete bağlı
active	True
Neden Manuel Oluşturulamıyor?
Çünkü 

create()
 metodu çağrıldığında otomatik olarak 

refresh_gelen_fatura_api_response()
 tetikleniyor - bu da API'den XML/detay çekmeye çalışıyor. API yapılandırması yoksa hata verir (biz bunu try-except ile sardık ama normalde engelliyor).

EFINANS_ALICI Nerelerde Kullanılıyor? (12 yerde!)
Hepsi 

mdx_utility_mixin.py
 içinde:


search_incoming_invoices()
 → Faturaları listele

get_incoming_invoice_html()
 → HTML ek çek

get_incoming_invoice_pdf()
 → PDF ek çek
accept_invoice() / reject_invoice() → Kabul/Red yanıtı
Ve daha fazlası...
Kısacası: Web Servisleri menüsünde EFINANS_ALICI kaydı doğru yapılandırılmadan gelen fatura çekilemez. Seniorunun dediği doğru! 👍


EFINANS_ALICI bilgilerini 2 yolla öğrenebilirsin:

Yol 1: Odoo Arayüzünden (en kolay)
Tarayıcıda → Muhasebe → Ayarlar (veya Lokalizasyon) → Web Servisleri menüsüne git. Orada EFINANS_ALICI kaydını göreceksin. Tüm URL, kullanıcı adı, şifre vs. orada.

Eğer menüyü bulamıyorsan, adres çubuğuna direkt yaz:

https://minddx-odoo-test2-staging-28722507.dev.odoo.com/odoo/mdx.web.service
Yol 2: Odoo Shell'den
python
ws = env['mdx.web.service'].search([])
for w in ws:
    print(f"Ad: {w.name}, URL: {w.url}, User: {w.username}, Pass: {w.password}, ERP: {w.erp_code}, Aktif: {w.active}")
⚠️ Bilmiyorsan kimden öğrenirsin?
Bu bilgiler QNB eFinans'tan gelir. Seniorundan veya muhasebe/IT ekibinden iste:

Ne	Kimden
URL	QNB eFinans entegrasyondan (genelde https://efaturaws.qnbefinans.com/... gibi)
Kullanıcı Adı / Şifre	QNB eFinans portal yöneticisinden
ERP Kodu	QNB eFinans sözleşmesinden
VKN	Şirketin vergi numarası (Odoo'da zaten res.company'de var)
Senioruna sor: "EFINANS_ALICI web servisi için kullanıcı adı, şifre ve URL bilgilerini alabilir miyim?"

Kayıt yoksa ona yeni oluşturup oradan girebilirsiniz.









Bu görev res.partner (Müşteri Kartı) üzerinde saha düzenlemesi. Hadi bakalım ne var ne yok:

Analyzed

Analyzed

Şimdi mevcut partner alanlarını da görelim:

Analyzed
Görev analizi tamam! İşte bu görevin özeti:

📋 Görev #2161 Analizi: Müşteri Kartı Saha Düzenleme
Bu görev res.partner (Müşteri/Cari Kartı) üzerinde 3 ana değişiklik istiyor:

🧩 1. "EKLENTİLER" Grubu Eklenmesi
6 adet Boolean (var/yok) alan:

Prozon IK Entegrasyonu
Netekstre Entegrasyonu
Netahsilat Entegrasyonu
E-Mutabakat Entegrasyonu
BulutTahsilat Entegrasyonu
Mikrokom IK Entegrasyonu
🗂️ 2. Sekme Düzenlemeleri
"DURUM & TARİHLER" → "GENEL BİLGİLER" olarak yeniden adlandır
"Bakım Yetkisi" alanını bu sekmeye taşı
"Canlı Şirket Sayısı" (integer) + "Canlı Şirketler" (text) alanları ekle
🔄 3. e-Dönüşüm / LİSANS Düzenlemeleri
"LİSANS & YETKİLER" → "LİSANS" olarak yeniden adlandır
Modül isimlerini küçük harfe çevir (E-Fatura → e-Fatura)
Her modül için "Şirket Sayısı" (integer) alanı ekle
⚠️ Ama dikkat!
Bu görev MOP (müşteri kartı) ile ilgili - yani muhtemelen farklı bir modülde (MOP veya CRM modülü). Edonusum modülünde şu an sadece "E-Dönüşüm" sekmesi var. "DURUM & TARİHLER", "LİSANS & YETKİLER" sekmeleri büyük ihtimalle başka bir modülde tanılı.

Bu göreve başlamak istiyor musun? Başlamadan önce "LİSANS & YETKİLER" ve "DURUM & TARİHLER" sekmelerinin hangi modülde olduğunu bulmamız lazım. Bunu staging'de partner formunu açıp bakarak yapabiliriz.