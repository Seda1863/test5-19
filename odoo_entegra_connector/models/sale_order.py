# -*- coding: utf-8 -*-
"""
sale_order.py
─────────────
sale.order genişlemesi.
Entegra kaynaklı siparişler için ek alanlar ve kargo push hook'u.
"""

import logging
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # --- Entegra Kimlik Alanlari ----------------------------------
    entegra_order_id = fields.Integer(
        string='Entegra Siparis ID',
        copy=False,
        index=True,
        help="Entegra'daki siparis ID'si. Duplicate import'u onler.",
    )
    entegra_order_number = fields.Char(
        string='Entegra Siparis No',
        copy=False,
        readonly=True,
    )
    entegra_supplier = fields.Char(
        string='Pazaryeri',
        copy=False,
        readonly=True,
        help='Siparisín geldigi pazaryeri: trendyol, hb, n11...',
    )
    entegra_status_label = fields.Char(
        string='Entegra Statüsü',
        copy=False,
        readonly=True,
    )
    entegra_backend_id = fields.Many2one(
        'entegra.backend',
        string='Entegra Backend',
        copy=False,
        readonly=True,
    )

    # --- Entegra Sync Durumu -------------------------------------
    entegra_sync_status = fields.Selection(
        selection=[
            ('0', "ERP'ye Gonderilecek"),
            ('1', "ERP'ye Gonderildi"),
            ('-1', 'Gonderilmeyecek'),
        ],
        string='Entegra Sync',
        default=False,
        copy=False,
    )

    # --- Kargo Bilgileri -----------------------------------------
    entegra_cargo_company = fields.Char(
        string='Kargo Firmasi',
        copy=False,
        help='Entegra kargo firmasi kodu: aras, yurtici, mng...',
    )
    entegra_cargo_code = fields.Char(
        string='Kargo Takip No',
        copy=False,
    )

    # --- Pazaryeri Notları (PDF'e çıkmaz) ------------------------
    entegra_marketplace_note = fields.Text(
        string='Pazaryeri Detayları',
        copy=False,
        help='Entegra\'dan gelen sipariş detayları (pazaryeri no, kargo, ödeme yöntemi).',
    )

    # --- Computed / UI -------------------------------------------
    is_entegra_order = fields.Boolean(
        string="Entegra Siparisi mi?",
        compute='_compute_is_entegra_order',
        store=True,
    )

    @api.depends('entegra_order_id')
    def _compute_is_entegra_order(self):
        for so in self:
            so.is_entegra_order = bool(so.entegra_order_id)

    # --- Kargo Push Aksiyonu (Manuel) ----------------------------
    def action_push_shipment_to_entegra(self):
        """
        Kargo bilgisini Entegra'ya manuel olarak gonderir.
        Picking tamamlaninca otomatik tetiklemek icin
        stock.picking'e override eklenebilir (gelecek adim).
        """
        self.ensure_one()

        if not self.is_entegra_order:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Bilgi',
                    'message': "Bu siparis Entegra'dan gelmemis.",
                    'type': 'warning',
                },
            }

        if not self.entegra_cargo_company or not self.entegra_cargo_code:
            raise UserError(_('Kargo bildirimi için kargo firması ve kargo takip numarası girilmelidir.'))

        backend = self.entegra_backend_id
        if not backend:
            backend = self.env['entegra.backend'].search(
                [('active', '=', True)], limit=1
            )

        if not backend:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Hata',
                    'message': 'Aktif Entegra baglantisi yok.',
                    'type': 'danger',
                },
            }

        result = self.env['entegra.order.import'].push_shipment_info(
            backend, self,
            self.entegra_cargo_company,
            self.entegra_cargo_code,
        )

        if not result.get('ok'):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Kargo Gönderilemedi'),
                    'message': result.get('message', _('Bilinmeyen hata')),
                    'type': 'danger',
                    'sticky': True,
                },
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Kargo Gönderildi'),
                'message': _("Kargo bilgisi Entegra'ya başarıyla iletildi."),
                'type': 'success',
                'sticky': False,
            },
        }

    # --- SQL Constraint ------------------------------------------
    _sql_constraints = [
        (
            'unique_entegra_order',
            'UNIQUE(entegra_order_id, entegra_backend_id)',
            "Bu Entegra siparis ID'si icin zaten bir kayit mevcut.",
        ),
    ]
