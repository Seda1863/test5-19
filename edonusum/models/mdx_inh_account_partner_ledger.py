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

    def _get_additional_column_aml_values(self):
        return SQL("""
            account_move_line.amount_currency AS amount_currency,
            CASE WHEN account_move_line.amount_currency > 0 
                 THEN account_move_line.amount_currency 
                 ELSE 0 END AS debit_currency,
            CASE WHEN account_move_line.amount_currency < 0 
                 THEN -account_move_line.amount_currency 
                 ELSE 0 END AS credit_currency,
            account_move_line.currency_id AS currency_id,
        """)

    def _get_report_line_move_line(self, options, aml, partner_line_id, init_bal_by_col_group, level_shift=0):
        report = self.env['account.report'].browse(options['report_id'])
        # company_currency = self.env.company.currency_id

        # 1) Önce standard satırı alalım
        line = super()._get_report_line_move_line(
            options, aml, partner_line_id, init_bal_by_col_group, level_shift
        )

        # 2) Hangi aml'nin hangi kuru var?
        currency_id = aml.get('currency_id')
        currency = currency_id and self.env['res.currency'].browse(currency_id) or None

        # 3) Satırdaki her bir sütun hücresine bakalım
        for cell in line['columns']:
            expr = cell.get('expression_label')
            # sadece kendi eklediğiniz 4 sütunu işleyin:
            if expr in ('debit_currency', 'credit_currency', 'currency_id', 'amount_currency'):
                # değer atamasına karar verelim
                if expr == 'debit_currency':
                        value = currency and aml.get('debit_currency', 0.0) or 0.0
                elif expr == 'credit_currency':
                        value = currency and aml.get('credit_currency', 0.0) or 0.0
                elif expr == 'amount_currency':
                        value = currency and aml.get('amount_currency', 0.0) or 0.0
                else:  # expr == 'currency_id'
                    # her satırda kur adını göstereceğiz:
                    value = currency.name if currency else ''

                # 4) Odoo'nun formatlama ve sembol ekleyeniyle hücreyi yeniden yaz
                new_cell = report._build_column_dict(
                    value,                           # miktar veya isim
                    # options['columns'] içindeki sütun tanımını bulalım:
                    next(c for c in options['columns'] if c['expression_label'] == expr),
                    options=options,
                    currency=currency              # None olursa şirket kuru kullanılır
                )
                # eski hücre içeriğini komple değiştiriyoruz
                cell.update(new_cell)

        return line

    def _report_expand_unfoldable_line_partner_ledger(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        result = super()._report_expand_unfoldable_line_partner_ledger(
            line_dict_id, groupby, options, progress, offset, unfold_all_batch_data
        )

        # Get partner ID from line_dict_id
        markup, model, partner_id = self.env['account.report']._parse_line_id(line_dict_id)[-1]

        if model != 'res.partner':
            return result

        # Calculate currency totals
        currency_totals = defaultdict(lambda: {
            'debit_currency': 0.0,
            'credit_currency': 0.0,
        })

        # Collect all AMLs for this partner
        all_aml_results = []
        current_offset = offset
        has_more = True
        report = self.env['account.report'].browse(options['report_id'])

        while has_more:
            if unfold_all_batch_data:
                aml_results = unfold_all_batch_data['aml_values'].get(partner_id, [])
                has_more = False
            else:
                aml_results = self._get_aml_values(
                    options, [partner_id], offset=current_offset, limit=report.load_more_limit + 1 if report.load_more_limit else None
                ).get(partner_id, [])
                has_more = report.load_more_limit and len(aml_results) > report.load_more_limit
                if has_more:
                    aml_results = aml_results[:report.load_more_limit]

            all_aml_results.extend(aml_results)
            current_offset += len(aml_results)

            if not has_more or options['export_mode'] == 'print':
                break

        # Calculate totals per currency
        for aml in all_aml_results:
            currency_id = aml.get('currency_id')
            currency_totals[currency_id]['debit_currency'] += aml.get('debit_currency', 0)
            currency_totals[currency_id]['credit_currency'] += aml.get('credit_currency', 0)

        # Create subtotal lines
        subtotal_lines = []

        for currency_id, totals in currency_totals.items():
            currency = self.env['res.currency'].browse(currency_id)

            columns = []
            for column in options['columns']:
                col_expr_label = column['expression_label']
                value = None

                if col_expr_label == 'debit_currency':
                    value = totals['debit_currency']
                elif col_expr_label == 'credit_currency':
                    value = totals['credit_currency']
                elif col_expr_label == 'amount_currency':
                    value = totals.get('debit_currency', 0) - totals.get('credit_currency', 0)
                elif col_expr_label == 'currency_id':
                    value = currency.name

                columns.append(report._build_column_dict(
                    value, column, options=options, currency=currency
                ))

            subtotal_lines.append({
                'id': report._get_generic_line_id(
                    'currency.totals', 
                    currency_id, 
                    parent_line_id=line_dict_id
                ),
                'parent_id': line_dict_id,
                'name': _("Total %s") % currency.name,
                'columns': columns,
                'level': 4,  # Deeper than transaction lines
                'class': 'o_bold_tr',
            })

        # Add subtotal lines after transaction lines
        if subtotal_lines:
            result['lines'].extend(subtotal_lines)

        return result

    def _get_aml_values(self, options, partner_ids, offset=0, limit=None):
        rslt = super()._get_aml_values(options, partner_ids, offset, limit)
        
        # Add currency_id to AML results
        for partner_id, amls in rslt.items():
            for aml in amls:
                aml['currency_id'] = aml.get('currency_id', False)
        
        return rslt