# -*- coding: utf-8 -*-
"""
entegra_backend.py
─────────────────
EntegraAPI bağlantı konfigürasyonu ve temel API client.

Token yönetimi KRİTİK:
  - Her request için token alma → otomatik IP ban (Entegra kuralı)
  - Access token: 1 hafta geçerli
  - Refresh token: 1 ay geçerli
  - Rate limit: 7200 req/saat, aşımda 15 dk IP engeli

Akış:
  get_valid_token() → cache geçerliyse dön
                    → süresi dolmuşsa refresh ile yenile
                    → refresh de dolmuşsa full login (son çare)
"""

import requests
import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Sabitler
# ─────────────────────────────────────────────
ENTEGRA_BASE_URL = 'https://apiv2.entegrabilisim.com'

ENTEGRA_ENDPOINTS = {
    'token_obtain':  '/api/user/token/obtain/',
    'token_refresh': '/api/user/token/refresh/',
    'products':      '/product/page={page}/',
    'products_list': '/product/list/v2/',
    'product_create':'/product/',
    'product_update':'/product/update/',
    'product_qty':   '/product/quantity/',
    'product_price': '/product/prices/',
    'product_variation_qty':   '/product/variation/quantity/',
    'product_variation_price': '/product/variation/price/',
    'variations':    '/product/variations/',
    'pictures':      '/product/pictures/',
    'orders':        '/order/page={page}/',
    'order_create':  '/order/',
    'order_update':  '/order/',
    'order_erp_update': '/order/update/',
    'order_shipment':'/order/sendShipment',
    'categories':    '/category/page={page}/',
    'stores':        '/store/getStores',
    'marketplace_qty_settings': '/store/getMarketplaceQuantitySettings',
    'brands':        '/product/brand/page={page}/',
    'prices':        '/price/getPrices',
    'marketplace_price_settings': '/price/getMarketplacePriceSettings',
    'customers':     '/customer/page={page}/',
}

# Entegra KDV oranları → Odoo vergi yüzdesi eşleme
KDV_RATE_MAP = {
    0:  0,
    8:  8,
    10: 10,
    18: 18,
    20: 20,
}

# Odoo vergi yüzdesi → Entegra kdv_id eşleme (ters)
ODOO_TAX_TO_KDV = {v: k for k, v in KDV_RATE_MAP.items()}


