# Part of Odoo. See LICENSE file for full copyright and licensing details.

# Supported currencies by Sipay
SUPPORTED_CURRENCIES = [
    'TRY',  # Turkish Lira
    'USD',  # US Dollar  
    'EUR',  # Euro
    'GBP',  # British Pound
]

# Default payment method codes
DEFAULT_PAYMENT_METHOD_CODES = [
    'card',
]

# API Endpoints
API_TOKEN_ENDPOINT = 'api/token'
API_PAYMENT_ENDPOINT = 'api/paySmart3D'
API_PAYMENT_COMPLETE_ENDPOINT = 'payment/complete'
API_CHECK_STATUS_ENDPOINT = 'api/checkstatus'
API_REFUND_ENDPOINT = 'api/refund'
API_CONFIRM_PAYMENT_ENDPOINT = 'api/confirmPayment'
API_CANCEL_PAYMENT_ENDPOINT = 'api/cancelPayment'

# Transaction types
TRANSACTION_TYPE_AUTH = 'Auth'
TRANSACTION_TYPE_PRE_AUTH = 'PreAuth'

# Payment status codes
STATUS_SUCCESS = '1'
STATUS_FAILED = '0'
STATUS_CANCELLED = '-1'

# Error codes
ERROR_3D_FAILED = '3D_FAILED'
ERROR_INSUFFICIENT_FUNDS = 'INSUFFICIENT_FUNDS'
ERROR_INVALID_CARD = 'INVALID_CARD'
ERROR_EXPIRED_CARD = 'EXPIRED_CARD'