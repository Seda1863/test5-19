# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    entegra_variant_mapping_ids = fields.One2many(
        'entegra.product.mapping',
        'product_id',
        string='Entegra Varyant Eşlemeleri',
    )
