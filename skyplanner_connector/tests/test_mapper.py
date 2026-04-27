# -*- coding: utf-8 -*-
"""
Tests for services/mapper.py

Pure data transformation — no API calls, no mocks needed.
Run: odoo-bin -i skyplanner_connector --test-enable --test-tags=skyplanner_mapper
"""
from datetime import datetime
from unittest.mock import MagicMock, PropertyMock, patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.skyplanner_connector.services.mapper import (
    SkyPlannerMapper,
    _fmt_dt,
)


@tagged('skyplanner_mapper', 'skyplanner_connector')
class TestDateFormatter(TransactionCase):
    """Test _fmt_dt helper."""

    def test_formats_datetime(self):
        dt = datetime(2025, 6, 15, 10, 30, 0)
        self.assertEqual(_fmt_dt(dt), '2025-06-15 10:30:00')

    def test_returns_none_for_falsy(self):
        self.assertIsNone(_fmt_dt(None))
        self.assertIsNone(_fmt_dt(False))
        self.assertIsNone(_fmt_dt(''))


@tagged('skyplanner_mapper', 'skyplanner_connector')
class TestExtractPlannedDates(TransactionCase):
    """
    Critical: extract_planned_dates must use min(starts) / max(ends).
    NEVER assume first part = earliest.
    """

    def setUp(self):
        super().setUp()
        self.mapper = SkyPlannerMapper(self.env)

    def _make_job(self, parts):
        return {'job_parts': parts}

    def _part(self, start, end, planned=True):
        return {
            'is_planned': planned,
            'planned_start_time': start,
            'planned_end_time': end,
            'planned_duration': 3600,
        }

    # ---- Happy path ----
    def test_single_part(self):
        job = self._make_job([
            self._part('2025-06-15 08:00:00', '2025-06-15 10:00:00'),
        ])
        start, end = self.mapper.extract_planned_dates(job)
        self.assertEqual(start, '2025-06-15 08:00:00')
        self.assertEqual(end, '2025-06-15 10:00:00')

    def test_multiple_parts_takes_min_start_max_end(self):
        """Must not return first part's times — use min/max across all parts."""
        job = self._make_job([
            self._part('2025-06-15 10:00:00', '2025-06-15 12:00:00'),  # part 1
            self._part('2025-06-15 08:00:00', '2025-06-15 14:00:00'),  # part 2 — earliest start, latest end
            self._part('2025-06-15 09:00:00', '2025-06-15 11:00:00'),  # part 3
        ])
        start, end = self.mapper.extract_planned_dates(job)
        # min start = part 2
        self.assertEqual(start, '2025-06-15 08:00:00')
        # max end = part 2
        self.assertEqual(end, '2025-06-15 14:00:00')

    def test_first_part_NOT_earliest_start(self):
        """
        Explicit regression test: first part has LATER start than second part.
        SkyPlanner doc warns this is possible.
        """
        job = self._make_job([
            self._part('2025-06-15 14:00:00', '2025-06-15 16:00:00'),  # first but latest
            self._part('2025-06-15 06:00:00', '2025-06-15 08:00:00'),  # second but earliest
        ])
        start, end = self.mapper.extract_planned_dates(job)
        self.assertEqual(start, '2025-06-15 06:00:00')  # must NOT return 14:00
        self.assertEqual(end, '2025-06-15 16:00:00')

    def test_skips_unplanned_parts(self):
        """Parts with is_planned=False must be excluded."""
        job = self._make_job([
            self._part('2025-06-15 01:00:00', '2025-06-15 02:00:00', planned=False),
            self._part('2025-06-15 08:00:00', '2025-06-15 10:00:00', planned=True),
        ])
        start, end = self.mapper.extract_planned_dates(job)
        self.assertEqual(start, '2025-06-15 08:00:00')
        self.assertNotEqual(start, '2025-06-15 01:00:00')

    def test_empty_parts_returns_job_level_fallback(self):
        job = {
            'job_parts': [],
            'start_time': '2025-06-15 09:00:00',
            'end_time': '2025-06-15 17:00:00',
        }
        start, end = self.mapper.extract_planned_dates(job)
        self.assertEqual(start, '2025-06-15 09:00:00')
        self.assertEqual(end, '2025-06-15 17:00:00')

    def test_no_parts_key_returns_none(self):
        start, end = self.mapper.extract_planned_dates({})
        self.assertIsNone(start)
        self.assertIsNone(end)

    # ---- Workstation extraction ----
    def test_get_planned_workstation_id(self):
        job = self._make_job([
            {'is_planned': False, 'planned_workstation_id': 99},
            {'is_planned': True, 'planned_workstation_id': 64},
            {'is_planned': True, 'planned_workstation_id': 65},
        ])
        ws_id = self.mapper.get_planned_workstation_id(job)
        self.assertEqual(ws_id, 64)  # first planned

    def test_get_planned_workstation_returns_none_if_none_planned(self):
        job = self._make_job([
            {'is_planned': False, 'planned_workstation_id': 99},
        ])
        ws_id = self.mapper.get_planned_workstation_id(job)
        self.assertIsNone(ws_id)


