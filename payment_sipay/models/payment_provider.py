# Part of Odoo. See LICENSE file for full copyright and licensing details.

import hashlib
import logging
import pprint

import requests
from urllib.parse import urljoin

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment_sipay import const


_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('sipay', "Sipay")], ondelete={'sipay': 'set default'}
    )
    sipay_merchant_key = fields.Char(
        string="Merchant Key",
        help="The merchant key provided by Sipay.",
        required_if_provider='sipay',
        groups='base.group_system',
    )
    sipay_app_id = fields.Char(
        string="App ID",
        help="The app ID provided by Sipay.",
        required_if_provider='sipay',
    )
    sipay_app_secret = fields.Char(
        string="App Secret",
        help="The app secret provided by Sipay.",
        required_if_provider='sipay',
        groups='base.group_system',
    )
    sipay_merchant_id = fields.Char(
        string="Merchant ID",
        help="The merchant ID provided by Sipay.",
        required_if_provider='sipay',
    )

    #=== COMPUTE METHODS ===#

    def _compute_feature_support_fields(self):
        """ Override of `payment` to enable additional features. """
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == 'sipay').update({
            'support_manual_capture': 'full_only',
            'support_refund': 'full_only',
        })

    # === BUSINESS METHODS ===#

    def _get_supported_currencies(self):
        """ Override of `payment` to return the supported currencies. """
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'sipay':
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    def _sipay_get_api_url(self):
        """ Return the API URL according to the provider state.

        Note: self.ensure_one()

        :return: The API URL
        :rtype: str
        """
        self.ensure_one()

        if self.state == 'enabled':
            return 'https://app.sipay.com.tr/ccpayment/'
        return 'https://provisioning.sipay.com.tr/ccpayment/'

    def _sipay_make_request(self, endpoint, payload=None, method='POST'):
        self.ensure_one()

        url = urljoin(self._sipay_get_api_url(), endpoint)
        headers = {'Content-Type': 'application/json'}

        # If we call a non-token endpoint, request a fresh token and add Authorization
        if endpoint != const.API_TOKEN_ENDPOINT:
            token_data = self._sipay_get_token()
            token = token_data.get('token') if isinstance(token_data, dict) else None
            if token:
                headers['Authorization'] = f'Bearer {token}'
                headers['Accept'] = 'application/json'

        try:
            if method == 'GET':
                response = requests.get(url, params=payload, headers=headers, timeout=10)
            else:
                response = requests.post(url, json=payload, headers=headers, timeout=10)

            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError:
                _logger.exception(
                    "Invalid API request at %s with data:\n%s", url, pprint.pformat(payload),
                )
                # protect against non-json response
                try:
                    error_msg = response.json().get('status_description', 'Unknown error')
                except ValueError:
                    error_msg = 'Unknown error'
                raise ValidationError("Sipay: " + _("Sipay gave us the following error: '%s'") % error_msg)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            _logger.exception("Unable to reach endpoint at %s", url)
            raise ValidationError(
                "Sipay: " + _("Could not establish the connection to the API.")
            )

        # try to parse json (may raise ValueError -> let it bubble or wrap if you prefer)
        return response.json()


    def _sipay_get_token(self):
        self.ensure_one()

        payload = {
            'app_id': self.sipay_app_id,
            'app_secret': self.sipay_app_secret,
        }

        _logger.info(
            "Sending token request for provider %s:\n%s",
            self.name, pprint.pformat(payload)
        )

        response = self._sipay_make_request(const.API_TOKEN_ENDPOINT, payload=payload)

        _logger.info(
            "Token response for provider %s:\n%s",
            self.name, pprint.pformat(response)
        )

        if isinstance(response, list) and len(response) > 0:
            response = response[0]

        if response.get('status_code') == 100:
            token_data = response.get('data', {})
            # DO NOT assign dynamic attribute on self (may raise AttributeError)
            # self._sipay_token = token_data.get('token')  <-- removed
            return token_data
        else:
            raise ValidationError(
                "Sipay: " + _("Failed to get token: %s") % response.get('status_description')
            )

    def _get_default_payment_method_codes(self):
        """ Override of `payment` to return the default payment method codes. """
        default_codes = super()._get_default_payment_method_codes()
        if self.code != 'sipay':
            return default_codes
        return const.DEFAULT_PAYMENT_METHOD_CODES
