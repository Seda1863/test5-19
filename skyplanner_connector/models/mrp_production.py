# -*- coding: utf-8 -*-
import logging
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    """
    Extends mrp.production with SkyPlanner integration fields and actions.

    Button flow on form:
      [Send to APS] → push MO + work orders to SkyPlanner
      [Get Plan]    → fetch plan (simulate mode — no write-back)
      [Apply Plan]  → async write-back via queue_job
      [Simulate]    → open wizard showing preview diff
    """
    _inherit = 'mrp.production'

    # -------------------------------------------------------------------------
    # SkyPlanner Fields — MO (phaser_order)
    # -------------------------------------------------------------------------
    skyplanner_phaser_order_id = fields.Integer(
        string='SkyPlanner Order ID',
        copy=False,
        help='Internal SkyPlanner ID from POST /phaser-orders.',
    )
    skyplanner_external_id = fields.Char(
        string='SkyPlanner External ID',
        copy=False,
        help='external_id sent to SkyPlanner (usually MO name).',
    )
    skyplanner_sync_state = fields.Selection(
        selection=[
            ('not_sent', 'Not Sent'),
            ('sent', 'Sent to APS'),
            ('exported', 'Exported'),
            ('planned', 'Planned'),
            ('applied', 'Applied'),
            ('error', 'Error'),
        ],
        string='APS Status',
        default='not_sent',
        copy=False,
        tracking=True,
    )
    skyplanner_last_sync = fields.Datetime(
        string='Last APS Sync',
        copy=False,
    )
    skyplanner_error = fields.Text(
        string='Last APS Error',
        copy=False,
    )

    # -------------------------------------------------------------------------
    # SkyPlanner Fields — Work Orders (phaser_order_rows / phaser_jobs)
    # -------------------------------------------------------------------------
    # Note: per-workorder fields are on mrp.workorder (see below)

    # -------------------------------------------------------------------------
    # UI Buttons
    # -------------------------------------------------------------------------
    def action_send_to_aps(self):
        """Push this MO and its work orders to SkyPlanner."""
        self.ensure_one()
        if not self.workorder_ids:
            raise UserError(_(
                'No work orders found on this MO. '
                'Confirm the MO first to generate work orders.'
            ))
        planner = self.env['skyplanner.planner']
        result = planner.push_production_order(self)
        if result.get('error'):
            self.skyplanner_sync_state = 'error'
            self.skyplanner_error = result.get('message')
            raise UserError(_('APS Push failed: %s') % result.get('message'))
        self.skyplanner_sync_state = 'sent'
        self.skyplanner_error = False
        return True

    def action_get_plan(self):
        """
        Fetch plan from SkyPlanner — SIMULATE mode only.
        Does NOT write back to Odoo. Opens wizard with preview.
        """
        self.ensure_one()
        if not self.skyplanner_phaser_order_id:
            raise UserError(_('This MO has not been sent to APS yet.'))
        wizard = self.env['skyplanner.simulate.wizard'].create({
            'production_id': self.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'skyplanner.simulate.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
        }

    def action_apply_plan(self):
        """
        Write planned dates back to work orders.
        RULE: Never overwrites work orders in progress/done state.
        RULE: Default is simulate — this is the only explicit apply path.
        """
        self.ensure_one()
        if not self.skyplanner_phaser_order_id:
            raise UserError(_('This MO has not been sent to APS yet.'))
        planner = self.env['skyplanner.planner']
        result = planner.fetch_and_apply(production_id=self.id, mode='apply')
        if result.get('error'):
            raise UserError(_('APS Apply failed: %s') % result.get('message'))
        applied = sum(1 for c in result.get('changes', []) if c.get('applied'))
        skipped = sum(1 for c in result.get('changes', []) if c.get('protected'))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('APS Plan Applied'),
                'message': _('%d work order(s) updated, %d protected (in progress/done).') % (applied, skipped),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_export_to_aps(self):
        """POST /phaser-orders/export — makes MO visible on SkyPlanner Gantt."""
        self.ensure_one()
        if not self.skyplanner_phaser_order_id:
            raise UserError(_('This MO has not been sent to APS yet.'))
        from ..services.api_client import SkyPlannerClient
        client = SkyPlannerClient.from_env(self.env)
        planner = self.env['skyplanner.planner']
        planner._export_and_log(client, self, self.skyplanner_phaser_order_id)

    def action_simulate_plan(self):
        """Open simulate wizard (alias for action_get_plan)."""
        return self.action_get_plan()


class MrpWorkorder(models.Model):
    """
    Extends mrp.workorder with SkyPlanner job fields.

    Critical fields:
      - skyplanner_phaser_job_id    : INPUT layer (from /phaser-jobs)
      - skyplanner_planning_job_id  : PLANNING layer (from /jobs after export)
                                      Required for timelog!
      - skyplanner_plan_version     : Used for stale plan detection
    """
    _inherit = 'mrp.workorder'

    # -------------------------------------------------------------------------
    # SkyPlanner Fields
    # -------------------------------------------------------------------------
    skyplanner_phaser_job_id = fields.Integer(
        string='SkyPlanner Phaser Job ID',
        copy=False,
        help='ID from POST /phaser-jobs. NOT used for timelog.',
    )
    skyplanner_planning_job_id = fields.Integer(
        string='SkyPlanner Planning Job ID',
        copy=False,
        help=(
            'ID from GET /jobs (production_planning_job_id). '
            'REQUIRED for timelog. Available only after export + schedule.'
        ),
    )
    skyplanner_external_id = fields.Char(
        string='SkyPlanner External ID',
        copy=False,
    )
    skyplanner_last_sync = fields.Datetime(
        string='Last APS Sync',
        copy=False,
    )
    skyplanner_plan_version = fields.Integer(
        string='APS Plan Version',
        default=0,
        copy=False,
        help=(
            'Incremented on each write-back. '
            'Used to reject stale plans: if incoming version < stored, skip.'
        ),
    )
    skyplanner_planned_start = fields.Datetime(
        string='APS Planned Start',
        copy=False,
        help='Planned start time from SkyPlanner (before write-back to date_start).',
    )
    skyplanner_planned_end = fields.Datetime(
        string='APS Planned End',
        copy=False,
        help='Planned end time from SkyPlanner (before write-back to date_finished).',
    )

    # -------------------------------------------------------------------------
    # Write-back helper (called by planner service)
    # -------------------------------------------------------------------------
    def skyplanner_apply_dates(self, start, end, incoming_version):
        """
        Apply planned dates from SkyPlanner.

        RULES (kırılamaz):
        1. state in ['progress', 'done'] → skip, never overwrite
        2. incoming_version < current plan_version → skip (stale plan)
        3. Only date_start and date_finished are written
        4. state / qty / duration_real are NEVER written
        """
        self.ensure_one()

        # Rule 1: protect running/done work orders
        if self.state in ('progress', 'done'):
            _logger.info(
                'SkyPlanner write-back skipped for WO %s — state=%s',
                self.id, self.state
            )
            return False

        # Rule 2: reject stale plan
        if incoming_version and incoming_version <= self.skyplanner_plan_version:
            _logger.warning(
                'SkyPlanner write-back skipped for WO %s — '
                'incoming version %s < stored %s',
                self.id, incoming_version, self.skyplanner_plan_version
            )
            return False

        # Rule 3: write only date fields
        vals = {
            'date_start': start,
            'date_finished': end,
            'skyplanner_planned_start': start,
            'skyplanner_planned_end': end,
            'skyplanner_last_sync': fields.Datetime.now(),
        }
        if incoming_version:
            vals['skyplanner_plan_version'] = incoming_version

        self.write(vals)
        _logger.info(
            'SkyPlanner write-back applied for WO %s: %s → %s',
            self.id, start, end
        )
        return True
