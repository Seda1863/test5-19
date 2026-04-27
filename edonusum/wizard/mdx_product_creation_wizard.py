from odoo import models, api

class MdxProductCreationWizard(models.TransientModel):
    _name = 'mdx.product.creation.wizard'
    _description = 'Ürün Oluşturma Sihirbazı'

    def action_confirm(self):
        self.ensure_one()
        active_id = self.env.context.get('active_id')
        fatura_line = self.env['mdx.gelen.fatura.line'].browse(active_id)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.product',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_manually_created_from_gelen_fatura_line_id': fatura_line.id,
                'default_name': fatura_line.supplier_product_name,
                'default_default_code': fatura_line.supplier_product_code,
                'default_type': 'consu',
                'default_purchase_ok': True,
                'default_property_account_expense_id': fatura_line.account_id.id,
            },
        }
