# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "Payment Provider: Sipay",
    "version": "1.58",
    "category": "Accounting/Payment Providers",
    "sequence": 350,
    "summary": "A Turkish payment provider supporting 3D Secure payments.",
    "description": " ",  # Non-empty string to avoid loading the README file.
    "depends": ["payment"],
    "external_dependencies": {
        "python": ["Crypto"],
    },
    "data": [
        "views/payment_provider_views.xml",
        "views/payment_sipay_templates.xml",
        "data/payment_provider_data.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "payment_sipay/static/src/js/payment_form.js",
            "payment_sipay/static/src/js/payment_sipay_mixin.js",
        ],
    },
    "license": "LGPL-3",
}
