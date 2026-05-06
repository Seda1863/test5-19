# -*- coding: utf-8 -*-
"""
entegra_product_mapping.py
──────────────────────────
Odoo product.template / product.product ↔ Entegra ürün eşleme tablosu.

productCode = Entegra'da birincil tanımlayıcı.
Odoo'da default_code (internal reference) ile eşleşir.

Tasarım kararları:
- Ana ürün → product.tmpl_id + entegra_product_id/code
- Varyant  → product_id (product.product) + entegra_variation_id
- Mapping yoksa push yapılmaz; önce ürün Entegra'ya gönderilmeli.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class EntegraProductMapping(models.Model):
    _name = 'entegra.product.mapping'
    _description = 'Entegra Ürün Eşlemesi'
    _order = 'product_tmpl_id, product_id'
    _rec_name = 'entegra_product_code'

    backend_id = fields.Many2one(
        'entegra.backend',
        string='Backend',
        required=True,
        ondelete='cascade',
        index=True,
    )

    # ─── Odoo Tarafı ──────────────────────────────────
    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Ürün Şablonu',
        required=True,
        ondelete='cascade',
        index=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Varyant',
        ondelete='cascade',
        help='Boşsa ana ürün mapping\'i. Doluysa varyant mapping\'i.',
        index=True,
    )
    is_variant = fields.Boolean(
        string='Varyant mı?',
        compute='_compute_is_variant',
        store=True,
    )

    # ─── Entegra Tarafı ───────────────────────────────
    entegra_product_id = fields.Integer(
        string='Entegra Ürün ID',
        help='Entegra\'nın atadığı integer ID.',
    )
    entegra_product_code = fields.Char(
        string='Entegra productCode',
        required=True,
        help='Ana ürün stok kodu. Odoo default_code ile aynı olmalı.',
    )
    entegra_variation_id = fields.Integer(
        string='Entegra Varyant ID',
        help='Varyant mapping için Entegra variationId.',
    )
    entegra_variation_code = fields.Char(
        string='Entegra Varyant Kodu',
        help='Varyant productCode. Odoo product.product.default_code ile aynı olmalı.',
    )

    # ─── Sync Durumu ──────────────────────────────────
    sync_status = fields.Selection(
        selection=[
            ('pending',  'Bekliyor'),
            ('synced',   'Senkronize'),
            ('error',    'Hata'),
            ('excluded', 'Hariç Tutuldu'),
        ],
        string='Sync Durumu',
        default='pending',
        index=True,
    )
    last_sync_date = fields.Datetime(string='Son Sync Tarihi')
    last_stock_sync = fields.Datetime(string='Son Stok Sync')
    last_price_sync = fields.Datetime(string='Son Fiyat Sync')
    sync_error = fields.Text(string='Sync Hatası')

    # ─── Computed ─────────────────────────────────────
    @api.depends('product_id')
    def _compute_is_variant(self):
        for rec in self:
            rec.is_variant = bool(rec.product_id)

    # ─── Constraints ──────────────────────────────────
    _sql_constraints = [
        (
            'unique_backend_product',
            'UNIQUE(backend_id, product_tmpl_id, product_id)',
            'Bu ürün için bu backend\'de zaten bir eşleme var.',
        ),
        (
            'unique_entegra_code',
            'UNIQUE(backend_id, entegra_product_code, entegra_variation_code)',
            'Bu Entegra kodu için zaten bir eşleme mevcut.',
        ),
    ]

    @api.constrains('entegra_product_code')
    def _check_product_code(self):
        for rec in self:
            if not rec.entegra_product_code:
                raise ValidationError(_('Entegra productCode boş olamaz.'))

    # ─── Yardımcı Metodlar ────────────────────────────
    def set_synced(self, entegra_id=None, variation_id=None):
        """Sync başarılı olduğunda çağrılır."""
        vals = {
            'sync_status': 'synced',
            'last_sync_date': fields.Datetime.now(),
            'sync_error': False,
        }
        if entegra_id:
            vals['entegra_product_id'] = entegra_id
        if variation_id:
            vals['entegra_variation_id'] = variation_id
        self.write(vals)

    def set_error(self, message):
        """Sync hatası olduğunda çağrılır."""
        self.write({
            'sync_status': 'error',
            'sync_error': message,
        })
