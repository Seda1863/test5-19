# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError

class MdxWorkType(models.Model):
    _name = 'mdx.work.type'
    _description = 'Work Type'

    name = fields.Char(string='Name', required=True)
    description = fields.Text(string='Description')
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company, readonly=True)
