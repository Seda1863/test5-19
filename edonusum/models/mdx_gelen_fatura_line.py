# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from fractions import Fraction
import json

class MdxGelenFaturaLine(models.Model):
    _name = 'mdx.gelen.fatura.line'
    _description = 'Gelen Fatura Satırları'
    _order = 'line_id asc'

    # store=True alanlar
    gelen_fatura_id = fields.Many2one('mdx.gelen.fatura', string='Gelen Fatura', required=True, ondelete='cascade', store=True)
    istisna_kodu = fields.Many2one('mdx.sabit.kod', string='İstisna Kodu', domain=[('liste_tipi_id.code', '=', 'ISTISNA')], store=True, compute='_compute_sabit_kod', readonly=False)
    tevkifat_kodu = fields.Many2one('mdx.sabit.kod', string='Tevkifat Kodu', domain=[('liste_tipi_id.code', '=', 'TEVKIFAT')], store=True, readonly=False)
    ihrac_kayit_kodu = fields.Many2one('mdx.sabit.kod', string='İhraç Kayıt Kodu', domain=[('liste_tipi_id.code', '=', 'IHRACKAYITLI')], store=True, compute='_compute_sabit_kod', readonly=False)
    gtip_kodu = fields.Char(string='GTIP Kodu', readonly=False, compute='_compute_gtip_kodu', store=True)
    ozel_matrah_kodu = fields.Many2one('mdx.sabit.kod', string='Özel Matrah Kodu', domain=[('liste_tipi_id.code', '=', 'OZELMATRAH')], compute='_compute_sabit_kod', readonly=False, store=True) 
    invoice_line_id = fields.Many2one('account.move.line', string='Fatura Satırı', readonly=True, compute='_compute_invoice_line_id', store=True)
    ref_po_line_id = fields.Many2one('purchase.order.line', string='Referans Sipariş Satırı', readonly=True, compute='_compute_ref_po_line_id', store=True)
    create_product = fields.Boolean(string='Ürün Oluştur', readonly=True, compute='_compute_create_product', store=True)
    create_supplierinfo = fields.Boolean(string='Tedarikçi Bilgisi Oluştur', compute='_compute_create_supplierinfo', store=True)

    # store=True yapılacak alanlar
    match_record = fields.Boolean(string='Eşleştir', readonly=False, default=False, store=True)
    line_id = fields.Integer(string='Satır No', readonly=True, store=True)
    supplier_product_code = fields.Char(string='Tedarikçi Ürün Kodu', readonly=True, store=True)
    supplier_product_name = fields.Char(string='Tedarikçi Ürün Adı', readonly=True, store=True)
    product_id = fields.Many2one('product.product', string='Ürün', create=False, store=True)
    account_id = fields.Many2one('account.account', string='Hesap', create=False, store=True) 
    cancel_supplierinfo_creation = fields.Boolean(string='Tedarikçi Bilgisi Oluşturma İptal', default=False, store=True)
    quantity = fields.Float(string='Miktar', readonly=True, store=True)
    price_unit = fields.Float(string='Birim Fiyat', readonly=True, store=True)
    price_subtotal = fields.Float(string='Tutar', readonly=True, store=True)
    tax_name = fields.Char(string='Vergi Adı', readonly=True, store=True)
    tax_rate = fields.Float(string='Vergi Oranı', readonly=True, store=True)

    # computed alanlar
    supplierinfo_id = fields.Many2one('product.supplierinfo', string='Tedarikçi Bilgisi', readonly=True, compute='_compute_supplierinfo_id')
    tax_id = fields.Many2one('account.tax', string='Vergi', readonly=True, compute='_compute_tax_id')
       
    @api.depends('invoice_line_id.purchase_line_id')
    def _compute_ref_po_line_id(self):
        for record in self:
            if record.invoice_line_id.purchase_line_id:
                record.ref_po_line_id = record.invoice_line_id.purchase_line_id
            else:
                record.ref_po_line_id = False

    @api.depends('gelen_fatura_id.invoice_id')
    def _compute_invoice_line_id(self):
        for record in self:
            if record.gelen_fatura_id.invoice_id:
                invoice_line = record.gelen_fatura_id.invoice_id.invoice_line_ids.filtered(
                    lambda x: x.gelen_fatura_line_id == record
                )
                record.invoice_line_id = invoice_line[:1]  # İlk bulunan satır atanır
            else:
                record.invoice_line_id = False

    @api.depends('gelen_fatura_id.tax_exemption_reason_code_id')
    def _compute_sabit_kod(self):
        for record in self:
            sabit_kod_liste_tipi = record.gelen_fatura_id.tax_exemption_reason_code_id.liste_tipi_id.code

            if sabit_kod_liste_tipi == 'ISTISNA':
                record.istisna_kodu = record.gelen_fatura_id.tax_exemption_reason_code_id
            # elif sabit_kod_liste_tipi == 'TEVKIFAT':
            #     record.tevkifat_kodu = record.gelen_fatura_id.tax_exemption_reason_code_id.tevkifat_kodu
            elif sabit_kod_liste_tipi == 'IHRACKAYITLI':
                record.ihrac_kayit_kodu = record.gelen_fatura_id.tax_exemption_reason_code_id
            elif sabit_kod_liste_tipi == 'OZELMATRAH':
                record.ozel_matrah_kodu = record.gelen_fatura_id.tax_exemption_reason_code_id                

    @api.depends('product_id', 'product_id.hs_code', 'product_id.product_tmpl_id.hs_code')
    def _compute_gtip_kodu(self):
        for record in self:
            hs_code = record.product_id.product_tmpl_id.hs_code or record.product_id.hs_code
            record.gtip_kodu = hs_code or False

    @api.depends('tax_name', 'tax_rate', 'tevkifat_kodu', 'ihrac_kayit_kodu')
    def _compute_tax_id(self):
        for record in self:
            record.tax_id = False
            if record.tax_rate is not None and record.tax_name:
                record.gelen_fatura_id.logging_field1 = f"{int(record.tax_rate)}% {record.tax_name}"

                computed_tax_name = f"{int(record.tax_rate)}%"

                if record.ihrac_kayit_kodu:
                    computed_tax_name = f"EX RS -{int(record.tax_rate)}%"

                    tax = self.env['account.tax'].search([
                        ('type_tax_use', '!=', 'sale'),
                        ('name', '=', computed_tax_name),
                    ], limit=1)

                elif record.tevkifat_kodu:
                    numerator = int(record.tevkifat_kodu.tevkifat_orani * 10)
                    denominator = 10
                    formatted_fraction = f"{numerator}/{denominator}"
                    
                    computed_tax_name = f"WH {int(record.tax_rate)}% ({formatted_fraction})"

                    tax = self.env['account.tax'].search([
                        ('type_tax_use', '=', 'purchase'),
                        ('name', '=', computed_tax_name),
                    ], limit=1)

                else:
                    tax = self.env['account.tax'].search([
                        ('type_tax_use', '=', 'purchase'),
                        ('amount', '=', float(record.tax_rate)),
                        ('name', '=', computed_tax_name),
                        '|',
                        ('tax_group_id.name', 'ilike', "KDV"),
                        ('tax_group_id.name', 'ilike', "VAT"),               
                    ], limit=1)

                self.gelen_fatura_id.logging_field2 = computed_tax_name

                if tax:
                    record.tax_id = tax.id
            else:
                record.tax_id = False

    @api.depends('product_id', 'supplier_product_name', 'supplier_product_code', 'gelen_fatura_id.supplier_id')
    def _compute_supplierinfo_id(self):
        for record in self:
            if record.product_id:
                existing_supplierinfo = self.env['product.supplierinfo'].search([
                    ('product_id', '=', record.product_id.id),
                    ('partner_id', '=', record.gelen_fatura_id.supplier_id.id),
                    ('product_name', '=', record.supplier_product_name),
                    ('product_code', '=', record.supplier_product_code),
                ], limit=1)
                
                if existing_supplierinfo:
                    record.supplierinfo_id = existing_supplierinfo.id
                    record.create_supplierinfo = False
                    existing_supplierinfo.write({
                        'price': record.price_unit,
                        'currency_id': record.gelen_fatura_id.odenecek_tutar_doviz_cinsi.id,
                        'min_qty': record.quantity,
                    })
                else:
                    record.supplierinfo_id = False
                    record.create_supplierinfo = True
            else:
                record.supplierinfo_id = False
                record.create_supplierinfo = True

    @api.onchange('match_record')
    def _onchange_match_record(self):
        product_id = self.product_id
        supplier_id = self.gelen_fatura_id.supplier_id
        supplier_product_name = self.supplier_product_name
        supplier_product_code = self.supplier_product_code
        account_id = self.account_id
        create_product = self.create_product
        create_supplierinfo = self.create_supplierinfo
        message = ""

        if self.match_record:
            if not supplier_id:
                self.match_record = False
                message = _("Satır: %s, Tedarikçi seçimi zorunludur!") % self.line_id
            
            if product_id:
                if not account_id:
                    if product_id.categ_id.property_account_expense_categ_id:
                        self.account_id = product_id.categ_id.property_account_expense_categ_id
                    else:
                        self.match_record = False
                        message = _("Satır: %s, Ürün için gider hesabı tanımlanmamıştır.") % self.line_id

                # if create_supplierinfo:
                #     message += "Satır: %s, Ürün fiyat listesine eklenecek.\nİptal etmek için yandaki kutucuğu işaretleyin.\n" % self.line_id
            else:

                if create_product:

                    # if account_id:
                        try:
                            # self.action_open_product_creation_wizard()
                            manually_created_product = self.env['product.product'].search([
                                ('manually_created_from_gelen_fatura_line_id', '=', self.id),
                            ], limit=1)
                            if manually_created_product:
                                product_id = manually_created_product
                        except Exception as e:
                            raise UserError(_("Ürün oluşturulurken hata oluştu: %s" % e))

                    # else:
                    #     message += "Ürün oluşturulacak, ancak bir hesap seçmelisiniz.\n"

        if message:      
            return {
                'warning': {
                    'title': _("Bilgilendirme"),
                    'message': message
                }
            }

    def action_create_product(self):
        self.ensure_one()
        vals = {
            'manually_created_from_gelen_fatura_line_id': self.id,
            'name': self.supplier_product_name,
            'default_code': self.supplier_product_code,
            # 'type': 'consu',
            'purchase_ok': True,
            # 'property_account_expense_id': self.account_id.id,
        }

        # account_id yoksa hata ver
        # if not self.account_id:
        #     raise UserError(_("Ürün oluşturulması için bir hesap seçmelisiniz."))

        # else:
        product = self.env['product.product'].create(vals)

        self.product_id = product
        self.create_product = False 
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.product',
            'res_id': product.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.env.context.get('no_onchange'):
            return
        
        for record in self:
            if not record.product_id:
                record.with_context(no_onchange=True).update({
                    'create_product': True,
                    'create_supplierinfo': True,
                    'account_id': False,
                })
                return

            record.with_context(no_onchange=True).update({
                'create_product': False,
                'create_supplierinfo': False,
                'account_id': record.product_id.property_account_expense_id.id or record.product_id.categ_id.property_account_expense_categ_id.id,
            })

            product_id = record.product_id
            supplier_id = record.gelen_fatura_id.supplier_id
            supplier_product_name = record.supplier_product_name
            supplier_product_code = record.supplier_product_code

            message = ""

            if not record.product_id.property_account_expense_id:
                message = _("Satır: %s, Ürün için gider hesabı tanımlanmamıştır.") % record.line_id
            else:
                record.account_id = record.product_id.property_account_expense_id.id or record.product_id.categ_id.property_account_expense_categ_id.id

            record.create_product = False

            existing_supplierinfo = product_id.seller_ids.filtered(
                lambda x: x.partner_id == supplier_id
                and x.product_name == supplier_product_name
                and x.product_code == supplier_product_code
            )
            record.create_supplierinfo = not existing_supplierinfo

        if message:
            return {
                'warning': {
                    'title': _("Uyarı!"),
                    'message': message
                }
            }
                    
    @api.constrains('product_id', 'account_id')
    def _check_line_mappings(self):
        for line in self:
            if line.gelen_fatura_id.controlled:
                if not line.product_id and not line.create_product:
                    raise ValidationError(_("Ürün seçilmediğinde, ya 'Hizmet Kartı' seçilmeli ya da 'Ürün Oluştur' işaretlenmelidir!"))
                
                if line.create_product and not line.account_id:
                    raise ValidationError(_("'Ürün Oluştur' seçildiğinde, gider hesabı zorunludur!"))

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(vals_list)

    def write(self, vals):
        for record in self:
            if record.gelen_fatura_id.invoice_created:
                editable_fields = {'product_id', 'account_id'}
                if any(field in vals for field in editable_fields):
                    raise UserError(_("Fatura oluşturulduktan sonra bu alanlar değiştirilemez!"))
        return super().write(vals)
    
    @api.depends('product_id')
    def _compute_create_product(self):
        for record in self:
            record.create_product = not record.product_id

    @api.depends('product_id', 'cancel_supplierinfo_creation')
    def _compute_create_supplierinfo(self):
        for record in self:
            if record.product_id:
                existing_supplierinfo = record.product_id.seller_ids.filtered(
                    lambda x: x.partner_id == record.gelen_fatura_id.supplier_id
                    and x.product_name == record.supplier_product_name
                    and x.product_code == record.supplier_product_code
                )

                if not record.cancel_supplierinfo_creation:
                    record.create_supplierinfo = not existing_supplierinfo
                else:
                    record.create_supplierinfo = False
            else:
                record.create_supplierinfo = False

    def action_view_mdx_gelen_fatura_line_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mdx.gelen.fatura.line',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }
