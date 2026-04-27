# -*- coding: utf-8 -*-
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    dbs_batch_line_id = fields.Many2one('dbs.batch.line', string='DBS Satiri', readonly=True)

    def _extract_dbs_ref(self):
        self.ensure_one()
        source = ' '.join(filter(None, [self.payment_ref, self.name, self.ref]))
        match = re.search(r'(DBS-[A-Za-z0-9_-]+)', source or '')
        return match.group(1) if match else False

    def _dbs_try_match(self):
        for line in self:
            if line.dbs_batch_line_id:
                continue
            dbs_ref = line._extract_dbs_ref()
            if not dbs_ref:
                continue

            dbs_line = self.env['dbs.batch.line'].search([
                ('dbs_line_ref', '=', dbs_ref),
                ('state', 'in', ('sent', 'accepted')),
            ], limit=1)
            if not dbs_line:
                continue

            amount = abs(line.amount or 0.0)
            if abs(amount - dbs_line.amount) > 0.01:
                continue

            invoice = dbs_line.move_id
            if invoice.state != 'posted' or invoice.payment_state == 'paid':
                continue

            register_ctx = {
                'active_model': 'account.move',
                'active_ids': invoice.ids,
            }
            wizard = self.env['account.payment.register'].with_context(register_ctx).create({
                'payment_date': line.date or fields.Date.context_today(line),
                'journal_id': line.journal_id.id,
                'amount': min(invoice.amount_residual, amount),
                'communication': dbs_ref,
            })
            wizard.action_create_payments()

            # Tahsilat eslesmesinde DBS taslak yevmiyelerini olustur (tahsilat + komisyon).
            contract = dbs_line.batch_id.contract_id
            if contract and contract.integration_type == 'manual':
                contract._create_settlement_entries_from_dbs_line(dbs_line, statement_line=line)

            dbs_line.write({
                'state': 'settled',
                'settled_at': fields.Datetime.now(),
                'last_message': _('Statement satirindan otomatik eslendi.'),
            })
            line.dbs_batch_line_id = dbs_line.id
            dbs_line.batch_id._refresh_state()

    @api.model
    def cron_dbs_try_match_lines(self):
        candidates = self.search([
            ('is_reconciled', '=', False),
            ('dbs_batch_line_id', '=', False),
        ], order='id desc', limit=500)
        candidates._dbs_try_match()
