# -*- coding: utf-8 -*-
"""
entegra_order_import.py
───────────────────────
Entegra → Odoo sipariş import servisi.

Akış:
  1. GET /order/page=1/?api_sync=0  → çekilmemiş siparişler
  2. entegra_order_id ile duplicate kontrolü
  3. res.partner bul veya oluştur (fatura + teslimat adresi)
  4. product.product eşle (mapping > default_code > fallback)
  5. sale.order + sale.order.line oluştur
  6. PUT /order/update/ → sync=1, erp_order_number=SO.name
  7. auto_confirm=True ise SO.action_confirm()

Kritik tasarım kararları:
  - api_sync=0 olan siparişler GET yapıldığında otomatik 1'e çekilir (Entegra davranışı).
    Bu doğal deduplikasyon mekanizması — race condition'a karşı entegra_order_id
    unique index ile desteklenir.
  - Partner eşleme önceliği: email → telefon → isim+şehir → yeni oluştur.
  - Ürün bulunamazsa: placeholder ürün KULLANILMAZ, log yazılır ve satır atlanır.
    Sipariş yine de oluşturulur (eksik satır uyarısıyla).
  - Fiyatlar Entegra'dan KDV hariç gelir — satır birim fiyat olarak atanır,
    vergi Odoo'daki ürün vergisinden alınır.
"""

import json
import logging
import time
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Entegra order status → Odoo etiket (bilgi amaçlı)
ENTEGRA_ORDER_STATUS = {
    1:  'Yeni Sipariş',
    2:  'Onaylandı',
    3:  'Kargolandı',
    4:  'Tamamlandı',
    5:  'Hatalı',
    6:  'Ön Sipariş',
    7:  'Kargoya Hazır',
    8:  'Ödeme Alındı',
    9:  'İade-İptal',
    10: 'Onay Bekliyor',
    11: 'İadesi Onaylanan',
}

# Entegra'dan import edilecek status'lar (iptal/hata olanlar alınmaz)
IMPORTABLE_STATUSES = {1, 2, 6, 7, 8, 10}

# Entegra para birimi → Odoo currency code
CURRENCY_CODE_MAP = {
    'TRL': 'TRY',
    'USD': 'USD',
    'EUR': 'EUR',
    'GBP': 'GBP',
    'JPY': 'JPY',
    'CHF': 'CHF',
}


