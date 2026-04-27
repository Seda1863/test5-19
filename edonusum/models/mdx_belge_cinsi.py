# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
import json

# Fatura, İrsaliye

class MdxBelgeCinsi(models.Model):
    _name = 'mdx.belge.cinsi'
    _description = 'Belge Cinsi'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    code = fields.Char(string='Kod', required=True, store=True, tracking=True)
    name = fields.Char(string='Ad', required=True, store=True, tracking=True)
    description = fields.Text(string='Açıklama', store=True, tracking=True)
    active = fields.Boolean(string='Aktif', default=True, store=True, tracking=True)
