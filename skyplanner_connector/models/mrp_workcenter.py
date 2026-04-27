# -*- coding: utf-8 -*-
"""
mrp.workcenter extension for SkyPlanner APS.

SkyPlanner veri modeli:
  workstation  = fiziksel makine/kaynak  → Odoo workcenter
  workstage    = süreç tipi (Kaynak, Montaj, vb.) → Odoo operation type

Her workcenter için iki ayrı SkyPlanner ID tutulur:
  skyplanner_workstation_id : POST /workstations → ID
  skyplanner_workstage_id   : POST /workstages → ID

phaser-job oluştururken HER İKİSİ de gereklidir.
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'

    # -------------------------------------------------------------------------
    # Workstation fields (fiziksel kaynak)
    # -------------------------------------------------------------------------
    skyplanner_workstation_id = fields.Integer(
        string='SkyPlanner Workstation ID',
        copy=False,
        readonly=True,
        help='ID from POST /workstations. Used in phaser-jobs.workstations field.',
    )
    skyplanner_external_id = fields.Char(
        string='External ID (Workstation)',
        copy=False,
        help=(
            'Unique external_id for this workstation in SkyPlanner. '
            'Default: workcenter code. Used to reconcile planned_workstation_id.'
        ),
    )
    skyplanner_scheduling_factor = fields.Float(
        string='Scheduling Factor',
        default=1.0,
        help='Capacity multiplier (1.0 = 100%). Sent to /workstations.',
    )
    skyplanner_workstation_synced = fields.Boolean(
        string='Workstation Synced',
        default=False,
        copy=False,
        readonly=True,
    )

    # -------------------------------------------------------------------------
    # Workstage fields (süreç tipi)
    # -------------------------------------------------------------------------
    skyplanner_workstage_id = fields.Integer(
        string='SkyPlanner Workstage ID',
        copy=False,
        readonly=True,
        help=(
            'ID from POST /workstages. '
            'REQUIRED for phaser-jobs.phaser_workstage_id. '
            'A workstage defines the type of operation (e.g. Welding, Assembly).'
        ),
    )
    skyplanner_workstage_name = fields.Char(
        string='Workstage Name',
        help=(
            'Name sent to SkyPlanner /workstages. '
            'If blank, workcenter name is used. '
            'Multiple workcenters can share the same workstage name '
            '(they will get the same workstage_id).'
        ),
    )
    skyplanner_workstage_external_id = fields.Char(
        string='External ID (Workstage)',
        copy=False,
        help='Unique external_id for this workstage in SkyPlanner.',
    )
    skyplanner_workstage_synced = fields.Boolean(
        string='Workstage Synced',
        default=False,
        copy=False,
        readonly=True,
    )

    # -------------------------------------------------------------------------
    # Computed status
    # -------------------------------------------------------------------------
    skyplanner_ready = fields.Boolean(
        string='APS Ready',
        compute='_compute_skyplanner_ready',
        store=True,
        help='True when both workstation and workstage are synced.',
    )
    skyplanner_last_sync = fields.Datetime(
        string='Last APS Sync',
        copy=False,
        readonly=True,
    )

    @api.depends('skyplanner_workstation_synced', 'skyplanner_workstage_synced')
    def _compute_skyplanner_ready(self):
        for rec in self:
            rec.skyplanner_ready = (
                rec.skyplanner_workstation_synced and rec.skyplanner_workstage_synced
            )

    # -------------------------------------------------------------------------
    # Defaults on create
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if not rec.skyplanner_external_id:
                rec.skyplanner_external_id = rec.code or rec.name
            if not rec.skyplanner_workstage_external_id:
                rec.skyplanner_workstage_external_id = (
                    f'ws-{rec.code or rec.name}'
                )
        return records

    # -------------------------------------------------------------------------
    # Sync: Workstation
    # -------------------------------------------------------------------------
    def action_sync_workstation(self):
        """POST or PUT /workstations for this workcenter."""
        self.ensure_one()
        from ..services.api_client import SkyPlannerClient, SkyPlannerAPIError

        client = SkyPlannerClient.from_env(self.env)
        Log = self.env['skyplanner.sync.log']

        payload = {
            'name': self.name,
            'external_id': self.skyplanner_external_id or self.code or self.name,
            'is_quick_log': False,
            'is_subcontract': False,
            'scheduling_factor': self.skyplanner_scheduling_factor,
        }

        try:
            if self.skyplanner_workstation_id:
                result, ms = client.put(
                    f'/workstations/{self.skyplanner_workstation_id}', payload
                )
                verb = 'PUT'
            else:
                result, ms = client.post('/workstations', payload)
                verb = 'POST'

            ws_data = result.get('workstation') or result
            ws_id = ws_data.get('id') or self.skyplanner_workstation_id
            self.write({
                'skyplanner_workstation_id': ws_id,
                'skyplanner_workstation_synced': True,
                'skyplanner_last_sync': fields.Datetime.now(),
            })
            Log.log(
                name=f'Sync workstation: {self.name}',
                direction='push', endpoint='/workstations', method=verb,
                status='success', http_code=200,
                payload=str(payload), response=str(result),
                odoo_model='mrp.workcenter', odoo_id=self.id, duration_ms=ms,
            )
            return ws_id

        except SkyPlannerAPIError as exc:
            Log.log(
                name=f'Workstation FAILED: {self.name}',
                direction='push', endpoint='/workstations', method='POST',
                status='error', error=str(exc),
                odoo_model='mrp.workcenter', odoo_id=self.id,
            )
            raise UserError(_('Workstation sync failed: %s') % exc)

    # -------------------------------------------------------------------------
    # Sync: Workstage
    # -------------------------------------------------------------------------
    def action_sync_workstage(self):
        """
        POST or PUT /workstages for this workcenter.

        Multiple workcenters can share a workstage (e.g. all welding machines
        → workstage 'Welding'). If skyplanner_workstage_name matches an existing
        workstage external_id, reuse it instead of creating a duplicate.
        """
        self.ensure_one()
        from ..services.api_client import SkyPlannerClient, SkyPlannerAPIError

        client = SkyPlannerClient.from_env(self.env)
        Log = self.env['skyplanner.sync.log']

        stage_name = self.skyplanner_workstage_name or self.name
        stage_ext_id = self.skyplanner_workstage_external_id or f'ws-{self.code or self.name}'

        payload = {
            'name': stage_name,
            'external_id': stage_ext_id,
            'description': f'Auto-created from Odoo workcenter: {self.name}',
            'workstations': str(self.skyplanner_workstation_id) if self.skyplanner_workstation_id else '',
        }

        try:
            if self.skyplanner_workstage_id:
                result, ms = client.put(
                    f'/workstages/{self.skyplanner_workstage_id}', payload
                )
                verb = 'PUT'
            else:
                # Check if a workstage with this external_id already exists
                existing = client.get(
                    '/workstages', params={'external_id': stage_ext_id, 'limit': 1}
                )
                stages = existing.get('workstages', [])
                if stages:
                    # Reuse existing workstage — don't create duplicate
                    ws_id = stages[0]['id']
                    self.write({
                        'skyplanner_workstage_id': ws_id,
                        'skyplanner_workstage_synced': True,
                        'skyplanner_last_sync': fields.Datetime.now(),
                    })
                    Log.log(
                        name=f'Sync workstage (reused): {stage_name}',
                        direction='push', endpoint='/workstages', method='GET',
                        status='success', http_code=200,
                        payload=str({'external_id': stage_ext_id}),
                        response=str(stages[0]),
                        odoo_model='mrp.workcenter', odoo_id=self.id,
                    )
                    _logger.info(
                        'SkyPlanner: reused existing workstage %d (%s) for %s',
                        ws_id, stage_name, self.name,
                    )
                    return ws_id

                result, ms = client.post('/workstages', payload)
                verb = 'POST'

            stage_data = result.get('workstage') or result
            ws_id = stage_data.get('id') or self.skyplanner_workstage_id
            self.write({
                'skyplanner_workstage_id': ws_id,
                'skyplanner_workstage_synced': True,
                'skyplanner_last_sync': fields.Datetime.now(),
            })
            Log.log(
                name=f'Sync workstage: {stage_name}',
                direction='push', endpoint='/workstages', method=verb,
                status='success', http_code=200,
                payload=str(payload), response=str(result),
                odoo_model='mrp.workcenter', odoo_id=self.id, duration_ms=ms,
            )
            return ws_id

        except SkyPlannerAPIError as exc:
            Log.log(
                name=f'Workstage FAILED: {stage_name}',
                direction='push', endpoint='/workstages', method='POST',
                status='error', error=str(exc),
                odoo_model='mrp.workcenter', odoo_id=self.id,
            )
            raise UserError(_('Workstage sync failed: %s') % exc)

    # -------------------------------------------------------------------------
    # Sync: Both (convenience)
    # -------------------------------------------------------------------------
    def action_sync_to_skyplanner(self):
        """Sync workstation then workstage — both required for phaser-jobs."""
        self.ensure_one()
        if not self.skyplanner_workstation_synced:
            self.action_sync_workstation()
        self.action_sync_workstage()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('APS Sync Complete'),
                'message': _(
                    '"%s" synced.\nWorkstation ID: %d | Workstage ID: %d'
                ) % (self.name, self.skyplanner_workstation_id, self.skyplanner_workstage_id),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_sync_all_workcenters(self):
        """Bulk sync from list view."""
        errors = []
        for wc in self:
            try:
                wc.action_sync_to_skyplanner()
            except UserError as exc:
                errors.append(f'{wc.name}: {exc}')
        if errors:
            raise UserError(_('Some workcenters failed:\n%s') % '\n'.join(errors))
