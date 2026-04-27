# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
import json

class MdxEbelgeSenaryo(models.Model):
    _name = 'mdx.ebelge.senaryo'
    _description = 'E-Belge Senaryo'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Ad', required=True, store=True, tracking=True)
    code = fields.Char(string='Kod', required=True, store=True, tracking=True)
    description = fields.Text(string='Açıklama', store=True, tracking=True)
    ebelge_turu_ids = fields.Many2many(comodel_name='mdx.ebelge.turu', string='Geçerli Olduğu E-Belge Türleri', domain=[('active', '=', True)], readonly=False, store=True, tracking=True)
    active = fields.Boolean(string='Aktif', default=True, store=True, tracking=True)