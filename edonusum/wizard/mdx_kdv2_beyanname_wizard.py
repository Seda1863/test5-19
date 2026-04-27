# -*- coding: utf-8 -*-

import base64
import calendar
from lxml import etree

from odoo import models, fields, api, _
from odoo.exceptions import UserError

import logging
import re

_logger = logging.getLogger(__name__)


class MdxKdv2BeyannameWizard(models.TransientModel):
    _name = 'mdx.kdv2.beyanname.wizard'
    _description = 'KDV2 Beyanname Wizard'

    @staticmethod
    def _clean_number(value):
        """Sadece rakamları alır, diğer karakterleri temizler"""
        if not value:
            return ''
        return re.sub(r'[^0-9]', '', str(value))

    @staticmethod
    def _clean_vat(vat, length=10):
        """Vergi numarasını temizler: TR prefix'i kaldırır, sadece rakam bırakır, belirtilen uzunluğa tamamlar"""
        if not vat:
            return ''
        # TR prefix'ini kaldır
        cleaned = re.sub(r'^TR', '', str(vat).upper())
        # Sadece rakamları al
        cleaned = re.sub(r'[^0-9]', '', cleaned)
        # Belirtilen uzunluğa sol taraftan 0 ile tamamla
        if cleaned and len(cleaned) < length:
            cleaned = cleaned.zfill(length)
        return cleaned

    @staticmethod
    def _clean_tc_kimlik(tc_no):
        """TC Kimlik numarasını temizler: 11 haneye tamamlar"""
        if not tc_no:
            return ''
        cleaned = re.sub(r'[^0-9]', '', str(tc_no))
        if cleaned and len(cleaned) < 11:
            cleaned = cleaned.zfill(11)
        return cleaned

    company_id = fields.Many2one('res.company', string='Şirket', default=lambda self: self.env.company, required=True)
    yil = fields.Selection(
        selection=[(str(y), str(y)) for y in range(2020, 2035)],
        string='Yıl', required=True,
        default=lambda self: str(fields.Date.context_today(self).year)
    )
    ay = fields.Selection([
        ('01', 'Ocak'), ('02', 'Şubat'), ('03', 'Mart'),
        ('04', 'Nisan'), ('05', 'Mayıs'), ('06', 'Haziran'),
        ('07', 'Temmuz'), ('08', 'Ağustos'), ('09', 'Eylül'),
        ('10', 'Ekim'), ('11', 'Kasım'), ('12', 'Aralık'),
    ], string='Ay', required=True,
        default=lambda self: str(fields.Date.context_today(self).month).zfill(2)
    )

    line_ids = fields.One2many('mdx.kdv2.beyanname.line', 'wizard_id', string='Rapor Satırları')
    xml_file = fields.Binary(string='XML Dosyası', readonly=True)
    xml_filename = fields.Char(string='XML Dosya Adı', readonly=True)

    def _get_date_range(self):
        """Seçilen dönem için tarih aralığını döndürür"""
        yil = int(self.yil)
        ay = int(self.ay)
        date_start = fields.Date.from_string(f'{yil}-{ay:02d}-01')
        last_day = calendar.monthrange(yil, ay)[1]
        date_end = fields.Date.from_string(f'{yil}-{ay:02d}-{last_day}')
        return date_start, date_end

    def _get_tevkifat_invoices(self):
        """Seçilen döneme ait tevkifatlı satınalma faturalarını getirir"""
        date_start, date_end = self._get_date_range()
        moves = self.env['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ("invoice_line_ids.tax_ids.name", "ilike", "wh"),  # Tevkifatlı vergi içeren faturalar
            ('invoice_date', '>=', date_start),
            ('invoice_date', '<=', date_end),
            ('company_id', '=', self.company_id.id),
        ])
        return moves

    def action_generate_report(self):
        """Rapor satırlarını oluşturur - tevkifat kodu ve müşteri bazında gruplama"""
        self.ensure_one()

        # Mevcut satırları temizle
        self.line_ids.unlink()

        moves = self._get_tevkifat_invoices()
        if not moves:
            raise UserError('Seçilen dönemde tevkifatlı satınalma faturası bulunamadı!')

        # Fatura satırlarını topla
        lines_data = []
        for move in moves:
            partner = move.partner_id
            # Parent partner varsa onu kullan (company vs contact)
            if partner.parent_id:
                partner = partner.parent_id

            for line in move.invoice_line_ids.filtered(lambda l: l.display_type == 'product' and l.tevkifat_kodu):
                tevkifat_kodu = line.tevkifat_kodu
                efinans_kod = tevkifat_kodu.efinans_kod

                # KDV oranı ve matrah hesaplama
                tax_amount = 0
                kdv_orani = 0
                
                # Grup vergileri (amount_type='group') ise alt satırlarındaki oranları almak için flatten kullanılır
                flat_taxes = line.tax_ids.flatten_taxes_hierarchy() if hasattr(line.tax_ids, 'flatten_taxes_hierarchy') else line.tax_ids
                for tax in flat_taxes:
                    if tax.tax_group_id and 'KDV' in (tax.tax_group_id.name or '').upper():
                        # KDV oranı ve tutar hesapla
                        if tax.amount > 0:
                            kdv_orani = abs(tax.amount)
                            tax_amount += abs(line.price_subtotal * tax.amount / 100)

                # Tevkifat oranı
                tevkifat_orani = tevkifat_kodu.tevkifat_orani or 0
                if tevkifat_orani > 0:
                    if tevkifat_orani <= 1.0:
                        tevkif_edilen_kdv = tax_amount * tevkifat_orani
                    else:
                        tevkif_edilen_kdv = tax_amount * (tevkifat_orani / 100)
                else:
                    tevkif_edilen_kdv = tax_amount

                lines_data.append({
                    'islem_turu': efinans_kod,
                    'partner_id': partner.id,
                    'soyadi': partner.name or '',
                    'adi': '',
                    'tc_kimlik_no': partner.l10n_tr_tax_office_number if hasattr(partner, 'l10n_tr_tax_office_number') else '',
                    'vergi_kimlik_no': partner.vat or '',
                    'matrah': abs(line.price_subtotal),
                    'kdv_orani': kdv_orani,
                    'tevkif_edilen_kdv': abs(tevkif_edilen_kdv),
                    'move_id': move.id,
                    'is_subtotal': False,
                })

        # Tevkifat kodu ve partner bazında sırala
        lines_data.sort(key=lambda x: (x['islem_turu'], x['partner_id']))

        # Satırları oluştur ve alt toplamlar ekle
        line_vals = []
        current_group_key = None
        group_matrah = 0
        group_tevkif = 0

        for data in lines_data:
            group_key = (data['islem_turu'], data['partner_id'])

            if current_group_key and current_group_key != group_key:
                # Önceki grubun alt toplamını ekle
                line_vals.append({
                    'wizard_id': self.id,
                    'islem_turu': '',
                    'soyadi': '',
                    'adi': '',
                    'tc_kimlik_no': '',
                    'vergi_kimlik_no': '',
                    'matrah': group_matrah,
                    'kdv_orani': 0,
                    'tevkif_edilen_kdv': group_tevkif,
                    'is_subtotal': True,
                })
                group_matrah = 0
                group_tevkif = 0

            current_group_key = group_key
            group_matrah += data['matrah']
            group_tevkif += data['tevkif_edilen_kdv']

            line_vals.append({
                'wizard_id': self.id,
                'islem_turu': data['islem_turu'],
                'partner_id': data['partner_id'],
                'soyadi': data['soyadi'],
                'adi': data['adi'],
                'tc_kimlik_no': data['tc_kimlik_no'],
                'vergi_kimlik_no': data['vergi_kimlik_no'],
                'matrah': data['matrah'],
                'kdv_orani': data['kdv_orani'],
                'tevkif_edilen_kdv': data['tevkif_edilen_kdv'],
                'is_subtotal': False,
            })

        # Son grubun alt toplamını ekle
        if current_group_key:
            line_vals.append({
                'wizard_id': self.id,
                'islem_turu': '',
                'soyadi': '',
                'adi': '',
                'tc_kimlik_no': '',
                'vergi_kimlik_no': '',
                'matrah': group_matrah,
                'kdv_orani': 0,
                'tevkif_edilen_kdv': group_tevkif,
                'is_subtotal': True,
            })

        self.env['mdx.kdv2.beyanname.line'].create(line_vals)

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mdx.kdv2.beyanname.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_generate_xml(self):
        """KDV2_16 şemasına uygun XML oluşturur"""
        self.ensure_one()
        company = self.company_id

        # Önce raporu oluştur
        if not self.line_ids:
            self.action_generate_report()

        # Ana XML elemanı
        xsi = 'http://www.w3.org/2001/XMLSchema-instance'
        root = etree.Element('beyanname', nsmap={'xsi': xsi})
        root.set('kodVer', 'KDV2_16')
        
        # xsi:noNamespaceSchemaLocation eklemek için özel QName kullanılıyor
        schemaLocation = etree.QName(xsi, 'noNamespaceSchemaLocation')
        root.set(schemaLocation, 'KDV2_16.xsd')

        # <genel> bölümü
        genel = etree.SubElement(root, 'genel')

        # <idari>
        idari = etree.SubElement(genel, 'idari')
        vd_kodu = etree.SubElement(idari, 'vdKodu')
        vd_kodu.text = company.beyanname_vd_kodu or ''

        donem = etree.SubElement(idari, 'donem')
        tip = etree.SubElement(donem, 'tip')
        # KDV2 beyannamesi her zaman aylık olmalıdır
        tip.text = 'aylik'
        yil_el = etree.SubElement(donem, 'yil')
        yil_el.text = self.yil
        ay_el = etree.SubElement(donem, 'ay')
        ay_el.text = self.ay

        # <mukellef>
        mukellef = etree.SubElement(genel, 'mukellef')
        self._add_text_element(mukellef, 'vergiNo', self._clean_vat(company.beyanname_vergi_no, 10))
        self._add_text_element(mukellef, 'tcKimlikNo', self._clean_tc_kimlik(company.beyanname_tc_kimlik_no))
        self._add_text_element(mukellef, 'soyadi', company.beyanname_soyadi or '')
        self._add_text_element(mukellef, 'adi', company.beyanname_adi or '')
        self._add_text_element(mukellef, 'ticSicilNo', self._clean_number(company.beyanname_ticaret_sicil_no))
        self._add_text_element(mukellef, 'eposta', company.beyanname_eposta or '')
        self._add_text_element(mukellef, 'alanKodu', self._clean_number(company.beyanname_alan_kodu))
        self._add_text_element(mukellef, 'telNo', self._clean_number(company.beyanname_tel_no))

        # <hsv>
        hsv = etree.SubElement(genel, 'hsv')
        hsv.set('sifat', company.beyanname_hsv_sifat or 'kendisi')
        self._add_text_element(hsv, 'vergiNo', self._clean_vat(company.beyanname_vergi_no, 10))
        self._add_text_element(hsv, 'soyadi', company.beyanname_soyadi or '')
        self._add_text_element(hsv, 'adi', company.beyanname_adi or '')
        self._add_text_element(hsv, 'eposta', company.beyanname_eposta or '')
        self._add_text_element(hsv, 'alanKodu', self._clean_number(company.beyanname_alan_kodu))
        self._add_text_element(hsv, 'telNo', self._clean_number(company.beyanname_tel_no))

        # <duzenleyen>
        duzenleyen = etree.SubElement(genel, 'duzenleyen')
        self._add_text_element(duzenleyen, 'vergiNo', self._clean_vat(company.beyanname_duzenleyen_vergi_no, 10))
        self._add_text_element(duzenleyen, 'soyadi', company.beyanname_duzenleyen_soyadi or '')
        self._add_text_element(duzenleyen, 'adi', company.beyanname_duzenleyen_adi or '')
        self._add_text_element(duzenleyen, 'tcKimlikNo', self._clean_tc_kimlik(company.beyanname_duzenleyen_tc_kimlik_no))
        self._add_text_element(duzenleyen, 'ticSicilNo', self._clean_number(company.beyanname_duzenleyen_ticaret_sicil_no))
        self._add_text_element(duzenleyen, 'eposta', company.beyanname_duzenleyen_eposta or '')
        self._add_text_element(duzenleyen, 'alanKodu', self._clean_number(company.beyanname_duzenleyen_alan_kodu))
        self._add_text_element(duzenleyen, 'telNo', self._clean_number(company.beyanname_duzenleyen_tel_no))

        # <ozel> bölümü
        ozel = etree.SubElement(root, 'ozel')

        # Rapor satırlarından alt toplamları al (tevkifatUygulananlar)
        detail_lines = self.line_ids.filtered(lambda l: not l.is_subtotal)
        subtotal_lines = self.line_ids.filtered(lambda l: l.is_subtotal)

        # tevkifatUygulananlar - islem_turu bazında matrah toplamları
        tevkifat_uygulananlar_data = {}
        for line in detail_lines:
            key = (line.islem_turu, line.kdv_orani)
            if key not in tevkifat_uygulananlar_data:
                tevkifat_uygulananlar_data[key] = {
                    'matrah': 0,
                    'vergi': 0,
                }
            tevkifat_uygulananlar_data[key]['matrah'] += line.matrah
            tevkifat_uygulananlar_data[key]['vergi'] += line.matrah  # vergiye tabi matrah

        if tevkifat_uygulananlar_data:
            tevkifat_uygulananlar = etree.SubElement(ozel, 'tevkifatUygulananlar')
            for (islem_turu, kdv_orani), data in tevkifat_uygulananlar_data.items():
                tevkifat_uygulanan = etree.SubElement(tevkifat_uygulananlar, 'tevkifatUygulanan')
                self._add_text_element(tevkifat_uygulanan, 'islemTuru', islem_turu)
                self._add_text_element(tevkifat_uygulanan, 'matrah', f'{data["matrah"]:.2f}')
                self._add_text_element(tevkifat_uygulanan, 'oran', str(int(kdv_orani)))
                # Tevkifat oranını sabit koddan al
                tevkifat_kod = self.env['mdx.sabit.kod'].search([
                    ('efinans_kod', '=', islem_turu),
                    ('liste_tipi_id.code', '=', 'TEVKIFAT'),
                ], limit=1)
                tevkifat_orani_val = tevkifat_kod.tevkifat_orani if tevkifat_kod else 0
                if tevkifat_orani_val:
                    # Oran formatı: 7/10, 9/10 vb.
                    if tevkifat_orani_val <= 1.0:
                        numerator = int(tevkifat_orani_val * 10)
                    else:
                        numerator = int(tevkifat_orani_val * 10 / 100)
                    self._add_text_element(tevkifat_uygulanan, 'tevkifatOrani', f'{numerator}/10')
                self._add_text_element(tevkifat_uygulanan, 'vergi', f'{data["vergi"]:.2f}')

        # kesintiler - her satır için kesinti kaydı
        # Partner ve islem_turu bazında grupla
        kesinti_data = {}
        for line in detail_lines:
            key = (line.islem_turu, line.partner_id.id if line.partner_id else 0)
            if key not in kesinti_data:
                kesinti_data[key] = {
                    'islem_turu': line.islem_turu,
                    'soyadi': line.soyadi,
                    'adi': line.adi,
                    'vergi_no': line.vergi_kimlik_no or '',
                    'tc_kimlik_no': line.tc_kimlik_no or '',
                    'matrah': 0,
                    'kdv_orani': line.kdv_orani,
                }
            kesinti_data[key]['matrah'] += line.matrah

        if kesinti_data:
            kesintiler = etree.SubElement(ozel, 'kesintiler')
            for key, data in kesinti_data.items():
                kesinti = etree.SubElement(kesintiler, 'kesinti')
                self._add_text_element(kesinti, 'islemTuru', data['islem_turu'])
                self._add_text_element(kesinti, 'soyadi', data['soyadi'])
                self._add_text_element(kesinti, 'adi', data['adi'])
                # VKN veya TCKN - temizlenmiş format
                if data['vergi_no']:
                    self._add_text_element(kesinti, 'vergiNo', self._clean_vat(data['vergi_no'], 10))
                elif data['tc_kimlik_no']:
                    self._add_text_element(kesinti, 'tcKimlikNo', self._clean_tc_kimlik(data['tc_kimlik_no']))
                self._add_text_element(kesinti, 'vergiyeTabiMatrah', f'{data["matrah"]:.2f}')
                self._add_text_element(kesinti, 'oran', str(int(data['kdv_orani'])))
                self._add_text_element(kesinti, 'odemeTuru', '102')

        # XML string oluştur
        xml_string = etree.tostring(root, pretty_print=True, xml_declaration=True, encoding='UTF-8')

        # Dosya adını oluştur: [vdKodu]_[vergiNo]_KDV2_16_[010525]_[310525].XML
        vd_kodu_str = company.beyanname_vd_kodu or ""
        vergi_no_str = company.beyanname_vergi_no or ""
        date_start, date_end = self._get_date_range()
        start_date_str = date_start.strftime('%d%m%y')
        end_date_str = date_end.strftime('%d%m%y')
        filename = f'{vd_kodu_str}_{vergi_no_str}_KDV2_16_{start_date_str}_{end_date_str}.XML'

        self.write({
            'xml_file': base64.b64encode(xml_string),
            'xml_filename': filename,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mdx.kdv2.beyanname.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _add_text_element(self, parent, tag, text):
        """XML elemanına metin ekler"""
        el = etree.SubElement(parent, tag)
        el.text = text or ''
        return el


class MdxKdv2BeyannameLineWizard(models.TransientModel):
    _name = 'mdx.kdv2.beyanname.line'
    _description = 'KDV2 Beyanname Rapor Satırı'

    wizard_id = fields.Many2one('mdx.kdv2.beyanname.wizard', string='Wizard', ondelete='cascade')
    islem_turu = fields.Char(string='İşlem Türü')
    partner_id = fields.Many2one('res.partner', string='Partner')
    soyadi = fields.Char(string='Soyadı (Ünvan)')
    adi = fields.Char(string='Adı (Ünvan Devamı)')
    tc_kimlik_no = fields.Char(string='T.C. Kimlik Numarası')
    vergi_kimlik_no = fields.Char(string='Vergi Kimlik Numarası')
    yurt_disi_kimlik_no = fields.Char(string='Yurt Dışı Kimlik No')
    matrah = fields.Float(string='Vergiye Tabi Matrah', digits=(16, 2))
    kdv_orani = fields.Float(string='KDV Oranı', digits=(5, 2))
    tevkif_edilen_kdv = fields.Float(string='Tevkif Edilen KDV Tutarı', digits=(16, 2))
    is_subtotal = fields.Boolean(string='Alt Toplam', default=False)
