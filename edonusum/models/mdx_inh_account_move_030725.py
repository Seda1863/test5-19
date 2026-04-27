# -*- coding: utf-8 -*-

# TODO: Geliştirmenin son aşamasında, logging_field1, logging_field2 ve logging_field3 alanları kaldırılacak
# TODO: fatura_aciklama sahasına özel karakter kontrolü eklenecek, özel karakter varsa hata mesajı verilecek
# TODO: fatura_no alanı ve uuid dolu ise, fatura gönderme butonu kaldırılacak.

import datetime
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
import xml.etree.ElementTree as ET
import logging

from .mdx_utility_mixin import MdxUtilityMixin

_logger = logging.getLogger(__name__)

class MdxInhAccountMove(models.Model):
    _inherit = 'account.move'

    currency_rate_type = fields.Selection([
        ('forexbuying', 'Döviz Alış'),
        ('forexselling', 'Döviz Satış'),
        ('banknotebuying', 'Efektif Alış'),
        ('banknoteselling', 'Efektif Satış'),
        ('manualexchange', 'Manuel Kur'),
    ], string='Kur Tipi', required=False, copy=False, store=True, default=lambda self: self.env.company.currency_rate_type or 'forexbuying',
        help="Kur tipi seçimi. Varsayılan olarak şirketin varsayılan kur tipini kullanır.")

    # store=True alanlar
    entry_sequence_no = fields.Integer(string='Yevmiye Sıra No', required=False, copy=False, store=True)
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
    uuid = fields.Char(string='UUID', required=False, store=True, copy=False)
    invoice_currency_inverse_rate = fields.Float(
        string='Invoice Currency Inverse Rate',
        # compute='_compute_invoice_currency_inverse_rate',
        store=True,
        copy=False,
        digits=0
    )
    invoice_currency_rate = fields.Float(
        string='Currency Rate',
        compute='_compute_invoice_currency_rate', store=True,
        copy=False,
        digits=0,
        help="Currency rate from company currency to document currency.",
    )
    
    gelen_fatura_id = fields.Many2one('mdx.gelen.fatura', string='Gelen Fatura', required=False, copy=False, readonly=True, store=True)

    # computed alanlar
    filtered_efatura_senaryo_ids = fields.Many2many('mdx.ebelge.senaryo', compute='_compute_filtered_efatura_senaryo_ids', store=False)
    efatura_gonderilebilir = fields.Boolean(string='E-Fatura Gönderilebilir', default=True, required=False, compute='_compute_efatura_gonderilebilir')
    filtered_partner_ids = fields.Many2many('res.partner', compute='_compute_filtered_partner_ids', store=False)

    # store=True yapılacak alanlar
    hesap_virman = fields.Boolean(string='Hesap Virman', default=False, store=True)
    kayit_aciklamasi = fields.Char(string='Kayıt Açıklaması', required=False, store=True)
    fatura_no = fields.Char(string='Fatura No', required=False, copy=False, store=True)
    efatura_turu_id = fields.Many2one('mdx.ebelge.turu', string='E-Fatura Türü', domain=[('active', '=', True), ('belge_cinsi_id.code', '=', 'FATURA')], store=True)
    efatura_senaryo_id = fields.Many2one('mdx.ebelge.senaryo', string='E-Fatura Senaryo', domain="[('id', 'in', filtered_efatura_senaryo_ids)]", required=False, store=True)
    fatura_tipi_id = fields.Many2one('mdx.ebelge.tipi', string='E-Fatura Tipi', domain=[('active', '=', True), ('belge_cinsi_id.code', '=', 'FATURA')], required=False, store=True)
    fatura_alt_tipi_id = fields.Many2one('mdx.fatura.alt.tipi', string='Fatura Alt Tipi', domain=[('active', '=', True)], required=False, store=True)
    fatura_statu_id = fields.Many2one('mdx.sabit.kod', string='Fatura Statüsü', domain=[('liste_id.code', '=', 'GIDENEFTURASTATU')], required=False, store=True)
    fatura_seri_id = fields.Many2one('mdx.fatura.seri', string='Fatura Seri', required=False, copy=False, domain=[('ebelge_turu_id.belge_cinsi_id.code', '=', 'FATURA'), ('active', '=', True)], store=True)
    belge_oid_kod = fields.Char(string='Belge OID Kodu', required=False, copy=False, store=True)
    fatura_gonderim_hata_kodu = fields.Text(string='Fatura Gönderim Hata Kodu', required=False, copy=False, store=True)
    fatura_durum_detay = fields.Text(string='Fatura Durum Detay', required=False, copy=False, store=True)
    fatura_aciklama = fields.Text(string='Fatura Açıklama', required=False, store=True)
    ekli_belge_id = fields.Many2one('ir.attachment', string='Ekli Belge', required=False, copy=False, store=True)
    belge_gonderim_sekli = fields.Selection([('ELEKTRONIK', 'Elektronik'), ('KAĞIT', 'Kağıt'), ], string='Belge Gönderim Şekli', required=False, default='ELEKTRONIK', store=True)
    teslim_sarti_id = fields.Many2one('mdx.sabit.kod', string='Teslim Şartı', domain=[('liste_id.code', '=', 'INCOTERMS')], required=False, store=True)
    gonderim_sekli_id = fields.Many2one('mdx.sabit.kod', string='Gönderim Şekli', domain=[('liste_id.code', '=', 'GONDERIMSEKLI')], required=False, store=True)
    odeme_yontemi_id = fields.Many2one('mdx.sabit.kod', string='Ödeme Yöntemi', domain=[('liste_id.code', '=', 'ODEMEYONTEMI')], required=False, store=True)
    gcb_tescil_no = fields.Char(string='GÇB Tescil No', required=False, store=True)
    gtb_referans_no = fields.Char(string='GTB Referans No', required=False, store=True)
    net_kg = fields.Float(string='Net Kg', required=False, store=True)
    brut_kg = fields.Float(string='Brüt Kg', required=False, store=True)
    bulundugu_kabin_numarasi = fields.Char(string='Bulunduğu Kabın Numarası', required=False, store=True)
    bulundugu_kabin_markasi = fields.Char(string='Bulunduğu Kabın Markası', required=False, store=True)
    bulundugu_kabin_adedi = fields.Integer(string='Bulunduğu Kabın Adedi', required=False, store=True)
    bulundugu_kabin_cinsi_ve_nevi_id = fields.Many2one('mdx.sabit.kod', string='Bulunduğu Kabın Cinsi ve Nevi', domain=[('liste_id.code', '=', 'PAKETKAPCINS')], required=False, store=True)
    fatura_xml = fields.Binary(string='Fatura XML', required=False, store=True)
    xml_ekli_belge_id = fields.Many2one('ir.attachment', string='XML Ekli Belge', required=False, store=True)
    vkn_tckn = fields.Char(string='VKN/TCKN', required=False, store=True)
    move_id = lambda self: self.env['account.move'].search([('id', '=', self.id)], limit=1)

    # logging alanları
    logging_field1 = fields.Text(string='Log1', required=False, copy=False)
    logging_field2 = fields.Text(string='Log2', required=False, copy=False)
    logging_field3 = fields.Text(string='Log3', required=False, copy=False)
    logging_field4 = fields.Text(string='Log4', required=False, copy=False)
    logging_field5 = fields.Text(string='Log5', required=False, copy=False)
    logging_field6 = fields.Text(string='Log6', required=False, copy=False)
    
    @api.depends('move_type')
    def _compute_filtered_partner_ids(self):
        for record in self:
            if record.move_type in ['out_invoice', 'out_refund']:
                record.filtered_partner_ids = self.env['res.partner'].search([('parent_id', '=', False), ('is_customer', '=', True)])
            elif record.move_type in ['in_invoice', 'in_refund']:
                record.filtered_partner_ids = self.env['res.partner'].search([('parent_id', '=', False), ('is_supplier', '=', True)])
            else:
                record.filtered_partner_ids = self.env['res.partner'].search([('parent_id', '=', False)])

    # @api.depends('currency_id')
    # def _compute_invoice_currency_inverse_rate(self):
    #     for move in self:
    #         if move.is_invoice(include_receipts=True):
    #             if move.currency_id:
    #                 move.invoice_currency_inverse_rate = 1 / move.currency_id.rate

    @api.depends('fatura_no', 'uuid', 'state', 'move_type')
    def _compute_efatura_gonderilebilir(self):
        for record in self:
            # record.efatura_gonderilebilir = record.state == 'posted' and record.move_type == 'out_invoice' and ( not record.fatura_no or not record.uuid )
            # record.efatura_gonderilebilir = record.state == 'posted' and ( not record.fatura_no or not record.uuid ) and (record.move_type == 'out_invoice'  or record.move_type == 'in_refund')

            if record.move_type in ['out_invoice', 'in_refund'] and record.state == 'posted':
                if record.fatura_no and record.uuid:
                    record.efatura_gonderilebilir = False
                else:
                    record.efatura_gonderilebilir = True
            else:
                record.efatura_gonderilebilir = False
                    
    @api.depends('efatura_turu_id')
    def _compute_filtered_efatura_senaryo_ids(self):
        for record in self:
            if record.efatura_turu_id:
                record.filtered_efatura_senaryo_ids = self.env['mdx.ebelge.senaryo'].search([
                    ('ebelge_turu_ids', 'in', record.efatura_turu_id.id),
                    ('active', '=', True)
                ])
            else:
                record.filtered_efatura_senaryo_ids = self.env['mdx.ebelge.senaryo'].search([('active', '=', True)])

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            if self.partner_id.parent_id and (self.partner_id.type == 'invoice' or self.partner_id.type == 'delivery'):
                self.efatura_turu_id = self.partner_id.parent_id.efatura_turu_id.id if self.partner_id.parent_id.efatura_turu_id else False
                self.efatura_senaryo_id = self.partner_id.parent_id.efatura_senaryo_id.id if self.partner_id.parent_id.efatura_senaryo_id else False
                self.fatura_tipi_id = self.partner_id.parent_id.fatura_tipi_id.id if self.partner_id.parent_id.fatura_tipi_id else False
                self.fatura_alt_tipi_id = self.partner_id.parent_id.fatura_alt_tipi_id.id if self.partner_id.parent_id.fatura_alt_tipi_id else False
                self.fatura_seri_id = self.env['mdx.fatura.seri'].search([('ebelge_turu_id.code', '=', self.efatura_turu_id.code)], limit=1)
                if self.line_ids:
                    for line in self.line_ids:
                        line.tevkifat_kodu = self.partner_id.parent_id.tevkifat_kodu.id if self.partner_id.parent_id.tevkifat_kodu else False
                        line.istisna_kodu = self.partner_id.parent_id.efatura_turu_id.id if self.partner_id.parent_id.efatura_turu_id else False
                        line.ozel_matrah_kodu = self.partner_id.parent_id.efatura_senaryo_id.id if self.partner_id.parent_id.efatura_senaryo_id else False
                        line.ihrac_kayit_kodu = self.partner_id.parent_id.fatura_tipi_id.id if self.partner_id.parent_id.fatura_tipi_id else False
            else:
                self.efatura_turu_id = self.partner_id.efatura_turu_id.id if self.partner_id.efatura_turu_id else False
                self.efatura_senaryo_id = self.partner_id.efatura_senaryo_id.id if self.partner_id.efatura_senaryo_id else False
                self.fatura_tipi_id = self.partner_id.fatura_tipi_id.id if self.partner_id.fatura_tipi_id else False
                self.fatura_alt_tipi_id = self.partner_id.fatura_alt_tipi_id.id if self.partner_id.fatura_alt_tipi_id else False
                self.fatura_seri_id = self.env['mdx.fatura.seri'].search([('ebelge_turu_id.code', '=', self.efatura_turu_id.code)], limit=1)
                if self.line_ids:
                    for line in self.line_ids:
                        line.tevkifat_kodu = self.partner_id.tevkifat_kodu.id if self.partner_id.tevkifat_kodu else False
                        line.istisna_kodu = self.partner_id.efatura_turu_id.id if self.partner_id.efatura_turu_id else False
                        line.ozel_matrah_kodu = self.partner_id.efatura_senaryo_id.id if self.partner_id.efatura_senaryo_id else False
                        line.ihrac_kayit_kodu = self.partner_id.fatura_tipi_id.id if self.partner_id.fatura_tipi_id else False

    @api.ondelete(at_uninstall=True)
    def _ondelete_invoice(self):
        # 'ondelete' işlemi
        for move in self:
            if move.gelen_fatura_id:
                gelen_fatura = move.gelen_fatura_id
                gelen_fatura.write({
                    'invoice_will_be_created': False,
                    'invoice_created': False,
                    'invoice_creation_date_time': False,
                })

    def unlink(self):
        for move in self:
            if move.fatura_no or move.uuid:
                raise UserError(
                    f'"{move.name}" faturası CTL\'ye gönderildiği için silinemez '
                    f'(Fatura No: {move.fatura_no or "-"}, UUID: {move.uuid or "-"}).\n'
                    f'E-fatura gönderilmiş kayıtlar Odoo üzerinden silinemez.'
                )
        return super().unlink()

    @api.model
    def create(self, vals):
        # Zorunlu alanlar güncellenmiyorsa, ilgili alanları dolduruyoruz
        if vals.get('move_type') in ['out_invoice', 'out_refund', 'in_invoice', 'in_refund']:
            vals['document_type'] = 'invoice'
        if not vals.get('document_number') and 'name' in vals:
            vals['document_number'] = vals.get('name')
        if not vals.get('document_date') and 'invoice_date' in vals:
            vals['document_date'] = vals.get('invoice_date')
        elif not vals.get('document_date') and 'date' in vals:
            vals['document_date'] = vals.get('date')
        # Eğer döviz alanı veya tarih güncellendiyse, kur hesaplamasını da güncelliyoruz
        if vals.get('currency_id') or vals.get('invoice_date') or vals.get('currency_rate_type') or vals.get('invoice_currency_rate'):
            currency = self.env['res.currency'].browse(vals.get('currency_id', self.currency_id.id))
            date = vals.get('invoice_date', self.date) or vals.get('date', self.date)
            rate_obj = self.env['res.currency.rate'].search([
                ('currency_id', '=', currency.id),
                ('name', '=', date)
            ], limit=1)
            # Eğer belirlenen tarihte rate bulunamazsa, o tarihten önceki en yakın tarihi alıyoruz
            if not rate_obj:
                rate_obj = self.env['res.currency.rate'].search([
                    ('currency_id', '=', currency.id),
                    ('name', '<', date)
                ], order='name desc', limit=1)
            rate_type = vals.get('currency_rate_type', self.currency_rate_type) or 'forexbuying'
            rate = 1.0
            if rate_type == 'forexbuying':
                rate = 1 / rate_obj.forex_buying if rate_obj.forex_buying else rate
            elif rate_type == 'forexselling':
                rate = 1 / rate_obj.forex_selling if rate_obj.forex_selling else rate
            elif rate_type == 'banknotebuying':
                rate = 1 / rate_obj.banknote_buying if rate_obj.banknote_buying else rate
            elif rate_type == 'banknoteselling':
                rate = 1 / rate_obj.banknote_selling if rate_obj.banknote_selling else rate
            elif rate_type == 'manualexchange':
                rate = vals.get('invoice_currency_rate', self.invoice_currency_rate) or rate
            vals['invoice_currency_rate'] = rate
            vals['invoice_currency_inverse_rate'] = 1.0 / rate if rate else 0.0
        
        # Partner bilgisi varsa, partner'e göre alanları doldur
        if 'partner_id' in vals:
            partner = self.env['res.partner'].browse(vals['partner_id'])

            if partner:
                if partner.parent_id and (partner.type == 'invoice' or partner.type == 'delivery'):
                    vals = self._update_fields_from_partner(partner.parent_id, vals)
                else:
                    vals = self._update_fields_from_partner(partner, vals)

        if not vals.get('fatura_seri_id') and vals.get('efatura_turu_id'):
            efatura_turu_id = vals['efatura_turu_id']
            efatura_turu = self.env['mdx.ebelge.turu'].browse(efatura_turu_id)  # İlgili kaydı bul
            efatura_turu_code = efatura_turu.code if efatura_turu else None  # Code değerini al

            if efatura_turu_code:
                fatura_seri = self.env['mdx.fatura.seri'].search(
                    [('ebelge_turu_id.code', '=', efatura_turu_code)],
                    limit=1
                )
                if fatura_seri:
                    vals['fatura_seri_id'] = fatura_seri.id
            # TODO: TEST
            if 'move_type' in vals and vals['move_type'] == 'in_refund':
                vals['fatura_tipi_id'] = self.env['mdx.ebelge.tipi'].search([('code', '=', 'IADE')], limit=1).id
                vals['efatura_senaryo_id'] = self.env['mdx.ebelge.senaryo'].search([('code', '=', 'TEMELFATURA')], limit=1).id 

            if not vals.get('document_date'):
                if vals.get('invoice_date'):
                    vals['document_date'] = vals['invoice_date']
                elif 'date' in vals:
                    vals['document_date'] = vals['date']
                else:
                    vals['document_date'] = self and self[0].date or False

            if vals.get('origin_payment_id'):
                payment = self.env['account.payment'].browse(vals['origin_payment_id'])
                if payment.exists():
                    # Ödeme bilgilerini ana kayda aktar
                    vals.update({
                        'currency_rate_type': payment.currency_rate_type,
                        'invoice_currency_inverse_rate': payment.payment_currency_inverse_rate,
                        'invoice_currency_rate': payment.payment_currency_rate,
                    })
                    # Satırları güncelle (invoice_line_ids komut formatında olduğu için işlem yapılmalı)
                    # new_invoice_lines = []
                    # for line_command in vals.get('invoice_line_ids', []):
                    #     # Her bir satır komutunu işle (genellikle (0, 0, {values}) formatında)
                    #     if line_command[0] == 0:  # Yeni satır oluşturma komutu
                    #         line_vals = line_command[2].copy() 
                    #         line_vals.update({
                    #             'currency_rate': payment.payment_currency_rate,
                    #             'debit': line_vals.get('debit', 0.0) * payment.payment_currency_rate,
                    #             'credit': line_vals.get('credit', 0.0) * payment.payment_currency_rate,
                    #         })
                    #         new_invoice_lines.append((0, 0, line_vals))
                    #     else:
                    #         new_invoice_lines.append(line_command)
                    # vals['invoice_line_ids'] = new_invoice_lines  # Güncellenmiş satırları ata

        return super(MdxInhAccountMove, self).create(vals)

    def write(self, vals):
        # Zorunlu alanlar güncellenmiyorsa, ilgili alanları dolduruyoruz
        if vals.get('move_type') in ['out_invoice', 'out_refund', 'in_invoice', 'in_refund']:
            vals['document_type'] = 'invoice'
        if not vals.get('document_number') and 'name' in vals:
            vals['document_number'] = vals.get('name')
        if not vals.get('document_date') and 'invoice_date' in vals:
            vals['document_date'] = vals.get('invoice_date')
        elif not vals.get('document_date') and 'date' in vals:
            vals['document_date'] = vals.get('date')
        # Eğer döviz alanı veya tarih güncellendiyse, kur hesaplamasını da güncelliyoruz
        if vals.get('currency_id') or vals.get('invoice_date') or vals.get('currency_rate_type') or vals.get('invoice_currency_rate'):
            currency = self.env['res.currency'].browse(vals.get('currency_id', self.currency_id.id))
            date = vals.get('invoice_date', self.date) or vals.get('date', self.date)
            rate_obj = self.env['res.currency.rate'].search([
                ('currency_id', '=', currency.id),
                ('name', '=', date)
            ], limit=1)
            # Eğer belirlenen tarihte rate bulunamazsa, o tarihten önceki en yakın tarihi alıyoruz
            if not rate_obj:
                rate_obj = self.env['res.currency.rate'].search([
                    ('currency_id', '=', currency.id),
                    ('name', '<', date)
                ], order='name desc', limit=1)
            rate_type = vals.get('currency_rate_type', self.currency_rate_type) or 'forexbuying'
            rate = 1.0
            if rate_type == 'forexbuying':
                rate = 1 / rate_obj.forex_buying if rate_obj.forex_buying else rate
            elif rate_type == 'forexselling':
                rate = 1 / rate_obj.forex_selling if rate_obj.forex_selling else rate
            elif rate_type == 'banknotebuying':
                rate = 1 / rate_obj.banknote_buying if rate_obj.banknote_buying else rate
            elif rate_type == 'banknoteselling':
                rate = 1 / rate_obj.banknote_selling if rate_obj.banknote_selling else rate
            elif rate_type == 'manualexchange':
                rate = vals.get('invoice_currency_rate', self.invoice_currency_rate) or rate
            vals['invoice_currency_rate'] = rate
            vals['invoice_currency_inverse_rate'] = 1.0 / rate if rate else 0.0
        
        # Partner bilgisi değişmişse, partner'e göre alanları doldur
        if 'partner_id' in vals:
            partner = self.env['res.partner'].browse(vals['partner_id'])
            if partner:
                if partner.parent_id and (partner.type == 'invoice' or partner.type == 'delivery'):
                    vals = self._update_fields_from_partner(partner.parent_id, vals)
                else:
                    vals = self._update_fields_from_partner(partner, vals)

        # TODO: TEST
        if 'efatura_turu_id' in vals:
            efatura_turu_code = self.env['mdx.ebelge.turu'].browse(vals['efatura_turu_id']).code
            if efatura_turu_code != 'EARSIV':
                if 'fatura_no' in vals or 'uuid' in vals:
                    for record in self:
                        record._download_invoice_pdf()

        if not vals.get('document_date'):
            if vals.get('invoice_date'):
                vals['document_date'] = vals['invoice_date']
            elif 'date' in vals:
                vals['document_date'] = vals['date']
            else:
                vals['document_date'] = self and self[0].date or False

        return super(MdxInhAccountMove, self).write(vals)
    
    def action_post(self):
        for record in self:
            message = ""

            # if record.origin_payment_id:
            #     record.currency_rate_type = record.origin_payment_id.currency_rate_type
            #     record.invoice_currency_inverse_rate = record.origin_payment_id.payment_currency_inverse_rate
            #     record.invoice_currency_rate = record.origin_payment_id.payment_currency_rate

            record.invoice_currency_rate = 1 / record.invoice_currency_inverse_rate if record.invoice_currency_inverse_rate else 0.0

            # E-Defter Alan Kontrolleri
            if record.move_type in ['out_invoice', 'out_refund', 'in_invoice', 'in_refund']:
                record.document_type = 'invoice'
            if not record.document_type:
                if record.move_type == 'entry' and record.payment_ids.document_type:
                    record.document_type = record.payment_ids.document_type
                else:
                    if record.company_id.edefter_musterisi:
                        message += "Belge Tipi zorunludur.\n"
            if record.document_type == 'other' and not record.document_type_description_id:
                if record.move_type == 'entry' and record.payment_ids.document_type_description_id:
                    record.document_type_description_id = record.payment_ids.document_type_description_id
                else:
                    if record.company_id.edefter_musterisi:
                        message += "Belge Tipi 'Diğer' ise, Belge Tipi Açıklaması zorunludur.\n"
            if not record.document_number:
                record.document_number = record.name
            if not record.document_date:
                if record.invoice_date:
                    record.document_date = record.invoice_date
                else:
                    record.document_date = record.date

            if record.move_type == 'out_invoice' or record.move_type == 'out_refund':

                # # E-Defter Alan Kontrolleri
                # if not record.payment_method:
                #     message += "Ödeme Yöntemi zorunludur.\n"

                # E-Fatura Alan Kontrolleri
                if record.efatura_senaryo_id.code == 'IHRACAT':
                    if not record.teslim_sarti_id:
                        message += "Teslim Şartı zorunludur.\n"
                    if not record.gonderim_sekli_id:
                        message += "Gönderim Şekli zorunludur.\n"
                    if not record.partner_shipping_id:
                        message += "Teslimat Adresi zorunludur.\n"

                # Fatura Satırları Kod Kontrolleri
                count = 0
                for line in record.invoice_line_ids:
                    count += 1
                    if not line.istisna_kodu and record.fatura_tipi_id.code == 'ISTISNA':
                        message += f"Satır : {count} İstisna Kodu zorunludur.\n"
                    if not line.tevkifat_kodu and record.fatura_tipi_id.code == 'TEVKIFAT':
                        message += f"Satır : {count} Tevkifat Kodu zorunludur.\n"
                    if not line.ozel_matrah_kodu and record.fatura_tipi_id.code == 'OZELMATRAH':
                        message += f"Satır : {count} Özel Matrah Kodu zorunludur.\n"
                    if not line.ihrac_kayit_kodu and record.fatura_tipi_id.code == 'IHRACKAYITLI':
                        message += f"Satır : {count} İhracat Kayıt Kodu zorunludur.\n"
                    if not line.gtip_kodu and record.efatura_senaryo_id.code == 'IHRACAT':
                        message += f"Satır : {count} GTIP Kodu zorunludur.\n"

                    if line.tevkifat_kodu and record.fatura_tipi_id.code == 'TEVKIFAT':
                        if line.tax_ids:
                            for tax in line.tax_ids:
                                if not tax.name.startswith('WH'):
                                    message += f"Satır : {count} Tevkifat Kodu için geçerli vergi kodu bulunamadı.\n"
                                else:
                                    if str(line.tevkifat_kodu.efinans_kod) != "626":
                                        # line.tevkifat_kodu.tevkifat_orani float 0,40 => str "(4/10)" dönüşümü ve vergi adı ile karşılaştırma
                                        f=lambda v:(lambda s,m:f"({m}/{10**len(m)})"if m else f"({s.partition('.')[0]}/1)")(s:=str(v),m:=s.partition('.')[2].rstrip('0'))
                                        frac = f(line.tevkifat_kodu.tevkifat_orani)
                                        if frac not in tax.name:
                                            message += f"Satır : {count} Tevkifat Kodunun oranı ile vergi kodunun oranı uyuşmuyor.\n"
                        else:
                            message += f"Satır : {count} Vergi Kodu zorunludur.\n"

            # record._onchange_invoice_date_currency_id()
            # if record.move_type == 'entry':
            #     if not record.payment_currency_rate:
            #         message += "Kur Oranı hesaplanamadı.\n"    
            
            if message:
                record.state = 'draft'
                raise UserError(message)
                
        result = super(MdxInhAccountMove, self).action_post()

        return result

    def _update_fields_from_partner(self, partner, vals):
        """
        Partner'e göre ilgili alanları güncelleyen yardımcı metod.
        """
        if partner:
            if partner.parent_id and (partner.type == 'invoice' or partner.type == 'delivery'):
                # E-Fatura Türü
                if not vals.get('efatura_turu_id') and partner.parent_id.efatura_turu_id:
                    vals['efatura_turu_id'] = partner.parent_id.efatura_turu_id.id

                # E-Fatura Senaryo
                if not vals.get('efatura_senaryo_id') and partner.parent_id.efatura_senaryo_id:
                    vals['efatura_senaryo_id'] = partner.parent_id.efatura_senaryo_id.id
                # TODO: TEST
                # Fatura Tipi
                if 'move_type' in vals and vals['move_type'] == 'in_refund':
                    vals['fatura_tipi_id'] = self.env['mdx.ebelge.tipi'].search([('code', '=', 'IADE')], limit=1).id
                else:
                    if not vals.get('fatura_tipi_id') and partner.parent_id.fatura_tipi_id:
                        vals['fatura_tipi_id'] = partner.parent_id.fatura_tipi_id.id

                # Fatura Alt Tipi
                if not vals.get('fatura_alt_tipi_id') and partner.parent_id.fatura_alt_tipi_id:
                    vals['fatura_alt_tipi_id'] = partner.parent_id.fatura_alt_tipi_id.id

            else:
                # E-Fatura Türü
                if not vals.get('efatura_turu_id') and partner.efatura_turu_id:
                    vals['efatura_turu_id'] = partner.efatura_turu_id.id

                # E-Fatura Senaryo
                if not vals.get('efatura_senaryo_id') and partner.efatura_senaryo_id:
                    vals['efatura_senaryo_id'] = partner.efatura_senaryo_id.id
                # TODO: TEST
                # Fatura Tipi
                if 'move_type' in vals and vals['move_type'] == 'in_refund':
                    vals['fatura_tipi_id'] = self.env['mdx.ebelge.tipi'].search([('code', '=', 'IADE')], limit=1).id
                else:
                    if not vals.get('fatura_tipi_id') and partner.fatura_tipi_id:
                        vals['fatura_tipi_id'] = partner.fatura_tipi_id.id

                # Fatura Alt Tipi
                if not vals.get('fatura_alt_tipi_id') and partner.fatura_alt_tipi_id:
                    vals['fatura_alt_tipi_id'] = partner.fatura_alt_tipi_id.id

        return vals

    @api.depends('fatura_tipi_id', 'efatura_senaryo_id')
    def _compute_readonly_fields(self):
        """Compute readonly state for fields based on other fields' values."""
        for record in self:
            record.efatura_senaryo_readonly = record.fatura_tipi_id.code in [
                'IADE', 'SGK']
            record.fatura_tipi_readonly = record.efatura_senaryo_id.code in [
                'YOLCUBERABERFATURA', 'IHRACAT']
            
    @api.depends('efatura_turu_id')
    def _compute_filtered_efatura_senaryo_ids(self):
        for record in self:
            if record.efatura_turu_id:
                record.filtered_efatura_senaryo_ids = self.env['mdx.ebelge.senaryo'].search([
                    ('ebelge_turu_ids', 'in', record.efatura_turu_id.id),
                    ('active', '=', True)
                ])
            else:
                record.filtered_efatura_senaryo_ids = self.env['mdx.ebelge.senaryo'].search([
                                                                                            ('active', '=', True)])

    @api.onchange('efatura_senaryo_id')
    def _onchange_efatura_senaryo_id(self):
        if self.efatura_senaryo_id:
            if self.efatura_senaryo_id.code == 'IHRACAT' or self.efatura_senaryo_id.code == 'YOLCUBERABERFATURA':
                self.fatura_tipi_id = self.env['mdx.ebelge.tipi'].search(
                    [('code', '=', 'ISTISNA')], limit=1)
            elif self.efatura_senaryo_id.code == 'ENERJI':
                self.fatura_tipi_id = self.env['mdx.ebelge.tipi'].search(
                    [('code', '=', 'SARJ')], limit=1)
                
    @api.onchange('fatura_tipi_id')
    def _onchange_fatura_tipi_id(self):
        if self.fatura_tipi_id and self.efatura_turu_id.code != 'EARSIV':
            if self.fatura_tipi_id.code == 'IADE' or self.fatura_tipi_id.code == 'SGK':
                self.efatura_senaryo_id = self.env['mdx.ebelge.senaryo'].search(
                    [('code', '=', 'TEMELFATURA')], limit=1)
                
    # account.move action_post metoduna yeni işlem ekle
    # def action_post(self):
    #     for move in self:
    #         if not move.gelen_fatura_id:
    #             self.write({'partner_id': move.partner_id.id, 'efatura_turu_id': move.efatura_turu_id.id})
    #             if move.efatura_turu_id and move.efatura_turu_id.belge_cinsi_id.code == 'FATURA':
    #                 if not move.fatura_no:
    #                     taslak_seri_id = self.env['mdx.fatura.seri'].search([('code', '=', 'FAT')], limit=1)
    #                     if not taslak_seri_id:
    #                         raise UserError("Fatura Seri 'FAT' bulunamadı.")
    #                     else:
    #                         taslak_seri_code = taslak_seri_id.code
    #                         taslak_seri_index = taslak_seri_id.index
    #                         date_today = datetime.date.today()
    #                         date_str = date_today.strftime("%Y-%m-%d")
    #                         taslak_seri_id.write({'index': taslak_seri_index + 1, 'last_used_date': date_today})
    #                         move.name = f"{taslak_seri_code}{date_str.split("-")[0]}{str(taslak_seri_index).zfill(9)}"

    #     result = super(MdxInhAccountMove, self).action_post()

    #     return result

    def action_generate_uuid(self):
        for record in self:
            record.uuid = MdxUtilityMixin.generate_uuid()

    def action_send_einvoice(self):
        """
        Generate XML for the current invoice record.
        """
        try:
            # try:S
            # Assuming `self` contains a single record of `account.move`
            # if len(self) != 1:
            #     raise UserError("Bu işlem yalnızca tek bir fatura üzerinde çalışır.")

            # self.logging_field1 = self.tax_totals
            
            # Generate XML using the utility function
            xml_content = self.env['mdx.utility.mixin'].generate_invoice_xml(self)
            self.logging_field1 = xml_content
            
            # Send the XML to the relevant service
            response = self.env['mdx.utility.mixin'].send_invoice_xml(self, xml_content)
            self.logging_field1 = response

            # # XML yanıtını parse ediyoruz
            # root = ET.fromstring(response)

            # # Namespace tanımları
            # namespace = {'ns2': 'http://service.connector.uut.cs.com.tr/'}

            # # belgeOid elemanını çekiyoruz
            # belge_oid_kod = root.find('.//ns2:belgeGonderExtResponse/belgeOid', namespace)

            # if belge_oid_kod == False:
            #     raise UserError("The 'belgeOid' element could not be found in the response XML.")
            
            # self.logging_field6 = belge_oid_kod.text
            # self.write({'belge_oid_kod': belge_oid_kod.text})
            # self.write({'name': self.fatura_no})
        except Exception as e:
            self.write({'uuid': ''})
            raise UserError(f"API yanıtı alınırken hata oluştu, Lütfen daha sonra tekrar deneyin.\nHata: {str(e)} \nHata Detayı: {str(e.args)}")

    def refresh_api_response(self):
        for record in self:
            if record.belge_oid_kod:
                try:
                    self.env['mdx.utility.mixin'].check_invoice_status(record.belge_oid_kod, self)
                    # XML yanıtını parse ediyoruz
                    # root = ET.fromstring(response)

                    # # XML'deki namespace'i belirliyoruz
                    # namespace = {'ns2': 'http://service.connector.uut.cs.com.tr/'}
                    # result_code = root.find('.//ns2:gidenBelgeDurumSorgulaExtResponse/return/gonderimCevabiKodu', namespace)
                    # if result_code is "1200":
                    #     self.write({'logging_field1': "Fatura başarıyla gönderildi."})

                    self._download_invoice_pdf()
                except Exception as e:
                    raise UserError(f"API yanıtı alınırken hata oluştu, Lütfen daha sonra tekrar deneyin.\nHata: {str(e)}")


    @api.depends('move_type', 'fatura_no', 'uuid', 'state')
    def _download_invoice_pdf(self):
        for record in self:
            try:
                # Koşulları logla
                record.logging_field5 = (
                    f"Checking conditions: move_type={record.move_type}, "
                    f"fatura_no={record.fatura_no}, uuid={record.uuid}, state={record.state}"
                )
                # if record.fatura_no and record.uuid and record.state == 'posted' and record.move_type == 'out_invoice':
                if record.fatura_no and record.uuid and record.state == 'posted':
                    _logger.info("Koşullar sağlandı, PDF oluşturuluyor...")
                    _logger.info(f"Fatura No: {record.fatura_no}, UUID: {record.uuid}, State: {record.state}")
                    # PDF'yi indir
                    attachment_pdf = MdxUtilityMixin.download_document_pdf(
                        record, "FATURA", record.uuid
                    )
                    _logger.info(f"PDF attachment: {attachment_pdf}")
                    if attachment_pdf:
                        record.ekli_belge_id = attachment_pdf.id
                        record.logging_field5 = "PDF başarıyla indirildi ve iliştirildi."
                    else:
                        record.logging_field5 = "PDF indirilemedi: attachment_pdf boş."
                else:
                    record.logging_field5 = "Koşullar sağlanmadı, PDF oluşturulamadı."
            except Exception as e:
                record.logging_field5 = f"PDF oluşturulurken hata: {str(e)}"


    def view_invoice_pdf_on_newtab(self):
        for record in self:
            if record.ekli_belge_id:
                record.logging_field6 = record.ekli_belge_id.mimetype
                return {
                    'type': 'ir.actions.act_url',
                    'url': '/web/content/%s' % record.ekli_belge_id.id,  # `download=true` kaldırıldı
                    'target': 'new',  # Yeni sekmede açılacak
                }
            else:
                raise UserError("Fatura PDF'i bulunamadı.")

    @api.depends('invoice_date', 'currency_id', 'company_id', 'invoice_currency_inverse_rate', 'invoice_currency_rate')
    def _calculate_invoice_currency_rate(self):
        for move in self:
            if move.is_invoice(include_receipts=True):
                if move.currency_id:
                    move.invoice_currency_rate = move.currency_id.rate
                    move.invoice_currency_inverse_rate = 1 / move.currency_id.rate

    # Kur Ayarları
    # @api.onchange('invoice_date', 'currency_id')
    # def _onchange_invoice_date_currency_id(self):
    #     if self.is_invoice(include_receipts=True):
    #         if self.invoice_date and self.currency_id:
    #             # Fatura tarihine göre geçerli olan kuru alıyoruz
    #             rate = self.currency_id.with_context(date=self.invoice_date).rate
    #             # Sıfır bölünmesini önlemek için kontrol
    #             if rate:
    #                 self.invoice_currency_rate = rate
    #                 self.invoice_currency_inverse_rate = 1.0 / rate
    #             else:
    #                 self.invoice_currency_rate = 0.0
    #                 self.invoice_currency_inverse_rate = 0.0

    @api.onchange('invoice_date', 'date', 'currency_id', 'currency_rate_type')
    def _onchange_invoice_date_currency_id(self):
        if self.is_invoice(include_receipts=True):
            if self.invoice_date and self.currency_id and self.currency_id.name != 'TRY':
                # Fatura tarihine göre geçerli olan kuru alıyoruz
                rate_obj = self.env['res.currency.rate'].search([
                    ('currency_id', '=', self.currency_id.id),
                    ('name', '=', self.date)
                ], limit=1)
                # Eğer belirlenen tarihte rate bulunamazsa, o tarihten önceki en yakın tarihi alıyoruz
                if not rate_obj:
                    rate_obj = self.env['res.currency.rate'].search([
                        ('currency_id', '=', self.currency_id.id),
                        ('name', '<', self.invoice_date)
                    ], order='name desc', limit=1)

                if not rate_obj:
                    raise UserError("Kur bilgisi bulunamadı. TCMB'den güncel kur bilgilerini alınız.")

                # Seçilen kur tipine göre ilgili alanı alıyoruz
                if self.currency_rate_type == 'forexbuying':
                    rate = 1 / rate_obj.forex_buying
                elif self.currency_rate_type == 'forexselling':
                    rate = 1 / rate_obj.forex_selling
                elif self.currency_rate_type == 'banknotebuying':
                    rate = 1 / rate_obj.banknote_buying
                elif self.currency_rate_type == 'banknoteselling':
                    rate = 1 / rate_obj.banknote_selling
                elif self.currency_rate_type == 'manualexchange':
                    rate = self.invoice_currency_rate

                # Sıfır bölünmesini önlemek için kontrol
                if rate:
                    self.invoice_currency_rate = rate
                    self.invoice_currency_inverse_rate = 1.0 / rate
                else:
                    self.invoice_currency_rate = 0.0
                    self.invoice_currency_inverse_rate = 0.0
        
        else:
            if not self.payment_ids:
                if self.date and self.currency_id and self.currency_id.name != 'TRY':
                    rate_obj = self.env['res.currency.rate'].search([
                        ('currency_id', '=', self.currency_id.id),
                        ('name', '=', self.date)
                    ], limit=1)
                    # Eğer belirlenen tarihte rate bulunamazsa, o tarihten önceki en yakın tarihi alıyoruz
                    if not rate_obj:
                        rate_obj = self.env['res.currency.rate'].search([
                            ('currency_id', '=', self.currency_id.id),
                            ('name', '<', self.date)
                        ], order='name desc', limit=1)

                    if not rate_obj:
                        raise UserError("Kur bilgisi bulunamadı. TCMB'den güncel kur bilgilerini alınız.")
                    
                    # Seçilen kur tipine göre ilgili alanı alıyoruz
                    if self.currency_rate_type == 'forexbuying':
                        rate = 1 / rate_obj.forex_buying
                    elif self.currency_rate_type == 'forexselling':
                        rate = 1 / rate_obj.forex_selling
                    elif self.currency_rate_type == 'banknotebuying':
                        rate = 1 / rate_obj.banknote_buying
                    elif self.currency_rate_type == 'banknoteselling':
                        rate = 1 / rate_obj.banknote_selling
                    elif self.currency_rate_type == 'manualexchange':
                        rate = self.invoice_currency_rate

                    # Sıfır bölünmesini önlemek için kontrol
                    if rate:
                        self.invoice_currency_rate = rate
                        self.invoice_currency_inverse_rate = 1.0 / rate
                    else:
                        self.invoice_currency_rate = 0.0
                        self.invoice_currency_inverse_rate = 0.0

        for line in self.line_ids:
            line.currency_rate = self.invoice_currency_rate

            if line.debit > 0:
                line.debit = round(abs(line.amount_currency) / line.currency_rate, 2)
            if line.credit > 0:
                line.credit = round(abs(line.amount_currency) / line.currency_rate, 2)

    @api.onchange('invoice_currency_rate')
    def _onchange_invoice_currency_rate(self):
        if self.is_invoice(include_receipts=True):
            if self.invoice_currency_rate:
                self.invoice_currency_inverse_rate = 1.0 / self.invoice_currency_rate

        if self.move_type == 'entry' and not self.payment_ids:
            if self.invoice_currency_rate:
                self.invoice_currency_inverse_rate = 1.0 / self.invoice_currency_rate

        for line in self.line_ids:
            line.currency_rate = self.invoice_currency_rate

            if line.debit > 0:
                line.debit = round(abs(line.amount_currency) / line.currency_rate, 2)
            if line.credit > 0:
                line.credit = round(abs(line.amount_currency) / line.currency_rate, 2)

    @api.onchange('invoice_currency_inverse_rate')
    def _onchange_invoice_currency_inverse_rate(self):
        if self.is_invoice(include_receipts=True):
            if self.invoice_currency_inverse_rate:
                self.invoice_currency_rate = 1.0 / self.invoice_currency_inverse_rate

        if self.move_type == 'entry' and not self.payment_ids:
                if self.invoice_currency_inverse_rate:
                    self.invoice_currency_rate = 1.0 / self.invoice_currency_inverse_rate

        for line in self.line_ids:
            line.currency_rate = self.invoice_currency_rate

            if line.debit > 0:
                line.debit = round(abs(line.amount_currency) / line.currency_rate, 2)
            if line.credit > 0:
                line.credit = round(abs(line.amount_currency) / line.currency_rate, 2)

    @api.depends('currency_id', 'company_currency_id', 'company_id', 'invoice_date', 'date', 'currency_rate_type')
    def _compute_invoice_currency_rate(self):
        for move in self:
            if move.invoice_date and move.currency_id:
                # Fatura tarihine göre geçerli olan kuru alıyoruz
                rate_obj = self.env['res.currency.rate'].search([
                    ('currency_id', '=', self.currency_id.id),
                    ('name', '=', self.date)
                ], limit=1)
                # Eğer belirlenen tarihte rate bulunamazsa, o tarihten önceki en yakın tarihi alıyoruz
                if not rate_obj:
                    rate_obj = self.env['res.currency.rate'].search([
                        ('currency_id', '=', move.currency_id.id),
                        ('name', '<', move.invoice_date)
                    ], order='name desc', limit=1)
                # Seçilen kur tipine göre ilgili alanı alıyoruz
                if move.currency_rate_type == 'forexbuying':
                    rate = 1 / rate_obj.forex_buying
                elif move.currency_rate_type == 'forexselling':
                    rate = 1 / rate_obj.forex_selling
                elif move.currency_rate_type == 'banknotebuying':
                    rate = 1 / rate_obj.banknote_buying
                elif move.currency_rate_type == 'banknoteselling':
                    rate = 1 / rate_obj.banknote_selling
                elif move.currency_rate_type == 'manualexchange':
                    rate = move.invoice_currency_rate
                else:
                    rate = self.env['res.currency']._get_conversion_rate(
                        from_currency=move.company_currency_id,
                        to_currency=move.currency_id,
                        company=move.company_id,
                        date=move.invoice_date or fields.Date.context_today(move),
                    )

                # Sıfır bölünmesini önlemek için kontrol
                if rate:
                    move.invoice_currency_rate = rate
                    move.invoice_currency_inverse_rate = 1.0 / rate
                else:
                    move.invoice_currency_rate = 0.0
                    move.invoice_currency_inverse_rate = 0.0
        
            else:
                if not move.payment_ids:
                    if move.date and move.currency_id:
                        rate_obj = self.env['res.currency.rate'].search([
                            ('currency_id', '=', move.currency_id.id),
                            ('name', '=', move.date)
                        ], limit=1)
                        # Eğer belirlenen tarihte rate bulunamazsa, o tarihten önceki en yakın tarihi alıyoruz
                        if not rate_obj:
                            rate_obj = self.env['res.currency.rate'].search([
                                ('currency_id', '=', move.currency_id.id),
                                ('name', '<', move.date)
                            ], order='name desc', limit=1)
                        # Seçilen kur tipine göre ilgili alanı alıyoruz
                        if move.currency_rate_type == 'forexbuying':
                            rate = 1 / rate_obj.forex_buying
                        elif move.currency_rate_type == 'forexselling':
                            rate = 1 / rate_obj.forex_selling
                        elif move.currency_rate_type == 'banknotebuying':
                            rate = 1 / rate_obj.banknote_buying
                        elif move.currency_rate_type == 'banknoteselling':
                            rate = 1 / rate_obj.banknote_selling
                        elif move.currency_rate_type == 'manualexchange':
                            rate = move.invoice_currency_rate
                        else:
                            rate = self.env['res.currency']._get_conversion_rate(
                                from_currency=move.company_currency_id,
                                to_currency=move.currency_id,
                                company=move.company_id,
                                date=move.invoice_date or fields.Date.context_today(move),
                            )

                        # Sıfır bölünmesini önlemek için kontrol
                        if rate:
                            move.invoice_currency_rate = rate
                            move.invoice_currency_inverse_rate = 1.0 / rate
                        else:
                            move.invoice_currency_rate = 0.0
                            move.invoice_currency_inverse_rate = 0.0

                    

