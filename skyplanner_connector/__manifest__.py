# -*- coding: utf-8 -*-
{
    'name': 'SkyPlanner APS Connector',
    'version': '19.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Odoo MRP ↔ SkyPlanner APS — finite capacity scheduling',
    'description': """
SkyPlanner APS Connector
========================

Integrates Odoo 18/19 Manufacturing (MRP) with SkyPlanner APS for
finite capacity scheduling.

Core flow:
  1. Sync workcenters → SkyPlanner /workstations
  2. Push MO → /phaser-orders → /phaser-order-rows → /phaser-jobs
  3. Export → /phaser-orders/export (mandatory before scheduling)
  4. Schedule → /ai-actions/schedule (requires SkyPlanner support activation)
  5. Fetch plan → GET /jobs?job_parts=true
  6. Apply dates → mrp.workorder.date_start/date_finished

Design rules (enforced in code):
  - SkyPlanner = planning only. Odoo = execution source of truth.
  - State (progress/done) work orders: never overwrite.
  - Default: simulate. Apply: explicit user action only, never cron.
  - All API calls logged. Silent fail: YASAK.
  - Authentication: Authorization-Token header (not Bearer).

Installation:
  Requires: Python requests library.
  """,
    'author': 'MindDX',
    'website': 'https://www.minddx.com',
    'depends': [
        'mrp',
    ],
    'data': [
        # 1. Security first
        'security/skyplanner_groups.xml',
        'security/ir.model.access.csv',

        # 2. Config defaults
        'data/skyplanner_config_data.xml',

        # 3. Views
        'views/res_config_settings_views.xml',
        'views/mrp_workcenter_views.xml',
        'views/mrp_production_views.xml',
        'views/skyplanner_mapping_views.xml',
        'views/skyplanner_sync_log_views.xml',

        # 4. Wizard
        'wizard/skyplanner_simulate_views.xml',

        # 5. Menu last (depends on actions above)
        'views/skyplanner_menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
    'external_dependencies': {
        'python': ['requests'],
    },
}
