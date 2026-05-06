# -*- coding: utf-8 -*-
"""
entegra_order_import_wizard.py
──────────────────────────────
Manuel sipariş import wizard.
Cron beklemeden anlık import, filtreli import (pazaryeri, tarih).
"""

import logging
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class EntegraOrderImportWizard(models.TransientModel):
    _name = 'entegra.order.import.wizard'
    _description = 'Entegra Siparis Import Wizard'

    backend_id = fields.Many2one(
        'entegra.backend',
        string='Entegra Backend',
        required=True,
        domain=[('active', '=', True)],
    )
    supplier = fields.Selection(
        selection=[
            ('trendyol', 'Trendyol'),
            ('hb', 'Hepsiburada'),
            ('n11', 'N11'),
            ('amazon', 'Amazon'),
            ('gg', 'GittiGidiyor'),
            ('manual', 'Manuel'),
        ],
        string='Pazaryeri',
        help='Boş bırakılırsa tüm pazaryerlerinden import edilir.',
    )
    date_from = fields.Date(string='Baslangic Tarihi')
    import_all = fields.Boolean(
        string='api_sync Filtresini Atla',
        default=False,
        help='Normalde sadece api_sync=0 (cikilmamis) siparisler alinir. '
             'Bu secenek ile tum siparisler sorgulanir — dikkatli kullan.',
    )

    # Sonuc alanlari
    result_imported = fields.Integer(string='Import Edilen', readonly=True)
    result_skipped  = fields.Integer(string='Atlanan',       readonly=True)
    result_errors   = fields.Integer(string='Hata',          readonly=True)
    result_details  = fields.Text(string='Detaylar',         readonly=True)
    state = fields.Selection(
        [('draft', 'Hazir'), ('done', 'Tamamlandi')],
        default='draft',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        backend = self.env['entegra.backend'].search([('active', '=', True)], limit=1)
        if backend:
            res['backend_id'] = backend.id
        return res

    def action_import(self):
        self.ensure_one()

        if not self.backend_id:
            raise UserError('Backend secilmedi.')

        import_service = self.env['entegra.order.import']
        results = import_service.import_new_orders(
            self.backend_id,
            supplier=self.supplier or None,
            date_from=str(self.date_from) if self.date_from else None,
            skip_sync_filter=self.import_all,
        )

        details_lines = results.get('errors', [])

        self.write({
            'result_imported': results.get('imported', 0),
            'result_skipped':  results.get('skipped', 0),
            'result_errors':   len(results.get('errors', [])),
            'result_details':  '\n'.join(details_lines) if details_lines
                               else 'Islem basariyla tamamlandi.',
            'state': 'done',
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
