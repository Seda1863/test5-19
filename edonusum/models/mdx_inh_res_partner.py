# -*- coding: utf-8 -*-

import requests
import xml.etree.ElementTree as ET
import json
import logging
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class MdxInhResPartner(models.Model):
    _inherit = 'res.partner'

    # store=True alanlar
    manually_created_from_gelen_fatura_id = fields.Many2one(
        'mdx.gelen.fatura', string='Fatura', help="Bu partner, ilgili faturadan manuel olarak oluşturulduysa burası dolu olur.",
        store=True 
    )
    manually_created_from_gelen_irsaliye_id = fields.Many2one(
        'mdx.gelen.irsaliye', string='İrsaliye', help="Bu partner, ilgili irsaliyeden manuel olarak oluşturulduysa burası dolu olur.",
        store=True 
    )
    legal_name = fields.Char(string='Legal Ad', store=True)
    is_customer = fields.Boolean(string='Müşteri', default=False, store=True)
    is_supplier = fields.Boolean(string='Tedarikçi', default=False, store=True)
    is_carrier = fields.Boolean(string='Taşıyıcı', default=False, store=True)
    efatura_musterisi = fields.Boolean(string='E-Fatura Müşterisi', default=False, readonly=False, store=True)
    earsiv_musterisi = fields.Boolean(string='E-Arşiv Müşterisi', default=False, readonly=False, store=True)
    eirsaliye_musterisi = fields.Boolean(string='E-İrsaliye Müşterisi', default=False, readonly=False, store=True)
    ticari_sicil_no = fields.Char(string='Ticari Sicil No', store=True)
    mersis_no = fields.Char(string='MERSIS No', store=True)
    vergi_dairesi = fields.Char(string='Vergi Dairesi', store=True)
    ozel_not = fields.Text(string='Özel Not', store=True)

    # store=True yapılacak alanlar
    efatura_turu_id = fields.Many2one('mdx.ebelge.turu', string='E-Fatura Türü', domain=[('active', '=', True), ('belge_cinsi_id.code', '=', 'FATURA')], store=True)
    efatura_senaryo_id = fields.Many2one('mdx.ebelge.senaryo', string='E-Fatura Senaryo', domain="[('id', 'in', filtered_efatura_senaryo_ids)]", store=True)    
    fatura_tipi_id = fields.Many2one('mdx.ebelge.tipi', string='Fatura Tipi', domain=[('belge_cinsi_id.code', '=', 'FATURA'), ('active', '=', True)], store=True)
    fatura_alt_tipi_id = fields.Many2one('mdx.fatura.alt.tipi', string='Fatura Alt Tipi', domain=[('active', '=', True)], store=True)
    eirsaliye_turu_id = fields.Many2one('mdx.ebelge.turu', string='E-İrsaliye Türü', domain=[('active', '=', True), ('belge_cinsi_id.code', '=', 'IRSALIYE')], store=True)
    eirsaliye_senaryo_id = fields.Many2one('mdx.ebelge.senaryo', string='E-İrsaliye Senaryo', domain="[('id', 'in', filtered_eirsaliye_senaryo_ids)]", store=True)
    eirsaliye_tipi_id = fields.Many2one('mdx.ebelge.tipi', string='E-İrsaliye Tipi', domain=[('belge_cinsi_id.code', '=', 'IRSALIYE')], store=True)
    vergi_kodu = fields.Many2one('mdx.sabit.kod', string='Vergi Kodu', domain=[('liste_tipi_id.code', '=', 'VERGI')], store=True)
    tevkifat_kodu = fields.Many2one('mdx.sabit.kod', string='Tevkifat Kodu', domain=[('liste_tipi_id.code', '=', 'TEVKIFAT')], store=True)
    istisna_kodu = fields.Many2one('mdx.sabit.kod', string='İstisna Kodu', domain=[('liste_tipi_id.code', '=', 'ISTISNA')], store=True)
    ozel_matrah_kodu = fields.Many2one('mdx.sabit.kod', string='Özel Matrah Kodu', domain=[('liste_tipi_id.code', '=', 'OZELMATRAH')], store=True)
    ihrac_kayit_kodu = fields.Many2one('mdx.sabit.kod', string='İhraç Kayıt Kodu', domain=[('liste_tipi_id.code', '=', 'IHRACKAYITLI')], store=True)
    incoterm_id = fields.Many2one('mdx.sabit.kod', string='Incoterm', domain=[ ('liste_tipi_id.code', '=', 'INCOTERMS')], store=True)
    currency_id = fields.Many2one('res.currency', string='Para Birimi', readonly=False, store=True)
    active = fields.Boolean(string='Aktif', default=True, store=True)
    
    # computed alanlar
    filtered_efatura_senaryo_ids = fields.Many2many('mdx.ebelge.senaryo', compute='_compute_filtered_efatura_senaryo_ids')
    filtered_eirsaliye_senaryo_ids = fields.Many2many('mdx.ebelge.senaryo', compute='_compute_filtered_eirsaliye_senaryo_ids')
    efatura_senaryo_readonly = fields.Boolean(string="E-Fatura Senaryo Readonly", compute="_compute_readonly_fields")
    fatura_tipi_readonly = fields.Boolean(string="Fatura Tipi Readonly", compute="_compute_readonly_fields")

    # Logging alanları
    logging_field1 = fields.Text(string='LOG1', readonly=False)
    logging_field2 = fields.Text(string='LOG2', readonly=False)
    logging_field3 = fields.Text(string='LOG3', readonly=False)
    logging_field4 = fields.Text(string='LOG4', readonly=False)
    logging_field5 = fields.Text(string='LOG5', readonly=False)
    logging_field6 = fields.Text(string='LOG6', readonly=False)
    
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

    @api.onchange('eirsaliye_turu_id')
    def _compute_filtered_eirsaliye_senaryo_ids(self):
        for record in self:
            if record.eirsaliye_turu_id:
                record.filtered_eirsaliye_senaryo_ids = self.env['mdx.ebelge.senaryo'].search([
                    ('ebelge_turu_ids', 'in', record.eirsaliye_turu_id.id),
                    ('active', '=', True)
                ])
            else:
                record.filtered_eirsaliye_senaryo_ids = self.env['mdx.ebelge.senaryo'].search([
                                                                                              ('active', '=', True)])
                
    @api.model_create_multi
    def create(self, vals_list):
        # country_id eklenmemişse, Türkiye olarak ayarla
        # for vals in vals_list:
        #     if 'country_id' not in vals:
        #         country = self.env['res.country'].search([('code', '=', 'TR')], limit=1)
        #         if country:
        #             vals['country_id'] = country.id

        # Önce kayıtları oluştur
        records = super(MdxInhResPartner, self).create(vals_list)

        # Kayıtlar oluşturulduktan sonra VAT kontrolü yaparak e-fatura sorgulaması yap
        for record in records:
            if record.vat:  # Yeni oluşturulan kaydın VAT numarası varsa çalıştır
                record.efatura_mukellef_sorgulama()

            # Parent_id varsa ilgili partner kodlarını güncelle
            if record.parent_id:
                if record.parent_id.parent_id:
                    record._get_partner_codes(record.parent_id.parent_id, vals_list[0])
                else:
                    record._get_partner_codes(record.parent_id, vals_list[0])

            if record.manually_created_from_gelen_fatura_id:
                fatura_id = record.manually_created_from_gelen_fatura_id
                fatura_id.write({
                    'supplier_id': record.id,
                })

        return records

    def write(self, vals):
        # Eğer parent_id değişmişse, ilgili partner kodlarını vals'a ekle (recursive write yapmadan)
        if 'parent_id' in vals and vals.get('parent_id'):
            parent = self.env['res.partner'].browse(vals['parent_id'])
            if parent:
                if parent.parent_id:
                    vals = self._get_partner_codes(parent.parent_id, vals.copy())
                else:
                    vals = self._get_partner_codes(parent, vals.copy())

        res = super(MdxInhResPartner, self).write(vals)

        # Eğer VAT değişmişse e-fatura sorgulaması yap
        if 'vat' in vals:
            for record in self:
                try:
                    record.efatura_mukellef_sorgulama()
                except Exception:
                    _logger.exception("efatura_mukellef_sorgulama failed for partner %s on write", record.id)

        # Rol bazli gorunumde Gelen Fatura sorumlusunu, partnerdeki Alici (buyer_id) degisikliginde guncelle.
        if 'buyer_id' in vals and 'buyer_id' in self._fields:
            try:
                self.env['mdx.gelen.fatura']._sync_responsible_users_for_suppliers(self)
                self.env['mdx.gelen.fatura']._sync_responsible_users_for_vats(self.mapped('vat'))
                self.env['mdx.gelen.fatura']._sync_responsible_users_for_supplier_names(self.mapped('name'))
            except Exception:
                _logger.exception("gelen fatura responsible_user sync failed for partners %s", self.ids)

        return res
    
    def _get_partner_codes(self, partner, vals):
        if partner.parent_id:
            vals['efatura_musterisi'] = partner.parent_id.efatura_musterisi
            vals['earsiv_musterisi'] = partner.parent_id.earsiv_musterisi
            vals['eirsaliye_musterisi'] = partner.parent_id.eirsaliye_musterisi
            vals['ticari_sicil_no'] = partner.parent_id.ticari_sicil_no
            vals['mersis_no'] = partner.parent_id.mersis_no
            vals['vergi_dairesi'] = partner.parent_id.vergi_dairesi
            vals['vergi_kodu'] = partner.parent_id.vergi_kodu.id if partner.parent_id.vergi_kodu else False
            vals['incoterm_id'] = partner.parent_id.incoterm_id.id if partner.parent_id.incoterm_id else False
            vals['currency_id'] = partner.parent_id.currency_id.id if partner.parent_id.currency_id else False
            vals['efatura_turu_id'] = partner.parent_id.efatura_turu_id.id if partner.parent_id.efatura_turu_id else False
            vals['efatura_senaryo_id'] = partner.parent_id.efatura_senaryo_id.id if partner.parent_id.efatura_senaryo_id else False
            vals['fatura_tipi_id'] = partner.parent_id.fatura_tipi_id.id if partner.parent_id.fatura_tipi_id else False
            vals['fatura_alt_tipi_id'] = partner.parent_id.fatura_alt_tipi_id.id if partner.parent_id.fatura_alt_tipi_id else False
            # vals['eirsaliye_turu_id'] = partner.parent_id.eirsaliye_turu_id.id if partner.parent_id.eirsaliye_turu_id else False
            # vals['eirsaliye_senaryo_id'] = partner.parent_id.eirsaliye_senaryo_id.id if partner.parent_id.eirsaliye_senaryo_id else False
            # vals['eirsaliye_tipi_id'] = partner.parent_id.eirsaliye_tipi_id.id if partner.parent_id.eirsaliye_tipi_id else False
            # vals['ozel_not'] = partner.parent_id.ozel_not
            vals['istisna_kodu'] = partner.istisna_kodu.id if partner.istisna_kodu else False
            vals['tevkifat_kodu'] = partner.tevkifat_kodu.id if partner.tevkifat_kodu else False
            vals['ihrac_kayit_kodu'] = partner.ihrac_kayit_kodu.id if partner.ihrac_kayit_kodu else False
            vals['ozel_matrah_kodu'] = partner.ozel_matrah_kodu.id if partner.ozel_matrah_kodu else False
            vals['vergi_kodu'] = partner.vergi_kodu.id if partner.vergi_kodu else False

        return vals
    
    def efatura_mukellef_sorgulama(self, vat=None, **kwargs):
        """
        E-Fatura Üyelik Sorgulama SOAP İsteği
        """
        self.ensure_one()
        # if not self.vat:
        #     raise UserError("Vergi Numarası (VAT) boş olamaz!")
        # elif len(self.vat) != 10:
            # raise UserError("Vergi Numarası (VAT) 10 haneli olmalıdır!")

        webservice = self.env['mdx.web.service'].search([('name', '=', 'EFINANS_GONDERICI'), ('active', '=', True), ('company_id', '=', self.env.user.company_id.id)], limit=1)
        username = webservice.username
        password = webservice.password
        url = webservice.url

        # SOAP İsteği Gövdesi
        soap_request = f"""
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
                <ser:efaturaKullanicisi>
                    <vergiTcKimlikNo>{self.vat}</vergiTcKimlikNo>
                </ser:efaturaKullanicisi>
            </soapenv:Body>
        </soapenv:Envelope>
        """

        self.logging_field6 = soap_request
        
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": ""
        }

        try:
            response = requests.post(url, data=soap_request, headers=headers, timeout=10, verify=False)

            if response.status_code == 200:
                
                root = ET.fromstring(response.text)

                namespaces = {
                    'S': 'http://schemas.xmlsoap.org/soap/envelope/',
                    'ns2': 'http://service.connector.uut.cs.com.tr/'
                }

                return_element = root.find('.//ns2:efaturaKullanicisiResponse/return', namespaces)

                self.logging_field1 = response.text
                self.logging_field2 = return_element.text

                if return_element is not None:
                    return_value = return_element.text.strip().lower()

                    # self.logging_field2 = return_value

                    if return_value == "true":
                        self.efatura_musterisi = True
                        self.earsiv_musterisi = False

                        # E-Fatura Türü ve Senaryo alanlarını ayarla
                        self.efatura_turu_id = self.env['mdx.ebelge.turu'].search(
                            [('code', '=', 'EFATURA')], limit=1)
                        self.efatura_senaryo_id = self.env.user.company_id.efatura_senaryo_id.id

                        # return {
                        #     "type": "ir.actions.client",
                        #     "tag": "reload",
                        # }
                    elif return_value == "false":
                        self.efatura_musterisi = False
                        self.earsiv_musterisi = True

                        # E-Fatura Türü ve Senaryo alanlarını ayarla
                        self.efatura_turu_id = self.env['mdx.ebelge.turu'].search(
                            [('code', '=', 'EARSIV')], limit=1)
                        self.efatura_senaryo_id = self.env['mdx.ebelge.senaryo'].search(
                            [('code', '=', 'EARSIVFATURA')], limit=1).id

                        # return {
                        #     "type": "ir.actions.client",
                        #     "tag": "reload",
                        # }
                    else:
                        # raise UserError(
                        #     f"Beklenmeyen yanıt değeri: {return_value}")
                        self.logging_field3 = f"Beklenmeyen yanıt değeri: {return_value}"

                    if self.fatura_tipi_id.code != 'TEVKIFAT':
                        self.fatura_tipi_id = self.env['mdx.ebelge.tipi'].search(
                        [('code', '=', 'SATIS')], limit=1).id

                    # self.street2 = self.country_id.code
                    if self.country_id.code != 'TR':
                        if self.env.user.company_id.hizmet_sektoru == True:
                            self.efatura_musterisi = False
                            self.earsiv_musterisi = True
                            self.efatura_turu_id = self.env['mdx.ebelge.turu'].search([('code', '=', 'EARSIV')], limit=1)
                            self.efatura_senaryo_id = self.env['mdx.ebelge.senaryo'].search([('code', '=', 'EARSIVFATURA')], limit=1)
                            self.fatura_tipi_id = self.env['mdx.ebelge.tipi'].search([('code', '=', 'ISTISNA')], limit=1)
                            self.istisna_kodu = self.env['mdx.sabit.kod'].search([('efinans_kod', '=', '302')], limit=1)
                        else:    
                            if self.efatura_musterisi == True:
                                if self.efatura_turu_id.code == 'EFATURA':
                                    self.efatura_turu_id = self.env['mdx.ebelge.turu'].search([('code', '=', 'EIHRACAT')], limit=1)
                                self.efatura_senaryo_id = self.env['mdx.ebelge.senaryo'].search([('code', '=', 'IHRACAT')], limit=1)
                                self.fatura_tipi_id = self.env['mdx.ebelge.tipi'].search([('code', '=', 'ISTISNA')], limit=1)
                                self.istisna_kodu = self.env['mdx.sabit.kod'].search([('efinans_kod', '=', '301')], limit=1)
                    
                else:
                    self.logging_field4 = f"API yanıtı bulunamadı: {response.text}"
            else:
                self.logging_field5 = f"API yanıtı alınamadı: {response.status_code}"
        except Exception as e:
            self.logging_field6 = f"Hata: {e}"

    @api.onchange('efatura_turu_id')
    def _onchange_efatura_turu_id(self):
        if self.efatura_turu_id:
            if self.country_id.code != 'TR':
                if self.env.user.company_id.hizmet_sektoru == True:
                    self.efatura_turu_id = self.env['mdx.ebelge.turu'].search([('code', '=', 'EARSIV')], limit=1)
                    self.efatura_senaryo_id = self.env['mdx.ebelge.senaryo'].search([('code', '=', 'EARSIVFATURA')], limit=1)
                    self.fatura_tipi_id = self.env['mdx.ebelge.tipi'].search([('code', '=', 'ISTISNA')], limit=1)
                    self.istisna_kodu = self.env['mdx.sabit.kod'].search([('efinans_kod', '=', '302')], limit=1)
                else:    
                    if self.efatura_musterisi == True:
                        if self.efatura_turu_id.code == 'EFATURA':
                            self.efatura_turu_id = self.env['mdx.ebelge.turu'].search([('code', '=', 'EIHRACAT')], limit=1)
                        self.efatura_senaryo_id = self.env['mdx.ebelge.senaryo'].search([('code', '=', 'IHRACAT')], limit=1)
                        self.fatura_tipi_id = self.env['mdx.ebelge.tipi'].search([('code', '=', 'ISTISNA')], limit=1)
                        self.istisna_kodu = self.env['mdx.sabit.kod'].search([('efinans_kod', '=', '301')], limit=1)
                    else:
                        self.efatura_turu_id = self.env['mdx.ebelge.turu'].search([('code', '=', 'EARSIV')], limit=1)
                        self.efatura_senaryo_id = self.env['mdx.ebelge.senaryo'].search([('code', '=', 'EARSIVFATURA')], limit=1)
                        self.fatura_tipi_id = self.env['mdx.ebelge.tipi'].search([('code', '=', 'SATIS')], limit=1)
            else:
                if self.efatura_musterisi == True:
                    self.efatura_turu_id = self.env['mdx.ebelge.turu'].search([('code', '=', 'EFATURA')], limit=1)
                    self.efatura_senaryo_id = self.env.user.company_id.efatura_senaryo_id.id
                    self.fatura_tipi_id = self.env['mdx.ebelge.tipi'].search([('code', '=', 'SATIS')], limit=1)
                else:
                    self.efatura_turu_id = self.env['mdx.ebelge.turu'].search([('code', '=', 'EARSIV')], limit=1)
                    self.efatura_senaryo_id = self.env['mdx.ebelge.senaryo'].search([('code', '=', 'EARSIVFATURA')], limit=1)
                    self.fatura_tipi_id = self.env['mdx.ebelge.tipi'].search([('code', '=', 'SATIS')], limit=1)

    @api.constrains('fatura_tipi_id', 'tevkifat_kodu', 'istisna_kodu', 'ihrac_kayit_kodu', 'ozel_matrah_kodu')
    def _check_fatura_tipi_kodlari(self):
        for record in self:
            # Tevkifat kontrolü
            if record.fatura_tipi_id.code == 'TEVKIFAT' and not record.tevkifat_kodu:
                raise ValidationError(
                    "Tevkifat Kodu, Fatura Tipi 'TEVKIFAT' olduğunda zorunludur.")

            # İstisna kontrolü
            if record.fatura_tipi_id.code == 'ISTISNA' and not record.istisna_kodu:
                raise ValidationError(
                    "İstisna Kodu, Fatura Tipi 'ISTISNA' olduğunda zorunludur.")

            # İhraç Kayıtlı kontrolü
            if record.fatura_tipi_id.code == 'IHRACKAYITLI' and not record.ihrac_kayit_kodu:
                raise ValidationError(
                    "İhraç Kayıtlı Kodu, Fatura Tipi 'IHRACKAYITLI' olduğunda zorunludur.")
            
            # Özel Matrah kontrolü
            if record.fatura_tipi_id.code == 'OZELMATRAH' and not record.ozel_matrah_kodu:
                raise ValidationError(
                    "Özel Matrah Kodu, Fatura Tipi 'OZELMATRAH' olduğunda zorunludur.")

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
        if self.fatura_tipi_id:
            if self.fatura_tipi_id.code == 'IADE' or self.fatura_tipi_id.code == 'SGK':
                self.efatura_senaryo_id = self.env['mdx.ebelge.senaryo'].search(
                    [('code', '=', 'TEMELFATURA')], limit=1)
                
    def simple_vat_check(self, country_code, vat_number):
        # TR ülke kodu için özel kontrol
        if country_code == 'TR':
            if vat_number and len(vat_number) in [10, 11]:
                return True
            else:
                return False
        # Diğer ülkeler için orijinal metodu çağır
        return super(MdxInhResPartner, self).simple_vat_check(country_code, vat_number)
    
    @api.model
    def process_efatura_mukellef_sorgulama(self):
        for record in self:
            if record.vat:
                webservice = self.env['mdx.web.service'].search([('name', '=', 'EFINANS_GONDERICI'), ('active', '=', True), ('company_id', '=', self.env.user.company_id.id)], limit=1)
                username = str(webservice.username)
                password = str(webservice.password)
                url = str(webservice.url)

                record.efatura_mukellef_sorgulama(record=self.id, vat=record.vat, username=username, password=password, url=url)
                record.logging_field1 = f"SOAP isteği gönderildi. URL: {url}"

    @api.model
    def process_efatura_mukellef_sorgulama(self):
        """
        Tüm partner kayıtları için E-Fatura Mükellef Sorgulama işlemini gerçekleştirir.
        Bu metod, bir cron job tarafından çağrılmak üzere tasarlanmıştır.
        """
        partners = self.search([('vat', '!=', False)])  # VAT numarası olan tüm partnerleri al
        for partner in partners:
            try:
                partner.efatura_mukellef_sorgulama()  # Her partner için sorgulama yap
            except Exception as e:
                partner.logging_field6 = f"Hata: {e}"  # Hata durumunda log alanına yaz

    # DENEYSEL