class EntegraOrderImport(models.Model):
    """
    Sipariş import mantığı. EntegraBackend cron'u ve wizard üzerinden çağrılır.
    """
    _name = 'entegra.order.import'
    _description = 'Entegra Sipariş Import Servisi'

    # ═══════════════════════════════════════════════════
    # ANA GİRİŞ NOKTASI
    # ═══════════════════════════════════════════════════

    @api.model
    def import_new_orders(self, backend, supplier=None, date_from=None, skip_sync_filter=False):
        """
        Yeni siparişleri Entegra'dan çekip Odoo'ya aktarır.

        Args:
            backend:           entegra.backend kaydı
            supplier:          Belirli bir pazaryeri filtresi ('trendyol', 'hb', 'n11'...)
            date_from:         Bu tarihten sonraki siparişleri çek (YYYY-MM-DD)
            skip_sync_filter:  True → api_sync=0 filtresi atlanır, tüm siparişler sorgulanır

        Returns:
            dict: {'imported': int, 'skipped': int, 'errors': list}
        """
        results = {'imported': 0, 'skipped': 0, 'errors': []}

        # Parametreleri oluştur
        endpoint = '/order/page={page}/'
        params = {'limit': 200}
        if not skip_sync_filter:
            params['api_sync'] = 0
        if supplier:
            params['supplier'] = supplier
        if date_from:
            params['start_date'] = date_from

        params_json = json.dumps(params, ensure_ascii=False)

        _logger.info(
            '[Entegra:%s] Sipariş import başlıyor. Endpoint: %s  Params: %s',
            backend.name, endpoint, params_json
        )

        # Tüm sayfaları çek (süreyi ölç)
        t0 = time.time()
        all_orders = backend._get_paginated(endpoint, params=params)
        duration_ms = int((time.time() - t0) * 1000)
        order_count = len(all_orders) if all_orders else 0

        _logger.info(
            '[Entegra:%s] API yanıtı: %d sipariş döndü (%d ms)',
            backend.name, order_count, duration_ms
        )

        if not all_orders:
            _logger.info('[Entegra:%s] Yeni sipariş bulunamadı.', backend.name)
            self._write_log(
                backend, 'order_import', 'success',
                record_name='Sipariş bulunamadı (0 kayıt)',
                request_data='Endpoint: %s\nParams: %s' % (endpoint, params_json),
                response_data='API 0 sipariş döndürdü',
                duration_ms=duration_ms,
            )
            return results

        _logger.info(
            '[Entegra:%s] %d sipariş bulundu, işleniyor...',
            backend.name, order_count
        )

        for order_data in all_orders:
            try:
                result = self._process_order(backend, order_data)
                if result == 'imported':
                    results['imported'] += 1
                elif result == 'skipped':
                    results['skipped'] += 1
            except Exception as e:
                order_id = order_data.get('id', '?')
                order_no = order_data.get('order_number', '?')
                msg = f'Sipariş {order_no} (ID:{order_id}): {str(e)}'
                _logger.error('[Entegra:%s] %s', backend.name, msg)
                results['errors'].append(msg)
                continue

        self._write_log(
            backend, 'order_import',
            'success' if not results['errors'] else 'warning',
            record_name='%d import, %d atlandı, %d hata' % (
                results['imported'], results['skipped'], len(results['errors'])
            ),
            request_data='Endpoint: %s\nParams: %s' % (endpoint, params_json),
            response_data='API %d sipariş döndürdü' % order_count,
            duration_ms=duration_ms,
        )

        _logger.info(
            '[Entegra:%s] Import tamamlandı: %d import / %d atlandı / %d hata',
            backend.name, results['imported'], results['skipped'], len(results['errors'])
        )
        return results

    # ═══════════════════════════════════════════════════
    # TEK SİPARİŞ İŞLEME
    # ═══════════════════════════════════════════════════

    def _process_order(self, backend, order_data):
        """
        Tek siparişi işler.

        Returns:
            str: 'imported' | 'skipped'
        """
        entegra_id = order_data.get('id')
        order_number = order_data.get('order_number')
        order_status = order_data.get('status')

        # 1. Duplicate kontrolü
        existing = self.env['sale.order'].search([
            ('entegra_order_id', '=', entegra_id),
            ('entegra_backend_id', '=', backend.id),
        ], limit=1)

        if existing:
            _logger.debug(
                '[Entegra:%s] Sipariş zaten var: %s → %s',
                backend.name, order_number, existing.name
            )
            return 'skipped'

        # 2. İptal/hata statüsündeki siparişleri alma
        if order_status and order_status not in IMPORTABLE_STATUSES:
            status_label = ENTEGRA_ORDER_STATUS.get(order_status, str(order_status))
            _logger.info(
                '[Entegra:%s] Sipariş %s atlandı (statü: %s)',
                backend.name, order_number, status_label
            )
            return 'skipped'

        # 3. Partner bul veya oluştur
        partner = self._get_or_create_partner(backend, order_data)
        shipping_partner = self._get_or_create_shipping_partner(order_data, partner)

        # 4. Sale.order oluştur
        so = self._create_sale_order(backend, order_data, partner, shipping_partner)

        # 5. Satır kalemlerini ekle
        missing_products = self._create_order_lines(backend, so, order_data)

        # 6. Entegra'ya ERP sync bildir
        self._confirm_erp_sync(backend, entegra_id, so.name)

        # 7. Otomatik onay
        if backend.auto_confirm_orders and not missing_products:
            try:
                so.action_confirm()
            except Exception as e:
                _logger.warning(
                    '[Entegra:%s] Sipariş %s otomatik onay hatası: %s',
                    backend.name, so.name, str(e)
                )

        if missing_products:
            _logger.warning(
                '[Entegra:%s] Sipariş %s oluşturuldu, eksik ürünler: %s',
                backend.name, so.name, ', '.join(missing_products)
            )

        return 'imported'

    # ═══════════════════════════════════════════════════
    # PARTNER YÖNETİMİ
    # ═══════════════════════════════════════════════════

    def _get_or_create_partner(self, backend, order_data):
        """
        Fatura partneri bul veya oluştur.

        Eşleme önceliği:
          1. Email ile ara (en güvenilir)
          2. Telefon ile ara
          3. İsim + şehir ile ara
          4. Bulunamazsa yeni oluştur
        """
        email = self._clean_email(order_data.get('email', ''))
        full_name = order_data.get('full_name') or order_data.get('invoice_fullname', '')
        company_name = order_data.get('company', '')
        mobile = str(order_data.get('mobile_phone', '')).strip()
        phone = str(order_data.get('phone', '')).strip()
        city = order_data.get('invoice_city', '')

        partner = None

        # 1. Email ile ara
        if email:
            partner = self.env['res.partner'].search([
                ('email', '=', email),
                ('type', 'in', ['contact', False]),
            ], limit=1)

        # 2. Telefon ile ara
        if not partner and mobile and len(mobile) >= 10:
            partner = self.env['res.partner'].search([
                ('mobile', '=', mobile),
            ], limit=1)

        # 3. İsim + şehir ile ara
        if not partner and full_name and city:
            partner = self.env['res.partner'].search([
                ('name', '=', full_name),
                ('city', '=', city),
            ], limit=1)

        # 4. Yeni partner oluştur
        if not partner:
            partner_vals = self._build_partner_vals(order_data, company_name, full_name, email, mobile, phone, city)
            partner = self.env['res.partner'].create(partner_vals)
            _logger.info(
                '[Entegra:%s] Yeni partner oluşturuldu: %s',
                backend.name, partner.name
            )
        else:
            _logger.debug(
                '[Entegra:%s] Mevcut partner bulundu: %s',
                backend.name, partner.name
            )

        return partner

    def _build_partner_vals(self, order_data, company_name, full_name, email, mobile, phone, city):
        """Partner oluşturma değerleri."""
        country = self.env.ref('base.tr', raise_if_not_found=False)

        vals = {
            'name': company_name or full_name or 'Entegra Müşteri',
            'email': email or False,
            'mobile': mobile or False,
            'phone': phone or False,
            'street': order_data.get('invoice_address', ''),
            'city': city,
            'country_id': country.id if country else False,
            'customer_rank': 1,
        }

        # Vergi/kurumsal bilgiler
        tax_office = order_data.get('tax_office', '')
        if tax_office:
            vals['company_type'] = 'company'
            # Odoo'da vergi dairesi alanı standart değil — nota ekle
            vals['comment'] = f'Vergi Dairesi: {tax_office}'

        if company_name and full_name and company_name != full_name:
            vals['company_type'] = 'company'

        return vals

    def _get_or_create_shipping_partner(self, order_data, invoice_partner):
        """
        Teslimat adresi invoice adresinden farklıysa ayrı partner oluşturur.
        Aynıysa invoice partner'ı döner.
        """
        ship_address = order_data.get('ship_address', '')
        ship_city = order_data.get('ship_city', '')
        invoice_address = order_data.get('invoice_address', '')
        invoice_city = order_data.get('invoice_city', '')

        # Adresler aynıysa ayrı shipping partner gerekmez
        if (ship_address == invoice_address and ship_city == invoice_city):
            return invoice_partner

        ship_fullname = order_data.get('ship_fullname', invoice_partner.name)
        ship_phone = str(order_data.get('ship_tel', '')).strip()
        ship_gsm = str(order_data.get('ship_gsm', '')).strip()

        # Mevcut shipping child partner ara
        shipping_partner = self.env['res.partner'].search([
            ('parent_id', '=', invoice_partner.id),
            ('type', '=', 'delivery'),
            ('street', '=', ship_address),
            ('city', '=', ship_city),
        ], limit=1)

        if not shipping_partner:
            country = self.env.ref('base.tr', raise_if_not_found=False)
            shipping_partner = self.env['res.partner'].create({
                'name': ship_fullname,
                'parent_id': invoice_partner.id,
                'type': 'delivery',
                'street': ship_address,
                'city': ship_city,
                'phone': ship_phone or False,
                'mobile': ship_gsm or False,
                'country_id': country.id if country else False,
            })

        return shipping_partner

    # ═══════════════════════════════════════════════════
    # SALE.ORDER OLUŞTURMA
    # ═══════════════════════════════════════════════════

    def _create_sale_order(self, backend, order_data, partner, shipping_partner):
        """sale.order kaydını oluşturur."""
        order_date = self._parse_order_date(order_data.get('order_date'))
        supplier = order_data.get('supplier', '')
        order_number = order_data.get('order_number', '')
        entegra_id = order_data.get('id')
        order_status = order_data.get('status', 1)
        cargo_company = order_data.get('cargo', '')
        cargo_code = order_data.get('cargo_code', '')

        # Para birimi
        currency = self._get_currency(order_data)

        # Depo
        warehouse = backend.default_warehouse_id
        if not warehouse:
            warehouse = self.env['stock.warehouse'].search([
                ('company_id', '=', self.env.company.id)
            ], limit=1)

        so_vals = {
            'partner_id': partner.id,
            'partner_shipping_id': shipping_partner.id,
            'partner_invoice_id': partner.id,
            'date_order': order_date or fields.Datetime.now(),
            'warehouse_id': warehouse.id if warehouse else False,
            'currency_id': currency.id if currency else False,
            # Pazaryeri sipariş numarasını standart referans alanına da yaz
            'client_order_ref': str(order_number) if order_number else False,
            # Entegra alanları
            'entegra_order_id': entegra_id,
            'entegra_order_number': str(order_number),
            'entegra_supplier': supplier,
            'entegra_sync_status': '1',  # ERP'ye alındı
            'entegra_backend_id': backend.id,
            'entegra_status_label': ENTEGRA_ORDER_STATUS.get(order_status, str(order_status)),
            'entegra_cargo_company': cargo_company,
            'entegra_cargo_code': cargo_code,
            # Pazaryeri detayları entegra_marketplace_note alanına yazılır (PDF'e çıkmaz)
            'entegra_marketplace_note': self._build_order_note(order_data),
        }

        so = self.env['sale.order'].create(so_vals)
        _logger.info(
            '[Entegra:%s] Sipariş oluşturuldu: %s ← Entegra %s (%s)',
            backend.name, so.name, order_number, supplier.upper()
        )
        return so

    def _build_order_note(self, order_data):
        """Sipariş notunu oluşturur (pazaryeri detayları)."""
        lines = []
        supplier = order_data.get('supplier', '')
        order_number = order_data.get('order_number', '')
        cargo = order_data.get('cargo', '')
        cargo_code = order_data.get('cargo_code', '')
        payment_type = order_data.get('payment_type', '')

        if supplier:
            lines.append(f'Pazaryeri: {supplier.upper()}')
        if order_number:
            lines.append(f'Pazaryeri Sipariş No: {order_number}')
        if cargo:
            lines.append(f'Kargo: {cargo}')
        if cargo_code:
            lines.append(f'Kargo Takip: {cargo_code}')
        if payment_type:
            lines.append(f'Ödeme Yöntemi: {payment_type}')

        return '\n'.join(lines) if lines else ''

    # ═══════════════════════════════════════════════════
    # SİPARİŞ KALEMLERİ
    # ═══════════════════════════════════════════════════

    def _create_order_lines(self, backend, so, order_data):
        """
        Sipariş kalemlerini oluşturur.

        Returns:
            list: Bulunamayan ürün kodları listesi (boşsa tüm kalemler eşlendi)
        """
        order_details = order_data.get('order_details', [])
        missing_products = []

        if not order_details:
            _logger.warning(
                '[Entegra:%s] Sipariş %s\'de ürün kalemi yok!',
                backend.name, order_data.get('order_number')
            )
            return missing_products

        for line_data in order_details:
            product_code = line_data.get('product_code', '').strip()
            quantity = float(line_data.get('quantity') or 1)
            price = float(line_data.get('price') or 0)
            first_price = float(line_data.get('first_price') or price)

            if not product_code:
                _logger.warning('[Entegra:%s] Kalemsiz product_code — atlanıyor.', backend.name)
                missing_products.append('(boş kod)')
                continue

            # Ürünü bul
            product = self._find_product(backend, product_code)

            if not product:
                missing_products.append(product_code)
                _logger.warning(
                    '[Entegra:%s] Ürün bulunamadı: "%s" — kalem atlanıyor.',
                    backend.name, product_code
                )
                continue

            # İndirim hesapla — Entegra formülü: (first_price - price)
            discount = 0.0
            if first_price > 0 and first_price > price:
                discount = round((first_price - price) / first_price * 100, 2)

            line_vals = {
                'order_id': so.id,
                'product_id': product.id,
                'product_uom_qty': quantity,
                'price_unit': first_price if first_price > 0 else price,
                'discount': discount,
                'name': product.display_name,
            }

            # Ürün vergisini uygula
            if product.taxes_id:
                line_vals['tax_id'] = [(6, 0, product.taxes_id.ids)]

            self.env['sale.order.line'].create(line_vals)

        return missing_products

    def _find_product(self, backend, product_code):
        """
        product_code ile Odoo ürününü bulur.

        Öncelik sırası:
          1. entegra.product.mapping (varyant kodu ile)
          2. product.product.default_code ile direkt eşleşme
          3. product.template.default_code ile eşleşme (tek varyantta)
        """
        # 1. Entegra mapping tablosunda ara (varyant kodu)
        var_mapping = self.env['entegra.product.mapping'].search([
            ('backend_id', '=', backend.id),
            ('entegra_variation_code', '=', product_code),
            ('product_id', '!=', False),
        ], limit=1)

        if var_mapping and var_mapping.product_id:
            return var_mapping.product_id

        # 2. Ana ürün mapping'inde ara
        main_mapping = self.env['entegra.product.mapping'].search([
            ('backend_id', '=', backend.id),
            ('entegra_product_code', '=', product_code),
            ('product_id', '=', False),
        ], limit=1)

        if main_mapping and main_mapping.product_tmpl_id:
            tmpl = main_mapping.product_tmpl_id
            if len(tmpl.product_variant_ids) == 1:
                return tmpl.product_variant_ids[0]

        # 3. product.product.default_code ile direkt eşleşme
        product = self.env['product.product'].search([
            ('default_code', '=', product_code),
            ('active', '=', True),
        ], limit=1)

        if product:
            return product

        # 4. product.template.default_code ile eşleşme
        tmpl = self.env['product.template'].search([
            ('default_code', '=', product_code),
            ('active', '=', True),
        ], limit=1)

        if tmpl and len(tmpl.product_variant_ids) == 1:
            return tmpl.product_variant_ids[0]

        return None

    # ═══════════════════════════════════════════════════
    # ENTEGRA'YA ERP SYNC BİLDİRİMİ
    # ═══════════════════════════════════════════════════

    def _confirm_erp_sync(self, backend, entegra_order_id, odoo_order_name):
        """
        Entegra'ya siparişin ERP'ye alındığını bildirir.
        PUT /order/update/ → sync=1, erp_order_number=SO.name

        Bu çağrı başarısız olsa bile SO oluşturulmuştur.
        Hata log'a yazılır, exception fırlatılmaz.
        """
        try:
            payload = {'list': [{
                'id': entegra_order_id,
                'sync': 1,
                'erp_order_number': odoo_order_name,
            }]}
            backend.api_put('/order/update/', payload)
            _logger.debug(
                '[Entegra:%s] ERP sync bildirimi OK: %s → %s',
                backend.name, entegra_order_id, odoo_order_name
            )
        except Exception as e:
            _logger.warning(
                '[Entegra:%s] ERP sync bildirimi başarısız (sipariş yine oluşturuldu): %s → %s',
                backend.name, entegra_order_id, str(e)
            )

    # ═══════════════════════════════════════════════════
    # KARGO BİLGİSİ GÜNCELLEME (Odoo → Entegra)
    # ═══════════════════════════════════════════════════

    @api.model
    def push_shipment_info(self, backend, sale_order, cargo_company, cargo_code):
        """
        Kargo bilgisini Entegra'ya gönderir.
        Odoo'da picking tamamlandığında çağrılır.

        Args:
            backend:       entegra.backend
            sale_order:    sale.order kaydı
            cargo_company: Kargo firması adı (aras, yurtici, mng...)
            cargo_code:    Kargo takip numarası
        """
        if not sale_order.entegra_order_id:
            return  # Entegra'dan gelmemiş sipariş

        try:
            # Kargo statü güncelle — PUT /order/ ile status=3 (Kargolandı)
            # NOT: Entegra'da /order/sendShipment ayrı bir endpoint olabilir.
            # İlk canlı testte response loglanmalı; gerekirse ENTEGRA_ENDPOINTS
            # 'order_shipment' anahtarına geçilmeli.
            from .entegra_backend import ENTEGRA_ENDPOINTS
            payload = {'list': [{
                'id': sale_order.entegra_order_id,
                'status': 3,  # Kargolandı
                'cargo_code2': cargo_code,
                'cargo_company': cargo_company,
            }]}
            backend.api_put(ENTEGRA_ENDPOINTS['order_update'], payload)

            # SO'daki kargo bilgilerini güncelle
            sale_order.write({
                'entegra_cargo_company': cargo_company,
                'entegra_cargo_code': cargo_code,
            })

            _logger.info(
                '[Entegra:%s] Kargo bilgisi gönderildi: SO=%s, Kargo=%s/%s',
                backend.name, sale_order.name, cargo_company, cargo_code
            )
        except Exception as e:
            _logger.error(
                '[Entegra:%s] Kargo bilgisi gönderilemedi: %s → %s',
                backend.name, sale_order.name, str(e)
            )

    # ═══════════════════════════════════════════════════
    # CRON METODU
    # ═══════════════════════════════════════════════════

    @api.model
    def _cron_import_orders(self):
        """Zamanlanmış sipariş import — tüm aktif backend'ler."""
        backends = self.env['entegra.backend'].search([('active', '=', True)])
        for backend in backends:
            try:
                self.import_new_orders(backend)
            except Exception as e:
                _logger.error(
                    '[Entegra:%s] Cron sipariş import hatası: %s',
                    backend.name, str(e)
                )

    # ═══════════════════════════════════════════════════
    # YARDIMCI METODLAR
    # ═══════════════════════════════════════════════════

    def _parse_order_date(self, date_str):
        """Entegra tarih formatlarını Odoo Datetime'a çevirir."""
        if not date_str:
            return False
        # Entegra formatları: "29.09.2021", "2022-10-21 00:00"
        for fmt in ('%d.%m.%Y', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        _logger.warning('[Entegra] Tarih ayrıştırılamadı: %s', date_str)
        return False

    def _clean_email(self, email):
        """
        Bazı pazaryerleri email'i şifreler/özel karakter içerir.
        Geçersiz formattaysa boş string döner.
        """
        if not email:
            return ''
        email = email.strip()
        if '@' not in email or len(email) < 5:
            return ''
        return email.lower()

    def _get_currency(self, order_data):
        """Entegra para biriminden Odoo currency bul. Default: TRY."""
        entegra_code = str(order_data.get('currency', '') or '').upper() or 'TRL'
        currency_name = CURRENCY_CODE_MAP.get(entegra_code, 'TRY')
        odoo_currency = self.env['res.currency'].search([
            ('name', '=', currency_name),
            ('active', '=', True),
        ], limit=1)
        return odoo_currency

    def _write_log(self, backend, operation, status, **kwargs):
        """Sync log kaydı yaz."""
        vals = {
            'backend_id': backend.id,
            'operation': operation,
            'status': status,
        }
        vals.update(kwargs)
        self.env['entegra.sync.log'].sudo().create(vals)
