# -*- coding: utf-8 -*-

import datetime
import json
from datetime import timezone

import requests
from odoo import models, fields, api, SUPERUSER_ID
from odoo.exceptions import UserError, ValidationError
import logging
import uuid
import base64

_logger = logging.getLogger(__name__)

class MdxInhHrEmployee(models.Model):
    _inherit = 'hr.employee'
    _description = 'MindDX HR Employee'

    # Tüm Prozon verilerini JSON olarak tutacak ana alan
    prozon_data = fields.Text(
        string='Prozon JSON Verisi',
        compute='_compute_prozon_data',
        store=True,
        help="Tüm Prozon alanlarının JSON halinde tutulduğu ana depo"
    )

    # Diğer tüm Prozon alanları artık bu JSON'dan hesaplanacak
    sended_to_prozon = fields.Boolean(
        string='Prozon\'a Gönderildi',
        compute='_compute_from_json',
        store=False,
        help="Prozon API'ye gönderildi mi?"
    )

    prozon_id = fields.Integer(
        string='Prozon ID',
        compute='_compute_from_json',
        store=False,
        help="Prozon API için çalışan ID'si"
    )

    prozon_first_name = fields.Char(
        string='Ad',
        compute='_compute_from_json',
        store=False,
        help="Prozon API için çalışan adı"
    )

    prozon_last_name = fields.Char(
        string='Soyad',
        compute='_compute_from_json',
        store=False,
        help="Prozon API için çalışan soyadı"
    )

    prozon_birth_date = fields.Date(
        string='Doğum Tarihi',
        compute='_compute_from_json',
        store=False,
        help="Prozon API için çalışan doğum tarihi"
    )

    prozon_identity_number = fields.Char(
        string='Kimlik Numarası',
        compute='_compute_from_json',
        store=False,
        help="Prozon API için çalışan kimlik numarası"
    )

    prozon_email = fields.Char(
        string='E-Posta',
        compute='_compute_from_json',
        store=False,
        help="Prozon API için çalışan e-posta adresi"
    )

    prozon_employee_type = fields.Selection([
        ('Normal Çalışan', 'Normal Çalışan'),
        ('Yabancı Uyruklu Çalışan', 'Yabancı Uyruklu Çalışan'),
        ('Emekli', 'Emekli'),
        ('Zorunlu Stajyer', 'Zorunlu Stajyer'),
        ('Zorunlu Olmayan Stajyer', 'Zorunlu Olmayan Stajyer'),
        ('Çırak', 'Çırak'),
        ('Kalfa', 'Kalfa'),
        ('İEP', 'İEP'),
        ('Genç İşçi', 'Genç İşçi'),
        ('Kayıt Dışı', 'Kayıt Dışı')
    ], string="Çalışan Tipi",
        store=True,
        help="Prozon API için çalışan türü"
    )

    prozon_gender = fields.Selection(
        [('0', 'Belirtilmemiş'), ('1', 'Erkek'), ('2', 'Kadın')],
        string="Prozon Cinsiyet",
        compute='_compute_from_json',
        store=False,
        help="Prozon API için çalışan cinsiyeti"
    )

    prozon_phone_number = fields.Char(
        string='Telefon Numarası',
        compute='_compute_from_json',
        store=False,
        help="Prozon API için çalışan telefon numarası"
    )

    prozon_intercom = fields.Char(
        string='Intercom',
        store=True,
        help="Prozon API için çalışan intercom bilgisi",
        default=''
    )

    prozon_role = fields.Selection(
        [('1', 'İK Yöneticisi'), ('2', 'Personel')],
        string="Kullanıcı Rolü",
        store=True,
        help="Prozon API için çalışan rolü",
        default='2'
    )

    prozon_profession_code = fields.Many2one(
        'mdx.sabit.kod',
        string="Meslek Kodu",
        store=True,
        help="Prozon API için Meslek Kodu",
        domain=[("liste_id.code", '=', 'MESLEK')]
    )

    prozon_workplace_code = fields.Char(
        string='Prozon İş Yeri Kodu',
        compute='_compute_from_json',
        store=False,
        help="Prozon API için iş yeri kodu"
    )

    prozon_workplace_entry_date = fields.Date(
        string='İşe Giriş Tarihi',
        store=True,
        help="Prozon API için işe giriş tarihi"
    )

    prozon_workplace_document_type = fields.Many2one(
        'mdx.sabit.kod',
        string='Belge Türü',
        store=True,
        help="Prozon API için belge türü",
        domain=[('liste_id.code', '=', 'IKBELGETURU')]
    )

    prozon_workplace_law_number = fields.Many2one(
        'mdx.sabit.kod',
        string='Kanun Numarası',
        store=True,
        help="Prozon API için kanun numarası",
        domain=[('liste_id.code', '=', 'IKKANUN')]
    )

    prozon_workplace_contract_type = fields.Selection([
        ('0', 'Belirsiz süreli tam zamanlı'),
        ('1', 'Belirsiz süreli kısmi zamanlı'),
        ('3', 'Belirli süreli tam zamanlı'),
        ('4', 'Belirli süreli kısmi zamanlı')
    ],
        string="Sözleşme Tipi",
        store=True,
        help="Prozon API için sözleşme türü",
        default='0'
    )

    prozon_workplace_contract_end_date = fields.Date(
        string='Sözleşme Bitiş Tarihi',
        store=True,
        help="Prozon API için sözleşme bitiş tarihi"
    )

    prozon_salary_wage_type = fields.Selection(
        [('0', 'Asgari'), ('1', 'Net'), ('2', 'Brüt')],
        string="Ücret Tipi",
        store=True,
        help="Prozon API için maaş ücret türü",
        default='1'
    )
    
    prozon_salary_period_type = fields.Selection(
        [('0', 'Saat'), ('1', 'Gün'), ('3', 'Ay')],
        string="Periyot Tipi",
        store=True,
        help="Prozon API için maaş dönem türü",
        default='3'
    )
    
    prozon_salary_wage = fields.Float(
        string='Personel Ücreti',
        store=True,
        help="Prozon API için maaş ücreti",
        digits=(16, 2),
        default=0.0
    )
    
    prozon_salary_foreign_currency = fields.Many2one(
        'res.currency',
        string='Ücret Para Birimi',
        compute='_compute_from_json',
        store=False,
        help="Prozon API için maaş para birimi"
    )
    
    prozon_salary_salary_type = fields.Selection(
        [('0', 'Maaş'), ('1', 'Huzur Hakkı')],
        string="Maaş Tipi",
        store=True,
        help="Prozon API için maaş türü",
        default='0'
    )

    prozon_error_message = fields.Text(
        string='Hata Mesajı',
        compute='_compute_from_json',
        store=False,
        help="Prozon API ile iletişimde oluşan hata mesajı"
    )

    prozon_response_body = fields.Text(string="Response Body")

    # Tüm Prozon verilerini toplayan ana compute metodu
    @api.depends(
        'name', 'birthday', 'identification_id', 'gender',
        'work_email', 'private_email', 'work_phone', 'private_phone', 'company_id', 
        'company_id.currency_id', 'company_id.prozon_workplace_code',
        'prozon_identity_number'  # API alanları için
    )
    def _compute_prozon_data(self):
        for emp in self:
            # API verilerini al
            api_data = self._get_prozon_api_data(emp)
            
            # Temel verileri topla
            data = {
                'first_name': emp.name and emp.name.rsplit(' ', 1)[0] or '',
                'last_name': emp.name and emp.name.split(' ')[-1] or '' if emp.name else '',
                'birth_date': emp.birthday and emp.birthday.isoformat() or None,
                'identity_number': emp.identification_id or '',
                'email': emp.work_email or emp.private_email or '',
                'gender': {'other':'0','male':'1','female':'2'}.get(emp.gender, '0'),
                'phone': emp.work_phone or emp.private_phone or '',
                'workplace_code': emp.company_id.prozon_workplace_code or '' if emp.company_id else '',
                'salary_currency_id': emp.company_id.currency_id.id if emp.company_id and emp.company_id.currency_id else None,
                
                # API'den gelen veriler
                'sended_to_prozon': api_data.get('sended_to_prozon', False),
                'prozon_id': api_data.get('prozon_id', 0),
                'prozon_error_message': api_data.get('prozon_error_message', ''),
            }
            emp.prozon_data = json.dumps(data)

    # JSON'dan diğer alanları hesaplayan metot
    @api.depends('prozon_data')
    def _compute_from_json(self):
        for emp in self:
            try:
                data = json.loads(emp.prozon_data or '{}')
            except json.JSONDecodeError:
                data = {}
            
            # Temel alanlar
            emp.prozon_first_name = data.get('first_name', '')
            emp.prozon_last_name = data.get('last_name', '')
            birth_date_str = data.get('birth_date')
            emp.prozon_birth_date = fields.Date.to_date(birth_date_str) if birth_date_str else False
            emp.prozon_identity_number = data.get('identity_number', '')
            emp.prozon_email = data.get('email', '')
            emp.prozon_gender = data.get('gender', '0')
            emp.prozon_phone_number = data.get('phone', '')
            emp.prozon_workplace_code = data.get('workplace_code', '')
            
            # Para birimi
            currency_id = data.get('salary_currency_id')
            if currency_id:
                emp.prozon_salary_foreign_currency = self.env['res.currency'].browse(currency_id)
            else:
                emp.prozon_salary_foreign_currency = self.env.ref('base.USD', raise_if_not_found=False)
            
            # API alanları
            emp.sended_to_prozon = data.get('sended_to_prozon', False)
            emp.prozon_id = data.get('prozon_id', 0)
            emp.prozon_error_message = data.get('prozon_error_message', '')

    # API verilerini getiren yardımcı metot
    def _get_prozon_api_data(self, employee):
        """Prozon API'den güncel verileri getirir"""
        web_service = self._get_prozon_web_service()
        if not web_service:
            return {
                'sended_to_prozon': False,
                'prozon_id': 0,
                'prozon_error_message': 'Prozon web servisi bulunamadı'
            }

        base_url = web_service.url
        identity_number = employee.identification_id or ''
        
        if not identity_number:
            return {
                'sended_to_prozon': False,
                'prozon_id': 0,
                'prozon_error_message': 'Kimlik numarası eksik'
            }

        request_url = f"{base_url}Employee/{identity_number}"
        headers = self._generate_prozon_headers(web_service)
        
        try:
            response = requests.get(request_url, headers=headers, timeout=10)
            response.raise_for_status()
            response_data = response.json()
            
            if response_data.get('Success', False):
                return {
                    'sended_to_prozon': True,
                    'prozon_id': response_data.get('Data', {}).get('id', 0),
                    'prozon_error_message': ''
                }
            else:
                return {
                    'sended_to_prozon': False,
                    'prozon_id': 0,
                    'prozon_error_message': response_data.get('Message', 'API hatası')
                }
                
        except Exception as e:
            error_msg = f"Connection Error: {str(e)}"
            _logger.error(error_msg)
            return {
                'sended_to_prozon': False,
                'prozon_id': 0,
                'prozon_error_message': error_msg
            }

    # Web servisini getiren yardımcı metot
    def _get_prozon_web_service(self):
        web_service = self.env['mdx.web.service'].search([('name', '=', 'PROZON')], limit=1)
        if not web_service:
            _logger.error("Prozon web service not found")
        return web_service

    # HTTP başlıklarını oluşturan yardımcı metot
    def _generate_prozon_headers(self, web_service):
        username = str(web_service.username)
        password = str(web_service.password)
        credentials = f"{username}:{password}"
        auth_token = base64.b64encode(credentials.encode()).decode()
        
        current_time = datetime.datetime.now(timezone.utc).isoformat()
        
        return {
            "Authorization": f"Basic {auth_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Odoo/ProzonAPIClient",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "X-CompanyID": "2",
            "X-UserID": "1",
            "X-Request-ID": str(uuid.uuid4()),
            "X-Request-Timestamp": current_time
        }

    # Prozon bağlantı aksiyonu
    def action_connect_prozon(self):
        self.ensure_one()
        web_service = self._get_prozon_web_service()
        if not web_service:
            raise UserError("Prozon web service not found. Please check settings.")

        request_url = f"{web_service.url}magiclink"
        headers = self._generate_prozon_headers(web_service)
        
        try:
            response = requests.get(request_url, headers=headers, timeout=10)
            response.raise_for_status()
            response_data = response.json()
            
            if response_data.get('Success', False) and (link := response_data.get('Data')):
                return {
                    'type': 'ir.actions.act_url',
                    'url': link,
                    'target': 'new',
                }
                
            error_msg = response_data.get('Message', 'Bilinmeyen API hatası')
            raise UserError(f"Prozon API Hatası: {error_msg}")
            
        except Exception as e:
            raise UserError(f"Bağlantı Hatası: {str(e)}")
        
    def action_send_to_prozon(self):
        self.ensure_one()
        web_service = self._get_prozon_web_service()
        if not web_service:
            raise UserError("Prozon web servisi bulunamadı. Lütfen ayarları kontrol edin.")
        
        request_url = f"{web_service.url}Employee"
        headers = self._generate_prozon_headers(web_service)
        
        # Zorunlu alan kontrolü
        if not all([self.prozon_first_name, self.prozon_last_name, self.prozon_identity_number]):
            raise UserError("Ad, soyad ve kimlik numarası zorunlu alanlardır!")
        
        # Tarih formatlama
        birth_date = self.prozon_birth_date.isoformat() if self.prozon_birth_date else ""
        entry_date = self.prozon_workplace_entry_date.isoformat() if self.prozon_workplace_entry_date else ""
        contract_end_date = self.prozon_workplace_contract_end_date.isoformat() if self.prozon_workplace_contract_end_date else ""
        
        employee_data = {
            "firstName": self.prozon_first_name,
            "lastName": self.prozon_last_name,
            "birthDate": birth_date,
            "identityNumber": self.prozon_identity_number,
            "email": self.prozon_email,
            "employeeType": self.prozon_employee_type,
            "gender": self.prozon_gender,
            "phoneNumber": self.prozon_phone_number,
            "intercom": self.prozon_intercom,
            "role": self.prozon_role,   
            "ProfessionCode": self.prozon_profession_code.code if self.prozon_profession_code else "0000.00",
            "KGVM": 1,
            "AUKGVM": 1,
            "Workplace": {
                "WorkplaceCode": self.prozon_workplace_code,
                "EntryDate": entry_date,
                "DocumentType": self.prozon_workplace_document_type.prozon_kod if self.prozon_workplace_document_type else "",
                "LawNumber": self.prozon_workplace_law_number.prozon_kod if self.prozon_workplace_law_number else "",
                "ContractType": self.prozon_workplace_contract_type,
                "ContractEndDate": contract_end_date,
                "Salary": {
                    "WageType": self.prozon_salary_wage_type,
                    "PeriodType": self.prozon_salary_period_type,
                    "Wage": self.prozon_salary_wage,    
                    "ForeignCurrency": self.prozon_salary_foreign_currency.name if self.prozon_salary_foreign_currency else "",
                    "SalaryType": self.prozon_salary_salary_type,
                },
                "DevirMatrahAy1": 1,
                "DevirMatrahYıl1": datetime.datetime.now().year,
                "DevirMatrahTutar1": 1.0,
                "DevirMatrahTutar2": 1.0,
            }
        }

        _logger.error(f"employee_data: {json.dumps(employee_data, indent=2, ensure_ascii=False)}")

        # try:
        response = requests.post(request_url, headers=headers, data=json.dumps(employee_data, ensure_ascii=False).encode('utf-8'), timeout=10)
            
        try:
            response_data = response.json()
            self.prozon_response_body = json.dumps(response_data, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            self.prozon_response_body = response.text
            
        if response.status_code >= 400:
            # error_msg = f"{response.status_code} {response.reason}"
            # if response_data and 'Message' in response_data:
            #     error_msg += f": {response_data['Message']}"
            # raise UserError(f"Prozon API Hatası: {error_msg}")
            self.prozon_error_message = f"HTTP {response.status_code}: {response.reason}"
            self.prozon_response_body = response.text
            _logger.error(f"Prozon API Hatası: HTTP {response.status_code}: {response.reason}")
            _logger.error(f"Response Body: {response.text}")
        
        # Başarı durumu
        if response_data.get('Success', False):
            self.sended_to_prozon = True
            self.prozon_id = response_data.get('Data', {}).get('id', 0)
            self.prozon_error_message = ""
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'Çalışan Prozon\'a başarıyla gönderildi',
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            error_msg = response_data.get('Message', 'Bilinmeyen API hatası')
            self.prozon_error_message = error_msg
            self.prozon_response_body = json.dumps(response_data, indent=2, ensure_ascii=False)
            raise UserError(f"Prozon API Hatası: {error_msg}")
                
    def action_update_on_prozon(self):
        self.ensure_one()
        # Burada Prozon API'de güncelleme işlemini gerçekleştir
        # Başarılı olursa:
        self.prozon_error_message = "Başarıyla güncellendi"
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': 'Çalışan Prozon\'da başarıyla güncellendi',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_delete_from_prozon(self):
        self.ensure_one()
        # Burada Prozon API'den silme işlemini gerçekleştir
        # Başarılı olursa:
        self.prozon_error_message = "Başarıyla silindi"
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': 'Çalışan Prozon\'dan başarıyla silindi',
                'type': 'success',
                'sticky': False,
            }
        }