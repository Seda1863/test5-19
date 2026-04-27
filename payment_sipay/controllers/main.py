# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import logging
import pprint

from odoo import http
from odoo.http import request
from odoo.exceptions import ValidationError


_logger = logging.getLogger(__name__)


class SipayController(http.Controller):
    _return_url = '/payment/sipay/return'

    @http.route('/payment/sipay/get_3d_form_data', type='json', auth='public', methods=['POST'])
    def sipay_get_3d_form_data(self, **data):
        """Prepare and return 3D Secure form data for Sipay payment."""
        try:
            _logger.info("Received 3D form data request: %s", data.get('reference'))
            
            # Get transaction
            reference = data.get('reference')
            if not reference:
                return {'success': False, 'error': 'Missing transaction reference'}
            
            tx_sudo = request.env['payment.transaction'].sudo().search([
                ('reference', '=', reference),
                ('provider_code', '=', 'sipay'),
                ('state', '=', 'draft')
            ], limit=1)
            
            if not tx_sudo:
                return {'success': False, 'error': 'Transaction not found or already processed'}
            
            # Prepare card data
            card_data = {
                'cc_holder_name': data.get('cc_holder_name'),
                'cc_no': data.get('cc_no'),
                'expiry_month': data.get('expiry_month'),
                'expiry_year': data.get('expiry_year'),
                'cvv': data.get('cvv'),
                'installments': data.get('installments', '1'),
            }
            
            # Validate required fields
            required_fields = ['cc_holder_name', 'cc_no', 'expiry_month', 'expiry_year', 'cvv']
            for field in required_fields:
                if not card_data.get(field):
                    return {'success': False, 'error': f'Missing required field: {field}'}
            
            # Get 3D form data from transaction
            form_data = tx_sudo.with_context(
                remote_addr=request.httprequest.environ.get('HTTP_X_FORWARDED_FOR') or 
                           request.httprequest.environ.get('REMOTE_ADDR')
            )._sipay_prepare_3d_form_data(card_data)
            
            _logger.info("Successfully prepared 3D form for %s", reference)
            
            return {
                'success': True,
                'form_action': form_data['form_action'],
                'form_fields': form_data['form_fields']
            }
            
        except Exception as e:
            _logger.exception("Error preparing 3D form data for %s: %s", data.get('reference'), str(e))
            return {'success': False, 'error': str(e)}

    @http.route(_return_url, type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def sipay_return_from_redirect(self, **data):
        """Process the notification data sent by Sipay after 3D Secure verification."""
        _logger.info("=== SIPAY 3D RETURN START ===")
        _logger.info("Request method: %s", request.httprequest.method)
        _logger.info("Full request data: %s", dict(request.params))
        _logger.info("Headers: %s", dict(request.httprequest.headers))
        
        # Extract the invoice_id to find the transaction
        invoice_id = data.get('invoice_id')
        if not invoice_id:
            _logger.error("Received Sipay return without invoice_id in data: %s", data)
            return request.redirect('/payment/status')

        # Find the transaction
        tx_sudo = request.env['payment.transaction'].sudo().search([
            ('reference', '=', invoice_id),
            ('provider_code', '=', 'sipay'),
        ], limit=1)

        if not tx_sudo:
            _logger.error("No transaction found for invoice_id: %s", invoice_id)
            return request.redirect('/payment/status')

        # Check current state to avoid double processing
        if tx_sudo.state in ['done', 'cancel', 'error']:
            _logger.info(
                "Transaction %s already in final state: %s",
                invoice_id, tx_sudo.state
            )
            return request.redirect('/payment/status')

        try:
            # Log detailed response for debugging
            _logger.info("Processing 3D return for transaction %s", invoice_id)
            _logger.info("Raw return data: %s", pprint.pformat(dict(data)))
            
            # Process the 3D return data
            tx_sudo._sipay_complete_3d_payment(data)
            
            _logger.info("Transaction %s new state: %s", invoice_id, tx_sudo.state)
            
        except Exception as e:
            _logger.exception("Error processing 3D return for %s: %s", invoice_id, str(e))
            tx_sudo._set_error(f"Error processing payment return: {str(e)}")

        _logger.info("=== SIPAY 3D RETURN END ===")
        return request.redirect('/payment/status')

    @http.route('/payment/sipay/webhook', type='json', auth='public', methods=['POST'], csrf=False)
    def sipay_webhook(self, **data):
        """Handle webhook notifications from Sipay.
        
        This endpoint can be used for server-to-server notifications
        about payment status changes.
        
        :param dict data: Webhook data from Sipay
        :return: Acknowledgment response
        :rtype: dict
        """
        _logger.warning("Received Sipay webhook notification:\n%s", pprint.pformat(data))
        
        try:
            invoice_id = data.get('invoice_id')
            order_no = data.get('order_no')
            status = data.get('status')
            
            if not invoice_id:
                return {'status': 'error', 'message': 'Missing invoice_id'}
            
            # Find transaction
            tx_sudo = request.env['payment.transaction'].sudo().search([
                ('reference', '=', invoice_id),
                ('provider_code', '=', 'sipay'),
            ], limit=1)
            
            if not tx_sudo:
                _logger.warning("Webhook: No transaction found for invoice_id: %s", invoice_id)
                return {'status': 'error', 'message': 'Transaction not found'}
            
            # Update transaction based on webhook data
            if order_no and not tx_sudo.sipay_order_no:
                tx_sudo.sipay_order_no = order_no
            
            # Process status update
            if status == '1':  # Success
                if tx_sudo.state not in ['done', 'authorized']:
                    tx_sudo._set_done()
            elif status in ['0', '-1']:  # Failed or Cancelled
                if tx_sudo.state not in ['cancel', 'error']:
                    error_msg = data.get('error_description', 'Payment failed')
                    tx_sudo._set_error(error_msg)
            
            return {'status': 'success', 'message': 'Webhook processed'}
            
        except Exception as e:
            _logger.exception("Error processing Sipay webhook: %s", str(e))
            return {'status': 'error', 'message': str(e)}