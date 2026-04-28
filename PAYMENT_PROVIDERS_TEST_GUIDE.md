# Türk Ödeme Sağlayıcıları — Test Rehberi

> Sipay · PayTR · Iyzico  
> Odoo 18 | Tarih: 2026-04-21

---

## 1. Modül Özeti

| Özellik | payment_sipay | payment_paytr | payment_iyzico |
|---|---|---|---|
| **Odoo Modül Adı** | `payment_sipay` | `payment_paytr` | `payment_iyzico` |
| **Provider code** | `sipay` | `paytr` | `iyzico` |
| **Versiyon** | 1.58 | 1.0 | — |
| **Yazar** | — | — | Odoo S.A. |
| **Auth Yöntemi** | Bearer token (app_id + app_secret → token) | HMAC-SHA256 (merchant_key + salt) | HMAC-SHA256 (IYZWSv2 header) |
| **3D Secure** | Var (paySmart3D) | Var (iframe) | Var (checkout form) |
| **Sandbox URL** | `provisioning.sipay.com.tr` ✅ | ❌ **Sandbox yok — her zaman CANLI** | `sandbox-api.iyzipay.com` ✅ |
| **Desteklenen Para Birimleri** | TRY, USD, EUR, GBP | TRY, USD, EUR, GBP | TRY, USD, EUR, GBP, CHF, NOK, RUB, IRR |
| **Manuel Capture** | Var (full_only) | Var (full_only) | Yok |
| **İade (Refund)** | Var (full_only) | Var (full_only) | Yok |
| **İptal (Void)** | Var | Yok | Yok |
| **Zorunlu Python Paketi** | `pycryptodome` (AES) | — | — |
| **Callback Alanı** | `invoice_id` | `merchant_oid` | `conversationId` |

---

## 2. Odoo Konfigürasyonu

### 2.1 Modül Yükleme

```
Ayarlar → Teknik → Modüller → Uygulama Yükle
```

- `payment_sipay` → **PyCryptodome gerekli**: `pip install pycryptodome`
- `payment_paytr` → Ekstra paket yok
- `payment_iyzico` → Ekstra paket yok

### 2.2 Provider Ayarları

```
Muhasebe → Konfigürasyon → Ödeme Sağlayıcıları
```

#### Sipay

| Alan | Değer |
|---|---|
| App ID | Sipay panelden al |
| App Secret | Sipay panelden al |
| Merchant Key | Sipay panelden al |
| Merchant ID | Sipay panelden al |
| Durum | **Test** (provisioning URL kullanılır) |

> ⚠️ Üretim URL (`app.sipay.com.tr`) kodda yorum satırı — aktif etmek için `payment_provider.py:82`'yi düzenle.

#### PayTR

| Alan | Değer |
|---|---|
| Merchant ID | PayTR panelden al |
| Merchant Key | PayTR panelden al |
| Merchant Salt | PayTR panelden al |
| Durum | ⚠️ **SANDBOX YOK** — Test için PayTR demo hesabı gerek |

> ⚠️ `_paytr_get_api_url()` her zaman `https://www.paytr.com/` döner. Test modu yok.

#### Iyzico

| Alan | Değer |
|---|---|
| Iyzico Key Id | Iyzico sandbox panelden al |
| Iyzico Key Secret | Iyzico sandbox panelden al |
| Durum | **Test** → sandbox-api.iyzipay.com |
| Durum | **Aktif** → api.iyzipay.com |

---

## 3. Akış Diyagramları

### 3.1 Sipay Akışı

```
Müşteri "Ödeme Yap" tıklar
  → Odoo: _sipay_get_token() → provisioning.sipay.com.tr/ccpayment/api/token
  → Token alınır, frontend'e gönderilir
  → JS: Kart bilgileri + AES hash hesaplanır
  → Müşteri: paySmart3D formuna POST edilir
  → Banka: 3D Secure sayfası
  → Sipay: POST /payment/sipay/return (invoice_id, status_code, sipay_status, hash_key)
  → Odoo: hash doğrulama + transaction state güncelleme
```

