# E-Dönüşüm Modülü Hata Yönetimi Geliştirme Planı

## 📋 İçindekiler
1. [Genel Bakış](#genel-bakis)
2. [Hata Kodu Sınıflandırması](#hata-kodu-siniflandirmasi)
3. [Mimari Tasarım](#mimari-tasarim)
4. [Implementation Planı](#implementation-plani)
5. [Dosya Yapısı](#dosya-yapisi)
6. [Test Stratejisi](#test-stratejisi)

---

## 1. Genel Bakış {#genel-bakis}

### 1.1 Amaç
- E-fatura/e-irsaliye gönderimi sırasında alınan hataları kullanıcıya anlaşılır şekilde bildirmek
- Fatura serisinde bozulma/atlama olmaması için atomic transaction yönetimi
- Hata durumunda faturanın tekrar gönderilebilmesi (retry mekanizması)
- Pre-validation ile hataların önceden tespit edilmesi

### 1.2 Kapsam
| Belge Tipi | Hata Kodu Aralığı | Toplam |
|------------|-------------------|--------|
| REST API | 1000-1021 | 22 |
| E-Fatura (EF) | EF0001-EF0530 | 530+ |
| E-İrsaliye (EI) | EI0001-EI0178 | 178+ |
| Sistem (AE) | AE00000-AE90000 | 100+ |

---

## 2. Hata Kodu Sınıflandırması {#hata-kodu-siniflandirmasi}

### 2.1 Severity Levels (Önem Düzeyleri)

```
CRITICAL  : İşlemi tamamen engelleyen hatalar (yeniden gönderme mümkün değil)
ERROR     : İşlemi engelleyen ancak düzeltilebilir hatalar  
WARNING   : Dikkat gerektiren durumlar
INFO      : Bilgilendirme amaçlı mesajlar
```

### 2.2 Error Categories (Hata Kategorileri)

#### A. Kimlik Doğrulama Hataları (AUTH)
| Kod | Açıklama | Severity | Retry |
|-----|----------|----------|-------|
| 1000 | Token yok | ERROR | ❌ |
| 1001 | Token geçersiz | ERROR | ✅ |
| EF0002 | Oturum hatası | ERROR | ✅ |
| EF0003 | Kullanıcı adı/şifre hatalı | CRITICAL | ❌ |
| EF0004 | Yetki hatası | CRITICAL | ❌ |

#### B. Validasyon Hataları - Alıcı Bilgileri (VAL_RECEIVER)
| Kod | Açıklama | Severity | Retry |
|-----|----------|----------|-------|
| EF0089 | Alıcı TCKN/VKN boş | ERROR | ❌ |
| EF0090 | Alıcı adres bilgileri eksik | ERROR | ❌ |
| EF0091 | Alıcı şehir alanı boş | ERROR | ❌ |
| EF0092 | Alıcı ilçe alanı boş | ERROR | ❌ |
| EF0119 | Hem TCKN hem VKN var | ERROR | ❌ |
| EF0120 | TCKN veya VKN yok | ERROR | ❌ |
| EF0121 | VKN varsa ünvan olmalı | ERROR | ❌ |
| EF0122 | TCKN varsa ad/soyad olmalı | ERROR | ❌ |
| EF0028 | Alıcı e-fatura sistemine kayıtlı değil | WARNING | ✅ |

#### C. Validasyon Hataları - Satıcı Bilgileri (VAL_SENDER)
| Kod | Açıklama | Severity | Retry |
|-----|----------|----------|-------|
| EF0093 | Satıcı TCKN/VKN boş | ERROR | ❌ |
| EF0094 | Satıcı adres bilgileri eksik | ERROR | ❌ |
| EF0095 | Satıcı ülke alanı boş | ERROR | ❌ |
| EF0096 | Satıcı şehir alanı boş | ERROR | ❌ |
| EF0097 | Satıcı ilçe alanı boş | ERROR | ❌ |
| EF0123-126 | Satıcı kimlik hataları | ERROR | ❌ |

#### D. Validasyon Hataları - Fatura Satırları (VAL_LINE)
| Kod | Açıklama | Severity | Retry |
|-----|----------|----------|-------|
| EF0098 | Mal bilgileri eksik | ERROR | ❌ |
| EF0099 | Ürün adı boş | ERROR | ❌ |
| EF0100 | Miktar boş | ERROR | ❌ |
| EF0101 | Birim boş | ERROR | ❌ |
| EF0102 | Birim fiyat boş | ERROR | ❌ |
| EF0129 | Fatura satırı yok | ERROR | ❌ |
| EF0363-368 | Satır değer hataları | ERROR | ❌ |

#### E. Validasyon Hataları - Vergi (VAL_TAX)
| Kod | Açıklama | Severity | Retry |
|-----|----------|----------|-------|
| EF0128 | Vergi çeşidi seçilmemiş | ERROR | ❌ |
| EF0130 | Vergi girilmemiş | ERROR | ❌ |
| EF0131 | Vergi bilgisi eksik | ERROR | ❌ |
| EF0150 | Muafiyet sebebi gerekli | ERROR | ❌ |
| EF0163-166 | Tevkifat tutarı hataları | ERROR | ❌ |
| EF0216-220 | Tevkifat kod hataları | ERROR | ❌ |

#### F. Format/Syntax Hataları (FORMAT)
| Kod | Açıklama | Severity | Retry |
|-----|----------|----------|-------|
| EF0106 | UBL versiyon hatalı | ERROR | ❌ |
| EF0107 | Özelleştirme numarası hatalı | ERROR | ❌ |
| EF0108 | Senaryo hatalı | ERROR | ❌ |
| EF0109 | Fatura numarası hatalı | ERROR | ❌ |
| EF0110 | UUID hatalı | ERROR | ❌ |
| EF0111 | Fatura tarihi hatalı | ERROR | ❌ |
| EF0112 | Fatura tipi hatalı | ERROR | ❌ |
| EF0113 | Döviz kodu hatalı | ERROR | ❌ |

#### G. Seri/Numara Hataları (SERIES)
| Kod | Açıklama | Severity | Retry |
|-----|----------|----------|-------|
| EF0039 | Seri 2 karakterden kısa | ERROR | ❌ |
| EF0044 | Fatura no daha önce kullanılmış | CRITICAL | ❌ |
| EF0152 | Seri tanımı geçersiz | ERROR | ❌ |
| EF0155-158 | Seri karakter hataları | ERROR | ❌ |
| EF0191 | Fatura no kayıtlı | CRITICAL | ❌ |
| EF0192 | Seri tanımı kayıtlı değil | ERROR | ❌ |
| EF0290 | Default seri bulunamadı | ERROR | ❌ |
| EF0341 | Yeni seri 1'den başlamalı | ERROR | ❌ |
| EF0346 | Fatura numarası beklenenden farklı | ERROR | ❌ |

#### H. Bağlantı/Sistem Hataları (SYSTEM)
| Kod | Açıklama | Severity | Retry |
|-----|----------|----------|-------|
| EF0001 | Sistem hatası | ERROR | ✅ |
| EF0247 | GİB sorgulama hatası | ERROR | ✅ |
| EF0248 | GİB bağlantı hatası | ERROR | ✅ |
| AE00001 | Sistem hatası | ERROR | ✅ |
| AE00051 | UUID mevcut ve imzalı | CRITICAL | ❌ |
| AE90000 | İşlev desteklenmiyor | ERROR | ❌ |
| AE99999 | Zaman aşımı | ERROR | ✅ |

#### I. İhracat Fatura Hataları (EXPORT)
| Kod | Açıklama | Severity | Retry |
|-----|----------|----------|-------|
| EF0311 | Alıcı GTB olmalı | ERROR | ❌ |
| EF0314 | İstisna tipinde olmalı | ERROR | ❌ |
| EF0315 | V1/V2 kullanılmamalı | ERROR | ❌ |
| EF0316-332 | Teslimat/eşya hataları | ERROR | ❌ |
| EF0344 | KDV muafiyet kodu 301 olmalı | ERROR | ❌ |
| EF0350-351 | İhracat fatura hataları | ERROR | ❌ |

#### J. Yolcu Beraber Fatura Hataları (TOURIST)
| Kod | Açıklama | Severity | Retry |
|-----|----------|----------|-------|
| EF0310 | Alıcı GTB olmalı | ERROR | ❌ |
| EF0312 | Sadece yolcu beraber fatura gönderilebilir | ERROR | ❌ |
| EF0313 | İstisna tipinde olmalı | ERROR | ❌ |
| EF0299-306 | Turist bilgi hataları | ERROR | ❌ |
| EF0343 | KDV muafiyet kodu 501 olmalı | ERROR | ❌ |

#### K. SGK Fatura Hataları (SGK)
| Kod | Açıklama | Severity | Retry |
|-----|----------|----------|-------|
| EF0396 | Alıcı SGK olmalı | ERROR | ❌ |
| EF0397 | SGK alt fatura tipi tanımsız | ERROR | ❌ |
| EF0398-403 | SGK zorunlu alan hataları | ERROR | ❌ |
| EF0404 | SGK fatura türü hatalı | ERROR | ❌ |
| EF0410-411 | SGK fatura izin hataları | ERROR | ❌ |

#### L. Kamu Fatura Hataları (PUBLIC)
| Kod | Açıklama | Severity | Retry |
|-----|----------|----------|-------|
| EF0459 | Sınıflandırma kodu zorunlu | ERROR | ❌ |
| EF0460 | Menşei bilgisi zorunlu | ERROR | ❌ |
| EF0461-463 | Ödeme bilgileri zorunlu | ERROR | ❌ |
| EF0466 | Fatura türü TEMEL/KAMU olmalı | ERROR | ❌ |
| EF0518 | Alıcı kamu olmalı | ERROR | ❌ |

#### M. Kontör/Ödeme Hataları (PAYMENT)
| Kod | Açıklama | Severity | Retry |
|-----|----------|----------|-------|
| EF0153 | Kontör yetersiz | CRITICAL | ❌ |
| EF00262 | Kontör sayısı yetersiz | CRITICAL | ❌ |
| EF0415 | Kart bilgisi hatalı | ERROR | ❌ |
| EF0420 | Ödeme alınamıyor | ERROR | ✅ |

#### N. E-İrsaliye Özel Hataları (DESPATCH)
| Kod | Açıklama | Severity | Retry |
|-----|----------|----------|-------|
| EI0001 | İrsaliye gönderene ait değil | ERROR | ❌ |
| EI0002 | Yanıt beklenmiyor | WARNING | ❌ |
| EI0005 | Gelen irsaliye bulunamadı | ERROR | ❌ |
| EI0006 | 7 gün süresi dolmuş | ERROR | ❌ |
| EI0010 | Daha önce gönderilmiş | CRITICAL | ❌ |
| EI0018 | İrsaliye no kullanılmış | CRITICAL | ❌ |
| EI0144 | Alıcı etiketi geçersiz | ERROR | ❌ |
| EI0145 | Alıcı e-irsaliye kayıtlı değil | WARNING | ✅ |

---

## 3. Mimari Tasarım {#mimari-tasarim}

### 3.1 Yeni Model Yapısı

```
mdx.efatura.hata.kodu (Error Code Master)
├── code (char): Hata kodu (EF0001, AE00000, etc.)
├── category (selection): Kategori
├── severity (selection): critical/error/warning/info
├── is_retryable (boolean): Yeniden denenebilir mi?
├── user_message_tr (text): Kullanıcı dostu Türkçe mesaj
├── technical_message (text): Teknik detay
├── solution_hint_tr (text): Çözüm önerisi
└── document_type (selection): FATURA/IRSALIYE/BOTH

mdx.efatura.islem (Transaction Log)
├── document_id (reference): İlgili belge
├── document_type (selection): EFATURA/EARSIV/EIRSALIYE
├── state (selection): draft/sending/sent/error/cancelled
├── error_code_id (m2o): Hata kodu referansı
├── error_message (text): Ham hata mesajı
├── retry_count (integer): Deneme sayısı
├── max_retry (integer): Max deneme
├── last_attempt_date (datetime): Son deneme tarihi
├── can_retry (boolean): Yeniden denenebilir mi?
├── series_snapshot (json): Seri durumu snapshot'ı
└── xml_content (text): Gönderilen XML

mdx.efatura.pre.validation (Pre-validation Rules)
├── name (char): Kural adı
├── document_type (selection): Belge tipi
├── validation_code (text): Python kodu
├── error_code_id (m2o): Başarısız olursa hata kodu
├── sequence (integer): Sıra
└── active (boolean): Aktif mi?
```

### 3.2 Sınıf Diyagramı

```
┌─────────────────────────────────────────────────────────────────┐
│                    MdxErrorHandlerMixin                          │
├─────────────────────────────────────────────────────────────────┤
│ + parse_error_response(response) -> dict                        │
│ + get_user_friendly_message(error_code) -> str                  │
│ + translate_error_code(code) -> mdx.efatura.hata.kodu           │
│ + is_retryable_error(error_code) -> bool                        │
│ + log_transaction(document, state, error=None)                  │
│ + get_solution_hint(error_code) -> str                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MdxPreValidationMixin                         │
├─────────────────────────────────────────────────────────────────┤
│ + validate_invoice_before_send(invoice) -> list[errors]         │
│ + validate_receiver_info(invoice) -> list[errors]               │
│ + validate_sender_info(invoice) -> list[errors]                 │
│ + validate_line_items(invoice) -> list[errors]                  │
│ + validate_tax_info(invoice) -> list[errors]                    │
│ + validate_series_availability(invoice) -> list[errors]         │
│ + validate_receiver_registration(invoice) -> list[errors]       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MdxSeriesManagerMixin                         │
├─────────────────────────────────────────────────────────────────┤
│ + reserve_series_number(series) -> int (with SAVEPOINT)         │
│ + release_series_number(series, number) (rollback)              │
│ + confirm_series_number(series, number) (commit)                │
│ + get_next_available_number(series) -> int                      │
│ + validate_series_sequence(series, number) -> bool              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MdxRetryManagerMixin                          │
├─────────────────────────────────────────────────────────────────┤
│ + can_retry(transaction) -> bool                                │
│ + schedule_retry(transaction, delay_minutes=5)                  │
│ + execute_retry(transaction)                                    │
│ + get_retry_queue() -> list[transactions]                       │
│ + process_retry_queue() (cron job)                              │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 Akış Diyagramı

```
┌──────────────────┐
│ action_send_     │
│ einvoice()       │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐     ┌──────────────────┐
│ Pre-validation   │────▶│ Validation       │
│ check            │ ERR │ Errors           │
└────────┬─────────┘     │ (User-friendly)  │
         │ OK            └──────────────────┘
         ▼
┌──────────────────┐
│ reserve_series_  │◄─── SAVEPOINT created
│ number()         │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ generate_        │
│ invoice_xml()    │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ log_transaction  │
│ (state=sending)  │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ send_invoice_    │
│ xml()            │
└────────┬─────────┘
         │
    ┌────┴────┐
    │         │
  SUCCESS   ERROR
    │         │
    ▼         ▼
┌────────┐  ┌──────────────────┐
│confirm_│  │release_series_   │◄─── ROLLBACK to SAVEPOINT
│series  │  │number()          │
└────────┘  └────────┬─────────┘
    │                │
    ▼                ▼
┌────────┐  ┌──────────────────┐
│log_    │  │parse_error_      │
│trans-  │  │response()        │
│action  │  └────────┬─────────┘
│(sent)  │           │
└────────┘           ▼
                ┌──────────────────┐
                │is_retryable?     │
                └────────┬─────────┘
                    ┌────┴────┐
                   YES       NO
                    │         │
                    ▼         ▼
              ┌────────┐ ┌──────────────┐
              │schedule│ │show_error_   │
              │_retry()│ │to_user()     │
              └────────┘ └──────────────┘
```

---

## 4. Implementation Planı {#implementation-plani}

### Faz 1: Temel Altyapı (Hafta 1-2)

#### 4.1.1 Hata Kodu Master Data Modeli
```python
# models/mdx_efatura_hata_kodu.py

class MdxEfaturaHataKodu(models.Model):
    _name = 'mdx.efatura.hata.kodu'
    _description = 'E-Fatura Hata Kodları'
    
    code = fields.Char('Hata Kodu', required=True, index=True)
    category = fields.Selection([
        ('AUTH', 'Kimlik Doğrulama'),
        ('VAL_RECEIVER', 'Alıcı Bilgileri'),
        ('VAL_SENDER', 'Satıcı Bilgileri'),
        ('VAL_LINE', 'Fatura Satırları'),
        ('VAL_TAX', 'Vergi Bilgileri'),
        ('FORMAT', 'Format/Syntax'),
        ('SERIES', 'Seri/Numara'),
        ('SYSTEM', 'Sistem/Bağlantı'),
        ('EXPORT', 'İhracat'),
        ('TOURIST', 'Yolcu Beraber'),
        ('SGK', 'SGK'),
        ('PUBLIC', 'Kamu'),
        ('PAYMENT', 'Kontör/Ödeme'),
        ('DESPATCH', 'E-İrsaliye'),
    ], string='Kategori', required=True)
    
    severity = fields.Selection([
        ('critical', 'Kritik'),
        ('error', 'Hata'),
        ('warning', 'Uyarı'),
        ('info', 'Bilgi'),
    ], string='Önem Düzeyi', default='error')
    
    is_retryable = fields.Boolean('Yeniden Denenebilir', default=False)
    user_message_tr = fields.Text('Kullanıcı Mesajı (TR)', required=True)
    technical_message = fields.Text('Teknik Mesaj')
    solution_hint_tr = fields.Text('Çözüm Önerisi (TR)')
    document_type = fields.Selection([
        ('FATURA', 'E-Fatura'),
        ('IRSALIYE', 'E-İrsaliye'),
        ('BOTH', 'Her İkisi'),
    ], default='BOTH')
    
    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Hata kodu benzersiz olmalıdır!')
    ]
```

#### 4.1.2 İşlem Log Modeli
```python
# models/mdx_efatura_islem.py

class MdxEfaturaIslem(models.Model):
    _name = 'mdx.efatura.islem'
    _description = 'E-Fatura İşlem Kaydı'
    _order = 'create_date desc'
    
    name = fields.Char('İşlem No', readonly=True, default=lambda self: _('New'))
    
    document_ref = fields.Reference(
        selection=[('account.move', 'Fatura'), ('stock.picking', 'İrsaliye')],
        string='Belge'
    )
    document_type = fields.Selection([
        ('EFATURA', 'E-Fatura'),
        ('EARSIV', 'E-Arşiv'),
        ('EIHRACAT', 'E-İhracat'),
        ('EIRSALIYE', 'E-İrsaliye'),
    ], string='Belge Türü')
    
    state = fields.Selection([
        ('draft', 'Hazırlanıyor'),
        ('validating', 'Doğrulanıyor'),
        ('sending', 'Gönderiliyor'),
        ('sent', 'Gönderildi'),
        ('error', 'Hata'),
        ('retry_scheduled', 'Tekrar Planlandı'),
        ('cancelled', 'İptal'),
    ], default='draft', string='Durum')
    
    # Error handling
    error_code_id = fields.Many2one('mdx.efatura.hata.kodu', 'Hata Kodu')
    error_message = fields.Text('Ham Hata Mesajı')
    error_display = fields.Html('Hata Detayı', compute='_compute_error_display')
    
    # Retry mechanism
    retry_count = fields.Integer('Deneme Sayısı', default=0)
    max_retry = fields.Integer('Max Deneme', default=3)
    last_attempt_date = fields.Datetime('Son Deneme')
    next_retry_date = fields.Datetime('Sonraki Deneme')
    can_retry = fields.Boolean('Yeniden Denenebilir', compute='_compute_can_retry')
    
    # Series management
    series_id = fields.Many2one('mdx.fatura.seri', 'Kullanılan Seri')
    series_number = fields.Integer('Seri Numarası')
    series_confirmed = fields.Boolean('Seri Onaylandı', default=False)
    
    # Technical data
    xml_content = fields.Text('XML İçeriği')
    response_content = fields.Text('Yanıt İçeriği')
    
    @api.depends('error_code_id', 'error_message')
    def _compute_error_display(self):
        for record in self:
            if record.error_code_id:
                html = f"""
                <div class="alert alert-danger">
                    <h4><i class="fa fa-exclamation-triangle"></i> {record.error_code_id.code}</h4>
                    <p><strong>{record.error_code_id.user_message_tr}</strong></p>
                    {f'<p class="text-muted">{record.error_code_id.solution_hint_tr}</p>' 
                     if record.error_code_id.solution_hint_tr else ''}
                </div>
                """
                record.error_display = html
            else:
                record.error_display = False
    
    @api.depends('retry_count', 'max_retry', 'error_code_id')
    def _compute_can_retry(self):
        for record in self:
            record.can_retry = (
                record.retry_count < record.max_retry and
                record.error_code_id and
                record.error_code_id.is_retryable and
                record.state == 'error'
            )
```

#### 4.1.3 Hata Kodu Verileri (Data File)
```xml
<!-- data/mdx_efatura_hata_kodu_data.xml -->

<odoo>
    <data noupdate="1">
        <!-- AUTH Category -->
        <record id="error_ef0001" model="mdx.efatura.hata.kodu">
            <field name="code">EF0001</field>
            <field name="category">SYSTEM</field>
            <field name="severity">error</field>
            <field name="is_retryable">True</field>
            <field name="user_message_tr">Sistem hatası oluştu. Lütfen birkaç dakika sonra tekrar deneyin.</field>
            <field name="solution_hint_tr">Bu hata genellikle geçicidir. 5-10 dakika bekleyip tekrar deneyin.</field>
        </record>
        
        <record id="error_ef0002" model="mdx.efatura.hata.kodu">
            <field name="code">EF0002</field>
            <field name="category">AUTH</field>
            <field name="severity">error</field>
            <field name="is_retryable">True</field>
            <field name="user_message_tr">Oturumunuzun süresi dolmuş. Yeniden bağlanılıyor...</field>
            <field name="solution_hint_tr">Sistem otomatik olarak yeniden bağlanmayı deneyecektir.</field>
        </record>
        
        <record id="error_ef0003" model="mdx.efatura.hata.kodu">
            <field name="code">EF0003</field>
            <field name="category">AUTH</field>
            <field name="severity">critical</field>
            <field name="is_retryable">False</field>
            <field name="user_message_tr">E-Fatura servis kullanıcı adı veya şifresi hatalı.</field>
            <field name="solution_hint_tr">Ayarlar > E-Dönüşüm > Web Servisleri bölümünden kullanıcı bilgilerinizi kontrol edin.</field>
        </record>
        
        <!-- VAL_RECEIVER Category -->
        <record id="error_ef0028" model="mdx.efatura.hata.kodu">
            <field name="code">EF0028</field>
            <field name="category">VAL_RECEIVER</field>
            <field name="severity">warning</field>
            <field name="is_retryable">True</field>
            <field name="user_message_tr">Alıcı firma e-fatura sistemine kayıtlı değil.</field>
            <field name="solution_hint_tr">Alıcı firmanın e-fatura mükellefi olup olmadığını kontrol edin. Değilse E-Arşiv fatura gönderin.</field>
        </record>
        
        <record id="error_ef0089" model="mdx.efatura.hata.kodu">
            <field name="code">EF0089</field>
            <field name="category">VAL_RECEIVER</field>
            <field name="severity">error</field>
            <field name="is_retryable">False</field>
            <field name="user_message_tr">Alıcı bilgilerinde Vergi/TC Kimlik Numarası eksik.</field>
            <field name="solution_hint_tr">Müşteri kartında VKN/TCKN alanını doldurun.</field>
        </record>
        
        <record id="error_ef0090" model="mdx.efatura.hata.kodu">
            <field name="code">EF0090</field>
            <field name="category">VAL_RECEIVER</field>
            <field name="severity">error</field>
            <field name="is_retryable">False</field>
            <field name="user_message_tr">Alıcı adres bilgileri eksik.</field>
            <field name="solution_hint_tr">Müşteri kartındaki adres bilgilerini (Şehir, İlçe, Adres) eksiksiz doldurun.</field>
        </record>
        
        <!-- SERIES Category -->
        <record id="error_ef0044" model="mdx.efatura.hata.kodu">
            <field name="code">EF0044</field>
            <field name="category">SERIES</field>
            <field name="severity">critical</field>
            <field name="is_retryable">False</field>
            <field name="user_message_tr">Bu fatura numarası daha önce kullanılmış!</field>
            <field name="solution_hint_tr">Fatura serisi atlamış olabilir. Sistem yöneticinizle iletişime geçin.</field>
        </record>
        
        <record id="error_ef0346" model="mdx.efatura.hata.kodu">
            <field name="code">EF0346</field>
            <field name="category">SERIES</field>
            <field name="severity">error</field>
            <field name="is_retryable">False</field>
            <field name="user_message_tr">Fatura numarası sıralı değil. Beklenen numaradan farklı.</field>
            <field name="solution_hint_tr">Fatura serisi senkronizasyonu bozulmuş olabilir. Seri ayarlarını kontrol edin.</field>
        </record>
        
        <!-- Continue with all error codes... -->
        
        <!-- AE System Codes -->
        <record id="error_ae00000" model="mdx.efatura.hata.kodu">
            <field name="code">AE00000</field>
            <field name="category">SYSTEM</field>
            <field name="severity">info</field>
            <field name="is_retryable">False</field>
            <field name="user_message_tr">İşlem başarılı.</field>
        </record>
        
        <record id="error_ae00001" model="mdx.efatura.hata.kodu">
            <field name="code">AE00001</field>
            <field name="category">SYSTEM</field>
            <field name="severity">error</field>
            <field name="is_retryable">True</field>
            <field name="user_message_tr">Sistem hatası oluştu.</field>
            <field name="solution_hint_tr">Birkaç dakika sonra tekrar deneyin.</field>
        </record>
        
        <record id="error_ae00051" model="mdx.efatura.hata.kodu">
            <field name="code">AE00051</field>
            <field name="category">SERIES</field>
            <field name="severity">critical</field>
            <field name="is_retryable">False</field>
            <field name="user_message_tr">Bu UUID ile daha önce fatura gönderilmiş ve imzalanmış.</field>
            <field name="solution_hint_tr">Bu fatura zaten başarıyla gönderilmiş. Durum sorgulama yapın.</field>
        </record>
    </data>
</odoo>
```

### Faz 2: Mixin'ler (Hafta 2-3)

#### 4.2.1 Error Handler Mixin
```python
# models/mdx_error_handler_mixin.py

import re
import logging
_logger = logging.getLogger(__name__)

class MdxErrorHandlerMixin(models.AbstractModel):
    _name = 'mdx.error.handler.mixin'
    _description = 'E-Fatura Hata Yönetimi Mixin'
    
    # Error code regex patterns
    ERROR_PATTERNS = {
        'EF': r'\[EF\d{4,5}\]',
        'AE': r'AE\d{5}',
        'EI': r'\[EI\d{4}\]',
        'REST': r'\[\d{4}\]',
    }
    
    def parse_error_response(self, response_text, response_code=None):
        """
        Parse error response from web service and extract error codes.
        Returns: dict with error_code, error_message, is_retryable
        """
        result = {
            'error_code': None,
            'error_message': response_text,
            'raw_response': response_text,
            'is_retryable': False,
        }
        
        # Try to find known error codes
        for prefix, pattern in self.ERROR_PATTERNS.items():
            matches = re.findall(pattern, response_text)
            if matches:
                # Clean the code (remove brackets)
                code = matches[0].strip('[]')
                result['error_code'] = code
                break
        
        # If no code found, try to extract from resultCode
        if not result['error_code']:
            # Try XML parsing for resultCode
            try:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(response_text)
                result_code = root.find('.//resultCode')
                if result_code is not None:
                    result['error_code'] = result_code.text
            except:
                pass
        
        # Get error record if code found
        if result['error_code']:
            error_record = self.get_error_record(result['error_code'])
            if error_record:
                result['error_record'] = error_record
                result['is_retryable'] = error_record.is_retryable
        
        return result
    
    def get_error_record(self, error_code):
        """Get error record from master data"""
        return self.env['mdx.efatura.hata.kodu'].search([
            ('code', '=', error_code)
        ], limit=1)
    
    def get_user_friendly_message(self, error_code, context=None):
        """
        Get user-friendly error message with context
        context: dict with placeholders like {invoice_number}, {partner_name}
        """
        error_record = self.get_error_record(error_code)
        if not error_record:
            return f"Hata kodu: {error_code} - Tanımlanmamış hata"
        
        message = error_record.user_message_tr
        
        # Replace placeholders if context provided
        if context:
            for key, value in context.items():
                message = message.replace('{' + key + '}', str(value))
        
        return message
    
    def format_error_for_user(self, error_info, document=None):
        """
        Format error information for displaying to user.
        Returns HTML formatted error message.
        """
        error_code = error_info.get('error_code', 'UNKNOWN')
        error_record = error_info.get('error_record')
        
        if error_record:
            severity_icons = {
                'critical': 'fa-times-circle text-danger',
                'error': 'fa-exclamation-circle text-danger',
                'warning': 'fa-exclamation-triangle text-warning',
                'info': 'fa-info-circle text-info',
            }
            
            icon = severity_icons.get(error_record.severity, 'fa-question-circle')
            
            html = f"""
            <div class="efatura-error-panel">
                <div class="error-header">
                    <i class="fa {icon}"></i>
                    <span class="error-code">{error_code}</span>
                    <span class="error-category">[{error_record.category}]</span>
                </div>
                <div class="error-message">
                    <p><strong>{error_record.user_message_tr}</strong></p>
                </div>
                {'<div class="error-solution"><i class="fa fa-lightbulb-o"></i> ' + 
                 error_record.solution_hint_tr + '</div>' 
                 if error_record.solution_hint_tr else ''}
                {'<div class="error-retry-hint"><i class="fa fa-refresh"></i> Bu hata otomatik olarak yeniden denenebilir.</div>' 
                 if error_record.is_retryable else ''}
            </div>
            """
            return html
        else:
            return f"""
            <div class="efatura-error-panel">
                <div class="error-header">
                    <i class="fa fa-exclamation-circle text-danger"></i>
                    <span class="error-code">{error_code}</span>
                </div>
                <div class="error-message">
                    <p>{error_info.get('error_message', 'Bilinmeyen hata')}</p>
                </div>
            </div>
            """
    
    def log_transaction_error(self, document, error_info, xml_content=None):
        """Create transaction log with error details"""
        error_record = error_info.get('error_record')
        
        vals = {
            'document_ref': f'{document._name},{document.id}',
            'document_type': getattr(document, 'efatura_turu_id', False) and 
                            document.efatura_turu_id.code or 'EFATURA',
            'state': 'error',
            'error_code_id': error_record.id if error_record else False,
            'error_message': error_info.get('error_message'),
            'xml_content': xml_content,
            'response_content': error_info.get('raw_response'),
            'last_attempt_date': fields.Datetime.now(),
        }
        
        return self.env['mdx.efatura.islem'].create(vals)
```

#### 4.2.2 Pre-Validation Mixin
```python
# models/mdx_pre_validation_mixin.py

class MdxPreValidationMixin(models.AbstractModel):
    _name = 'mdx.pre.validation.mixin'
    _description = 'E-Fatura Ön Doğrulama Mixin'
    
    def validate_invoice_before_send(self, invoice):
        """
        Run all pre-validations before sending invoice.
        Returns: list of validation errors with error codes
        """
        errors = []
        
        # Run all validation methods
        errors.extend(self._validate_company_info(invoice))
        errors.extend(self._validate_partner_info(invoice))
        errors.extend(self._validate_line_items(invoice))
        errors.extend(self._validate_tax_info(invoice))
        errors.extend(self._validate_series(invoice))
        errors.extend(self._validate_document_type_specific(invoice))
        
        return errors
    
    def _validate_company_info(self, invoice):
        """Validate seller/company information"""
        errors = []
        company = invoice.company_id
        
        if not company.vat:
            errors.append({
                'code': 'EF0093',
                'message': 'Şirket VKN/TCKN bilgisi eksik.',
                'field': 'company_id.vat'
            })
        
        if not company.street:
            errors.append({
                'code': 'EF0094',
                'message': 'Şirket adres bilgisi eksik.',
                'field': 'company_id.street'
            })
        
        if not company.city:
            errors.append({
                'code': 'EF0096',
                'message': 'Şirket şehir bilgisi eksik.',
                'field': 'company_id.city'
            })
        
        if not company.country_id:
            errors.append({
                'code': 'EF0095',
                'message': 'Şirket ülke bilgisi eksik.',
                'field': 'company_id.country_id'
            })
        
        return errors
    
    def _validate_partner_info(self, invoice):
        """Validate customer/receiver information"""
        errors = []
        partner = invoice.partner_id.commercial_partner_id
        
        # VKN/TCKN check
        vat = partner.vat or partner.tckn
        if not vat:
            errors.append({
                'code': 'EF0089',
                'message': f'{partner.name} için VKN/TCKN bilgisi eksik.',
                'field': 'partner_id.vat'
            })
        
        # Check if both VKN and TCKN exist (error)
        if partner.vat and partner.tckn:
            errors.append({
                'code': 'EF0119',
                'message': f'{partner.name} için hem VKN hem TCKN tanımlı. Sadece biri olmalı.',
                'field': 'partner_id'
            })
        
        # Address checks
        if not partner.street and not partner.street2:
            errors.append({
                'code': 'EF0090',
                'message': f'{partner.name} için adres bilgisi eksik.',
                'field': 'partner_id.street'
            })
        
        if not partner.city:
            errors.append({
                'code': 'EF0091',
                'message': f'{partner.name} için şehir bilgisi eksik.',
                'field': 'partner_id.city'
            })
        
        # Name/Title check based on VKN/TCKN
        if partner.vat and not partner.name:
            errors.append({
                'code': 'EF0121',
                'message': 'VKN tanımlı ise ünvan boş olamaz.',
                'field': 'partner_id.name'
            })
        
        return errors
    
    def _validate_line_items(self, invoice):
        """Validate invoice line items"""
        errors = []
        
        if not invoice.invoice_line_ids:
            errors.append({
                'code': 'EF0129',
                'message': 'Faturada en az bir satır olmalıdır.',
                'field': 'invoice_line_ids'
            })
            return errors
        
        for idx, line in enumerate(invoice.invoice_line_ids.filtered(lambda l: not l.display_type), 1):
            # Product name
            if not line.name and not line.product_id:
                errors.append({
                    'code': 'EF0099',
                    'message': f'Satır {idx}: Ürün adı boş olamaz.',
                    'field': f'invoice_line_ids[{line.id}].name'
                })
            
            # Quantity
            if not line.quantity or line.quantity == 0:
                errors.append({
                    'code': 'EF0100',
                    'message': f'Satır {idx}: Miktar boş veya sıfır olamaz.',
                    'field': f'invoice_line_ids[{line.id}].quantity'
                })
            
            # Unit
            if not line.product_uom_id:
                errors.append({
                    'code': 'EF0101',
                    'message': f'Satır {idx}: Birim seçilmemiş.',
                    'field': f'invoice_line_ids[{line.id}].product_uom_id'
                })
            
            # Price
            if line.price_unit is None:
                errors.append({
                    'code': 'EF0102',
                    'message': f'Satır {idx}: Birim fiyat boş olamaz.',
                    'field': f'invoice_line_ids[{line.id}].price_unit'
                })
        
        return errors
    
    def _validate_tax_info(self, invoice):
        """Validate tax information"""
        errors = []
        
        for idx, line in enumerate(invoice.invoice_line_ids.filtered(lambda l: not l.display_type), 1):
            # Check if tax exists
            if not line.tax_ids:
                errors.append({
                    'code': 'EF0130',
                    'message': f'Satır {idx}: Vergi tanımlanmamış.',
                    'field': f'invoice_line_ids[{line.id}].tax_ids'
                })
                continue
            
            # Check tax exemption
            for tax in line.tax_ids:
                if tax.amount == 0 and not getattr(line, 'kdv_muafiyet_kodu', None):
                    errors.append({
                        'code': 'EF0150',
                        'message': f'Satır {idx}: %0 KDV için muafiyet sebebi girilmelidir.',
                        'field': f'invoice_line_ids[{line.id}].kdv_muafiyet_kodu'
                    })
        
        return errors
    
    def _validate_series(self, invoice):
        """Validate invoice series"""
        errors = []
        
        if not invoice.fatura_seri_id:
            errors.append({
                'code': 'EF0290',
                'message': 'Fatura serisi seçilmemiş.',
                'field': 'fatura_seri_id'
            })
        
        return errors
    
    def _validate_document_type_specific(self, invoice):
        """Validate based on document type (export, tourist, SGK, etc.)"""
        errors = []
        
        doc_type = getattr(invoice, 'efatura_turu_id', False)
        if not doc_type:
            return errors
        
        # Export invoice validations
        if doc_type.code == 'EIHRACAT':
            errors.extend(self._validate_export_invoice(invoice))
        
        # Check if receiver is registered for e-invoice
        if doc_type.code == 'EFATURA':
            errors.extend(self._validate_receiver_registration(invoice))
        
        return errors
    
    def _validate_export_invoice(self, invoice):
        """Validate export invoice specific requirements"""
        errors = []
        
        partner = invoice.partner_id.commercial_partner_id
        
        # Check if receiver is GTB for export
        if partner.vat != '1460415308':  # GTB VKN
            errors.append({
                'code': 'EF0311',
                'message': 'İhracat faturasının alıcısı Gümrük ve Ticaret Bakanlığı olmalıdır.',
                'field': 'partner_id'
            })
        
        # Check for delivery information
        if not getattr(invoice, 'teslimat_ulke_id', None):
            errors.append({
                'code': 'EF0330',
                'message': 'Teslimat ülkesi boş olamaz.',
                'field': 'teslimat_ulke_id'
            })
        
        return errors
    
    def _validate_receiver_registration(self, invoice):
        """Check if receiver is registered for e-invoice"""
        errors = []
        
        partner = invoice.partner_id.commercial_partner_id
        vat = partner.vat or partner.tckn
        
        if not vat:
            return errors
        
        # This should call the web service to check registration
        # For now, we'll check a cached field or skip
        if hasattr(partner, 'efatura_mukellef') and partner.efatura_mukellef == False:
            errors.append({
                'code': 'EF0028',
                'message': f'{partner.name} e-fatura sistemine kayıtlı değil. E-Arşiv olarak gönderilebilir.',
                'field': 'partner_id',
                'severity': 'warning'
            })
        
        return errors
    
    def display_validation_errors(self, errors):
        """
        Display validation errors to user in a formatted way.
        Raises UserError with formatted message.
        """
        if not errors:
            return True
        
        # Group errors by severity
        critical_errors = [e for e in errors if e.get('severity') == 'critical' or 
                         e.get('code', '').startswith('EF004')]
        normal_errors = [e for e in errors if e not in critical_errors and 
                        e.get('severity') != 'warning']
        warnings = [e for e in errors if e.get('severity') == 'warning']
        
        message_parts = []
        
        if critical_errors:
            message_parts.append("❌ KRİTİK HATALAR:")
            for err in critical_errors:
                message_parts.append(f"  • [{err['code']}] {err['message']}")
        
        if normal_errors:
            message_parts.append("\n⚠️ HATALAR:")
            for err in normal_errors:
                message_parts.append(f"  • [{err['code']}] {err['message']}")
        
        if warnings:
            message_parts.append("\nℹ️ UYARILAR:")
            for warn in warnings:
                message_parts.append(f"  • [{warn['code']}] {warn['message']}")
        
        final_message = "\n".join(message_parts)
        
        # If only warnings, maybe allow to proceed with confirmation
        if not critical_errors and not normal_errors:
            return True  # Only warnings, can proceed
        
        raise UserError(final_message)
```

#### 4.2.3 Series Manager Mixin
```python
# models/mdx_series_manager_mixin.py

class MdxSeriesManagerMixin(models.AbstractModel):
    _name = 'mdx.series.manager.mixin'
    _description = 'Fatura Seri Yönetimi Mixin'
    
    def reserve_series_number(self, series_record, invoice_record):
        """
        Reserve a series number with SAVEPOINT for atomic transaction.
        Returns: dict with number and savepoint_name
        """
        # Create a savepoint
        savepoint_name = f'series_reserve_{series_record.id}_{invoice_record.id}'
        self.env.cr.execute(f'SAVEPOINT {savepoint_name}')
        
        try:
            # Lock the series record for update
            self.env.cr.execute(
                "SELECT index FROM mdx_fatura_seri WHERE id = %s FOR UPDATE",
                (series_record.id,)
            )
            
            # Get current index
            current_index = series_record.index
            new_index = current_index + 1
            
            # Update index
            series_record.write({
                'index': new_index,
                'last_used_date': fields.Date.today()
            })
            
            # Generate invoice number
            invoice_number = f"{series_record.code}{str(new_index).zfill(9)}"
            
            _logger.info(f"Series {series_record.code} reserved number {new_index} "
                        f"for invoice {invoice_record.id}")
            
            return {
                'number': new_index,
                'invoice_number': invoice_number,
                'savepoint_name': savepoint_name,
                'series_id': series_record.id,
            }
            
        except Exception as e:
            # Rollback to savepoint on error
            self.env.cr.execute(f'ROLLBACK TO SAVEPOINT {savepoint_name}')
            _logger.error(f"Failed to reserve series number: {str(e)}")
            raise UserError(f"Seri numarası rezervasyonu başarısız: {str(e)}")
    
    def release_series_number(self, reservation):
        """
        Release a reserved series number by rolling back to savepoint.
        Called when invoice send fails.
        """
        savepoint_name = reservation.get('savepoint_name')
        if savepoint_name:
            try:
                self.env.cr.execute(f'ROLLBACK TO SAVEPOINT {savepoint_name}')
                _logger.info(f"Series reservation rolled back: {savepoint_name}")
                return True
            except Exception as e:
                _logger.error(f"Failed to rollback series reservation: {str(e)}")
                return False
        return False
    
    def confirm_series_number(self, reservation):
        """
        Confirm a reserved series number by releasing the savepoint.
        Called when invoice send succeeds.
        """
        savepoint_name = reservation.get('savepoint_name')
        if savepoint_name:
            try:
                self.env.cr.execute(f'RELEASE SAVEPOINT {savepoint_name}')
                _logger.info(f"Series reservation confirmed: {savepoint_name}")
                return True
            except Exception as e:
                _logger.error(f"Failed to confirm series reservation: {str(e)}")
                return False
        return False
    
    def validate_series_sequence(self, series_record, expected_number):
        """
        Validate that the series number is sequential.
        """
        current_index = series_record.index
        
        if expected_number != current_index + 1:
            raise UserError(
                f"Seri numarası sıralı değil!\n"
                f"Beklenen: {current_index + 1}\n"
                f"Gelen: {expected_number}\n"
                f"Lütfen seri ayarlarını kontrol edin."
            )
        
        return True
```

#### 4.2.4 Retry Manager Mixin
```python
# models/mdx_retry_manager_mixin.py

from datetime import timedelta

class MdxRetryManagerMixin(models.AbstractModel):
    _name = 'mdx.retry.manager.mixin'
    _description = 'E-Fatura Tekrar Deneme Yönetimi'
    
    RETRY_DELAYS = [5, 15, 60, 240]  # Minutes: 5min, 15min, 1hour, 4hours
    
    def can_retry_transaction(self, transaction):
        """Check if transaction can be retried"""
        if not transaction.error_code_id:
            return False
        
        if not transaction.error_code_id.is_retryable:
            return False
        
        if transaction.retry_count >= transaction.max_retry:
            return False
        
        if transaction.state != 'error':
            return False
        
        return True
    
    def schedule_retry(self, transaction, immediate=False):
        """Schedule a retry for the transaction"""
        if not self.can_retry_transaction(transaction):
            return False
        
        retry_count = transaction.retry_count
        delay_minutes = self.RETRY_DELAYS[min(retry_count, len(self.RETRY_DELAYS) - 1)]
        
        if immediate:
            next_retry = fields.Datetime.now()
        else:
            next_retry = fields.Datetime.now() + timedelta(minutes=delay_minutes)
        
        transaction.write({
            'state': 'retry_scheduled',
            'next_retry_date': next_retry,
        })
        
        _logger.info(f"Retry scheduled for transaction {transaction.id} at {next_retry}")
        return True
    
    def execute_retry(self, transaction):
        """Execute a retry for the transaction"""
        if not self.can_retry_transaction(transaction):
            return False
        
        # Get the original document
        document = transaction.document_ref
        if not document:
            return False
        
        # Increment retry count
        transaction.write({
            'retry_count': transaction.retry_count + 1,
            'last_attempt_date': fields.Datetime.now(),
            'state': 'sending',
        })
        
        try:
            # Re-send the document
            if document._name == 'account.move':
                result = document.action_send_einvoice_retry(transaction)
            elif document._name == 'stock.picking':
                result = document.action_send_edespatch_retry(transaction)
            else:
                return False
            
            if result.get('success'):
                transaction.write({'state': 'sent'})
                return True
            else:
                # Check if still retryable
                if self.can_retry_transaction(transaction):
                    self.schedule_retry(transaction)
                else:
                    transaction.write({'state': 'error'})
                return False
                
        except Exception as e:
            _logger.error(f"Retry failed for transaction {transaction.id}: {str(e)}")
            transaction.write({
                'state': 'error',
                'error_message': str(e),
            })
            
            if self.can_retry_transaction(transaction):
                self.schedule_retry(transaction)
            
            return False
    
    def process_retry_queue(self):
        """Process all scheduled retries (called by cron)"""
        transactions = self.env['mdx.efatura.islem'].search([
            ('state', '=', 'retry_scheduled'),
            ('next_retry_date', '<=', fields.Datetime.now()),
        ])
        
        _logger.info(f"Processing {len(transactions)} scheduled retries")
        
        success_count = 0
        for trans in transactions:
            try:
                if self.execute_retry(trans):
                    success_count += 1
            except Exception as e:
                _logger.error(f"Error processing retry for {trans.id}: {str(e)}")
        
        _logger.info(f"Retry queue processed: {success_count}/{len(transactions)} successful")
        
        return {'processed': len(transactions), 'successful': success_count}
```

### Faz 3: Mevcut Kodun Güncellenmesi (Hafta 3-4)

#### 4.3.1 mdx_inh_account_move.py Güncellemesi
```python
# Mevcut action_send_einvoice metodunun güncellenmesi

def action_send_einvoice(self):
    """Send invoice with improved error handling"""
    self.ensure_one()
    
    # Pre-validation
    validator = self.env['mdx.pre.validation.mixin']
    errors = validator.validate_invoice_before_send(self)
    
    if errors:
        validator.display_validation_errors(errors)
        return False
    
    # Reserve series number with savepoint
    series_manager = self.env['mdx.series.manager.mixin']
    reservation = None
    
    try:
        reservation = series_manager.reserve_series_number(
            self.fatura_seri_id, 
            self
        )
        
        # Update invoice with reserved number
        self.write({
            'fatura_no': reservation['invoice_number'],
        })
        
        # Generate XML
        xml_string = self.generate_invoice_xml(self)
        
        # Create transaction log
        transaction = self.env['mdx.efatura.islem'].create({
            'document_ref': f'account.move,{self.id}',
            'document_type': self.efatura_turu_id.code,
            'state': 'sending',
            'series_id': self.fatura_seri_id.id,
            'series_number': reservation['number'],
            'xml_content': xml_string,
        })
        
        # Send invoice
        response = self.send_invoice_xml(self, xml_string)
        
        # Parse response
        error_handler = self.env['mdx.error.handler.mixin']
        result = error_handler.parse_error_response(response)
        
        if result.get('error_code') and result['error_code'] != 'AE00000':
            # Error occurred
            series_manager.release_series_number(reservation)
            
            # Update transaction
            transaction.write({
                'state': 'error',
                'error_code_id': result.get('error_record', False) and 
                                result['error_record'].id,
                'error_message': result.get('error_message'),
                'response_content': result.get('raw_response'),
            })
            
            # Clear UUID for retry
            self.write({'uuid': ''})
            
            # Check if retryable
            if result.get('is_retryable'):
                retry_manager = self.env['mdx.retry.manager.mixin']
                retry_manager.schedule_retry(transaction)
                
                raise UserError(
                    error_handler.format_error_for_user(result, self) +
                    "\n\nBu hata otomatik olarak yeniden denenecektir."
                )
            else:
                raise UserError(
                    error_handler.format_error_for_user(result, self)
                )
        
        # Success
        series_manager.confirm_series_number(reservation)
        transaction.write({
            'state': 'sent',
            'series_confirmed': True,
        })
        
        return True
        
    except UserError:
        raise
    except Exception as e:
        # Unexpected error - rollback series
        if reservation:
            series_manager.release_series_number(reservation)
        
        _logger.error(f"Unexpected error sending invoice {self.id}: {str(e)}")
        raise UserError(f"Beklenmeyen hata: {str(e)}")
```

### Faz 4: UI/UX Geliştirmeleri (Hafta 4-5)

#### 4.4.1 Form View Güncellemeleri
```xml
<!-- views/mdx_inh_account_move_views.xml -->

<!-- Error banner for invoices -->
<xpath expr="//sheet" position="before">
    <div class="alert alert-danger" role="alert"
         attrs="{'invisible': [('efatura_hata_durumu', '!=', 'error')]}">
        <field name="efatura_hata_html" widget="html" nolabel="1"/>
        <button name="action_retry_efatura" type="object" 
                string="Tekrar Dene" class="btn btn-sm btn-warning"
                attrs="{'invisible': [('efatura_retry_possible', '=', False)]}"/>
        <button name="action_view_efatura_log" type="object"
                string="İşlem Geçmişi" class="btn btn-sm btn-secondary"/>
    </div>
</xpath>

<!-- Transaction history smart button -->
<xpath expr="//div[@name='button_box']" position="inside">
    <button name="action_view_efatura_transactions" type="object"
            class="oe_stat_button" icon="fa-history"
            attrs="{'invisible': [('efatura_transaction_count', '=', 0)]}">
        <field name="efatura_transaction_count" widget="statinfo" 
               string="E-Fatura İşlemleri"/>
    </button>
</xpath>
```

#### 4.4.2 Wizard for Manual Retry
```python
# wizard/mdx_efatura_retry_wizard.py

class MdxEfaturaRetryWizard(models.TransientModel):
    _name = 'mdx.efatura.retry.wizard'
    _description = 'E-Fatura Tekrar Gönderim Sihirbazı'
    
    invoice_id = fields.Many2one('account.move', 'Fatura', required=True)
    transaction_id = fields.Many2one('mdx.efatura.islem', 'Son İşlem')
    
    error_display = fields.Html('Son Hata', related='transaction_id.error_display')
    can_retry = fields.Boolean('Tekrar Denenebilir', related='transaction_id.can_retry')
    retry_count = fields.Integer('Deneme Sayısı', related='transaction_id.retry_count')
    
    force_new_uuid = fields.Boolean('Yeni UUID Oluştur', default=True,
        help="Önceki UUID ile çakışma varsa işaretleyin")
    force_new_series = fields.Boolean('Yeni Seri Numarası Al', default=False,
        help="Seri numarası çakışması varsa işaretleyin")
    
    def action_retry(self):
        """Manually retry sending the invoice"""
        self.ensure_one()
        
        if self.force_new_uuid:
            self.invoice_id.write({
                'uuid': self.env['mdx.utility.mixin'].generate_uuid()
            })
        
        if self.force_new_series:
            # Get new series number
            pass
        
        return self.invoice_id.action_send_einvoice()
```

### Faz 5: Cron Jobs & Monitoring (Hafta 5)

#### 4.5.1 Cron Job Tanımları
```xml
<!-- data/mdx_efatura_cron_data.xml -->

<odoo>
    <data noupdate="1">
        <!-- Process retry queue every 5 minutes -->
        <record id="ir_cron_efatura_retry_queue" model="ir.cron">
            <field name="name">E-Fatura: Tekrar Deneme Kuyruğu</field>
            <field name="model_id" ref="model_mdx_retry_manager_mixin"/>
            <field name="state">code</field>
            <field name="code">model.process_retry_queue()</field>
            <field name="interval_number">5</field>
            <field name="interval_type">minutes</field>
            <field name="numbercall">-1</field>
            <field name="active">True</field>
        </record>
        
        <!-- Daily report of failed transactions -->
        <record id="ir_cron_efatura_daily_report" model="ir.cron">
            <field name="name">E-Fatura: Günlük Hata Raporu</field>
            <field name="model_id" ref="model_mdx_efatura_islem"/>
            <field name="state">code</field>
            <field name="code">model.send_daily_error_report()</field>
            <field name="interval_number">1</field>
            <field name="interval_type">days</field>
            <field name="numbercall">-1</field>
            <field name="active">True</field>
        </record>
    </data>
</odoo>
```

---

## 5. Dosya Yapısı {#dosya-yapisi}

```
edonusum/
├── __manifest__.py (güncelle)
├── __init__.py (güncelle)
│
├── models/
│   ├── __init__.py (güncelle)
│   ├── mdx_efatura_hata_kodu.py        # YENİ
│   ├── mdx_efatura_islem.py            # YENİ
│   ├── mdx_error_handler_mixin.py      # YENİ
│   ├── mdx_pre_validation_mixin.py     # YENİ
│   ├── mdx_series_manager_mixin.py     # YENİ
│   ├── mdx_retry_manager_mixin.py      # YENİ
│   ├── mdx_utility_mixin.py            # GÜNCELLE
│   ├── mdx_inh_account_move.py         # GÜNCELLE
│   └── mdx_inh_stock_picking.py        # GÜNCELLE
│
├── wizard/
│   ├── __init__.py (güncelle)
│   └── mdx_efatura_retry_wizard.py     # YENİ
│
├── views/
│   ├── mdx_efatura_hata_kodu_views.xml # YENİ
│   ├── mdx_efatura_islem_views.xml     # YENİ
│   ├── mdx_efatura_wizard_views.xml    # YENİ
│   ├── mdx_inh_account_move_views.xml  # GÜNCELLE
│   └── menu_items.xml                  # GÜNCELLE
│
├── data/
│   ├── mdx_efatura_hata_kodu_data.xml  # YENİ (tüm hata kodları)
│   ├── mdx_efatura_cron_data.xml       # YENİ
│   └── mdx_efatura_mail_templates.xml  # YENİ
│
├── security/
│   └── ir.model.access.csv             # GÜNCELLE
│
└── static/
    └── src/
        └── css/
            └── efatura_error.css       # YENİ
```

---

## 6. Test Stratejisi {#test-stratejisi}

### 6.1 Unit Tests

```python
# tests/test_error_handler.py

class TestErrorHandler(TransactionCase):
    
    def test_parse_ef_error_code(self):
        """Test parsing EF error codes"""
        handler = self.env['mdx.error.handler.mixin']
        result = handler.parse_error_response('[EF0089] Alıcı bilgilerinde...')
        self.assertEqual(result['error_code'], 'EF0089')
    
    def test_parse_ae_error_code(self):
        """Test parsing AE error codes"""
        handler = self.env['mdx.error.handler.mixin']
        result = handler.parse_error_response('AE00051: UUID mevcut')
        self.assertEqual(result['error_code'], 'AE00051')
    
    def test_retryable_error(self):
        """Test identifying retryable errors"""
        handler = self.env['mdx.error.handler.mixin']
        result = handler.parse_error_response('[EF0001] Sistem hatası')
        self.assertTrue(result['is_retryable'])
    
    def test_non_retryable_error(self):
        """Test identifying non-retryable errors"""
        handler = self.env['mdx.error.handler.mixin']
        result = handler.parse_error_response('[EF0044] Fatura no kullanılmış')
        self.assertFalse(result['is_retryable'])


class TestPreValidation(TransactionCase):
    
    def setUp(self):
        super().setUp()
        self.invoice = self.env['account.move'].create({...})
    
    def test_missing_partner_vat(self):
        """Test validation fails when partner VAT is missing"""
        validator = self.env['mdx.pre.validation.mixin']
        errors = validator.validate_invoice_before_send(self.invoice)
        error_codes = [e['code'] for e in errors]
        self.assertIn('EF0089', error_codes)


class TestSeriesManager(TransactionCase):
    
    def test_series_reservation(self):
        """Test series number reservation"""
        series = self.env['mdx.fatura.seri'].create({...})
        manager = self.env['mdx.series.manager.mixin']
        
        initial_index = series.index
        reservation = manager.reserve_series_number(series, self.invoice)
        
        self.assertEqual(reservation['number'], initial_index + 1)
    
    def test_series_rollback(self):
        """Test series rollback on error"""
        series = self.env['mdx.fatura.seri'].create({...})
        manager = self.env['mdx.series.manager.mixin']
        
        initial_index = series.index
        reservation = manager.reserve_series_number(series, self.invoice)
        manager.release_series_number(reservation)
        
        series.refresh()
        self.assertEqual(series.index, initial_index)
```

### 6.2 Integration Tests

```python
# tests/test_invoice_send.py

class TestInvoiceSend(TransactionCase):
    
    @patch('requests.post')
    def test_send_invoice_success(self, mock_post):
        """Test successful invoice sending"""
        mock_post.return_value.status_code = 200
        mock_post.return_value.content = b'<resultCode>AE00000</resultCode>'
        
        result = self.invoice.action_send_einvoice()
        self.assertTrue(result)
        self.assertEqual(self.invoice.efatura_durum, 'sent')
    
    @patch('requests.post')
    def test_send_invoice_retryable_error(self, mock_post):
        """Test retryable error handling"""
        mock_post.return_value.status_code = 200
        mock_post.return_value.content = b'[EF0001] Sistem hatası'
        
        with self.assertRaises(UserError):
            self.invoice.action_send_einvoice()
        
        # Check transaction was created with retry scheduled
        transaction = self.env['mdx.efatura.islem'].search([
            ('document_ref', '=', f'account.move,{self.invoice.id}')
        ])
        self.assertEqual(transaction.state, 'retry_scheduled')
    
    @patch('requests.post')
    def test_series_rollback_on_error(self, mock_post):
        """Test series number is rolled back on error"""
        mock_post.return_value.status_code = 500
        
        series = self.invoice.fatura_seri_id
        initial_index = series.index
        
        with self.assertRaises(UserError):
            self.invoice.action_send_einvoice()
        
        series.refresh()
        self.assertEqual(series.index, initial_index)
```

---

## 7. Zaman Çizelgesi

| Faz | Süre | Çıktılar |
|-----|------|----------|
| Faz 1: Temel Altyapı | 2 hafta | Models, Data files |
| Faz 2: Mixins | 1 hafta | Error handler, Pre-validation, Series manager, Retry manager |
| Faz 3: Kod Güncellemesi | 1 hafta | Updated send methods, transaction logging |
| Faz 4: UI/UX | 1 hafta | Views, Wizards, CSS |
| Faz 5: Cron & Monitoring | 0.5 hafta | Cron jobs, Reports |
| Test & QA | 1 hafta | Unit tests, Integration tests |
| **TOPLAM** | **6.5 hafta** | |

---

## 8. Öncelik Sıralaması

### P0 - Kritik (İlk 2 hafta)
1. ✅ Hata kodu master data modeli
2. ✅ Error handler mixin
3. ✅ Series manager mixin (rollback mekanizması)
4. ✅ Mevcut send metodlarının güncellenmesi

### P1 - Yüksek (Hafta 3-4)
5. ✅ Pre-validation mixin
6. ✅ Transaction log modeli
7. ✅ Retry manager mixin
8. ✅ UI hata gösterimi

### P2 - Orta (Hafta 5-6)
9. ⬜ Cron jobs
10. ⬜ Wizard'lar
11. ⬜ Raporlama
12. ⬜ Email bildirimleri

### P3 - Düşük (İleri tarih)
13. ⬜ Dashboard
14. ⬜ Analytics
15. ⬜ API entegrasyonu
