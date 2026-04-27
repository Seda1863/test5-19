# -*- coding: utf-8 -*-

import uuid
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MdxEfaturaRetryWizard(models.TransientModel):
    _name = 'mdx.efatura.retry.wizard'
    _description = 'E-Fatura/E-İrsaliye Tekrar Gönderim Sihirbazı'

    invoice_id = fields.Many2one('account.move', string='Fatura')
    picking_id = fields.Many2one('stock.picking', string='İrsaliye')
    transaction_id = fields.Many2one('mdx.efatura.islem', string='Son İşlem')

    error_display = fields.Html('Son Hata', related='transaction_id.error_display', readonly=True)
    can_retry = fields.Boolean('Tekrar Denenebilir', related='transaction_id.can_retry', readonly=True)
    retry_count = fields.Integer('Deneme Sayısı', related='transaction_id.retry_count', readonly=True)

    force_new_uuid = fields.Boolean(
        'Yeni UUID Oluştur', default=True,
        help="Önceki UUID ile çakışma varsa işaretleyin",
    )
    force_new_series = fields.Boolean(
        'Yeni Seri Numarası Al', default=False,
        help="Seri numarası çakışması varsa işaretleyin",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        active_model = self.env.context.get('active_model', 'account.move')

        if active_id:
            if active_model == 'stock.picking':
                picking = self.env['stock.picking'].browse(active_id)
                res['picking_id'] = picking.id
                last_transaction = self.env['mdx.efatura.islem'].search([
                    ('document_ref', '=', 'stock.picking,%d' % picking.id),
                    ('state', 'in', ['error', 'retry_scheduled']),
                ], order='create_date desc', limit=1)
                if last_transaction:
                    res['transaction_id'] = last_transaction.id
            else:
                invoice = self.env['account.move'].browse(active_id)
                res['invoice_id'] = invoice.id
                last_transaction = self.env['mdx.efatura.islem'].search([
                    ('document_ref', '=', 'account.move,%d' % invoice.id),
                    ('state', 'in', ['error', 'retry_scheduled']),
                ], order='create_date desc', limit=1)
                if last_transaction:
                    res['transaction_id'] = last_transaction.id
        return res

    def action_retry(self):
        """Manuel olarak fatura/irsaliyeyi yeniden gönder."""
        self.ensure_one()

        if self.picking_id:
            # E-İrsaliye retry
            if self.force_new_uuid:
                self.picking_id.write({'uuid': str(uuid.uuid4())})
            if self.force_new_series:
                self.picking_id.write({'irsaliye_no': False})
            return self.picking_id.action_send_waybill()

        if self.invoice_id:
            # E-Fatura retry
            if self.force_new_uuid:
                self.invoice_id.write({'uuid': str(uuid.uuid4())})
            if self.force_new_series:
                self.invoice_id.write({'fatura_no': False})
            return self.invoice_id.action_send_einvoice()
