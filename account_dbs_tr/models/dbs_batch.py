# -*- coding: utf-8 -*-
import base64
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, MissingError, UserError


class DbsBatch(models.Model):
    _name = 'dbs.batch'
    _description = 'DBS Toplu Islem'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(default='New', copy=False, required=True)
    date = fields.Date(default=fields.Date.context_today, required=True)
    contract_id = fields.Many2one('dbs.contract', string='DBS Sozlesmesi', required=True)
    company_id = fields.Many2one(related='contract_id.company_id', store=True)
    currency_id = fields.Many2one(related='contract_id.currency_id', store=True)
    bank_partner_id = fields.Many2one(related='contract_id.bank_partner_id', store=True)

    state = fields.Selection([
        ('draft', 'Taslak'),
        ('sent', 'Gonderildi'),
        ('ack', 'ACK Alindi'),
        ('settled', 'Kapatildi'),
        ('closed', 'Kapandi'),
        ('cancel', 'Iptal Edildi'),
    ], default='draft', required=True, tracking=True)

    bank_reference = fields.Char(string='Banka Referansi')
    export_file = fields.Binary(string='Export Dosyasi', attachment=True)
    export_filename = fields.Char(string='Export Dosya Adi')
    ack_file = fields.Binary(string='ACK Dosyasi', attachment=True)
    ack_filename = fields.Char(string='ACK Dosya Adi')

    sent_at = fields.Datetime()
    ack_at = fields.Datetime()
    settled_at = fields.Datetime()

    line_ids = fields.One2many('dbs.batch.line', 'batch_id', string='Satirlar')
    total_amount = fields.Monetary(compute='_compute_totals', currency_field='currency_id', string='Toplam Tutar')
    line_count = fields.Integer(compute='_compute_totals', string='Satir Sayisi')
    invoice_count = fields.Integer(compute='_compute_totals', string='Fatura Sayisi')
    line_refs_text = fields.Text(compute='_compute_line_overview', string='DBS Satir Refleri')
    customers_text = fields.Text(compute='_compute_line_overview', string='Musteriler')
    invoices_text = fields.Text(compute='_compute_line_overview', string='Faturalar')
    due_dates_text = fields.Text(compute='_compute_line_overview', string='Vadeler')
    amounts_text = fields.Text(compute='_compute_line_overview', string='Tutarlar')
    line_states_text = fields.Text(compute='_compute_line_overview', string='Durumlar')
    reject_codes_text = fields.Text(compute='_compute_line_overview', string='Ret Kodlari')
    messages_text = fields.Text(compute='_compute_line_overview', string='Mesajlar')

    @api.depends('line_ids.amount')
    def _compute_totals(self):
        for rec in self:
            rec.total_amount = sum(rec.line_ids.mapped('amount'))
            rec.line_count = len(rec.line_ids)
            rec.invoice_count = len(rec.line_ids.mapped('move_id'))

    @api.depends(
        'line_ids.dbs_line_ref',
        'line_ids.partner_id',
        'line_ids.move_id',
        'line_ids.due_date',
        'line_ids.amount',
        'line_ids.state',
        'line_ids.reject_code',
        'line_ids.last_message',
    )
    def _compute_line_overview(self):
        state_labels = dict(self.env['dbs.batch.line']._fields['state'].selection)
        for rec in self:
            lines = rec.line_ids.sorted('id')
            rec.line_refs_text = '\n'.join([(val or '') for val in lines.mapped('dbs_line_ref')])
            rec.customers_text = '\n'.join([(val or '') for val in lines.mapped('partner_id.display_name')])
            # Use stored invoice_name to avoid account.move read access issues in multi-company users.
            rec.invoices_text = '\n'.join([(val or '') for val in lines.mapped('invoice_name')])
            rec.due_dates_text = '\n'.join(
                [fields.Date.to_string(d) if d else '' for d in lines.mapped('due_date')]
            )
            rec.amounts_text = '\n'.join([str(v) for v in lines.mapped('amount')])
            rec.line_states_text = '\n'.join([state_labels.get(st, st) for st in lines.mapped('state')])
            rec.reject_codes_text = '\n'.join([(val or '') for val in lines.mapped('reject_code')])
            rec.messages_text = '\n'.join([(val or '') for val in lines.mapped('last_message')])

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('dbs.batch') or 'New'
        return super().create(vals_list)

    def _log(self, level, message):
        self.env['dbs.message.log'].create({
            'name': f'DBS Batch: {self.name}',
            'level': level,
            'batch_id': self.id,
            'contract_id': self.contract_id.id,
            'model': self._name,
            'res_id': self.id,
            'message': message,
        })

    @api.model
    def _log_contract(self, contract, level, message):
        self.env['dbs.message.log'].create({
            'name': f'DBS Contract: {contract.name}',
            'level': level,
            'batch_id': False,
            'contract_id': contract.id,
            'model': 'dbs.contract',
            'res_id': contract.id,
            'message': message,
        })

    def _refresh_state(self):
        self.ensure_one()
        states = set(self.line_ids.mapped('state'))
        if not states:
            return
        if states.issubset({'settled'}):
            self.state = 'settled'
            self.settled_at = fields.Datetime.now()
        elif any(s in states for s in ('accepted', 'rejected')):
            self.state = 'ack'
        elif states.issubset({'sent', 'accepted', 'rejected', 'settled'}):
            self.state = 'sent'

    def _next_line_ref(self):
        self.ensure_one()
        seq = len(self.line_ids) + 1
        return f'DBS-{self.company_id.id}-{fields.Date.today().strftime("%Y%m%d")}-{seq:05d}'

    def _add_invoices(self, moves):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Sadece draft batch satir ekleyebilir.'))

        new_lines = []
        new_line_refs = []
        seq_counter = len(self.line_ids) + 1
        for move in moves:
            if move.state != 'posted':
                raise UserError(_('%s: Fatura posted olmali.') % (move.display_name,))
            if move.move_type != 'out_invoice':
                raise UserError(_('%s: Sadece musteri faturasi gonderilebilir.') % (move.display_name,))
            if move.payment_state not in ('not_paid', 'partial'):
                raise UserError(_('%s: Fatura odeme durumuna gore DBS uygun degil.') % (move.display_name,))

            partner = move.partner_id.commercial_partner_id
            move_contract = move.dbs_send_contract_id
            if not partner.dbs_enabled or partner.dbs_status != 'active':
                raise UserError(_('%s: Musteri DBS aktif degil.') % (partner.display_name,))
            if not move_contract or move_contract != self.contract_id:
                raise UserError(_('%s: Secilen DBS sozlesmesi bu toplu islem ile uyusmuyor.') % (partner.display_name,))
            if not partner.dbs_customer_code:
                raise UserError(_('%s: DBS musteri kodu bos.') % (partner.display_name,))

            existing = self.env['dbs.batch.line'].search([
                ('move_id', '=', move.id),
                ('state', 'in', ('to_send', 'sent', 'accepted')),
            ], limit=1)
            if existing:
                raise UserError(_('%s: Bu fatura zaten acik bir DBS satirinda mevcut.') % (move.display_name,))

            line_ref = f'DBS-{self.company_id.id}-{fields.Date.today().strftime("%Y%m%d")}-{seq_counter:05d}'
            while self.env['dbs.batch.line'].search_count([('dbs_line_ref', '=', line_ref)]):
                seq_counter += 1
                line_ref = f'DBS-{self.company_id.id}-{fields.Date.today().strftime("%Y%m%d")}-{seq_counter:05d}'

            new_lines.append((0, 0, {
                'dbs_line_ref': line_ref,
                'move_id': move.id,
                'partner_id': partner.id,
                'partner_customer_code': partner.dbs_customer_code,
                'currency_id': self.currency_id.id,
                'amount': move.amount_residual,
                'due_date': move.invoice_date_due,
                'state': 'to_send',
            }))
            new_line_refs.append(line_ref)
            seq_counter += 1

        if new_lines:
            self.write({'line_ids': new_lines})

            # As soon as DBS lines are prepared, create draft journal entries
            # from contract accounting definitions (settlement + optional commission).
            created_lines = self.line_ids.filtered(lambda l: l.dbs_line_ref in new_line_refs)
            for line in created_lines:
                self.contract_id._create_settlement_entries_from_dbs_line(line)

    def _split_sendable_lines(self, lines):
        self.ensure_one()
        sendable_lines = self.env['dbs.batch.line']
        skipped_lines = self.env['dbs.batch.line']
        for line in lines:
            try:
                line.move_id.check_access_rights('read')
                line.move_id.check_access_rule('read')
                _ = line.move_id.display_name
                sendable_lines |= line
            except (AccessError, MissingError):
                skipped_lines |= line
        return sendable_lines, skipped_lines

    def _apply_ack_rows(self, result_lines, source_name=False):
        self.ensure_one()
        stats = {
            'accepted': 0,
            'rejected': 0,
            'settled': 0,
            'unmatched': 0,
            'invalid': 0,
        }

        if not result_lines:
            self._log('warning', 'ACK dosyasinda islenecek satir bulunamadi.')
            self.ack_at = fields.Datetime.now()
            return stats

        for row in result_lines:
            ref = (row.get('dbs_line_ref') or '').strip()
            if not ref:
                stats['invalid'] += 1
                self._log('warning', 'ACK satirinda line_ref bos gecildi.')
                continue

            line = self.line_ids.filtered(lambda l: l.dbs_line_ref == ref)[:1]
            if not line:
                stats['unmatched'] += 1
                self._log('warning', f'ACK satiri eslesmedi: {ref}')
                continue

            status = (row.get('status') or '').strip().lower()
            vals = {
                'last_message': row.get('message') or False,
            }
            if status == 'accepted':
                vals.update({
                    'state': 'accepted',
                    'reject_code': False,
                })
                stats['accepted'] += 1
            elif status == 'rejected':
                vals.update({
                    'state': 'rejected',
                    'reject_code': row.get('reject_code') or False,
                })
                stats['rejected'] += 1
            elif status == 'settled':
                vals.update({
                    'state': 'settled',
                    'reject_code': False,
                    'settled_at': fields.Datetime.now(),
                })
                stats['settled'] += 1
            else:
                stats['invalid'] += 1
                self._log('warning', f'ACK satirinda gecersiz status: {status or "<bos>"}')
                continue
            line.write(vals)

        self.ack_at = fields.Datetime.now()
        self._refresh_state()
        summary = (
            'ACK ozeti - accepted: %(accepted)s, rejected: %(rejected)s, settled: %(settled)s, '
            'unmatched: %(unmatched)s, invalid: %(invalid)s'
        ) % stats
        if source_name:
            summary = f'[{source_name}] {summary}'
        self._log('info', summary)
        return stats

    def action_send(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Sadece draft batch gonderilebilir.'))
            if not rec.line_ids:
                raise UserError(_('Batch satiri yok.'))
            candidate_lines = rec.line_ids.filtered(lambda l: l.state == 'to_send')
            if not candidate_lines:
                raise UserError(_('Gonderilecek to_send durumunda satir bulunamadi.'))

            sendable_lines, skipped_lines = rec._split_sendable_lines(candidate_lines)
            if skipped_lines:
                skipped_lines.write({
                    'state': 'returned',
                    'last_message': _('Gonderimde skip edildi: fatura erisim yetkisi yok.'),
                })
                refs = ', '.join(skipped_lines.mapped('dbs_line_ref')[:20])
                rec._log(
                    'warning',
                    _(
                        'Gonderimde %(count)s satir skip edildi (erisim yok). Ref(ilk 20): %(refs)s'
                    ) % {
                        'count': len(skipped_lines),
                        'refs': refs or '-',
                    }
                )

            if not sendable_lines:
                rec._log('warning', 'Batch gonderimi yapilmadi: tum satirlar erisim nedeniyle skip edildi.')
                continue

            try:
                adapter = rec.contract_id._get_adapter()
                try:
                    result = adapter.export_batch(rec, lines=sendable_lines)
                except TypeError as exc:
                    if "unexpected keyword argument 'lines'" not in str(exc):
                        raise
                    result = adapter.export_batch(rec)
                rec.write({
                    'export_file': result.get('payload'),
                    'export_filename': result.get('filename'),
                    'bank_reference': result.get('bank_reference'),
                    'sent_at': fields.Datetime.now(),
                    'state': 'sent',
                })
                rec._log(
                    'info',
                    'Gonderim ozeti - sent: %(sent)s, skipped(no access): %(skipped)s' % {
                        'sent': len(sendable_lines),
                        'skipped': len(skipped_lines),
                    }
                )
            except Exception as exc:
                rec._log('error', str(exc))
                raise UserError(_('DBS gonderim hatasi: %s') % str(exc))

    def action_import_ack(self):
        for rec in self:
            if not rec.ack_file:
                raise UserError(_('ACK dosyasi yukleyin.'))
            filename = (rec.ack_filename or '').strip().lower()
            if filename and not filename.endswith(('.csv', '.txt')):
                raise UserError(_('ACK dosyasi .csv veya .txt formatinda olmali.'))

            adapter = rec.contract_id._get_adapter()
            try:
                result_lines = adapter.import_ack(rec.contract_id, base64.b64decode(rec.ack_file))
            except Exception as exc:
                rec._log('error', str(exc))
                raise UserError(_('ACK import hatasi: %s') % str(exc))
            rec._apply_ack_rows(result_lines, source_name=rec.ack_filename or 'manual_upload')

    def action_close(self):
        for rec in self:
            rec.state = 'closed'

    def action_cancel(self):
        for rec in self:
            rec.state = 'cancel'

    def action_open_contract(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('DBS Sozlesmesi'),
            'res_model': 'dbs.contract',
            'view_mode': 'form',
            'res_id': self.contract_id.id,
            'target': 'current',
        }

    def action_open_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('DBS Faturalari'),
            'res_model': 'dbs.batch.line',
            'view_mode': 'list,form',
            'domain': [('batch_id', '=', self.id)],
            'target': 'current',
        }

    def action_open_invoices(self):
        self.ensure_one()
        invoice_ids = self.line_ids.mapped('move_id').ids
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
        invoice_ids = self.line_ids.mapped('move_id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Kaynak Faturalar'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', invoice_ids)],
            'target': 'current',
        }

    @api.model
    def cron_create_batch(self):
        moves = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')),
            ('partner_id.dbs_enabled', '=', True),
            ('partner_id.dbs_status', '=', 'active'),
        ])

        for move in moves:
            contract = move.partner_id.commercial_partner_id.dbs_contract_id
            if not contract or not contract.active:
                continue

            existing_lines = self.env['dbs.batch.line'].search([
                ('move_id', '=', move.id),
                ('state', 'in', ('to_send', 'sent', 'accepted')),
            ], limit=1)
            if existing_lines:
                continue

            move.dbs_send_contract_id = contract
            batch = self.create({'contract_id': contract.id})
            try:
                batch._add_invoices(move)
            except UserError as exc:
                batch._log('warning', f'{move.display_name}: {str(exc)}')

    @api.model
    def cron_poll_ack(self):
        open_batches = self.search([
            ('state', 'in', ('sent', 'ack')),
            ('contract_id.active', '=', True),
        ])
        if not open_batches:
            return True

        for contract in open_batches.mapped('contract_id'):
            contract_batches = open_batches.filtered(lambda b: b.contract_id == contract)
            processed_filenames = set(
                contract_batches.filtered(lambda b: b.ack_at and b.ack_filename).mapped('ack_filename')
            )

            try:
                adapter = contract._get_adapter()
                payloads = adapter.fetch_ack_payloads(contract)
            except Exception as exc:
                self._log_contract(contract, 'error', f'cron_poll_ack fetch hatasi: {str(exc)}')
                continue

            if not payloads:
                continue

            for payload in payloads:
                filename = (payload.get('filename') or '').strip() or 'cron_ack.csv'
                content_bytes = payload.get('content_bytes') or b''
                if filename in processed_filenames:
                    self._log_contract(contract, 'warning', f'ACK dosyasi tekrar geldi, skip edildi: {filename}')
                    continue

                try:
                    rows = adapter.import_ack(contract, content_bytes)
                except Exception as exc:
                    self._log_contract(contract, 'error', f'{filename}: ACK parse/import hatasi: {str(exc)}')
                    processed_filenames.add(filename)
                    continue

                if not rows:
                    self._log_contract(contract, 'warning', f'{filename}: ACK satiri bulunamadi.')
                    processed_filenames.add(filename)
                    continue

                rows_by_ref = defaultdict(list)
                invalid_ref_count = 0
                for row in rows:
                    ref = (row.get('dbs_line_ref') or '').strip()
                    if not ref:
                        invalid_ref_count += 1
                        continue
                    rows_by_ref[ref].append(row)

                matched_any_batch = False
                for batch in contract_batches:
                    line_refs = set(batch.line_ids.mapped('dbs_line_ref'))
                    if not line_refs:
                        continue
                    batch_rows = []
                    for line_ref in list(rows_by_ref.keys()):
                        if line_ref in line_refs:
                            batch_rows.extend(rows_by_ref.pop(line_ref))
                    if not batch_rows:
                        continue
                    matched_any_batch = True
                    batch.write({
                        'ack_file': base64.b64encode(content_bytes),
                        'ack_filename': filename,
                    })
                    batch._apply_ack_rows(batch_rows, source_name=f'cron:{filename}')

                unmatched_count = sum(len(items) for items in rows_by_ref.values())
                if invalid_ref_count or unmatched_count or not matched_any_batch:
                    self._log_contract(
                        contract,
                        'warning',
                        (
                            '%(filename)s: cron ACK kismi eslesme. matched_batch=%(matched)s, '
                            'unmatched=%(unmatched)s, invalid_ref=%(invalid)s'
                        ) % {
                            'filename': filename,
                            'matched': 1 if matched_any_batch else 0,
                            'unmatched': unmatched_count,
                            'invalid': invalid_ref_count,
                        },
                    )
                processed_filenames.add(filename)
        return True

