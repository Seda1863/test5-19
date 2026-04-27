# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MdxPreValidationMixin(models.AbstractModel):
    _name = 'mdx.pre.validation.mixin'
    _description = 'E-Fatura Ön Doğrulama Mixin'

    def validate_invoice_before_send(self, invoice):
        """
        Fatura gönderilmeden önce tüm ön doğrulama kontrollerini çalıştırır.
        :param invoice: account.move kaydı
        :return: list of dict [{code, message, field, severity}]
        """
        errors = []
        errors.extend(self._validate_company_info(invoice))
        errors.extend(self._validate_partner_info(invoice))
        errors.extend(self._validate_line_items(invoice))
        errors.extend(self._validate_tax_info(invoice))
        errors.extend(self._validate_series(invoice))
        errors.extend(self._validate_document_type_specific(invoice))
        return errors

    # ==================== SATICI (ŞİRKET) DOĞRULAMALARI ====================
    def _validate_company_info(self, invoice):
        """EF0093-EF0097: Satıcı bilgileri doğrulama"""
        errors = []
        company = invoice.company_id

        if not company.vat:
            errors.append({
                'code': 'EF0093',
                'message': 'Şirket VKN/TCKN bilgisi eksik.',
                'field': 'company_id.vat',
            })

        if not company.street:
            errors.append({
                'code': 'EF0094',
                'message': 'Şirket adres bilgisi eksik.',
                'field': 'company_id.street',
            })

        if not company.country_id:
            errors.append({
                'code': 'EF0095',
                'message': 'Şirket ülke bilgisi eksik.',
                'field': 'company_id.country_id',
            })

        if not company.city:
            errors.append({
                'code': 'EF0096',
                'message': 'Şirket şehir bilgisi eksik.',
                'field': 'company_id.city',
            })

        return errors

    # ==================== ALICI (MÜŞTERİ) DOĞRULAMALARI ====================
    def _validate_partner_info(self, invoice):
        """EF0089-EF0092, EF0119-EF0122: Alıcı bilgileri doğrulama"""
        errors = []
        partner = invoice.partner_id.commercial_partner_id

        # VKN/TCKN kontrolü
        vat = partner.vat
        if not vat:
            errors.append({
                'code': 'EF0089',
                'message': '%s için VKN/TCKN bilgisi eksik.' % partner.name,
                'field': 'partner_id.vat',
            })

        # VKN uzunluğuna göre tip belirleme: 10 hane = VKN (tüzel), 11 hane = TCKN (gerçek)
        if vat:
            clean_vat = vat.strip()
            if len(clean_vat) == 11:
                # TCKN: ad/soyad olmalı
                if not partner.name:
                    errors.append({
                        'code': 'EF0122',
                        'message': 'TCKN tanımlı ise ad/soyad boş olamaz.',
                        'field': 'partner_id.name',
                    })
            elif len(clean_vat) == 10:
                # VKN: ünvan olmalı
                if not partner.name:
                    errors.append({
                        'code': 'EF0121',
                        'message': 'VKN tanımlı ise ünvan boş olamaz.',
                        'field': 'partner_id.name',
                    })

        # Adres kontrolleri
        if not partner.street and not partner.street2:
            errors.append({
                'code': 'EF0090',
                'message': '%s için adres bilgisi eksik.' % partner.name,
                'field': 'partner_id.street',
            })

        if not partner.city:
            errors.append({
                'code': 'EF0091',
                'message': '%s için şehir bilgisi eksik.' % partner.name,
                'field': 'partner_id.city',
            })

        return errors

    # ==================== FATURA SATIRLARI DOĞRULAMALARI ====================
    def _validate_line_items(self, invoice):
        """EF0099-EF0102, EF0129: Fatura satırları doğrulama"""
        errors = []

        lines = invoice.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
        if not lines:
            errors.append({
                'code': 'EF0129',
                'message': 'Faturada en az bir satır olmalıdır.',
                'field': 'invoice_line_ids',
            })
            return errors

        for idx, line in enumerate(lines, 1):
            if not line.name and not line.product_id:
                errors.append({
                    'code': 'EF0099',
                    'message': 'Satır %d: Ürün adı boş olamaz.' % idx,
                    'field': 'invoice_line_ids.name',
                })

            if not line.quantity:
                errors.append({
                    'code': 'EF0100',
                    'message': 'Satır %d: Miktar boş veya sıfır olamaz.' % idx,
                    'field': 'invoice_line_ids.quantity',
                })

            if not line.product_uom_id:
                errors.append({
                    'code': 'EF0101',
                    'message': 'Satır %d: Birim seçilmemiş.' % idx,
                    'field': 'invoice_line_ids.product_uom_id',
                })

            if line.price_unit < 0:
                errors.append({
                    'code': 'EF0102',
                    'message': 'Satır %d: Birim fiyat negatif olamaz.' % idx,
                    'field': 'invoice_line_ids.price_unit',
                })

        return errors

    # ==================== VERGİ DOĞRULAMALARI ====================
    def _validate_tax_info(self, invoice):
        """EF0128-EF0131, EF0150: Vergi bilgileri doğrulama"""
        errors = []

        lines = invoice.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
        for idx, line in enumerate(lines, 1):
            if not line.tax_ids:
                errors.append({
                    'code': 'EF0130',
                    'message': 'Satır %d: Vergi tanımlanmamış.' % idx,
                    'field': 'invoice_line_ids.tax_ids',
                })
                continue

            for tax in line.tax_ids:
                if tax.amount == 0 and not getattr(line, 'kdv_muafiyet_kodu', None):
                    errors.append({
                        'code': 'EF0150',
                        'message': 'Satır %d: %%0 KDV için muafiyet sebebi girilmelidir.' % idx,
                        'field': 'invoice_line_ids.kdv_muafiyet_kodu',
                    })

        return errors

    # ==================== SERİ DOĞRULAMALARI ====================
    def _validate_series(self, invoice):
        """EF0290: Fatura serisi doğrulama"""
        errors = []

        if not invoice.fatura_seri_id:
            errors.append({
                'code': 'EF0290',
                'message': 'Fatura serisi seçilmemiş.',
                'field': 'fatura_seri_id',
            })

        return errors

    # ==================== BELGE TİPİNE ÖZEL DOĞRULAMALAR ====================
    def _validate_document_type_specific(self, invoice):
        """Belge türüne göre özel doğrulamalar"""
        errors = []

        doc_type = getattr(invoice, 'efatura_turu_id', False)
        if not doc_type:
            return errors

        if doc_type.code == 'EIHRACAT':
            errors.extend(self._validate_export_invoice(invoice))

        if doc_type.code == 'EFATURA':
            errors.extend(self._validate_receiver_registration(invoice))

        return errors

    def _validate_export_invoice(self, invoice):
        """EF0311, EF0330: İhracat faturası doğrulamaları"""
        errors = []
        partner = invoice.partner_id.commercial_partner_id

        if partner.vat != '1460415308':
            errors.append({
                'code': 'EF0311',
                'message': 'İhracat faturasının alıcısı Gümrük ve Ticaret Bakanlığı olmalıdır.',
                'field': 'partner_id',
            })

        return errors

    def _validate_receiver_registration(self, invoice):
        """EF0028: Alıcı e-fatura mükellefi mi kontrolü"""
        errors = []
        partner = invoice.partner_id.commercial_partner_id

        if not partner.vat:
            return errors

        if hasattr(partner, 'efatura_musterisi') and not partner.efatura_musterisi:
            errors.append({
                'code': 'EF0028',
                'message': '%s e-fatura sistemine kayıtlı değil. E-Arşiv olarak gönderilebilir.' % partner.name,
                'field': 'partner_id',
                'severity': 'warning',
            })

        return errors

    # ==================== İRSALİYE DOĞRULAMALARI ====================
    def validate_picking_before_send(self, picking):
        """
        İrsaliye (stock.picking) gönderilmeden önce tüm ön doğrulama kontrollerini çalıştırır.
        :param picking: stock.picking kaydı
        :return: list of dict [{code, message, field, severity}]
        """
        errors = []
        errors.extend(self._validate_picking_company_info(picking))
        errors.extend(self._validate_picking_partner_info(picking))
        errors.extend(self._validate_picking_lines(picking))
        errors.extend(self._validate_picking_series(picking))
        errors.extend(self._validate_picking_transport_info(picking))
        errors.extend(self._validate_picking_scenario_specific(picking))
        return errors

    def _validate_picking_company_info(self, picking):
        """EI0001-EI0004: Gönderici (şirket) bilgileri doğrulama"""
        errors = []
        company = picking.company_id

        if not company.vat:
            errors.append({
                'code': 'EI0001',
                'message': 'Şirket VKN/TCKN bilgisi eksik.',
                'field': 'company_id.vat',
            })

        if not company.street:
            errors.append({
                'code': 'EI0002',
                'message': 'Şirket adres bilgisi eksik.',
                'field': 'company_id.street',
            })

        if not company.country_id:
            errors.append({
                'code': 'EI0003',
                'message': 'Şirket ülke bilgisi eksik.',
                'field': 'company_id.country_id',
            })

        if not company.city:
            errors.append({
                'code': 'EI0004',
                'message': 'Şirket şehir bilgisi eksik.',
                'field': 'company_id.city',
            })

        return errors

    def _validate_picking_partner_info(self, picking):
        """EI0010-EI0014: Alıcı bilgileri doğrulama"""
        errors = []
        partner = picking.partner_id

        if not partner:
            errors.append({
                'code': 'EI0010',
                'message': 'Teslimat adresi (alıcı) seçilmemiş.',
                'field': 'partner_id',
                'severity': 'critical',
            })
            return errors

        commercial = partner.commercial_partner_id

        if not commercial.vat:
            errors.append({
                'code': 'EI0011',
                'message': '%s için VKN/TCKN bilgisi eksik.' % commercial.name,
                'field': 'partner_id.vat',
            })

        if not commercial.street and not commercial.street2:
            errors.append({
                'code': 'EI0012',
                'message': '%s için adres bilgisi eksik.' % commercial.name,
                'field': 'partner_id.street',
            })

        if not commercial.city:
            errors.append({
                'code': 'EI0013',
                'message': '%s için şehir bilgisi eksik.' % commercial.name,
                'field': 'partner_id.city',
            })

        if not commercial.country_id:
            errors.append({
                'code': 'EI0014',
                'message': '%s için ülke bilgisi eksik.' % commercial.name,
                'field': 'partner_id.country_id',
            })

        return errors

    def _validate_picking_lines(self, picking):
        """EI0020-EI0023: İrsaliye satırları doğrulama"""
        errors = []

        lines = picking.move_ids.filtered(lambda m: m.state != 'cancel')
        if not lines:
            errors.append({
                'code': 'EI0020',
                'message': 'İrsaliyede en az bir aktif satır (stok hareketi) olmalıdır.',
                'field': 'move_ids',
                'severity': 'critical',
            })
            return errors

        for idx, line in enumerate(lines, 1):
            if not line.product_id:
                errors.append({
                    'code': 'EI0021',
                    'message': 'Satır %d: Ürün seçilmemiş.' % idx,
                    'field': 'move_ids.product_id',
                })

            if line.quantity <= 0:
                errors.append({
                    'code': 'EI0022',
                    'message': 'Satır %d (%s): Miktar sıfır veya negatif olamaz.' % (
                        idx, line.product_id.display_name or line.name or '?'),
                    'field': 'move_ids.quantity',
                })

            if not line.product_uom:
                errors.append({
                    'code': 'EI0023',
                    'message': 'Satır %d (%s): Birim seçilmemiş.' % (
                        idx, line.product_id.display_name or line.name or '?'),
                    'field': 'move_ids.product_uom',
                })

        return errors

    def _validate_picking_series(self, picking):
        """EI0030: İrsaliye seri doğrulama"""
        errors = []

        if not picking.irsaliye_seri_id:
            errors.append({
                'code': 'EI0030',
                'message': 'İrsaliye serisi seçilmemiş.',
                'field': 'irsaliye_seri_id',
                'severity': 'critical',
            })

        return errors

    def _validate_picking_transport_info(self, picking):
        """EI0040-EI0045: Nakliye/taşıma bilgileri doğrulama"""
        errors = []

        has_carrier = bool(picking.nakliye_sirketi_id)
        has_driver = bool(picking.sofor_adi and picking.sofor_soyadi)

        if not has_carrier and not has_driver:
            errors.append({
                'code': 'EI0040',
                'message': 'Nakliye şirketi seçin veya şoför bilgilerini (ad, soyad) doldurun.',
                'field': 'nakliye_sirketi_id',
                'severity': 'warning',
            })

        if has_carrier:
            carrier = picking.nakliye_sirketi_id
            if not carrier.vat:
                errors.append({
                    'code': 'EI0041',
                    'message': 'Nakliye şirketi (%s) VKN bilgisi eksik.' % carrier.name,
                    'field': 'nakliye_sirketi_id.vat',
                })

        if has_driver and not has_carrier:
            if not picking.sofor_tc_no:
                errors.append({
                    'code': 'EI0043',
                    'message': 'Şoför TC kimlik numarası eksik.',
                    'field': 'sofor_tc_no',
                    'severity': 'warning',
                })

        return errors

    def _validate_picking_scenario_specific(self, picking):
        """EI0050-EI0060: Senaryo bazlı doğrulamalar"""
        errors = []

        senaryo = picking.eirsaliye_senaryo_id
        tipi = picking.irsaliye_tipi_id
        if not senaryo:
            return errors

        senaryo_code = senaryo.code

        # ProfileID ↔ TypeCode matris kontrolü
        from . import mdx_inh_stock_picking
        valid_types = mdx_inh_stock_picking.VALID_DESPATCH_PROFILE_TYPE_MATRIX.get(senaryo_code, [])
        if tipi and valid_types and tipi.code not in valid_types:
            errors.append({
                'code': 'EI0050',
                'message': "'%s' senaryosu ile '%s' irsaliye tipi birlikte kullanılamaz. Geçerli: %s" % (
                    senaryo_code, tipi.code, ', '.join(valid_types)),
                'field': 'irsaliye_tipi_id',
            })

        # MATBUDAN: matbu belge alanları zorunlu
        if tipi and tipi.code == 'MATBUDAN':
            if not picking.matbuu_belge_no:
                errors.append({
                    'code': 'EI0051',
                    'message': "MATBUDAN tipinde 'Matbu Belge No' zorunludur.",
                    'field': 'matbuu_belge_no',
                })
            if not picking.matbuu_belge_tarihi:
                errors.append({
                    'code': 'EI0052',
                    'message': "MATBUDAN tipinde 'Matbu Belge Tarihi' zorunludur.",
                    'field': 'matbuu_belge_tarihi',
                })

        # IDISIRSALIYE: sevkiyat no + etiket no kontrolleri
        if senaryo_code == 'IDISIRSALIYE':
            import re
            if not picking.idis_sevkiyat_no:
                errors.append({
                    'code': 'EI0053',
                    'message': "IDISIRSALIYE senaryosunda 'İDİS Sevkiyat No' zorunludur.",
                    'field': 'idis_sevkiyat_no',
                })
            elif not re.match(r'^SE-\d{7}$', picking.idis_sevkiyat_no):
                errors.append({
                    'code': 'EI0054',
                    'message': "İDİS Sevkiyat No formatı geçersiz. Beklenen: SE-NNNNNNN (örn: SE-0000001)",
                    'field': 'idis_sevkiyat_no',
                })

            for line in picking.move_ids.filtered(lambda m: m.state != 'cancel'):
                if not getattr(line, 'idis_etiket_no', None):
                    errors.append({
                        'code': 'EI0055',
                        'message': "IDISIRSALIYE: '%s' satırı için İDİS Etiket No eksik." % (
                            line.product_id.display_name or line.name or '?'),
                        'field': 'move_ids.idis_etiket_no',
                    })

        # HKSIRSALIYE: künye no kontrolleri
        if senaryo_code == 'HKSIRSALIYE':
            for line in picking.move_ids.filtered(lambda m: m.state != 'cancel'):
                kunye = getattr(line, 'hks_kunye_no', None)
                if not kunye:
                    errors.append({
                        'code': 'EI0056',
                        'message': "HKSIRSALIYE: '%s' satırı için HKS Künye No eksik." % (
                            line.product_id.display_name or line.name or '?'),
                        'field': 'move_ids.hks_kunye_no',
                    })
                elif len(kunye) != 19:
                    errors.append({
                        'code': 'EI0057',
                        'message': "HKS Künye No 19 karakter olmalı. '%s' satırında %d karakter." % (
                            line.product_id.display_name or line.name or '?', len(kunye)),
                        'field': 'move_ids.hks_kunye_no',
                    })

        return errors

    # ==================== HATALARI GÖSTER ====================
    def display_validation_errors(self, errors):
        """
        Doğrulama hatalarını kullanıcı dostu formatta gösterir.
        Sadece uyarı varsa gönderime izin verir.
        :raises: UserError (kritik/normal hata varsa)
        :return: True (sadece uyarı varsa)
        """
        if not errors:
            return True

        critical_errors = [
            e for e in errors
            if e.get('severity') == 'critical'
            or (e.get('code', '').startswith('EF004'))
        ]
        normal_errors = [
            e for e in errors
            if e not in critical_errors and e.get('severity') != 'warning'
        ]
        warnings = [e for e in errors if e.get('severity') == 'warning']

        message_parts = []

        if critical_errors:
            message_parts.append("KRİTİK HATALAR:")
            for err in critical_errors:
                message_parts.append("  [%s] %s" % (err['code'], err['message']))

        if normal_errors:
            message_parts.append("\nHATALAR:")
            for err in normal_errors:
                message_parts.append("  [%s] %s" % (err['code'], err['message']))

        if warnings:
            message_parts.append("\nUYARILAR:")
            for warn in warnings:
                message_parts.append("  [%s] %s" % (warn['code'], warn['message']))

        final_message = "\n".join(message_parts)

        # Sadece uyarı varsa gönderime izin ver
        if not critical_errors and not normal_errors:
            return True

        raise UserError(final_message)
