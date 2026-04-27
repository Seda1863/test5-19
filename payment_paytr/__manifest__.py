# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "Payment Provider: PayTR",
    "version": "1.0",
    "category": "Accounting/Payment Providers",
    "sequence": 350,
    "summary": "PayTR integration for Odoo payment system (iframe & token based).",
    "description": "Integration of PayTR payment provider with Odoo Payment module.",
    "depends": ["payment"],
    "data": [
        "views/payment_provider_views.xml",
        "views/payment_paytr_templates.xml",
        "data/payment_provider_data.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "payment_paytr/static/src/js/payment_form.js",
            "payment_paytr/static/src/js/payment_paytr_mixin.js",
        ],
    },
    "license": "LGPL-3",
}
