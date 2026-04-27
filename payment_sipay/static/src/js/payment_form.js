/** @odoo-module **/

import paymentForm from '@payment/js/payment_form';
import { rpc } from "@web/core/network/rpc";

// #=== GETTERS ===#

/**
 * Return all relevant inline form inputs of the provided payment option.
 *
 * Tries multiple fallbacks:
 * 1) exact container id -> #sipay-container-<paymentOptionId>
 * 2) inside payment option wrapper ids (common variants)
 * 3) any element with data-sipay-container="true" (first match)
 * 4) finally searches document-level class selectors as a last resort
 *
 * @private
 * @param {number} paymentOptionId - The id of the selected payment option.
 * @return {Object} - An object mapping the name of inline form inputs to their DOM element.
 */
function _getSipayInlineFormInputs(paymentOptionId) {
    console.log('_getSipayInlineFormInputs called for paymentOptionId', paymentOptionId);

    let container = document.getElementById(`sipay-container-${paymentOptionId}`);
    if (!container) {
        const wrapperIds = [
            `payment_option_${paymentOptionId}`,
            `payment-option-${paymentOptionId}`,
            `payment-option_${paymentOptionId}`,
            `payment_option-${paymentOptionId}`,
        ];
        for (const id of wrapperIds) {
            const el = document.getElementById(id);
            if (el) {
                const found = el.querySelector('[data-sipay-container="true"], .o_sipay_form');
                if (found) {
                    container = found;
                    console.log('Found container inside wrapper', id, found);
                    break;
                }
            }
        }
    }

    if (!container) {
        const any = document.querySelector('[data-sipay-container="true"], .o_sipay_form');
        if (any) {
            container = any;
            console.warn('Falling back to any data-sipay-container element', container);
        }
    }

    if (!container) {
        const anyByClass = document.querySelector('.o_sipay_form');
        if (anyByClass) {
            container = anyByClass;
            console.warn('Falling back to first .o_sipay_form in document', container);
        }
    }

    if (!container) {
        console.error(`Sipay: missing container for paymentOptionId ${paymentOptionId}`);
        return {};
    }

    return {
        ccHolderName: container.querySelector('.o_sipay_cc_holder_name') || container.querySelector(`#o_sipay_cc_holder_name_${paymentOptionId}`),
        ccNo:         container.querySelector('.o_sipay_cc_no')         || container.querySelector(`#o_sipay_cc_no_${paymentOptionId}`),
        expiryMonth:  container.querySelector('.o_sipay_expiry_month')  || container.querySelector(`#o_sipay_expiry_month_${paymentOptionId}`),
        expiryYear:   container.querySelector('.o_sipay_expiry_year')   || container.querySelector(`#o_sipay_expiry_year_${paymentOptionId}`),
        cvv:          container.querySelector('.o_sipay_cvv')          || container.querySelector(`#o_sipay_cvv_${paymentOptionId}`),
        installments: container.querySelector('.o_sipay_installments') || container.querySelector(`#o_sipay_installments_${paymentOptionId}`),
        _container: container,
    };
}

