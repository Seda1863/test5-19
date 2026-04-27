# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
import json

class MdxWebService(models.Model):
    _name = 'mdx.web.service'
    _description = 'Web Servis'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Ad', required=True, tracking=True)
    description = fields.Text(string='Açıklama', tracking=True)
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company, tracking=True)
    url = fields.Char(string='URL', tracking=True)
    username = fields.Char(string='Kullanıcı Adı', tracking=True)
    password = fields.Char(string='Şifre', tracking=True)
    vkn = fields.Char(string='VKN', tracking=True)
    erp_code = fields.Char(string='ERP Kodu', tracking=True)
    token = fields.Char(string='Token', tracking=True)
    api_get_transactions = fields.Char(string='Get Transactions', tracking=True)
    api_put_status = fields.Char(string='Put Status', tracking=True)
    accept = fields.Char(string='Accept', tracking=True)
    content_type = fields.Char(string='Content Type', tracking=True)
    api_post_cari = fields.Char(string='Post Cari', tracking=True)
    api_get_account_plan_codes = fields.Char(string='Get Account Plan Codes', tracking=True)
    active = fields.Boolean(string='Aktif', default=True, tracking=True)