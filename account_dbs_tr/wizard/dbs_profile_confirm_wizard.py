# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DbsProfileConfirmWizard(models.TransientModel):
    _name = 'dbs.profile.confirm.wizard'
    _description = 'DBS Profile Confirm Wizard'

    move_id = fields.Many2one('account.move', required=True, readonly=True)
    partner_id = fields.Many2one('res.partner', required=True, readonly=True)
    contract_id = fields.Many2one('dbs.contract', required=True, readonly=True)
    currency_id = fields.Many2one('res.currency', required=True, readonly=True)

    # Contract bilgileri (partner wizard'dan gösterilmek üzere)
    contract_bank_id = fields.Many2one(related='contract_id.bank_id', readonly=True, string='Banka')
    contract_bank_account_id = fields.Many2one(related='contract_id.bank_account_id', readonly=True, string='Banka Hesabi (IBAN)')
    contract_limit = fields.Monetary(related='contract_id.limit_amount', readonly=True, string='Sozlesme Limiti', currency_field='currency_id')
    contract_settlement_journal_id = fields.Many2one(related='contract_id.settlement_bank_journal_id', readonly=True, string='Yevmiye Adi')
    
    # Move'ün ilişkili yevmiye kayıtları (gösterim için)
    move_journal_entries_ids = fields.Many2many('account.move', compute='_compute_move_related_entries', string='Kaynak Fatura Yevmiyeleri')
    move_entry_count = fields.Integer(compute='_compute_move_related_entries', string='Yevmiye Sayisi')

    dbs_customer_code = fields.Char(string='DBS Musteri Kodu', required=True)
    dbs_limit = fields.Monetary(string='DBS Ic Limit', currency_field='currency_id', required=True)
    dbs_risk_control = fields.Selection([
        ('continue', 'Isleme Devam Edilecek'),
        ('warn', 'Kullanici Uyarilacak'),
        ('block', 'Islem Durdurulacak'),
    ], string='DBS Risk Kontrol', required=True, default='continue')
    dbs_used_amount = fields.Monetary(string='Kullanilan Limit', currency_field='currency_id', readonly=True)
    dbs_available_amount = fields.Monetary(string='Kullanilabilir Limit', currency_field='currency_id', readonly=True)
    dbs_required_amount = fields.Monetary(string='Gerekli Tutar', currency_field='currency_id', readonly=True)
    dbs_over_amount = fields.Monetary(string='Asim Tutar', currency_field='currency_id', readonly=True)
    dbs_risk_status = fields.Char(string='Risk Durumu', readonly=True)
    limit_exceeded_action = fields.Text(compute='_compute_limit_exceeded_action', string='Limit Asilinca Yapilacaklar')
    message = fields.Text(string='Bilgi', readonly=True)

    @api.depends('dbs_risk_control', 'dbs_over_amount')
    def _compute_limit_exceeded_action(self):
        for wiz in self:
            if wiz.dbs_over_amount <= 0:
                wiz.limit_exceeded_action = _('Limit asilmadi. Islem devam edecek.')
            else:
                risk_labels = dict(wiz._fields['dbs_risk_control'].selection)
                risk_text = risk_labels.get(wiz.dbs_risk_control, wiz.dbs_risk_control)
                over_amount_str = f"{wiz.dbs_over_amount:,.2f}"
                
                if wiz.dbs_risk_control == 'continue':
                    wiz.limit_exceeded_action = _('Limit %s TL asildi.\nSecilen Ayar: %s\nIslem devam edecek, fakat limit uyari logu tutulacak.') % (over_amount_str, risk_text)
                elif wiz.dbs_risk_control == 'warn':
                    wiz.limit_exceeded_action = _('Limit %s TL asildi.\nSecilen Ayar: %s\nMusteri uyarilacak, islem devam edecek.') % (over_amount_str, risk_text)
                elif wiz.dbs_risk_control == 'block':
                    wiz.limit_exceeded_action = _('Limit %s TL asildi.\nSecilen Ayar: %s\nIslem durdurulacak, musteri risk kontrol beklemede kalacak.') % (over_amount_str, risk_text)

    @api.depends('move_id')
    def _compute_move_related_entries(self):
        for wiz in self:
            # Move'ün kendi journal entry'sini göster ve ilişkili manual fee moves'ları
            move = wiz.move_id
            related_entries = self.env['account.move'].search([
                ('dbs_source_move_id', '=', move.id),
            ])
            # Kaynağın kendisini de ekle
            all_entries = (move | related_entries).sorted('date')
            wiz.move_journal_entries_ids = all_entries
            wiz.move_entry_count = len(all_entries)

    @api.onchange('dbs_limit', 'dbs_risk_control')
    def _onchange_dbs_limit_and_risk(self):
        for wiz in self:
            used_amount = sum(self.env['dbs.batch.line'].search([
                ('partner_id', '=', wiz.partner_id.id),
                ('contract_id', '=', wiz.contract_id.id),
                ('state', 'in', ('to_send', 'sent', 'accepted')),
            ]).mapped('amount'))
            required_amount = wiz.move_id.amount_residual or 0.0
            available_amount = (wiz.dbs_limit or 0.0) - used_amount
            over_amount = max(required_amount - available_amount, 0.0)
            wiz.dbs_used_amount = used_amount
            wiz.dbs_available_amount = available_amount
            wiz.dbs_required_amount = required_amount
            wiz.dbs_over_amount = over_amount
            if over_amount > 0:
                wiz.dbs_risk_status = _('Limit asildi')
            elif wiz.dbs_limit:
                wiz.dbs_risk_status = _('Limit yeterli')
            else:
                wiz.dbs_risk_status = _('Limit giriniz')

    def action_confirm(self):
        self.ensure_one()
        if not (self.dbs_customer_code or '').strip():
            raise UserError(_('DBS Musteri Kodu zorunludur.'))
        if (self.dbs_limit or 0.0) <= 0.0:
            raise UserError(_('DBS Ic Limit 0dan buyuk olmali.'))

        partner = self.partner_id.commercial_partner_id
        partner.write({
            'dbs_enabled': True,
            'dbs_status': 'active',
            'dbs_contract_id': self.contract_id.id,
            'dbs_customer_code': self.dbs_customer_code.strip(),
            'dbs_limit': self.dbs_limit,
            'dbs_risk_control': self.dbs_risk_control,
        })
        return self.move_id.with_context(dbs_profile_confirmed=True).action_send_to_dbs()

    def action_cancel(self):
        return {'type': 'ir.actions.act_window_close'}

    def action_open_contract(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('DBS Sozlesmesi'),
            'res_model': 'dbs.contract',
            'view_mode': 'form',
            'res_id': self.contract_id.id,
            'target': 'new',
        }

    def action_open_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fatura'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
            'target': 'new',
        }
