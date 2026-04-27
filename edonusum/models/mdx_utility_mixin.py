import binascii
import io
import json
import traceback
import zipfile
import subprocess
import tempfile
import os

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

# from googletrans import Translator
import hashlib
import base64
import uuid
import time
from datetime import datetime, date
import requests
import re
from pytz import timezone
from lxml import etree
import xml.etree.ElementTree as ET
import logging
_logger = logging.getLogger(__name__)

class MdxUtilityMixin(models.AbstractModel):
    _name = "mdx.utility.mixin"
    _description = "Utility Functions for Odoo"

    # @staticmethod
    # def check_license(self):
    #     """
    #     Check if the license is active.
    #     """
    #     config = self.env['ir.config_parameter'].sudo()
    #     is_active = config.get_param('edonusum.is_edonusum_license_active', default='False')
    #     if is_active != 'True':
    #         raise UserError("MindDX lokalizasyon(edonusum) lisansı aktif değil. Bu işlemi gerçekleştiremezsiniz.")

    @staticmethod
    def generate_uuid():
        """
        Generate a unique UUID in Odoo.
        """
        return str(uuid.uuid4())

    @staticmethod
    def base64_encode(data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        return base64.b64encode(data).decode("utf-8")

    @staticmethod
    def base64_decode(data):
        return base64.b64decode(data).decode("utf-8")

    @staticmethod
    def calculate_md5(data):
        md5_hash = hashlib.md5(data.encode("utf-8")).hexdigest()
        return md5_hash

    @staticmethod
    def find_zip_codes(data):
        return re.findall(r"\b\d{5}\b", data)

    @staticmethod
    def number_to_words(number):
        """
        Convert a number into its Turkish word representation.
        :param number: Integer or float.
        :return: String representation in Turkish words.
        """

        def ones_and_tens_to_words(num, scale=""):
            ones = [
                "",
                "Bir",
                "İki",
                "Üç",
                "Dört",
                "Beş",
                "Altı",
                "Yedi",
                "Sekiz",
                "Dokuz",
            ]
            tens = [
                "",
                "On",
                "Yirmi",
                "Otuz",
                "Kırk",
                "Elli",
                "Altmış",
                "Yetmiş",
                "Seksen",
                "Doksan",
            ]
            hundreds = [
                "",
                "Yüz",
                "İkiYüz",
                "ÜçYüz",
                "DörtYüz",
                "BeşYüz",
                "AltıYüz",
                "YediYüz",
                "SekizYüz",
                "DokuzYüz",
            ]

            result = []
            num_str = str(num).zfill(3)
            result.append(hundreds[int(num_str[0])])
            result.append(tens[int(num_str[1])])
            result.append(ones[int(num_str[2])])

            if scale:
                if num > 1 or scale == "Bin":
                    result.append(scale)

            return "".join([word for word in result if word])

        if not isinstance(number, (int, float)):
            raise ValueError("Input must be an integer or float.")

        number_str = f"{number:.2f}".split(".")
        whole_part = int(number_str[0])
        fraction_part = int(number_str[1]) if len(number_str) > 1 else 0

        words = []
        if whole_part >= 1_000_000_000:
            billions = whole_part // 1_000_000_000
            words.append(ones_and_tens_to_words(billions, scale="Milyar"))
            whole_part %= 1_000_000_000

        if whole_part >= 1_000_000:
            millions = whole_part // 1_000_000
            words.append(ones_and_tens_to_words(millions, scale="Milyon"))
            whole_part %= 1_000_000

        if whole_part >= 1_000:
            thousands = whole_part // 1_000
            words.append(ones_and_tens_to_words(thousands, scale="Bin"))
            whole_part %= 1_000

        words.append(ones_and_tens_to_words(whole_part))

        if fraction_part > 0:
            words.append(ones_and_tens_to_words(fraction_part))

        return "".join(words)

    def generate_note_for_invoice(self, invoice_record):
        total_note = invoice_record.amount_total
        # Format to 4 decimal places and split
        formatted_total = "{:.4f}".format(total_note)
        parts = formatted_total.split('.')
        whole_part = int(parts[0])
        fraction_part_str = parts[1].rstrip('0')  # Remove trailing zeros
        fraction_part = int(fraction_part_str) if fraction_part_str else 0

        # Get all active currencies
        currency_units = {
            cur.name: (
                "".join(
                    [
                        x[0].upper() + x[1:]
                        for x in (
                            cur.currency_unit_label_efatura or cur.full_name
                        ).split(" ")
                    ]
                ),
                cur.currency_subunit_label_efatura or cur.currency_subunit_label,
            )
            for cur in self.env["res.currency"].search([("active", "=", True)])
        }

        # Default values for units
        currency = invoice_record.currency_id
        currency_code = currency.name
        upper_unit, lower_unit = currency_units.get(
            currency_code, (currency_code, "AltBirim")
        )

        # Convert amounts to words
        note = self.number_to_words(whole_part)
        note_fraction = self.number_to_words(fraction_part) if fraction_part > 0 else None

        # Construct the final note
        if whole_part and fraction_part:
            final_note = f"Yalnız: {note} {upper_unit} {note_fraction} {lower_unit}"
        elif whole_part:
            final_note = f"Yalnız: {note} {upper_unit}"
        elif fraction_part:
            final_note = f"Yalnız: {note_fraction} {lower_unit}"
        else:
            final_note = f"Yalnız: Sıfır {upper_unit}"

        # Add exchange rate note for non-TRY currencies
        if currency_code != "TRY":
            exchange_rate = invoice_record.invoice_currency_inverse_rate or 1.0
            home_currency_unit = self.env.company.currency_id.full_name
            home_currency_subunit = self.env.company.currency_id.currency_subunit_label
            home_currency_code = self.env.company.currency_id.name
            final_note += f" (1 {currency_code} = {exchange_rate:.4f} {home_currency_code})"

        return final_note

    @staticmethod
    def generate_xml(self, root_tag, child_tag, items):
        """
        Generate an XML string based on the given parameters.

        :param root_tag: Root tag name for the XML.
        :param child_tag: Tag name for child elements.
        :param items: A list of dictionaries containing child attributes and elements.
        :return: A formatted XML string.
        """
        # MdxUtilityMixin.check_license(self)

        # XML root element
        root = etree.Element(root_tag)

        # Add child elements
        for item in items:
            child = etree.SubElement(root, child_tag, id=str(item.get("id", "")))
            for key, value in item.items():
                if key != "id":  # Skip the `id` attribute as it's already added
                    element = etree.SubElement(child, key)
                    element.text = str(value)

        # Convert XML to a string
        xml_string = etree.tostring(
            root, pretty_print=True, encoding="UTF-8", xml_declaration=True
        ).decode("UTF-8")

        return xml_string

    def generate_invoice_xml(self, invoice_record, preview_mode=False):
        # MdxUtilityMixin.check_license(self)

        for invoice_record in invoice_record.with_context(lang="tr_TR"):

            # E-Fatura Alan Kontrolleri
            # Recordset karşılaştırması context farklılıklarından etkilenebilir, bu yüzden .id ile karşılaştırıyoruz
            fatura_seri_ebelge_turu_id = invoice_record.fatura_seri_id.ebelge_turu_id.id if invoice_record.fatura_seri_id and invoice_record.fatura_seri_id.ebelge_turu_id else False
            efatura_turu_id = invoice_record.efatura_turu_id.id if invoice_record.efatura_turu_id else False
            if fatura_seri_ebelge_turu_id != efatura_turu_id:
                raise UserError(
                    f"Fatura serisi ve e-fatura türü arasında uyumsuzluk var! "
                    f"Fatura Seri E-Belge Türü: {invoice_record.fatura_seri_id.ebelge_turu_id.code if invoice_record.fatura_seri_id and invoice_record.fatura_seri_id.ebelge_turu_id else 'N/A'}, "
                    f"E-Fatura Türü: {invoice_record.efatura_turu_id.code if invoice_record.efatura_turu_id else 'N/A'}. Lütfen kontrol edin."
                )

            # Calculate issue date
            issue_date = invoice_record.invoice_date or datetime.today().date()
            issue_date_str = issue_date.strftime("%Y-%m-%d")

            # Generate invoice number
            fatura_seri_id = invoice_record.fatura_seri_id
            if not fatura_seri_id:
                # Preview modunda değilsek hata ver, preview ise geçici no ata
                if not preview_mode:
                     invoice_record.write({"fatura_no": ""})
                     raise UserError("Fatura serisi bulunamadı! Lütfen fatura serisini kontrol edin.")
            
            # Seri ilk kez mi kullanılıyor?
            invoice_with_serial = self.env["account.move"].search(
                [
                    ("fatura_seri_id", "=", fatura_seri_id.id),
                    ("state", "in", ["draft", "posted"]),
                ],
                limit=1,
            )

            if not invoice_with_serial:
                fatura_seri_last_used_date = issue_date
            else:
                fatura_seri_last_used_date = (
                    fatura_seri_id.last_used_date or datetime.today().date()
                )

            fatura_seri_last_used_date_str = fatura_seri_last_used_date.strftime(
                "%Y-%m-%d"
            )

            if fatura_seri_last_used_date > issue_date:
                if not preview_mode:
                    raise ValueError(f"Fatura serisinde sonraki tarihli fatura bulunmaktadır! Serideki son kullanılan tarih: {fatura_seri_last_used_date_str} - Fatura tarihi: {issue_date_str}")

            eski_fatura_no = invoice_record.fatura_no
            fatura_seri_code = fatura_seri_id.code
            year = issue_date_str.split("-")[0]

            time_now = datetime.now().time()
            issue_time_str = (
                f"{str(time_now.hour).zfill(2)}:{str(time_now.minute).zfill(2)}:{str(time_now.second).zfill(2)}"
            )

            if eski_fatura_no and eski_fatura_no.startswith(fatura_seri_code):
                fatura_no = eski_fatura_no
            else:
                if not preview_mode:
                    # Bu yıl içinde bu seri ilk kez mi kullanılıyor?
                    current_year = issue_date.year
                    invoice_with_serial_in_year = self.env["account.move"].search(
                        [
                            ("fatura_seri_id", "=", fatura_seri_id.id),
                            ("state", "in", ["draft", "posted"]),
                            ("invoice_date", ">=", f"{current_year}-01-01"),
                            ("invoice_date", "<=", f"{current_year}-12-31"),
                        ],
                        limit=1,
                    )

                    if not invoice_with_serial_in_year:
                        # Bu yıl ilk kez kullanılıyor, sırayı 1'den başlat
                        fatura_seri_index = 1
                        # Seri kaydındaki index'i de 1'e çek
                        fatura_seri_id.write({"index": 1})
                    else:
                        fatura_seri_index = fatura_seri_id.index

                    fatura_seri_id.write(
                        {"index": fatura_seri_index + 1, "last_used_date": issue_date}
                    )
                    fatura_no = f"{fatura_seri_code}{year}{str(fatura_seri_index).zfill(9)}"  # Index'e 12 basamağa kadar sıfır ekliyoruz

                    invoice_record.write({"fatura_no": fatura_no})
                else:
                    fatura_no = invoice_record.name

            # expense_count = len(invoice_record.expense_sheet_id.expense_line_ids)

            # Update document counter
            document_sayac_id = self.env["mdx.dokuman.sayac"].search(
                [
                    # ('company_id', '=', invoice_record.company_id.id),
                    # ('ebelge_turu_id', '=', invoice_record.efatura_turu_id.id),
                    ("code", "=", "DOKUMANSAYAC"),
                    ("active", "=", True),
                ],
                limit=1,
            )

            if not document_sayac_id:
                raise ValueError("Giden E-Fatura sayacı bulunamadı!")

            document_counter = document_sayac_id.gonderilecek_sonraki_sira_no
            if not preview_mode:
                document_sayac_id.write(
                    {
                        "gonderilecek_sonraki_sira_no": document_counter + 1,
                        "last_used_date": issue_date,
                    }
                )

            # Prepare dynamic fields
            efatura_turu = invoice_record.efatura_turu_id.ebelge_turu_origin_id.code
            efatura_senaryo = invoice_record.efatura_senaryo_id.code
            fatura_tipi = invoice_record.fatura_tipi_id.code
            uuid = invoice_record.uuid
            if not uuid:
                uuid = self.generate_uuid()
                # WRITE İŞLEMİNİ ENGELLE
                if not preview_mode:
                    invoice_record.write({"uuid": uuid})

            xml_string = '<?xml version="1.0" encoding="utf-8"?>'
            xml_string += '<Invoice xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" xmlns:udt="urn:un:unece:uncefact:data:specification:UnqualifiedDataTypesSchemaModule:2" xmlns:ccts="urn:un:unece:uncefact:documentation:2" xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" xmlns:qdt="urn:oasis:names:specification:ubl:schema:xsd:QualifiedDatatypes-2" xmlns:ubltr="urn:oasis:names:specification:ubl:schema:xsd:TurkishCustomizationExtensionComponents" xmlns:ds="http://www.w3.org/2000/09/xmldsig#" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2 UBL-Invoice-2.1.xsd" xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2">'
            xml_string += "<ext:UBLExtensions>"
            xml_string += "<ext:UBLExtension>"
            xml_string += "<ext:ExtensionContent/>"
            xml_string += "</ext:UBLExtension>"
            xml_string += "</ext:UBLExtensions>"
            xml_string += "<cbc:UBLVersionID>2.1</cbc:UBLVersionID>"
            xml_string += "<cbc:CustomizationID>TR1.2</cbc:CustomizationID>"
            xml_string += "<cbc:ProfileID>" + efatura_senaryo + "</cbc:ProfileID>"
            xml_string += "<cbc:ID>" + fatura_no + "</cbc:ID>"
            xml_string += "<cbc:CopyIndicator>false</cbc:CopyIndicator>"
            xml_string += "<cbc:UUID>" + uuid + "</cbc:UUID>"
            xml_string += "<cbc:IssueDate>" + issue_date_str + "</cbc:IssueDate>"
            
            if invoice_record.irsaliyesiz_faturalandir:
                xml_string += "<cbc:IssueTime>" + issue_time_str + "</cbc:IssueTime>"
                
            xml_string += (
                "<cbc:InvoiceTypeCode>" + fatura_tipi + "</cbc:InvoiceTypeCode>"
            )
                    
            if efatura_turu == "EARSIV":
                # belge_gonderim_sekli: ELEKTRONIK veya KAĞIT -> KAGIT olarak normalize et
                gonderim_degeri = invoice_record.belge_gonderim_sekli or "ELEKTRONIK"
                if gonderim_degeri == "KAĞIT":
                    gonderim_degeri = "KAGIT"
                xml_string += "<cbc:Note>Gönderim Şekli:" + gonderim_degeri + "</cbc:Note>"

            if fatura_tipi == "IADE":
                bill_date = (
                    str(
                        invoice_record.iade_edilen_fatura_tarihi.strftime(
                            "%Y-%m-%d"
                        )
                    )
                    if invoice_record.iade_edilen_fatura_tarihi
                    else (
                        str(invoice_record.reversed_entry_id.invoice_date.strftime("%Y-%m-%d"))
                        if invoice_record.reversed_entry_id.invoice_date
                        else datetime.date.today().strftime("%Y-%m-%d")
                    )
                )

                fatura_no_bil = str(
                    invoice_record.iade_edilen_fatura_no
                    or invoice_record.reversed_entry_id.fatura_no
                    or invoice_record.reversed_entry_id.name
                    or ""
                )
                xml_string += (
                    "<cbc:Note>"
                    + bill_date
                    + " Tarihli, "
                    + fatura_no_bil
                    + " No'lu faturaya istinaden iade faturasıdır.</cbc:Note>"
                )
                xml_string += "<cbc:Note>Fatura Tarihi:" + bill_date + "</cbc:Note>"

            if invoice_record.irsaliyesiz_faturalandir and invoice_record.move_type == 'out_invoice':
                xml_string += "<cbc:Note>İRSALİYE YERİNE GEÇER</cbc:Note>"
            total_note = self.generate_note_for_invoice(invoice_record)
            xml_string += "<cbc:Note>" + total_note + "</cbc:Note>"

            net_kg = invoice_record.net_kg or 0.0
            brut_kg = invoice_record.net_kg or 0.0
            teslim_sarti = invoice_record.teslim_sarti_id.name or ""
            gonderim_sekli = invoice_record.gonderim_sekli_id.name or ""
            # irsaliye_no = invoice_record.irsaliye_no_id.name # TODO: Add irsaliye_no field to account.move model

            # if irsaliye_no: # TODO: Add irsaliye_no field to account.move model
            #     xml_string += '<cbc:Note>İrsaliye Bilgisi : ' + irsaliye_no + '</cbc:Note>'

            if net_kg:
                xml_string += "<cbc:Note>Net KG: " + str(net_kg) + "</cbc:Note>"
                xml_string += "<cbc:Note>Brüt KG: " + str(brut_kg) + "</cbc:Note>"
                xml_string += (
                    "<cbc:Note>Teslim Şartı: " + str(teslim_sarti) + "</cbc:Note>"
                )
                xml_string += (
                    "<cbc:Note>Taşıma Modu: " + str(gonderim_sekli) + "</cbc:Note>"
                )

            if invoice_record.fatura_aciklama:
                # Ayıraç varsa temizle
                aciklama_metni = invoice_record.fatura_aciklama
                separator = "*** EK AÇIKLAMALAR ***"
                
                if separator in aciklama_metni:
                    parts = aciklama_metni.split(separator)
                    system_part = parts[0].strip()
                    user_part = parts[1].strip()
                    
                    # Eğer kullanıcı kısmı boşsa, sadece sistem kısmını al
                    if not user_part:
                        aciklama_metni = system_part
                    # Doluysa olduğu gibi bırak (veya isterseniz ayıracı kaldırıp birleştirebilirsiniz)
                    # else: aciklama_metni = f"{system_part}\n{user_part}" 

                xml_string += (
                    "<cbc:Note>" + aciklama_metni + "</cbc:Note>"
                )

            if invoice_record.fatura_tipi_id.code == "TEVKIFAT":
                xml_string += (
                    "<cbc:Note>"
                    + str(invoice_record.line_ids[0].tevkifat_kodu.name)
                    + "</cbc:Note>"
                )
                xml_string += (
                    "<cbc:Note> Tevkifat Oranı: %"
                    + str(invoice_record.line_ids[0].tevkifat_kodu.tevkifat_orani)
                    + "</cbc:Note>"
                )

            if invoice_record.fatura_tipi_id.code == "IHRACKAYITLI":
                xml_string += "<cbc:Note> 3065 sayılı KDV Kn. hükümlerine göre ihraç edilmek şartıylateslim edildiğinden KDV tahsil edilmemiştir. </cbc:Note>"
                xml_string += (
                    "<cbc:Note>"
                    + str(invoice_record.line_ids[0].ihrac_kayit_kodu.name)
                    + "</cbc:Note>"
                )

            xml_string += (
                "<cbc:DocumentCurrencyCode>"
                + invoice_record.currency_id.name
                + "</cbc:DocumentCurrencyCode>"
            )
            xml_string += "<cbc:AccountingCost/>"
            xml_string += (
                "<cbc:LineCountNumeric>"
                + str(len(invoice_record.invoice_line_ids))
                + "</cbc:LineCountNumeric>"
            )

            # BAŞLANGIÇ: Faturayla İlişkili Sipariş ve Teslimatları Bulma Mantığı
            sale_orders = self.env['sale.order']
            pickings = self.env['stock.picking']

            # Fatura satırlarından ilgili satış siparişi satırlarını (sale.order.line) topla
            sale_order_lines = invoice_record.invoice_line_ids.mapped('sale_line_ids')

            pickings = invoice_record.picking_ids.filtered(lambda p: p.state == 'done' and p.invoice_ids in [invoice_record])

            if sale_order_lines and not pickings:
                # Satış siparişi satırlarından benzersiz satış siparişlerini (sale.order) al
                sale_orders = sale_order_lines.mapped('order_id')

                # Bu satış siparişi satırlarına bağlı olan ve "Tamamlandı" durumundaki
                # stok hareketlerini (stock.move) bul. Bu, sadece gerçekten teslim edilmiş
                # kalemlerin irsaliyelerini almamızı sağlar.
                moves = sale_order_lines.mapped('move_ids').filtered(lambda m: m.state == 'done')

                # Stok hareketlerinden ilişkili ve benzersiz teslimatları (stock.picking) al

                pickings = moves.mapped('picking_id')

            # XML'de genellikle tek bir sipariş referansı beklenir.
            # Eğer fatura birden fazla siparişi içeriyorsa, ilkini referans alıyoruz.
            sale_id = sale_orders if sale_orders else self.env['sale.order']

            # picking_id değişkeni yerine artık bir liste (recordset) olan 'pickings' kullanılacak.
            # BİTİŞ: Faturayla İlişkili Sipariş ve Teslimatları Bulma Mantığı

            if sale_id:
                xml_string += "<cac:OrderReference>"
                xml_string += "<cbc:ID>" + str(sale_id.name) + "</cbc:ID>"
                # Müşteri referansı boş olabilir, bu durumu kontrol ediyoruz.
                client_order_ref = sale_id.client_order_ref or ""
                xml_string += "<cbc:SalesOrderID>PO No: " + str(client_order_ref) + "</cbc:SalesOrderID>"
                xml_string += "<cbc:IssueDate>" + str(sale_id.date_order.strftime("%Y-%m-%d")) + "</cbc:IssueDate>"
                xml_string += "</cac:OrderReference>"

            # Bir fatura birden fazla teslimatı (irsaliyeyi) kapsayabilir.
            # Bu nedenle bulunan her bir teslimat için ayrı bir referans bloğu oluşturuyoruz.
            if pickings:
                if any(picking_id.irsaliye_no for picking_id in pickings):
                    for picking_id in pickings:
                        xml_string += "<cac:DespatchDocumentReference>"
                        if not picking_id.irsaliye_no and not invoice_record.irsaliyesiz_faturalandir:
                            raise UserError(
                                f"{picking_id.name} teslimatı için e-iraliye gönderilmemiş! Lütfen önce irsaliye gönderimini yapın."
                            )
                        xml_string += "<cbc:ID>" + str(picking_id.irsaliye_no) + "</cbc:ID>"
                        # Teslimat tarihi boş olabilir, bu durumu kontrol ediyoruz.
                        shipping_date_obj = picking_id.scheduled_date or datetime.now()
                        shipping_date = shipping_date_obj.strftime("%Y-%m-%d")
                        xml_string += "<cbc:IssueDate>" + str(shipping_date) + "</cbc:IssueDate>"
                        xml_string += "</cac:DespatchDocumentReference>"

            if invoice_record.fatura_tipi_id.code == "IADE" or invoice_record.fatura_tipi_id.code == "TEVKIFATIADE":
                xml_string += "<cac:BillingReference><cac:InvoiceDocumentReference>"
                xml_string += "<cbc:ID>" + invoice_record.iade_edilen_fatura_no + "</cbc:ID>"
                xml_string += "<cbc:IssueDate>" + str(invoice_record.iade_edilen_fatura_tarihi) + "</cbc:IssueDate>"
                xml_string += "<cbc:DocumentTypeCode>IADE</cbc:DocumentTypeCode>"
                xml_string += "</cac:InvoiceDocumentReference></cac:BillingReference>"

            # if irsaliye_no: # TODO: Add irsaliye_no field to account.move model
            #     shipping_date = invoice_record.irsaliye_no_id.shipping_date or time.strftime("%Y-%m-%d")
            #     xml_string += '<cac:DespatchDocumentReference>'
            #     xml_string += '<cbc:ID>' + str(invoice_record.irsaliye_no_id.name) + '</cbc:ID>'
            #     xml_string += '<cbc:IssueDate>' + str(shipping_date) + '</cbc:IssueDate>'
            #     xml_string += '</cac:DespatchDocumentReference>'

            company_name = invoice_record.company_id.name or ""
            company_vkn = invoice_record.company_id.vat or ""
            company_phone = invoice_record.company_id.phone or ""
            company_email = invoice_record.company_id.email or ""
            company_city = invoice_record.company_id.city or ""
            company_state = invoice_record.company_id.state_id.name or ""
            company_zip = invoice_record.company_id.zip or ""
            company_country = invoice_record.company_id.country_id.name or ""
            company_vergi_dairesi = invoice_record.company_id.vergi_dairesi or ""
            company_mersis_no = invoice_record.company_id.mersis_no or ""
            company_ticaret_sicil_no = invoice_record.company_id.ticaret_sicil_no or ""
            gumruk_ticaret_bakanligi_carisi = (
                invoice_record.company_id.gumruk_ticaret_bakanligi_carisi_id or ""
            )
            company_address = (
                invoice_record.company_id.street
                or "" + "\n" + invoice_record.company_id.street2
                or "" + "\n" + invoice_record.company_id.zip
                or ""
            )

            receiver_name = (
                invoice_record.partner_id.name
                or invoice_record.partner_id.parent_id.name
                or ""
            )
            exchange_rate = round(invoice_record.invoice_currency_inverse_rate or 1.0, 6)
            receiver_vkn = (
                invoice_record.partner_id.vat
                or invoice_record.partner_id.parent_id.name
                or ""
            )

            if invoice_record.efatura_turu_id.code == "EIHRACAT":
                receiver_vkn = gumruk_ticaret_bakanligi_carisi.vat or ""
                receiver_name = gumruk_ticaret_bakanligi_carisi.name or ""

            if efatura_turu != "EARSIV":
                xml_string += "<cac:Signature>"
                xml_string += '<cbc:ID schemeID="VKN_TCKN">' + company_vkn +'</cbc:ID>'
                xml_string += "<cac:SignatoryParty>"
                xml_string += "<cac:PartyIdentification>"
                xml_string += '<cbc:ID schemeID="VKN">' + company_vkn +'</cbc:ID>'
                xml_string += "</cac:PartyIdentification>"
                xml_string += "<cac:PostalAddress>"
                xml_string += (
                    "<cbc:CitySubdivisionName>"
                    + company_city
                    + "</cbc:CitySubdivisionName>"
                )
                xml_string += "<cbc:CityName>" + company_state + "</cbc:CityName>"
                xml_string += "<cac:Country>"
                xml_string += "<cbc:Name>" + company_country + "</cbc:Name>"
                xml_string += "</cac:Country>"
                xml_string += "</cac:PostalAddress>"
                xml_string += "</cac:SignatoryParty>"
                xml_string += "<cac:DigitalSignatureAttachment>"
                xml_string += "<cac:ExternalReference>"
                xml_string += "<cbc:URI>#Signature_" + fatura_no + "</cbc:URI>"
                xml_string += "</cac:ExternalReference>"
                xml_string += "</cac:DigitalSignatureAttachment>"
                xml_string += "</cac:Signature>"

            xml_string += "<cac:AccountingSupplierParty>"
            xml_string += "<cac:Party>"
            xml_string += "<cac:PartyIdentification>"

            web_service_vkn = ""
            if efatura_turu == "EARSIV":
                web_service_vkn = self.env['mdx.web.service'].sudo().search([
                    ('company_id', '=', invoice_record.company_id.id),
                    ('name', '=', 'EFINANS_GONDERICI_EARSIV'),
                    ('active', '=', True)], limit=1).vkn
            else:
                web_service_vkn = self.env['mdx.web.service'].sudo().search([
                    ('company_id', '=', invoice_record.company_id.id),
                    ('name', '=', 'EFINANS_GONDERICI'),
                    ('active', '=', True)], limit=1).vkn
                
            xml_string += '<cbc:ID schemeID="VKN">' + web_service_vkn + "</cbc:ID>"
            xml_string += "</cac:PartyIdentification>"
            xml_string += "<cac:PartyIdentification>"
            xml_string += (
                '<cbc:ID schemeID="TICARETSICILNO">'
                + company_ticaret_sicil_no
                + "</cbc:ID>"
            )
            xml_string += "</cac:PartyIdentification>"
            xml_string += "<cac:PartyIdentification>"
            xml_string += (
                '<cbc:ID schemeID="MERSISNO">' + company_mersis_no + "</cbc:ID>"
            )
            xml_string += "</cac:PartyIdentification>"
            xml_string += "<cac:PartyName>"
            xml_string += "<cbc:Name>" + company_name + "</cbc:Name>"
            xml_string += "</cac:PartyName>"
            xml_string += "<cac:PostalAddress>"
            xml_string += "<cbc:StreetName>" + company_address + "</cbc:StreetName>"
            xml_string += (
                "<cbc:CitySubdivisionName>"
                + company_city
                + "</cbc:CitySubdivisionName>"
            )
            xml_string += "<cbc:CityName>" + company_state + "</cbc:CityName>"
            xml_string += "<cbc:PostalZone></cbc:PostalZone>"
            xml_string += "<cbc:Region></cbc:Region>"
            xml_string += "<cac:Country>"
            xml_string += "<cbc:Name>" + company_country + "</cbc:Name>"
            xml_string += "</cac:Country>"
            xml_string += "</cac:PostalAddress>"
            xml_string += "<cac:PartyTaxScheme>"
            xml_string += "<cac:TaxScheme>"
            xml_string += "<cbc:Name>" + company_vergi_dairesi + "</cbc:Name>"
            xml_string += "</cac:TaxScheme>"
            xml_string += "</cac:PartyTaxScheme>"
            xml_string += "<cac:Contact>"
            xml_string += "<cbc:Telephone>" + company_phone + "</cbc:Telephone>"
            xml_string += "<cbc:Telefax></cbc:Telefax>"
            xml_string += (
                "<cbc:ElectronicMail>" + company_email + "</cbc:ElectronicMail>"
            )
            xml_string += "</cac:Contact>"
            xml_string += "</cac:Party>"
            xml_string += "</cac:AccountingSupplierParty>"
            xml_string += "<cac:AccountingCustomerParty>"

            # Find Billing Address (Contact)
            if invoice_record.efatura_turu_id.code == "EIHRACAT":
                if gumruk_ticaret_bakanligi_carisi:
                    billing_address_contact = self.env["res.partner"].search(
                        [
                            ("parent_id", "=", gumruk_ticaret_bakanligi_carisi.id),
                            ("type", "=", "invoice"),
                        ],
                        limit=1,
                    )
                else:
                    raise UserError(
                        "Şirket bilgilerinde Gümrük ve Ticaret Bakanlığı Carisi bilgisi bulunamadı!"
                    )

                buyer_billing_address_contact = self.env["res.partner"].search(
                    [
                        ("parent_id", "=", invoice_record.partner_id.id),
                        ("type", "=", "invoice"),
                    ],
                    limit=1,
                )
            else:
                if invoice_record.partner_id.type != "invoice":
                    billing_address_contact = self.env["res.partner"].search(
                        [
                            ("parent_id", "=", invoice_record.partner_id.id),
                            ("type", "=", "invoice"),
                        ],
                        limit=1,
                    )
                elif invoice_record.partner_id.type == "invoice":
                    billing_address_contact = invoice_record.partner_id

            # billing_address_contact = invoice_record.sale_order_id.partner_invoice_id # TODO: TEST THIS LINE

            if billing_address_contact:
                billing_address = (
                    (billing_address_contact.street or "")
                    + " "
                    + (billing_address_contact.street2 or "")
                    + " "
                    + (billing_address_contact.zip or "")
                )
                billing_address = billing_address.replace("&", " ")
                billing_city = billing_address_contact.city or ""
                billing_state = billing_address_contact.state_id.name or ""
                billing_country = billing_address_contact.country_id.name or ""
                billing_zip = billing_address_contact.zip or ""
                billing_vergi_dairesi = billing_address_contact.vergi_dairesi or ""
            else:
                if invoice_record.efatura_turu_id.code == "EIHRACAT":
                    billing_address = (
                        (gumruk_ticaret_bakanligi_carisi.street or "")
                        + " "
                        + (gumruk_ticaret_bakanligi_carisi.street2 or "")
                        + " "
                        + (gumruk_ticaret_bakanligi_carisi.zip or "")
                    )
                    billing_address = billing_address.replace("&", " ")
                    billing_city = gumruk_ticaret_bakanligi_carisi.city or ""
                    billing_state = gumruk_ticaret_bakanligi_carisi.state_id.name or ""
                    billing_country = (
                        gumruk_ticaret_bakanligi_carisi.country_id.name or ""
                    )
                    billing_zip = gumruk_ticaret_bakanligi_carisi.zip or ""
                    billing_vergi_dairesi = (
                        gumruk_ticaret_bakanligi_carisi.vergi_dairesi or ""
                    )
                else:
                    billing_address = (
                        (invoice_record.partner_id.street or "")
                        + " "
                        + (invoice_record.partner_id.street2 or "")
                        + " "
                        + (invoice_record.partner_id.zip or "")
                    )
                    billing_address = billing_address.replace("&", " ")
                    billing_city = invoice_record.partner_id.city or ""
                    billing_state = invoice_record.partner_id.state_id.name or ""
                    billing_country = invoice_record.partner_id.country_id.name or ""
                    billing_zip = invoice_record.partner_id.zip or ""
                    billing_vergi_dairesi = (
                        invoice_record.partner_id.vergi_dairesi or ""
                    )

            # if billing_address_contact.country_id.code == 'TR':
            #     receiver_vkn = billing_address_contact.vat or ""

            xml_string += "<cac:Party>"
            xml_string += "<cac:PartyIdentification>"
            if len(receiver_vkn) == 10:
                xml_string += '<cbc:ID schemeID="VKN">' + receiver_vkn + "</cbc:ID>"
            elif len(receiver_vkn) == 11:
                xml_string += '<cbc:ID schemeID="TCKN">' + receiver_vkn + "</cbc:ID>"

            xml_string += "</cac:PartyIdentification>"
            xml_string += "<cac:PartyName>"
            xml_string += "<cbc:Name>" + receiver_name + "</cbc:Name>"
            xml_string += "</cac:PartyName>"
            xml_string += "<cac:PostalAddress>"
            xml_string += "<cbc:StreetName>" + billing_address + "</cbc:StreetName>"
            xml_string += (
                "<cbc:CitySubdivisionName>"
                + billing_city
                + "</cbc:CitySubdivisionName>"
            )
            xml_string += "<cbc:CityName>" + billing_state + "</cbc:CityName>"
            xml_string += "<cac:Country>"
            xml_string += "<cbc:Name>" + billing_country + "</cbc:Name>"
            xml_string += "</cac:Country>"
            xml_string += "</cac:PostalAddress>"
            xml_string += "<cac:PartyTaxScheme>"
            xml_string += "<cac:TaxScheme>"
            xml_string += "<cbc:Name>" + billing_vergi_dairesi + "</cbc:Name>"
            xml_string += "</cac:TaxScheme>"
            xml_string += "</cac:PartyTaxScheme>"

            if len(receiver_vkn) == 11:
                # İsmi ad ve soyad olarak ayır
                name_parts = receiver_name.strip().split()
                if len(name_parts) >= 2:
                    first_name = " ".join(name_parts[:-1])
                    family_name = name_parts[-1]
                else:
                    first_name = receiver_name.strip() or "."
                    family_name = "."
                xml_string += "<cac:Person>"
                xml_string += "<cbc:FirstName>" + first_name + "</cbc:FirstName>"
                xml_string += "<cbc:FamilyName>" + family_name + "</cbc:FamilyName>"
                xml_string += "</cac:Person>"

            xml_string += "</cac:Party>"
            xml_string += "</cac:AccountingCustomerParty>"

            if invoice_record.efatura_turu_id.code == "EIHRACAT" or invoice_record.mikro_ihracat:
                buyer_billing_address_contact = self.env["res.partner"].search(
                    [
                        ("parent_id", "=", invoice_record.partner_id.id),
                        ("type", "=", "invoice"),
                    ],
                    limit=1,
                )

                buyer_name = (
                    invoice_record.partner_id.name
                    or invoice_record.partner_id.parent_id.name
                    or ""
                )
                buyer_vkn = (
                    invoice_record.partner_id.vat
                    or invoice_record.partner_id.parent_id.vat
                    or ""
                )

                if buyer_billing_address_contact:
                    buyer_billing_address = (
                        (buyer_billing_address_contact.street or "")
                        + " "
                        + (buyer_billing_address_contact.street2 or "")
                        + " "
                        + (buyer_billing_address_contact.zip or "")
                    )
                    buyer_billing_address = buyer_billing_address.replace("&", " ")
                    buyer_billing_city = buyer_billing_address_contact.city or ""
                    buyer_billing_state = (
                        buyer_billing_address_contact.state_id.name or ""
                    )
                    buyer_billing_country = (
                        buyer_billing_address_contact.country_id.name or ""
                    )
                    buyer_billing_zip = buyer_billing_address_contact.zip or ""
                    buyer_billing_vergi_dairesi = (
                        buyer_billing_address_contact.vergi_dairesi or ""
                    )
                else:
                    buyer_billing_address = (
                        (invoice_record.partner_id.street or "")
                        + " "
                        + (invoice_record.partner_id.street2 or "")
                        + " "
                        + (invoice_record.partner_id.zip or "")
                    )
                    buyer_billing_address = buyer_billing_address.replace("&", " ")
                    buyer_billing_city = invoice_record.partner_id.city or ""
                    buyer_billing_state = invoice_record.partner_id.state_id.name or ""
                    buyer_billing_country = (
                        invoice_record.partner_id.country_id.name or ""
                    )
                    buyer_billing_zip = invoice_record.partner_id.zip or ""
                    buyer_billing_vergi_dairesi = (
                        invoice_record.partner_id.vergi_dairesi or ""
                    )

                xml_string += "<cac:BuyerCustomerParty>"
                xml_string += "<cac:Party>"
                xml_string += "<cbc:WebsiteURI/>"
                xml_string += "<cac:PartyIdentification>"
                xml_string += '<cbc:ID schemeID="PARTYTYPE">EXPORT</cbc:ID>'
                xml_string += "</cac:PartyIdentification>"
                xml_string += "<cac:PartyName>"
                xml_string += "<cbc:Name>" + buyer_name + "</cbc:Name>"
                xml_string += "</cac:PartyName>"
                xml_string += "<cac:PostalAddress>"
                xml_string += (
                    "<cbc:StreetName>" + buyer_billing_address + "</cbc:StreetName>"
                )
                xml_string += "<cbc:BuildingName/>"
                xml_string += "<cbc:BuildingNumber/>"
                xml_string += (
                    "<cbc:CitySubdivisionName>"
                    + buyer_billing_city
                    + "</cbc:CitySubdivisionName>"
                )
                xml_string += "<cbc:CityName>" + buyer_billing_state + "</cbc:CityName>"
                xml_string += (
                    "<cbc:PostalZone>" + buyer_billing_zip + "</cbc:PostalZone>"
                )
                xml_string += "<cbc:Region/>"
                xml_string += "<cac:Country>"
                xml_string += "<cbc:Name>" + buyer_billing_country + "</cbc:Name>"
                xml_string += "</cac:Country>"
                xml_string += "</cac:PostalAddress>"
                xml_string += "<cac:PartyLegalEntity>"
                xml_string += (
                    "<cbc:RegistrationName>" + buyer_name + "</cbc:RegistrationName>"
                )
                xml_string += "<cbc:CompanyID>" + buyer_vkn + "</cbc:CompanyID>"
                xml_string += "</cac:PartyLegalEntity>"
                xml_string += "<cac:Contact>"
                xml_string += "<cbc:Telephone/>"
                xml_string += "<cbc:Telefax/>"
                xml_string += "<cbc:ElectronicMail/>"
                xml_string += "</cac:Contact>"
                xml_string += "</cac:Party>"
                xml_string += "</cac:BuyerCustomerParty>"

            elif efatura_turu == "EFATURA" or efatura_turu == "EARSIV":
                payment_type = invoice_record.odeme_yontemi_id.code or ""
                payment_term = str(invoice_record.invoice_date_due) or ""
                if not payment_term:
                    payment_term = "PESIN"
                    payment_type = ""

                xml_string += "<cac:PaymentMeans>"
                xml_string += (
                    "<cbc:PaymentMeansCode>" + "42" + "</cbc:PaymentMeansCode>"
                )  # Ödeme Şekli
                xml_string += (
                    "<cbc:PaymentDueDate>" + payment_term + "</cbc:PaymentDueDate>"
                )
                xml_string += (
                    "<cbc:PaymentChannelCode>"
                    + payment_type
                    + "</cbc:PaymentChannelCode>"
                )
                # xml_string += '<cbc:InstructionNote> Son ödeme tarihi : ' + payment_term + '</cbc:InstructionNote>'
                xml_string += "<cac:PayeeFinancialAccount>"
                xml_string += "<cbc:ID></cbc:ID>"  # Ödeme Hesabı
                xml_string += (
                    "<cbc:CurrencyCode>"
                    + invoice_record.currency_id.name
                    + "</cbc:CurrencyCode>"
                )
                xml_string += "</cac:PayeeFinancialAccount>"
                xml_string += "</cac:PaymentMeans>"

            if invoice_record.efatura_turu_id.code == "EIHRACAT" or invoice_record.mikro_ihracat:
                incoterms = invoice_record.teslim_sarti_id.efinans_kod or ""

                # Finde Delivery Address
                delivery_address_contact = self.env["res.partner"].search(
                    [
                        ("parent_id", "=", invoice_record.partner_id.id),
                        ("type", "=", "delivery"),
                    ],
                    limit=1,
                )

                if delivery_address_contact:
                    delivery_address = (
                        (delivery_address_contact.street or "")
                        + " "
                        + (delivery_address_contact.street2 or "")
                        + " "
                        + (delivery_address_contact.zip or "")
                    )
                    delivery_address = delivery_address.replace("&", " ")
                    delivery_city = delivery_address_contact.city or ""
                    delivery_state = delivery_address_contact.state_id.name or ""
                    delivery_country = delivery_address_contact.country_id.name or ""
                    delivery_zip = delivery_address_contact.zip or ""
                    delivery_vergi_dairesi = (
                        delivery_address_contact.vergi_dairesi or ""
                    )
                else:
                    delivery_address = (
                        (invoice_record.partner_id.street or "")
                        + " "
                        + (invoice_record.partner_id.street2 or "")
                        + " "
                        + (invoice_record.partner_id.zip or "")
                    )
                    delivery_address = delivery_address.replace("&", " ")
                    delivery_city = invoice_record.partner_id.city or ""
                    delivery_state = invoice_record.partner_id.state_id.name or ""
                    delivery_country = invoice_record.partner_id.country_id.name or ""
                    delivery_zip = invoice_record.partner_id.zip or ""
                    delivery_vergi_dairesi = (
                        invoice_record.partner_id.vergi_dairesi or ""
                    )

                xml_string += "<cac:Delivery>"
                xml_string += "<cac:DeliveryAddress>"
                xml_string += "<cbc:Room/>"
                xml_string += (
                    "<cbc:StreetName>" + delivery_address + "</cbc:StreetName>"
                )
                xml_string += "<cbc:BuildingName/>"
                xml_string += "<cbc:BuildingNumber/>"
                xml_string += (
                    "<cbc:CitySubdivisionName>"
                    + delivery_city
                    + "</cbc:CitySubdivisionName>"
                )
                xml_string += "<cbc:CityName>" + delivery_state + "</cbc:CityName>"
                xml_string += "<cbc:PostalZone>" + delivery_zip + "</cbc:PostalZone>"
                xml_string += "<cbc:Region/>"
                xml_string += "<cac:Country>"
                xml_string += "<cbc:Name>" + delivery_country + "</cbc:Name>"
                xml_string += "</cac:Country>"
                xml_string += "</cac:DeliveryAddress>"
                xml_string += "<cac:DeliveryTerms>"
                xml_string += '<cbc:ID schemeID="INCOTERMS">' + incoterms + "</cbc:ID>"
                xml_string += "</cac:DeliveryTerms>"
                xml_string += "<cac:Shipment>"
                xml_string += "<cbc:ID/>"
                xml_string += "<cac:GoodsItem/>"
                xml_string += "<cac:ShipmentStage>"
                xml_string += (
                    "<cbc:TransportModeCode>"
                    + str(invoice_record.gonderim_sekli_id.efinans_kod)
                    + "</cbc:TransportModeCode>"
                )
                xml_string += "</cac:ShipmentStage>"
                xml_string += "<cac:TransportHandlingUnit>"
                xml_string += "<cac:ActualPackage/>"
                xml_string += "<cac:TransportMeans/>"
                xml_string += "</cac:TransportHandlingUnit>"
                xml_string += "</cac:Shipment>"
                xml_string += "</cac:Delivery>"

            # base_price = 0
            # line_count_tax = []
            # percent_tax = []
            # total_tax = []
            # total_taxable = []
            # discount = 0

            # Fatura satırları
            # for line in invoice_record.invoice_line_ids:
            #     line_quantity = line.quantity
            #     line_taxable_amount = line.price_subtotal
            #     line_rate = line_taxable_amount / line_quantity
            #     if not line_quantity:
            #         continue
            #     discount_value = line.discount
            #     if not discount_value:
            #         discount_value = 0
            #     base_price += line_rate * line_quantity
            #     discount += discount_value
            #     line_percent_tax = line.tax_ids[0].name.split('%')[0] # TODO: Fatura satırında taxrate1 sahası yok !!!
            #     line_total_tax = line.taxamount1 # TODO: Fatura satırında taxamount1 sahası yok !!!
            #     index = line_percent_tax in percent_tax
            #     fatura_alt_tipi = invoice_record.fatura_alt_tipi_id.code
            # if fatura_alt_tipi == 'OTV':
            #     otv_line_amount = line.amount_currency
            #     otv_line_tax = line.taxamount1 # TODO: Fatura satırında taxamount1 sahası yok !!!
            #     line_taxable_amount += otv_line_amount
            #     line_total_tax += otv_line_tax
            # if not index:
            #     percent_tax.append(line_percent_tax)
            #     line_count_tax.append(1)
            #     total_tax.append(line_total_tax)
            #     total_taxable.append(line_taxable_amount)
            # else:
            #     line_count_tax[index] += 1
            #     total_tax[index] += line_total_tax
            #     total_taxable[index] += line_taxable_amount

            # for expense_line in invoice_record.expense_sheet_id.expense_line_ids:
            #     # discount_value = expense_line.discount # TODO: Masraf satırında discount sahası yok !!!
            #     # if not discount_value:
            #     #     discount_value = 0
            #     line_rate = expense_line.price_unit
            #     line_percent_tax = expense_line.taxrate1 # TODO: Masraf satırında taxrate1 sahası yok !!!
            #     line_total_tax = expense_line.taxamount1 # TODO: Masraf satırında taxamount1 sahası yok !!!
            #     line_taxable_amount = expense_line.price_unit * expense_line.quantity
            #     index = line_percent_tax in percent_tax
            #     if not index:
            #         percent_tax.append(line_percent_tax)
            #         line_count_tax.append(1)
            #         total_tax.append(line_total_tax)
            #         total_taxable.append(line_taxable_amount)
            #     else:
            #         line_count_tax[index] += 1
            #         total_tax[index] += line_total_tax
            #         total_taxable[index] += line_taxable_amount

            # tax_otv_count = []
            # percent_otv_tax = []
            # taxable_otv_amount = []
            # total_otv_tax = []
            # tax_otv_code = []
            # tax_otv_desc = []
            # fatura_alt_tipi = invoice_record.fatura_alt_tipi_id.code

            # if fatura_alt_tipi == 'OTV':
            #     for line in invoice_record.invoice_line_ids:
            #         quantity_otv = line.quantity
            #         otv_code_id = line.otv_code_id # TODO: Fatura satırında otv_code_id sahası yok !!!
            #         if not quantity_otv:
            #             continue
            #         line_total_amount = line.price_subtotal
            #         line_otv_total_amount = 0
            #         if otv_code_id:
            #             line_otv_total_amount = line.price_subtotal
            #         line_otv_percent_tax = line.taxrate1 # TODO: Fatura satırında taxrate1 sahası yok !!!
            #         otv_code = otv_code_id.code
            #         otv_name = otv_code_id.name
            #         index = otv_code in tax_otv_code
            #         index2 = True
            #         code_index = len(percent_otv_tax)
            #         all_indexes = []

            #         for i in range(len(all_indexes)):
            #             if otv_code == tax_otv_code[all_indexes[i]]:
            #                 index2 = False
            #                 index = all_indexes[i]

            #         if not index or not index2:
            #             percent_otv_tax.append(line_otv_percent_tax)
            #             tax_otv_count.append(1)
            #             total_otv_tax.append(line_otv_total_amount)
            #             taxable_otv_amount.append(line_total_amount)
            #             tax_otv_code.append(otv_code)
            #             tax_otv_desc.append(otv_name)

            # discount = discount.round(2)
            # total = invoice_record.amount_total.round(2)
            # subtotal = invoice_record.amount_untaxed.round(2)
            # tax_total = invoice_record.amount_tax.round(2)
            # tax_excluded = subtotal - discount
            # fatura_alt_tipi = invoice_record.fatura_alt_tipi_id.code
            # if fatura_alt_tipi == 'OTV':
            #     tax_excluded = base_price.round(2)
            # tax_code = invoice_record.tax_code_id.code or "" # TODO: Fatura modelinde tax_code_id sahası yok !!!
            # tax_scheme = invoice_record.tax_code_id.name or "" # TODO: Fatura modelinde tax_code_id sahası yok !!!
            # indirim = False
            # if discount > -1 * discount:
            #     indirim = True
            # else :
            #     discount = -1 * discount

            # xml_string += '<cac:AllowanceCharge>'
            # xml_string += '<cbc:ChargeIndicator>' + str(indirim) + '</cbc:ChargeIndicator>'
            # xml_string += '<cbc:Amount currencyID="' + invoice_record.currency_id.name + '">' + exchange_rate + '</cbc:Amount>'
            # xml_string += '</cac:AllowanceCharge>'
            # ==========================================
            # total_discount = 0
            # for invoice_line in invoice_record.invoice_line_ids:
            #     # Toplam allowance charge hesabı
            #     discount_rate = invoice_line.discount # indirim yüzdesi
            #     total_discount += invoice_line.price_unit * discount_rate / 100

            # xml_string += "<cac:AllowanceCharge>"
            # xml_string += "<cbc:ChargeIndicator>true</cbc:ChargeIndicator>"
            # xml_string += '<cbc:Amount currencyID="' + invoice_record.currency_id.name + '">' + str(total_discount) + '</cbc:Amount>'
            # xml_string += "</cac:AllowanceCharge>"

            # KUR HESAPLAMASI
            xml_string += "<cac:PricingExchangeRate>"
            xml_string += (
                "<cbc:SourceCurrencyCode>"
                + str(invoice_record.currency_id.name)
                + "</cbc:SourceCurrencyCode>"
            )
            xml_string += (
                "<cbc:TargetCurrencyCode>"
                + str(self.env.user.company_id.currency_id.name)
                + "</cbc:TargetCurrencyCode>"
            )
            xml_string += (
                '<cbc:CalculationRate>'
                + f"{exchange_rate:.6f}"
                + '</cbc:CalculationRate>'
            )
            xml_string += "</cac:PricingExchangeRate>"

            xml_string += "<cac:TaxTotal>"
            xml_string += (
                '<cbc:TaxAmount currencyID="{}">{:.2f}</cbc:TaxAmount>'.format(
                    invoice_record.currency_id.name,
                    invoice_record.tax_totals["tax_amount_currency"],
                )
            )

            tax_amount_currency = 0
            # tax_totals değişkeninden XML yazımı
            for subtotal in invoice_record.tax_totals["subtotals"][0]["tax_groups"]:
                if subtotal["group_name"].startswith("KDV") and not subtotal[
                    "group_name"
                ].split("%")[1].startswith("-"):
                    xml_string += "<cac:TaxSubtotal>"
                    xml_string += '<cbc:TaxableAmount currencyID="{}">{:.2f}</cbc:TaxableAmount>'.format(
                        invoice_record.currency_id.name,
                        subtotal["base_amount_currency"],
                    )
                    xml_string += (
                        '<cbc:TaxAmount currencyID="{}">{:.2f}</cbc:TaxAmount>'.format(
                            invoice_record.currency_id.name,
                            subtotal["tax_amount_currency"],
                        )
                    )
                    xml_string += "<cbc:Percent>{}</cbc:Percent>".format(
                        subtotal["group_name"].split("%")[1]
                    )
                    xml_string += "<cac:TaxCategory>"
                    if fatura_tipi == "IHRACKAYITLI":
                        tax_amount_currency = subtotal["tax_amount_currency"]
                        xml_string += (
                            "<cbc:TaxExemptionReasonCode>"
                            + str(
                                invoice_record.invoice_line_ids[
                                    0
                                ].ihrac_kayit_kodu.efinans_kod
                            )
                            + "</cbc:TaxExemptionReasonCode>"
                        )
                        xml_string += (
                            "<cbc:TaxExemptionReason>"
                            + str(
                                invoice_record.invoice_line_ids[
                                    0
                                ].ihrac_kayit_kodu.description
                            )
                            + "</cbc:TaxExemptionReason>"
                        )
                    elif fatura_tipi == "ISTISNA":
                        xml_string += (
                            "<cbc:TaxExemptionReasonCode>"
                            + str(
                                invoice_record.invoice_line_ids[
                                    0
                                ].istisna_kodu.efinans_kod
                            )
                            + "</cbc:TaxExemptionReasonCode>"
                        )
                        xml_string += (
                            "<cbc:TaxExemptionReason>"
                            + str(
                                invoice_record.invoice_line_ids[
                                    0
                                ].istisna_kodu.description
                            )
                            + "</cbc:TaxExemptionReason>"
                        )
                    xml_string += "<cac:TaxScheme>"
                    tax_name = subtotal["group_name"].split("%")[0]
                    if tax_name.startswith("KDV"):
                        tax_name = "KDV"
                    xml_string += "<cbc:Name>{}</cbc:Name>".format(tax_name)
                    xml_string += "<cbc:TaxTypeCode>0015</cbc:TaxTypeCode>"
                    xml_string += "</cac:TaxScheme>"
                    xml_string += "</cac:TaxCategory>"
                    xml_string += "</cac:TaxSubtotal>"
            xml_string += "</cac:TaxTotal>"

            wh_total = 0
            if fatura_tipi == "TEVKIFAT":
                xml_string += "<cac:WithholdingTaxTotal>"
                for subtotal in invoice_record.tax_totals[
                    "subtotals"
                ]:  # 'subtotals' bir liste, burada her bir 'subtotal' üzerinde işlem yapıyoruz
                    for group in subtotal["tax_groups"]:  # 'tax_groups' bir liste
                        # KDV dışındaki vergi gruplarını işleme al
                        if not group["group_name"].startswith("KDV"):
                            wh_total += group["tax_amount_currency"] * -1
                xml_string += (
                    '<cbc:TaxAmount currencyID="{}">{}</cbc:TaxAmount>'.format(
                        invoice_record.currency_id.name, str(wh_total)
                    )
                )

                # Subtotals içinde döngü yapıyoruz
                for subtotal in invoice_record.tax_totals[
                    "subtotals"
                ]:  # 'subtotals' bir liste, burada her bir 'subtotal' üzerinde işlem yapıyoruz
                    for group in subtotal["tax_groups"]:  # 'tax_groups' bir liste
                        # KDV dışındaki vergi gruplarını işleme al
                        if not group["group_name"].startswith("KDV"):

                            taxable_amount = str(group["base_amount_currency"])
                            tax_amount = str(group["tax_amount_currency"] * -1)

                            percent = "0"
                            kdv = "0"
                            # KDV oranlarına bağlı olarak Percent eklemek için kontrol
                            if (
                                subtotal["tax_groups"][0]["group_name"].startswith(
                                    "KDV"
                                )
                                and subtotal["tax_groups"][0]["group_name"].split("%")[
                                    1
                                ]
                                == "20"
                            ):
                                kdv = "20"
                                # percent = group['group_name'].split('%')[1]
                                percent = group["group_name"].split("%-")[1]

                            xml_string += "<cac:TaxSubtotal>"
                            xml_string += '<cbc:TaxableAmount currencyID="{}">{}</cbc:TaxableAmount>'.format(
                                invoice_record.currency_id.name,
                                int(float(taxable_amount) * float(kdv) / 100),
                            )
                            xml_string += '<cbc:TaxAmount currencyID="{}">{}</cbc:TaxAmount>'.format(
                                invoice_record.currency_id.name, tax_amount
                            )

                            xml_string += "<cbc:Percent>{}</cbc:Percent>".format(
                                int(int(percent) / 2 * 10)
                            )
                            xml_string += "<cac:TaxCategory>"
                            xml_string += "<cbc:Name>KDV TEVKIFAT</cbc:Name>"
                            xml_string += "<cac:TaxScheme>"

                            # invoice_line_ids üzerinden her bir satırın tax_ids[0].id değerlerini alıp birleştiriyoruz
                            logging_field4_value = "\n".join(
                                [
                                    str(line.tax_ids[0].id)
                                    for line in invoice_record.invoice_line_ids
                                    if line.tax_ids
                                ]
                            )

                            # 'logging_field4' alanına yazıyoruz
                            invoice_record.write(
                                {"logging_field4": logging_field4_value}
                            )

                            if invoice_record.logging_field5:
                                logging_field5_value = (
                                    invoice_record.logging_field5
                                    + "\n"
                                    + str(group["involved_tax_ids"][0])
                                )
                            else:
                                logging_field5_value = str(group["involved_tax_ids"][0])

                            # 'logging_field5' alanına yazıyoruz
                            invoice_record.write(
                                {"logging_field5": logging_field5_value}
                            )

                            # Filtreleme işlemi için tax_ids[0].invoice_label üzerinden vergi etiketini alıyoruz
                            involved_tax = (
                                self.env["account.tax"]
                                .search([("id", "=", group["involved_tax_ids"][0])])
                                .id
                            )

                            if not preview_mode:
                                invoice_record.write({"logging_field6": str(involved_tax)})
                                # raise UserError("Involved Tax ID: {}".format(involved_tax)) # 39

                                invoice_record.write(
                                    {
                                        "logging_field6": str(invoice_record.logging_field6)
                                        + "\n"
                                        + str(
                                            invoice_record.invoice_line_ids[0]
                                            .tax_ids[0]
                                            .children_tax_ids[0]
                                            .id
                                        )
                                    }
                                )
                            # raise UserError("First Children Tax ID: {}".format(invoice_record.invoice_line_ids[0].tax_ids[0].children_tax_ids[0].id)) # 32
                            filtered_lines = invoice_record.invoice_line_ids.filtered(
                                lambda x: involved_tax
                                in x.tax_ids[0].children_tax_ids.ids
                            )

                            # Eğer filtrelenmiş satırlar varsa, tevkifat kodunu ve açıklamasını ekliyoruz
                            if filtered_lines:
                                tevkifat_aciklama = (
                                    filtered_lines[0].tevkifat_kodu.description
                                    if filtered_lines[0].tevkifat_kodu
                                    else "Unknown"
                                )
                                tevkifat_kodu = (
                                    filtered_lines[0].tevkifat_kodu.efinans_kod
                                    if filtered_lines[0].tevkifat_kodu
                                    else "Unknown"
                                )
                                xml_string += "<cbc:Name>{}</cbc:Name>".format(
                                    tevkifat_aciklama
                                )
                                xml_string += (
                                    "<cbc:TaxTypeCode>{}</cbc:TaxTypeCode>".format(
                                        tevkifat_kodu
                                    )
                                )
                            else:
                                raise UserError("Tevkifat Kodu Bulunamadı!")

                            xml_string += "</cac:TaxScheme>"
                            xml_string += "</cac:TaxCategory>"
                            xml_string += "</cac:TaxSubtotal>"

                xml_string += "</cac:WithholdingTaxTotal>"

            if fatura_tipi == "TEVKIFAT":
                discount_total = 0
                total = 0
                for inv_line in invoice_record.invoice_line_ids:
                    line_taxable_amount = inv_line.price_unit * inv_line.quantity
                    line_discount_amount = line_taxable_amount * (inv_line.discount / 100)
                    discount_total += line_discount_amount
                    total += line_taxable_amount

                xml_string += "<cac:LegalMonetaryTotal>"
                xml_string += (
                    '<cbc:LineExtensionAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + "{:.2f}".format(total)
                    + "</cbc:LineExtensionAmount>"
                )
                xml_string += (
                    '<cbc:TaxExclusiveAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + "{:.2f}".format(invoice_record.amount_untaxed)
                    + "</cbc:TaxExclusiveAmount>"
                )
                xml_string += (
                    '<cbc:TaxInclusiveAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + "{:.2f}".format(
                        invoice_record.amount_untaxed
                        + invoice_record.amount_tax
                        + wh_total
                    )
                    + "</cbc:TaxInclusiveAmount>"
                )
                xml_string += (
                    '<cbc:AllowanceTotalAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + "{:.2f}".format(discount_total)
                    + "</cbc:AllowanceTotalAmount>"
                )
                xml_string += (
                    '<cbc:ChargeTotalAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">0</cbc:ChargeTotalAmount>'
                )
                xml_string += (
                    '<cbc:PayableRoundingAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">0</cbc:PayableRoundingAmount>'
                )
                xml_string += (
                    '<cbc:PayableAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + "{:.2f}".format(invoice_record.amount_total)
                    + "</cbc:PayableAmount>"
                )
                xml_string += "</cac:LegalMonetaryTotal>"
            elif fatura_tipi == "IHRACKAYITLI":
                
                discount_total = 0
                total = 0
                for inv_line in invoice_record.invoice_line_ids:
                    line_taxable_amount = inv_line.price_unit * inv_line.quantity
                    line_discount_amount = line_taxable_amount * (inv_line.discount / 100)
                    discount_total += line_discount_amount
                    total += line_taxable_amount

                xml_string += "<cac:LegalMonetaryTotal>"
                xml_string += (
                    '<cbc:LineExtensionAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + "{:.2f}".format(total)
                    + "</cbc:LineExtensionAmount>"
                )
                xml_string += (
                    '<cbc:TaxExclusiveAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + "{:.2f}".format(invoice_record.amount_untaxed)
                    + "</cbc:TaxExclusiveAmount>"
                )
                xml_string += (
                    '<cbc:TaxInclusiveAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + "{:.2f}".format(invoice_record.amount_total + tax_amount_currency)
                    + "</cbc:TaxInclusiveAmount>"
                )
                xml_string += (
                    '<cbc:AllowanceTotalAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + "{:.2f}".format(discount_total)
                    + "</cbc:AllowanceTotalAmount>"
                )
                xml_string += (
                    '<cbc:ChargeTotalAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">0</cbc:ChargeTotalAmount>'
                )
                xml_string += (
                    '<cbc:PayableRoundingAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">0</cbc:PayableRoundingAmount>'
                )
                xml_string += (
                    '<cbc:PayableAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + "{:.2f}".format(invoice_record.amount_total)
                    + "</cbc:PayableAmount>"
                )
                xml_string += "</cac:LegalMonetaryTotal>"
            else:
                discount_total = 0
                total = 0
                for inv_line in invoice_record.invoice_line_ids:
                    line_taxable_amount = inv_line.price_unit * inv_line.quantity
                    line_discount_amount = line_taxable_amount * (inv_line.discount / 100)
                    discount_total += line_discount_amount
                    total += line_taxable_amount

                xml_string += "<cac:LegalMonetaryTotal>"
                xml_string += (
                    '<cbc:LineExtensionAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + "{:.2f}".format(total)
                    + "</cbc:LineExtensionAmount>"
                )
                xml_string += (
                    '<cbc:TaxExclusiveAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + "{:.2f}".format(invoice_record.amount_untaxed)
                    + "</cbc:TaxExclusiveAmount>"
                )
                xml_string += (
                    '<cbc:TaxInclusiveAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + "{:.2f}".format(invoice_record.amount_total)
                    + "</cbc:TaxInclusiveAmount>"
                )
                xml_string += (
                    '<cbc:AllowanceTotalAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + "{:.2f}".format(discount_total)
                    + "</cbc:AllowanceTotalAmount>"
                )
                xml_string += (
                    '<cbc:ChargeTotalAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">0</cbc:ChargeTotalAmount>'
                )
                xml_string += (
                    '<cbc:PayableRoundingAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">0</cbc:PayableRoundingAmount>'
                )
                xml_string += (
                    '<cbc:PayableAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + "{:.2f}".format(invoice_record.amount_total)
                    + "</cbc:PayableAmount>"
                )
                xml_string += "</cac:LegalMonetaryTotal>"

            # Satır bazlı işleme
            for line_index, line in enumerate(invoice_record.invoice_line_ids, start=1):
                line_quantity = line.quantity
                line_taxable_amount = line.price_unit * line.quantity
                line_discount_amount = line_taxable_amount * (line.discount / 100)
                line_taxable_amount -= line_discount_amount
                line_rate = line_taxable_amount / line_quantity if line_quantity else 0

                # Vergi yüzdesini ayıkla
                line_percent_tax = "0"
                if line.tax_ids:
                    if line.tax_ids[0].name.split("%")[0].strip().isdigit():
                        line_percent_tax = line.tax_ids[0].name.split("%")[0].strip()
                    line_percent_tax = re.search(
                        r"\d+", line.tax_ids[0].name.split("%")[0].strip()
                    )
                    line_percent_tax = (
                        line_percent_tax.group(0) if line_percent_tax else "0"
                    )

                line_tax_amount = line_taxable_amount * (int(line_percent_tax) / 100)
                line_unit_code = line.product_id.uom_id._get_unece_code() or "C62"

                # XML satır verileri
                xml_string += "<cac:InvoiceLine>"
                xml_string += "<cbc:ID>{}</cbc:ID>".format(line_index)
                xml_string += '<cbc:InvoicedQuantity unitCode="{}">{}</cbc:InvoicedQuantity>'.format(
                    str(line_unit_code), str(line_quantity)
                )
                xml_string += '<cbc:LineExtensionAmount currencyID="{}">{}</cbc:LineExtensionAmount>'.format(
                    invoice_record.currency_id.name, str(line_taxable_amount)
                )

                if invoice_record.efatura_turu_id.code == "EIHRACAT" or invoice_record.mikro_ihracat:
                    # kap_marka = invoice_record.bulundugu_kabin_markasi
                    kap_no = invoice_record.bulundugu_kabin_numarasi or ""
                    kap_adet = invoice_record.bulundugu_kabin_adedi or ""
                    kap_cins = (
                        invoice_record.bulundugu_kabin_cinsi_ve_nevi_id.efinans_kod
                        or ""
                    )
                    efinans_gonderim_sekli = (
                        invoice_record.gonderim_sekli_id.efinans_kod or ""
                    )

                    xml_string += "<cac:Delivery>"
                    xml_string += "<cac:DeliveryTerms>"
                    xml_string += (
                        '<cbc:ID schemeID="INCOTERMS">' + incoterms + "</cbc:ID>"
                    )
                    xml_string += "</cac:DeliveryTerms>"
                    xml_string += "<cac:Shipment>"
                    xml_string += "<cbc:ID>{}</cbc:ID>".format(line_index)
                    xml_string += (
                        '<cbc:GrossWeightMeasure unitCode="KGM">'
                        + str(brut_kg)
                        + "</cbc:GrossWeightMeasure>"
                    )
                    xml_string += (
                        '<cbc:NetWeightMeasure unitCode="KGM">'
                        + str(net_kg)
                        + "</cbc:NetWeightMeasure>"
                    )
                    xml_string += "<cac:GoodsItem>"
                    xml_string += (
                        "<cbc:RequiredCustomsID>"
                        + line.gtip_kodu
                        + "</cbc:RequiredCustomsID>"
                    )
                    xml_string += "</cac:GoodsItem>"
                    xml_string += "<cac:ShipmentStage>"
                    xml_string += (
                        "<cbc:TransportModeCode>"
                        + str(efinans_gonderim_sekli)
                        + "</cbc:TransportModeCode>"
                    )
                    xml_string += "</cac:ShipmentStage>"
                    # xml_string += '''
                    # <cac:TransportHandlingUnit>
                    # <cac:ActualPackage>
                    # <cbc:ID>{kap_no}</cbc:ID>
                    # <cbc:Quantity>{kap_adet}</cbc:Quantity>
                    # <cbc:PackagingTypeCode>{kap_cins}</cbc:PackagingTypeCode>
                    # </cac:ActualPackage>
                    # <cac:TransportMeans/>
                    # </cac:TransportHandlingUnit>
                    # '''.format(
                    #     kap_no=kap_no,
                    #     kap_adet=kap_adet,
                    #     kap_cins=kap_cins
                    # )
                    xml_string += "<cac:TransportHandlingUnit>"
                    xml_string += "<cac:ActualPackage>"
                    if kap_no:
                        xml_string += "<cbc:ID>{}</cbc:ID>".format(kap_no)
                    if kap_adet:
                        xml_string += "<cbc:Quantity>{}</cbc:Quantity>".format(kap_adet)
                    if kap_cins:
                        xml_string += (
                            "<cbc:PackagingTypeCode>{}</cbc:PackagingTypeCode>".format(
                                kap_cins
                            )
                        )
                    xml_string += "</cac:ActualPackage>"
                    xml_string += "<cac:TransportMeans/>"
                    xml_string += "</cac:TransportHandlingUnit>"
                    xml_string += "</cac:Shipment>"
                    xml_string += "</cac:Delivery>"

                # AllowanceCharge kısmı
                xml_string += """
                <cac:AllowanceCharge>
                    <cbc:ChargeIndicator>{charge_indicator}</cbc:ChargeIndicator>
                    <cbc:AllowanceChargeReason/>
                    <cbc:MultiplierFactorNumeric>{discount_rate}</cbc:MultiplierFactorNumeric>
                    <cbc:SequenceNumeric>{line_index}</cbc:SequenceNumeric>
                    <cbc:Amount currencyID="{currency}">{discount_amount}</cbc:Amount>
                    <cbc:BaseAmount currencyID="{company_currency}">{taxable_amount}</cbc:BaseAmount>
                </cac:AllowanceCharge>
                """.format(
                    charge_indicator='false' if line.discount > 0 else 'true',
                    discount_rate= str(line.discount / 100),
                    line_index=line_index,
                    discount_amount=str(line_discount_amount),
                    currency=line.currency_id.name,
                    company_currency=line.company_currency_id.name,
                    taxable_amount=str(line_taxable_amount),
                )

                # Vergi bilgileri
                xml_string += "<cac:TaxTotal>"
                xml_string += (
                    '<cbc:TaxAmount currencyID="{}">{}</cbc:TaxAmount>'.format(
                        invoice_record.currency_id.name, str(line_tax_amount)
                    )
                )
                xml_string += "<cac:TaxSubtotal>"
                xml_string += (
                    '<cbc:TaxableAmount currencyID="{}">{}</cbc:TaxableAmount>'.format(
                        invoice_record.currency_id.name, str(line_taxable_amount)
                    )
                )
                xml_string += (
                    '<cbc:TaxAmount currencyID="{}">{}</cbc:TaxAmount>'.format(
                        invoice_record.currency_id.name, str(line_tax_amount)
                    )
                )
                xml_string += "<cbc:Percent>{}</cbc:Percent>".format(
                    str(line_percent_tax)
                )
                xml_string += "<cac:TaxCategory>"

                if fatura_tipi == "ISTISNA":
                    xml_string += """
                        <cbc:TaxExemptionReasonCode>{istisna_kodu}</cbc:TaxExemptionReasonCode>
                        <cbc:TaxExemptionReason>{istisna_aciklama}</cbc:TaxExemptionReason>
                    """.format(
                        istisna_kodu=line.istisna_kodu.efinans_kod,
                        istisna_aciklama=line.istisna_kodu.description,
                    )

                xml_string += "<cac:TaxScheme>"
                # xml_string += '<cbc:Name>{}</cbc:Name>'.format(line.tax_ids[0].tax_group_id.name.split(' ')[0])
                xml_string += "<cbc:Name>KDV</cbc:Name>"
                xml_string += "<cbc:TaxTypeCode>0015</cbc:TaxTypeCode>"
                xml_string += "</cac:TaxScheme>"
                xml_string += "</cac:TaxCategory>"
                xml_string += "</cac:TaxSubtotal>"
                xml_string += "</cac:TaxTotal>"

                if fatura_tipi == "TEVKIFAT":
                    tevkifat_kodu_description = line.tevkifat_kodu.description
                    tevkifat_orani = line.tevkifat_kodu.tevkifat_orani
                    tevkifat_kodu = line.tevkifat_kodu.efinans_kod

                    xml_string += "<cac:WithholdingTaxTotal>"
                    xml_string += (
                        '<cbc:TaxAmount currencyID="{}">{}</cbc:TaxAmount>'.format(
                            invoice_record.currency_id.name,
                            str(line_tax_amount * float(tevkifat_orani)),
                        )
                    )
                    xml_string += "<cac:TaxSubtotal>"
                    xml_string += '<cbc:TaxableAmount currencyID="{}">{}</cbc:TaxableAmount>'.format(
                        invoice_record.currency_id.name, str(line_tax_amount)
                    )
                    xml_string += (
                        '<cbc:TaxAmount currencyID="{}">{}</cbc:TaxAmount>'.format(
                            invoice_record.currency_id.name,
                            str(line_tax_amount * float(tevkifat_orani)),
                        )
                    )
                    xml_string += "<cbc:Percent>{}</cbc:Percent>".format(
                        str(int(tevkifat_orani * 100))
                    )
                    xml_string += "<cac:TaxCategory>"
                    xml_string += "<cbc:Name>KDV TEVKIFAT</cbc:Name>"
                    xml_string += "<cac:TaxScheme>"
                    xml_string += "<cbc:Name>{}</cbc:Name>".format(
                        tevkifat_kodu_description
                    )
                    xml_string += "<cbc:TaxTypeCode>{}</cbc:TaxTypeCode>".format(
                        tevkifat_kodu
                    )
                    xml_string += "</cac:TaxScheme>"
                    xml_string += "</cac:TaxCategory>"
                    xml_string += "</cac:TaxSubtotal>"
                    xml_string += "</cac:WithholdingTaxTotal>"

                xml_string += "<cac:Item>"
                xml_string += "<cbc:Description>" + str(line.line_description) + "</cbc:Description>"


                product_name = str(line.product_id.name)
                cleaned_name = re.sub(r'^\[.*?\]\s*', '', product_name)
                xml_string += "<cbc:Name>" + cleaned_name + "</cbc:Name>"
                xml_string += "<cac:SellersItemIdentification>"
                # # xml_string += '<cbc:ID>' + self.generate_cbc_id(fatura_seri_code,line.product_id.id) + '</cbc:ID>'
                xml_string += "<cbc:ID>" + str(line.product_id.default_code) + "</cbc:ID>"
                xml_string += "</cac:SellersItemIdentification>"
                xml_string += "</cac:Item>"
                xml_string += "<cac:Price>"
                xml_string += (
                    '<cbc:PriceAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + str(line.price_unit)
                    + "</cbc:PriceAmount>"
                )
                xml_string += "</cac:Price>"
                xml_string += "</cac:InvoiceLine>"

            xml_string += "</Invoice>"

            if not preview_mode:
                invoice_record.write({"logging_field6": xml_string})

            return xml_string

    @staticmethod
    def generate_cbc_id(prefix, serial):
        year = datetime.date.today().year
        return f"{prefix}{year}{serial:09d}"

    def send_invoice_xml(self, invoice_record, xml_string):

        # MdxUtilityMixin.check_license(self)

        web_service = self.env["mdx.web.service"].search(
            [
                ("name", "=", "EFINANS_GONDERICI"),
                ("active", "=", True),
                ("company_id", "=", self.env.user.company_id.id),
            ],
            limit=1,
        )
        username = str(web_service.username)
        password = str(web_service.password)
        url = str(web_service.url)
        erp_code = str(web_service.erp_code)
        vkn = str(invoice_record.company_id.vat)
        decoded_xml = self.base64_encode(xml_string)
        hash_obj = self.calculate_md5(xml_string)
        counter = (
            self.env["mdx.dokuman.sayac"]
            .search(
                [
                    ("code", "=", "DOKUMANSAYAC"),
                    ("company_id", "=", self.env.user.company_id.id),
                ],
                limit=1,
            )
            .gonderilecek_sonraki_sira_no
        )

        post_string = '<?xml version="1.0" encoding="utf-8"?>'
        if (
            invoice_record.efatura_turu_id.code == "EFATURA"
            or invoice_record.efatura_turu_id.code == "EIHRACAT"
        ):
            post_string += '<soapenv:Envelope xmlns:ser="http://service.connector.uut.cs.com.tr/" xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
            post_string += "<soapenv:Header>"
            post_string += '<wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">'
            post_string += "<wsse:UsernameToken>"
            post_string += "<wsse:Username>" + str(username) + "</wsse:Username>"
            post_string += "<wsse:Password>" + str(password) + "</wsse:Password>"
            post_string += "</wsse:UsernameToken>"
            post_string += "</wsse:Security>"
            post_string += "</soapenv:Header>"
            post_string += "<soapenv:Body>"
            post_string += "<ser:belgeGonderExt>"
            post_string += "<parametreler>"
            post_string += "<belgeHash>" + hash_obj + "</belgeHash>"
            post_string += "<belgeNo>" + str(counter) + "</belgeNo>"
            post_string += "<belgeTuru>FATURA_UBL</belgeTuru>"
            post_string += "<belgeVersiyon>1.2</belgeVersiyon>"
            post_string += "<erpKodu>" + erp_code + "</erpKodu>"
            post_string += "<mimeType>application/xml</mimeType>"
            post_string += "<vergiTcKimlikNo>" + str(vkn) + "</vergiTcKimlikNo>"
            post_string += "<veri>" + decoded_xml + "</veri>"
            post_string += "</parametreler>"
            post_string += "</ser:belgeGonderExt>"
            post_string += "</soapenv:Body>"
            post_string += "</soapenv:Envelope>"

            namespaces = {"ns2": "http://service.connector.uut.cs.com.tr/"}

        elif invoice_record.efatura_turu_id.code == "EARSIV":
            web_service = self.env["mdx.web.service"].search(
                [
                    ("name", "=", "EFINANS_GONDERICI_EARSIV"),
                    ("active", "=", True),
                    ("company_id", "=", self.env.user.company_id.id),
                ],
                limit=1,
            )

            if web_service:
                username = str(web_service.username)
                password = str(web_service.password)
                url = str(web_service.url)
                erp_code = str(web_service.erp_code)
                vkn = str(web_service.vkn)

            # url = "https://earsivtest.efinans.com.tr/earsiv/ws/EarsivWebService?wsdl"
            post_string += '<soapenv:Envelope xmlns:ser="http://service.earsiv.uut.cs.com.tr/" xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
            post_string += "<soapenv:Header>"
            post_string += '<wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">'
            post_string += "<wsse:UsernameToken>"
            post_string += (
                "<wsse:Username>" + username + "</wsse:Username>"
            )
            post_string += "<wsse:Password>" + password + "</wsse:Password>"
            post_string += "</wsse:UsernameToken>"
            post_string += "</wsse:Security>"
            post_string += "</soapenv:Header>"
            post_string += "<soapenv:Body>"
            post_string += "<ser:faturaOlustur>"
            post_string += (
                '<input>{"islemId":"'
                + str(invoice_record.uuid)
                + '", "vkn" :"'
                + str(vkn)
                + '", "sube":"MERKEZ","kasa":"2", "donenBelgeFormati" : "3", "sablonAdi" : "test.xslt"}</input>'
            )
            post_string += "<fatura>"
            post_string += "<belgeFormati>UBL</belgeFormati>"
            post_string += "<belgeIcerigi>" + decoded_xml + "</belgeIcerigi>"
            post_string += "</fatura>"
            post_string += "</ser:faturaOlustur>"
            post_string += "</soapenv:Body>"
            post_string += "</soapenv:Envelope>"

            invoice_record.write({"logging_field1": xml_string})

            namespaces = {
                "S": "http://schemas.xmlsoap.org/soap/envelope/",
                "ns2": "http://service.earsiv.uut.cs.com.tr/",
            }

        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}

        invoice_record.write({"logging_field3": xml_string})
        invoice_record.write({"logging_field2": post_string})

        response = requests.post(url, data=post_string, headers=headers)

        invoice_record.write({"logging_field4": response.content})
        # invoice_record.write({'belge_oid_kod': response.status_code})

        root = ET.fromstring(response.content)

        if response.status_code == 200:

            if invoice_record.efatura_turu_id.code == "EARSIV":
                invoice_record.write({"logging_field1": response.content})

                # resultCode elementini kontrol et
                result_code_element = root.find(
                    ".//ns2:faturaOlusturResponse/return/resultCode", namespaces
                )
                if (
                    result_code_element is not None
                    and result_code_element.text == "AE00000"
                ):
                    # invoice_record.write({'name': invoice_record.fatura_no})
                    invoice_record.write(
                        {"fatura_gonderim_hata_kodu": result_code_element.text}
                    )
                    invoice_record.write({"fatura_durum_detay": "İşlem başarılı."})

                    pdf_data_element = root.find(
                        ".//ns2:faturaOlusturResponse/output/belgeIcerigi", namespaces
                    )

                    if pdf_data_element is not None:
                        pdf_data = base64.b64decode(pdf_data_element.text)
                        file_name = invoice_record.fatura_no + ".pdf"

                        attachment = self.env["ir.attachment"].create(
                            {
                                "name": file_name,
                                "datas": base64.b64encode(pdf_data),
                                "res_model": "account.move",
                                "res_id": invoice_record.id,
                                "type": "binary",
                            }
                        )

                        if attachment:
                            invoice_record.ekli_belge_id = attachment.id
                            invoice_record.logging_field5 = (
                                "PDF başarıyla indirildi ve iliştirildi."
                            )
                        else:
                            invoice_record.logging_field5 = (
                                "PDF indirilemedi: attachment_pdf boş."
                            )
                    else:
                        invoice_record.logging_field5 = (
                            "Yanıt içerisinde belge içeriği bulunamadı."
                        )
                else:
                    invoice_record.write({"uuid": ""})
                    invoice_record.write(
                        {
                            "fatura_gonderim_hata_kodu": (
                                result_code_element.text
                                if result_code_element is not None
                                else "Bilinmiyor"
                            )
                        }
                    )

                    result_text_element = root.find(
                        ".//ns2:faturaOlusturResponse/return/resultText", namespaces
                    )

                    if result_text_element is not None:
                        invoice_record.write(
                            {"fatura_durum_detay": "HATA : " + result_text_element.text}
                        )
                    else:
                        invoice_record.write({"fatura_durum_detay": "Bilinmiyor"})

            else:
                belge_oid = root.find(
                    ".//ns2:belgeGonderExtResponse/belgeOid", namespaces
                ).text

                invoice_record.write({"belge_oid_kod": belge_oid})

        else:
            if invoice_record.efatura_turu_id.code != "EARSIV":

                invoice_record.write(
                    {"fatura_gonderim_hata_kodu": response.status_code}
                )

                # fault_code = root.find('.//ns2:Fault/faultcode', namespaces).text
                # fault_string = root.find('.//Fault/ns2:faultstring', namespaces).text

                # invoice_record.write({
                #     'fatura_gonderim_hata_kodu':
                #     """Fault Code: {}\nFault String: {}""".format(fault_code, fault_string)
                # })

    class EbelgeDurumDetay:
        def __init__(
            self,
            aciklama,
            alim_tarihi,
            durum,
            gonderim_cevabi_kodu,
            gonderim_durumu,
            yanit_durumu,
            ulasti_mi,
            yeniden_gonderilebilir_mi,
            belge_oid,
        ):
            self.aciklama = aciklama
            self.alim_tarihi = alim_tarihi
            self.gonderim_cevabi_kodu = gonderim_cevabi_kodu
            self.belge_oid = belge_oid

            # Varsayılan değer
            self.durum = "Bilinmiyor"
            durum = str(durum)  # Integer'ı string'e dönüştür
            if durum == "1":
                self.durum = "Alındı, işlenmeyi bekliyor."
            elif durum == "2":
                self.durum = "İşlenemedi. Açıklama alanında hata mesajı bulunabilir."
            elif durum == "3":
                self.durum = "İşlendi, gönderime hazır."

            self.gonderim_durumu = "Bilinmiyor"
            gonderim_durumu = str(gonderim_durumu)  # Integer'ı string'e dönüştür
            if gonderim_durumu == "-2":
                self.gonderim_durumu = "İptal edildi, Gönderilmeyecek."
            elif gonderim_durumu == "-1":
                self.gonderim_durumu = "Kuyruğa eklendi."
            elif gonderim_durumu == "0":
                self.gonderim_durumu = (
                    "Gönderilemedi, sistem gönderim işlemini yeniden deneyecek."
                )
            elif gonderim_durumu == "1":
                self.gonderim_durumu = "Gönderilecek."
            elif gonderim_durumu == "2":
                self.gonderim_durumu = "Gönderildi."
            elif gonderim_durumu == "3":
                self.gonderim_durumu = "GİB merkez yanıtı geldi."
            elif gonderim_durumu == "4":
                self.gonderim_durumu = "Alıcı yanıtı geldi."

            self.yanit_durumu = "Bilinmiyor"
            yanit_durumu = str(yanit_durumu)  # Integer'ı string'e dönüştür
            if yanit_durumu == "-1":
                self.yanit_durumu = (
                    "Yanıt gerekmiyor. Temel faturalar için yanıt beklenmez."
                )
            elif yanit_durumu == "0":
                self.yanit_durumu = (
                    "Yanıt bekleniyor. Ticari fatura için cevap bekleniyor."
                )
            elif yanit_durumu == "1":
                self.yanit_durumu = "Red cevabı geldi."
            elif yanit_durumu == "2":
                self.yanit_durumu = "Kabul cevabı geldi."

            self.ulasti_mi = "Bilinmiyor"
            if ulasti_mi == "true":
                self.ulasti_mi = "Evet"
            elif ulasti_mi == "false":
                self.ulasti_mi = "Hayır"

            self.yeniden_gonderilebilir_mi = "Bilinmiyor"
            if yeniden_gonderilebilir_mi == "true":
                self.yeniden_gonderilebilir_mi = "Evet"
            elif yeniden_gonderilebilir_mi == "false":
                self.yeniden_gonderilebilir_mi = "Hayır"

    def download_document_pdf(self, document_type, uuid):

        # MdxUtilityMixin.check_license(self)

        web_service = self.env["mdx.web.service"].search(
            [
                ("name", "=", "EFINANS_GONDERICI"),
                ("active", "=", True),
                ("company_id", "=", self.env.user.company_id.id),
            ],
            limit=1,
        )
        username = str(web_service.username)
        password = str(web_service.password)
        vkn = str(web_service.vkn)
        url = web_service.url

        post_string = f"""
            <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
            xmlns:ser="http://service.connector.uut.cs.com.tr/">
            <soapenv:Header>
                <wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
                    <wsse:UsernameToken>
                        <wsse:Username>{username}</wsse:Username>
                        <wsse:Password>{password}</wsse:Password>
                    </wsse:UsernameToken>
                </wsse:Security>
            </soapenv:Header>
            <soapenv:Body>
                <ser:gidenBelgeleriIndirEttn>
                    <!-- Gönderici VKN -->
                    <vergiTcKimlikNo>{vkn}</vergiTcKimlikNo>
                    <!-- Zero or more repetitions: -->
                    <belgeEttnListesi>{uuid}</belgeEttnListesi>
                    <!-- FATURA,IRSALIYE ve UYGULAMA_YANITI  -->
                    <belgeTuru>{document_type}</belgeTuru>
                    <!-- HTML, PDF, UBL -->
                    <belgeFormati>PDF</belgeFormati>
                </ser:gidenBelgeleriIndirEttn>
            </soapenv:Body>
        </soapenv:Envelope>
        """

        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}

        response = requests.post(url, data=post_string, headers=headers)
        _logger.info(f"SOAP Response Status Code: {response.status_code}")
        _logger.info(f"SOAP Response Content: {response.content}")
        if response.status_code == 200:
            try:
                _logger.info("SOAP isteği başarılı, XML parse ediliyor...")
                # XML'i parse et
                root = ET.fromstring(response.content)

                # Namespace tanımları
                namespaces = {
                    "S": "http://schemas.xmlsoap.org/soap/envelope/",
                    "ns2": "http://service.connector.uut.cs.com.tr/",
                }

                # <return> elementini bul
                return_element = root.find(
                    ".//ns2:gidenBelgeleriIndirEttnResponse/return", namespaces
                )
                _logger.info(f"Return Element: {return_element}")
                if return_element is not None:
                    # Base64 stringi al
                    base64_zip = return_element.text

                    # Base64'ü decode et
                    zip_data = base64.b64decode(base64_zip)
                    _logger.info("Base64 ZIP verisi decode edildi.")

                    # ZIP dosyasını aç ve PDF dosyasını çıkar
                    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                        for file_name in zf.namelist():
                            if file_name.endswith(".pdf"):
                                pdf_data = zf.read(file_name)
                                _logger.info(f"PDF dosyası bulundu: {file_name}")
                                _logger.info("PDF verisi okunuyor...")
                                _logger.info(f"PDF veri boyutu: {len(pdf_data)} bayt")
                                # PDF dosyasını kaydet
                                with open(file_name, "wb") as pdf_file:
                                    pdf_file.write(pdf_data)
                                print(f"PDF dosyası başarıyla indirildi: {file_name}")

                                if document_type == "FATURA":
                                    model = "account.move"
                                elif document_type == "IRSALIYE":
                                    model = "stock.picking"

                                # Save pdf file
                                attachment = self.env["ir.attachment"].create(
                                    {
                                        "name": file_name,
                                        "datas": base64.b64encode(pdf_data),
                                        "res_model": model,
                                        "res_id": self.id,
                                        "type": "binary",
                                    }
                                )

                                return attachment
                    print("ZIP dosyasında PDF bulunamadı.")
                else:
                    print("Yanıt içerisinde <return> elementi bulunamadı.")
            except Exception as e:
                print(f"Bir hata oluştu: {e}")
        else:
            print(f"SOAP isteği başarısız oldu: {response.status_code}")

    def check_invoice_status(self, oid, invoice_record):

        # MdxUtilityMixin.check_license(self)

        # Kullanıcı bilgilerini al
        web_service = self.env["mdx.web.service"].search(
            [
                ("name", "=", "EFINANS_GONDERICI"),
                ("active", "=", True),
                ("company_id", "=", self.env.user.company_id.id),
            ],
            limit=1,
        )
        username = str(web_service.username)
        password = str(web_service.password)
        url = web_service.url
        vkn = str(web_service.vkn)

        # SOAP talebi oluştur
        post_string = f"""
            <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
            xmlns:ser="http://service.connector.uut.cs.com.tr/">
            <soapenv:Header>
                <wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
                    <wsse:UsernameToken>
                        <wsse:Username>{username}</wsse:Username>
                        <wsse:Password>{password}</wsse:Password>
                    </wsse:UsernameToken>
                </wsse:Security>
            </soapenv:Header>
            <soapenv:Body>
                <ser:gidenBelgeDurumSorgulaExt>
                    <vergiTcKimlikNo>{vkn}</vergiTcKimlikNo>
                    <parametreler>
                        <belgeNo>{oid}</belgeNo>
                        <belgeNoTipi>OID</belgeNoTipi>
                        <donusTipiVersiyon>6.0</donusTipiVersiyon>
                    </parametreler>
                </ser:gidenBelgeDurumSorgulaExt>
            </soapenv:Body>
            </soapenv:Envelope>
        """

        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}

        # Talebi gönder
        response = requests.post(url, data=post_string, headers=headers)

        if response.status_code == 200:
            root = ET.fromstring(response.content)

            # 'ns2' ad alanını doğru şekilde kullanmak
            namespaces = {
                "S": "http://schemas.xmlsoap.org/soap/envelope/",
                "ns2": "http://service.connector.uut.cs.com.tr/",
            }

            # <return> elementini bul
            return_element = root.find(
                ".//ns2:gidenBelgeDurumSorgulaExtResponse/return", namespaces
            )

            def get_element_text(xpath):
                # XML parse işlemi ile element bulunması
                element = return_element.find(xpath)
                if element is not None:
                    return element.text
                return None

            # XML'den değerleri çek
            aciklama = get_element_text("aciklama")
            alim_tarihi = get_element_text("alimTarihi")
            durum = get_element_text("durum")
            gonderim_cevabi_kodu = get_element_text("gonderimCevabiKodu")
            gonderim_durumu = get_element_text("gonderimDurumu")
            yanit_durumu = get_element_text("yanitDurumu")
            ulasti_mi = get_element_text("ulastiMi")
            yeniden_gonderilebilir_mi = get_element_text("yenidenGonderilebilirMi")
            yerel_belge_oid = get_element_text("yerelBelgeOid")

            # Eğer açıklama yoksa, belgeNo'yu kullan
            if not aciklama:
                aciklama = get_element_text("belgeNo")
            else:
                invoice_record.write({"uuid": ""})

            # # "SAXParseException" kontrolü
            # if "SAXParseException" in aciklama:
            #     raise UserError(f"Yanıt XML hatası içeriyor: {aciklama}")

            # Durum detayını oluştur
            durum_detay = self.EbelgeDurumDetay(
                aciklama or "Bilinmiyor",
                alim_tarihi or "Bilinmiyor",
                durum or "0",
                gonderim_cevabi_kodu or "-1",
                gonderim_durumu or "-2",
                yanit_durumu or "-1",
                ulasti_mi or "false",
                yeniden_gonderilebilir_mi or "false",
                yerel_belge_oid or "0",
            )

            # Invoice kaydına verileri yaz
            invoice_record.write(
                {
                    "logging_field6": durum_detay,
                    "belge_oid_kod": durum_detay.belge_oid if durum != "2" else "",
                    "fatura_durum_detay": f"""Açıklama: {str(durum_detay.aciklama)}\nAlım Tarihi: {str(durum_detay.alim_tarihi)}\nDurum: {str(durum_detay.durum)}\nGönderim Cevabı Kodu: {str(durum_detay.gonderim_cevabi_kodu)}\nGönderim Durumu: {str(durum_detay.gonderim_durumu)}\nYanıt Durumu: {str(durum_detay.yanit_durumu)}\nUlaştı Mı: {str(durum_detay.ulasti_mi)}\nYeniden Gönderilebilir Mi: {str(durum_detay.yeniden_gonderilebilir_mi)}""",
                }
            )
        else:
            raise UserError("Fatura durum sorgulama işlemi başarısız oldu.")

        return response.text

    def generate_waybill_xml(self, waybill_record, preview_mode=False):

        # MdxUtilityMixin.check_license(self)

        partner_id = waybill_record.sale_id.partner_id.commercial_partner_id

        # if partner_id.type != "delivery":
        #     # Find Delivery Address
        #     partner_delivery_address_id = self.env["res.partner"].search(
        #         [("parent_id", "=", partner_id.id), ("type", "=", "delivery")], limit=1
        #     )
        # elif partner_id.type == "delivery":
        partner_delivery_address_id = waybill_record.partner_id
        # partner_id = waybill_record.partner_id.parent_id

        partner_website = partner_id.website or ""

        partner_address = (
            (partner_id.street or "")
            + " "
            + (partner_id.street2 or "")
            + " "
            + (partner_id.zip or "")
        )
        partner_address = partner_address.replace("&", " ")
        partner_city = partner_id.city or ""
        partner_state = partner_id.state_id.name or ""
        partner_country = partner_id.country_id.name or ""
        partner_zip = partner_id.zip or ""
        partner_vergi_dairesi = partner_id.vergi_dairesi or ""
        partner_phone = partner_id.phone or ""
        partner_email = partner_id.email or ""

        if partner_delivery_address_id:
            partner_delivery_address = (
                (partner_delivery_address_id.street or "")
                + " "
                + (partner_delivery_address_id.street2 or "")
                + " "
                + (partner_delivery_address_id.zip or "")
            )
            partner_delivery_address = partner_delivery_address.replace("&", " ")
            partner_delivery_city = partner_delivery_address_id.city or ""
            partner_delivery_state = partner_delivery_address_id.state_id.name or ""
            partner_delivery_country = partner_delivery_address_id.country_id.name or ""
            partner_delivery_zip = partner_delivery_address_id.zip or ""
            partner_delivery_vergi_dairesi = (
                partner_delivery_address_id.vergi_dairesi or ""
            )
            partner_delivery_phone = partner_delivery_address_id.phone or ""
            partner_delivery_email = partner_delivery_address_id.email or ""
        else:
            partner_delivery_address = partner_address
            partner_delivery_city = partner_city
            partner_delivery_state = partner_state
            partner_delivery_country = partner_country
            partner_delivery_zip = partner_zip
            partner_delivery_vergi_dairesi = partner_vergi_dairesi
            partner_delivery_phone = partner_phone
            partner_delivery_email = partner_email

        carrier_partner_id = waybill_record.nakliye_sirketi_id
        if carrier_partner_id:
            carrier_partner_name = (
                carrier_partner_id.name or carrier_partner_id.parent_id.name or ""
            )
            carrier_partner_vkn = carrier_partner_id.vat or ""
            carrier_partner_website = carrier_partner_id.website or ""
            carrier_partner_email = carrier_partner_id.email or ""
            carrier_partner_phone = carrier_partner_id.phone or ""
            # carrier_partner_fax = carrier_partner_id.fax
            carrier_partner_vergi_dairesi = carrier_partner_id.vergi_dairesi or ""

            carrier_billing_address = self.env["res.partner"].search(
                [("parent_id", "=", carrier_partner_id.id), ("type", "=", "invoice")],
                limit=1,
            )

            if carrier_billing_address:
                carrier_billing_address = (
                    (carrier_billing_address.street or "")
                    + " "
                    + (carrier_billing_address.street2 or "")
                    + " "
                    + (carrier_billing_address.zip or "")
                )
                carrier_billing_address = carrier_billing_address.replace("&", " ")
                carrier_city = carrier_billing_address.city or ""
                carrier_state = carrier_billing_address.state_id.name or ""
                carrier_country = carrier_billing_address.country_id.name or ""
                carrier_zip = carrier_billing_address.zip or ""
                carrier_vergi_dairesi = carrier_billing_address.vergi_dairesi or ""
            else:
                carrier_address = (
                    (carrier_partner_id.street or "")
                    + " "
                    + (carrier_partner_id.street2 or "")
                    + " "
                    + (carrier_partner_id.zip or "")
                )
                carrier_address = carrier_address.replace("&", " ")
                carrier_city = carrier_partner_id.city or ""
                carrier_state = carrier_partner_id.state_id.name or ""
                carrier_country = carrier_partner_id.country_id.name or ""
                carrier_zip = carrier_partner_id.zip or ""
                carrier_vergi_dairesi = carrier_partner_id.vergi_dairesi or ""

        # picking_type_id = waybill_record.picking_type_id
        date_deadline = waybill_record.date_deadline
        origin = waybill_record.origin

        user_tz = (
            self.env.user.tz or "UTC"
        )  # Kullanıcının zaman dilimini al, yoksa UTC kullan
        local_tz = timezone(user_tz)

        # Zamanı kullanıcı saat dilimine çevir
        issue_date_utc = waybill_record.scheduled_date.replace(tzinfo=timezone("UTC"))
        issue_date_local = issue_date_utc.astimezone(local_tz)

        issue_date_str = issue_date_local.strftime("%Y-%m-%d")
        issue_time = issue_date_local.strftime("%H:%M:%S")

        irsaliye_seri_id = waybill_record.irsaliye_seri_id

        if not irsaliye_seri_id:
            waybill_record.write({"irsaliye_no": ""})
            raise UserError(
                "İrsaliye serisi bulunamadı! Lütfen irsaliye serisini kontrol edin."
            )
        
        irsaliye_seri_last_used_date = (
            irsaliye_seri_id.last_used_date or datetime.today().date()
        )
        irsaliye_seri_last_used_date_str = irsaliye_seri_last_used_date.strftime(
            "%Y-%m-%d"
        )
        # if irsaliye_seri_last_used_date > issue_date:
        #     raise ValueError(f"Fatura serisinde sonraki tarihli irsaliye bulunmaktadır! Serideki son kullanılan tarih: {fatura_seri_last_used_date_str} - Fatura tarihi: {issue_date_str}")

        eski_irsaliye_no = waybill_record.irsaliye_no
        irsaliye_seri_code = irsaliye_seri_id.code
        year = issue_date_str.split("-")[0]

        if eski_irsaliye_no and eski_irsaliye_no.startswith(irsaliye_seri_code):
            irsaliye_no = eski_irsaliye_no
        else:
            # WRITE İŞLEMİNİ ENGELLE
            if not preview_mode:
                # Bu yıl içinde bu seri ilk kez mi kullanılıyor?
                current_year = issue_date_local.year
                waybill_with_serial_in_year = self.env["stock.picking"].search(
                    [
                        ("irsaliye_seri_id", "=", irsaliye_seri_id.id),
                        ("state", "=", "done"),
                        ("scheduled_date", ">=", f"{current_year}-01-01"),
                        ("scheduled_date", "<=", f"{current_year}-12-31"),
                    ],
                    limit=1,
                )

                if not waybill_with_serial_in_year:
                    # Bu yıl ilk kez kullanılıyor, sırayı 1'den başlat
                    irsaliye_seri_index = 1
                    # Seri kaydındaki index'i de 1'e çek
                    irsaliye_seri_id.write({"index": 1})
                else:
                    irsaliye_seri_index = irsaliye_seri_id.index
                    
                irsaliye_seri_id.write(
                    {"index": irsaliye_seri_index + 1, "last_used_date": issue_date_local}
                )
                irsaliye_no = f"{irsaliye_seri_code}{year}{str(irsaliye_seri_index).zfill(9)}"
                waybill_record.write(
                    {
                        "logging_field7": irsaliye_no
                        + " - "
                        + str(irsaliye_seri_index)
                        + " - "
                        + year
                    }
                )
                waybill_record.write({"irsaliye_no": irsaliye_no})
            else:
                irsaliye_no = waybill_record.name

        # Update document counter
        document_sayac_id = self.env["mdx.dokuman.sayac"].search(
            [
                # ('company_id', '=', invoice_record.company_id.id),
                # ('ebelge_turu_id', '=', invoice_record.efatura_turu_id.id),
                ("code", "=", "DOKUMANSAYAC"),
                ("active", "=", True),
            ],
            limit=1,
        )

        if not document_sayac_id:
            raise ValueError("Giden E-İrsaliye sayacı bulunamadı!")

        document_counter = document_sayac_id.gonderilecek_sonraki_sira_no
        if not preview_mode:
            document_sayac_id.write(
                {
                    "gonderilecek_sonraki_sira_no": document_counter + 1,
                    "last_used_date": issue_date_local,
                }
            )

        # Prepare dynamic fields
        ebelge_turu_id = waybill_record.ebelge_turu_id
        eirsaliye_senaryo_id = waybill_record.eirsaliye_senaryo_id
        irsaliye_tipi_id = waybill_record.irsaliye_tipi_id
        uuid = waybill_record.uuid
        if not uuid:
            uuid = self.generate_uuid()
            # WRITE İŞLEMİNİ ENGELLE
            if not preview_mode:
                waybill_record.write({"uuid": uuid})

        irsaliye_aciklama = waybill_record.irsaliye_aciklama or ""

        separator = "*** EK AÇIKLAMALAR ***"
        if separator in irsaliye_aciklama:
            parts = irsaliye_aciklama.split(separator)
            system_part = parts[0].strip()
            user_part = parts[1].strip()
            
            # Kullanıcı notu yoksa ayıracı at, sadece sistem notunu kullan
            if not user_part:
                irsaliye_aciklama = system_part

        xml_string = '<?xml version="1.0" encoding="UTF-8"?>'
        xml_string += '<DespatchAdvice xmlns="urn:oasis:names:specification:ubl:schema:xsd:DespatchAdvice-2" xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2" xmlns:n4="http://www.altova.com/samplexml/other-namespace" xsi:schemaLocation="urn:oasis:names:specification:ubl:schema:xsd:DespatchAdvice-2 ../xsdrt/maindoc/UBL-DespatchAdvice-2.1.xsd">'
        xml_string += "<ext:UBLExtensions>"
        xml_string += "<ext:UBLExtension>"
        xml_string += "<ext:ExtensionContent/>"
        xml_string += "</ext:UBLExtension>"
        xml_string += "</ext:UBLExtensions>"
        xml_string += "<cbc:UBLVersionID>2.1</cbc:UBLVersionID>"
        xml_string += "<cbc:CustomizationID>TR1.2</cbc:CustomizationID>"
        xml_string += "<cbc:ProfileID>" + eirsaliye_senaryo_id.code + "</cbc:ProfileID>"
        xml_string += "<cbc:ID>" + irsaliye_no + "</cbc:ID>"
        xml_string += "<cbc:CopyIndicator>false</cbc:CopyIndicator>"
        xml_string += "<cbc:UUID>" + uuid + "</cbc:UUID>"
        xml_string += "<cbc:IssueDate>" + str(issue_date_str) + "</cbc:IssueDate>"
        xml_string += "<cbc:IssueTime>" + str(issue_time) + "</cbc:IssueTime>"
        xml_string += (
            "<cbc:DespatchAdviceTypeCode>"
            + irsaliye_tipi_id.code
            + "</cbc:DespatchAdviceTypeCode>"
        )
        xml_string += "<cbc:Note>" + irsaliye_aciklama + "</cbc:Note>"
        # *** TEST ***
        # xml_string += "<cbc:Note>" + "Delivery Address ID: " + str(partner_delivery_address_id.id) + "</cbc:Note>"
        # xml_string += "<cbc:Note>" + "Partner ID: " + str(partner_id.id) + "</cbc:Note>"

        if origin:
            origin_sale_order = self.env["sale.order"].search(
                [("name", "=", origin)], limit=1
            )
            if origin_sale_order:
                xml_string += "<cac:OrderReference>"
                xml_string += "<cbc:ID>" + origin_sale_order.name + "</cbc:ID>"
                xml_string += (
                    "<cbc:IssueDate>"
                    + str(origin_sale_order.date_order.strftime("%Y-%m-%d"))
                    + "</cbc:IssueDate>"
                )
                xml_string += "</cac:OrderReference>"
            else:
                # TODO : SALES ORDER'DAN BAŞKA BİR ORIGIN VARSA NE YAPILACAK?
                xml_string += "<cbc:Note>*** KONSİNYE İRSALİYESİDİR ***\n*** FATURA EDİLMEYECEKTİR  ***</cbc:Note>"
        else:
            xml_string += "<cbc:Note>*** KONSİNYE İRSALİYESİDİR ***\n*** FATURA EDİLMEYECEKTİR  ***</cbc:Note>"

        if irsaliye_tipi_id.code == "MATBUUDAN":
            matbuu_belge_tarihi = waybill_record.matbuu_belge_tarihi or issue_date_str
            matbuu_belge_no = waybill_record.matbuu_belge_no or ""

            xml_string += "<cac:AdditionalDocumentReference>"
            xml_string += "<cbc:ID>" + irsaliye_no + "</cbc:ID>"
            xml_string += "<cbc:IssueDate>" + str(issue_date_str) + "</cbc:IssueDate>"
            xml_string += "<cbc:DocumentType>MATBU</cbc:DocumentType>"
            xml_string += "</cac:AdditionalDocumentReference>"

        xml_string += "<cac:AdditionalDocumentReference>"
        xml_string += "<cbc:ID>" + irsaliye_no + "</cbc:ID>"
        xml_string += "<cbc:IssueDate>" + str(issue_date_str) + "</cbc:IssueDate>"
        xml_string += "<cbc:DocumentType>XSLT</cbc:DocumentType>"
        xml_string += "</cac:AdditionalDocumentReference>"

        company_name = waybill_record.company_id.name or ""
        company_vkn = waybill_record.company_id.vat or ""
        company_phone = waybill_record.company_id.phone or ""
        company_email = waybill_record.company_id.email or ""
        company_website = waybill_record.company_id.website or ""
        company_city = waybill_record.company_id.city or ""
        company_state = waybill_record.company_id.state_id.name or ""
        company_zip = waybill_record.company_id.zip or ""
        company_country = waybill_record.company_id.country_id.name or ""
        company_vergi_dairesi = waybill_record.company_id.vergi_dairesi or ""
        company_mersis_no = waybill_record.company_id.mersis_no or ""
        company_ticaret_sicil_no = waybill_record.company_id.ticaret_sicil_no or ""
        gumruk_ticaret_bakanligi_carisi = (
            waybill_record.company_id.gumruk_ticaret_bakanligi_carisi_id or ""
        )
        company_address = (
            waybill_record.company_id.street
            or "" + "\n" + waybill_record.company_id.street2
            or "" + "\n" + waybill_record.company_id.zip
            or ""
        )

        # Şirket Bilgileri
        xml_string += "<cac:Signature>"
        xml_string += '<cbc:ID schemeID="VKN_TCKN">' + company_vkn + "</cbc:ID>"
        xml_string += "<cac:SignatoryParty>"
        xml_string += "<cac:PartyIdentification>"
        xml_string += '<cbc:ID schemeID="VKN">' + company_vkn + "</cbc:ID>"
        xml_string += "</cac:PartyIdentification>"
        xml_string += "<cac:PostalAddress>"
        xml_string += "<cbc:StreetName>" + company_address + "</cbc:StreetName>"
        xml_string += (
            "<cbc:CitySubdivisionName>" + company_state + "</cbc:CitySubdivisionName>"
        )
        xml_string += "<cbc:CityName>" + company_city + "</cbc:CityName>"
        xml_string += "<cbc:PostalZone>" + company_zip + "</cbc:PostalZone>"
        xml_string += "<cac:Country>"
        xml_string += "<cbc:Name>" + company_country + "</cbc:Name>"
        xml_string += "</cac:Country>"
        xml_string += "</cac:PostalAddress>"
        xml_string += "</cac:SignatoryParty>"
        xml_string += "<cac:DigitalSignatureAttachment>"
        xml_string += "<cac:ExternalReference>"
        xml_string += "<cbc:URI>" + "#Signature_---" + irsaliye_no + "</cbc:URI>"
        xml_string += "</cac:ExternalReference>"
        xml_string += "</cac:DigitalSignatureAttachment>"
        xml_string += "</cac:Signature>"

        xml_string += "<cac:DespatchSupplierParty>"
        xml_string += "<cac:Party>"
        xml_string += "<cbc:WebsiteURI>" + (company_website or "") + "</cbc:WebsiteURI>"
        xml_string += "<cac:PartyIdentification>"
        xml_string += '<cbc:ID schemeID="VKN">' + company_vkn + "</cbc:ID>"
        xml_string += "</cac:PartyIdentification>"
        xml_string += "<cac:PartyName>"
        xml_string += "<cbc:Name>" + company_name + "</cbc:Name>"
        xml_string += "</cac:PartyName>"
        xml_string += "<cac:PostalAddress>"
        xml_string += "<cbc:Room></cbc:Room>"
        xml_string += "<cbc:StreetName>" + company_address + "</cbc:StreetName>"
        xml_string += "<cbc:BuildingName></cbc:BuildingName>"
        xml_string += "<cbc:BuildingNumber></cbc:BuildingNumber>"
        xml_string += (
            "<cbc:CitySubdivisionName>" + company_state + "</cbc:CitySubdivisionName>"
        )
        xml_string += "<cbc:CityName>" + company_city + "</cbc:CityName>"
        xml_string += "<cbc:PostalZone>" + company_zip + "</cbc:PostalZone>"
        xml_string += "<cbc:Region></cbc:Region>"
        xml_string += "<cbc:District></cbc:District>"
        xml_string += "<cac:Country>"
        xml_string += "<cbc:Name>" + company_zip + "</cbc:Name>"
        xml_string += "</cac:Country>"
        xml_string += "</cac:PostalAddress>"
        xml_string += "<cac:PhysicalLocation>"
        xml_string += "<cbc:ID>Fiziki Çıkış Adresi</cbc:ID>"
        xml_string += "<cac:Address>"
        xml_string += "<cbc:Room></cbc:Room>"
        xml_string += "<cbc:StreetName>" + company_address + "</cbc:StreetName>"
        xml_string += "<cbc:BuildingName></cbc:BuildingName>"
        xml_string += "<cbc:BuildingNumber></cbc:BuildingNumber>"
        xml_string += (
            "<cbc:CitySubdivisionName>" + company_state + "</cbc:CitySubdivisionName>"
        )
        xml_string += "<cbc:CityName>" + company_city + "</cbc:CityName>"
        xml_string += "<cbc:PostalZone>" + company_zip + "</cbc:PostalZone>"
        xml_string += "<cbc:Region></cbc:Region>"
        xml_string += "<cbc:District></cbc:District>"
        xml_string += "<cac:Country>"
        xml_string += "<cbc:Name>" + company_country + "</cbc:Name>"
        xml_string += "</cac:Country>"
        xml_string += "</cac:Address>"
        xml_string += "</cac:PhysicalLocation>"
        xml_string += "<cac:PartyTaxScheme>"
        xml_string += "<cac:TaxScheme>"
        xml_string += "<cbc:Name>" + company_vergi_dairesi + "</cbc:Name>"
        xml_string += "<cbc:TaxTypeCode></cbc:TaxTypeCode>"
        xml_string += "</cac:TaxScheme>"
        xml_string += "</cac:PartyTaxScheme>"
        xml_string += "<cac:Contact>"
        xml_string += "<cbc:Telephone>" + company_phone + "</cbc:Telephone>"
        # xml_string += '<cbc:Telefax>' + company_fax + '</cbc:Telefax>'
        xml_string += "<cbc:ElectronicMail>" + company_email + "</cbc:ElectronicMail>"
        xml_string += "</cac:Contact>"
        xml_string += "</cac:Party>"
        xml_string += "<cac:DespatchContact>"
        xml_string += "<cbc:Name>" + company_name + "</cbc:Name>"
        xml_string += "<cbc:Telephone/>"
        xml_string += "<cbc:Telefax/>"
        xml_string += "<cbc:ElectronicMail/>"
        xml_string += "</cac:DespatchContact>"
        xml_string += "</cac:DespatchSupplierParty>"

        xml_string += "<cac:DeliveryCustomerParty>"
        xml_string += "<cac:Party>"
        xml_string += "<cbc:WebsiteURI>" + (partner_delivery_address_id.commercial_partner_id.website or "") + "</cbc:WebsiteURI>"
        xml_string += "<cac:PartyIdentification>"

        if len(partner_delivery_address_id.commercial_partner_id.vat) == 10:
            xml_string += '<cbc:ID schemeID="VKN">' + partner_delivery_address_id.commercial_partner_id.vat + "</cbc:ID>"
        elif len(partner_delivery_address_id.commercial_partner_id.vat) == 11:
            xml_string += '<cbc:ID schemeID="TCKN">' + partner_delivery_address_id.commercial_partner_id.vat + "</cbc:ID>"

        xml_string += "</cac:PartyIdentification>"
        xml_string += "<cac:PartyName>"
        xml_string += "<cbc:Name>" + partner_delivery_address_id.name + "</cbc:Name>"
        xml_string += "</cac:PartyName>"
        xml_string += "<cac:PostalAddress>"
        xml_string += "<cbc:Room></cbc:Room>"
        xml_string += (
            "<cbc:StreetName>" + partner_delivery_address + "</cbc:StreetName>"
        )
        xml_string += "<cbc:BuildingName></cbc:BuildingName>"
        xml_string += "<cbc:BuildingNumber></cbc:BuildingNumber>"
        xml_string += (
            "<cbc:CitySubdivisionName>"
            + partner_delivery_state
            + "</cbc:CitySubdivisionName>"
        )
        xml_string += "<cbc:CityName>" + partner_delivery_city + "</cbc:CityName>"
        xml_string += "<cbc:PostalZone>" + partner_delivery_zip + "</cbc:PostalZone>"
        xml_string += "<cbc:Region></cbc:Region>"
        xml_string += "<cbc:District></cbc:District>"
        if partner_delivery_country:
            xml_string += "<cac:Country>"
            xml_string += "<cbc:Name>" + partner_delivery_country + "</cbc:Name>"
            xml_string += "</cac:Country>"
        xml_string += "</cac:PostalAddress>"
        xml_string += "<cac:PhysicalLocation>"
        xml_string += "<cbc:ID>Fiziki Sevk Adresi</cbc:ID>"
        xml_string += "<cac:Address>"
        xml_string += "<cbc:Room></cbc:Room>"
        xml_string += "<cbc:StreetName></cbc:StreetName>"
        xml_string += "<cbc:BuildingName></cbc:BuildingName>"
        xml_string += "<cbc:BuildingNumber></cbc:BuildingNumber>"
        xml_string += (
            "<cbc:CitySubdivisionName>"
            + partner_delivery_state
            + "</cbc:CitySubdivisionName>"
        )
        xml_string += "<cbc:CityName>" + partner_delivery_city + "</cbc:CityName>"
        xml_string += "<cbc:PostalZone>" + partner_delivery_zip + "</cbc:PostalZone>"
        xml_string += "<cbc:Region></cbc:Region>"
        xml_string += "<cbc:District></cbc:District>"
        xml_string += "<cac:Country>"
        xml_string += "<cbc:Name>" + partner_delivery_country + "</cbc:Name>"
        xml_string += "</cac:Country>"
        xml_string += "</cac:Address>"
        xml_string += "</cac:PhysicalLocation>"
        xml_string += "<cac:PartyTaxScheme>"
        xml_string += "<cac:TaxScheme>"
        xml_string += "<cbc:Name>" + partner_delivery_vergi_dairesi + "</cbc:Name>"
        xml_string += "<cbc:TaxTypeCode/>"
        xml_string += "</cac:TaxScheme>"
        xml_string += "</cac:PartyTaxScheme>"
        xml_string += "<cac:Contact>"
        xml_string += "<cbc:Telephone>" + partner_delivery_phone + "</cbc:Telephone>"
        # xml_string += '<cbc:Telefax>' + customer_fax + '</cbc:Telefax>'
        xml_string += (
            "<cbc:ElectronicMail>" + partner_delivery_email + "</cbc:ElectronicMail>"
        )
        xml_string += "</cac:Contact>"
        xml_string += "</cac:Party>"
        xml_string += "</cac:DeliveryCustomerParty>"

        xml_string += "<cac:BuyerCustomerParty>"
        xml_string += "<cac:Party>"
        xml_string += "<cbc:WebsiteURI>" + partner_website + "</cbc:WebsiteURI>"
        xml_string += "<cac:PartyIdentification>"

        if len(partner_id.vat) == 10:
            xml_string += '<cbc:ID schemeID="VKN">' + partner_id.vat + "</cbc:ID>"
        elif len(partner_id.vat) == 11:
            xml_string += '<cbc:ID schemeID="TCKN">' + partner_id.vat + "</cbc:ID>"

        xml_string += "</cac:PartyIdentification>"
        xml_string += "<cac:PartyName>"
        xml_string += "<cbc:Name>" + partner_id.name + "</cbc:Name>"
        xml_string += "</cac:PartyName>"
        xml_string += "<cac:PostalAddress>"
        xml_string += "<cbc:Room></cbc:Room>"
        xml_string += "<cbc:StreetName>" + partner_address + "</cbc:StreetName>"
        xml_string += "<cbc:BuildingName></cbc:BuildingName>"
        xml_string += "<cbc:BuildingNumber></cbc:BuildingNumber>"
        xml_string += (
            "<cbc:CitySubdivisionName>" + partner_state + "</cbc:CitySubdivisionName>"
        )
        xml_string += "<cbc:CityName>" + partner_city + "</cbc:CityName>"
        xml_string += "<cbc:PostalZone>" + partner_zip + "</cbc:PostalZone>"
        xml_string += "<cbc:Region></cbc:Region>"
        xml_string += "<cbc:District></cbc:District>"
        xml_string += "<cac:Country>"
        xml_string += "<cbc:Name>" + partner_country + "</cbc:Name>"
        xml_string += "</cac:Country>"
        xml_string += "</cac:PostalAddress>"
        xml_string += "<cac:PartyTaxScheme>"
        xml_string += "<cac:TaxScheme>"
        xml_string += "<cbc:Name>" + partner_vergi_dairesi + "</cbc:Name>"
        xml_string += "<cbc:TaxTypeCode/>"
        xml_string += "</cac:TaxScheme>"
        xml_string += "</cac:PartyTaxScheme>"
        xml_string += "<cac:Contact>"
        xml_string += "<cbc:Telephone>" + partner_phone + "</cbc:Telephone>"
        # xml_string += '<cbc:Telefax>' + customer_fax + '</cbc:Telefax>'
        xml_string += "<cbc:ElectronicMail>" + partner_email + "</cbc:ElectronicMail>"
        xml_string += "</cac:Contact>"
        xml_string += "</cac:Party>"
        xml_string += "</cac:BuyerCustomerParty>"

        if carrier_partner_id:
            if carrier_partner_id:
                if not carrier_partner_id.vat:
                    raise UserError("Lütfen nakliye şirketinin vergi numarasını doldurun.")
                if not carrier_partner_id.zip:
                    raise UserError("Lütfen nakliye şirketinin posta kodunu doldurun.")

            xml_string += "<cac:Shipment>"
            xml_string += "<cbc:ID></cbc:ID>"
            xml_string += "<cac:Delivery>"
            xml_string += "<cac:DeliveryAddress>"
            xml_string += "<cbc:Room></cbc:Room>"
            xml_string += "<cbc:StreetName>" + carrier_address + "</cbc:StreetName>"
            xml_string += "<cbc:BuildingName></cbc:BuildingName>"
            xml_string += "<cbc:BuildingNumber></cbc:BuildingNumber>"
            xml_string += (
                "<cbc:CitySubdivisionName>"
                + carrier_state
                + "</cbc:CitySubdivisionName>"
            )
            xml_string += "<cbc:CityName>" + carrier_city + "</cbc:CityName>"
            xml_string += "<cbc:PostalZone>" + carrier_zip + "</cbc:PostalZone>"
            xml_string += "<cbc:Region></cbc:Region>"
            xml_string += "<cbc:District></cbc:District>"
            xml_string += "<cac:Country>"
            xml_string += "<cbc:Name>" + carrier_country + "</cbc:Name>"
            xml_string += "</cac:Country>"
            xml_string += "</cac:DeliveryAddress>"
            xml_string += "<cac:CarrierParty>"
            xml_string += "<cbc:WebsiteURI></cbc:WebsiteURI>"
            xml_string += "<cac:PartyIdentification>"
            xml_string += (
                '<cbc:ID schemeID="VKN">' + str(carrier_partner_vkn) + "</cbc:ID>"
            )
            xml_string += "</cac:PartyIdentification>"
            xml_string += "<cac:PartyName>"
            xml_string += "<cbc:Name>" + carrier_partner_name + "</cbc:Name>"
            xml_string += "</cac:PartyName>"
            xml_string += "<cac:PostalAddress>"
            xml_string += "<cbc:Room></cbc:Room>"
            xml_string += "<cbc:StreetName>" + carrier_address + "</cbc:StreetName>"
            xml_string += "<cbc:BuildingName></cbc:BuildingName>"
            xml_string += "<cbc:BuildingNumber></cbc:BuildingNumber>"
            xml_string += (
                "<cbc:CitySubdivisionName>"
                + carrier_state
                + "</cbc:CitySubdivisionName>"
            )
            xml_string += "<cbc:CityName>" + carrier_city + "</cbc:CityName>"
            xml_string += "<cbc:PostalZone>" + carrier_zip + "</cbc:PostalZone>"
            xml_string += "<cbc:Region></cbc:Region>"
            xml_string += "<cbc:District></cbc:District>"
            xml_string += "<cac:Country>"
            xml_string += "<cbc:Name>" + carrier_country + "</cbc:Name>"
            xml_string += "</cac:Country>"
            xml_string += "</cac:PostalAddress>"
            xml_string += "<cac:Contact>"
            xml_string += "<cbc:Telephone>" + carrier_partner_phone + "</cbc:Telephone>"
            # xml_string += '<cbc:Telefax>' + carrier_company_fax + '</cbc:Telefax>'
            xml_string += (
                "<cbc:ElectronicMail>" + carrier_partner_email + "</cbc:ElectronicMail>"
            )
            xml_string += "</cac:Contact>"
            xml_string += "</cac:CarrierParty>"
            xml_string += "<cac:Despatch>"
            xml_string += (
                "<cbc:ActualDespatchDate>"
                + str(issue_date_str)
                + "</cbc:ActualDespatchDate>"
            )
            xml_string += (
                "<cbc:ActualDespatchTime>"
                + str(issue_time)
                + "</cbc:ActualDespatchTime>"
            )
            xml_string += "</cac:Despatch>"
            xml_string += "</cac:Delivery>"
            xml_string += "</cac:Shipment>"
        else:
            # sofor_adi = waybill_record.sofor_adi or ""
            # sofor_soyadi = waybill_record.sofor_soyadi or ""
            # sofor_tc_no = waybill_record.sofor_tc_no or ""
            # sofor_ilce = waybill_record.sofor_ilce or ""
            # sofor_il = waybill_record.sofor_il or ""
            # sofor_zip = waybill_record.sofor_zip or ""
            # sofor_ulke = waybill_record.sofor_ulke or ""
            # arac_plaka_no = waybill_record.arac_plaka_no or ""

            sofor_adi = waybill_record.sofor_adi
            sofor_soyadi = waybill_record.sofor_soyadi
            sofor_tc_no = waybill_record.sofor_tc_no
            sofor_ilce = waybill_record.sofor_ilce or ""
            sofor_il = waybill_record.sofor_il or ""
            sofor_zip = waybill_record.sofor_zip
            sofor_ulke = waybill_record.sofor_ulke or ""
            arac_plaka_no = waybill_record.arac_plaka_no or ""

            if (
                not sofor_adi
                or not sofor_soyadi
                or not sofor_tc_no
                or not arac_plaka_no
            ):
                raise UserError(
                    "Lütfen nakliye şirketi seçin veya şoför bilgilerini (Şoför adı, soyadı, TCKN, posta kodu) doldurun."
                )

            # Firmanın Kendi Araçları Taşıyorsa
            xml_string += "<cac:Shipment>"
            xml_string += "<cbc:ID></cbc:ID>"
            xml_string += "<cac:ShipmentStage>"
            xml_string += "<cac:TransportMeans>"
            xml_string += "<cac:RoadTransport>"
            xml_string += (
                '<cbc:LicensePlateID schemeID="PLAKA">'
                + arac_plaka_no
                + "</cbc:LicensePlateID>"
            )
            xml_string += "</cac:RoadTransport>"
            xml_string += "</cac:TransportMeans>"
            xml_string += "<cac:DriverPerson>"
            xml_string += "<cbc:FirstName>" + sofor_adi + "</cbc:FirstName>"
            xml_string += "<cbc:FamilyName>" + sofor_soyadi + "</cbc:FamilyName>"
            xml_string += "<cbc:Title>Şoför</cbc:Title>"
            xml_string += "<cbc:NationalityID>" + sofor_tc_no + "</cbc:NationalityID>"
            xml_string += "</cac:DriverPerson>"
            xml_string += "</cac:ShipmentStage>"
            xml_string += "<cac:Delivery>"
            xml_string += "<cac:DeliveryAddress>"
            xml_string += "<cbc:Room></cbc:Room>"
            xml_string += "<cbc:StreetName></cbc:StreetName>"
            xml_string += "<cbc:BuildingName></cbc:BuildingName>"
            xml_string += "<cbc:BuildingNumber></cbc:BuildingNumber>"
            xml_string += (
                "<cbc:CitySubdivisionName>" + sofor_ilce + "</cbc:CitySubdivisionName>"
            )
            xml_string += "<cbc:CityName>" + sofor_il + "</cbc:CityName>"
            xml_string += "<cbc:PostalZone>" + sofor_zip + "</cbc:PostalZone>"
            xml_string += "<cbc:Region></cbc:Region>"
            xml_string += "<cbc:District></cbc:District>"
            xml_string += "<cac:Country>"
            xml_string += "<cbc:Name>" + sofor_ulke + "</cbc:Name>"
            xml_string += "</cac:Country>"
            xml_string += "</cac:DeliveryAddress>"
            xml_string += "<cac:Despatch>"
            xml_string += (
                "<cbc:ActualDespatchDate>"
                + str(issue_date_str)
                + "</cbc:ActualDespatchDate>"
            )
            xml_string += (
                "<cbc:ActualDespatchTime>"
                + str(issue_time)
                + "</cbc:ActualDespatchTime>"
            )
            xml_string += "</cac:Despatch>"
            xml_string += "</cac:Delivery>"
            xml_string += "<cac:TransportHandlingUnit/>"
            xml_string += "</cac:Shipment>"

        for line_index, line in enumerate(waybill_record.move_ids, start=1):
            # description_pickingout = line.product_id.description_pickingout or ""
            line_unit_code = line.product_id.uom_id._get_unece_code() or "C62"

            xml_string += "<cac:DespatchLine>"
            xml_string += "<cbc:ID>" + str(line_index) + "</cbc:ID>"
            # TODO : Ölçü birimi değiştirilecek
            xml_string += (
                '<cbc:DeliveredQuantity unitCode="'
                + str(line_unit_code)
                + '">'
                + str(line.product_uom_qty)
                + "</cbc:DeliveredQuantity>"
            )
            # xml_string += '<cbc:OutstandingReason>' + outstanding_reason + '</cbc:OutstandingReason>'
            xml_string += "<cac:OrderLineReference>"
            xml_string += "<cbc:LineID>" + str(line_index) + "</cbc:LineID>"
            xml_string += "</cac:OrderLineReference>"
            xml_string += "<cac:Item>"
            xml_string += "<cbc:Description></cbc:Description>"
            product_name = str(line.product_id.name)
            cleaned_name = re.sub(r'^\[.*?\]\s*', '', product_name)
            xml_string += "<cbc:Name>" + cleaned_name + "</cbc:Name>"
            xml_string += "<cac:BuyersItemIdentification>"
            xml_string += "<cbc:ID></cbc:ID>"
            xml_string += "</cac:BuyersItemIdentification>"
            xml_string += "<cac:SellersItemIdentification>"
            xml_string += "<cbc:ID>" + str(line.product_id.default_code) + "</cbc:ID>"
            xml_string += "</cac:SellersItemIdentification>"
            xml_string += "<cac:ManufacturersItemIdentification>"
            xml_string += "<cbc:ID></cbc:ID>"
            xml_string += "</cac:ManufacturersItemIdentification>"
            xml_string += "</cac:Item>"
            xml_string += "<cac:Shipment>"
            xml_string += "<cbc:ID></cbc:ID>"
            xml_string += "<cac:GoodsItem>"
            xml_string += "<cac:InvoiceLine>"
            xml_string += "<cbc:ID></cbc:ID>"
            xml_string += (
                "<cbc:InvoicedQuantity>"
                + str(line.quantity)
                + "</cbc:InvoicedQuantity>"
            )
            xml_string += (
                '<cbc:LineExtensionAmount currencyID="TRY">0</cbc:LineExtensionAmount>'
            )
            xml_string += "<cac:Item>"
            xml_string += "<cbc:Description/>"
            xml_string += "<cbc:Name></cbc:Name>"
            xml_string += "</cac:Item>"
            xml_string += "<cac:Price>"
            xml_string += '<cbc:PriceAmount currencyID="TRY">0</cbc:PriceAmount>'
            xml_string += "</cac:Price>"
            xml_string += "</cac:InvoiceLine>"
            xml_string += "</cac:GoodsItem>"
            xml_string += "</cac:Shipment>"
            xml_string += "</cac:DespatchLine>"

        xml_string += "</DespatchAdvice>"

        return xml_string

    def send_waybill_xml(self, waybill_record, xml_string):

        # MdxUtilityMixin.check_license(self)

        web_service = self.env["mdx.web.service"].search(
            [
                ("name", "=", "EFINANS_GONDERICI"),
                ("active", "=", True),
                ("company_id", "=", self.env.user.company_id.id),
            ],
            limit=1,
        )
        username = web_service.username
        password = web_service.password
        url = web_service.url
        erp_code = web_service.erp_code
        vkn = waybill_record.company_id.vat
        decoded_xml = self.base64_encode(xml_string)
        hash_obj = self.calculate_md5(xml_string)
        counter = (
            self.env["mdx.dokuman.sayac"]
            .search(
                [
                    ("code", "=", "DOKUMANSAYAC"),
                    ("company_id", "=", self.env.user.company_id.id),
                ],
                limit=1,
            )
            .gonderilecek_sonraki_sira_no
        )

        post_string = '<?xml version="1.0" encoding="utf-8"?>'
        post_string += '<soapenv:Envelope xmlns:ser="http://service.connector.uut.cs.com.tr/" xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
        post_string += "<soapenv:Header>"
        post_string += '<wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">'
        post_string += "<wsse:UsernameToken>"
        post_string += "<wsse:Username>" + str(username) + "</wsse:Username>"
        post_string += "<wsse:Password>" + str(password) + "</wsse:Password>"
        post_string += "</wsse:UsernameToken>"
        post_string += "</wsse:Security>"
        post_string += "</soapenv:Header>"
        post_string += "<soapenv:Body>"
        post_string += "<ser:belgeGonderExt>"
        post_string += "<parametreler>"
        post_string += "<belgeHash>" + hash_obj + "</belgeHash>"
        post_string += "<belgeNo>" + str(counter) + "</belgeNo>"
        post_string += "<belgeTuru>IRSALIYE_UBL</belgeTuru>"
        post_string += "<belgeVersiyon>1.2</belgeVersiyon>"
        post_string += "<erpKodu>" + erp_code + "</erpKodu>"
        post_string += "<mimeType>application/xml</mimeType>"
        post_string += "<vergiTcKimlikNo>" + str(vkn) + "</vergiTcKimlikNo>"
        post_string += "<veri>" + decoded_xml + "</veri>"
        post_string += "</parametreler>"
        post_string += "</ser:belgeGonderExt>"
        post_string += "</soapenv:Body>"
        post_string += "</soapenv:Envelope>"

        namespaces = {"ns2": "http://service.connector.uut.cs.com.tr/"}

        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}

        waybill_record.write({"logging_field3": xml_string})
        waybill_record.write({"logging_field2": post_string})

        response = requests.post(url, data=post_string, headers=headers)

        waybill_record.write({"logging_field4": response.content})
        # waybill_record.write({'belge_oid_kod': response.status_code})

        root = ET.fromstring(response.content)

        if response.status_code == 200:

            belge_oid = root.find(
                ".//ns2:belgeGonderExtResponse/belgeOid", namespaces
            ).text

            waybill_record.write({"belge_oid_kod": belge_oid})

        else:

            waybill_record.write({"irsaliye_gonderim_hata_kodu": response.status_code})

            # fault_code = root.find('.//ns2:Fault/faultcode', namespaces).text
            # fault_string = root.find('.//Fault/ns2:faultstring', namespaces).text

            # waybill_record.write({
            #     'fatura_gonderim_hata_kodu':
            #     """Fault Code: {}\nFault String: {}""".format(fault_code, fault_string)
            # })

    def check_waybill_status(self, oid, waybill_record):

        # MdxUtilityMixin.check_license(self)

        # Kullanıcı bilgilerini al
        web_service = self.env["mdx.web.service"].search(
            [
                ("name", "=", "EFINANS_GONDERICI"),
                ("active", "=", True),
                ("company_id", "=", self.env.user.company_id.id),
            ],
            limit=1,
        )
        username = str(web_service.username)
        password = str(web_service.password)
        vkn = str(web_service.vkn)
        url = web_service.url

        # SOAP talebi oluştur
        post_string = f"""
            <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
            xmlns:ser="http://service.connector.uut.cs.com.tr/">
            <soapenv:Header>
                <wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
                    <wsse:UsernameToken>
                        <wsse:Username>{username}</wsse:Username>
                        <wsse:Password>{password}</wsse:Password>
                    </wsse:UsernameToken>
                </wsse:Security>
            </soapenv:Header>
            <soapenv:Body>
                <ser:gidenBelgeDurumSorgulaExt>
                    <vergiTcKimlikNo>{vkn}</vergiTcKimlikNo>
                    <parametreler>
                        <belgeNo>{oid}</belgeNo>
                        <belgeNoTipi>OID</belgeNoTipi>
                        <donusTipiVersiyon>6.0</donusTipiVersiyon>
                    </parametreler>
                </ser:gidenBelgeDurumSorgulaExt>
            </soapenv:Body>
            </soapenv:Envelope>
        """

        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}

        # Talebi gönder
        response = requests.post(url, data=post_string, headers=headers)

        if response.status_code == 200:
            root = ET.fromstring(response.content)

            # 'ns2' ad alanını doğru şekilde kullanmak
            namespaces = {
                "S": "http://schemas.xmlsoap.org/soap/envelope/",
                "ns2": "http://service.connector.uut.cs.com.tr/",
            }

            # <return> elementini bul
            return_element = root.find(
                ".//ns2:gidenBelgeDurumSorgulaExtResponse/return", namespaces
            )

            def get_element_text(xpath):
                # XML parse işlemi ile element bulunması
                element = return_element.find(xpath)
                if element is not None:
                    return element.text
                return None

            # XML'den değerleri çek
            aciklama = get_element_text("aciklama")
            alim_tarihi = get_element_text("alimTarihi")
            durum = get_element_text("durum")
            gonderim_cevabi_kodu = get_element_text("gonderimCevabiKodu")
            gonderim_durumu = get_element_text("gonderimDurumu")
            yanit_durumu = get_element_text("yanitDurumu")
            ulasti_mi = get_element_text("ulastiMi")
            yeniden_gonderilebilir_mi = get_element_text("yenidenGonderilebilirMi")
            yerel_belge_oid = get_element_text("yerelBelgeOid")

            # Eğer açıklama yoksa, belgeNo'yu kullan
            if not aciklama:
                aciklama = get_element_text("belgeNo")
            else:
                waybill_record.write({"uuid": ""})

            # # "SAXParseException" kontrolü
            # if "SAXParseException" in aciklama:
            #     raise UserError(f"Yanıt XML hatası içeriyor: {aciklama}")

            # Durum detayını oluştur
            durum_detay = self.EbelgeDurumDetay(
                aciklama or "Bilinmiyor",
                alim_tarihi or "Bilinmiyor",
                durum or "0",
                gonderim_cevabi_kodu or "-1",
                gonderim_durumu or "-2",
                yanit_durumu or "-1",
                ulasti_mi or "false",
                yeniden_gonderilebilir_mi or "false",
                yerel_belge_oid or "0",
            )

            # Invoice kaydına verileri yaz
            waybill_record.write(
                {
                    "logging_field6": durum_detay,
                    "belge_oid_kod": durum_detay.belge_oid,
                    "irsaliye_durum_detay": f"""Açıklama: {str(durum_detay.aciklama)}\nAlım Tarihi: {str(durum_detay.alim_tarihi)}\nDurum: {str(durum_detay.durum)}\nGönderim Cevabı Kodu: {str(durum_detay.gonderim_cevabi_kodu)}\nGönderim Durumu: {str(durum_detay.gonderim_durumu)}\nYanıt Durumu: {str(durum_detay.yanit_durumu)}\nUlaştı Mı: {str(durum_detay.ulasti_mi)}\nYeniden Gönderilebilir Mi: {str(durum_detay.yeniden_gonderilebilir_mi)}""",
                }
            )
        else:
            raise UserError("İrsaliye durum sorgulama işlemi başarısız oldu.")

        return response.text

    def search_incoming_invoices(self):

        # MdxUtilityMixin.check_license(self)

        web_service = self.env["mdx.web.service"].search(
            [
                ("name", "=", "EFINANS_ALICI"),
                ("active", "=", True),
                ("company_id", "=", self.env.user.company_id.id),
            ],
            limit=1,
        )

        if not web_service:
            raise UserError("Web servisi yapılandırması bulunamadı!")

        username = str(web_service.username)
        password = str(web_service.password)
        url = web_service.url
        erp_code = web_service.erp_code
        vkn = str(self.env.user.company_id.vat)
        year = str(datetime.now().year)

        post_string = f"""<?xml version="1.0" encoding="UTF-8"?>
            <soapenv:Envelope xmlns:ser="http://service.connector.uut.cs.com.tr/"
                xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
                <soapenv:Header>
                    <wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
                        <wsse:UsernameToken>
                            <wsse:Username>{username}</wsse:Username>
                            <wsse:Password>{password}</wsse:Password>
                        </wsse:UsernameToken>
                    </wsse:Security>
                </soapenv:Header>
                <soapenv:Body>
                    <ser:gelenBelgeleriListeleExt>
                        <parametreler>
                            <belgeTuru>FATURA</belgeTuru>
                            <donusTipiVersiyon>6.0</donusTipiVersiyon>
                            <erpKodu>{erp_code}</erpKodu>
                            <vergiTcKimlikNo>{vkn}</vergiTcKimlikNo>
                            <belgelerAlindiMi>true</belgelerAlindiMi>
                        </parametreler>
                    </ser:gelenBelgeleriListeleExt>
                </soapenv:Body>
            </soapenv:Envelope>
        """

        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}

        try:
            response = requests.post(
                url, data=post_string.encode("utf-8"), headers=headers, timeout=60
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise UserError(f"SOAP isteği başarısız! Hata: {str(e)}")

        return_elements = []
        if response.status_code == 200:
            root = ET.fromstring(response.text)

            namespaces = {
                "S": "http://schemas.xmlsoap.org/soap/envelope/",
                "ns2": "http://service.connector.uut.cs.com.tr/",
            }

            return_elements = root.findall(
                ".//ns2:gelenBelgeleriListeleExtResponse/return", namespaces
            )

            belge_sira_no = 0
            for return_elem in return_elements:
                invoice_data = {
                    "company_id": web_service.company_id.id,
                    "name": return_elem.find("belgeNo").text or "",
                    "belge_sira_no": return_elem.find("belgeSiraNo").text or "",
                    "belge_tarihi": (
                        datetime.strptime(
                            return_elem.find("belgeTarihi").text, "%Y%m%d"
                        ).date()
                        if return_elem.find("belgeTarihi") is not None
                        and return_elem.find("belgeTarihi").text
                        else False
                    ),
                    "belge_turu": return_elem.find("belgeTuru").text or "FATURA",
                    "ettn": return_elem.find("ettn").text or "",
                    "gonderen_etiket": return_elem.find("gonderenEtiket").text or "",
                    "gonderen_vkn_tckn": return_elem.find("gonderenVknTckn").text or "",
                    "alan_etiket": return_elem.find("alanEtiket").text or "",
                    "alici_unvan": return_elem.find("aliciUnvan").text or "",
                    "belge_versiyon": return_elem.find("belgeVersiyon").text or "",
                    "satici_unvan": return_elem.find("saticiUnvan").text or "",
                    "zarf_id": return_elem.find("zarfId").text or "",
                    "odenecek_tutar": (
                        float(return_elem.find("odenecekTutar").text)
                        if return_elem.find("odenecekTutar") is not None
                        else 0.0
                    ),
                    "odenecek_tutar_doviz_cinsi": (
                        self.env["res.currency"]
                        .search(
                            [
                                (
                                    "name",
                                    "=",
                                    return_elem.find("odenecekTutarDovizCinsi").text,
                                )
                            ]
                        )
                        .id
                        if return_elem.find("odenecekTutarDovizCinsi") is not None
                        else False
                    ),
                    "belge_hash": (
                        return_elem.find("belgeHash").text
                        if return_elem.find("belgeHash") is not None
                        else ""
                    ),
                    "fatura_gelis_tarihi": (
                        datetime.strptime(
                            return_elem.find("faturaGelisTarihi").text[:8], "%Y%m%d"
                        ).date()
                        if return_elem.find("faturaGelisTarihi") is not None
                        and return_elem.find("faturaGelisTarihi").text
                        else False
                    ),
                    "fatura_senaryo": (
                        self.env["mdx.ebelge.senaryo"]
                        .search([("code", "=", return_elem.find("profileId").text)])
                        .id
                        if return_elem.find("profileId") is not None
                        else False
                    ),
                    "fatura_onay_statu": (
                        "0"
                        if return_elem.find("profileId").text == "TICARIFATURA"
                        else "-1"
                    ),
                }
                belge_sira_no = return_elem.find("belgeSiraNo").text

                existing_invoice = self.env["mdx.gelen.fatura"].search(
                    [("ettn", "=", invoice_data["ettn"])], limit=1
                )
                if not existing_invoice:
                    self.env["mdx.gelen.fatura"].create(invoice_data)

            while len(return_elements) == 100:
                post_string = f"""<?xml version="1.0" encoding="UTF-8"?>
                    <soapenv:Envelope xmlns:ser="http://service.connector.uut.cs.com.tr/"
                        xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
                        <soapenv:Header>
                            <wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
                                <wsse:UsernameToken>
                                    <wsse:Username>{username}</wsse:Username>
                                    <wsse:Password>{password}</wsse:Password>
                                </wsse:UsernameToken>
                            </wsse:Security>
                        </soapenv:Header>
                        <soapenv:Body>
                            <ser:gelenBelgeleriListeleExt>
                                <parametreler>
                                    <belgeTuru>FATURA</belgeTuru>
                                    <donusTipiVersiyon>6.0</donusTipiVersiyon>
                                    <erpKodu>{erp_code}</erpKodu>
                                    <vergiTcKimlikNo>{vkn}</vergiTcKimlikNo>
                                    <sonAlinanBelgeSiraNumarasi>{belge_sira_no}</sonAlinanBelgeSiraNumarasi>
                                    <belgelerAlindiMi>true</belgelerAlindiMi>
                                </parametreler>
                            </ser:gelenBelgeleriListeleExt>
                        </soapenv:Body>
                    </soapenv:Envelope>
                """

                try:
                    response = requests.post(
                        url,
                        data=post_string.encode("utf-8"),
                        headers=headers,
                        timeout=60,
                    )
                    response.raise_for_status()
                except requests.exceptions.RequestException as e:
                    raise UserError(f"SOAP isteği başarısız! Hata: {str(e)}")

                if response.status_code == 200:
                    root = ET.fromstring(response.text)
                    return_elements = root.findall(
                        ".//ns2:gelenBelgeleriListeleExtResponse/return", namespaces
                    )

                    belge_sira_no = 0
                    for return_elem in return_elements:
                        invoice_data = {
                            "company_id": web_service.company_id.id,
                            "name": return_elem.find("belgeNo").text or "",
                            "belge_sira_no": return_elem.find("belgeSiraNo").text or "",
                            "belge_tarihi": (
                                datetime.strptime(
                                    return_elem.find("belgeTarihi").text, "%Y%m%d"
                                ).date()
                                if return_elem.find("belgeTarihi") is not None
                                and return_elem.find("belgeTarihi").text
                                else False
                            ),
                            "belge_turu": return_elem.find("belgeTuru").text
                            or "FATURA",
                            "ettn": return_elem.find("ettn").text or "",
                            "gonderen_etiket": return_elem.find("gonderenEtiket").text
                            or "",
                            "gonderen_vkn_tckn": return_elem.find(
                                "gonderenVknTckn"
                            ).text
                            or "",
                            "alan_etiket": return_elem.find("alanEtiket").text or "",
                            "alici_unvan": return_elem.find("aliciUnvan").text or "",
                            "belge_versiyon": return_elem.find("belgeVersiyon").text
                            or "",
                            "satici_unvan": return_elem.find("saticiUnvan").text or "",
                            "zarf_id": return_elem.find("zarfId").text or "",
                            "odenecek_tutar": (
                                float(return_elem.find("odenecekTutar").text)
                                if return_elem.find("odenecekTutar") is not None
                                else 0.0
                            ),
                            "odenecek_tutar_doviz_cinsi": (
                                self.env["res.currency"]
                                .search(
                                    [
                                        (
                                            "name",
                                            "=",
                                            return_elem.find(
                                                "odenecekTutarDovizCinsi"
                                            ).text,
                                        )
                                    ]
                                )
                                .id
                                if return_elem.find("odenecekTutarDovizCinsi")
                                is not None
                                else False
                            ),
                            "belge_hash": (
                                return_elem.find("belgeHash").text
                                if return_elem.find("belgeHash") is not None
                                else ""
                            ),
                            "fatura_gelis_tarihi": (
                                datetime.strptime(
                                    return_elem.find("faturaGelisTarihi").text[:8],
                                    "%Y%m%d",
                                ).date()
                                if return_elem.find("faturaGelisTarihi") is not None
                                and return_elem.find("faturaGelisTarihi").text
                                else False
                            ),
                            "fatura_senaryo": (
                                self.env["mdx.ebelge.senaryo"]
                                .search(
                                    [("code", "=", return_elem.find("profileId").text)]
                                )
                                .id
                                if return_elem.find("profileId") is not None
                                else False
                            ),
                            "fatura_onay_statu": (
                                "0"
                                if return_elem.find("profileId").text == "TICARIFATURA"
                                else "-1"
                            ),
                        }
                        belge_sira_no = return_elem.find("belgeSiraNo").text

                        existing_invoice = self.env["mdx.gelen.fatura"].search(
                            [("ettn", "=", invoice_data["ettn"])], limit=1
                        )
                        if not existing_invoice:
                            self.env["mdx.gelen.fatura"].create(invoice_data)
                else:
                    raise UserError(
                        f"Fatura listesi alınamadı! HTTP Durum Kodu: {response.status_code}"
                    )
        else:
            raise UserError(
                f"Fatura listesi alınamadı! HTTP Durum Kodu: {response.status_code}"
            )

    def get_incoming_invoice_html(self, ettn):

        # MdxUtilityMixin.check_license(self)

        web_service = self.env["mdx.web.service"].search(
            [
                ("name", "=", "EFINANS_ALICI"),
                ("active", "=", True),
                ("company_id", "=", self.env.user.company_id.id),
            ],
            limit=1,
        )

        gelen_fatura_record = self.env["mdx.gelen.fatura"].search(
            [("ettn", "=", ettn)], limit=1
        )

        if not web_service:
            raise UserError("Web servisi yapılandırması bulunamadı!")

        username = str(web_service.username)
        password = str(web_service.password)
        url = web_service.url
        erp_code = web_service.erp_code
        vkn = str(self.env.user.company_id.vat)

        post_string = f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                            xmlns:ser="http://service.connector.uut.cs.com.tr/">
                            <soapenv:Header>
                                <wsse:Security soap:mustUnderstand="1"
                                    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
                                    xmlns:soap="soap">
                                    <wsse:UsernameToken>
                                        <wsse:Username>{username}</wsse:Username>
                                        <wsse:Password>{password}</wsse:Password>
                                    </wsse:UsernameToken>
                                </wsse:Security>
                            </soapenv:Header>
                            <soapenv:Body>
                                <ser:gelenBelgeIndirExt>
                                    <vergiTcKimlikNo>{vkn}</vergiTcKimlikNo>
                                    <belgeEttn>{ettn}</belgeEttn>
                                    <belgeTuru>FATURA</belgeTuru>
                                    <erpKodu>{erp_code}</erpKodu>
                                    <belgeFormati>HTML</belgeFormati>
                                </ser:gelenBelgeIndirExt>
                            </soapenv:Body>
                        </soapenv:Envelope>
        """

        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}

        try:
            response = requests.post(
                url, data=post_string.encode("utf-8"), headers=headers, timeout=60
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise UserError(f"SOAP isteği başarısız! Hata: {str(e)}")

        if response.status_code == 200:
            root = ET.fromstring(response.text)

            namespaces = {
                "S": "http://schemas.xmlsoap.org/soap/envelope/",
                "ns2": "http://service.connector.uut.cs.com.tr/",
            }

            html_data_element = root.find(
                ".//ns2:gelenBelgeIndirExtResponse/return", namespaces
            )

            if html_data_element is not None:
                html_data = self.base64_decode(html_data_element.text)
                file_name = f"{ettn}.html"

                attachment = self.env["ir.attachment"].create(
                    {
                        "name": file_name,
                        "datas": self.base64_encode(html_data),
                        # 'datas_fname': file_name,
                        "res_model": "mdx.gelen.fatura",
                        "res_id": gelen_fatura_record.id,
                        "type": "binary",
                    }
                )

                if attachment:
                    gelen_fatura_record.write({"fatura_html": attachment.id})
                else:
                    gelen_fatura_record.write(
                        {"logging_field1": "Fatura HTML içeriği kaydedilemedi!"}
                    )

        else:
            gelen_fatura_record.write(
                {
                    "logging_field1": f"Fatura HTML içeriği alınamadı! HTTP Durum Kodu: {response.status_code}"
                }
            )

    def get_incoming_invoice_pdf(self, ettn):

        # MdxUtilityMixin.check_license(self)

        # Web servisini bul
        web_service = self.env["mdx.web.service"].search(
            [
                ("name", "=", "EFINANS_ALICI"),
                ("active", "=", True),
                ("company_id", "=", self.env.user.company_id.id),
            ],
            limit=1,
        )
        if not web_service:
            raise UserError("Web servisi yapılandırması bulunamadı!")

        # İlgili gelen fatura kaydını bul
        gelen_fatura_record = self.env["mdx.gelen.fatura"].search(
            [("ettn", "=", ettn)], limit=1
        )
        if not gelen_fatura_record:
            raise UserError(f"Ettn ile eşleşen gelen fatura bulunamadı: {ettn}")

        # SOAP isteği için gerekli parametreler
        username, password, url, erp_code = (
            str(web_service.username),
            str(web_service.password),
            web_service.url,
            web_service.erp_code,
        )
        vkn = str(self.env.user.company_id.vat)

        # SOAP post string
        post_string = f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                                xmlns:ser="http://service.connector.uut.cs.com.tr/">
                                <soapenv:Header>
                                    <wsse:Security soap:mustUnderstand="1"
                                        xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
                                        xmlns:soap="soap">
                                        <wsse:UsernameToken>
                                            <wsse:Username>{username}</wsse:Username>
                                            <wsse:Password>{password}</wsse:Password>
                                        </wsse:UsernameToken>
                                    </wsse:Security>
                                </soapenv:Header>
                                <soapenv:Body>
                                    <ser:gelenBelgeIndirExt>
                                        <vergiTcKimlikNo>{vkn}</vergiTcKimlikNo>
                                        <belgeEttn>{ettn}</belgeEttn>
                                        <belgeTuru>FATURA</belgeTuru>
                                        <erpKodu>{erp_code}</erpKodu>
                                        <belgeFormati>PDF</belgeFormati>
                                    </ser:gelenBelgeIndirExt>
                                </soapenv:Body>
                            </soapenv:Envelope>"""

        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}

        # SOAP isteği gönder ve hata yönetimi
        try:
            response = requests.post(
                url, data=post_string.encode("utf-8"), headers=headers, timeout=60
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise UserError(f"SOAP isteği başarısız! Hata: {str(e)}")

        # Yanıt durumu kontrolü
        if response.status_code == 200:
            try:
                # XML yanıtını ayrıştır
                root = ET.fromstring(response.text)
                namespaces = {
                    "S": "http://schemas.xmlsoap.org/soap/envelope/",
                    "ns2": "http://service.connector.uut.cs.com.tr/",
                }
                pdf_data_element = root.find(
                    ".//ns2:gelenBelgeIndirExtResponse/return", namespaces
                )

                if pdf_data_element is not None:
                    # PDF verisini base64 çöz
                    pdf_data = base64.b64decode(pdf_data_element.text)
                    file_name = f"{ettn}.pdf"

                    # PDF'yi ir.attachment olarak kaydet
                    attachment = self.env["ir.attachment"].create(
                        {
                            "name": file_name,
                            "datas": base64.b64encode(
                                pdf_data
                            ),  # PDF'yi yeniden base64'e encode edip saklıyoruz
                            "res_model": "mdx.gelen.fatura",
                            "res_id": gelen_fatura_record.id,
                            "type": "binary",
                        }
                    )

                    # Attachment kaydını gelen fatura ile ilişkilendir
                    if attachment:
                        gelen_fatura_record.write({"fatura_pdf": attachment.id})
                    else:
                        gelen_fatura_record.write(
                            {"logging_field1": "Fatura PDF içeriği kaydedilemedi!"}
                        )
                else:
                    gelen_fatura_record.write(
                        {"logging_field1": "PDF verisi bulunamadı!"}
                    )
            except Exception as e:
                raise UserError(f"Yanıt işlenirken hata oluştu: {str(e)}")
        else:
            gelen_fatura_record.write(
                {
                    "logging_field1": f"Fatura PDF alınamadı! HTTP Durum Kodu: {response.status_code}"
                }
            )

    def get_incoming_invoice_xml(self, ettn):

        # MdxUtilityMixin.check_license(self)

        """
        Faturayı XML (UBL) formatında indirir ve kaydeder.
        """
        web_service = self.env["mdx.web.service"].search(
            [
                ("name", "=", "EFINANS_ALICI"),
                ("active", "=", True),
                ("company_id", "=", self.env.user.company_id.id),
            ],
            limit=1,
        )

        gelen_fatura_record = self.env["mdx.gelen.fatura"].search(
            [("ettn", "=", ettn)], limit=1
        )

        if not web_service:
            gelen_fatura_record.write(
                {"attachment_error_details": "Web servisi yapılandırması bulunamadı!"}
            )
            return

        try:
            username = str(web_service.username)
            password = str(web_service.password)
            url = web_service.url
            erp_code = web_service.erp_code
            vkn = str(self.env.user.company_id.vat)

            post_string = f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                                xmlns:ser="http://service.connector.uut.cs.com.tr/">
                                <soapenv:Header>
                                    <wsse:Security soap:mustUnderstand="1"
                                        xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
                                        xmlns:soap="soap">
                                        <wsse:UsernameToken>
                                            <wsse:Username>{username}</wsse:Username>
                                            <wsse:Password>{password}</wsse:Password>
                                        </wsse:UsernameToken>
                                    </wsse:Security>
                                </soapenv:Header>
                                <soapenv:Body>
                                    <ser:gelenBelgeIndirExt>
                                        <vergiTcKimlikNo>{vkn}</vergiTcKimlikNo>
                                        <belgeEttn>{ettn}</belgeEttn>
                                        <belgeTuru>FATURA</belgeTuru>
                                        <erpKodu>{erp_code}</erpKodu>
                                        <belgeFormati>UBL</belgeFormati>
                                    </ser:gelenBelgeIndirExt>
                                </soapenv:Body>
                            </soapenv:Envelope>
            """

            headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}

            try:
                response = requests.post(
                    url, data=post_string.encode("utf-8"), headers=headers, timeout=60
                )
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                error_msg = f"SOAP isteği başarısız! Hata: {str(e)}"
                gelen_fatura_record.write({"attachment_error_details": error_msg})
                return

            if response.status_code == 200:
                root = ET.fromstring(response.text)
                namespaces = {
                    "S": "http://schemas.xmlsoap.org/soap/envelope/",
                    "ns2": "http://service.connector.uut.cs.com.tr/",
                }

                xml_data_element = root.find(
                    ".//ns2:gelenBelgeIndirExtResponse/return", namespaces
                )

                if xml_data_element is not None and xml_data_element.text:
                    try:
                        decoded_xml = base64.b64decode(xml_data_element.text).decode(
                            "utf-8-sig"
                        )
                    except (binascii.Error, UnicodeDecodeError) as e:
                        error_msg = f"Base64 decode hatası: {str(e)}"
                        gelen_fatura_record.write(
                            {"attachment_error_details": error_msg}
                        )
                        return

                    # XML validasyon ve parse işlemleri
                    try:
                        root = ET.fromstring(decoded_xml.encode("utf-8"))
                    except ET.ParseError as e:
                        error_msg = f"XML parse hatası: {str(e)} - İlk 100 karakter: {decoded_xml[:100]}"
                        gelen_fatura_record.write(
                            {"attachment_error_details": error_msg}
                        )
                        return

                    # Attachment oluşturma
                    file_name = f"{ettn}.xml"
                    attachment = self.env["ir.attachment"].create(
                        {
                            "name": file_name,
                            "datas": base64.b64encode(decoded_xml.encode("utf-8")),
                            "res_model": "mdx.gelen.fatura",
                            "res_id": gelen_fatura_record.id,
                            "type": "binary",
                        }
                    )

                    if attachment:
                        gelen_fatura_record.write({"fatura_xml": attachment.id})

                        # XML'den veri çekme
                        ns = {
                            "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
                            "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
                            "ubl": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
                        }

                        try:
                            # OrderReference/ID çekme
                            order_ref_element = root.find(
                                ".//cac:OrderReference/cbc:ID", ns
                            )

                            if order_ref_element is None:
                                order_ref_element = root.find(
                                    ".//{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}OrderReference"
                                    "/{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID"
                                )

                            if order_ref_element is None:
                                order_refs = root.findall(".//cac:OrderReference", ns)
                                if order_refs:
                                    order_ref_element = order_refs[0].find("cbc:ID", ns)

                            order_ref_id = (
                                order_ref_element.text
                                if order_ref_element is not None
                                else False
                            )

                            despatch_ref_element = root.find(
                                ".//cac:DespatchDocumentReference/cbc:ID", ns
                            )

                            if despatch_ref_element is None:
                                despatch_ref_element = root.find(
                                    ".//{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}DespatchDocumentReference"
                                    "/{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID"
                                )

                            if despatch_ref_element is None:
                                despatch_refs = root.findall(
                                    ".//cac:DespatchDocumentReference", ns
                                )
                                if despatch_refs:
                                    despatch_ref_element = despatch_refs[0].find(
                                        "cbc:ID", ns
                                    )

                            despatch_ref_id = (
                                despatch_ref_element.text
                                if despatch_ref_element is not None
                                else False
                            )

                            payment_terms_element = root.find(".//cac:PaymentTerms", ns)
                            if payment_terms_element is None:
                                payment_terms_element = root.find(
                                    ".//{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}PaymentTerms"
                                )

                            payment_due_date = (
                                payment_terms_element.find(
                                    "cbc:PaymentDueDate", ns
                                ).text
                                if payment_terms_element is not None
                                else False
                            )

                            if payment_due_date:
                                gelen_fatura_record.write(
                                    {"son_odeme_tarihi": payment_due_date}
                                )

                            if not despatch_ref_id:
                                gelen_fatura_record.write(
                                    {
                                        "attachment_error_details": "DespatchReference/ID bulunamadı!"
                                    }
                                )

                            if order_ref_id and isinstance(order_ref_id, str):
                                if "<![CDATA[" in order_ref_id:
                                    order_ref_id = (
                                        order_ref_id.split("<![CDATA[")[1]
                                        .split("]]>")[0]
                                        .strip()
                                    )
                                else:
                                    order_ref_id = order_ref_id.strip()
                            else:
                                gelen_fatura_record.write(
                                    {
                                        "attachment_error_details": "OrderReference/ID bulunamadı ya da geçersiz!"
                                    }
                                )
                                order_ref_id = False

                            tax_exemption_reason_code_element = root.find(
                                ".//cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:TaxExemptionReasonCode",
                                ns,
                            )

                            if tax_exemption_reason_code_element is None:
                                tax_exemption_reason_code_element = root.find(
                                    ".//{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxTotal"
                                    "/{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxSubtotal"
                                    "/{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxCategory"
                                    "/{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxExemptionReasonCode"
                                )

                            tax_exemption_reason_code = (
                                tax_exemption_reason_code_element.text
                                if tax_exemption_reason_code_element is not None
                                else False
                            )

                            if tax_exemption_reason_code:
                                tax_exemption_reason_code = self.env[
                                    "mdx.sabit.kod"
                                ].search(
                                    [("efinans_kod", "=", tax_exemption_reason_code)],
                                    limit=1,
                                )
                                gelen_fatura_record.write(
                                    {
                                        "tax_exemption_reason_code_id": tax_exemption_reason_code.id
                                    }
                                )

                            invoice_lines = root.findall(".//cac:InvoiceLine", ns)
                            for line in invoice_lines:

                                # Fatura satırlarını işleme
                                line_id = (
                                    line.find("cbc:ID", ns).text
                                    if line.find("cbc:ID", ns) is not None
                                    else "Bilinmiyor"
                                )
                                line_quantity = (
                                    float(line.find("cbc:InvoicedQuantity", ns).text)
                                    if line.find("cbc:InvoicedQuantity", ns) is not None
                                    else 0.0
                                )
                                line_total = (
                                    float(line.find("cbc:LineExtensionAmount", ns).text)
                                    if line.find("cbc:LineExtensionAmount", ns)
                                    is not None
                                    else 0.0
                                )
                                line_tax_rate = (
                                    float(
                                        line.find(
                                            "cac:TaxTotal/cac:TaxSubtotal/cbc:Percent",
                                            ns,
                                        ).text
                                    )
                                    if line.find(
                                        "cac:TaxTotal/cac:TaxSubtotal/cbc:Percent", ns
                                    )
                                    is not None
                                    else 0.0
                                )
                                line_tax_name = (
                                    line.find(
                                        "cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cac:TaxScheme/cbc:Name",
                                        ns,
                                    ).text
                                    if line.find(
                                        "cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cac:TaxScheme/cbc:Name",
                                        ns,
                                    )
                                    is not None
                                    else "Bilinmiyor"
                                )
                                line_product_name = (
                                    line.find("cac:Item/cbc:Name", ns).text
                                    if line.find("cac:Item/cbc:Name", ns) is not None
                                    else "Bilinmiyor"
                                )
                                line_sellers_item_id = (
                                    line.find(
                                        "cac:Item/cac:SellersItemIdentification/cbc:ID",
                                        ns,
                                    ).text
                                    if line.find(
                                        "cac:Item/cac:SellersItemIdentification/cbc:ID",
                                        ns,
                                    )
                                    is not None
                                    else "Bilinmiyor"
                                )
                                line_price = (
                                    float(
                                        line.find("cac:Price/cbc:PriceAmount", ns).text
                                    )
                                    if line.find("cac:Price/cbc:PriceAmount", ns)
                                    is not None
                                    else 0.0
                                )
                                line_tevkifat_code = (
                                    line.find(
                                        "cac:WithholdingTaxTotal/cac:TaxSubtotal/cac:TaxCategory/cac:TaxScheme/cbc:TaxTypeCode",
                                        ns,
                                    ).text
                                    if line.find(
                                        "cac:WithholdingTaxTotal/cac:TaxSubtotal/cac:TaxCategory/cac:TaxScheme/cbc:TaxTypeCode",
                                        ns,
                                    )
                                    is not None
                                    else False
                                )
                                product = self.env["product.product"].search(
                                    [
                                        (
                                            "seller_ids.product_name",
                                            "=",
                                            line_product_name,
                                        ),
                                        (
                                            "seller_ids.product_code",
                                            "=",
                                            line_sellers_item_id,
                                        ),
                                        (
                                            "seller_ids.partner_id.id",
                                            "=",
                                            gelen_fatura_record.supplier_id.id,
                                        ),
                                    ],
                                    limit=1,
                                )
                                # supplierinfo_id = False
                                create_product = False
                                create_supplierinfo = False
                                if product:
                                    product_account = (
                                        product.property_account_expense_id
                                    )
                                    # supplierinfo_id = product.product_tmpl_id.seller_ids.filtered(
                                    #     lambda x: x.product_name == line_product_name and
                                    #     x.product_code == line_sellers_item_id and
                                    #     x.partner_id.id == gelen_fatura_record.supplier_id.id).id if product else False

                                    if product_account:
                                        account_id = product_account.id
                                    else:
                                        account_id = False
                                else:
                                    create_product = True
                                    create_supplierinfo = True
                                    account_id = False

                                if line_tevkifat_code:
                                    tevkifat_code = self.env["mdx.sabit.kod"].search(
                                        [("efinans_kod", "=", line_tevkifat_code)],
                                        limit=1,
                                    )
                                    if tevkifat_code:

                                        line_tevkifat_code = tevkifat_code.id

                                gelen_fatura_line = self.env[
                                    "mdx.gelen.fatura.line"
                                ].create(
                                    {
                                        "gelen_fatura_id": gelen_fatura_record.id,
                                        "line_id": line_id,
                                        "quantity": line_quantity,
                                        "price_unit": line_price,
                                        "price_subtotal": line_total,
                                        "tax_rate": line_tax_rate,
                                        "tax_name": line_tax_name,
                                        # 'tax_id': tax_id,
                                        "supplier_product_name": line_product_name,
                                        "supplier_product_code": line_sellers_item_id,
                                        # 'supplierinfo_id': supplierinfo_id if supplierinfo_id else False,
                                        "product_id": product.id if product else False,
                                        "account_id": (
                                            account_id if account_id else False
                                        ),
                                        "create_product": create_product,
                                        "create_supplierinfo": create_supplierinfo,
                                        "tevkifat_kodu": line_tevkifat_code,
                                    }
                                )

                        except AttributeError as ae:
                            error_msg = f"XML element attribute hatası: {str(ae)}"
                            gelen_fatura_record.write(
                                {"attachment_error_details": error_msg}
                            )
                            return
                        except Exception as e:
                            error_msg = f"Genel XML parse hatası: {str(e)}"
                            gelen_fatura_record.write(
                                {"attachment_error_details": error_msg}
                            )
                            return

                        gelen_fatura_record.write(
                            {
                                "so_number_from_xml": order_ref_id,
                                "waybill_number_from_xml": despatch_ref_id,
                            }
                        )

                    else:
                        gelen_fatura_record.write(
                            {
                                "attachment_error_details": "Fatura XML içeriği kaydedilemedi!"
                            }
                        )
                else:
                    error_msg = (
                        f"HTTP Hatası: {response.status_code} - {response.text[:200]}"
                    )
                    gelen_fatura_record.write({"attachment_error_details": error_msg})
                    return

        except requests.exceptions.RequestException as e:
            error_msg = f"Ağ hatası: {str(e)}"
            gelen_fatura_record.write({"attachment_error_details": error_msg})
            return
        except Exception as e:
            error_msg = f"Beklenmeyen hata: {str(e)}"
            gelen_fatura_record.write({"attachment_error_details": error_msg})
            return

    def check_gelen_fatura_status(self, gelen_fatura, ettn):

        # MdxUtilityMixin.check_license(self)

        # Kullanıcı bilgilerini al
        web_service = self.env["mdx.web.service"].search(
            [
                ("name", "=", "EFINANS_ALICI"),
                ("active", "=", True),
                ("company_id", "=", self.env.user.company_id.id),
            ],
            limit=1,
        )
        username = str(web_service.username)
        password = str(web_service.password)
        vkn = str(web_service.vkn)
        url = web_service.url

        # SOAP talebi oluştur
        post_string = f"""
            <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                xmlns:ser="http://service.connector.uut.cs.com.tr/">
                <soapenv:Header>
                    <wsse:Security soap:mustUnderstand="1"
                        xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
                        xmlns:soap="soap">
                        <wsse:UsernameToken>
                            <wsse:Username>{username}</wsse:Username>
                            <wsse:Password>{password}</wsse:Password>
                        </wsse:UsernameToken>
                    </wsse:Security>
                </soapenv:Header>
                <soapenv:Body>
                    <ser:gelenBelgeDurumSorgula>
                        <vergiTcKimlikNo>{vkn}</vergiTcKimlikNo>
                        <ettn>{ettn}</ettn>
                        <belgeTuru>FATURA</belgeTuru>
                    </ser:gelenBelgeDurumSorgula>
                </soapenv:Body>
            </soapenv:Envelope>
        """

        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}

        # Talebi gönder
        response = requests.post(url, data=post_string, headers=headers)

        if response.status_code == 200:
            root = ET.fromstring(response.content)

            # 'ns2' ad alanını doğru şekilde kullanmak
            namespaces = {
                "S": "http://schemas.xmlsoap.org/soap/envelope/",
                "ns2": "http://service.connector.uut.cs.com.tr/",
            }

            # <return> elementini bul
            return_element = root.find(
                ".//ns2:gelenBelgeDurumSorgulaResponse/return", namespaces
            )

            def get_element_text(xpath):
                # XML parse işlemi ile element bulunması
                element = return_element.find(xpath)
                if element is not None:
                    return element.text
                return None

            # XML'den değerleri çek
            # aciklama = get_element_text('aciklama')
            alim_tarihi = get_element_text("alimTarihi")
            belge_no = get_element_text("belgeNo")
            ettn = get_element_text("ettn")
            yanit_detayi = get_element_text("yanitDetayi")
            yanit_durumu = get_element_text("yanitDurumu")
            yanit_gonderim_cevabi_detayi = get_element_text("yanitGonderimCevabiDetayi")
            yanit_gonderim_cevabi_kodu = get_element_text("yanitGonderimCevabiKodu")
            yanit_gonderim_durumu = get_element_text("yanitGonderimDurumu")
            yanit_gonderim_tarihi = get_element_text("yanitGonderimTarihi")

            # # "SAXParseException" kontrolü
            # if "SAXParseException" in aciklama:
            #     raise UserError(f"Yanıt XML hatası içeriyor: {aciklama}")

            # Durum detayını oluştur
            durum_detay = self.gelenBelgeDurumDetay(
                alim_tarihi=alim_tarihi or False,
                belge_no=belge_no or False,
                ettn=ettn or False,
                yanit_detayi=yanit_detayi or False,
                yanit_durumu=yanit_durumu or False,
                yanit_gonderim_cevabi_detayi=yanit_gonderim_cevabi_detayi or False,
                yanit_gonderim_cevabi_kodu=yanit_gonderim_cevabi_kodu or False,
                yanit_gonderim_durumu=yanit_gonderim_durumu or False,
                yanit_gonderim_tarihi=yanit_gonderim_tarihi or False,
            )

            # Invoice kaydına verileri yaz
            gelen_fatura.write(
                {
                    "fatura_onay_statu": str(yanit_durumu),
                    "fatura_durum_detay": f"""Alım Tarihi: {durum_detay.alim_tarihi or 'Bilinmiyor'}\nBelge No: {durum_detay.belge_no or 'Bilinmiyor'}\nETTN: {durum_detay.ettn}\nYanıt Detayı: {durum_detay.yanit_detayi or 'Bilinmiyor'}\nYanıt Durumu: {durum_detay.yanit_durumu or 'Bilinmiyor'}\nYanıt Gönderim Cevabı Detayı: {durum_detay.yanit_gonderim_cevabi_detayi or 'Bilinmiyor'}\nYanıt Gönderim Cevabı Kodu: {durum_detay.yanit_gonderim_cevabi_kodu or 'Bilinmiyor'}\nYanıt Gönderim Durumu: {durum_detay.yanit_gonderim_durumu or 'Bilinmiyor'}\nYanıt Gönderim Tarihi: {durum_detay.yanit_gonderim_tarihi or 'Bilinmiyor'}""",  # noqa
                }
            )
        else:
            raise UserError("Fatura durum sorgulama işlemi başarısız oldu.")

        return response.text

    class gelenBelgeDurumDetay:
        def __init__(
            self,
            alim_tarihi,
            belge_no,
            ettn,
            yanit_detayi,
            yanit_durumu,
            yanit_gonderim_cevabi_detayi,
            yanit_gonderim_cevabi_kodu,
            yanit_gonderim_durumu,
            yanit_gonderim_tarihi,
        ):
            self.alim_tarihi = alim_tarihi
            self.belge_no = belge_no
            self.ettn = ettn
            self.yanit_detayi = yanit_detayi
            self.yanit_gonderim_cevabi_detayi = yanit_gonderim_cevabi_detayi
            self.yanit_gonderim_cevabi_kodu = yanit_gonderim_cevabi_kodu
            self.yanit_gonderim_tarihi = yanit_gonderim_tarihi

            self.yanit_durumu = "Bilinmiyor"
            yanit_durumu = str(yanit_durumu)  # Integer'ı string'e dönüştür
            if yanit_durumu == "-1":
                self.yanit_durumu = (
                    "Yanıt gerekmiyor. Temel faturalar için yanıt beklenmez."
                )
            elif yanit_durumu == "0":
                self.yanit_durumu = (
                    "Yanıt bekleniyor. Ticari fatura için cevap bekleniyor."
                )
            elif yanit_durumu == "1":
                self.yanit_durumu = "Red cevabı geldi."
            elif yanit_durumu == "2":
                self.yanit_durumu = "Kabul cevabı geldi."

            self.yanit_gonderim_durumu = "Bilinmiyor"
            yanit_gonderim_durumu = str(
                yanit_gonderim_durumu
            )  # Integer'ı string'e dönüştür
            if yanit_gonderim_durumu == "-2":
                self.yanit_gonderim_durumu = "İptal edildi, Gönderilmeyecek."
            elif yanit_gonderim_durumu == "-1":
                self.yanit_gonderim_durumu = "Kuyruğa eklendi."
            elif yanit_gonderim_durumu == "0":
                self.yanit_gonderim_durumu = (
                    "Gönderilemedi, sistem gönderim işlemini yeniden deneyecek."
                )
            elif yanit_gonderim_durumu == "1":
                self.yanit_gonderim_durumu = "Gönderilecek."
            elif yanit_gonderim_durumu == "2":
                self.yanit_gonderim_durumu = "Gönderildi."
            elif yanit_gonderim_durumu == "3":
                self.yanit_gonderim_durumu = "GİB merkez yanıtı geldi."
            elif yanit_gonderim_durumu == "4":
                self.yanit_gonderim_durumu = "Alıcı yanıtı geldi."

    def response_gelen_fatura(self, gelen_fatura, response, kabul_red_aciklama):

        # MdxUtilityMixin.check_license(self)

        try:
            issue_date = date.today()  # HATA BURADAYDI
            issue_date_str = issue_date.strftime("%Y-%m-%d")
            issue_time = datetime.now().strftime("%H:%M:%S")  # HATA BURADAYDI

            web_service = self.env["mdx.web.service"].search(
                [
                    ("name", "=", "EFINANS_ALICI"),
                    ("active", "=", True),
                    ("company_id", "=", self.env.user.company_id.id),
                ],
                limit=1,
            )

            username = str(web_service.username)
            password = str(web_service.password)
            erp_code = web_service.erp_code
            url = web_service.url
            vkn = str(web_service.vkn)

            response_note = ""
            status = gelen_fatura.fatura_onay_statu
            if response == "KABUL":
                if kabul_red_aciklama != False:
                    response_note = kabul_red_aciklama
                else:
                    response_note = "Uygun."
                status = "2"
            else:
                if kabul_red_aciklama != False:
                    response_note = kabul_red_aciklama
                else:
                    response_note = "Uygun DEGİL."
                status = "1"

            response_string = '<?xml version="1.0" encoding="UTF-8"?>'
            response_string += "<uygulamaYaniti>"
            response_string += "<alici>"
            response_string += "<vergiNo>" + vkn + "</vergiNo>"
            response_string += "</alici>"
            response_string += "<gonderici>"
            response_string += (
                "<vergiNo>" + gelen_fatura.gonderen_vkn_tckn + "</vergiNo>"
            )
            response_string += "</gonderici>"
            response_string += "<faturaNo/>"
            response_string += "<faturaId>" + gelen_fatura.ettn + "</faturaId>"
            response_string += "<cevapKodu>" + response + "</cevapKodu>"
            response_string += "<cevapNotu>" + response_note + "</cevapNotu>"
            response_string += "<faturaTipi/>"
            response_string += "<cevapTarihi>" + issue_date_str + "</cevapTarihi>"
            response_string += "<cevapZamani>" + issue_time + "</cevapZamani>"
            response_string += "</uygulamaYaniti>"

            decoded_xml = self.base64_encode(response_string)
            hash_obj = self.calculate_md5(response_string)

            counter = (
                self.env["mdx.dokuman.sayac"]
                .search(
                    [
                        ("code", "=", "DOKUMANSAYAC"),
                        ("company_id", "=", self.env.user.company_id.id),
                    ],
                    limit=1,
                )
                .gonderilecek_sonraki_sira_no
            )
            counter += 1
            self.env["mdx.dokuman.sayac"].search(
                [
                    ("code", "=", "DOKUMANSAYAC"),
                    ("company_id", "=", self.env.user.company_id.id),
                ]
            ).write({"gonderilecek_sonraki_sira_no": counter})

            post_string = '<?xml version="1.0" encoding="utf-8"?>'
            post_string += '<soapenv:Envelope xmlns:ser="http://service.connector.uut.cs.com.tr/" xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
            post_string += "<soapenv:Header>"
            post_string += '<wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">'
            post_string += "<wsse:UsernameToken>"
            post_string += "<wsse:Username>" + str(username) + "</wsse:Username>"
            post_string += "<wsse:Password>" + str(password) + "</wsse:Password>"
            post_string += "</wsse:UsernameToken>"
            post_string += "</wsse:Security>"
            post_string += "</soapenv:Header>"
            post_string += "<soapenv:Body>"
            post_string += "<ser:belgeGonderExt>"
            post_string += "<parametreler>"
            post_string += "<belgeHash>" + str(hash_obj) + "</belgeHash>"
            post_string += "<belgeNo>" + str(counter) + "</belgeNo>"
            post_string += "<belgeTuru>UYGULAMA_YANITI</belgeTuru>"
            post_string += "<belgeVersiyon>1.0</belgeVersiyon>"
            post_string += "<erpKodu>" + str(erp_code) + "</erpKodu>"
            post_string += "<mimeType>application/xml</mimeType>"
            post_string += "<vergiTcKimlikNo>" + str(vkn) + "</vergiTcKimlikNo>"
            post_string += "<veri>" + str(decoded_xml) + "</veri>"
            post_string += "</parametreler>"
            post_string += "</ser:belgeGonderExt>"
            post_string += "</soapenv:Body>"
            post_string += "</soapenv:Envelope>"

            gelen_fatura.write({"logging_field6": post_string})

            # namespaces = {
            #     'ns2': 'http://service.connector.uut.cs.com.tr/'
            # }

            headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}

            response = requests.post(url, data=post_string, headers=headers)

            # root = ET.fromstring(response.content)

            if response.status_code == 200:
                # XML'den değerleri çek
                gelen_fatura.write(
                    {
                        "fatura_onay_statu": status,
                        "logging_field5": response.text + " ***RESPONSE",
                    }
                )

            else:
                gelen_fatura.write(
                    {"logging_field4": str(response.status_code) + " ***RESPONSE"}
                )
                return
        except Exception as e:
            raise UserError(f"XML parse hatası: {str(e)}")

    def check_gelen_irsaliye_status(self, gelen_irsaliye, yanit_belge_oid):

        # MdxUtilityMixin.check_license(self)

        # Kullanıcı bilgilerini al
        web_service = self.env["mdx.web.service"].search(
            [
                ("name", "=", "EFINANS_ALICI"),
                ("active", "=", True),
                ("company_id", "=", self.env.user.company_id.id),
            ],
            limit=1,
        )
        username = str(web_service.username)
        password = str(web_service.password)
        vkn = str(web_service.vkn)
        url = web_service.url

        # SOAP talebi oluştur
        post_string = f"""
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ser="http://service.connector.uut.cs.com.tr/">
        <soapenv:Header>
        <wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
        <wsse:UsernameToken>
        <wsse:Username>{username}</wsse:Username>
        <wsse:Password>{password}</wsse:Password>
        </wsse:UsernameToken>
        </wsse:Security>
        </soapenv:Header>
        <soapenv:Body>
        <ser:gidenBelgeDurumSorgulaExt>
        <!-- Optional: -->
        <vergiTcKimlikNo>{vkn}</vergiTcKimlikNo>
        <!-- Optional: -->
        <parametreler>
        <belgeNo>{yanit_belge_oid}</belgeNo>
        <belgeNoTipi>OID</belgeNoTipi>
        <donusTipiVersiyon>6.0</donusTipiVersiyon>
        <!-- Zero or more repetitions:
                    <belgeNoList></belgeNoList>
                    -->
        <!-- Optional:
                    <belgeTuru></belgeTuru>
                    -->
        </parametreler>
        </ser:gidenBelgeDurumSorgulaExt>
        </soapenv:Body>
        </soapenv:Envelope>
        """

        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}

        # Talebi gönder
        response = requests.post(url, data=post_string, headers=headers)

        if response.status_code == 200:
            root = ET.fromstring(response.content)

            # 'ns2' ad alanını doğru şekilde kullanmak
            namespaces = {
                "S": "http://schemas.xmlsoap.org/soap/envelope/",
                "ns2": "http://service.connector.uut.cs.com.tr/",
            }

            return_element = root.find(
                ".//ns2:gidenBelgeDurumSorgulaExtResponse/return", namespaces
            )

            def get_element_text(xpath):
                # XML parse işlemi ile element bulunması
                element = return_element.find(xpath)
                if element is not None:
                    return element.text
                return None

            # XML'den değerleri çek
            aciklama = get_element_text("aciklama")
            alim_tarihi = get_element_text("alimTarihi")
            durum = get_element_text("durum")
            ettn = get_element_text("ettn")
            gonderim_cevabi_detayi = get_element_text("gonderimCevabiDetayi")
            gonderim_cevabi_kodu = get_element_text("gonderimCevabiKodu")
            gonderim_durumu = get_element_text("gonderimDurumu")
            olusturulma_tarihi = get_element_text("olusturulmaTarihi")
            yanit_durumu = get_element_text("yanitDurumu")
            ulasti_mi = get_element_text("ulastiMi")
            yeniden_gonderilebilir_mi = get_element_text("yenidenGonderilebilirMi")
            yerel_belge_oid = get_element_text("yerelBelgeOid")
            yanit_verilen_belge_ettn = get_element_text("yanitVerilenBelgeEttn")

            if aciklama:
                gelen_irsaliye.write(
                    {
                        "irsaliye_onay_statu": "0",
                        "irsaliye_durum_detay": f"""HATA: {aciklama}""",
                    }
                )
            else:
                # # "SAXParseException" kontrolü
                # if "SAXParseException" in aciklama:
                #     raise UserError(f"Yanıt XML hatası içeriyor: {aciklama}")

                # Durum detayını oluştur
                durum_detay = self.EirsaliyeYanitDurumDetay(
                    aciklama=aciklama or "Bilinmiyor",
                    alim_tarihi=alim_tarihi or "Bilinmiyor",
                    durum=durum or "Bilinmiyor",
                    ettn=ettn or "Bilinmiyor",
                    gonderim_cevabi_detayi=gonderim_cevabi_detayi or "Bilinmiyor",
                    gonderim_cevabi_kodu=gonderim_cevabi_kodu or "Bilinmiyor",
                    gonderim_durumu=gonderim_durumu or "Bilinmiyor",
                    olusturulma_tarihi=olusturulma_tarihi or "Bilinmiyor",
                    yanit_durumu=yanit_durumu or "Bilinmiyor",
                    ulasti_mi=ulasti_mi or "Bilinmiyor",
                    yeniden_gonderilebilir_mi=yeniden_gonderilebilir_mi or "Bilinmiyor",
                    yerel_belge_oid=yerel_belge_oid or "Bilinmiyor",
                    yanit_verilen_belge_ettn=yanit_verilen_belge_ettn or "Bilinmiyor",
                )

                # Invoice kaydına verileri yaz
                gelen_irsaliye.write(
                    {
                        "irsaliye_onay_statu": "1",
                        "irsaliye_durum_detay": f"""Alım Tarihi: {durum_detay.alim_tarihi}\nDurum: {durum_detay.durum}\nETTN: {durum_detay.ettn}\nGönderim Cevabı Detayı: {durum_detay.gonderim_cevabi_detayi}\nGönderim Cevabı Kodu: {durum_detay.gonderim_cevabi_kodu}\nGönderim Durumu: {durum_detay.gonderim_durumu}\nOluşturulma Tarihi: {durum_detay.olusturulma_tarihi}\nYanıt Durumu: {durum_detay.yanit_durumu}\nUlaştı Mı: {durum_detay.ulasti_mi}\nYeniden Gönderilebilir Mi: {durum_detay.yeniden_gonderilebilir_mi}\nYerel Belge OID: {durum_detay.yerel_belge_oid}\nYanıt Verilen Belge ETTN: {durum_detay.yanit_verilen_belge_ettn}""",  # noqa
                    }
                )
        else:
            raise UserError("İrsaliye durum sorgulama işlemi başarısız oldu.")

        return response.text

    class EirsaliyeYanitDurumDetay:
        def __init__(
            self,
            aciklama,
            alim_tarihi,
            durum,
            ettn,
            gonderim_cevabi_detayi,
            gonderim_cevabi_kodu,
            gonderim_durumu,
            olusturulma_tarihi,
            yanit_durumu,
            ulasti_mi,
            yeniden_gonderilebilir_mi,
            yerel_belge_oid,
            yanit_verilen_belge_ettn,
        ):
            self.aciklama = aciklama
            self.alim_tarihi = alim_tarihi
            self.durum = durum
            self.ettn = ettn
            self.gonderim_cevabi_detayi = gonderim_cevabi_detayi
            self.gonderim_cevabi_kodu = gonderim_cevabi_kodu
            self.gonderim_durumu = gonderim_durumu
            self.olusturulma_tarihi = olusturulma_tarihi
            self.yanit_durumu = yanit_durumu
            self.ulasti_mi = ulasti_mi
            self.yeniden_gonderilebilir_mi = yeniden_gonderilebilir_mi
            self.yerel_belge_oid = yerel_belge_oid
            self.yanit_verilen_belge_ettn = yanit_verilen_belge_ettn

            self.durum = "Bilinmiyor"
            durum = str(durum)  # Integer'ı string'e dönüştür
            if durum == "1":
                self.durum = "Alındı, işlenmeyi bekliyor."
            elif durum == "2":
                self.durum = "2	İşlenemedi. aciklama alanında hata mesajı bulunabilir."
            elif durum == "3":
                self.durum = "İşlendi, gönderime hazır."

            self.gonderim_durumu = "Bilinmiyor"
            gonderim_durumu = str(gonderim_durumu)  # Integer'ı string'e dönüştür
            if gonderim_durumu == "-2":
                self.gonderim_durumu = "İptal edildi, Gönderilmeyecek."
            elif gonderim_durumu == "-1":
                self.gonderim_durumu = "Kuyruğa eklendi."
            elif gonderim_durumu == "0":
                self.gonderim_durumu = (
                    "Gönderilemedi, sistem gönderim işlemini yeniden deneyecek."
                )
            elif gonderim_durumu == "1":
                self.gonderim_durumu = "Gönderilecek."
            elif gonderim_durumu == "2":
                self.gonderim_durumu = "Gönderildi."
            elif gonderim_durumu == "3":
                self.gonderim_durumu = "GİB merkez yanıtı geldi."
            elif gonderim_durumu == "4":
                self.gonderim_durumu = "Alıcı yanıtı geldi."

            self.yanit_durumu = "Bilinmiyor"
            yanit_durumu = str(yanit_durumu)  # Integer'ı string'e dönüştür
            if yanit_durumu == "-1":
                self.yanit_durumu = (
                    "Yanıt gerekmiyor. Temel faturalar için yanıt beklenmez."
                )
            elif yanit_durumu == "0":
                self.yanit_durumu = (
                    "Yanıt bekleniyor. Ticari fatura için cevap bekleniyor."
                )
            elif yanit_durumu == "1":
                self.yanit_durumu = "Red cevabı geldi."
            elif yanit_durumu == "2":
                self.yanit_durumu = "Kabul cevabı geldi."

            self.ulasti_mi = "Bilinmiyor"
            if ulasti_mi == "true":
                self.ulasti_mi = "Evet"
            elif ulasti_mi == "false":
                self.ulasti_mi = "Hayır"

            self.yeniden_gonderilebilir_mi = "Bilinmiyor"
            if yeniden_gonderilebilir_mi == "true":
                self.yeniden_gonderilebilir_mi = "Evet"
            elif yeniden_gonderilebilir_mi == "false":
                self.yeniden_gonderilebilir_mi = "Hayır"

    def response_gelen_irsaliye(self, gelen_irsaliye):

        # MdxUtilityMixin.check_license(self)

        # try:
        # Tarih ve saat bilgileri
        issue_date = date.today()
        issue_date_str = issue_date.strftime("%Y-%m-%d")
        issue_time = datetime.now().strftime("%H:%M:%S")

        web_service = self.env["mdx.web.service"].search(
            [
                ("name", "=", "EFINANS_ALICI"),
                ("active", "=", True),
                ("company_id", "=", self.env.user.company_id.id),
            ],
            limit=1,
        )

        username = str(web_service.username)
        password = str(web_service.password)
        erp_code = web_service.erp_code
        url = web_service.url
        vkn = str(web_service.vkn)

        # İlgili attachment'tan XML verisini çek ve decode et
        attachment = gelen_irsaliye.irsaliye_xml
        if not attachment:
            raise UserError("XML verisi bulunamadı.")
        response_string = base64.b64decode(attachment.datas).decode("utf-8")

        # Başlık kısmında gerekli replace işlemleri (DespatchAdvice -> ReceiptAdvice, DespatchLine -> ReceiptLine)
        response_string = response_string.replace("DespatchAdvice", "ReceiptAdvice")
        response_string = response_string.replace("DespatchLine", "ReceiptLine")

        # lxml kullanarak XML'i parse et
        parser = etree.XMLParser(remove_blank_text=True)
        root = etree.fromstring(response_string.encode("utf-8"), parser)

        # Namespace tanımlamaları (kullandığınız URN'lere göre ayarlayın)
        ns = {
            "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
            "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
            "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
        }

        # 0. Gereksiz ext:UBLExtensions (ve dolayısıyla ds, xades tanımlamalarını) kaldır
        for ext_elem in root.xpath("//ext:UBLExtensions", namespaces=ns):
            parent = ext_elem.getparent()
            if parent is not None:
                parent.remove(ext_elem)

        # 1. Başlık elemanlarını güncelle
        # cbc:ID güncelle (örn. "AAA2025000000001")
        # id_elem = root.find('{%s}ID' % ns['cbc'])
        # if id_elem is not None:
        #     id_elem.text = "AAA2025000000001"

        # cbc:UUID güncelle (örn. "11D07AD7-1113-4FF8-A6E7-038E1C19273E")
        uuid_elem = root.find("{%s}UUID" % ns["cbc"])
        if uuid_elem is not None:
            uuid_elem.text = (
                gelen_irsaliye.ettn
            )  # veya "11D07AD7-1113-4FF8-A6E7-038E1C19273E" ihtiyaca göre

        # cbc:IssueDate güncelle
        issue_date_elem = root.find("{%s}IssueDate" % ns["cbc"])
        if issue_date_elem is not None:
            issue_date_elem.text = issue_date_str

        # cbc:IssueTime güncelle
        issue_time_elem = root.find("{%s}IssueTime" % ns["cbc"])
        if issue_time_elem is not None:
            issue_time_elem.text = issue_time

        # ReceiptAdviceTypeCode değeri aynen kalıyor (örneğin "SEVK")

        # 2. OrderReference öğesini ekle veya güncelle
        # Beklenen: <cac:OrderReference>
        #             <cbc:ID>SO20250000000300</cbc:ID>
        #             <cbc:IssueDate>2025-02-20</cbc:IssueDate>
        #         </cac:OrderReference>
        # OrderReference öğesini oluşturun veya güncelleyin
        order_ref = root.find("{%s}OrderReference" % ns["cac"])
        if order_ref is None:
            order_ref = etree.Element("{%s}OrderReference" % ns["cac"])
            id_order = etree.SubElement(order_ref, "{%s}ID" % ns["cbc"])
            id_order.text = gelen_irsaliye.so_number_from_xml
            issue_date_order = etree.SubElement(order_ref, "{%s}IssueDate" % ns["cbc"])
            issue_date_order.text = gelen_irsaliye.belge_tarihi.strftime("%Y-%m-%d")
            # Örneğin, ReceiptAdviceTypeCode öğesinden sonra ekleyin
            rac_elem = root.find("{%s}ReceiptAdviceTypeCode" % ns["cbc"])
            if rac_elem is not None:
                parent = rac_elem.getparent()
                index = list(parent).index(rac_elem)
                parent.insert(index + 1, order_ref)
            else:
                root.insert(0, order_ref)

        # DespatchDocumentReference öğesini oluşturun veya güncelleyin
        despatch_doc_ref = root.find("{%s}DespatchDocumentReference" % ns["cac"])
        if despatch_doc_ref is None:
            despatch_doc_ref = etree.Element(
                "{%s}DespatchDocumentReference" % ns["cac"]
            )
            # OrderReference'in hemen ardından eklemek için:
            order_index = list(root).index(order_ref)
            root.insert(order_index + 1, despatch_doc_ref)
        # DespatchDocumentReference içeriğini güncelleyin
        id_despatch = despatch_doc_ref.find("{%s}ID" % ns["cbc"])
        if id_despatch is None:
            id_despatch = etree.SubElement(despatch_doc_ref, "{%s}ID" % ns["cbc"])
        id_despatch.text = gelen_irsaliye.ettn
        issue_date_despatch = despatch_doc_ref.find("{%s}IssueDate" % ns["cbc"])
        if issue_date_despatch is None:
            issue_date_despatch = etree.SubElement(
                despatch_doc_ref, "{%s}IssueDate" % ns["cbc"]
            )
        issue_date_despatch.text = gelen_irsaliye.irsaliye_gelis_tarihi.strftime(
            "%Y-%m-%d"
        )

        # 1. Signature içeriğini güncelleme
        # XML'de ds:Signature öğesini buluyoruz (namespace: http://www.w3.org/2000/09/xmldsig#)
        # signature = root.find('.//{http://www.w3.org/2000/09/xmldsig#}Signature')
        signature = root.find("{%s}Signature" % ns["cac"])
        if signature is not None:
            delivery_customer = root.find("{%s}DeliveryCustomerParty" % ns["cac"])
            uri = signature.find(".//{%s}URI" % ns["cbc"]).text
            # Örneğin, ds:SignatureValue öğesini güncelleyelim
            if delivery_customer is not None:
                signature.clear()  # Mevcut alt elementleri kaldırır

                # 1. <cbc:ID schemeID="VKN_TCKN">...</cbc:ID> ekleyin
                id_elem = etree.SubElement(signature, "{%s}ID" % ns["cbc"])
                id_elem.set("schemeID", "VKN_TCKN")
                id_value = delivery_customer.find(".//{%s}ID" % ns["cbc"])
                id_elem.text = id_value.text if id_value is not None else ""

                # 2. <cac:SignatoryParty> bölümünü oluşturun
                signatory_party = etree.SubElement(
                    signature, "{%s}SignatoryParty" % ns["cac"]
                )

                # 2.1 <cac:PartyIdentification> altındaki <cbc:ID schemeID="VKN">...</cbc:ID>
                party_identification = etree.SubElement(
                    signatory_party, "{%s}PartyIdentification" % ns["cac"]
                )
                party_id = etree.SubElement(party_identification, "{%s}ID" % ns["cbc"])
                party_id.set("schemeID", "VKN")
                party_id.text = id_value.text if id_value is not None else ""

                # 2.2 <cac:PostalAddress> altındaki alanları ekleyin
                postal_address = etree.SubElement(
                    signatory_party, "{%s}PostalAddress" % ns["cac"]
                )

                # <cbc:CitySubdivisionName>
                city_sub_elem = etree.SubElement(
                    postal_address, "{%s}CitySubdivisionName" % ns["cbc"]
                )
                cs_value = delivery_customer.find(
                    ".//{%s}CitySubdivisionName" % ns["cbc"]
                )
                city_sub_elem.text = cs_value.text if cs_value is not None else ""

                # <cbc:CityName>
                city_name_elem = etree.SubElement(
                    postal_address, "{%s}CityName" % ns["cbc"]
                )
                cn_value = delivery_customer.find(".//{%s}CityName" % ns["cbc"])
                city_name_elem.text = cn_value.text if cn_value is not None else ""

                # <cac:Country> içerisinde <cbc:Name>
                country_elem = etree.SubElement(
                    postal_address, "{%s}Country" % ns["cac"]
                )
                country_name_elem = etree.SubElement(
                    country_elem, "{%s}Name" % ns["cbc"]
                )
                # Ülke bilgisini doğru namespace ile, hiyerarşi içerisinde arayın
                country_source = delivery_customer.find(".//{%s}Country" % ns["cac"])
                if country_source is not None:
                    c_name = country_source.find("{%s}Name" % ns["cbc"])
                    country_name_elem.text = c_name.text if c_name is not None else ""
                else:
                    country_name_elem.text = ""

                # 3. <cac:DigitalSignatureAttachment> bölümünü oluşturun
                digital_signature_attachment = etree.SubElement(
                    signature, "{%s}DigitalSignatureAttachment" % ns["cac"]
                )
                external_reference = etree.SubElement(
                    digital_signature_attachment, "{%s}ExternalReference" % ns["cac"]
                )
                uri_elem = etree.SubElement(external_reference, "{%s}URI" % ns["cbc"])
                uri_value = delivery_customer.find(".//{%s}WebsiteURI" % ns["cbc"])
                uri_elem.text = uri_value.text if uri_value is not None else ""

        # 2. cac:DespatchSupplierParty ve cac:DeliveryCustomerParty öğelerinin yerlerini değiştirme
        # # Namespace tanımlamanızdaki cac kısmını kullanıyoruz.
        # delivery_customer = root.find('{%s}DeliveryCustomerParty' % ns['cac'])
        despatch_supplier = root.find("{%s}DespatchSupplierParty" % ns["cac"])
        if delivery_customer is not None and despatch_supplier is not None:
            # Her iki öğeyi de mevcut ebeveynden kaldırıyoruz
            parent = delivery_customer.getparent()
            parent.remove(delivery_customer)
            parent.remove(despatch_supplier)

            # İstenen sıralamaya göre: önce DeliveryCustomerParty, sonra DespatchSupplierParty.
            # Bu öğeleri, örneğin, Signature öğesinin hemen sonrasına ekleyebilir veya başka bir uygun pozisyona yerleştirebilirsiniz.
            # Aşağıda, root üzerinde Signature öğesini bulup, onun hemen sonrasına ekleme örneği verilmiştir:
            sig = root.find("{%s}Signature" % ns["cac"])
            if sig is not None:
                parent_of_sig = sig.getparent()
                sig_index = list(parent_of_sig).index(sig)
                # Eğer parent_of_sig ile delivery_customer/despatch_supplier aynı ebeveyn ise
                parent_of_sig.insert(sig_index + 1, delivery_customer)
                parent_of_sig.insert(sig_index + 2, despatch_supplier)
            else:
                # Eğer Signature bulunamazsa, root üzerinde uygun bir index belirleyip ekleyebilirsiniz.
                root.insert(0, delivery_customer)
                root.insert(1, despatch_supplier)

        # 4. Fazladan gelen <cac:GoodsItem>, <cac:ShipmentStage> ve <cac:TransportHandlingUnit> öğelerini kaldır
        for tag in ["GoodsItem", "ShipmentStage", "TransportHandlingUnit"]:
            for elem in root.xpath("//cac:%s" % tag, namespaces=ns):
                parent = elem.getparent()
                if parent is not None:
                    parent.remove(elem)

        # Orijinal XML’deki ActualDespatchDate ve ActualDespatchTime değerlerini alalım
        despatch_date_elem = root.find(".//{%s}ActualDespatchDate" % ns["cbc"])
        despatch_time_elem = root.find(".//{%s}ActualDespatchTime" % ns["cbc"])
        new_date = (
            despatch_date_elem.text if despatch_date_elem is not None else "2025-02-28"
        )
        new_time = (
            despatch_time_elem.text if despatch_time_elem is not None else "14:00:00"
        )

        # <cac:Delivery> öğelerini güncelleyelim
        delivery_nodes = root.xpath("//cac:Delivery", namespaces=ns)
        for delivery in delivery_nodes:
            # Mevcut alt öğeleri temizle
            for child in list(delivery):
                delivery.remove(child)
            # Yeni alt öğeleri ekle: ActualDeliveryDate ve ActualDeliveryTime, orijinaldeki despatch değerlerinden alınacak
            act_del_date = etree.SubElement(
                delivery, "{%s}ActualDeliveryDate" % ns["cbc"]
            )
            act_del_date.text = new_date
            act_del_time = etree.SubElement(
                delivery, "{%s}ActualDeliveryTime" % ns["cbc"]
            )
            act_del_time.text = new_time
            # <cac:Despatch> öğesi ekleniyor (içeriği boş bırakılıyor)
            despatch_el = etree.SubElement(delivery, "{%s}Despatch" % ns["cac"])

        original_receipt_lines = root.xpath("//cac:ReceiptLine", namespaces=ns)
        line_unit_codes = {}
        for idx, rec_line in enumerate(original_receipt_lines, start=1):
            # Her satır için ilgili miktar alanlarının unitCode değerlerini alıyoruz;
            # eğer ilgili element veya unitCode yoksa varsayılan "C62" değeri kullanılıyor.
            received_el = rec_line.find("{%s}ReceivedQuantity" % ns["cbc"])
            rejected_el = rec_line.find("{%s}RejectedQuantity" % ns["cbc"])
            short_el = rec_line.find("{%s}ShortQuantity" % ns["cbc"])
            oversupply_el = rec_line.find("{%s}OversupplyQuantity" % ns["cbc"])
            line_unit_codes[idx] = {
                "received": (
                    received_el.get("unitCode")
                    if (received_el is not None and received_el.get("unitCode"))
                    else "C62"
                ),
                "rejected": (
                    rejected_el.get("unitCode")
                    if (rejected_el is not None and rejected_el.get("unitCode"))
                    else "C62"
                ),
                "short": (
                    short_el.get("unitCode")
                    if (short_el is not None and short_el.get("unitCode"))
                    else "C62"
                ),
                "oversupply": (
                    oversupply_el.get("unitCode")
                    if (oversupply_el is not None and oversupply_el.get("unitCode"))
                    else "C62"
                ),
            }

        # 6. Mevcut ReceiptLine öğelerini kaldırıyoruz
        receipt_lines = root.xpath("//cac:ReceiptLine", namespaces=ns)
        for rec_line in receipt_lines:
            parent = rec_line.getparent()
            if parent is not None:
                parent.remove(rec_line)

        # 7. Gelen satır kayıtları (gelen_irsaliye.waybill_line_ids) üzerinden yeni ReceiptLine öğelerini oluşturuyoruz
        for idx, line in enumerate(gelen_irsaliye.waybill_line_ids, start=1):
            receipt_line = etree.Element("{%s}ReceiptLine" % ns["cac"])

            # <cbc:ID>
            id_el = etree.SubElement(receipt_line, "{%s}ID" % ns["cbc"])
            id_el.text = str(idx)

            # UnitCode değerlerini, ilgili orijinal satırdan alıyoruz (varsayılan olarak "C62" eğer yoksa)
            unit_codes = line_unit_codes.get(
                idx,
                {
                    "received": "C62",
                    "rejected": "C62",
                    "short": "C62",
                    "oversupply": "C62",
                },
            )

            # <cbc:ReceivedQuantity unitCode="...">
            rec_qty_el = etree.SubElement(
                receipt_line, "{%s}ReceivedQuantity" % ns["cbc"]
            )
            rec_qty_el.set("unitCode", unit_codes["received"])
            rec_qty_el.text = str(line.received_qty)

            # <cbc:RejectedQuantity unitCode="..."> (varsa)
            if line.rejected_qty:
                rej_qty_el = etree.SubElement(
                    receipt_line, "{%s}RejectedQuantity" % ns["cbc"]
                )
                rej_qty_el.set("unitCode", unit_codes["rejected"])
                rej_qty_el.text = str(line.rejected_qty)

            # <cbc:ShortQuantity unitCode="..."> (varsa)
            if line.short_qty:
                short_qty_el = etree.SubElement(
                    receipt_line, "{%s}ShortQuantity" % ns["cbc"]
                )
                short_qty_el.set("unitCode", unit_codes["short"])
                short_qty_el.text = str(line.short_qty)

            # <cbc:OversupplyQuantity unitCode="..."> (varsa)
            if line.oversupply_qty:
                over_qty_el = etree.SubElement(
                    receipt_line, "{%s}OversupplyQuantity" % ns["cbc"]
                )
                over_qty_el.set("unitCode", unit_codes["oversupply"])
                over_qty_el.text = str(line.oversupply_qty)

            # <cbc:RejectReason> (varsa)
            if line.reject_reason:
                rej_reason_el = etree.SubElement(
                    receipt_line, "{%s}RejectReason" % ns["cbc"]
                )
                rej_reason_el.text = line.reject_reason

            # <cac:OrderLineReference> içerisinde <cbc:LineID>
            order_line_ref = etree.SubElement(
                receipt_line, "{%s}OrderLineReference" % ns["cac"]
            )
            line_id_el = etree.SubElement(order_line_ref, "{%s}LineID" % ns["cbc"])
            line_id_el.text = str(idx)

            # <cac:DespatchLineReference> içerisinde <cbc:LineID>
            despatch_line_ref = etree.SubElement(
                receipt_line, "{%s}DespatchLineReference" % ns["cac"]
            )
            line_id_ref_el = etree.SubElement(
                despatch_line_ref, "{%s}LineID" % ns["cbc"]
            )
            line_id_ref_el.text = str(idx)

            # <cac:Item> kısmı
            item_el = etree.SubElement(receipt_line, "{%s}Item" % ns["cac"])
            name_el = etree.SubElement(item_el, "{%s}Name" % ns["cbc"])
            name_el.text = line.supplier_product_name or ""
            sellers_item = etree.SubElement(
                item_el, "{%s}SellersItemIdentification" % ns["cac"]
            )
            id_item_el = etree.SubElement(sellers_item, "{%s}ID" % ns["cbc"])
            id_item_el.text = line.supplier_product_code or ""

            # Oluşturulan ReceiptLine öğesini kök (root) elementine ekliyoruz
            root.append(receipt_line)

        # Güncellenmiş XML string'ini oluştur ve log alanına yazdırın
        response_string_modified = etree.tostring(
            root, encoding="utf-8", pretty_print=True
        ).decode("utf-8")
        gelen_irsaliye.write({"logging_field2": response_string_modified})

        decoded_xml = self.base64_encode(response_string_modified)
        hash_obj = self.calculate_md5(response_string_modified)

        counter = (
            self.env["mdx.dokuman.sayac"]
            .search(
                [
                    ("code", "=", "DOKUMANSAYAC"),
                    ("company_id", "=", self.env.user.company_id.id),
                ],
                limit=1,
            )
            .gonderilecek_sonraki_sira_no
        )
        counter += 1
        self.env["mdx.dokuman.sayac"].search(
            [
                ("code", "=", "DOKUMANSAYAC"),
                ("company_id", "=", self.env.user.company_id.id),
            ]
        ).write({"gonderilecek_sonraki_sira_no": counter})

        post_string = '<?xml version="1.0" encoding="utf-8"?>'
        post_string += '<soapenv:Envelope xmlns:ser="http://service.connector.uut.cs.com.tr/" xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
        post_string += "<soapenv:Header>"
        post_string += '<wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">'
        post_string += "<wsse:UsernameToken>"
        post_string += "<wsse:Username>" + str(username) + "</wsse:Username>"
        post_string += "<wsse:Password>" + str(password) + "</wsse:Password>"
        post_string += "</wsse:UsernameToken>"
        post_string += "</wsse:Security>"
        post_string += "</soapenv:Header>"
        post_string += "<soapenv:Body>"
        post_string += "<ser:belgeGonderExt>"
        post_string += "<parametreler>"
        post_string += "<belgeHash>" + str(hash_obj) + "</belgeHash>"
        post_string += "<belgeNo>" + str(counter) + "</belgeNo>"
        post_string += "<belgeTuru>IRSALIYE_YANITI_UBL</belgeTuru>"
        post_string += "<belgeVersiyon>1.0</belgeVersiyon>"
        post_string += "<erpKodu>" + str(erp_code) + "</erpKodu>"
        post_string += "<mimeType>application/xml</mimeType>"
        post_string += "<vergiTcKimlikNo>" + str(vkn) + "</vergiTcKimlikNo>"
        post_string += "<veri>" + str(decoded_xml) + "</veri>"
        post_string += "</parametreler>"
        post_string += "</ser:belgeGonderExt>"
        post_string += "</soapenv:Body>"
        post_string += "</soapenv:Envelope>"

        gelen_irsaliye.write({"logging_field6": post_string})

        # namespaces = {
        #     'ns2': 'http://service.connector.uut.cs.com.tr/'
        # }

        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}

        response = requests.post(url, data=post_string, headers=headers)

        # root = ET.fromstring(response.content)

        if response.status_code == 200:
            # XML'den değerleri çek
            gelen_irsaliye.write(
                {
                    "irsaliye_onay_statu": "1",
                    "logging_field5": response.text + " ***RESPONSE",
                }
            )

            # belgeOid al
            root = ET.fromstring(response.text)
            namespaces = {
                "S": "http://schemas.xmlsoap.org/soap/envelope/",
                "ns2": "http://service.connector.uut.cs.com.tr/",
            }

            # belgeOid, ns2:belgeGonderExtResponse altındadır.
            belge_elem = root.find(".//ns2:belgeGonderExtResponse/belgeOid", namespaces)
            if belge_elem is not None:
                belge_oid = belge_elem.text or ""
                gelen_irsaliye.write({"yanit_belge_oid": belge_oid})

        else:
            gelen_irsaliye.write(
                {"logging_field4": str(response.status_code) + " ***RESPONSE"}
            )
            return

    # except Exception as e:
    #     raise UserError(f"XML parse hatası: {str(e)}")

    # TODO : GELEN IRSALIYE METOTLARI DUZENLENECEK

    def search_incoming_waybills(self):

        # MdxUtilityMixin.check_license(self)

        web_service = self.env["mdx.web.service"].search(
            [
                ("name", "=", "EFINANS_ALICI"),
                ("active", "=", True),
                ("company_id", "=", self.env.user.company_id.id),
            ],
            limit=1,
        )

        if not web_service:
            raise UserError("Web servisi yapılandırması bulunamadı!")

        username = str(web_service.username)
        password = str(web_service.password)
        url = web_service.url
        erp_code = web_service.erp_code
        vkn = str(self.env.user.company_id.vat)
        year = str(date.today().year)

        post_string = f"""<?xml version="1.0" encoding="UTF-8"?>
            <soapenv:Envelope xmlns:ser="http://service.connector.uut.cs.com.tr/"
                xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
                <soapenv:Header>
                    <wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
                        <wsse:UsernameToken>
                            <wsse:Username>{username}</wsse:Username>
                            <wsse:Password>{password}</wsse:Password>
                        </wsse:UsernameToken>
                    </wsse:Security>
                </soapenv:Header>
                <soapenv:Body>
                    <ser:gelenBelgeleriListeleExt>
                        <parametreler>
                            <belgeTuru>IRSALIYE</belgeTuru>
                            <donusTipiVersiyon>6.0</donusTipiVersiyon>
                            <erpKodu>{erp_code}</erpKodu>
                            <vergiTcKimlikNo>{vkn}</vergiTcKimlikNo>
                            <gelisTarihiBaslangic>{year}01010000000</gelisTarihiBaslangic>
                            <belgelerAlindiMi>true</belgelerAlindiMi>
                        </parametreler>
                    </ser:gelenBelgeleriListeleExt>
                </soapenv:Body>
            </soapenv:Envelope>
        """

        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}

        try:
            response = requests.post(
                url, data=post_string.encode("utf-8"), headers=headers, timeout=60
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise UserError(f"SOAP isteği başarısız! Hata: {str(e)}")

        if response.status_code == 200:
            root = ET.fromstring(response.text)

            namespaces = {
                "S": "http://schemas.xmlsoap.org/soap/envelope/",
                "ns2": "http://service.connector.uut.cs.com.tr/",
            }

            return_elements = root.findall(
                ".//ns2:gelenBelgeleriListeleExtResponse/return", namespaces
            )

            belge_sira_no = 0
            for return_elem in return_elements:
                waybill_data = {
                    "company_id": web_service.company_id.id,
                    "name": return_elem.find("belgeNo").text or "",
                    "belge_sira_no": return_elem.find("belgeSiraNo").text or "",
                    "belge_tarihi": (
                        datetime.strptime(
                            return_elem.find("belgeTarihi").text, "%Y%m%d"
                        ).date()
                        if return_elem.find("belgeTarihi") is not None
                        and return_elem.find("belgeTarihi").text
                        else False
                    ),
                    "belge_turu": return_elem.find("belgeTuru").text or "IRSALIYE",
                    "ettn": return_elem.find("ettn").text or "",
                    "gonderen_etiket": return_elem.find("gonderenEtiket").text or "",
                    "gonderen_vkn_tckn": return_elem.find("gonderenVknTckn").text or "",
                    "alan_etiket": return_elem.find("alanEtiket").text or "",
                    "alici_unvan": return_elem.find("aliciUnvan").text or "",
                    "belge_versiyon": return_elem.find("belgeVersiyon").text or "",
                    "satici_unvan": return_elem.find("saticiUnvan").text or "",
                    "zarf_id": return_elem.find("zarfId").text or "",
                    "belge_hash": (
                        return_elem.find("belgeHash").text
                        if return_elem.find("belgeHash") is not None
                        else ""
                    ),
                    "irsaliye_gelis_tarihi": (
                        datetime.strptime(
                            return_elem.find("faturaGelisTarihi").text[:8], "%Y%m%d"
                        ).date()
                        if return_elem.find("faturaGelisTarihi") is not None
                        and return_elem.find("faturaGelisTarihi").text
                        else False
                    ),
                    "irsaliye_senaryo": (
                        self.env["mdx.ebelge.senaryo"]
                        .search([("code", "=", return_elem.find("profileId").text)])
                        .id
                        if return_elem.find("profileId") is not None
                        else False
                    ),
                }
                belge_sira_no = return_elem.find("belgeSiraNo").text

                existing_waybill = self.env["mdx.gelen.irsaliye"].search(
                    [("ettn", "=", waybill_data["ettn"])], limit=1
                )
                if not existing_waybill:
                    self.env["mdx.gelen.irsaliye"].create(waybill_data)

            while len(return_elements) == 100:
                post_string = f"""<?xml version="1.0" encoding="UTF-8"?>
                    <soapenv:Envelope xmlns:ser="http://service.connector.uut.cs.com.tr/"
                        xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
                        <soapenv:Header>
                            <wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
                                <wsse:UsernameToken>
                                    <wsse:Username>{username}</wsse:Username>
                                    <wsse:Password>{password}</wsse:Password>
                                </wsse:UsernameToken>
                            </wsse:Security>
                        </soapenv:Header>
                        <soapenv:Body>
                            <ser:gelenBelgeleriListeleExt>
                                <parametreler>
                                    <belgeTuru>IRSALIYE</belgeTuru>
                                    <donusTipiVersiyon>6.0</donusTipiVersiyon>
                                    <erpKodu>{erp_code}</erpKodu>
                                    <vergiTcKimlikNo>{vkn}</vergiTcKimlikNo>
                                    <sonAlinanBelgeSiraNumarasi>{belge_sira_no}</sonAlinanBelgeSiraNumarasi>
                                    <belgelerAlindiMi>true</belgelerAlindiMi>
                                </parametreler>
                            </ser:gelenBelgeleriListeleExt>
                        </soapenv:Body>
                    </soapenv:Envelope>
                """

                try:
                    response = requests.post(
                        url,
                        data=post_string.encode("utf-8"),
                        headers=headers,
                        timeout=60,
                    )
                    response.raise_for_status()
                except requests.exceptions.RequestException as e:
                    raise UserError(f"SOAP isteği başarısız! Hata: {str(e)}")

                if response.status_code == 200:
                    root = ET.fromstring(response.text)
                    return_elements = root.findall(
                        ".//ns2:gelenBelgeleriListeleExtResponse/return", namespaces
                    )

                    belge_sira_no = 0
                    for return_elem in return_elements:
                        waybill_data = {
                            "company_id": web_service.company_id.id,
                            "name": return_elem.find("belgeNo").text or "",
                            "belge_sira_no": return_elem.find("belgeSiraNo").text or "",
                            "belge_tarihi": (
                                datetime.strptime(
                                    return_elem.find("belgeTarihi").text, "%Y%m%d"
                                ).date()
                                if return_elem.find("belgeTarihi") is not None
                                and return_elem.find("belgeTarihi").text
                                else False
                            ),
                            "belge_turu": return_elem.find("belgeTuru").text
                            or "IRSALIYE",
                            "ettn": return_elem.find("ettn").text or "",
                            "gonderen_etiket": return_elem.find("gonderenEtiket").text
                            or "",
                            "gonderen_vkn_tckn": return_elem.find(
                                "gonderenVknTckn"
                            ).text
                            or "",
                            "alan_etiket": return_elem.find("alanEtiket").text or "",
                            "alici_unvan": return_elem.find("aliciUnvan").text or "",
                            "belge_versiyon": return_elem.find("belgeVersiyon").text
                            or "",
                            "satici_unvan": return_elem.find("saticiUnvan").text or "",
                            "zarf_id": return_elem.find("zarfId").text or "",
                            "belge_hash": (
                                return_elem.find("belgeHash").text
                                if return_elem.find("belgeHash") is not None
                                else ""
                            ),
                            "irsaliye_gelis_tarihi": (
                                datetime.strptime(
                                    return_elem.find("faturaGelisTarihi").text[:8],
                                    "%Y%m%d",
                                ).date()
                                if return_elem.find("faturaGelisTarihi") is not None
                                and return_elem.find("faturaGelisTarihi").text
                                else False
                            ),
                            "irsaliye_senaryo": (
                                self.env["mdx.ebelge.senaryo"]
                                .search(
                                    [("code", "=", return_elem.find("profileId").text)]
                                )
                                .id
                                if return_elem.find("profileId") is not None
                                else False
                            ),
                        }
                        belge_sira_no = return_elem.find("belgeSiraNo").text

                        existing_waybill = self.env["mdx.gelen.irsaliye"].search(
                            [("ettn", "=", waybill_data["ettn"])], limit=1
                        )
                        if not existing_waybill:
                            self.env["mdx.gelen.irsaliye"].create(waybill_data)

        else:
            raise UserError(
                f"İrsaliye listesi alınamadı! HTTP Durum Kodu: {response.status_code}"
            )

    def get_incoming_waybill_html(self, ettn):

        # MdxUtilityMixin.check_license(self)

        web_service = self.env["mdx.web.service"].search(
            [
                ("name", "=", "EFINANS_ALICI"),
                ("active", "=", True),
                ("company_id", "=", self.env.user.company_id.id),
            ],
            limit=1,
        )

        gelen_irsaliye_record = self.env["mdx.gelen.irsaliye"].search(
            [("ettn", "=", ettn)], limit=1
        )

        if not web_service:
            raise UserError("Web servisi yapılandırması bulunamadı!")

        username = str(web_service.username)
        password = str(web_service.password)
        url = web_service.url
        erp_code = web_service.erp_code
        vkn = str(self.env.user.company_id.vat)

        post_string = f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                            xmlns:ser="http://service.connector.uut.cs.com.tr/">
                            <soapenv:Header>
                                <wsse:Security soap:mustUnderstand="1"
                                    xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
                                    xmlns:soap="soap">
                                    <wsse:UsernameToken>
                                        <wsse:Username>{username}</wsse:Username>
                                        <wsse:Password>{password}</wsse:Password>
                                    </wsse:UsernameToken>
                                </wsse:Security>
                            </soapenv:Header>
                            <soapenv:Body>
                                <ser:gelenBelgeIndirExt>
                                    <vergiTcKimlikNo>{vkn}</vergiTcKimlikNo>
                                    <belgeEttn>{ettn}</belgeEttn>
                                    <belgeTuru>IRSALIYE</belgeTuru>
                                    <erpKodu>{erp_code}</erpKodu>
                                    <belgeFormati>HTML</belgeFormati>
                                </ser:gelenBelgeIndirExt>
                            </soapenv:Body>
                        </soapenv:Envelope>
        """

        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}

        try:
            response = requests.post(
                url, data=post_string.encode("utf-8"), headers=headers, timeout=60
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise UserError(f"SOAP isteği başarısız! Hata: {str(e)}")

        if response.status_code == 200:
            root = ET.fromstring(response.text)

            namespaces = {
                "S": "http://schemas.xmlsoap.org/soap/envelope/",
                "ns2": "http://service.connector.uut.cs.com.tr/",
            }

            html_data_element = root.find(
                ".//ns2:gelenBelgeIndirExtResponse/return", namespaces
            )

            if html_data_element is not None:
                html_data = self.base64_decode(html_data_element.text)
                file_name = f"{ettn}.html"

                attachment = self.env["ir.attachment"].create(
                    {
                        "name": file_name,
                        "datas": self.base64_encode(html_data),
                        # 'datas_fname': file_name,
                        "res_model": "mdx.gelen.irsaliye",
                        "res_id": gelen_irsaliye_record.id,
                        "type": "binary",
                    }
                )

                if attachment:
                    gelen_irsaliye_record.write({"irsaliye_html": attachment.id})
                else:
                    gelen_irsaliye_record.write(
                        {"logging_field1": "İrsaliye HTML içeriği kaydedilemedi!"}
                    )

        else:
            gelen_irsaliye_record.write(
                {
                    "logging_field1": f"İrsaliye HTML içeriği alınamadı! HTTP Durum Kodu: {response.status_code}"
                }
            )

    def get_incoming_waybill_pdf(self, ettn):

        # MdxUtilityMixin.check_license(self)

        # Web servisini bul
        web_service = self.env["mdx.web.service"].search(
            [
                ("name", "=", "EFINANS_ALICI"),
                ("active", "=", True),
                ("company_id", "=", self.env.user.company_id.id),
            ],
            limit=1,
        )
        if not web_service:
            raise UserError("Web servisi yapılandırması bulunamadı!")

        # İlgili gelen irsaliye kaydını bul
        gelen_irsaliye_record = self.env["mdx.gelen.irsaliye"].search(
            [("ettn", "=", ettn)], limit=1
        )
        if not gelen_irsaliye_record:
            raise UserError(f"Ettn ile eşleşen gelen irsaliye bulunamadı: {ettn}")

        # SOAP isteği için gerekli parametreler
        username, password, url, erp_code = (
            str(web_service.username),
            str(web_service.password),
            web_service.url,
            web_service.erp_code,
        )
        vkn = str(self.env.user.company_id.vat)

        # SOAP post string
        post_string = f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                                xmlns:ser="http://service.connector.uut.cs.com.tr/">
                                <soapenv:Header>
                                    <wsse:Security soap:mustUnderstand="1"
                                        xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
                                        xmlns:soap="soap">
                                        <wsse:UsernameToken>
                                            <wsse:Username>{username}</wsse:Username>
                                            <wsse:Password>{password}</wsse:Password>
                                        </wsse:UsernameToken>
                                    </wsse:Security>
                                </soapenv:Header>
                                <soapenv:Body>
                                    <ser:gelenBelgeIndirExt>
                                        <vergiTcKimlikNo>{vkn}</vergiTcKimlikNo>
                                        <belgeEttn>{ettn}</belgeEttn>
                                        <belgeTuru>IRSALIYE</belgeTuru>
                                        <erpKodu>{erp_code}</erpKodu>
                                        <belgeFormati>PDF</belgeFormati>
                                    </ser:gelenBelgeIndirExt>
                                </soapenv:Body>
                            </soapenv:Envelope>"""

        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}

        # SOAP isteği gönder ve hata yönetimi
        try:
            response = requests.post(
                url, data=post_string.encode("utf-8"), headers=headers, timeout=60
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise UserError(f"SOAP isteği başarısız! Hata: {str(e)}")

        # Yanıt durumu kontrolü
        if response.status_code == 200:
            try:
                # XML yanıtını ayrıştır
                root = ET.fromstring(response.text)
                namespaces = {
                    "S": "http://schemas.xmlsoap.org/soap/envelope/",
                    "ns2": "http://service.connector.uut.cs.com.tr/",
                }
                pdf_data_element = root.find(
                    ".//ns2:gelenBelgeIndirExtResponse/return", namespaces
                )

                if pdf_data_element is not None:
                    # PDF verisini base64 çöz
                    pdf_data = base64.b64decode(pdf_data_element.text)
                    file_name = f"{ettn}.pdf"

                    # PDF'yi ir.attachment olarak kaydet
                    attachment = self.env["ir.attachment"].create(
                        {
                            "name": file_name,
                            "datas": base64.b64encode(
                                pdf_data
                            ),  # PDF'yi yeniden base64'e encode edip saklıyoruz
                            "res_model": "mdx.gelen.irsaliye",
                            "res_id": gelen_irsaliye_record.id,
                            "type": "binary",
                        }
                    )

                    # Attachment kaydını gelen irsaliye ile ilişkilendir
                    if attachment:
                        gelen_irsaliye_record.write({"irsaliye_pdf": attachment.id})
                    else:
                        gelen_irsaliye_record.write(
                            {"logging_field1": "İrsaliye PDF içeriği kaydedilemedi!"}
                        )
                else:
                    gelen_irsaliye_record.write(
                        {"logging_field1": "PDF verisi bulunamadı!"}
                    )
            except Exception as e:
                raise UserError(f"Yanıt işlenirken hata oluştu: {str(e)}")
        else:
            gelen_irsaliye_record.write(
                {
                    "logging_field1": f"İrsaliye PDF alınamadı! HTTP Durum Kodu: {response.status_code}"
                }
            )

    def get_incoming_waybill_xml(self, ettn):

        # MdxUtilityMixin.check_license(self)

        """
        İrsaliyeyi XML (UBL) formatında indirir ve kaydeder.
        """
        web_service = self.env["mdx.web.service"].search(
            [
                ("name", "=", "EFINANS_ALICI"),
                ("active", "=", True),
                ("company_id", "=", self.env.user.company_id.id),
            ],
            limit=1,
        )

        gelen_irsaliye_record = self.env["mdx.gelen.irsaliye"].search(
            [("ettn", "=", ettn)], limit=1
        )

        if not web_service:
            raise UserError("Web servisi yapılandırması bulunamadı!")

        try:
            username = str(web_service.username)
            password = str(web_service.password)
            url = web_service.url
            erp_code = web_service.erp_code
            vkn = str(self.env.user.company_id.vat)

            post_string = f"""<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                                xmlns:ser="http://service.connector.uut.cs.com.tr/">
                                <soapenv:Header>
                                    <wsse:Security soap:mustUnderstand="1"
                                        xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
                                        xmlns:soap="soap">
                                        <wsse:UsernameToken>
                                            <wsse:Username>{username}</wsse:Username>
                                            <wsse:Password>{password}</wsse:Password>
                                        </wsse:UsernameToken>
                                    </wsse:Security>
                                </soapenv:Header>
                                <soapenv:Body>
                                    <ser:gelenBelgeIndirExt>
                                        <vergiTcKimlikNo>{vkn}</vergiTcKimlikNo>
                                        <belgeEttn>{ettn}</belgeEttn>
                                        <belgeTuru>IRSALIYE</belgeTuru>
                                        <erpKodu>{erp_code}</erpKodu>
                                        <belgeFormati>UBL</belgeFormati>
                                    </ser:gelenBelgeIndirExt>
                                </soapenv:Body>
                            </soapenv:Envelope>
            """

            headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""}

            try:
                response = requests.post(
                    url, data=post_string.encode("utf-8"), headers=headers, timeout=60
                )
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                raise UserError(f"SOAP isteği başarısız! Hata: {str(e)}")

            if response.status_code == 200:
                root = ET.fromstring(response.text)
                namespaces = {
                    "S": "http://schemas.xmlsoap.org/soap/envelope/",
                    "ns2": "http://service.connector.uut.cs.com.tr/",
                }

                xml_data_element = root.find(
                    ".//ns2:gelenBelgeIndirExtResponse/return", namespaces
                )

                if xml_data_element is not None and xml_data_element.text:
                    try:
                        decoded_xml = base64.b64decode(xml_data_element.text).decode(
                            "utf-8-sig"
                        )
                    except (binascii.Error, UnicodeDecodeError) as e:
                        error_msg = f"Base64 decode hatası: {str(e)}"
                        gelen_irsaliye_record.write(
                            {"invoice_creation_error_details": error_msg}
                        )
                        raise UserError(error_msg)

                    # XML validation ve parse işlemleri
                    try:
                        root = ET.fromstring(decoded_xml.encode("utf-8"))
                    except ET.ParseError as e:
                        error_msg = f"XML parse hatası: {str(e)} - İlk 100 karakter: {decoded_xml[:100]}"
                        gelen_irsaliye_record.write(
                            {"invoice_creation_error_details": error_msg}
                        )
                        raise UserError(error_msg)

                    # Attachment oluşturma
                    file_name = f"{ettn}.xml"
                    attachment = self.env["ir.attachment"].create(
                        {
                            "name": file_name,
                            "datas": base64.b64encode(decoded_xml.encode("utf-8")),
                            "res_model": "mdx.gelen.irsaliye",
                            "res_id": gelen_irsaliye_record.id,
                            "type": "binary",
                        }
                    )

                    if attachment:
                        gelen_irsaliye_record.write({"irsaliye_xml": attachment.id})

                        # XML'den veri çekme kısmı GÜNCELLENDİ
                        ns = {
                            "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
                            "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
                            "ubl": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",  # Ana namespace eklendi
                        }

                        try:
                            # Direkt element bulma
                            order_ref_element = root.find(
                                ".//cac:OrderReference/cbc:ID", ns
                            )

                            # XPath ile alternatif arama
                            if order_ref_element is None:
                                order_ref_element = root.find(
                                    ".//{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}OrderReference"
                                    "/{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}ID"
                                )

                            # Tüm olasılıkları kontrol etme
                            if order_ref_element is None:
                                order_refs = root.findall(".//cac:OrderReference", ns)
                                if order_refs:
                                    order_ref_element = order_refs[0].find("cbc:ID", ns)

                            order_ref_id = (
                                order_ref_element.text
                                if order_ref_element is not None
                                else False
                            )

                            if order_ref_id and isinstance(order_ref_id, str):
                                if "<![CDATA[" in order_ref_id:
                                    order_ref_id = (
                                        order_ref_id.split("<![CDATA[")[1]
                                        .split("]]>")[0]
                                        .strip()
                                    )
                                else:
                                    order_ref_id = order_ref_id.strip()
                            else:
                                gelen_irsaliye_record.write(
                                    {
                                        "attachment_error_details": "OrderReference/ID bulunamadı ya da geçersiz!"
                                    }
                                )
                                order_ref_id = False

                            # additional_document_reference_element = root.findall(".//cac:AdditionalDocumentReference", ns)

                            # tax_exemption_reason_code_element = root.find(".//cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:TaxExemptionReasonCode", ns)

                            # XPath ile alternatif arama
                            # if tax_exemption_reason_code_element is None:
                            #     tax_exemption_reason_code_element = root.find(
                            #         ".//{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxTotal"
                            #         "/{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxSubtotal"
                            #         "/{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}TaxCategory"
                            #         "/{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}TaxExemptionReasonCode"
                            #     )

                            # tax_exemption_reason_code = tax_exemption_reason_code_element.text if tax_exemption_reason_code_element is not None else False

                            # if tax_exemption_reason_code:
                            #     tax_exemption_reason_code = self.env['mdx.sabit.kod'].search([('efinans_kod', '=', tax_exemption_reason_code)], limit=1)
                            #     gelen_irsaliye_record.write({'tax_exemption_reason_code_id': tax_exemption_reason_code.id})

                            waybill_lines = root.findall(".//cac:DespatchLine", ns)
                            for line in waybill_lines:

                                line_id = (
                                    line.find("cbc:ID", ns).text
                                    if line.find("cbc:ID", ns) is not None
                                    else "Bilinmiyor"
                                )
                                line_quantity = (
                                    float(line.find("cbc:DeliveredQuantity", ns).text)
                                    if line.find("cbc:DeliveredQuantity", ns)
                                    is not None
                                    else 0.0
                                )
                                line_product_name = (
                                    line.find("cac:Item/cbc:Name", ns).text
                                    if line.find("cac:Item/cbc:Name", ns) is not None
                                    else "Bilinmiyor"
                                )
                                line_sellers_item_id = (
                                    line.find(
                                        "cac:Item/cac:SellersItemIdentification/cbc:ID",
                                        ns,
                                    ).text
                                    if line.find(
                                        "cac:Item/cac:SellersItemIdentification/cbc:ID",
                                        ns,
                                    )
                                    is not None
                                    else "Bilinmiyor"
                                )
                                product = self.env["product.product"].search(
                                    [
                                        (
                                            "seller_ids.product_name",
                                            "=",
                                            line_product_name,
                                        ),
                                        (
                                            "seller_ids.product_code",
                                            "=",
                                            line_sellers_item_id,
                                        ),
                                        (
                                            "seller_ids.partner_id.id",
                                            "=",
                                            gelen_irsaliye_record.supplier_id.id,
                                        ),
                                    ],
                                    limit=1,
                                )
                                # supplierinfo_id = False
                                create_product = False
                                create_supplierinfo = False
                                if product:
                                    product_account = (
                                        product.property_account_expense_id
                                    )
                                    # supplierinfo_id = product.product_tmpl_id.seller_ids.filtered(
                                    #     lambda x: x.product_name == line_product_name and
                                    #     x.product_code == line_sellers_item_id and
                                    #     x.partner_id.id == gelen_irsaliye_record.supplier_id.id).id if product else False

                                    if product_account:
                                        account_id = product_account.id
                                    else:
                                        account_id = False
                                else:
                                    create_product = True
                                    create_supplierinfo = True
                                    account_id = False

                                # if line_tevkifat_code:
                                #     tevkifat_code = self.env['mdx.sabit.kod'].search([('efinans_kod', '=', line_tevkifat_code)], limit=1)
                                #     if tevkifat_code:
                                #     #     gelen_irsaliye_record.write({'tevkifat_kodu': tevkifat_code.id})
                                #         line_tevkifat_code = tevkifat_code.id

                                # tax_id = False
                                # if line_tax_rate and line_tax_name:
                                #     computed_tax_name = f"{line_tax_rate}%"
                                # tax_group = self.env['account.tax.group'].search(
                                #     ['|', ("name", "=ilike", "KDV%"), ("name", "=ilike", "VAT%")],
                                #     limit=1
                                # )
                                #     if tax_group:
                                #         tax = self.env['account.tax'].search([
                                #             ('type_tax_use', '=', 'purchase'),
                                #             ('amount', '=', line_tax_rate),
                                #             ('tax_group_id', '=', tax_group.id),
                                #             ('name', '=', computed_tax_name),
                                #         ], limit=1)
                                #         if tax:
                                #             tax_id = tax.id

                                # create gelen_irsaliye_line
                                gelen_irsaliye_line = self.env[
                                    "mdx.gelen.irsaliye.line"
                                ].create(
                                    {
                                        "gelen_irsaliye_id": gelen_irsaliye_record.id,
                                        "line_id": line_id,
                                        "quantity": line_quantity,
                                        # 'price_unit': line_price,
                                        # 'price_subtotal': line_total,
                                        # 'tax_rate': line_tax_rate,
                                        # 'tax_name': line_tax_name,
                                        # 'tax_id': tax_id,
                                        "supplier_product_name": line_product_name,
                                        "supplier_product_code": line_sellers_item_id,
                                        # 'supplierinfo_id': supplierinfo_id if supplierinfo_id else False,
                                        "product_id": product.id if product else False,
                                        "account_id": (
                                            account_id if account_id else False
                                        ),
                                        "create_product": create_product,
                                        "create_supplierinfo": create_supplierinfo,
                                        # 'tevkifat_kodu': line_tevkifat_code
                                    }
                                )

                                # product = self.env['product.product'].search([('seller_ids.product_name', '=', line_product_name), ('seller_ids.product_code', '=', line_sellers_item_id)], limit=1)
                                # if product:
                                #     gelen_irsaliye_line.write({'product_id': product.id})
                                #     product_account = product.property_account_expense_id
                                #     if product_account:
                                #         gelen_irsaliye_line.write({'account_id': product_account.id})
                                # else:
                                #     gelen_irsaliye_line.write({'create_product': True})

                                # Loglama eklendi
                                # gelen_irsaliye_record.write({
                                #     'logging_field2': f"Satır ID: {line_id}\nMiktar: {line_quantity}\nToplam: {line_total}\nVergi Oranı: {line_tax_rate}\nVergi Adı: {line_tax_name}\nÜrün Adı: {line_product_name}\nÜrün ID: {line_sellers_item_id}\nFiyat: {line_price}"
                                # })

                        except AttributeError as ae:
                            error_msg = f"XML element attribute hatası: {str(ae)}"
                            gelen_irsaliye_record.write({"logging_field1": error_msg})
                            raise UserError(error_msg)
                        except Exception as e:
                            error_msg = f"Genel XML parse hatası: {str(e)}"
                            gelen_irsaliye_record.write({"logging_field1": error_msg})
                            raise UserError(error_msg)

                        gelen_irsaliye_record.write(
                            {"so_number_from_xml": order_ref_id}
                        )

                    else:
                        gelen_irsaliye_record.write(
                            {"logging_field1": "İrsaliye XML içeriği kaydedilemedi!"}
                        )

            else:
                error_msg = (
                    f"HTTP Hatası: {response.status_code} - {response.text[:200]}"
                )
                gelen_irsaliye_record.write({"logging_field1": error_msg})
                raise UserError(error_msg)

        except requests.exceptions.RequestException as e:
            error_msg = f"Ağ hatası: {str(e)}"
            gelen_irsaliye_record.write({"logging_field2": error_msg})
            raise UserError(error_msg)
        except Exception as e:
            error_msg = f"Beklenmeyen hata: {str(e)}"
            gelen_irsaliye_record.write({"logging_field3": error_msg})
            raise UserError(error_msg)

    def transform_xml_with_xslt(self, xml_content, xslt_b64_data):
        """
        Verilen XML içeriğini, verilen XSLT (Base64 formatında) verisi ile işleyip HTML döndürür.
        """
        if not xslt_b64_data:
             raise UserError("Dönüştürme için geçerli bir XSLT verisi sağlanmadı!")

        try:
            # XSLT İçeriğini Base64'ten Çöz (Binary alan direkt data döner)
            # Not: Binary alan bazen bytes, bazen string dönebilir, garantiye alıyoruz.
            if isinstance(xslt_b64_data, bytes):
                xslt_b64_data = xslt_b64_data.decode('utf-8')
                
            xslt_content = base64.b64decode(xslt_b64_data).decode('utf-8')
            
            # XML ve XSLT'yi Parse Et
            xml_root = etree.fromstring(xml_content.encode('utf-8'))
            xslt_root = etree.fromstring(xslt_content.encode('utf-8'))
            
            # Dönüştürme İşlemi (Transformation)
            transform = etree.XSLT(xslt_root)
            html_dom = transform(xml_root)
            
            # Sonucu String'e çevir
            return str(html_dom)
            
        except Exception as e:
            _logger.error(f"XSLT Dönüştürme Hatası: {str(e)}")
            raise UserError(f"XSLT şablonu ile XML dönüştürülürken hata oluştu: {str(e)}")

    def convert_html_to_pdf(self, html_content):
        """
        HTML içeriğini wkhtmltopdf kullanarak PDF binary verisine çevirir.
        JavaScript çalıştırılması (QR Kod için) desteklenir.
        """
        if not html_content:
            return False

        # Geçici dosya yolları oluştur
        fd, html_path = tempfile.mkstemp(suffix='.html', prefix='preview_')
        pdf_path = html_path.replace('.html', '.pdf')

        try:
            # HTML içeriğini geçici dosyaya yaz
            with os.fdopen(fd, 'wb') as f:
                f.write(html_content.encode('utf-8'))

            # wkhtmltopdf komutunu hazırla
            # --enable-javascript: QR kod scripti için gerekli
            # --javascript-delay 1000: Scriptin çalışması için 1 saniye bekle
            command = [
                'wkhtmltopdf',
                '--enable-javascript',
                '--javascript-delay', '1000',
                '--no-stop-slow-scripts',
                '--page-size', 'A4',
                '--margin-top', '10',
                '--margin-bottom', '10',
                '--margin-left', '10',
                '--margin-right', '10',
                html_path,
                pdf_path
            ]

            # Komutu çalıştır
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, err = process.communicate()

            if process.returncode != 0:
                _logger.error(f"PDF Dönüştürme Hatası (wkhtmltopdf): {err}")
                raise UserError(f"PDF oluşturulurken hata meydana geldi: {err}")

            # Oluşan PDF'i oku
            with open(pdf_path, 'rb') as pdf_file:
                pdf_content = pdf_file.read()

            return pdf_content

        except Exception as e:
            raise UserError(f"PDF dönüştürme işlemi başarısız: {str(e)}")

        finally:
            # Geçici dosyaları temizle
            if os.path.exists(html_path):
                os.remove(html_path)
            if os.path.exists(pdf_path):
                os.remove(pdf_path)

    def create_preview_attachment(self, record, doc_type):
        """
        Fatura veya İrsaliye için XSLT dönüşümü yapar, ardından HTML'i PDF'e çevirir ve Attachment olarak kaydeder.
        """
        xml_content = ""
        xslt_b64_data = False

        # 1. XML Oluştur ve XSLT Verisini Al
        if doc_type == 'FATURA':
            if not record.uuid:
                record.uuid = self.generate_uuid()
            
            # Preview Mode: True (DB'ye kayıt atmaz)
            xml_content = self.generate_invoice_xml(record, preview_mode=True)
            
            if record.efatura_turu_id and record.efatura_turu_id.xslt_attachment_id:
                xslt_b64_data = record.efatura_turu_id.xslt_attachment_id

        elif doc_type == 'IRSALIYE':
            if not record.uuid:
                record.uuid = self.generate_uuid()

            # Preview Mode: True
            xml_content = self.generate_waybill_xml(record, preview_mode=True)
            
            if record.ebelge_turu_id and record.ebelge_turu_id.xslt_attachment_id:
                xslt_b64_data = record.ebelge_turu_id.xslt_attachment_id

        # 2. Fallback XSLT Kontrolü
        if not xslt_b64_data:
            fallback_attachment = self.env['ir.attachment'].search([('name', '=', 'argedit_general.xslt')], limit=1)
            if fallback_attachment:
                xslt_b64_data = fallback_attachment.datas

        if not xslt_b64_data:
            raise UserError(f"{doc_type} türü için tanımlı bir XSLT şablonu bulunamadı!")

        # 3. XML + XSLT -> HTML Dönüşümü
        html_content = self.transform_xml_with_xslt(xml_content, xslt_b64_data)

        # 4. HTML -> PDF Dönüşümü (YENİ KISIM)
        pdf_content = self.convert_html_to_pdf(html_content)

        # 5. Attachment Olarak Kaydet (PDF)
        attachment_name = f"{doc_type}_ONIZLEME_{record.name or 'Draft'}.pdf"
        
        # Eski önizlemeyi temizle
        self.env['ir.attachment'].search([
            ('res_model', '=', record._name),
            ('res_id', '=', record.id),
            ('name', '=', attachment_name)
        ]).unlink()

        attachment = self.env['ir.attachment'].create({
            'name': attachment_name,
            'type': 'binary',
            'datas': base64.b64encode(pdf_content), # PDF binary verisini base64 yapıp kaydediyoruz
            'res_model': record._name,
            'res_id': record.id,
            'mimetype': 'application/pdf', # Mimetype PDF olarak güncellendi
        })

        record.write({
            'uuid': False
        })

        # 6. URL Döndür
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=false', # Tarayıcıda PDF viewer açar
            'target': 'new',
        }