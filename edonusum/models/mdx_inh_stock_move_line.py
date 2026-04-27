# -*- coding: utf-8 -*-

# TODO: Geliştirmenin son aşamasında, logging_field1, logging_field2 ve logging_field3 alanları kaldırılacak
# TODO: fatura_aciklama sahasına özel karakter kontrolü eklenecek, özel karakter varsa hata mesajı verilecek
# TODO: fatura_no alanı ve uuid dolu ise, fatura gönderme butonu kaldırılacak.

import datetime
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
import xml.etree.ElementTree as ET

from .mdx_utility_mixin import MdxUtilityMixin

class MdxInhStockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    # olcu_birim_id = fields.Many2one('mdx.sabit.kod', string='Ölçü Birimi', domain=[('liste_tipi_id.code', '=', 'OLCUBIRIM')], store=True)
    gelen_irsaliye_line_id = fields.Many2one('mdx.gelen.irsaliye.line', string='Gelen İrsaliye Satırı', store=True)
    
    # @api.model
    # def create(self, vals):
    #     if 'gelen_irsaliye_line_id' in vals:
    #         gelen_irsaliye_line_id = vals['gelen_irsaliye_line_id']
    #         gelen_irsaliye_line = self.env['mdx.gelen.irsaliye.line'].search([('id', '=', gelen_irsaliye_line_id)])
    #         if gelen_irsaliye_line.ref_po_line_id:
    #             vals['move_id'].purchase_line_id = gelen_irsaliye_line.ref_po_line_id
    #     return super(MdxInhStockMoveLine, self).create(vals)