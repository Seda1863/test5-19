# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
import json

class MdxKodListeTipi(models.Model):
    _name = 'mdx.kod.liste.tipi'
    _description = 'Kod Liste Tipi'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    code = fields.Char(string='Kod', required=True, store=True, tracking=True)
    name = fields.Char(string='Ad', required=True, store=True, tracking=True)
    description = fields.Text(string='Açıklama', store=True, tracking=True)
    active = fields.Boolean(string='Aktif', default=True, store=True, tracking=True)
    kod_liste_alt_tipi_ids = fields.One2many('mdx.kod.liste.alt.tipi', 'kod_liste_tipi_id', string='Kod Liste Alt Tipleri', domain=[('active', '=', True)], store=True)