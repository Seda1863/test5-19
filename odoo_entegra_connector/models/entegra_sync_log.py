# -*- coding: utf-8 -*-
"""
entegra_sync_log.py
───────────────────
Her Entegra API sync işleminin kaydını tutar.
Hata debug'ı ve audit trail için kullanılır.
"""

from odoo import fields, models


class EntegraSyncLog(models.Model):
    _name = 'entegra.sync.log'
    _description = 'Entegra Sync Logu'
    _order = 'create_date desc'
    _rec_name = 'operation'

    backend_id = fields.Many2one(
        'entegra.backend',
        string='Backend',
        required=True,
        ondelete='cascade',
    )
    operation = fields.Selection(
        selection=[
            ('product_push',    'Ürün Push'),
            ('product_update',  'Ürün Güncelleme'),
            ('stock_update',    'Stok Güncelleme'),
            ('price_update',    'Fiyat Güncelleme'),
            ('order_import',    'Sipariş Import'),
            ('order_update',    'Sipariş Güncelleme'),
            ('send_shipment',   'Kargo Bildirimi'),
            ('token_obtain',    'Token Alma'),
            ('token_refresh',   'Token Yenileme'),
        ],
        string='İşlem',
        required=True,
    )
    status = fields.Selection(
        selection=[
            ('success', 'Başarılı'),
            ('error',   'Hata'),
            ('warning', 'Uyarı'),
        ],
        string='Durum',
        required=True,
    )
    model_name = fields.Char(string='Model')
    record_id = fields.Integer(string='Kayıt ID')
    record_name = fields.Char(string='Kayıt Adı')

    # Entegra tarafı referans
    entegra_ref = fields.Char(string='Entegra Referans')

    # İstek / yanıt detayları (hata debug için)
    request_data = fields.Text(string='Gönderilen Veri')
    response_data = fields.Text(string='Alınan Yanıt')
    error_message = fields.Text(string='Hata Mesajı')

    duration_ms = fields.Integer(string='Süre (ms)')
    create_date = fields.Datetime(string='Tarih', readonly=True)

    def action_view_record(self):
        """İlgili Odoo kaydına git."""
        self.ensure_one()
        if not self.model_name or not self.record_id:
            return
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.model_name,
            'res_id': self.record_id,
            'view_mode': 'form',
        }
