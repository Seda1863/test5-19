/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PaymentForm } from "@payment/js/payment_form";
import { rpc } from "@web/core/network/rpc";

patch(PaymentForm.prototype, {

    async _prepareInlineForm(providerId, providerCode, paymentOptionId, paymentMethodCode, flow) {
        if (providerCode !== 'iyzico') {
            return super._prepareInlineForm(...arguments);
        }
        this._setPaymentFlow('direct');
    },

    async _processDirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (providerCode !== 'iyzico') {
            return super._processDirectFlow(...arguments);
        }
        await this._processIyzicoPayment(processingValues);
    },

    async _processIyzicoPayment(processingValues) {
        try {
            const response = await rpc('/payment/iyzico/initialize_checkout', {
                reference: processingValues.reference,
            });

            if (!response || !(response.paymentPageUrl || response.payment_url)) {
                console.error('Iyzico: Geçersiz yanıt', response);
                alert("Iyzico bağlantısı oluşturulamadı. Lütfen tekrar deneyin.");
                return;
            }

            window.top.location.href = response.paymentPageUrl || response.payment_url;

        } catch (err) {
            console.error('Iyzico hata:', err);
            alert("Iyzico ödeme başlatılamadı. Lütfen tekrar deneyin.");
        }
    },
});
