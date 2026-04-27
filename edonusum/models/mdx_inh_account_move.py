# -*- coding: utf-8 -*-

import datetime
from odoo import models, fields, api, _
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

    # Dönem Sonu Kapanış etiketleme
    mdx_closing_step = fields.Selection([
        ('yansitma', 'Yansıtma'),
        ('kapanish', 'Kapatma'),
        ('devir', '690 Devir'),
    ], string='Kapanış Adımı', copy=False, store=True, index=True)
    mdx_closing_period = fields.Char(string='Kapanış Dönemi', copy=False, store=True, index=True)

    # computed alanlar
    filtered_efatura_senaryo_ids = fields.Many2many('mdx.ebelge.senaryo', compute='_compute_filtered_efatura_senaryo_ids', store=False)
    efatura_gonderilebilir = fields.Boolean(string='E-Fatura Gönderilebilir', default=True, required=False, compute='_compute_efatura_gonderilebilir', store=True)
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
    # fatura_seri_id = fields.Many2one('mdx.fatura.seri', string='Fatura Seri', required=False, copy=False, domain=[('ebelge_turu_id.belge_cinsi_id.code', '=', 'FATURA'), ('ebelge_turu_id', '=', False), ('active', '=', True)], store=True)
    fatura_seri_id = fields.Many2one('mdx.fatura.seri', string='Fatura Seri', required=False, copy=False, domain=[('ebelge_turu_id.belge_cinsi_id.code', '=', 'FATURA'), ('active', '=', True)], store=True)
    belge_oid_kod = fields.Char(string='Belge OID Kodu', required=False, copy=False, store=True)
    fatura_gonderim_hata_kodu = fields.Text(string='Fatura Gönderim Hata Kodu', required=False, copy=False, store=True)
    fatura_durum_detay = fields.Text(string='Fatura Durum Detay', required=False, copy=False, store=True)
    # fatura_aciklama = fields.Text(string='Fatura Açıklama', required=False, store=True, readonly=False)
    fatura_aciklama = fields.Text(string='Fatura Açıklama', required=False, store=True, readonly=False, compute='_compute_fatura_aciklama', precompute=True, copy=False)
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

    edefter_musterisi = fields.Boolean(string='e-Defter Müşterisi', related='company_id.edefter_musterisi', readonly=False)
    irsaliyesiz_faturalandir = fields.Boolean(string='İrsaliyesiz Faturalandır', readonly=False, store=True, copy=False, default=True)
    mikro_ihracat = fields.Boolean(string='Mikro İhracat', readonly=False, store=True, copy=False, default=False)
    iade_edilen_fatura_no = fields.Char(string='İade Edilen Fatura No', required=False, store=True, copy=False, default=lambda self: self.reversed_entry_id.fatura_no, readonly=False)
    iade_edilen_fatura_tarihi = fields.Date(string='İade Edilen Fatura Tarihi', required=False, store=True, copy=False, default=lambda self: self.reversed_entry_id.invoice_date, readonly=False)

    @api.depends(
        'ref', 
        'state', 
        'partner_id', 
        'invoice_line_ids', 
        # 'picking_ids',  # İrsaliye bağımlılıkları kaldırıldı
        # 'picking_ids.irsaliye_aciklama', 
        # 'picking_ids.irsaliye_no', 
        # 'picking_ids.name',
        'invoice_line_ids.sale_line_ids.order_id.client_order_ref',
        'invoice_line_ids.sale_line_ids.order_id.name',
        'invoice_origin',
        'fatura_aciklama'
    )
    def _compute_fatura_aciklama(self):
        # Ayıraç Tanımı
        SEPARATOR = "*** EK AÇIKLAMALAR ***"

        for record in self:
            # --- 1. SİSTEM METNİ HESAPLAMA ---
            aciklama_satirlari = []
            
            # A. Fatura Ref
            ref_text = record.ref or ""
            if ref_text:
                aciklama_satirlari.append(ref_text)

            # B. Sipariş Bilgileri (Sadece Sipariş Adı ve Müşteri Referansı)
            # Not: İrsaliye mantığı tamamen kaldırıldı.
            orders = record.invoice_line_ids.mapped('sale_line_ids.order_id')
            for order in orders:
                # Sipariş Adı (Örn: SO001)
                if order.name and order.name not in aciklama_satirlari:
                        aciklama_satirlari.append(order.name)
                
                # Müşteri Sipariş Referansı
                if order.client_order_ref:
                    if order.client_order_ref != ref_text and order.client_order_ref not in aciklama_satirlari:
                            aciklama_satirlari.append(order.client_order_ref)

            system_text = "\n".join(aciklama_satirlari)

            # --- 2. MEVCUT VERİYİ ANALİZ ET VE KORU (Aynı Mantık) ---
            current_text = record.fatura_aciklama or ""
            manual_part = ""

            if SEPARATOR in current_text:
                parts = current_text.split(SEPARATOR)
                if len(parts) > 1:
                    manual_part = parts[-1].strip()
            else:
                if current_text.strip() != system_text.strip():
                    clean_current = current_text.replace(system_text, "").strip()
                    clean_current = clean_current.strip(" -")
                    if clean_current:
                        manual_part = clean_current
                    elif current_text and not system_text:
                        manual_part = current_text

            # --- 3. BİRLEŞTİRME VE YAZMA ---
            final_text = system_text
            
            if manual_part:
                prefix = "\n\n" if final_text else ""
                final_text += f"{prefix}{SEPARATOR}\n{manual_part}"

            if record.fatura_aciklama != final_text:
                record.fatura_aciklama = final_text

    def _validate_product_hs_code_required(self):
        if self.env.context.get('skip_gtip_validation'):
            return

        for move in self:
            if not move.is_invoice(include_receipts=True):
                continue

            for l in move.line_ids:
                if not (l.display_type == 'product' or not l.display_type):
                    continue
                if not l.product_id:
                    continue

                # GTIP format kontrolü: 12 haneli, sadece rakam
                if l.gtip_kodu:
                    cleaned = l.gtip_kodu.strip().replace(' ', '').replace('-', '').replace('.', '')
                    if not cleaned.isdigit():
                        raise ValidationError(
                            _("GTIP kodu sadece rakamlardan oluşmalıdır. Hatalı değer: '%s'") % l.gtip_kodu
                        )
                    if len(cleaned) != 12:
                        raise ValidationError(
                            _("GTIP kodu tam olarak 12 haneli olmalıdır. '%s' → %d hane girilmiş.") % (l.gtip_kodu, len(cleaned))
                        )

                # İstisna kodu varsa satırda GTIP zorunlu
                if l.istisna_kodu and not l.gtip_kodu:
                    raise ValidationError(
                        _("Istisna kodu secili satirlarda GTIP Kodu zorunludur (12 haneli rakam). "
                          "Lütfen fatura satırında GTIP kodunu girin.")
                    )

    # GTIP zorunluluk kontrolu artik action_post icinde yapiliyor.
    # Taslak asamasinda GTIP olmadan kaydedilebilir.
    # @api.constrains('move_type', 'line_ids', ...) GTIP icin kaldirildi.

    # @api.depends(
    #     'ref', 
    #     'state', 
    #     'partner_id', 
    #     'invoice_line_ids', 
    #     'picking_ids',      
    #     'picking_ids.irsaliye_aciklama', 
    #     'picking_ids.irsaliye_no', 
    #     'picking_ids.name',
    #     'invoice_line_ids.sale_line_ids.order_id.client_order_ref',
    #     'invoice_line_ids.sale_line_ids.order_id.name',
    #     'invoice_origin',
    #     'fatura_aciklama'
    # )
    # def _compute_fatura_aciklama(self):
    #     # DEĞİŞİKLİK 1: Ayıraç sadeleştirildi (Enter karakterleri kaldırıldı)
    #     SEPARATOR = "*** EK AÇIKLAMALAR ***"

    #     for record in self:
    #         # --- 1. SİSTEM METNİNİ HESAPLA ---
    #         aciklama_satirlari = []
            
    #         # Fatura Ref
    #         ref_text = record.ref or ""
    #         if ref_text:
    #             aciklama_satirlari.append(ref_text)

    #         # İrsaliye Bilgileri
    #         irsaliye_verisi_var = False
    #         if record.picking_ids:
    #             sorted_pickings = record.picking_ids.sorted(key=lambda p: p.name)
    #             for picking in sorted_pickings:
    #                 satir_metni = picking.name or ""
                    
    #                 if picking.irsaliye_no:
    #                     satir_metni += f" ({picking.irsaliye_no})"
                    
    #                 raw_aciklama = picking.irsaliye_aciklama
    #                 if raw_aciklama:
    #                     irsaliye_verisi_var = True
    #                     # Ref Temizliği
    #                     temiz_aciklama = raw_aciklama
    #                     if ref_text and ref_text in raw_aciklama:
    #                         temiz_aciklama = raw_aciklama.replace(ref_text, "").strip()
    #                         temiz_aciklama = temiz_aciklama.strip(" -:")

    #                     if temiz_aciklama:
    #                         satir_metni += f": {temiz_aciklama}"
                    
    #                 if satir_metni not in aciklama_satirlari:
    #                     aciklama_satirlari.append(satir_metni)

    #         # Fallback: Sipariş Verileri
    #         if not irsaliye_verisi_var:
    #             orders = record.invoice_line_ids.mapped('sale_line_ids.order_id')
    #             for order in orders:
    #                 if order.name and order.name not in aciklama_satirlari:
    #                      aciklama_satirlari.append(order.name)
                    
    #                 if order.client_order_ref:
    #                     if order.client_order_ref != ref_text and order.client_order_ref not in aciklama_satirlari:
    #                          aciklama_satirlari.append(order.client_order_ref)

    #         system_text = "\n".join(aciklama_satirlari)

    #         # --- 2. MEVCUT VERİYİ ANALİZ ET ---
    #         current_text = record.fatura_aciklama or ""
    #         manual_part = ""

    #         # DEĞİŞİKLİK 2: Split mantığı güncellendi
    #         if SEPARATOR in current_text:
    #             parts = current_text.split(SEPARATOR)
    #             if len(parts) > 1:
    #                 manual_part = parts[-1].strip()
    #         else:
    #             # Ayraç yoksa ve metin farklıysa manuel not olarak al
    #             if current_text.strip() != system_text.strip():
    #                 clean_current = current_text.replace(system_text, "").strip()
    #                 clean_current = clean_current.strip(" -")
                    
    #                 if clean_current:
    #                     manual_part = clean_current
    #                 elif current_text and not system_text:
    #                     manual_part = current_text

    #         # --- 3. BİRLEŞTİRME ---
    #         final_text = system_text
            
    #         # DEĞİŞİKLİK 3: Sadece manuel not varsa ayıracı ekle
    #         if manual_part:
    #             prefix = "\n\n" if final_text else ""
    #             final_text += f"{prefix}{SEPARATOR}\n{manual_part}"

    #         if record.fatura_aciklama != final_text:
    #             record.fatura_aciklama = final_text

    # 2. TETİKLEYİCİ: Kullanıcı ekrandayken sildiği anda geri gelmesi için
    @api.onchange('fatura_aciklama')
    def _onchange_fatura_aciklama_protection(self):
        """
        Kullanıcı metni elle değiştirdiğinde compute metodunu çalışmaya zorlar.
        Böylece sistem kısmını silerse, compute metodu onu tekrar yerine koyar.
        """
        self._compute_fatura_aciklama()

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

    cheque_status = fields.Many2one(
        'mdx.sabit.kod',
        string='Çek Durumu',
        domain="[('liste_id.code', '=', 'CEKSTATU')]",
        required=False,
        copy=False,
        store=True,
        help="Çek durumunu belirten sabit kod. Bu alan, çek yaprağı durumunu takip etmek ve değiştirmek için kullanılacaktır."
    )

    # logging alanları
    logging_field1 = fields.Text(string='Log1', required=False, copy=False)
    logging_field2 = fields.Text(string='Log2', required=False, copy=False)
    logging_field3 = fields.Text(string='Log3', required=False, copy=False)
    logging_field4 = fields.Text(string='Log4', required=False, copy=False)
    logging_field5 = fields.Text(string='Log5', required=False, copy=False)
    logging_field6 = fields.Text(string='Log6', required=False, copy=False)

    @api.depends('move_type', 'company_id')
    def _compute_cheque_leaf_domain(self):
        for record in self:
            result = []
            if record.move_type == 'entry':
                result = self.env['mdx.cheque.leaf'].search([
                    ('company_id.id', '=', self.env.company.id),
                    # ('account_move_id', '=', False),
                    # ('inbound_payment_id', '=', False),
                    # ('outbound_payment_id', '=', False),
                    ('active', '=', True),
                ])

            record.computed_cheque_leaf_domain = result
    
    @api.depends('amount_total', 'cheque_leaf_id', 'cheque_leaf_id.amount')
    def _compute_difference(self):
        for record in self:
            # Güvenli sayısal değerler: None ise 0.0 olsun
            amt_total = record.amount_total or 0.0
            cheque_amt = record.cheque_leaf_id.amount or 0.0
            # Tek formül: her durumda amt_total - cheque_amt
            record.difference = amt_total - cheque_amt

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
            # if not record.cheque_leaf_id:
            #     record.cheque_amount = 0.0
            #     record.bring_cheque_amount = False
            #     record.expiry_date = False
            #     record.currency_id = record.company_id.currency_id
                
            #     check_leaf_will_unlinked = self.env['mdx.cheque.leaf'].search([
            #         ('id', '=', record.cheque_leaf_id.id),
            #         ('account_move_id', '=', record.id)
            #     ], limit=1)

            #     if check_leaf_will_unlinked:
            #         check_leaf_will_unlinked.write({
            #             'account_move_id': False,
            #             'cheque_status': self.env['mdx.sabit.kod'].search([('liste_id.code', '=', 'CEKSTATU'), ('code', '=', 'TASLAK')], limit=1).id,
            #         })

            # if record.cheque_leaf_id and record.cheque_leaf_id.inbound_payment_id and record.payment_type == 'inbound':
            #     return {'warning': {
            #         'title': _("Uyarı"),
            #         'message': _("Seçilen çek yaprağı zaten onaylanmış bir müşteri ödemesi tarafından kullanılıyor. Lütfen farklı bir çek yaprağı seçin."),
            #     }}
            
            # if record.cheque_leaf_id and record.cheque_leaf_id.outbound_payment_id and record.payment_type == 'outbound':
            #     return {'warning': {
            #         'title': _("Uyarı"),
            #         'message': _("Seçilen çek yaprağı zaten onaylanmış bir tedarikçi ödemesi tarafından kullanılıyor. Lütfen farklı bir çek yaprağı seçin."),
            #     }}

            # if record.payment_method != 'check':
            #     record.cheque_leaf_id = False
            #     return {'warning': {
            #         'title': _("Uyarı"),
            #         'message': _("Ödeme yöntemi 'Çek' olarak ayarlanmadı. Çek yaprağı seçimi geçersiz."),
            #     }}

            # if record.cheque_leaf_id and record.cheque_leaf_id.account_move_id and record.cheque_leaf_id.account_move_id != record:
            #     return {'warning': {
            #         'title': _("Uyarı"),
            #         'message': _("Seçilen çek yaprağı zaten başka bir muhasebe kaydı tarafından kullanılıyor. Lütfen farklı bir çek yaprağı seçin."),
            #     }}
            
            if record.state == 'posted':
                return {'warning': {
                    'title': _("Uyarı"),
                    'message': _("Onaylanmış bir ödeme kaydı için çek yaprağı değiştirilemez."),
                }}
            
            if record.cheque_leaf_id:
                record.expiry_date = record.cheque_leaf_id.due_date
                record.currency_id = record.cheque_leaf_id.currency_id
                record.difference = record.amount_total - record.cheque_leaf_id.amount
                record.cheque_status = record.cheque_leaf_id.cheque_status.id if record.cheque_leaf_id.cheque_status else False

            else:
                record.currency_id = record.company_id.currency_id
                record.cheque_amount = 0.0
                record.bring_cheque_amount = False
                record.expiry_date = False
                record.cheque_status = False


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
                        line.istisna_kodu = self.partner_id.parent_id.istisna_kodu.id if self.partner_id.parent_id.istisna_kodu else False
                        line.ozel_matrah_kodu = self.partner_id.parent_id.ozel_matrah_kodu.id if self.partner_id.parent_id.ozel_matrah_kodu else False
                        line.ihrac_kayit_kodu = self.partner_id.parent_id.ihrac_kayit_kodu.id if self.partner_id.parent_id.ihrac_kayit_kodu else False
                        line._onchange_set_zero_kdv_for_istisna()
            else:
                self.efatura_turu_id = self.partner_id.efatura_turu_id.id if self.partner_id.efatura_turu_id else False
                self.efatura_senaryo_id = self.partner_id.efatura_senaryo_id.id if self.partner_id.efatura_senaryo_id else False
                self.fatura_tipi_id = self.partner_id.fatura_tipi_id.id if self.partner_id.fatura_tipi_id else False
                self.fatura_alt_tipi_id = self.partner_id.fatura_alt_tipi_id.id if self.partner_id.fatura_alt_tipi_id else False
                self.fatura_seri_id = self.env['mdx.fatura.seri'].search([('ebelge_turu_id.code', '=', self.efatura_turu_id.code)], limit=1)
                if self.line_ids:
                    for line in self.line_ids:
                        line.tevkifat_kodu = self.partner_id.tevkifat_kodu.id if self.partner_id.tevkifat_kodu else False
                        line.istisna_kodu = self.partner_id.istisna_kodu.id if self.partner_id.istisna_kodu else False
                        line.ozel_matrah_kodu = self.partner_id.ozel_matrah_kodu.id if self.partner_id.ozel_matrah_kodu else False
                        line.ihrac_kayit_kodu = self.partner_id.ihrac_kayit_kodu.id if self.partner_id.ihrac_kayit_kodu else False
                        line._onchange_set_zero_kdv_for_istisna()

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
            try:
                if rate_type == 'forexbuying':
                    rate = 1 / rate_obj.forex_buying if rate_obj and rate_obj.forex_buying and rate_obj.forex_buying != 0 else 1.0
                elif rate_type == 'forexselling':
                    rate = 1 / rate_obj.forex_selling if rate_obj and rate_obj.forex_selling and rate_obj.forex_selling != 0 else 1.0
                elif rate_type == 'banknotebuying':
                    rate = 1 / rate_obj.banknote_buying if rate_obj and rate_obj.banknote_buying and rate_obj.banknote_buying != 0 else 1.0
                elif rate_type == 'banknoteselling':
                    rate = 1 / rate_obj.banknote_selling if rate_obj and rate_obj.banknote_selling and rate_obj.banknote_selling != 0 else 1.0
                elif rate_type == 'manualexchange':
                    rate = vals.get('invoice_currency_rate', self.invoice_currency_rate) or 1.0
            except ZeroDivisionError:
                rate = 1.0
                _logger.warning(f"Zero division error in create method. Using default rate 1.0")
            # Güvenli değerler: 0 veya None ise 1.0 kullan
            if not rate or rate == 0:
                rate = 1.0
            vals['invoice_currency_rate'] = rate
            vals['invoice_currency_inverse_rate'] = 1.0 / rate if rate and rate != 0 else 1.0

        # Partner bilgisi varsa, partner'e göre alanları doldur
        if 'partner_id' in vals:
            partner = self.env['res.partner'].browse(vals['partner_id'])

            if partner:
                if partner.parent_id and (partner.type == 'invoice' or partner.type == 'delivery'):
                    vals = self._update_fields_from_partner(partner.parent_id, vals)
                else:
                    vals = self._update_fields_from_partner(partner, vals)

        # İade faturası için reversed_entry_id varsa, iade edilen fatura bilgilerini doldur
        if vals.get('reversed_entry_id'):
            reversed_entry = self.env['account.move'].browse(vals['reversed_entry_id'])
            if reversed_entry:
                if not vals.get('iade_edilen_fatura_no') and reversed_entry.fatura_no:
                    vals['iade_edilen_fatura_no'] = reversed_entry.fatura_no
                if not vals.get('iade_edilen_fatura_tarihi') and reversed_entry.invoice_date:
                    vals['iade_edilen_fatura_tarihi'] = reversed_entry.invoice_date

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
                # E-Fatura Senaryo: EFATURA -> TEMELFATURA, EARSIV -> EARSIVFATURA
                efatura_turu_id = vals.get('efatura_turu_id')
                if efatura_turu_id:
                    efatura_turu = self.env['mdx.ebelge.turu'].browse(efatura_turu_id)
                    if efatura_turu.code == 'EFATURA':
                        vals['efatura_senaryo_id'] = self.env['mdx.ebelge.senaryo'].search([('code', '=', 'TEMELFATURA')], limit=1).id
                    elif efatura_turu.code == 'EARSIV':
                        vals['efatura_senaryo_id'] = self.env['mdx.ebelge.senaryo'].search([('code', '=', 'EARSIVFATURA')], limit=1).id

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
                    # vals['invoice_line_ids'] = new_invoice_lines  # Güncellenmiş satırları ata,

            # if vals.get('cheque_status') and vals.get('cheque_leaf_id'):
                # cheque_leaf_record = self.env['mdx.cheque.leaf'].browse(vals['cheque_leaf_id'])
                # if cheque_leaf_record and cheque_leaf_record.account_move_id and cheque_leaf_record.account_move_id != self:
                #     return {'warning': {
                #         'title': _("Uyarı"),
                #         'message': _("Seçilen çek yaprağı zaten başka bir muhasebe kaydı tarafından kullanılıyor. Lütfen farklı bir çek yaprağı seçin."),
                #     }}
                # cheque_status = self.env['mdx.sabit.kod'].browse(vals['cheque_status'])
                # cheque_leaf_id = self.env['mdx.cheque.leaf'].browse(vals['cheque_leaf_id'])
                # if cheque_status.code != cheque_leaf_id.cheque_status.code:
                #     cheque_leaf_id.write({
                #         'cheque_status': cheque_status.id,
                        # 'account_move_id': self.id,
                    # })

        move = super(MdxInhAccountMove, self).create(vals)
        # GTIP validasyonu artık sadece action_post'ta yapılıyor.
        # Taslak aşamasında GTIP olmadan kaydedilebilir.
        return move

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
            try:
                if rate_type == 'forexbuying':
                    rate = 1 / rate_obj.forex_buying if rate_obj and rate_obj.forex_buying and rate_obj.forex_buying != 0 else 1.0
                elif rate_type == 'forexselling':
                    rate = 1 / rate_obj.forex_selling if rate_obj and rate_obj.forex_selling and rate_obj.forex_selling != 0 else 1.0
                elif rate_type == 'banknotebuying':
                    rate = 1 / rate_obj.banknote_buying if rate_obj and rate_obj.banknote_buying and rate_obj.banknote_buying != 0 else 1.0
                elif rate_type == 'banknoteselling':
                    rate = 1 / rate_obj.banknote_selling if rate_obj and rate_obj.banknote_selling and rate_obj.banknote_selling != 0 else 1.0
                elif rate_type == 'manualexchange':
                    rate = vals.get('invoice_currency_rate', self.invoice_currency_rate) or 1.0
            except ZeroDivisionError:
                rate = 1.0
                _logger.warning(f"Zero division error in write method. Using default rate 1.0")
            # Güvenli değerler: 0 veya None ise 1.0 kullan
            if not rate or rate == 0:
                rate = 1.0
            vals['invoice_currency_rate'] = rate
            vals['invoice_currency_inverse_rate'] = 1.0 / rate if rate and rate != 0 else 1.0
        
        # Partner bilgisi değişmişse, partner'e göre alanları doldur
        if 'partner_id' in vals:
            partner = self.env['res.partner'].browse(vals['partner_id'])
            if partner:
                if partner.parent_id and (partner.type == 'invoice' or partner.type == 'delivery'):
                    vals = self._update_fields_from_partner(partner.parent_id, vals)
                else:
                    vals = self._update_fields_from_partner(partner, vals)

        # İade faturası için fatura tipi ve senaryo ayarla
        if 'move_type' in vals and vals['move_type'] == 'in_refund':
            vals['fatura_tipi_id'] = self.env['mdx.ebelge.tipi'].search([('code', '=', 'IADE')], limit=1).id
            # E-Fatura Senaryo: EFATURA -> TEMELFATURA, EARSIV -> EARSIVFATURA
            efatura_turu_id = vals.get('efatura_turu_id')
            if efatura_turu_id:
                efatura_turu = self.env['mdx.ebelge.turu'].browse(efatura_turu_id)
                if efatura_turu.code == 'EFATURA':
                    vals['efatura_senaryo_id'] = self.env['mdx.ebelge.senaryo'].search([('code', '=', 'TEMELFATURA')], limit=1).id
                elif efatura_turu.code == 'EARSIV':
                    vals['efatura_senaryo_id'] = self.env['mdx.ebelge.senaryo'].search([('code', '=', 'EARSIVFATURA')], limit=1).id
            else:
                # Mevcut kayıttan efatura_turu_id al
                for record in self:
                    if record.efatura_turu_id:
                        if record.efatura_turu_id.code == 'EFATURA':
                            vals['efatura_senaryo_id'] = self.env['mdx.ebelge.senaryo'].search([('code', '=', 'TEMELFATURA')], limit=1).id
                        elif record.efatura_turu_id.code == 'EARSIV':
                            vals['efatura_senaryo_id'] = self.env['mdx.ebelge.senaryo'].search([('code', '=', 'EARSIVFATURA')], limit=1).id
                        break

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

        result = super(MdxInhAccountMove, self).write(vals)
        # GTIP validasyonu artık sadece action_post'ta yapılıyor.
        # Taslak aşamasında GTIP olmadan kaydedilebilir.
        return result
    
    def button_draft(self):
        for record in self:
            if record.cheque_leaf_id:
                cheque_status_code = ""
                if record.cheque_leaf_id.outbound_payment_id:
                    if record.cheque_leaf_id.created_with_cheque_book:
                        cheque_status_code = "KESIDE"
                    else:
                        cheque_status_code = "CIROEDILDI"
                else:
                    if record.cheque_leaf_id.inbound_payment_id:
                        cheque_status_code = "PORTFOYDE"

                # Çek yaprağı durumunu 'Taslak' olarak güncelle
                record.cheque_leaf_id.write({
                    'cheque_status': self.env['mdx.sabit.kod'].search([('liste_id.code', '=', 'CEKSTATU'), ('code', '=', cheque_status_code)], limit=1).id,
                    # 'account_move_id': False,  # Çek yaprağını kayıttan ayır
                })
                record.cheque_status = self.env['mdx.sabit.kod'].search([('liste_id.code', '=', 'CEKSTATU'), ('code', '=', cheque_status_code)], limit=1).id

        return super(MdxInhAccountMove, self).button_draft()
    
    def action_post(self):

        for record in self:
            message = ""

            # if record.origin_payment_id:
            #     record.currency_rate_type = record.origin_payment_id.currency_rate_type
            #     record.invoice_currency_inverse_rate = record.origin_payment_id.payment_currency_inverse_rate
            #     record.invoice_currency_rate = record.origin_payment_id.payment_currency_rate

            # Güvenli oran: invoice_currency_inverse_rate 0 veya None ise 1.0 kullan
            safe_inverse = record.invoice_currency_inverse_rate if record.invoice_currency_inverse_rate else 1.0
            record.invoice_currency_rate = 1 / safe_inverse if safe_inverse else 1.0

            # E-Defter Alan Kontrolleri
            # Odeme Yontemi ve Belge Tipi zorunludur (tum kayit tipleri icin)
            if record.move_type in ['in_invoice', 'in_refund']:
                if not record.document_type:
                    record.document_type = 'invoice'
            if not record.document_type:
                if record.move_type == 'entry' and record.payment_ids.document_type:
                    record.document_type = record.payment_ids.document_type
                else:
                    message += "Belge Tipi zorunludur.\n"
            if not record.payment_method:
                if record.move_type == 'entry' and record.payment_ids and hasattr(record.payment_ids, 'payment_method') and record.payment_ids.payment_method:
                    record.payment_method = record.payment_ids.payment_method
                else:
                    message += "Ödeme Yöntemi zorunludur.\n"
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

                # E-Defter Alan Kontrolleri - Musteri Faturalari ve iadeler icin artik zorunlu degil
                # Kullanici bu alanlari doldurmak zorunda degil

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

            # GTIP Kodu Kontrolu - TUM fatura tipleri icin
            if record.is_invoice(include_receipts=True):
                gtip_count = 0
                for line in record.invoice_line_ids:
                    gtip_count += 1
                    if not line.product_id:
                        continue

                    # GTIP format kontrolü: girilmişse 12 haneli rakam olmalı
                    if line.gtip_kodu:
                        cleaned = line.gtip_kodu.strip().replace(' ', '').replace('-', '').replace('.', '')
                        if not cleaned.isdigit():
                            message += f"Satır : {gtip_count} GTIP kodu sadece rakamlardan oluşmalıdır. Hatalı: '{line.gtip_kodu}'\n"
                        elif len(cleaned) != 12:
                            message += f"Satır : {gtip_count} GTIP kodu 12 haneli olmalıdır. Girilen: {len(cleaned)} hane.\n"

                    # İstisna kodu varsa satırda GTIP zorunlu (ürün kartından otomatik gelmeli veya elle girilmeli)
                    if line.istisna_kodu and not line.gtip_kodu:
                        message += f"Satır : {gtip_count} istisna kaydı olan üründe GTIP Kodu zorunludur (12 haneli rakam).\n"

            if record.cheque_leaf_id:
                # conflicted_account_move = self.env['account.move'].search([
                #     ('id', '!=', record.id),
                #     ('cheque_leaf_id', '=', record.cheque_leaf_id.id),
                # ], limit=1)

                # if conflicted_account_move:
                #     if conflicted_account_move.state == 'posted':
                #         message += "Seçilen çek yaprağı onaylanmış bir muhasebe kaydı tarafından kullanılıyor. Lütfen farklı bir çek yaprağı seçin.\n"
                #     elif conflicted_account_move.state == 'draft':
                #         message += "Seçilen çek yaprağı taslak bir muhasebe kaydı tarafından kullanılıyor. Lütfen farklı bir çek yaprağı seçin.\n"
                
                record.cheque_leaf_id.write({
                    'cheque_status': record.cheque_status.id,
                    # 'account_move_id': record.id,
                })
            else:
                if record.payment_method == 'check':
                    message += "Çek yaprağı seçilmedi. Lütfen bir çek yaprağı seçin.\n"
                record.cheque_amount = 0.0
                record.bring_cheque_amount = False
                record.expiry_date = False
                record.cheque_status = False

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
            # kaydın partner_id'si partner.commercial_partner_id olarak ayarlanacak
            vals['partner_id'] = partner.commercial_partner_id.id
            
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
                    # E-Fatura Senaryo: EFATURA -> TEMELFATURA, EARSIV -> EARSIVFATURA
                    efatura_turu_id = vals.get('efatura_turu_id') or (partner.parent_id.efatura_turu_id.id if partner.parent_id.efatura_turu_id else False)
                    if efatura_turu_id:
                        efatura_turu = self.env['mdx.ebelge.turu'].browse(efatura_turu_id)
                        if efatura_turu.code == 'EFATURA':
                            vals['efatura_senaryo_id'] = self.env['mdx.ebelge.senaryo'].search([('code', '=', 'TEMELFATURA')], limit=1).id
                        elif efatura_turu.code == 'EARSIV':
                            vals['efatura_senaryo_id'] = self.env['mdx.ebelge.senaryo'].search([('code', '=', 'EARSIVFATURA')], limit=1).id
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
                    # E-Fatura Senaryo: EFATURA -> TEMELFATURA, EARSIV -> EARSIVFATURA
                    efatura_turu_id = vals.get('efatura_turu_id') or (partner.efatura_turu_id.id if partner.efatura_turu_id else False)
                    if efatura_turu_id:
                        efatura_turu = self.env['mdx.ebelge.turu'].browse(efatura_turu_id)
                        if efatura_turu.code == 'EFATURA':
                            vals['efatura_senaryo_id'] = self.env['mdx.ebelge.senaryo'].search([('code', '=', 'TEMELFATURA')], limit=1).id
                        elif efatura_turu.code == 'EARSIV':
                            vals['efatura_senaryo_id'] = self.env['mdx.ebelge.senaryo'].search([('code', '=', 'EARSIVFATURA')], limit=1).id
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
        # Müşteri faturası ve iadeler için zorunlu alan kontrolleri
        if self.move_type in ('out_invoice', 'out_refund'):
            errors = []
            if not self.payment_method:
                errors.append("Ödeme Yöntemi zorunludur.")
            if not self.document_type:
                errors.append("Belge Tipi (E-Defter) zorunludur.")
            if errors:
                raise UserError("\n".join(errors))

        # try:
            # try:S
            # Assuming `self` contains a single record of `account.move`
            # if len(self) != 1:
            #     raise UserError("Bu işlem yalnızca tek bir fatura üzerinde çalışır.")

            # self.logging_field1 = self.tax_totals
            
            # Generate XML using the utility function
        sale_order_lines = self.invoice_line_ids.mapped('sale_line_ids')

        pickings = self.picking_ids.filtered(lambda p: p.state == 'done' and p.invoice_ids in [self])

        if sale_order_lines and not pickings:
            
            moves = sale_order_lines.mapped('move_ids').filtered(lambda m: m.state == 'done')

            pickings = moves.mapped('picking_id')

        if pickings:
            for picking_id in pickings:
                if not picking_id.irsaliye_no and self.irsaliyesiz_faturalandir == False:
                    raise UserError(
                        f"{picking_id.name} teslimatı için e-iraliye gönderilmemiş! Lütfen önce irsaliye gönderimini yapın."
                    )

        try:
            xml_content = self.env['mdx.utility.mixin'].generate_invoice_xml(self)
            self.logging_field6 = xml_content
        except Exception as e:
            self.write({'uuid': ''})
            raise UserError(f"XML oluşturulurken hata oluştu.\nHata: {str(e)} \nHata Detayı: {str(e.args)}")
        
        try:
            # Send the XML to the relevant service
            response = self.env['mdx.utility.mixin'].send_invoice_xml(self, xml_content)
            self.logging_field1 = response
        except Exception as e:
            self.write({'uuid': ''})
            raise UserError(f"XML gönderilirken hata oluştu.\nHata: {str(e)} \nHata Detayı: {str(e.args)}")

            # self.refresh_api_response()
            # self._download_invoice_pdf()

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
        # except Exception as e:
        #     self.write({'uuid': ''})
        #     raise UserError(f"API yanıtı alınırken hata oluştu, Lütfen daha sonra tekrar deneyin.\nHata: {str(e)} \nHata Detayı: {str(e.args)}")

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
            if self.invoice_date and self.currency_id and self.currency_id != self.company_currency_id:
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
                rate = 1.0
                try:
                    if self.currency_rate_type == 'forexbuying':
                        rate = 1 / rate_obj.forex_buying if rate_obj.forex_buying and rate_obj.forex_buying != 0 else 1.0
                    elif self.currency_rate_type == 'forexselling':
                        rate = 1 / rate_obj.forex_selling if rate_obj.forex_selling and rate_obj.forex_selling != 0 else 1.0
                    elif self.currency_rate_type == 'banknotebuying':
                        rate = 1 / rate_obj.banknote_buying if rate_obj.banknote_buying and rate_obj.banknote_buying != 0 else 1.0
                    elif self.currency_rate_type == 'banknoteselling':
                        rate = 1 / rate_obj.banknote_selling if rate_obj.banknote_selling and rate_obj.banknote_selling != 0 else 1.0
                    elif self.currency_rate_type == 'manualexchange':
                        rate = self.invoice_currency_rate if self.invoice_currency_rate else 1.0
                except ZeroDivisionError:
                    rate = 1.0
                    _logger.warning(f"Zero division error in currency rate calculation for move {self.id}. Using default rate 1.0")

                # Sıfır bölünmesini önlemek için kontrol
                if rate and rate != 0:
                    self.invoice_currency_rate = rate
                    self.invoice_currency_inverse_rate = 1.0 / rate
                else:
                    self.invoice_currency_rate = 1.0
                    self.invoice_currency_inverse_rate = 1.0
            
            else:
                # Aynı para birimi veya para birimi belirtilmemişse
                self.invoice_currency_rate = 1.0
                self.invoice_currency_inverse_rate = 1.0

        else:
            if not self.payment_ids:
                if self.date and self.currency_id and self.currency_id != self.company_currency_id:
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
                    rate = 1.0
                    try:
                        if self.currency_rate_type == 'forexbuying':
                            rate = 1 / rate_obj.forex_buying if rate_obj.forex_buying and rate_obj.forex_buying != 0 else 1.0
                        elif self.currency_rate_type == 'forexselling':
                            rate = 1 / rate_obj.forex_selling if rate_obj.forex_selling and rate_obj.forex_selling != 0 else 1.0
                        elif self.currency_rate_type == 'banknotebuying':
                            rate = 1 / rate_obj.banknote_buying if rate_obj.banknote_buying and rate_obj.banknote_buying != 0 else 1.0
                        elif self.currency_rate_type == 'banknoteselling':
                            rate = 1 / rate_obj.banknote_selling if rate_obj.banknote_selling and rate_obj.banknote_selling != 0 else 1.0
                        elif self.currency_rate_type == 'manualexchange':
                            rate = self.invoice_currency_rate if self.invoice_currency_rate else 1.0
                    except ZeroDivisionError:
                        rate = 1.0
                        _logger.warning(f"Zero division error in currency rate calculation for move {self.id}. Using default rate 1.0")

                    # Sıfır bölünmesini önlemek için kontrol
                    if rate and rate != 0:
                        self.invoice_currency_rate = rate
                        self.invoice_currency_inverse_rate = 1.0 / rate
                    else:
                        self.invoice_currency_rate = 1.0
                        self.invoice_currency_inverse_rate = 1.0
                else:
                    # Aynı para birimi veya para birimi belirtilmemişse
                    self.invoice_currency_rate = 1.0
                    self.invoice_currency_inverse_rate = 1.0

        # Satırları güncelle
        for line in self.line_ids:
            line.currency_rate = self.invoice_currency_rate

            if line.debit > 0:
                line.debit = round(abs(line.amount_currency) / line.currency_rate, 2) if line.currency_rate and line.currency_rate != 0 else abs(line.amount_currency)
            if line.credit > 0:
                line.credit = round(abs(line.amount_currency) / line.currency_rate, 2) if line.currency_rate and line.currency_rate != 0 else abs(line.amount_currency)

    @api.onchange('invoice_currency_rate')
    def _onchange_invoice_currency_rate(self):
        if self.is_invoice(include_receipts=True):
            if self.invoice_currency_rate and self.invoice_currency_rate != 0:
                self.invoice_currency_inverse_rate = 1.0 / self.invoice_currency_rate
            else:
                self.invoice_currency_inverse_rate = 1.0

        if self.move_type == 'entry' and not self.payment_ids:
            if self.invoice_currency_rate and self.invoice_currency_rate != 0:
                self.invoice_currency_inverse_rate = 1.0 / self.invoice_currency_rate
            else:
                self.invoice_currency_inverse_rate = 1.0

        for line in self.line_ids:
            line.currency_rate = self.invoice_currency_rate

            if line.debit > 0:
                line.debit = round(abs(line.amount_currency) / line.currency_rate, 2) if line.currency_rate and line.currency_rate != 0 else abs(line.amount_currency)
            if line.credit > 0:
                line.credit = round(abs(line.amount_currency) / line.currency_rate, 2) if line.currency_rate and line.currency_rate != 0 else abs(line.amount_currency)

    @api.onchange('invoice_currency_inverse_rate')
    def _onchange_invoice_currency_inverse_rate(self):
        if self.is_invoice(include_receipts=True):
            if self.invoice_currency_inverse_rate and self.invoice_currency_inverse_rate != 0:
                self.invoice_currency_rate = 1.0 / self.invoice_currency_inverse_rate
            else:
                self.invoice_currency_rate = 1.0

        if self.move_type == 'entry' and not self.payment_ids:
            if self.invoice_currency_inverse_rate and self.invoice_currency_inverse_rate != 0:
                self.invoice_currency_rate = 1.0 / self.invoice_currency_inverse_rate
            else:
                self.invoice_currency_rate = 1.0

        for line in self.line_ids:
            line.currency_rate = self.invoice_currency_rate

            if line.debit > 0:
                line.debit = round(abs(line.amount_currency) / line.currency_rate, 2) if line.currency_rate and line.currency_rate != 0 else abs(line.amount_currency)
            if line.credit > 0:
                line.credit = round(abs(line.amount_currency) / line.currency_rate, 2) if line.currency_rate and line.currency_rate != 0 else abs(line.amount_currency)

    @api.depends('currency_id', 'company_currency_id', 'company_id', 'invoice_date', 'date', 'currency_rate_type')
    def _compute_invoice_currency_rate(self):
        for move in self:
            # Initialize with default values
            rate = 1.0
            move.invoice_currency_rate = 1.0
            move.invoice_currency_inverse_rate = 1.0
            
            if move.invoice_date and move.currency_id and move.currency_id != move.company_currency_id:
                # Fatura tarihine göre geçerli olan kuru alıyoruz
                rate_obj = self.env['res.currency.rate'].search([
                    ('currency_id', '=', move.currency_id.id),
                    ('name', '=', move.date)
                ], limit=1)
                
                # Eğer belirlenen tarihte rate bulunamazsa, o tarihten önceki en yakın tarihi alıyoruz
                if not rate_obj:
                    rate_obj = self.env['res.currency.rate'].search([
                        ('currency_id', '=', move.currency_id.id),
                        ('name', '<', move.invoice_date)
                    ], order='name desc', limit=1)
                
                if rate_obj:
                    # Seçilen kur tipine göre ilgili alanı alıyoruz
                    try:
                        if move.currency_rate_type == 'forexbuying':
                            rate = 1 / rate_obj.forex_buying if rate_obj.forex_buying and rate_obj.forex_buying != 0 else 1.0
                        elif move.currency_rate_type == 'forexselling':
                            rate = 1 / rate_obj.forex_selling if rate_obj.forex_selling and rate_obj.forex_selling != 0 else 1.0
                        elif move.currency_rate_type == 'banknotebuying':
                            rate = 1 / rate_obj.banknote_buying if rate_obj.banknote_buying and rate_obj.banknote_buying != 0 else 1.0
                        elif move.currency_rate_type == 'banknoteselling':
                            rate = 1 / rate_obj.banknote_selling if rate_obj.banknote_selling and rate_obj.banknote_selling != 0 else 1.0
                        elif move.currency_rate_type == 'manualexchange':
                            rate = move.invoice_currency_rate if move.invoice_currency_rate else 1.0
                        else:
                            rate = self.env['res.currency']._get_conversion_rate(
                                from_currency=move.company_currency_id,
                                to_currency=move.currency_id,
                                company=move.company_id,
                                date=move.invoice_date or fields.Date.context_today(move),
                            )
                    except ZeroDivisionError:
                        rate = 1.0
                        _logger.warning(f"Zero division error for currency rate calculation. Using default rate 1.0 for move {move.id}")
                else:
                    # Rate obj bulunamazsa varsayılan kur
                    rate = self.env['res.currency']._get_conversion_rate(
                        from_currency=move.company_currency_id,
                        to_currency=move.currency_id,
                        company=move.company_id,
                        date=move.invoice_date or fields.Date.context_today(move),
                    )

                # Sıfır bölünmesini önlemek için kontrol
                if rate and rate != 0.0:
                    move.invoice_currency_rate = rate
                    move.invoice_currency_inverse_rate = 1.0 / rate
                else:
                    move.invoice_currency_rate = 1.0
                    move.invoice_currency_inverse_rate = 1.0
            
            else:
                if not move.payment_ids:
                    if move.date and move.currency_id and move.currency_id != move.company_currency_id:
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
                        
                        if rate_obj:
                            # Seçilen kur tipine göre ilgili alanı alıyoruz
                            try:
                                if move.currency_rate_type == 'forexbuying':
                                    rate = 1 / rate_obj.forex_buying if rate_obj.forex_buying and rate_obj.forex_buying != 0 else 1.0
                                elif move.currency_rate_type == 'forexselling':
                                    rate = 1 / rate_obj.forex_selling if rate_obj.forex_selling and rate_obj.forex_selling != 0 else 1.0
                                elif move.currency_rate_type == 'banknotebuying':
                                    rate = 1 / rate_obj.banknote_buying if rate_obj.banknote_buying and rate_obj.banknote_buying != 0 else 1.0
                                elif move.currency_rate_type == 'banknoteselling':
                                    rate = 1 / rate_obj.banknote_selling if rate_obj.banknote_selling and rate_obj.banknote_selling != 0 else 1.0
                                elif move.currency_rate_type == 'manualexchange':
                                    rate = move.invoice_currency_rate if move.invoice_currency_rate else 1.0
                                else:
                                    rate = self.env['res.currency']._get_conversion_rate(
                                        from_currency=move.company_currency_id,
                                        to_currency=move.currency_id,
                                        company=move.company_id,
                                        date=move.invoice_date or fields.Date.context_today(move),
                                    )
                            except ZeroDivisionError:
                                rate = 1.0
                                _logger.warning(f"Zero division error for currency rate calculation. Using default rate 1.0 for move {move.id}")
                        else:
                            # Rate obj bulunamazsa varsayılan kur
                            rate = self.env['res.currency']._get_conversion_rate(
                                from_currency=move.company_currency_id,
                                to_currency=move.currency_id,
                                company=move.company_id,
                                date=move.invoice_date or fields.Date.context_today(move),
                            )

                        # Sıfır bölünmesini önlemek için kontrol
                        if rate and rate != 0.0:
                            move.invoice_currency_rate = rate
                            move.invoice_currency_inverse_rate = 1.0 / rate
                        else:
                            move.invoice_currency_rate = 1.0
                            move.invoice_currency_inverse_rate = 1.0

    def action_preview_efatura(self):
        """
        Faturayı göndermeden önce XSLT ile HTML olarak önizler.
        """
        self.ensure_one()
        
        # Müşteri faturası ve iadeler için zorunlu alan kontrolleri
        if self.move_type in ('out_invoice', 'out_refund'):
            errors = []
            if not self.payment_method:
                errors.append("Ödeme Yöntemi zorunludur.")
            if not self.document_type:
                errors.append("Belge Tipi (E-Defter) zorunludur.")
            if errors:
                raise UserError("\n".join(errors))
        
        return self.env['mdx.utility.mixin'].create_preview_attachment(self, 'FATURA')
    
    picking_ids = fields.Many2many(
        comodel_name="stock.picking",
        string="Related Pickings",
        store=True,
        compute="_compute_picking_ids",
        help="Related pickings (only when the invoice has been generated from a sale "
        "order).",
    )

    picking_count = fields.Integer(
        string="Pickings count", compute="_compute_picking_count"
    )

    @api.depends("invoice_line_ids", "invoice_line_ids.move_line_ids")
    def _compute_picking_ids(self):
        for invoice in self:
            invoice.picking_ids = invoice.mapped(
                "invoice_line_ids.move_line_ids.picking_id"
            )

    @api.depends("picking_ids")
    def _compute_picking_count(self):
        for invoice in self:
            invoice.picking_count = len(invoice.picking_ids)

    def action_show_picking(self):
        """This function returns an action that display existing pickings
        of given invoice.
        It can either be a in a list or in a form view, if there is only
        one picking to show.
        """
        self.ensure_one()
        form_view_name = "stock.view_picking_form"
        result = self.env["ir.actions.act_window"]._for_xml_id(
            "stock.action_picking_tree_all"
        )
        if len(self.picking_ids) > 1:
            result["domain"] = f"[('id', 'in', {self.picking_ids.ids})]"
        else:
            form_view = self.env.ref(form_view_name)
            result["views"] = [(form_view.id, "form")]
            result["res_id"] = self.picking_ids.id
        return result
