# Payment Provider: Sipay

## Genel Bakış

Bu modül, Odoo 18 e-ticaret platformu için Sipay ödeme entegrasyonunu sağlar. Sipay, Türkiye'de yaygın olarak kullanılan bir sanal POS çözümüdür ve 3D Secure ödemeleri destekler.

## Özellikler

- **3D Secure Ödeme Desteği**: Güvenli online ödemeler için 3D Secure protokolü
- **Manuel Yakalama**: Ön yetkilendirme ve manuel ödeme yakalama desteği
- **İade İşlemleri**: Tam iade işlemleri
- **İptal İşlemleri**: Ön yetkilendirilmiş ödemelerin iptali
- **Çoklu Para Birimi**: TRY, USD ve EUR desteği
- **Taksit Desteği**: Kredi kartı taksit seçenekleri

## Kurulum

1. Bu modülü Odoo addons dizinine kopyalayın
2. Odoo'yu yeniden başlatın
3. Uygulamalar menüsünden modülü güncelleyin
4. "Payment Provider: Sipay" modülünü yükleyin

## Yapılandırma

1. **Ayarlar > Ödeme Sağlayıcıları** menüsüne gidin
2. Sipay sağlayıcısını seçin
3. Aşağıdaki bilgileri girin:
   - **Merchant Key**: Sipay tarafından sağlanan merchant key
   - **App ID**: Sipay tarafından sağlanan app ID
   - **App Secret**: Sipay tarafından sağlanan app secret
   - **Merchant ID**: Sipay tarafından sağlanan merchant ID

4. Test ortamı için "Test Modu" seçeneğini aktif edin
5. Canlı ortam için "Etkin" durumuna geçin

## Test Bilgileri

### Test Ortamı Bilgileri
- **Merchant KEY**: `$2y$10$HmRgYosneqcwHj.UH7upGuyCZqpQ1ITgSMj9Vvxn.t6f.Vdf2SQFO`
- **APP KEY**: `6d4a7e9374a76c15260fcc75e315b0b9`
- **APP SECRET**: `b46a67571aa1e7ef5641dc3fa6f1712a`
- **Merchant ID**: `18309`

### Test Kredi Kartları
- **Visa**: `4508034508034509`
- **MasterCard**: `5406675406675403`
- **Troy**: `6501700139082826`
- **Son Kullanma Tarihi**: `12/26`
- **CVV**: `000`
- **3D Secure Şifresi**: `a` (Troy için: `123456`)

## Kullanım

1. E-ticaret sitenizde ödeme adımına gelin
2. Ödeme yöntemi olarak Sipay'i seçin
3. Kredi kartı bilgilerinizi girin
4. 3D Secure doğrulamasını tamamlayın
5. Ödeme onaylandıktan sonra siparişiniz tamamlanır

## Teknik Detaylar

### Dosya Yapısı
```
payment_sipay/
├── __init__.py
├── __manifest__.py
├── const.py
├── controllers/
│   ├── __init__.py
│   └── main.py
├── data/
│   └── payment_provider_data.xml
├── models/
│   ├── __init__.py
│   ├── payment_provider.py
│   └── payment_transaction.py
├── static/
│   ├── img/
│   │   └── sipay_icon.png
│   └── src/
│       └── js/
│           └── payment_form.js
└── views/
    ├── payment_provider_views.xml
    └── payment_sipay_templates.xml
```

### API Entegrasyonu

Modül, aşağıdaki Sipay API endpoint'lerini kullanır:

- **Token Alma**: `/api/token` - Kimlik doğrulama token'ı alır
- **Taksit Bilgisi**: `/api/getpos` - Kart için taksit seçeneklerini getirir
- **Ödeme**: `/api/paySmart3D` - 3D Secure ödeme işlemini başlatır
- **Durum Kontrolü**: `/api/checkstatus` - Ödeme durumunu kontrol eder
- **İade**: `/api/refund` - İade işlemi yapar
- **Yakalama**: `/api/confirmPayment` - Ön yetkilendirilmiş ödemeyi yakalar
- **İptal**: `/api/cancelPayment` - Ön yetkilendirilmiş ödemeyi iptal eder

## Güvenlik

- Tüm hassas bilgiler (App Secret, Merchant Key) şifrelenmiş olarak saklanır
- 3D Secure protokolü ile güvenli ödeme
- Hash doğrulama ile veri bütünlüğü kontrolü
- SSL/TLS şifreli iletişim

## Destek

Herhangi bir sorun veya soru için:
- Sipay API Dokümantasyonu: https://apidocs.sipay.com.tr/
- Sipay Destek: support@sipay.com.tr

## Lisans

LGPL-3

## Sürüm Geçmişi

### 1.0.0 (2025)
- İlk sürüm
- 3D Secure ödeme desteği
- Manuel yakalama ve iade işlemleri
- Çoklu para birimi desteği
