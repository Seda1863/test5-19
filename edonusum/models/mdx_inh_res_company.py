# -*- coding: utf-8 -*-

import logging
import requests
from dateutil.relativedelta import relativedelta
from lxml import etree
import datetime
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.addons.account.tools import LegacyHTTPAdapter
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class MdxInhResCompany(models.Model):
    _inherit = 'res.company'

    # prozon_workplace_code = fields.Char(string='Prozon İş Yeri Kodu', store=True, help="Prozon API için iş yeri kodu")

    # store=True alanlar
    owner_id = fields.Many2one('res.users', string='Sorumlu Kişi', domain=[('active', '=', True)], store=True)
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
    ], string='Mali Yıl Başlangıç Ayı', required=False, default='01', store=True)
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
    ], string='Mali Yıl Son Ayı', required=False, compute='_compute_fiscal_year_end_month', store=True)
    edefter_musterisi = fields.Boolean(string='E-Defter Kullanıcısı', default=False, store=True)

    # Diğer alanlar
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

    currency_rate_type = fields.Selection([
        ('forexbuying', 'Döviz Alış'),
        ('forexselling', 'Döviz Satış'),
        ('banknotebuying', 'Efektif Alış'),
        ('banknoteselling', 'Efektif Satış'),
        ('manualexchange', 'Manuel Kur'),
    ], string='Kur Tipi', required=False, copy=False, store=True,
    help="Kur tipi seçimi. Faturalarda varsayılan olarak kullanılır.")

    @api.depends('fiscal_year_start_month')
    def _compute_fiscal_year_end_month(self):
        for record in self:
            if record.fiscal_year_start_month:
                month_int = int(record.fiscal_year_start_month)
                if month_int == 1:
                    record.fiscal_year_end_month = '12'
                else:
                    record.fiscal_year_end_month = str(month_int - 1).zfill(2)
            else:
                record.fiscal_year_end_month = False

    def _parse_tcmb_data(self, available_currencies, specific_date=None):
        """TCMB'den belirli tarih için veri çeker"""
        if specific_date:
            date_str = specific_date.strftime("%d%m%Y")
            year_month = specific_date.strftime("%Y%m")
            server_url = f'https://www.tcmb.gov.tr/kurlar/{year_month}/{date_str}.xml'
        else:
            server_url = 'https://www.tcmb.gov.tr/kurlar/today.xml'

        available_currency_names = set(available_currencies.mapped('name'))
        session = requests.Session()
        session.mount('https://', LegacyHTTPAdapter())

        try:
            res = session.get(server_url, timeout=30)
            res.raise_for_status()
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                _logger.warning("TCMB verisi yok: %s", specific_date if specific_date else "bugün")
                return {}
            raise UserError(_("TCMB bağlantı hatası: %s", str(e)))
        except Exception as e:
            raise UserError(_("Genel hata: %s", str(e)))

        try:
            root = etree.fromstring(res.content)
        except etree.XMLSyntaxError as e:
            raise UserError(_("Geçersiz XML yanıtı: %s", str(e)))

        try:
            xml_date = root.attrib['Date']
            parsed_date = datetime.datetime.strptime(xml_date, '%m/%d/%Y')
            adjusted_date = parsed_date + relativedelta(days=1)  # Her zaman +1 gün
            rate_date = fields.Date.to_string(adjusted_date)
        except Exception as e:
            raise UserError(_("Tarih parse hatası: %s", str(e)))

        rslt = {}
        for currency in root.findall('Currency'):
            code = currency.attrib['Kod']
            if code in available_currency_names:
                try:
                    forex_buying = float(currency.find('ForexBuying').text or 0)
                    forex_selling = float(currency.find('ForexSelling').text or 0)
                    banknote_buying = float(currency.find('BanknoteBuying').text or 0)
                    banknote_selling = float(currency.find('BanknoteSelling').text or 0)
                except Exception as e:
                    _logger.error("Kur parse hatası (%s): %s", code, str(e))
                    continue

                if (forex_buying + forex_selling) != 0:
                    rate = 2 / (forex_buying + forex_selling)
                else:
                    rate = 0
                rslt[code] = (rate, forex_buying, forex_selling, banknote_buying, banknote_selling, rate_date)
        rslt['TRY'] = (1.0, 1.0, 1.0, 1.0, 1.0, rate_date)
        _logger.debug("TCMB parse sonuçları: %s", rslt)
        return rslt

    def _fetch_historical_tcmb_rates(self, company, currencies):
        """
        Her para birimi için ayrı ayrı eksik gün kontrolü yapar.
        Eğer o para birimi için belirtilen günde TCMB'den veri çekilemezse o gün atlanır.
        """
        CurrencyRate = self.env['res.currency.rate']
        for currency in currencies:
            # Sadece bu para birimi için mevcut rate kayıtlarını al
            existing_rates = CurrencyRate.search([
                ('company_id', '=', company.id),
                ('currency_id', '=', currency.id)
            ], order='name ASC')
            existing_dates = set()
            for rate in existing_rates:
                # rate.name string ise date'e çevir
                if isinstance(rate.name, str):
                    date_obj = fields.Date.from_string(rate.name)
                else:
                    date_obj = rate.name
                existing_dates.add(date_obj)
            # Eğer hiç kayıt yoksa yılın ilk gününü hedefleyelim
            # if existing_dates:
            #     min_date = min(existing_dates)
            # else:
            # Önceki yılı son gününden itibaren:
            min_date = datetime.date(datetime.date.today().year, 1, 1) - relativedelta(days=7)
            # min_date = datetime.date(2025, 10, 30) # 30.10.2025'ten itibaren
            all_dates = [min_date + timedelta(days=x) for x in range((datetime.date.today() - min_date).days)]
            missing_dates = [d for d in all_dates if d not in existing_dates and d < datetime.date.today()]
            _logger.debug("Eksik tarihler %s için (%s): %s", currency.name, company.name, missing_dates)

            for current_date in missing_dates:
                if current_date.weekday() >= 5:
                    _logger.info("Hafta sonu olduğu için gün atlandı (%s - %s)", currency.name, current_date)
                    continue
                try:
                    # Burada available_currencies parametresini o para birimini içeren recordset olarak gönderiyoruz
                    parse_results = self._parse_tcmb_data(currency, current_date)
                    if parse_results and currency.name in parse_results:
                        # Yalnızca ilgili para birimi için rate kaydı oluştur
                        self._generate_currency_rates_for_date(company, {currency.name: parse_results[currency.name]})
                    else:
                        _logger.info("TCMB verisi mevcut değil (%s) için, gün atlandı: %s", currency.name, current_date)
                except requests.HTTPError as e:
                    if e.response.status_code == 404:
                        _logger.warning("TCMB verisi yok (%s): %s", currency.name, current_date)
                    else:
                        _logger.error("HTTP Hatası (%s - %s): %s", currency.name, current_date, str(e))
                except Exception as e:
                    _logger.error("Genel Hata (%s - %s): %s", currency.name, current_date, str(e))

    def _generate_currency_rates_for_date(self, company, parsed_data):
        """Belirli tarih için kur kaydı oluşturur"""
        CurrencyRate = self.env['res.currency.rate']
        for currency_code, rate_data in parsed_data.items():
            try:
                rate, forex_buying, forex_selling, banknote_buying, banknote_selling, date_rate = rate_data
                currency = self.env['res.currency'].search([('name', '=', currency_code)], limit=1)
                if not currency:
                    _logger.info("Para birimi bulunamadı: %s", currency_code)
                    continue

                existing_rate = CurrencyRate.search([
                    ('currency_id', '=', currency.id),
                    ('name', '=', date_rate),
                    ('company_id', '=', company.id)
                ], limit=1)

                vals = {
                    'currency_id': currency.id,
                    'name': date_rate,
                    'company_id': company.id,
                    'rate': rate,
                    'forex_buying': forex_buying,
                    'forex_selling': forex_selling,
                    'banknote_buying': banknote_buying,
                    'banknote_selling': banknote_selling,
                }

                if existing_rate:
                    existing_rate.write(vals)
                    _logger.debug("Güncellendi: %s için %s", currency_code, date_rate)
                else:
                    CurrencyRate.create(vals)
                    _logger.debug("Oluşturuldu: %s için %s", currency_code, date_rate)
            except Exception as e:
                _logger.error("Kur kaydı oluşturma hatası (%s): %s", currency_code, str(e))

    def _generate_currency_rates(self, parsed_data):
        """Tüm provider'lar için currency rate oluşturur"""
        if self.currency_provider != 'tcmb':
            return super()._generate_currency_rates(parsed_data)

        CurrencyRate = self.env['res.currency.rate']
        for company in self:
            try:
                base_currency = company.currency_id
                if base_currency.name not in parsed_data:
                    raise UserError(_("Ana para birimi (%s) TCMB verilerinde bulunamadı!", base_currency.name))

                base_rate = parsed_data[base_currency.name][0]
                for currency_code, rate_data in parsed_data.items():
                    rate, forex_buying, forex_selling, banknote_buying, banknote_selling, date_rate = rate_data
                    currency = self.env['res.currency'].search([('name', '=', currency_code)], limit=1)
                    if not currency:
                        _logger.info("Para birimi bulunamadı: %s", currency_code)
                        continue

                    existing_rate = CurrencyRate.search([
                        ('currency_id', '=', currency.id),
                        ('name', '=', date_rate),
                        ('company_id', '=', company.id)
                    ], limit=1)

                    vals = {
                        'currency_id': currency.id,
                        'rate': 1 / forex_buying if forex_buying else 0,
                        'name': date_rate,
                        'company_id': company.id,
                        'forex_buying': forex_buying or 0.0,
                        'forex_selling': forex_selling or 0.0,
                        'banknote_buying': banknote_buying or 0.0,
                        'banknote_selling': banknote_selling or 0.0,
                    }

                    if existing_rate:
                        existing_rate.write(vals)
                        _logger.debug("Güncellendi: %s için %s", currency_code, date_rate)
                    else:
                        CurrencyRate.create(vals)
                        _logger.debug("Oluşturuldu: %s için %s", currency_code, date_rate)
            except Exception as e:
                _logger.error("Kur oluşturma hatası (%s): %s", company.name, str(e))

    def update_currency_rates(self):
        """Ana güncelleme metodunu override et"""
        active_currencies = self.env['res.currency'].search([])
        rslt = True

        try:
            for provider, companies in self._group_by_provider().items():
                if provider == 'tcmb':
                    # 1. Her para birimi için eksik tarihleri çek
                    for company in companies:
                        self._fetch_historical_tcmb_rates(company, active_currencies)
                    # 2. Güncel veriyi çek
                    parse_results = self._parse_tcmb_data(active_currencies)
                    if parse_results:
                        companies._generate_currency_rates(parse_results)
                else:
                    # Diğer provider'lar için standart işlem
                    parse_func = getattr(companies, '_parse_%s_data' % provider, None)
                    if parse_func:
                        parse_results = parse_func(active_currencies)
                        companies._generate_currency_rates(parse_results)
        except Exception as e:
            if self._context.get('suppress_errors'):
                _logger.error("Hata bastırıldı: %s", str(e))
                raise UserError(_("Eksik tarihler çekilemedi! Lütfen logları kontrol edin."))
            else:
                raise UserError(_("Kur güncelleme hatası: %s", str(e)))

        return rslt

    def _parse_float(self, value):
        """String'i floata çevir (TCMB formatı için)"""
        try:
            return float(value.replace(',', '.').strip()) if value else 0.0
        except (ValueError, TypeError):
            return 0.0
