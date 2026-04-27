from odoo import models, api

class MdxServiceCreationWizard(models.TransientModel):
    _name = 'mdx.service.creation.wizard'
    _description = 'Hizmet Oluşturma Sihirbazı'

    def action_confirm(self):
        self.ensure_one()
        active_id = self.env.context.get('active_id')
        fatura_line = self.env['mdx.gelen.fatura.line'].browse(active_id)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mdx.gelen.eslestirme',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_manually_created_from_gelen_fatura_line_id': fatura_line.id,
                'default_supplier_service_name': fatura_line.supplier_product_name,
                'default_supplier_service_code': fatura_line.supplier_product_code,
                'default_account_id': fatura_line.account_id.id,
                # 'default_supplier_id': fatura_line.gelen_fatura_id.supplier_id.id,
                # 'default_first_matched_gelen_fatura_id': fatura_line.gelen_fatura_id.id,
                # 'default_last_matched_gelen_fatura_id': fatura_line.gelen_fatura_id.id,
                'default_first_matched_gelen_fatura_line_id': fatura_line.id,
                'default_last_matched_gelen_fatura_line_id': fatura_line.id,
            },
        }
