# -*- coding: utf-8 -*-
"""
E-Fatura Error Handler Mixin

Bu mixin, e-fatura/e-arşiv/e-irsaliye işlemlerinde oluşan hataların:
- Parse edilmesini
- Kategorize edilmesini
- Kullanıcı dostu mesajlara dönüştürülmesini
- Loglama ve izleme yapılmasını
sağlar.

Kullanım:
    class MyModel(models.Model):
        _name = 'my.model'
        _inherit = ['mdx.error.handler.mixin']
        
        def my_method(self):
            try:
                # ... işlemler
            except Exception as e:
                return self._handle_efatura_error(e, 'EFATURA')
"""

import re
import logging
from datetime import datetime

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class MdxErrorHandlerMixin(models.AbstractModel):
    _name = 'mdx.error.handler.mixin'
    _description = 'E-Fatura Hata İşleyici Mixin'

    # ==================== ERROR PARSING PATTERNS ====================
    ERROR_CODE_PATTERNS = [
        # eFinans E-Fatura/E-Arşiv hata kodları
        (r'\b(EF\d{4})\b', 'EFATURA'),
        (r'\b(EF\d{3})\b', 'EFATURA'),  # EF001 formatı için
        
        # eFinans E-İrsaliye hata kodları
        (r'\b(EI\d{4})\b', 'IRSALIYE'),
        (r'\b(EI\d{3})\b', 'IRSALIYE'),
        
        # Sistem/API hata kodları
        (r'\b(AE\d{5})\b', 'SYSTEM'),
        (r'\b(AE\d{4})\b', 'SYSTEM'),
        
        # REST API hata kodları (sadece resultCode/errorCode bağlamında)
        (r'\bresultCode["\s:=]+["\']?(\d{4})["\']?', 'REST'),
        (r'\berrorCode["\s:=]+["\']?(\d{4})["\']?', 'REST'),
    ]

    # ==================== PUBLIC METHODS ====================
    def _parse_error_code(self, error_message):
        """
        Hata mesajından hata kodunu çıkartır.
        
        :param error_message: Hata mesajı (string veya Exception)
        :return: tuple (error_code, error_type) veya (None, None)
        """
        if error_message is None:
            return None, None
            
        # Exception ise string'e çevir
        if isinstance(error_message, Exception):
            error_message = str(error_message)
        
        if not isinstance(error_message, str):
            error_message = str(error_message)
        
        for pattern, error_type in self.ERROR_CODE_PATTERNS:
            match = re.search(pattern, error_message, re.IGNORECASE)
            if match:
                code = match.group(1).upper()
                # Kodu normalize et (örn: EF001 -> EF0001)
                normalized_code = self._normalize_error_code(code)
                return normalized_code, error_type
        
        return None, None
    
    def _normalize_error_code(self, code):
        """
        Hata kodunu standart formata normalize eder.
        
        :param code: Hata kodu
        :return: Normalize edilmiş kod
        """
        if not code:
            return code
            
        code = code.upper().strip()
        
        # EF/EI kodları için 4 haneli numara
        match = re.match(r'^(EF|EI)(\d+)$', code)
        if match:
            prefix = match.group(1)
            number = match.group(2).zfill(4)
            return f"{prefix}{number}"
        
        # AE kodları için 5 haneli numara
        match = re.match(r'^AE(\d+)$', code)
        if match:
            number = match.group(1).zfill(5)
            return f"AE{number}"
        
        return code
    
    def _get_error_info(self, error_code):
        """
        Hata kodu için detaylı bilgi alır.
        
        :param error_code: Hata kodu
        :return: dict veya None
        """
        if not error_code:
            return None
            
        HataKodu = self.env['mdx.efatura.hata.kodu'].sudo()
        return HataKodu.get_error_info(error_code)
    
    def _get_user_friendly_message(self, error_code, original_message=None):
        """
        Kullanıcı dostu hata mesajı oluşturur.
        
        :param error_code: Hata kodu
        :param original_message: Orijinal hata mesajı (fallback)
        :return: string
        """
        error_info = self._get_error_info(error_code)
        
        if error_info:
            message = error_info.get('user_message', '')
            solution = error_info.get('solution_hint', '')
            
            if solution:
                message += f"\n\n💡 Çözüm: {solution}"
            
            # Kritik hatalar için uyarı ekle
            if error_info.get('severity') == 'critical':
                message = f"⚠️ KRİTİK HATA\n\n{message}"
            
            return message
        
        # Hata kodu bulunamazsa orijinal mesajı kullan
        if original_message:
            # Teknik detayları temizle
            return self._sanitize_error_message(original_message)
        
        return f"Bilinmeyen hata: {error_code}" if error_code else "Beklenmeyen bir hata oluştu."
    
    def _sanitize_error_message(self, message):
        """
        Teknik hata mesajını kullanıcı dostu hale getirir.
        
        :param message: Orijinal hata mesajı
        :return: Temizlenmiş mesaj
        """
        if not message:
            return "Beklenmeyen bir hata oluştu."
        
        message = str(message)
        
        # Stack trace ve teknik detayları kaldır
        lines = message.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Dosya yolu içeren satırları atla
            if 'File "' in line or 'line ' in line:
                continue
            # Traceback satırlarını atla
            if line.strip().startswith('Traceback'):
                continue
            if line.strip().startswith('at '):
                continue
            cleaned_lines.append(line)
        
        result = '\n'.join(cleaned_lines).strip()
        
        # Çok uzunsa kısalt
        if len(result) > 500:
            result = result[:497] + '...'
        
        return result if result else "Beklenmeyen bir hata oluştu."
    
    def _is_error_retryable(self, error_code):
        """
        Hatanın yeniden denenebilir olup olmadığını kontrol eder.
        
        :param error_code: Hata kodu
        :return: bool
        """
        error_info = self._get_error_info(error_code)
        return error_info.get('is_retryable', False) if error_info else False
    
    def _get_retry_config(self, error_code):
        """
        Yeniden deneme yapılandırmasını alır.
        
        :param error_code: Hata kodu
        :return: dict
        """
        error_info = self._get_error_info(error_code)
        
        if error_info and error_info.get('is_retryable'):
            return {
                'retryable': True,
                'max_count': error_info.get('max_retry_count', 3),
                'delay': error_info.get('retry_delay_seconds', 60),
            }
        
        return {
            'retryable': False,
            'max_count': 0,
            'delay': 0,
        }
    
    def _handle_efatura_error(self, exception, document_type='EFATURA', 
                               record=None, context_info=None):
        """
        E-Fatura hatasını işleyip uygun şekilde raporlar.
        
        :param exception: Exception nesnesi veya hata mesajı
        :param document_type: Belge türü (EFATURA, EARSIV, IRSALIYE)
        :param record: İlgili kayıt (opsiyonel - loglama için)
        :param context_info: Ek bağlam bilgisi (dict)
        :return: dict - işlem sonucu
        """
        error_message = str(exception) if isinstance(exception, Exception) else exception
        error_code, error_type = self._parse_error_code(error_message)
        
        # Hata bilgisini al
        error_info = self._get_error_info(error_code) if error_code else None
        
        # Kullanıcı dostu mesaj oluştur
        user_message = self._get_user_friendly_message(error_code, error_message)
        
        # Loglama
        self._log_error(
            error_code=error_code,
            error_message=error_message,
            document_type=document_type,
            record=record,
            context_info=context_info,
            error_info=error_info,
        )
        
        result = {
            'success': False,
            'error_code': error_code,
            'error_type': error_type or 'UNKNOWN',
            'user_message': user_message,
            'original_message': error_message,
            'retryable': self._is_error_retryable(error_code) if error_code else False,
            'retry_config': self._get_retry_config(error_code) if error_code else None,
            'category': error_info.get('category') if error_info else 'UNKNOWN',
            'severity': error_info.get('severity') if error_info else 'error',
        }
        
        return result
    
    def _raise_user_error(self, exception, document_type='EFATURA'):
        """
        Kullanıcı dostu UserError fırlatır.
        
        :param exception: Exception nesnesi veya hata mesajı
        :param document_type: Belge türü
        :raises: UserError
        """
        result = self._handle_efatura_error(exception, document_type)
        raise UserError(result['user_message'])
    
    def _log_error(self, error_code, error_message, document_type, 
                   record=None, context_info=None, error_info=None):
        """
        Hatayı sisteme loglar.
        
        :param error_code: Hata kodu
        :param error_message: Hata mesajı
        :param document_type: Belge türü
        :param record: İlgili kayıt
        :param context_info: Ek bağlam
        :param error_info: Hata bilgisi
        """
        severity = error_info.get('severity', 'error') if error_info else 'error'
        category = error_info.get('category', 'UNKNOWN') if error_info else 'UNKNOWN'
        
        # Log message oluştur
        log_parts = [
            f"[E-FATURA ERROR]",
            f"Code: {error_code or 'N/A'}",
            f"Category: {category}",
            f"Severity: {severity}",
            f"Type: {document_type}",
        ]
        
        if record:
            log_parts.append(f"Record: {record._name}({record.id})")
        
        log_parts.append(f"Message: {error_message}")
        
        if context_info:
            log_parts.append(f"Context: {context_info}")
        
        log_message = ' | '.join(log_parts)
        
        # Severity'ye göre log level belirle
        if severity == 'critical':
            _logger.critical(log_message)
        elif severity == 'error':
            _logger.error(log_message)
        elif severity == 'warning':
            _logger.warning(log_message)
        else:
            _logger.info(log_message)
    
    # ==================== SOAP/XML ERROR PARSING ====================
    def _parse_soap_response_error(self, response_xml):
        """
        SOAP yanıtından hata bilgilerini çıkartır.
        
        :param response_xml: SOAP yanıt XML'i
        :return: dict
        """
        if not response_xml:
            return {
                'success': False,
                'error_code': None,
                'error_message': 'Boş yanıt alındı',
            }
        
        try:
            from lxml import etree
            
            # XML'i parse et
            if isinstance(response_xml, str):
                response_xml = response_xml.encode('utf-8')
            
            root = etree.fromstring(response_xml)
            
            # Namespace'leri temizle
            for elem in root.iter():
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}')[1]
            
            # resultCode ve resultText ara
            result_code = None
            result_text = None
            
            result_code_elem = root.find('.//resultCode')
            if result_code_elem is not None:
                result_code = result_code_elem.text
            
            result_text_elem = root.find('.//resultText')
            if result_text_elem is not None:
                result_text = result_text_elem.text
            
            # Fault mesajı ara
            fault_string = root.find('.//faultstring')
            if fault_string is not None and fault_string.text:
                result_text = result_text or fault_string.text
            
            # Başarılı mı kontrol et
            success = result_code in ('AE00000', '0', 'SUCCESS', None) and not fault_string
            
            return {
                'success': success,
                'error_code': result_code,
                'error_message': result_text,
            }
            
        except Exception as e:
            _logger.error(f"SOAP yanıtı parse edilirken hata: {e}")
            return {
                'success': False,
                'error_code': None,
                'error_message': f'Yanıt parse hatası: {str(e)}',
            }
    
    def _parse_rest_response_error(self, response_dict):
        """
        REST API yanıtından hata bilgilerini çıkartır.
        
        :param response_dict: REST yanıt dict'i
        :return: dict
        """
        if not response_dict:
            return {
                'success': False,
                'error_code': None,
                'error_message': 'Boş yanıt alındı',
            }
        
        error_code = response_dict.get('errorCode') or response_dict.get('resultCode')
        error_message = response_dict.get('errorMessage') or response_dict.get('resultText') or response_dict.get('message')
        
        success = str(error_code) in ('0', 'AE00000', None) or response_dict.get('success', False)
        
        return {
            'success': success,
            'error_code': str(error_code) if error_code else None,
            'error_message': error_message,
        }
    
    # ==================== BATCH ERROR HANDLING ====================
    def _handle_batch_errors(self, errors_list, document_type='EFATURA'):
        """
        Toplu işlem hatalarını işler.
        
        :param errors_list: Hata listesi
        :param document_type: Belge türü
        :return: dict - özet bilgi
        """
        if not errors_list:
            return {
                'total_errors': 0,
                'categories': {},
                'retryable_count': 0,
                'critical_count': 0,
            }
        
        categories = {}
        retryable_count = 0
        critical_count = 0
        
        for error in errors_list:
            result = self._handle_efatura_error(error, document_type)
            
            category = result.get('category', 'UNKNOWN')
            categories[category] = categories.get(category, 0) + 1
            
            if result.get('retryable'):
                retryable_count += 1
            
            if result.get('severity') == 'critical':
                critical_count += 1
        
        return {
            'total_errors': len(errors_list),
            'categories': categories,
            'retryable_count': retryable_count,
            'critical_count': critical_count,
        }
