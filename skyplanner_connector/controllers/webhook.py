# -*- coding: utf-8 -*-
"""
SkyPlanner Webhook Controller
Route: POST /skyplanner/webhook

Alınan event'ler:
  plan_updated   → belirli MO'lar için fetch_and_apply (simulate)
  job_completed  → log only (gelecek: Odoo workorder state güncelle)
  (diğerleri)    → log + ignore

Idempotency: external_id bazlı deduplication (skyplanner.sync.log)
Auth: Authorization-Token header (aynı API token)

Dikkat: webhook, kullanıcı yokken çalışır (auth='none').
Odoo env'i admin olarak alınır.
"""
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

_HANDLED_EVENTS = {'plan_updated', 'job_completed', 'order_exported'}


class SkyPlannerWebhookController(http.Controller):

    @http.route(
        '/skyplanner/webhook',
        type='jsonrpc',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def handle_webhook(self, **kwargs):
        env = request.env(user=1)  # admin context — webhook has no user

        # ---- Parse body ----
        try:
            data = request.get_json_data()
        except Exception:
            data = kwargs or {}

        if not isinstance(data, dict):
            _logger.warning('SkyPlanner webhook: unexpected payload type %s', type(data))
            return {'status': 'error', 'message': 'Invalid payload'}

        event = data.get('event', 'unknown')
        external_id = str(data.get('external_id') or data.get('id') or '')

        _logger.info(
            'SkyPlanner webhook received: event=%s external_id=%s',
            event, external_id or '(none)',
        )

        # ---- Auth check ----
        expected_token = env['ir.config_parameter'].sudo().get_param(
            'skyplanner.api_token', ''
        )
        incoming_token = (
            request.httprequest.headers.get('Authorization-Token', '') or
            request.httprequest.headers.get('X-Skyplanner-Token', '')
        )
        if expected_token and incoming_token != expected_token:
            _logger.warning(
                'SkyPlanner webhook: auth failed — token mismatch'
            )
            return {'status': 'error', 'message': 'Unauthorized'}

        # ---- Idempotency ----
        Log = env['skyplanner.sync.log']
        if external_id and Log.is_duplicate_webhook(external_id):
            _logger.info(
                'SkyPlanner webhook: duplicate event %s — ignored', external_id
            )
            return {'status': 'duplicate', 'message': 'Already processed'}

        # ---- Dispatch ----
        try:
            result = self._dispatch(env, event, data)
        except Exception as exc:
            _logger.exception('SkyPlanner webhook: unhandled error for event=%s', event)
            Log.log(
                name=f'Webhook ERROR: {event}',
                direction='webhook',
                status='error',
                payload=json.dumps(data),
                error=str(exc),
                external_id=external_id or None,
            )
            return {'status': 'error', 'message': str(exc)}

        # ---- Log success ----
        Log.log(
            name=f'Webhook: {event}',
            direction='webhook',
            status='success',
            payload=json.dumps(data),
            external_id=external_id or None,
        )
        return {'status': 'ok', 'event': event, 'result': result}

    # =========================================================================
    # Event dispatchers
    # =========================================================================
    def _dispatch(self, env, event, data):
        if event == 'plan_updated':
            return self._handle_plan_updated(env, data)
        elif event == 'order_exported':
            return self._handle_order_exported(env, data)
        elif event == 'job_completed':
            return self._handle_job_completed(env, data)
        else:
            _logger.info('SkyPlanner webhook: unhandled event "%s" — logged only', event)
            return {'ignored': True}

    def _handle_plan_updated(self, env, data):
        """
        SkyPlanner updated the plan for one or more orders.

        Expected payload:
        {
          "event": "plan_updated",
          "external_id": "uuid",
          "phaser_order_ids": [42, 43],
          "phaser_order_id": 42       ← single order variant
        }

        Action: trigger fetch_and_apply (simulate) for affected MOs.
        Apply is NOT triggered automatically — user must click Apply Plan.
        """
        phaser_order_ids = data.get('phaser_order_ids') or []
        single = data.get('phaser_order_id')
        if single and single not in phaser_order_ids:
            phaser_order_ids.append(single)

        if not phaser_order_ids:
            _logger.warning('plan_updated webhook: no phaser_order_ids found')
            return {'mo_count': 0}

        # Find Odoo MOs by skyplanner_phaser_order_id
        productions = env['mrp.production'].search([
            ('skyplanner_phaser_order_id', 'in', phaser_order_ids),
            ('state', 'not in', ('done', 'cancel')),
        ])

        if not productions:
            _logger.info(
                'plan_updated webhook: no active MOs found for phaser_order_ids=%s',
                phaser_order_ids,
            )
            return {'mo_count': 0}

        planner = env['skyplanner.planner']
        triggered = []
        for production in productions:
            try:
                # simulate mode — never auto-apply from webhook
                result = planner.fetch_and_apply(
                    production_id=production.id,
                    mode='simulate',
                )
                triggered.append({
                    'mo': production.name,
                    'changes': len(result.get('changes', [])),
                    'errors': result.get('errors', []),
                })
                _logger.info(
                    'Webhook plan_updated: simulated MO %s — %d changes',
                    production.name, len(result.get('changes', [])),
                )
            except Exception as exc:
                _logger.error(
                    'Webhook plan_updated: error for MO %s: %s',
                    production.name, exc,
                )
                triggered.append({'mo': production.name, 'error': str(exc)})

        return {'mo_count': len(triggered), 'details': triggered}

    def _handle_order_exported(self, env, data):
        """
        SkyPlanner confirmed order export to Production Planning.

        Updates skyplanner_sync_state → 'exported' for matched MOs.
        """
        phaser_order_id = data.get('phaser_order_id')
        if not phaser_order_id:
            return {'updated': 0}

        productions = env['mrp.production'].search([
            ('skyplanner_phaser_order_id', '=', phaser_order_id),
        ])
        productions.write({'skyplanner_sync_state': 'exported'})
        _logger.info(
            'Webhook order_exported: updated %d MO(s) for phaser_order_id=%d',
            len(productions), phaser_order_id,
        )
        return {'updated': len(productions)}

    def _handle_job_completed(self, env, data):
        """
        SkyPlanner Timer: a job was completed.

        Currently: log only.
        Future: update mrp.workorder.qty_produced if configured.

        Expected payload:
        {
          "event": "job_completed",
          "production_planning_job_id": 101,
          "amount": 15,
          "faulty_amount": 1,
          "person_id": 485
        }
        """
        planning_job_id = data.get('production_planning_job_id')
        amount = data.get('amount', 0)
        _logger.info(
            'Webhook job_completed: planning_job_id=%s amount=%s',
            planning_job_id, amount,
        )
        # Future: find WO by skyplanner_planning_job_id and update qty
        return {'logged': True, 'planning_job_id': planning_job_id}
