# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import hashlib
import hmac
import logging
import pprint

from odoo import http
from odoo.http import request
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PaytrController(http.Controller):
    _return_url = '/payment/paytr/return'
    _callback_url = '/payment/paytr/callback'

    @http.route('/payment/paytr/get_direct_form_data', type='json', auth='public', methods=['POST'])
    def paytr_get_direct_form_data(self, reference, cc_owner, card_number,
                                   expiry_month, expiry_year, cvv, installments='1', **kwargs):
        """Compute PayTR Direct API token and return form fields for frontend submission."""
        try:
            tx_sudo = request.env['payment.transaction'].sudo().search([
                ('reference', '=', reference),
                ('provider_code', '=', 'paytr'),
                ('state', '=', 'draft'),
            ], limit=1)
            if not tx_sudo:
                return {'success': False, 'error': 'Transaction not found'}

            provider = tx_sudo.provider_id
            if not provider or provider.code != 'paytr':
                return {'success': False, 'error': 'Invalid provider'}

            forwarded = request.httprequest.environ.get('HTTP_X_FORWARDED_FOR', '')
            user_ip = forwarded.split(',')[0].strip() if forwarded else request.httprequest.remote_addr

            amount_kurus = str(int(round(tx_sudo.amount * 100)))
            currency = tx_sudo.currency_id.name or 'TRY'
            email = tx_sudo.partner_email or 'test@example.com'
            test_mode = '0' if provider.state == 'enabled' else '1'

            installment_count = str(int(installments)) if installments else '1'

            token_values = {
                'user_ip': user_ip,
                'merchant_oid': reference,
                'email': email,
                'payment_amount': amount_kurus,
                'payment_type': 'card',
                'installment_count': installment_count,
                'currency': currency,
                'test_mode': test_mode,
                'non_3d': '0',
            }

            paytr_token = provider._paytr_direct_get_token(token_values)

            base_url = request.httprequest.host_url.rstrip('/')
            ok_url = base_url + '/payment/paytr/return'
            fail_url = base_url + '/payment/paytr/return'

            form_fields = {
                'merchant_id': provider.paytr_merchant_id,
                'user_ip': user_ip,
                'merchant_oid': reference,
                'email': email,
                'payment_amount': amount_kurus,
                'currency': currency,
                'payment_type': 'card',
                'installment_count': installment_count,
                'card_type': '',
                'card_number': card_number,
                'expiry_month': expiry_month,
                'expiry_year': expiry_year,
                'cvv': cvv,
                'cc_owner': cc_owner,
                'merchant_ok_url': ok_url,
                'merchant_fail_url': fail_url,
                'test_mode': test_mode,
                'non_3d': '0',
                'paytr_token': paytr_token,
            }

            _logger.info(
                "PayTR Direct form data prepared for %s (test_mode=%s, amount=%s %s)",
                reference, test_mode, amount_kurus, currency
            )

            return {
                'success': True,
                'form_action': 'https://www.paytr.com/odeme',
                'form_fields': form_fields,
            }

        except Exception as e:
            _logger.exception("Error preparing PayTR Direct API form data: %s", str(e))
            return {'success': False, 'error': str(e)}

    @http.route(_callback_url, type='http', auth='public', methods=['POST'], csrf=False)
    def paytr_callback(self, **post):
        """PayTR server-side callback: validate hash and update transaction state."""
        _logger.info("=== PAYTR CALLBACK START ===")
        _logger.info("Callback data: %s", pprint.pformat(dict(post)))

        merchant_oid = post.get('merchant_oid')
        if not merchant_oid:
            _logger.error("PayTR callback missing merchant_oid")
            return 'ERROR'

        tx_sudo = request.env['payment.transaction'].sudo().search([
            ('reference', '=', merchant_oid),
            ('provider_code', '=', 'paytr'),
        ], limit=1)

        if not tx_sudo:
            _logger.error("No transaction found for merchant_oid: %s", merchant_oid)
            return 'ERROR'

        provider = tx_sudo.provider_id
        if not provider:
            _logger.error("No provider found for transaction: %s", merchant_oid)
            return 'ERROR'

        try:
            status = post.get('status', '')
            total_amount = post.get('total_amount', '')
            hash_str = merchant_oid + provider.paytr_merchant_salt + status + total_amount
            expected_hash = base64.b64encode(
                hmac.new(
                    provider.paytr_merchant_key.encode(),
                    hash_str.encode(),
                    hashlib.sha256
                ).digest()
            ).decode()

            if expected_hash != post.get('hash'):
                _logger.warning("Hash mismatch for %s", merchant_oid)
                return 'bad hash'

            if status == 'success':
                _logger.info("Payment success for %s", merchant_oid)
                tx_sudo._set_done()
            else:
                _logger.warning("Payment failed for %s", merchant_oid)
                tx_sudo._set_error(post.get('failed_reason_msg', 'Payment failed'))

        except Exception as e:
            _logger.exception("Callback error: %s", str(e))
            tx_sudo._set_error(str(e))
            return 'ERROR'

        _logger.info("=== PAYTR CALLBACK END ===")
        return 'OK'

    @http.route(_return_url, type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def paytr_return(self, **data):
        """User redirect after 3DS (informational — state set by callback)."""
        _logger.info("PayTR return URL data: %s", pprint.pformat(data))
        return request.redirect('/payment/status')
