/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PaymentForm } from "@payment/js/payment_form";
import { rpc } from "@web/core/network/rpc";

function _getPaytrInlineFormInputs(paymentOptionId) {
    let container = document.getElementById(`paytr-container-${paymentOptionId}`);

    if (!container) {
        const wrapperIds = [
            `payment_option_${paymentOptionId}`,
            `payment-option-${paymentOptionId}`,
        ];
        for (const id of wrapperIds) {
            const el = document.getElementById(id);
            if (el) {
                const found = el.querySelector('[data-paytr-container="true"], .o_paytr_form');
                if (found) { container = found; break; }
            }
        }
    }

    if (!container) {
        const any = document.querySelector('[data-paytr-container="true"], .o_paytr_form');
        if (any) container = any;
    }

    if (!container) {
        console.error(`PayTR: missing container for paymentOptionId ${paymentOptionId}`);
        return {};
    }

    return {
        ccOwner:      container.querySelector('.o_paytr_cc_owner')      || container.querySelector(`#o_paytr_cc_owner_${paymentOptionId}`),
        cardNumber:   container.querySelector('.o_paytr_card_number')   || container.querySelector(`#o_paytr_card_number_${paymentOptionId}`),
        expiryMonth:  container.querySelector('.o_paytr_expiry_month')  || container.querySelector(`#o_paytr_expiry_month_${paymentOptionId}`),
        expiryYear:   container.querySelector('.o_paytr_expiry_year')   || container.querySelector(`#o_paytr_expiry_year_${paymentOptionId}`),
        cvv:          container.querySelector('.o_paytr_cvv')           || container.querySelector(`#o_paytr_cvv_${paymentOptionId}`),
        installments: container.querySelector('.o_paytr_installments')  || container.querySelector(`#o_paytr_installments_${paymentOptionId}`),
    };
}

patch(PaymentForm.prototype, {

    async _prepareInlineForm(providerId, providerCode, paymentOptionId, paymentMethodCode, flow) {
        if (providerCode !== 'paytr') {
            return super._prepareInlineForm(...arguments);
        }
        if (flow === 'token') {
            return;
        }
        this._setPaymentFlow('direct');
    },

    async _processDirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (providerCode !== 'paytr') {
            return super._processDirectFlow(...arguments);
        }
        await this._processPaytrPayment(paymentOptionId, processingValues);
    },

    async _processPaytrPayment(paymentOptionId, processingValues) {
        if (typeof this._disableButton === 'function') this._disableButton();

        try {
            const inputs = _getPaytrInlineFormInputs(paymentOptionId);

            const ccOwnerEl      = inputs.ccOwner      || document.querySelector('.o_paytr_cc_owner');
            const cardNumberEl   = inputs.cardNumber   || document.querySelector('.o_paytr_card_number');
            const expiryMonthEl  = inputs.expiryMonth  || document.querySelector('.o_paytr_expiry_month');
            const expiryYearEl   = inputs.expiryYear   || document.querySelector('.o_paytr_expiry_year');
            const cvvEl          = inputs.cvv          || document.querySelector('.o_paytr_cvv');
            const installmentsEl = inputs.installments || document.querySelector('.o_paytr_installments');

            const ccOwner     = ccOwnerEl      ? ccOwnerEl.value.trim()                         : '';
            const cardNumber  = cardNumberEl   ? cardNumberEl.value.trim().replace(/\s/g, '')   : '';
            const expiryMonth = expiryMonthEl  ? expiryMonthEl.value.trim()                     : '';
            const expiryYear  = expiryYearEl   ? expiryYearEl.value.trim()                      : '';
            const cvv         = cvvEl          ? cvvEl.value.trim()                             : '';
            const installments = installmentsEl ? installmentsEl.value : '1';

            if (!ccOwner || !cardNumber || !expiryMonth || !expiryYear || !cvv) {
                this._displayErrorDialog("Eksik Bilgi", "Lütfen tüm kart bilgilerini eksiksiz doldurun.");
                if (typeof this._enableButton === 'function') this._enableButton();
                return;
            }

            if (cardNumber.length < 15 || cardNumber.length > 19 || !/^\d+$/.test(cardNumber)) {
                this._displayErrorDialog("Geçersiz Kart Numarası", "Lütfen geçerli bir kart numarası giriniz.");
                if (typeof this._enableButton === 'function') this._enableButton();
                return;
            }

            if (cvv.length < 3 || cvv.length > 4 || !/^\d+$/.test(cvv)) {
                this._displayErrorDialog("Geçersiz CVV", "Lütfen geçerli bir CVV giriniz.");
                if (typeof this._enableButton === 'function') this._enableButton();
                return;
            }

            this._showPaytrLoadingState();

            const response = await rpc('/payment/paytr/get_direct_form_data', {
                'reference': processingValues.reference,
                'cc_owner': ccOwner,
                'card_number': cardNumber,
                'expiry_month': expiryMonth,
                'expiry_year': expiryYear,
                'cvv': cvv,
                'installments': installments,
            });

            if (!response.success) {
                this._hidePaytrLoadingState();
                this._displayErrorDialog("Hata", response.error || "PayTR form verisi alınamadı.");
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
                    this._hidePaytrLoadingState();
                    this._displayErrorDialog("Yönlendirme Hatası", "3D Secure sayfasına yönlendirilemedi. Lütfen tekrar deneyin.");
                    if (typeof this._enableButton === 'function') this._enableButton();
                }
            }, 100);

        } catch (error) {
            console.error('PayTR payment error:', error);
            this._hidePaytrLoadingState();
            this._displayErrorDialog("Hata", "Ödeme işlemi başlatılamadı. Lütfen tekrar deneyin.");
            if (typeof this._enableButton === 'function') this._enableButton();
        }
    },

    _showPaytrLoadingState() {
        if (typeof this._disableButton === 'function') this._disableButton();
        if (!document.getElementById('paytr-loading')) {
            const loader = document.createElement('div');
            loader.id = 'paytr-loading';
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

    _hidePaytrLoadingState() {
        const loader = document.getElementById('paytr-loading');
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
        if (providerCode === 'paytr') {
            return _getPaytrInlineFormInputs(paymentOptionId);
        }
        return super._getInlineFormInputs(...arguments);
    },
});
