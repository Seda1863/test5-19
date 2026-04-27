# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SkyPlannerSyncLog(models.Model):
    """
    Sync log for all SkyPlanner API calls.
    Used for idempotency checks (webhook deduplication) and debugging.
    Silent fail is YASAK — every API call must be logged.
    """
    _name = 'skyplanner.sync.log'
    _description = 'SkyPlanner Sync Log'
    _order = 'create_date desc'

    # -------------------------------------------------------------------------
    # Fields
    # -------------------------------------------------------------------------
    name = fields.Char(
        string='Description',
        required=True,
    )
    direction = fields.Selection(
        selection=[
            ('push', 'Push (Odoo → SkyPlanner)'),
            ('pull', 'Pull (SkyPlanner → Odoo)'),
            ('webhook', 'Webhook (SkyPlanner → Odoo)'),
        ],
        string='Direction',
        required=True,
    )
    endpoint = fields.Char(string='Endpoint')
    http_method = fields.Char(string='HTTP Method')
    status = fields.Selection(
        selection=[
            ('success', 'Success'),
            ('error', 'Error'),
            ('skipped', 'Skipped'),
        ],
        string='Status',
        required=True,
        default='success',
    )
    http_status_code = fields.Integer(string='HTTP Status Code')
    payload = fields.Text(string='Request Payload')
    response = fields.Text(string='Response')
    error_message = fields.Text(string='Error Message')
    external_id = fields.Char(
        string='External ID',
        index=True,
        help='Used for webhook idempotency check.',
    )
    odoo_model = fields.Char(string='Odoo Model')
    odoo_id = fields.Integer(string='Odoo Record ID')
    duration_ms = fields.Integer(string='Duration (ms)')

    # -------------------------------------------------------------------------
    # Idempotency
    # -------------------------------------------------------------------------
    @api.model
    def is_duplicate_webhook(self, external_id):
        """Return True if webhook with this external_id was already processed."""
        if not external_id:
            return False
        return bool(self.search([
            ('external_id', '=', str(external_id)),
            ('direction', '=', 'webhook'),
            ('status', '=', 'success'),
        ], limit=1))

    # -------------------------------------------------------------------------
    # Convenience creator
    # -------------------------------------------------------------------------
    @api.model
    def log(self, name, direction, endpoint=None, method=None,
            status='success', http_code=None, payload=None,
            response=None, error=None, external_id=None,
            odoo_model=None, odoo_id=None, duration_ms=None):
        """Single-call log helper."""
        return self.create({
            'name': name,
            'direction': direction,
            'endpoint': endpoint,
            'http_method': method,
            'status': status,
            'http_status_code': http_code,
            'payload': payload,
            'response': response,
            'error_message': error,
            'external_id': str(external_id) if external_id else None,
            'odoo_model': odoo_model,
            'odoo_id': odoo_id,
            'duration_ms': duration_ms,
        })
