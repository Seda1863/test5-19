# -*- coding: utf-8 -*-

# TODO: Geliştirmenin son aşamasında, logging_field1, logging_field2 ve logging_field3 alanları kaldırılacak
# TODO: fatura_aciklama sahasına özel karakter kontrolü eklenecek, özel karakter varsa hata mesajı verilecek
# TODO: fatura_no alanı ve uuid dolu ise, fatura gönderme butonu kaldırılacak.

import datetime
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
import xml.etree.ElementTree as ET
import json

from .mdx_utility_mixin import MdxUtilityMixin

class MdxInhStockPicking(models.Model):
    _inherit = 'stock.picking'

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
    
    # store=True alanlar
    kayit_aciklamasi = fields.Char(string='Kayıt Açıklaması', required=False, store=True)
    irsaliye_no = fields.Char(string='İrsaliye No', required=False, copy=False, store=True)
    matbuu_belge_tarihi = fields.Date(string='Matbu Belge Tarihi', required=False, store=True)
    matbuu_belge_no = fields.Char(string='Matbu Belge No', required=False, store=True)
    uuid = fields.Char(string='UUID', required=False, copy=False, store=True)
    belge_oid_kod = fields.Char(string='Belge OID Kodu', required=False, copy=False, store=True)
    irsaliye_gonderim_hata_kodu = fields.Text(string='İrsaliye Gönderim Hata Kodu', required=False, copy=False, store=True)
    irsaliye_durum_detay = fields.Text(string='İrsaliye Durum Detay', required=False, copy=False, store=True)
    irsaliye_aciklama = fields.Text(string='İrsaliye Açıklama', required=False, store=True, compute='_compute_irsaliye_aciklama', readonly=False, copy=False, precompute=True)
    ekli_belge_id = fields.Many2one('ir.attachment', string='Ekli Belge', required=False, copy=False, store=True)
    nakliye_sirketi_id = fields.Many2one('res.partner', string='Nakliye Şirketi', required=False, domain=[('is_company', '=', True), ('is_carrier', '=', True), ('active', '=', True)], store=True)
    sofor_adi = fields.Char(string='Şoför Adı', required=False, store=True)
    sofor_soyadi = fields.Char(string='Şoför Soyadı', required=False, store=True)
    sofor_tc_no = fields.Char(string='Şoför TC No', required=False, store=True)
    sofor_ilce = fields.Char(string='Şoför Semt/İlçe', required=False, store=True)
    sofor_il = fields.Char(string='Şoför İl', required=False, store=True)
    sofor_ulke = fields.Char(string='Şoför Ülke', required=False, store=True)
    sofor_zip = fields.Char(string='Şoför Posta Kodu', required=False, store=True)
    arac_plaka_no = fields.Char(string='Araç Plaka No', required=False, store=True)
    dorse_plaka_no_1 = fields.Char(string='Dorse Plaka No 1', required=False, store=True)
    dorse_plaka_no_2 = fields.Char(string='Dorse Plaka No 2', required=False, store=True)

    @api.depends('sale_id.client_order_ref', 'origin', 'carrier_tracking_ref', 'irsaliye_aciklama')
    def _compute_irsaliye_aciklama(self):
        # DEĞİŞİKLİK 1: Ayıraçtan enter karakterlerini kaldırdık. Sadece metni arayacağız.
        SEPARATOR = "*** EK AÇIKLAMALAR ***"
        
        for record in self:
            # --- 1. SİSTEM METNİ HESAPLAMA ---
            aciklama_listesi = []

            if record.origin:
                aciklama_listesi.append(record.origin)

            if record.sale_id and record.sale_id.client_order_ref:
                ref = record.sale_id.client_order_ref
                if ref not in aciklama_listesi:
                    aciklama_listesi.append(ref)

            if record.carrier_tracking_ref:
                tracking_ref = record.carrier_tracking_ref
                if tracking_ref not in aciklama_listesi:
                    aciklama_listesi.append(tracking_ref)

            system_text = " - ".join(aciklama_listesi)

            # --- 2. MEVCUT VERİYİ ANALİZ ET ---
            current_text = record.irsaliye_aciklama or ""
            manual_part = ""

            # DEĞİŞİKLİK 2: Split mantığı güncellendi.
            if SEPARATOR in current_text:
                # Ayıracı bulunca sonrasını alıyoruz (strip ile boşlukları temizleyerek)
                parts = current_text.split(SEPARATOR)
                if len(parts) > 1:
                    manual_part = parts[-1].strip()
            else:
                # Ayraç yoksa ve metin sistemden farklıysa, kalanı manuel not say
                # (Fakat sistem metni içinde geçiyorsa onu temizle)
                if current_text.strip() != system_text.strip():
                    clean_current = current_text.replace(system_text, "").strip()
                    # Fazladan kalan tireleri temizle
                    clean_current = clean_current.strip(" -")
                    if clean_current:
                        manual_part = clean_current
                    elif current_text and not system_text:
                         manual_part = current_text

            # --- 3. BİRLEŞTİRME ---
            final_text = system_text
            
            # DEĞİŞİKLİK 3: Sadece manuel not varsa ayıracı ve notu ekle. Yoksa ekleme.
            if manual_part:
                # Sistem metni varsa 2 satır boşluk, yoksa (direkt manuel ile başlıyorsa) dokunma
                prefix = "\n\n" if final_text else ""
                final_text += f"{prefix}{SEPARATOR}\n{manual_part}"

            if record.irsaliye_aciklama != final_text:
                record.irsaliye_aciklama = final_text

    # GÜNCELLEME: UI'da anlık koruma için onchange
    @api.onchange('irsaliye_aciklama')
    def _onchange_irsaliye_aciklama_protection(self):
        """Kullanıcı elle müdahale ettiğinde compute metodunu tetikler."""
        self._compute_irsaliye_aciklama()

    # computed alanlar
    filtered_eirsaliye_senaryo_ids = fields.Many2many(
        'mdx.ebelge.senaryo',
        compute='_compute_filtered_eirsaliye_senaryo_ids',
        store=False
    )
    eirsaliye_gonderilebilir = fields.Boolean(string='E-İrsaliye Gönderilebilir', default=True, required=False, compute='_compute_eirsaliye_gonderilebilir', store=False)

    # store=True yapılacak alanlar
    ebelge_turu_id = fields.Many2one('mdx.ebelge.turu', string='E-Belge Türü', domain=[('active', '=', True), ('belge_cinsi_id.code', '=', 'IRSALIYE')], default=lambda self: self.env['mdx.ebelge.turu'].search([('belge_cinsi_id.code', '=', 'IRSALIYE')], limit=1), required=False, readonly=False, store=True)
    eirsaliye_senaryo_id = fields.Many2one(
        'mdx.ebelge.senaryo',
        string='E-İrsaliye Senaryo',
        domain="[('id', 'in', filtered_eirsaliye_senaryo_ids)]",
        default=lambda self: self.env['mdx.ebelge.senaryo'].search([('code', '=', 'TEMELIRSALIYE')], limit=1),
        required=False
    , store=True)
    irsaliye_tipi_id = fields.Many2one('mdx.ebelge.tipi', string='E-İrsaliye Tipi', domain=[('active', '=', True), ('belge_cinsi_id.code', '=', 'IRSALIYE')], required=False, default=lambda self: self.env['mdx.ebelge.tipi'].search([('code', '=', 'SEVK')], limit=1), store=True)
    irsaliye_statu_id = fields.Many2one('mdx.sabit.kod', string='İrsaliye Statüsü', domain=[('liste_id.code', '=', 'GIDENEIRSALIYE')], required=False, store=True)
    irsaliye_seri_id = fields.Many2one('mdx.fatura.seri', string='İrsaliye Seri', required=False, copy=False, domain=[('ebelge_turu_id.belge_cinsi_id.code', '=', 'IRSALIYE'), ('active', '=', True)], default=lambda self: self.env['mdx.fatura.seri'].search([('ebelge_turu_id.belge_cinsi_id.code', '=', 'IRSALIYE'), ('active', '=', True)], limit=1), store=True)

    # logging alanları
    logging_field1 = fields.Text(string='Log1', required=False, copy=False)
    logging_field2 = fields.Text(string='Log2', required=False, copy=False)
    logging_field3 = fields.Text(string='Log3', required=False, copy=False)
    logging_field4 = fields.Text(string='Log4', required=False, copy=False)
    logging_field5 = fields.Text(string='Log5', required=False, copy=False)
    logging_field6 = fields.Text(string='Log6', required=False, copy=False)
    logging_field7 = fields.Text(string='Log7', required=False, copy=False)
    
    # @api.depends('move_type', 'reversed_entry_id', 'is_storno')
    # def _compute_fatura_tipi_id(self):
    #     for record in self:
    #         if record.move_type == 'in_refund' and record.reversed_entry_id and record.is_storno:
    #             record.fatura_tipi_id = self.env['mdx.ebelge.tipi'].search([('code', '=', 'IADE')], limit=1)

    # @api.depends('move_type')
    # def _compute_logging_field7(self):
    #     for record in self:
    #         if record.move_type == 'in_refund':
    #             record.logging_field7 = self.ref

    # @api.depends('currency_id')
    # def _compute_invoice_currency_inverse_rate(self):
    #     for move in self:
    #         if move.is_invoice(include_receipts=True):
    #             if move.currency_id:
    #                 move.invoice_currency_inverse_rate = 1 / move.currency_id.rate
    # return_picking_type_id = lambda self: self.picking_type_id.return_picking_type_id
    filtered_partner_ids = fields.Many2many('res.partner', compute='_compute_filtered_partner_ids', store=False)

    gelen_irsaliye_id = fields.Many2one('mdx.gelen.irsaliye', string='Gelen İrsaliye', required=False, store=True)

    @api.ondelete(at_uninstall=True)
    def _ondelete_waybill(self):
        # 'ondelete' işlemi
        for move in self:
            if move.gelen_irsaliye_id:
                gelen_irsaliye = move.gelen_irsaliye_id
                gelen_irsaliye.write({
                    'waybill_will_be_created': False,
                    'waybill_created': False,
                    'waybill_creation_date_time': False,
                })

    @api.depends('picking_type_code')
    def _compute_filtered_partner_ids(self):
        for record in self:
            if record.picking_type_code in ['outgoing']:
                record.filtered_partner_ids = self.env['res.partner'].search([('is_customer', '=', True)])
            elif record.picking_type_code in ['incoming']:
                record.filtered_partner_ids = self.env['res.partner'].search([('is_supplier', '=', True)])
            else:
                record.filtered_partner_ids = self.env['res.partner'].search([('parent_id', '=', False)])

    @api.depends('irsaliye_no', 'uuid', 'state', 'picking_type_code')
    def _compute_eirsaliye_gonderilebilir(self):
        for record in self:
            # record.efatura_gonderilebilir = record.state == 'posted' and record.move_type == 'out_invoice' and ( not record.fatura_no or not record.uuid )
            # record.eirsaliye_gonderilebilir = record.state == 'done' and ( not record.irsaliye_no or not record.uuid ) and record.picking_type_code in ['outgoing']
            if record.picking_type_code == 'outgoing' and record.state == 'done':
                if record.irsaliye_no and record.uuid:
                    record.eirsaliye_gonderilebilir = False
                else:
                    record.eirsaliye_gonderilebilir = True
            else:
                record.eirsaliye_gonderilebilir = False             

    @api.depends('ebelge_turu_id')
    def _compute_filtered_eirsaliye_senaryo_ids(self):
        for record in self:
            if record.ebelge_turu_id:
                record.filtered_eirsaliye_senaryo_ids = self.env['mdx.ebelge.senaryo'].search([
                    ('ebelge_turu_ids', 'in', record.ebelge_turu_id.id),
                    ('active', '=', True)
                ])
            else:
                record.filtered_eirsaliye_senaryo_ids = self.env['mdx.ebelge.senaryo'].search([('active', '=', True)])

    # @api.onchange('partner_id')
    # def _onchange_partner_id(self):
    #     if self.partner_id:
    #         self.efatura_turu_id = self.partner_id.efatura_turu_id.id if self.partner_id.efatura_turu_id else False
    #         self.efatura_senaryo_id = self.partner_id.efatura_senaryo_id.id if self.partner_id.efatura_senaryo_id else False
    #         self.fatura_tipi_id = self.partner_id.fatura_tipi_id.id if self.partner_id.fatura_tipi_id else False
    #         self.fatura_alt_tipi_id = self.partner_id.fatura_alt_tipi_id.id if self.partner_id.fatura_alt_tipi_id else False
    #         self.fatura_seri_id = self.env['mdx.fatura.seri'].search([('ebelge_turu_id.code', '=', self.efatura_turu_id.code)], limit=1)
    #         if self.line_ids:
    #             for line in self.line_ids:
    #                 line.tevkifat_kodu = self.partner_id.tevkifat_kodu.id if self.partner_id.tevkifat_kodu else False
    #                 line.istisna_kodu = self.partner_id.efatura_turu_id.id if self.partner_id.efatura_turu_id else False
    #                 line.ozel_matrah_kodu = self.partner_id.efatura_senaryo_id.id if self.partner_id.efatura_senaryo_id else False
    #                 line.ihrac_kayit_kodu = self.partner_id.fatura_tipi_id.id if self.partner_id.fatura_tipi_id else False
            
    # @api.model
    # def create(self, vals):
    #     # Partner bilgisi varsa, partner'e göre alanları doldur
    #     if 'partner_id' in vals:
    #         partner = self.env['res.partner'].browse(vals['partner_id'])
    #         vals = self._update_fields_from_partner(partner, vals)

    #     if not vals.get('fatura_seri_id') and vals.get('efatura_turu_id'):
    #         efatura_turu_id = vals['efatura_turu_id']
    #         efatura_turu = self.env['mdx.ebelge.turu'].browse(efatura_turu_id)  # İlgili kaydı bul
    #         efatura_turu_code = efatura_turu.code if efatura_turu else None  # Code değerini al

    #         if efatura_turu_code:
    #             fatura_seri = self.env['mdx.fatura.seri'].search(
    #                 [('ebelge_turu_id.code', '=', efatura_turu_code)],
    #                 limit=1
    #             )
    #             if fatura_seri:
    #                 vals['fatura_seri_id'] = fatura_seri.id

    #     return super(MdxInhStockPicking, self).create(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # document_type other ise document_type_description_id alanı zorunlu
            if vals.get('document_type') == 'other' and not vals.get('document_type_description_id'):
                raise ValidationError("Belge Tipi 'Diğer' ise, Belge Tipi Açıklaması alanı zorunludur.")

        return super().create(vals_list)

    def write(self, vals): # TODO: _download_waybill_pdf eklenecek
        # Partner bilgisi değişmişse, partner'e göre alanları doldur
        # if 'partner_id' in vals:
        #     partner = self.env['res.partner'].browse(vals['partner_id'])
        #     vals = self._update_fields_from_partner(partner, vals)

        if 'irsaliye_no' in vals or 'uuid' in vals:
            for record in self:
                record._download_waybill_pdf()

        # document_type other ise document_type_description_id alanı zorunlu
        if vals.get('document_type') == 'other' and not vals.get('document_type_description_id'):
            raise ValidationError("Belge Tipi 'Diğer' ise, Belge Tipi Açıklaması alanı zorunludur.")

        return super(MdxInhStockPicking, self).write(vals)

    # def _update_fields_from_partner(self, partner, vals):
    #     """
    #     Partner'e göre ilgili alanları güncelleyen yardımcı metod.
    #     """
    #     if partner:
    #         # E-Fatura Türü
    #         if not vals.get('efatura_turu_id') and partner.efatura_turu_id:
    #             vals['efatura_turu_id'] = partner.efatura_turu_id.id

    #         # E-Fatura Senaryo
    #         if not vals.get('efatura_senaryo_id') and partner.efatura_senaryo_id:
    #             vals['efatura_senaryo_id'] = partner.efatura_senaryo_id.id

    #         # Fatura Tipi
    #         if not vals.get('fatura_tipi_id'):
    #             if vals.get('is_storno') == False or vals.get('move_type') == 'in_refdund':
    #                 if partner.fatura_tipi_id:
    #                     vals['fatura_tipi_id'] = partner.fatura_tipi_id.id
    #             else:
    #                 vals['fatura_tipi_id'] = self.env['mdx.ebelge.tipi'].search([('code', '=', 'IADE')], limit=1).id

    #         # Fatura Alt Tipi
    #         if not vals.get('fatura_alt_tipi_id') and partner.fatura_alt_tipi_id:
    #             vals['fatura_alt_tipi_id'] = partner.fatura_alt_tipi_id.id

    #     return vals

    # @api.depends('fatura_tipi_id', 'efatura_senaryo_id')
    # def _compute_readonly_fields(self):
    #     """Compute readonly state for fields based on other fields' values."""
    #     for record in self:
    #         record.efatura_senaryo_readonly = record.fatura_tipi_id.code in [
    #             'IADE', 'SGK']
    #         record.fatura_tipi_readonly = record.efatura_senaryo_id.code in [
    #             'YOLCUBERABERFATURA', 'IHRACAT']
            
    # @api.depends('efatura_turu_id')
    # def _compute_filtered_efatura_senaryo_ids(self):
    #     for record in self:
    #         if record.efatura_turu_id:
    #             record.filtered_efatura_senaryo_ids = self.env['mdx.ebelge.senaryo'].search([
    #                 ('ebelge_turu_ids', 'in', record.efatura_turu_id.id),
    #                 ('active', '=', True)
    #             ])
    #         else:
    #             record.filtered_efatura_senaryo_ids = self.env['mdx.ebelge.senaryo'].search([
    #                                                                                         ('active', '=', True)])

    # @api.onchange('efatura_senaryo_id')
    # def _onchange_efatura_senaryo_id(self):
    #     if self.efatura_senaryo_id:
    #         if self.efatura_senaryo_id.code == 'IHRACAT' or self.efatura_senaryo_id.code == 'YOLCUBERABERFATURA':
    #             self.fatura_tipi_id = self.env['mdx.ebelge.tipi'].search(
    #                 [('code', '=', 'ISTISNA')], limit=1)
    #         elif self.efatura_senaryo_id.code == 'ENERJI':
    #             self.fatura_tipi_id = self.env['mdx.ebelge.tipi'].search(
    #                 [('code', '=', 'SARJ')], limit=1)
                
    # @api.onchange('fatura_tipi_id')
    # def _onchange_fatura_tipi_id(self):
    #     if self.fatura_tipi_id and self.efatura_turu_id.code != 'EARSIV':
    #         if self.fatura_tipi_id.code == 'IADE' or self.fatura_tipi_id.code == 'SGK':
    #             self.efatura_senaryo_id = self.env['mdx.ebelge.senaryo'].search(
    #                 [('code', '=', 'TEMELFATURA')], limit=1)
                
    # account.move action_post metoduna yeni işlem ekle
    # def action_confirm(self):
    #     for record in self:

            # if record.picking_type_code == 'outgoing':
            #     if not record.nakliye_sirketi_id and (not record.sofor_adi or not record.sofor_soyadi or not record.sofor_tc_no or not record.sofor_zip):
            #         raise UserError("Lütfen nakliye şirketi seçin veya şoför bilgilerini (Şoför adı, soyadı, TCKN, posta kodu) doldurun.")
                
            #     if record.nakliye_sirketi_id:
            #         if record.nakliye_sirketi_id.vat:
            #             raise UserError("Lütfen nakliye şirketinin vergi numarasını doldurun.")
            #         if record.nakliye_sirketi_id.zip:
            #             raise UserError("Lütfen nakliye şirketinin posta kodunu doldurun.")
                
            # if record.ebelge_turu_id and record.ebelge_turu_id.belge_cinsi_id.code == 'IRSALIYE':
            #     if not record.irsaliye_no:
            #         taslak_seri = self.env['mdx.fatura.seri'].search([('code', '=', 'IRS')], limit=1)
            #         if not taslak_seri:
            #             raise UserError("Belge Seri 'IRS' bulunamadı.")
                    
            #         # Seri numarasını güncelle ve irsaliye numarasını oluştur
            #         taslak_seri_code = taslak_seri.code
            #         taslak_seri_index = taslak_seri.index
            #         date_today = datetime.date.today()
            #         taslak_seri.write({'index': taslak_seri_index + 1, 'last_used_date': date_today})

            #         # İrsaliye numarası oluşturulması
            #         record.name = f"{taslak_seri_code}{date_today.year}{str(taslak_seri_index).zfill(9)}"

        # Orijinal `action_confirm` metodunu çağır
        # result = super().action_confirm()
        # return result

    def action_generate_uuid(self):
        for record in self:
            record.uuid = MdxUtilityMixin.generate_uuid()

    def action_send_waybill(self):
        """
        Generate XML for the current invoice record.
        """
        try:
            # try:
            # Assuming `self` contains a single record of `account.move`
            # if len(self) != 1:
            #     raise UserError("Bu işlem yalnızca tek bir fatura üzerinde çalışır.")

            # self.logging_field1 = self.tax_totals
            # if not self.nakliye_sirketi_id or (not self.sofor_adi or not self.sofor_soyadi or not self.sofor_tc_no or not self.sofor_zip):
            #     raise UserError("Lütfen nakliye şirketi seçin veya şoför bilgilerini (Şoför adı, soyadı, TCKN, posta kodu) doldurun.")
            
            # if self.nakliye_sirketi_id:
            #     if self.nakliye_sirketi_id.vat:
            #         raise UserError("Lütfen nakliye şirketinin vergi numarasını doldurun.")
            #     if self.nakliye_sirketi_id.zip:
            #         raise UserError("Lütfen nakliye şirketinin posta kodunu doldurun.")

            # Generate XML using the utility function
            xml_content = self.env['mdx.utility.mixin'].generate_waybill_xml(self)
            self.logging_field1 = xml_content
            
            # Send the XML to the relevant service
            response = self.env['mdx.utility.mixin'].send_waybill_xml(self, xml_content)
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
            # self.write({'name': self.irsaliye_no})
        except Exception as e:
            # self.write({'uuid': ''})
            raise UserError(f"API yanıtı alınırken hata oluştu, Lütfen daha sonra tekrar deneyin.\nHata: {str(e)}")

    def refresh_api_response(self):
        for record in self:
            if record.belge_oid_kod:
                try:
                    self.env['mdx.utility.mixin'].check_waybill_status(record.belge_oid_kod, self)
                    # XML yanıtını parse ediyoruz
                    # root = ET.fromstring(response)

                    # # XML'deki namespace'i belirliyoruz
                    # namespace = {'ns2': 'http://service.connector.uut.cs.com.tr/'}
                    # result_code = root.find('.//ns2:gidenBelgeDurumSorgulaExtResponse/return/gonderimCevabiKodu', namespace)
                    # if result_code is "1200":
                    #     self.write({'logging_field1': "Fatura başarıyla gönderildi."})

                    self._download_waybill_pdf()
                except Exception as e:
                    raise UserError(f"API yanıtı alınırken hata oluştu, Lütfen daha sonra tekrar deneyin.\nHata: {str(e)}")


    @api.depends('irsaliye_no', 'uuid', 'state')
    def _download_waybill_pdf(self):
        for record in self:
            try:
                # Koşulları logla
                record.logging_field5 = (
                    # f"Checking conditions: move_type={record.move_type}, "
                    f"irsaliye_no={record.irsaliye_no}, uuid={record.uuid}, state={record.state}"
                )
                
                # if record.fatura_no and record.uuid and record.state == 'posted' and record.move_type == 'out_invoice':
                # if record.irsaliye_no and record.uuid and record.state == 'posted':
                if record.irsaliye_no and record.uuid:
                    attachment_pdf = MdxUtilityMixin.download_document_pdf(
                        record, "IRSALIYE", record.uuid
                    )

                    if attachment_pdf:
                        record.ekli_belge_id = attachment_pdf.id
                        record.logging_field5 = "PDF başarıyla indirildi ve iliştirildi."
                    else:
                        record.logging_field5 = "PDF indirilemedi: attachment_pdf boş."
                else:
                    record.logging_field5 = "Koşullar sağlanmadı, PDF oluşturulamadı."
            except Exception as e:
                record.logging_field5 = f"PDF oluşturulurken hata: {str(e)}"


    def view_waybill_pdf_on_newtab(self):
        for record in self:
            if record.ekli_belge_id:
                record.logging_field6 = record.ekli_belge_id.mimetype
                return {
                    'type': 'ir.actions.act_url',
                    'url': '/web/content/%s' % record.ekli_belge_id.id,  # `download=true` kaldırıldı
                    'target': 'new',  # Yeni sekmede açılacak
                }
            else:
                raise UserError("İrsaliye PDF'i bulunamadı.")
            
    def action_preview_eirsaliye(self):
        """
        İrsaliyeyi göndermeden önce XSLT ile HTML olarak önizler.
        """
        self.ensure_one()
        return self.env['mdx.utility.mixin'].create_preview_attachment(self, 'IRSALIYE')
    
    invoice_ids = fields.Many2many(
        comodel_name="account.move", copy=False, string="Invoices", readonly=True
    )
    invoice_count = fields.Integer(
        string="Number of Invoices", compute="_compute_invoice_count"
    )

    def action_view_invoice(self):
        """This function returns an action that display existing invoices
        of given stock pickings.
        It can either be a in a list or in a form view, if there is only
        one invoice to show.
        """
        self.ensure_one()
        form_view_name = "account.view_move_form"
        result = self.env["ir.actions.act_window"]._for_xml_id(
            "account.action_move_out_invoice_type"
        )
        if len(self.invoice_ids) > 1:
            result["domain"] = f"[('id', 'in', {self.invoice_ids.ids})]"
        else:
            form_view = self.env.ref(form_view_name)
            result["views"] = [(form_view.id, "form")]
            result["res_id"] = self.invoice_ids.id
        return result

    @api.depends("invoice_ids")
    def _compute_invoice_count(self):
        for order in self:
            order.invoice_count = len(order.invoice_ids)
    