# -*- coding: utf-8 -*-
"""
Queue Job definitions for async SkyPlanner operations.

Uses OCA queue_job module.
Retry pattern: 1st retry after 60s, 2nd after 3min, 3rd after 10min.

Rules:
  - Apply plan: always async via queue_job
  - Cron-triggered apply: YASAK
  - Failed jobs: logged to skyplanner.sync.log
"""
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class SkyPlannerSyncJobs(models.AbstractModel):
    _name = 'skyplanner.sync.jobs'
    _description = 'SkyPlanner Async Job Definitions'

    @api.model
    def job_push_production_order(self, production_id):
        """
        Async push: MO → SkyPlanner.
        Usage: self.env['skyplanner.sync.jobs'].with_delay().job_push_production_order(id)
        """
        production = self.env['mrp.production'].browse(production_id)
        if not production.exists():
            _logger.warning('SkyPlanner job: MO id=%d not found', production_id)
            return
        planner = self.env['skyplanner.planner']
        result = planner.push_production_order(production)
        if result.get('error'):
            # Import here to avoid top-level dep on queue_job
            from odoo.addons.queue_job.exception import RetryableJobError
            from odoo.addons.skyplanner_connector.services.api_client import (
                SkyPlannerAPIError,
            )
            raise RetryableJobError(result['message'])

    @api.model
    def job_fetch_and_apply(self, production_id):
        """
        Async apply: SkyPlanner plan → Odoo work orders.
        Usage: self.env['skyplanner.sync.jobs'].with_delay().job_fetch_and_apply(id)
        """
        planner = self.env['skyplanner.planner']
        result = planner.fetch_and_apply(production_id, mode='apply')
        if result.get('error'):
            from odoo.addons.queue_job.exception import RetryableJobError
            raise RetryableJobError(result['message'])
        applied = sum(1 for c in result.get('changes', []) if c.get('applied'))
        skipped = sum(1 for c in result.get('changes', []) if c.get('protected'))
        _logger.info(
            'SkyPlanner apply done: MO=%d applied=%d skipped(protected)=%d',
            production_id, applied, skipped,
        )
