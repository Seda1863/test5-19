# -*- coding: utf-8 -*-
import logging
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class GuaranteeLetter(models.Model):
    _name = 'guarantee.letter'
    _description = 'Teminat Mektubu'
    _order = 'issue_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Referans No',
        readonly=True,
        copy=False,
        default='Yeni',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Şirket',
        default=lambda self: self.env.company,
        required=True,
    )
    letter_no = fields.Char(
        string='Mektup No',
        tracking=True,
        help='Bankanın verdiği teminat mektubu numarası',
    )
    letter_party_type = fields.Selection([
        ('received', 'Alınan Teminat Mektubu'),
        ('given', 'Verilen Teminat Mektubu'),
    ], string='Mektup Türü', default='received', required=True, tracking=True)
    letter_type_id = fields.Many2one(
        'guarantee.letter.type',
        string='Teminat Türü',
        required=True,
        tracking=True,
    )
    bank_partner_id = fields.Many2one(
        'res.partner',
        string='Banka',
        required=True,
        tracking=True,
        domain="[('is_company', '=', True)]",
    )
    beneficiary_partner_id = fields.Many2one(
        'res.partner',
        string='Muhatap',
        required=True,
        tracking=True,
        help='Teminat mektubunun verildiği kurum/kişi',
    )
    lehdar_partner_id = fields.Many2one(
        'res.partner',
        string='Lehdar',
        tracking=True,
        default=lambda self: self.env.company.partner_id,
        help='Lehine teminat mektubu düzenlenen taraf',
    )
    project_id = fields.Many2one(
        'project.project',
        string='Proje',
        tracking=True,
    )
    issue_date = fields.Date(
        string='Düzenleme Tarihi',
        required=True,
        tracking=True,
    )
    expiry_date = fields.Date(
        string='Vade Tarihi',
        required=True,
        tracking=True,
    )
    remaining_days = fields.Integer(
        string='Kalan Gün',
        compute='_compute_remaining_days',
        store=True,
    )
    amount = fields.Monetary(
        string='Tutar',
        required=True,
        tracking=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Para Birimi',
        default=lambda self: self.env.company.currency_id,
        required=False,
    )
    company_currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        string='Sirket Para Birimi',
        readonly=True,
    )
    currency_rate_type = fields.Selection([
        ('forexbuying', 'Doviz Alis'),
        ('forexselling', 'Doviz Satis'),
        ('banknotebuying', 'Efektif Alis'),
        ('banknoteselling', 'Efektif Satis'),
        ('manualexchange', 'Manuel Kur'),
    ], string='Kur Tipi', default=lambda self: self._get_default_rate_type(), tracking=True)
    letter_currency_rate = fields.Float(
        string='Kur Orani',
        digits=(12, 6),
        help='1 Sirket Para Birimi = X Islem Para Birimi',
    )
    letter_currency_inverse_rate = fields.Float(
        string='Ters Kur Orani',
        digits=(12, 6),
        help='1 Islem Para Birimi = X Sirket Para Birimi',
    )
    responsible_id = fields.Many2one(
        'res.users',
        string='Sorumlu',
        default=lambda self: self.env.user,
        tracking=True,
    )
    reminder_user_id = fields.Many2one(
        'res.users',
        string='Hatırlatma Kullanıcısı',
        required=True,
        tracking=True,
        help='Vade hatırlatma activity kaydı bu kullanıcıya atanır.',
    )
    reminder_email_to = fields.Char(
        string='Bilgilendirme E-Postaları',
        required=True,
        help='Virgülle ayırarak birden fazla e-posta adresi girebilirsiniz.',
    )
    reminder_day_7 = fields.Boolean(string='7 Gün Kala Bildir', default=True)
    reminder_day_15 = fields.Boolean(string='15 Gün Kala Bildir', default=True)
    reminder_day_30 = fields.Boolean(string='30 Gün Kala Bildir', default=True)
    intro_notification_sent = fields.Boolean(
        string='İlk Bilgilendirme Gönderildi',
        copy=False,
        readonly=True,
    )
    state = fields.Selection([
        ('draft', 'Taslak'),
        ('waiting_approval', 'Onay Bekliyor'),
        ('active', 'Aktif'),
        ('return_requested', 'İade Talep Edildi'),
        ('returned', 'İade Edildi'),
        ('cancelled', 'İptal'),
        ('encashed', 'Nakde Çevrildi'),
    ], string='Durum', default='draft', tracking=True, copy=False)

    description = fields.Text(string='Açıklama')
    notes = fields.Text(string='Notlar')
    commission_rate = fields.Float(string='Komisyon Oranı (%)')
    commission_amount = fields.Monetary(
        string='Komisyon Tutarı',
        currency_field='currency_id',
    )
    has_blockage = fields.Boolean(string='Blokaj Var mı')
    blockage_amount = fields.Monetary(
        string='Blokaj Tutarı',
        currency_field='currency_id',
    )

    journal_entry_id = fields.Many2one(
        'account.move',
        string='Yevmiye No',
        copy=False,
        readonly=True,
    )
    return_journal_entry_id = fields.Many2one(
        'account.move',
        string='İade Yevmiye No',
        copy=False,
        readonly=True,
    )
    commission_journal_entry_id = fields.Many2one(
        'account.move',
        string='Komisyon Yevmiye No',
        copy=False,
        readonly=True,
    )
    blockage_journal_entry_id = fields.Many2one(
        'account.move',
        string='Blokaj Yevmiye No',
        copy=False,
        readonly=True,
    )
    encash_journal_entry_id = fields.Many2one(
        'account.move',
        string='Tazmin Yevmiye No',
        copy=False,
        readonly=True,
    )
    accounting_state = fields.Selection([
        ('draft', 'Taslak'),
        ('created', 'Oluşturuldu'),
        ('cancelled', 'İptal'),
    ], string='Muhasebe Durumu', compute='_compute_accounting_state', store=True)
    journal_entry_create_date = fields.Datetime(
        string='Oluşturma Tarihi',
        readonly=True,
        copy=False,
    )

    bank_limit_id = fields.Many2one(
        'bank.guarantee.limit',
        string='Banka Limiti',
        compute='_compute_bank_limit',
        store=True,
    )

    # ── Computed ──
    @api.depends('expiry_date')
    def _compute_remaining_days(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.expiry_date:
                rec.remaining_days = (rec.expiry_date - today).days
            else:
                rec.remaining_days = 0

    @api.depends('bank_partner_id', 'company_id')
    def _compute_bank_limit(self):
        for rec in self:
            if rec.bank_partner_id:
                limit = self.env['bank.guarantee.limit'].search([
                    ('bank_partner_id', '=', rec.bank_partner_id.id),
                    ('company_id', '=', rec.company_id.id),
                ], limit=1)
                rec.bank_limit_id = limit.id if limit else False
            else:
                rec.bank_limit_id = False

    @api.depends('journal_entry_id', 'journal_entry_id.state')
    def _compute_accounting_state(self):
        for rec in self:
            if not rec.journal_entry_id:
                rec.accounting_state = 'draft'
            elif rec.journal_entry_id.state == 'cancel':
                rec.accounting_state = 'cancelled'
            else:
                rec.accounting_state = 'created'

    @api.onchange('company_id')
    def _onchange_company_id_set_lehdar(self):
        for rec in self:
            if rec.company_id and not rec.lehdar_partner_id:
                rec.lehdar_partner_id = rec.company_id.partner_id
            if rec.company_id and not rec.currency_id:
                rec.currency_id = rec.company_id.currency_id

    @api.onchange('responsible_id')
    def _onchange_responsible_id_set_reminder_user(self):
        for rec in self:
            if rec.responsible_id and not rec.reminder_user_id:
                rec.reminder_user_id = rec.responsible_id

    @api.onchange('commission_rate', 'amount')
    def _onchange_commission_rate(self):
        for rec in self:
            if rec.commission_rate and rec.amount:
                rec.commission_amount = (rec.amount * rec.commission_rate) / 100.0

    @api.onchange('issue_date', 'currency_id', 'currency_rate_type', 'company_id')
    def _onchange_currency_rate_setup(self):
        for rec in self:
            rec._set_currency_rate_fields_from_selection()

    @api.onchange('letter_currency_rate')
    def _onchange_letter_currency_rate(self):
        for rec in self:
            if rec.currency_rate_type == 'manualexchange' and rec.letter_currency_rate:
                rec.letter_currency_inverse_rate = 1.0 / rec.letter_currency_rate

    @api.onchange('letter_currency_inverse_rate')
    def _onchange_letter_currency_inverse_rate(self):
        for rec in self:
            if rec.currency_rate_type == 'manualexchange' and rec.letter_currency_inverse_rate:
                rec.letter_currency_rate = 1.0 / rec.letter_currency_inverse_rate

    # ── Sequence ──
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Yeni') == 'Yeni':
                vals['name'] = self.env['ir.sequence'].next_by_code('guarantee.letter') or 'Yeni'
            if not vals.get('reminder_user_id') and vals.get('responsible_id'):
                vals['reminder_user_id'] = vals['responsible_id']

            company = self.env['res.company'].browse(vals.get('company_id')) if vals.get('company_id') else self.env.company
            currency = self.env['res.currency'].browse(vals.get('currency_id')) if vals.get('currency_id') else company.currency_id
            vals.setdefault('currency_id', currency.id)
            rate_type = vals.get('currency_rate_type') or self._get_default_rate_type(company)
            rate_date = vals.get('issue_date') or fields.Date.context_today(self)
            manual_rate = vals.get('letter_currency_rate') if rate_type == 'manualexchange' else None
            rate, inverse_rate = self._compute_selected_currency_rates(
                currency=currency,
                company=company,
                rate_date=rate_date,
                rate_type=rate_type,
                manual_rate=manual_rate,
            )
            vals.setdefault('currency_rate_type', rate_type)
            vals['letter_currency_rate'] = rate
            vals['letter_currency_inverse_rate'] = inverse_rate

        records = super().create(vals_list)
        records._send_initial_notification_if_needed()
        return records

    def write(self, vals):
        if 'currency_id' in vals and not vals.get('currency_id'):
            for rec in self:
                vals['currency_id'] = rec.company_id.currency_id.id
                break

        res = super().write(vals)

        rate_keys = {
            'issue_date',
            'currency_id',
            'currency_rate_type',
            'company_id',
            'letter_currency_rate',
            'letter_currency_inverse_rate',
        }
        if rate_keys.intersection(vals.keys()) and not self.env.context.get('skip_currency_rate_sync'):
            for rec in self:
                rec._set_currency_rate_fields_from_selection()

        fields_to_check = {
            'reminder_user_id',
            'reminder_email_to',
            'reminder_day_7',
            'reminder_day_15',
            'reminder_day_30',
        }
        if fields_to_check.intersection(vals.keys()):
            self._send_initial_notification_if_needed()
        return res

    # ── Workflow Actions ──
    def action_submit_approval(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Sadece taslak durumundaki kayıtlar onaya gönderilebilir."))
            rec.state = 'waiting_approval'

    def action_approve(self):
        for rec in self:
            if rec.state != 'waiting_approval':
                raise UserError(_("Sadece onay bekleyen kayıtlar onaylanabilir."))
            # Banka limit kontrolü
            rec._check_bank_limit()
            rec.state = 'active'
            rec._create_memorandum_entry_for_active()
            rec._create_commission_entry()
            rec._create_blockage_entry()

    def action_request_return(self):
        for rec in self:
            if rec.state != 'active':
                raise UserError(_("Sadece aktif teminat mektupları için iade talep edilebilir."))
            rec.state = 'return_requested'

    def action_return(self):
        for rec in self:
            if rec.state not in ('active', 'return_requested'):
                raise UserError(_("Bu kayıt iade edilemez."))
            rec.state = 'returned'
            rec._create_memorandum_reverse_entry()

    def action_cancel(self):
        for rec in self:
            if rec.state in ('returned', 'encashed'):
                raise UserError(_("Kapanmış kayıtlar iptal edilemez."))
            rec.state = 'cancelled'

    def action_encash(self):
        for rec in self:
            if rec.state != 'active':
                raise UserError(_("Sadece aktif teminat mektupları nakde çevrilebilir."))
            rec._create_memorandum_reverse_entry()
            rec._create_encash_entry()
            rec.state = 'encashed'

    def action_reset_draft(self):
        for rec in self:
            if rec.state not in ('cancelled', 'waiting_approval'):
                raise UserError(_("Sadece iptal veya onay bekleyen kayıtlar taslağa alınabilir."))
            rec.state = 'draft'

    # ── Limit Kontrolü ──
    def _check_bank_limit(self):
        self.ensure_one()
        limit_rec = self.env['bank.guarantee.limit'].search([
            ('bank_partner_id', '=', self.bank_partner_id.id),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if limit_rec:
            letter_currency = self.currency_id or self.company_id.currency_id
            rate_date = self.issue_date or fields.Date.context_today(self)
            requested_in_limit_currency = letter_currency._convert(
                self.amount,
                limit_rec.currency_id,
                self.company_id,
                rate_date,
            )
            if limit_rec.available_amount < requested_in_limit_currency:
                raise UserError(_(
                    "%(bank)s bankasında yeterli teminat limiti bulunmamaktadır.\n\n"
                    "Toplam Limit: %(limit)s\n"
                    "Kullanılan: %(used)s\n"
                    "Kullanılabilir: %(available)s\n"
                    "Talep Edilen: %(requested)s",
                    bank=self.bank_partner_id.name,
                    limit=f"{limit_rec.limit_amount:,.2f}",
                    used=f"{limit_rec.used_amount:,.2f}",
                    available=f"{limit_rec.available_amount:,.2f}",
                    requested=f"{limit_rec.currency_id.round(requested_in_limit_currency):,.2f}",
                ))

    def _get_move_extra_vals(self):
        """edonusum uyumluluğu için tüm fişlerde zorunlu alanları set et."""
        AccountMove = self.env['account.move']
        extra_vals = {}
        transaction_currency = self.currency_id or self.company_id.currency_id
        if 'document_type' in AccountMove._fields:
            extra_vals['document_type'] = 'receipt'
        if 'payment_method' in AccountMove._fields:
            extra_vals['payment_method'] = 'bank'
        if 'currency_id' in AccountMove._fields:
            extra_vals['currency_id'] = transaction_currency.id
        if 'currency_rate_type' in AccountMove._fields:
            extra_vals['currency_rate_type'] = self.currency_rate_type or self._get_default_rate_type(self.company_id)
        if 'invoice_currency_rate' in AccountMove._fields:
            extra_vals['invoice_currency_rate'] = self.letter_currency_rate or 1.0
        if 'invoice_currency_inverse_rate' in AccountMove._fields:
            extra_vals['invoice_currency_inverse_rate'] = self.letter_currency_inverse_rate or 1.0
        return extra_vals

    def _get_move_date(self):
        """Yevmiye tarihini belirler; kur dönüşümü bu tarihe göre yapılır."""
        self.ensure_one()
        return fields.Date.context_today(self)

    @api.model
    def _get_default_rate_type(self, company=None):
        company = company or self.env.company
        if 'currency_rate_type' in company._fields and company.currency_rate_type:
            return company.currency_rate_type
        return 'forexbuying'

    @api.model
    def _get_rate_record_for_date(self, currency, company, rate_date):
        rate_model = self.env['res.currency.rate']
        domain = [
            ('currency_id', '=', currency.id),
            ('name', '<=', rate_date),
        ]
        if 'company_id' in rate_model._fields:
            domain += ['|', ('company_id', '=', company.id), ('company_id', '=', False)]
        return rate_model.search(domain, order='name desc, id desc', limit=1)

    @api.model
    def _compute_selected_currency_rates(self, currency, company, rate_date, rate_type, manual_rate=None):
        company_currency = company.currency_id
        if currency == company_currency:
            return 1.0, 1.0

        context_currency = currency.with_company(company).with_context(date=rate_date)
        selected_rate = context_currency.rate or 1.0
        rate_record = self._get_rate_record_for_date(currency, company, rate_date)
        rate_model_fields = self.env['res.currency.rate']._fields
        rate_field_map = {
            'forexbuying': 'forex_buying',
            'forexselling': 'forex_selling',
            'banknotebuying': 'banknote_buying',
            'banknoteselling': 'banknote_selling',
        }

        if rate_type == 'manualexchange' and manual_rate:
            selected_rate = manual_rate
        else:
            selected_field = rate_field_map.get(rate_type)
            if selected_field and selected_field in rate_model_fields and rate_record:
                selected_value = rate_record[selected_field]
                if selected_value:
                    selected_rate = 1.0 / selected_value

        if not selected_rate:
            selected_rate = 1.0
        inverse_rate = 1.0 / selected_rate if selected_rate else 1.0
        return selected_rate, inverse_rate

    def _set_currency_rate_fields_from_selection(self):
        self.ensure_one()
        if not self.currency_id:
            self.currency_id = self.company_id.currency_id
        rate_type = self.currency_rate_type or self._get_default_rate_type(self.company_id)
        rate_date = self.issue_date or fields.Date.context_today(self)
        manual_rate = self.letter_currency_rate if rate_type == 'manualexchange' else None
        rate, inverse_rate = self._compute_selected_currency_rates(
            currency=self.currency_id,
            company=self.company_id,
            rate_date=rate_date,
            rate_type=rate_type,
            manual_rate=manual_rate,
        )

        if self.env.context.get('skip_currency_rate_sync') or not self._origin.id:
            self.letter_currency_rate = rate
            self.letter_currency_inverse_rate = inverse_rate
            self.currency_rate_type = rate_type
            return

        self.with_context(skip_currency_rate_sync=True).write({
            'currency_rate_type': rate_type,
            'letter_currency_rate': rate,
            'letter_currency_inverse_rate': inverse_rate,
        })

    def _prepare_line_amounts(self, amount, move_date):
        """Seçilen para birimini günlük kura göre şirket para birimine çevirir."""
        self.ensure_one()
        company_currency = self.company_id.currency_id

        if self.currency_id == company_currency:
            return {
                'balance_amount': amount,
                'foreign_currency_id': company_currency.id,
                'debit_amount_currency': amount,
                'credit_amount_currency': -amount,
            }

        rate, inverse_rate = self._compute_selected_currency_rates(
            currency=self.currency_id,
            company=self.company_id,
            rate_date=move_date,
            rate_type=self.currency_rate_type or self._get_default_rate_type(self.company_id),
            manual_rate=self.letter_currency_rate if self.currency_rate_type == 'manualexchange' else None,
        )
        balance_amount = company_currency.round(amount * inverse_rate)
        foreign_amount = self.currency_id.round(amount)
        return {
            'balance_amount': balance_amount,
            'foreign_currency_id': self.currency_id.id,
            'debit_amount_currency': foreign_amount,
            'credit_amount_currency': -foreign_amount,
        }

    def _get_account_by_code(self, code, purpose, require_nazim=False, allow_prefix=False):
        self.ensure_one()
        account_model = self.env['account.account'].with_company(self.company_id)
        base_domain = []
        if 'company_ids' in account_model._fields:
            base_domain.append(('company_ids', 'in', self.company_id.id))
        if 'deprecated' in account_model._fields:
            base_domain.append(('deprecated', '=', False))
        else:
            # Odoo 19+: deprecated field kaldırıldı, active kullan
            base_domain.append(('active', '=', True))

        domain = [('code', '=', code), *base_domain]

        account = account_model.search(domain, limit=1)
        if not account and allow_prefix:
            prefix_domain = [('code', '=like', f'{code}%'), *base_domain]
            account = account_model.search(prefix_domain, order='code asc', limit=1)

        if not account:
            code_label = _('%(code)s veya %(code)s*', code=code) if allow_prefix else code
            raise UserError(_(
                "%(company)s şirketinde %(purpose)s için %(code)s kodlu hesap bulunamadı.",
                company=self.company_id.display_name,
                purpose=purpose,
                code=code_label,
            ))

        if require_nazim and not (account.code or '').startswith('9'):
            raise UserError(_(
                "%(purpose)s için seçilen hesap 9 ile başlamalıdır. Bulunan hesap: %(code)s",
                purpose=purpose,
                code=account.code,
            ))
        return account

    def _get_memo_accounts(self, *, reverse=False):
        self.ensure_one()

        if self.letter_party_type == 'given':
            opening_debit_code, opening_credit_code = '903', '902'
            opening_debit_purpose = _('Verilen mektup nazım borç hesabı')
            opening_credit_purpose = _('Verilen mektup nazım alacak hesabı')
        else:
            opening_debit_code, opening_credit_code = '900', '901'
            opening_debit_purpose = _('Alınan mektup nazım borç hesabı')
            opening_credit_purpose = _('Alınan mektup nazım alacak hesabı')

        if reverse:
            opening_debit_code, opening_credit_code = opening_credit_code, opening_debit_code
            opening_debit_purpose, opening_credit_purpose = opening_credit_purpose, opening_debit_purpose

        debit_account = self._get_account_by_code(
            opening_debit_code,
            opening_debit_purpose,
            require_nazim=True,
            allow_prefix=True,
        )
        credit_account = self._get_account_by_code(
            opening_credit_code,
            opening_credit_purpose,
            require_nazim=True,
            allow_prefix=True,
        )
        return debit_account, credit_account

    def _get_misc_journal(self):
        self.ensure_one()
        journal = self.env['account.journal'].search([
            ('company_id', '=', self.company_id.id),
            ('type', '=', 'general'),
        ], limit=1)
        if not journal:
            raise UserError(_(
                "%(company)s şirketi için bir Genel Yevmiye (type=general) bulunamadı.",
                company=self.company_id.display_name,
            ))
        return journal

    def _ensure_nazim_accounts(self, debit_account, credit_account):
        """Nazım fişleri sadece 9* hesaplarla çalışmalıdır."""
        self.ensure_one()
        invalid_accounts = [
            account for account in (debit_account, credit_account)
            if not (account.code or '').startswith('9')
        ]
        if invalid_accounts:
            invalid_list = ', '.join(
                f"{account.code} ({account.display_name})" for account in invalid_accounts
            )
            raise UserError(_(
                "Nazım kayıtlar yalnızca 9 ile başlayan hesap kodlarına atılabilir. "
                "Uygun olmayan hesap(lar): %(accounts)s",
                accounts=invalid_list,
            ))

    def _build_memorandum_move_vals(self, *, reverse=False):
        self.ensure_one()
        debit_account, credit_account = self._get_memo_accounts(reverse=reverse)
        journal = self._get_misc_journal()
        self._ensure_nazim_accounts(debit_account, credit_account)
        direction = _('İade Ters Kayıt') if reverse else _('Aktifleştirme Kaydı')
        move_date = self._get_move_date()
        amounts = self._prepare_line_amounts(self.amount, move_date)

        line_label = _(
            '%(name)s - %(direction)s (%(partner)s)',
            name=self.name,
            direction=direction,
            partner=self.beneficiary_partner_id.display_name,
        )
        extra_vals = self._get_move_extra_vals()

        return {
            'move_type': 'entry',
            'date': move_date,
            'journal_id': journal.id,
            'company_id': self.company_id.id,
            'ref': _('%(name)s / %(letter)s', name=self.name, letter=self.letter_no or ''),
            **extra_vals,
            'line_ids': [
                (0, 0, {
                    'name': line_label,
                    'account_id': debit_account.id,
                    'debit': amounts['balance_amount'],
                    'credit': 0.0,
                    'currency_id': amounts['foreign_currency_id'],
                    'amount_currency': amounts['debit_amount_currency'],
                }),
                (0, 0, {
                    'name': line_label,
                    'account_id': credit_account.id,
                    'debit': 0.0,
                    'credit': amounts['balance_amount'],
                    'currency_id': amounts['foreign_currency_id'],
                    'amount_currency': amounts['credit_amount_currency'],
                }),
            ],
        }

    def _create_memorandum_entry_for_active(self):
        self.ensure_one()
        if self.journal_entry_id and self.journal_entry_id.state != 'cancel':
            return

        move = self.env['account.move'].create(self._build_memorandum_move_vals(reverse=False))
        move.action_post()
        self.journal_entry_id = move.id
        self.journal_entry_create_date = fields.Datetime.now()

    def _create_memorandum_reverse_entry(self):
        self.ensure_one()
        if self.return_journal_entry_id and self.return_journal_entry_id.state != 'cancel':
            return

        reverse_move = self.env['account.move'].create(self._build_memorandum_move_vals(reverse=True))
        reverse_move.action_post()
        self.return_journal_entry_id = reverse_move.id

    def _create_financial_entry(self, *, debit_code, credit_code, amount, ref_suffix, purpose_debit, purpose_credit):
        self.ensure_one()
        if amount <= 0:
            return False

        journal = self._get_misc_journal()
        move_date = self._get_move_date()
        amounts = self._prepare_line_amounts(amount, move_date)
        debit_account = self._get_account_by_code(
            debit_code,
            purpose_debit,
            require_nazim=False,
            allow_prefix=True,
        )
        credit_account = self._get_account_by_code(
            credit_code,
            purpose_credit,
            require_nazim=False,
            allow_prefix=True,
        )
        line_label = _(
            '%(name)s - %(suffix)s (%(partner)s)',
            name=self.name,
            suffix=ref_suffix,
            partner=self.beneficiary_partner_id.display_name,
        )

        move_vals = {
            'move_type': 'entry',
            'date': move_date,
            'journal_id': journal.id,
            'company_id': self.company_id.id,
            'ref': _('%(name)s / %(suffix)s', name=self.name, suffix=ref_suffix),
            **self._get_move_extra_vals(),
            'line_ids': [
                (0, 0, {
                    'name': line_label,
                    'account_id': debit_account.id,
                    'debit': amounts['balance_amount'],
                    'credit': 0.0,
                    'currency_id': amounts['foreign_currency_id'],
                    'amount_currency': amounts['debit_amount_currency'],
                }),
                (0, 0, {
                    'name': line_label,
                    'account_id': credit_account.id,
                    'debit': 0.0,
                    'credit': amounts['balance_amount'],
                    'currency_id': amounts['foreign_currency_id'],
                    'amount_currency': amounts['credit_amount_currency'],
                }),
            ],
        }
        move = self.env['account.move'].create(move_vals)
        move.action_post()
        return move

    def _create_commission_entry(self):
        self.ensure_one()
        if self.commission_journal_entry_id and self.commission_journal_entry_id.state != 'cancel':
            return
        move = self._create_financial_entry(
            debit_code='780',
            credit_code='102',
            amount=self.commission_amount,
            ref_suffix=_('Komisyon Kaydı'),
            purpose_debit=_('Komisyon gider hesabı'),
            purpose_credit=_('Komisyon ödeme hesabı'),
        )
        if move:
            self.commission_journal_entry_id = move.id

    def _create_blockage_entry(self):
        self.ensure_one()
        if self.blockage_journal_entry_id and self.blockage_journal_entry_id.state != 'cancel':
            return
        if not self.has_blockage:
            return
        move = self._create_financial_entry(
            debit_code='126',
            credit_code='102',
            amount=self.blockage_amount,
            ref_suffix=_('Blokaj Kaydı'),
            purpose_debit=_('Verilen depozito ve teminat hesabı'),
            purpose_credit=_('Blokaj ödeme hesabı'),
        )
        if move:
            self.blockage_journal_entry_id = move.id

    def _create_encash_entry(self):
        self.ensure_one()
        if self.encash_journal_entry_id and self.encash_journal_entry_id.state != 'cancel':
            return

        if self.letter_party_type == 'given':
            debit_code, credit_code = '689', '300'
            ref_suffix = _('Tazmin Kaydı (Lehdar)')
            debit_purpose = _('Tazmin gider hesabı')
            credit_purpose = _('Banka kredileri hesabı')
        else:
            debit_code, credit_code = '100', '679'
            ref_suffix = _('Tazmin Kaydı (Muhatap)')
            debit_purpose = _('Tahsilat kasa hesabı')
            credit_purpose = _('Diğer olağandışı gelir ve karlar hesabı')

        move = self._create_financial_entry(
            debit_code=debit_code,
            credit_code=credit_code,
            amount=self.amount,
            ref_suffix=ref_suffix,
            purpose_debit=debit_purpose,
            purpose_credit=credit_purpose,
        )
        if move:
            self.encash_journal_entry_id = move.id

    def action_open_journal_entry(self):
        self.ensure_one()
        if not self.journal_entry_id:
            raise UserError(_("Bu kayıt için henüz yevmiye kaydı oluşturulmamış."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Yevmiye Kaydı'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.journal_entry_id.id,
            'target': 'current',
        }

    def _get_reminder_emails(self):
        self.ensure_one()
        emails = []

        if self.reminder_email_to:
            for email in self.reminder_email_to.replace(';', ',').split(','):
                clean_email = email.strip()
                if clean_email:
                    emails.append(clean_email)

        if self.reminder_user_id and self.reminder_user_id.email:
            emails.append(self.reminder_user_id.email.strip())

        # Tekrarları korumadan kaldır
        return list(dict.fromkeys(emails))

    def _is_reminder_day_enabled(self, days):
        self.ensure_one()
        day_map = {
            7: self.reminder_day_7,
            15: self.reminder_day_15,
            30: self.reminder_day_30,
        }
        return bool(day_map.get(days))

    def _queue_initial_notification_email(self):
        self.ensure_one()
        emails = self._get_reminder_emails()
        if not emails:
            return False

        enabled_days = []
        if self.reminder_day_7:
            enabled_days.append('7')
        if self.reminder_day_15:
            enabled_days.append('15')
        if self.reminder_day_30:
            enabled_days.append('30')
        day_text = ', '.join(enabled_days) if enabled_days else '-'

        mail = self.env['mail.mail'].sudo().create({
            'subject': _(
                "Teminat Bilgilendirme Ataması: %(name)s",
                name=self.name,
            ),
            'body_html': _(
                "<p>Merhaba,</p>"
                "<p><strong>%(name)s</strong> numaralı teminat mektubu için "
                "bilgilendirme kişisi olarak tanımlandınız.</p>"
                "<p>Seçilen hatırlatma günleri: %(days)s</p>"
                "<p>Banka: %(bank)s<br/>Muhatap: %(beneficiary)s<br/>"
                "Vade: %(expiry)s</p>",
                name=self.name,
                days=day_text,
                bank=self.bank_partner_id.name,
                beneficiary=self.beneficiary_partner_id.name,
                expiry=self.expiry_date.strftime('%d.%m.%Y') if self.expiry_date else '-',
            ),
            'email_to': ','.join(emails),
            'auto_delete': False,
            'model': 'guarantee.letter',
            'res_id': self.id,
        })
        mail.with_context(force_send=True).send(raise_exception=False)
        return mail.state == 'sent'

    def _send_initial_notification_if_needed(self):
        for rec in self:
            if rec.intro_notification_sent:
                continue
            if not (rec.reminder_day_7 or rec.reminder_day_15 or rec.reminder_day_30):
                continue
            if not rec._get_reminder_emails():
                continue

            if rec._queue_initial_notification_email():
                rec.intro_notification_sent = True

    def action_send_notification_setup_email(self):
        self.ensure_one()
        if not (self.reminder_day_7 or self.reminder_day_15 or self.reminder_day_30):
            raise UserError(_("Lütfen en az bir hatırlatma günü seçin (7/15/30)."))
        if not self._get_reminder_emails():
            raise UserError(_("Lütfen hatırlatma kullanıcısı veya bilgilendirme e-posta adresi girin."))

        sent = self._queue_initial_notification_email()
        if sent:
            self.intro_notification_sent = True
            self.message_post(body=_("Bilgilendirme atama e-postası gönderildi."))
        else:
            self.message_post(body=_("Bilgilendirme atama e-postası gönderim denemesi başarısız oldu."))

    def _queue_expiry_reminder_email(self, days):
        self.ensure_one()
        emails = self._get_reminder_emails()
        if not emails:
            return False

        body_html = _(
            "<p>%(name)s numaralı teminat mektubunun vadesine "
            "<strong>%(days)s gün</strong> kalmıştır.</p>"
            "<p>Banka: %(bank)s<br/>Muhatap: %(beneficiary)s<br/>"
            "Tutar: %(amount)s<br/>Vade: %(expiry)s</p>",
            name=self.name,
            days=days,
            bank=self.bank_partner_id.name,
            beneficiary=self.beneficiary_partner_id.name,
            amount=f"{self.amount:,.2f}",
            expiry=self.expiry_date.strftime('%d.%m.%Y'),
        )
        mail = self.env['mail.mail'].sudo().create({
            'subject': _(
                "Teminat Mektubu Vade Hatırlatması: %(name)s (%(days)s gün)",
                name=self.name,
                days=days,
            ),
            'body_html': body_html,
            'email_to': ','.join(emails),
            'auto_delete': False,
            'model': 'guarantee.letter',
            'res_id': self.id,
        })
        mail.with_context(force_send=True).send(raise_exception=False)
        return mail.state == 'sent'

    # ── Cron: Vade Hatırlatıcı ──
    @api.model
    def cron_expiry_reminder(self):
        """30, 15 ve 7 gün kala hatırlatma activity'si oluştur"""
        today = fields.Date.context_today(self)
        reminder_days = [30, 15, 7]

        for days in reminder_days:
            target_date = today + relativedelta(days=days)
            letters = self.search([
                ('state', '=', 'active'),
                ('expiry_date', '=', target_date),
            ])
            for letter in letters:
                if not letter._is_reminder_day_enabled(days):
                    continue
                # Aynı gün için zaten activity varsa tekrar oluşturma
                existing = self.env['mail.activity'].search([
                    ('res_model', '=', 'guarantee.letter'),
                    ('res_id', '=', letter.id),
                    ('summary', 'like', f'{days} gün'),
                ], limit=1)
                if not existing:
                    reminder_user = letter.reminder_user_id or letter.responsible_id or self.env.user
                    letter.activity_schedule(
                        'mail.mail_activity_data_warning',
                        date_deadline=today,
                        summary=_("Teminat mektubu vadesine %s gün kaldı") % days,
                        note=_(
                            "<p>%(name)s numaralı teminat mektubunun vadesine "
                            "<strong>%(days)s gün</strong> kalmıştır.</p>"
                            "<p>Banka: %(bank)s<br/>Lehtar: %(beneficiary)s<br/>"
                            "Tutar: %(amount)s<br/>Vade: %(expiry)s</p>",
                            name=letter.name,
                            days=days,
                            bank=letter.bank_partner_id.name,
                            beneficiary=letter.beneficiary_partner_id.name,
                            amount=f"{letter.amount:,.2f}",
                            expiry=letter.expiry_date.strftime('%d.%m.%Y'),
                        ),
                        user_id=reminder_user.id,
                    )
                    letter._queue_expiry_reminder_email(days)
                    _logger.info(
                        "Teminat mektubu hatırlatması: %s - %s gün kala",
                        letter.name, days,
                    )


class GuaranteeLetterType(models.Model):
    _name = 'guarantee.letter.type'
    _description = 'Teminat Türü'
    _order = 'sequence, id'

    name = fields.Char(string='Teminat Türü', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
