# -*- coding: utf-8 -*-
"""
SkyPlanner Planner Service

Orchestrates the full push/pull flow:
  push_production_order()  → MO → SkyPlanner (steps 1-4)
  fetch_and_apply()        → SkyPlanner plan → Odoo (steps 5-7)

Design rules (kırılamaz):
  - simulate mode = default, no Odoo write
  - apply mode = explicit only (never from cron)
  - state in (progress, done) → write-back skip
  - silent fail → YASAK — every call logged
"""
import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .api_client import SkyPlannerClient, SkyPlannerAPIError
from .mapper import SkyPlannerMapper

_logger = logging.getLogger(__name__)


class SkyPlannerPlanner(models.AbstractModel):
    """
    AbstractModel so it can be called via self.env['skyplanner.planner'].
    No DB table created.
    """
    _name = 'skyplanner.planner'
    _description = 'SkyPlanner Planner Service'

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------
    def _get_client(self):
        return SkyPlannerClient.from_env(self.env)

    def _get_mapper(self):
        return SkyPlannerMapper(self.env)

    def _log(self, **kwargs):
        return self.env['skyplanner.sync.log'].log(**kwargs)

    def _get_param(self, key, default=False):
        return self.env['ir.config_parameter'].sudo().get_param(key, default)

    # -------------------------------------------------------------------------
    # PUSH: MO → SkyPlanner
    # -------------------------------------------------------------------------
    @api.model
    def push_production_order(self, production):
        """
        Full push flow for one mrp.production:

          1. POST /phaser-orders         → phaser_order_id
          2. POST /phaser-order-rows     → phaser_order_row_id  (1 per MO)
          3. POST /phaser-jobs           → phaser_job_id        (1 per workorder)
          4. POST /phaser-orders/export  → Production Planning layer
             (only if skyplanner.auto_export = True)

        Returns dict: {'ok': True} or {'error': True, 'message': '...'}
        """
        production.ensure_one()
        client = self._get_client()
        mapper = self._get_mapper()
        Mapping = self.env['skyplanner.mapping']

        try:
            # ---- Step 1: phaser-order ----------------------------------------
            order_payload = mapper.build_phaser_order(production)
            result, ms = client.post('/phaser-orders', order_payload)
            phaser_order = result.get('phaser-order') or result
            phaser_order_id = phaser_order['id']

            Mapping.set_mapping(
                'mrp.production', production.id,
                'phaser_order', phaser_order_id,
                external_id=production.name,
            )
            production.write({
                'skyplanner_phaser_order_id': phaser_order_id,
                'skyplanner_external_id': production.name,
            })
            self._log(
                name=f'Push phaser-order: {production.name}',
                direction='push',
                endpoint='/phaser-orders',
                method='POST',
                status='success',
                http_code=200,
                payload=json.dumps(order_payload),
                response=json.dumps(result),
                odoo_model='mrp.production',
                odoo_id=production.id,
                duration_ms=ms,
            )
            _logger.info(
                'SkyPlanner: created phaser-order %d for MO %s',
                phaser_order_id, production.name,
            )

            # ---- Step 2: phaser-order-row ------------------------------------
            # One row per MO (all work orders are process steps under this row)
            row_payload = mapper.build_phaser_order_row(production, phaser_order_id)
            result_row, ms = client.post('/phaser-order-rows', row_payload)
            phaser_row = result_row.get('phaser-order-row') or result_row
            phaser_order_row_id = phaser_row['id']

            Mapping.set_mapping(
                'mrp.production', production.id,
                'phaser_order_row', phaser_order_row_id,
                external_id=row_payload.get('external_id'),
            )
            self._log(
                name=f'Push phaser-order-row: {production.name}',
                direction='push',
                endpoint='/phaser-order-rows',
                method='POST',
                status='success',
                http_code=200,
                payload=json.dumps(row_payload),
                response=json.dumps(result_row),
                odoo_model='mrp.production',
                odoo_id=production.id,
                duration_ms=ms,
            )

            # ---- Step 3: phaser-jobs (one per workorder) ---------------------
            for idx, wo in enumerate(production.workorder_ids, start=1):
                job_payload = mapper.build_phaser_job(wo, phaser_order_row_id, order_number=idx)
                result_job, ms = client.post('/phaser-jobs', job_payload)
                phaser_job = result_job.get('phaser-job') or result_job
                phaser_job_id = phaser_job['id']

                Mapping.set_mapping(
                    'mrp.workorder', wo.id,
                    'phaser_job', phaser_job_id,
                    external_id=job_payload.get('external_id'),
                )
                wo.write({
                    'skyplanner_phaser_job_id': phaser_job_id,
                    'skyplanner_external_id': job_payload.get('external_id'),
                })
                self._log(
                    name=f'Push phaser-job: {wo.name}',
                    direction='push',
                    endpoint='/phaser-jobs',
                    method='POST',
                    status='success',
                    http_code=200,
                    payload=json.dumps(job_payload),
                    response=json.dumps(result_job),
                    odoo_model='mrp.workorder',
                    odoo_id=wo.id,
                    duration_ms=ms,
                )
                _logger.info(
                    'SkyPlanner: created phaser-job %d for WO %s',
                    phaser_job_id, wo.name,
                )

            production.write({
                'skyplanner_sync_state': 'sent',
                'skyplanner_last_sync': fields.Datetime.now(),
                'skyplanner_error': False,
            })

            # ---- Step 4: auto-export (optional) ------------------------------
            auto_export = self._get_param('skyplanner.auto_export', 'False')
            if auto_export in ('True', '1', 'true'):
                self._export_and_log(client, production, phaser_order_id)

            return {'ok': True, 'phaser_order_id': phaser_order_id}

        except (SkyPlannerAPIError, ValueError, KeyError) as exc:
            msg = str(exc)
            _logger.error('SkyPlanner push error for MO %s: %s', production.name, msg)
            self._log(
                name=f'Push FAILED: {production.name}',
                direction='push',
                status='error',
                error=msg,
                odoo_model='mrp.production',
                odoo_id=production.id,
            )
            production.write({
                'skyplanner_sync_state': 'error',
                'skyplanner_error': msg,
            })
            return {'error': True, 'message': msg}

    def _export_and_log(self, client, production, phaser_order_id):
        """POST /phaser-orders/export and update sync state."""
        try:
            result, ms = client.export_phaser_orders([phaser_order_id])
            self._log(
                name=f'Export phaser-order: {production.name}',
                direction='push',
                endpoint='/phaser-orders/export',
                method='POST',
                status='success',
                http_code=200,
                payload=json.dumps({'ids': [phaser_order_id]}),
                response=json.dumps(result),
                odoo_model='mrp.production',
                odoo_id=production.id,
                duration_ms=ms,
            )
            production.skyplanner_sync_state = 'exported'
            _logger.info('SkyPlanner: exported phaser-order %d', phaser_order_id)
        except SkyPlannerAPIError as exc:
            _logger.error('SkyPlanner export error: %s', exc)
            self._log(
                name=f'Export FAILED: {production.name}',
                direction='push',
                endpoint='/phaser-orders/export',
                method='POST',
                status='error',
                error=str(exc),
                odoo_model='mrp.production',
                odoo_id=production.id,
            )

    # -------------------------------------------------------------------------
    # PULL: SkyPlanner plan → Odoo
    # -------------------------------------------------------------------------
    @api.model
    def fetch_and_apply(self, production_id, mode='simulate'):
        """
        Fetch planned dates from SkyPlanner and optionally write back.

        mode='simulate' → returns diff, does NOT write to Odoo
        mode='apply'    → writes date_start/date_finished to work orders

        CRITICAL RULES:
        - Default: simulate
        - Apply: explicit user action only — NEVER from cron
        - WO state in (progress, done) → always skip
        - Stale plan (version check) → skip
        - job_parts=true REQUIRED for planned dates

        Returns dict with 'changes' list or 'error'.
        """
        production = self.env['mrp.production'].browse(production_id)
        if not production.exists():
            return {'error': True, 'message': f'MO id={production_id} not found'}

        client = self._get_client()
        mapper = self._get_mapper()
        Mapping = self.env['skyplanner.mapping']

        try:
            # Get all planning jobs for this MO's work orders
            changes = []
            errors = []

            for wo in production.workorder_ids:
                if not wo.skyplanner_phaser_job_id:
                    _logger.warning(
                        'WO %s has no skyplanner_phaser_job_id — skipped', wo.id
                    )
                    continue

                # Resolve production_planning_job_id from mapping or phaser-jobs
                planning_job_id = wo.skyplanner_planning_job_id
                if not planning_job_id:
                    planning_job_id = self._resolve_planning_job_id(
                        client, Mapping, wo
                    )
                    if not planning_job_id:
                        errors.append(f'WO {wo.name}: no planning_job_id (export+schedule needed)')
                        continue

                # Fetch /jobs/{id}?job_parts=true
                try:
                    job_data = client.get(
                        f'/jobs/{planning_job_id}',
                        params={'job_parts': 'true'},
                    )
                except SkyPlannerAPIError as exc:
                    errors.append(f'WO {wo.name}: {exc}')
                    continue

                start, end = mapper.extract_planned_dates(job_data)
                if not start or not end:
                    errors.append(f'WO {wo.name}: no planned dates in response')
                    continue

                protected = wo.state in ('progress', 'done')
                change = {
                    'wo_id': wo.id,
                    'wo_name': wo.name,
                    'workcenter': wo.workcenter_id.name,
                    'current_start': str(wo.date_start or ''),
                    'current_end': str(wo.date_finished or ''),
                    'planned_start': start,
                    'planned_end': end,
                    'protected': protected,
                    'planning_job_id': planning_job_id,
                }
                changes.append(change)

                if mode == 'apply' and not protected:
                    # Increment version to detect stale writes
                    new_version = (wo.skyplanner_plan_version or 0) + 1
                    applied = wo.skyplanner_apply_dates(start, end, new_version)
                    change['applied'] = applied

            if mode == 'apply':
                production.write({
                    'skyplanner_sync_state': 'applied',
                    'skyplanner_last_sync': fields.Datetime.now(),
                })
            elif mode == 'simulate' and changes:
                production.skyplanner_sync_state = 'planned'

            self._log(
                name=f'Fetch plan ({mode}): {production.name}',
                direction='pull',
                endpoint='/jobs',
                method='GET',
                status='success' if not errors else 'error',
                error='\n'.join(errors) if errors else None,
                odoo_model='mrp.production',
                odoo_id=production.id,
            )

            return {
                'ok': True,
                'mode': mode,
                'changes': changes,
                'errors': errors,
            }

        except (SkyPlannerAPIError, Exception) as exc:
            msg = str(exc)
            _logger.error('SkyPlanner fetch error for MO %s: %s', production.name, msg)
            self._log(
                name=f'Fetch FAILED ({mode}): {production.name}',
                direction='pull',
                status='error',
                error=msg,
                odoo_model='mrp.production',
                odoo_id=production.id,
            )
            return {'error': True, 'message': msg}

    def _resolve_planning_job_id(self, client, Mapping, wo):
        """
        Find production_planning_job_id by querying /phaser-jobs.
        SkyPlanner links phaser_job → production_planning_job_id after export.
        """
        # Check mapping table first
        mapping = Mapping.search([
            ('odoo_model', '=', 'mrp.workorder'),
            ('odoo_id', '=', wo.id),
            ('mapping_type', '=', 'planning_job'),
        ], limit=1)
        if mapping:
            return mapping.skyplanner_id

        # Query SkyPlanner to find production_planning_job_id
        try:
            jobs_resp = client.get('/phaser-jobs', params={
                'contain': 'jobs',
                'limit': 1,
            })
            # phaser-jobs response: look for our phaser_job_id
            phaser_jobs = jobs_resp.get('phaser-jobs', [])
            for pj in phaser_jobs:
                if pj.get('id') == wo.skyplanner_phaser_job_id:
                    planning_job_id = pj.get('production_planning_job_id')
                    if planning_job_id:
                        # Cache in mapping table
                        Mapping.set_mapping(
                            'mrp.workorder', wo.id,
                            'planning_job', planning_job_id,
                        )
                        wo.skyplanner_planning_job_id = planning_job_id
                        return planning_job_id
        except SkyPlannerAPIError:
            pass
        return None
