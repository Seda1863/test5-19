# -*- coding: utf-8 -*-

import base64
from datetime import datetime
import re
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import xml.etree.ElementTree as ET
from odoo.tools import float_compare
import json

from .mdx_utility_mixin import MdxUtilityMixin

class MdxGelenFatura(models.Model):
    _name = 'mdx.gelen.fatura'
    _description = 'Gelen Fatura'
    _order = 'belge_sira_no asc'

    company_id = fields.Many2one('res.company', string='Şirket', required=True, store=True, default=lambda self: self.env.company)
    # store=True alanlar
    fatura_html = fields.Many2one('ir.attachment', string='Fatura HTML', store=True)
    fatura_pdf = fields.Many2one('ir.attachment', string='Fatura PDF', store=True)
    fatura_xml = fields.Many2one('ir.attachment', string='Fatura XML', store=True)
    fatura_pdf_preview = fields.Html(string='Fatura Onizleme', compute='_compute_fatura_pdf_preview', sanitize=False, store=False)
    attachment_error_details = fields.Text(string='Belge Eki Hata Detayları', required=False, store=True, copy=False)
    so_number_from_xml = fields.Char(string="E-Finans Gelen Sipariş No", readonly=True)
    ref_po_id = fields.Many2one('purchase.order', string='Satınalma Siparişi', compute='_compute_ref_po_id', store=True, readonly=False)
    fatura_onay_statu = fields.Selection([
        ('-1', 'Yanıt Gerekmiyor'),
        ('0', 'Yanıt Bekleniyor'),
        ('1', 'Reddedildi'),
        ('2', 'Kabul Edildi'),
    ], string='Ticari Fatura Statü', store=True, readonly=True)
    ref_in_receipt_id = fields.Many2one('stock.picking', string='Gelen İrsaliye', compute='_compute_ref_in_receipt_id', store=True, readonly=False)
    invoice_created = fields.Boolean(string='Fatura Oluşturuldu', default=False, copy=False, readonly=True, store=True)
    invoice_creation_date_time = fields.Datetime(string='Faturanın Oluşturulduğu Tarih', store=True, readonly=True)
    invoice_id = fields.Many2one('account.move', string='Fatura', readonly=True, store=True, copy=False, check_company=True)
    invoice_line_ids = fields.One2many('mdx.gelen.fatura.line', 'gelen_fatura_id', store=True)
    manually_matched = fields.Boolean(string='Manuel İşlendi', default=False, store=True)

    # store=True yapılacak alanlar
    name = fields.Char(string='Belge No', readonly=True, copy=False, store=True)
    belge_sira_no = fields.Integer(string='Belge Sıra No', readonly=True, copy=False, store=True)
    belge_tarihi = fields.Date(string='Belge Tarihi', readonly=True, copy=False, store=True)
    belge_turu = fields.Selection([
        ('IRSALIYE', 'İrsaliye'),
        ('FATURA', 'Fatura'),
    ], string='Belge Türü', default='FATURA', readonly=True, copy=False, store=True)
    ettn = fields.Char(string='ETTN', readonly=True, copy=False, store=True)
    gonderen_etiket = fields.Char(string='Gönderen Etiket', readonly=True, copy=False, store=True)
    gonderen_vkn_tckn = fields.Char(string='Gönderen VKN/TCKN', copy=False, readonly=True, store=True)
    alan_etiket = fields.Char(string='Alıcı Etiket', readonly=True, copy=False, store=True)
    alici_unvan = fields.Char(string='Alıcı Ünvan', readonly=True, copy=False, store=True)
    belge_versiyon = fields.Char(string='Belge Versiyon', readonly=True, copy=False, store=True)
    satici_unvan = fields.Char(string='Satıcı Ünvan', copy=False, readonly=True, store=True)
    zarf_id = fields.Char(string='Zarf ID', readonly=True, copy=False, store=True)
    odenecek_tutar = fields.Float(string='Ödenecek Tutar', readonly=True, copy=False, store=True)
    odenecek_tutar_doviz_cinsi = fields.Many2one('res.currency', string='Ödenecek Tutar Döviz Cinsi', readonly=True, copy=False, store=True)
    belge_hash = fields.Char(string='Belge Hash', readonly=True, copy=False, store=True)
    fatura_gelis_tarihi = fields.Date(string='Fatura Geliş Tarihi', readonly=True, copy=False, store=True)
    son_odeme_tarihi = fields.Date(string='Son Ödeme Tarihi', readonly=True, copy=False, store=True)
    fatura_senaryo = fields.Many2one('mdx.ebelge.senaryo', string='Fatura Senaryo', readonly=True, copy=False, store=True)
    kabul_red_aciklama = fields.Text(string='Kabul/Red Açıklaması', readonly=True, copy=False, store=True)
    fatura_durum_detay = fields.Text(string='Fatura Durum Detay', readonly=True, copy=False, store=True)
    waybill_number_from_xml = fields.Char(string="E-Finans Gelen İrsaliye No", readonly=True, store=True)
    tax_exemption_reason_code_id = fields.Many2one('mdx.sabit.kod', string='Vergi İstisna Nedeni', readonly=True, store=True)
    controlled = fields.Boolean(string='Kontrol Edildi', default=False, store=True)
    controlled_date_time = fields.Datetime(string='Kontrol Edildiği Tarihi', default=False, store=True)
    controlled_by = fields.Many2one('res.users', string='Kontrol Eden Kişi', default=False, store=True)
    invoice_will_be_created = fields.Boolean(string='Fatura Oluşturulacak', default=False, store=True)
    invoice_creation_error_details = fields.Text(string='Fatura Oluşturma Hatası', required=False, store=True)
    supplier_id = fields.Many2one('res.partner', string='Tedarikçi', required=False, domain=[('parent_id', '=', False), ('is_supplier', '=', True)], copy=False, compute='_compute_supplier_id', store=True, readonly=False)
    responsible_user_id = fields.Many2one(
        'res.users',
        string='Sorumlu Kullanici',
        copy=False,
        index=True,
        store=True,
        readonly=False,
        compute='_compute_responsible_user_id',
        compute_sudo=True,
        inverse='_inverse_responsible_user_id',
    )
    is_editable = fields.Boolean(compute='_compute_is_editable', string="Düzenlenebilir")
    fatura_durum_text = fields.Char(string='Fatura Durumu', compute='_compute_fatura_durum_text', store=False)

    def _resolve_responsible_user_from_supplier(self):
        self.ensure_one()
        supplier = self.supplier_id if self.supplier_id else False
        if not supplier:
            return self.env['res.users']
        # buyer_id field is expected on partner in this deployment.
        if 'buyer_id' in supplier._fields and supplier.buyer_id:
            return supplier.buyer_id
        commercial = supplier.commercial_partner_id
        if commercial and 'buyer_id' in commercial._fields and commercial.buyer_id:
            return commercial.buyer_id
        return self.env['res.users']

    @api.model
    def _normalize_trade_name(self, value):
        text = (value or '').upper().strip()
        if not text:
            return ''
        # Remove common dynamic suffixes like ERP1/ERP2 and non-alnum chars.
        text = re.sub(r'\bERP\s*\d+\b', '', text)
        text = text.replace('İ', 'I').replace('Ş', 'S').replace('Ğ', 'G').replace('Ü', 'U').replace('Ö', 'O').replace('Ç', 'C')
        text = re.sub(r'[^A-Z0-9]+', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    @api.depends('supplier_id')
    def _compute_responsible_user_id(self):
        """Auto-assign responsible user dari supplier.buyer_id, tapi jangan override manual assignment."""
        for rec in self:
            # Jika sudah diset manual (not from supplier_id change), jangan override
            if rec.responsible_user_id and not rec.supplier_id:
                continue
            buyer = rec._resolve_responsible_user_from_supplier()
            rec.responsible_user_id = buyer.id if buyer else False

    def _inverse_responsible_user_id(self):
        """Inverse method untuk manual write pada responsible_user_id."""
        # Tidak perlu lakukan apa-apa, just allow the write
        pass

    def _sync_responsible_users(self):
        """Keep a single sync entrypoint; compute method handles assignment."""
        self._compute_responsible_user_id()

    def action_assign_to_me(self):
        """Sorumlu kullanıcıyı current user'a set et."""
        self.ensure_one()
        self.responsible_user_id = self.env.user.id
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Başarılı',
                'message': f'Fatura {self.name} size atandı.',
                'type': 'success',
                'sticky': False,
            }
        }

    @api.model
    def _sync_responsible_users_for_suppliers(self, suppliers):
        suppliers = suppliers.exists() if suppliers else self.env['res.partner']
        if not suppliers:
            return
        commercial_suppliers = suppliers.mapped('commercial_partner_id')
        related_suppliers = self.env['res.partner'].search([
            ('commercial_partner_id', 'in', commercial_suppliers.ids)
        ])
        invoices = self.search([('supplier_id', 'in', related_suppliers.ids)])
        if invoices:
            invoices._sync_responsible_users()

        # Fallback: match by normalized supplier title when VAT differs but entity name is same.
        for supplier in commercial_suppliers:
            supplier_norm = self._normalize_trade_name(supplier.name)
            if not supplier_norm:
                continue

            candidates = self.search([
                ('satici_unvan', 'ilike', (supplier.name or '')[:32])
            ])
            matched = candidates.filtered(lambda inv: self._normalize_trade_name(inv.satici_unvan) == supplier_norm)
            if not matched:
                continue

            to_link = matched.filtered(lambda inv: not inv.supplier_id or inv.supplier_id.commercial_partner_id != supplier)
            if to_link:
                to_link.with_context(skip_responsible_sync=True).write({'supplier_id': supplier.id})
            matched._sync_responsible_users()

    @api.model
    def _sync_responsible_users_for_vats(self, vats):
        vat_list = [v.strip() for v in (vats or []) if v and str(v).strip()]
        if not vat_list:
            return
        invoices = self.search([('gonderen_vkn_tckn', 'in', vat_list)])
        if invoices:
            # Ensure supplier resolution is up-to-date before syncing owners.
            invoices._compute_supplier_id()
            invoices._sync_responsible_users()

    @api.model
    def _sync_responsible_users_for_supplier_names(self, supplier_names):
        normalized_names = [n.strip() for n in (supplier_names or []) if n and str(n).strip()]
        if not normalized_names:
            return

        invoices = self.search([('satici_unvan', 'in', normalized_names)])
        if invoices:
            invoices._compute_supplier_id()
            invoices._sync_responsible_users()

    @api.depends('supplier_id', 'fatura_onay_statu')
    def _compute_fatura_durum_text(self):
        for record in self:
            if not record.supplier_id:
                record.fatura_durum_text = '⛔ Cari Eşleştirilemedi'
            elif record.fatura_onay_statu == '0':
                record.fatura_durum_text = '⏳ Onay Bekleniyor'
            elif record.fatura_onay_statu in ('2', '-1'):
                record.fatura_durum_text = '✅ Kaydedilebilir'
            elif record.fatura_onay_statu == '1':
                record.fatura_durum_text = '❌ Reddedildi'
            else:
                record.fatura_durum_text = '—'
    # is_available = fields.Boolean(string='Erişilebilir', default=True, store=True, compute='_compute_is_available')

    # # is_available alanı için hesaplama
    # @api.depends('fatura_onay_statu', 'invoice_id', 'manually_matched')
    # def _compute_is_available(self):
    #     for record in self:
    #         if record.fatura_onay_statu != '1' or not record.invoice_id or not record.manually_matched:
    #             record.is_available = False
    #         else:
    #             record.is_available = True

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
                if record.invoice_id.gelen_fatura_id:
                    raise UserError(_("Bu fatura zaten eşleştirilmiş!"))

    @api.depends('fatura_pdf')
    def _compute_fatura_pdf_preview(self):
        for record in self:
            if record.fatura_pdf:
                pdf_url = "/web/content/%s?download=false" % record.fatura_pdf.id
                record.fatura_pdf_preview = (
                    '<iframe src="%s" style="width:100%%; min-height:900px; border:1px solid #dcdcdc;"></iframe>'
                    % pdf_url
                )
            else:
                record.fatura_pdf_preview = False

    @api.depends('so_number_from_xml')
    def _compute_ref_po_id(self):
        for record in self:
            if record.so_number_from_xml:
                record.ref_po_id = self.env['purchase.order'].search([('name', '=', record.so_number_from_xml)], limit=1)

    @api.depends('waybill_number_from_xml')
    def _compute_ref_in_receipt_id(self):
        for record in self:
            if record.waybill_number_from_xml:
                record.ref_in_receipt_id = self.env['stock.picking'].search([('name', '=', record.waybill_number_from_xml)], limit=1)

    def action_create_supplier_invoice(self):
        self.ensure_one()

        existing_out_invoice = self.env['account.move'].search([('gelen_fatura_id', '=', self.id)], limit=1)
        if existing_out_invoice:
            self.invoice_will_be_created = False
            self.invoice_created = True
            self.invoice_creation_date_time = existing_out_invoice.create_date
            self.invoice_id = existing_out_invoice.id
            self.invoice_creation_error_details = "Bu faturaya ait bir tedarikçi faturası zaten oluşturulmuş!"
            
            raise UserError(_("Bu faturaya ait bir tedarikçi faturası zaten oluşturulmuş!"))
            # return {
            #     'type': 'ir.actions.client',
            #     'tag': 'display_notification',
            #     'params': {
            #         'type': 'info',
            #         'message': _('Bu faturaya ait bir tedarikçi faturası zaten oluşturulmuş!'),
            #         'sticky': False
            #     }
            # }
        
        purchase_order = self.ref_po_id

        invoice_lines = []
        for line in self.invoice_line_ids:
            line_vals = {
                'company_id': self.company_id.id,
                'product_id': line.product_id.id,
                'quantity': line.quantity,
                'price_unit': line.price_unit,
                'account_id': line.account_id.id,
                'tax_ids': [(6, 0, [line.tax_id.id])] if line.tax_id else [],
                'tevkifat_kodu': line.tevkifat_kodu.id if line.tevkifat_kodu else False,
                'istisna_kodu': line.istisna_kodu.id if line.istisna_kodu else False,
                'ihrac_kayit_kodu': line.ihrac_kayit_kodu.id if line.ihrac_kayit_kodu else False,
                'gelen_fatura_line_id': line.id,
            }
            # if not line.eslestirme_id and line.product_id:
            #     line_vals['product_id'] = line.product_id.id

            if line.ref_po_line_id:
                line_vals['purchase_line_id'] = line.ref_po_line_id.id

            if line.gelen_fatura_id.ref_po_id:
                line_vals['purchase_order_id'] = line.gelen_fatura_id.ref_po_id.id

            invoice_lines.append((0, 0, line_vals))

        invoice_vals = {
            'fatura_no': self.name,
            'partner_id': self.supplier_id.id,
            'invoice_origin': self.name,
            'move_type': 'in_invoice',  # Tedarikçi faturası için
            'invoice_line_ids': invoice_lines,
            'invoice_date': self.belge_tarihi,
            'date': self.belge_tarihi,
            'invoice_date_due': self.son_odeme_tarihi,
            'currency_id': self.odenecek_tutar_doviz_cinsi.id,
            'ref': self.ref_po_id.name if self.ref_po_id else False,
            'gelen_fatura_id': self.id,  # Eğer account.move modelinde gelen fatura alanı varsa
            'ekli_belge_id': self.fatura_pdf.id if self.fatura_pdf else False,
        }

        # Faturayı oluşturuyoruz
        invoice = self.env['account.move'].create(invoice_vals)

        if purchase_order:
            purchase_order.write({'invoice_ids': [(4, invoice.id)]})

        # mdx.gelen.fatura kaydımızın invoice_id alanını güncelliyoruz
        self.write({
            'invoice_id': invoice.id,
            'invoice_created': True,
            'invoice_creation_date_time': fields.Datetime.now(),
            'invoice_will_be_created': False,
        })

        # Oluşturulan faturayı formda görüntülemek için ilgili action'ı döndürüyoruz
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'target': 'current',
            'res_id': invoice.id,
        }
        
    @api.constrains('controlled')
    def _check_controlled(self):
        for record in self:
            if record.controlled:
                if not all(line.match_record for line in record.invoice_line_ids):
                    raise ValidationError(_("Fatura satırlarının eşleşme durumunu kontrol ediniz!"))
                else:
                    if any(line.create_product for line in record.invoice_line_ids):
                        return {
                            'type': 'ir.actions.client',
                            'tag': 'display_notification',
                            'params': {
                                'type': 'info',
                                'message': _('Fatura satırlarında otomatik ürün oluşturulacak satırlar var!'),
                                'sticky': False
                            }
                        }

    def _auto_create_products(self):
        for rec in self:
            if rec.controlled:

                if not rec.invoice_line_ids:
                    continue

                if rec.invoice_created:
                    continue

                if not all(line.match_record for line in rec.invoice_line_ids):
                    raise UserError(_("Fatura satırlarının eşleşme durumunu kontrol ediniz!"))
                
                if not rec.supplier_id:
                    raise UserError(_("Lütfen tedarikçi seçiniz!"))
                
                for line in rec.invoice_line_ids:
                    if line.supplierinfo_id and line.product_id:
                        line.supplierinfo_id.write({
                            'price': line.price_unit,
                            'currency_id': rec.odenecek_tutar_doviz_cinsi.id,
                            'min_qty': line.quantity,
                        })

                    if line.create_product and not line.product_id and line.account_id:
                        product = self.env['product.product'].create({
                            'name': line.supplier_product_name,
                            'default_code': line.supplier_product_code,
                            'type': 'consu',
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
                            'price': line.price_unit,
                            'currency_id': self.odenecek_tutar_doviz_cinsi.id,
                            'min_qty': line.quantity,
                            'delay': 0,
                            'sequence': 0,
                        })
                        line.write({
                            'supplierinfo_id': supplierinfo.id,
                            'create_supplierinfo': False,
                        })

    @api.model_create_multi
    def create(self, vals_list):
        records = super(MdxGelenFatura, self).create(vals_list)
        records._sync_responsible_users()
        for record in records:
            if record.fatura_senaryo.code != 'TICARIFATURA':
                record.fatura_onay_statu = '-1'
            else:
                record.fatura_onay_statu = '0'
                try:
                    record.refresh_gelen_fatura_api_response()
                except Exception as e:
                    import logging
                    _logger = logging.getLogger(__name__)
                    _logger.warning("Gelen fatura API yaniti alinamadi (olusturma sirasinda): %s", str(e))
        # records._auto_create_products()
        return records

    def write(self, vals):
        for record in self:
            if record.invoice_created:
                blocked_fields = {'supplier_id', 'ref_po_id', 'invoice_line_ids'}
                if any(field in vals for field in blocked_fields):
                    raise UserError(_("Fatura oluşturulduktan sonra bu alanlar değiştirilemez!"))
            if record.manually_matched and record.invoice_id:
                record.invoice_id.gelen_fatura_id = record.id
                record.invoice_id.fatura_no = record.name
                record.invoice_id.invoice_origin = record.name
                record.invoice_will_be_created = False
                record.invoice_created = False
                record.invoice_creation_date_time = False
                record.invoice_creation_error_details = False
            
        res = super(MdxGelenFatura, self).write(vals)
        if not self.env.context.get('skip_responsible_sync') and any(k in vals for k in ('supplier_id', 'gonderen_vkn_tckn')):
            self._sync_responsible_users()
        self._auto_create_products()
        return res

    @api.depends('gonderen_vkn_tckn')
    def _compute_supplier_id(self):
        for record in self:
            supplier = record.env['res.partner'].search([
                ('vat', '=', record.gonderen_vkn_tckn),
                ('is_supplier', '=', True)
            ], limit=1)

            if supplier:
                record.supplier_id = supplier.id
            else:
                supplier = record.env['res.partner'].search([
                    ('vat', '=', record.gonderen_vkn_tckn),
                    ('is_supplier', '=', False)
                ], limit=1)
                
                if supplier:
                    supplier.write({'is_supplier': True})
                    record.supplier_id = supplier.id
                    # Not: Aşağıdaki return blokları compute içinde çalışmaz, kaldırıldı

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

        if not self.fatura_xml or not self.fatura_xml.datas:
            raise UserError(_("XML eki bulunamadı!"))

        xml_data = base64.b64decode(self.fatura_xml.datas).decode('utf-8')
        root = ET.fromstring(xml_data)
        ns = {
            'cbc': "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
            'cac': "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
        }

        def _node_text(node, path):
            if node is None:
                return ""
            found = node.find(path, ns)
            return (found.text or "").strip() if found is not None else ""

        accounting_supplier_party = root.find('.//cac:AccountingSupplierParty/cac:Party', ns)
        postal_address = accounting_supplier_party.find('./cac:PostalAddress', ns) if accounting_supplier_party is not None else None
        contact = accounting_supplier_party.find('./cac:Contact', ns) if accounting_supplier_party is not None else None

        street_name = _node_text(postal_address, './cbc:StreetName')
        building_name = _node_text(postal_address, './cbc:BuildingName')
        building_number = _node_text(postal_address, './cbc:BuildingNumber')
        city_subdivision_name = _node_text(postal_address, './cbc:CitySubdivisionName')
        city_name = _node_text(postal_address, './cbc:CityName')
        postal_zone = _node_text(postal_address, './cbc:PostalZone')
        country_name = _node_text(postal_address, './cac:Country/cbc:Name')
        country_code = _node_text(postal_address, './cac:Country/cbc:IdentificationCode')
        telephone = _node_text(contact, './cbc:Telephone')
        electronic_mail = _node_text(contact, './cbc:ElectronicMail')

        # 3. YENİ TEDARİKÇİ OLUŞTURMA
        partner_address = " ".join(part for part in (street_name, building_name, building_number) if part)

        country = self.env['res.country']
        country_rec = country.browse()
        if country_code:
            country_rec = country.search([('code', '=', country_code.upper())], limit=1)
        if not country_rec and country_name:
            country_rec = country.search([('name', 'ilike', country_name)], limit=1)

        state_domain = [('name', 'ilike', city_name or city_subdivision_name)]
        if country_rec:
            state_domain.append(('country_id', '=', country_rec.id))
        state_id = self.env['res.country.state'].search(state_domain, limit=1).id if (city_name or city_subdivision_name) else False

        self.logging_field1 = country_rec.id
        self.logging_field2 = state_id

        partner_vals = {
            'manually_created_from_gelen_fatura_id': self.id,
            'vat': self.gonderen_vkn_tckn,
            'name': self.satici_unvan,
            'supplier_rank': 1,
            'company_type': 'company',
            'country_id': country_rec.id,
            'street': partner_address,
            'state_id': state_id,
            'city': city_name or city_subdivision_name,
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
    
    def action_search_incoming_invoice(self):
        self.env['mdx.utility.mixin'].search_incoming_invoices()

    @api.model
    def process_pending_attachments_gelen_fatura(self, *args, **kwargs):
        pending_html = self.search([('fatura_html', '=', False)])
        for invoice in pending_html:
            try:
                self.env['mdx.utility.mixin'].get_incoming_invoice_html(invoice.ettn)
            except Exception as e:
                invoice.write({'attachment_error_details': f"HTML işleme hatası: {str(e)}"})
        
        pending_pdf = self.search([('fatura_pdf', '=', False)])
        for invoice in pending_pdf:
            try:
                self.env['mdx.utility.mixin'].get_incoming_invoice_pdf(invoice.ettn)
            except Exception as e:
                invoice.write({'attachment_error_details': f"PDF işleme hatası: {str(e)}"})
        
        pending_xml = self.search([('fatura_xml', '=', False)])
        for invoice in pending_xml:
            try:
            # Her kaydı ayrı bir savepoint içinde işleyerek hata durumunda rollback yapıyoruz.
                with self.env.cr.savepoint():
                    self.env['mdx.utility.mixin'].get_incoming_invoice_xml(invoice.ettn)
            except Exception as e:
                invoice.write({'attachment_error_details': f"XML işleme hatası: {str(e)}"})

    # @api.model
    # def process_create_out_invoices_gelen_fatura(self):
    #     self.env['mdx.utility.mixin'].create_out_invoices()
    
    def _compute_is_editable(self):
        for record in self:
            record.is_editable = not record.invoice_created

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
    @api.constrains('invoice_will_be_created', 'controlled', 'supplier_id', 'invoice_line_ids', 'fatura_onay_statu')
    def _check_invoice_creation(self):
        for record in self:
            if record.invoice_will_be_created:
                if not record.controlled:
                    raise ValidationError(_("Fatura oluşturma işlemi için önce kontrol tamamlanmalı!"))
                if not record.supplier_id:
                    raise ValidationError(_("Lütfen tedarikçi seçiniz!"))
                if not record.invoice_line_ids:
                    raise ValidationError(_("En az bir fatura satırı eklenmelidir!"))
                # if record.fatura_onay_statu == '0':
                #     raise ValidationError(_("Fatura kabul/red işlemi bekleniyor!"))

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

    def process_create_out_invoices_gelen_fatura(self):
        for record in self.filtered(lambda r: r.invoice_will_be_created and not r.invoice_created):
            try:
                # Fatura oluşturma işlemleri burada yapılacak
                # Örnek: record._create_invoice()
                self.env['mdx.utility.mixin'].create_out_invoices()
                record.invoice_created = True
                record.invoice_will_be_created = False
                record.invoice_creation_date_time = datetime.now()
            except Exception as e:
                record.invoice_creation_error_details = str(e)
                raise UserError(_("Fatura oluşturma hatası: %s") % e)

    def action_view_pdf_attachment(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s' % self.fatura_pdf.id,
            'target': 'new',
        }

    def refresh_gelen_fatura_api_response(self):
        for record in self:
            try:
                self.env['mdx.utility.mixin'].check_gelen_fatura_status(record, record.ettn)

                if record.fatura_onay_statu == '2':
                    record.invoice_will_be_created = False
            except Exception as e:
                raise UserError(f"API yanıtı alınırken hata oluştu, Lütfen daha sonra tekrar deneyin.\nHata: {str(e)}")
            
    def accept_gelen_fatura(self):
        for record in self:
            if self.fatura_senaryo.code == 'TICARIFATURA' and self.fatura_onay_statu == '0':
                try:
                    self.env['mdx.utility.mixin'].response_gelen_fatura(record, 'KABUL', self.kabul_red_aciklama)
                    # self.refresh_gelen_fatura_api_response()
                except Exception as e:
                    raise UserError(f"API yanıtı alınırken hata oluştu, Lütfen daha sonra tekrar deneyin.\nHata: {str(e)}")
            else:
                raise UserError(_("Kabul işlemi için gerekli koşullar sağlanmıyor!"))
                
    def reject_gelen_fatura(self):
        for record in self:
            if self.fatura_senaryo.code == 'TICARIFATURA' and self.fatura_onay_statu == '0':
                try:
                    self.env['mdx.utility.mixin'].response_gelen_fatura(record, 'RED', self.kabul_red_aciklama)
                    # self.refresh_gelen_fatura_api_response()
                except Exception as e:
                    raise UserError(f"API yanıtı alınırken hata oluştu, Lütfen daha sonra tekrar deneyin.\nHata: {str(e)}")
            else:
                raise UserError(_("Red işlemi için gerekli koşullar sağlanmıyor!"))

    # =========================================================================
    # CRON: Gelen Fatura Durum Bildirimi (Her gece 00:00)
    # =========================================================================
    @api.model
    def _cron_send_pending_approval_notification(self):
        """
        Her gece 00:00'da çalışır.
        Onay bekleyen ve reddedilen gelen faturaların durumunu,
        tedarikçinin Satınalma Alıcısının (buyer_id) e-posta
        adresine bildirir.

        Sadece şu durumlar dahil:
        - '0'  Yanıt Bekleniyor (Onay Bekleyen)
        - '1'  Reddedildi
        """
        import logging
        _logger = logging.getLogger(__name__)

        # 1. Onay bekleyen veya reddedilen faturaları bul
        all_invoices = self.search([
            ('supplier_id', '!=', False),
            ('fatura_onay_statu', 'in', ['0', '1']),
        ])

        if not all_invoices:
            _logger.info("Gelen Fatura Bildirim: Bildirilecek fatura bulunamadı.")
            return

        _logger.info("Gelen Fatura Bildirim: %d adet fatura bulundu.", len(all_invoices))

        # 2. Tedarikçiye göre grupla
        from collections import defaultdict
        supplier_invoices = defaultdict(lambda: self.env['mdx.gelen.fatura'])
        no_email_invoices = self.env['mdx.gelen.fatura']

        for inv in all_invoices:
            supplier = inv.supplier_id
            # Tedarikçinin Satınalma > Alıcı (buyer_id) kontağının emailini al
            partner = supplier.commercial_partner_id or supplier
            buyer = partner.buyer_id  # res.users (Satınalma Alıcısı)
            buyer_email = buyer.email if buyer else None
            if buyer_email:
                # Alıcıya göre grupla (aynı alıcının farklı tedarikçileri olabilir)
                supplier_invoices[(partner, buyer)] |= inv
            else:
                no_email_invoices |= inv

        # 3. E-posta adresi olmayan tedarikçiler için fallback
        if no_email_invoices:
            fallback_email = self.env['ir.config_parameter'].sudo().get_param(
                'edonusum.gelen_fatura_fallback_email', default=''
            )
            suppliers_without_buyer = set(no_email_invoices.mapped('supplier_id.name'))
            if fallback_email:
                _logger.info(
                    "Gelen Fatura Bildirim: %d adet faturanın tedarikçisinde Alıcı (buyer_id) veya e-posta yok. "
                    "Fallback adrese (%s) gönderilecek. Tedarikçiler: %s",
                    len(no_email_invoices), fallback_email, ', '.join(suppliers_without_buyer)
                )
                self._send_pending_approval_email(
                    email_to=fallback_email,
                    recipient_name="İlgili Yetkililer",
                    invoices=no_email_invoices,
                )
            else:
                _logger.warning(
                    "Gelen Fatura Bildirim: %d adet faturanın tedarikçisinde Alıcı (buyer_id) tanımlı değil "
                    "veya Alıcının e-postası boş. Fallback e-posta da ayarlanmamış. "
                    "(Ayarlar > Teknik > Parametreler: edonusum.gelen_fatura_fallback_email) Tedarikçiler: %s",
                    len(no_email_invoices), ', '.join(suppliers_without_buyer)
                )

        # 4. Her tedarikçinin alıcısına bekleyen/reddedilen faturalarını mail ile gönder
        for (supplier, buyer), invoices in supplier_invoices.items():
            try:
                self._send_pending_approval_email(
                    email_to=buyer.email,
                    recipient_name=buyer.name,
                    invoices=invoices,
                )
                _logger.info(
                    "Gelen Fatura Bildirim: %s (Alıcı: %s - %s) adresine %d adet fatura bildirimi gönderildi.",
                    supplier.name, buyer.name, buyer.email, len(invoices)
                )
            except Exception as e:
                _logger.error(
                    "Gelen Fatura Bildirim: %s (Alıcı: %s - %s) adresine mail gönderilemedi. Hata: %s",
                    supplier.name, buyer.name, buyer.email, str(e)
                )

    def _send_pending_approval_email(self, email_to, recipient_name, invoices):
        """Onay bekleyen fatura özet mailini tedarikçiye gönderir."""
        from datetime import date as date_cls

        today = date_cls.today()

        # Fatura satırlarını HTML tablo olarak oluştur
        rows_html = ""
        total_amount = 0.0
        for inv in invoices.sorted(key=lambda r: r.belge_tarihi or date_cls.min):
            belge_no = inv.name or "-"
            tedarikci = inv.satici_unvan or (inv.supplier_id.name if inv.supplier_id else "-")
            belge_tarihi = inv.belge_tarihi.strftime('%d.%m.%Y') if inv.belge_tarihi else "-"
            son_odeme = inv.son_odeme_tarihi.strftime('%d.%m.%Y') if inv.son_odeme_tarihi else "-"
            tutar = inv.odenecek_tutar or 0.0
            doviz = inv.odenecek_tutar_doviz_cinsi.name if inv.odenecek_tutar_doviz_cinsi else "TRY"
            total_amount += tutar

            # Vade geçmiş mi kontrol et
            vade_style = ""
            vade_icon = ""
            if inv.son_odeme_tarihi and inv.son_odeme_tarihi < today:
                vade_style = "color: #dc2626; font-weight: bold;"
                vade_icon = " ⚠️"

            # Fatura durumunu belirle
            durum_map = {
                '-1': ('Yanıt Gerekmiyor', '#6b7280', '➖'),
                '0': ('Yanıt Bekleniyor', '#d97706', '⏳'),
                '1': ('Reddedildi', '#dc2626', '❌'),
                '2': ('Kabul Edildi', '#059669', '✅'),
            }
            durum_info = durum_map.get(inv.fatura_onay_statu or '', ('Bilinmiyor', '#6b7280', '—'))
            durum_text = f"{durum_info[2]} {durum_info[0]}"
            durum_color = durum_info[1]

            rows_html += f"""
            <tr>
                <td style="padding: 8px 12px; border-bottom: 1px solid #e5e7eb;">{belge_no}</td>
                <td style="padding: 8px 12px; border-bottom: 1px solid #e5e7eb;">{tedarikci}</td>
                <td style="padding: 8px 12px; border-bottom: 1px solid #e5e7eb;">{belge_tarihi}</td>
                <td style="padding: 8px 12px; border-bottom: 1px solid #e5e7eb; {vade_style}">{son_odeme}{vade_icon}</td>
                <td style="padding: 8px 12px; border-bottom: 1px solid #e5e7eb; text-align: right;">{tutar:,.2f} {doviz}</td>
                <td style="padding: 8px 12px; border-bottom: 1px solid #e5e7eb; text-align: center; color: {durum_color}; font-weight: 600;">{durum_text}</td>
            </tr>"""

        # Vade geçmiş fatura sayısı
        overdue_count = len(invoices.filtered(
            lambda i: i.son_odeme_tarihi and i.son_odeme_tarihi < today
        ))

        overdue_warning = ""
        if overdue_count:
            overdue_warning = f"""
            <div style="background: #fef2f2; border-left: 4px solid #dc2626; padding: 12px 16px; margin: 16px 0; font-size: 14px; color: #991b1b;">
                ⚠️ <strong>{overdue_count} adet faturanın vadesi geçmiştir!</strong> Lütfen öncelikli olarak kontrol ediniz.
            </div>"""

        # Base URL
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', default='')

        body_html = f"""
        <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 800px; margin: 0 auto; background: #ffffff;">

            <div style="background: #4a1942; padding: 20px 30px; border-radius: 8px 8px 0 0;">
                <h2 style="color: #ffffff; margin: 0; font-size: 18px;">
                    📄 Gelen Fatura Durum Raporu
                </h2>
                <p style="color: #d8b4fe; margin: 5px 0 0; font-size: 13px;">
                    {today.strftime('%d.%m.%Y')} tarihli günlük bildirim
                </p>
            </div>

            <div style="padding: 24px 30px;">
                <p style="font-size: 15px; color: #333;">
                    Sayın <strong>{recipient_name}</strong>,
                </p>
                <p style="font-size: 14px; color: #555; line-height: 1.6;">
                    Aşağıda <strong>{len(invoices)} adet</strong> gelen faturanızın
                    güncel durumu yer almaktadır.
                </p>

                {overdue_warning}

                <table style="width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 13px;">
                    <thead>
                        <tr style="background: #4a1942; color: #ffffff;">
                            <th style="padding: 10px 12px; text-align: left;">Belge No</th>
                            <th style="padding: 10px 12px; text-align: left;">Tedarikçi</th>
                            <th style="padding: 10px 12px; text-align: left;">Belge Tarihi</th>
                            <th style="padding: 10px 12px; text-align: left;">Vade Tarihi</th>
                            <th style="padding: 10px 12px; text-align: right;">Tutar</th>
                            <th style="padding: 10px 12px; text-align: center;">Durum</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                    <tfoot>
                        <tr style="background: #f3f4f6; font-weight: bold;">
                            <td colspan="4" style="padding: 10px 12px;">
                                Toplam: {len(invoices)} fatura
                            </td>
                            <td style="padding: 10px 12px; text-align: right;">{total_amount:,.2f}</td>
                            <td></td>
                        </tr>
                    </tfoot>
                </table>

                <div style="text-align: center; margin: 24px 0;">
                    <a href="{base_url}/odoo/gelen-fatura"
                       style="display: inline-block; background: #4a1942; color: #fff; padding: 12px 28px;
                              border-radius: 6px; text-decoration: none; font-size: 14px; font-weight: 600;">
                        📋 Gelen Faturalara Git
                    </a>
                </div>

                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">
                <p style="font-size: 11px; color: #9ca3af; text-align: center;">
                    Bu e-posta MindDX Lokalizasyon modülü tarafından otomatik olarak gönderilmiştir.<br>
                    Bildirim ayarlarını değiştirmek için sistem yöneticinize başvurunuz.
                </p>
            </div>
        </div>
        """

        # Mail gönder
        mail_values = {
            'subject': f"📄 Gelen Fatura Durum Raporu — {len(invoices)} adet ({today.strftime('%d.%m.%Y')})",
            'body_html': body_html,
            'email_to': email_to,
            'email_from': self.env.company.email or self.env['ir.mail_server'].sudo().search([], limit=1).smtp_user or 'noreply@minddx.com',
            'auto_delete': True,
        }
        mail = self.env['mail.mail'].sudo().create(mail_values)
        mail.send()
