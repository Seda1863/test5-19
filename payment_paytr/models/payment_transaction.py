# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from odoo import models, fields
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    paytr_order_no = fields.Char(string='PayTR Order No', readonly=True, copy=False)

    # === TOKEN VE CALLBACK İŞLEMLERİ === #

    def _get_specific_processing_values(self, processing_values):
        """
        Override of `payment` to return PayTR-specific values.
        Frontend artık doğrudan provider kimliklerini almaz.
        Sadece güvenli meta veriler gönderilir.
        """
        res = super()._get_specific_processing_values(processing_values)
        if self.provider_code != 'paytr':
            return res

        self.ensure_one()
        return {
            'reference': self.reference,
            'amount': self.amount,
            'currency': self.currency_id.name,
            'partner_name': self.partner_name,
            'partner_email': self.partner_email,
        }

    def _get_specific_rendering_values(self, processing_values):
        """
        Override of `payment` to return values used by frontend JS.
        PayTR token’ı backend controller alacağı için burada sadece
        transaction bilgileri döndürülür.
        """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'paytr':
            return res

        self.ensure_one()
        return {
            'reference': self.reference,
            'amount': self.amount,
            'currency': self.currency_id.name,
        }

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """
        Find the PayTR transaction based on callback payload.
        Source: merchant_oid field.
        """
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'paytr' or len(tx) == 1:
            return tx

        reference = notification_data.get('merchant_oid')
        if not reference:
            raise ValidationError("PayTR: Missing merchant_oid in callback data.")

        tx = self.search([
            ('reference', '=', reference),
            ('provider_code', '=', 'paytr')
        ])
        if not tx:
            raise ValidationError("PayTR: No transaction found for reference %s." % reference)
        return tx

    def _process_notification_data(self, notification_data):
        """
        Process PayTR callback notification.
        Controller’da hash doğrulaması zaten yapılır.
        Burada sadece transaction state güncellenir.
        """
        super()._process_notification_data(notification_data)
        if self.provider_code != 'paytr':
            return

        status = notification_data.get('status')
        total_amount = notification_data.get('total_amount')
        failed_reason = notification_data.get('failed_reason_msg')

        _logger.info(
            "Processing PayTR notification for %s: status=%s, total_amount=%s",
            self.reference, status, total_amount
        )

        # Sipariş numarasını kaydet
        self.paytr_order_no = notification_data.get('merchant_oid', '')

        if status == 'success':
            self._set_done()
            _logger.info("PayTR payment marked as DONE for %s", self.reference)
        else:
            self._set_error("PayTR: %s" % (failed_reason or 'Payment failed'))
            _logger.warning("PayTR payment marked as FAILED for %s", self.reference)
