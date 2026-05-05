# -*- coding: utf-8 -*-
"""
SkyPlanner Mapper — Odoo records → SkyPlanner API payloads.

Pure data transformation. No API calls, no DB writes.

Key rules:
  - external_id = Odoo record name/code (stable, human-readable)
  - workstations  = comma-separated SkyPlanner workstation IDs (string!)
  - phaser_workstage_id = skyplanner_workstage_id from workcenter
  - duration = seconds (Odoo: minutes → ×60)
  - datetime format: "YYYY-MM-DD HH:MM:SS"
  - job_parts: iterate ALL parts, min(starts) / max(ends) — never assume first=earliest
"""
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

_DT_FORMAT = '%Y-%m-%d %H:%M:%S'


def _fmt_dt(dt):
    """Format datetime/date for SkyPlanner API. Returns None if falsy."""
    if not dt:
        return None
    if hasattr(dt, 'strftime'):
        return dt.strftime(_DT_FORMAT)
    return str(dt)


class SkyPlannerMapper:
    """Stateless payload builder. Instantiate with Odoo env."""

    def __init__(self, env):
        self.env = env
        get = env['ir.config_parameter'].sudo().get_param
        self._default_customer_id = int(
            get('skyplanner.default_customer_id', 0) or 0
        )

    # =========================================================================
    # phaser-orders
    # =========================================================================
    def build_phaser_order(self, production):
        """
        mrp.production → POST /phaser-orders payload.
        Required: production_planning_customer_id, number.
        """
        return {
            'production_planning_customer_id': self._resolve_customer_id(production),
            'number': production.name.replace('/', '-'),
            'external_order_number': production.name.replace('/', '-'),
            'status': 'new',
            'description': production.product_id.display_name or '',
            'delivery_date': _fmt_dt(production.date_deadline),
            'start_eligibility_date': _fmt_dt(production.date_start),
        }

    def _resolve_customer_id(self, production):
        """
        Resolve SkyPlanner customer ID from default config.
        mrp.production has no partner_id in Odoo 19.
        """
        if self._default_customer_id:
            return self._default_customer_id

        raise ValueError(
            f'No SkyPlanner customer ID for MO "{production.name}". '
            'Configure a Default Customer ID in Settings → SkyPlanner APS.'
        )

    # =========================================================================
    # phaser-order-rows
    # =========================================================================
    def build_phaser_order_row(self, production, phaser_order_id, row_index=1):
        """
        mrp.production → POST /phaser-order-rows payload.
        One row per MO. All work orders become phaser-jobs under this row.
        """
        return {
            'phaser_order_id': phaser_order_id,
            'external_id': f'{production.name}',
            'row_index': row_index,
            'status': 'new',
            'amount': production.product_qty,
            'ordered_amount': production.product_qty,
            'delivery_date': _fmt_dt(production.date_deadline),
            'start_eligibility_date': _fmt_dt(production.date_start),
            'description': production.product_id.display_name or '',
            'get_default_steps': False,     # push steps explicitly
            'use_custom_materials': False,
        }

    # =========================================================================
    # phaser-jobs (process steps)
    # =========================================================================
    def build_phaser_job(self, workorder, phaser_order_row_id, order_number=1):
        """
        mrp.workorder → POST /phaser-jobs payload.

        Required:
          phaser_order_row_id  — from previous step
          phaser_workstage_id  — from workcenter.skyplanner_workstage_id  ← CRITICAL
          workstations         — comma-separated workstation IDs (string)  ← CRITICAL

        Raises ValueError if workcenter is not synced to SkyPlanner.
        """
        workcenter = workorder.workcenter_id
        self._validate_workcenter(workcenter)

        workstage_id = workcenter.skyplanner_workstage_id
        workstation_ids_str = str(workcenter.skyplanner_workstation_id)
        duration_sec = int((workorder.duration_expected or 60) * 60)

        return {
            'phaser_order_row_id': phaser_order_row_id,
            'phaser_workstage_id': workstage_id,
            'workstations': workstation_ids_str,
            'external_id': f'{workorder.production_id.name}-WO{workorder.id}',
            'name': workorder.name or workcenter.name,
            'order_number': order_number,
            'duration': float(duration_sec),
            'settingtime': 0,
            'settletime': 0,
            'status': 'new',
            'min_degree': 100,
            'can_split_job': False,
            'start_eligibility_date': _fmt_dt(workorder.date_start),
        }

    def _validate_workcenter(self, workcenter):
        """
        Guard: both workstation AND workstage must be synced.
        Raises ValueError with actionable message.
        """
        errors = []
        if not workcenter.skyplanner_workstation_id:
            errors.append(
                f'Workcenter "{workcenter.name}" has no Workstation ID. '
                'Go to the workcenter and click "Sync Workstation".'
            )
        if not workcenter.skyplanner_workstage_id:
            errors.append(
                f'Workcenter "{workcenter.name}" has no Workstage ID. '
                'Go to the workcenter and click "Sync Workstage".'
            )
        if errors:
            raise ValueError('\n'.join(errors))

    # =========================================================================
    # job_parts → Odoo dates  (CRITICAL: min/max, not first/last)
    # =========================================================================
    def extract_planned_dates(self, job_data):
        """
        Extract min(planned_start_time) and max(planned_end_time) from job_parts.

        SkyPlanner doc (explicit warning):
          "ilk bölümün en erken planlanan_başlangıç_zamanına sahip olduğunu
          varsaymayın! Bu her zaman geçerli değildir."

        Returns (start_str, end_str) or (None, None) if no planned parts.
        """
        parts = job_data.get('job_parts', [])

        planned_parts = [
            p for p in parts
            if p.get('is_planned')
            and p.get('planned_start_time')
            and p.get('planned_end_time')
        ]

        if not planned_parts:
            # Fallback: job-level times (pre-export or unscheduled)
            start = job_data.get('start_time')
            end = job_data.get('end_time')
            if start or end:
                _logger.debug(
                    'job_parts empty — using job-level times: %s → %s', start, end
                )
            return start, end

        starts = [p['planned_start_time'] for p in planned_parts]
        ends = [p['planned_end_time'] for p in planned_parts]
        return min(starts), max(ends)

    def get_planned_workstation_id(self, job_data):
        """
        Extract planned_workstation_id from job_parts.
        Returns ID of the first planned part with a workstation.
        Used to detect if SkyPlanner reassigned to a different workcenter.
        """
        parts = job_data.get('job_parts', [])
        for part in parts:
            if part.get('is_planned') and part.get('planned_workstation_id'):
                return part['planned_workstation_id']
        return None

    # =========================================================================
    # Export payload helper
    # =========================================================================
    def build_export_payload(self, phaser_order_ids):
        """POST /phaser-orders/export payload."""
        return {'ids': list(phaser_order_ids)}
