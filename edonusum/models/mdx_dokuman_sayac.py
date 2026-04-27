# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
import json

class MdxDokumanSayac(models.Model):
    _name = 'mdx.dokuman.sayac'
    _description = 'Doküman Sayac'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    code = fields.Char(string='Kod', required=True, store=True, tracking=True)
    name = fields.Char(string='Ad', required=True, store=True, tracking=True)
    description = fields.Text(string='Açıklama', store=True, tracking=True)
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company, store=True, tracking=True)
    gonderilecek_sonraki_sira_no = fields.Integer(string='Gönderilecek Sonraki Sıra No', default=0, store=True, tracking=True)
    last_used_date = fields.Date(string='Son Kullanılan Tarih', store=True, tracking=True)
    active = fields.Boolean(string='Aktif', default=True, store=True, tracking=True)

    # Aynı listede aynı kodun olmaması için kontrol yapılır.
    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Ad alanı benzersiz olmalıdır!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        """
        Batch işlemlerini destekleyen create metodu.
        """
        for vals in vals_list:
            if vals.get('name') and self.env['mdx.dokuman.sayac'].search([('name', '=', vals.get('name'))]):
                raise UserError('Ad alanı benzersiz olmalıdır!')
        return super(MdxDokumanSayac, self).create(vals_list)
    
    @api.depends('name')
    def _compute_gelen_giden(self):
        if self.name:
            if 'gelen' in self.name.lower():
                self.gelen_giden = 'Gelen'
            elif 'giden' in self.name.lower():
                self.gelen_giden = 'Giden'
            else:
                self.gelen_giden = False

    @api.depends('name')
    def _compute_ebelge_turu_id(self):
        for record in self:
            if record.name:
                if 'fatura' in record.name.lower():
                    record.ebelge_turu_id = record.env['mdx.ebelge.turu'].search([('code', 'like', 'FAT')], limit=1).id
                elif 'irsaliye' in record.name.lower():
                    record.ebelge_turu_id = record.env['mdx.ebelge.turu'].search([
                        ('code', 'like', 'IRS'),
                        ('ebelge_turu_origin_id', '=', False)], limit=1).id
                else:
                    record.ebelge_turu_id = False

        
        