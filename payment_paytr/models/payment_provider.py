# Part of Odoo. See LICENSE file for full copyright and licensing details.

import hashlib
import logging
import pprint

import requests
from urllib.parse import urljoin

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment_paytr import const


_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('paytr', "PayTR")], ondelete={'paytr': 'set default'}
    )
    paytr_merchant_key = fields.Char(
        string="Merchant Key",
        help="The merchant key provided by PayTR.",
        required_if_provider='paytr',
        groups='base.group_system',
    )
    paytr_merchant_id = fields.Char(
        string="Merchant ID",
        help="The app ID provided by PayTR.",
        required_if_provider='paytr',
    )
    paytr_merchant_salt = fields.Char(
        string="Merchant Salt",
        help="The app secret provided by PayTR.",
        required_if_provider='paytr',
        groups='base.group_system',
    )


    #=== COMPUTE METHODS ===#

    def _compute_feature_support_fields(self):
        """ Override of `payment` to enable additional features. """
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == 'paytr').update({
            'support_manual_capture': 'full_only',
            'support_refund': 'full_only',
        })

    # === BUSINESS METHODS ===#

    def _get_supported_currencies(self):
        """ Override of `payment` to return the supported currencies. """
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'paytr':
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    def _paytr_get_api_url(self):
        """Return base PayTR API URL (test or production)."""
        self.ensure_one()
        # Canlı sistem için:
        return 'https://www.paytr.com/'
        # Eğer ileride test ortamı gerekiyorsa:
        # return 'https://sandbox.paytr.com/' if self.state == 'test' else 'https://www.paytr.com/'


    def _paytr_make_request(self, endpoint, payload=None, method='POST'):
        """Send request to PayTR API (used for token creation and status checks)."""
        self.ensure_one()

        url = urljoin(self._paytr_get_api_url(), endpoint)
        _logger.info("Sending PayTR request to %s with payload:\n%s", url, pprint.pformat(payload))

        try:
            if method == 'GET':
                # PayTR genellikle GET endpoint kullanmaz ama genel yapı için bırakıldı
                response = requests.get(url, params=payload, timeout=10)
            else:
                # PayTR JSON değil form-data bekler
                response = requests.post(url, data=payload, timeout=10)

            # HTTP hatalarını kontrol et
            response.raise_for_status()

            # Cevabı JSON olarak çözümle
            try:
                result = response.json()
            except ValueError:
                _logger.error("PayTR: Non-JSON response received: %s", response.text)
                raise ValidationError(_("PayTR: Invalid response format."))

            # PayTR beklenen status alanı
            if result.get('status') != 'success':
                error_message = result.get('reason') or result.get('error') or 'Unknown error'
                _logger.error("PayTR error: %s", error_message)
                raise ValidationError(_("PayTR API error: %s") % error_message)

            _logger.info("PayTR request successful: %s", pprint.pformat(result))
            return result

        except requests.exceptions.Timeout:
            _logger.exception("PayTR: Request timed out at %s", url)
            raise ValidationError(_("PayTR: Request timed out. Please try again."))

        except requests.exceptions.ConnectionError:
            _logger.exception("PayTR: Unable to connect to endpoint %s", url)
            raise ValidationError(_("PayTR: Could not establish connection to the API."))

        except requests.exceptions.HTTPError as e:
            _logger.exception("PayTR: HTTP error occurred: %s", str(e))
            raise ValidationError(_("PayTR: HTTP error - %s") % str(e))



    def _paytr_direct_get_token(self, values):
        """Compute PayTR Direct API paytr_token (HMAC-SHA256, base64 encoded)."""
        self.ensure_one()
        import base64, hmac as _hmac, hashlib
        hash_str = (
            str(self.paytr_merchant_id)
            + str(values['user_ip'])
            + str(values['merchant_oid'])
            + str(values['email'])
            + str(values['payment_amount'])
            + str(values['payment_type'])
            + str(values['installment_count'])
            + str(values['currency'])
            + str(values['test_mode'])
            + str(values['non_3d'])
        )
        return base64.b64encode(
            _hmac.new(
                self.paytr_merchant_key.encode(),
                (hash_str + self.paytr_merchant_salt).encode(),
                hashlib.sha256
            ).digest()
        ).decode()

            

    def _get_default_payment_method_codes(self):
        """ Override of `payment` to return the default payment method codes. """
        default_codes = super()._get_default_payment_method_codes()
        if self.code != 'paytr':
            return default_codes
        return const.DEFAULT_PAYMENT_METHOD_CODES
