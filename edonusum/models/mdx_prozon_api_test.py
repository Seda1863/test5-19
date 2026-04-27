import binascii
import io
import json
import traceback
import zipfile

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

import hashlib
import base64
import uuid
import time
from datetime import datetime, date
import requests
import re
from pytz import timezone
from lxml import etree
import xml.etree.ElementTree as ET
import logging
from urllib.parse import urlparse

_logger = logging.getLogger(__name__)


class Mdx(models.Model):
    _name = "mdx.prozon.api.test"
    _description = "MDX Prozon API Test Model"

    name = fields.Char(string="Name", required=True)
    description = fields.Text(string="Description")
    username = fields.Char(
        string="User Name",
        required=True,
        help="Prozon API User Name. This is the username used to authenticate with the Prozon API.",
    )
    password = fields.Char(
        string="Password",
        required=True,
        help="Prozon API Password. This is the password used to authenticate with the Prozon API.",
    )
    workplace_code = fields.Char(
        string="Workplace Code",
        help="Prozon API Workplace Code. This is the code of the workplace associated with the API requests.",
    )
    base_url = "https://apihr.prozon.net/api/v1/"
    endpoint = fields.Selection(
        [
            ("get_magiclink", "GET | MagicLink"  ),
            ("get_employee", "GET | Employee"),
            ("get_employee_by_id", "GET | EmployeeByIdentityNumber"),
            ("add_employee", "POST | AddEmployee"),
            ("update_employee", "PUT | UpdateEmployee"),
            ("delete_employee", "DEL | DeleteEmployee"),
        ],
        string="Endpoint",
        required=True,
        default="get_magiclink",
    )
    employee_identity_number = fields.Char(string="Employee Identity Number")

    # Employee Fields for Add/Update
    first_name = fields.Char(string="First Name")
    last_name = fields.Char(string="Last Name")
    birth_date = fields.Date(string="Birth Date")
    email = fields.Char(string="Email")
    # EMPLOYEE TYPE ALANI GÜNCELLENDİ (Dokümandaki değerlere göre)
    employee_type = fields.Selection([
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
    ], string="Employee Type")
    gender = fields.Selection([('0', 'Belirtilmemiş'), ('1', 'Erkek'), ('2', 'Kadın')], string="Gender")
    phone_number = fields.Char(string="Phone Number")
    intercom = fields.Char(string="Intercom")
    role = fields.Selection([('1', 'İK Yöneticisi'), ('2', 'Personel')], string="Role")

    # Workplace Fields (nested in request body)
    workplace_entry_date = fields.Date(string="Workplace Entry Date")
    workplace_document_type = fields.Char(string="Workplace Document Type")
    workplace_law_number = fields.Char(string="Workplace Law Number")
    workplace_contract_type = fields.Selection([
        ('0', 'Belirsiz süreli tam zamanlı'),
        ('1', 'Belirsiz süreli kısmi zamanlı'),
        ('3', 'Belirli süreli tam zamanlı'),
        ('4', 'Belirli süreli kısmi zamanlı')
    ], string="Workplace Contract Type")
    workplace_contract_end_date = fields.Date(string="Workplace Contract End Date")

    # Salary Fields (nested in workplace)
    salary_wage_type = fields.Selection([('0', 'Asgari'), ('1', 'Net'), ('2', 'Brüt')], string="Salary Wage Type")
    salary_period_type = fields.Selection([('0', 'Saat'), ('1', 'Gün'), ('3', 'Ay')], string="Salary Period Type")
    salary_wage = fields.Float(string="Salary Wage")
    salary_foreign_currency = fields.Char(string="Salary Foreign Currency")
    salary_salary_type = fields.Selection([('0', 'Maaş'), ('1', 'Huzur Hakkı')], string="Salary Salary Type")

    request_url = fields.Char(string="Request URL", compute="_compute_request_url", store=True)
    request_method = fields.Selection(
        [("GET", "GET"), ("POST", "POST"), ("PUT", "PUT"), ("DEL", "DELETE")],
        string="Request Method",
        compute="_compute_request_method",
        store=True,
    )
    request_headers = fields.Text(
        string="Request Headers",
        default=lambda self: json.dumps(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Odoo/ProzonAPIClient",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "X-CompanyID": "2",
                "X-UserID": "1",
            },
            indent=4,
            ensure_ascii=False,
        ),
        help="Request Headers for Prozon API. Authentication is added automatically.",
    )
    request_body = fields.Text(string="Request Body", compute="_compute_request_body", store=True)
    response_status_code = fields.Integer(string="Response Status Code", readonly=True)
    response_body = fields.Text(string="Response Body")

    data_url = fields.Char(
        string="Data URL",
        compute="_compute_data_url",
        store=False,
    )

    @api.depends("response_body")
    def _compute_data_url(self):
        for record in self:
            record.data_url = False
            try:
                response = json.loads(record.response_body or "{}")
                data_url = response.get("Data")
                if isinstance(data_url, str) and urlparse(data_url).scheme in ("http", "https"  ):
                    record.data_url = data_url
            except Exception:
                record.data_url = False

    @api.depends("endpoint", "employee_identity_number")
    def _compute_request_url(self):
        for record in self:
            if record.endpoint:
                if record.endpoint == "get_magiclink":
                    record.request_url = f"{record.base_url}magiclink"
                elif record.endpoint == "get_employee":
                    record.request_url = f"{record.base_url}Employee"
                elif record.endpoint == "get_employee_by_id" and record.employee_identity_number:
                    # Dokümantasyona göre güncellendi
                    record.request_url = f"{record.base_url}Employee/{record.employee_identity_number}"
                elif record.endpoint == "add_employee":
                    record.request_url = f"{record.base_url}Employee"
                elif record.endpoint == "update_employee" and record.employee_identity_number:
                    record.request_url = f"{record.base_url}Employee/{record.employee_identity_number}"
                elif record.endpoint == "delete_employee" and record.employee_identity_number:
                    record.request_url = f"{record.base_url}Employee/{record.employee_identity_number}"
            else:
                record.request_url = ""

    @api.depends("endpoint")
    def _compute_request_method(self):
        for record in self:
            if record.endpoint:
                if record.endpoint.startswith("get_"):
                    record.request_method = "GET"
                elif record.endpoint.startswith("add_"):
                    record.request_method = "POST"
                elif record.endpoint.startswith("update_"):
                    record.request_method = "PUT"
                elif record.endpoint.startswith("delete_"):
                    record.request_method = "DEL"
            else:
                record.request_method = ""

    @api.depends(
        "endpoint",
        "first_name",
        "last_name",
        "birth_date",
        "employee_identity_number",
        "email",
        "employee_type",
        "gender",
        "phone_number",
        "intercom",
        "role",
        "workplace_code",
        "workplace_entry_date",
        "workplace_document_type",
        "workplace_law_number",
        "workplace_contract_type",
        "workplace_contract_end_date",
        "salary_wage_type",
        "salary_period_type",
        "salary_wage",
        "salary_foreign_currency",
        "salary_salary_type",
    )
    def _compute_request_body(self):
        for record in self:
            body = {}
            if record.endpoint == "add_employee" or record.endpoint == "update_employee":
                body = {
                    "firstName": record.first_name or "",
                    "lastName": record.last_name or "",
                    "birthDate": record.birth_date.strftime("%Y-%m-%d") if record.birth_date else "",
                    "identityNumber": record.employee_identity_number or "",
                    "email": record.email or "",
                    "employeeType": record.employee_type or "", # String olarak gönderiliyor
                    "gender": int(record.gender) if record.gender else 0, # int olarak gönderiliyor
                    "phoneNumber": record.phone_number or "",
                    "intercom": record.intercom or "",
                    "role": int(record.role) if record.role else 0, # int olarak gönderiliyor
                }

                if record.endpoint == "add_employee":
                    workplace_data = {
                        "WorkplaceCode": record.workplace_code or "",
                        "EntryDate": record.workplace_entry_date.strftime("%Y-%m-%d") if record.workplace_entry_date else "",
                        "DocumentType": record.workplace_document_type or "",
                        "LawNumber": record.workplace_law_number or "",
                        "ContractType": int(record.workplace_contract_type) if record.workplace_contract_type else 0, # int olarak gönderiliyor
                        "ContractEndDate": record.workplace_contract_end_date.strftime("%Y-%m-%d") if record.workplace_contract_end_date else "",
                    }
                    salary_data = {
                        "WageType": int(record.salary_wage_type) if record.salary_wage_type else 0, # int olarak gönderiliyor
                        "PeriodType": int(record.salary_period_type) if record.salary_period_type else 0, # int olarak gönderiliyor
                        "Wage": record.salary_wage if record.salary_wage is not False else 0,
                        "ForeignCurrency": record.salary_foreign_currency or "",
                        "SalaryType": int(record.salary_salary_type) if record.salary_salary_type else 0, # int olarak gönderiliyor
                    }
                    workplace_data["salary"] = salary_data
                    body["workplace"] = workplace_data
                else: # update_employee
                    body["workplace"] = None # Or populate if specific workplace fields are changed

            if body:
                record.request_body = json.dumps(body, indent=4, ensure_ascii=False)
            else:
                record.request_body = ""

    @api.onchange("endpoint")
    def _onchange_endpoint(self):
        # Clear all employee related fields when endpoint changes
        self.first_name = False
        self.last_name = False
        self.birth_date = False
        self.email = False
        self.employee_type = False
        self.gender = False
        self.phone_number = False
        self.intercom = False
        self.role = False
        self.workplace_entry_date = False
        self.workplace_document_type = False
        self.workplace_law_number = False
        self.workplace_contract_type = False
        self.workplace_contract_end_date = False
        self.salary_wage_type = False
        self.salary_period_type = False
        self.salary_wage = False
        self.salary_foreign_currency = False
        self.salary_salary_type = False
        self.request_body = "" # Clear computed body

        # workplace_code'u sadece add_employee için görünür yapacağımız için burada temizliyoruz
        if self.endpoint != "add_employee":
            self.workplace_code = False

        if self.endpoint in ("update_employee", "delete_employee", "get_employee_by_id"):
            self.employee_identity_number = self.employee_identity_number # Keep existing if any
        else:
            self.employee_identity_number = False

    @api.onchange('request_headers')
    def _onchange_request_headers(self):
        if self.request_headers:
            try:
                parsed = json.loads(self.request_headers)
                self.request_headers = json.dumps(parsed, indent=4, ensure_ascii=False)
            except json.JSONDecodeError as e:
                raise UserError(f"Request Headers alanında geçersiz JSON formatı: {e}")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'request_headers' in vals and vals['request_headers']:
                try:
                    parsed = json.loads(vals['request_headers'])
                    vals['request_headers'] = json.dumps(parsed, indent=4, ensure_ascii=False)
                except json.JSONDecodeError as e:
                    raise UserError(f"Request Headers alanında geçersiz JSON formatı: {e}")
        return super().create(vals_list)

    def write(self, vals):
        if 'request_headers' in vals and vals['request_headers']:
            try:
                parsed = json.loads(vals['request_headers'])
                vals['request_headers'] = json.dumps(parsed, indent=4, ensure_ascii=False)
            except json.JSONDecodeError as e:
                raise UserError(f"Request Headers alanında geçersiz JSON formatı: {e}")
        return super().write(vals)

    def action_fetch_employee_data(self):
        self.ensure_one()
        if not self.employee_identity_number:
            raise UserError("Lütfen çalışan kimlik numarasını girin.")

        original_endpoint = self.endpoint
        original_request_url = self.request_url
        original_request_method = self.request_method

        try:
            # Adım 1: Tüm çalışanları çekmek için endpoint'i ayarla
            self.endpoint = "get_employee"
            self._compute_request_url()
            self._compute_request_method()

            # Tüm çalışanları çekme isteğini gönder
            self.execute_request()

            if self.response_status_code == 200 and self.response_body:
                try:
                    response_data = json.loads(self.response_body)
                    all_employees = response_data.get("Data") # API yanıtında çalışan listesinin 'Data' anahtarında olduğunu varsayıyoruz

                    if not isinstance(all_employees, list):
                        raise UserError("API'den beklenen çalışan listesi alınamadı. Yanıt formatı hatalı.")

                    found_employee = None
                    for emp in all_employees:
                        # Çalışan kimlik numarasına göre filtrele (işyeri kodu filtrelemesi kaldırıldı)
                        if emp.get("IdentityNumber") == self.employee_identity_number:
                            found_employee = emp
                            break
                    
                    if found_employee:
                        # Adım 2: Bulunan çalışanın bilgilerini alanlara doldur
                        self.first_name = found_employee.get("FirstName")
                        self.last_name = found_employee.get("LastName")
                        self.birth_date = fields.Date.from_string(found_employee.get("BirthDate").split('T')[0]) if found_employee.get("BirthDate") else False
                        self.email = found_employee.get("Email")
                        self.employee_type = found_employee.get("EmployeeType") # String olarak atanıyor
                        self.gender = str(found_employee.get("Gender")) if found_employee.get("Gender") is not None else False # int'ten string'e
                        self.phone_number = found_employee.get("PhoneNumber")
                        self.intercom = found_employee.get("Intercom")
                        self.role = str(found_employee.get("Role")) if found_employee.get("Role") is not None else False # int'ten string'e

                        # İşyeri ve Maaş bilgileri iç içe olabilir
                        workplace_info = found_employee.get("Workplace")
                        if workplace_info:
                            self.workplace_code = workplace_info.get("WorkplaceCode")
                            self.workplace_entry_date = fields.Date.from_string(workplace_info.get("EntryDate").split('T')[0]) if workplace_info.get("EntryDate") else False
                            self.workplace_document_type = workplace_info.get("DocumentType")
                            self.workplace_law_number = workplace_info.get("LawNumber")
                            self.workplace_contract_type = str(workplace_info.get("ContractType")) if workplace_info.get("ContractType") is not None else False # int'ten string'e
                            self.workplace_contract_end_date = fields.Date.from_string(workplace_info.get("ContractEndDate").split('T')[0]) if workplace_info.get("ContractEndDate") else False

                            salary_info = workplace_info.get("Salary")
                            if salary_info:
                                self.salary_wage_type = str(salary_info.get("WageType")) if salary_info.get("WageType") is not None else False # int'ten string'e
                                self.salary_period_type = str(salary_info.get("PeriodType")) if salary_info.get("PeriodType") is not None else False # int'ten string'e
                                self.salary_wage = salary_info.get("Wage")
                                self.salary_foreign_currency = salary_info.get("ForeignCurrency")
                                self.salary_salary_type = str(salary_info.get("SalaryType")) if salary_info.get("SalaryType") is not None else False # int'ten string'e
                        else: # Workplace bilgisi yoksa alanları temizle
                            self.workplace_code = False
                            self.workplace_entry_date = False
                            self.workplace_document_type = False
                            self.workplace_law_number = False
                            self.workplace_contract_type = False
                            self.workplace_contract_end_date = False
                            self.salary_wage_type = False
                            self.salary_period_type = False
                            self.salary_wage = False
                            self.salary_foreign_currency = False
                            self.salary_salary_type = False
                        
                        # Çekilen verilerle request body'yi yeniden hesapla
                        self._compute_request_body()
                        
                        # Formu yeniden yükle (alanların güncellenmesi için)
                        return {
                            'type': 'ir.actions.act_window',
                            'res_model': self._name,
                            'res_id': self.id,
                            'view_mode': 'form',
                            'target': 'current',
                            'flags': {'form_view_initial_mode': 'edit'}, # Formu düzenleme modunda aç
                        }
                    else:
                        raise UserError(f"Belirtilen kimlik numarasına ({self.employee_identity_number}) sahip çalışan bulunamadı.")
                except json.JSONDecodeError:
                    raise UserError("API yanıtı geçerli bir JSON değil.")
                except Exception as e:
                    raise UserError(f"Çalışan bilgilerini işlerken bir hata oluştu: {e}")
            else:
                raise UserError(f"Tüm çalışanlar çekilemedi. Durum Kodu: {self.response_status_code}. Yanıt: {self.response_body}")
        finally:
            # Orijinal endpoint'i geri yükle ve URL/Metodu yeniden hesapla
            self.endpoint = original_endpoint
            self._compute_request_url()
            self._compute_request_method()

    def execute_request(self):
        for record in self:
            if not record.request_url:
                raise UserError("Request URL is not set. Please check the endpoint and parameters.")

            try:
                headers = json.loads(record.request_headers)
            except json.JSONDecodeError as e:
                raise UserError(f"Invalid JSON in Request Headers: {e}")

            credentials = f"{record.username}:{record.password}"
            auth_token = base64.b64encode(credentials.encode()).decode()
            headers["Authorization"] = f"Basic {auth_token}"

            headers.update({
                "X-Request-ID": str(uuid.uuid4()),
                "X-Request-Timestamp": datetime.now(timezone("UTC")).isoformat()
            })

            method = record.request_method
            
            request_data = None
            if method in ("POST", "PUT") and record.request_body:
                try:
                    parsed_body = json.loads(record.request_body)
                    request_data = json.dumps(parsed_body, ensure_ascii=False)
                    
                    if "Content-Type" not in headers:
                        headers["Content-Type"] = "application/json"
                except json.JSONDecodeError as e:
                    raise UserError(f"Invalid JSON in Request Body: {e}")

            try:
                if method == "GET":
                    response = requests.get(record.request_url, headers=headers)
                elif method == "POST":
                    response = requests.post(record.request_url, headers=headers, data=request_data)
                elif method == "PUT":
                    response = requests.put(record.request_url, headers=headers, data=request_data)
                elif method == "DEL":
                    response = requests.delete(record.request_url, headers=headers)
                else:
                    raise UserError(f"Unsupported HTTP method: {method}")

                record.response_status_code = response.status_code

                try:
                    parsed_response = json.loads(response.text)
                    record.response_body = json.dumps(
                        parsed_response, 
                        indent=4, 
                        ensure_ascii=False,
                        sort_keys=True
                    )
                except json.JSONDecodeError:
                    record.response_body = response.text

            except requests.RequestException as e:
                _logger.error("API call failed: %s\n%s", e, traceback.format_exc())
                raise UserError(f"API call failed: {e}\n{traceback.format_exc()}")
            
    def action_open_data_url(self):
        self.ensure_one()
        if not self.data_url:
            raise UserError("There is no valid Data URL to open.")
        return {
            "type": "ir.actions.act_url",
            "url": self.data_url,
            "target": "new",
        }

