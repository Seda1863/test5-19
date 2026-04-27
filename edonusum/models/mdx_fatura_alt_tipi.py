# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
import json

class MdxFaturaAltTipi(models.Model):
    _name = 'mdx.fatura.alt.tipi'
    _description = 'Fatura Alt Tipi'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Ad', required=True, store=True, tracking=True)
    code = fields.Char(string='Kod', required=True, store=True, tracking=True)
    description = fields.Text(string='Açıklama', store=True, tracking=True)
    fatura_tipi_id = fields.Many2one('mdx.ebelge.tipi', string='Fatura Tipi', domain=[('belge_cinsi_id.code', '=', 'FATURA')], store=True, tracking=True)
    active = fields.Boolean(string='Aktif', default=True, store=True, tracking=True)

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Kod alanı benzersiz olmalıdır!'),
    ]