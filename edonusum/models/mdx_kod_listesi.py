# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
import json

import logging

_logger = logging.getLogger(__name__)

class MdxKodListesi(models.Model):
    _name = 'mdx.kod.listesi'
    _description = 'Kod Listesi'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Ad', required=True, store=True, tracking=True)
    code = fields.Char(string='Kod', required=True, store=True, tracking=True)
    description = fields.Text(string='Açıklama', store=True, tracking=True)
    liste_tipi_id = fields.Many2one('mdx.kod.liste.tipi', string='Kod Liste Tipi', required=True, store=True, tracking=True)
    liste_alt_tipi_id = fields.Many2one('mdx.kod.liste.alt.tipi', string='Kod Liste Alt Tipi', store=True, tracking=True)
    active = fields.Boolean(string='Aktif', default=True, store=True, tracking=True)
    sabit_kod_ids = fields.One2many('mdx.sabit.kod', 'liste_id', string='Sabit Kodlar', domain=[('active', '=', True)], store=True)
    ubltr_custom = fields.Selection([('UBLTR', 'UBLTR'), ('Custom', 'Custom')], string='UBLTR/Custom', default='UBLTR', store=True, tracking=True)
    # E-Belge Statü Listesi İçin
    ebelge_turu_id = fields.Many2one('mdx.ebelge.turu', string='E-Belge Türü', compute='_compute_ebelge_turu_id', store=True, readonly=False, domain=[('code', 'in', ['EFATURA', 'EIRSALIYE'])], tracking=True)
    gelen_giden = fields.Selection([('Gelen', 'Gelen'), ('Giden', 'Giden')], string='Gelen/Giden', compute='_compute_gelen_giden', store=True, readonly=False, tracking=True)

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Kod alanı benzersiz olmalıdır!'),
    ]
    
    @api.depends('name')
    def _compute_gelen_giden(self):
        for record in self:  # Her kaydı tek tek kontrol et
            if record.name:
                if 'gelen' in record.name.lower():
                    record.gelen_giden = 'Gelen'
                elif 'giden' in record.name.lower():
                    record.gelen_giden = 'Giden'
                else:
                    record.gelen_giden = False

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

    @api.onchange('liste_tipi_id')
    def _onchange_liste_tipi_id(self):
        if self.liste_tipi_id.code != 'EBELGESTATU':
            self.ebelge_turu_id = False
            self.gelen_giden = False