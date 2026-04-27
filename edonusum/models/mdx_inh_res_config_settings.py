from odoo import models, fields, api
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)

class MdxInhResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    edonusum_license_key = fields.Char(
        string="Lisans Anahtarı",
        config_parameter='edonusum.edonusum_license_key',
        compute='_compute_edonusum_license_key',
        help="Lisans anahtarınızı buraya girin",
        readonly=False,
        store=True,
    )

    edonusum_license_expiration_date = fields.Datetime(
        string="Lisans Bitiş Tarihi",
        config_parameter='edonusum.edonusum_license_expiration_date',
        compute='_compute_edonusum_license_expiration_date',
        store=True,
        help="Lisansın geçerlilik süresinin son tarihi",
        readonly=True,
    )
    is_edonusum_license_active = fields.Boolean(
        string="Lisans Aktif",
        compute='_compute_edonusum_license_status',
        help="Lisansın aktif/pasif durumunu gösterir",
        store=True,
        readonly=True,
    )
    validation_message = fields.Text(
        string="",
        help="Lisans doğrulama mesajı",
        readonly=True,
    )

    def _compute_edonusum_license_key(self):
        for record in self:
            record.edonusum_license_key = self.env['ir.config_parameter'].sudo().get_param(
                'edonusum.edonusum_license_key', default=''
            )

    @api.depends('edonusum_license_key')
    def _compute_edonusum_license_expiration_date(self):
        for record in self:
            if record.edonusum_license_key:
                record.validate_license_key()
            else:
                record.edonusum_license_expiration_date = False
                record.is_edonusum_license_active = False

    @api.depends('edonusum_license_expiration_date')
    def _compute_edonusum_license_status(self):
        for record in self:
            is_active = False
            if record.edonusum_license_expiration_date:
                is_active = record.edonusum_license_expiration_date >= fields.Datetime.now()
            record.is_edonusum_license_active = is_active
            self.env['ir.config_parameter'].sudo().set_param(
                'edonusum.is_edonusum_license_active', str(is_active)
            )

    def validate_license_key(self):
        for record in self:
            if not record.edonusum_license_key:
                raise UserError("Lütfen bir lisans anahtarı girin.")

            # Ana şirketin VAT (vergi numarası) değerini al
            main_company = self.env['res.company']._company_default_get()
            company_vat = main_company.vat
            if not company_vat:
                record.validation_message = "Ana şirketin vergi numarası (VAT) tanımlı değil."
                return

            api_url = "http://20.160.81.46:5000/api/validate"
            payload = {
                "license_key": record.edonusum_license_key,
                "vat": company_vat  # VAT değerini API'ye gönder
            }
            try:
                response = requests.post(api_url, json=payload, timeout=10)
                response.raise_for_status()
                data = response.json()

                # Lisans doğrulama başarısızsa
                if not data.get("valid"):
                    record.validation_message = data.get("error", "Geçersiz lisans anahtarı.")
                    record.edonusum_license_expiration_date = False
                    record.is_edonusum_license_active = False
                    return

                # API'den dönen VAT değerini kontrol et
                api_vat = data.get("vat")
                if not api_vat:
                    record.validation_message = "API'den dönen vergi numarası (VAT) alınamadı."
                    record.edonusum_license_expiration_date = False
                    record.is_edonusum_license_active = False
                    return

                if api_vat != company_vat:
                    record.validation_message = (
                        f"Vergi numarası uyuşmazlığı: "
                        f"API'den dönen VAT ({api_vat}) ile şirketin VAT'ı ({company_vat}) uyuşmuyor."
                    )
                    record.edonusum_license_expiration_date = False
                    record.is_edonusum_license_active = False
                    return

                # Lisans geçerlilik tarihini kontrol et
                expiration_date = data.get("expiration_date")
                if not expiration_date:
                    record.validation_message = "Lisans geçerlilik tarihi alınamadı."
                    record.edonusum_license_expiration_date = False
                    record.is_edonusum_license_active = False
                    return

                # Lisans doğrulama başarılı
                record.edonusum_license_expiration_date = expiration_date
                record.validation_message = "Lisans doğrulama başarılı."
                self.env['ir.config_parameter'].sudo().set_param(
                    'edonusum.edonusum_license_key', record.edonusum_license_key
                )

            except requests.exceptions.RequestException as e:
                record.validation_message = f"API bağlantı hatası: {e}"

    @api.model
    def cron_update_license_expiration(self):
        """Lisans anahtarını kullanarak expiration_date'i API'den günceller."""
        license_key = self.env['ir.config_parameter'].sudo().get_param('edonusum.edonusum_license_key')
        if not license_key:
            _logger.warning("Lisans anahtarı bulunamadı.")
            return

        # Ana şirketin VAT (vergi numarası) değerini al
        main_company = self.env['res.company']._company_default_get()
        company_vat = main_company.vat
        if not company_vat:
            _logger.warning("Ana şirketin vergi numarası (VAT) tanımlı değil.")
            return

        api_url = "http://20.160.81.46:5000/api/validate"
        payload = {
            "license_key": license_key,
            "vat": company_vat
        }
        try:
            response = requests.post(api_url, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Lisans doğrulama başarısızsa
            if not data.get("valid"):
                _logger.error(f"Lisans doğrulama başarısız: {data.get('error')}")
                return

            # Lisans geçerlilik tarihini güncelle
            expiration_date = data.get("expiration_date")
            if expiration_date:
                self.env['ir.config_parameter'].sudo().set_param(
                    'edonusum.edonusum_license_expiration_date', expiration_date
                )
                _logger.info(f"Lisans geçerlilik tarihi güncellendi: {expiration_date}")
            else:
                _logger.warning("API'den geçerlilik tarihi alınamadı.")

        except requests.exceptions.RequestException as e:
            _logger.error(f"API bağlantı hatası: {e}")