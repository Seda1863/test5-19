# -*- coding: utf-8 -*-
"""
entegra_product_push.py
───────────────────────
Odoo → Entegra ürün senkronizasyon servisi.

Kapsam:
  - Ürün oluşturma (Create Products V2)
  - Ürün güncelleme (Update Product V2)
  - Varyant ekleme (Add Variations)
  - Stok güncelleme (Update Product Quantity) — batch 50
  - Fiyat güncelleme (Update Product Prices) — batch 50
  - Resim gönderme (Add Pictures) — base64

Kritik kurallar:
  - productCode → Odoo default_code. BOŞ OLAMAZ.
  - Varyantlı ürünlerde "Renk" attribute ZORUNLU (Entegra kuralı).
  - KDV Entegra'ya KDV HARİÇ fiyat gönderilir.
  - Fiyat kodu eşlemesi entegra.price.mapping üzerinden yönetilir.
  - Stok ve fiyat batch boyutu: max 50 (Entegra limiti).
"""

import base64
import logging
import time

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# Renk attribute isimleri (büyük/küçük harf bağımsız kontrol)
COLOR_ATTRIBUTE_NAMES = {'renk', 'color', 'colour', 'rénk'}

# Entegra para birimi kodu eşlemesi
CURRENCY_MAP = {
    'TRY': 'TRL',
    'USD': 'USD',
    'EUR': 'EUR',
    'GBP': 'GBP',
    'JPY': 'JPY',
}


