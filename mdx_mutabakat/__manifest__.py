{
    'name': 'MDX Mutabakat Sistemi',
    'version': '19.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Tedarikçi mutabakat mektubu gönderme ve yanıt takip sistemi',
    'description': """
        Tedarikçilere mutabakat mektubu gönderilmesini ve yanıtların takip edilmesini sağlar.
        - Toplu / tekli mutabakat gönderimi
        - E-posta ile "Mutabıkız" / "Mutabık Değiliz" yanıt toplama
        - Yanıt takibi ve raporlama
    """,
    'author': 'MindDX Dijital Dönüşüm Teknolojileri',
    'website': 'https://www.minddx.ai',
    'depends': ['account', 'mail', 'contacts'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/mutabakat_cron_data.xml',
        'report/mutabakat_report.xml',
        'report/mutabakat_report_templates.xml',
        'data/mail_template_data.xml',
        'views/mdx_mutabakat_views.xml',
        'views/mdx_mutabakat_wizard_views.xml',
        'views/res_partner_views.xml',
        'views/response_page_template.xml',
    ],
    'assets': {},
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
