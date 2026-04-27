# -*- coding: utf-8 -*-

import requests
import xml.etree.ElementTree as ET
import json
from datetime import timedelta

from odoo import models, fields, api
import logging
from odoo.exceptions import UserError, ValidationError
_logger = logging.getLogger(__name__)

class MdxInhResCurrency(models.Model):
    _inherit = 'res.currency'

    # store=True yapılacak alanlar
    currency_unit_label_efatura = fields.Char(string="Currency Unit (E-Invoice)", store=True)
    currency_subunit_label_efatura = fields.Char(string="Currency Subunit (E-Invoice)", store=True)
    forex_buying = fields.Float('Forex Buying', compute='_compute_mdx_rate_fields', digits=(12, 6), store=False)
    forex_selling = fields.Float('Forex Selling', compute='_compute_mdx_rate_fields', digits=(12, 6), store=False)
    banknote_buying = fields.Float('Banknote Buying', compute='_compute_mdx_rate_fields', digits=(12, 6), store=False)
    banknote_selling = fields.Float('Banknote Selling', compute='_compute_mdx_rate_fields', digits=(12, 6), store=False)

    def _get_rates(self, company, date):
        """ TCMB verilerini de içerecek şekilde genişletilmiş kur verilerini getirir """
        if not self.ids:
            return {}
            
        self.env['res.currency.rate'].flush_model([
            'rate', 'forex_buying', 'forex_selling', 
            'banknote_buying', 'banknote_selling', 
            'currency_id', 'company_id', 'name'
        ])
        
        query = """
            SELECT c.id,
                   COALESCE(r.rate, 1.0) as rate,
                   r.forex_buying,
                   r.forex_selling,
                   r.banknote_buying,
                   r.banknote_selling
            FROM res_currency c
            LEFT JOIN LATERAL (
                SELECT rate, forex_buying, forex_selling, banknote_buying, banknote_selling 
                FROM res_currency_rate 
                WHERE currency_id = c.id 
                AND name <= %s 
                AND (company_id IS NULL OR company_id = %s)
                ORDER BY name DESC, company_id 
                LIMIT 1
            ) r ON TRUE
            WHERE c.id IN %s
        """
        self._cr.execute(query, (date, company.root_id.id, tuple(self.ids)))
        return {
            row[0]: {
                'rate': row[1],
                'forex_buying': row[2] or 0.0,
                'forex_selling': row[3] or 0.0,
                'banknote_buying': row[4] or 0.0,
                'banknote_selling': row[5] or 0.0,
            }
            for row in self._cr.fetchall()
        }

    @api.depends('rate_ids.rate', 'rate_ids.forex_buying', 'rate_ids.forex_selling', 'rate_ids.banknote_buying', 'rate_ids.banknote_selling')
    @api.depends_context('to_currency', 'date', 'company', 'company_id')
    def _compute_current_rate(self):
        """ Mevcut hesaplamaya ek olarak TCMB kurlarını da hesaplar """
        # super(MdxInhResCurrency, self)._compute_current_rate()
        
        date = self._context.get('date') or fields.Date.context_today(self)
        company = self.env['res.company'].browse(self._context.get('company_id')) or self.env.company
        company = company.root_id
        to_currency = self.browse(self.env.context.get('to_currency')) or company.currency_id
        
        currency_rates = (self + to_currency)._get_rates(company, date)
        
        for currency in self:
            currency.rate = (currency_rates[currency.id]['rate'] or 1.0) / currency_rates[to_currency.id]['rate']
            currency.inverse_rate = 1 / currency.rate

    @api.depends('rate_ids.rate', 'rate_ids.forex_buying', 'rate_ids.forex_selling', 'rate_ids.banknote_buying', 'rate_ids.banknote_selling')
    @api.depends_context('to_currency', 'date', 'company', 'company_id')
    def _compute_mdx_rate_fields(self):
        date = self._context.get('date') or fields.Date.context_today(self)
        company = self.env['res.company'].browse(self._context.get('company_id')) or self.env.company
        company = company.root_id

        currency_rates = self._get_rates(company, date)

        for currency in self:
            currency.forex_buying = currency_rates.get(currency.id, {}).get('forex_buying', 0.0) or 0.0
            currency.forex_selling = currency_rates.get(currency.id, {}).get('forex_selling', 0.0) or 0.0
            currency.banknote_buying = currency_rates.get(currency.id, {}).get('banknote_buying', 0.0) or 0.0
            currency.banknote_selling = currency_rates.get(currency.id, {}).get('banknote_selling', 0.0) or 0.0