paymentForm.include({

    // #=== DOM MANIPULATION ===#

    /**
     * Prepare the inline form of Sipay for direct payment.
     *
     * @override method from @payment/js/payment_form
     * @private
     * @param {number} providerId - The id of the selected payment option's provider.
     * @param {string} providerCode - The code of the selected payment option's provider.
     * @param {number} paymentOptionId - The id of the selected payment option
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {string} flow - The online payment flow of the selected payment option.
     * @return {void}
     */
    async _prepareInlineForm(providerId, providerCode, paymentOptionId, paymentMethodCode, flow) {
        console.log('Sipay _prepareInlineForm called', providerCode, paymentOptionId, flow);
        if (providerCode !== 'sipay') {
            console.log('Not Sipay, calling super');
            this._super(...arguments);
            return;
        } else if (flow === 'token') {
            console.warn('Sipay does not support tokenization, switching to direct flow');
            return;
        }
        console.log('Preparing Sipay inline form for direct flow');
        this._setPaymentFlow('direct');
    },

    // #=== PAYMENT FLOW ===#

    /**
     * Process Sipay payment with card details.
     *
     * @override method from payment.payment_form
     * @private
     * @param {string} providerCode - The code of the selected payment option's provider.
     * @param {number} paymentOptionId - The id of the selected payment option.
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {object} processingValues - The processing values of the transaction.
     * @return {void}
     */
    async _prepareInlineForm(providerId, providerCode, paymentOptionId, paymentMethodCode, flow) {
        console.log('Sipay _prepareInlineForm called', providerCode, paymentOptionId, flow);
        if (providerCode !== 'sipay') {
            console.log('Not Sipay, calling super');
            this._super(...arguments);
            return;
        } else if (flow === 'token') {
            console.warn('Sipay does not support tokenization, switching to direct flow');
            return;
        }
        console.log('Preparing Sipay inline form for direct flow');
        this._setPaymentFlow('direct');
    },

    async _processDirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        console.log('_processDirectFlow called for provider', providerCode, 'option', paymentOptionId);
        if (providerCode !== 'sipay') {
            console.log('Not Sipay, calling super');
            this._super(...arguments);
            return;
        }
        console.log('Processing Sipay direct flow payment');
        await this._processSipayPayment(paymentOptionId, processingValues);
    },

    /**
     * Process Sipay payment with card details.
     *
     * @private
     * @param {number} paymentOptionId - the payment option DOM id (from payment widget)
     * @param {object} processingValues - The processing values of the transaction.
     * @return {void}
     */
    async _processSipayPayment(paymentOptionId, processingValues) {
        console.log('_processSipayPayment called for option', paymentOptionId, 'processingValues', processingValues);

        if (typeof this._disableButton === 'function') {
            this._disableButton();
        }

        try {
            console.log('Getting inline form inputs for paymentOptionId:', paymentOptionId);
            const inputs = _getSipayInlineFormInputs(paymentOptionId);
            console.log('Inputs found:', inputs);

            const ccHolderNameEl = inputs.ccHolderName || document.querySelector('.o_sipay_cc_holder_name');
            const ccNoEl = inputs.ccNo || document.querySelector('.o_sipay_cc_no');
            const expiryMonthEl = inputs.expiryMonth || document.querySelector('.o_sipay_expiry_month');
            const expiryYearEl = inputs.expiryYear || document.querySelector('.o_sipay_expiry_year');
            const cvvEl = inputs.cvv || document.querySelector('.o_sipay_cvv');
            const installmentsEl = inputs.installments || document.querySelector('.o_sipay_installments');

            const ccHolderName = ccHolderNameEl ? ccHolderNameEl.value.trim() : '';
            const ccNo = ccNoEl ? ccNoEl.value.trim().replace(/\s/g, '') : '';
            const expiryMonth = expiryMonthEl ? expiryMonthEl.value.trim() : '';
            const expiryYear = expiryYearEl ? expiryYearEl.value.trim() : '';
            const cvv = cvvEl ? cvvEl.value.trim() : '';
            const installments = installmentsEl ? installmentsEl.value : '1';

            // Validasyonlar
            if (!ccHolderName || !ccNo || !expiryMonth || !expiryYear || !cvv) {
                this._displayErrorDialog(
                    "Eksik Bilgi",
                    "Lütfen tüm kart bilgilerini eksiksiz doldurun."
                );
                if (typeof this._enableButton === 'function') {
                    this._enableButton();
                }
                return;
            }

            if (ccNo.length < 15 || ccNo.length > 19 || !/^\d+$/.test(ccNo)) {
                this._displayErrorDialog(
                    "Geçersiz Kart Numarası",
                    "Lütfen geçerli bir kart numarası giriniz."
                );
                if (typeof this._enableButton === 'function') {
                    this._enableButton();
                }
                return;
            }

            if (cvv.length < 3 || cvv.length > 4 || !/^\d+$/.test(cvv)) {
                this._displayErrorDialog(
                    "Geçersiz CVV",
                    "Lütfen geçerli bir CVV numarası giriniz."
                );
                if (typeof this._enableButton === 'function') {
                    this._enableButton();
                }
                return;
            }

            let fullExpiryYear = expiryYear;
            if (expiryYear.length === 2) {
                fullExpiryYear = '20' + expiryYear;
            }

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
                this._displayErrorDialog(
                    "Hata",
                    response.error || "3D Secure form verisi alınamadı."
                );
                if (typeof this._enableButton === 'function') {
                    this._enableButton();
                }
                return;
            }

            console.log('Form action:', response.form_action);
            console.log('Form fields:', Object.keys(response.form_fields));

            // Create form with target="_top" to bypass iframe restrictions
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = response.form_action;
            form.target = '_top'; // Değişiklik: _self yerine _top kullan
            form.style.display = 'none';
            form.setAttribute('data-sipay-3d-form', 'true');
            form.setAttribute('accept-charset', 'UTF-8');

            // Add all form fields
            for (const [key, value] of Object.entries(response.form_fields)) {
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = key;
                input.value = value;
                form.appendChild(input);
                
                console.log(`Adding field: ${key} = ${key.includes('cvv') || key.includes('cc_no') || key.includes('hash_key') || key.includes('merchant_key') ? '***' : value}`);
            }

            document.body.appendChild(form);
            
            console.log('Form created, submitting to:', response.form_action);
            
            // Odoo event handler'larını geçici olarak devre dışı bırak
            const originalOnError = window.onerror;
            window.onerror = function(msg, url, lineNo, columnNo, error) {
                if (msg && typeof msg === 'string' && 
                    (msg.includes('cross-origin') || msg.includes('SecurityError'))) {
                    console.log('Suppressed cross-origin error during 3D Secure redirect');
                    return true; // Hatayı bastır
                }
                if (originalOnError) {
                    return originalOnError(msg, url, lineNo, columnNo, error);
                }
                return false;
            };

            // Formu gönder
            setTimeout(() => {
                try {
                    form.submit();
                    console.log('Form submitted successfully');
                    
                    // Event handler'ı 2 saniye sonra geri yükle
                    setTimeout(() => {
                        window.onerror = originalOnError;
                    }, 2000);
                } catch (error) {
                    console.error('Form submission error:', error);
                    window.onerror = originalOnError;
                    this._hideSipayLoadingState();
                    this._displayErrorDialog(
                        "Yönlendirme Hatası",
                        "3D Secure sayfasına yönlendirilemedi. Lütfen tekrar deneyin."
                    );
                    if (typeof this._enableButton === 'function') {
                        this._enableButton();
                    }
                }
            }, 100); // 500ms'den 100ms'ye düşürdük

        } catch (error) {
            console.error('Error preparing 3D Secure payment:', error);
            this._hideSipayLoadingState();
            this._displayErrorDialog(
                "Hata",
                "3D Secure işlemi başlatılamadı. Lütfen tekrar deneyin."
            );
            if (typeof this._enableButton === 'function') {
                this._enableButton();
            }
        }
    },

    /**
     * Loading state göster
     */
    _showSipayLoadingState() {
        console.log('Showing Sipay loading state...');
        
        if (typeof this._disableButton === 'function') {
            this._disableButton();
        }
        
        const loadingElement = document.querySelector('.o_payment_processing');
        if (loadingElement) {
            loadingElement.style.display = 'block';
        }
        
        const existingLoader = document.getElementById('sipay-loading');
        if (!existingLoader) {
            const loader = document.createElement('div');
            loader.id = 'sipay-loading';
            loader.innerHTML = `
                <div style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; 
                           background: rgba(255,255,255,0.9); z-index: 9999; 
                           display: flex; justify-content: center; align-items: center;">
                    <div style="text-align: center; padding: 30px; background: white; 
                               border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.15);">
                        <h3 style="margin: 0 0 15px 0; color: #333;">3D Secure Yönlendiriliyor...</h3>
                        <p style="margin: 0 0 20px 0; color: #666;">Lütfen bekleyin, bankanızın 3D Secure sayfasına yönlendiriliyorsunuz.</p>
                        <div style="margin-top: 20px;">
                            <div style="display: inline-block; width: 40px; height: 40px; border: 4px solid #f3f3f3; 
                                       border-top: 4px solid #3498db; border-radius: 50%; animation: spin 1s linear infinite;">
                            </div>
                        </div>
                    </div>
                </div>
                <style>
                    @keyframes spin {
                        0% { transform: rotate(0deg); }
                        100% { transform: rotate(360deg); }
                    }
                </style>
            `;
            document.body.appendChild(loader);
        }
    },

    /**
     * Loading state'i gizle
     */
    _hideSipayLoadingState() {
        console.log('Hiding Sipay loading state...');
        
        const loader = document.getElementById('sipay-loading');
        if (loader) {
            loader.remove();
        }
        
        const loadingElement = document.querySelector('.o_payment_processing');
        if (loadingElement) {
            loadingElement.style.display = 'none';
        }
    },

    /**
     * Hata dialog göster
     */
    _displayErrorDialog(title, message) {
        console.error('Displaying error dialog:', title, message);
        
        if (typeof this.displayError === 'function') {
            this.displayError({
                title: title,
                message: message
            });
        } else {
            alert(`${title}: ${message}`);
        }
    },

    /**
     * Override _getInlineFormInputs to handle Sipay specific inputs
     */
    _getInlineFormInputs(paymentOptionId, providerCode) {
        if (providerCode === 'sipay') {
            return _getSipayInlineFormInputs(paymentOptionId);
        }
        return this._super(...arguments);
    },

});