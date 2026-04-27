# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
import json

class MdxEbelgeTuru(models.Model):
    _name = 'mdx.ebelge.turu'
    _description = 'E-Belge Türü'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Ad', required=True, store=True, tracking=True)
    code = fields.Char(string='Kod', required=True, store=True, tracking=True)
    description = fields.Text(string='Açıklama', store=True, tracking=True)
    belge_cinsi_id = fields.Many2one('mdx.belge.cinsi', string='Belge Cinsi', store=True, tracking=True)
    
    # YENİ EKLENEN ALAN: XSLT Dosyası Seçimi
    xslt_attachment_id = fields.Binary(string='XSLT Dosyası', help='Bu alanda, e-belge türü için kullanılacak XSLT dosyasını ekleyebilirsiniz. XSLT dosyası, XML verilerini istenilen formata dönüştürmek için kullanılır.')
    
    ebelge_turu_origin_id = fields.Many2one(
        'mdx.ebelge.turu',
        string='E-Belge Türü (Origin)',
        domain="[('ebelge_turu_origin_id', '=', False)]",
        compute='_compute_ebelge_turu_origin_id',
        store=True,
        readonly=False,
        tracking=True
    )
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
            if vals.get('code') and self.env['mdx.ebelge.turu'].search([('code', '=', vals.get('code'))]):
                raise UserError('Kod alanı benzersiz olmalıdır!')
        return super(MdxEbelgeTuru, self).create(vals_list)
    
    @api.depends('code')
    def _compute_ebelge_turu_origin_id(self):
        for rec in self:
            if rec.code:
                origin_record = self.search([
                    ('code', '=', rec.code),
                    ('ebelge_turu_origin_id', '=', False)
                ], limit=1)
                rec.ebelge_turu_origin_id = origin_record.id if origin_record else False
            else:
                rec.ebelge_turu_origin_id = False