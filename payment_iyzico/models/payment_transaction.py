# Part of Odoo. See LICENSE file for full copyright and licensing details.

from urllib.parse import urljoin

from odoo import models
from odoo.exceptions import ValidationError
from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment_iyzico import const
import logging

_logger = logging.getLogger(__name__)


def _get_client_ip():
    """Gerçek istemci IP'sini al (proxy arkasında da çalışır)."""
    try:
        from odoo.http import request as http_request
        if http_request and http_request.httprequest:
            forwarded = http_request.httprequest.environ.get('HTTP_X_FORWARDED_FOR', '')
            if forwarded:
                return forwarded.split(',')[0].strip()
            return http_request.httprequest.environ.get('REMOTE_ADDR', '0.0.0.0')
    except Exception:
        pass
    return '0.0.0.0'


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    # === BUSINESS METHODS - PRE-PROCESSING === #

    def _get_specific_rendering_values(self, *args):
        """Override of `payment` to return Iyzico specific rendering values."""
        if self.provider_code != 'iyzico':
            return super()._get_specific_rendering_values(*args)

        # 1️Ödeme isteği hazırlanıyor
        payload = self._iyzico_prepare_cf_initialize_payload()
        try:
            payment_link_data = self._send_api_request(
                'POST',
                'payment/iyzipos/checkoutform/initialize/auth/ecom',
                json=payload,
            )
        except ValidationError as error:
            self._set_error(str(error))
            return {}

        # 2️ Iyzico yönlendirme sayfasını al
        api_url = payment_link_data.get('paymentPageUrl')
        if not api_url:
            self._set_error("Iyzico: No paymentPageUrl returned by API.")
            return {}

        parsed_url = urls.url_parse(api_url)
        url_params = urls.url_decode(parsed_url.query)

        return {
            'api_url': api_url,
            'url_params': url_params,
        }

    def _iyzico_prepare_cf_initialize_payload(self):
        """Hazır ödeme isteği payload'ı oluşturur."""
        base_url = self.provider_id.get_base_url()
        first_name, last_name = payment_utils.split_partner_name(self.partner_name)

        # --- DÜZELTME BAŞLANGICI: İsim yoksa varsayılan ata GEÇİCİ---
        if not first_name:
            first_name = 'Misafir'  # veya 'Guest'
        if not last_name:
            last_name = 'Kullanici' # veya 'User'
        # --- DÜZELTME SONU ---

        # Geri dönüş URL'si (return callback)
        query_string_params = urls.url_encode({'tx_ref': self.reference})
        return_url = f'{urljoin(base_url, const.PAYMENT_RETURN_ROUTE)}?{query_string_params}'

        return {
            'basketItems': [{
                'id': self.id,
                'price': self.amount,
                'name': 'Odoo purchase',
                'category1': 'Service',
                'itemType': 'VIRTUAL',
            }],
            'billingAddress': {
                'address': self.partner_address,
                'contactName': self.partner_name,
                'city': self.partner_city,
                'country': self.partner_country_id.name,
            },
            'buyer': {
                'id': self.partner_id.id,
                'name': first_name,
                'surname': last_name,
                'identityNumber': str(self.partner_id.id).zfill(5),
                'email': self.partner_email,
                'registrationAddress': self.partner_address,
                'city': self.partner_city,
                'country': self.partner_country_id.name,
                'ip': _get_client_ip(),
            },
            'callbackUrl': return_url,
            'conversationId': self.reference,
            'currency': self.currency_id.name,
            'locale': 'tr' if self.env.lang == 'tr_TR' else 'en',
            'paidPrice': self.amount,
            'price': self.amount,
        }

    # === BUSINESS METHODS - PROCESSING === #

    def _extract_amount_data(self, payment_data):
        """Override of `payment` to extract the amount and currency."""
        if self.provider_code != 'iyzico':
            return super()._extract_amount_data(payment_data)

        return {
            'amount': payment_data.get('price'),
            'currency_code': payment_data.get('currency'),
        }

    def _apply_updates(self, payment_data):
        """Update the transaction based on the received Iyzico payment data."""
        if self.provider_code != 'iyzico':
            return super()._apply_updates(payment_data)

        self.provider_reference = payment_data.get('paymentId')

        # Kart / banka ayrımı
        if bool(payment_data.get('cardType')):
            payment_method_code = payment_data.get('cardAssociation', '')
            payment_method = self.env['payment.method']._get_from_code(
                payment_method_code.lower(), mapping=const.PAYMENT_METHODS_MAPPING
            )
        elif bool(payment_data.get('bankName')):
            payment_method = self.env.ref('payment.payment_method_bank_transfer')
        else:
            payment_method = self.env.ref('payment.payment_method_unknown')
        self.payment_method_id = payment_method or self.payment_method_id

        # Ödeme durumu
        status = payment_data.get('paymentStatus')
        if status in const.PAYMENT_STATUS_MAPPING['pending']:
            self._set_pending()
        elif status in const.PAYMENT_STATUS_MAPPING['done']:
            self._set_done()
        elif status in const.PAYMENT_STATUS_MAPPING['error']:
            self._set_error(self.env._(
                "An error occurred during processing of your payment "
                "(code %(code)s: %(explanation)s). Please try again.",
                code=status,
                explanation=payment_data.get('errorMessage'),
            ))
        else:
            _logger.warning(
                "Received data with invalid payment status (%s) for transaction %s",
                status, self.reference
            )
            self._set_error(self.env._("Unknown status code: %s", status))

    # === REQUEST HELPERS === #

    def _send_api_request(self, method, endpoint, *, params=None, data=None, json=None, **kwargs):
        """Iyzico transaction helper — delegates API calls to provider."""
        self.ensure_one()
        return self.provider_id._send_api_request(
            method,
            endpoint,
            params=params,
            data=data,
            json=json,
            reference=self.reference,
            **kwargs,
        )
