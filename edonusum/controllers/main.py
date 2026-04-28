from odoo import http
from odoo.http import request
import requests

class EdonusumController(http.Controller):

    @http.route('/api/validate_license', type='jsonrpc', auth='user')
    def validate_license(self, license_key):
        if not license_key:
            return {'valid': False, 'error': 'Lisans anahtarı eksik.'}

        # Lisans doğrulama API'sine istek gönder
        api_url = "http://20.160.81.46:5000/api/validate"
        payload = {"license_key": license_key}
        try:
            response = requests.post(api_url, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data
        except requests.exceptions.RequestException as e:
            return {'valid': False, 'error': str(e)}