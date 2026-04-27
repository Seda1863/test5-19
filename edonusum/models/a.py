def generate_invoice_xml(self, invoice_record):
        # MdxUtilityMixin.check_license(self)

        for invoice_record in invoice_record.with_context(lang="tr_TR"):

            # E-Fatura Alan Kontrolleri
            if invoice_record.fatura_seri_id.ebelge_turu_id != invoice_record.efatura_turu_id.ebelge_turu_origin_id:
                raise UserError(
                    "Fatura serisi ve e-fatura türü arasında uyumsuzluk var! Lütfen kontrol edin."
                )

            # Calculate issue date
            issue_date = invoice_record.invoice_date or datetime.today().date()
            issue_date_str = issue_date.strftime("%Y-%m-%d")

            # Generate invoice number
            fatura_seri_id = invoice_record.fatura_seri_id

            if not fatura_seri_id:
                invoice_record.write({"fatura_no": ""})
                raise UserError(
                    "Fatura serisi bulunamadı! Lütfen fatura serisini kontrol edin."
                )
            
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
                raise ValueError(f"Fatura serisinde sonraki tarihli fatura bulunmaktadır! Serideki son kullanılan tarih: {fatura_seri_last_used_date_str} - Fatura tarihi: {issue_date_str}")

            eski_fatura_no = invoice_record.fatura_no
            fatura_seri_code = fatura_seri_id.code
            year = issue_date_str.split("-")[0]  # Yılın son iki hanesini alıyoruz

            if eski_fatura_no and eski_fatura_no.startswith(fatura_seri_code):
                fatura_no = eski_fatura_no
            else:
                if not invoice_with_serial:
                    fatura_seri_index = 1
                else:
                    fatura_seri_index = fatura_seri_id.index

                fatura_seri_id.write(
                    {"index": fatura_seri_index + 1, "last_used_date": issue_date}
                )
                fatura_no = f"{fatura_seri_code}{year}{str(fatura_seri_index).zfill(9)}"  # Index'e 12 basamağa kadar sıfır ekliyoruz

                invoice_record.write({"fatura_no": fatura_no})

            expense_count = len(invoice_record.expense_sheet_id.expense_line_ids)

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
            uuid = invoice_record.uuid or self.generate_uuid()
            if not invoice_record.uuid:
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
            xml_string += (
                "<cbc:InvoiceTypeCode>" + fatura_tipi + "</cbc:InvoiceTypeCode>"
            )
                    
            if efatura_turu == "EARSIV":
                xml_string += "<cbc:Note>Gönderim Şekli: ELEKTRONIK</cbc:Note>"

            if fatura_tipi == "IADE":
                bill_date = (
                    str(
                        invoice_record.reversed_entry_id.invoice_date.strftime(
                            "%Y-%m-%d"
                        )
                    )
                    if invoice_record.reversed_entry_id.invoice_date
                    else (
                        str(invoice_record.invoice_date.strftime("%Y-%m-%d"))
                        if invoice_record.invoice_date
                        else datetime.date.today().strftime("%Y-%m-%d")
                    )
                )

                fatura_no_bil = str(
                    invoice_record.reversed_entry_id.fatura_no
                    or invoice_record.reversed_entry_id.name
                    or ""
                )
                xml_string += (
                    "<cbc:Note>"
                    + fatura_no_bil
                    + " No'lu faturaya istinaden iade faturasıdır.</cbc:Note>"
                )
                xml_string += "<cbc:Note>Fatura Tarihi:" + bill_date + "</cbc:Note>"

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
                    "<cbc:Note>Gönderim Şekli: " + str(gonderim_sekli) + "</cbc:Note>"
                )

            if invoice_record.fatura_aciklama:
                xml_string += (
                    "<cbc:Note>" + invoice_record.fatura_aciklama + "</cbc:Note>"
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
            
            if sale_order_lines:
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
                        # if not picking_id.irsaliye_no:
                        #     raise UserError(
                        #         f"{picking_id.name} teslimatı için e-iraliye gönderilmemiş! Lütfen önce irsaliye gönderimini yapın."
                        #     )
                        xml_string += "<cbc:ID>" + str(picking_id.irsaliye_no) + "</cbc:ID>"
                        # Teslimat tarihi boş olabilir, bu durumu kontrol ediyoruz.
                        shipping_date_obj = picking_id.scheduled_date or datetime.now()
                        shipping_date = shipping_date_obj.strftime("%Y-%m-%d")
                        xml_string += "<cbc:IssueDate>" + str(shipping_date) + "</cbc:IssueDate>"
                        xml_string += "</cac:DespatchDocumentReference>"

            if invoice_record.fatura_tipi_id.code == "IADE" or invoice_record.fatura_tipi_id.code == "TEVKIFATIADE":
                xml_string += "<cac:BillingReference><cac:InvoiceDocumentReference>"
                xml_string += "<cbc:ID>" + invoice_record.reversed_entry_id.fatura_no + "</cbc:ID>"
                xml_string += "<cbc:IssueDate>" + str(invoice_record.reversed_entry_id.invoice_date) + "</cbc:IssueDate>"
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
            if len(company_vkn) == 10:
                xml_string += '<cbc:ID schemeID="VKN">' + receiver_vkn + "</cbc:ID>"
            elif len(company_vkn) == 11:
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

            if len(company_vkn) == 11:
                xml_string += "<cac:Person>"
                xml_string += "<cbc:FirstName>" + receiver_name + "</cbc:FirstName>"
                xml_string += "<cbc:FamilyName> </cbc:FamilyName>"  # TODO
                xml_string += "</cac:Person>"

            xml_string += "</cac:Party>"
            xml_string += "</cac:AccountingCustomerParty>"

            if invoice_record.efatura_turu_id.code == "EIHRACAT":
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

            if invoice_record.efatura_turu_id.code == "EIHRACAT":
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
            xml_string += "<cac:AllowanceCharge>"
            xml_string += "<cbc:ChargeIndicator>true</cbc:ChargeIndicator>"
            xml_string += '<cbc:Amount currencyID="TRY">0</cbc:Amount>'
            xml_string += "</cac:AllowanceCharge>"

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
                xml_string += "<cac:LegalMonetaryTotal>"
                xml_string += (
                    '<cbc:LineExtensionAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + str(invoice_record.amount_untaxed)
                    + "</cbc:LineExtensionAmount>"
                )
                xml_string += (
                    '<cbc:TaxExclusiveAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + str(invoice_record.amount_untaxed)
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
                    + '">0</cbc:AllowanceTotalAmount>'
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
                    + str(invoice_record.amount_total)
                    + "</cbc:PayableAmount>"
                )
                xml_string += "</cac:LegalMonetaryTotal>"
            elif fatura_tipi == "IHRACKAYITLI":
                xml_string += "<cac:LegalMonetaryTotal>"
                xml_string += (
                    '<cbc:LineExtensionAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + str(invoice_record.amount_untaxed)
                    + "</cbc:LineExtensionAmount>"
                )
                xml_string += (
                    '<cbc:TaxExclusiveAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + str(invoice_record.amount_untaxed)
                    + "</cbc:TaxExclusiveAmount>"
                )
                xml_string += (
                    '<cbc:TaxInclusiveAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + str(invoice_record.amount_total + tax_amount_currency)
                    + "</cbc:TaxInclusiveAmount>"
                )
                xml_string += (
                    '<cbc:AllowanceTotalAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">0</cbc:AllowanceTotalAmount>'
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
                    + str(invoice_record.amount_total)
                    + "</cbc:PayableAmount>"
                )
                xml_string += "</cac:LegalMonetaryTotal>"
            else:
                xml_string += "<cac:LegalMonetaryTotal>"
                xml_string += (
                    '<cbc:LineExtensionAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + str(invoice_record.amount_untaxed)
                    + "</cbc:LineExtensionAmount>"
                )
                xml_string += (
                    '<cbc:TaxExclusiveAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + str(invoice_record.amount_untaxed)
                    + "</cbc:TaxExclusiveAmount>"
                )
                xml_string += (
                    '<cbc:TaxInclusiveAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + str(invoice_record.amount_total)
                    + "</cbc:TaxInclusiveAmount>"
                )
                xml_string += (
                    '<cbc:AllowanceTotalAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">0</cbc:AllowanceTotalAmount>'
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
                    + str(invoice_record.amount_total)
                    + "</cbc:PayableAmount>"
                )
                xml_string += "</cac:LegalMonetaryTotal>"

            # Satır bazlı işleme
            for line_index, line in enumerate(invoice_record.invoice_line_ids, start=1):
                line_quantity = line.quantity
                line_taxable_amount = line.price_subtotal
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
                    line_unit_code, str(line_quantity)
                )
                xml_string += '<cbc:LineExtensionAmount currencyID="{}">{}</cbc:LineExtensionAmount>'.format(
                    invoice_record.currency_id.name, str(line_taxable_amount)
                )

                if invoice_record.efatura_turu_id.code == "EIHRACAT":
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

                allowance_charge_reason = ""
                if fatura_tipi == "IHRACKAYITLI":
                    allowance_charge_reason = """
                    <cbc:AllowanceChargeReason/>
                    <cbc:MultiplierFactorNumeric>0</cbc:MultiplierFactorNumeric>
                    <cbc:SequenceNumeric>0</cbc:SequenceNumeric>
                    """

                # AllowanceCharge kısmı
                xml_string += """
                <cac:AllowanceCharge>
                    <cbc:ChargeIndicator>true</cbc:ChargeIndicator>
                    {allowance_charge_reason}
                    <cbc:Amount currencyID="{currency}">0</cbc:Amount>
                    <cbc:BaseAmount currencyID="{currency}">{taxable_amount}</cbc:BaseAmount>
                </cac:AllowanceCharge>
                """.format(
                    allowance_charge_reason=allowance_charge_reason,
                    currency=invoice_record.currency_id.name,
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
                xml_string += "<cbc:Name>" + line.name + "</cbc:Name>"
                xml_string += "<cac:SellersItemIdentification>"
                # # xml_string += '<cbc:ID>' + self.generate_cbc_id(fatura_seri_code,line.product_id.id) + '</cbc:ID>'
                xml_string += "<cbc:ID>" + str(line.product_id.id) + "</cbc:ID>"
                xml_string += "</cac:SellersItemIdentification>"
                xml_string += "</cac:Item>"
                xml_string += "<cac:Price>"
                xml_string += (
                    '<cbc:PriceAmount currencyID="'
                    + invoice_record.currency_id.name
                    + '">'
                    + str(line_rate)
                    + "</cbc:PriceAmount>"
                )
                xml_string += "</cac:Price>"
                xml_string += "</cac:InvoiceLine>"

            xml_string += "</Invoice>"

            invoice_record.write({"logging_field6": xml_string})
            return xml_string