### 3.2 PayTR Akışı

```
Müşteri "Ödeme Yap" tıklar
  → Odoo controller: paytr_merchant_id + hash hesapla → www.paytr.com/odeme/api
  → PayTR: iframe token döner
  → Frontend: iframe gösterilir, kart bilgileri PayTR'de girilir
  → PayTR: POST /payment/paytr/return (merchant_oid, status, hash)
  → Odoo: hash doğrulama + transaction state güncelleme
```

### 3.3 Iyzico Akışı

```
Müşteri "Ödeme Yap" tıklar
  → Odoo: checkout form initialize → sandbox-api.iyzipay.com
  → paymentPageUrl alınır
  → Müşteri iyzipay checkout sayfasına yönlendirilir
  → Iyzico: GET /payment/iyzico/return?tx_ref=... (token ile)
  → Odoo: token → Iyzico API'dan ödeme detayı çek → state güncelle
```

---

## 4. Test Senaryoları

### S-01: Sipay — Başarılı 3D Secure Ödeme (Mutlu Yol)

**Ön koşul:** Sipay test hesabı, provisioning URL aktif, PyCryptodome kurulu  
**Para birimi:** TRY  
**Miktar:** 100.00

| Adım | Aksiyon | Beklenen Sonuç |
|---|---|---|
| 1 | Odoo e-ticaret ya da fatura ödeme sayfasına git | Sipay ödeme formu görünür |
| 2 | Test kart bilgilerini gir (aşağıda) | Form doldu |
| 3 | "Öde" tıkla | Sipay 3D sayfasına yönlendirilir |
| 4 | Bankadan gelen SMS kodunu gir | Yönlendirme `/payment/sipay/return`'e |
| 5 | Odoo'da transaction'ı kontrol et | `State: Done`, `sipay_3d_status: verified` |
| 6 | Muhasebe → Ödeme Hareketleri | Bağlı ödeme kaydı oluştu |

**Sipay Test Kartları:**

| Kart No | SKT | CVV | 3D SMS |
|---|---|---|---|
| 4508 0345 0803 4509 | 12/26 | 000 | 123456 |
| 5400 6101 0600 0016 | 12/26 | 000 | 123456 |

---

### S-02: Sipay — Yetersiz Bakiye

| Adım | Aksiyon | Beklenen Sonuç |
|---|---|---|
| 1 | Yetersiz bakiyeli test kartı kullan | — |
| 2 | 3D SMS kodunu gir | Return URL'e gelir |
| 3 | Odoo transaction | `State: Error`, hata mesajı: `INSUFFICIENT_FUNDS` |
| 4 | Müşteriye hata sayfası | Açıklayıcı mesaj var mı? |

---

### S-03: Sipay — İade (Refund)

**Ön koşul:** S-01 tamamlanmış, `provider_reference` (order_no) set edilmiş

| Adım | Aksiyon | Beklenen Sonuç |
|---|---|---|
| 1 | Muhasebe → Ödemeler → İlgili ödemeyi aç | — |
| 2 | "İade" butonu | İade miktarı gir |
| 3 | Onay | Sipay `api/refund` çağrılır |
| 4 | İade transaction | `State: Done` |
| 5 | Sipay paneli | İade kaydı görünür |

---

### S-04: Sipay — PreAuth + Capture

| Adım | Aksiyon | Beklenen Sonuç |
|---|---|---|
| 1 | Provider ayarında "Manuel Capture" aktif | — |
| 2 | Ödeme yap | `State: Authorized` (PreAuth) |
| 3 | Odoo transaction → "Tahsil Et" | `api/confirmPayment` çağrılır |
| 4 | Transaction | `State: Done` |

---

### S-05: Sipay — İptal (Void)

| Adım | Aksiyon | Beklenen Sonuç |
|---|---|---|
| 1 | Authorized state'deki transaction | — |
| 2 | "Void" | `api/cancelPayment` çağrılır |
| 3 | Transaction | `State: Canceled` |

---

