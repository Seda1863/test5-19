# -*- coding: utf-8 -*-
"""
product_template.py
───────────────────
product.template genişlemesi.

Entegra ile ilgili alanlar ve:
  - Manuel push butonu (action_push_to_entegra)
  - Stok/fiyat write hook'u (dirty flag ile)
  - Toplu push için class method
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # --- Entegra Alanlari -----------------------------------------
    entegra_mapping_ids = fields.One2many(
        'entegra.product.mapping',
        'product_tmpl_id',
        string='Entegra Eslemeleri',
    )
    entegra_exclude = fields.Boolean(
        string="Entegra'ya Gonderme",
        default=False,
        help='Bu urunu Entegra senkronizasyonundan haric tut.',
    )
    entegra_sync_status = fields.Selection(
        selection=[
            ('not_synced', 'Gonderilmedi'),
            ('synced',     'Senkronize'),
            ('error',      'Hata'),
            ('excluded',   'Haric'),
        ],
        string='Entegra Durumu',
        compute='_compute_entegra_sync_status',
        store=False,
    )
    entegra_last_sync = fields.Datetime(
        string='Son Entegra Sync',
        compute='_compute_entegra_sync_status',
        store=False,
    )

    # --- Computed --------------------------------------------------
    @api.depends('entegra_mapping_ids', 'entegra_mapping_ids.sync_status')
    def _compute_entegra_sync_status(self):
        for tmpl in self:
            if tmpl.entegra_exclude:
                tmpl.entegra_sync_status = 'excluded'
                tmpl.entegra_last_sync = False
                continue

            mappings = tmpl.entegra_mapping_ids.filtered(lambda m: not m.product_id)
            if not mappings:
                tmpl.entegra_sync_status = 'not_synced'
                tmpl.entegra_last_sync = False
            elif any(m.sync_status == 'error' for m in mappings):
                tmpl.entegra_sync_status = 'error'
                tmpl.entegra_last_sync = max(
                    (m.last_sync_date for m in mappings if m.last_sync_date),
                    default=False
                )
            elif all(m.sync_status == 'synced' for m in mappings):
                tmpl.entegra_sync_status = 'synced'
                tmpl.entegra_last_sync = max(
                    (m.last_sync_date for m in mappings if m.last_sync_date),
                    default=False
                )
            else:
                tmpl.entegra_sync_status = 'not_synced'
                tmpl.entegra_last_sync = False

    # --- Buton Aksiyonlari ----------------------------------------
    def action_push_to_entegra(self):
        """
        Urunu secili backend'e gonderir.
        Birden fazla backend varsa secim wizard'i acar.
        """
        self.ensure_one()

        if not self.default_code:
            raise UserError(
                "Entegra'ya gondermek icin once 'Ic Referans' alanini doldurun."
            )

        backends = self.env['entegra.backend'].search([('active', '=', True)])

        if not backends:
            raise UserError("Aktif Entegra baglantisi tanimli degil.")

        if len(backends) == 1:
            return self._do_push(backends[0])

        return {
            'type': 'ir.actions.act_window',
            'name': 'Entegra Backend Sec',
            'res_model': 'entegra.push.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_product_ids': [(6, 0, self.ids)],
                'default_backend_ids': [(6, 0, backends.ids)],
            },
        }

    def _do_push(self, backend, force_update=False):
        """Push servisini cagirir ve sonucu bildirim olarak doner."""
        push_service = self.env['entegra.product.push']
        results = push_service.push_products(backend, self, force_update=force_update)

        success_count = len(results['success'])
        error_count = len(results['error'])

        if error_count == 0:
            msg_type = 'success'
            message = '%d urun basariyla Entegra\'ya gonderildi.' % success_count
        else:
            msg_type = 'warning'
            errors = '\n'.join(
                "* %s: %s" % (e['name'], e['error']) for e in results['error']
            )
            message = '%d basarili, %d hata.\n%s' % (success_count, error_count, errors)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Entegra Senkronizasyon',
                'message': message,
                'type': msg_type,
                'sticky': error_count > 0,
            },
        }

    def action_force_update_entegra(self):
        """Mapping olsa bile yeniden gonder (zorla guncelleme)."""
        self.ensure_one()
        backends = self.env['entegra.backend'].search([('active', '=', True)])
        if not backends:
            raise UserError("Aktif Entegra baglantisi yok.")
        return self._do_push(backends[0], force_update=True)

    # --- Write Hook -----------------------------------------------
    def write(self, vals):
        """
        Fiyat degisimlerini izler.
        Gercek stok degisimi stock.quant uzerinden gelir.
        """
        price_fields = {'list_price', 'standard_price'}
        if price_fields.intersection(vals.keys()):
            affected = self.filtered(
                lambda t: t.entegra_mapping_ids.filtered(
                    lambda m: m.sync_status == 'synced'
                )
            )
            if affected:
                _logger.debug(
                    '[Entegra] Fiyat degisimi tespit edildi: %s',
                    affected.mapped('default_code')
                )
        return super().write(vals)
