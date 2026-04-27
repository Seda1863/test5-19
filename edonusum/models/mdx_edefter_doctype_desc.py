# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
import json

class MdxEDefterDoctypeDesc(models.Model):
    _name = 'mdx.edefter.doctype.desc'
    _description = 'E-Defter Belge Tipi Açıklaması'

    name = fields.Char(string='Ad', required=True, store=True)
    description = fields.Text(string='Açıklama', store=True)
    active = fields.Boolean(string='Aktif', default=True)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Kod alanı benzersiz olmalıdır!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        """
        Batch işlemleri destekleyen create metodu.
        """
        for vals in vals_list:
            if vals.get('name') and self.env['mdx.edefter.doctype.desc'].search([('name', '=', vals.get('name'))]):
                raise UserError('Name alanı benzersiz olmalıdır!')
        return super(MdxEDefterDoctypeDesc, self).create(vals_list)
   