class DbsBatchLine(models.Model):
    _name = 'dbs.batch.line'
    _description = 'DBS Batch Line'
    _order = 'id'

    batch_id = fields.Many2one('dbs.batch', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='batch_id.company_id', store=True)
    contract_id = fields.Many2one(related='batch_id.contract_id', store=True, string='DBS Sozlesmesi')
    contract_company_id = fields.Many2one(related='contract_id.company_id', store=True, string='Sozlesme Sirketi')
    batch_state = fields.Selection(related='batch_id.state', store=True, string='Toplu Islem Durumu')
    currency_id = fields.Many2one('res.currency', required=True)

    dbs_line_ref = fields.Char(string='DBS Satir Ref', required=True, index=True)
    move_id = fields.Many2one('account.move', string='Fatura', required=True)
    invoice_name = fields.Char(related='move_id.name', store=True, string='Fatura No')
    partner_id = fields.Many2one('res.partner', string='Musteri', required=True)
    partner_customer_code = fields.Char(string='DBS Musteri Kodu')
    due_date = fields.Date(string='Vade')
    amount = fields.Monetary(currency_field='currency_id', required=True)

    state = fields.Selection([
        ('to_send', 'Gonderime Hazir'),
        ('sent', 'Gonderildi'),
        ('accepted', 'Onaylandi'),
        ('rejected', 'Reddedildi'),
        ('settled', 'Kapatildi'),
        ('returned', 'Iade'),
    ], default='to_send', required=True)

    reject_code = fields.Char(string='Ret Kodu')
    last_message = fields.Char(string='Mesaj')
    settled_at = fields.Datetime()
    retry_count = fields.Integer(string='Yeniden Deneme', default=0)
    last_retry_at = fields.Datetime(string='Son Yeniden Deneme')
    warned_at = fields.Datetime(string='Musteri Uyari Zamani')

    _sql_constraints = [
        ('uniq_dbs_line_ref', 'unique(dbs_line_ref)', 'DBS satir referansi benzersiz olmalidir.'),
    ]

    @api.onchange('move_id')
    def _onchange_move_id(self):
        for line in self:
            move = line.move_id
            if not move:
                continue
            line.partner_id = move.partner_id.commercial_partner_id
            line.due_date = move.invoice_date_due
            line.amount = move.amount_residual
            line.currency_id = move.currency_id or line.batch_id.currency_id
            line.partner_customer_code = line.partner_id.dbs_customer_code

            if line.batch_id and not line.dbs_line_ref:
                line.dbs_line_ref = line.batch_id._next_line_ref()

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        for line in self:
            line.partner_customer_code = line.partner_id.commercial_partner_id.dbs_customer_code

    def action_retry_rejected(self):
        target_lines = self.filtered(lambda l: l.state == 'rejected')
        if not target_lines:
            raise UserError(_('Yeniden deneme icin rejected satir secin.'))

        for line in target_lines:
            line.write({
                'state': 'to_send',
                'reject_code': False,
                'last_message': _('Yeniden deneme icin satir to_send durumuna alindi.'),
                'retry_count': (line.retry_count or 0) + 1,
                'last_retry_at': fields.Datetime.now(),
            })
            if line.batch_id:
                line.batch_id.state = 'draft'
                line.batch_id._log('info', f'{line.dbs_line_ref}: yeniden deneme icin to_send alindi.')
        return True

    def action_open_invoice(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fatura'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
            'target': 'current',
        }

    def action_open_batch(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('DBS Toplu Islem'),
            'res_model': 'dbs.batch',
            'view_mode': 'form',
            'res_id': self.batch_id.id,
            'target': 'current',
        }

    def action_open_contract(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('DBS Sozlesmesi'),
            'res_model': 'dbs.contract',
            'view_mode': 'form',
            'res_id': self.contract_id.id,
            'target': 'current',
        }

    def action_warn_customer(self):
        if not self:
            return True

        for line in self:
            partner = line.partner_id.commercial_partner_id
            body = _(
                'DBS satiri ret/alarm bildirimi: Ref=%(ref)s, Fatura=%(invoice)s, Ret Kodu=%(code)s, Mesaj=%(msg)s'
            ) % {
                'ref': line.dbs_line_ref or '-',
                'invoice': line.invoice_name or '-',
                'code': line.reject_code or '-',
                'msg': line.last_message or '-',
            }
            try:
                partner.message_post(body=body)
            except Exception:
                pass
            line.write({
                'warned_at': fields.Datetime.now(),
                'last_message': _('Musteri uyarildi.'),
            })
            if line.batch_id:
                line.batch_id._log('info', f'{line.dbs_line_ref}: musteri uyarildi.')
        return True

    def action_suspend_customer_profile(self):
        if not self:
            return True

        for line in self:
            partner = line.partner_id.commercial_partner_id
            partner.write({'dbs_status': 'suspended'})
            line.write({'last_message': _('Musteri DBS profili askiya alindi.')})
            if line.batch_id:
                line.batch_id._log('warning', f'{line.dbs_line_ref}: {partner.display_name} DBS profili askiya alindi.')
        return True
