# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def init(self):
        # Keep DB schema resilient on environments where code is deployed
        # before module upgrade is executed.
        self._cr.execute(
            "ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS dbs_risk_control varchar"
        )
        self._cr.execute(
            "UPDATE res_partner SET dbs_risk_control = 'continue' WHERE dbs_risk_control IS NULL"
        )

    company_currency_id = fields.Many2one(
        'res.currency',
        string='Sirket Para Birimi',
        related='company_id.currency_id',
        readonly=True,
    )

    dbs_enabled = fields.Boolean(string='DBS Aktif')
    dbs_contract_id = fields.Many2one('dbs.contract', string='DBS Sozlesmesi')
    dbs_customer_code = fields.Char(string='DBS Musteri Kodu')
    dbs_limit = fields.Monetary(string='DBS Ic Limit', currency_field='company_currency_id')
    dbs_status = fields.Selection([
        ('active', 'Aktif'),
        ('suspended', 'Askida'),
        ('closed', 'Kapali'),
    ], string='DBS Durumu', default='active', required=True)
    dbs_risk_control = fields.Selection([
        ('continue', 'Isleme Devam Edilecek'),
        ('warn', 'Kullanici Uyarilacak'),
        ('block', 'Islem Durdurulacak'),
    ], string='DBS Risk Kontrol', default='continue', required=True)
    dbs_limit_available = fields.Monetary(
        string='Kullanilabilir DBS Limit',
        currency_field='company_currency_id',
        compute='_compute_dbs_limit_available',
    )
    dbs_used_amount = fields.Monetary(
        string='Kullanilan DBS Limit',
        currency_field='company_currency_id',
        compute='_compute_dbs_limit_usage',
    )
    dbs_over_amount = fields.Monetary(
        string='Limit Asim Tutarı',
        currency_field='company_currency_id',
        compute='_compute_dbs_limit_usage',
    )
    dbs_bank_id = fields.Many2one(related='commercial_partner_id.dbs_contract_id.bank_id', readonly=True, string='Banka')
    dbs_bank_account_id = fields.Many2one(related='commercial_partner_id.dbs_contract_id.bank_account_id', readonly=True, string='Banka Hesabi (IBAN)')
    dbs_settlement_bank_journal_id = fields.Many2one(related='commercial_partner_id.dbs_contract_id.settlement_bank_journal_id', readonly=True, string='Tahsilat Yevmiyesi')
    dbs_status_summary = fields.Text(compute='_compute_dbs_status_summary', string='DBS Durum Özeti')
    dbs_contract_count = fields.Integer(compute='_compute_dbs_related_counts', string='DBS Sozlesme Sayisi')
    dbs_batch_count = fields.Integer(compute='_compute_dbs_related_counts', string='DBS Toplu Islem Sayisi')
    dbs_line_count = fields.Integer(compute='_compute_dbs_related_counts', string='DBS Satir Sayisi')
    dbs_invoice_count = fields.Integer(compute='_compute_dbs_related_counts', string='DBS Fatura Sayisi')

    @api.depends('dbs_limit', 'dbs_enabled')
    def _compute_dbs_limit_available(self):
        for rec in self:
            if not rec.dbs_enabled or not rec.dbs_limit:
                rec.dbs_limit_available = rec.dbs_limit or 0.0
                continue

            open_lines = self.env['dbs.batch.line'].search([
                ('partner_id', '=', rec.id),
                ('state', 'in', ('to_send', 'sent', 'accepted')),
            ])
            rec.dbs_limit_available = (rec.dbs_limit or 0.0) - sum(open_lines.mapped('amount'))

    @api.depends('dbs_limit', 'dbs_enabled', 'dbs_limit_available')
    def _compute_dbs_limit_usage(self):
        for rec in self:
            used_amount = max((rec.dbs_limit or 0.0) - (rec.dbs_limit_available or 0.0), 0.0)
            rec.dbs_used_amount = used_amount
            rec.dbs_over_amount = max(used_amount - (rec.dbs_limit or 0.0), 0.0)

    @api.depends(
        'dbs_enabled', 'dbs_status', 'dbs_risk_control', 'dbs_contract_id', 'dbs_customer_code',
        'dbs_limit', 'dbs_limit_available', 'dbs_used_amount', 'dbs_over_amount',
        'dbs_bank_id', 'dbs_bank_account_id', 'dbs_settlement_bank_journal_id',
        'dbs_contract_count', 'dbs_batch_count', 'dbs_line_count', 'dbs_invoice_count',
    )
    def _compute_dbs_status_summary(self):
        for rec in self:
            status_label = dict(rec._fields['dbs_status'].selection).get(rec.dbs_status, rec.dbs_status or '-')
            risk_label = dict(rec._fields['dbs_risk_control'].selection).get(rec.dbs_risk_control, rec.dbs_risk_control or '-')
            bank_name = rec.dbs_bank_id.display_name or '-'
            bank_account = rec.dbs_bank_account_id.acc_number or '-'
            journal_name = rec.dbs_settlement_bank_journal_id.display_name or '-'
            contract_name = rec.dbs_contract_id.display_name or '-'

            rec.dbs_status_summary = '\n'.join([
                f'DBS Aktif: {"Evet" if rec.dbs_enabled else "Hayır"}',
                f'DBS Durumu: {status_label}',
                f'DBS Risk Kontrol: {risk_label}',
                f'Sözleşme: {contract_name}',
                f'DBS Müşteri Kodu: {rec.dbs_customer_code or "-"}',
                f'Banka: {bank_name}',
                f'IBAN: {bank_account}',
                f'Tahsilat Yevmiyesi: {journal_name}',
                f'Limit: {rec.dbs_limit or 0.0:.2f}',
                f'Kullanılan Limit: {rec.dbs_used_amount or 0.0:.2f}',
                f'Kullanılabilir Limit: {rec.dbs_limit_available or 0.0:.2f}',
                f'Limit Aşımı: {rec.dbs_over_amount or 0.0:.2f}',
                f'DBS Sözleşme Sayısı: {rec.dbs_contract_count}',
                f'DBS Toplu İşlem Sayısı: {rec.dbs_batch_count}',
                f'DBS Satır Sayısı: {rec.dbs_line_count}',
                f'DBS Fatura Sayısı: {rec.dbs_invoice_count}',
            ])

    @api.depends('dbs_enabled', 'dbs_contract_id', 'dbs_limit', 'dbs_status')
    def _compute_dbs_related_counts(self):
        batch_model = self.env['dbs.batch']
        line_model = self.env['dbs.batch.line']
        for rec in self:
            contract = rec.commercial_partner_id.dbs_contract_id
            rec.dbs_contract_count = 1 if contract else 0
            rec.dbs_batch_count = batch_model.search_count([('contract_id', '=', contract.id)]) if contract else 0
            rec.dbs_line_count = line_model.search_count([('partner_id', '=', rec.id)])
            rec.dbs_invoice_count = len(line_model.search([('partner_id', '=', rec.id)]).mapped('move_id'))

    @api.onchange('dbs_status')
    def _onchange_dbs_status(self):
        for rec in self:
            if rec.dbs_status in ('suspended', 'closed'):
                rec.dbs_enabled = False

    @api.onchange('dbs_enabled')
    def _onchange_dbs_enabled(self):
        for rec in self:
            if rec.dbs_enabled and rec.dbs_status in ('suspended', 'closed'):
                rec.dbs_status = 'active'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('dbs_status') in ('suspended', 'closed'):
                vals['dbs_enabled'] = False
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        # Durum askıya/kapalıya çekilince aktif işaretini kaldır
        if vals.get('dbs_status') in ('suspended', 'closed'):
            vals['dbs_enabled'] = False
        # DBS Aktif işaretlenince durumu otomatik Aktif yap
        elif vals.get('dbs_enabled'):
            vals.setdefault('dbs_status', 'active')
        return super().write(vals)

    def action_open_dbs_contract(self):
        self.ensure_one()
        contract = self.commercial_partner_id.dbs_contract_id
        if not contract:
            raise UserError(_('Bu musteriye bagli DBS sozlesmesi yok.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('DBS Sozlesmesi'),
            'res_model': 'dbs.contract',
            'view_mode': 'form',
            'res_id': contract.id,
            'target': 'current',
        }

    def action_open_dbs_batches(self):
        self.ensure_one()
        contract = self.commercial_partner_id.dbs_contract_id
        domain = [('contract_id', '=', contract.id)] if contract else [('id', '=', 0)]
        return {
            'type': 'ir.actions.act_window',
            'name': _('DBS Toplu Islemler'),
            'res_model': 'dbs.batch',
            'view_mode': 'list,form',
            'domain': domain,
            'target': 'current',
        }

    def action_open_dbs_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('DBS Faturalari'),
            'res_model': 'dbs.batch.line',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'target': 'current',
        }

    def action_open_dbs_invoices(self):
        self.ensure_one()
        invoice_ids = self.env['dbs.batch.line'].search([('partner_id', '=', self.id)]).mapped('move_id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('DBS Faturalari'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', invoice_ids)],
            'target': 'current',
        }

    def _get_dbs_report_payload(self):
        self.ensure_one()
        contract = self.commercial_partner_id.dbs_contract_id
        batch_model = self.env['dbs.batch']
        line_model = self.env['dbs.batch.line']
        batches = batch_model.search([('contract_id', '=', contract.id)], order='date desc, id desc', limit=10) if contract else batch_model.browse()
        lines = line_model.search([('partner_id', '=', self.id)], order='id desc', limit=10)
        invoices = lines.mapped('move_id')
        return {
            'contract': contract,
            'batches': batches,
            'lines': lines,
            'invoices': invoices,
            'bank_name': self.dbs_bank_id.display_name or '-',
            'bank_account': self.dbs_bank_account_id.acc_number or '-',
            'journal_name': self.dbs_settlement_bank_journal_id.display_name or '-',
            'summary': self.dbs_status_summary or '',
            'used_amount': self.dbs_used_amount or 0.0,
            'available_amount': self.dbs_limit_available or 0.0,
            'over_amount': self.dbs_over_amount or 0.0,
        }

    def action_print_dbs_report(self):
        self.ensure_one()
        return self.env.ref('account_dbs_tr.action_report_dbs_partner').report_action(self)
