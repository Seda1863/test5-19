/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PaymentForm } from "@payment/js/payment_form";
import { rpc } from "@web/core/network/rpc";

function _getSipayInlineFormInputs(paymentOptionId) {
    let container = document.getElementById(`sipay-container-${paymentOptionId}`);
    if (!container) {
        for (const id of [`payment_option_${paymentOptionId}`, `payment-option-${paymentOptionId}`]) {
            const el = document.getElementById(id);
            if (el) {
                const found = el.querySelector('[data-sipay-container="true"], .o_sipay_form');
                if (found) { container = found; break; }
            }
        }
    }
    if (!container) container = document.querySelector('[data-sipay-container="true"], .o_sipay_form');
    if (!container) {
        console.error(`Sipay: missing container for paymentOptionId ${paymentOptionId}`);
        return {};
    }
    return {
        ccHolderName: container.querySelector('.o_sipay_cc_holder_name') || container.querySelector(`#o_sipay_cc_holder_name_${paymentOptionId}`),
        ccNo:         container.querySelector('.o_sipay_cc_no')          || container.querySelector(`#o_sipay_cc_no_${paymentOptionId}`),
        expiryMonth:  container.querySelector('.o_sipay_expiry_month')   || container.querySelector(`#o_sipay_expiry_month_${paymentOptionId}`),
        expiryYear:   container.querySelector('.o_sipay_expiry_year')    || container.querySelector(`#o_sipay_expiry_year_${paymentOptionId}`),
        cvv:          container.querySelector('.o_sipay_cvv')            || container.querySelector(`#o_sipay_cvv_${paymentOptionId}`),
        installments: container.querySelector('.o_sipay_installments')   || container.querySelector(`#o_sipay_installments_${paymentOptionId}`),
    };
}