class EntegraBackend(models.Model):
    """
    Entegra bağlantı konfigürasyonu.
    Şirket başına tek backend tanımlanması önerilir.
    """
    _name = 'entegra.backend'
    _description = 'Entegra API Bağlantısı'
    _order = 'name'

    # ─── Temel Bilgiler ───────────────────────────────
    name = fields.Char(
        string='Bağlantı Adı',
        required=True,
        help='Örn: "Entegra Üretim" veya "Entegra Test"'
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Şirket',
        required=True,
        default=lambda self: self.env.company,
    )
    api_url = fields.Char(
        string='API URL',
        required=True,
        default=ENTEGRA_BASE_URL,
    )

    # ─── Kimlik Bilgileri ─────────────────────────────
    api_email = fields.Char(
        string='API Email',
        required=True,
        groups='base.group_system',
    )
    api_password = fields.Char(
        string='API Şifre',
        required=True,
        groups='base.group_system',
    )

    # ─── Token Cache (sistem alanları — UI'da sadece bilgi) ───
    access_token = fields.Char(
        string='Access Token',
        readonly=True,
        groups='base.group_system',
        copy=False,
    )
    refresh_token = fields.Char(
        string='Refresh Token',
        readonly=True,
        groups='base.group_system',
        copy=False,
    )
    token_expiry = fields.Datetime(
        string='Token Geçerlilik Tarihi',
        readonly=True,
        help='Access token bu tarihten sonra geçersiz.',
    )
    refresh_expiry = fields.Datetime(
        string='Refresh Token Geçerlilik Tarihi',
        readonly=True,
        help='Refresh token bu tarihten sonra geçersiz. Yeni login gerekir.',
    )
    last_token_refresh = fields.Datetime(
        string='Son Token Yenileme',
        readonly=True,
    )

    # ─── Senkronizasyon Ayarları ──────────────────────
    supplier_name = fields.Char(
        string='Supplier Adı (Entegra)',
        required=True,
        help='Entegra\'da ürün oluştururken kullanılan supplier alanı. Sonradan değiştirilemez.',
    )
    default_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Varsayılan Depo',
        help='Sipariş import ve stok senkronizasyonu için kullanılacak depo.',
    )
    entegra_store_id = fields.Integer(
        string='Entegra Store ID',
        default=0,
        help='Fiyat ve stok güncellemelerinde kullanılan depo ID (genellikle 0).',
    )

    # ─── Fiyat Mapping ────────────────────────────────
    price_mapping_ids = fields.One2many(
        'entegra.price.mapping',
        'backend_id',
        string='Fiyat Eşlemeleri',
        help='Odoo fiyat listesi → Entegra fiyat kodu eşlemesi.',
    )

    # ─── Sync Ayarları ────────────────────────────────
    order_import_sync_status = fields.Selection(
        selection=[('0', 'ERP\'ye Gönderilecek (sync=0)'),
                   ('1', 'ERP\'ye Gönderildi (sync=1)')],
        string='Sipariş Import Filtresi',
        default='0',
        help='Hangi sync durumundaki siparişler import edilsin.',
    )
    auto_confirm_orders = fields.Boolean(
        string='Siparişleri Otomatik Onayla',
        default=False,
        help='Import edilen siparişler otomatik olarak onaylansın mı?',
    )

    # ─── Durum ────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ('draft', 'Yapılandırılmadı'),
            ('connected', 'Bağlandı'),
            ('error', 'Hata'),
        ],
        string='Durum',
        default='draft',
        readonly=True,
    )
    last_error = fields.Text(string='Son Hata', readonly=True)

    # ═══════════════════════════════════════════════════
    # TOKEN YÖNETİMİ
    # ═══════════════════════════════════════════════════

    def get_valid_token(self):
        """
        Geçerli access token döner.

        Öncelik sırası:
          1. Cache'deki token hâlâ geçerliyse → döndür
          2. Access token süresi dolmuş, refresh geçerliyse → refresh yap
          3. Her ikisi de dolmuşsa → full login yap

        UYARI: Bu metod her API çağrısında kullanılmalı.
        Doğrudan token endpoint'i çağırma.
        """
        self.ensure_one()
        now = fields.Datetime.now()

        # 1. Cache kontrolü — token hâlâ geçerli mi?
        if (self.access_token
                and self.token_expiry
                and self.token_expiry > now + timedelta(minutes=30)):
            # 30 dakika tampon: süresi dolmadan önce yenile
            return self.access_token

        # 2. Refresh token geçerli mi?
        if (self.refresh_token
                and self.refresh_expiry
                and self.refresh_expiry > now):
            _logger.info('[Entegra:%s] Access token yenileniyor (refresh)', self.name)
            return self._refresh_access_token()

        # 3. Full login (son çare — her çağrıda yapılmamalı)
        _logger.info('[Entegra:%s] Full login yapılıyor', self.name)
        return self._obtain_token()

    def _obtain_token(self):
        """
        Email + password ile yeni token alır.
        Sadece ilk bağlantıda veya refresh token dolduğunda kullanılır.
        """
        self.ensure_one()
        url = self.api_url.rstrip('/') + ENTEGRA_ENDPOINTS['token_obtain']

        try:
            response = requests.post(
                url,
                json={
                    'email': self.api_email,
                    'password': self.api_password,
                },
                headers={'Content-Type': 'application/json'},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.Timeout:
            self._set_error('Token alınamadı: Bağlantı zaman aşımı.')
            raise UserError(_('Entegra API bağlantı zaman aşımı. Lütfen tekrar deneyin.'))
        except requests.exceptions.ConnectionError as e:
            self._set_error(f'Bağlantı hatası: {e}')
            raise UserError(_('Entegra API\'ye bağlanılamadı: %s') % str(e))
        except requests.exceptions.HTTPError as e:
            self._set_error(f'HTTP hatası: {e}')
            raise UserError(_('Entegra kimlik doğrulama hatası: %s') % str(e))

        access = data.get('access')
        refresh = data.get('refresh')

        if not access:
            self._set_error('Token yanıtında "access" alanı yok.')
            raise UserError(_('Entegra\'dan geçersiz token yanıtı alındı.'))

        now = fields.Datetime.now()
        self.sudo().write({
            'access_token': access,
            'refresh_token': refresh,
            'token_expiry': now + timedelta(days=7),
            'refresh_expiry': now + timedelta(days=30),
            'last_token_refresh': now,
            'state': 'connected',
            'last_error': False,
        })

        self.env['entegra.sync.log'].sudo().create({
            'backend_id': self.id,
            'operation': 'token_obtain',
            'status': 'success',
            'record_name': 'Full login',
        })

        _logger.info('[Entegra:%s] Token başarıyla alındı. Geçerlilik: 7 gün.', self.name)
        return access

    def _refresh_access_token(self):
        """
        Refresh token ile yeni access token alır.
        Full login yapmadan token ömrünü uzatır.
        """
        self.ensure_one()
        url = self.api_url.rstrip('/') + ENTEGRA_ENDPOINTS['token_refresh']

        try:
            response = requests.post(
                url,
                json={'refresh': self.refresh_token},
                headers={'Content-Type': 'application/json'},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.HTTPError:
            # Refresh token da geçersiz — full login'e düş
            _logger.warning('[Entegra:%s] Refresh başarısız, full login deneniyor.', self.name)
            return self._obtain_token()
        except Exception as e:
            self._set_error(f'Refresh hatası: {e}')
            raise UserError(_('Entegra token yenileme hatası: %s') % str(e))

        access = data.get('access')
        if not access:
            return self._obtain_token()

        now = fields.Datetime.now()
        self.sudo().write({
            'access_token': access,
            'token_expiry': now + timedelta(days=7),
            'last_token_refresh': now,
            'state': 'connected',
            'last_error': False,
        })

        self.env['entegra.sync.log'].sudo().create({
            'backend_id': self.id,
            'operation': 'token_refresh',
            'status': 'success',
            'record_name': 'Refresh token ile yenilendi',
        })

        _logger.info('[Entegra:%s] Access token refresh ile yenilendi.', self.name)
        return access

    # ═══════════════════════════════════════════════════
    # API CLIENT — TEMEL HTTP METODları
    # ═══════════════════════════════════════════════════

    def _get_headers(self):
        """Tüm API isteklerinde kullanılacak header."""
        token = self.get_valid_token()
        return {
            'Authorization': f'JWT {token}',
            'Content-Type': 'application/json',
        }

    def _request(self, method, endpoint, params=None, json_data=None, timeout=60):
        """
        Temel HTTP request metodu.
        Tüm API çağrıları bu metod üzerinden yapılır.

        Args:
            method:    'GET', 'POST', 'PUT'
            endpoint:  ENTEGRA_ENDPOINTS değerlerinden biri
            params:    URL query parametreleri (GET için)
            json_data: Request body (POST/PUT için)
            timeout:   Saniye cinsinden timeout

        Returns:
            dict: Parsed JSON response

        Raises:
            UserError: API hatası veya bağlantı sorunu
        """
        self.ensure_one()
        url = self.api_url.rstrip('/') + endpoint

        _logger.debug('[Entegra:%s] %s %s | params=%s', self.name, method, endpoint, params)

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                params=params,
                json=json_data,
                timeout=timeout,
            )
        except requests.exceptions.Timeout:
            msg = f'API zaman aşımı: {method} {endpoint}'
            self._set_error(msg)
            _logger.error('[Entegra:%s] %s', self.name, msg)
            raise UserError(_('Entegra API zaman aşımı: %s %s') % (method, endpoint))
        except requests.exceptions.ConnectionError as e:
            msg = f'Bağlantı hatası: {e}'
            self._set_error(msg)
            raise UserError(_('Entegra API bağlantı hatası: %s') % str(e))

        # HTTP hata kontrolü
        if response.status_code == 401:
            # Token geçersiz — sıfırla ve yeniden dene
            self.sudo().write({'access_token': False, 'token_expiry': False})
            _logger.warning('[Entegra:%s] 401 Unauthorized — token sıfırlandı.', self.name)
            raise UserError(_('Entegra yetkilendirme hatası (401). Bağlantıyı test edin.'))

        if response.status_code == 429:
            self._set_error('Rate limit aşıldı (429). 15 dakika bekleniyor.')
            _logger.warning('[Entegra:%s] Rate limit aşıldı!', self.name)
            raise UserError(_('Entegra rate limit aşıldı. 15 dakika sonra tekrar deneyin.'))

        if not response.ok:
            msg = f'HTTP {response.status_code}: {response.text[:500]}'
            self._set_error(msg)
            _logger.error('[Entegra:%s] %s', self.name, msg)
            raise UserError(_('Entegra API hatası [%s]: %s') % (response.status_code, response.text[:200]))

        try:
            return response.json()
        except ValueError:
            return {'raw': response.text}

    def api_get(self, endpoint, params=None):
        """GET isteği."""
        return self._request('GET', endpoint, params=params)

    def api_post(self, endpoint, data):
        """POST isteği."""
        return self._request('POST', endpoint, json_data=data)

    def api_put(self, endpoint, data):
        """PUT isteği."""
        return self._request('PUT', endpoint, json_data=data)

    # ═══════════════════════════════════════════════════
    # SAYFALAMA YARDIMCISI
    # ═══════════════════════════════════════════════════

    def _get_paginated(self, endpoint_template, params=None, max_pages=50):
        """
        Sayfalı endpoint'lerden tüm kayıtları çeker.

        Args:
            endpoint_template: '{page}' placeholder içeren endpoint, örn: '/order/page={page}/'
            params:            Ek filtre parametreleri
            max_pages:         Sonsuz döngüye karşı güvenlik limiti

        Returns:
            list: Tüm sayfalardaki kayıtların birleştirilmiş listesi
        """
        all_results = []
        page = 1

        while page <= max_pages:
            endpoint = endpoint_template.format(page=page)
            response = self.api_get(endpoint, params=params)

            # Entegra farklı endpoint'lerde farklı key kullanıyor
            results = (
                response.get('results')
                or response.get('data')
                or response.get('list')
                or (response if isinstance(response, list) else [])
            )

            if not results:
                break

            all_results.extend(results)

            # Bir sonraki sayfa var mı?
            if not response.get('next'):
                break

            page += 1

        _logger.debug('[Entegra:%s] %s — toplam %d kayıt çekildi.',
                      self.name, endpoint_template, len(all_results))
        return all_results

    # ═══════════════════════════════════════════════════
    # BATCH GÖNDERİM YARDIMCISI
    # ═══════════════════════════════════════════════════

    def _send_batched(self, endpoint, records, batch_size=50):
        """
        Büyük listeleri Entegra'nın batch limitine göre böler ve gönderir.
        Entegra quantity/price update için max 50 kayıt/istek kuralı var.

        Args:
            endpoint:   API endpoint
            records:    Gönderilecek kayıt listesi
            batch_size: Entegra limiti (varsayılan 50)

        Returns:
            list: Her batch'in response'ları
        """
        responses = []
        for i in range(0, len(records), batch_size):
            chunk = records[i:i + batch_size]
            resp = self.api_put(endpoint, {'list': chunk})
            responses.append(resp)
            _logger.debug('[Entegra:%s] Batch %d-%d gönderildi.',
                          self.name, i, i + len(chunk))
        return responses

    # ═══════════════════════════════════════════════════
    # BAĞLANTI TESTİ
    # ═══════════════════════════════════════════════════

    def action_test_connection(self):
        """
        Kullanıcı arayüzünden bağlantı testi.
        Cache kontrolü yapar; geçerli token varsa yeni istek atmaz (TC-003).
        """
        self.ensure_one()
        try:
            self.get_valid_token()
            # Basit bir GET ile doğrula — ilk marka sayfasını çek
            brands_ep = ENTEGRA_ENDPOINTS['brands'].format(page=1)
            result = self.api_get(brands_ep, params={})
            count = len(result.get('results', result.get('data', [])))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Bağlantı Başarılı'),
                    'message': _(
                        'Entegra API\'ye başarıyla bağlanıldı. '
                        '%d marka kaydı bulundu.'
                    ) % count,
                    'type': 'success',
                    'sticky': False,
                },
            }
        except UserError as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Bağlantı Hatası'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                },
            }

    def action_clear_token_cache(self):
        """Zorla yeni token almak için cache'i temizler."""
        self.ensure_one()
        self.sudo().write({
            'access_token': False,
            'refresh_token': False,
            'token_expiry': False,
            'refresh_expiry': False,
            'state': 'draft',
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Token Cache Temizlendi'),
                'message': _('Bir sonraki API çağrısında yeni token alınacak.'),
                'type': 'info',
                'sticky': False,
            },
        }

    # ═══════════════════════════════════════════════════
    # YARDIMCI METODLAR
    # ═══════════════════════════════════════════════════

    def _set_error(self, message):
        """Hata durumunu kaydet."""
        self.sudo().write({
            'state': 'error',
            'last_error': message,
        })
        _logger.error('[Entegra:%s] %s', self.name, message)

    def _get_kdv_id(self, tax_amount):
        """
        Odoo vergi yüzdesinden Entegra kdv_id üretir.

        Args:
            tax_amount: float, örn 20.0

        Returns:
            int: Entegra kdv_id (0, 8, 10, 18, 20)
        """
        rate = int(tax_amount)
        if rate not in ODOO_TAX_TO_KDV:
            _logger.warning(
                '[Entegra] Bilinmeyen vergi oranı: %s — kdv_id=0 kullanılacak.', rate
            )
            return 0
        return ODOO_TAX_TO_KDV[rate]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for backend in records:
            if not backend.price_mapping_ids:
                self.env['entegra.price.mapping'].create({
                    'backend_id': backend.id,
                    'sequence': 10,
                    'marketplace': 'general',
                    'entegra_price_code': 'price1',
                    'price_field': 'list_price',
                    'active': True,
                })
        return records

    @api.model
    def _cron_refresh_tokens(self):
        """
        Zamanlanmış görev: Tüm aktif backend'lerin token'larını proaktif yeniler.
        Günde 1x çalışır — token ban riskini sıfıra indirir.
        """
        backends = self.search([('active', '=', True)])
        for backend in backends:
            try:
                backend.get_valid_token()
                _logger.info('[Entegra:%s] Proaktif token yenileme OK.', backend.name)
            except Exception as e:
                _logger.error('[Entegra:%s] Proaktif token yenileme hatası: %s',
                              backend.name, str(e))


