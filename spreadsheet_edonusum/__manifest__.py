# -*- coding: utf-8 -*-
{
    'name': 'Spreadsheet Dashboard - E-Dönüşüm Muhasebe',
    'version': '19.0.1.0.10',
    'category': 'Accounting/Localizations',
    'summary': 'E-Dönüşüm Muhasebe Dashboard - Çek Yönetimi, E-Fatura, E-İrsaliye Analizleri',
    'description': """
        E-Dönüşüm Muhasebe Dashboard Modülü
        ====================================
        
        Bu modül edonusum modülüne ek olarak aşağıdaki dashboard'ları sunar:
        
        1. ÇEK TAKİP PANELİ
           - Vadesi Gelen/Geçen Çekler
           - Çek Portföy Durumu
           - Çek Hareketleri Analizi
           - Vade Takvimi
        
        2. E-FATURA ANALİZ PANELİ
           - Giden E-Fatura Özeti
           - Gelen E-Fatura Takibi
           - E-Arşiv Fatura Analizi
           - Fatura Tipi/Senaryo Dağılımı
        
        3. E-İRSALİYE TAKİP PANELİ
           - Giden E-İrsaliye Analizi
           - Gelen E-İrsaliye Durumu
           - Faturalanmamış İrsaliyeler
        
        4. TEVKİFAT VE VERGİ ANALİZİ
           - Tevkifat Oranlarına Göre Dağılım
           - İstisna Kodlu Faturalar
           - KDV Analizi
        
        5. CARİ HESAP ANALİZİ
           - E-Fatura Mükellef Durumu
           - Müşteri/Tedarikçi Bakiye Analizi
           - Dövizli İşlem Özeti
    """,
    'author': 'MindDX Digital Dönüşüm Teknolojileri A.Ş.',
    'website': 'https://www.minddx.com',
    'depends': [
        'spreadsheet_dashboard',
        'edonusum',
        'account',
        'stock',
    ],
    'data': [
        'data/dashboard_groups.xml',
        'data/dashboards.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
