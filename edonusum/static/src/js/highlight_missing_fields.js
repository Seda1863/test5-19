odoo.define('edonusum.highlight_missing_fields', function (require) {
    "use strict";

    var FormRenderer = require('web.FormRenderer');
    var NotificationManager = require('web.notification');

    FormRenderer.include({
        /**
         * Eksik sahaları vurgular ve kullanıcıya mesaj gösterir.
         */
        highlightMissingFields: function (params) {
            var self = this;

            // Eksik alanları vurgula
            params.fields.forEach(function (fieldName) {
                var $field = self.$(`[name="${fieldName}"]`);
                if ($field.length) {
                    $field.css({
                        'border': '2px solid red',
                        'background-color': '#f8d7da',
                    });
                    $field.focus(); // Cursor'u alana getir
                }
            });

            // Uyarı mesajını göster
            new NotificationManager(this).displayNotification({
                title: "Eksik Alanlar",
                message: params.message,
                type: "danger",
                sticky: true,
            });
        },

        _renderView: function () {
            this._super.apply(this, arguments);
            if (this.state.context.highlight_missing_fields_params) {
                this.highlightMissingFields(this.state.context.highlight_missing_fields_params);
            }
        },
    });
});
