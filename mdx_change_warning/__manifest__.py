# -*- coding: utf-8 -*-
{
    'name': 'MindDX Değişiklik Onay Sistemi',
    'version': '19.0.1.0.0',
    'installable': True,
    'application': False,
    'author': 'MindDX Digital Dönüşüm Teknolojileri A.Ş.',
    'summary': 'Kayıt değişikliklerinde kullanıcıdan onay alır',
    'description': """
        Belirli modellerde belirli alanlar değiştirildiğinde
        kullanıcıya onay diyaloğu gösterir.
        Kurallar Ayarlar > Teknik > Değişiklik Uyarıları menüsünden yönetilir.
    """,
    'depends': ['base', 'web'],
    'category': 'Technical',
    'data': [
        'security/ir.model.access.csv',
        'views/mdx_change_warning_rule_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mdx_change_warning/static/src/js/change_warning_interceptor.js',
        ],
    },
    'license': 'LGPL-3',
}
