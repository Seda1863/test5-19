/** @odoo-module **/

import paymentForm from '@payment/js/payment_form';
import { rpc } from "@web/core/network/rpc";

paymentForm.include({

    async _prepareInlineForm(providerId, providerCode, paymentOptionId, paymentMethodCode, flow) {
        console.log('Iyzico _prepareInlineForm called', providerCode);
        if (providerCode !== 'iyzico') {
            return this._super(...arguments);
        }
        this._setPaymentFlow('direct');
    },

    async _processDirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        console.log('_processDirectFlow called for', providerCode);
        if (providerCode !== 'iyzico') {
            return this._super(...arguments);
        }
        await this._processIyzicoPayment(processingValues);
    },

    async _processIyzicoPayment(processingValues) {
        console.log('Iyzico ödeme başlatılıyor...', processingValues);

        try {
            const response = await rpc('/payment/iyzico/initialize_checkout', {
                reference: processingValues.reference,
            });

            // --- Yanıt doğrulama ---
            if (!response || !(response.paymentPageUrl || response.payment_url)) {
                console.error('Iyzico: Geçersiz yanıt', response);
                alert("Iyzico bağlantısı oluşturulamadı. Lütfen tekrar deneyin.");
                return;
            }

            // --- URL Seçimi ---
            const redirectUrl = response.paymentPageUrl || response.payment_url;
            console.log('Redirecting to:', redirectUrl);

            // --- Yönlendirme ---
            window.top.location.href = redirectUrl;

        } catch (err) {
            console.error('Iyzico hata:', err);
            alert("Iyzico ödeme başlatılamadı. Lütfen tekrar deneyin.");
        }
    },
});
