# -*- coding: utf-8 -*-
from odoo import models, fields, api


class BankGuaranteeLimit(models.Model):
    _name = 'bank.guarantee.limit'
    _description = 'Banka Teminat Limiti'
    _order = 'bank_partner_id'
    _rec_name = 'bank_partner_id'

    company_id = fields.Many2one(
        'res.company',
        string='Şirket',
        default=lambda self: self.env.company,
        required=True,
    )
    bank_partner_id = fields.Many2one(
        'res.partner',
        string='Banka',
        required=True,
        domain="[('is_company', '=', True)]",
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Para Birimi',
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    limit_amount = fields.Monetary(
        string='Toplam Limit',
        required=True,
        currency_field='currency_id',
    )
    used_amount = fields.Monetary(
        string='Kullanılan',
        compute='_compute_amounts',
        store=False,
        currency_field='currency_id',
    )
    available_amount = fields.Monetary(
        string='Kullanılabilir',
        compute='_compute_amounts',
        store=False,
        currency_field='currency_id',
    )
    letter_count = fields.Integer(
        string='Aktif Mektup Sayısı',
        compute='_compute_amounts',
        store=False,
    )

    _sql_constraints = [
        ('bank_company_uniq', 'unique(bank_partner_id, company_id)',
         'Her banka için şirket başına tek limit kaydı olabilir.'),
    ]

    @api.depends('limit_amount')
    def _compute_amounts(self):
        for rec in self:
            active_letters = self.env['guarantee.letter'].search([
                ('bank_partner_id', '=', rec.bank_partner_id.id),
                ('company_id', '=', rec.company_id.id),
                ('state', 'in', ('active', 'return_requested')),
            ])
            used_amount = 0.0
            for letter in active_letters:
                letter_currency = letter.currency_id or rec.company_id.currency_id
                rate_date = letter.issue_date or fields.Date.context_today(letter)
                used_amount += letter_currency._convert(
                    letter.amount,
                    rec.currency_id,
                    rec.company_id,
                    rate_date,
                )
            rec.used_amount = rec.currency_id.round(used_amount)
            rec.available_amount = rec.limit_amount - rec.used_amount
            rec.letter_count = len(active_letters)

    def action_view_letters(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Teminat Mektupları',
            'res_model': 'guarantee.letter',
            'view_mode': 'list,form',
            'domain': [
                ('bank_partner_id', '=', self.bank_partner_id.id),
                ('company_id', '=', self.company_id.id),
                ('state', 'in', ('active', 'return_requested')),
            ],
        }