@tagged('skyplanner_mapper', 'skyplanner_connector')
class TestBuildPhaserOrder(TransactionCase):
    """Tests for build_phaser_order payload construction."""

    def setUp(self):
        super().setUp()
        # Set a default customer ID so we don't need partner mapping
        self.env['ir.config_parameter'].sudo().set_param(
            'skyplanner.default_customer_id', '99'
        )
        self.mapper = SkyPlannerMapper(self.env)

    def test_required_fields_present(self):
        """production_planning_customer_id and number are required."""
        production = MagicMock()
        production.name = 'MO/2025/001'
        production.partner_id = False
        production.product_id.display_name = 'Product A'
        production.date_deadline = None
        production.date_start = None

        payload = self.mapper.build_phaser_order(production)
        self.assertIn('production_planning_customer_id', payload)
        self.assertIn('number', payload)
        self.assertEqual(payload['number'], 'MO/2025/001')
        self.assertEqual(payload['production_planning_customer_id'], 99)

    def test_no_customer_raises_value_error(self):
        """Must raise ValueError if no customer mapping and no default."""
        self.env['ir.config_parameter'].sudo().set_param(
            'skyplanner.default_customer_id', '0'
        )
        mapper = SkyPlannerMapper(self.env)
        production = MagicMock()
        production.name = 'MO/001'
        production.partner_id = False

        with self.assertRaises(ValueError) as ctx:
            mapper.build_phaser_order(production)
        self.assertIn('customer', str(ctx.exception).lower())


@tagged('skyplanner_mapper', 'skyplanner_connector')
class TestValidateWorkcenter(TransactionCase):
    """Tests for workcenter validation before phaser-job build."""

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param(
            'skyplanner.default_customer_id', '99'
        )
        self.mapper = SkyPlannerMapper(self.env)

    def _make_workcenter(self, ws_id=0, stage_id=0):
        wc = MagicMock()
        wc.name = 'Test Workcenter'
        wc.skyplanner_workstation_id = ws_id
        wc.skyplanner_workstage_id = stage_id
        return wc

    def test_raises_if_no_workstation_id(self):
        wc = self._make_workcenter(ws_id=0, stage_id=5)
        with self.assertRaises(ValueError) as ctx:
            self.mapper._validate_workcenter(wc)
        self.assertIn('Workstation ID', str(ctx.exception))

    def test_raises_if_no_workstage_id(self):
        wc = self._make_workcenter(ws_id=7, stage_id=0)
        with self.assertRaises(ValueError) as ctx:
            self.mapper._validate_workcenter(wc)
        self.assertIn('Workstage ID', str(ctx.exception))

    def test_raises_both_errors_in_one_message(self):
        wc = self._make_workcenter(ws_id=0, stage_id=0)
        with self.assertRaises(ValueError) as ctx:
            self.mapper._validate_workcenter(wc)
        msg = str(ctx.exception)
        self.assertIn('Workstation', msg)
        self.assertIn('Workstage', msg)

    def test_passes_when_both_set(self):
        wc = self._make_workcenter(ws_id=7, stage_id=5)
        # Should not raise
        self.mapper._validate_workcenter(wc)


@tagged('skyplanner_mapper', 'skyplanner_connector')
class TestBuildPhaserJob(TransactionCase):
    """Tests for build_phaser_job payload construction."""

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param(
            'skyplanner.default_customer_id', '99'
        )
        self.mapper = SkyPlannerMapper(self.env)

    def _make_workorder(self, ws_id=7, stage_id=5, duration_min=60):
        wo = MagicMock()
        wo.id = 42
        wo.name = 'Welding'
        wo.production_id.name = 'MO/2025/001'
        wo.duration_expected = duration_min
        wo.date_start = None
        wo.workcenter_id.name = 'Welding Station'
        wo.workcenter_id.skyplanner_workstation_id = ws_id
        wo.workcenter_id.skyplanner_workstage_id = stage_id
        return wo

    def test_required_fields_present(self):
        wo = self._make_workorder()
        payload = self.mapper.build_phaser_job(wo, phaser_order_row_id=10, order_number=1)
        self.assertEqual(payload['phaser_order_row_id'], 10)
        self.assertEqual(payload['phaser_workstage_id'], 5)
        self.assertEqual(payload['workstations'], '7')
        self.assertEqual(payload['order_number'], 1)

    def test_duration_converted_minutes_to_seconds(self):
        wo = self._make_workorder(duration_min=90)
        payload = self.mapper.build_phaser_job(wo, phaser_order_row_id=10)
        self.assertEqual(payload['duration'], 5400.0)  # 90 * 60

    def test_default_duration_when_zero(self):
        wo = self._make_workorder(duration_min=0)
        payload = self.mapper.build_phaser_job(wo, phaser_order_row_id=10)
        # fallback: 60 minutes = 3600 seconds
        self.assertEqual(payload['duration'], 3600.0)

    def test_workstations_is_string_not_int(self):
        """SkyPlanner requires comma-separated string, not integer."""
        wo = self._make_workorder(ws_id=64)
        payload = self.mapper.build_phaser_job(wo, phaser_order_row_id=10)
        self.assertIsInstance(payload['workstations'], str)
        self.assertEqual(payload['workstations'], '64')
