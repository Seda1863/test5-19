from odoo import api, models, _, fields
from odoo.exceptions import UserError
from odoo.osv import expression
from odoo.tools import SQL

from datetime import timedelta
from collections import defaultdict

class MdxInhPartnerLedgerCustomHandler(models.AbstractModel):
    _name = 'mdx.inh.account.partner.ledger.report.handler'
    _inherit = 'account.partner.ledger.report.handler'
    _description = 'Mdx Inh Partner Ledger Custom Handler'

    def _get_aml_values(self, options, partner_ids, offset=0, limit=None):
        rslt = super()._get_aml_values(options, partner_ids, offset, limit)
        
        # Para birimi bilgilerini ekle
        for partner_id, amls in rslt.items():
            for aml in amls:
                if aml.get('currency_id'):
                    currency = self.env['res.currency'].browse(aml['currency_id'])
                    aml['currency_symbol'] = currency.symbol
        return rslt

class MdxInhCustomerStatementHandler(models.AbstractModel):
    _name = 'mdx.inh.account.customer.statement.report.handler'
    _inherit = 'account.customer.statement.report.handler'

    def _get_currency_totals(self, aml_results):
        currency_totals = defaultdict(lambda: {'amount': 0.0, 'balance': 0.0})
        for aml in aml_results:
            currency_id = aml.get('currency_id')
            if currency_id:
                currency = self.env['res.currency'].browse(currency_id)
                amount = aml.get('amount_currency', 0.0)
                
                # Tutar ve bakiye hesaplama
                currency_totals[currency]['amount'] += amount
                currency_totals[currency]['balance'] += amount
        return currency_totals

    def _format_currency_line(self, currency_totals):
        """Para birimi toplamlarını formatlı şekilde döndürür"""
        amount_parts = []
        balance_parts = []
        
        for currency, values in currency_totals.items():
            symbol = currency.symbol
            amount_parts.append(f"{values['amount']:,.2f}{symbol}")
            balance_parts.append(f"{values['balance']:,.2f}{symbol}")
        
        return "  |  ".join(amount_parts), "  |  ".join(balance_parts)

    def _get_column_indexes(self, options):
        """Sütun indekslerini bul"""
        amount_index = None
        balance_index = None
        
        for i, column in enumerate(options['columns']):
            if column['expression_label'] == 'amount':
                amount_index = i
            elif column['expression_label'] == 'balance':
                balance_index = i
                
        return amount_index, balance_index

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        # Sütun indekslerini al
        amount_index, balance_index = self._get_column_indexes(options)
        
        # Orijinal satırları al
        lines = super()._dynamic_lines_generator(report, options, all_column_groups_expression_totals, warnings)
        
        # Para birimi toplamları için sözlük
        all_currency_totals = defaultdict(lambda: {'amount': 0.0, 'balance': 0.0})
        new_lines = []
        
        for line in lines:
            line_data = line[1]  # (sequence, line_dict)
            new_lines.append(line)
            
            # Partner satırlarını bul
            if line_data.get('unfoldable') and 'res.partner' in str(line_data.get('id', '')):
                # Partner ID'yi al
                markup, model, partner_id = report._parse_line_id(line_data['id'])[-1]
                
                if model == 'res.partner':
                    # Partner ID'yi güvenli şekilde işle
                    try:
                        partner_id = int(partner_id) if partner_id and partner_id != 'no_partner' else None
                    except (TypeError, ValueError):
                        partner_id = None
                    
                    # Partner'a ait hareketleri getir
                    if partner_id is not None:
                        aml_results = self._get_aml_values(options, [partner_id]).get(partner_id, [])
                    else:
                        # 'no_partner' durumu için
                        aml_results = self._get_aml_values(options, [None]).get(None, [])
                    
                    # Para birimi toplamlarını hesapla
                    currency_totals = self._get_currency_totals(aml_results)
                    
                    # Formatlanmış string oluştur
                    amount_str, balance_str = self._format_currency_line(currency_totals)
                    
                    # Genel toplamları güncelle
                    for currency, values in currency_totals.items():
                        all_currency_totals[currency]['amount'] += values['amount']
                        all_currency_totals[currency]['balance'] += values['balance']
                    
                    # Boş sütunlar oluştur
                    columns = [{'name': ''} for _ in options['columns']]
                    
                    # 3. ve 5. sütunları doldur (Amount ve Balance)
                    if amount_index is not None:
                        columns[amount_index]['name'] = amount_str
                    if balance_index is not None:
                        columns[balance_index]['name'] = balance_str
                    
                    # Yeni ara toplam satırı ekle
                    currency_line = {
                        'id': report._get_generic_line_id('currency.summary', partner_id or 'no_partner', parent_line_id=line_data['id']),
                        'name': _("Para Birimlerine Göre Toplam"),
                        'level': line_data['level'] + 1,
                        'parent_id': line_data['id'],
                        'columns': columns,
                        'class': 'o_bold',  # Bold satır
                    }
                    new_lines.append((0, currency_line))
        
        # Genel toplam satırını bul ve değiştir
        for i, line in enumerate(new_lines):
            line_data = line[1]
            if line_data.get('id', '').endswith('total'):
                # Genel toplam için para birimi toplamları
                amount_str, balance_str = self._format_currency_line(all_currency_totals)
                
                # Boş sütunlar oluştur
                columns_total = [{'name': ''} for _ in options['columns']]
                
                # 3. ve 5. sütunları doldur (Amount ve Balance)
                if amount_index is not None:
                    columns_total[amount_index]['name'] = amount_str
                if balance_index is not None:
                    columns_total[balance_index]['name'] = balance_str
                
                # Yeni genel toplam satırı oluştur
                total_currency_line = {
                    'id': report._get_generic_line_id('currency.total', 0),
                    'name': _("Total Currency Summary"),
                    'level': 1,
                    'columns': columns_total,
                    'class': 'o_bold',  # Bold satır
                }
                
                # Orijinal toplam satırından sonra ekle
                new_lines.insert(i + 1, (0, total_currency_line))
                break
        
        return new_lines