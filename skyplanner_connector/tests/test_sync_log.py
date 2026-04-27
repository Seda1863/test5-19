# -*- coding: utf-8 -*-
"""
Tests for models/skyplanner_sync_log.py
Run: odoo-bin -i skyplanner_connector --test-enable --test-tags=skyplanner_sync_log
"""
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('skyplanner_sync_log', 'skyplanner_connector')
class TestSkyPlannerSyncLog(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Log = self.env['skyplanner.sync.log']

    # ---- log() helper ----
    def test_log_creates_record(self):
        log = self.Log.log(
            name='Test push',
            direction='push',
            endpoint='/phaser-orders',
            method='POST',
            status='success',
            http_code=200,
            odoo_model='mrp.production',
            odoo_id=1,
        )
        self.assertTrue(log.id)
        self.assertEqual(log.direction, 'push')
        self.assertEqual(log.status, 'success')
        self.assertEqual(log.endpoint, '/phaser-orders')

    def test_log_error(self):
        log = self.Log.log(
            name='Push FAILED',
            direction='push',
            status='error',
            error='Connection timeout',
        )
        self.assertEqual(log.status, 'error')
        self.assertEqual(log.error_message, 'Connection timeout')

    # ---- is_duplicate_webhook ----
    def test_duplicate_webhook_detected(self):
        ext_id = 'unique-event-abc-123'
        # First event — not duplicate
        self.assertFalse(self.Log.is_duplicate_webhook(ext_id))

        # Log it as processed
        self.Log.log(
            name='Webhook: plan_updated',
            direction='webhook',
            status='success',
            external_id=ext_id,
        )

        # Second call — must detect duplicate
        self.assertTrue(self.Log.is_duplicate_webhook(ext_id))

    def test_duplicate_check_only_matches_webhook_direction(self):
        ext_id = 'push-event-xyz'
        # Log as 'push' not 'webhook'
        self.Log.log(
            name='Push event',
            direction='push',
            status='success',
            external_id=ext_id,
        )
        # Should NOT count as duplicate webhook
        self.assertFalse(self.Log.is_duplicate_webhook(ext_id))

    def test_duplicate_check_only_matches_success_status(self):
        ext_id = 'failed-event-xyz'
        self.Log.log(
            name='Failed webhook',
            direction='webhook',
            status='error',
            external_id=ext_id,
        )
        # Failed processing — allow retry
        self.assertFalse(self.Log.is_duplicate_webhook(ext_id))

    def test_no_external_id_not_duplicate(self):
        """Empty/None external_id must never block processing."""
        self.assertFalse(self.Log.is_duplicate_webhook(None))
        self.assertFalse(self.Log.is_duplicate_webhook(''))
        self.assertFalse(self.Log.is_duplicate_webhook(False))

    def test_different_external_ids_independent(self):
        self.Log.log(
            name='W1', direction='webhook', status='success', external_id='id-1'
        )
        self.assertTrue(self.Log.is_duplicate_webhook('id-1'))
        self.assertFalse(self.Log.is_duplicate_webhook('id-2'))
