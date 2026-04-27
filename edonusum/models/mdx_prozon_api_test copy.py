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
            ("get_magiclink", "GET | MagicLink" ),
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
    # request_body artık compute değil, onchange ile set edilecek ve kullanıcı tarafından düzenlenebilir olacak
    request_body = fields.Text(string="Request Body")
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
                if isinstance(data_url, str) and urlparse(data_url).scheme in ("http", "https" ):
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
                    record.request_url = (
                        f"{record.base_url}Employee/{record.employee_identity_number}/"
                        f"{str(record.employee_identity_number).replace(' ', '')}"
                    )
                elif record.endpoint == "add_employee":
                    record.request_url = f"{record.base_url}Employee"
                elif record.endpoint == "update_employee" and record.employee_identity_number:
                    record.request_url = f"{record.base_url}employee/{record.employee_identity_number}"
                elif record.endpoint == "delete_employee" and record.employee_identity_number:
                    record.request_url = f"{record.base_url}employee/{record.employee_identity_number}"
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

    # request_body artık onchange ile set edilecek
    @api.onchange("endpoint", "employee_identity_number")
    def _onchange_endpoint_set_request_body(self):
        if self.endpoint == "add_employee":
            self.request_body = json.dumps(
                {
                    "firstName": "ALİ HAYDAR",
                    "lastName": "BİLGİÇ",
                    "birthDate": "1999-01-01",
                    "identityNumber": self.employee_identity_number,
                    "email": "ahb1245@gmail.com",
                    "employeeType": "Normal Çalışan",
                    "gender": 1,
                    "phoneNumber": "5555555555",
                    "intercom": "",
                    "role": 1,
                    "workplace": {
                        "WorkplaceCode": "65DE95F11B51",
                        "EntryDate": "2025-05-01",
                        "DocumentType": "1",
                        "LawNumber": "5510",
                        "ContractType": 0,
                        "ContractEndDate": "",
                        "salary": {
                            "WageType": 1,
                            "PeriodType": 3,
                            "Wage": 99990,
                            "ForeignCurrency": "TL",
                            "SalaryType": 0,
                        },
                    },
                },
                indent=4,
                ensure_ascii=False,
            )
        elif self.endpoint == "update_employee":
            self.request_body = json.dumps(
                {
                    "firstName": "Ali",
                    "lastName": "Haydar",
                    "birthDate": "1999-01-01",
                    "identityNumber": self.employee_identity_number,
                    "email": "ahb123457@gmail.com",
                    "employeeType": "Normal Çalışan",
                    "gender": 1,
                    "phoneNumber": "5555555555",
                    "intercom": "",
                    "role": 1,
                    "workplace": None,
                },
                indent=4,
                ensure_ascii=False,
            )
        else:
            self.request_body = ""

    @api.onchange('request_headers')
    def _onchange_request_headers(self):
        if self.request_headers:
            try:
                # JSON'ı otomatik olarak düzenle
                parsed = json.loads(self.request_headers)
                self.request_headers = json.dumps(parsed, indent=4, ensure_ascii=False)
            except json.JSONDecodeError as e:
                # Geçersiz JSON olduğunda hata fırlat
                raise UserError(f"Request Headers alanında geçersiz JSON formatı: {e}")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'request_headers' in vals and vals['request_headers']:
                try:
                    parsed = json.loads(vals['request_headers'])
                    vals['request_headers'] = json.dumps(parsed, indent=4, ensure_ascii=False)
                except json.JSONDecodeError as e:
                    # Geçersiz JSON olduğunda hata fırlat
                    raise UserError(f"Request Headers alanında geçersiz JSON formatı: {e}")
            
            # request_body için de create/write sırasında JSON doğrulama ve biçimlendirme
            if 'request_body' in vals and vals['request_body']:
                try:
                    parsed = json.loads(vals['request_body'])
                    vals['request_body'] = json.dumps(parsed, indent=4, ensure_ascii=False)
                except json.JSONDecodeError as e:
                    raise UserError(f"Request Body alanında geçersiz JSON formatı: {e}")
        return super().create(vals_list)

    def write(self, vals):
        if 'request_headers' in vals and vals['request_headers']:
            try:
                parsed = json.loads(vals['request_headers'])
                vals['request_headers'] = json.dumps(parsed, indent=4, ensure_ascii=False)
            except json.JSONDecodeError as e:
                # Geçersiz JSON olduğunda hata fırlat
                raise UserError(f"Request Headers alanında geçersiz JSON formatı: {e}")
        
        # request_body için de create/write sırasında JSON doğrulama ve biçimlendirme
        if 'request_body' in vals and vals['request_body']:
            try:
                parsed = json.loads(vals['request_body'])
                vals['request_body'] = json.dumps(parsed, indent=4, ensure_ascii=False)
            except json.JSONDecodeError as e:
                raise UserError(f"Request Body alanında geçersiz JSON formatı: {e}")
        return super().write(vals)

    def execute_request(self):
        for record in self:
            if not record.request_url:
                raise UserError("Request URL is not set. Please check the endpoint and parameters.")

            try:
                # Başlıkları her zaman düzgün JSON olarak yükle
                headers = json.loads(record.request_headers)
            except json.JSONDecodeError as e:
                raise UserError(f"Invalid JSON in Request Headers: {e}")

            # Temel kimlik doğrulama
            credentials = f"{record.username}:{record.password}"
            auth_token = base64.b64encode(credentials.encode()).decode()
            headers["Authorization"] = f"Basic {auth_token}"

            # İstek kimliği ve zaman damgası ekle
            headers.update({
                "X-Request-ID": str(uuid.uuid4()),
                "X-Request-Timestamp": datetime.now(timezone("UTC")).isoformat()
            })

            method = record.request_method
            
            # JSON doğrulama ve içerik tipi ayarlama
            request_data = None
            if method in ("POST", "PUT") and record.request_body:
                try:
                    # JSON'ı doğrula ve düzgün biçimlendir (kayıt sırasında zaten yapılıyor ama burada son kontrol)
                    parsed_body = json.loads(record.request_body)
                    request_data = json.dumps(parsed_body, ensure_ascii=False)
                    
                    # Eğer kullanıcı Content-Type belirtmemişse otomatik ekle
                    if "Content-Type" not in headers:
                        headers["Content-Type"] = "application/json"
                except json.JSONDecodeError as e:
                    raise UserError(f"Invalid JSON in Request Body: {e}")

            try:
                # İstekleri gönder
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

                # Yanıtı işle
                record.response_status_code = response.status_code

                try:
                    # Yanıtı düzgün biçimlendirilmiş JSON olarak kaydet
                    parsed_response = json.loads(response.text)
                    record.response_body = json.dumps(
                        parsed_response, 
                        indent=4, 
                        ensure_ascii=False,
                        sort_keys=True
                    )
                except json.JSONDecodeError:
                    # JSON olmayan yanıtları olduğu gibi kaydet
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
