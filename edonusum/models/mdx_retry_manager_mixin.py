# -*- coding: utf-8 -*-

import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MdxRetryManagerMixin(models.AbstractModel):
    _name = 'mdx.retry.manager.mixin'
    _description = 'E-Fatura Tekrar Deneme Yönetimi'

    # Artan bekleme süreleri (dakika): 5dk, 15dk, 1 saat, 4 saat
    RETRY_DELAYS = [5, 15, 60, 240]

    def can_retry_transaction(self, transaction):
        """İşlemin yeniden denenip denemeyeceğini kontrol eder."""
        if not transaction.error_code_id:
            return False
        if not transaction.error_code_id.is_retryable:
            return False
        if transaction.retry_count >= transaction.max_retry:
            return False
        if transaction.state != 'error':
            return False
        return True

    def schedule_retry(self, transaction, immediate=False):
        """
        İşlem için yeniden deneme planlar.
        :param transaction: mdx.efatura.islem kaydı
        :param immediate: True ise hemen dene
        :return: bool
        """
        if not self.can_retry_transaction(transaction):
            return False

        retry_count = transaction.retry_count
        delay_minutes = self.RETRY_DELAYS[min(retry_count, len(self.RETRY_DELAYS) - 1)]

        if immediate:
            next_retry = fields.Datetime.now()
        else:
            next_retry = fields.Datetime.now() + timedelta(minutes=delay_minutes)

        transaction.write({
            'state': 'retry_scheduled',
            'next_retry_date': next_retry,
        })

        _logger.info("İşlem %d için tekrar deneme planlandı: %s", transaction.id, next_retry)
        return True

    def execute_retry(self, transaction):
        """
        Bir işlemi yeniden dener.
        :param transaction: mdx.efatura.islem kaydı
        :return: bool
        """
        if not self.can_retry_transaction(transaction):
            return False

        document = transaction.document_ref
        if not document or not document.exists():
            transaction.write({
                'state': 'cancelled',
                'error_message': 'İlgili belge silinmiş veya bulunamadı.',
            })
            return False

        transaction.write({
            'retry_count': transaction.retry_count + 1,
            'last_attempt_date': fields.Datetime.now(),
            'state': 'sending',
        })

        try:
            if document._name == 'account.move':
                result = document.action_send_einvoice_retry(transaction)
            elif document._name == 'stock.picking':
                result = document.action_send_waybill_retry(transaction)
            else:
                transaction.write({'state': 'error'})
                return False

            if result and result.get('success'):
                transaction.write({'state': 'sent'})
                return True
            else:
                if self.can_retry_transaction(transaction):
                    self.schedule_retry(transaction)
                else:
                    transaction.write({'state': 'error'})
                return False

        except Exception as e:
            _logger.error("İşlem %d için tekrar deneme başarısız: %s", transaction.id, str(e))
            # Hata kodunu parse et ve güncelle
            error_handler = self.env['mdx.error.handler.mixin']
            error_result = error_handler._handle_efatura_error(e, record=transaction)
            error_code = error_result.get('error_code')
            error_record = False
            if error_code:
                error_record = self.env['mdx.efatura.hata.kodu'].search(
                    [('code', '=', error_code)], limit=1
                )
            transaction.write({
                'state': 'error',
                'error_message': str(e),
                'error_code_id': error_record.id if error_record else transaction.error_code_id.id,
            })
            if self.can_retry_transaction(transaction):
                self.schedule_retry(transaction)
            return False

    def process_retry_queue(self):
        """Planlanmış tekrar denemeleri işler (cron job tarafından çağrılır)."""
        transactions = self.env['mdx.efatura.islem'].sudo().search([
            ('state', '=', 'retry_scheduled'),
            ('next_retry_date', '<=', fields.Datetime.now()),
        ])

        _logger.info("Tekrar deneme kuyruğu: %d adet işlem işlenecek", len(transactions))

        success_count = 0
        for trans in transactions:
            try:
                if self.execute_retry(trans):
                    success_count += 1
            except Exception as e:
                _logger.error("İşlem %d için tekrar deneme hatası: %s", trans.id, str(e))

        _logger.info(
            "Tekrar deneme kuyruğu tamamlandı: %d/%d başarılı",
            success_count, len(transactions),
        )
        return {'processed': len(transactions), 'successful': success_count}
