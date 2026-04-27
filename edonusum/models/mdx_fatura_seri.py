# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
import json

class MdxFaturaSeri(models.Model):
    _name = 'mdx.fatura.seri'
    _description = 'Fatura Seri'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Ad', required=True, store=True, tracking=True)
    code = fields.Char(string='Kod', required=True, store=True, tracking=True)
    description = fields.Text(string='Açıklama', store=True, tracking=True)
    ebelge_turu_id = fields.Many2one('mdx.ebelge.turu', string='E-Belge Türü', store=True, tracking=True)
    last_used_date = fields.Date(string='Son Kullanılan Tarih', store=True, tracking=True)
    index = fields.Integer(string='Sıra No', default=0, store=True, tracking=True)
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company, tracking=True)
    active = fields.Boolean(string='Aktif', default=True, tracking=True)

    # Aynı listede aynı kodun olmaması için kontrol yapılır.
    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Kod alanı benzersiz olmalıdır!'),
    ]

     # TODO : BURAYA BAKILACAK !!!
    # @api.depends('ebelge_turu_id')
    # def _compute_ebelge_turu_id(self):
    #     for record in self:
    #         if record.ebelge_turu_id:
    #             record.ebelge_turu_id = record.ebelge_turu_id.id
    #         else:
    #             # Bu fatura serisine ilk sahip olan faturanın efatura_turu_id'sini al
    #             record.ebelge_turu_id = self.env['account.move'].search([
    #                 ('fatura_seri_id', '=', record.id),
    #                 ('efatura_turu_id', '!=', False)
    #             ], limit=1).sorted('create_date', reverse=True).efatura_turu_id.id if record.ebelge_turu_id else False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code') and self.env['mdx.fatura.seri'].search([('code', '=', vals.get('code'))]):
                raise UserError('Kod alanı benzersiz olmalıdır!')

        return super(MdxFaturaSeri, self).create(vals_list)
    
    @api.onchange('code', 'name')
    def _onchange_code_name(self):
        if self.code and self.name:
            self.name = self.code
        elif self.name and not self.code:
            self.name = self.name
        elif not self.name and self.code:
            self.name = self.code
