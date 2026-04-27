# -*- coding: utf-8 -*-

import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import xml.etree.ElementTree as ET
import logging
from .mdx_utility_mixin import MdxUtilityMixin

_logger = logging.getLogger(__name__)

class MdxInhAccountPayment(models.Model):
    _inherit = 'account.payment'

    payment_type = fields.Selection([
        ('outbound', 'Send'),
        ('inbound', 'Receive'),
    ], string='Payment Type', default='inbound', required=True, tracking=True, copy=False, store=True,
        help="Select 'Send' for vendor payments and 'Receive' for customer payments.")

    payment_method = fields.Selection([
        ('cash', 'Nakit'),
        ('bank', 'Banka'),
        ('credit_card', 'Kredi Kartı'),
        ('check', 'Çek'),
        ('promissory_note', 'Senet'),
    ], string='Ödeme Yöntemi', required=False, copy=False, store=True)
    document_type = fields.Selection([
        ('check', 'Çek'),
        ('invoice', 'Fatura'),
        ('order-customer', 'Müşteri Sipariş Belgesi'),
        ('order-vendor', 'Satıcı Sipariş Belgesi'),
        ('voucher', 'Senet'),
        ('shipment', 'Navlun'),
        ('receipt', 'Makbuz'),
        ('other', 'Diğer'),
    ], string='Belge Tipi', required=False, copy=False, store=True)
    document_type_description_id = fields.Many2one('mdx.edefter.doctype.desc', string='Belge Tipi Açıklaması', required=False, copy=False, store=True)
    document_number = fields.Char(string='Belge No', required=False, copy=False, store=True)
    document_date = fields.Date(string='Belge Tarihi', required=False, copy=False, store=True)

    payment_currency_rate = fields.Float(string="Ödeme Kur Oranı", readonly=False,
        help="Ödeme tarihindeki seçili kur tipine göre hesaplanan döviz kuru", store=True)
    payment_currency_inverse_rate = fields.Float(string="Ödeme Kur Ters Oranı", readonly=False,
        help="Ödeme kur oranının ters değeri", store=True)

    currency_rate_type = fields.Selection([
        ('forexbuying', 'Döviz Alış'),
        ('forexselling', 'Döviz Satış'),
        ('banknotebuying', 'Efektif Alış'),
        ('banknoteselling', 'Efektif Satış'),
        ('manualexchange', 'Manuel Kur'),
    ], string='Kur Tipi', required=False, copy=False, store=True, default=lambda self: self.env.company.currency_rate_type or 'forexbuying',
        help="Kur tipi seçimi. Varsayılan olarak şirketin varsayılan kur tipini kullanır.")

    edefter_musterisi = fields.Boolean(string='e-Defter Müşterisi', related='company_id.edefter_musterisi', readonly=False)

    cheque_leaf_id = fields.Many2one(
        'mdx.cheque.leaf',
        string='Çek Yaprağı',
        domain="[('id', 'in', computed_cheque_leaf_domain)]",
        # related='cheque_leaf_id',
        required=False,
        copy=False,
        store=True,
        help="Çek ödeme türü için seçilen çek yaprağı. Bu alan, ödeme kaydı oluşturulurken kullanılacaktır."
    )

    cheque_leaf_bank = fields.Char(
        string='Çek Banka',
        compute='_compute_cheque_leaf_info',
        store=False,
        help="Seçilen çek yaprağının banka adı."
    )

    cheque_leaf_number = fields.Integer(
        string='Çek Numarası',
        compute='_compute_cheque_leaf_info',
        store=False,
        help="Seçilen çek yaprağının numarası."
    )

    @api.depends('cheque_leaf_id', 'cheque_leaf_id.cheque_number', 'cheque_leaf_id.cheque_book_id', 'cheque_leaf_id.cheque_book_id.bank_name')
    def _compute_cheque_leaf_info(self):
        for record in self:
            if record.cheque_leaf_id:
                record.cheque_leaf_number = record.cheque_leaf_id.cheque_number or 0
                if record.cheque_leaf_id.cheque_book_id:
                    record.cheque_leaf_bank = record.cheque_leaf_id.cheque_book_id.bank_name or ""
                else:
                    record.cheque_leaf_bank = ""
            else:
                record.cheque_leaf_bank = ""
                record.cheque_leaf_number = 0

    computed_cheque_leaf_domain = fields.Many2many(
        'mdx.cheque.leaf',
        compute='_compute_cheque_leaf_domain',
        string='Çek Yaprağı Alanı Domaini',
        store=False,
        help="Çek yaprağı alanı için dinamik domain. Çek yaprakları, seçilen banka ve para birimine göre filtrelenecektir."
    )

    cheque_amount = fields.Monetary(
        string='Çek Tutarı',
        required=False,
        copy=False,
        # readonly=True,
        compute='_compute_cheque_amount',
        store=True,
        help="Çek ödeme türü için çek tutarı. Bu alan, ödeme kaydı oluşturulurken kullanılacaktır.",
        currency_field='currency_id'
    )

    bring_cheque_amount = fields.Boolean(
        string='Çek Tutarını Getir',
        required=False,
        copy=False,
        store=True,
        help="Çek ödeme türü için çek getirme seçeneği. Bu alan, ödeme kaydı oluşturulurken kullanılacaktır."
    )

    expiry_date = fields.Date(
        string='Vade Tarihi',
        required=False,
        copy=False,
        readonly=True,
        compute='_compute_expiry_date',
        store=True,
        help="Çek ödeme türü için vade tarihi. Bu alan, ödeme kaydı oluşturulurken kullanılacaktır."
    )

    difference = fields.Monetary(
        string='Fark Tutarı',
        required=False,
        compute='_compute_difference',
        readonly=True,
        copy=False,
        store=True,
        help="Ödeme kaydı oluşturulurken hesaplanan fark tutarı. Bu alan, ödeme kaydı oluşturulurken kullanılacaktır.",
        currency_field='currency_id'
    )
    warning_message = fields.Text(
        string='Uyarı Mesajı',
        compute='_compute_warning_message',
        store=False,
        help="Ödeme kaydı oluşturulurken oluşabilecek uyarı mesajlarını tutar. Bu alan, ödeme kaydı oluşturulurken kullanılacaktır."
    )

    @api.depends('payment_method')
    def _compute_warning_message(self):
        for record in self:
            message = ""
            if record.payment_method == 'check':
                message = "Yevmiyenin Çek Hesabı Olduğundan Emin Olunuz!\n"

        record.warning_message = message

    @api.depends('amount', 'cheque_leaf_id', 'cheque_leaf_id.amount')
    def _compute_difference(self):
        for record in self:
            if record.cheque_leaf_id and record.bring_cheque_amount and record.cheque_leaf_id.amount and record.amount:
                cheque_amount = 0.0
                cheque_amount = record.cheque_leaf_id.amount
                difference = record.amount - cheque_amount
                record.difference = difference
            else:
                record.difference = 0.0

    @api.onchange('payment_method')
    def _onchange_payment_method(self):
        if self.payment_method == 'check':
            self.document_type = 'other'
            self.document_type_description_id = self.env['mdx.edefter.doctype.desc'].search(
                [('name', '=', 'Çek Bordrosu')],
                limit=1
            ).id or ""

    @api.depends('bring_cheque_amount', 'cheque_leaf_id', 'cheque_leaf_id.amount')
    def _compute_cheque_amount(self):
        for record in self:
            if record.bring_cheque_amount and record.cheque_leaf_id:
                record.cheque_amount = record.cheque_leaf_id.amount
            else:
                record.cheque_amount = 0.0

    @api.depends('cheque_leaf_id', 'cheque_leaf_id.due_date')
    def _compute_expiry_date(self):
        for record in self:
            if record.cheque_leaf_id:
                record.expiry_date = record.cheque_leaf_id.due_date
            else:
                record.expiry_date = False

    @api.onchange('cheque_leaf_id')
    def _onchange_cheque_leaf_id(self):
        for record in self:
            if not record.cheque_leaf_id:
                record.cheque_amount = 0.0
                record.bring_cheque_amount = False
                record.expiry_date = False
                record.currency_id = record.company_id.currency_id
                
                check_leaf_will_unlinked = self.env['mdx.cheque.leaf'].search([
                    ('id', '=', record.cheque_leaf_id.id),
                    ('inbound_payment_id', '=', record.id) if record.payment_type == 'inbound' else ('outbound_payment_id', '=', record.id)
                ], limit=1)

                if check_leaf_will_unlinked:
                    check_leaf_will_unlinked.write({
                        'inbound_payment_id': False if record.payment_type == 'inbound' else check_leaf_will_unlinked.inbound_payment_id.id,
                        'outbound_payment_id': False if record.payment_type == 'outbound' else check_leaf_will_unlinked.outbound_payment_id.id,
                        'cheque_status': self.env['mdx.sabit.kod'].search([('liste_id.code', '=', 'CEKSTATU'), ('code', '=', 'TASLAK')], limit=1).id,
                    })

            if record.cheque_leaf_id and record.cheque_leaf_id.inbound_payment_id and record.payment_type == 'inbound':
                return {'warning': {
                    'title': _("Uyarı"),
                    'message': _("Seçilen çek yaprağı zaten onaylanmış bir müşteri ödemesi tarafından kullanılıyor. Lütfen farklı bir çek yaprağı seçin."),
                }}
            
            if record.cheque_leaf_id and record.cheque_leaf_id.outbound_payment_id and record.payment_type == 'outbound':
                return {'warning': {
                    'title': _("Uyarı"),
                    'message': _("Seçilen çek yaprağı zaten onaylanmış bir tedarikçi ödemesi tarafından kullanılıyor. Lütfen farklı bir çek yaprağı seçin."),
                }}

            # if record.payment_method != 'check':
            #     record.cheque_leaf_id = False
            #     return {'warning': {
            #         'title': _("Uyarı"),
            #         'message': _("Ödeme yöntemi 'Çek' olarak ayarlanmadı. Çek yaprağı seçimi geçersiz."),
            #     }}
            
            if record.state == 'posted':
                return {'warning': {
                    'title': _("Uyarı"),
                    'message': _("Onaylanmış bir ödeme kaydı için çek yaprağı değiştirilemez."),
                }}
            
            if record.cheque_leaf_id:
                record.expiry_date = record.cheque_leaf_id.due_date
                record.currency_id = record.cheque_leaf_id.currency_id
                record.difference = record.amount - record.cheque_leaf_id.amount
            else:
                record.currency_id = record.company_id.currency_id
                record.cheque_amount = 0.0
                record.bring_cheque_amount = False
                record.expiry_date = False

    @api.onchange('date', 'currency_id', 'currency_rate_type')
    def _onchange_date_currency_id(self):
        if self.currency_id:
            date = self.date or fields.Date.today()
            rate_obj = self.currency_id.with_context(date=date)
            # Varsayılan olarak genel rate değeri
            rate = rate_obj.rate  
            if self.currency_rate_type == 'forexbuying':
                rate = 1 / rate_obj.forex_buying if rate_obj.forex_buying else rate
            elif self.currency_rate_type == 'forexselling':
                rate = 1 / rate_obj.forex_selling if rate_obj.forex_selling else rate
            elif self.currency_rate_type == 'banknotebuying':
                rate = 1 / rate_obj.banknote_buying if rate_obj.banknote_buying else rate
            elif self.currency_rate_type == 'banknoteselling':
                rate = 1 / rate_obj.banknote_selling if rate_obj.banknote_selling else rate
            elif self.currency_rate_type == 'manualexchange':
                # Manuel kurda, kullanıcının girdiği değer kullanılsın; eğer yoksa genel rate alınır.
                rate = self.payment_currency_rate or rate

            if rate:
                self.payment_currency_rate = rate
                self.payment_currency_inverse_rate = 1.0 / rate
            else:
                self.payment_currency_rate = 0.0
                self.payment_currency_inverse_rate = 0.0

    @api.onchange('payment_currency_rate')
    def _onchange_payment_currency_rate(self):
        if self.payment_currency_rate:
            self.payment_currency_inverse_rate = 1.0 / self.payment_currency_rate

    @api.onchange('payment_currency_inverse_rate')
    def _onchange_payment_currency_inverse_rate(self):
        if self.payment_currency_inverse_rate:
            self.payment_currency_rate = 1.0 / self.payment_currency_inverse_rate

    @api.model
    def create(self, vals):
        # Zorunlu alanları oluşturma anında dolduruyoruz
        if not vals.get('document_number'):
            move_id = vals.get('move_id')
            vals['document_number'] = vals.get('name') or self.env['account.move'].browse(move_id).name
        if not vals.get('document_date'):
            vals['document_date'] = vals.get('date') or fields.Date.today()
        # İlgili kur hesaplaması için; form üzerinden geçmese de default değerlerin yazılması sağlanır.
        if vals.get('payment_transaction_id'):
            payment_method_code = self.env['payment.transaction'].browse(vals.get('payment_transaction_id')).payment_method_id.code
            if payment_method_code == 'card':
                vals['payment_method'] = 'credit_card'
                vals['document_type'] = 'invoice'

            if not vals.get('document_number'):
                payment_method_reference = self.env['payment.transaction'].browse(vals.get('payment_transaction_id')).reference
                vals['document_number'] = payment_method_reference or vals.get('name') or '/'

        if vals.get('currency_id') and vals.get('date'):
            # Simüle etmek için döviz nesnesini alıp context oluşturuyoruz
            currency = self.env['res.currency'].browse(vals.get('currency_id'))
            date = vals.get('date')
            rate_obj = currency.with_context(date=date)
            rate = rate_obj.rate
            rate_type = vals.get('currency_rate_type', 'forexbuying')
            if rate_type == 'forexbuying':
                rate = 1 / rate_obj.forex_buying if rate_obj.forex_buying else rate
            elif rate_type == 'forexselling':
                rate = 1 / rate_obj.forex_selling if rate_obj.forex_selling else rate
            elif rate_type == 'banknotebuying':
                rate = 1 / rate_obj.banknote_buying if rate_obj.banknote_buying else rate
            elif rate_type == 'banknoteselling':
                rate = 1 / rate_obj.banknote_selling if rate_obj.banknote_selling else rate
            elif rate_type == 'manualexchange':
                rate = vals.get('payment_currency_rate') or rate
            vals['payment_currency_rate'] = rate or 1.0
            vals['payment_currency_inverse_rate'] = 1.0 / rate if rate else 1.0

        return super(MdxInhAccountPayment, self).create(vals)

    def write(self, vals):
        _logger.warning(f"Writing values to account.payment: {vals}")
        # Process each payment record (for multi-record update support)
        for payment in self:
            # Backup current values
            current_move_id = payment.move_id.id if payment.move_id else None
            current_currency_id = payment.currency_id.id
            current_date = payment.date
            current_rate_type = payment.currency_rate_type
            current_rate = payment.payment_currency_rate

            # Fill required fields
            if not vals.get('document_number') and 'name' in vals:
                vals['document_number'] = vals.get('name')
            if not vals.get('document_date') and 'date' in vals:
                vals['document_date'] = vals.get('date')

            # Currency rate update logic
            if any(key in vals for key in ['currency_id', 'date', 'currency_rate_type', 'payment_currency_rate']):
                currency = self.env['res.currency'].browse(vals.get('currency_id', payment.currency_id.id))
                date = vals.get('date', payment.date) or fields.Date.today()
                
                # Rate calculation
                rate_obj = self.env['res.currency.rate'].search([
                    ('currency_id', '=', currency.id),
                    ('name', '<=', date)
                ], order='name desc', limit=1)
                
                rate_type = vals.get('currency_rate_type', payment.currency_rate_type) or 'forexbuying'
                manual_rate = vals.get('payment_currency_rate', payment.payment_currency_rate)
                
                # Automatic/manual rate selection
                if rate_type == 'manualexchange' and manual_rate:
                    new_rate = manual_rate
                else:
                    if rate_type == 'forexbuying':
                        new_rate = 1 / rate_obj.forex_buying if rate_obj and rate_obj.forex_buying else 1.0
                    elif rate_type == 'forexselling':
                        new_rate = 1 / rate_obj.forex_selling if rate_obj and rate_obj.forex_selling else 1.0
                    elif rate_type == 'banknotebuying':
                        new_rate = 1 / rate_obj.banknote_buying if rate_obj and rate_obj.banknote_buying else 1.0
                    elif rate_type == 'banknoteselling':
                        new_rate = 1 / rate_obj.banknote_selling if rate_obj and rate_obj.banknote_selling else 1.0
                    else:
                        new_rate = 1.0

                # Eğer new_rate 0 ise, varsayılan değer olarak 1.0 kullan
                if new_rate == 0:
                    _logger.warning(f"new_rate is 0 for payment {payment.id}, using default value 1.0")
                    new_rate = 1.0

                vals.update({
                    'payment_currency_rate': new_rate,
                    'payment_currency_inverse_rate': 1.0 / new_rate if new_rate else 0.0
                })

            # Check for move and line updates
            if payment.move_id:
                
                # Update move                
                move = payment.move_id
                new_rate_type = vals.get('currency_rate_type', payment.currency_rate_type)
                new_rate = vals.get('payment_currency_rate', payment.payment_currency_rate)
                initial_state = move.state

                # 1. Update move's currency and rate information
                move_vals = {
                    'currency_rate_type': new_rate_type,
                    'invoice_currency_rate': new_rate,
                    'invoice_currency_inverse_rate': 1 / new_rate if new_rate else 0.0,
                    'state': 'draft' if move.state != 'draft' else move.state,
                }
                _logger.warning(f"Updating move {move} with values: {move_vals}")
                move.write(move_vals)

                # 2. Update all move lines - SIFIRA BÖLME HATASI DÜZELTMESİ
                line_updates = []
                for line in move.line_ids:
                    if line.amount_currency:
                        # Calculate new debit/credit based on amount_currency and new rate
                        amount_currency = line.amount_currency
                        # new_rate 0 olmamasını garanti et
                        safe_rate = new_rate if new_rate != 0 else 1.0
                        debit = abs(amount_currency) / safe_rate if amount_currency > 0 else 0.0
                        credit = abs(amount_currency) / safe_rate if amount_currency < 0 else 0.0
                        
                        line_updates.append((1, line.id, {
                            'currency_rate': safe_rate,
                            'debit': round(debit, 2),
                            'credit': round(credit, 2)
                        }))
                    else:
                        # If no amount_currency, just update the currency rate
                        safe_rate = new_rate if new_rate != 0 else 1.0
                        line_updates.append((1, line.id, {
                            'currency_rate': safe_rate
                        }))
                
                # If we have line updates, write them to the move
                if line_updates:
                    _logger.warning(f"Updating move lines for move {payment.move_id} with values: {line_updates}")
                    # Update all lines at once with check_move_validity=False
                    move.with_context(check_move_validity=False).write({
                        'line_ids': line_updates
                    })

                if initial_state != 'draft':
                    move.write({'state': initial_state})  # Restore original state if it was not draft
            
            # Call original write method
            result = super(MdxInhAccountPayment, self).write(vals)
            _logger.warning("Write operation completed successfully")
            return result

    @api.depends('payment_type', 'company_id')
    def _compute_cheque_leaf_domain(self):
        for record in self:
            result = []
            if record.payment_type == 'inbound':
                result = self.env['mdx.cheque.leaf'].search([
                    ('company_id.id', '=', self.env.company.id),
                    ('cheque_book_id', '=', False),
                    ('inbound_payment_id', '=', False),
                    ('active', '=', True),
                ])
            elif record.payment_type == 'outbound':
                result = self.env['mdx.cheque.leaf'].search([
                    ('company_id.id', '=', self.env.company.id),
                    ('outbound_payment_id', '=', False),
                    ('active', '=', True),
                ])

            record.computed_cheque_leaf_domain = result

    def action_draft(self):
        # Çek yaprağı ile ilgili kontrolleri kaldırıyoruz
        if self.cheque_leaf_id:
            cheque_status_code = "TASLAK"

            if self.cheque_leaf_id.inbound_payment_id and self.payment_type == 'inbound':

                self.cheque_leaf_id.write({
                    'issuer_id': False,
                    'inbound_payment_id': False,
                    'cheque_status': self.env['mdx.sabit.kod'].search([('liste_id.code', '=', 'CEKSTATU'), ('code', '=', cheque_status_code)], limit=1).id,
                    'first_owner_id': False if not self.cheque_leaf_id.created_with_cheque_book and self.partner_type == 'customer' else self.cheque_leaf_id.first_owner_id.id,
                })
            if self.cheque_leaf_id.outbound_payment_id and self.payment_type == 'outbound':
                if self.cheque_leaf_id.created_with_cheque_book:
                    cheque_status_code = "CEKOLUSTURULDU"
                else:
                    if self.cheque_leaf_id.issuer_id:
                        cheque_status_code = "PORTFOYDE"

                self.cheque_leaf_id.write({
                    'receiver_id': False,
                    'outbound_payment_id': False,
                    'cheque_status': self.env['mdx.sabit.kod'].search([('liste_id.code', '=', 'CEKSTATU'), ('code', '=', cheque_status_code)], limit=1).id,
                    'first_owner_id': False if not self.cheque_leaf_id.created_with_cheque_book else self.cheque_leaf_id.first_owner_id.id,
                })                

        return super(MdxInhAccountPayment, self).action_draft()

    def action_post(self):
        message = ""
        for record in self:
            # Zorunlu alan kontrolleri
            if not record.document_type and record.edefter_musterisi:
                message += "Belge Tipi zorunludur.\n"
            if record.document_type == 'other' and not record.document_type_description_id and record.edefter_musterisi:
                message += "Belge Tipi 'Diğer' ise, Belge Tipi Açıklaması zorunludur.\n"
            # Ödeme kur oranı kontrolü
            if not record.payment_currency_rate:
                message += "Ödeme Kur Oranı hesaplanamadı.\n"

            # Çek yaprağı kontrolü
            if record.cheque_leaf_id:
                if not record.cheque_leaf_id.amount:
                    message += "Çek yaprağı için geçerli bir tutar bulunamadı.\nLütfen çek yaprağının tutarını kontrol edin.\n"
                if not record.cheque_leaf_id.due_date:
                    message += "Çek yaprağı için vade tarihi belirtilmemiş.\nLütfen çek yaprağının vade tarihini kontrol edin.\n"
                if not record.cheque_leaf_id.currency_id:
                    message += "Çek yaprağı için geçerli bir para birimi bulunamadı.\nLütfen çek yaprağının para birimini kontrol edin.\n"
                if record.currency_id != record.cheque_leaf_id.currency_id:
                    message += "Çek yaprağı ile ödeme para birimleri uyuşmuyor.\nLütfen çek yaprağının para birimini kontrol edin.\n"
                if record.cheque_leaf_id.issuer_id and record.cheque_leaf_id.issuer_id != record.partner_id and record.payment_type == 'inbound':
                    message += "Çek yaprağı için seçilen müşteri ile çek yaprağının 'Çeki Veren / Müşteri' bilgisi uyuşmuyor.\nLütfen müşteri bilgisini kontrol edin.\n"
                # if not record.cheque_leaf_id.issuer_id and not record.cheque_leaf_id.created_with_cheque_book:
                #     message += "Çek yaprağı için 'Çeki Veren / Müşteri' bilgisi boş ve herhangi bir çek defteri ile oluşturulmamış.\nLütfen müşteri bilgisini kontrol edin.\n"
                if record.difference != 0.0 or record.cheque_leaf_id.amount != record.amount or record.amount - record.cheque_leaf_id.amount != 0.0:
                    difference = record.amount - record.cheque_leaf_id.amount
                    record.write({
                        'difference': difference,
                    })
                    message += "Çek tutarı ile ödeme tutarı arasında fark var. Lütfen kontrol edin.\n"
                
                payment_partner = False
                conflicted_payment = False
                if record.payment_type == 'inbound':
                    record.cheque_leaf_id.write({
                        'cheque_status': self.env['mdx.sabit.kod'].search([('liste_id.code', '=', 'CEKSTATU'), ('code', '=', 'PORTFOYDE')], limit=1).id,
                        'inbound_payment_id': record.id if record.payment_type == 'inbound' else False,
                    })
                    conflicted_payment = self.env['account.payment'].search([
                        ('cheque_leaf_id', '=', record.cheque_leaf_id.id),
                        ('payment_type', '=', 'inbound'),
                        ('id', '!=', record.id)
                    ], limit=1)
                    payment_partner = "müşteri"
                elif record.payment_type == 'outbound':
                    if record.cheque_leaf_id.created_with_cheque_book:
                        cheque_status_code = "KESIDE"
                    else:
                        cheque_status_code = "CIROEDILDI"

                    record.cheque_leaf_id.write({
                        'cheque_status': self.env['mdx.sabit.kod'].search([('liste_id.code', '=', 'CEKSTATU'), ('code', '=', cheque_status_code)], limit=1).id,
                        'outbound_payment_id': record.id if record.payment_type == 'outbound' else False,
                    })              
                    conflicted_payment = self.env['account.payment'].search([
                        ('cheque_leaf_id', '=', record.cheque_leaf_id.id),
                        ('payment_type', '=', 'outbound'),
                        ('id', '!=', record.id)
                    ], limit=1)
                    payment_partner = "tedarikçi"

                # conflicted_payment_link = self.env['ir.config_parameter'].sudo().get_param('web.base.url') + '/web#id=%s&model=account.payment&view_type=form' % conflicted_payment.id if conflicted_payment else ''

                if conflicted_payment:
                    if conflicted_payment.state != 'posted':
                        message += "Seçilen çek yaprağı henüz onaylanmamış başka bir " + payment_partner +" ödeme kaydı tarafından kullanılıyor. Lütfen kontrol edin veya farklı bir çek yaprağı seçin.\nÇek yaprağının seçili olduğu ödeme kaydı: %s\n" % (conflicted_payment.name)
                    else:
                        message += "Seçilen çek yaprağı onaylanmış başka bir " + payment_partner +" ödeme kaydı tarafından kullanılıyor. Lütfen kontrol edin veya farklı bir çek yaprağı seçin.\nÇek yaprağının seçili olduğu ödeme kaydı: %s\n" % (conflicted_payment.name)
                    
                
                if record.partner_id:
                    record.cheque_leaf_id.write({
                        'receiver_id': record.partner_id.id if record.partner_type == 'supplier' else False,
                        'issuer_id': record.partner_id.id if record.partner_type == 'customer' else False,
                        'first_owner_id': record.partner_id.id if record.partner_type == 'customer' and not record.cheque_leaf_id.created_with_cheque_book else False,
                    })
                else:
                    if record.payment_type == 'inbound':
                        message += "Çek yaprağı için müşteri seçilmemiş. Lütfen müşteri bilgilerini doldurun.\n"
                    elif record.payment_type == 'outbound':
                        message += "Çek yaprağı için tedarikçi seçilmemiş. Lütfen tedarikçi bilgilerini doldurun.\n"

                if message:
                    record.state = 'draft'
                    raise UserError(message)

        result = super(MdxInhAccountPayment, self).action_post()

        return result

    def button_open_check_leaf(self):
        ''' Redirect the user to the cheque leaf form view. '''

        self.ensure_one()
        return {
            'name': _("Cheque Leaf"),
            'type': 'ir.actions.act_window',
            'res_model': 'mdx.cheque.leaf',
            'context': {'create': False},
            'view_mode': 'form',
            'res_id': self.cheque_leaf_id.id if self.cheque_leaf_id else False,
        }

    @api.depends('move_id.amount_total_signed', 'amount', 'payment_type', 'currency_id', 'date', 'company_id', 'company_currency_id', 'payment_currency_rate')
    def _compute_amount_company_currency_signed(self):
        for payment in self:
            if payment.move_id:
                liquidity_lines = payment._seek_for_lines()[0]
                if liquidity_lines:
                    payment.amount_company_currency_signed = sum(liquidity_lines.mapped('balance'))
                else:
                    if payment.payment_currency_rate:
                        payment.amount_company_currency_signed = payment.amount * payment.payment_currency_rate
                    else:
                        payment.amount_company_currency_signed = payment.currency_id._convert(
                            from_amount=payment.amount,
                            to_currency=payment.company_currency_id,
                            company=payment.company_id,
                            date=payment.date,
                        )
            else:
                if payment.payment_currency_rate:
                    payment.amount_company_currency_signed = payment.amount * payment.payment_currency_rate
                else:
                    payment.amount_company_currency_signed = payment.currency_id._convert(
                        from_amount=payment.amount,
                        to_currency=payment.company_currency_id,
                        company=payment.company_id,
                        date=payment.date,
                    )

    def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
        ''' Prepare the dictionary to create the default account.move.lines for the current payment.
        :param write_off_line_vals: Optional list of dictionaries to create a write-off account.move.line easily containing:
            * amount:       The amount to be added to the counterpart amount.
            * name:         The label to set on the line.
            * account_id:   The account on which create the write-off.
        :param force_balance: Optional balance.
        :return: A list of python dictionary to be passed to the account.move.line's 'create' method.
        '''
        self.ensure_one()
        write_off_line_vals = write_off_line_vals or []

        if not self.outstanding_account_id:
            raise UserError(_(
                "You can't create a new payment without an outstanding payments/receipts account set either on the company or the %(payment_method)s payment method in the %(journal)s journal.",
                payment_method=self.payment_method_line_id.name, journal=self.journal_id.display_name))

        # Compute amounts.
        write_off_line_vals_list = write_off_line_vals or []
        write_off_amount_currency = sum(x['amount_currency'] for x in write_off_line_vals_list)
        write_off_balance = sum(x['balance'] for x in write_off_line_vals_list)

        if self.payment_type == 'inbound':
            # Receive money.
            liquidity_amount_currency = self.amount
        elif self.payment_type == 'outbound':
            # Send money.
            liquidity_amount_currency = -self.amount
        else:
            liquidity_amount_currency = 0.0

        if not write_off_line_vals and force_balance is not None:
            sign = 1 if liquidity_amount_currency > 0 else -1
            liquidity_balance = sign * abs(force_balance)
        else:
            # MANUEL KUR DESTEĞİ EKLENDİ
            if self.payment_currency_rate and self.currency_id != self.company_id.currency_id:
                liquidity_balance = liquidity_amount_currency / self.payment_currency_rate
            else:
                liquidity_balance = self.currency_id._convert(
                    liquidity_amount_currency,
                    self.company_id.currency_id,
                    self.company_id,
                    self.date,
                )

        counterpart_amount_currency = -liquidity_amount_currency - write_off_amount_currency
        counterpart_balance = -liquidity_balance - write_off_balance
        currency_id = self.currency_id.id

        # Compute a default label to set on the journal items.
        liquidity_line_name = ''.join(x[1] for x in self._get_aml_default_display_name_list())
        counterpart_line_name = ''.join(x[1] for x in self._get_aml_default_display_name_list())

        line_vals_list = [
            # Liquidity line.
            {
                'name': liquidity_line_name,
                'date_maturity': self.date,
                'amount_currency': liquidity_amount_currency,
                'currency_id': currency_id,
                'debit': liquidity_balance if liquidity_balance > 0.0 else 0.0,
                'credit': -liquidity_balance if liquidity_balance < 0.0 else 0.0,
                'partner_id': self.partner_id.id,
                'account_id': self.outstanding_account_id.id,
                'currency_rate': self.payment_currency_rate if self.payment_currency_rate else 1.0,  # EKLENDİ
            },
            # Receivable / Payable.
            {
                'name': counterpart_line_name,
                'date_maturity': self.date,
                'amount_currency': counterpart_amount_currency,
                'currency_id': currency_id,
                'debit': counterpart_balance if counterpart_balance > 0.0 else 0.0,
                'credit': -counterpart_balance if counterpart_balance < 0.0 else 0.0,
                'partner_id': self.partner_id.id,
                'account_id': self.destination_account_id.id,
                'currency_rate': self.payment_currency_rate if self.payment_currency_rate else 1.0,  # EKLENDİ
            },
        ]

        # Write-off lines için currency_rate ekle
        for write_off_line in write_off_line_vals_list:
            write_off_line['currency_rate'] = self.payment_currency_rate if self.payment_currency_rate else 1.0

        return line_vals_list + write_off_line_vals_list

class MdxInhAccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = {
            'date': self.payment_date,
            'amount': self.amount,
            'payment_type': self.payment_type,
            'partner_type': self.partner_type,
            'memo': self.communication,
            'journal_id': self.journal_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'partner_id': self.partner_id.id,
            'partner_bank_id': self.partner_bank_id.id,
            'payment_method_line_id': self.payment_method_line_id.id,
            'destination_account_id': self.line_ids[0].account_id.id,
            'write_off_line_vals': [],
            'payment_method': 'bank',
            'document_type': 'other',
            'document_type_description_id': self.env['mdx.edefter.doctype.desc'].search(
                [('name', '=', 'Dekont')],  # Corrected domain: list of tuples
                limit=1
            ).id or "",
            'document_date': self.payment_date,
        }

        if self.payment_difference_handling == 'reconcile':
            if self.early_payment_discount_mode:
                epd_aml_values_list = []
                for aml in batch_result['lines']:
                    if aml.move_id._is_eligible_for_early_payment_discount(self.currency_id, self.payment_date):
                        epd_aml_values_list.append({
                            'aml': aml,
                            'amount_currency': -aml.amount_residual_currency,
                            'balance': aml.currency_id._convert(-aml.amount_residual_currency, aml.company_currency_id, date=self.payment_date),
                        })

                open_amount_currency = self.payment_difference * (-1 if self.payment_type == 'outbound' else 1)
                open_balance = self.currency_id._convert(open_amount_currency, self.company_id.currency_id, self.company_id, self.payment_date)
                early_payment_values = self.env['account.move']._get_invoice_counterpart_amls_for_early_payment_discount(epd_aml_values_list, open_balance)
                for aml_values_list in early_payment_values.values():
                    payment_vals['write_off_line_vals'] += aml_values_list

            elif not self.currency_id.is_zero(self.payment_difference):

                if self.writeoff_is_exchange_account:
                    # Force the rate when computing the 'balance' only when the payment has a foreign currency.
                    # If not, the rate is forced during the reconciliation to put the difference directly on the
                    # exchange difference.
                    if self.currency_id != self.company_currency_id:
                        payment_vals['force_balance'] = sum(batch_result['lines'].mapped('amount_residual'))
                else:
                    if self.payment_type == 'inbound':
                        # Receive money.
                        write_off_amount_currency = self.payment_difference
                    else:  # if self.payment_type == 'outbound':
                        # Send money.
                        write_off_amount_currency = -self.payment_difference

                    payment_vals['write_off_line_vals'].append({
                        'name': self.writeoff_label,
                        'account_id': self.writeoff_account_id.id,
                        'partner_id': self.partner_id.id,
                        'currency_id': self.currency_id.id,
                        'amount_currency': write_off_amount_currency,
                        'balance': self.currency_id._convert(write_off_amount_currency, self.company_id.currency_id, self.company_id, self.payment_date),
                    })

        return payment_vals