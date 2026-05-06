# -*- coding: utf-8 -*-
"""
entegra_push_wizard.py
Manuel urun push wizard.
"""

import logging
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class EntergraPushWizard(models.TransientModel):
    _name = 'entegra.push.wizard'
    _description = 'Entegra Urun Push Wizard'

    product_ids = fields.Many2many(
        'product.template',
        string='Urunler',
        required=True,
    )
    backend_id = fields.Many2one(
        'entegra.backend',
        string='Entegra Backend',
        required=True,
        domain=[('active', '=', True)],
    )
    force_update = fields.Boolean(
        string='Zorla Guncelle',
        default=False,
        help='Zaten senkronize urunleri de yeniden gonder.',
    )
    push_images = fields.Boolean(
        string='Resimleri Gonder',
        default=True,
    )
    result_success = fields.Integer(string='Basarili', readonly=True)
    result_error = fields.Integer(string='Hata', readonly=True)
    result_details = fields.Text(string='Detaylar', readonly=True)
    state = fields.Selection(
        [('draft', 'Hazir'), ('done', 'Tamamlandi')],
        default='draft',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids', [])
        active_model = self.env.context.get('active_model', '')
        if active_ids and active_model == 'product.template':
            res['product_ids'] = [(6, 0, active_ids)]
        backends = self.env['entegra.backend'].search([('active', '=', True)], limit=1)
        if backends:
            res['backend_id'] = backends.id
        return res

    def action_push(self):
        self.ensure_one()
        if not self.product_ids:
            raise UserError('Gonderilecek urun secilmedi.')
        if not self.backend_id:
            raise UserError('Backend secilmedi.')

        push_service = self.env['entegra.product.push']
        results = push_service.push_products(
            self.backend_id,
            self.product_ids,
            force_update=self.force_update,
        )

        success_count = len(results['success'])
        error_count = len(results['error'])
        details_lines = [
            "HATA -- %s: %s" % (e['name'], e['error'])
            for e in results['error']
        ]

        self.write({
            'result_success': success_count,
            'result_error': error_count,
            'result_details': '\n'.join(details_lines) if details_lines else 'Tum urunler basariyla gonderildi.',
            'state': 'done',
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_push_stock_only(self):
        self.ensure_one()
        self.env['entegra.product.push'].push_stock(self.backend_id, self.product_ids)
        return {'type': 'ir.actions.act_window_close'}

    def action_push_prices_only(self):
        self.ensure_one()
        self.env['entegra.product.push'].push_prices(self.backend_id, self.product_ids)
        return {'type': 'ir.actions.act_window_close'}
