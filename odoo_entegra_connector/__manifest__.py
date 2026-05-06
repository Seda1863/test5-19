# -*- coding: utf-8 -*-
{
    'name': 'Entegra Connector',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Odoo ↔ Entegra Pazaryeri Entegrasyonu',
    'description': """
        Entegra API v2 ile Odoo arasında ürün, stok, fiyat ve sipariş senkronizasyonu.
        Desteklenen pazaryerleri: Trendyol, Hepsiburada, N11, Amazon ve diğerleri.
    """,
    'author': 'MindDX',
    'website': 'https://www.minddx.com.tr',
    'license': 'OPL-1',
    'depends': [
        'base',
        'sale_management',
        'stock',
        'product',
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/entegra_backend_views.xml',
        'views/entegra_sync_log_views.xml',
        'views/product_template_views.xml',
        'views/entegra_push_wizard_views.xml',
        'views/sale_order_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
