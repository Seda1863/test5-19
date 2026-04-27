# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
import json

class MdxEbelgeTipi(models.Model):
    _name = 'mdx.ebelge.tipi'
    _description = 'E-Belge Tipi'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Ad', required=True, store=True, tracking=True)
    code = fields.Char(string='Kod', required=True, store=True, tracking=True)
    description = fields.Text(string='Açıklama', store=True, tracking=True)
    belge_cinsi_id = fields.Many2one('mdx.belge.cinsi', string='Belge Cinsi', store=True, tracking=True)
    active = fields.Boolean(string='Aktif', default=True, tracking=True)

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Kod alanı benzersiz olmalıdır!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        """
        Batch işlemleri destekleyen create metodu.
        """
        for vals in vals_list:
            if vals.get('code') and self.env['mdx.ebelge.tipi'].search([('code', '=', vals.get('code'))]):
                raise UserError('Kod alanı benzersiz olmalıdır!')
        return super(MdxEbelgeTipi, self).create(vals_list)