# -*- coding: utf-8 -*-
"""
Tests for services/planner.py

Uses mock API client — no live SkyPlanner required.
Run: odoo-bin -i skyplanner_connector --test-enable --test-tags=skyplanner_planner
"""
from unittest.mock import MagicMock, patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('skyplanner_planner', 'skyplanner_connector')
class TestWriteBack(TransactionCase):
    """
    Tests for mrp.workorder.skyplanner_apply_dates()

    Core rules tested:
      1. state in (progress, done) → never overwrite
      2. stale version → skip
      3. only date fields written — not state/qty
    """

    def setUp(self):
        super().setUp()
        # Create minimal mrp data
        self.product = self.env['product.product'].create({
            'name': 'Test Product',
            'type': 'consu',
        })
        self.bom = self.env['mrp.bom'].create({
            'product_id': self.product.id,
            'product_tmpl_id': self.product.product_tmpl_id.id,
            'product_qty': 1.0,
        })
        self.workcenter = self.env['mrp.workcenter'].create({
            'name': 'Test WC',
            'time_efficiency': 100,
        })
        self.production = self.env['mrp.production'].create({
            'product_id': self.product.id,
            'product_qty': 1.0,
            'bom_id': self.bom.id,
        })

    def _create_workorder(self, state='pending'):
        wo = self.env['mrp.workorder'].create({
            'name': 'Test WO',
            'production_id': self.production.id,
            'workcenter_id': self.workcenter.id,
            'product_uom_id': self.product.uom_id.id,
            'state': state,
        })
        return wo

    # ---- Rule 1: state protection ----
    def test_progress_state_not_overwritten(self):
        """WO in progress must never have dates overwritten."""
        wo = self._create_workorder(state='progress')
        original_start = wo.date_start

        result = wo.skyplanner_apply_dates(
            start='2025-06-15 08:00:00',
            end='2025-06-15 10:00:00',
            incoming_version=1,
        )
        self.assertFalse(result)
        self.assertEqual(wo.date_start, original_start)

    def test_done_state_not_overwritten(self):
        """WO in done must never have dates overwritten."""
        wo = self._create_workorder(state='done')
        result = wo.skyplanner_apply_dates(
            start='2025-06-15 08:00:00',
            end='2025-06-15 10:00:00',
            incoming_version=1,
        )
        self.assertFalse(result)

    # ---- Rule 2: version protection ----
    def test_stale_version_skipped(self):
        """Incoming version older than stored must be skipped."""
        wo = self._create_workorder(state='ready')
        wo.skyplanner_plan_version = 5  # current version

        result = wo.skyplanner_apply_dates(
            start='2025-06-15 08:00:00',
            end='2025-06-15 10:00:00',
            incoming_version=3,  # older — stale
        )
        self.assertFalse(result)

    def test_same_version_also_skipped(self):
        """Same version (not newer) must also be skipped."""
        wo = self._create_workorder(state='ready')
        wo.skyplanner_plan_version = 5
        result = wo.skyplanner_apply_dates(
            start='2025-06-15 08:00:00',
            end='2025-06-15 10:00:00',
            incoming_version=5,  # same — not newer
        )
        self.assertFalse(result)

    # ---- Rule 3: correct fields written ----
    def test_dates_written_for_pending_wo(self):
        """Pending WO: planned dates must be updated."""
        wo = self._create_workorder(state='pending')
        result = wo.skyplanner_apply_dates(
            start='2025-06-15 08:00:00',
            end='2025-06-15 10:00:00',
            incoming_version=1,
        )
        self.assertTrue(result)
        # Check that skyplanner_planned_start was updated
        self.assertTrue(wo.skyplanner_planned_start)
        self.assertTrue(wo.skyplanner_planned_end)

    def test_version_incremented_after_apply(self):
        wo = self._create_workorder(state='pending')
        wo.skyplanner_plan_version = 2
        wo.skyplanner_apply_dates(
            start='2025-06-15 08:00:00',
            end='2025-06-15 10:00:00',
            incoming_version=3,
        )
        self.assertEqual(wo.skyplanner_plan_version, 3)

    def test_state_never_written(self):
        """write-back must never force state to progress or done."""
        wo = self._create_workorder(state='ready')
        wo.skyplanner_apply_dates(
            start='2025-06-15 08:00:00',
            end='2025-06-15 10:00:00',
            incoming_version=1,
        )
        # Odoo 18 may recompute state via its own state machine when dates change,
        # but write-back must never force state to a terminal/active value.
        self.assertNotIn(wo.state, ('progress', 'done'))


@tagged('skyplanner_planner', 'skyplanner_connector')
class TestSkyPlannerMapping(TransactionCase):
    """Tests for skyplanner.mapping model helpers."""

    def setUp(self):
        super().setUp()
        self.Mapping = self.env['skyplanner.mapping']

    def test_set_and_get_mapping(self):
        self.Mapping.set_mapping(
            'mrp.production', 42, 'phaser_order', 100, external_id='MO001'
        )
        result = self.Mapping.get_skyplanner_id('mrp.production', 42, 'phaser_order')
        self.assertEqual(result, 100)

    def test_upsert_updates_existing(self):
        self.Mapping.set_mapping('mrp.production', 42, 'phaser_order', 100)
        self.Mapping.set_mapping('mrp.production', 42, 'phaser_order', 200)  # update
        result = self.Mapping.get_skyplanner_id('mrp.production', 42, 'phaser_order')
        self.assertEqual(result, 200)  # must be updated

        # Only one record must exist (upsert, not duplicate)
        count = self.Mapping.search_count([
            ('odoo_model', '=', 'mrp.production'),
            ('odoo_id', '=', 42),
            ('mapping_type', '=', 'phaser_order'),
        ])
        self.assertEqual(count, 1)

    def test_get_missing_returns_false(self):
        result = self.Mapping.get_skyplanner_id('mrp.production', 999, 'phaser_order')
        self.assertFalse(result)

    def test_different_types_independent(self):
        """phaser_job and planning_job IDs must not collide."""
        self.Mapping.set_mapping('mrp.workorder', 1, 'phaser_job', 50)
        self.Mapping.set_mapping('mrp.workorder', 1, 'planning_job', 999)

        phaser = self.Mapping.get_skyplanner_id('mrp.workorder', 1, 'phaser_job')
        planning = self.Mapping.get_skyplanner_id('mrp.workorder', 1, 'planning_job')
        self.assertEqual(phaser, 50)
        self.assertEqual(planning, 999)
        self.assertNotEqual(phaser, planning)