patch(PaymentForm.prototype, {

    async _prepareInlineForm(providerId, providerCode, paymentOptionId, paymentMethodCode, flow) {
        if (providerCode !== 'sipay') {
            return super._prepareInlineForm(...arguments);
        }
        if (flow === 'token') {
            return;
        }
        this._setPaymentFlow('direct');
    },

    async _processDirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (providerCode !== 'sipay') {
            return super._processDirectFlow(...arguments);
        }
        await this._processSipayPayment(paymentOptionId, processingValues);
    },

    async _processSipayPayment(paymentOptionId, processingValues) {
        if (typeof this._disableButton === 'function') this._disableButton();

        try {
            const inputs = _getSipayInlineFormInputs(paymentOptionId);

            const ccHolderNameEl = inputs.ccHolderName || document.querySelector('.o_sipay_cc_holder_name');
            const ccNoEl         = inputs.ccNo         || document.querySelector('.o_sipay_cc_no');
            const expiryMonthEl  = inputs.expiryMonth  || document.querySelector('.o_sipay_expiry_month');
            const expiryYearEl   = inputs.expiryYear   || document.querySelector('.o_sipay_expiry_year');
            const cvvEl          = inputs.cvv          || document.querySelector('.o_sipay_cvv');
            const installmentsEl = inputs.installments || document.querySelector('.o_sipay_installments');

            const ccHolderName = ccHolderNameEl ? ccHolderNameEl.value.trim() : '';
            const ccNo         = ccNoEl         ? ccNoEl.value.trim().replace(/\s/g, '') : '';
            const expiryMonth  = expiryMonthEl  ? expiryMonthEl.value.trim() : '';
            const expiryYear   = expiryYearEl   ? expiryYearEl.value.trim() : '';
            const cvv          = cvvEl          ? cvvEl.value.trim() : '';
            const installments = installmentsEl ? installmentsEl.value : '1';

            if (!ccHolderName || !ccNo || !expiryMonth || !expiryYear || !cvv) {
                this._displayErrorDialog("Eksik Bilgi", "Lütfen tüm kart bilgilerini eksiksiz doldurun.");
                if (typeof this._enableButton === 'function') this._enableButton();
                return;
            }

            if (ccNo.length < 15 || ccNo.length > 19 || !/^\d+$/.test(ccNo)) {
                this._displayErrorDialog("Geçersiz Kart Numarası", "Lütfen geçerli bir kart numarası giriniz.");
                if (typeof this._enableButton === 'function') this._enableButton();
                return;
            }

            if (cvv.length < 3 || cvv.length > 4 || !/^\d+$/.test(cvv)) {
                this._displayErrorDialog("Geçersiz CVV", "Lütfen geçerli bir CVV giriniz.");
                if (typeof this._enableButton === 'function') this._enableButton();
                return;
            }

            let fullExpiryYear = expiryYear.length === 2 ? '20' + expiryYear : expiryYear;

            this._showSipayLoadingState();

            const response = await rpc('/payment/sipay/get_3d_form_data', {
                'reference': processingValues.reference,
                'cc_holder_name': ccHolderName,
                'cc_no': ccNo,
                'expiry_month': expiryMonth,
                'expiry_year': fullExpiryYear,
                'cvv': cvv,
                'installments': installments,
            });

            if (!response.success) {
                this._hideSipayLoadingState();
                this._displayErrorDialog("Hata", response.error || "3D Secure form verisi alınamadı.");
                if (typeof this._enableButton === 'function') this._enableButton();
                return;
            }

            const form = document.createElement('form');
            form.method = 'POST';
            form.action = response.form_action;
            form.target = '_top';
            form.style.display = 'none';
            form.setAttribute('accept-charset', 'UTF-8');

            for (const [key, value] of Object.entries(response.form_fields)) {
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = key;
                input.value = value;
                form.appendChild(input);
            }

            document.body.appendChild(form);

            const originalOnError = window.onerror;
            window.onerror = function(msg) {
                if (msg && typeof msg === 'string' &&
                    (msg.includes('cross-origin') || msg.includes('SecurityError'))) {
                    return true;
                }
                return originalOnError ? originalOnError(...arguments) : false;
            };

            setTimeout(() => {
                try {
                    form.submit();
                    setTimeout(() => { window.onerror = originalOnError; }, 2000);
                } catch (err) {
                    window.onerror = originalOnError;
                    this._hideSipayLoadingState();
                    this._displayErrorDialog("Yönlendirme Hatası", "3D Secure sayfasına yönlendirilemedi. Lütfen tekrar deneyin.");
                    if (typeof this._enableButton === 'function') this._enableButton();
                }
            }, 100);

        } catch (error) {
            console.error('Sipay payment error:', error);
            this._hideSipayLoadingState();
            this._displayErrorDialog("Hata", "Ödeme işlemi başlatılamadı. Lütfen tekrar deneyin.");
            if (typeof this._enableButton === 'function') this._enableButton();
        }
    },

    _showSipayLoadingState() {
        if (typeof this._disableButton === 'function') this._disableButton();
        if (!document.getElementById('sipay-loading')) {
            const loader = document.createElement('div');
            loader.id = 'sipay-loading';
            loader.innerHTML = `
                <div style="position:fixed;top:0;left:0;width:100%;height:100%;
                            background:rgba(255,255,255,0.9);z-index:9999;
                            display:flex;justify-content:center;align-items:center;">
                    <div style="text-align:center;padding:30px;background:white;
                                border-radius:12px;box-shadow:0 4px 20px rgba(0,0,0,0.15);">
                        <h3 style="margin:0 0 15px 0;color:#333;">3D Secure Yönlendiriliyor...</h3>
                        <p style="margin:0 0 20px 0;color:#666;">Bankanızın 3D Secure sayfasına yönlendiriliyorsunuz.</p>
                        <div style="display:inline-block;width:40px;height:40px;border:4px solid #f3f3f3;
                                    border-top:4px solid #3498db;border-radius:50%;animation:spin 1s linear infinite;">
                        </div>
                    </div>
                </div>
                <style>@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}</style>
            `;
            document.body.appendChild(loader);
        }
    },

    _hideSipayLoadingState() {
        const loader = document.getElementById('sipay-loading');
        if (loader) loader.remove();
    },

    _displayErrorDialog(title, message) {
        if (typeof this.displayError === 'function') {
            this.displayError({ title, message });
        } else {
            alert(`${title}: ${message}`);
        }
    },

    _getInlineFormInputs(paymentOptionId, providerCode) {
        if (providerCode === 'sipay') {
            return _getSipayInlineFormInputs(paymentOptionId);
        }
        return super._getInlineFormInputs(...arguments);
    },
});
