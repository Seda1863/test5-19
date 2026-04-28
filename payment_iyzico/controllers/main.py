# Part of Odoo. See LICENSE file for full copyright and licensing details.

import pprint
import logging

from odoo import http
from odoo.http import request
from odoo.exceptions import ValidationError

from odoo.addons.payment_iyzico import const

_logger = logging.getLogger(__name__)


class IyzicoController(http.Controller):
    """
    Controller for Iyzico payment processing.
    Handles both:
        - initialize_checkout (frontend)
        - return_from_payment (callback)
    """

    # === 1️⃣ ÖDEME BAŞLATMA === #
    @http.route(
        '/payment/iyzico/initialize_checkout',
        type='jsonrpc', auth='public', csrf=False
    )
    def iyzico_initialize_checkout(self, reference=None, **kwargs):
        """
        Ödemeyi başlatır. Frontend 'Pay Now' butonuna basınca çağrılır.
        Iyzico API'ye istek atar ve paymentPageUrl döner.
        """
        _logger.info("[Iyzico] Checkout initialize requested for reference=%s", reference)

        if not reference:
            _logger.error("[Iyzico] Missing transaction reference in request.")
            return {'success': False, 'error': 'Missing transaction reference'}

        tx = request.env['payment.transaction'].sudo().search([('reference', '=', reference)], limit=1)
        if not tx:
            _logger.error("[Iyzico] Transaction not found for reference %s", reference)
            return {'success': False, 'error': 'Transaction not found'}

        try:
            # Payload hazırla
            payload = tx._iyzico_prepare_cf_initialize_payload()
            _logger.debug("[Iyzico] Payload: %s", pprint.pformat(payload))

            # API çağrısı yap
            result = tx.provider_id._send_api_request(
                'POST',
                'payment/iyzipos/checkoutform/initialize/auth/ecom',
                json=payload,
            )

            _logger.info("[Iyzico] Initialize API response:\n%s", pprint.pformat(result))

            # API sonucu kontrol et
            if not result or not isinstance(result, dict):
                _logger.error("[Iyzico] Invalid API response format: %s", result)
                return {'success': False, 'error': 'Invalid API response format'}

            payment_url = result.get('paymentPageUrl')
            if not payment_url:
                _logger.error("[Iyzico] Missing paymentPageUrl in response")
                return {'success': False, 'error': 'Iyzico did not return paymentPageUrl'}

            return {'success': True, 'payment_url': payment_url}

        except ValidationError as e:
            _logger.error("[Iyzico] Validation error during checkout init: %s", e)
            return {'success': False, 'error': str(e)}
        except Exception as e:
            _logger.exception("[Iyzico] Unexpected error during checkout init: %s", e)
            # Dönüş her durumda JSON olmalı
            return {'success': False, 'error': f"Unexpected error: {str(e)}"}

    # === 2️⃣ CALLBACK (ÖDEME DÖNÜŞÜ) === #
    @http.route(
        const.PAYMENT_RETURN_ROUTE,
        type='http', auth='public', methods=['POST'],
        csrf=False, save_session=False
    )
    def iyzico_return_from_payment(self, tx_ref='', **data):
        """
        Iyzico dönüş callback'i.
        """
        _logger.info("[Iyzico] Return route triggered with data:\n%s", pprint.pformat(data))

        if not tx_ref:
            _logger.warning("[Iyzico] Missing transaction reference in return data.")
            return request.redirect('/payment/status')

        token = data.get('token')
        if not token:
            _logger.warning("[Iyzico] Missing token in return payload.")
            return request.redirect('/payment/status')

        try:
            self._verify_and_process(tx_ref, token)
        except Exception as e:
            _logger.exception("[Iyzico] Error in verify_and_process: %s", e)

        return request.redirect('/payment/status')

    # === 3️⃣ DOĞRULAMA (GÜNCELLENDİ) === #
    @staticmethod
    def _verify_and_process(tx_ref, token):
        """
        Iyzico API’ye ödeme doğrulama isteği atar.
        """
        _logger.info("[Iyzico] Verifying payment for reference=%s with token=%s", tx_ref, token)
        tx_sudo = request.env['payment.transaction'].sudo().search([('reference', '=', tx_ref)], limit=1)
        
        if not tx_sudo:
            _logger.error("[Iyzico] Transaction not found for verification (ref=%s)", tx_ref)
            return

        try:
            verified_payment_data = tx_sudo._send_api_request(
                'POST',
                'payment/iyzipos/checkoutform/auth/ecom/detail',
                json={
                    'conversationId': tx_sudo.reference,
                    'locale': 'tr' if request.env.lang == 'tr_TR' else 'en',
                    'token': token,
                },
            )

            _logger.info("[Iyzico] Verification response:\n%s", pprint.pformat(verified_payment_data))
            
            # Başarılı güncellemeleri uygula
            tx_sudo._apply_updates(verified_payment_data)
            _logger.info("[Iyzico] Transaction %s successfully processed.", tx_ref)

        except Exception as e:
            # Hata yakalama bloğu: İster Validation ister sistem hatası olsun
            _logger.exception("[Iyzico] Error during verification: %s", e)
            
            # Kullanıcıya gösterilecek genel mesaj
            general_error_msg = "Ödeme işleminiz gerçekleştirilemedi. Lütfen tekrar deneyin veya bankanızla iletişime geçin."
            
            # İşlemi Odoo'da 'Hata' durumuna çekiyoruz ki "Please Wait" ekranı kalksın
            tx_sudo._set_error(general_error_msg)