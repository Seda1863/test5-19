# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # -------------------------------------------------------------------------
    # SkyPlanner API Configuration
    # Stored as ir.config_parameter (system parameters)
    # -------------------------------------------------------------------------
    skyplanner_api_token = fields.Char(
        string='API Token',
        config_parameter='skyplanner.api_token',
        help='Authorization-Token header value. Get from SkyPlanner support.',
    )
    skyplanner_base_url = fields.Char(
        string='Base URL',
        config_parameter='skyplanner.base_url',
        default='https://demo.skyplanner.app/production-planning/api/v3',
        help='https://{site}.skyplanner.app/production-planning/api/v3',
    )
    skyplanner_default_customer_id = fields.Integer(
        string='Default Customer ID (SkyPlanner)',
        config_parameter='skyplanner.default_customer_id',
        help='SkyPlanner internal customer ID used when no match found on MO.',
    )
    skyplanner_auto_export = fields.Boolean(
        string='Auto Export after Push',
        config_parameter='skyplanner.auto_export',
        default=False,
        help=(
            'Automatically call /phaser-orders/export after pushing MO to SkyPlanner. '
            'Disable if you want to batch-export manually.'
        ),
    )
    skyplanner_timeout = fields.Integer(
        string='API Timeout (sec)',
        config_parameter='skyplanner.timeout',
        default=30,
    )