### S-06: Sipay — Hash Doğrulama

**Test:** Return URL'e elle sahte `hash_key` gönder

| Adım | Aksiyon | Beklenen Sonuç |
|---|---|---|
| 1 | `/payment/sipay/return` POST et, `hash_key: BOZUK` | — |
| 2 | Log'ları incele | `WARNING: Hash validation failed but continuing` |
| 3 | Transaction state | Hash başarısız olsa da **işlem devam eder** — bu tasarım kararı mı? |

> ⚠️ **Dikkat:** Mevcut kod hash doğrulama başarısız olsa da işlemi durdurmaz (warn + continue). Bu güvenlik açığı olabilir. Test sırasında doğrula.

---

### S-07: PayTR — Başarılı iframe Ödemesi

**Ön koşul:** PayTR test/demo hesabı (gerçek API key gerekli, sandbox yok!)  
**Para birimi:** TRY

| Adım | Aksiyon | Beklenen Sonuç |
|---|---|---|
| 1 | Ödeme sayfasına git | PayTR iframe yüklenir |
| 2 | Test kart bilgilerini gir | — |
| 3 | Ödeme tamamla | `/payment/paytr/return` POST (merchant_oid, status=success) |
| 4 | Hash doğrulama | HMAC-SHA256 kontrolü geçer |
| 5 | Transaction | `State: Done` |

**PayTR Test Kartları:**

| Kart No | SKT | CVV | Sonuç |
|---|---|---|---|
| 4355 0843 5508 4358 | 12/26 | 000 | Başarılı |
| 5890 0400 0000 0016 | 12/26 | 000 | Başarılı |
| 4111 1111 1111 1111 | 12/26 | 000 | Başarısız |

---

### S-08: PayTR — Başarısız Ödeme

| Adım | Aksiyon | Beklenen Sonuç |
|---|---|---|
| 1 | Başarısız test kartı kullan | — |
| 2 | `/payment/paytr/return` POST: `status=failed, failed_reason_msg=...` | — |
| 3 | Transaction | `State: Error`, `failed_reason_msg` görünür |

---

### S-09: PayTR — Hash Doğrulama (HMAC)

**Test:** Return URL'e elle yanlış hash gönder

| Adım | Aksiyon | Beklenen Sonuç |
|---|---|---|
| 1 | Geçersiz hash ile POST | Controller hash'i reddeder mi? |
| 2 | Log | Hata loglanır |
| 3 | Transaction | **Error state** olmalı |

> 🔍 Controller kodunu oku (`controllers/main.py`) — hash kontrolünün nerede yapıldığını doğrula.

---

### S-10: PayTR — Sandbox Eksikliği (Kritik Bulgu)

| Adım | Aksiyon | Beklenen Sonuç |
|---|---|---|
| 1 | Provider state "test" yap | — |
| 2 | `_paytr_get_api_url()` çağrısını incele | **Her zaman `paytr.com` döner** |
| 3 | Gerçek para çekilmez mi? | Test hesabı yoksa CANLI ortamda test edilir |

> ⚠️ **Aksiyon gerekli:** `_paytr_get_api_url()` içine sandbox URL desteği ekle:
> ```python
> if self.state == 'test':
>     return 'https://www.paytr.com/'  # PayTR'nin test modu aynı URL, test_mode=1 ile
> ```
> PayTR'de `test_mode=1` parametresi ile gerçek çekim olmaz — token payload'da gönderilmeli.

---

### S-11: Iyzico — Başarılı Checkout Form Ödemesi

**Ön koşul:** Iyzico sandbox hesabı  
**Durum:** Test (sandbox-api.iyzipay.com)

| Adım | Aksiyon | Beklenen Sonuç |
|---|---|---|
| 1 | Ödeme sayfasına git | Iyzico checkout form URL'e yönlendirme |
| 2 | Iyzico sandbox sayfasında test kart gir | — |
| 3 | Ödemeyi tamamla | `/payment/iyzico/return?tx_ref=...` GET |
| 4 | Transaction | `State: Done`, `provider_reference`: paymentId |
| 5 | Kart association | MASTERCARD/VISA/TROY badge görünür |

**Iyzico Test Kartları:**

| Kart No | SKT | CVV | 3D Sonuç |
|---|---|---|---|
| 5528 7900 0000 0008 | 12/30 | 123 | Başarılı |
| 5528 7900 0000 0016 | 12/30 | 123 | Başarısız |
| 4603 4504 9849 4218 | 01/30 | 414 | Başarılı |

---

### S-12: Iyzico — Buyer Bilgisi Eksikliği

| Adım | Aksiyon | Beklenen Sonuç |
|---|---|---|
| 1 | Partner adı boş olan müşteri ile ödeme başlat | — |
| 2 | Iyzico payload | `buyer.name='Misafir'`, `surname='Kullanici'` (fallback) |
| 3 | API yanıtı | Kabul edilir mi? |

> 📝 `payment_transaction.py:62-65` — Geçici fallback var, gerçek kullanımda problem çıkabilir. Test et.

---

### S-13: Iyzico — Webhook/Return Callback

| Adım | Aksiyon | Beklenen Sonuç |
|---|---|---|
| 1 | Iyzico sandbox → webhook ayarla | — |
| 2 | Ödeme tamamla | Iyzico GET `/payment/iyzico/return?tx_ref=REF&token=TOKEN` gönderir |
| 3 | Controller | Token ile Iyzico API'dan durum sorgular |
| 4 | Status mapping | `SUCCESS` → Done, `FAILURE` → Error, `INIT_THREEDS` → Pending |

---

### S-14: Para Birimi Destekleme Testi

| Provider | Test | Beklenen |
|---|---|---|
| Sipay | EUR ödeme | Kabul |
| Sipay | JPY ödeme | Reddedilir (desteklenmiyor) |
| PayTR | USD ödeme | Kabul |
| Iyzico | CHF ödeme | Kabul |
| Iyzico | JPY ödeme | Reddedilir |

---

### S-15: Eş Zamanlı Çoklu Provider Testi

| Adım | Aksiyon | Beklenen |
|---|---|---|
| 1 | Tüm 3 provider da Odoo'da aktif | — |
| 2 | Ödeme sayfasında | Müşteriye 3 seçenek görünür |
| 3 | Sipay seç | Sadece Sipay flow tetiklenir |
| 4 | PayTR seç | Sadece PayTR flow tetiklenir |
| 5 | Provider kodları karışır mı? | `if self.provider_code != 'xxx': return super()` guard'ları çalışır |

---

## 5. Bilinen Sorunlar & Eksikler

### 5.1 payment_paytr

| # | Sorun | Dosya | Satır | Önerilen Çözüm |
|---|---|---|---|---|
| P-1 | Sandbox URL yok | `models/payment_provider.py` | 66-71 | `test_mode=1` payload + state kontrolü ekle |
| P-2 | `hmac.new` → Python 3'te `hmac.new` yok | `models/payment_provider.py` | 142 | `hmac.new` → `hmac.new` değil, `hmac.new` Python 2. Python 3'te `hmac.new(key, msg, digestmod)` yerine doğrudan `hmac.new` kullan — `_paytr_get_token`'da aynı hata var |
| P-3 | `paytr_order_no` alanı set edilmiyor | `models/payment_transaction.py` | — | `_process_notification_data`'da `self.paytr_order_no = notification_data.get('merchant_oid')` ekle |

> ⚠️ **P-2 Kritik:** `hmac.new(...)` Python 3'te `hmac.HMAC` constructor çağrısı olarak yanlış kullanılmış. Doğrusu:
> ```python
> # Yanlış (Python 2 tarzı):
> hmac.new(key, msg, digestmod).hexdigest()
> # Doğru (Python 3):
> hmac.new(key, msg=msg, digestmod=hashlib.sha256).hexdigest()
> ```
> Hem `payment_paytr` hem de `payment_iyzico`'da aynı sorun var — test sırasında `AttributeError: module 'hmac' has no attribute 'new'` hatası alırsın.

