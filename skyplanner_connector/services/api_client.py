# -*- coding: utf-8 -*-
"""
SkyPlanner API Client

Authentication: Authorization-Token header (NOT Authorization: Bearer)
Base URL: https://{site}.skyplanner.app/production-planning/api/v3/

Error handling:
  4xx → log + skip (not retryable, except 401/403)
  5xx → retryable
  timeout → retryable
"""
import json
import logging
import time

import requests
from requests.exceptions import RequestException, Timeout

from odoo import _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# HTTP status codes that should not be retried
_NON_RETRYABLE = {400, 404, 409, 422}


class SkyPlannerAPIError(Exception):
    """Raised on SkyPlanner API errors."""

    def __init__(self, message, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
        # 4xx (except 401/403) = skip, not retry
        self.is_retryable = status_code not in _NON_RETRYABLE if status_code else True

    def __str__(self):
        base = super().__str__()
        if self.status_code:
            return f'[HTTP {self.status_code}] {base}'
        return base


class SkyPlannerClient:
    """
    Thin REST client for SkyPlanner API v3.

    Usage:
        client = SkyPlannerClient.from_env(env)
        response = client.post('/phaser-orders', payload)

    All methods return parsed JSON dict.
    All errors raise SkyPlannerAPIError.
    """

    def __init__(self, base_url, api_token, timeout=30):
        if not api_token:
            raise UserError(_(
                'SkyPlanner API Token is not configured. '
                'Go to Settings → SkyPlanner APS and enter the token.'
            ))
        if not base_url:
            raise UserError(_('SkyPlanner Base URL is not configured.'))

        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._session = requests.Session()
        # Critical: Authorization-Token (not Bearer)
        self._session.headers.update({
            'Authorization-Token': api_token,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        })

    # -------------------------------------------------------------------------
    # Factory
    # -------------------------------------------------------------------------
    @classmethod
    def from_env(cls, env):
        """Build client from Odoo ir.config_parameter."""
        get_param = env['ir.config_parameter'].sudo().get_param
        return cls(
            base_url=get_param('skyplanner.base_url', ''),
            api_token=get_param('skyplanner.api_token', ''),
            timeout=int(get_param('skyplanner.timeout', 30)),
        )

    # -------------------------------------------------------------------------
    # Core HTTP methods
    # -------------------------------------------------------------------------
    def _request(self, method, endpoint, params=None, data=None):
        url = f'{self.base_url}/{endpoint.lstrip("/")}'
        start = time.monotonic()
        try:
            resp = self._session.request(
                method=method,
                url=url,
                params=params,
                json=data,
                timeout=self.timeout,
            )
        except Timeout:
            duration_ms = int((time.monotonic() - start) * 1000)
            _logger.error('SkyPlanner timeout: %s %s (%dms)', method, url, duration_ms)
            raise SkyPlannerAPIError(
                f'Request timed out after {self.timeout}s: {method} {endpoint}',
            )
        except RequestException as exc:
            _logger.error('SkyPlanner network error: %s', exc)
            raise SkyPlannerAPIError(f'Network error: {exc}')

        duration_ms = int((time.monotonic() - start) * 1000)
        _logger.debug(
            'SkyPlanner %s %s → %d (%dms)',
            method, endpoint, resp.status_code, duration_ms,
        )

        return self._handle_response(resp, method, endpoint, duration_ms)

    def _handle_response(self, resp, method, endpoint, duration_ms):
        body = None
        try:
            body = resp.json()
        except ValueError:
            body = resp.text

        if resp.status_code == 200:
            return body, duration_ms

        if resp.status_code == 401:
            raise SkyPlannerAPIError(
                'Authentication failed — check Authorization-Token in Settings.',
                status_code=401,
                response_body=body,
            )
        if resp.status_code == 403:
            raise SkyPlannerAPIError(
                'Access denied (403). For ai-actions/schedule: contact SkyPlanner support '
                'to enable API scheduling.',
                status_code=403,
                response_body=body,
            )
        if resp.status_code in _NON_RETRYABLE:
            msg = body if isinstance(body, str) else json.dumps(body)
            _logger.warning(
                'SkyPlanner %s %s → %d (skip, not retryable): %s',
                method, endpoint, resp.status_code, msg[:300],
            )
            raise SkyPlannerAPIError(
                f'Request rejected: {msg[:300]}',
                status_code=resp.status_code,
                response_body=body,
            )
        # 5xx or unexpected
        raise SkyPlannerAPIError(
            f'Server error {resp.status_code}: {str(body)[:300]}',
            status_code=resp.status_code,
            response_body=body,
        )

    # -------------------------------------------------------------------------
    # Public HTTP verbs
    # -------------------------------------------------------------------------
    def get(self, endpoint, params=None):
        data, _ = self._request('GET', endpoint, params=params)
        return data

    def post(self, endpoint, data=None):
        result, duration_ms = self._request('POST', endpoint, data=data)
        return result, duration_ms

    def put(self, endpoint, data=None):
        result, duration_ms = self._request('PUT', endpoint, data=data)
        return result, duration_ms

    def delete(self, endpoint, data=None):
        result, duration_ms = self._request('DELETE', endpoint, data=data)
        return result, duration_ms

    # -------------------------------------------------------------------------
    # Convenience methods
    # -------------------------------------------------------------------------
    def get_jobs_with_parts(self, params=None):
        """GET /jobs?job_parts=true — required for planned dates."""
        p = dict(params or {})
        p['job_parts'] = 'true'
        return self.get('/jobs', params=p)

    def export_phaser_orders(self, order_ids):
        """POST /phaser-orders/export — REQUIRED before schedule."""
        result, duration_ms = self.post(
            '/phaser-orders/export',
            {'ids': order_ids},
        )
        return result, duration_ms

    def schedule(self, phaser_order_ids=None, phaser_job_ids=None):
        """
        POST /ai-actions/schedule
        NOTE: disabled by default — contact SkyPlanner support.
        """
        payload = {}
        if phaser_order_ids:
            payload['phaser_order_ids'] = phaser_order_ids
        if phaser_job_ids:
            payload['phaser_job_ids'] = phaser_job_ids
        result, duration_ms = self.post('/ai-actions/schedule', payload)
        return result, duration_ms

    def get_phaser_jobs_for_order(self, phaser_order_id):
        """GET /phaser-jobs?phaser_order_row_id= ... via contain."""
        return self.get('/phaser-jobs', params={
            'contain': 'phaser-order-rows,jobs,job-parts',
            'limit': 200,
        })
