{
    'name': 'MDX Teminat Mektubu Yönetimi',
    'version': '18.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Banka teminat mektuplarının takibi, vade kontrolü ve limit yönetimi',
    'description': """
        Banka teminat mektuplarının merkezi yönetimi:
        - Teminat mektubu kaydı ve takibi
        - Banka limit kontrolü
        - Vade hatırlatıcı (30/15/7 gün)
        - Onay akışı (Taslak → Onay Bekliyor → Aktif → İade/İptal)
        - PDF ve Pivot raporlama
    """,
    'author': 'MindDX Dijital Dönüşüm Teknolojileri',
    'website': 'https://www.minddx.ai',
    'depends': ['account', 'mail', 'project', 'contacts'],
    'data': [
        'security/guarantee_letter_security.xml',
        'security/ir.model.access.csv',
        'data/guarantee_letter_type_data.xml',
        'data/ir_sequence_data.xml',
        'data/guarantee_cron_data.xml',
        'report/guarantee_report.xml',
        'report/guarantee_report_templates.xml',
        'views/guarantee_letter_views.xml',
        'views/bank_guarantee_limit_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
