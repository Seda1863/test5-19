# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
from odoo.tools import float_is_zero, SQL
from odoo.exceptions import UserError

from itertools import chain


class MdxInhMulticurrencyRevaluationReportCustomHandler(models.AbstractModel):
    _inherit = 'account.multicurrency.revaluation.report.handler'
    _description = 'MindDX Multicurrency Revaluation Report Custom Handler'

    def _custom_options_initializer(self, report, options, previous_options):
        if report.root_report_id and report.root_report_id.custom_handler_model_id != report.custom_handler_model_id:
            report.root_report_id._init_options_custom(options, previous_options)
            
        # Hiç super kullanmadan doğrudan kendi kodumuzu çalıştır
        active_currencies = self.env['res.currency'].search([('active', '=', True)])
        if len(active_currencies) < 2:
            raise UserError(_("You need to activate more than one currency to access this report."))
        
        # Yeni yapı: {currency_id: {'rate': float, ...}}
        raw_rates = active_currencies._get_rates(self.env.company, options.get('date').get('date_to'))
        
        # Normalize the rates to the company's currency
        company_currency_id = self.env.company.currency_id.id
        company_rate_data = raw_rates.get(company_currency_id, {})
        company_rate = company_rate_data.get('rate', 1.0) if isinstance(company_rate_data, dict) else company_rate_data
        
        # Düzeltme: Sadece 'rate' değerlerini kullan ve normalize et
        normalized_rates = {}
        for currency_id, rate_data in raw_rates.items():
            # Eğer rate_data sözlükse 'rate' anahtarını kullan, değilse direkt değer
            current_rate = rate_data['rate'] if isinstance(rate_data, dict) else rate_data
            normalized_rates[currency_id] = current_rate / company_rate

        options['currency_rates'] = {
            str(currency_id.id): {
                'currency_id': currency_id.id,
                'currency_name': currency_id.name,
                'currency_main': self.env.company.currency_id.name,
                'rate': (normalized_rates[currency_id.id]
                        if not previous_options.get('currency_rates', {}).get(str(currency_id.id), {}).get('rate') else
                        float(previous_options['currency_rates'][str(currency_id.id)]['rate'])),
            } for currency_id in active_currencies
        }

        for currency_rates in options['currency_rates'].values():
            if currency_rates['rate'] == 0:
                raise UserError(_("The currency rate cannot be equal to zero"))

        options['company_currency'] = options['currency_rates'].pop(str(self.env.company.currency_id.id))
        options['custom_rate'] = any(
            not float_is_zero(cr['rate'] - normalized_rates[cr['currency_id']], 20)
            for cr in options['currency_rates'].values()
        )

        options['multi_currency'] = True
        options['buttons'].append({'name': _('Adjustment Entry'), 'sequence': 30, 'action': 'action_multi_currency_revaluation_open_revaluation_wizard', 'always_show': True})