# -*- coding: utf-8 -*-
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DbsContract(models.Model):
    _name = 'dbs.contract'
    _description = 'DBS Sozlesmesi'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Sozlesme', required=True, copy=False, default='New')
    company_id = fields.Many2one('res.company', string='Sirket', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', string='Para Birimi', required=True, default=lambda self: self.env.company.currency_id)
    contact_id = fields.Many2one('res.partner', string='Kontak', domain="[('is_company', '=', True)]")
    limit_amount = fields.Monetary(string='Limit Bilgisi', currency_field='currency_id')
    bank_id = fields.Many2one('res.bank', string='Banka')
    bank_account_id = fields.Many2one('res.partner.bank', string='Banka Hesabi (IBAN)', domain="[('bank_id', '=', bank_id)]")

    # Legacy field is kept for backward compatibility in adapters/logs.
    bank_partner_id = fields.Many2one('res.partner', string='Banka', domain="[('is_company', '=', True)]")
    settlement_bank_journal_id = fields.Many2one(
        'account.journal',
        string='Yevmiye Adi',
        required=True,
        domain="[('default_account_id.code', '=like', '102%')]",
    )
    settlement_debit_account_id = fields.Many2one(
        'account.account',
        string='Tahsilat Borc Hesabi',
        required=False,
        help='DBS tahsilat taslak yevmiyesinde borc satiri bu hesaba yazilir (orn: 102).',
    )
    settlement_credit_account_id = fields.Many2one(
        'account.account',
        string='Tahsilat Alacak Hesabi',
        required=False,
        help='DBS tahsilat taslak yevmiyesinde alacak satiri bu hesaba yazilir (orn: 120).',
    )
    commission_debit_account_id = fields.Many2one(
        'account.account',
        string='Komisyon Borc Hesabi',
        required=False,
        help='DBS komisyon taslak yevmiyesinde borc satiri bu hesaba yazilir (orn: 780).',
    )
    commission_credit_account_id = fields.Many2one(
        'account.account',
        string='Komisyon Alacak Hesabi',
        required=False,
        help='DBS komisyon taslak yevmiyesinde alacak satiri bu hesaba yazilir (orn: 102).',
    )
    suspense_account_id = fields.Many2one(
        'account.account',
        string='Ara Hesap',
        required=False,
        help='Banka entegrasyonu kullaniliyorsa, tahsilata gonderilen DBS takibi icin doldurulmali. Orn: 136',
    )

    fee_type = fields.Selection([
        ('none', 'Yok'),
        ('percent', 'Yuzde'),
        ('fixed', 'Sabit'),
    ], string='Komisyon Tipi', default='none')
    fee_value = fields.Float(string='Ucret Degeri')
    fee_account_id = fields.Many2one('account.account', string='Komisyon Gider Hesabi')
    tax_account_id = fields.Many2one('account.account', string='Vergi Hesabi')

    integration_type = fields.Selection([
        ('manual', 'Manuel'),
        ('sftp', 'SFTP'),
        ('api', 'API'),
    ], string='Entegrasyon Tipi', required=True, default='manual')
    adapter_code = fields.Char(string='Adaptor Kodu', required=True, default='manual')
    api_endpoint = fields.Char(string='API Endpoint')
    api_token = fields.Char(string='API Token', password=True)
    api_ack_method = fields.Char(string='ACK Method', default='GET')
    api_ack_timeout = fields.Integer(string='ACK Timeout (sn)', default=20)
    api_company_code = fields.Char(string='Sirket Kodu Header')
    api_accept_header = fields.Char(string='Accept Header', default='application/json')

    sftp_host = fields.Char(string='SFTP Host')
    sftp_port = fields.Integer(string='SFTP Port', default=22)
    sftp_username = fields.Char(string='SFTP Kullanici')
    sftp_password = fields.Char(string='SFTP Sifre', password=True)
    sftp_path = fields.Char(string='SFTP ACK Klasoru')
    sftp_timeout = fields.Integer(string='SFTP Timeout (sn)', default=20)
    sftp_ack_filename_pattern = fields.Char(string='ACK Dosya Kalibi', default='.*\\.(csv|txt)$')
    sftp_ack_archive_path = fields.Char(string='ACK Arsiv Klasoru', default='/archive/ack')
    sftp_ack_delete_after_fetch = fields.Boolean(string='ACK Alindiktan Sonra Sil', default=False)

    technical_params = fields.Text(string='Teknik Parametreler')
    manual_fee_move_ids = fields.One2many('account.move', 'dbs_contract_id', string='Yevmiye Kayitlari', readonly=True)
    manual_fee_move_count = fields.Integer(compute='_compute_dbs_related_counts', string='Yevmiye Kayit Sayisi')
    dbs_partner_count = fields.Integer(compute='_compute_dbs_related_counts', string='DBS Musteri Sayisi')
    dbs_batch_count = fields.Integer(compute='_compute_dbs_related_counts', string='DBS Toplu Islem Sayisi')
    dbs_line_count = fields.Integer(compute='_compute_dbs_related_counts', string='DBS Satir Sayisi')
    dbs_invoice_count = fields.Integer(compute='_compute_dbs_related_counts', string='DBS Fatura Sayisi')

    active = fields.Boolean(string='Aktif', default=True, tracking=True)

    @api.depends('manual_fee_move_ids', 'contact_id', 'limit_amount', 'active')
    def _compute_dbs_related_counts(self):
        batch_model = self.env['dbs.batch']
        line_model = self.env['dbs.batch.line']
        for rec in self:
            rec.manual_fee_move_count = len(rec.manual_fee_move_ids)
            rec.dbs_partner_count = 1 if rec.contact_id else 0
            rec.dbs_batch_count = batch_model.search_count([('contract_id', '=', rec.id)])
            rec.dbs_line_count = line_model.search_count([('contract_id', '=', rec.id)])
            rec.dbs_invoice_count = line_model.search_count([('contract_id', '=', rec.id)])

    @api.onchange('bank_id')
    def _onchange_bank_id(self):
        for rec in self:
            if not rec.bank_id:
                rec.bank_account_id = False
                continue
            valid_accounts = self.env['res.partner.bank'].search([
                ('bank_id', '=', rec.bank_id.id),
            ], limit=1)
            rec.bank_account_id = valid_accounts[:1].id if valid_accounts else False

    def _sync_contact_dbs_fields(self):
        for rec in self:
            partner = rec.contact_id.commercial_partner_id
            if not partner:
                continue

            vals = {
                'dbs_limit': rec.limit_amount or 0.0,
            }
            if rec.active:
                vals.update({
                    'dbs_enabled': True,
                    'dbs_status': 'active',
                    'dbs_contract_id': rec.id,
                })
            else:
                vals['dbs_enabled'] = False
                if partner.dbs_contract_id == rec:
                    vals['dbs_contract_id'] = False

            partner.write(vals)

    def action_open_dbs_partner(self):
        self.ensure_one()
        if not self.contact_id:
            raise UserError(_('Bu DBS sozlesmesinin bagli kontak kaydi yok.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('DBS Musterisi'),
            'res_model': 'res.partner',
            'view_mode': 'form',
            'res_id': self.contact_id.id,
            'target': 'current',
        }

    def action_open_dbs_batches(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('DBS Toplu Islemler'),
            'res_model': 'dbs.batch',
            'view_mode': 'list,form',
            'domain': [('contract_id', '=', self.id)],
            'target': 'current',
        }

    def action_open_dbs_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('DBS Faturalari'),
            'res_model': 'dbs.batch.line',
            'view_mode': 'list,form',
            'domain': [('contract_id', '=', self.id)],
            'target': 'current',
        }

    def action_open_dbs_invoices(self):
        self.ensure_one()
        invoice_ids = self.env['dbs.batch.line'].search([('contract_id', '=', self.id)]).mapped('move_id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('DBS Faturalari'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', invoice_ids)],
            'target': 'current',
        }

    def action_open_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Yevmiye Kayitlari'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.manual_fee_move_ids.ids)],
            'target': 'current',
        }

    def _get_settlement_bank_account(self):
        self.ensure_one()
        bank_account = self.settlement_bank_journal_id.default_account_id
        if bank_account:
            return bank_account
        return self.env['account.account'].search([
            ('company_id', '=', self.company_id.id),
            ('code', '=like', '102%'),
        ], limit=1)

    def _get_invoice_receivable_account(self, invoice):
        self.ensure_one()
        invoice.ensure_one()
        receivable_line = invoice.line_ids.filtered(
            lambda l: l.account_id and l.account_id.account_type == 'asset_receivable'
        )[:1]
        if receivable_line:
            return receivable_line.account_id
        return self.env['account.account'].search([
            ('company_id', '=', self.company_id.id),
            ('code', '=like', '120%'),
        ], limit=1)

    def _create_settlement_move_from_dbs_line(self, dbs_line, statement_line=False):
        self.ensure_one()
        dbs_line.ensure_one()

        invoice = dbs_line.move_id
        journal = self.settlement_bank_journal_id
        if not journal:
            raise UserError(_('Tahsilat taslak yevmiye icin Yevmiye Adi zorunludur.'))

        bank_account = self.settlement_debit_account_id or self._get_settlement_bank_account()
        receivable_account = self.settlement_credit_account_id or self._get_invoice_receivable_account(invoice)
        if not bank_account or not receivable_account:
            raise UserError(_('Tahsilat taslak yevmiye icin 102 ve 120 hesaplari bulunamadi.'))

        currency = invoice.currency_id or self.currency_id
        amount = abs((statement_line.amount if statement_line else 0.0) or dbs_line.amount or 0.0)
        amount = currency.round(amount)
        if amount <= 0:
            return self.env['account.move']

        existing = self.env['account.move'].search([
            ('dbs_contract_id', '=', self.id),
            ('dbs_batch_line_id', '=', dbs_line.id),
            ('dbs_entry_type', '=', 'settlement'),
        ], limit=1)
        if existing:
            return existing

        ref = _('DBS Tahsilat - %(invoice)s - %(ref)s') % {
            'invoice': invoice.name or invoice.display_name,
            'ref': dbs_line.dbs_line_ref,
        }
        return self.env['account.move'].create({
            'company_id': self.company_id.id,
            'date': statement_line.date if statement_line else (invoice.invoice_date or fields.Date.context_today(self)),
            'journal_id': journal.id,
            'move_type': 'entry',
            'ref': ref,
            'dbs_contract_id': self.id,
            'dbs_source_move_id': invoice.id,
            'dbs_batch_line_id': dbs_line.id,
            'dbs_entry_type': 'settlement',
            'line_ids': [
                (0, 0, {
                    'name': _('DBS Tahsilat - %(invoice)s') % {'invoice': invoice.name or invoice.display_name},
                    'account_id': bank_account.id,
                    'debit': amount,
                    'credit': 0.0,
                    'partner_id': invoice.partner_id.commercial_partner_id.id,
                }),
                (0, 0, {
                    'name': _('DBS Tahsilat Karsiligi - %(invoice)s') % {'invoice': invoice.name or invoice.display_name},
                    'account_id': receivable_account.id,
                    'debit': 0.0,
                    'credit': amount,
                    'partner_id': invoice.partner_id.commercial_partner_id.id,
                }),
            ],
        })

    def _create_manual_fee_move_from_dbs_line(self, dbs_line):
        self.ensure_one()
        dbs_line.ensure_one()

        invoice = dbs_line.move_id

        if self.integration_type != 'manual' or self.fee_type == 'none':
            return self.env['account.move']
        self.ensure_one()
        invoice.ensure_one()

        if self.integration_type != 'manual' or self.fee_type == 'none':
            return self.env['account.move']

        currency = invoice.currency_id or self.currency_id
        amount_base = invoice.amount_total or 0.0
        if amount_base <= 0:
            return self.env['account.move']

        fee_rate = self.fee_value or 0.0
        if self.fee_type == 'percent':
            fee_amount = amount_base * (fee_rate / 100.0)
        else:
            fee_amount = self.fee_value or 0.0

        fee_amount = currency.round(fee_amount)
        if fee_amount <= 0:
            return self.env['account.move']

        debit_account = self.commission_debit_account_id or self.fee_account_id or self.env['account.account'].search([
            ('company_id', '=', self.company_id.id),
            ('code', '=like', '780%'),
        ], limit=1)
        credit_account = self.commission_credit_account_id or self._get_settlement_bank_account()

        if not debit_account or not credit_account:
            raise UserError(_('Manuel komisyon fisi icin 780 ve 102 hesaplari bulunamadi.'))

        journal = self.settlement_bank_journal_id
        if not journal:
            raise UserError(_('Manuel komisyon fisi icin Yevmiye Adi zorunludur.'))

        ref = _('DBS Komisyon - %(invoice)s') % {'invoice': invoice.name or invoice.display_name}
        existing = self.env['account.move'].search([
            ('dbs_contract_id', '=', self.id),
            ('dbs_batch_line_id', '=', dbs_line.id),
            ('dbs_entry_type', '=', 'commission'),
        ], limit=1)
        if existing:
            return existing

        return self.env['account.move'].create({
            'company_id': self.company_id.id,
            'date': invoice.invoice_date or fields.Date.context_today(self),
            'journal_id': journal.id,
            'move_type': 'entry',
            'ref': ref,
            'dbs_contract_id': self.id,
            'dbs_source_move_id': invoice.id,
            'dbs_batch_line_id': dbs_line.id,
            'dbs_entry_type': 'commission',
            'dbs_fee_amount': fee_amount,
            'dbs_fee_rate': fee_rate if self.fee_type == 'percent' else 0.0,
            'line_ids': [
                (0, 0, {
                    'name': _('DBS Komisyon Gideri - %(invoice)s') % {'invoice': invoice.name or invoice.display_name},
                    'account_id': debit_account.id,
                    'debit': fee_amount,
                    'credit': 0.0,
                    'partner_id': invoice.partner_id.commercial_partner_id.id,
                }),
                (0, 0, {
                    'name': _('DBS Banka Tahsilat Karsiligi - %(invoice)s') % {'invoice': invoice.name or invoice.display_name},
                    'account_id': credit_account.id,
                    'debit': 0.0,
                    'credit': fee_amount,
                    'partner_id': invoice.partner_id.commercial_partner_id.id,
                }),
            ],
        })

    def _create_settlement_entries_from_dbs_line(self, dbs_line, statement_line=False):
        self.ensure_one()
        dbs_line.ensure_one()
        settlement_move = self._create_settlement_move_from_dbs_line(dbs_line, statement_line=statement_line)
        commission_move = self._create_manual_fee_move_from_dbs_line(dbs_line)
        return settlement_move | commission_move

    def _compute_fee_amount_for_line(self, dbs_line):
        self.ensure_one()
        invoice = dbs_line.move_id
        currency = invoice.currency_id or self.currency_id
        amount_base = invoice.amount_total or 0.0
        if amount_base <= 0:
            return 0.0

        if self.fee_type == 'percent':
            amount = amount_base * ((self.fee_value or 0.0) / 100.0)
        elif self.fee_type == 'fixed':
            amount = self.fee_value or 0.0
        else:
            amount = 0.0
        return currency.round(amount)

    def _sync_draft_moves_for_line(self, dbs_line):
        self.ensure_one()
        dbs_line.ensure_one()
        invoice = dbs_line.move_id
        partner = invoice.partner_id.commercial_partner_id

        settlement_move = self.env['account.move'].search([
            ('dbs_contract_id', '=', self.id),
            ('dbs_batch_line_id', '=', dbs_line.id),
            ('dbs_entry_type', '=', 'settlement'),
        ], limit=1)
        if settlement_move and settlement_move.state == 'draft':
            amount = abs(dbs_line.amount or 0.0)
            bank_account = self.settlement_debit_account_id or self._get_settlement_bank_account()
            receivable_account = self.settlement_credit_account_id or self._get_invoice_receivable_account(invoice)
            if bank_account and receivable_account and amount > 0:
                settlement_move.write({
                    'journal_id': self.settlement_bank_journal_id.id,
                    'ref': _('DBS Tahsilat - %(invoice)s - %(ref)s') % {
                        'invoice': invoice.name or invoice.display_name,
                        'ref': dbs_line.dbs_line_ref,
                    },
                    'line_ids': [
                        (5, 0, 0),
                        (0, 0, {
                            'name': _('DBS Tahsilat - %(invoice)s') % {'invoice': invoice.name or invoice.display_name},
                            'account_id': bank_account.id,
                            'debit': amount,
                            'credit': 0.0,
                            'partner_id': partner.id,
                        }),
                        (0, 0, {
                            'name': _('DBS Tahsilat Karsiligi - %(invoice)s') % {'invoice': invoice.name or invoice.display_name},
                            'account_id': receivable_account.id,
                            'debit': 0.0,
                            'credit': amount,
                            'partner_id': partner.id,
                        }),
                    ],
                })

        commission_move = self.env['account.move'].search([
            ('dbs_contract_id', '=', self.id),
            ('dbs_batch_line_id', '=', dbs_line.id),
            ('dbs_entry_type', '=', 'commission'),
        ], limit=1)
        fee_amount = self._compute_fee_amount_for_line(dbs_line)
        if self.fee_type == 'none' or fee_amount <= 0:
            if commission_move and commission_move.state == 'draft':
                commission_move.unlink()
            return

        if commission_move and commission_move.state != 'draft':
            return

        debit_account = self.commission_debit_account_id or self.fee_account_id or self.env['account.account'].search([
            ('company_id', '=', self.company_id.id),
            ('code', '=like', '780%'),
        ], limit=1)
        credit_account = self.commission_credit_account_id or self._get_settlement_bank_account()
        if not debit_account or not credit_account:
            return

        vals = {
            'company_id': self.company_id.id,
            'date': invoice.invoice_date or fields.Date.context_today(self),
            'journal_id': self.settlement_bank_journal_id.id,
            'move_type': 'entry',
            'ref': _('DBS Komisyon - %(invoice)s') % {'invoice': invoice.name or invoice.display_name},
            'dbs_contract_id': self.id,
            'dbs_source_move_id': invoice.id,
            'dbs_batch_line_id': dbs_line.id,
            'dbs_entry_type': 'commission',
            'dbs_fee_amount': fee_amount,
            'dbs_fee_rate': self.fee_value if self.fee_type == 'percent' else 0.0,
            'line_ids': [
                (5, 0, 0),
                (0, 0, {
                    'name': _('DBS Komisyon Gideri - %(invoice)s') % {'invoice': invoice.name or invoice.display_name},
                    'account_id': debit_account.id,
                    'debit': fee_amount,
                    'credit': 0.0,
                    'partner_id': partner.id,
                }),
                (0, 0, {
                    'name': _('DBS Banka Tahsilat Karsiligi - %(invoice)s') % {'invoice': invoice.name or invoice.display_name},
                    'account_id': credit_account.id,
                    'debit': 0.0,
                    'credit': fee_amount,
                    'partner_id': partner.id,
                }),
            ],
        }

        if commission_move:
            commission_move.write(vals)
        else:
            self.env['account.move'].create(vals)

    def _sync_draft_moves_from_contract(self):
        for contract in self:
            lines = self.env['dbs.batch.line'].search([
                ('contract_id', '=', contract.id),
            ])
            for line in lines:
                contract._sync_draft_moves_for_line(line)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('dbs.contract') or 'New'
            if vals.get('integration_type') and not vals.get('adapter_code'):
                vals['adapter_code'] = vals.get('integration_type')
        records = super().create(vals_list)
        records._sync_technical_params_json()
        records._sync_contact_dbs_fields()
        return records

    def write(self, vals):
        vals = dict(vals)
        if 'integration_type' in vals and 'adapter_code' not in vals:
            vals['adapter_code'] = vals.get('integration_type') or 'manual'
        res = super().write(vals)
        integration_sync_fields = {
            'integration_type',
            'api_endpoint',
            'api_token',
            'api_ack_method',
            'api_ack_timeout',
            'api_company_code',
            'api_accept_header',
            'sftp_host',
            'sftp_port',
            'sftp_username',
            'sftp_password',
            'sftp_path',
            'sftp_timeout',
            'sftp_ack_filename_pattern',
            'sftp_ack_archive_path',
            'sftp_ack_delete_after_fetch',
        }
        if integration_sync_fields & set(vals.keys()):
            self._sync_technical_params_json()
        if {'active', 'contact_id', 'limit_amount'} & set(vals.keys()):
            self._sync_contact_dbs_fields()
        sync_fields = {
            'settlement_bank_journal_id',
            'settlement_debit_account_id',
            'settlement_credit_account_id',
            'commission_debit_account_id',
            'commission_credit_account_id',
            'fee_type',
            'fee_value',
            'fee_account_id',
        }
        if sync_fields & set(vals.keys()):
            self._sync_draft_moves_from_contract()
        return res

    def _get_technical_params_dict(self):
        self.ensure_one()
        generated = self._build_technical_params_from_fields()
        if generated:
            return generated

        params_text = (self.technical_params or '').strip()
        if not params_text:
            return {}
        try:
            params = json.loads(params_text)
        except Exception as exc:
            raise UserError(_('Teknik Parametreler JSON formatinda olmali: %s') % str(exc))
        if not isinstance(params, dict):
            raise UserError(_('Teknik Parametreler JSON obje formatinda olmali.'))
        return params

    def _build_technical_params_from_fields(self):
        self.ensure_one()
        if self.integration_type == 'api' and self.api_endpoint and self.api_token:
            params = {
                'endpoint': self.api_endpoint,
                'token': self.api_token,
                'ack_method': self.api_ack_method or 'GET',
                'ack_timeout': self.api_ack_timeout or 20,
                'ack_headers': {
                    'X-Company-Code': self.api_company_code or self.company_id.name,
                    'Accept': self.api_accept_header or 'application/json',
                },
                'ack_filename': 'ack.csv',
            }
            return params

        if self.integration_type == 'sftp' and self.sftp_host and self.sftp_username and self.sftp_path:
            return {
                'host': self.sftp_host,
                'port': self.sftp_port or 22,
                'username': self.sftp_username,
                'password': self.sftp_password or '',
                'path': self.sftp_path,
                'timeout': self.sftp_timeout or 20,
                'ack_filename_pattern': self.sftp_ack_filename_pattern or '.*\\.(csv|txt)$',
                'ack_archive_path': self.sftp_ack_archive_path or '/archive/ack',
                'ack_delete_after_fetch': bool(self.sftp_ack_delete_after_fetch),
            }
        return {}

    def _sync_technical_params_json(self):
        for rec in self:
            params = rec._build_technical_params_from_fields()
            if params:
                rec.technical_params = json.dumps(params, ensure_ascii=True, indent=2)

    @api.onchange('integration_type')
    def _onchange_integration_type(self):
        for rec in self:
            rec.adapter_code = rec.integration_type or 'manual'

    def action_test_connection(self):
        for rec in self:
            params = rec._get_technical_params_dict()

            if rec.integration_type == 'manual':
                rec.message_post(body=_('Manual entegrasyon secili. Teknik baglanti testi uygulanmadi.'))
                continue

            if rec.integration_type == 'api':
                missing = [key for key in ('endpoint', 'token') if not params.get(key)]
                if missing:
                    raise UserError(_('API testi icin eksik teknik parametre(ler): %s') % ', '.join(missing))
                rec.message_post(body=_('API teknik parametre testi basarili (endpoint/token mevcut).'))
                continue

            if rec.integration_type == 'sftp':
                missing = [key for key in ('host', 'username', 'path') if not params.get(key)]
                if missing:
                    raise UserError(_('SFTP testi icin eksik teknik parametre(ler): %s') % ', '.join(missing))
                rec.message_post(body=_('SFTP teknik parametre testi basarili (host/username/path mevcut).'))
                continue

            rec.message_post(body=_('DBS baglanti testi tamamlandi.'))
        return True

    def _get_adapter(self):
        self.ensure_one()
        code = (self.adapter_code or 'manual').strip().lower()
        model_name = f'dbs.adapter.{code}'
        if model_name in self.env:
            return self.env[model_name]
        if self.integration_type == 'manual':
            return self.env['dbs.adapter.manual']
        raise UserError(_("Adaptor bulunamadi: %s") % model_name)
 