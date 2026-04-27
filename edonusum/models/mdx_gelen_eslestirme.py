# -*- coding: utf-8 -*-

import base64
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import xml.etree.ElementTree as ET

from .mdx_utility_mixin import MdxUtilityMixin

class MdxGelenEslestirme(models.Model):
    _name = 'mdx.gelen.eslestirme'
    _description = 'Gelen Fatura Hizmet Eşleştirme'
    _order = 'matched_count desc'

    name = fields.Char(string='Eşleştirme No', required=True, copy=False, readonly=True, index=True, default=lambda self: _('Yeni'))
    # service_name = fields.Char(string='Hizmet Adı', required=True)
    # service_code = fields.Char(string='Hizmet Kodu', required=True)
    supplier_service_name = fields.Char(string='Tedarikçi Hizmet Adı', required=True, store= True)
    supplier_service_code = fields.Char(string='Tedarikçi Hizmet Kodu', required=True, store=True)
    account_id = fields.Many2one('account.account', string='Hesap', required=True, store=True)
    supplier_id = fields.Many2one('res.partner', string='Tedarikçi', required=True, domain=[('is_supplier', '=', True),('parent_id', '=', False)], store= True)
    company_id = fields.Many2one('res.company', string='Şirket', required=True, default=lambda self: self.env.company, store= True)
    active = fields.Boolean(string='Aktif', default=True)

    first_matched_gelen_fatura_id = fields.Many2one('mdx.gelen.fatura', string='İlk Eşleştirildiği Belge', readonly=True, store=True)
    last_matched_gelen_fatura_id = fields.Many2one('mdx.gelen.fatura', string='Son Eşleştirildiği Belge', readonly=True, store=True)
    first_matched_gelen_fatura_line_id = fields.Many2one('mdx.gelen.fatura.line', string='İlk Eşleştirildiği Belge Satırı', readonly=True, store=True)
    last_matched_gelen_fatura_line_id = fields.Many2one('mdx.gelen.fatura.line', string='Son Eşleştirildiği Belge Satırı', readonly=True, store=True)
    matched_count = fields.Integer(string='Eşleştirme Sayısı', compute='_compute_matched_count', store=True)
    manually_created_from_gelen_fatura_line_id = fields.Many2one('mdx.gelen.fatura.line', string='Fatura Satırı', help="Bu hizmet, ilgili fatura satırından manuel olarak oluşturulduysa burası dolu olur.", store= True)

    @api.depends('first_matched_gelen_fatura_id', 'last_matched_gelen_fatura_id')
    def _compute_matched_count(self):
        for record in self:
            record.matched_count = self.env['mdx.gelen.fatura.line'].search_count([('eslestirme_id', '=', record.id)])

    @api.model
    def create(self, vals):
        service = super(MdxGelenEslestirme, self).create(vals)
        if service.manually_created_from_gelen_fatura_line_id:
            # İlgili fatura satırını alalım
            fatura_line = service.manually_created_from_gelen_fatura_line_id
            # Fatura satırındaki hizmet alanını güncelleyelim
            fatura_line.write({
                'eslestirme_id': service.id,
                'create_service_card': False,
                'product_id': False,
                'create_product': False,
                'create_supplierinfo': False,
            })

            if hasattr(fatura_line, 'supplierinfo_id'):
                fatura_line.write({
                    'supplierinfo_id': fatura_line.supplierinfo_id.id,
                    'create_supplierinfo': False,
                })
        return service
    

    

   