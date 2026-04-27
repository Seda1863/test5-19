# -*- coding: utf-8 -*-
from odoo import fields, models


class DbsMessageLog(models.Model):
    _name = 'dbs.message.log'
    _description = 'DBS Message Log'
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Baslik', required=True)
    level = fields.Selection([
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ], default='info', required=True)
    model = fields.Char(string='Model')
    res_id = fields.Integer(string='Kayit ID')
    batch_id = fields.Many2one('dbs.batch', string='DBS Batch')
    contract_id = fields.Many2one('dbs.contract', string='DBS Sozlesme')
    message = fields.Text(string='Mesaj', required=True)