class EntegraPriceMapping(models.Model):
    """
    Odoo pricelist → Entegra priceCode eşlemesi.
    Müşterinin aktif pazaryerlerine göre konfigüre edilir.
    """
    _name = 'entegra.price.mapping'
    _description = 'Entegra Fiyat Eşlemesi'
    _order = 'sequence'

    backend_id = fields.Many2one(
        'entegra.backend',
        string='Backend',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(default=10)
    pricelist_id = fields.Many2one(
        'product.pricelist',
        string='Odoo Fiyat Listesi',
    )
    price_field = fields.Selection(
        selection=[
            ('list_price', 'Satış Fiyatı (list_price)'),
            ('standard_price', 'Maliyet Fiyatı'),
            ('pricelist', 'Fiyat Listesi'),
        ],
        string='Kaynak Alan',
        default='list_price',
        required=True,
    )
    entegra_price_code = fields.Char(
        string='Entegra Fiyat Kodu',
        required=True,
        help='Örn: price1, trendyol_listPrice, hb_price, n11_price',
    )
    marketplace = fields.Selection(
        selection=[
            ('general',      'Genel'),
            ('trendyol',     'Trendyol'),
            ('hepsiburada',  'Hepsiburada'),
            ('n11',          'N11'),
            ('amazon',       'Amazon'),
            ('gittigidiyor', 'GittiGidiyor'),
            ('ciceksepeti',  'ÇiçekSepeti'),
            ('pazarama',     'Pazarama'),
        ],
        string='Pazaryeri',
        help='Bu fiyatın uygulanacağı pazaryeri.',
    )
    active = fields.Boolean(default=True)
