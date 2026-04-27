# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
import json

class MdxKodListeAltTipi(models.Model):
    _name = 'mdx.kod.liste.alt.tipi'
    _description = 'Kod Liste Alt Tipi'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    code = fields.Char(string='Kod', required=True, store=True, tracking=True)
    name = fields.Char(string='Ad', required=True, store=True, tracking=True)
    description = fields.Text(string='Açıklama', store=True, tracking=True)
    active = fields.Boolean(string='Aktif', default=True, store=True, tracking=True)
    kod_liste_tipi_id = fields.Many2one('mdx.kod.liste.tipi', string='Kod Liste Tipi', required=True, store=True, tracking=True)