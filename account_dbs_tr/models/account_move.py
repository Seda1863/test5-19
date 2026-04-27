# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    dbs_invoice_partner_id = fields.Many2one(
        'res.partner',
        related='partner_id.commercial_partner_id',
        readonly=True,
        string='DBS Fatura Musteisi',
    )

    dbs_send_contract_id = fields.Many2one(
        'dbs.contract',
        string='DBS Gonderim Sozlesmesi',
        copy=False,
        domain="[('active', '=', True), ('company_id', '=', company_id), ('contact_id', '=', dbs_invoice_partner_id)]",
    )

    dbs_contract_id = fields.Many2one('dbs.contract', string='DBS Sozlesmesi', copy=False, readonly=True)
    dbs_source_move_id = fields.Many2one('account.move', string='DBS Kaynak Fatura', copy=False, readonly=True)
    dbs_batch_line_id = fields.Many2one('dbs.batch.line', string='DBS Batch Satiri', copy=False, readonly=True)
    dbs_entry_type = fields.Selection([
        ('settlement', 'Tahsilat'),
        ('commission', 'Komisyon'),
    ], string='DBS Yevmiye Tipi', copy=False, readonly=True)
    dbs_fee_amount = fields.Monetary(string='DBS Komisyon Tutari', currency_field='currency_id', copy=False, readonly=True)
    dbs_fee_rate = fields.Float(string='DBS Komisyon Orani (%)', copy=False, readonly=True)

    dbs_state = fields.Selection([
        ('none', 'Yok'),
        ('to_send', 'Gonderime Hazir'),
        ('sent', 'Gonderildi'),
        ('accepted', 'Onaylandi'),
        ('rejected', 'Reddedildi'),
        ('settled', 'Kapatildi'),
    ], compute='_compute_dbs_info', string='DBS Durumu')
    dbs_line_ref = fields.Char(compute='_compute_dbs_info', string='DBS Ref')
    dbs_line_count = fields.Integer(compute='_compute_dbs_info', string='DBS Kayit Sayisi')
    dbs_batch_count = fields.Integer(compute='_compute_dbs_info', string='DBS Toplu Islem Sayisi')
    dbs_batch_id = fields.Many2one('dbs.batch', compute='_compute_dbs_info', string='DBS Toplu Islem')
    dbs_history = fields.Text(compute='_compute_dbs_info', string='DBS Tarihcesi')
    dbs_send_allowed = fields.Boolean(compute='_compute_dbs_send_allowed', string='DBS Gonderime Uygun')
    dbs_button_visible = fields.Boolean(compute='_compute_dbs_button_visible', string='DBS Butonu Gorunsun')
    dbs_eligible_label = fields.Selection([
        ('eligible', "DBS'ye Uygun"),
        ('no_contract', 'Sozlesme Secilmedi'),
        ('contract_mismatch', 'Sozlesme-Musteri Uyusmuyor'),
        ('partner_inactive', 'Musteri DBS Aktif Degil'),
        ('already_sent', 'Zaten Gonderildi'),
        ('not_applicable', '-'),
    ], compute='_compute_dbs_eligible_label', string='DBS Uygunluk')

    @api.depends('state', 'payment_state')
    def _compute_dbs_info(self):
        line_model = self.env['dbs.batch.line']
        for move in self:
            lines = line_model.search([('move_id', '=', move.id)], limit=1, order='id desc')
            history_lines = line_model.search([('move_id', '=', move.id)], order='id desc', limit=10)
            move.dbs_line_count = line_model.search_count([('move_id', '=', move.id)])
            move.dbs_batch_count = line_model.search_count([('move_id', '=', move.id), ('batch_id', '!=', False)])
            if lines:
                move.dbs_state = lines.state
                move.dbs_line_ref = lines.dbs_line_ref
                move.dbs_batch_id = lines.batch_id.id
            else:
                move.dbs_state = 'none'
                move.dbs_line_ref = False
                move.dbs_batch_id = False

            if history_lines:
                chunks = []
                for line in history_lines:
                    chunks.append('%s | %s | %s' % (
                        (line.create_date and fields.Datetime.to_string(line.create_date)) or '-',
                        line.dbs_line_ref or '-',
                        line.state or '-',
                    ))
                move.dbs_history = '\n'.join(chunks)
            else:
                move.dbs_history = False

    @api.depends(
        'move_type',
        'state',
        'payment_state',
        'partner_id',
        'partner_id.dbs_enabled',
        'partner_id.dbs_status',
        'partner_id.commercial_partner_id',
        'dbs_send_contract_id',
        'dbs_send_contract_id.contact_id',
        'dbs_send_contract_id.active',
        'dbs_line_count',
    )
    def _compute_dbs_send_allowed(self):
        line_model = self.env['dbs.batch.line']
        for move in self:
            allowed = (
                move.move_type == 'out_invoice'
                and move.state == 'posted'
                and move.payment_state in ('not_paid', 'partial')
            )

            partner = move.partner_id.commercial_partner_id
            if (
                not partner
                or not partner.dbs_enabled
                or partner.dbs_status != 'active'
            ):
                allowed = False

            contract = move.dbs_send_contract_id
            if not contract or not contract.active:
                allowed = False

            if allowed:
                existing = line_model.search_count([
                    ('move_id', '=', move.id),
                    ('state', 'in', ('to_send', 'sent', 'accepted', 'settled')),
                ])
                if existing:
                    allowed = False

            move.dbs_send_allowed = allowed

    @api.depends('move_type', 'state', 'payment_state', 'dbs_line_count')
    def _compute_dbs_button_visible(self):
        for move in self:
            move.dbs_button_visible = (
                move.move_type == 'out_invoice'
                and move.state == 'posted'
                and move.payment_state in ('not_paid', 'partial')
                and move.dbs_line_count == 0
            )

    @api.depends(
        'move_type', 'state', 'payment_state',
        'partner_id', 'partner_id.dbs_enabled', 'partner_id.dbs_status',
        'partner_id.commercial_partner_id',
        'dbs_send_contract_id', 'dbs_send_contract_id.contact_id', 'dbs_send_contract_id.active',
        'dbs_line_count',
    )
    def _compute_dbs_eligible_label(self):
        line_model = self.env['dbs.batch.line']
        for move in self:
            if (
                move.move_type != 'out_invoice'
                or move.state != 'posted'
                or move.payment_state not in ('not_paid', 'partial')
            ):
                move.dbs_eligible_label = 'not_applicable'
                continue

            partner = move.partner_id.commercial_partner_id
            if not partner or not partner.dbs_enabled or partner.dbs_status != 'active':
                move.dbs_eligible_label = 'partner_inactive'
                continue

            contract = move.dbs_send_contract_id
            if not contract or not contract.active:
                move.dbs_eligible_label = 'no_contract'
                continue

            if contract.contact_id and contract.contact_id != partner:
                move.dbs_eligible_label = 'contract_mismatch'
                continue

            existing = line_model.search_count([
                ('move_id', '=', move.id),
                ('state', 'in', ('to_send', 'sent', 'accepted', 'settled')),
            ])
            if existing:
                move.dbs_eligible_label = 'already_sent'
                continue

            move.dbs_eligible_label = 'eligible'

    @api.onchange('partner_id')
    def _onchange_partner_id_reset_dbs_contract(self):
        for move in self:
            partner = move.partner_id.commercial_partner_id
            if not partner:
                move.dbs_send_contract_id = False
                continue

            contracts = self.env['dbs.contract'].search([
                ('active', '=', True),
                ('company_id', '=', move.company_id.id),
                ('contact_id', '=', partner.id),
            ], order='id desc')
            move.dbs_send_contract_id = contracts[:1].id if len(contracts) == 1 else False

    def action_send_to_dbs(self):
        self.ensure_one()

        if self.state != 'posted':
            raise UserError(_('Fatura onaylanmadan DBS\'ye gonderilemez.'))
        if self.payment_state not in ('not_paid', 'partial'):
            raise UserError(_('Bu fatura zaten odenmis, DBS\'ye gonderilemez.'))

        # DBS akisi yalnizca banka odeme yontemi ile calisir.
        if 'payment_method' in self._fields and self.payment_method and self.payment_method != 'bank':
            raise UserError(_('DBS gonderimi icin Odeme Yontemi "Banka" olmalidir.'))
        if 'payment_method' in self._fields and not self.payment_method:
            raise UserError(_('DBS gonderimi icin once Odeme Yontemi secin. Odeme Yontemi "Banka" olmalidir.'))

        partner = self.partner_id.commercial_partner_id
        if not partner.dbs_enabled:
            raise UserError(_('Musteri icin DBS aktif degil. Musteri kaydinda DBS\'yi etkinlestirin.'))
        if partner.dbs_status != 'active':
            raise UserError(_('Musteri DBS durumu aktif degil (mevcut durum: %s).') % partner.dbs_status)

        existing = self.env['dbs.batch.line'].search_count([
            ('move_id', '=', self.id),
            ('state', 'in', ('to_send', 'sent', 'accepted', 'settled')),
        ])
        if existing:
            raise UserError(_('Bu fatura zaten acik bir DBS satirinda mevcut.'))

        contract = self.dbs_send_contract_id
        if not contract:
            raise UserError(_('Lutfen DBS sozlesmesi secin.'))
        if not contract.active:
            raise UserError(_('Secilen DBS sozlesmesi aktif degil.'))
        if contract.contact_id and contract.contact_id != partner:
            raise UserError(_('Secilen DBS sozlesmesi bu faturanin musteri kaydi ile uyusmuyor.'))

        profile_action = self._open_dbs_profile_wizard_if_needed(partner, contract)
        if profile_action:
            return profile_action

        risk_info = self._get_dbs_risk_info(contract)
        risk_policy = partner.dbs_risk_control or 'continue'
        if risk_info['is_exceeded'] and risk_policy == 'block':
            raise UserError(_(
                'DBS risk limiti asildi. Islem durduruldu.\n'
                'Limit: %(limit).2f\n'
                'Kullanilabilir: %(available).2f\n'
                'Islem Tutari: %(required).2f\n'
                'Asim: %(over).2f'
            ) % risk_info)

        if risk_info['is_exceeded'] and risk_policy == 'warn' and not self.env.context.get('dbs_risk_confirmed'):
            wiz = self.env['dbs.risk.confirm.wizard'].create({
                'move_id': self.id,
                'contract_id': contract.id,
                'partner_id': partner.id,
                'currency_id': self.currency_id.id,
                'limit_amount': risk_info['limit'],
                'available_amount': risk_info['available'],
                'required_amount': risk_info['required'],
                'over_amount': risk_info['over'],
                'message': _(
                    'DBS risk limiti asiliyor. Isleme devam etmek istiyor musunuz?\n\n'
                    'Limit: %(limit).2f\n'
                    'Kullanilabilir: %(available).2f\n'
                    'Islem Tutari: %(required).2f\n'
                    'Asim: %(over).2f'
                ) % risk_info,
            })
            return {
                'type': 'ir.actions.act_window',
                'name': _('DBS Risk Uyarisi'),
                'res_model': 'dbs.risk.confirm.wizard',
                'view_mode': 'form',
                'res_id': wiz.id,
                'target': 'new',
            }

        batch = self.env['dbs.batch'].create({'contract_id': contract.id})
        batch._add_invoices(self)
        return {
            'type': 'ir.actions.act_window',
            'name': _('DBS Toplu Islem'),
            'res_model': 'dbs.batch',
            'view_mode': 'form',
            'res_id': batch.id,
            'target': 'current',
        }

    def _open_dbs_profile_wizard_if_needed(self, partner, contract):
        self.ensure_one()
        if self.env.context.get('dbs_profile_confirmed'):
            return False

        needs_customer_code = not bool((partner.dbs_customer_code or '').strip())
        needs_limit = (partner.dbs_limit or 0.0) <= 0.0
        missing_labels = []
        if needs_customer_code:
            missing_labels.append(_('DBS Musteri Kodu'))
        if needs_limit:
            missing_labels.append(_('DBS Ic Limit'))

        # Limit/risk ayarlari kullanici tarafindan gonderim aninda secilebilsin.
        # Eksik alan yoksa da wizard onay/duzenleme ekrani olarak acilir.
        message_text = (
            _('DBS gonderimi oncesi limit ve risk kontrol bilgilerini onaylayin/guncelleyin.')
            if not missing_labels
            else _('DBS gonderimi icin eksik bilgiler var: %(fields)s') % {
                'fields': ', '.join(missing_labels)
            }
        )

        wiz = self.env['dbs.profile.confirm.wizard'].create({
            'move_id': self.id,
            'partner_id': partner.id,
            'contract_id': contract.id,
            'currency_id': self.currency_id.id,
            'dbs_customer_code': partner.dbs_customer_code or '',
            'dbs_limit': partner.dbs_limit or 0.0,
            'dbs_risk_control': partner.dbs_risk_control or 'continue',
            'message': message_text,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('DBS Bilgilerini Tamamla'),
            'res_model': 'dbs.profile.confirm.wizard',
            'view_mode': 'form',
            'res_id': wiz.id,
            'target': 'new',
        }

    def _get_dbs_risk_info(self, contract):
        self.ensure_one()
        partner = self.partner_id.commercial_partner_id
        limit_amount = partner.dbs_limit or 0.0

        open_lines = self.env['dbs.batch.line'].search([
            ('partner_id', '=', partner.id),
            ('state', 'in', ('to_send', 'sent', 'accepted')),
            ('contract_id', '=', contract.id),
        ])
        used_amount = sum(open_lines.mapped('amount'))
        available_amount = limit_amount - used_amount
        required_amount = self.amount_residual or 0.0
        over_amount = max(required_amount - available_amount, 0.0)
        return {
            'limit': limit_amount,
            'available': available_amount,
            'required': required_amount,
            'over': over_amount,
            'is_exceeded': over_amount > 0,
        }

    def action_view_dbs_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('DBS Geçmişi'),
            'res_model': 'dbs.batch.line',
            'view_mode': 'list,form',
            'domain': [('move_id', '=', self.id)],
            'target': 'current',
        }

    def action_open_dbs_batch(self):
        self.ensure_one()
        if not self.dbs_batch_id:
            raise UserError(_('Bu faturaya bagli DBS toplu islem kaydi yok.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('DBS Toplu Islem'),
            'res_model': 'dbs.batch',
            'view_mode': 'form',
            'res_id': self.dbs_batch_id.id,
            'target': 'current',
        }

    def action_open_dbs_contract(self):
        self.ensure_one()
        contract = self.dbs_contract_id or self.dbs_send_contract_id
        if not contract:
            raise UserError(_('Bu faturaya bagli DBS sozlesmesi yok.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('DBS Sozlesmesi'),
            'res_model': 'dbs.contract',
            'view_mode': 'form',
            'res_id': contract.id,
            'target': 'current',
        }
