# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class SkyPlannerSyncJobs(models.AbstractModel):
    _name = 'skyplanner.sync.jobs'
    _description = 'SkyPlanner Job Definitions'

    @api.model
    def job_push_production_order(self, production_id):
        production = self.env['mrp.production'].browse(production_id)
        if not production.exists():
            _logger.warning('SkyPlanner job: MO id=%d not found', production_id)
            return
        planner = self.env['skyplanner.planner']
        result = planner.push_production_order(production)
        if result.get('error'):
            _logger.error('SkyPlanner push failed for MO %d: %s', production_id, result.get('message'))

    @api.model
    def job_fetch_and_apply(self, production_id):
        planner = self.env['skyplanner.planner']
        result = planner.fetch_and_apply(production_id, mode='apply')
        if result.get('error'):
            _logger.error('SkyPlanner apply failed for MO %d: %s', production_id, result.get('message'))
            return
        applied = sum(1 for c in result.get('changes', []) if c.get('applied'))
        skipped = sum(1 for c in result.get('changes', []) if c.get('protected'))
        _logger.info(
            'SkyPlanner apply done: MO=%d applied=%d skipped(protected)=%d',
            production_id, applied, skipped,
        )
