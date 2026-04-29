# -*- coding: utf-8 -*-

import base64
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import xml.etree.ElementTree as ET
from odoo.tools import float_compare
import json

from .mdx_utility_mixin import MdxUtilityMixin

class MdxGelenIrsaliye(models.Model):
    _name = 'mdx.gelen.irsaliye'
    _description = 'Gelen İrsaliye'
    _order = 'create_date desc'

    company_id = fields.Many2one('res.company', string='Şirket', required=True, store=True, default=lambda self: self.env.company)
    # store=True alanlar
    ref_po_id = fields.Many2one('purchase.order', string='Satınalma Siparişi', compute='_compute_ref_po_id', readonly=False, store=True)
    irsaliye_html = fields.Many2one('ir.attachment', string='İrsaliye HTML', store=True)
    irsaliye_pdf = fields.Many2one('ir.attachment', string='İrsaliye PDF', store=True)
    irsaliye_xml = fields.Many2one('ir.attachment', string='İrsaliye XML', store=True)
    attachment_error_details = fields.Text(string='Belge Eki Hata Detayları', required=False, copy=False, store=True)
    irsaliye_onay_statu = fields.Selection([
        ('0', 'Yanıt Bekleniyor'),
        ('1', 'Yanıt Gönderildi'),
    ], string='İrsaliye Statü', readonly=True, store=True)
    waybill_created = fields.Boolean(string='İrsaliye Oluşturuldu', default=False, copy=False, readonly=True, store=True)
    waybill_creation_date_time = fields.Datetime(string='İrsaliyenın Oluşturulduğu Tarih', readonly=True, store=True)
    waybill_id = fields.Many2one('stock.picking', string='İrsaliye', readonly=True, copy=False, store=True, check_company=True)
    supplier_id = fields.Many2one('res.partner', string='Tedarikçi', required=False, domain=[('parent_id', '=', False), ('is_supplier', '=', True)], copy=False, compute='_compute_supplier_id', readonly=False, store=True)
    waybill_line_ids = fields.One2many('mdx.gelen.irsaliye.line', 'gelen_irsaliye_id', store=True)
    manually_matched = fields.Boolean(string='Manuel İşlendi', default=False, store=True)

    # store=True yapılacak alanlar
    name = fields.Char(string='Belge No', readonly=True, copy=False, store=True)
    belge_sira_no = fields.Char(string='Belge Sıra No', readonly=True, copy=False, store=True)
    belge_tarihi = fields.Date(string='Belge Tarihi', readonly=True, copy=False, store=True)
    belge_turu = fields.Selection([('IRSALIYE', 'İrsaliye'),('FATURA', 'Fatura')], string='Belge Türü', default='FATURA', readonly=True, copy=False, store=True)
    ettn = fields.Char(string='ETTN', readonly=True, copy=False, store=True)
    gonderen_etiket = fields.Char(string='Gönderen Etiket', readonly=True, copy=False, store=True)
    gonderen_vkn_tckn = fields.Char(string='Gönderen VKN/TCKN', copy=False, readonly=True, store=True)
    alan_etiket = fields.Char(string='Alıcı Etiket', readonly=True, copy=False, store=True)
    alici_unvan = fields.Char(string='Alıcı Ünvan', readonly=True, copy=False, store=True)
    belge_versiyon = fields.Char(string='Belge Versiyon', readonly=True, copy=False, store=True)
    satici_unvan = fields.Char(string='Satıcı Ünvan', copy=False, readonly=True, store=True)
    zarf_id = fields.Char(string='Zarf ID', readonly=True, copy=False, store=True)
    belge_hash = fields.Char(string='Belge Hash', readonly=True, copy=False, store=True)
    irsaliye_senaryo = fields.Many2one('mdx.ebelge.senaryo', string='İrsaliye Senaryo', readonly=True, copy=False, store=True)
    irsaliye_gelis_tarihi = fields.Date(string='İrsaliye Geliş Tarihi', readonly=True, copy=False, store=True)
    irsaliye_durum_detay = fields.Text(string='İrsaliye Durum Detay', readonly=True, copy=False, store=True)
    yanit_belge_oid = fields.Char(string='Yanıt Belge OID', readonly=True, copy=False, store=True)
    so_number_from_xml = fields.Char(string="E-Finans Gelen Sipariş No", readonly=True, store=True)
    controlled = fields.Boolean(string='Kontrol Edildi', default=False, store=True)
    controlled_date_time = fields.Datetime(string='Kontrol Edildiği Tarihi', default=False, store=True)
    controlled_by = fields.Many2one('res.users', string='Kontrol Eden Kişi', default=False, store=True)
    waybill_will_be_created = fields.Boolean(string='İrsaliye Oluşturulacak', default=False, store=True)
    waybill_creation_error_details = fields.Text(string='İrsaliye Oluşturma Hatası', required=False, store=True)
    is_editable = fields.Boolean(compute='_compute_is_editable', string="Düzenlenebilir", store=True)

    # logging alanları
    logging_field1 = fields.Text(string='Log1', required=False, copy=False)
    logging_field2 = fields.Text(string='Log2', required=False, copy=False)
    logging_field3 = fields.Text(string='Log3', required=False, copy=False)
    logging_field4 = fields.Text(string='Log4', required=False, copy=False)
    logging_field5 = fields.Text(string='Log5', required=False, copy=False)
    logging_field6 = fields.Text(string='Log6', required=False, copy=False)
    
    @api.onchange('manually_matched')
    def _onchange_manually_matched(self):
        for record in self:
            if record.manually_matched:
                record.waybill_will_be_created = False
                record.waybill_created = False
                record.waybill_creation_date_time = False
                record.waybill_creation_error_details = False

    @api.depends('so_number_from_xml')
    def _compute_ref_po_id(self):
        for record in self:
            if record.so_number_from_xml:
                record.ref_po_id = self.env['purchase.order'].search([('name', '=', record.so_number_from_xml)], limit=1)

    def action_create_waybill(self):
        self.ensure_one()

        existing_in_receipt = self.env['stock.picking'].search([('gelen_irsaliye_id', '=', self.id)], limit=1)
        if existing_in_receipt:
            self.waybill_will_be_created = False
            self.waybill_created = True
            self.waybill_creation_date_time = existing_in_receipt.create_date
            self.waybill_id = existing_in_receipt.id

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'info',
                    'message': _('Bu irsaliyeye ait bir tedarikçi irsaliyesi zaten oluşturulmuş!'),
                    'sticky': False
                }
            }

        purchase_order = self.ref_po_id

        # if purchase_order:
        #     purchase_order.write({'gelen_irsaliye_id': self.id})

        waybill_lines = []
        for line in self.waybill_line_ids:
            # if purchase_order_id:
            #     for po_line in self.ref_po_id.order_line:
            #         if po_line.product_id == line.product_id:sss
            #             line.write({'ref_po_line_id': po_line.id})
            #             break

            line_vals = {
                'product_id': line.product_id.id,
                'quantity': line.received_qty,
                'gelen_irsaliye_line_id': line.id,
            }
            # if line.ref_po_line_id:
            #     line_vals['move_id.purchase_line_id'] = line.ref_po_line_id.id

            waybill_lines.append((0, 0, line_vals))

        waybill_vals = {
            'company_id': self.company_id.id,
            'irsaliye_no': self.name,
            'partner_id': self.supplier_id.id,
            'origin': self.name,
            # 'purchase_id': purchase_order_id,
            'picking_type_id': self.env['stock.picking.type'].search([('code', '=', 'incoming')], limit=1).id,
            'move_line_ids': waybill_lines,
            'date': self.belge_tarihi,
            'gelen_irsaliye_id': self.id,  # Eğer stock.picking modelinde gelen irsaliye alanı varsa
            'ekli_belge_id': self.irsaliye_pdf.id if self.irsaliye_pdf else False,
        }

        # İrsaliye (stock.picking) kaydını oluşturuyoruz.
        waybill = self.env['stock.picking'].create(waybill_vals)

        if purchase_order:
            purchase_order.write({'picking_ids': [(4, waybill.id)]})

        # Oluşturulan kaydı mdx.gelen.irsaliye kaydına ilişkilendiriyoruz.
        self.write({
            'waybill_id': waybill.id,
            'waybill_created': True,
            'waybill_creation_date_time': fields.Datetime.now(),
            'waybill_will_be_created': False,
        })

        # Oluşturulan irsaliyenin form görünümünü açıyoruz.
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'target': 'current',
            'res_id': waybill.id,
        }

    @api.constrains('controlled')
    def _check_controlled(self):
        for record in self:
            if record.controlled:
                if not all(line.match_record for line in record.waybill_line_ids):
                    raise ValidationError(_("İrsaliye satırlarının eşleşme durumunu kontrol ediniz!"))
                else:
                    if any(line.create_product for line in record.waybill_line_ids):
                        return {
                            'type': 'ir.actions.client',
                            'tag': 'display_notification',
                            'params': {
                                'type': 'info',
                                'message': _('İrsaliye satırlarında otomatik ürün oluşturulacak satırlar var!'),
                                'sticky': False
                            }
                        }

    def _auto_create_products(self):
        for rec in self:
            if rec.controlled:

                if not rec.waybill_line_ids:
                    continue

                if rec.waybill_created:
                    continue

                if not all(line.match_record for line in rec.waybill_line_ids):
                    raise UserError(_("İrsaliye satırlarının eşleşme durumunu kontrol ediniz!"))
                
                if not rec.supplier_id:
                    raise UserError(_("Lütfen tedarikçi seçiniz!"))
                
                for line in rec.waybill_line_ids:
                    # if line.supplierinfo_id and line.product_id:
                        # line.supplierinfo_id.write({
                        #     'price': line.price_unit,
                        #     'currency_id': rec.odenecek_tutar_doviz_cinsi.id,
                        #     'min_qty': line.quantity,
                        # })

                    if line.create_product and not line.product_id and line.account_id:
                        product = self.env['product.product'].create({
                            'name': line.supplier_product_name,
                            'default_code': line.supplier_product_code,
                            # 'type': 'consu',
                            'purchase_ok': True,
                            'property_account_expense_id': line.account_id.id,
                        })
                        line.write({
                            'product_id': product.id,
                            'create_product': False,
                        })
                        
                    if line.create_supplierinfo and line.product_id and not line.cancel_supplierinfo_creation:
                        supplierinfo = self.env['product.supplierinfo'].create({
                            'partner_id': self.supplier_id.id,
                            'product_id': line.product_id.id,
                            'product_name': line.supplier_product_name,
                            'product_code': line.supplier_product_code,
                            'product_tmpl_id': line.product_id.product_tmpl_id.id,
                            'product_uom': line.product_id.uom_id.id,
                            # 'price': line.price_unit,
                            # 'currency_id': self.odenecek_tutar_doviz_cinsi.id,
                            # 'min_qty': line.quantity,
                            'delay': 0,
                            'sequence': 0,
                        })
                        line.write({
                            'supplierinfo_id': supplierinfo.id,
                            'create_supplierinfo': False,
                        })

    @api.model_create_multi
    def create(self, vals_list):
        records = super(MdxGelenIrsaliye, self).create(vals_list)
        records.irsaliye_onay_statu = '0'
        self.refresh_gelen_irsaliye_api_response()
        # records._auto_create_products()
        return records

    def write(self, vals):
        for record in self:
            if record.waybill_created:
                blocked_fields = {'supplier_id', 'ref_po_id', 'waybill_line_ids'}
                if any(field in vals for field in blocked_fields):
                    raise UserError(_("İrsaliye oluşturulduktan sonra bu alanlar değiştirilemez!"))
        res = super(MdxGelenIrsaliye, self).write(vals)
        self._auto_create_products()
        return res

    @api.depends('gonderen_vkn_tckn')
    def _compute_supplier_id(self):
        # create_supplier = False
        for record in self:
            supplier = self.env['res.partner'].search([('vat', '=', record.gonderen_vkn_tckn), ('is_supplier', '=', True)], limit=1)
            if supplier:
                record.supplier_id = supplier.id
            else:
                supplier = self.env['res.partner'].search([('vat', '=', self.gonderen_vkn_tckn), ('is_supplier', '=', False)], limit=1)
                if supplier:
                    supplier.write({'is_supplier': True})
                    record.supplier_id = supplier.id

                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'type': 'info',
                            'message': _('Partner bulundu, tedarikçi olarak işaretlendi!'),
                            'sticky': False
                        }
                    }
                # else:
                    # create_supplier = True
            

    def action_create_new_supplier(self):
        self.ensure_one()
        
        # 1. ZORUNLU ALAN KONTROLÜ
        # if not self.gonderen_vkn_tckn:
        #     raise UserError(_("VKN/TCKN bilgisi boş olamaz!"))
        # if not self.satici_unvan:
        #     raise UserError(_("Satıcı ünvanı boş olamaz!"))

        # 2. VAROLAN TEDARİKÇİ KONTROLÜ
        existing_partner = self.env['res.partner'].search([
            ('vat', '=', self.gonderen_vkn_tckn),
            ('supplier_rank', '>', 0)
        ], limit=1)

        if existing_partner:
            # Mevcut tedarikçiyi ata
            self.write({'supplier_id': existing_partner.id})
            return {
                'type': 'ir.action.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'info',
                    'message': _('%(name)s isimli tedarikçi zaten mevcut!') % {'name': existing_partner.name},
                    'sticky': False
                }
            }

        # XML'den alınan bilgilerle tedarikçi oluşturma
        # fatura_xml = ET.fromstring(self.fatura_xml.datas.decode('utf-8'))
        # TODO: XML'den alınan bilgilerle tedarikçi oluşturma (adress, city, country, phone, email, etc.)
        xml_data = base64.b64decode(self.irsaliye_xml.datas).decode('utf-8')
        root = ET.fromstring(xml_data)

        ns = {
                'cbc': "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
                'cac': "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
                'ubl': "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"  # Ana namespace eklendi
            }  
        
        despatch_supplier_party = root.find('.//cac:DespatchSupplierParty/cac:Party', ns)
        postal_address = despatch_supplier_party.find('.//cac:PostalAddress', ns)
        street_name = postal_address.find('.//cbc:StreetName', ns).text if postal_address.find('.//cbc:StreetName', ns) is not None else ""
        building_name = postal_address.find('.//cbc:BuildingName', ns).text if postal_address.find('.//cbc:BuildingName', ns) is not None else ""
        building_number = postal_address.find('.//cbc:BuildingNumber', ns).text if postal_address.find('.//cbc:BuildingNumber', ns) is not None else ""
        city_subdivision_name = postal_address.find('.//cbc:CitySubdivisionName', ns).text if postal_address.find('.//cbc:CitySubdivisionName', ns) is not None else ""
        city_name = postal_address.find('.//cbc:CityName', ns).text if postal_address.find('.//cbc:CityName', ns) is not None else ""
        postal_zone = postal_address.find('.//cbc:PostalZone', ns).text if postal_address.find('.//cbc:PostalZone', ns) is not None else ""
        country = postal_address.find('.//cac:Country/cbc:Name', ns).text if postal_address.find('.//cac:Country/cbc:Name', ns) is not None else ""
        party_tax_scheme_name = despatch_supplier_party.find('.//cac:PartyTaxScheme/cac:TaxScheme/cbc:Name', ns).text if despatch_supplier_party.find('.//cac:PartyTaxScheme/cac:TaxScheme/cbc:Name', ns) is not None else ""
        contact = despatch_supplier_party.find('.//cac:Contact', ns) if despatch_supplier_party.find('.//cac:Contact', ns) is not None else ""
        telephone = contact.find('.//cbc:Telephone', ns).text if contact.find('.//cbc:Telephone', ns) is not None else ""
        electronic_mail = contact.find('.//cbc:ElectronicMail', ns).text if contact.find('.//cbc:ElectronicMail', ns) is not None else ""

        # 3. YENİ TEDARİKÇİ OLUŞTURMA
        partner_address = ''
        if street_name is not None:
            partner_address += street_name + ' '
        if building_name is not None:
            partner_address += building_name + ' '
        if building_number is not None:
            partner_address += building_number + ' '
        if postal_zone is not None:
            partner_address += postal_zone + ' '

        country_id = self.env['res.country'].search([('name', '=', country.capitalize())], limit=1).id
        state_id = self.env['res.country.state'].search([('name', '=', city_name.capitalize())], limit=1).id

        self.logging_field1 = country_id
        self.logging_field2 = state_id

        partner_vals = {
            'manually_created_from_gelen_irsaliye_id': self.id,
            'vat': self.gonderen_vkn_tckn,
            'name': self.satici_unvan,
            'supplier_rank': 1,
            'company_type': 'company',
            'country_id': country_id,
            'street': partner_address,
            'state_id': state_id,
            'city': city_subdivision_name,
            'zip': postal_zone,
            'phone': telephone,
            'email': electronic_mail,
            'is_supplier': True,
            'customer_rank': 0
        }

        try:
            new_partner = self.env['res.partner'].create(partner_vals)
            self.write({'supplier_id': new_partner.id})
            

            return {
                'type': 'ir.action.client',
                'res_model': 'res.partner',
                'view_mode': 'form',
                'target': 'current',
                'res_id': new_partner.id,
            }
        
        except Exception as e:
            error_msg = _("Tedarikçi oluşturulamadı! Hata: %s") % str(e)
            self.logging_field1 = error_msg
            raise UserError(error_msg)
    
    def action_search_incoming_waybill(self):
        self.env['mdx.utility.mixin'].search_incoming_waybills()

    @api.model
    def process_pending_attachments_gelen_irsaliye(self, *args, **kwargs):
        pending_html = self.search([('irsaliye_html', '=', False)])
        for waybill in pending_html:
            try:
                self.env['mdx.utility.mixin'].get_incoming_waybill_html(waybill.ettn)
            except Exception as e:
                waybill.write({'attachment_error_details': f"HTML işleme hatası: {str(e)}"})

        pending_pdf = self.search([('irsaliye_pdf', '=', False)])
        for waybill in pending_pdf:
            try:
                self.env['mdx.utility.mixin'].get_incoming_waybill_pdf(waybill.ettn)
            except Exception as e:
                waybill.write({'attachment_error_details': f"PDF işleme hatası: {str(e)}"})

        pending_xml = self.search([('irsaliye_xml', '=', False)])
        for waybill in pending_xml:
            try:
                with self.env.cr.savepoint():
                    self.env['mdx.utility.mixin'].get_incoming_waybill_xml(waybill.ettn)
            except Exception as e:
                waybill.write({'attachment_error_details': f"XML işleme hatası: {str(e)}"})

    # @api.model
    # def process_create_out_invoices_gelen_irsaliye(self):
    #     self.env['mdx.utility.mixin'].create_out_invoices()
    
    def _compute_is_editable(self):
        for record in self:
            record.is_editable = not record.waybill_created

    # Onchange metodları
    @api.onchange('controlled')
    def _onchange_controlled(self):
        for record in self:
            if record.controlled:
                record.controlled_date_time = datetime.now()
                record.controlled_by = self.env.user
            else:
                record.controlled_date_time = False
                record.controlled_by = False
                # record.invoice_will_be_created = False

    # @api.onchange('supplier_id') # TODO: Test'ten sonra açılacak
    # def _onchange_supplier_id(self):
    #     for record in self:
    #         if record.supplier_id and record.supplier_id.vat != record.gonderen_vkn_tckn:
    #             raise ValidationError(_("Tedarikçi VKN/TCKN bilgisi eşleşmiyor!"))
    #         # elif not record.supplier_id and not record.create_supplier: # TODO: Bu kısım başka yere taşınacak
    #         #     raise ValidationError(_("Lütfen tedarikçi veya tedarikçi oluştur seçeneğini seçiniz!"))
                
    # Constraint metodları
    @api.constrains('waybill_will_be_created', 'controlled', 'supplier_id', 'waybill_line_ids', 'irsaliye_onay_statu')
    def _check_waybill_creation(self):
        for record in self:
            if record.waybill_will_be_created:
                if not record.controlled:
                    raise ValidationError(_("İrsaliye oluşturma işlemi için önce kontrol tamamlanmalı!"))
                if not record.supplier_id:
                    raise ValidationError(_("Lütfen tedarikçi seçiniz!"))
                if not record.waybill_line_ids:
                    raise ValidationError(_("En az bir irsaliye satırı eklenmelidir!"))
                # if record.irsaliye_onay_statu == '0':
                #     raise ValidationError(_("İrsaliye kabul/red işlemi bekleniyor!"))

    @api.constrains('ref_po_id')
    def _check_po_match(self):
        for record in self:
            if record.ref_po_id and record.ref_po_id.partner_id != record.supplier_id:
                order_no = record.so_number_from_xml or "Bilinmiyor"
                expected_supplier = record.supplier_id.name or "Bilinmiyor"
                actual_supplier = record.ref_po_id.partner_id.name or "Bilinmiyor"
                raise ValidationError(_(
                    "E-finans'tan gelen sipariş no %s için, beklenen tedarikçi '%s' yerine, "
                    "satınalma siparişinde '%s' görünüyor!"
                ) % (order_no, expected_supplier, actual_supplier))

    # def process_create_out_waybill_gelen_irsaliye(self):
    #     for record in self.filtered(lambda r: r.waybill_will_be_created and not r.waybill_created):
    #         try:
    #             # İrsaliye oluşturma işlemleri burada yapılacak
    #             # Örnek: record._create_waybill()
    #             self.env['mdx.utility.mixin'].create_out_waybill()
    #             record.waybill_created = True
    #             record.waybill_will_be_created = False
    #             record.waybill_creation_date_time = datetime.now()
    #         except Exception as e:
    #             record.waybill_creation_error_details = str(e)
    #             raise UserError(_("İrsaliye oluşturma hatası: %s") % e)

    
    def action_view_pdf_attachment(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s' % self.irsaliye_pdf.id,
            'target': 'new',
        }

    def refresh_gelen_irsaliye_api_response(self):
        for record in self:
            # raise UserError(_("Bu fonksiyon üzerine çalışılmaktadır, lütfen daha sonra tekrar deneyin!"))
            try:
                # TODO: Açılacak oid kodu ile buradan sorgu yapılacak
                self.env['mdx.utility.mixin'].check_gelen_irsaliye_status(record, record.yanit_belge_oid)
            except Exception as e:
                raise UserError(f"API yanıtı alınırken hata oluştu, Lütfen daha sonra tekrar deneyin.\nHata: {str(e)}")
            
    def send_gelen_irsaliye_response(self):
        for record in self:
            # raise UserError(_("Bu fonksiyon üzerine çalışılmaktadır, lütfen daha sonra tekrar deneyin!"))
            if self.irsaliye_onay_statu == '0':
                # try:
                    # TODO: Buradan gelen oid kodu için saha açılıp oraya kaydedilecek (200 durumunda)
                    self.env['mdx.utility.mixin'].response_gelen_irsaliye(record)
                    # self.refresh_gelen_irsaliye_api_response(record)
                # except Exception as e:
                #     raise UserError(f"API yanıtı alınırken hata oluştu, Lütfen daha sonra tekrar deneyin.\nHata: {str(e)}")
            else:
                raise UserError(_("Kabul işlemi için gerekli koşullar sağlanmıyor!"))
                
    # def reject_gelen_irsaliye(self):
    #     for record in self:
    #         if self.irsaliye_onay_statu == '0':
    #             try:
    #                 self.env['mdx.utility.mixin'].response_gelen_irsaliye(record, 'RED', self.kabul_red_aciklama)
    #                 # self.refresh_gelen_irsaliye_api_response(record)
    #             except Exception as e:
    #                 raise UserError(f"API yanıtı alınırken hata oluştu, Lütfen daha sonra tekrar deneyin.\nHata: {str(e)}")
    #         else:
    #             raise UserError(_("Red işlemi için gerekli koşullar sağlanmıyor!"))