# -*- coding: utf-8 -*-
"""
Tests for services/api_client.py

Mock HTTP — no live SkyPlanner required.
Run: odoo-bin -i skyplanner_connector --test-enable --test-tags=skyplanner_api
"""
from unittest.mock import MagicMock, patch

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.skyplanner_connector.services.api_client import (
    SkyPlannerAPIError,
    SkyPlannerClient,
)


@tagged('skyplanner_api', 'skyplanner_connector')
class TestSkyPlannerClient(TransactionCase):
    """Unit tests for SkyPlannerClient."""

    def setUp(self):
        super().setUp()
        self.client = SkyPlannerClient(
            base_url='https://demo.skyplanner.app/production-planning/api/v3',
            api_token='test-token-123',
            timeout=5,
        )

    # -------------------------------------------------------------------------
    # Auth header
    # -------------------------------------------------------------------------
    def test_auth_header_set_correctly(self):
        """Authorization-Token header must be set, not Bearer."""
        headers = self.client._session.headers
        self.assertIn('Authorization-Token', headers)
        self.assertEqual(headers['Authorization-Token'], 'test-token-123')
        # Must NOT have Authorization: Bearer
        self.assertNotIn('Authorization', headers)

    def test_missing_token_raises_user_error(self):
        with self.assertRaises(UserError):
            SkyPlannerClient(base_url='https://x.skyplanner.app', api_token='')

    def test_missing_base_url_raises_user_error(self):
        with self.assertRaises(UserError):
            SkyPlannerClient(base_url='', api_token='token')

    # -------------------------------------------------------------------------
    # HTTP success
    # -------------------------------------------------------------------------
    @patch('requests.Session.request')
    def test_get_returns_parsed_json(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'phaser-orders': [{'id': 1}]}
        mock_request.return_value = mock_resp

        result = self.client.get('/phaser-orders')
        self.assertEqual(result['phaser-orders'][0]['id'], 1)

    @patch('requests.Session.request')
    def test_post_returns_result_and_duration(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'phaser-order': {'id': 42}}
        mock_request.return_value = mock_resp

        result, ms = self.client.post('/phaser-orders', {'number': 'MO001'})
        self.assertEqual(result['phaser-order']['id'], 42)
        self.assertIsInstance(ms, int)

    # -------------------------------------------------------------------------
    # HTTP errors
    # -------------------------------------------------------------------------
    @patch('requests.Session.request')
    def test_401_raises_api_error(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {'message': 'Unauthorized'}
        mock_request.return_value = mock_resp

        with self.assertRaises(SkyPlannerAPIError) as ctx:
            self.client.get('/phaser-orders')
        self.assertIn('Authentication failed', str(ctx.exception))

    @patch('requests.Session.request')
    def test_403_raises_api_error_with_support_hint(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.json.return_value = {'error': 'forbidden'}
        mock_request.return_value = mock_resp

        with self.assertRaises(SkyPlannerAPIError) as ctx:
            self.client.post('/ai-actions/schedule', {})
        self.assertIn('support', str(ctx.exception).lower())

    @patch('requests.Session.request')
    def test_422_not_retryable(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 422
        mock_resp.json.return_value = {'message': 'Validation error'}
        mock_request.return_value = mock_resp

        with self.assertRaises(SkyPlannerAPIError) as ctx:
            self.client.post('/phaser-orders', {})
        self.assertFalse(ctx.exception.is_retryable)

    @patch('requests.Session.request')
    def test_500_is_retryable(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.json.return_value = {'error': 'Server error'}
        mock_request.return_value = mock_resp

        with self.assertRaises(SkyPlannerAPIError) as ctx:
            self.client.get('/phaser-orders')
        self.assertTrue(ctx.exception.is_retryable)

    @patch('requests.Session.request')
    def test_timeout_raises_api_error(self, mock_request):
        from requests.exceptions import Timeout
        mock_request.side_effect = Timeout()

        with self.assertRaises(SkyPlannerAPIError) as ctx:
            self.client.get('/phaser-orders')
        self.assertIn('timed out', str(ctx.exception).lower())

    # -------------------------------------------------------------------------
    # Convenience methods
    # -------------------------------------------------------------------------
    @patch('requests.Session.request')
    def test_get_jobs_with_parts_adds_param(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'jobs': []}
        mock_request.return_value = mock_resp

        self.client.get_jobs_with_parts()
        call_kwargs = mock_request.call_args
        params = call_kwargs[1].get('params') or call_kwargs[0][3] if len(call_kwargs[0]) > 3 else {}
        # job_parts=true must be in params
        self.assertIn('job_parts', str(call_kwargs))

    @patch('requests.Session.request')
    def test_export_phaser_orders_sends_ids(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'message': 'exported'}
        mock_request.return_value = mock_resp

        self.client.export_phaser_orders([1, 2, 3])
        call_json = mock_request.call_args[1].get('json', {})
        self.assertEqual(call_json.get('ids'), [1, 2, 3])
