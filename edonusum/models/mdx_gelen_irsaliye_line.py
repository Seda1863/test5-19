# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from fractions import Fraction
import json

class MdxGelenIrsaliyeLine(models.Model):
    _name = 'mdx.gelen.irsaliye.line'
    _description = 'Gelen İrsaliye Satırları'
    _order = 'line_id asc'

    # store=True alanlar
    gelen_irsaliye_id = fields.Many2one('mdx.gelen.irsaliye', string='Gelen İrsaliye', required=True, ondelete='cascade', store=True)
    quantity = fields.Float(string='Miktar', readonly=True, store=True)
    received_qty = fields.Float(string='Teslim Alınan Miktar', readonly=True, compute='_compute_received_qty', store=True, default=lambda self: self.quantity)
    rejected_qty = fields.Float(string='Kabul Edilmeyen Miktar', store=True, default=0)
    short_qty = fields.Float(string='Eksik Miktar', store=True, default=0)
    oversupply_qty = fields.Float(string='Fazla Miktar', store=True, default=0)
    create_product = fields.Boolean(string='Ürün Oluştur', store=True, readonly=True, compute='_compute_create_product')
    create_supplierinfo = fields.Boolean(string='Tedarikçi Bilgisi Oluştur', store=True, compute='_compute_create_supplierinfo')
    reject_reason = fields.Text(string='Açıklama', store=True)
    waybill_line_id = fields.Many2one('stock.move.line', string='İrsaliye Satırı', readonly=True, compute='_compute_waybill_line_id', store=True)
    ref_po_line_id = fields.Many2one('purchase.order.line', string='Referans Sipariş Satırı', readonly=True, store=True)

    # store=True yapılacak alanlar
    match_record = fields.Boolean(string='Eşleştir', readonly=False, default=False, store=True)
    line_id = fields.Integer(string='Satır No', readonly=True, store=True)
    supplier_product_code = fields.Char(string='Tedarikçi Ürün Kodu', readonly=True, store=True)
    supplier_product_name = fields.Char(string='Tedarikçi Ürün Adı', readonly=True, store=True)
    supplierinfo_id = fields.Many2one('product.supplierinfo', string='Tedarikçi Bilgisi', readonly=True, compute='_compute_supplierinfo_id', store=True)
    product_id = fields.Many2one('product.product', string='Ürün', create=False, store=True)
    account_id = fields.Many2one('account.account', string='Hesap', create=False, store=True)
    cancel_supplierinfo_creation = fields.Boolean(string='Tedarikçi Bilgisi Oluşturma İptal', default=False, store=True)

    @api.depends('quantity', 'received_qty', 'rejected_qty', 'short_qty', 'oversupply_qty')
    def _compute_received_qty(self):
        for record in self:
            record.received_qty = record.quantity - record.short_qty + record.oversupply_qty - record.rejected_qty

    @api.depends('gelen_irsaliye_id.waybill_id')
    def _compute_waybill_line_id(self):
        for record in self:
            if record.gelen_irsaliye_id.waybill_id:
                waybill_line = record.gelen_irsaliye_id.waybill_id.move_line_ids.filtered(
                    lambda x: x.gelen_irsaliye_line_id == record
                )
                record.waybill_line_id = waybill_line[:1]  # İlk bulunan satır atanır
            else:
                record.waybill_line_id = False            

    @api.depends('product_id', 'supplier_product_name', 'supplier_product_code', 'gelen_irsaliye_id.supplier_id')
    def _compute_supplierinfo_id(self):
        for record in self:
            if record.product_id:
                existing_supplierinfo = self.env['product.supplierinfo'].search([
                    ('product_id', '=', record.product_id.id),
                    ('partner_id', '=', record.gelen_irsaliye_id.supplier_id.id),
                    ('product_name', '=', record.supplier_product_name),
                    ('product_code', '=', record.supplier_product_code),
                ], limit=1)
                
                if existing_supplierinfo:
                    record.supplierinfo_id = existing_supplierinfo.id
                    record.create_supplierinfo = False
                    # existing_supplierinfo.write({
                    #     'price': record.price_unit,
                    #     'currency_id': record.gelen_irsaliye_id.odenecek_tutar_doviz_cinsi.id,
                    #     'min_qty': record.quantity,
                    # })
                else:
                    record.supplierinfo_id = False
                    record.create_supplierinfo = True
            else:
                record.supplierinfo_id = False
                record.create_supplierinfo = True

    @api.onchange('match_record')
    def _onchange_match_record(self):
        product_id = self.product_id
        supplier_id = self.gelen_irsaliye_id.supplier_id
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

                if create_supplierinfo:
                    message += "Satır: %s, Ürün fiyat listesine eklenecek.\n" % self.line_id
            else:

                if create_product:

                    # if account_id:
                        try:
                            # self.action_open_product_creation_wizard()
                            manually_created_product = self.env['product.product'].search([
                                ('manually_created_from_gelen_irsaliye_line_id', '=', self.id),
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
            'manually_created_from_gelen_irsaliye_line_id': self.id,
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
            supplier_id = record.gelen_irsaliye_id.supplier_id
            supplier_product_name = record.supplier_product_name
            supplier_product_code = record.supplier_product_code

            message = ""

            if not record.product_id.property_account_expense_id:
                if not record.product_id.categ_id.property_account_expense_categ_id:
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
            if line.gelen_irsaliye_id.controlled:
                if not line.product_id and not line.create_product:
                    raise ValidationError(_("Ürün seçilmediğinde, ya 'Hizmet Kartı' seçilmeli ya da 'Ürün Oluştur' işaretlenmelidir!"))
                
                if line.create_product and not line.account_id:
                    raise ValidationError(_("'Ürün Oluştur' seçildiğinde, gider hesabı zorunludur!"))

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(vals_list)

    def write(self, vals):
        for record in self:
            if record.gelen_irsaliye_id.waybill_created:
                editable_fields = {'product_id', 'account_id'}
                if any(field in vals for field in editable_fields):
                    raise UserError(_("İrsaliye oluşturulduktan sonra bu alanlar değiştirilemez!"))
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
                    lambda x: x.partner_id == record.gelen_irsaliye_id.supplier_id
                    and x.product_name == record.supplier_product_name
                    and x.product_code == record.supplier_product_code
                )
                if not record.cancel_supplierinfo_creation:
                    record.create_supplierinfo = not existing_supplierinfo
                else:
                    record.create_supplierinfo = False
            else:
                record.create_supplierinfo = False

    def action_view_mdx_gelen_irsaliye_line_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mdx.gelen.irsaliye.line',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }