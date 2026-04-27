# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SkyPlannerMapping(models.Model):
    """
    ID Mapping table between Odoo records and SkyPlanner entities.

    SkyPlanner has two distinct ID spaces:
      - phaser_job_id  : INPUT layer ID (from /phaser-orders, /phaser-order-rows, /phaser-jobs)
      - planning_job_id: PLANNING layer ID (from /jobs after export+schedule)

    Timelog requires planning_job_id — never phaser_job_id.
    """
    _name = 'skyplanner.mapping'
    _description = 'SkyPlanner ID Mapping'
    _order = 'write_date desc'
    _rec_name = 'display_name'

    # -------------------------------------------------------------------------
    # Fields
    # -------------------------------------------------------------------------
    odoo_model = fields.Char(
        string='Odoo Model',
        required=True,
        index=True,
        help='e.g. mrp.production or mrp.workorder',
    )
    odoo_id = fields.Integer(
        string='Odoo Record ID',
        required=True,
        index=True,
    )
    mapping_type = fields.Selection(
        selection=[
            ('phaser_order', 'Phaser Order'),           # /phaser-orders
            ('phaser_order_row', 'Phaser Order Row'),   # /phaser-order-rows
            ('phaser_job', 'Phaser Job'),               # /phaser-jobs (INPUT)
            ('planning_job', 'Planning Job'),           # /jobs (after export — for timelog)
        ],
        string='Mapping Type',
        required=True,
        index=True,
    )
    skyplanner_id = fields.Integer(
        string='SkyPlanner ID',
        required=True,
        help='Internal SkyPlanner entity ID.',
    )
    external_id = fields.Char(
        string='External ID',
        help='The external_id value sent to SkyPlanner (usually Odoo record name).',
    )
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True,
    )

    # -------------------------------------------------------------------------
    # Computed
    # -------------------------------------------------------------------------
    @api.depends('odoo_model', 'odoo_id', 'mapping_type', 'skyplanner_id')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = (
                f"{rec.odoo_model}:{rec.odoo_id} → "
                f"[{rec.mapping_type}] {rec.skyplanner_id}"
            )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    @api.model
    def get_skyplanner_id(self, odoo_model, odoo_id, mapping_type):
        """Return SkyPlanner ID for a given Odoo record, or False."""
        rec = self.search([
            ('odoo_model', '=', odoo_model),
            ('odoo_id', '=', odoo_id),
            ('mapping_type', '=', mapping_type),
        ], limit=1)
        return rec.skyplanner_id if rec else False

    @api.model
    def set_mapping(self, odoo_model, odoo_id, mapping_type, skyplanner_id,
                    external_id=None):
        """Upsert a mapping record."""
        existing = self.search([
            ('odoo_model', '=', odoo_model),
            ('odoo_id', '=', odoo_id),
            ('mapping_type', '=', mapping_type),
        ], limit=1)
        vals = {
            'skyplanner_id': skyplanner_id,
            'external_id': external_id,
        }
        if existing:
            existing.write(vals)
            return existing
        return self.create({
            'odoo_model': odoo_model,
            'odoo_id': odoo_id,
            'mapping_type': mapping_type,
            **vals,
        })
