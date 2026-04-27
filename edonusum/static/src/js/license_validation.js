/** filepath: c:\Users\ABAS\Documents\minddx-odoo\Odoo\addons\edonusum\static\src\js\license_validation.js **/
odoo.define('edonusum.license_validation', function (require) {
    "use strict";

    const rpc = require('web.rpc');
    const Notification = require('web.Notification');
    const core = require('web.core');
    const _t = core._t;

    function validateLicenseKey(licenseKey) {
        if (!licenseKey) {
            new Notification(this, {
                title: _t("Hata"),
                message: _t("Lütfen bir lisans anahtarı girin."),
                type: 'danger',
            }).show();
            return;
        }

        // Lisans doğrulama API'sine istek gönder
        rpc.query({
            route: '/api/validate_license',
            params: { license_key: licenseKey },
        }).then(function (response) {
            if (response.valid) {
                new Notification(this, {
                    title: _t("Başarılı"),
                    message: _t("Lisans başarıyla doğrulandı."),
                    type: 'success',
                }).show();
                // Sayfayı yenile
                location.reload();
            } else {
                new Notification(this, {
                    title: _t("Hata"),
                    message: _t("Geçersiz lisans anahtarı."),
                    type: 'danger',
                }).show();
            }
        }).catch(function (error) {
            new Notification(this, {
                title: _t("Hata"),
                message: _t("Lisans doğrulama sırasında bir hata oluştu."),
                type: 'danger',
            }).show();
            console.error(error);
        });
    }

    return {
        validateLicenseKey: validateLicenseKey,
    };
});