
# -*- coding: utf-8 -*-

import logging
import requests
from dateutil.relativedelta import relativedelta
from lxml import etree
from pytz import timezone
import datetime
import json

from odoo import api, fields, models
from odoo.addons.account.tools import LegacyHTTPAdapter
from odoo.exceptions import UserError
from odoo.tools.translate import _

_logger = logging.getLogger(__name__)

class MdxInhResCompany(models.Model):
    _inherit = 'res.company'

    # store=True alanlar
    owner_id = fields.Many2one('res.users', string='Sorumlu Kişi', domain=[('active', '=', True)], store= True)
    fiscal_year_start_month = fields.Selection([
        ('01', 'Ocak'),
        ('02', 'Şubat'),
        ('03', 'Mart'),
        ('04', 'Nisan'),
        ('05', 'Mayıs'),
        ('06', 'Haziran'),
        ('07', 'Temmuz'),
        ('08', 'Ağustos'),
        ('09', 'Eylül'),
        ('10', 'Ekim'),
        ('11', 'Kasım'),
        ('12', 'Aralık'),
    ], string='Mali Yıl Başlangıç Ayı', required=True, default='01', store=True)
    fiscal_year_end_month = fields.Selection([
        ('01', 'Ocak'),
        ('02', 'Şubat'),
        ('03', 'Mart'),
        ('04', 'Nisan'),
        ('05', 'Mayıs'),
        ('06', 'Haziran'),
        ('07', 'Temmuz'),
        ('08', 'Ağustos'),
        ('09', 'Eylül'),
        ('10', 'Ekim'),
        ('11', 'Kasım'),
        ('12', 'Aralık'),
    ], string='Mali Yıl Son Ayı', required=True, compute='_compute_fiscal_year_end_month', store=True)

    # store=True yapılacak alanlar
    gumruk_ticaret_bakanligi_carisi_id = fields.Many2one('res.partner', string='Gümrük ve Ticaret Bakanlığı Cari', domain=[('active', '=', True)], store=True)
    iade_hesabi_id = fields.Many2one('account.account', string='İade Hesabı', store=True)
    iade_hesabi_kdv_id = fields.Many2one('account.account', string='İade Hesabı (KDV)', store=True)
    yurtici_satis_hesabi_id = fields.Many2one('account.account', string='Yurtiçi Satış Hesabı', store=True)
    yurtdisi_satis_hesabi_id = fields.Many2one('account.account', string='Yurtdışı Satış Hesabı', store=True)
    efatura_senaryo_id = fields.Many2one('mdx.ebelge.senaryo', string='Tercih Edilen Fatura Senaryo', domain=[('active', '=', True), ('code', 'in', ['TEMELFATURA', 'TICARIFATURA'])], store=True)
    efatura_musterisi = fields.Boolean(string='E-Fatura Müşterisi', default=False, store=True)
    earsiv_musterisi = fields.Boolean(string='E-Arşiv Müşterisi', default=False, store=True)
    eirsaliye_musterisi = fields.Boolean(string='E-İrsaliye Müşterisi', default=False, store=True)
    hizmet_sektoru = fields.Boolean(string='Hizmet Sektörü', default=False, store=True)
    legal_name = fields.Char(string='Legal Ad', store=True)
    fax = fields.Char(string='Faks', store=True)
    mersis_no = fields.Char(string='MERSIS No', store=True)
    ticaret_sicil_no = fields.Char(string='Ticaret Sicil No', store=True)
    vergi_dairesi = fields.Char(string='Vergi Dairesi', store=True)
    web_site = fields.Char(string='Web Sitesi', store=True)
    web_service_ids = fields.One2many('mdx.web.service', 'company_id', string='Web Services', store=True)
    active = fields.Boolean(string='Aktif', default=True, store=True)
    
    @api.depends('fiscal_year_start_month')
    def _compute_fiscal_year_end_month(self):
        for record in self:
            if record.fiscal_year_start_month:
                    month_int = int(record.fiscal_year_start_month)
                    # Eğer başlangıç ayı Ocak ise, mali yıl son ayı Aralık olur.
                    if month_int == 1:
                        record.fiscal_year_end_month = '12'
                    else:
                        record.fiscal_year_end_month = str(month_int - 1).zfill(2)
            else:
                record.fiscal_year_end_month = False

    # KUR GELİŞTİRMESİ:
    
    def _parse_tcmb_data(self, available_currencies):
        """TCMB'den Forex Buying, Forex Selling, Banknote Buying, Banknote Selling değerlerini alır"""
        server_url = 'https://www.tcmb.gov.tr/kurlar/today.xml'
        available_currency_names = set(available_currencies.mapped('name'))

        # SSL hatalarını önlemek için LegacyHTTPAdapter kullanıyoruz
        session = requests.Session()
        session.mount('https://', LegacyHTTPAdapter())

        res = session.get(server_url, timeout=30)
        res.raise_for_status()

        root = etree.fromstring(res.text.encode())
        # Parse the date from XML and subtract one day
        parsed_date = datetime.datetime.strptime(root.attrib['Date'], '%m/%d/%Y')
        adjusted_date = parsed_date + relativedelta(days=1)
        rate_date = fields.Date.to_string(adjusted_date)
        rslt = {}

        for currency in root:
            code = currency.attrib['Kod']
            if code in available_currency_names:
                forex_buying = float(currency.find('ForexBuying').text or 0)
                forex_selling = float(currency.find('ForexSelling').text or 0)
                banknote_buying = float(currency.find('BanknoteBuying').text or 0)
                banknote_selling = float(currency.find('BanknoteSelling').text or 0)

                rslt[code] = ((2/(forex_buying + forex_selling)), forex_buying, forex_selling, banknote_buying, banknote_selling, rate_date)

        # TRY için varsayılan değer
        rslt['TRY'] = (1.0, 1.0, 1.0, 1.0, 1.0, rate_date)
        return rslt

    def _generate_currency_rates(self, parsed_data):
        """ TCMB'den gelen verileri currency rate modeline kaydeder """
        Currency = self.env['res.currency']
        CurrencyRate = self.env['res.currency.rate']

        for company in self:
            rate_info = parsed_data.get(company.currency_id.name, None)

            if not rate_info:
                raise UserError(_("Your main currency (%s) is not supported by this exchange rate provider. Please choose another one.", company.currency_id.name))

            # _, _, _, _, _, rate_date = rate_info
            base_currency_rate = rate_info[0]

            for currency, (rate, forex_buying, forex_selling, banknote_buying, banknote_selling, date_rate) in parsed_data.items():
                rate_value = rate / base_currency_rate
                currency_object = Currency.search([('name', '=', currency)])
                if currency_object:
                    existing_rate = CurrencyRate.search([
                        ('currency_id', '=', currency_object.id),
                        ('name', '=', date_rate),
                        ('company_id', '=', company.id)
                    ])
                    if existing_rate:
                        existing_rate.write({
                            'rate': 1 / forex_buying,
                            'forex_buying': forex_buying or 0.0,
                            'forex_selling': forex_selling or 0.0,
                            'banknote_buying': banknote_buying or 0.0,
                            'banknote_selling': banknote_selling or 0.0,
                        })
                    else:
                        CurrencyRate.create({
                            'currency_id': currency_object.id,
                            'rate': 1 / forex_buying,
                            'name': date_rate,
                            'company_id': company.id,
                            'forex_buying': forex_buying or 0.0,
                            'forex_selling': forex_selling or 0.0,
                            'banknote_buying': banknote_buying or 0.0,
                            'banknote_selling': banknote_selling or 0.0,
                        })

    def update_currency_rates(self):
        """
        TCMB seçiliyse özel metodu çağır, diğer durumlarda standart süreci uygula.
        """
        active_currencies = self.env['res.currency'].search([])
        rslt = True

        for (currency_provider, companies) in self._group_by_provider().items():
            if currency_provider == 'tcmb':
                parse_function = self._parse_tcmb_data
            else:
                parse_function = getattr(companies, '_parse_' + currency_provider + '_data', None)

            if not parse_function:
                continue

            try:
                parse_results = parse_function(active_currencies)
                companies._generate_currency_rates(parse_results)
            except Exception as error:
                if self._context.get('suppress_errors'):
                    _logger.warning(error)
                    _logger.warning('Unable to connect to the online exchange rate platform %s. The web service may be temporarily down. Please try again in a moment.', currency_provider)
                    rslt = False
                elif isinstance(error, UserError):
                    raise error
                else:
                    raise UserError(_('Unable to connect to the online exchange rate platform %s. The web service may be temporarily down. Please try again in a moment.', currency_provider))
        return rslt
