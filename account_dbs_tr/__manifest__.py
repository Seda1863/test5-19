{
    'name': 'TR DBS Core (Dogrudan Borclandirma Sistemi)',
    'version': '19.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Turkiye DBS cekirdek modul: sozlesme, batch, ACK ve statement esleme',
    'description': """
        DBS cekirdek modul (MVP):
        - DBS sozlesme ve musteri profil yonetimi
        - Faturalardan DBS batch olusturma
        - Dosya tabanli export ve ACK import
        - Statement satirlarindan otomatik DBS esleme
        - Adaptor pattern ile banka bazli genisleme
    """,
    'author': 'MindDX Dijital Donusum Teknolojileri',
    'website': 'https://www.minddx.ai',
    'depends': ['account', 'mail'],
    'data': [
        'security/dbs_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/cron_data.xml',
        'views/dbs_contract_views.xml',
        'views/dbs_batch_views.xml',
        'views/dbs_risk_confirm_wizard_views.xml',
        'views/dbs_profile_confirm_wizard_views.xml',
        'views/res_partner_views.xml',
        'views/account_move_views.xml',
        'report/dbs_partner_report.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