### 5.2 payment_iyzico

| # | Sorun | Dosya | Satır | Önerilen Çözüm |
|---|---|---|---|---|
| I-1 | `hmac.new` Python 3 hatası | `models/payment_provider.py` | 103 | `hmac.new` → `hmac.new` Python 3'te yok, `hmac.new` kullan |
| I-2 | `buyer.ip: '0.0.0.0'` | `models/payment_transaction.py` | 95 | Gerçek IP alınmalı (`request.httprequest.environ`) |
| I-3 | Refund desteği yok | — | — | Iyzico API'da `payment/iyzipos/refund` endpoint var |
| I-4 | `identityNumber` sahte | `models/payment_transaction.py` | 89 | TC kimlik zorunlu değil ama production'da sorun çıkabilir |

### 5.3 payment_sipay

| # | Sorun | Dosya | Satır | Önerilen Çözüm |
|---|---|---|---|---|
| S-1 | Hash başarısız olsa işlem devam eder | `models/payment_transaction.py` | 268-273 | Güvenlik riski — hash hatasında `_set_error()` çağrılmalı |
| S-2 | Production URL yorum satırında | `models/payment_provider.py` | 79-82 | State kontrolüne bağla |
| S-3 | `_sipay_get_token()` her ödeme isteğinde tekrar çağrılıyor | `models/payment_transaction.py` | 349 | Token cache'lenmeli (TTL: 5 dk) |
| S-4 | `Crypto` import ikili (`import base64` 2 kez) | `models/payment_transaction.py` | 5-12 | Temizle |

---

## 6. Test Ortamı Kurulumu

### 6.1 Sipay Sandbox

1. [https://apidocs.sipay.com.tr](https://apidocs.sipay.com.tr) → sandbox hesabı aç
2. App ID, App Secret, Merchant Key, Merchant ID al
3. `provisioning.sipay.com.tr` zaten aktif

### 6.2 PayTR

1. [https://dev.paytr.com](https://dev.paytr.com) → Demo hesabı aç
2. **Test modu:** `test_mode=1` parametresini token hash payload'a ekle — gerçek para çekilmez
3. Odoo kodu `test_mode` parametresi **şu an göndermyor** → düzeltme gerekli

### 6.3 Iyzico Sandbox

1. [https://sandbox-merchant.iyzipay.com](https://sandbox-merchant.iyzipay.com) → sandbox hesap
2. API Key, Secret Key al
3. Odoo provider state "Test" → otomatik sandbox URL kullanır

### 6.4 Ngrok (Webhook testi için)

PayTR ve Sipay callback için dışarıdan erişilebilir URL gerekli:

```bash
ngrok http 8069
# Çıkan URL'yi PayTR ve Sipay paneline yaz
# Örn: https://abc123.ngrok.io/payment/paytr/return
```

---

## 7. Controller Endpoint Özeti

| Provider | Endpoint | Method | Notlar |
|---|---|---|---|
| Sipay | `/payment/sipay/return` | POST | `invoice_id`, `status_code`, `hash_key` |
| PayTR | `/payment/paytr/return` | POST | `merchant_oid`, `status`, `hash` |
| Iyzico | `/payment/iyzico/return` | GET | `tx_ref`, `token` |

---

## 8. Test Öncelik Sırası

```
1. Kritik düzeltme: hmac.new sorunu (paytr + iyzico) → düzelt → kurulum bile çöker
2. Sipay mutlu yol (sandbox mevcut, en kolay)
3. Sipay hash güvenlik açığı
4. Iyzico mutlu yol (sandbox mevcut)
5. PayTR (sandbox yok, en zor — demo hesap + ngrok gerek)
6. PayTR sandbox desteği ekleme
7. İade/Capture/Void akışları
```

---

*Bu belge kod incelemesi sonucu oluşturulmuştur. API dökümantasyon linkleri:*  
*Sipay: https://apidocs.sipay.com.tr | PayTR: https://dev.paytr.com/en | Iyzico: https://docs.iyzico.com*