class EntegraProductPush(models.Model):
    """
    Ürün push mantığı. EntegraBackend üzerinden çağrılır.
    """
    _name = 'entegra.product.push'
    _description = 'Entegra Ürün Push Servisi'

    # ═══════════════════════════════════════════════════
    # ANA GİRİŞ NOKTASI
    # ═══════════════════════════════════════════════════

    @api.model
    def push_products(self, backend, products, force_update=False):
        """
        Ürünleri Entegra'ya gönderir (create veya update).

        Args:
            backend:       entegra.backend kaydı
            products:      product.template recordset
            force_update:  True → mapping olsa bile güncelle

        Returns:
            dict: {'success': [...], 'error': [...]}
        """
        results = {'success': [], 'error': []}

        for tmpl in products:
            try:
                self._push_single_product(backend, tmpl, force_update)
                results['success'].append(tmpl.id)
            except Exception as e:
                _logger.error(
                    '[Entegra:%s] Ürün push hatası: %s (%s)',
                    backend.name, tmpl.display_name, str(e)
                )
                results['error'].append({'id': tmpl.id, 'name': tmpl.display_name, 'error': str(e)})
                # Bir ürünün hatası diğerini durdurmasın
                continue

        _logger.info(
            '[Entegra:%s] Push tamamlandı. Başarılı: %d / Hata: %d',
            backend.name, len(results['success']), len(results['error'])
        )
        return results

    def _push_single_product(self, backend, tmpl, force_update=False):
        """
        Tek ürünü push eder. Create veya update karar verir.

        Raises:
            UserError: Validasyon veya API hatası
        """
        # 1. Ön validasyon
        self._validate_product(tmpl)

        # 2. Mevcut mapping var mı?
        mapping = self.env['entegra.product.mapping'].search([
            ('backend_id', '=', backend.id),
            ('product_tmpl_id', '=', tmpl.id),
            ('product_id', '=', False),  # Ana ürün mapping'i
        ], limit=1)

        if mapping and not force_update:
            # Update akışı
            self._update_product(backend, tmpl, mapping)
        else:
            # Create akışı
            self._create_product(backend, tmpl, mapping)

    # ═══════════════════════════════════════════════════
    # ÜRÜN OLUŞTURMA
    # ═══════════════════════════════════════════════════

    def _create_product(self, backend, tmpl, existing_mapping=None):
        """Entegra'da yeni ürün oluşturur (Create Products V2)."""
        payload = self._build_product_payload(backend, tmpl)

        _logger.info(
            '[Entegra:%s] Ürün oluşturuluyor: %s', backend.name, tmpl.default_code
        )

        t0 = time.time()
        response = backend.api_post('/product/', {'list': [payload]})
        duration_ms = int((time.time() - t0) * 1000)

        # Response'dan Entegra ID al (API'ye göre değişebilir)
        entegra_id = self._extract_entegra_id(response)

        # Mapping oluştur veya güncelle
        mapping_vals = {
            'backend_id': backend.id,
            'product_tmpl_id': tmpl.id,
            'product_id': False,
            'entegra_product_code': tmpl.default_code,
            'sync_status': 'synced',
            'last_sync_date': fields.Datetime.now(),
            'sync_error': False,
        }
        if entegra_id:
            mapping_vals['entegra_product_id'] = entegra_id

        if existing_mapping:
            existing_mapping.write(mapping_vals)
            mapping = existing_mapping
        else:
            mapping = self.env['entegra.product.mapping'].create(mapping_vals)

        # Varyantları da push et
        if tmpl.attribute_line_ids:
            self._push_variants(backend, tmpl, mapping)

        # Resimleri gönder
        if tmpl.image_1920:
            self._push_image(backend, tmpl, tmpl.default_code)

        # Sync log
        self._write_log(backend, 'product_push', 'success',
                        model_name='product.template',
                        record_id=tmpl.id,
                        record_name=tmpl.name,
                        entegra_ref=tmpl.default_code,
                        duration_ms=duration_ms)

    def _update_product(self, backend, tmpl, mapping):
        """Mevcut Entegra ürününü günceller (Update Product V2)."""
        payload = self._build_update_payload(backend, tmpl, mapping)

        _logger.info(
            '[Entegra:%s] Ürün güncelleniyor: %s', backend.name, tmpl.default_code
        )

        from .entegra_backend import ENTEGRA_ENDPOINTS
        t0 = time.time()
        backend.api_put(ENTEGRA_ENDPOINTS['product_update'], {'list': [payload]})
        duration_ms = int((time.time() - t0) * 1000)

        mapping.write({
            'sync_status': 'synced',
            'last_sync_date': fields.Datetime.now(),
            'sync_error': False,
        })

        # Varyantları güncelle
        if tmpl.attribute_line_ids:
            self._push_variants(backend, tmpl, mapping)

        self._write_log(backend, 'product_update', 'success',
                        model_name='product.template',
                        record_id=tmpl.id,
                        record_name=tmpl.name,
                        entegra_ref=tmpl.default_code,
                        duration_ms=duration_ms)

    # ═══════════════════════════════════════════════════
    # PAYLOAD BUILDER — ANA ÜRÜN
    # ═══════════════════════════════════════════════════

    def _build_product_payload(self, backend, tmpl):
        """
        Create Products V2 için tam payload oluşturur.
        Fiyatlar KDV HARİÇ gönderilir.
        """
        # Vergi oranı
        tax = tmpl.taxes_id[:1]
        tax_rate = tax.amount if tax else 0
        kdv_id = backend._get_kdv_id(tax_rate)

        # Para birimi
        currency_code = CURRENCY_MAP.get(
            tmpl.currency_id.name if tmpl.currency_id else 'TRY', 'TRL'
        )

        # Stok (Odoo'nun saydığı tüm depolar)
        quantity = int(tmpl.qty_available)

        # Fiyat listesi (KDV hariç)
        prices = self._build_price_list(backend, tmpl)

        payload = {
            'productName': tmpl.name,
            'productCode': tmpl.default_code,
            'status': 1,
            'quantity': quantity,
            'kdv_id': kdv_id,
            'currencyType': currency_code,
            'description': self._clean_html(tmpl.description_sale or tmpl.name),
            'brand': tmpl.product_brand_id.name if hasattr(tmpl, 'product_brand_id') and tmpl.product_brand_id else '',
            'supplier': backend.supplier_name,
            'supplier_id': tmpl.default_code,
            'product_pictures': [],
            'prices': prices,
        }

        # Opsiyonel alanlar
        if tmpl.weight:
            payload['agirlik'] = tmpl.weight
        if hasattr(tmpl, 'barcode') and tmpl.barcode:
            payload['barcode'] = tmpl.barcode

        # Boyutlar (product.template'de varsa)
        if hasattr(tmpl, 'volume') and tmpl.volume:
            # volume = en * boy * derinlik — ayrıştıramıyoruz, skip
            pass

        # Varyantlar (ana ürün oluştururken varyantları da gönder)
        if tmpl.attribute_line_ids:
            payload['variations'] = self._build_variations_payload(tmpl)
        else:
            payload['variations'] = []

        return payload

    def _build_update_payload(self, backend, tmpl, mapping):
        """Update Product V2 için payload. Sadece değişen alanlar."""
        tax = tmpl.taxes_id[:1]
        tax_rate = tax.amount if tax else 0
        kdv_id = backend._get_kdv_id(tax_rate)

        currency_code = CURRENCY_MAP.get(
            tmpl.currency_id.name if tmpl.currency_id else 'TRY', 'TRL'
        )

        prices = self._build_price_list(backend, tmpl)

        payload = {
            'productCode': tmpl.default_code,
            'productName': tmpl.name,
            'quantity': int(tmpl.qty_available),
            'kdv_id': kdv_id,
            'currencyType': currency_code,
            'description': self._clean_html(tmpl.description_sale or tmpl.name),
            'status': 1,
            'prices': prices,
        }

        if tmpl.weight:
            payload['agirlik'] = tmpl.weight
        if hasattr(tmpl, 'barcode') and tmpl.barcode:
            payload['barcode'] = tmpl.barcode
        if hasattr(tmpl, 'product_brand_id') and tmpl.product_brand_id:
            payload['brand'] = tmpl.product_brand_id.name

        return payload

    # ═══════════════════════════════════════════════════
    # PAYLOAD BUILDER — VARYANTLAR
    # ═══════════════════════════════════════════════════

    def _build_variations_payload(self, tmpl):
        """
        Tüm aktif varyantları Entegra formatına çevirir.

        KURAL: Varyant ürünlerde Renk attribute ZORUNLU.
        Renk yoksa → variation_specs'e 'Renk: Standart' eklenir.
        """
        variations = []
        has_color = self._has_color_attribute(tmpl)

        for variant in tmpl.product_variant_ids.filtered(lambda v: v.active):
            if not variant.default_code:
                _logger.warning(
                    '[Entegra] Varyant "%s" için default_code boş — atlanıyor.',
                    variant.display_name
                )
                continue

            variation_specs = self._build_variation_specs(variant, add_dummy_color=not has_color)

            var_payload = {
                'productCode': variant.default_code,
                'barcode': variant.barcode or '',
                'quantity': int(variant.qty_available),
                'price': 0,
                'price_prefix': '+',
                'variation_specs': variation_specs,
                'variation_pictures': [],
            }

            # Varyant resmi varsa
            if variant.image_1920:
                # Resimler Add Pictures endpoint'i ile ayrıca gönderilir
                pass

            variations.append(var_payload)

        return variations

    def _push_variants(self, backend, tmpl, parent_mapping):
        """
        Varyantları Entegra'ya ekler veya günceller.
        Mevcut mapping varsa → Update Variation, yoksa → Add Variation.
        """
        has_color = self._has_color_attribute(tmpl)

        for variant in tmpl.product_variant_ids.filtered(lambda v: v.active):
            if not variant.default_code:
                continue

            var_mapping = self.env['entegra.product.mapping'].search([
                ('backend_id', '=', backend.id),
                ('product_id', '=', variant.id),
            ], limit=1)

            variation_specs = self._build_variation_specs(variant, add_dummy_color=not has_color)

            var_payload = {
                'productCode': tmpl.default_code,  # Ana ürün kodu
                'variations': [{
                    'productCode': variant.default_code,
                    'barcode': variant.barcode or '',
                    'quantity': int(variant.qty_available),
                    'price': 0,
                    'price_prefix': '+',
                    'variation_specs': variation_specs,
                    'variation_pictures': [],
                }]
            }

            try:
                if var_mapping:
                    # Güncelle
                    update_payload = {
                        'productCode': variant.default_code,
                        'mainProductCode': tmpl.default_code,
                        'quantity': int(variant.qty_available),
                        'variation_specs': variation_specs,
                    }
                    backend.api_put('/product/variations/', {'list': [update_payload]})
                    var_mapping.write({
                        'sync_status': 'synced',
                        'last_sync_date': fields.Datetime.now(),
                        'sync_error': False,
                    })
                else:
                    # Yeni varyant ekle
                    response = backend.api_post('/product/variations/', {'list': [var_payload]})
                    variation_id = self._extract_variation_id(response)

                    self.env['entegra.product.mapping'].create({
                        'backend_id': backend.id,
                        'product_tmpl_id': tmpl.id,
                        'product_id': variant.id,
                        'entegra_product_code': tmpl.default_code,
                        'entegra_variation_code': variant.default_code,
                        'entegra_variation_id': variation_id or 0,
                        'sync_status': 'synced',
                        'last_sync_date': fields.Datetime.now(),
                    })
            except Exception as e:
                _logger.error(
                    '[Entegra:%s] Varyant push hatası: %s → %s',
                    backend.name, variant.default_code, str(e)
                )

    def _build_variation_specs(self, variant, add_dummy_color=False):
        """
        Varyant attribute değerlerini Entegra variation_specs formatına çevirir.
        add_dummy_color=True → Renk attribute yoksa 'Renk: Standart' ekler.
        """
        specs = []
        has_color_in_specs = False

        for ptav in variant.product_template_attribute_value_ids:
            attr_name = ptav.attribute_id.name
            if attr_name.lower() in COLOR_ATTRIBUTE_NAMES:
                has_color_in_specs = True
            specs.append({
                'name': attr_name,
                'value': ptav.product_attribute_value_id.name,
            })

        if add_dummy_color and not has_color_in_specs:
            specs.insert(0, {'name': 'Renk', 'value': 'Standart'})

        return specs

    def _has_color_attribute(self, tmpl):
        """Ürün şablonunda renk attribute var mı kontrol eder."""
        for line in tmpl.attribute_line_ids:
            if line.attribute_id.name.lower() in COLOR_ATTRIBUTE_NAMES:
                return True
        return False

    # ═══════════════════════════════════════════════════
    # STOK SENKRONİZASYONU
    # ═══════════════════════════════════════════════════

    @api.model
    def push_stock(self, backend, products=None):
        """
        Ürün stok miktarlarını Entegra'ya gönderir.
        Entegra limiti: max 50 ürün/istek.

        Args:
            backend:  entegra.backend kaydı
            products: product.template recordset (None → tüm eşlenmiş ürünler)
        """
        mappings = self.env['entegra.product.mapping'].search([
            ('backend_id', '=', backend.id),
            ('sync_status', '=', 'synced'),
            ('product_id', '=', False),  # Ana ürün
        ])

        if products:
            mappings = mappings.filtered(
                lambda m: m.product_tmpl_id.id in products.ids
            )

        if not mappings:
            _logger.info('[Entegra:%s] Stok güncellenecek eşlenmiş ürün yok.', backend.name)
            return

        # Ana ürün stok kayıtları
        qty_records = []
        for mapping in mappings:
            tmpl = mapping.product_tmpl_id
            if tmpl.entegra_exclude:
                continue

            qty_records.append({
                'productCode': mapping.entegra_product_code,
                'store_id': backend.entegra_store_id,
                'quantity': int(tmpl.qty_available),
            })

        # Varyant stok kayıtları
        var_mappings = self.env['entegra.product.mapping'].search([
            ('backend_id', '=', backend.id),
            ('sync_status', '=', 'synced'),
            ('product_id', '!=', False),
        ])

        if products:
            var_mappings = var_mappings.filtered(
                lambda m: m.product_tmpl_id.id in products.ids
            )

        var_qty_records = []
        for var_mapping in var_mappings:
            variant = var_mapping.product_id
            if not variant or not var_mapping.entegra_variation_code:
                continue
            var_qty_records.append({
                'productCode': var_mapping.entegra_variation_code,
                'mainProductCode': var_mapping.entegra_product_code,
                'store_id': backend.entegra_store_id,
                'quantity': int(variant.qty_available),
            })

        # Batch gönderim — max 50
        all_records = qty_records + var_qty_records
        if not all_records:
            return

        t0 = time.time()
        responses = backend._send_batched(
            '/product/quantity/', all_records, batch_size=50
        )
        duration_ms = int((time.time() - t0) * 1000)

        # Son sync tarihini güncelle
        mappings.write({'last_stock_sync': fields.Datetime.now()})
        var_mappings.write({'last_stock_sync': fields.Datetime.now()})

        self._write_log(backend, 'stock_update', 'success',
                        record_name=f'{len(all_records)} ürün',
                        duration_ms=duration_ms)

        _logger.info(
            '[Entegra:%s] Stok güncellendi. %d kayıt / %d batch / %dms',
            backend.name, len(all_records), len(responses), duration_ms
        )

    # ═══════════════════════════════════════════════════
    # FİYAT SENKRONİZASYONU
    # ═══════════════════════════════════════════════════

    @api.model
    def push_prices(self, backend, products=None):
        """
        Ürün fiyatlarını Entegra'ya gönderir.
        Price mapping konfigürasyonundan okur.
        Entegra limiti: max 50 ürün/istek.

        Fiyatlar KDV HARİÇ gönderilir.
        """
        if not backend.price_mapping_ids:
            _logger.warning(
                '[Entegra:%s] Fiyat eşlemesi tanımlı değil — fiyat push atlanıyor.',
                backend.name
            )
            return

        mappings = self.env['entegra.product.mapping'].search([
            ('backend_id', '=', backend.id),
            ('sync_status', '=', 'synced'),
            ('product_id', '=', False),
        ])

        if products:
            mappings = mappings.filtered(
                lambda m: m.product_tmpl_id.id in products.ids
            )

        price_records = []

        for mapping in mappings:
            tmpl = mapping.product_tmpl_id
            if tmpl.entegra_exclude:
                continue

            prices = self._build_price_list(backend, tmpl)
            if not prices:
                continue

            price_records.append({
                'productCode': mapping.entegra_product_code,
                'mainProductCode': '',
                'prices': prices,
            })

        if not price_records:
            _logger.info('[Entegra:%s] Güncellenecek fiyat kaydı yok.', backend.name)
            return

        t0 = time.time()
        responses = backend._send_batched(
            '/product/prices/', price_records, batch_size=50
        )
        duration_ms = int((time.time() - t0) * 1000)

        mappings.write({'last_price_sync': fields.Datetime.now()})

        self._write_log(backend, 'price_update', 'success',
                        record_name=f'{len(price_records)} ürün',
                        duration_ms=duration_ms)

        _logger.info(
            '[Entegra:%s] Fiyat güncellendi. %d kayıt / %dms',
            backend.name, len(price_records), duration_ms
        )

    def _build_price_list(self, backend, tmpl):
        """
        Entegra prices listesi oluşturur.
        entegra.price.mapping konfigürasyonundan okur.

        Returns:
            list: [{'priceCode': '...', 'priceValue': float, 'store_id': int}, ...]
        """
        prices = []

        for pm in backend.price_mapping_ids.filtered(lambda p: p.active):
            price_value = self._get_price_from_mapping(tmpl, pm)
            if price_value is None:
                continue

            # KDV hariç kontrol
            price_value = self._ensure_tax_excluded(tmpl, price_value)

            prices.append({
                'priceCode': pm.entegra_price_code,
                'priceValue': round(price_value, 2),
                'store_id': backend.entegra_store_id,
            })

        return prices

    def _get_price_from_mapping(self, tmpl, price_mapping):
        """Price mapping'e göre Odoo'dan fiyat okur."""
        if price_mapping.price_field == 'list_price':
            return tmpl.list_price
        elif price_mapping.price_field == 'standard_price':
            return tmpl.standard_price
        elif price_mapping.price_field == 'pricelist' and price_mapping.pricelist_id:
            # Odoo 17+: _get_product_price(product, qty, currency, uom, date)
            price = price_mapping.pricelist_id._get_product_price(
                tmpl.product_variant_id, 1.0
            )
            return price
        return None

    def _ensure_tax_excluded(self, tmpl, price):
        """
        Fiyatın KDV hariç olmasını garantiler.
        Odoo'da fiyatlar genellikle KDV hariç saklanır (list_price).
        Eğer taxes_id'de price_include=True varsa düşür.
        """
        for tax in tmpl.taxes_id:
            if tax.price_include and tax.amount > 0:
                price = price / (1 + tax.amount / 100)
        return price

    # ═══════════════════════════════════════════════════
    # RESİM PUSH
    # ═══════════════════════════════════════════════════

    def _push_image(self, backend, tmpl, product_code):
        """
        Ürün resmini base64 byte olarak Entegra'ya gönderir.
        Add Pictures endpoint'i kullanır.
        """
        if not tmpl.image_1920:
            return

        try:
            image_b64 = tmpl.image_1920.decode() if isinstance(tmpl.image_1920, bytes) else tmpl.image_1920
            # Odoo binary field zaten base64
            payload = {
                'list': [{
                    'productCode': product_code,
                    'name': tmpl.name,
                    'filename': f'{product_code}.jpg',
                    'supplier': backend.supplier_name,
                    'supplier_id': product_code,
                    'picture': [{'picture_byte': image_b64}],
                }]
            }
            backend.api_post('/product/pictures/', payload)
            _logger.info('[Entegra:%s] Resim gönderildi: %s', backend.name, product_code)
        except Exception as e:
            # Resim hatası push'ı durdurmasın
            _logger.warning(
                '[Entegra:%s] Resim gönderilemedi: %s → %s',
                backend.name, product_code, str(e)
            )

    # ═══════════════════════════════════════════════════
    # VALİDASYON
    # ═══════════════════════════════════════════════════

    def _validate_product(self, tmpl):
        """
        Push öncesi ürün validasyonu.

        Raises:
            UserError: Validasyon başarısız
        """
        errors = []

        if not tmpl.default_code:
            errors.append(
                f'"{tmpl.name}": İç Referans (default_code) boş. '
                'Entegra productCode zorunludur.'
            )

        if tmpl.entegra_exclude:
            raise UserError(
                _('"%(name)s" ürünü Entegra\'ya gönderilmeyecek şekilde işaretli.',
                  name=tmpl.name)
            )

        if errors:
            raise UserError('\n'.join(errors))

    # ═══════════════════════════════════════════════════
    # CRON METODLARI
    # ═══════════════════════════════════════════════════

    @api.model
    def _cron_push_stock(self):
        """Zamanlanmış stok güncellemesi — tüm aktif backend'ler."""
        backends = self.env['entegra.backend'].search([('active', '=', True)])
        for backend in backends:
            try:
                self.push_stock(backend)
            except Exception as e:
                _logger.error(
                    '[Entegra:%s] Cron stok güncelleme hatası: %s', backend.name, str(e)
                )

    @api.model
    def _cron_push_prices(self):
        """Zamanlanmış fiyat güncellemesi — tüm aktif backend'ler."""
        backends = self.env['entegra.backend'].search([('active', '=', True)])
        for backend in backends:
            try:
                self.push_prices(backend)
            except Exception as e:
                _logger.error(
                    '[Entegra:%s] Cron fiyat güncelleme hatası: %s', backend.name, str(e)
                )

    # ═══════════════════════════════════════════════════
    # YARDIMCI METODLAR
    # ═══════════════════════════════════════════════════

    def _extract_entegra_id(self, response):
        """API response'dan Entegra ürün ID'sini çıkarır."""
        if not response:
            return None
        if isinstance(response, dict):
            return (response.get('id')
                    or response.get('product_id')
                    or (response.get('data') or {}).get('id'))
        return None

    def _extract_variation_id(self, response):
        """API response'dan Entegra varyant ID'sini çıkarır."""
        if not response:
            return None
        if isinstance(response, dict):
            return (response.get('id')
                    or response.get('variation_id')
                    or (response.get('data') or {}).get('id'))
        return None

    def _clean_html(self, text):
        """HTML tag'larını temizler (description alanı için)."""
        if not text:
            return ''
        import re
        clean = re.compile('<.*?>')
        return re.sub(clean, '', text).strip()

    def _write_log(self, backend, operation, status, **kwargs):
        """Sync log kaydı oluşturur."""
        vals = {
            'backend_id': backend.id,
            'operation': operation,
            'status': status,
        }
        vals.update(kwargs)
        self.env['entegra.sync.log'].sudo().create(vals)
