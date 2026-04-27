# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import hashlib
import json
import logging
import pprint
import random
import secrets
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from odoo import _, api, models, fields
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment_sipay import const


_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    sipay_order_no = fields.Char(string='Sipay Order No', readonly=True, copy=False)
    sipay_3d_status = fields.Selection([
        ('pending', 'Pending 3D Verification'),
        ('verified', '3D Verified'),
        ('failed', '3D Failed')
    ], string='3D Status', readonly=True, copy=False)

    def _sipay_generate_hash_key(self, total, installment, currency_code, merchant_key, invoice_id, app_secret):
        """Generate hash key for Sipay 3D Secure payment."""
        try:
            # Sipay formatına uygun veri string'i oluştur
            data = f"{total}|{installment}|{currency_code}|{merchant_key}|{invoice_id}"
            
            _logger.info("Hash generation data: %s", data)

            # IV oluştur - 16 byte olmalı
            iv_random = secrets.token_bytes(8)
            iv = iv_random.hex()[:16]
            
            # Salt oluştur - 4 byte olmalı  
            salt_random = secrets.token_bytes(2)
            salt = salt_random.hex()[:4]

            # Password oluştur (app_secret'ten SHA1 hash)
            hash_app_sec = hashlib.sha1()
            hash_app_sec.update(app_secret.encode('utf-8'))
            password = hash_app_sec.hexdigest()

            # Key oluştur (password + salt SHA256 hash)
            str_pass_salt = password + salt
            hash_str = hashlib.sha256()
            hash_str.update(str_pass_salt.encode('utf-8'))
            salt_with_password = hash_str.hexdigest()
            key = salt_with_password[:32].encode('utf-8')

            # Veriyi şifrele - PKCS7 padding ile
            cipher = AES.new(key, AES.MODE_CBC, iv.encode('utf-8'))
            padded_data = pad(data.encode('utf-8'), AES.block_size)
            encrypted_bytes = cipher.encrypt(padded_data)
            encrypted = base64.b64encode(encrypted_bytes).decode('utf-8')

            # Final hash bundle oluştur - SADECE / ve + karakterlerini değiştir
            msg_encrypted_bundle = f"{iv}:{salt}:{encrypted}"
            msg_encrypted_bundle = msg_encrypted_bundle.replace("/", "__")
            # = karakterlerini KALDIRMA - Sipay bunları bekliyor olabilir

            _logger.info("Generated hash key (first 50 chars): %s", msg_encrypted_bundle[:50])

            return msg_encrypted_bundle

        except Exception as error:
            _logger.error("Error generating Sipay hash key: %s", error)
            _logger.error("Hash generation params - total: %s, installment: %s, currency: %s, merchant_key: %s, invoice: %s", 
                        total, installment, currency_code, merchant_key, invoice_id)
            raise ValidationError(_("Failed to generate security hash for payment."))

    def _sipay_validate_return_hash(self, hash_key, app_secret):
        """Validate the hash key received from Sipay return."""
        try:
            if not hash_key:
                _logger.warning("Empty hash key received")
                return None
                
            # Replace characters back
            hash_key = hash_key.replace("_", "/").replace("-", "+")
            
            # Base64 padding ekle (gerekiyorsa)
            def add_base64_padding(data):
                padding = 4 - len(data) % 4
                if padding != 4:
                    data += "=" * padding
                return data
            
            components = hash_key.split(":")
            if len(components) != 3:
                _logger.warning("Invalid hash key format: %s", hash_key)
                return None
                
            iv = components[0]
            salt = components[1]
            encrypted_msg = components[2]

            # Base64 padding ekle
            encrypted_msg = add_base64_padding(encrypted_msg)

            # Generate password from app_secret
            hash_app_sec = hashlib.sha1()
            hash_app_sec.update(app_secret.encode("UTF-8"))
            password = hash_app_sec.hexdigest()

            # Generate key from password and salt
            str_pass_salt = password + salt
            hash_str = hashlib.sha256()
            hash_str.update(str_pass_salt.encode("UTF-8"))
            key_hex = hash_str.hexdigest()
            key = key_hex[:32].encode('utf-8')

            # Decrypt the message
            try:
                cipher = AES.new(key, AES.MODE_CBC, iv.encode('utf-8'))
                encrypted_bytes = base64.b64decode(encrypted_msg)
                decrypted_bytes = cipher.decrypt(encrypted_bytes)
                
                # Remove padding
                try:
                    decrypted_bytes = unpad(decrypted_bytes, AES.block_size)
                except ValueError:
                    # Eğer padding zaten yoksa, sadece null byte'ları temizle
                    decrypted_bytes = decrypted_bytes.rstrip(b'\x00')
                
                decrypted_msg = decrypted_bytes.decode('utf-8', errors='ignore')
                
                _logger.info("Decrypted hash data: %s", decrypted_msg)
                
                # Parse decrypted data
                if "|" in decrypted_msg:
                    parts = decrypted_msg.split("|")
                    return {
                        'status': parts[0] if len(parts) > 0 else '',
                        'total': parts[1] if len(parts) > 1 else '',
                        'invoice_id': parts[2] if len(parts) > 2 else '',
                        'order_id': parts[3] if len(parts) > 3 else '',
                        'currency_code': parts[4] if len(parts) > 4 else ''
                    }
            except Exception as decryption_error:
                _logger.warning("Decryption failed, but continuing: %s", decryption_error)
                return None
            
            return None
            
        except Exception as error:
            _logger.error("Error validating Sipay return hash: %s", error)
            return None

    def _sipay_prepare_3d_form_data(self, card_data):
        """Prepare form data for 3D Secure redirect."""
        self.ensure_one()
        
        # Amount formatını kontrol et
        total_amount = "{:.2f}".format(self.amount)
        installments = str(card_data.get('installments', '1'))
        
        # Hash key oluştur
        hash_key = self._sipay_generate_hash_key(
            total=total_amount,
            installment=installments,
            currency_code=self.currency_id.name,
            merchant_key=self.provider_id.sipay_merchant_key,
            invoice_id=self.reference,
            app_secret=self.provider_id.sipay_app_secret
        )
        
        if not hash_key:
            raise ValidationError(_("Failed to generate payment security hash."))
        
        # İsim ve soyisim ayırma
        name_parts = card_data['cc_holder_name'].strip().split(' ', 1)
        name = name_parts[0]
        surname = name_parts[1] if len(name_parts) > 1 else name_parts[0]
        
        # Telefon numarasını temizle
        partner_phone = self.partner_id.phone or self.partner_id.mobile or '+905555555555'
        partner_phone = ''.join(filter(str.isdigit, partner_phone))
        
        # Items JSON formatı
        items_data = [{
            "name": f"Order {self.reference}",
            "quantity": 1,
            "price": float(total_amount)
        }]
        items_json = json.dumps(items_data)
        
        # IP adresi
        remote_addr = request.httprequest.environ.get('HTTP_X_FORWARDED_FOR') or request.httprequest.environ.get('REMOTE_ADDR') if request else '127.0.0.1'
        
        # Form alanlarını hazırla
        form_fields = {
            'cc_holder_name': card_data['cc_holder_name'],
            'cc_no': card_data['cc_no'],
            'expiry_month': card_data['expiry_month'],
            'expiry_year': card_data['expiry_year'],
            'cvv': card_data['cvv'],
            'currency_code': self.currency_id.name,
            'installments_number': installments,
            'invoice_id': self.reference,
            'invoice_description': f'Payment for order {self.reference}',
            'name': name,
            'surname': surname,
            'total': total_amount,
            'merchant_key': self.provider_id.sipay_merchant_key,
            'items': items_json,
            'return_url': f'{self.provider_id.get_base_url()}/payment/sipay/return',
            'cancel_url': f'{self.provider_id.get_base_url()}/payment/sipay/return',
            'hash_key': hash_key,
            'bill_email': self.partner_id.email or 'noreply@example.com',
            'bill_phone': partner_phone,
            'response_method': 'POST',
            'order_type': '0',
            'payment_completed_by': 'app',
            'ip': remote_addr,
        }
        
        # Debug logging
        _logger.info(
            "Prepared 3D form for transaction %s. Hash key length: %d",
            self.reference, len(hash_key)
        )
        
        # API URL
        api_url = self.provider_id._sipay_get_api_url().rstrip('/')
        form_action = f"{api_url}/api/paySmart3D"
        
        # Durumu güncelle
        self.sipay_3d_status = 'pending'

        return {
            'form_action': form_action,
            'form_fields': form_fields
        }

    def _sipay_complete_3d_payment(self, return_data):
        """Complete the payment after 3D verification."""
        self.ensure_one()
        
        _logger.info(
            "Processing 3D return for transaction %s. Status code: %s",
            self.reference, return_data.get('status_code')
        )
        
        # Order number'ı kaydet
        if return_data.get('order_no'):
            self.sipay_order_no = return_data['order_no']
        
        # Hash key doğrulama — başarısız olursa işlemi durdur
        if return_data.get('hash_key'):
            try:
                self._sipay_verify_notification_data(return_data)
                _logger.info("Hash validation passed for transaction %s", self.reference)
            except Exception as hash_error:
                self.sipay_3d_status = 'failed'
                self._set_error("Sipay: Hash doğrulama başarısız — %s" % str(hash_error))
                _logger.error(
                    "Hash validation FAILED for transaction %s, aborting: %s",
                    self.reference, str(hash_error)
                )
                return
        
        # Status kontrolü - Sipay dokümantasyonuna göre
        sipay_status = return_data.get('sipay_status')
        status_code = return_data.get('status_code')
        payment_status = return_data.get('payment_status')
        
        _logger.info(
            "Payment status check - sipay_status: %s, status_code: %s, payment_status: %s",
            sipay_status, status_code, payment_status
        )
        
        # 3D durumunu kontrol et (sipay_status veya status_code)
        # Sipay'den "Invalid hash key" hatası geldiğinde bile status_code 68 olarak geliyor
        # Bu durumda işlemi başarısız olarak işaretle
        if str(status_code) == '68' or str(sipay_status) == '0':
            self.sipay_3d_status = 'failed'
            error_msg = return_data.get('status_description') or return_data.get('error', '3D Secure verification failed')
            error_code = return_data.get('status_code') or return_data.get('error_code', 'Unknown')
            
            self._set_error(f"Sipay Error {error_code}: {error_msg}")
            _logger.error("3D Secure failed for transaction %s: %s - %s", self.reference, error_code, error_msg)
            return
        
        # 3D başarılıysa ödeme durumunu kontrol et
        if str(sipay_status) == '1' or str(status_code) == '100':
            self.sipay_3d_status = 'verified'
            _logger.info("3D verification successful for transaction %s", self.reference)
            
            if str(payment_status) == '1':
                # Ödeme başarılı
                self.provider_reference = return_data.get('order_no')
                
                transaction_type = return_data.get('transaction_type')
                if transaction_type == 'PreAuth':
                    self._set_authorized()
                    _logger.info("Payment authorized successfully for transaction %s", self.reference)
                else:  # Auth
                    self._set_done()
                    _logger.info("Payment completed successfully for transaction %s", self.reference)
            else:
                # 3D başarılı ama ödeme başarısız
                error_msg = return_data.get('status_description') or return_data.get('error', 'Payment failed after 3D verification')
                error_code = return_data.get('status_code') or return_data.get('error_code', 'Unknown')
                original_error = return_data.get('original_bank_error_description', '')
                
                full_error = f"Error {error_code}: {error_msg}"
                if original_error:
                    full_error += f" - {original_error}"
                    
                self._set_error(f"Sipay: {full_error}")
                _logger.warning("Payment failed after 3D verification for transaction %s: %s", self.reference, full_error)
        else:
            # Diğer hata durumları
            self.sipay_3d_status = 'failed'
            error_msg = return_data.get('status_description') or return_data.get('error', '3D Secure verification failed')
            error_code = return_data.get('status_code') or return_data.get('error_code', 'Unknown')
            
            self._set_error(f"3D Secure verification failed: {error_code} - {error_msg}")
            _logger.error("3D Secure failed for transaction %s: %s - %s", self.reference, error_code, error_msg)

    def _get_specific_processing_values(self, processing_values):
        """ Override of `payment` to return Sipay-specific processing values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic and specific processing values of the
                                       transaction.
        :return: The provider-specific processing values.
        :rtype: dict
        """
        res = super()._get_specific_processing_values(processing_values)
        if self.provider_code != 'sipay':
            return res

        # Get token from Sipay
        token_data = self.provider_id._sipay_get_token()
        
        return {
            'sipay_token': token_data.get('token'),
            'sipay_is_3d': token_data.get('is_3d'),
            'sipay_merchant_key': self.provider_id.sipay_merchant_key,
            'sipay_app_secret': self.provider_id.sipay_app_secret,
            'sipay_api_url': self.provider_id._sipay_get_api_url(),
            'currency_code': self.currency_id.name,
            'amount': self.amount,
            'partner_email': self.partner_id.email or '',
            'partner_phone': self.partner_id.phone or self.partner_id.mobile or '',
        }

    def _get_specific_rendering_values(self, processing_values):
        """ Override of `payment` to return Sipay-specific rendering values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic and specific processing values of the transaction
        :return: The dict of provider-specific processing values
        :rtype: dict
        """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'sipay':
            return res

        api_url = self.provider_id._sipay_get_api_url()
        rendering_values = {
            'api_url': api_url + const.API_PAYMENT_ENDPOINT,
            'merchant_key': self.provider_id.sipay_merchant_key,
            'invoice_id': self.reference,
            'invoice_description': f'Payment for order {self.reference}',
            'total': self.amount,
            'currency_code': self.currency_id.name,
            'installments_number': 1,
            'name': self.partner_name.split()[0] if self.partner_name else '',
            'surname': ' '.join(self.partner_name.split()[1:]) if self.partner_name and len(self.partner_name.split()) > 1 else '',
            'items': self.reference,
            'return_url': self._get_return_url(),
            'cancel_url': self._get_return_url(),
        }

        return rendering_values

    def _get_return_url(self):
        """ Return the URL to redirect the customer after payment.

        Note: self.ensure_one()

        :return: The return URL
        :rtype: str
        """
        self.ensure_one()
        base_url = self.provider_id.get_base_url()
        return f'{base_url}/payment/sipay/return'

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """ Override of `payment` to find the transaction based on Sipay data.

        :param str provider_code: The code of the provider that handled the transaction
        :param dict notification_data: The notification data sent by the provider
        :return: The transaction if found
        :rtype: recordset of `payment.transaction`
        :raise: ValidationError if the data match no transaction
        """
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'sipay' or len(tx) == 1:
            return tx

        reference = notification_data.get('invoice_id')
        if not reference:
            raise ValidationError("Sipay: " + _("Received data with missing invoice_id."))

        tx = self.search([('reference', '=', reference), ('provider_code', '=', 'sipay')])
        if not tx:
            raise ValidationError(
                "Sipay: " + _("No transaction found matching reference %s.", reference)
            )

        return tx

    def _process_notification_data(self, notification_data):
        """ Override of `payment` to process the transaction based on Sipay data.

        Note: self.ensure_one()

        :param dict notification_data: The notification data sent by the provider
        :return: None
        """
        super()._process_notification_data(notification_data)
        if self.provider_code != 'sipay':
            return

        # Verify the notification data
        self._sipay_verify_notification_data(notification_data)

        # Update the provider reference
        self.provider_reference = notification_data.get('order_no')

        # Update the payment state
        payment_status = notification_data.get('payment_status')
        transaction_type = notification_data.get('transaction_type')
        
        if payment_status == '1':
            if transaction_type == const.TRANSACTION_TYPE_PRE_AUTH:
                self._set_authorized()
            else:  # Auth
                self._set_done()
        else:
            error_code = notification_data.get('error_code', 'Unknown')
            error_description = notification_data.get('original_bank_error_description', 'Payment failed')
            self._set_error(f"Sipay Error {error_code}: {error_description}")

    def _sipay_verify_notification_data(self, notification_data):
        """Verify the integrity of the notification data."""
        self.ensure_one()

        received_hash = notification_data.get('hash_key')
        if received_hash:
            # Sipay'den gelen hash_key'i doğrula
            decrypted_data = self._sipay_validate_return_hash(
                received_hash, 
                self.provider_id.sipay_app_secret
            )
            
            if decrypted_data:
                # Decrypted verileri kontrol et
                if decrypted_data.get('invoice_id') != self.reference:
                    _logger.warning(
                        "Invoice ID mismatch in hash verification for transaction %s.\n"
                        "Decrypted: %s, Expected: %s",
                        self.reference, decrypted_data.get('invoice_id'), self.reference
                    )
                else:
                    _logger.info("Return hash key validated successfully for transaction %s", self.reference)
                    
                # Amount kontrolü (isteğe bağlı)
                expected_amount = "{:.2f}".format(self.amount)
                if decrypted_data.get('total') and decrypted_data.get('total') != expected_amount:
                    _logger.warning(
                        "Amount mismatch in hash verification for transaction %s.\n"
                        "Decrypted: %s, Expected: %s",
                        self.reference, decrypted_data.get('total'), expected_amount
                    )
            else:
                # Hash doğrulama başarısız, ancak işleme devam et
                _logger.warning(
                    "Hash validation failed for transaction %s, but continuing processing.\n"
                    "Received hash: %s",
                    self.reference, received_hash
                )

    def _send_refund_request(self, amount_to_refund=None):
        """ Override of `payment` to send a refund request to Sipay.

        Note: self.ensure_one()

        :param float amount_to_refund: The amount to refund.
        :return: The refund transaction created to process the refund request.
        :rtype: recordset of `payment.transaction`
        """
        refund_tx = super()._send_refund_request(amount_to_refund=amount_to_refund)
        if self.provider_code != 'sipay':
            return refund_tx

        # Get token first
        self.provider_id._sipay_get_token()

        # Make the refund request to Sipay
        payload = {
            'order_id': self.provider_reference,
            'refund_amount': -refund_tx.amount,  # The amount is negative for refund transactions
            'merchant_key': self.provider_id.sipay_merchant_key,
        }
        
        _logger.warning(
            "Sending refund request for transaction with reference %s:\n%s",
            self.reference, pprint.pformat(payload)
        )
        
        response_content = self.provider_id._sipay_make_request(
            const.API_REFUND_ENDPOINT, payload=payload
        )
        
        _logger.warning(
            "Refund response for transaction with reference %s:\n%s",
            self.reference, pprint.pformat(response_content)
        )

        # Process the refund response
        if isinstance(response_content, list) and len(response_content) > 0:
            response_content = response_content[0]

        if response_content.get('status_code') == 100:
            refund_tx._set_done()
        else:
            error_msg = response_content.get('status_description', 'Refund failed')
            refund_tx._set_error(f"Sipay: {error_msg}")

        return refund_tx

    def _send_capture_request(self, amount_to_capture=None):
        """ Override of `payment` to send a capture request to Sipay.

        Note: self.ensure_one()

        :param float amount_to_capture: The amount to capture.
        :return: None
        """
        super()._send_capture_request(amount_to_capture=amount_to_capture)
        if self.provider_code != 'sipay':
            return

        # Get token first
        self.provider_id._sipay_get_token()

        # Make the capture request to Sipay
        payload = {
            'order_id': self.provider_reference,
            'merchant_key': self.provider_id.sipay_merchant_key,
        }
        
        _logger.warning(
            "Sending capture request for transaction with reference %s:\n%s",
            self.reference, pprint.pformat(payload)
        )
        
        response_content = self.provider_id._sipay_make_request(
            const.API_CONFIRM_PAYMENT_ENDPOINT, payload=payload
        )
        
        _logger.warning(
            "Capture response for transaction with reference %s:\n%s",
            self.reference, pprint.pformat(response_content)
        )

        # Process the capture response
        if isinstance(response_content, list) and len(response_content) > 0:
            response_content = response_content[0]

        if response_content.get('status_code') == 100:
            self._set_done()
        else:
            error_msg = response_content.get('status_description', 'Capture failed')
            self._set_error(f"Sipay: {error_msg}")

    def _send_void_request(self, amount_to_void=None):
        """ Override of `payment` to send a void request to Sipay.

        Note: self.ensure_one()

        :param float amount_to_void: The amount to void.
        :return: None
        """
        super()._send_void_request(amount_to_void=amount_to_void)
        if self.provider_code != 'sipay':
            return

        # Get token first
        self.provider_id._sipay_get_token()

        # Make the void request to Sipay
        payload = {
            'order_id': self.provider_reference,
            'merchant_key': self.provider_id.sipay_merchant_key,
        }
        
        _logger.warning(
            "Sending void request for transaction with reference %s:\n%s",
            self.reference, pprint.pformat(payload)
        )
        
        response_content = self.provider_id._sipay_make_request(
            const.API_CANCEL_PAYMENT_ENDPOINT, payload=payload
        )
        
        _logger.warning(
            "Void response for transaction with reference %s:\n%s",
            self.reference, pprint.pformat(response_content)
        )

        # Process the void response
        if isinstance(response_content, list) and len(response_content) > 0:
            response_content = response_content[0]

        if response_content.get('status_code') == 100:
            self._set_canceled()
        else:
            error_msg = response_content.get('status_description', 'Void failed')
            self._set_error(f"Sipay: {error_msg}")