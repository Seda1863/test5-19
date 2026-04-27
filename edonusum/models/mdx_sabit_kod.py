# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
import json

class MdxSabitKod(models.Model):
    _name = 'mdx.sabit.kod'
    _description = 'Sabit Kod'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Ad', compute='_compute_name', store=True, readonly=False, tracking=True)
    code = fields.Char(string='Kod', compute='_compute_code', store=True, readonly=False, tracking=True)
    liste_tipi_id = fields.Many2one('mdx.kod.liste.tipi', related='liste_id.liste_tipi_id', string='Kod Liste Tipi', readonly=True, store=True)
    liste_alt_tipi_id = fields.Many2one('mdx.kod.liste.alt.tipi', related='liste_id.liste_alt_tipi_id', string='Kod Liste Alt Tipi', readonly=True, store=True)
    tevkifat_orani = fields.Float(string='Tevkifat Oranı', digits=(16, 2), default=0.0, compute='_compute_tevkifat_orani', store=True, readonly=False, tracking=True)
    vergi_kisaltma = fields.Char(string='Vergi Kısaltma', store=True, readonly=False, tracking=True)
    ebelge_turu_id = fields.Many2one('mdx.ebelge.turu', string='E-Belge Türü', related='liste_id.ebelge_turu_id', readonly=True, store=True)
    gelen_giden = fields.Selection(
        related='liste_id.gelen_giden', 
        string='Gelen/Giden', 
        readonly=True, 
        store=True
    )

    efinans_kod = fields.Char(string='E-Finans Kodu', store=True, readonly=False, tracking=True)
    # prozon_kod = fields.Char(string='Prozon Kodu', store=True, readonly=False, tracking=True)
    description = fields.Text(string='Açıklama', store=True, readonly=False, tracking=True)
    liste_id = fields.Many2one('mdx.kod.listesi', string='Kod Listesi', required=True, store=True, readonly=False, tracking=True)
    
    active = fields.Boolean(string='Aktif', default=True, tracking=True)

    # Aynı listede aynı kodun olmaması için kontrol yapılır.
    _sql_constraints = [
        ('code_uniq', 'unique(code, liste_id)', 'Kod alanı benzersiz olmalıdır!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code') and self.env['mdx.sabit.kod'].search([
                ('code', '=', vals.get('code')),
                ('liste_id', '=', vals.get('liste_id'))
            ]):
                raise UserError('Kod alanı ve Liste kombinasyonu benzersiz olmalıdır!')
        return super(MdxSabitKod, self).create(vals_list)
    
    @api.depends('efinans_kod', 'description')
    def _compute_name(self):
        for rec in self:
            if rec.efinans_kod and rec.description:
                rec.name = rec.efinans_kod+" - "+rec.description

    @api.depends('efinans_kod', 'liste_id')
    def _compute_code(self):
        for rec in self:
            if rec.efinans_kod and rec.liste_id:
                rec.code = rec.liste_id.code+"_"+rec.efinans_kod