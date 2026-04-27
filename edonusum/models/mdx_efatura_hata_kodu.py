# -*- coding: utf-8 -*-
"""
E-Fatura Hata Kodu Master Data Model

Bu model, eFinans ve GİB'den gelen tüm hata kodlarını kategorize ederek saklar.
Her hata kodu için:
- Kullanıcı dostu Türkçe mesajlar
- Çözüm önerileri
- Yeniden deneme politikası
- Önem seviyesi
bilgilerini içerir.

Kategoriler:
- AUTH: Kimlik doğrulama hataları
- VAL_RECEIVER: Alıcı bilgi doğrulama hataları
- VAL_SENDER: Satıcı bilgi doğrulama hataları
- VAL_LINE: Satır bilgi doğrulama hataları
- VAL_TAX: Vergi doğrulama hataları
- FORMAT: Format/Şema hataları
- SERIES: Seri/Numara hataları
- SYSTEM: Sistem hataları
- EXPORT: İhracat faturası hataları
- TOURIST: Yolcu beraber fatura hataları
- SGK: SGK faturası hataları
- PUBLIC: Kamu faturası hataları
- PAYMENT: Ödeme/Kontör hataları
- DESPATCH: E-İrsaliye hataları
"""

from odoo import api, fields, models, _


class MdxEfaturaHataKodu(models.Model):
    _name = 'mdx.efatura.hata.kodu'
    _description = 'E-Fatura Hata Kodu Tanımları'
    _order = 'code'
    _rec_name = 'code'

    # ==================== CATEGORY SELECTION ====================
    CATEGORY_SELECTION = [
        ('AUTH', 'Kimlik Doğrulama'),
        ('VAL_RECEIVER', 'Alıcı Doğrulama'),
        ('VAL_SENDER', 'Satıcı Doğrulama'),
        ('VAL_LINE', 'Satır Doğrulama'),
        ('VAL_TAX', 'Vergi Doğrulama'),
        ('FORMAT', 'Format/Şema'),
        ('SERIES', 'Seri/Numara'),
        ('SYSTEM', 'Sistem'),
        ('EXPORT', 'İhracat Faturası'),
        ('TOURIST', 'Yolcu Beraber'),
        ('SGK', 'SGK Faturası'),
        ('PUBLIC', 'Kamu Faturası'),
        ('PAYMENT', 'Ödeme/Kontör'),
        ('DESPATCH', 'E-İrsaliye'),
    ]

    SEVERITY_SELECTION = [
        ('info', 'Bilgi'),
        ('warning', 'Uyarı'),
        ('error', 'Hata'),
        ('critical', 'Kritik'),
    ]

    DOCUMENT_TYPE_SELECTION = [
        ('EFATURA', 'E-Fatura'),
        ('EARSIV', 'E-Arşiv'),
        ('IRSALIYE', 'E-İrsaliye'),
        ('ALL', 'Tümü'),
    ]

    # ==================== FIELDS ====================
    code = fields.Char(
        string='Hata Kodu',
        required=True,
        index=True,
        help="eFinans veya GİB hata kodu (örn: EF0044, AE00001)"
    )
    
    category = fields.Selection(
        selection=CATEGORY_SELECTION,
        string='Kategori',
        required=True,
        index=True,
        help="Hata kategorisi"
    )
    
    severity = fields.Selection(
        selection=SEVERITY_SELECTION,
        string='Önem Seviyesi',
        required=True,
        default='error',
        help="Hatanın kritiklik seviyesi"
    )
    
    document_type = fields.Selection(
        selection=DOCUMENT_TYPE_SELECTION,
        string='Belge Türü',
        default='ALL',
        help="Bu hatanın hangi belge türüne ait olduğu"
    )
    
    is_retryable = fields.Boolean(
        string='Yeniden Denenebilir',
        default=False,
        help="Bu hata için otomatik yeniden deneme yapılabilir mi?"
    )
    
    max_retry_count = fields.Integer(
        string='Maksimum Deneme',
        default=3,
        help="Otomatik yeniden deneme sayısı (is_retryable=True ise)"
    )
    
    retry_delay_seconds = fields.Integer(
        string='Deneme Aralığı (sn)',
        default=60,
        help="Yeniden denemeler arası bekleme süresi"
    )
    
    user_message_tr = fields.Text(
        string='Kullanıcı Mesajı (TR)',
        required=True,
        help="Kullanıcıya gösterilecek Türkçe hata mesajı"
    )
    
    user_message_en = fields.Text(
        string='Kullanıcı Mesajı (EN)',
        help="Kullanıcıya gösterilecek İngilizce hata mesajı"
    )
    
    solution_hint_tr = fields.Text(
        string='Çözüm Önerisi (TR)',
        help="Kullanıcıya gösterilecek Türkçe çözüm önerisi"
    )
    
    solution_hint_en = fields.Text(
        string='Çözüm Önerisi (EN)',
        help="Kullanıcıya gösterilecek İngilizce çözüm önerisi"
    )
    
    technical_description = fields.Text(
        string='Teknik Açıklama',
        help="Geliştiriciler için teknik açıklama"
    )
    
    active = fields.Boolean(
        string='Aktif',
        default=True,
    )
    
    # ==================== SQL CONSTRAINTS ====================
    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Bu hata kodu zaten tanımlanmış!'),
    ]

    # ==================== ACTIONS ====================
    def toggle_active(self):
        """Aktif/Pasif durumunu değiştirir."""
        for record in self:
            record.active = not record.active

    # ==================== COMPUTED FIELDS ====================
    @api.depends('code', 'user_message_tr')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"[{record.code}] {record.user_message_tr[:50]}..." if record.user_message_tr and len(record.user_message_tr) > 50 else f"[{record.code}] {record.user_message_tr or ''}"

    # ==================== PUBLIC METHODS ====================
    @api.model
    def get_error_info(self, error_code):
        """
        Verilen hata kodu için tüm bilgileri döndürür.
        
        :param error_code: Hata kodu (string)
        :return: dict veya None
        """
        if not error_code:
            return None
            
        # Önce tam eşleşme ara
        error = self.search([('code', '=', error_code)], limit=1)
        
        # Bulunamazsa EF/EI/AE prefix'i ile ara
        if not error and error_code.startswith(('EF', 'EI', 'AE')):
            # Numarayı çıkar ve farklı formatlarla dene
            import re
            match = re.match(r'([A-Z]+)0*(\d+)', error_code)
            if match:
                prefix = match.group(1)
                number = match.group(2)
                # Farklı sıfır padding'leri ile dene
                for padding in ['', '0', '00', '000', '0000']:
                    test_code = f"{prefix}{padding}{number}"
                    error = self.search([('code', '=', test_code)], limit=1)
                    if error:
                        break
        
        if not error:
            return None
            
        return {
            'code': error.code,
            'category': error.category,
            'category_name': dict(self.CATEGORY_SELECTION).get(error.category, ''),
            'severity': error.severity,
            'severity_name': dict(self.SEVERITY_SELECTION).get(error.severity, ''),
            'is_retryable': error.is_retryable,
            'max_retry_count': error.max_retry_count,
            'retry_delay_seconds': error.retry_delay_seconds,
            'user_message': error.user_message_tr or error.user_message_en or '',
            'solution_hint': error.solution_hint_tr or error.solution_hint_en or '',
            'document_type': error.document_type,
        }
    
    @api.model
    def get_user_friendly_message(self, error_code, original_message=None):
        """
        Hata kodu için kullanıcı dostu mesaj döndürür.
        Hata kodu bulunamazsa orijinal mesajı döndürür.
        
        :param error_code: Hata kodu (string)
        :param original_message: Orijinal hata mesajı (fallback)
        :return: string
        """
        error_info = self.get_error_info(error_code)
        
        if error_info:
            message = error_info['user_message']
            if error_info['solution_hint']:
                message += f"\n\n💡 Çözüm: {error_info['solution_hint']}"
            return message
        
        return original_message or f"Bilinmeyen hata: {error_code}"
    
    @api.model
    def is_error_retryable(self, error_code):
        """
        Verilen hata kodunun yeniden denenebilir olup olmadığını döndürür.
        
        :param error_code: Hata kodu (string)
        :return: bool
        """
        error_info = self.get_error_info(error_code)
        return error_info.get('is_retryable', False) if error_info else False
    
    @api.model
    def get_retry_config(self, error_code):
        """
        Yeniden deneme yapılandırmasını döndürür.
        
        :param error_code: Hata kodu (string)
        :return: dict {'retryable': bool, 'max_count': int, 'delay': int}
        """
        error_info = self.get_error_info(error_code)
        
        if error_info and error_info['is_retryable']:
            return {
                'retryable': True,
                'max_count': error_info['max_retry_count'],
                'delay': error_info['retry_delay_seconds'],
            }
        
        return {
            'retryable': False,
            'max_count': 0,
            'delay': 0,
        }
    
    @api.model
    def get_errors_by_category(self, category):
        """
        Belirli bir kategorideki tüm hata kodlarını döndürür.
        
        :param category: Kategori kodu
        :return: recordset
        """
        return self.search([('category', '=', category)])
    
    @api.model
    def get_critical_errors(self):
        """
        Kritik seviyedeki tüm hata kodlarını döndürür.
        
        :return: recordset
        """
        return self.search([('severity', '=', 'critical')])
    
    @api.model
    def get_retryable_errors(self):
        """
        Yeniden denenebilir tüm hata kodlarını döndürür.
        
        :return: recordset
        """
        return self.search([('is_retryable', '=', True)])
    
    @api.model
    def parse_error_code_from_message(self, message):
        """
        Hata mesajından hata kodunu çıkartır.
        
        :param message: Hata mesajı (string)
        :return: string veya None
        """
        if not message:
            return None
            
        import re
        
        # eFinans hata kodu pattern'leri
        patterns = [
            r'\b(EF\d{4})\b',      # EF0001, EF0044, vb.
            r'\b(EI\d{4})\b',      # EI0001, EI0018, vb.
            r'\b(AE\d{5})\b',      # AE00001, AE00051, vb.
            r'\b(\d{4})\b',        # REST API: 1000, 1001, vb.
            r'resultCode["\s:=]+(\w+)',  # XML response
            r'errorCode["\s:=]+(\w+)',   # JSON response
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                code = match.group(1).upper()
                # Veritabanında var mı kontrol et
                if self.search([('code', '=', code)], limit=1):
                    return code
        
        return None
    
    @api.model
    def categorize_error(self, error_code):
        """
        Hata kodunu analiz edip kategori bilgisi döndürür.
        
        :param error_code: Hata kodu
        :return: dict
        """
        error_info = self.get_error_info(error_code)
        
        if not error_info:
            # Bilinmeyen hata kodu - prefix'e göre tahmin et
            if error_code and error_code.startswith('EI'):
                return {
                    'category': 'DESPATCH',
                    'document_type': 'IRSALIYE',
                    'severity': 'error',
                }
            elif error_code and error_code.startswith('AE'):
                return {
                    'category': 'SYSTEM',
                    'document_type': 'ALL',
                    'severity': 'error',
                }
            else:
                return {
                    'category': 'SYSTEM',
                    'document_type': 'EFATURA',
                    'severity': 'error',
                }
        
        return {
            'category': error_info['category'],
            'document_type': error_info['document_type'],
            'severity': error_info['severity'],
        }
