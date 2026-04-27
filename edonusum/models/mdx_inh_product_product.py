# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo import Command

class MdxProductProduct(models.Model):
    _inherit = 'product.product'

    manually_created_from_gelen_fatura_line_id = fields.Many2one(
        'mdx.gelen.fatura.line', 
        string='Fatura Satırı',
        help="Bu ürün, ilgili fatura satırından manuel olarak oluşturulduysa burası dolu olur.",
        store=True,
    )

    manually_created_from_gelen_irsaliye_line_id = fields.Many2one(
        'mdx.gelen.irsaliye.line', 
        string='İrsaliye Satırı',
        help="Bu ürün, ilgili irsaliye satırından manuel olarak oluşturulduysa burası dolu olur.",
        store=True,
    )

    @api.model
    def create(self, vals):
        product = super(MdxProductProduct, self).create(vals)
        if product.manually_created_from_gelen_fatura_line_id:
            # İlgili fatura satırını alalım
            fatura_line = product.manually_created_from_gelen_fatura_line_id
            # Fatura satırındaki ürün alanını güncelleyelim
            fatura_line.write({
                'product_id': product.id,
                'create_product': False,
                'create_supplierinfo': False,
                # 'create_service_card': False,
            })
            # Fatura satırının tedarikçi bilgisini fatura üzerinden alıyoruz
            supplier = fatura_line.gelen_fatura_id.supplier_id
            if supplier and fatura_line.create_supplierinfo:
                supplierinfo = self.env['product.supplierinfo'].create({
                    'partner_id': supplier.id,
                    'product_id': product.id,
                    'product_name': fatura_line.supplier_product_name,
                    'product_code': fatura_line.supplier_product_code,
                    'product_tmpl_id': product.product_tmpl_id.id,
                    'product_uom': fatura_line.product_id.uom_id.id,
                    'price': fatura_line.price_unit,
                    'currency_id': fatura_line.gelen_fatura_id.odenecek_tutar_doviz_cinsi.id,
                    'min_qty': fatura_line.quantity,
                    'delay': 0,
                    'sequence': 0,
                })
                # Fatura satırında supplierinfo varsa güncelleyelim (alan tanımınız varsa)
                if hasattr(fatura_line, 'supplierinfo_id'):
                    fatura_line.write({
                        'supplierinfo_id': supplierinfo.id,
                        'create_supplierinfo': False,
                    })

        elif product.manually_created_from_gelen_irsaliye_line_id:
            # İlgili irsaliye satırını alalım
            irsaliye_line = product.manually_created_from_gelen_irsaliye_line_id
            # irsaliye satırındaki ürün alanını güncelleyelim
            irsaliye_line.write({
                'product_id': product.id,
                'create_product': False,
                'create_supplierinfo': False,
                # 'create_service_card': False,
            })
            # irsaliye satırının tedarikçi bilgisini irsaliye üzerinden alıyoruz
            supplier = irsaliye_line.gelen_irsaliye_id.supplier_id
            if supplier and fatura_line.create_supplierinfo:
                supplierinfo = self.env['product.supplierinfo'].create({
                    'partner_id': supplier.id,
                    'product_id': product.id,
                    'product_name': irsaliye_line.supplier_product_name,
                    'product_code': irsaliye_line.supplier_product_code,
                    'product_tmpl_id': product.product_tmpl_id.id,
                    'product_uom': irsaliye_line.product_id.uom_id.id,
                    # 'price': irsaliye_line.price_unit,
                    # 'currency_id': irsaliye_line.gelen_irsaliye_id.odenecek_tutar_doviz_cinsi.id,
                    'min_qty': irsaliye_line.quantity,
                    'delay': 0,
                    'sequence': 0,
                })
                # irsaliye satırında supplierinfo varsa güncelleyelim (alan tanımınız varsa)
                if hasattr(irsaliye_line, 'supplierinfo_id'):
                    irsaliye_line.write({
                        'supplierinfo_id': supplierinfo.id,
                        'create_supplierinfo': False,
                    })

        return product
    
    @api.ondelete(at_uninstall=True)
    def _unlink_except_manually_created(self):
        for product in self:
            if product.manually_created_from_gelen_fatura_line_id:
                product.manually_created_from_gelen_fatura_line_id.write({
                    'product_id': False,
                    'create_product': True,
                    'create_supplierinfo': True,
                })
            elif product.manually_created_from_gelen_irsaliye_line_id:
                product.manually_created_from_gelen_irsaliye_line_id.write({
                    'product_id': False,
                    'create_product': True,
                    'create_supplierinfo': True,
                })

class MdxInhProductTemplate(models.Model):
    _inherit = 'product.template'

    work_type_id = fields.Many2one(
        'mdx.work.type',
        string='İş Türü',
        help="Bu ürünün ait olduğu iş türü.",
        store=True,
    )

    # Ürün kartındaki istisna kodu - fatura satırında bu ürün seçildiğinde otomatik gelir
    istisna_kodu = fields.Many2one(
        'mdx.sabit.kod',
        string='İstisna Kodu',
        domain=[('liste_tipi_id.code', '=', 'ISTISNA')],
        store=True,
        help="Bu ürünün istisna kodu. Fatura satırında bu ürün seçildiğinde bu kod otomatik gelir ve vergiler %0 olur.",
    )

    @api.onchange('seller_ids')
    def _onchange_seller_ids_istisna(self):
        """
        Tedarikçilerden birinin istisna kodu varsa ürünün istisna kodunu ve satış vergilerini güncelle.
        """
        for record in self:
            if not record.istisna_kodu:
                for supplierinfo in record.seller_ids:
                    if supplierinfo.partner_id and hasattr(supplierinfo.partner_id, 'istisna_kodu') and supplierinfo.partner_id.istisna_kodu:
                        record.istisna_kodu = supplierinfo.partner_id.istisna_kodu.id
                        break
            # İstisna kodu varsa satış vergilerini %0 yap
            if record.istisna_kodu:
                record._set_zero_sale_taxes_for_istisna()

    def _set_zero_sale_taxes_for_istisna(self):
        """
        Ürünün istisna kodu varsa satış vergilerini (taxes_id) %0 KDV olarak ayarla.
        """
        for record in self:
            if not record.istisna_kodu:
                continue
            company = self.env.company
            zero_tax = self.env['account.tax'].search([
                ('type_tax_use', '=', 'sale'),
                ('amount', '=', 0.0),
                ('company_id', 'in', [company.id, False]),
                '|',
                ('tax_group_id.name', 'ilike', 'KDV'),
                ('tax_group_id.name', 'ilike', 'VAT'),
            ], limit=1)
            if not zero_tax:
                zero_tax = self.env['account.tax'].search([
                    ('type_tax_use', '=', 'sale'),
                    ('amount', '=', 0.0),
                    ('company_id', 'in', [company.id, False]),
                ], limit=1)
            if zero_tax:
                record.taxes_id = [Command.set([zero_tax.id])]
